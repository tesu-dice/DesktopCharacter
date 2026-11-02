"""
Googleカレンダー・Googleタスクの情報を取得し、JSONキャッシュとして保存するコレクター。

設計方針: docs/開発ログ/202608_カレンダー連携/GoogleCalendar連携_設計方針.md
認証情報の保持: docs/開発予定/202610_GCalの認証情報保持/（要件定義・詳細設計）

- 認証は起動時に一度だけ試行する（application start の購読から、バックグラウンドで実行）。
- 承認後のトークンは oauth_token.json に保存し、次回からは自動で連携する
  （設定「毎回承認する」がオンのときは保存せず、起動時に残っているトークンも削除する）。
- 権限（Permission.get_calendar_info）と「毎回承認する」は起動時の値を写し取って使い、
  起動中に設定を変えても扱いは変わらない（main.pyは権限を見ずに Req_CalendarInfo を発行する）。
- 失敗は5つに分類し（client_secret.json / 承認できず / トークン無効 / 通信エラー / API無効）、
  分類ごとのメッセージは Req_PopUpMessage で直接表示する。起動時の結果は OnCalendarStartupStatus で1回だけ通知する。
- 取得したカレンダー情報は google_calendar_cache.json に上書き保存する。
- ai_tools/get_calendar_info_tool.py はこのキャッシュファイルを読むだけで、
  このクラスのインスタンスを直接参照しない（Tool側の無引数インスタンス化制約のため）。
"""
import os
import json
import threading
import datetime
import logging
from typing import Optional, Dict, Any, List, Set, Tuple

import httplib2
from google.auth.exceptions import RefreshError, TransportError
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from oauthlib.oauth2.rfc6749.errors import AccessDeniedError

from services.config_controller import UserSettings
from services.Event_Bus import EventBus

logger = logging.getLogger(__name__)

# スコープ設定（旧 collectors/GoogleCalendarAPI.py から移植）
# 読み取り専用への変更はユーザーが行う。アプリ側は「この権限がトークンに含まれているか」だけを見る。
SCOPES = [
    "https://www.googleapis.com/auth/calendar",
    "https://www.googleapis.com/auth/tasks",
]
CLIENT_SECRET_FILENAME = "client_secret.json"
CACHE_FILENAME = "google_calendar_cache.json"
TOKEN_FILENAME = "oauth_token.json"

APPROVAL_TIMEOUT_SECONDS = 300      # ブラウザでの承認待ち
STARTUP_STATUS_WAIT_SECONDS = 60    # 起動時メッセージが結果を待つ時間

# RefreshError のうち、トークンが無効（分類3）とみなすエラーコード。これ以外は通信エラー（分類4）扱い
INVALID_TOKEN_ERROR_CODES = {"invalid_grant", "invalid_client", "unauthorized_client"}

# HttpError の理由（reason）による振り分け
API_DISABLED_REASONS = {"accessNotConfigured", "SERVICE_DISABLED"}
RATE_LIMIT_REASONS = {"rateLimitExceeded", "userRateLimitExceeded", "dailyLimitExceeded",
                      "quotaExceeded", "RATE_LIMIT_EXCEEDED"}
INSUFFICIENT_SCOPE_REASONS = {"insufficientPermissions", "ACCESS_TOKEN_SCOPE_INSUFFICIENT"}

POPUP_TITLE = "Googleカレンダー連携"
SERVICE_DISPLAY_NAMES = {"calendar": "Google Calendar API", "tasks": "Google Tasks API"}


class StartupStatus:
    """OnCalendarStartupStatus で渡す起動時の状態。失敗の分類もこの値で表す。"""
    OFF = "off"
    SUCCESS = "success"
    WAITING = "waiting"                # 1分の時点でブラウザでの承認待ち
    CONNECTING = "connecting"          # 1分の時点でブラウザは開いていないが処理中
    CLIENT_SECRET = "client_secret"    # 分類1
    NOT_APPROVED = "not_approved"      # 分類2
    INVALID_TOKEN = "invalid_token"    # 分類3（起動時の状態としてはまれ）
    NETWORK = "network"                # 分類4
    API_DISABLED = "api_disabled"      # 分類5


class GoogleCalendarCollector:
    """
    Googleカレンダー/タスクの認証・トークンの保存・API取得・JSONキャッシュ書き込みを担うクラス。
    services/WindowsInfoCollecter.py の win_info_collector と同様に、
    bus / setting をコンストラクタで受け取る。
    """

    def __init__(self, bus: EventBus, setting: UserSettings, app_dir: str, debug: int = -1):
        self.bus = bus
        self.setting = setting
        self.app_dir = app_dir
        self.debug = debug
        self.cache_path = os.path.join(app_dir, CACHE_FILENAME)
        self.token_path = os.path.join(app_dir, TOKEN_FILENAME)

        self.calendar_service = None
        self.tasks_service = None
        # auth_state: "disabled" | "not_started" | "in_progress" | "authenticated" | "failed"
        self.auth_state = "not_started"
        self._auth_lock = threading.Lock()
        # 取得全体を直列にする（googleapiclientが使うhttplib2はスレッドセーフではないため）
        self._fetch_lock = threading.Lock()

        # 起動時メッセージ向けの状態（OnCalendarStartupStatus を1回だけ発行する）
        self._waiting_for_browser = False
        self._status_lock = threading.Lock()
        self._startup_status_published = False
        self._startup_timer: Optional[threading.Timer] = None
        # この起動で表示したメッセージの分類（同じ分類は1回の起動につき1回まで）
        self._notified: Set[str] = set()

        if debug >= 0:
            indent = "  " * debug
            print(f"{indent}GoogleCalendarCollector.__init__() called.")

        # 起動時に古いキャッシュを削除（安全性のため）
        self.clear_cache()

        # 権限と「毎回承認する」は起動時の値を写し取り、以降は設定を見ない
        # （設定のオブジェクトは設定画面と共有されており、保存するとその場で中身が変わるため）
        self._permission = setting.get_setting_value("ApplicationSettings.Permission.get_calendar_info") == True
        self._approve_every_start = setting.get_setting_value("ApplicationSettings.GoogleCalendar.ApproveEveryStart", False) == True

        if not self._permission:
            self.auth_state = "disabled"
            self._delete_token()
            if debug >= 0:
                indent = "  " * debug
                print(f"{indent}GoogleCalendarCollector: 権限オフのため無効化します。")
        elif self._approve_every_start:
            # 毎回承認する設定のため、前回までに保存されたトークンは使わずに削除する
            self._delete_token()

    def start(self, debug: int = -1):
        """
        application start の購読ハンドラ。認証を開始する。
        __init__で始めると、_setup_event_listeners の subscribe_when 登録より前に
        OnCalendarStartupStatus を発行してしまう場合があるため、ここで開始する。
        EventBusが別スレッドで呼ぶため、このスレッドのまま認証を進める。
        """
        if self.auth_state == "disabled":
            self._publish_startup_status(StartupStatus.OFF)
            return
        self._startup_timer = threading.Timer(STARTUP_STATUS_WAIT_SECONDS, self._on_startup_wait_timeout)
        self._startup_timer.daemon = True
        self._startup_timer.start()
        self._authenticate(debug=debug)

    def _authenticate(self, debug: int = -1):
        """
        起動時の認証。client_secret.jsonの確認 → 保存済みトークンの読み込み・更新
        → （なければ）ブラウザでの承認と保存 → サービスの作成 → すぐに1回取得 → 起動時の状態の発行。
        """
        with self._auth_lock:
            if self.auth_state == "in_progress":
                return
            self.auth_state = "in_progress"

        try:
            # 1. client_secret.json
            if not self._check_client_secret():
                self._handle_failure(StartupStatus.CLIENT_SECRET)
                return

            # 2. 保存済みのトークン（「毎回承認する」がオンなら__init__で削除済みのためNoneになる）
            creds = self._load_token()
            if creds is not None and not creds.valid:
                creds = self._refresh_on_startup(creds)

            # 3. ブラウザでの承認
            if creds is None:
                creds = self._run_browser_approval()
                if creds is None:
                    return
                if not self._approve_every_start:
                    self._save_token(creds)

            # 4. サービスの作成
            self.calendar_service = build("calendar", "v3", credentials=creds)
            self.tasks_service = build("tasks", "v1", credentials=creds)
            self.auth_state = "authenticated"
            logger.info("Googleカレンダーの認証に成功しました。")
            if debug >= 0:
                indent = "  " * debug
                print(f"{indent}GoogleCalendarCollector: 認証に成功しました。")

            # 5. すぐに1回取得する（起動直後にAIが予定を答えられるように）
            category = self._fetch_and_store(debug=debug)

            # 6. 起動時の状態（1分を過ぎていれば発行済み）
            status = StartupStatus.SUCCESS if category is None else category
            if not self._publish_startup_status(status) and status == StartupStatus.SUCCESS:
                logger.info("Googleカレンダーの連携に成功しました（起動時メッセージの表示後）。")
        except Exception as e:
            # 想定外のエラーは「承認できなかった」（分類2）として扱う
            logger.error(f"Googleカレンダーの認証中に想定外のエラーが発生しました: {type(e).__name__}")
            self._handle_failure(StartupStatus.NOT_APPROVED)

    def _check_client_secret(self) -> bool:
        """client_secret.jsonがあり、デスクトップアプリ等のクライアント情報として読めるかを確認する。"""
        client_secret_path = os.path.join(self.app_dir, CLIENT_SECRET_FILENAME)
        if not os.path.exists(client_secret_path):
            logger.warning(f"{CLIENT_SECRET_FILENAME}が見つかりません: {client_secret_path}")
            return False
        try:
            with open(client_secret_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, json.JSONDecodeError, UnicodeDecodeError) as e:
            logger.warning(f"{CLIENT_SECRET_FILENAME}を読めません: {type(e).__name__}")
            return False
        if not isinstance(data, dict) or ("installed" not in data and "web" not in data):
            logger.warning(f"{CLIENT_SECRET_FILENAME}の形式が正しくありません（installed/webの項目がありません）。")
            return False
        return True

    def _load_token(self) -> Optional[Credentials]:
        """
        oauth_token.jsonを読み込む。ない・読めない・使う権限が含まれていない場合はNone。
        Noneのときは呼び出し元がブラウザでの承認に進む（分類3はログのみ）。
        """
        if not os.path.exists(self.token_path):
            return None
        try:
            with open(self.token_path, "r", encoding="utf-8") as f:
                info = json.load(f)
        except (OSError, json.JSONDecodeError, UnicodeDecodeError) as e:
            logger.warning(f"保存済みのトークンを読めません（ブラウザでの承認に進みます）: {type(e).__name__}")
            return None
        if not isinstance(info, dict) or not self._has_required_scopes(info.get("scopes")):
            logger.warning("保存済みのトークンに使う権限が含まれていません（ブラウザでの承認に進みます）。")
            return None
        try:
            # scopesを渡すと保存されているスコープが上書きされ、不足を見落とすため渡さない
            return Credentials.from_authorized_user_info(info)
        except ValueError as e:
            logger.warning(f"保存済みのトークンに必要な項目がありません（ブラウザでの承認に進みます）: {type(e).__name__}")
            return None

    @staticmethod
    def _has_required_scopes(scopes) -> bool:
        """SCOPESがすべて含まれているかを返す。余分な権限があってもよい。"""
        if isinstance(scopes, str):
            granted = set(scopes.split())
        elif isinstance(scopes, (list, tuple, set)):
            granted = set(scopes)
        else:
            granted = set()
        return set(SCOPES) <= granted

    def _refresh_on_startup(self, creds: Credentials) -> Optional[Credentials]:
        """
        起動時に期限切れのトークンを更新する。更新したトークンはファイルに保存し直さない
        （リフレッシュトークンは変わらず、次回の起動時にまた更新すればよいため）。
        トークンが無効ならNone（ブラウザでの承認へ）、通信エラーならそのまま返す（次の取得でライブラリが再試行する）。
        """
        try:
            creds.refresh(Request())
            return creds
        except RefreshError as e:
            if self._classify_exception(e) == StartupStatus.INVALID_TOKEN:
                logger.warning(f"保存済みのトークンが無効です（ブラウザでの承認に進みます）: {self._refresh_error_summary(e)}")
                return None
            logger.warning(f"トークンを更新できませんでした（トークンを残して続けます）: {self._refresh_error_summary(e)}")
            return creds
        except (TransportError, OSError) as e:
            logger.warning(f"通信エラーのためトークンを更新できませんでした（トークンを残して続けます）: {type(e).__name__}")
            return creds

    def _run_browser_approval(self) -> Optional[Credentials]:
        """ブラウザでの承認（最長5分）。失敗したら分類2として処理し、Noneを返す。"""
        client_secret_path = os.path.join(self.app_dir, CLIENT_SECRET_FILENAME)
        flow = InstalledAppFlow.from_client_secrets_file(client_secret_path, SCOPES)
        self._waiting_for_browser = True
        try:
            creds = flow.run_local_server(port=0, access_type="offline", prompt="consent",
                                          timeout_seconds=APPROVAL_TIMEOUT_SECONDS)
        except AccessDeniedError:
            logger.warning("同意画面で承認が拒否されました。")
            self._handle_failure(StartupStatus.NOT_APPROVED)
            return None
        except Warning:
            # 一方だけ許可した場合、oauthlibはスコープの変化をWarningとして投げる
            logger.warning("カレンダーとタスクの一方だけが許可されました。")
            self._handle_failure(StartupStatus.NOT_APPROVED, detail="partial")
            return None
        except AttributeError:
            # タイムアウト時、ライブラリは受け取ったURL（None）に.replaceをかけてAttributeErrorを出す
            logger.warning(f"{APPROVAL_TIMEOUT_SECONDS}秒以内に承認されませんでした。")
            self._handle_failure(StartupStatus.NOT_APPROVED)
            return None
        except Exception as e:
            # 承認後のトークンの受け取りの通信エラー、ローカルのポートが使えない など
            logger.error(f"ブラウザでの承認に失敗しました: {type(e).__name__}")
            self._handle_failure(StartupStatus.NOT_APPROVED)
            return None
        finally:
            self._waiting_for_browser = False

        if not self._has_required_scopes(creds.scopes):
            logger.warning("承認されたトークンに使う権限が含まれていません。")
            self._handle_failure(StartupStatus.NOT_APPROVED, detail="partial")
            return None
        return creds

    def _save_token(self, creds: Credentials) -> None:
        """一時ファイルに書いてからos.replaceでtoken_pathに反映する。失敗してもログのみでその起動中は連携を続ける。"""
        tmp_path = self.token_path + ".tmp"
        try:
            with open(tmp_path, "w", encoding="utf-8") as f:
                f.write(creds.to_json())
            os.replace(tmp_path, self.token_path)
            logger.info("トークンを保存しました。")
        except OSError as e:
            logger.error(f"トークンを保存できませんでした（この起動中は連携を続けます）: {type(e).__name__}")

    def _delete_token(self) -> None:
        """token_path（と書き込み途中の一時ファイル）があれば削除する。"""
        for path in (self.token_path, self.token_path + ".tmp"):
            if os.path.exists(path):
                try:
                    os.remove(path)
                    logger.info(f"トークンを削除しました: {path}")
                except OSError as e:
                    logger.warning(f"トークンの削除に失敗しました: {path}, エラー: {type(e).__name__}")

    def is_available(self) -> bool:
        """認証済みかどうかを返す。"""
        return self.auth_state == "authenticated"

    def refresh_cache(self, debug: int = -1):
        """
        Req_CalendarInfo の購読ハンドラ本体。
        権限の判定はこのクラスが起動時の値で行う（main.pyは権限を見ずに Req_CalendarInfo を発行する）。
        認証済みでなければ何もしない（権限オフ・認証失敗時もここで止まる）。
        """
        if not self.is_available():
            return
        self._fetch_and_store(debug=debug)

    def _fetch_and_store(self, debug: int = -1) -> Optional[str]:
        """
        取得・キャッシュ書き込み・失敗の分類をまとめて行う。refresh_cache()と認証直後の取得の両方から呼ぶ。
        戻り値は失敗の分類（成功、またはログのみのエラーならNone）。
        """
        failures: List[Tuple[str, str]] = []   # (サービス名 "calendar"/"tasks"/"", 分類)
        with self._fetch_lock:
            try:
                data = self._fetch_events_and_tasks(failures)
                self._write_cache(data)
                if debug >= 0:
                    indent = "  " * debug
                    print(f"{indent}GoogleCalendarCollector._fetch_and_store(): "
                          f"events={len(data.get('events', []))}, tasks={len(data.get('tasks', []))}")
            except Exception as e:
                # RefreshError・通信エラーなど、カレンダーごとのtryで捕まえないもの
                category = self._classify_exception(e)
                if category is None:
                    logger.error(f"Googleカレンダー/タスクの取得で予期しないエラーが発生しました: {type(e).__name__}")
                    return None
                if isinstance(e, RefreshError):
                    logger.warning(f"Googleカレンダー/タスクの取得に失敗しました: {self._refresh_error_summary(e)}")
                else:
                    logger.warning(f"Googleカレンダー/タスクの取得に失敗しました: {type(e).__name__}")
                failures.append(("", category))

        # 分類の優先順位: トークン無効 → API無効 → 通信エラー
        categories = {c for _, c in failures}
        if StartupStatus.INVALID_TOKEN in categories:
            self._handle_failure(StartupStatus.INVALID_TOKEN)
            return StartupStatus.INVALID_TOKEN
        if StartupStatus.API_DISABLED in categories:
            services = {s for s, c in failures if c == StartupStatus.API_DISABLED}
            self._handle_failure(StartupStatus.API_DISABLED, detail=services)
            return StartupStatus.API_DISABLED
        if StartupStatus.NETWORK in categories:
            self._handle_failure(StartupStatus.NETWORK)
            return StartupStatus.NETWORK
        return None

    def _resolve_calendar_display_name(self, calendar_list_item: dict) -> str:
        """
        calendarList().list()の1件からカレンダーの表示名を決める。
        - summaryOverride（ユーザーが「マイカレンダー」画面で設定した表示名）があれば最優先。
        - primaryカレンダー（自分のアカウント自身のカレンダー）は、summaryOverrideが
          未設定だとsummaryがGoogleアカウントのメールアドレスになってしまうため、
          メールアドレスをそのままAIに渡さないよう固定の代替名にフォールバックする。
        - それ以外の所有カレンダー（"仕事"等）はsummaryがカレンダー名そのものなのでそのまま使う。
        """
        override = calendar_list_item.get("summaryOverride")
        if override:
            return override
        if calendar_list_item.get("primary"):
            return "メインカレンダー"
        return calendar_list_item.get("summary") or calendar_list_item.get("id") or "メインカレンダー"

    def _list_calendars(self, failures: List[Tuple[str, str]]) -> List[dict]:
        """
        calendarList().list()を全ページ分取得して返す。
        失敗時は取得できた分（なければ空リスト）を返し、取得エラーの分類はfailuresに追記する。
        """
        items: List[dict] = []
        try:
            page_token = None
            while True:
                result = self.calendar_service.calendarList().list(pageToken=page_token).execute()
                items.extend(result.get("items", []))
                page_token = result.get("nextPageToken")
                if not page_token:
                    break
        except HttpError as e:
            logger.warning(f"カレンダー一覧の取得に失敗しました: {e}")
            category = self._classify_http_error(e)
            if category is not None:
                failures.append(("calendar", category))
        return items

    def _resolve_calendar_ids(self, failures: List[Tuple[str, str]]) -> List[Dict[str, str]]:
        """
        取得対象のカレンダー一覧を決定する。
        設定 GoogleCalendar.CalendarIds（カンマ区切り・設定画面には非表示）が明示されていればそれを優先する。
        未設定なら calendarList().list() を呼び、accessRole=="owner"（＝Googleカレンダー
        画面の「マイカレンダー」欄に出る、自分が所有するカレンダー）を自動的に対象にする。
        「他のカレンダー」欄（共有カレンダー・購読カレンダー等、accessRoleがowner以外）は
        既定では含めない。含めたい場合はCalendarIdsで明示的にIDを追加する。
        取得エラーの分類はfailuresに追記する。
        """
        calendar_items = self._list_calendars(failures)

        override = self.setting.get_setting_value("ApplicationSettings.GoogleCalendar.CalendarIds", "")
        if isinstance(override, str) and override.strip():
            ids = [cid.strip() for cid in override.split(",") if cid.strip()]
            if ids:
                return self._resolve_override_calendars(ids, calendar_items)

        calendars: List[Dict[str, str]] = [
            {"id": item.get("id"), "summary": self._resolve_calendar_display_name(item)}
            for item in calendar_items if item.get("accessRole") == "owner"
        ]
        if not calendars:
            logger.warning("取得対象のカレンダーが見つからないため、primaryのみ取得します。")
            calendars = [{"id": "primary", "summary": "メインカレンダー"}]
        return calendars

    def _resolve_override_calendars(self, ids: List[str], calendar_items: List[dict]) -> List[Dict[str, str]]:
        """
        CalendarIdsで指定されたIDに表示名を付ける。IDはメールアドレスの場合があるため、AIにはそのまま渡さない。
        - calendarListにあるIDは、自動取得と同じく_resolve_calendar_display_nameで名前を決める。
        - "primary"はメインカレンダー（calendarListのprimary項目があればその名前）。
        - calendarListに見つからないIDは「カレンダー1」「カレンダー2」…の連番にする。
        """
        items_by_id = {item.get("id"): item for item in calendar_items}
        primary_item = next((item for item in calendar_items if item.get("primary")), None)

        calendars: List[Dict[str, str]] = []
        unknown_count = 0
        for cid in ids:
            item = items_by_id.get(cid)
            if item is None and cid == "primary":
                item = primary_item
            if item is not None:
                summary = self._resolve_calendar_display_name(item)
            elif cid == "primary":
                summary = "メインカレンダー"
            else:
                unknown_count += 1
                summary = f"カレンダー{unknown_count}"
            calendars.append({"id": cid, "summary": summary})
        return calendars

    def _fetch_events_and_tasks(self, failures: List[Tuple[str, str]]) -> dict:
        """
        FetchRangeDays設定から取得範囲を計算し、Google Calendar/Tasks APIを呼ぶ。
        取得した生データはフィールド選別のみ行い、時刻表示変換やテキスト整形は行わない
        （それらはai_tools/get_calendar_info_tool.py側の責務）。
        マイカレンダー内の複数カレンダーそれぞれに対して予定を取得し、1つのリストに統合する。
        取得エラーの分類はfailuresに追記する（一部が失敗しても他の取得は続ける）。
        """
        fetch_range_days = self.setting.get_setting_value("ApplicationSettings.GoogleCalendar.FetchRangeDays", 7)
        if not isinstance(fetch_range_days, int) or fetch_range_days <= 0:
            fetch_range_days = 7

        now = datetime.datetime.now().astimezone()
        time_min_dt = now - datetime.timedelta(days=1)
        time_max_dt = now + datetime.timedelta(days=fetch_range_days)

        calendars = self._resolve_calendar_ids(failures)
        events = []
        for cal in calendars:
            try:
                events_result = self.calendar_service.events().list(
                    calendarId=cal["id"],
                    timeMin=time_min_dt.isoformat(),
                    timeMax=time_max_dt.isoformat(),
                    singleEvents=True,
                    orderBy="startTime",
                ).execute()
            except HttpError as e:
                logger.warning(f"カレンダー'{cal['summary']}'の予定取得に失敗しました（他のカレンダーの取得は継続します）: {e}")
                category = self._classify_http_error(e)
                if category is not None:
                    failures.append(("calendar", category))
                continue
            raw_events = events_result.get("items", [])
            events.extend(self._trim_event_fields(e, calendar_summary=cal["summary"]) for e in raw_events)

        tasks = []
        try:
            tasklists = self.tasks_service.tasklists().list().execute()
            items = tasklists.get("items", [])
            if items:
                tasklist_id = items[0]["id"]
                tasks_result = self.tasks_service.tasks().list(tasklist=tasklist_id).execute()
                raw_tasks = tasks_result.get("items", [])
                tasks = [self._trim_task_fields(t) for t in raw_tasks]
        except HttpError as e:
            logger.warning(f"Googleタスクの取得に失敗しました（予定の取得は継続します）: {e}")
            category = self._classify_http_error(e)
            if category is not None:
                failures.append(("tasks", category))

        return {
            "fetched_at": now.isoformat(),
            "range": {
                "from": time_min_dt.date().isoformat(),
                "to": time_max_dt.date().isoformat(),
            },
            "calendars": [cal["summary"] for cal in calendars],
            "events": events,
            "tasks": tasks,
        }

    def _classify_exception(self, e: Exception) -> Optional[str]:
        """例外を失敗の分類に振り分ける（分類の判定はここと_classify_http_errorにまとめる）。Noneはログのみ。"""
        if isinstance(e, RefreshError):
            response_data = e.args[1] if len(e.args) > 1 else None
            if isinstance(response_data, dict) and response_data.get("error") in INVALID_TOKEN_ERROR_CODES:
                return StartupStatus.INVALID_TOKEN
            # Google側の一時的な5xxエラーなどでもRefreshErrorになるため、トークンは残す
            return StartupStatus.NETWORK
        if isinstance(e, HttpError):
            return self._classify_http_error(e)
        if isinstance(e, (TransportError, httplib2.HttpLib2Error, OSError)):
            return StartupStatus.NETWORK
        return None

    def _classify_http_error(self, e: HttpError) -> Optional[str]:
        """HttpErrorをステータスコードと理由（reason）で振り分ける。403だけではAPI無効と決めない。Noneはログのみ。"""
        status = e.status_code
        reasons = self._extract_http_error_reasons(e)
        if status == 403 and reasons & API_DISABLED_REASONS:
            return StartupStatus.API_DISABLED
        if status in (403, 429) and reasons & RATE_LIMIT_REASONS:
            return StartupStatus.NETWORK
        if status == 403 and reasons & INSUFFICIENT_SCOPE_REASONS:
            return StartupStatus.INVALID_TOKEN
        if isinstance(status, int) and status >= 500:
            return StartupStatus.NETWORK
        return None

    @staticmethod
    def _extract_http_error_reasons(e: HttpError) -> Set[str]:
        """
        応答本文のJSONから error.errors[].reason と error.details[].reason を集める。
        HttpError.error_details は details と errors の両方があると details しか持たず、
        HttpError.reason は理由ではなくメッセージ文のため、本文を直接読む。
        """
        reasons: Set[str] = set()
        try:
            content = e.content.decode("utf-8") if isinstance(e.content, bytes) else e.content
            data = json.loads(content)
        except (ValueError, TypeError, AttributeError):
            return reasons
        if isinstance(data, list) and data:
            data = data[0]
        error = data.get("error") if isinstance(data, dict) else None
        if not isinstance(error, dict):
            return reasons
        for key in ("errors", "details"):
            items = error.get(key)
            if isinstance(items, list):
                for item in items:
                    if isinstance(item, dict) and isinstance(item.get("reason"), str):
                        reasons.add(item["reason"])
        return reasons

    @staticmethod
    def _refresh_error_summary(e: RefreshError) -> str:
        """RefreshErrorのログ用の要約（"invalid_grant: ..."の形）。応答のJSON（args[1]）はそのまま出さない。"""
        return str(e.args[0]) if e.args else type(e).__name__

    def _handle_failure(self, category: str, detail: Any = "") -> None:
        """失敗の分類ごとの後始末（auth_state・メッセージ・起動時の状態）を行う。"""
        if category == StartupStatus.CLIENT_SECRET:
            self.auth_state = "failed"
            self._notify(category, f"{CLIENT_SECRET_FILENAME}が見つからないか、内容が正しくありません。\n"
                                   f"アプリと同じフォルダに{CLIENT_SECRET_FILENAME}を配置し直して、アプリを終了して起動し直してください。")
            self._publish_startup_status(category)
        elif category == StartupStatus.NOT_APPROVED:
            self.auth_state = "failed"
            if detail == "partial":
                message = ("カレンダーとタスクの一方だけが許可されました。\n"
                           "アプリを終了して起動し直し、承認の画面で両方にチェックを入れてください。")
            else:
                message = ("Googleでの承認が完了しませんでした。\n"
                           f"連携する場合は、アプリを終了して起動し直し、開いたブラウザの画面で{APPROVAL_TIMEOUT_SECONDS // 60}分以内に承認してください。")
            self._notify(category, message)
            self._publish_startup_status(category)
        elif category == StartupStatus.INVALID_TOKEN:
            # 起動中はブラウザを開かず、以降の取得を止める（次回の起動時に承認し直す）
            self.auth_state = "failed"
            self._notify(category, "Googleカレンダーとの連携が無効になりました（アクセスの取り消しなど）。\n"
                                   "連携し直す場合は、アプリを終了して起動し直してください。起動時にブラウザでの承認に進みます。")
        elif category == StartupStatus.API_DISABLED:
            names = "・".join(SERVICE_DISPLAY_NAMES.get(s, s) for s in sorted(detail)) if detail else "Google Calendar API・Google Tasks API"
            self._notify(category, "Googleカレンダーの予定を取得できませんでした。\n"
                                   f"GCPのプロジェクトで {names} が有効になっているか確認してください。")
        elif category == StartupStatus.NETWORK:
            # 自動で戻るため、メッセージは出さずログのみ（起動時は起動時メッセージに載る）
            logger.info("通信エラーのため、次回の取得で再試行します。")

    def _notify(self, category: str, message: str) -> None:
        """メッセージを表示する。同じ分類は1回の起動につき1回まで。"""
        if category in self._notified:
            return
        self._notified.add(category)
        self.bus.publish("Req_PopUpMessage", "warning", POPUP_TITLE, message)

    def _publish_startup_status(self, status: str) -> bool:
        """OnCalendarStartupStatus を1回だけ発行する。発行したらTrue、発行済みならFalse。"""
        with self._status_lock:
            if self._startup_status_published:
                return False
            self._startup_status_published = True
        if self._startup_timer is not None:
            self._startup_timer.cancel()
        self.bus.publish("OnCalendarStartupStatus", status)
        return True

    def _on_startup_wait_timeout(self) -> None:
        """起動から1分の時点で結果が出ていなければ、その時点の状態を発行する。"""
        status = StartupStatus.WAITING if self._waiting_for_browser else StartupStatus.CONNECTING
        self._publish_startup_status(status)

    def _trim_event_fields(self, raw_event: dict, calendar_summary: str = "") -> dict:
        """通信用ノイズフィールド（kind/etag/htmlLink/creator/organizer/sequence等）を除外する純粋関数。"""
        return {
            "id": raw_event.get("id"),
            "status": raw_event.get("status"),
            "summary": raw_event.get("summary", ""),
            "description": raw_event.get("description", ""),
            "location": raw_event.get("location", ""),
            "start": raw_event.get("start", {}),
            "end": raw_event.get("end", {}),
            "recurringEventId": raw_event.get("recurringEventId"),
            "calendarSummary": calendar_summary,
        }

    def _trim_task_fields(self, raw_task: dict) -> dict:
        """id/title/notes/status/due/completedのみを残す純粋関数。"""
        return {
            "id": raw_task.get("id"),
            "title": raw_task.get("title", ""),
            "notes": raw_task.get("notes", ""),
            "status": raw_task.get("status"),
            "due": raw_task.get("due"),
            "completed": raw_task.get("completed"),
        }

    def _write_cache(self, data: dict) -> None:
        """
        一時ファイルへ書いてからos.replaceでcache_pathに反映する。
        Tool側が読んでいる最中に不完全なJSONを掴まないためのアトミック書き込み。
        """
        tmp_path = self.cache_path + ".tmp"
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp_path, self.cache_path)

    def read_cache(self) -> Optional[Dict[str, Any]]:
        """cache_pathを読みJSONとして返す。存在しない/壊れている場合はNoneを返す。"""
        try:
            with open(self.cache_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError) as e:
            logger.debug(f"カレンダーキャッシュの読み込みに失敗しました: {self.cache_path}, エラー: {e}")
            return None

    def clear_cache(self) -> None:
        """cache_pathが存在すれば削除する。起動時（__init__）と終了時（myapp.exit()）の両方から呼ばれる。"""
        if os.path.exists(self.cache_path):
            try:
                os.remove(self.cache_path)
            except OSError as e:
                logger.warning(f"カレンダーキャッシュの削除に失敗しました: {self.cache_path}, エラー: {e}")

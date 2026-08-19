"""
Googleカレンダー・Googleタスクの情報を取得し、JSONキャッシュとして保存するコレクター。

設計方針: docs/開発予定/202608_カレンダー連携/GoogleCalendar連携_設計方針.md

- 認証は起動時に一度だけ試行する（バックグラウンドスレッド、非同期）。
- 認証トークンはファイルに保存しない（プロセスメモリ上にのみ保持）。
- 取得したカレンダー情報は google_calendar_cache.json に上書き保存する。
- ai_tools/get_calendar_info_tool.py はこのキャッシュファイルを読むだけで、
  このクラスのインスタンスを直接参照しない（Tool側の無引数インスタンス化制約のため）。
"""
import os
import json
import threading
import datetime
import logging
from typing import Optional, Dict, Any, List

from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from services.config_controller import UserSettings
from services.Event_Bus import EventBus

logger = logging.getLogger(__name__)

# スコープ設定（旧 collectors/GoogleCalendarAPI.py から移植）
SCOPES = [
    "https://www.googleapis.com/auth/calendar",
    "https://www.googleapis.com/auth/tasks",
]
CLIENT_SECRET_FILENAME = "client_secret.json"
CACHE_FILENAME = "google_calendar_cache.json"


class GoogleCalendarCollector:
    """
    Googleカレンダー/タスクの認証・API取得・JSONキャッシュ書き込みを担うクラス。
    services/WindowsInfoCollecter.py の win_info_collector と同様に、
    bus / setting をコンストラクタで受け取る。
    """

    def __init__(self, bus: EventBus, setting: UserSettings, app_dir: str, debug: int = -1):
        self.bus = bus
        self.setting = setting
        self.app_dir = app_dir
        self.debug = debug
        self.cache_path = os.path.join(app_dir, CACHE_FILENAME)

        self.calendar_service = None
        self.tasks_service = None
        # auth_state: "disabled" | "not_started" | "in_progress" | "authenticated" | "failed"
        self.auth_state = "not_started"
        self._auth_lock = threading.Lock()

        if debug >= 0:
            indent = "  " * debug
            print(f"{indent}GoogleCalendarCollector.__init__() called.")

        # 起動時に古いキャッシュを削除（安全性のため）
        self.clear_cache()

        if self._is_configured():
            self._start_auth_async()
        else:
            self.auth_state = "disabled"
            if debug >= 0:
                indent = "  " * debug
                print(f"{indent}GoogleCalendarCollector: 権限オフまたはclient_secret.json未配置のため無効化します。")

    def _is_configured(self) -> bool:
        """Permission.get_calendar_infoがTrueかつclient_secret.jsonが存在するかを判定する。"""
        permission = self.setting.get_setting_value("ApplicationSettings.Permission.get_calendar_info")
        if permission != True:
            return False
        client_secret_path = os.path.join(self.app_dir, CLIENT_SECRET_FILENAME)
        return os.path.exists(client_secret_path)

    def _start_auth_async(self):
        """Tkのメインループをブロックしないよう、認証をバックグラウンドスレッドで開始する。"""
        threading.Thread(target=self._authenticate, kwargs={"debug": self.debug}, daemon=True).start()

    def _authenticate(self, debug: int = -1):
        """
        OAuthフローを実行し、calendar_service / tasks_service を構築する。
        トークンファイルへの書き込みは行わない。
        """
        with self._auth_lock:
            if self.auth_state == "in_progress":
                return
            self.auth_state = "in_progress"

        try:
            client_secret_path = os.path.join(self.app_dir, CLIENT_SECRET_FILENAME)
            flow = InstalledAppFlow.from_client_secrets_file(client_secret_path, SCOPES)
            creds = flow.run_local_server(port=0, access_type="offline", prompt="consent")

            self.calendar_service = build("calendar", "v3", credentials=creds)
            self.tasks_service = build("tasks", "v1", credentials=creds)
            self.auth_state = "authenticated"
            logger.info("Googleカレンダーの認証に成功しました。")
            if debug >= 0:
                indent = "  " * debug
                print(f"{indent}GoogleCalendarCollector: 認証に成功しました。")
        except Exception as e:
            self.auth_state = "failed"
            logger.error(f"Googleカレンダーの認証に失敗しました: {e}")
            print(f"エラー: Googleカレンダーの認証に失敗しました: {e}")

    def is_available(self) -> bool:
        """認証済みかどうかを返す。"""
        return self.auth_state == "authenticated"

    def refresh_cache(self, debug: int = -1):
        """
        Req_CalendarInfo の購読ハンドラ本体。
        認証済みでなければ何もしない。オーケストレーションのみを担い、
        取得範囲の計算やフィールド整形などの詳細は持たない。
        """
        if not self.is_available():
            return
        try:
            data = self._fetch_events_and_tasks()
            self._write_cache(data)
            if debug >= 0:
                indent = "  " * debug
                print(f"{indent}GoogleCalendarCollector.refresh_cache(): "
                      f"events={len(data.get('events', []))}, tasks={len(data.get('tasks', []))}")
        except HttpError as e:
            logger.error(f"Googleカレンダー/タスクの取得に失敗しました: {e}")
        except Exception as e:
            logger.error(f"GoogleCalendarCollector.refresh_cache()で予期しないエラーが発生しました: {e}")

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

    def _resolve_calendar_ids(self) -> List[Dict[str, str]]:
        """
        取得対象のカレンダー一覧を決定する。
        設定 GoogleCalendar.CalendarIds（カンマ区切り）が明示されていればそれを優先する。
        未設定なら calendarList().list() を呼び、accessRole=="owner"（＝Googleカレンダー
        画面の「マイカレンダー」欄に出る、自分が所有するカレンダー）を自動的に対象にする。
        「他のカレンダー」欄（共有カレンダー・購読カレンダー等、accessRoleがowner以外）は
        既定では含めない。含めたい場合はCalendarIdsで明示的にIDを追加する。
        """
        override = self.setting.get_setting_value("ApplicationSettings.GoogleCalendar.CalendarIds", "")
        if isinstance(override, str) and override.strip():
            ids = [cid.strip() for cid in override.split(",") if cid.strip()]
            if ids:
                return [{"id": cid, "summary": cid} for cid in ids]

        calendars: List[Dict[str, str]] = []
        try:
            page_token = None
            while True:
                result = self.calendar_service.calendarList().list(pageToken=page_token).execute()
                for item in result.get("items", []):
                    if item.get("accessRole") == "owner":
                        calendars.append({
                            "id": item.get("id"),
                            "summary": self._resolve_calendar_display_name(item),
                        })
                page_token = result.get("nextPageToken")
                if not page_token:
                    break
        except HttpError as e:
            logger.warning(f"カレンダー一覧の取得に失敗しました。primaryのみ取得します: {e}")

        if not calendars:
            calendars = [{"id": "primary", "summary": "primary"}]
        return calendars

    def _fetch_events_and_tasks(self) -> dict:
        """
        FetchRangeDays設定から取得範囲を計算し、Google Calendar/Tasks APIを呼ぶ。
        取得した生データはフィールド選別のみ行い、時刻表示変換やテキスト整形は行わない
        （それらはai_tools/get_calendar_info_tool.py側の責務）。
        マイカレンダー内の複数カレンダーそれぞれに対して予定を取得し、1つのリストに統合する。
        """
        fetch_range_days = self.setting.get_setting_value("ApplicationSettings.GoogleCalendar.FetchRangeDays", 7)
        if not isinstance(fetch_range_days, int) or fetch_range_days <= 0:
            fetch_range_days = 7

        now = datetime.datetime.now().astimezone()
        time_min_dt = now - datetime.timedelta(days=1)
        time_max_dt = now + datetime.timedelta(days=fetch_range_days)

        calendars = self._resolve_calendar_ids()
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

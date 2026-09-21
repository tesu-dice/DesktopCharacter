import json
import os
import threading
from datetime import datetime, timedelta
import logging
from services.Event_Bus import EventBus # 環境に合わせて適宜読み込み

logger = logging.getLogger(__name__)

class UserActivityManager:
    def __init__(self, bus:EventBus, dir=""):
        self.bus = bus
        self.storage_dir = os.path.join(dir, "user_logs")
        os.makedirs(self.storage_dir, exist_ok=True)
        #self.filepath = self._get_filepath_for_today()
        self._initialize_json_if_needed()

        #要約キャッチアップ（定刻トリガー廃止・トリクル方式）関連の状態
        self._catchup_in_progress = False # 要約要求が処理中かどうか（同時に1件までしか進めない）
        self._catchup_halted = False      # AIサービス利用不可等でキャッチアップ自体を停止したか（再起動まで戻らない）
        self._catchup_lock = threading.Lock()

    def _get_filepath_for_today(self) -> str:
        today_str = datetime.now().strftime("%Y-%m-%d")
        return os.path.join(self.storage_dir, f"{today_str}.json")

    def _initialize_json_if_needed(self):
        filepath = self._get_filepath_for_today()
        if not os.path.exists(filepath):
            initial_data = {
                "logs": [],
                "hourlogs": [],
                "daylogs": []  # リスト構造に統一しました（元のコードはdictでしたが拡張性を考慮）
            }
            self._save_data(initial_data)

    def _load_data(self, date_str: str = "") -> dict:
        """指定日のデータを読み込む。日付指定がなければ今日のファイル。"""
        target_path = self._get_filepath_for_today()
        if date_str:
            target_path = os.path.join(self.storage_dir, f"{date_str}.json")

        try:
            with open(target_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            # ファイルがない場合は初期化（今日の日付の場合のみ）
            if target_path == self._get_filepath_for_today():
                self._initialize_json_if_needed()
                # 再帰呼び出しのリスクを避けるため、再度openを試みるか空データを返す
                with open(target_path, 'r', encoding='utf-8') as f:
                    return json.load(f)
            else:
                logger.warning(f"ログファイルが見つかりません: {target_path}")
                return {"logs": [], "hourlogs": [], "daylogs": []}

    def _save_data(self, data: dict, filename: str = ""):
        if filename == "":
            filepath = self._get_filepath_for_today()
        else:
            filepath = os.path.join(self.storage_dir, f"{filename}.json")
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

    #logs/hourlogs/daylogsの値を安全にdictのリストへ正規化する（旧仕様のdict形式や破損データを吸収する）
    def _safe_log_list(self, value, context: str = "") -> list:
        """
        data.get("logs"/"hourlogs"/"daylogs") で取り出した値を、常に「dictのリスト」として扱えるように正規化する。

        旧バージョンでは daylogs が単一のdict（例: {"summary": ""}）で保存されていたファイルや、
        要素がdictでない壊れたデータが混在するファイルが存在するため、ここで一括して吸収する。
        - listでない場合（旧仕様のdict形式など）は空リストとして扱う。
        - list内にdictでない要素が混ざっている場合はその要素だけを除外する。
        """
        if not isinstance(value, list):
            if value: # 空dict({})や空文字ではなく、何か中身がある場合のみ警告する
                logger.warning(f"_safe_log_list(): 想定外の形式のためリストとして扱います。(context={context}, type={type(value).__name__}, value={value})")
            return []

        cleaned = [item for item in value if isinstance(item, dict)]
        if len(cleaned) != len(value):
            logger.warning(f"_safe_log_list(): dict以外の要素を除外しました。(context={context}, 元件数={len(value)}, 正常件数={len(cleaned)})")
        return cleaned

    #ログ記録機能
    def add_userlog(self, time_str: str, window_title: str, media_info: str):
        """アクティビティログを記録するのみに専念"""
        data = self._load_data()
        
        #すでにログがあるかどうかの確認
        if self.check_log_existence(time_str, "minute")[0] == True:
            return
        
        new_log = {
            "time": time_str,
            "window": window_title,
            "media": media_info
        }
        
        data["logs"].append(new_log)
        self._save_data(data)
    #時間毎、一日毎のログを保存
    def add_summary_log(self, time_str: str, scope: str, reply_to:str, text: str):
        """
        LLMの要約結果を保存する（時間/日次 共通）
        scope: 'hour' or 'day'
        """
        #不正な呼び出しの場合は無視
        if not time_str or not text or "-" not in time_str:
            logger.warning(f"add_summary_log() 不正な呼び出しです。(time_str, scope, replay_to, text) = ({time_str}, {scope}, {reply_to}, {text})")
            return
        
        # 保存先のキーを決定
        target_key = "hourlogs" if scope == "hour" else "daylogs"
        #フォーマット調整
        time_str = time_str.split(":")[0]#YYYY-mm-dd HH:MM:SS ->をYYYY-mm-ddまたはYYYY-mm-dd HHに変換
        key_time = time_str if scope == "hour" else time_str.split(" ")[0]#保存で使うキー
        file_name = time_str.split(" ")[0]#保存先のファイル名
        
        data = self._load_data(file_name)

        #定期的な記録でないかつ、ログ収集が十分でない可能性の場合はファイルに書き込まないで終了
        if reply_to != "":
            try:
                log_time = datetime.strptime(key_time, "%Y-%m-%d %H") if scope =="hour" else datetime.strptime(key_time, "%Y-%m-%d")
                now = datetime.now()
                #未来のログリクエストではないかつ、今より1日 or 1時間以内ならログは残さない
                nessesary_diff = timedelta(hours= 1) if scope == "hour" else timedelta(days= 1)
                if now > log_time and nessesary_diff > now-log_time:
                    self.bus.publish(reply_to, text)
                    return
            
            except Exception as  e:
                logger.error(f"add_summary_log() (time_str, scope, replay_to, error) = ({time_str}, {scope}, {reply_to}, {e})")

        # 既存ログを検索して上書き、アプリのリクエストで予定より早く生成されてる場合は定刻のログが書き換え
        # 旧仕様のdict形式や破損データが残っている場合はここで正規化し、以後の保存で自然に修復する
        data[target_key] = self._safe_log_list(data.get(target_key, []), context=f"add_summary_log:{target_key}")
        log_found = False
        for log in data[target_key]:
            if log.get("time") == key_time:
                log["summary"] = text  # 概要を上書き
                log_found = True
                break

        if log_found:
            print(f"[{scope} summary] 上書き保存しました: {key_time}")
        else: # ログが見つからなかった場合は新規追加
            new_log = {"time": key_time, "summary": text}
            data[target_key].append(new_log)
            print(f"[{scope} summary] 新規保存しました: {key_time}")
        logger.info(f"要約テキストを保存しました。({time_str}, {scope}, {reply_to})")
        self._save_data(data, file_name)
        #通知イベントが指定されている場合
        if reply_to != "" :
            self.bus.publish(reply_to, text)

    #ログリストをMarkdownテーブル形式に変換する
    def _to_markdown_table(self, logs: list, columns: list) -> str:
        def escape(s):
            return str(s).replace("|", "｜")
        header = "| " + " | ".join(columns) + " |"
        separator = "|" + "|".join(["---"] * len(columns)) + "|"
        rows = ["| " + " | ".join(escape(log.get(col, "")) for col in columns) + " |" for log in logs]
        return "\n".join([header, separator] + rows)

    #時間毎、一日毎のログ用のリクエストを作成
    def request_summary(self, scope: str, target_time: str, reply_to =""):
        """
        要約リクエストの共通メソッド
        scope: "hour" | "day"
        """
        file_name = target_time.split(" ")[0]
        data = self._load_data(file_name)
        #すでにログがあるかどうかの確認
        exists, existing_summary = self.check_log_existence(target_time, scope)
        if exists:
            if reply_to != "":
                self.bus.publish(reply_to, existing_summary)
            return

        if scope == "hour":
            target_hour = target_time.split(" ")[1].split(":")[0]
            all_logs = self._safe_log_list(data.get("logs", []), context=f"request_summary:logs:{target_time}")
            logs = [
                log for log in all_logs
                if isinstance(log.get("time"), str) and " " in log["time"] and log["time"].split(" ")[1].startswith(f"{target_hour}:")
            ]
            if not logs:
                print(f"{target_hour}時台のログはありません。")
                self.add_summary_log(target_time, scope=scope, reply_to=reply_to, text=f"{target_hour}時台のログはありませんでした。")
                return
            llm_input = self._to_markdown_table(logs, ["time", "window", "media"])

        elif scope == "day":
            hour_summaries = self._safe_log_list(data.get("hourlogs", []), context=f"request_summary:hourlogs:{target_time}")
            summarized_hours = {
                log["time"].split(" ")[1]
                for log in hour_summaries
                if isinstance(log.get("time"), str) and " " in log["time"]
            }
            unsummarized_logs = [
                log for log in self._safe_log_list(data.get("logs", []), context=f"request_summary:logs:{target_time}")
                if isinstance(log.get("time"), str) and " " in log["time"] and log["time"].split(" ")[1].split(":")[0] not in summarized_hours
            ]
            if not hour_summaries and not unsummarized_logs:
                print("本日のログはありません。")
                self.add_summary_log(target_time, scope=scope, reply_to=reply_to, text=f"{target_time.split(' ')[0]}のログはありませんでした。")
                return
            date_str = target_time.split(" ")[0]
            hour_table = self._to_markdown_table(hour_summaries, ["time", "summary"])
            unsummarized_table = self._to_markdown_table(unsummarized_logs, ["time", "window", "media"])
            llm_input = f"# {date_str} の活動ログ\n\n## 時間サマリー\n{hour_table}\n\n## 未集計ログ\n{unsummarized_table}"

        else:
            return

        self.bus.publish("Req_UserSummaryLog", llm_input, scope, target_time, reply_to)
        print(f"[{scope}] 要約リクエストを送信しました。")
        logger.info(f"{scope} についての要約文章のリクエストを行いました。")
    #ログの有無を確認する
    def check_log_existence(self, time_str: str, scope: str) -> tuple[bool, str]:
        """
        指定された時刻・スコープのログ(要約)が既に存在するかを確認する。

        Args:
            time_str (str): "YYYY-MM-DD HH:MM:SS" などの時刻文字列
            scope (str): "minute", "hour", "day" のいずれか

        Returns:
            tuple[bool, str]: (存在するか, 存在する場合の要約テキスト)
                                存在しない場合は (False, "") を返す。
        """
        
        # 1. 日付情報の解析と対象ファイルの決定
        try:
            # 入力が "YYYY-MM-DD" のみの場合と "YYYY-MM-DD HH:MM" の場合に対応
            if len(time_str) <= 10:
                dt = datetime.strptime(time_str, "%Y-%m-%d")
            elif ":" not in time_str:
                dt = datetime.strptime(time_str, "%Y-%m-%d %H")
            else:
                dt = datetime.strptime(time_str, "%Y-%m-%d %H:%M") 
            target_date_str = dt.strftime("%Y-%m-%d")
        except ValueError:
            logger.error(f"時刻フォーマットエラー: {time_str}")
            return True, "データの参照に失敗しました。"

        # ファイルロード（指定日のファイルを読み込む）
        data = self._load_data(date_str=target_date_str)
        if not data:
            return False, ""

        # 2. スコープに応じた検索キーと参照リストの決定
        target_list = []
        search_key = ""

        if scope == "day":
            # 日次: "daylogs" を参照、キーは "YYYY-MM-DD"
            target_list = self._safe_log_list(data.get("daylogs", []), context=f"check_log_existence:daylogs:{target_date_str}")
            search_key = target_date_str

        elif scope == "hour":
            # 時間: "hourlogs" を参照、キーは "HH" (例: "14")
            target_list = self._safe_log_list(data.get("hourlogs", []), context=f"check_log_existence:hourlogs:{target_date_str}")
            search_key = dt.strftime("%Y-%m-%d %H")

        elif scope == "minute":
            # ※現在のJSON構造にない場合は空リストになります
            target_list = self._safe_log_list(data.get("logs", []), context=f"check_log_existence:logs:{target_date_str}")
            search_key = dt.strftime("%Y-%m-%d H:%M")
        
        else:
            logger.warning(f"不明なスコープ指定です: {time_str}, {scope}")
            return False, ""

        # 3. 検索実行
        # リスト内を走査して、timeが一致するものを探す
        found_log = next((item for item in target_list if item.get("time") == search_key), None)

        if found_log:
            # 見つかった場合: Trueと、その内容(summary)を返す
            return True, found_log.get("summary", "")
        else:
            # 見つからなかった場合
            return False, ""

    #未要約の対象を最も古いものから1件だけ探す（時間要約→日次要約の順序保証はこの探索順だけで実現する）
    def get_next_pending_summary_target(self) -> tuple[str, str]:
        """
        user_logs 配下の全履歴を日付昇順で走査し、未要約の対象を最も古いものから1件だけ返す。

        Returns:
            tuple[str, str] | None: (scope, target_time)。scopeは"hour"または"day"、
                target_timeはrequest_summary()にそのまま渡せる形式
                （時間: "YYYY-MM-DD HH:00" / 日: "YYYY-MM-DD"）。
                未要約の対象が無ければNoneを返す。
        """
        try:
            filenames = os.listdir(self.storage_dir)
        except FileNotFoundError:
            return None

        date_strs = []
        for filename in filenames:
            if not filename.endswith(".json"):
                continue
            date_str = filename[:-len(".json")]
            try:
                datetime.strptime(date_str, "%Y-%m-%d") # YYYY-MM-DD形式以外のファイルは無視
            except ValueError:
                continue
            date_strs.append(date_str)
        date_strs.sort() # 日付昇順

        now = datetime.now()
        today_str = now.strftime("%Y-%m-%d")

        for date_str in date_strs:
            is_today = (date_str == today_str)
            data = self._load_data(date_str)

            # その日付内に記録済みの時間帯を時間昇順でチェック
            logs = self._safe_log_list(data.get("logs", []), context=f"get_next_pending_summary_target:logs:{date_str}")
            logged_hours = sorted({
                log["time"].split(" ")[1].split(":")[0]
                for log in logs
                if isinstance(log.get("time"), str) and " " in log["time"]
            })
            for hour in logged_hours:
                if is_today and int(hour) >= now.hour:
                    continue # 当日かつ現在時刻以降の時間帯は進行中のため対象外
                target_time = f"{date_str} {hour}:00"
                if self.check_log_existence(target_time, "hour")[0] == False:
                    return ("hour", target_time)

            # 時間要約が揃っていれば日次要約をチェック（当日は除く）
            if not is_today:
                if self.check_log_existence(date_str, "day")[0] == False:
                    return ("day", date_str)

        return None

    #要約のキャッチアップ処理（1tickにつき最大1件のトリクル方式）
    def run_catchup_tick(self, debug: int = -1):
        """
        "Req_SummaryCatchup"（main.pyのn分毎tick）から呼び出される想定。
        前回の要求が処理中/エラー停止中でなければ、未要約の対象を1件だけ要求する。
        """
        with self._catchup_lock:
            if self._catchup_halted:
                return # 6.3のエラーにより停止済み。アプリ再起動まで何もしない
            if self._catchup_in_progress:
                return # 前回発行した要求がまだ完了していない

            target = self.get_next_pending_summary_target()
            if target is None:
                return

            scope, target_time = target
            self._catchup_in_progress = True

        # 発行のみ。実際のLLM呼び出しはキュー経由で非同期に行われる
        # ここで想定外の例外が発生すると reply_to が二度と呼ばれず _catchup_in_progress が
        # True のまま固定化し、以降のtickが永久に「処理中」判定でスキップされ続けてしまう
        # （再起動しても同じ最古のターゲットで同じ例外を再現し、無限ループしているように見える）。
        # そのため念のため捕捉し、in_progressを戻して次tickでのリトライを可能にしておく。
        try:
            self.request_summary(scope=scope, target_time=target_time, reply_to="OnCatchupSummaryDone")
        except Exception as e:
            logger.error(f"run_catchup_tick(): request_summary()で想定外のエラーが発生しました。(scope={scope}, target_time={target_time}, error={e})")
            with self._catchup_lock:
                self._catchup_in_progress = False

    #キャッチアップの要約要求が1件完了した際の通知ハンドラ
    def _on_catchup_done(self, text: str = "", debug: int = -1):
        with self._catchup_lock:
            self._catchup_in_progress = False

    #キャッチアップ中にAIサービスが使えなかった際の通知ハンドラ（キャッチアップ自体を停止する）
    def _on_catchup_llm_error(self, scope: str = "", target_time: str = "", debug: int = -1):
        logger.error(f"要約キャッチアップを停止しました。(scope={scope}, target_time={target_time})")
        with self._catchup_lock:
            self._catchup_halted = True
            self._catchup_in_progress = False

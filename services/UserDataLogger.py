import json
import os
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

        # スケジュール確認をここで行うなら、メソッドを分ける
        self._check_and_trigger_summary(time_str)
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
        log_found = False
        if target_key in data:
            for log in data[target_key]:
                if log.get("time") == key_time:
                    log["summary"] = text  # 概要を上書き
                    log_found = True
                    break

        if log_found:
            print(f"[{scope} summary] 上書き保存しました: {key_time}")
        else: # ログが見つからなかった場合は新規追加
            new_log = {"time": key_time, "summary": text}
            if target_key not in data:
                data[target_key] = []
            data[target_key].append(new_log)
            print(f"[{scope} summary] 新規保存しました: {key_time}")
        logger.info(f"要約テキストを保存しました。({time_str}, {scope}, {reply_to})")
        self._save_data(data, file_name)
        #通知イベントが指定されている場合
        if reply_to != "" :
            self.bus.publish(reply_to, text)

    #時間毎、一日毎のログを保存する条件分け
    def _check_and_trigger_summary(self, time_str: str):
        """
        時間に基づいて要約リクエストが必要か判定する
        ※ 本来は外部スケジューラで管理するのが望ましいが、簡易実装としてここに配置
        """
        # "YYYY-MM-DD HH:MM" 形式を想定
        try:
            time_part = time_str.split(" ")[1] # HH:MM
            hour, minute = time_part.split(":")
        except IndexError:
            return # フォーマット不正時は何もしない


        # 23:55 -> 日次要約
        if hour == "23" and minute == "55":
            self.request_summary(scope="day", target_time=time_str)
        # 毎時55分 -> 時間要約(11時台は作成しない)
        elif  minute == "55":
            self.request_summary(scope="hour", target_time=time_str)
    #時間毎、一日毎のログ用のリクエストを作成
    def request_summary(self, scope: str, target_time: str, reply_to =""):
        """
        要約リクエストの共通メソッド
        scope: "hour" | "day"
        """
        file_name = target_time.split(" ")[0]
        data = self._load_data(file_name)
        #すでにログがあるかどうかの確認
        if self.check_log_existence(target_time, scope)[0] == True:
            return
        
        logs_to_process = []
        prompt_prefix = ""

        if scope == "hour":
            # 時間帯(HH)の抽出
            target_hour = target_time.split(" ")[1].split(":")[0]
            # ログ抽出フィルタ
            logs_to_process = [
                log for log in data["logs"]
                if log["time"].split(" ")[1].startswith(f"{target_hour}:")
            ]
            prompt_prefix = "次のユーザの1時間のアクティビティを短く要約してください。"
            #参照できるログ情報がない場合
            if not logs_to_process:
                print(f"{target_hour}時台のログはありません。")
                self.add_summary_log(target_time, scope=scope, reply_to="", text= f"{target_hour}時台のログはありませんでした。")
                return

        elif scope == "day":
            # 1. 既存のhourlogsを取得
            hour_summaries = data.get("hourlogs", [])#各時刻の要約ログの辞書のリストを取得
            summarized_hours = {log['time'].split(' ')[1] for log in hour_summaries} # "HH"形式のセット

            # 2. hourlogsが存在しない時間帯の生ログを取得
            unsummarized_logs = [#時刻の文字列"HH"だけ取ってsummarized_hoursと一致しない場合は追加。
                log for log in data.get("logs", [])
                if log['time'].split(' ')[1].split(':')[0] not in summarized_hours
            ]

            # 3. プロンプトの作成
            prompt_prefix = (
                "以下はユーザーの1日の活動記録です。\n"
                "'hour_summaries'には時間ごとの要約が、'unsummarized_raw_logs'にはまだ要約されていない時間帯の生ログが含まれています。\n"
                "これらすべてを考慮して、1日の活動全体を3つ程度の主要な出来事にまとめてください。"
            )
            
            # 処理対象のログがない場合は終了
            if not hour_summaries and not unsummarized_logs:
                print("本日のログはありません。")
                self.add_summary_log(target_time, scope=scope, reply_to="", text=f"{target_time.split(' ')[0]}のログはありませんでした。")
                return

            # LLMに渡すペイロードを作成
            logs_to_process = {
                "hour_summaries": hour_summaries,
                "unsummarized_raw_logs": unsummarized_logs
            }
        
        # 共通の送信処理
        llm_input_json = json.dumps(logs_to_process, indent=2, ensure_ascii=False)
        request_text = f"{prompt_prefix}\n{llm_input_json}"
        
        # EventBusへ送信（コンテキストとしてログデータを渡す）
        # ※受け取り側で time などのメタデータが必要なら、辞書形式で渡すのがベターです
        payload = {
            "time": target_time,
            "text": request_text,
            "scope": scope
        }
        # 今回は元の文字列送信に合わせています
        self.bus.publish("Req_UserSummaryLog_context", request_text)
        self.bus.publish("Req_UserSummaryLog_TimeAndScope", target_time, scope, reply_to)
        print(f"[{scope}] 要約リクエストを送信しました。")
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
            target_list = data.get("daylogs", [])
            search_key = target_date_str

        elif scope == "hour":
            # 時間: "hourlogs" を参照、キーは "HH" (例: "14")
            target_list = data.get("hourlogs", [])
            search_key = dt.strftime("%Y-%m-%d %H")

        elif scope == "minute":
            # ※現在のJSON構造にない場合は空リストになります
            target_list = data.get("logs", []) 
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

    #RAG活用のリクエストを処理する。
    def handle_rag_request(self, request:str):#将来的に複数の場合はstrのリストになるかも？
        #有効なリクエストがない場合
        if request == "" or "-" not in request or request == "None": #時刻形式が適切でない場合
            self.bus.publish("RAGisReady", "必要情報なし")#RAG機能ONだけど情報なし
            return
        #リクエスト内容に関しての読みわけ　"YYYY-MM-DD HH"形式
        target = "day" if request.find(" ") == -1 else "hour"
        exist, content = self.check_log_existence(time_str=request, scope=target)
        if exist:#すでにログがあるとき
            self.bus.publish("RAGisReady", content)
        else:#ログがなければ最終的な完了通知のイベント名を指定して。ログの作成を行う。
            self.request_summary(scope=target, target_time=request, reply_to="RAGisReady")
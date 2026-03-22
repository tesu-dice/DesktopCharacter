import datetime
import os
# --- 標準ライブラリでタイムゾーンを扱うためのモジュール ---
# zoneinfoはIANA形式の文字列を扱うために使用していたため、必須ではなくなりますが、
# 将来的な拡張性のために残しておいても問題ありません。
from zoneinfo import ZoneInfo 
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

# スコープ設定
SCOPES = [
    "https://www.googleapis.com/auth/calendar",
    "https://www.googleapis.com/auth/tasks"
]
CLIENT_SECRET_FILE = "client_secret.json"
OAUTH_TOKEN_FILE = "oauth_token.json"


class GoogleScheduleControl:
    def __init__(self):
        creds = None
        if os.path.exists(OAUTH_TOKEN_FILE):
            creds = Credentials.from_authorized_user_file(OAUTH_TOKEN_FILE, SCOPES)

        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                flow = InstalledAppFlow.from_client_secrets_file(
                    CLIENT_SECRET_FILE, SCOPES
                )
                creds = flow.run_local_server(port=0, access_type="offline", prompt="consent")

            # トークンをjsonアフィルとして残す
            with open(OAUTH_TOKEN_FILE, "w") as token:
                token.write(creds.to_json())

        self.calendar_service = build("calendar", "v3", credentials=creds)
        self.tasks_service = build("tasks", "v1", credentials=creds)

    def _sanitize_text(self, text):
        if not text:
            return ""
        sanitized = text.replace("\r", "").replace("\n", "<br>")
        sanitized = sanitized.replace("|", "\\|")
        return sanitized

    ### <<< 修正: タイムゾーン引数を int 型に限定 >>>
    def get_calendar_by_date(self, date_str: str, start_time: datetime.time, end_time: datetime.time, timezone: int):
        """
        指定日の指定時刻範囲・指定タイムゾーンの予定を取得。
        Args:
            date_str (str): 開始日付 ('YYYY-MM-DD')
            start_time (datetime.time): 取得開始時刻
            end_time (datetime.time): 取得終了時刻
            timezone (int): UTCからの時差を時間単位の整数で指定 (例: 日本なら 9)
        """
        # --- タイムゾーンオブジェクトの生成ロジックを簡略化 ---
        if not isinstance(timezone, int):
            raise TypeError("timezoneはUTCからの時差を整数(int)で指定してください。")
        tz_obj = datetime.timezone(datetime.timedelta(hours=timezone))

        start_date = datetime.datetime.strptime(date_str, "%Y-%m-%d").date()
        end_date = start_date

        if end_time <= start_time:
            end_date += datetime.timedelta(days=1)
        
        start_datetime_naive = datetime.datetime.combine(start_date, start_time)
        end_datetime_naive = datetime.datetime.combine(end_date, end_time)

        start_datetime_aware = start_datetime_naive.replace(tzinfo=tz_obj)
        end_datetime_aware = end_datetime_naive.replace(tzinfo=tz_obj)
        
        time_min = start_datetime_aware.isoformat()
        time_max = end_datetime_aware.isoformat()

        events_result = self.calendar_service.events().list(
            calendarId="primary", timeMin=time_min, timeMax=time_max,
            singleEvents=True, orderBy="startTime"
        ).execute()

        return events_result.get("items", [])

    def get_tasks(self):
        tasklists = self.tasks_service.tasklists().list().execute()
        items = tasklists.get("items", [])
        if not items: return []
        tasklist_id = items[0]["id"]
        tasks_result = self.tasks_service.tasks().list(tasklist=tasklist_id).execute()
        return tasks_result.get("items", [])

    def _format_event_time(self, start, end):
        if len(start) == 10 and len(end) == 10: return "終日"
        start_time = start[11:16] if "T" in start else ""
        end_time = end[11:16] if "T" in end else ""
        return f"{start_time}-{end_time}" if start_time and end_time else start_time or end_time

    ### <<< 修正: タイムゾーン引数を int 型に限定し、デフォルト値を 9 に変更 >>>
    def generate_daily_md(self, date_str, output_dir="./diary",
                          start_time=datetime.time.min, end_time=datetime.time.max, timezone: int = 9):
        """
        指定日の予定とタスクをMarkdownファイルとして出力
        Args:
            date_str (str): 日付 ('YYYY-MM-DD')
            output_dir (str): 出力先ディレクトリ
            start_time (datetime.time): 予定の取得開始時刻
            end_time (datetime.time): 予定の取得終了時刻
            timezone (int): UTCからの時差 (デフォルト: 9)
        """
        events = self.get_calendar_by_date(date_str, start_time, end_time, timezone)
        tasks = None

        os.makedirs(output_dir, exist_ok=True)
        file_path = os.path.join(output_dir, f"{date_str}.md")

        with open(file_path, "w", encoding="utf-8") as f:
            f.write(f"# {date_str} の日記 (UTC+{timezone})\n\n")
            f.write("## タスク\n")
            if not tasks: f.write("（タスクはありません）\n- [ ] 新しいタスク\n")
            else:
                f.write("| 完了 | 項目名 | 時刻 | 備考 |\n| ---- | ------ | ---- | ---- |\n")
                for t in tasks:
                    title, status = self._sanitize_text(t.get("title", "（タイトルなし）")), t.get("status", "")
                    checked, notes = "x" if status == "completed" else " ", self._sanitize_text(t.get("notes", ""))
                    due_time = ""
                    if "due" in t:
                        try:
                            due_dt = datetime.datetime.fromisoformat(t["due"].replace("Z", "+00:00")); due_time = due_dt.strftime("%H:%M")
                        except ValueError: pass
                    f.write(f"| [{checked}] | {title} | {due_time} | {notes} |\n")
                f.write("\n")
            f.write("## タイムライン\n")
            if not events: f.write("（予定はありません）\n\n")
            else:
                f.write("| 時刻 | 項目名 | 備考 |\n| ---- | ------ | ---- |\n")
                for e in events:
                    start = e["start"].get("dateTime", e["start"].get("date")); end = e["end"].get("dateTime", e["end"].get("date"))
                    time_str, summary = self._format_event_time(start, end), self._sanitize_text(e.get("summary", "（タイトルなし）"))
                    description = self._sanitize_text(e.get("description", ""))
                    # Taskの場合説明を取得できず、はURLが含まれるので除外
                    if "tasks.google.com" in description:
                        description = ""
                        continue
                    f.write(f"| {time_str} | {summary} | {description} |\n")
                f.write("\n")
            f.write("## 自由記述\n")
            f.write("ここに自由に記入してください。\n")

        print(f"日記を作成しました: {file_path}")


def main():
    try:
        gcal = GoogleScheduleControl()
        start_date = datetime.date(2026, 2, 1)
        
        end_date = datetime.date(2026, 2, 28)

        current_date = start_date
        while current_date <= end_date:
            date_str = current_date.strftime("%Y-%m-%d")
            gcal.generate_daily_md( date_str,
                                    start_time=datetime.time(6, 0),
                                    end_time=datetime.time(4, 0),
                                    timezone=9,  # 日本時間を指定
                                    output_dir="./diary")
            current_date += datetime.timedelta(days=1)

        

    except (HttpError, ValueError, TypeError) as error:
        print(f"エラーが発生しました: {error}")


if __name__ == "__main__":
    main()
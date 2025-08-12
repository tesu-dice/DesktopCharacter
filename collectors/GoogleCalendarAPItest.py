import datetime
import os
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

            with open(OAUTH_TOKEN_FILE, "w") as token:
                token.write(creds.to_json())

        self.calendar_service = build("calendar", "v3", credentials=creds)
        self.tasks_service = build("tasks", "v1", credentials=creds)

    def _sanitize_text(self, text):
        """表内で崩れないように文字列を整形"""
        if not text:
            return ""
        # 改行は <br> に
        sanitized = text.replace("\r", "").replace("\n", "<br>")
        # パイプ記号をエスケープ
        sanitized = sanitized.replace("|", "\\|")
        return sanitized

    def get_calendar_by_date(self, date_str):
        """指定日の予定を取得"""
        target_date = datetime.datetime.strptime(date_str, "%Y-%m-%d").date()
        time_min = datetime.datetime.combine(target_date, datetime.time.min).isoformat() + "Z"
        time_max = datetime.datetime.combine(target_date, datetime.time.max).isoformat() + "Z"

        events_result = self.calendar_service.events().list(
            calendarId="primary",
            timeMin=time_min,
            timeMax=time_max,
            singleEvents=True,
            orderBy="startTime",
        ).execute()

        return events_result.get("items", [])

    def get_tasks(self):
        """最初のタスクリストからタスクを取得"""
        tasklists = self.tasks_service.tasklists().list().execute()
        items = tasklists.get("items", [])
        if not items:
            return []

        tasklist_id = items[0]["id"]
        tasks_result = self.tasks_service.tasks().list(tasklist=tasklist_id).execute()
        tasks = tasks_result.get("items", [])
        return tasks

    def _format_event_time(self, start, end):
        """開始時刻-終了時刻形式に整形（終日対応）"""
        # 終日イベント判定
        if len(start) == 10 and len(end) == 10:  # YYYY-MM-DD
            return "終日"

        start_time = start[11:16] if "T" in start else ""
        end_time = end[11:16] if "T" in end else ""
        if start_time and end_time:
            return f"{start_time}-{end_time}"
        return start_time or end_time

    def generate_daily_md(self, date_str, output_dir="./diary"):
        """指定日の予定とタスクをMarkdownファイルとして出力"""
        events = self.get_calendar_by_date(date_str)
        tasks = None#self.get_tasks()

        os.makedirs(output_dir, exist_ok=True)
        file_path = os.path.join(output_dir, f"{date_str}.md")

        with open(file_path, "w", encoding="utf-8") as f:
            f.write(f"# {date_str} の日記\n\n")

            # --- タスク ---
            f.write("## タスク\n")
            if not tasks:
                f.write("（タスクはありません）\n- [ ] 新しいタスク\n")
            else:
                f.write("| 完了 | 項目名 | 時刻 | 備考 |\n")
                f.write("| ---- | ------ | ---- | ---- |\n")
                for t in tasks:
                    title = self._sanitize_text(t.get("title", "（タイトルなし）"))
                    status = t.get("status", "")
                    checked = "x" if status == "completed" else " "
                    notes = self._sanitize_text(t.get("notes", ""))
                    due_time = ""
                    if "due" in t:
                        try:
                            due_dt = datetime.datetime.fromisoformat(t["due"].replace("Z", "+00:00"))
                            due_time = due_dt.strftime("%H:%M")
                        except ValueError:
                            pass
                    f.write(f"| [{checked}] | {title} | {due_time} | {notes} |\n")
                f.write("\n")

            # --- 予定 ---
            f.write("## 予定\n")
            if not events:
                f.write("（予定はありません）\n\n")
            else:
                f.write("| 時刻 | 項目名 | 備考 |\n")
                f.write("| ---- | ------ | ---- |\n")
                for e in events:
                    start = e["start"].get("dateTime", e["start"].get("date"))
                    end = e["end"].get("dateTime", e["end"].get("date"))
                    time_str = self._format_event_time(start, end)
                    summary = self._sanitize_text(e.get("summary", "（タイトルなし）"))
                    description = self._sanitize_text(e.get("description", ""))
                    f.write(f"| {time_str} | {summary} | {description} |\n")
                f.write("\n")

            # --- 自由記述 ---
            f.write("## 自由記述\n")
            f.write("ここに自由に記入してください。\n")

        print(f"日記を作成しました: {file_path}")


def main():
    try:
        gcal = GoogleScheduleControl()
        # 今日の日記を作成（例）
        today_str = datetime.date.today().strftime("%Y-%m-%d")
        gcal.generate_daily_md(today_str)

    except HttpError as error:
        print(f"API Error: {error}")


if __name__ == "__main__":
    main()

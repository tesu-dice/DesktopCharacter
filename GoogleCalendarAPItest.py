import datetime
import os.path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

# スコープの設定 (予定の読み書きとタスクの読み書き)
SCOPES = ["https://www.googleapis.com/auth/calendar", "https://www.googleapis.com/auth/tasks"]


def main():
    creds = None
    if os.path.exists("token.json"):
        creds = Credentials.from_authorized_user_file("token.json", SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                "GoogleCalendarAPI.json", SCOPES
            )
            creds = flow.run_local_server(port=0)

        with open("token.json", "w") as token:
            token.write(creds.to_json())

    try:
        calendar_service = build("calendar", "v3", credentials=creds)
        tasks_service = build("tasks", "v1", credentials=creds)

        # 予定の読み込み
        now = datetime.datetime.utcnow().isoformat() + "Z"
        events_result = (
            calendar_service.events()
            .list(
                calendarId="primary",
                timeMin=now,
                maxResults=10,
                singleEvents=True,
                orderBy="startTime",
            )
            .execute()
        )
        events = events_result.get("items", [])
        if not events:
            print("No upcoming events found.")
        else:
            print("Upcoming events:")
            for event in events:
                start = event["start"].get("dateTime", event["start"].get("date"))
                print(start, event["summary"])

        # 予定の追加
        event = {
            'summary': 'Meeting with Team',
            'location': 'Conference Room',
            'description': 'Discuss project progress',
            'start': {
                'dateTime': '2024-03-15T10:00:00-07:00',
                'timeZone': 'America/Los_Angeles',
            },
            'end': {
                'dateTime': '2024-03-15T11:00:00-07:00',
                'timeZone': 'America/Los_Angeles',
            },
            'attendees': [
                {'email': 'someone@example.com'},
            ],
            'reminders': {
                'useDefault': False,
                'overrides': [
                    {'method': 'email', 'minutes': 24 * 60},
                    {'method': 'popup', 'minutes': 10},
                ],
            },
        }
        event = calendar_service.events().insert(calendarId='primary', body=event).execute()
        print('Event created: %s' % (event.get('htmlLink')))

        # 予定の編集 (イベントIDを指定)
        event_id = event['id']
        event = calendar_service.events().get(calendarId='primary', eventId=event_id).execute()
        event['summary'] = 'Updated Meeting with Team'
        updated_event = calendar_service.events().update(calendarId='primary', eventId=event_id, body=event).execute()
        print('Event updated: %s' % (updated_event.get('htmlLink')))

        # タスクリストの取得
        tasklists = tasks_service.tasklists().list().execute()
        tasklists_items = tasklists.get('items', [])

        if not tasklists_items:
            print("No task lists found.")
        else:
            print("Task Lists:")
            for tasklist in tasklists_items:
                print(f"- {tasklist['title']} (ID: {tasklist['id']})")

            # 最初のタスクリストを選択 (または、ユーザに選択させる)
            tasklist_id = tasklists_items[0]['id']

            # タスクの読み込み
            tasks = tasks_service.tasks().list(tasklist=tasklist_id).execute()
            tasks_items = tasks.get('items', [])

            if not tasks_items:
                print("No tasks found in the selected list.")
            else:
                print("Tasks in the selected list:")
                for task in tasks_items:
                    print(f"- {task['title']} (Status: {task['status']})")

            # タスクの追加
            task = {'title': 'New Task'}
            new_task = tasks_service.tasks().insert(tasklist=tasklist_id, body=task).execute()
            print(f"Task created: {new_task['title']}")

            # タスクの更新（完了にする）
            task_id = new_task['id']
            updated_task = tasks_service.tasks().get(tasklist=tasklist_id, task=task_id).execute()
            updated_task['status'] = 'completed'  # タスクを完了にする

            completed_task = tasks_service.tasks().update(tasklist=tasklist_id, task=task_id, body=updated_task).execute()
            print(f"Task completed: {completed_task['title']}")


    except HttpError as error:
        print(f"An error occurred: {error}")


if __name__ == "__main__":
    main()


"""
Googleカレンダー/タスクのキャッシュ（collectors/GoogleCalendarCollector.py が書き込む
google_calendar_cache.json）を読んで、AIに整形して返す読み取り専用Tool。

設計方針: docs/開発予定/202608_カレンダー連携/GoogleCalendar連携_設計方針.md 10.2章

ai_tools/tools_main.py:ToolExecutor._discover_tools() によって引数なし（obj()）で
インスタンス化される制約があるため、GoogleCalendarCollectorの生存インスタンスは
参照できない。キャッシュJSONファイルを直接読むことでのみ連携する。
このTool自身はキャッシュの更新をトリガーしない。
"""
import os
import json
import datetime
from typing import Dict, Any, List, Optional
import logging

from ai_tools.tool_base import BaseTool

logger = logging.getLogger(__name__)


class GetCalendarInfoTool(BaseTool):
    """
    Googleカレンダーの予定・Googleタスクのうち、直近24時間・今後24時間分を確認するツール。
    """

    @property
    def name(self) -> str:
        return "get_calendar_info"

    @property
    def description(self) -> str:
        return (
            "Googleカレンダー（マイカレンダー内の全カレンダー）の予定と、期限の近いGoogleタスクを確認します。"
            "直近24時間・今後24時間（合計48時間）分の情報を返します。"
            "利用にはclient_secret.jsonの配置と、起動時のGoogle認証が必要です。"
            "情報はバックグラウンドで定期取得されたキャッシュのため、多少古い場合があります。"
        )

    @property
    def args_schema(self) -> Dict[str, Any]:
        return {"type": "object", "properties": {}}

    def _get_cache_path(self) -> str:
        """google_calendar_cache.jsonの絶対パスを返す。get_user_activity_summary_tool.pyと同じパターン。"""
        current_dir = os.path.dirname(os.path.abspath(__file__))
        return os.path.join(current_dir, "..", "google_calendar_cache.json")

    def _load_cache(self) -> Optional[Dict[str, Any]]:
        """キャッシュJSONを読む。存在しない/壊れている場合はNoneを返す。"""
        try:
            with open(self._get_cache_path(), "r", encoding="utf-8") as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError) as e:
            logger.debug(f"カレンダーキャッシュの読み込みに失敗しました: {e}")
            return None

    def _parse_iso_datetime(self, value: str) -> datetime.datetime:
        """
        ISO8601文字列をタイムゾーン付きdatetimeに変換する。
        - "YYYY-MM-DD"（終日イベントのdate）はローカルタイムゾーンの0時として扱う。
        - 末尾"Z"はPython 3.9のdatetime.fromisoformat()が扱えないため"+00:00"に置換する
          （本プロジェクトはwinrtの制約でPython 3.9.13を使用するため、3.11以降のZ対応には頼れない）。
        """
        if len(value) == 10:  # "YYYY-MM-DD"
            naive = datetime.datetime.strptime(value, "%Y-%m-%d")
            return naive.astimezone()
        normalized = value.replace("Z", "+00:00")
        dt = datetime.datetime.fromisoformat(normalized)
        if dt.tzinfo is None:
            dt = dt.astimezone()
        return dt

    def _filter_within_window(self, data: Dict[str, Any], hours: int = 24) -> Dict[str, Any]:
        """現在時刻を基準に前後hours時間以内に該当するevents/tasksのみを抽出する。"""
        now = datetime.datetime.now().astimezone()
        window_start = now - datetime.timedelta(hours=hours)
        window_end = now + datetime.timedelta(hours=hours)

        filtered_events = []
        for event in data.get("events", []):
            start_raw = event.get("start", {}) or {}
            end_raw = event.get("end", {}) or {}
            start_value = start_raw.get("dateTime") or start_raw.get("date")
            end_value = end_raw.get("dateTime") or end_raw.get("date") or start_value
            if not start_value:
                continue
            try:
                start_dt = self._parse_iso_datetime(start_value)
                end_dt = self._parse_iso_datetime(end_value)
            except (ValueError, TypeError) as e:
                logger.debug(f"予定の日時解析に失敗しました。スキップします: {event.get('id')}, エラー: {e}")
                continue
            if end_dt >= window_start and start_dt <= window_end:
                filtered_events.append(event)

        filtered_tasks = []
        for task in data.get("tasks", []):
            due = task.get("due")
            if not due:
                # 期限未設定のタスクは、未完了であれば常に含める
                if task.get("status") != "completed":
                    filtered_tasks.append(task)
                continue
            try:
                due_dt = self._parse_iso_datetime(due)
            except (ValueError, TypeError) as e:
                logger.debug(f"タスクの期限解析に失敗しました。スキップします: {task.get('id')}, エラー: {e}")
                continue
            if window_start <= due_dt <= window_end:
                filtered_tasks.append(task)

        return {"events": filtered_events, "tasks": filtered_tasks}

    def _format_event_time(self, start: Dict[str, Any], end: Dict[str, Any]) -> str:
        """
        start/end辞書のdateまたはdateTimeから終日判定・時刻表示文字列を組み立てる。
        Googleカレンダーの終日イベントはend.dateが「排他的（最終日の翌日）」で返ってくる仕様のため、
        単純な start_date == end_date 判定では単日の終日イベントを検出できない。
        end.dateから1日引いた「最終日」を使って単日/複数日を判定する。
        """
        start_date = start.get("date")
        end_date = end.get("date")
        if start_date and end_date:
            try:
                start_d = datetime.date.fromisoformat(start_date)
                end_d = datetime.date.fromisoformat(end_date)
                last_day = end_d - datetime.timedelta(days=1)
            except ValueError:
                return "終日"
            if last_day <= start_d:
                return "終日"
            return f"終日（{start_date}〜{last_day.isoformat()}）"

        start_dt_str = start.get("dateTime", "") or ""
        end_dt_str = end.get("dateTime", "") or ""
        start_time = start_dt_str[11:16] if "T" in start_dt_str else ""
        end_time = end_dt_str[11:16] if "T" in end_dt_str else ""
        if start_time and end_time:
            return f"{start_time}-{end_time}"
        return start_time or end_time or "時刻不明"

    def _normalize_text(self, text: str) -> str:
        """改行・制御文字の除去、tasks.google.comを含むdescriptionの除外を行う。"""
        if not text:
            return ""
        if "tasks.google.com" in text:
            return ""
        normalized = text.replace("\r\n", " ").replace("\r", " ").replace("\n", " ")
        return normalized.strip()

    def _event_date(self, start: Dict[str, Any]) -> datetime.date:
        """イベントのstart辞書（dateTimeまたはdate）からローカル日付を取り出す。"""
        value = start.get("dateTime") or start.get("date")
        if not value:
            return datetime.datetime.now().astimezone().date()
        try:
            return self._parse_iso_datetime(value).date()
        except (ValueError, TypeError):
            return datetime.datetime.now().astimezone().date()

    def _format_date_label(self, date_obj: datetime.date, today: datetime.date) -> str:
        """
        "YYYY-MM-DD(曜)"に加えて、今日を基準にした相対ラベル（今日/昨日/明日）を付記する。
        窓が前後24時間＝最大3暦日にまたがるため、時刻(HH:MM)だけでは
        「どの日の予定か」をAI側が推測するしかなくなる（実際に前日の予定を当日と誤認する不具合の原因になった）。
        日付の特定・相対ラベル付けはコード側で確定させ、AIに日付計算を委ねないようにする。
        """
        weekday_ja = ["月", "火", "水", "木", "金", "土", "日"]
        label = f"{date_obj.isoformat()}({weekday_ja[date_obj.weekday()]})"
        delta_days = (date_obj - today).days
        if delta_days == 0:
            label += " 今日"
        elif delta_days == -1:
            label += " 昨日"
        elif delta_days == 1:
            label += " 明日"
        return label

    def _group_events_by_date(self, events: list) -> Dict[datetime.date, list]:
        """イベントをローカル日付ごとにグループ化し、各グループ内は開始時刻順に並べる。"""
        grouped: Dict[datetime.date, list] = {}
        for event in events:
            date_obj = self._event_date(event.get("start", {}) or {})
            grouped.setdefault(date_obj, []).append(event)
        for date_obj, group in grouped.items():
            group.sort(key=lambda e: (e.get("start", {}) or {}).get("dateTime")
                                      or (e.get("start", {}) or {}).get("date") or "")
        return grouped

    def _to_markdown_table(self, rows: List[Dict[str, str]], columns: List[str]) -> str:
        """
        行のリストをMarkdownテーブル形式の文字列に変換する。
        services/UserDataLogger.py:_to_markdown_table() と同じ書式（ヘッダー行＋区切り行、
        セル内の"|"は全角"｜"にエスケープ）に揃えている。
        """
        def escape(s):
            return str(s).replace("|", "｜")
        header = "| " + " | ".join(columns) + " |"
        separator = "|" + "|".join(["---"] * len(columns)) + "|"
        body = ["| " + " | ".join(escape(row.get(col, "")) for col in columns) + " |" for row in rows]
        return "\n".join([header, separator] + body)

    def _format_text(self, filtered: Dict[str, Any], fetched_at: str) -> str:
        """
        events/tasksをMarkdownテーブル形式に整形する。
        現在時刻を明示し、予定は「日付」列を必ず持たせることで、
        「HH:MMだけでは日付が一意に決まらない」問題を避ける。
        カレンダー名は分類名（マイカレンダーでの表示名）で統一し、アカウント名は出さない
        （collectors/GoogleCalendarCollector.py側でsummaryOverride優先に解決済み）。
        """
        now = datetime.datetime.now().astimezone()
        today = now.date()
        lines = [f"（現在時刻: {self._format_date_label(today, today)} {now.strftime('%H:%M')}）", ""]

        events = filtered.get("events", [])
        if events:
            grouped = self._group_events_by_date(events)
            rows = []
            for date_obj in sorted(grouped.keys()):
                date_label = self._format_date_label(date_obj, today)
                for event in grouped[date_obj]:
                    time_str = self._format_event_time(event.get("start", {}) or {}, event.get("end", {}) or {})
                    summary = event.get("summary") or "（タイトルなし）"
                    description = self._normalize_text(event.get("description", ""))
                    calendar_name = event.get("calendarSummary") or "-"
                    rows.append({
                        "日付": date_label,
                        "時刻": time_str,
                        "カレンダー": calendar_name,
                        "予定": summary,
                        "詳細": description,
                    })
            lines.append("【予定】")
            lines.append(self._to_markdown_table(rows, ["日付", "時刻", "カレンダー", "予定", "詳細"]))
        else:
            lines.append("【予定】直近24時間・今後24時間に予定はありません。")

        lines.append("")

        tasks = filtered.get("tasks", [])
        if tasks:
            rows = []
            for task in tasks:
                title = task.get("title") or "（タイトルなしタスク）"
                status = "完了" if task.get("status") == "completed" else "未完了"
                due = task.get("due") or ""
                if due:
                    try:
                        due_date = self._parse_iso_datetime(due).date()
                        due_label = self._format_date_label(due_date, today)
                    except (ValueError, TypeError):
                        due_label = due[:10]
                else:
                    due_label = "-"
                rows.append({"状態": status, "タスク": title, "期限": due_label})
            lines.append("【タスク】")
            lines.append(self._to_markdown_table(rows, ["状態", "タスク", "期限"]))
        else:
            lines.append("【タスク】該当する期限のタスクはありません。")

        lines.append("")
        lines.append(f"（カレンダー情報のキャッシュ取得時刻: {fetched_at}）")
        return "\n".join(lines)

    def execute(self, args: Dict[str, Any]) -> str:
        """
        オーケストレーションのみ: _load_cache() → Noneなら固定文言 → _filter_within_window() → _format_text()。
        ネットワークI/Oや認証状態の判断は一切行わない（読み取り専用）。
        """
        data = self._load_cache()
        if data is None:
            return (
                "Googleカレンダー連携は現在利用できません"
                "（未設定・未認証、またはキャッシュがまだ取得できていません）。"
            )
        filtered = self._filter_within_window(data)
        return self._format_text(filtered, data.get("fetched_at", "不明"))

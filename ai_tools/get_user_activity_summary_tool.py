import json
import os
from datetime import datetime, timedelta
from typing import Dict, Any, List
import logging

from ai_tools.tool_base import BaseTool

logger = logging.getLogger(__name__)

class GetUserActivitySummaryTool(BaseTool):
    """
    ユーザーの過去の活動履歴から、指定された時間範囲の要約を取得するツール。
    要約が存在しない場合は、関連する分単位の活動ログを返します。
    ログ自体が存在しない場合は、その旨を伝えます。
    """

    @property
    def name(self) -> str:
        return "get_user_activity_summary"

    @property
    def description(self) -> str:
        return "ユーザーの過去の活動履歴から、指定された時間範囲の要約を取得します。ユーザーの過去の行動や興味を理解するために使用します。要約が存在しない場合は、関連する分単位の活動ログを返します。ログ自体が存在しない場合は、その旨を伝えます。"

    @property
    def args_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "target_time": {
                    "type": "string",
                    "description": "要約を取得したい時刻または日付。時間単位の場合は 'YYYY-MM-DD HH' 形式（例: '2026-04-09 10'）、日単位の場合は 'YYYY-MM-DD' 形式（例: '2026-04-08'）。",
                },
                "scope": {
                    "type": "string",
                    "enum": ["hour", "day"],
                    "description": "要約の範囲。'hour' または 'day'。",
                },
            },
            "required": ["target_time", "scope"],
        }

    def _get_user_logs_dir(self) -> str:
        """user_logsディレクトリの絶対パスを返す。"""
        # ai_tools/get_user_activity_summary_tool.py から見て、
        # ../user_logs が user_logs ディレクトリになる
        current_dir = os.path.dirname(os.path.abspath(__file__))
        return os.path.join(current_dir, "..", "user_logs")

    def _load_data_from_file(self, date_str: str) -> Dict[str, Any]:
        """指定日のログファイルを読み込む。"""
        filepath = os.path.join(self._get_user_logs_dir(), f"{date_str}.json")
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError) as e:
            logger.debug(f"ログファイルの読み込みに失敗しました: {filepath}, エラー: {e}")
            return {"logs": [], "hourlogs": [], "daylogs": []}

    def execute(self, args: Dict[str, Any]) -> str:
        target_time_str = args["target_time"]
        scope = args["scope"]

        try:
            # 日付情報の解析
            if len(target_time_str) <= 10: # YYYY-MM-DD 形式
                dt_object = datetime.strptime(target_time_str, "%Y-%m-%d")
            elif ":" not in target_time_str: # YYYY-MM-DD HH 形式
                dt_object = datetime.strptime(target_time_str, "%Y-%m-%d %H")
            else: # YYYY-MM-DD HH:MM 形式 (Toolの引数としては想定外だが念のため)
                dt_object = datetime.strptime(target_time_str, "%Y-%m-%d %H:%M")
            
            target_date_str = dt_object.strftime("%Y-%m-%d")
        except ValueError:
            return f"エラー: 不正な時刻フォーマットです。'YYYY-MM-DD HH' または 'YYYY-MM-DD' 形式を使用してください。入力: {target_time_str}"

        # ログデータを読み込む
        data = self._load_data_from_file(target_date_str)
        if not data["logs"] and not data["hourlogs"] and not data["daylogs"]:
            return "指定された日付のログは存在しません。"

        summary_found = False
        summary_text = ""
        
        # 要約の検索
        if scope == "hour":
            target_hour_key = dt_object.strftime("%Y-%m-%d %H")
            for log in data.get("hourlogs", []):
                if log.get("time") == target_hour_key:
                    summary_text = log.get("summary", "")
                    summary_found = True
                    break
        elif scope == "day":
            target_day_key = dt_object.strftime("%Y-%m-%d")
            for log in data.get("daylogs", []):
                if log.get("time") == target_day_key:
                    summary_text = log.get("summary", "")
                    summary_found = True
                    break
        
        if summary_found and summary_text:
            return f"ユーザー活動要約 ({scope} {target_time_str}): {summary_text}"
        
        # 要約が見つからない場合、分単位のログを返す
        detailed_logs = []
        if scope == "hour":
            target_hour_prefix = dt_object.strftime("%Y-%m-%d %H:")
            for log in data.get("logs", []):
                if log.get("time", "").startswith(target_hour_prefix):
                    detailed_logs.append(f"- {log.get('time').split(' ')[1]}: {log.get('window')} ({log.get('media')})")
        elif scope == "day":
            # hourlogsにない時間帯の生ログを収集
            summarized_hours = {log['time'].split(' ')[1] for log in data.get("hourlogs", [])} # "YYYY-MM-DD HH"
            for log in data.get("logs", []):
                log_hour_key = datetime.strptime(log.get('time'), "%Y-%m-%d %H:%M:%S").strftime("%Y-%m-%d %H")
                if log_hour_key not in summarized_hours:
                    detailed_logs.append(f"- {log.get('time').split(' ')[1]}: {log.get('window')} ({log.get('media')})")
            
            # hourlogsの要約も追加
            for log in data.get("hourlogs", []):
                detailed_logs.append(f"- {log.get('time').split(' ')[1]}: {log.get('summary')}")

        if detailed_logs:
            return f"指定された時間 ({scope} {target_time_str}) の要約は見つかりませんでしたが、以下の活動ログが見つかりました:\n" + "\n".join(detailed_logs)
        else:
            return f"指定された時間 ({scope} {target_time_str}) の要約も活動ログも存在しません。"

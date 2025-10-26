"""
一定時間ごとにユーザデータをwindowsInfoCollecterに問い合わせ。
ログファイルに保存する。n時間ごとにLLMを使ってその時間帯での全体的なサマリーを作成、保存するようにする。

"""


import json
import os
from datetime import datetime
from collections import defaultdict


# --------------------------------------------------------------------------
# メインクラス
# --------------------------------------------------------------------------


class UserActivityManager:
    """
    ユーザーのPC利用状況を記録・管理するクラス。

    日ごとのJSONファイル（YYYYMMDD.json）にログを保存し、
    時間ごとのサマリーや日ごとのサマリーを管理する機能を提供します。
    """
    def __init__(self, storage_dir: str = "."):
        """
        コンストラクタ。

        Args:
            storage_dir (str): JSONファイルを保存するディレクトリ。
        """
        self.storage_dir = storage_dir
        os.makedirs(self.storage_dir, exist_ok=True)
        self.filepath = self._get_filepath_for_today()
        self._initialize_json_if_needed()

    def _get_filepath_for_today(self) -> str:
        """今日の日付に基づいたJSONファイルのパスを生成します。"""
        today_str = datetime.now().strftime("%Y%m%d")
        return os.path.join(self.storage_dir, f"{today_str}.json")

    def _initialize_json_if_needed(self):
        """JSONファイルが存在しない場合、初期構造で新規作成します。"""
        if not os.path.exists(self.filepath):
            initial_data = {
                "logs": [],
                "hourlogs": [],
                "daylogs": {
                    "summary": ""
                }
            }
            self._save_data(initial_data)

    def _load_data(self) -> dict:
        """JSONファイルからデータを読み込みます。"""
        try:
            with open(self.filepath, 'r', encoding='utf-8') as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            # ファイルが破損または存在しない場合は初期化
            self._initialize_json_if_needed()
            return self._load_data()

    def _save_data(self, data: dict):
        """データをJSONファイルに書き込みます。"""
        with open(self.filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

    def add_userlog(self, time:str, window_title: str, media_info: str):
        """
        新しいアクティビティログを記録します。

        Args:
            window_title (str): アクティブウィンドウのタイトル。
            media_info (str): 再生中のメディア情報。
        """
        data = self._load_data()
        now = time
        
        new_log = {
            "time": now,
            "window": window_title,
            "media": media_info
        }
        
        data["logs"].append(new_log)
        self._save_data(data)
        print(f"[{new_log['time']}] ログを追加しました: {window_title}")

    def create_and_save_hourly_summary(self):
        """
        現在の時間帯のログから要約を生成し、保存します。
        例：11:55に実行すると、11時台のログを要約します。
        """
        now = datetime.now()
        target_hour_str = now.strftime("%H")
        
        data = self._load_data()
        
        # 対象時間のログを抽出
        target_logs = [
            log for log in data["logs"] 
            if log["time"].startswith(target_hour_str + ":")
        ]
        
        if not target_logs:
            print(f"{target_hour_str}時台のログはありません。")
            return
            
        # LLM（ダミー）で要約を生成
        summary_text = summarize_with_llm(target_logs)
        
        new_summary = {
            "time": target_hour_str,
            "summary": summary_text
        }
        
        # 既存のサマリーがあれば更新、なければ追加
        hourlog_found = False
        for i, hourlog in enumerate(data["hourlogs"]):
            if hourlog["time"] == target_hour_str:
                data["hourlogs"][i] = new_summary
                hourlog_found = True
                break
        
        if not hourlog_found:
            data["hourlogs"].append(new_summary)
            
        self._save_data(data)
        print(f"\n--- {target_hour_str}時台のサマリーを生成/更新しました ---")
        print(summary_text)
        print("------------------------------------------\n")

    def create_and_save_daily_summary(self):
        """
        その日の全てのログから日次要約を生成し、保存します。
        """
        data = self._load_data()
        all_logs = data["logs"]
        
        if not all_logs:
            print("本日のログはありません。日次サマリーは作成できません。")
            return
            
        # LLM（ダミー）で要約を生成
        summary_text = summarize_with_llm(all_logs)
        
        data["daylogs"]["summary"] = summary_text
        self._save_data(data)
        
        print(f"\n--- 本日のサマリーを生成しました ---")
        print(summary_text)
        print("-------------------------------------\n")


if __name__ == '__main__':
    # --- このプログラムの実行例 ---
    
    # 1. マネージャークラスのインスタンスを作成
    #    実行ディレクトリに "user_logs" フォルダが作成され、その中にJSONが保存されます。
    activity_manager = UserActivityManager(storage_dir="user_logs")

    # 2. 5分ごとにログを記録する処理をシミュレート
    print("--- ログ記録シミュレーション開始 ---")
    for i in range(5):
        activity_manager.add_log(f"time{i}", f"window{i}", f"media{i}")
    
    # 3. 特定の時間になったと仮定し、時間ごとのサマリーを作成
    #    （この例では直前に追加したログが対象になります）
    activity_manager.create_and_save_hourly_summary()

    # 4. ユーザーの指示または一日の終わりに日次サマリーを作成
    activity_manager.create_and_save_daily_summary()
    
    # 5. 生成されたJSONファイルの中身を確認
    print(f"\nデータは {activity_manager.filepath} に保存されました。")
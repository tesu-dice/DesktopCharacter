import datetime
from typing import Dict, Any
import asyncio

# 必要なライブラリを直接インポート
import win32gui
try:
    from winrt.windows.media.control import (
        GlobalSystemMediaTransportControlsSessionManager as MediaManager,
        GlobalSystemMediaTransportControlsSessionMediaProperties as MediaProperties,
        GlobalSystemMediaTransportControlsSessionPlaybackInfo as PlaybackInfo,
        GlobalSystemMediaTransportControlsSessionPlaybackStatus as PlaybackStatus
    )
    WINRT_AVAILABLE = True
except ImportError:
    WINRT_AVAILABLE = False

from ai_tools.tool_base import BaseTool

# --- 1. 現在時刻を取得するツール ---
class GetCurrentTimeTool(BaseTool):
    """現在の日時を取得するツール。"""

    @property
    def name(self) -> str:
        return "get_current_time"

    @property
    def description(self) -> str:
        return "現在の正確な日時を「YYYY-MM-DD HH:MM」の形式で取得します。"

    @property
    def args_schema(self) -> Dict[str, Any]:
        return {"type": "object", "properties": {}}

    def execute(self, args: Dict[str, Any] = None) -> str:
        now = datetime.datetime.now()
        return now.strftime(f"現在の日時は %Y年%m月%d日 %H時%M分 です。")


# --- 2. アクティブウィンドウを取得するツール ---
class GetActiveWindowTool(BaseTool):
    """アクティブウィンドウのタイトルを取得するツール。"""

    @property
    def name(self) -> str:
        return "get_active_window"

    @property
    def description(self) -> str:
        return "現在フォアグラウンドでアクティブになっているウィンドウのタイトルを取得します。ユーザーが現在どのアプリケーションやファイルを扱っているかを知るのに役立ちます。"

    @property
    def args_schema(self) -> Dict[str, Any]:
        return {"type": "object", "properties": {}}

    def execute(self, args: Dict[str, Any] = None) -> str:
        try:
            window_title = win32gui.GetWindowText(win32gui.GetForegroundWindow())
            window_title = window_title.replace(" — ", " - ")
            infos = window_title.split(" - ")
            if len(infos) == 2:
                result = f"{infos[1]}: {infos[0]}"
            elif len(infos) > 2:
                remaining_parts = " - ".join(infos[:-2])
                result = f"{infos[-1]}: {infos[-2]}[{remaining_parts}]"
            else:
                result = window_title
            return f"現在のアクティブウィンドウは「{result}」です。"
        except Exception as e:
            return f"エラー: アクティブウィンドウの取得中にエラーが発生しました: {e}"


# --- 3. 再生中のメディアを取得するツール ---
class GetPlayingMediaTool(BaseTool):
    """再生中のメディア情報を取得するツール。"""

    @property
    def name(self) -> str:
        return "get_playing_media"

    @property
    def description(self) -> str:
        return "現在再生中の音楽や動画の情報を取得します。（例: 曲名 by アーティスト名）"

    @property
    def args_schema(self) -> Dict[str, Any]:
        return {"type": "object", "properties": {}}

    async def _get_media_info_async(self):
        """非同期でメディア情報を取得する内部メソッド。"""
        if not WINRT_AVAILABLE:
            return "メディア情報取得に必要なライブラリ(winrt)がインストールされていません。"
        
        try:
            media_manager = await MediaManager.request_async()
            current_session = media_manager.get_current_session()
            if current_session:
                media_properties: MediaProperties = await current_session.try_get_media_properties_async()
                playback_info: PlaybackInfo = current_session.get_playback_info()

                if media_properties and playback_info:
                    media_title = media_properties.title or '[情報なし]'
                    media_artist = media_properties.artist or '[情報なし]'
                    media_state = PlaybackStatus(playback_info.playback_status).name
                    
                    if media_state == "PLAYING":
                        return f"{media_title} by {media_artist}"
            return "再生中のメディアなし"
        except Exception as e:
            return f"メディア情報の取得に失敗しました: {e}"

    def execute(self, args: Dict[str, Any] = None) -> str:
        try:
            # 非同期メソッドを同期的に呼び出す
            return f"現在再生中のメディア: {asyncio.run(self._get_media_info_async())}"
        except RuntimeError:
            # 既にイベントループが実行中の場合のフォールバック
            try:
                loop = asyncio.get_running_loop()
                task = loop.create_task(self._get_media_info_async())
                # この方法は完了待機が複雑なため、エラーメッセージを返すに留める
                return "非同期処理の実行に問題が発生しました。イベントループが競合している可能性があります。"
            except Exception as inner_e:
                return f"エラー: メディア情報の取得中に予期せぬ非同期エラーが発生しました: {inner_e}"
        except Exception as e:
            return f"エラー: メディア情報の取得中にエラーが発生しました: {e}"

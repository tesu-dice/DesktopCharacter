"""
Windowsからデータを取得して受け渡す用のクラス

"""
#ライブラリ
import time
import datetime
import asyncio
import win32gui #pip install pywin32
from screeninfo import get_monitors
from winrt.windows.media.control import (
    GlobalSystemMediaTransportControlsSessionManager as MediaManager,
    GlobalSystemMediaTransportControlsSessionMediaProperties as MediaProperties,
    GlobalSystemMediaTransportControlsSessionPlaybackInfo as PlaybackInfo,
    GlobalSystemMediaTransportControlsSessionPlaybackStatus as PlaybackStatus
)

#プログラム間でのインポート
from services.config_controller import UserSettings
from services.Event_Bus import EventBus


class win_info_collector():
    def __init__(self, _bus:EventBus, UserSetting :UserSettings, debug = -1):
        self.time_init = datetime.datetime.now()
        self.time_last = datetime.datetime.now()
        self.bus = _bus
        self.usersetting = UserSetting
        if debug >= 0:
            indent = "  " * debug
            print(f"{indent}win_info_collector.__init__() called.")
            print(f"{indent}{self.get_datetime()}")
            print(f"{indent}{self.get_nowday()}")
            print(f"{indent}{self.get_activate_window()}")
            self.get_plaing_media(debug = debug + 1)
            get_TotalMonitorSize(debug=debug + 1)
            debug = debug + 1 if debug >= 0 else -1
            
    #作業中のウィンドウのID取得してそのタイトルを文字列で返す。
    def get_activate_window(self):
        window_title = win32gui.GetWindowText(win32gui.GetForegroundWindow())
        return window_title
    
    #再生中のメディアを取得
    def get_plaing_media(self, debug=-1):
        #実際に動作するのは_get_media_info(). 非同期的に動作するので分割。self側で履歴管理とかするならここで。
        return asyncio.run(_get_media_info(debug=debug))

    
        
    # YYYY-MM-DD hh:mm 形式の現在時刻を文字列で返す。
    def get_datetime(self):
        now = datetime.datetime.now()
        return now.strftime(f"%Y-%m-%d %H:%M")

    #今日の日付を取得
    def get_nowday(self):
        day = datetime.datetime.now
        day = datetime.date.today()
        #print("win_info_collector get_nowday() day = " + str(day) ) 
        return day
    
    def check_freetime(self, debug = -1):
        freetime =  datetime.datetime.now() - self.time_last
        freetime = freetime.seconds
        if debug >= 0:
            indent = "  " * debug
            print(f"{indent}経過時間(秒) = ", freetime, "会話周期(秒)= ", self.usersetting.get_setting_value("ApplicationSettings.ActiveSpeak.Time"))
            debug = debug + 1 if debug >= 0 else -1
        
        if freetime >= self.usersetting.get_setting_value("ApplicationSettings.ActiveSpeak.Time"):
            self.time_last = datetime.datetime.now()
            return True
        else:
            return False
    
# モニターを検出、すべての画面を含んだ左上の座標と右下の座標を取得ー＞左上のx,y、右下までのwidth, height
def get_TotalMonitorSize(debug = -1):
    monitors = get_monitors()
    
    #すべてのウィンドウでの一番左上端を計算
    min_x, min_y = 0, 0
    for m in monitors:
        if m.x < min_x:
            min_x = m.x
        if m.y < min_y:
            min_y = m.y
    
    #すべてのウィンドウでの左上端から右下端までの距離を計算
    maxwidth, maxheight = 0, 0
    for m in monitors:
        if m.x + m.width > maxwidth:
            maxwidth = m.x + m.width + abs(min_x)
        if m.y + m.height > maxheight:
            maxheight = m.y + m.height + abs(min_y)
    
    if debug >= 0:
        indent = "  " * debug
        print(f"{indent}get_TotalMonitorSize() called.")
        print(f"{indent}検出されたモニター:")
        for i, m in enumerate(monitors):
            print(f"{indent}  モニター {i}: 幅={m.width}, 高さ={m.height}, X={m.x}, Y={m.y}, プライマリ={m.is_primary}, ウィンドウ名={m.name}, 画面の長さ{m.height_mm}mm x {m.width_mm}mm")
        print(f"{indent}全結合画面サイズ{maxwidth}x{maxheight}, 左上の座標(x,y):({min_x}{min_y})")
    return maxwidth, maxheight, min_x, min_y

#再生中のメディアを取得
async def _get_media_info(debug = -1) -> str:
    try:
        media_manager = await MediaManager.request_async()
        current_session = media_manager.get_current_session()
        if current_session != None:
            media_properties: MediaProperties = await current_session.try_get_media_properties_async()
            if media_properties:
                media_title = media_properties.title if media_properties.title else '[情報なし]'
                media_artist = media_properties.artist if media_properties.artist else '[情報なし]'
            playback_info: PlaybackInfo = current_session.get_playback_info()
            if playback_info:
                media_state = PlaybackStatus(playback_info.playback_status).name 
        else:
            media_state = "取得失敗"
            media_title = "取得失敗"
            media_artist = "取得失敗"
    except Exception as e:
        print(f"WindowsMediaの取得に失敗しました。エラー:\n   {e}")
    if debug >= 0:
        indent = "  " * debug
        print(f"{indent}WindowsInfoCollector._get_media_info() called.")
        print(f"{indent}現在のメディア状態: {media_state}")
        print(f"{indent}現在のメディアタイトル: {media_title}")
        print(f"{indent}現在のメディアアーティスト: {media_artist}")
    if media_state == "PLAYING":
        return f"{media_title} by {media_artist}"
    else:
        return "再生中のメディアなし"
        



if __name__ == "__main__":
    #このプログラムのみのテスト用
    import config_controller
    setting = config_controller.read_configfile("config.json")
    if setting is None:
        print("コンフィグファイルの読み込みに失敗しました。")
    this = win_info_collector(setting,debug=0)

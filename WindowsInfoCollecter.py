"""
Windowsからデータを取得して受け渡す用のクラス

"""
import datetime
import win32gui #pip install pywin32
from screeninfo import get_monitors


class win_info_collector():
    def __init__(self, debug = False):
        self.time_init = datetime.datetime.now()
        self.time_last = datetime.datetime.now()
        if debug == True:
            print(self.get_datetime())
            print(self.get_nowday())
            print(get_TotalMonitorSize(debug=debug))
            print(self.get_activate_window())

    #作業中のウィンドウのIDゲットしてそのタイトルを文字列で返す。
    def get_activate_window(self):
        window_title = win32gui.GetWindowText(win32gui.GetForegroundWindow())
        return window_title
    
    #YYYY-MM-DD hh:mm:ss.ssssを文字列で返す。
    def get_datetime(self):
        nowtime = str(datetime.datetime.now())
        #print("win_info_collecter get_nowtime() nowtime = " + nowtime )
        return nowtime

    #今日の日付を取得
    def get_nowday(self):
        day = datetime.datetime.now
        day = datetime.date.today()
        #print("win_info_collector get_nowday() day = " + str(day) ) 
        return day
    
    def check_freetime(self):
        freetime =  datetime.datetime.now() - self.time_last
        freetime = freetime.seconds
        if freetime >= 300:
            self.time_last = datetime.datetime.now()
            return True
        else:
            return False
    
# モニターを検出、すべての画面を含んだ左上の座標と右下の座標を取得ー＞左上のx,y、右下までのwidth, height
def get_TotalMonitorSize(debug = False):
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
    
    if debug == True:
        print("検出されたモニター:")
        for i, m in enumerate(monitors):
            print(f"  モニター {i}: 幅={m.width}, 高さ={m.height}, X={m.x}, Y={m.y}, プライマリ={m.is_primary}, ウィンドウ名={m.name}, 画面の長さ{m.height_mm}mm x {m.width_mm}mm")
        print("関数での返り値:トータル画面幅、トータル画面高さ、左上のx座標、左上のy座標")
        print(maxwidth, maxheight, min_x, min_x)
    return maxwidth, maxheight, min_x, min_y


if __name__ == "__main__":
    this = win_info_collector(debug=True)

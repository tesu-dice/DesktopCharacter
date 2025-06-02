"""
Windowsからデータを取得して受け渡す用のクラス

"""
import datetime
import win32gui
from screeninfo import get_monitors


class win_info_collector():
    def __init__(self):
        self.time_init = datetime.datetime.now()
        self.time_last = datetime.datetime.now()
        self.get_datetime()
        self.get_nowday()
        self.get_monitors_list()

    #作業中のウィンドウのIDゲットしてそのタイトルを文字列で返す。
    def get_activate_window(self):
        window_title = win32gui.GetWindowText(win32gui.GetForegroundWindow())
        return window_title
    
    #YYYY-MM-DD hh:mm:ss.ssssを文字列で返す。
    def get_datetime(self):
        nowtime = str(datetime.datetime.now())
        print("win_info_collecter get_nowtime() nowtime = " + nowtime )
        return nowtime

    #今日の日付を取得
    def get_nowday(self):
        day = datetime.datetime.now
        day = datetime.date.today()
        print("win_info_collector get_nowday() day = " + str(day) ) 
        return day
    
    def check_freetime(self):
        freetime =  datetime.datetime.now() - self.time_last
        freetime = freetime.seconds
        if freetime >= 300:
            self.time_last = datetime.datetime.now()
            return True
        else:
            return False
    
    # モニターを検出、リストを返す。
    def get_monitors_list(self):
        monitors = get_monitors()
        print("検出されたモニター:")
        for i, m in enumerate(monitors):
            print(f"  モニター {i}: 幅={m.width}, 高さ={m.height}, X={m.x}, Y={m.y}, プライマリ={m.is_primary}, ウィンドウ名={m.name}, 画面の長さ{m.height_mm}mm x {m.width_mm}mm")
        return monitors

    # UIオブジェクトをmonitorに配置　※検討中につき一次的に中断＆保留20250528
    def place_window_to_monitor(self, ui_object, monitor_num):
        selected_index = monitor_num
        if 0 <= selected_index < len(self.get_monitors_list()):
            monitor = self.get_monitors_list()[selected_index]
            
            # ウィンドウをモニターの中央に配置するための計算
            window_width = ui_object.winfo_width() # 現在のウィンドウの幅
            window_height = ui_object.winfo_height() # 現在のウィンドウの高さ
            print(f"ウィンドウの幅: {window_width}, 高さ: {window_height}")
            print(f"モニターの幅: {monitor.width}, 高さ: {monitor.height}")
            
            x_pos = monitor.x + (monitor.width - window_width) // 2
            y_pos = monitor.y + (monitor.height - window_height) // 2
            
            ui_object.place(x = x_pos, y = y_pos)
            print(f"ウィンドウをモニター {selected_index} に配置しました。座標: {x_pos},{y_pos}")
        else:
            print("無効なモニター選択です。")

        
        



        




if __name__ == "__main__":
    this = win_info_collector()

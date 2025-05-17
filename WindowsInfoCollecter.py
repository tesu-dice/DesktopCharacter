"""
Windowsからデータを取得して受け渡す用のクラス

"""
import datetime
import win32gui


class win_info_collector():
    def __init__(self):
        print("win_info_collecter init() called")
        self.time_init = datetime.datetime.now()
        self.time_last = datetime.datetime.now()
        self.get_datetime()
        self.get_nowday()

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
        print(freetime)
        print(type(freetime))
        if freetime >= 300:
            self.time_last = datetime.datetime.now()
            return True
        else:
            return False
        




if __name__ == "__main__":
    this = win_info_collector()

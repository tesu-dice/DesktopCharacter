"""
いろいろなプログラムの中継訳
"""
#ライブラリ
import subprocess

#プログラム
import UI_main
import geminiAPI
import WindowsInfoCollecter
import config_controller

class myapp():
    def __init__(self):
       
        #voicevoxを起動
        try:
            result = subprocess.Popen("windows-nvidia/run.exe")
        except Exception as e:
            print("VoiceVoxEngineの実行に失敗しました。")
            print(e)

         #初期化
            #ユーザで他の読み込み
        self.setting = config_controller.read_configfile("config.json")
        if self.setting is None:
            print("コンフィグファイルの読み込みに失敗しました。")
        self.ai = geminiAPI.geminiAI(self.setting)
        self.WinInfo = WindowsInfoCollecter.win_info_collector()
        self.ui = UI_main.UI(self, self.setting)
        

        
        self.ui.after(500, self.update)
        start_app(self)

    def reboot_app(self):
        self.ui.destroy()
        self.__init__()
        start_app(self)



    #入力テキストをAIに伝え、UIにログを追加
    def SendMessage_toAI(self, text):
        t = "現在時刻：" + self.WinInfo.get_datetime() + "\n"
        w = "作業中窓：" + self.WinInfo.get_activate_window() + "\n"
        # ユーザーメッセージのログ追加は TalkWindow 側で行う
        # self.ui.add_log(t + w + text) # この行は不要になりました

        img , response = self.ai.response(t + w + text)

        self.ui.update_character_image(img)
        if self.ui.talk_window and self.ui.talk_window.winfo_exists() and self.ui.talk_window.winfo_ismapped():
             self.ui.talk_window.add_log(">>>\n" + response) # AI応答を TalkWindow に追加

    #状態監視の実行
    def update(self):
        print("main.py update() called")
        if self.WinInfo.check_freetime():
            self.SendMessage_toAI("System:ユーザは上記のように作業中です。話しかけてください。")
        self.ui.after(10000, self.update)




def start_app(app = None):
    print("main.py start")
    if app == None:
        app = myapp()
    app.ui.mainloop()


if __name__ =="__main__":
    start_app()
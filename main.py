"""
いろいろなプログラムの中継訳

"""
#ライブラリ
import subprocess

#プログラム
import UI
import geminiAPI
import WindowsInfoCollecter

class myapp():
    def __init__(self):
        #初期化
        self.ui = UI.UI(self)
        self.ai = geminiAPI.geminiAI()
        self.WinInfo = WindowsInfoCollecter.win_info_collector()

        #voicevoxを起動
        try:
            result = subprocess.Popen("windows-nvidia/run.exe")
        except Exception as e:
            print("VoiceVoxEngineの実行に失敗しました。")
            print(e)

    #UIからの入力テキストをAIに伝え、UIにログを追加
    def SendMessage_toAI(self, text):
        t = "現在時刻：" + self.WinInfo.get_datetime() + "\n"
        w = "作業中窓：" + self.WinInfo.get_activate_window() + "\n"
        self.ui.add_log(t + w + text)
        img , response = self.ai.response(t + w + text)
    
        self.ui.update_character_image(img)
        self.ui.add_log(response)

    #状態監視の実行
    def update(self):
        print("main.py update() called")
        if self.WinInfo.check_freetime():
            self.SendMessage_toAI("System:ユーザは以下のように作業中です。話しかけてください。")
        self.ui.win.after(5000, self.update)






print("main.py end")
if __name__ =="__main__":
    app = myapp()
    app.ui.win.after(500, app.update)

    app.ui.win.mainloop()
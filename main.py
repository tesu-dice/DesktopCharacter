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
from talk_VoiceVoxEngine import start_server


class myapp():
    def __init__(self):
        #ユーザで他の読み込み
        self.setting = config_controller.read_configfile("config.json")
        if self.setting is None:
            print("コンフィグファイルの読み込みに失敗しました。")
        #VOICEVOXEngineの起動
        if  self.setting.get_setting_value("VoiceSettings.VOICEVOX.autorun") == True and \
            self.setting.get_setting_value("VoiceSettings.VOICEVOX.path") != "":
            start_server(self.setting.get_setting_value("VoiceSettings.VOICEVOX.path"))
        #各要素の起動
        
        self.WinInfo = WindowsInfoCollecter.win_info_collector(self.setting)
        self.ui = UI_main.UI(self, self.setting)
        self.ai = geminiAPI.geminiAI(self.setting, self.ui)
        

        
        self.ui.after(500, self.update)
        start_app(self)
    #アプリケーションの再起動
    def reboot_app(self):
        self.ui.destroy()
        self.__init__()
        start_app(self)



    #入力テキストをAIに伝え、UIにログを追加
    def SendMessage_toAI(self, text):
        t, w, m = "", "", ""
        t = "現在時刻：" + self.WinInfo.get_datetime() + "\n"
        if self.setting.get_setting_value("ApplicationSettings.Permisson.ActiveWindow") == True:
            w = "作業中窓：" + self.WinInfo.get_activate_window() + "\n"
        if self.setting.get_setting_value("ApplicationSettings.Permisson.PlayingMedia") == True:
            m = "再生中のメディア：" #関数まだ作ってない。

        response_text = self.ai.response(t + w + m + text)
        self.ui.talk_window.add_log(">>>\n" + response_text) # AI応答を TalkWindow に追加

    #状態監視の実行
    def update(self, debug = False):
        if debug == True:
            print(f"main.py update() called. activespeak={self.setting.get_setting_value('ApplicationSettings.ActiveSpeak.on/off')}")
        if self.setting.get_setting_value("ApplicationSettings.ActiveSpeak.on/off") == True:    
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
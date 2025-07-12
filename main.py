
"""
いろいろなプログラムの起動と管理を行うメインプログラム
"""
#ライブラリ
import os

#プログラム
import UI_main
import geminiAPI
import WindowsInfoCollecter
import config_controller
from talk_VoiceVoxEngine import start_server
from release_check import check_nowver_is_newestver, CURRENT_APP_VERSION


class myapp():
    def __init__(self, engine_process = None, TalkHistory = None, debug = -1):
        #初期化
        self.engine_process = engine_process
        # TalkHistoryを安全に引き継ぐための作法
        if TalkHistory is None:
            self.TalkHistory = []
        else:
            self.TalkHistory = TalkHistory
            
        _start_info_texts ="" # 起動メッセージ用テキスト
        #デバックフラグの管理
        if debug > -1:
            indent = "  " * debug
            print(f"{indent}main.py __init__() called.")
            debug = debug + 1 if debug >= 0 else -1
            
        #リリースバージョンの確認
        CURRENT_APP_VERSION = "v0.0.0" # 現在のバージョンを設定
        _result = check_nowver_is_newestver("tesu-dice", "releace_check", CURRENT_APP_VERSION)
        if _result[0] == False:
            print(f"新しいバージョンが利用可能です！ 最新バージョン: {_result[1]}, 現在のバージョン: {_result[2]}")
            print("最新版をダウンロードしてください")
        else :
            print(f"お使いのバージョンは最新です。 最新バージョン: {_result[1]}, 現在のバージョン: {_result[2]}")
        _start_info_texts += f"---バージョン情報---:\n{'最新です。' if _result[0] else '更新があります。'} ({_result[1]}->{_result[2]})\n\n"
            
            
        #ユーザデータの読み込み
        self.setting = config_controller.read_configfile("config.json")
        if self.setting is None:
            print("コンフィグファイルの読み込みに失敗しました。")
        #VOICEVOXEngineの起動
        if  self.engine_process == None and \
            self.setting.get_setting_value("VoiceSettings.engine") == "VOICEVOX" and \
            self.setting.get_setting_value("VoiceSettings.VOICEVOX.autorun") == True and \
            self.setting.get_setting_value("VoiceSettings.VOICEVOX.path") != "":
            
            self.engine_process = start_server(self.setting.get_setting_value("VoiceSettings.VOICEVOX.path"), self.setting.get_setting_value("VoiceSettings.VOICEVOX.usegpu"),debug=debug)
            _start_info_texts += f"---VOICEVOXエンジンの起動---\n{('成功' if self.engine_process != False else '失敗')}\n\n"
        #各要素の起動
        self.WinInfo = WindowsInfoCollecter.win_info_collector(self.setting, debug=debug)
        self.ui = UI_main.UI(self, self.setting, debug=debug)
        self.ai = geminiAPI.geminiAI(self.setting, self, self.TalkHistory, debug=debug)
        
        self.ui.show_message_box("info", "DesktopCharacter起動メッセージ", str(_start_info_texts))
        self.ui.after(500, self.update)

    #アプリケーションの再起動
    def reboot(self, debug = -1):
        self.ui.destroy()
        # start_app に状態を引き継いで再起動
        start_app(engine_process=self.engine_process, TalkHistory=self.TalkHistory, debug=debug)
    
    #状態監視の実行
    def update(self, debug = -1):
        # print(self.setting.get_setting_value("ApplicationSettings.ActiveSpeak.Time"))
        if debug >= 0:
            indent = "  " * debug
            print(f"{indent}main.py update() called. activespeak={self.setting.get_setting_value('ApplicationSettings.ActiveSpeak.on/off')}")
            debug = debug + 1 if debug >= 0 else -1
        
        if self.setting.get_setting_value("ApplicationSettings.ActiveSpeak.on/off") == True:    
            if self.WinInfo.check_freetime():
                self.SendMessage_toAI("System:ユーザは上記のように作業中です。話しかけてください。", debug=debug)
        self.ui.after(10000, self.update)

    #入力テキストをAIに伝え、UIにログを追加
    def SendMessage_toAI(self, text, debug = -1):
        #会話送信テキストの準備と送信
        t, w, m = "", "", ""
        t = "現在時刻：" + self.WinInfo.get_datetime() + "\n"
        if self.setting.get_setting_value("ApplicationSettings.Permisson.ActiveWindow") == True:
            w = "アクティブなウィンドウ：" + self.WinInfo.get_activate_window() + "\n"
        if self.setting.get_setting_value("ApplicationSettings.Permisson.PlayingMedia") == True:
            m = "再生中のメディア：" + self.WinInfo.get_plaing_media(debug = debug + 1 if debug >= 0 else -1) + "\n"
        send_text = text + "\n"+ t + w + m 
        response_text = self.ai.response(send_text, debug=debug)
        #入力と返答をアプリ側へ反映
        self.add_talkhistory("user",send_text, debug=debug)
        self.add_talkhistory("model",response_text, debug=debug)

    def add_talkhistory(self,type, text, debug = -1):
        newhistory = {"role": f"{type}", "parts":[text]}
        self.TalkHistory.append(newhistory)
        #トークウィンドウがあればテキストを追加
        if self.ui.talk_window and self.ui.talk_window.winfo_exists():
            if debug > -1:
                indent = "  " * debug
                print(f"{indent}main.py add_talkhistory() called.")
                debug +=1
            self.ui.talk_window.add_log(newhistory)

def start_app(engine_process = None, TalkHistory = None, debug = -1):
    """
    アプリケーションを起動する唯一の関数。
    初回起動と再起動の両方を担う。
    """
    app = myapp(engine_process=engine_process, TalkHistory=TalkHistory, debug=debug)
    app.ui.mainloop()

def get_CharacterFolders(debug=-1):
    files = os.listdir("立ち絵")
    if debug >= 0:
        indent = "  " * debug
        print(f"{indent}UI.py get_CharacterFolders() called.")
        print(f"{indent}loaded files = {files}")
    return files

if __name__ =="__main__":
    # 初回起動
    start_app(debug=0)

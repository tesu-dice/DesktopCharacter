
"""
いろいろなプログラムの起動と管理を行うメインプログラム
"""
#ライブラリ
import os
import threading
import logging
import sys
#プログラム
from ui import UI_main
from ai import AI_main
from services import WindowsInfoCollecter
from services import config_controller
from services.Event_Bus import EventBus
from services.release_check import check_nowver_is_newestver
from tts.talk_VoiceVoxEngine import start_server


class myapp():
    def __init__(self, engine_process = None, TalkHistory = [], debug = -1):
        #初期化
        _setup_logging_info()
        self.engine_process = engine_process
        _start_info_texts ="" # 起動メッセージ用テキスト
        _start_info_error ="" # 起動エラーメッセージ用テキスト
        
        #デバックフラグの管理
        if debug > -1:
            indent = "  " * debug
            print(f"{indent}main.py __init__() called.")
            debug = debug + 1 if debug >= 0 else -1
            
        #リリースバージョンの確認
        CURRENT_APP_VERSION = "1.0.1" # 現在のバージョンを設定
        _result = check_nowver_is_newestver("tesu-dice", "DesktopCharacter_forRelease", CURRENT_APP_VERSION)
        if _result[0] == False:
            print(f"新しいバージョンが利用可能です！ 最新バージョン: {_result[1]}, 現在のバージョン: {_result[2]}")
            print("最新版をダウンロードしてください")
        else :
            print(f"お使いのバージョンは最新です。 最新バージョン: {_result[1]}, 現在のバージョン: {_result[2]}")
        _start_info_texts += f"---バージョン情報---\n{'最新です。' if _result[0] else '更新があります。'} [{_result[1]}] -> [{_result[2]}]\n\n"
            
            
        #ユーザデータの読み込み
        self.setting = config_controller.read_configfile("config.json")
        if self.setting is None:
            _start_info_error += f"設定ファイルの読み込みに失敗しました。\n"
            
        #VOICEVOXEngineの起動
        if  self.engine_process == None and \
            self.setting.get_setting_value("VoiceSettings.VOICEVOX.autorun") == True:
            
            self.engine_process = start_server(self.setting.get_setting_value("VoiceSettings.VOICEVOX.path"), self.setting.get_setting_value("VoiceSettings.VOICEVOX.usegpu"),debug=debug)
            _start_info_texts += f"---VOICEVOXエンジンの起動---\n{('成功' if self.engine_process != False else '失敗')}\n\n"

        

        #各要素の起動
        self.WinInfo = WindowsInfoCollecter.win_info_collector(self.setting, debug=debug)
        
        self.AI_Manager = AI_main.AI_Manager(self, self.setting, TalkHistory, debug=debug)
        
        self.ui = UI_main.UI(self, self.setting, debug=debug)

        #AIサービスとの接続確認
        if self.setting.get_setting_value("LLMSettings.Service") != "未選択":
            _start_info_texts += f"---AIサービスとの接続確認---\n"
            _result = self.AI_Manager.test_connection(debug=debug)
            _start_info_texts += f"{('成功' if _result[0] else '失敗')}\n\n"
            if _result[0] == False:
                _start_info_error += f"GeminiAPIの接続に失敗しました。:\n{_result[1]}\n\n"



        #起動メッセージ
        self.ui.show_message_box("info", "起動メッセージ", _start_info_texts)
        #エラーメッセージ
        if _start_info_error != "":
            self.ui.show_message_box("info", "エラーメッセージ", _start_info_error)
        
        #アプリケーション動作開始
        self.update(debug=debug)
        

    #アプリケーションの再起動
    def reboot(self, debug = -1):
        self.ui.after_cancel(self.update_id)
        self.ui.destroy()
        # start_app に状態を引き継いで再起動
        start_app(engine_process=self.engine_process, TalkHistory=self.AI_Manager.history, debug=debug)
    
    #状態監視の実行
    def update(self, debug = -1):
        print(self.setting.get_setting_value("ApplicationSettings.ActiveSpeak.Time"))
        if debug >= 0:
            indent = "  " * debug
            print(f"{indent}main.py update() called. activespeak={self.setting.get_setting_value('ApplicationSettings.ActiveSpeak.on/off')}")
            debug = debug + 1 if debug >= 0 else -1
        
        if self.setting.get_setting_value("ApplicationSettings.ActiveSpeak.on/off") == True:    
            if self.WinInfo.check_freetime():
                self.SendMessage_toAI("ユーザー作業中...", debug=debug)
        self.update_id = self.ui.after(10000, self.update, debug)

    #入力テキストをAIに伝える
    def SendMessage_toAI(self, text, debug = -1):
        #会話送信テキストの準備と送信
        t, w, m = "", "", ""
        if self.setting.get_setting_value("ApplicationSettings.Permisson.CurrentTime") == True:
            t = "\n現在時刻：" + self.WinInfo.get_datetime()
        if self.setting.get_setting_value("ApplicationSettings.Permisson.ActiveWindow") == True:
            w = "\nアクティブなウィンドウ：" + self.WinInfo.get_activate_window()
        if self.setting.get_setting_value("ApplicationSettings.Permisson.PlayingMedia") == True:
            m = "\n再生中のメディア：" + self.WinInfo.get_plaing_media(debug = debug + 1 if debug >= 0 else -1) 
        send_text = text + t + w + m 
        thread = threading.Thread(target=self.AI_Manager.response, args=(send_text, debug))
        thread.daemon = True
        thread.start()



def start_app(engine_process = None, TalkHistory = [], debug = -1):
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

#EventBusにおける購読処理の初期化
def _setup_event_listeners(self):
    pass

#Loggingの初期化
def _setup_logging_info():
    # loggingの基本設定を行う
    """
    level=logging.DEBUG:
    DEBUGに設定しておくと、全てのレベルのログが記録されるので、開発中はこれが便利です。
        DEBUG: 開発中に見る詳細な情報
        INFO: 正常な動作の記録（「アプリが起動した」「応答を生成した」など）
        WARNING: すぐには問題ないが、注意が必要なこと（「設定ファイルの一部が古い」など）
        ERROR: 処理が続行できないような重大なエラー
    """
    #ログの基本設定
    logging.basicConfig(
        level=logging.INFO,  # DEBUGレベル以上のログをすべて記録する
        format='%(asctime)s - %(levelname)s - [%(name)s] %(message)s',
        filename='application.log', # ログをこのファイルに出力する
        encoding='utf-8',
        filemode='w' # 起動時にファイルを上書き（'a'にすると追記）
    )
    
    #自分のモジュールは個別で設定する。
    logging.getLogger('ai').setLevel(logging.DEBUG)
    logging.getLogger("collectors").setLevel(logging.DEBUG)
    logging.getLogger("services").setLevel(logging.DEBUG)
    logging.getLogger("tts").setLevel(logging.DEBUG)
    logging.getLogger("ui").setLevel(logging.DEBUG)
    
    


    logging.info("ロギングの設定が完了しました。アプリケーションを起動します。")
    


if __name__ =="__main__":
    # 初回起動
    start_app(debug=-1)

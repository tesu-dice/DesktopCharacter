"""
いろいろなプログラムの起動と管理を行うメインプログラム
"""
#ライブラリ
import os
import sys
import logging
#プログラム
from services import WindowsInfoCollecter
from services.config_controller import UserSettings, read_configfile
from services import UserDataLogger
from services import Event_Bus
from services import speech2text
from ui import UI_main
from ai import AI_main
from services.release_check import check_nowver_is_newestver
from services.WindowsInfoCollecter import get_datetime
from ui.TTS_VoiceVoxEngine import start_server



#パス取得
"""
実行中のスクリプトが存在するディレクトリの絶対パスを取得する。
PyInstallerなどでコンパイルされた場合にも対応できる書き方。
"""
if getattr(sys, 'frozen', False):
    app_dir = os.path.dirname(sys.executable)
else:
    app_dir = os.path.dirname(os.path.abspath(__file__))



class myapp():
    def __init__(self, engine_process = None, TalkHistory = [], debug = -1):
        #初期化
        _setup_logging_info()
        self.engine_process = engine_process
        self.app_dir = app_dir
        _start_info_texts ="" # 起動メッセージ用テキスト
        _start_info_error ="" # 起動エラーメッセージ用テキスト
        
        #デバックフラグの管理
        if debug > -1:
            indent = "  " * debug
            print(f"{indent}main.py __init__() called.")
            debug = debug + 1 if debug >= 0 else -1
            
            
            
        
            
        
        

        #各要素の起動
            #シングルトンではないけどシングルトンのように扱う要素
        self.setting = read_configfile("config.json")#ユーザデータの読み込み
        self.bus = Event_Bus.EventBus()
            #各種サービス要素
        self.WinInfo = WindowsInfoCollecter.win_info_collector(self.bus, self.setting, debug=debug)
        self.UserDataLoger = UserDataLogger.UserActivityManager(self.bus, dir = app_dir)
        self.AI_Manager = AI_main.AI_Manager(self.bus, self.setting, TalkHistory, debug=debug)
        self.ui = UI_main.UI(self.bus, self.setting, debug=debug)
        self.S2T = speech2text.speech2text_manager(self.bus, self.setting, debug=debug)
        #イベントバスへの購読設定
        self._setup_event_listeners()
        
        

        
        #アプリケーション動作開始
        self.bus.publish("application start")
        self.mm_last = None # 同じ時刻で何度も処理しないためのint分
        self.update_id = self.ui.after(10*1000, self.update, debug)
        
    #EventBusにおける購読処理の初期化
    def _setup_event_listeners(self):
        #アプリケーションの起動メッセージ(サーバの起動完了後)
        self.bus.subscribe("application start", self.ui.start_TTS_Server)
        self.bus.subscribe("Start_TTS_Server", self.app_start_message)

        #アプリUI用の整理
        self.bus.subscribe("Req_PopUpMessage", self.ui.show_message_box)
        self.bus.subscribe("Req_UIMessage", self.ui.talk_window.add_log)



        #会話用の入力からの流れ(RAG機能OFFなら途中飛ばす。)
        self.bus.subscribe("MessageInput", self.ui.talk_window.add_log)#入力文字のUI表示
        self.bus.subscribe("MessageInput", self.Check_responseMode)#RAGのON/OFFの確認
        self.bus.subscribe_when(["MessageInput","Response_RAGisOFF"], self.AI_Manager.response)#RAGがOFFの際のテキスト生成
        self.bus.subscribe_when(["MessageInput","Response_RAGisON"], self.AI_Manager.make_rag_request)#RAG参照用のリクエスト生成
        self.bus.subscribe("Req_RAGInfo", self.UserDataLoger.handle_rag_request)#RAG情報の参照可能か確認してデータの準備や完了通知の指示
        self.bus.subscribe_when(["MessageInput","RAGisReady"], self.AI_Manager.response_withRAG)#RAGがONの際のテキスト生成
        self.bus.subscribe("AIGenerateMessage", self.ui.talk_window.add_log)#会話テキストの生成を受けてUIに表示、RAGのON/OFFに関わらずここで合流。
        self.bus.subscribe("AIGenerateMessage", self.ui.Reflect_Text) #TTSと立ち絵へ反映

        
        #ユーザデータの記録
            #5分毎のユーザアクティビティの記録
        self.bus.subscribe_workflow("Req_UserActivityLog", handler=self.WinInfo.get_activate_window, response_event="Req_UserActivityLog_win")
        self.bus.subscribe_workflow("Req_UserActivityLog", handler=self.WinInfo.get_plaing_media, response_event="Req_UserActivityLog_media")
        self.bus.subscribe_workflow("Req_UserActivityLog", handler=self.WinInfo.get_datetime, response_event="Req_UserActivityLog_time")
        self.bus.subscribe_when(["Req_UserActivityLog_time","Req_UserActivityLog_win", "Req_UserActivityLog_media"], self.UserDataLoger.add_userlog)
            #一時間毎, 一日毎の要約作成
        self.bus.subscribe_workflow("Req_UserSummaryLog_context", handler=self.AI_Manager.response_onetime, response_event="Req_UserSummaryLog_response")
        self.bus.subscribe_when(["Req_UserSummaryLog_TimeAndScope", "Req_UserSummaryLog_response"], self.UserDataLoger.add_summary_log)

        #アプリケーションの終了
        self.bus.subscribe("Req_ExitApp", self.exit)

        #設定の更新
        self.bus.subscribe("SettingsUpdated", self.on_settings_updated)

    #アプリケーション起動時の送信メッセージ
    def app_start_message(self, serverid, debug = -1):
        _start_info_texts = ""
        _start_info_error = ""
        debug = -1
        if debug >= 0:
            indent = "  " * debug
            print(f"{indent}main.py app_start_message() called.")
            print(f"{indent}serverid = {serverid}")
            debug = debug + 1 if debug >= 0 else -1
        
        #リリースバージョンの確認
        CURRENT_APP_VERSION = "20260201" # 現在のバージョンを設定
        _result = check_nowver_is_newestver("tesu-dice", "DesktopCharacter_forRelease", CURRENT_APP_VERSION)
        if _result[0] == False:#更新有の際の催促用メッセージ
            print(f"新しいバージョンが利用可能です！ 最新バージョン: {_result[1]}, 現在のバージョン: {_result[2]}")
            print("最新版をダウンロードしてください")
        else :#通常の起動メッセージ
            print(f"お使いのバージョンは最新です。 最新バージョン: {_result[1]}, 現在のバージョン: {_result[2]}")
        _start_info_texts += f"---バージョン情報---\n{'最新です。' if _result[0] else '更新があります。'} [{_result[2]}] -> [{_result[1]}]\n\n"
        


        #AIサービスとの接続確認
        if self.setting.get_setting_value("LLMSettings.Service") != "未選択":
            _start_info_texts += f"---AIサービスとの接続確認---\n"
            _result = self.AI_Manager.test_connection(debug=debug)
            _start_info_texts += f"{('成功' if _result[0] else '失敗')}\n\n"
            if _result[0] == False:
                _start_info_error += f"自然言語AIサービスとの接続に失敗しました。:\n{_result[1]}\n\n"

        #VoiceVoxサーバの起動
        if serverid == None:
            pass
            
        else:
            _start_info_texts += f"---VoiceVoxサーバの起動---\n"
            f = serverid != False
            _start_info_texts += f"{('成功' if f else '失敗')}\n\n"
            if not f:
                _start_info_error += f"VoiceVoxサーバの起動に失敗しました。"
                logging.error("VoiceVoxサーバの起動に失敗しました。")
            


        
        #起動メッセージ
        self.bus.publish("Req_PopUpMessage", "info", "起動メッセージ", _start_info_texts)
        #エラーメッセージ
        if _start_info_error != "":
            self.bus.publish("Req_PopUpMessage", "info", "エラーメッセージ", _start_info_error)
    
    #設定を更新した場合の処理
    def on_settings_updated(self, new_settings: UserSettings):
        """設定が更新されたときに呼び出され、アプリケーション全体の設定を更新します。"""
        logging.info("アプリケーション全体の設定を更新します...")
        self.setting = new_settings
        logging.info("アプリケーション全体の設定更新が完了しました。")

    #アプリケーションの終了、再起動
    def exit(self, _reboot = False, debug = -1):
        print(f"アプリケーションを終了します。再起動: {_reboot}")
        # self.ui.afterでスケジュールされたupdateをキャンセル
        if hasattr(self, 'update_id'):
            self.ui.after_cancel(self.update_id)
        
        # UIを破棄して現在のプロセスを終了する
        self.ui.destroy()

        if _reboot:
            # PyInstallerなどでexe化されているかチェック
            if getattr(sys, 'frozen', False):
                # exe化されている場合: 自分自身(exe)を起動
                application_path = sys.executable
                os.execl(application_path, application_path)
            else:
                # 通常のPythonスクリプトとして実行されている場合
                python = sys.executable
                os.execl(python, python, *sys.argv)
        
    #状態監視の実行
    def update(self, debug = -1):
        print("update called.  ",self.setting.get_setting_value("ApplicationSettings.ActiveSpeak.Time"),"秒毎に会話します。")
        #デバック処理
        if debug >= 0:
            indent = "  " * debug
            print(f"{indent}main.py update() called. activespeak={self.setting.get_setting_value('ApplicationSettings.ActiveSpeak.on/off')}")
            debug = debug + 1 if debug >= 0 else -1
        #経過時間毎の処理
        if self.setting.get_setting_value("ApplicationSettings.ActiveSpeak.on/off") == True:    
            if self.WinInfo.check_freetime():
                self.SendMessage_toAI("SYSTEM：ユーザー作業中...", debug=debug)
        #時間依存の処理
        time = self.WinInfo.get_datetime()
        mm_now = int(time.split(":")[1])
        if mm_now % 5 == 0 and self.mm_last != mm_now:#現在時刻の分が5で割れるかつ前の処理時刻でないか確認
            print("5分に一回の処理です。")
            self.mm_last = mm_now
            #ユーザアクティビティログの要求（時刻とログの許可がある場合）
            allow_time_access = self.setting.get_setting_value("ApplicationSettings.Permission.get_current_time")
            allow_logging_access = self.setting.get_setting_value("ApplicationSettings.Permission.UserActivityLog")
            if allow_time_access == True and allow_logging_access == True:
                self.bus.publish("Req_UserActivityLog")
                
        #テスト用

        
        #繰り返し処理
        self.update_id = self.ui.after(10*1000, self.update, debug)

    #入力の際の場合分け
    def Check_responseMode(self,input_dict,  debug=-1):
        react_response= self.setting.get_setting_value("ApplicationSettings.Permission.ReAct_response")
        rag_response = self.setting.get_setting_value("ApplicationSettings.Permission.UserActivityLog")
        
        if react_response == False and rag_response == True:
            self.bus.publish("Response_RAGisON")
        else:
            self.bus.publish("Response_RAGisOFF")

    #入力テキストをAIに伝える
    def SendMessage_toAI(self, text, debug = -1):
        #会話送信テキストの準備と送信
        t, w, m = "", "", ""
        if self.setting.get_setting_value("ApplicationSettings.Permission.get_current_time") == True:
            t = "\n現在時刻：" + self.WinInfo.get_datetime()
        if self.setting.get_setting_value("ApplicationSettings.Permission.get_active_window") == True:
            w = "\nアクティブなウィンドウ：" + self.WinInfo.get_activate_window()
        if self.setting.get_setting_value("ApplicationSettings.Permission.get_playing_media") == True:
            m = "\n再生中のメディア：" + self.WinInfo.get_plaing_media()
        send_text = text + t + w + m
        self.bus.publish("MessageInput", {"role": "user", "parts":[send_text]}, debug=debug)



def start_app(engine_process = None, TalkHistory = [], debug = -1):
    """
    アプリケーションを起動する唯一の関数。
    初回起動と再起動の両方を担う。
    """
    app = myapp(engine_process=engine_process, TalkHistory=TalkHistory, debug=debug)
    app.ui.mainloop()





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
    log_filepath = os.path.join(app_dir, 'application.log')# ログファイルのフルパスを安全に作成
    # 1. ルートロガーを取得
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)  # アプリケーション全体の基本レベル

    # 2. 既存のハンドラを一度すべてクリアする（ライブラリによる設定をリセット）
    if root_logger.hasHandlers():
        root_logger.handlers.clear()
    # 3. ファイル出力用のハンドラを新規作成
    # mode='w' で、起動時にファイルを上書き（新規作成）します
    file_handler = logging.FileHandler(log_filepath, mode='w', encoding='utf-8')
    # 4. ログの書式（フォーマット）を定義
    formatter = logging.Formatter('%(asctime)s - %(levelname)s - [%(name)s] %(message)s')
    # 5. ハンドラに書式をセット
    file_handler.setFormatter(formatter)

    # 6. ルートロガーに、設定済みのハンドラを追加
    root_logger.addHandler(file_handler)

    #自分のモジュールは個別で設定する。
    logging.getLogger('ai').setLevel(logging.DEBUG)
    logging.getLogger("collectors").setLevel(logging.DEBUG)
    logging.getLogger("services").setLevel(logging.DEBUG)
    logging.getLogger("ui").setLevel(logging.DEBUG)
    
    


    logging.info("ロギングの設定が完了しました。アプリケーションを起動します。")
    


if __name__ =="__main__":
    print("アプリケーションを起動します。")
    start_app(debug=-1)

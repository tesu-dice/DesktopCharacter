# c:\Users\owner\Downloads\myfile\create\programing\DesktopCharacter\UI.py
"""
透明な最大化ウィンドウを最前面に配置、キャラクターの画像を設置しておく。
フレーム内に会話や各種UIを設置、キャラクターを右クリックして終了ボタンを押すとアプリケーションを終了する。
"""

# UI.py
import tkinter as tk
from tkinter import ttk  # スタイル付きウィジェットのため
from tkinter import messagebox
import logging
logger = logging.getLogger(__name__)

# プログラム同士のやり取り
from services.config_controller import UserSettings
from services.Event_Bus import EventBus
from services.WindowsInfoCollecter import get_TotalMonitorSize
from ui import TTS_VoiceVoxEngine
from ui import TTS_WindowsNarratorManager
from ui import UI_characterImage
from ui import UI_settings

from ui import UI_talk # UI_talk モジュールをインポート


#左クリック時のメニューバーの管理
class ContextMenuManager:
    def __init__(self, ui, bus : EventBus, setting : UserSettings):
        self.ui  = ui
        self.bus = bus
        self.setting = setting
        self.menu = tk.Menu(self.ui, tearoff=0)

        _font = ("Yu Gothic UI", setting.get_setting_value("ApplicationSettings.FontSize"))
        self.menu.add_command(label="会話", command=self.show_textFrame, font = _font)
        self.menu.add_command(label="設定", command=self.show_settingUI, font = _font)
        self.menu.add_command(label="終了", command=self.exit_app, font = _font)

    def show_menu(self, event):
        self.menu.post(event.x_root, event.y_root)

    def show_textFrame(self):
        #アクティブウィンドウをself.ui.talk_windowsにする。
        self.ui.talk_window.deiconify()
        self.ui.talk_window.focus_force()
        
    def show_settingUI(self):
        if self.ui.setting_window is None or not self.ui.setting_window.winfo_exists():
            self.ui.setting_window = UI_settings.UI(self.ui, self.bus, self.ui.setting)
        else:#すでに存在している場合
            self.ui.setting_window.deiconify()
            self.ui.setting_window.focus_force()



    def exit_app(self, reboot = False):
        self.bus.publish("Req_ExitApp", reboot)
            
        




# UI全体の管理
class UI(tk.Tk):
    def __init__(self, bus: EventBus, setting: UserSettings, debug=-1):
        super().__init__()
        logger.info("UIの初期化を開始します。")
        self.bus = bus
        self.setting = setting
        self.debug = debug

        self.context_menu_manager = None
        self.TTS = None # TTSクライアントのインスタンスを保持
        self.engine_process = None # VoiceVoxのプロセスを保持
        self.setting_window = None # 設定ウィンドウのインスタンスを保持
        self.talk_window = None # 会話ウィンドウのインスタンスを保持
        self.charaImg = None
        # EventBusの購読設定
        self.bus.subscribe("SettingsUpdated", self.apply_settings)



        # --- ウィンドウの基本設定 ---
        self.title("DesktopCharacter")
        if self.setting.get_setting_value("ApplicationSettings.CharacterImage.AlwaysOnTop"):
            self.attributes("-topmost", True)
        self.overrideredirect(True) # ウィンドウのタイトルバーなどを非表示
        self.trans_color = "#888888"
        self.config(background=self.trans_color)
        self.attributes("-transparentcolor", self.trans_color)
        
        # --- UI要素の配置 ---
        self.talk_window = UI_talk.TalkWindow(self, self.bus, self.setting, debug=self.debug)
        self.charaImg = UI_characterImage.CharacterLabel(master=self, click_callback=self._handle_character_click, setting=self.setting, bus=self.bus, debug=self.debug)
        self.charaImg.bind("<Button-1>", self.start_drag)
        self.charaImg.bind("<B1-Motion>", self.do_drag)

        # --- 右クリックメニューの設定 ---
        self.context_menu_manager = ContextMenuManager(ui= self, bus=self.bus, setting = self.setting)
        self.charaImg.bind("<Button-3>", self.context_menu_manager.show_menu)

        # ウィンドウ位置の初期化
        self.after(10, self.refresh_window_position)
        self.apply_settings(self.setting)
        logger.info("UIの初期化が完了しました。")

    def _initialize_tts(self):
        """設定に基づいてTTSクライアントを初期化または再初期化します。"""
        selected_service = self.setting.get_setting_value("VoiceSettings.engine")
        logger.info(f"TTSクライアントを初期化しています... サービス: {selected_service}")

        if selected_service == "VOICEVOX":
            self.TTS = TTS_VoiceVoxEngine
        elif selected_service == "windowsNarrator":
            self.TTS = TTS_WindowsNarratorManager
        else:
            self.TTS = None
            logger.warning(f"選択されたTTSサービス '{selected_service}' はサポートされていません。")

    def _apply_font_settings(self):
        """現在の設定に基づいてフォントをUI全体に適用します。"""
        font_size = self.setting.get_setting_value("ApplicationSettings.FontSize")
        if not isinstance(font_size, int):
            font_size = 15 # デフォルト値
        font_family = "Yu Gothic UI"
        default_font = (font_family, font_size)
        
        self.option_add("*Font", default_font)
        style = ttk.Style(self)
        style.configure(".", font=default_font, padding=2)

    def apply_settings(self, new_settings: UserSettings):
        """設定が更新されたときに呼び出され、UIの各要素を更新します。"""
        logger.info("UIのメイン設定を更新します...")
        self.setting = new_settings

        # ウィンドウ設定の更新
        self.attributes("-topmost", self.setting.get_setting_value("ApplicationSettings.CharacterImage.AlwaysOnTop"))
        self.context_menu_manager = ContextMenuManager(ui= self, bus=self.bus, setting = self.setting)
        self.charaImg.bind("<Button-3>", self.context_menu_manager.show_menu)


        # フォントの再適用
        self._apply_font_settings()

        # TTSクライアントの再初期化
        self._initialize_tts()
        logger.info("UIのメイン設定の更新が完了しました。")

    def refresh_window_position(self):
        """ウィンドウの位置とサイズをモニター全体に合わせます。"""
        monitors_data = get_TotalMonitorSize()
        self.withdraw()
        self.geometry(f"{monitors_data[0]}x{monitors_data[1]}+{monitors_data[2]}+{monitors_data[3]}")
        self.deiconify()
    
    def Reflect_Text(self, talk_dict:dict, debug=-1):
        """テキスト応答を設定に基づいて読み上げます。"""
        if self.TTS is None:
            logger.warning("TTSクライアントが初期化されていないため、読み上げをスキップします。")
            return

        texts = talk_dict.get("parts")[0]
        for text in texts.split("\n"):
            if not text:
                continue
            
            image_name = None
            if "：" in text:
                parts = text.split("：", 1)
                image_name = parts[0]
                text_to_speak = parts[1]
            else:
                text_to_speak = text

            if image_name:
                self.update_character_image(image_name)
            
            #読み上げ処理
            engine = self.setting.get_setting_value("VoiceSettings.engine")
            if engine == "VOICEVOX":
                speaker = self.setting.get_setting_value("VoiceSettings.VOICEVOX.Model")
                speaker = speaker.split("=")[-1]
                self.TTS.text_to_speech(text_to_speak, speaker=speaker, debug=debug)
            elif engine == "windowsNarrator":
                speaker = self.setting.get_setting_value("VoiceSettings.windowsNarrator.Model")
                self.TTS.text_to_speech(text_to_speak, model_description=speaker, debug=debug)
                
    def start_TTS_Server(self):
        print("start_TTS_Server() called.")
        print(self.setting.get_setting_value("VoiceSettings.engine"), self.setting.get_setting_value("VoiceSettings.VOICEVOX.autorun"), self.engine_process)
        """設定に基づいてVOICEVOXサーバーを起動します。"""
        if self.engine_process is None and \
           self.setting.get_setting_value("VoiceSettings.engine") == "VOICEVOX" and \
           self.setting.get_setting_value("VoiceSettings.VOICEVOX.autorun") == True:
            
            self.engine_process = TTS_VoiceVoxEngine.start_server(
                self.setting.get_setting_value("VoiceSettings.VOICEVOX.path"),
                self.setting.get_setting_value("VoiceSettings.VOICEVOX.usegpu"),
                debug=self.debug
            )
        self.bus.publish("Start_TTS_Server", self.engine_process)

    def _handle_character_click(self):
        """キャラクタークリック時の処理"""
        if self.talk_window and self.talk_window.winfo_exists() and self.talk_window.winfo_ismapped():
            self.talk_window.add_log("システム: キャラクターがクリックされました！")

    def update_character_image(self, image_name):
        """キャラクターの表示画像を更新します。"""
        self.charaImg.update_image(image_name)

    def start_drag(self, event):
        self.drag_item = event.widget
        self.start_x = event.x
        self.start_y = event.y

    def do_drag(self, event):
        if self.drag_item:
            new_x = self.drag_item.winfo_x() + (event.x - self.start_x)
            new_y = self.drag_item.winfo_y() + (event.y - self.start_y)
            self.drag_item.place(x=new_x, y=new_y)

    def _on_closing(self):
        """ウィンドウの閉じるボタンが押されたときの処理"""
        self.bus.publish("Req_ExitApp", False)

    @staticmethod
    def show_message_box(type, title:str, message:str)->bool:
        #title でクラスやサービス名、messageで内容をユーザに通知
        if type == "info":
            return messagebox.showinfo(title, message)
        elif type == "warning":
            return messagebox.showwarning(title, message)
        elif type == "error":
            return messagebox.showerror(title, message)
        elif type == "question":
            return messagebox.askyesno(title, message)



if __name__ == "__main__":
    import main 
    main.start_app(debug=0)
    

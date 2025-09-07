"""
会話ログ表示とユーザー入力のための Toplevel ウィンドウです。
"""
import tkinter as tk
from tkinter import ttk
import logging
logger = logging.getLogger(__name__)

# プログラム同士のインポート
from services.config_controller import UserSettings
from services.Event_Bus import EventBus


class TalkWindow(tk.Toplevel):
    """ログ表示とユーザー入力のための Toplevel ウィンドウです。"""
    def __init__(self, master, bus:EventBus, setting: UserSettings, debug=-1):
        # Toplevelとしての初期化
        super().__init__(master)
        self.title("DesktopCharacter_会話")
        self.geometry(f"{500}x{400}")
        # self.geometry(f"{setting.get_setting_value('otherSettings.textWindowSize.width')}x{setting.get_setting_value('otherSettings.textWindowSize.height')}") # 設定ファイルから読み込む場合
        self.debug = debug # デバッグレベルをインスタンス変数として保持
        self.bus = bus
        self.setting = setting

        

        # フレームとスクロールバー付きのキャンバスの配置 (UI_settings.py と同様の構造)
        main_frame = tk.Frame(self)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
 
        # 入力エリア
        input_frame = tk.Frame(main_frame)
        input_frame.pack(side=tk.BOTTOM, fill=tk.X, pady=(5, 0))

        self.input_text = tk.Entry(input_frame)
        self.input_text.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 5))
        self.input_text.bind("<Return>", self._on_send_click) # Enterキーで送信

        self.send_button = ttk.Button(input_frame, text="送信", command=self._on_send_click)
        self.send_button.pack(side=tk.RIGHT)

        # ログ表示エリア
        # input_frame を配置した後の、main_frame の残りのスペース全てを使用します。
        # fill=tk.BOTH と expand=True により、ウィンドウサイズ変更に追従して拡大・縮小します。
        log_frame = tk.Frame(main_frame)
        log_frame.pack(side=tk.TOP, fill=tk.BOTH, expand=True)

        self.message_text = tk.Text(log_frame, wrap="word", state="disabled",
                                    background="#F0F0F0")
        self.message_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self.bar_vertical_scroll = tk.Scrollbar(
            log_frame, orient=tk.VERTICAL, command=self.message_text.yview
        )
        self.bar_vertical_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.message_text["yscrollcommand"] = self.bar_vertical_scroll.set

        #会話履歴があればそれを表示
        print("ここで過去の会話履歴を表示数動作があります。これは初期化後にAI_mainのほうで過去履歴を発見したイベントが発行されてから処理するのでコメントアウトします。")
        # for l in self.app.AI_Manager.history:
        #     self.add_log(l)
        #Xボタンで破棄しないように設定
        self.protocol("WM_DELETE_WINDOW", self.withdraw)
        
        self.bus.subscribe("UserSettings_Updated", self._apply_settings) # イベントを購読
        self._apply_settings(self.setting) # 初期スタイルを適用
        

    def _on_send_click(self, event=None): # debug引数を削除し、self.debugを使用
        """送信ボタンクリックまたはEnterキー押下時の処理"""
        message = self.input_text.get()
        if message:
            # EventBusで送信ボタンが押されたことを報告
            self.bus.publish("UserSendMessage", message, debug=self.debug)
            # 入力フィールドをクリア
            self.input_text.delete(0, tk.END)

    def add_log(self, talkhistory, debug=-1):
        """ログ表示エリアにメッセージを追加します。"""
        message = str(talkhistory.get("parts")[0])
        if talkhistory.get("role") == "user":
            message = f"[ 入力 ]\n{message}\n"
        elif talkhistory.get("role") == "model":
            message = f"[ 出力 ]\n{message}\n"
            #メタデータ表示ONならトークン数を表示
            if self.setting.get_setting_value("ApplicationSettings.ShowMetadatas") == True:
                message += "利用したトークン数：" + str(talkhistory["token_count"])+ "\n"
        message += "\n"

        if message:
            self.message_text.configure(state="normal")
            self.message_text.insert("end", message)
            self.message_text.see("end")
            self.message_text.configure(state="disabled")
    
    def add_log_text(self, message, debug = -1):
        if message:
            self.message_text.configure(state="normal")
            self.message_text.insert("end", message+"\n")
            self.message_text.see("end")
            self.message_text.configure(state="disabled")

    def _apply_settings(self, setting : UserSettings):
        """設定に基づいてUIのスタイルを適用する"""
        self.setting = setting

        # フォント設定
        try:
            font_size = int(self.setting.get_setting_value("ApplicationSettings.FontSize"))
            font_family = "Yu Gothic UI"
            
            # tk.Text ウィジェットのフォント設定
            font_tuple = (font_family, font_size)
            self.message_text.configure(font=font_tuple)
            
            # tk.Entry ウィジェットのフォント設定
            self.input_text.configure(font=font_tuple)

        except (ValueError, TypeError, AttributeError) as e:
            logger.warning(f"Invalid or missing font settings. Using default. Error: {e}")
            # デフォルトフォントを設定するなどのフォールバック処理
            default_font = ("Yu Gothic UI", 10)
            self.message_text.configure(font=default_font)
            self.input_text.configure(font=default_font)

if __name__ == "__main__":
    import main
    main.start_app(debug=0)

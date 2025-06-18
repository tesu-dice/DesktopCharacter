"""
会話ログ表示とユーザー入力のための Toplevel ウィンドウです。
"""
import tkinter as tk
from tkinter import ttk
import json # object型を文字列として編集するために使用

# プログラム同士のインポート
import config_controller

class TalkWindow(tk.Toplevel):
    """ログ表示とユーザー入力のための Toplevel ウィンドウです。"""
    def __init__(self, master, master_controller, setting: config_controller.UserSettings):
        # Toplevelとしての初期化
        super().__init__(master)
        self.title("会話")
        # 初期サイズと位置は適宜調整してください
        self.geometry(f"{500}x{400}")
        # self.geometry(f"{setting.get_setting_value('otherSettings.textWindowSize.width')}x{setting.get_setting_value('otherSettings.textWindowSize.height')}") # 設定ファイルから読み込む場合
        self.master_controller = master_controller
        self.setting = setting

        # 削除ボタンの上書き（WM_DELETE_WINDOW プロトコルを上書き）
        self.protocol("WM_DELETE_WINDOW", self.withdraw) 



        # フレームとスクロールバー付きのキャンバスの配置 (UI_settings.py と同様の構造)
        main_frame = tk.Frame(self)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
 
        # 入力エリア
        # main_frame の下部に配置し、水平方向(X)にのみ拡張します。
        # input_frame の高さは、中のウィジェット(Entry, Button)によって決まります。
        # pady=(5, 0) は、input_frame の上に5ピクセルの余白を設けます。
        input_frame = tk.Frame(main_frame)
        input_frame.pack(side=tk.BOTTOM, fill=tk.X, pady=(5, 0))

        self.input_text = tk.Entry(input_frame, font=("Arial", self.setting.get_setting_value("applicationSettings.FontSize")))
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
                                    background="#F0F0F0", font=("Arial", self.setting.get_setting_value("applicationSettings.FontSize")))
        self.message_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self.bar_vertical_scroll = tk.Scrollbar(
            log_frame, orient=tk.VERTICAL, command=self.message_text.yview
        )
        self.bar_vertical_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.message_text["yscrollcommand"] = self.bar_vertical_scroll.set

    def _on_send_click(self, event=None): # Enterキー対応のため event=None を追加
        """送信ボタンクリックまたはEnterキー押下時の処理"""
        message = self.input_text.get()
        if message:
            # ユーザーメッセージをログに追加
            self.add_log("あなた: " + message)
            # master_controller 経由でAIに送信
            self.master_controller.SendMessage_toAI(message)
            # 入力フィールドをクリア
            self.input_text.delete(0, tk.END)

    def add_log(self, message):
        """ログ表示エリアにメッセージを追加します。"""
        if message:
            self.message_text.configure(state="normal")
            self.message_text.insert("end", message + "\n")
            self.message_text.see("end")
            self.message_text.configure(state="disabled")

if __name__ == "__main__":
    # テスト用のダミー master_controller と settings
    class DummyMasterController:
        def SendMessage_toAI(self, text):
            print(f"DummyMasterController received message: {text}")
            # ダミーの応答をログに追加
            self.talk_window_ref.add_log("AI: ダミー応答です。")

    class DummySettings:
         def get_setting_value(self, path, default=None):
            # テスト用のダミー設定値を返す
            if path == "applicationSettings.FontSize": return 12
            if path == "otherSettings.textWindowSize.width": return 500
            if path == "otherSettings.textWindowSize.height": return 400
            return default

    root = tk.Tk()
    root.withdraw() # メインウィンドウは非表示

    dummy_mc = DummyMasterController()
    dummy_settings = DummySettings()

    talk_window = TalkWindow(root, dummy_mc, dummy_settings)
    dummy_mc.talk_window_ref = talk_window # ダミーコントローラーに参照を持たせる

    talk_window.add_log("システム: 会話ウィンドウを開きました。")

    root.mainloop()



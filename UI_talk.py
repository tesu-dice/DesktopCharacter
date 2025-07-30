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
    def __init__(self, master, app, setting: config_controller.UserSettings, debug=-1):
        # Toplevelとしての初期化
        super().__init__(master)
        self.title("会話")
        # 初期サイズと位置は適宜調整してください
        self.geometry(f"{500}x{400}")
        # self.geometry(f"{setting.get_setting_value('otherSettings.textWindowSize.width')}x{setting.get_setting_value('otherSettings.textWindowSize.height')}") # 設定ファイルから読み込む場合
        self.debug = debug # デバッグレベルをインスタンス変数として保持
        self.app = app
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
        for l in self.app.AI_Manager.history:
            self.add_log(l)
        #Xボタンで破棄しないように設定
        self.protocol("WM_DELETE_WINDOW", self.withdraw)
        

    def _on_send_click(self, event=None): # debug引数を削除し、self.debugを使用
        """送信ボタンクリックまたはEnterキー押下時の処理"""
        message = self.input_text.get()
        if message:
            # app 経由でAIに送信
            self.app.SendMessage_toAI(message, debug=self.debug)
            # 入力フィールドをクリア
            self.input_text.delete(0, tk.END)

    def add_log(self, talkhistory, debug=-1):
        """ログ表示エリアにメッセージを追加します。"""
        message = str(talkhistory.get("parts")[0])
        if talkhistory.get("role") == "user":
            message = f"入力:{message}"
        elif talkhistory.get("role") == "model":
            message = f">>>\n{message}\n"

        if message:
            self.message_text.configure(state="normal")
            self.message_text.insert("end", message)
            self.message_text.see("end")
            self.message_text.configure(state="disabled")
    
    def add_log_text(self, message, debug = -1):
        if message:
            self.message_text.configure(state="normal")
            self.message_text.insert("end", message)
            self.message_text.see("end")
            self.message_text.configure(state="disabled")

if __name__ == "__main__":
    import main
    main.start_app(debug=0)

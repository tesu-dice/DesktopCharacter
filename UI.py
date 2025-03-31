# UI.py
import tkinter as tk
from tkinter import ttk  # スタイル付きウィジェットのため
from PIL import Image, ImageTk  # 画像表示のため
import geminiAPI 

class myapp():
    def __init__(self, master):
        self.master = master
        master.title("アシストキャラクター")


        # 画面サイズを取得
        self.win_w = int(master.winfo_screenwidth()/2)
        self.win_h = int(master.winfo_screenheight()/2)
        master.geometry(f"{self.win_w}x{self.win_h}")
        

        # 画面を左右に分割
        self.left_frame = tk.Frame(master, width=self.win_w//2, height=self.win_h)
        self.left_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self.right_frame = tk.Frame(master, width=self.win_w//2, height=self.win_h)
        self.right_frame.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True)

        # 左側のフレームにログと入力欄を配置
        self.create_log_area(self.left_frame)
        self.create_input_area(self.left_frame)

        # 右側のフレームにキャラクター画像を配置
        self.create_character_image(self.right_frame)

        self.gemini = geminiAPI.geminiAI()

    def create_log_area(self, parent):
        """ログ表示エリアを作成"""
        frame = tk.Frame(parent)
        frame.pack(side=tk.TOP, fill=tk.BOTH, expand=True, padx=10, pady=10)  # 余白を追加

        # メッセージ用のテキストボックス
        self.message_text = tk.Text(frame, wrap="word", width=50, height=20)
        self.message_text.configure(state="disabled", background="#F0F0F0")  # 編集不可, 背景色
        self.message_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        # 縦スクロールバー
        self.bar_vertical_scroll = tk.Scrollbar(
            frame, orient=tk.VERTICAL, command=self.message_text.yview
        )
        self.bar_vertical_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.message_text["yscrollcommand"] = self.bar_vertical_scroll.set

    def create_input_area(self, parent):
        """テキスト入力エリアを作成"""
        frame = tk.Frame(parent)
        frame.pack(side=tk.BOTTOM, fill=tk.X, padx=10, pady=10)  # 余白を追加

        self.input_text = tk.Entry(frame, width=5)
        self.input_text.pack(side=tk.LEFT, fill=tk.X, expand=True)

        self.send_button = ttk.Button(frame, text="送信", command=self.send_message)  # スタイル付きボタン
        self.send_button.pack(side=tk.RIGHT)

    def create_character_image(self, parent):
        """キャラクター画像表示エリアを作成"""
        try:
            # 画像を読み込む (パスは適宜変更)
            image = Image.open("character0000.png")  # 画像ファイル名を指定
            # 画像サイズを調整 (必要に応じて)
            image = image.resize((int(image.width *(self.win_h / image.height)), int(image.height *(self.win_h / image.height)) ))
            #image = image.resize((self.win_w, self.win_h),Image.LANCZOS)   # サイズ調整
            self.photo = ImageTk.PhotoImage(image)  # PhotoImageオブジェクトを保持
            self.image_button = tk.Button(parent, image=self.photo, bd=0, highlightthickness=0, command=self.character_click) #ボタン化
            self.image_button.pack( padx=10, pady=10)  # ボタンをフレームいっぱいに表示
            self.image_button.config(width=self.win_w, height=self.win_h)

        except FileNotFoundError:
            print("Error: character.png not found")
            label = tk.Label(parent, text="画像が見つかりません", font=("Arial", 12))
            label.pack(expand=True)

    def add_log(self, _message):
        """ログにメッセージを追加"""
        if _message != "":
            # 編集可能に設定
            self.message_text.configure(state="normal")

            # メッセージを追加して改行
            self.message_text.insert("end", _message + "\n")

            # 最新メッセージが表示されるようにスクロール
            self.message_text.see("end")

            # 再び編集不可に設定
            self.message_text.configure(state="disabled")

    def send_message(self):
        """メッセージ送信処理"""
        message = self.input_text.get()
        if message:
            self.add_log("User: " + message)
            self.input_text.delete(0, tk.END)
            # ここでAPIにメッセージを送信する処理を追加する (geminiAPI.pyを使用)
            ans = self.gemini.response(message)
            self.add_log(ans)


    def character_click(self):
        """キャラクタークリック時の処理"""
        self.add_log("キャラクターがクリックされました！")


if __name__ == "__main__":
    root = tk.Tk()
    app = myapp(root)
    root.mainloop()
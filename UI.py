# c:\Users\owner\Downloads\myfile\create\programing\DesktopCharacter\UI.py
"""
透明な最大化ウィンドウを最前面に配置、キャラクターの画像を設置しておく。
フレーム内に会話や各種UIを設置、キャラクターを右クリックして終了ボタンを押すとアプリケーションを終了する。
"""

# UI.py
import tkinter as tk
from tkinter import ttk  # スタイル付きウィジェットのため
import random  # 初期立ち絵をランダムに設定するため
#プログラム同士のやり取り
import Character_Image_Controller


class MenuFrame(tk.Frame):
    """ログ表示とユーザー入力のためのフレームです。"""
    def __init__(self, parent, send_message_callback):
        super().__init__(parent)
        self.send_message_callback = send_message_callback

        self._create_log_area()
        self._create_input_area()
        self.place(x=100, y=50)


    def _create_log_area(self):
        log_frame = tk.Frame(self, bg=self.cget("background"))
        log_frame.pack(side=tk.TOP, fill=tk.BOTH, expand=True, padx=100, pady=5)

        self.message_text = tk.Text(log_frame, wrap="word", width=50, height=15) # 元のheight=20から調整
        self.message_text.configure(state="disabled", background="#F0F0F0")
        self.message_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self.bar_vertical_scroll = tk.Scrollbar(
            log_frame, orient=tk.VERTICAL, command=self.message_text.yview
        )
        self.bar_vertical_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.message_text["yscrollcommand"] = self.bar_vertical_scroll.set

    def _create_input_area(self):
        input_frame = tk.Frame(self, bg=self.cget("background"))
        input_frame.pack(side=tk.BOTTOM, fill=tk.X, padx=5, pady=5)

        self.input_text = tk.Entry(input_frame, width=40) # 元のwidth=5から調整
        self.input_text.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 5))

        self.send_button = ttk.Button(input_frame, text="送信", command=self._on_send_click)
        self.send_button.pack(side=tk.RIGHT)

    def _on_send_click(self):
        message = self.input_text.get()
        if message:
            self.send_message_callback(message)
            self.input_text.delete(0, tk.END)

    def add_log(self, message):
        """ログ表示エリアにメッセージを追加します。"""
        if message: # 元の _message != "" と同等
            self.message_text.configure(state="normal")
            self.message_text.insert("end", message + "\n")
            self.message_text.see("end")
            self.message_text.configure(state="disabled")


class CharacterLabel(tk.Label):
    """キャラクター画像を表示するためのフレーム（ラベル/ボタン）です。"""
    def __init__(self, parent, click_callback):
        super().__init__(parent, bg=parent.cget("background"), activebackground=parent.cget("background"))
        self.click_callback = click_callback


        # Character_Image_Controller は主に高さを基準に画像をスケーリングします
        self.character_image_manager = Character_Image_Controller.charaimg_controller(win_h=500, win_w=500)
        self._create_image_widget()

    #ラベルの画像を初期化
    def _create_image_widget(self):
        try:
            if not self.character_image_manager.imgs:
                print("エラー: CharacterImageManagerによって画像が読み込まれていません。")
                self = tk.Label(self, text="画像なし", font=("Arial", 12))
            else:
                initial_img_name = random.choice(list(self.character_image_manager.imgs.keys()))
                img_tk = self.character_image_manager.imgs[initial_img_name]
                self["image"] = img_tk
                

            

        except Exception as e: # FileNotFoundError だけでなく一般的なエラーも捕捉
            print(f"キャラクター画像ウィジェットの作成中にエラーが発生しました: {e}")
            self = tk.Label(self, text="画像なし", font=("Arial", 12))
        
        self.place(x=1000, y=300)

    def update_image(self, img_name):
        """表示されているキャラクター画像を更新します。"""
        if img_name in self.character_image_manager.imgs:
            new_img_tk = self.character_image_manager.imgs[img_name]
            self.image_widget.config(image=new_img_tk)
            self.image_widget.image = new_img_tk  # 新しい画像への参照を保持
        else:
            print(f"エラー: 画像名 '{img_name}' は CharacterImageManager に見つかりません。")


class UI: # クラス名を ui から UI に変更 (Pythonの慣習に従う)
    def __init__(self, master_controller): # 引数名を master から master_controller に変更
        self.master_controller = master_controller

        # メインウィンドウの設定
        self.win = tk.Tk()
        self.win.attributes("-topmost", True)
        self.win.overrideredirect(True) # ウィンドウのタイトルバーなどを非表示
        self.trans_color = "#888888"
        self.win.config(background=self.trans_color)
        self.win.attributes("-transparentcolor", self.trans_color)
        
        screen_width = self.win.winfo_screenwidth()
        screen_height = self.win.winfo_screenheight()
        self.win.geometry(f"{screen_width}x{screen_height}") # フルスクリーンに

        
        
        # CharacterLabelのインスタンス化と配置
        self.character_label = CharacterLabel(parent=self.win, click_callback=self._handle_character_click )
        self.character_label.bind("<Button-1>", self.start_drag)
        self.character_label.bind("<B1-Motion>", self.do_drag)
        # MenuFrameのインスタンス化と配置
        self.menu_frame = MenuFrame(self.win, self._handle_user_message_send)
        self.menu_frame.bind("<Button-1>", self.start_drag)
        self.menu_frame.bind("<B1-Motion>", self.do_drag)

        


    def _handle_user_message_send(self, message_from_input):
        """MenuFrameからユーザーメッセージが送信されたときの処理"""
        if message_from_input: # message_from_input が空でないことを確認
            formatted_message = "UserMessage: " + message_from_input
            self.master_controller.SendMessage_toAI(formatted_message) # master_controller経由で送信

    def _handle_character_click(self):
        """キャラクタークリック時の処理"""
        self.add_log("キャラクターがクリックされました！")

    # --- master_controller (myapp) から呼び出される公開メソッド ---
    def add_log(self, message):
        """ログにメッセージを追加します (MenuFrameへ委譲)。"""
        self.menu_frame.add_log(message)

    def update_character_image(self, image_name): # メソッド名を変更: update_character -> update_character_image
        """キャラクターの表示画像を更新します (CharacterLabelへ委譲)。"""
        self.character_label.update_image(image_name)
    
    def start_drag(self, event):
        self.drag_item = event.widget
        self.start_x = event.x
        self.start_y = event.y

    def do_drag(self, event):
        if self.drag_item:
            new_x = self.drag_item.winfo_x() + (event.x - self.start_x)
            new_y = self.drag_item.winfo_y() + (event.y - self.start_y)
            self.drag_item.place(x=new_x, y=new_y)



if __name__ == "__main__":
    import main
    a = main.myapp()
    # main.py で myapp が UI インスタンスを self.ui として保持し、
    # UI クラス名が 'ui' から 'UI' に変更されたことを想定しています。
    a.ui.win.mainloop() # main.py で UI.UI を使用してインスタンス化されていることを確認してください

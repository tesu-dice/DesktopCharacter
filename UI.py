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


class TextFrame(tk.Frame):
    """ログ表示とユーザー入力のためのフレームです。"""
    def __init__(self, parent, send_message_callback):
        super().__init__(parent)
        self.parent = parent
        self.send_message_callback = send_message_callback
        self["borderwidth"] = 10
        self["relief"] = "ridge"

        self._create_log_area()
        self._create_input_area()
        self._create_distroy_button()

    def _create_distroy_button(self):
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

    def _create_distroy_button(self):
        self.destroy_button = ttk.Button(self, text="閉じる", command=self.place_forget)
        #フレームの右上に配置
        self.destroy_button.place(relx=1.0, rely=0.0, anchor=tk.NE)

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
    def __init__(self, master, click_callback):
        super().__init__(master)
        self.config(background=self.master.cget("background"))
        self.config(activebackground=self.master.cget("background"))
        self.click_callback = click_callback

        #tk.Tkの縦横のサイズを取得(適切に取得できず、1,が返される)
        self.character_image_manager = Character_Image_Controller.charaimg_controller(win_h=self.master.winfo_screenwidth()//4, win_w=self.master.winfo_screenwidth()//4)
        self._init_image()
        self.place( x=self.master.winfo_screenwidth()/4*3,
                    y=self.master.winfo_screenheight()/2
                    )
        


    #ラベルの画像を初期化
    def _init_image(self):
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
        
        

    #キャラクター画像の更新
    def update_image(self, img_name):
        """表示されているキャラクター画像を更新します。"""
        if img_name in self.character_image_manager.imgs:
            new_img_tk = self.character_image_manager.imgs[img_name]
            self.config(image=new_img_tk)
        else:
            print(f"エラー: 画像名 '{img_name}' は CharacterImageManager に見つかりません。")

class ContextMenuManager:
    def __init__(self, parent, click_callback, TF: TextFrame):
        self.parent = parent
        self.click_callback = click_callback
        self.TF = TF
        self.menu = tk.Menu(parent, tearoff=0)
        
        self.menu.add_command(label="会話", command=self.show_textFrame)
        self.menu.add_command(label="終了", command=self.exit_app)

    def show_menu(self, event):
        self.menu.post(event.x_root, event.y_root)
    def show_textFrame(self):
        self.TF.place(x=self.parent.winfo_width()/2, y=self.parent.winfo_height()/2)
        


    def exit_app(self):
        self.parent.destroy()



class UI(tk.Tk): # クラス名を ui から UI に変更 (Pythonの慣習に従う)
    def __init__(self, master_controller): # 引数名を master から master_controller に変更
        super().__init__()
        self.master_controller = master_controller

        # メインウィンドウの設定
        self.title("デスクトップキャラクター")
        self.attributes("-topmost", True)
        self.overrideredirect(True) # ウィンドウのタイトルバーなどを非表示
        self.trans_color = "#888888"
        self.config(background=self.trans_color)
        self.attributes("-transparentcolor", self.trans_color)
        screen_width = self.winfo_screenwidth()
        screen_height = self.winfo_screenheight()
        self.geometry(f"{screen_width}x{screen_height}") # フルスクリーンに
        
        
        # CharacterLabelのインスタンス化と配置
        self.character_label = CharacterLabel(self, click_callback=self._handle_character_click )
        self.character_label.bind("<Button-1>", self.start_drag)
        self.character_label.bind("<B1-Motion>", self.do_drag)
        

        # TextFrameのインスタンス化と配置
        self.text_frame = TextFrame(self, self._handle_user_message_send)
        self.text_frame.bind("<Button-1>", self.start_drag)
        self.text_frame.bind("<B1-Motion>", self.do_drag)

        # ContextMenuManagerのインスタンス化
        self.context_menu_manager = ContextMenuManager(self, click_callback=self._handle_character_click, TF=self.text_frame)
        self.character_label.bind("<Button-3>", self.context_menu_manager.show_menu)

    #ユーザのメッセージ送信
    def _handle_user_message_send(self, message_from_input):
        """TextFrameからユーザーメッセージが送信されたときの処理"""
        if message_from_input: # message_from_input が空でないことを確認
            formatted_message = "UserMessage: " + message_from_input
            self.master_controller.SendMessage_toAI(formatted_message) # master_controller経由で送信

    #キャラクター画像クリックを
    def _handle_character_click(self):
        """キャラクタークリック時の処理"""
        self.add_log("キャラクターがクリックされました！")

    # --- master_controller (myapp) から呼び出される公開メソッド ---
    def add_log(self, message):
        """ログにメッセージを追加します (TextFrameへ委譲)。"""
        self.text_frame.add_log(message)

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
    a.ui.mainloop() # main.py で UI.UI を使用してインスタンス化されていることを確認してください

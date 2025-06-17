# c:\Users\owner\Downloads\myfile\create\programing\DesktopCharacter\UI.py
"""
透明な最大化ウィンドウを最前面に配置、キャラクターの画像を設置しておく。
フレーム内に会話や各種UIを設置、キャラクターを右クリックして終了ボタンを押すとアプリケーションを終了する。
"""

# UI.py
import tkinter as tk
from tkinter import ttk  # スタイル付きウィジェットのため
import random  # 初期立ち絵をランダムに設定するため
# プログラム同士のやり取り
from main import myapp
import Character_Image_Controller
from WindowsInfoCollecter import get_TotalMonitorSize
import UI_settings
import config_controller
from config_controller import UserSettings
import UI_talk # UI_talk モジュールをインポート

class CharacterLabel(tk.Label):
    """キャラクター画像を表示するためのフレーム（ラベル/ボタン）です。"""
    def __init__(self, master, click_callback, setting:UserSettings):
        super().__init__(master)
        self.config(background=self.master.cget("background"))
        self.config(activebackground=self.master.cget("background"))
        self.click_callback = click_callback
        self.setting = setting


        #tk.Tkの縦横のサイズを取得(適切に取得できず、1,が返される)
        # print("UIのウィジェットのサイズ")
        # print(self.master.winfo_screenwidth())
        # print(self.master.winfo_screenheight())
        # print(self.master.geometry()) # まだ配置してない状態で参照するので1+1
        # print(self.master.winfo_geometry())
        # print(self.winfo_geometry)
        _size = self.setting.get_setting_value("applicationSettings.CharacterSize")
        self.character_image_manager = Character_Image_Controller.charaimg_controller(win_h=_size, win_w=_size)
        self._init_image()
        self.place( x=self.master.winfo_screenwidth()/4*3 + abs(get_TotalMonitorSize()[2]),
                    y=self.master.winfo_screenheight()/2 + abs(get_TotalMonitorSize()[3])
                    )

    #ラベルの画像を初期化
    def _init_image(self):
        try:
            if not self.character_image_manager.imgs:
                print("エラー: CharacterImageManagerによって画像が読み込まれていません。")
                self = tk.Label(self, text="画像なし", font=("Arial", self.setting.get_setting_value("applicationSettings.FontSize")))
            else:
                initial_img_name = random.choice(list(self.character_image_manager.imgs.keys()))
                img_tk = self.character_image_manager.imgs[initial_img_name]
                self["image"] = img_tk
                

            

        except Exception as e: # FileNotFoundError だけでなく一般的なエラーも捕捉
            print(f"キャラクター画像ウィジェットの作成中にエラーが発生しました: {e}")
            self = tk.Label(self, text="画像なし", font=("Arial", self.setting.get_setting_value("applicationSettings.FontSize")))

    #キャラクター画像の更新
    def update_image(self, img_name):
        """表示されているキャラクター画像を更新します。"""
        if img_name in self.character_image_manager.imgs:
            new_img_tk = self.character_image_manager.imgs[img_name]
            self.config(image=new_img_tk)
        else:
            print(f"エラー: 画像名 '{img_name}' は CharacterImageManager に見つかりません。")

#左クリック時のメニューバーの管理
class ContextMenuManager:
    def __init__(self, app:myapp, ui):
        self.app = app
        self.ui  = ui
        self.menu = tk.Menu(self.ui, tearoff=0)

        
        self.menu.add_command(label="会話", command=self.show_textFrame)
        self.menu.add_command(label="設定", command=self.show_settingUI)
        self.menu.add_command(label="再起動", command=self.reboot_app)
        self.menu.add_command(label="終了", command=self.exit_app)

    def show_menu(self, event):
        self.menu.post(event.x_root, event.y_root)

    def show_textFrame(self):
        self.ui.talk_window = UI_talk.TalkWindow(self.ui, self.app, self.app.setting)
        
    def show_settingUI(self):
        setting_window = UI_settings.UI_settings(self.ui, settings=config_controller.read_configfile("config.json"))
    
    #appの再起動
    def reboot_app(self):
        self.app.reboot_app()


    def exit_app(self):
        self.ui.destroy()



# UI全体の管理
class UI(tk.Tk):
    def __init__(self, app, setting:UserSettings):
        super().__init__()
        self.app = app
        self.setting = setting

        # メインウィンドウの設定
        self.title("デスクトップキャラクター")
        self.attributes("-topmost", True)
        self.overrideredirect(True) # ウィンドウのタイトルバーなどを非表示
        self.trans_color = "#888888"
        self.config(background=self.trans_color)
        self.attributes("-transparentcolor", self.trans_color)
        screen_width = self.winfo_screenwidth()
        screen_height = self.winfo_screenheight()
        monitors_data = get_TotalMonitorSize()

        self.geometry(f"{monitors_data[0]}x{monitors_data[1]}+{monitors_data[2]}+{monitors_data[3]}") # すべての範囲に収まるように取得
        
        # 会話ウィンドウのインスタンスを保持する変数 (最初はNone)
        self.talk_window = None

        # CharacterLabelのインスタンス化と配置
        self.character_label = CharacterLabel(master=self, click_callback=self._handle_character_click, setting= self.setting )
        self.character_label.bind("<Button-1>", self.start_drag)
        self.character_label.bind("<B1-Motion>", self.do_drag)

        # ContextMenuManagerのインスタンス化
        self.context_menu_manager = ContextMenuManager(app=self.app, ui =self)
        self.character_label.bind("<Button-3>", self.context_menu_manager.show_menu)

    #ユーザのメッセージ送信
    def _handle_user_message_send(self, message_from_input):
        """TextFrameからユーザーメッセージが送信されたときの処理"""
        if message_from_input: # message_from_input が空でないことを確認
            formatted_message = "UserMessage: " + message_from_input
            # このメソッドは TalkWindow に移動しました。UI クラスでは直接メッセージ送信処理は行いません。
            # TalkWindow が master_controller を直接呼び出します。
            pass # このメソッドは不要になりました

    #キャラクター画像クリックを
    def _handle_character_click(self):
        """キャラクタークリック時の処理"""
        # キャラクタークリック時のログは TalkWindow が開いていればそこに追加
        if self.talk_window and self.talk_window.winfo_exists() and self.talk_window.winfo_ismapped():
             self.talk_window.add_log("システム: キャラクターがクリックされました！")


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
    app = main.myapp()
    

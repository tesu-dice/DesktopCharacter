# c:\Users\owner\Downloads\myfile\create\programing\DesktopCharacter\UI.py
"""
透明な最大化ウィンドウを最前面に配置、キャラクターの画像を設置しておく。
フレーム内に会話や各種UIを設置、キャラクターを右クリックして終了ボタンを押すとアプリケーションを終了する。
"""

# UI.py
import tkinter as tk
from tkinter import ttk  # スタイル付きウィジェットのため
from tkinter import messagebox
import random  # 初期立ち絵をランダムに設定するため
# プログラム同士のやり取り
from config_controller import UserSettings
from talk_VoiceVoxEngine import kill_server
import UI_characterImage
from WindowsInfoCollecter import get_TotalMonitorSize
import UI_settings

import UI_talk # UI_talk モジュールをインポート


#左クリック時のメニューバーの管理
class ContextMenuManager:
    def __init__(self, app, ui):
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
        self.ui.talk_window.deiconify()
        
    def show_settingUI(self):
        self.ui.setting_window.deiconify()

    #appの再起動
    def reboot_app(self):
        self.app.reboot_app()


    def exit_app(self):
        kill_server(self.app.engine_prosess)
        self.ui.destroy()




# UI全体の管理
class UI(tk.Tk):
    def __init__(self, app, setting:UserSettings, debug =-1):
        super().__init__()
        if debug >= 0:
            indent = "  " * debug
            print(f"{indent}UI.py __init__() called.")
            send_message("デバックメッセージ", "UI_main.py sendmessage()の動作確認です。")
            debug = debug + 1 if debug >= 0 else -1
        self.app = app
        self.setting = setting
        self.talk_window = UI_talk.TalkWindow(self, self.app, self.setting); self.talk_window.withdraw()
        self.setting_window = UI_settings.UI(self, self.setting); self.setting_window.withdraw()
        
        

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

        # CharacterLabelのインスタンス化と配置
        self.charaImg = UI_characterImage.CharacterLabel(master=self, click_callback=self._handle_character_click, setting= self.setting )
        self.charaImg.bind("<Button-1>", self.start_drag)
        self.charaImg.bind("<B1-Motion>", self.do_drag)


        # ContextMenuManagerのインスタンス化
        self.context_menu_manager = ContextMenuManager(app=self.app, ui =self)
        self.charaImg.bind("<Button-3>", self.context_menu_manager.show_menu)

        

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


def send_message(title:str, message:str)->bool:
    result = messagebox.askyesno(title, message)
    return result
    

if __name__ == "__main__":
    import main 
    main.start_app(debug=0)
    

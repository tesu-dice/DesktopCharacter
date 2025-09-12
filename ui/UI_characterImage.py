"""
キャラクターの画像の管理
class charaimg_controller
    キャラクターの画像を読み込んでリストとして管理する。
    def __init__(self, win_h, win_w):
    def load_imgs(self):
    


"""
#一般ライブラリ
import os
from PIL import Image, ImageTk  # 画像表示のため
import tkinter as tk
import random
from PIL.Image import FLIP_LEFT_RIGHT 
#プログラムのインポート
from services.config_controller import UserSettings
from services.WindowsInfoCollecter import get_TotalMonitorSize


#キャラクター画像を管理するクラス
class charaimg_controller():
    def __init__(self, win_h, win_w, setting:UserSettings):
        self.win_h = win_h
        self.win_w = win_w
        self.setting = setting
        self.imgs ={} #画像名：画像ファイルの辞書

        
        self.load_imgs()
        
    #キャラクター画像の読み取り
    def load_imgs(self):
        dir_path = f"立ち絵/{self.setting.get_setting_value('ApplicationSettings.CharacterImage.Folder')}/"
        try :
            files = os.listdir(dir_path)
        except:
            self.bus.publish("Req_PopUpMessage", "info", "エラーメッセージ", "立ち絵情報の取得に失敗しました。")
            files = os.listdir("立ち絵/CHARAT-MONO/")
        #画像の名前と画像を適正サイズに変更して保存
        for f in files :
            image = Image.open(dir_path + f)  # 画像ファイル名を指定
            # 画像サイズを調整 (必要に応じて)
            image = image.resize((int(image.width *(self.win_h / image.height)), int(image.height *(self.win_h / image.height)) ))
            #画像の左右反転
            if self.setting.get_setting_value("ApplicationSettings.CharacterImage.Flip"):
                image = image.transpose(FLIP_LEFT_RIGHT)
            image = ImageTk.PhotoImage(image)
            
            self.imgs[f] = image
        #print("character-img_controller.py load_imgs() end")
        #print(self.imgs)


class CharacterLabel(tk.Label):
    """キャラクター画像を表示するためのフレーム（ラベル/ボタン）です。"""
    def __init__(self, master, click_callback, setting:UserSettings, bus, debug = -1):
        super().__init__(master)
        self.config(background=self.master.cget("background"))
        self.config(activebackground=self.master.cget("background"))
        self.click_callback = click_callback
        self.setting = setting
        self.bus = bus
        self.bus.subscribe("SettingsUpdated", self.on_settings_updated)
        
        _size = self.setting.get_setting_value("ApplicationSettings.CharacterImage.Size")
        self.character_image_manager = charaimg_controller(win_h=_size, win_w=_size, setting=self.setting)
        self._init_image()
        self.place( x=self.master.winfo_screenwidth()/2 + abs(get_TotalMonitorSize()[2]),
                    y=self.master.winfo_screenheight()/2 + abs(get_TotalMonitorSize()[3])
                    )
        if debug >=  0:
            indent = "  " * debug
            print(f"{indent}CharacterLabel.__init__() called.")
            print(f"{indent}CharaImageSize = {_size}")
            
            debug = debug + 1 if debug >= 0 else -1
           

    #ラベルの画像を初期化
    def _init_image(self):
        try:
            if not self.character_image_manager.imgs:
                print("エラー: CharacterImageManagerによって画像が読み込まれていません。")
                self.config(text="画像なし") # 画像がない場合、テキストを表示
            else:
                initial_img_name = random.choice(list(self.character_image_manager.imgs.keys()))
                img_tk = self.character_image_manager.imgs[initial_img_name]
                self["image"] = img_tk
                

        except Exception as e: # FileNotFoundError だけでなく一般的なエラーも捕捉
            print(f"キャラクター画像ウィジェットの作成中にエラーが発生しました: {e}")
            self.config(text="画像なし") # エラー時にもテキストを表示

    #キャラクター画像の更新
    def update_image(self, img_name):
        """表示されているキャラクター画像を更新します。"""
        if img_name in self.character_image_manager.imgs:
            new_img_tk = self.character_image_manager.imgs[img_name]
            self.config(image=new_img_tk)
        else:
            print(f"エラー: 画像名 '{img_name}' は CharacterImageManager に見つかりません。")

    def on_settings_updated(self, new_settings: UserSettings):
        """設定が更新されたときに呼び出され、キャラクターの表示を更新します。"""
        print("キャラクター画像の表示設定を更新します...")
        self.setting = new_settings

        # 新しい設定で画像を再読み込み
        _size = self.setting.get_setting_value("ApplicationSettings.CharacterImage.Size")
        self.character_image_manager = charaimg_controller(win_h=_size, win_w=_size, setting=self.setting)
        self._init_image()

        # ウィンドウの位置も更新される可能性があるため再配置
        self.place( x=self.master.winfo_screenwidth()/2 + abs(get_TotalMonitorSize()[2]),
                    y=self.master.winfo_screenheight()/2 + abs(get_TotalMonitorSize()[3])
                    )
        print("キャラクター画像の表示設定の更新が完了しました。")

    

if __name__ == "__main__":
    import main
    main.start_app(debug=0)

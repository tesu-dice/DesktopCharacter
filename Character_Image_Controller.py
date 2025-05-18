"""
キャラクターの画像の管理
class charaimg_controller
    キャラクターの画像を読み込んでリストとして管理する。
    def __init__(self, win_h, win_w):
    def load_imgs(self):
    
    

"""
import os 
from PIL import Image, ImageTk  # 画像表示のため

class charaimg_controller():
    def __init__(self, win_h, win_w):
        self.win_h = win_h; self.win_w = win_w
        self.imgs ={} #画像名：画像ファイルの辞書

        
        self.load_imgs()
        

    #キャラクター画像の読み取り
    def load_imgs(self):
        dir_path = "立ち絵/"
        files = os.listdir(dir_path)
        #画像の名前と画像を適正サイズに変更して保存
        for f in files :
            image = Image.open(dir_path + f)  # 画像ファイル名を指定
            # 画像サイズを調整 (必要に応じて)
            image = image.resize((int(image.width *(self.win_h / image.height)), int(image.height *(self.win_h / image.height)) ))
            image = ImageTk.PhotoImage(image)
            
            self.imgs[f] = image
        print("character-img_controller.py load_imgs() end")
        #print(self.imgs)



if __name__ == "__main__":
    a = charaimg_controller(500, 500)


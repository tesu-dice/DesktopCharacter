
"""
待機状態の画面
"""
import tkinter as tk
import cv2
from PIL import Image, ImageTk
import menu


#与えられたパスの画像をトリミング
def image(str,width, height, sx,sy):
    img_cv =cv2.imread(str,-1)
    print(img_cv.shape)
    
    img_cv =img_cv[sy:sy+height, sx:sx+width]#トリミング

    img_cv=cv2.resize(img_cv, (width, height))#縦横引き伸ばし
    img_rgb =cv2.cvtColor(img_cv, cv2.COLOR_BGR2RGB)#BGRなのでRGBに直す
    print(img_rgb.shape)
    
    img_pil =Image.fromarray(img_rgb)#RGBからPILフォーマットに変換
    img_tk= ImageTk.PhotoImage(image=img_pil)#変換
    return img_tk


#メニュー画面を表示
def openmenu ():
    menu.show()


#ラベルをクラス化
class UI ():
    swich :bool =None #1で表示、０で非表示
    depend =None
    text :str =None#
    font =None
    gb :str =None
    fg :str =None
    img =None
    sx :int =None
    sy :int =None
    gx :int =None
    gy :int =None
    width :float =None
    height :float =None
    posx:float=None
    posy:float=None

    def __init__(self,swich, depend, text, font, bg, fg, img, sx, sy, width, height, posx, posy):
        if(img!=None):
            img_gbr =cv2.imread(img)
            print(img_gbr.shape)
            img_gbr =img_gbr[sx:sx+width, sy:sy+height]#トリミング
            print(img_gbr.shape)
            """img_gbr =cv2.resize(img_gbr, (width, height))#縦横引き伸ばし
            print(img_gbr.shape)"""
            img_rgb =cv2.cvtColor(img_gbr, cv2.COLOR_BGR2RGB)#BGRなのでRGBに直す
            print(img_rgb.shape)
            img_pil =Image.fromarray(img_rgb)#RGBからPILフォーマットに変換
            img_tk= ImageTk.PhotoImage(image=img_pil)#変換
        else:
            img_tk=None
            
        self=tk.Canvas(width=width, height=height, background=bg)
        self.place(x=posx, y=posy)
        self.create_image(0,0,image=img_tk)

        if(swich==1):
            self.place(x=posx, y=posy)
        


    
#透明の待機ウィンドウ設定
def setwindow():
    global transparentcolor, main, screenw, screenh
    main =tk.Tk()
    transparentcolor = "#000000" #透明色の定義
    main.config(background=transparentcolor)#背景色指定
    main.attributes("-transparentcolor", transparentcolor)#透過色指定
    main.attributes('-fullscreen', True)#フルスクリーン
    main.attributes("-topmost",True)#最前面に表示
    screenw = main.winfo_screenwidth()
    screenh = main.winfo_screenheight()

#ディスプレイサイズを出力
def get_displaywidth():
    return screenw
def get_displayheight():
    return screenh



#待機中のボタン表示
def setchara():
    
    image=image("character.png",500,400,250,200)
    character = tk.Button(main, image=image, command = openmenu, 
                        borderwidth =0, highlightthickness=0,#borderwidth =0, highlightthickness=0　　で枠線なし
                        bg=transparentcolor, activebackground=transparentcolor)#ボタンを押したときとかその他の時に背景透明
    character.place(x=1100,y=400)


setwindow()
main.mainloop()






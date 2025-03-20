import tkinter as tk
from PIL import Image, ImageTk



def menu():
    global menu
    menu =tk.Frame()
    menu.config(background="#0f0f0f")#背景色指定
    menu.geometory("400x700")
    


def show():
    menu()
    print("menu.py ""show"" called")




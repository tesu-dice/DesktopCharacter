"""
"""

import tkinter as tk
import UI
import geminiAPI
class myapp():
    def __init__(self):
        self.ui = UI.ui(self)
        self.ai = geminiAPI.geminiAI()

    #UIで取得したテキストをAIに伝える
    def SendMessage_UItoAI(self, text):
        anser = self.ai.response(text)
        self.ui.add_log(anser)







# print(root.winfo_geometry())
# print(root.winfo_height(), root.winfo_width())
# print(root.winfo_screenheight(), root.winfo_screenwidth())
# print(root.winfo_screenmmheight(), root.winfo_screenmmwidth())

print("main.py end")
if __name__ =="__main__":
    app = myapp()
    app.ui.win.mainloop()
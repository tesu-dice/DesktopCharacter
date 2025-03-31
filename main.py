"""
"""

import tkinter as tk
import UI


root = tk.Tk()

app = UI.myapp(root)

print(root.winfo_geometry())
print(root.winfo_height(), root.winfo_width())
print(root.winfo_screenheight(), root.winfo_screenwidth())
print(root.winfo_screenmmheight(), root.winfo_screenmmwidth())

print("main.py end")

root.mainloop()
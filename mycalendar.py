
import tkinter as tk1 
import datetime as dt1 
import calendar as cl1 

def generate_calendar1(y1, m1): 
    global wd1 
    global cal1 
    for i1 in range( len(cal1) ): 
        cal1[i1] = ""
    date1 = dt1.date( y1, m1, 1 ) 
    wd1 = date1.weekday() 
    if wd1 > 5: 
        wd1 = wd1 - 7 
    cal_max1 = cl1.monthrange( y1, m1 )[1] 
    for i1 in range( cal_max1 ): 
        str1 = str( i1+1 ) 
        i2 = i1 + wd1 + 1 
        cal1[i2] = str1 

def set_calendar1(cal1, btn1): 
    for i1 in range( len(cal1) ): 
        str1 = cal1[i1] 
        btn1[i1]["text"] = str1 

def prev_next1( n1 ): 
    global y1 
    global m1 
    global btn1 
    m2 = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December" ] 
    m1 = m1 + n1 
    if m1 > 12: 
        y1 = y1 + 1 
        m1 = 1 
    elif m1 < 1: 
        y1 = y1 - 1 
        m1 = 12 
    label1["text"] = str(m1) 
    label2["text"] = m2[m1-1] 
    label3["text"] = str(y1) 
    generate_calendar1(y1, m1) 
    set_calendar1(cal1, btn1) 

def btn_click1():
    return 

root = tk1.Tk()
root.title(u"iroha_calendar v0.1")
root.geometry("755x530+100+100")
root["bg"] = "#EEEEE8"

label1 = tk1.Label(font=("Meiryo UI",26),anchor=tk1.CENTER, width=2)
label1["bg"] = "#EEEEE8" 
label1.place(x=50, y=3) 

label2 = tk1.Label(font=("Meiryo UI",10),anchor=tk1.W, width=10)
label2["bg"] = "#EEEEE5" 
label2.place(x=120, y=8) 

label3 = tk1.Label(font=("Meiryo UI",12),anchor=tk1.W, width=10)
label3["bg"] = "#EEEEE8" 
label3.place(x=120, y=25) 

label4 = [""]*7 
a1 = ["Sunday","Monday","Tuesday","Wednesday","Thursday","Friday","Saturday" ] 
for i1 in range( 7 ): 
    label4[i1] = tk1.Label(text=a1[i1], font=("Meiryo UI",9), anchor=tk1.CENTER, width=10)
    label4[i1]["bg"] = "#EEEEE8" 
    label4[i1].place(x=30+103*i1, y=55) 

btn1 = [""]*42 
for i1 in range( 6 ): 
    for i2 in range( 7 ): 
        fg1 = "#000000" 
        if i2 == 0: 
            bg1 = "#FFF0F0" 
            fg1 = "#FF0000" 
        elif i2 == 6: 
            bg1 = "#F6F0FF" 
            fg1 = "#0000A0" 
        else: 
            bg1 = "#FFFFFF"  
        btn1[i2+7*i1] = tk1.Button(root, font=("Meiryo UI",11), anchor=tk1.NW, bg=bg1, fg=fg1, relief='flat', command=btn_click1) 
        x2 = 20 + 103 * i2 
        y2 = 75 + i1 * 73 
        btn1[i2+7*i1].place(x=x2, y=y2, width=100, height=70)

btn2 = tk1.Button(root, text="prev", font=("Meiryo UI",11), bg="#D0D0D0", relief='flat', command=lambda:prev_next1(-1) )
btn2.place(x=600, y=10, width=60, height=30)

btn3 = tk1.Button(root, text="next", font=("Meiryo UI",11), bg="#D0D0D0", relief='flat', command=lambda:prev_next1(1) )
btn3.place(x=680, y=10, width=60, height=30)

now1 = dt1.datetime.now() 
y1 = now1.year 
m1 = now1.month 
d1 = now1.day 
wd1 = 0
cal1 = [""]*40 

prev_next1( 0 ) 

root.mainloop()



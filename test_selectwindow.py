import tkinter as tk
from screeninfo import get_monitors

class MultiScreenApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("マルチスクリーンGUI配置")
        self.geometry("600x400") # デフォルトのウィンドウサイズ

        self.monitors = get_monitors()
        print("検出されたモニター:")
        for i, m in enumerate(self.monitors):
            print(f"  モニター {i}: 幅={m.width}, 高さ={m.height}, X={m.x}, Y={m.y}, プライマリ={m.is_primary}, ウィンドウ名={m.name}, 画面の長さ{m.height_mm}mm x {m.width_mm}mm")

        self.create_widgets()

    def create_widgets(self):
        tk.Label(self, text="表示したいモニターを選択してください:").pack(pady=10)

        # モニター選択用のラジオボタン
        self.selected_monitor_index = tk.IntVar(self)
        self.selected_monitor_index.set(0) # デフォルトでプライマリモニターを選択

        for i, m in enumerate(self.monitors):
            monitor_desc = f"モニター {i} ({m.width}x{m.height} @ {m.x},{m.y})"
            if m.is_primary:
                monitor_desc += " (プライマリ)"
                self.selected_monitor_index.set(i) # プライマリがあればデフォルトに設定
            
            tk.Radiobutton(self, text=monitor_desc, variable=self.selected_monitor_index, value=i).pack(anchor="w")

        tk.Button(self, text="このモニターにウィンドウを配置", command=self.place_window_on_selected_monitor).pack(pady=20)
        tk.Button(self, text="キャラクターウィンドウを配置", command=self.place_character_window).pack(pady=10)

    def place_window_on_selected_monitor(self):
        selected_index = self.selected_monitor_index.get()
        if 0 <= selected_index < len(self.monitors):
            monitor = self.monitors[selected_index]
            
            # ウィンドウをモニターの中央に配置するための計算
            window_width = self.winfo_width() # 現在のウィンドウの幅
            window_height = self.winfo_height() # 現在のウィンドウの高さ
            print(f"ウィンドウの幅: {window_width}, 高さ: {window_height}")
            print(f"モニターの幅: {monitor.width}, 高さ: {monitor.height}")
            
            x_pos = monitor.x + (monitor.width - window_width) // 2
            y_pos = monitor.y + (monitor.height - window_height) // 2
            
            self.geometry(f"{window_width}x{window_height}+{x_pos}+{y_pos}")
            print(f"ウィンドウをモニター {selected_index} に配置しました。座標: {x_pos},{y_pos}")
        else:
            print("無効なモニター選択です。")

    def place_character_window(self):
        # ここにキャラクターウィンドウのコードを統合するか、呼び出す
        # 例として、特定のモニターの左上隅にキャラクターウィンドウを配置
        selected_index = self.selected_monitor_index.get()
        if 0 <= selected_index < len(self.monitors):
            monitor = self.monitors[selected_index]

            character_window_width = 200 # キャラクターウィンドウのサイズ
            character_window_height = 200
            
            # モニターの左上隅に配置
            char_x_pos = monitor.x
            char_y_pos = monitor.y

            # ここでCharacterWindowクラスを呼び出すか、定義する
            # 例: CharacterWindow(char_x_pos, char_y_pos)
            print(f"キャラクターウィンドウをモニター {selected_index} の ({char_x_pos},{char_y_pos}) に配置する予定です。")
            
            # 実際のキャラクターウィンドウを作成・配置する処理
            # 例: 新しいToplevelウィンドウを作成
            char_win = tk.Toplevel(self)
            char_win.overrideredirect(True) # タイトルバーなし
            char_win.attributes('-transparentcolor', 'white') # 透明色
            char_win.attributes('-topmost', True) # 最前面
            char_win.geometry(f"{character_window_width}x{character_window_height}+{char_x_pos}+{char_y_pos}")
            char_win.config(bg='white') # 透明にする背景色
            tk.Label(char_win, text="キャラ！", bg='white', font=("Arial", 30)).pack(expand=True, fill="both")
            
        else:
            print("キャラクターウィンドウ配置のための無効なモニター選択です。")


if __name__ == "__main__":
    app = MultiScreenApp()
    app.mainloop()
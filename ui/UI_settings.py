# トップレベルウィンドウを使ったユーザーデータの変更・更新用プログラム。
# トップレベルウィンドウを使って、コンフィグの項目を再帰的に表示・変更できるようにする。

# このモジュールは、アプリケーションの設定値を動的に変更するためのGUIを提供します。
# 設定はJSON形式で管理され、ネストされた構造をUI上にツリー形式で表示し、
# ユーザーが各設定項目の値を変更・保存できるようにします。

# ライブラリのインポート
import tkinter as tk
import tkinter.filedialog
from tkinter import ttk  # スタイル付きウィジェットのため
import logging
logger = logging.getLogger(__name__)

# プログラム同士のインポート（これらは外部ファイルとして存在し、設定UIから利用される）
from services import config_controller # 設定ファイルの読み書きや、設定値の管理を行うモジュール
from services.Event_Bus import EventBus
from ai import AI_geminiAPI
from ai import AI_ollama
from ui import TTS_VoiceVoxEngine # VoiceVoxエンジンのスピーカーリストなどを取得するために使用
from ui import TTS_WindowsNarratorManager # Windowsナレーターの音声モデルなどを取得するために使用
from main import get_CharacterFolders # mainモジュールからget_CharacterFoldersをインポート

class Tooltip:
    """
    ウィジェットにツールチップ機能を提供します。
    マウスがウィジェット上にあるときに、説明テキストの小さなポップアップウィンドウを表示します。
    """
    def __init__(self, widget, text, settings: config_controller.UserSettings):
        self.widget = widget
        self.text = text
        self.settings = settings
        self.tooltip_window = None
        self.widget.bind("<Enter>", self.show_tooltip)
        self.widget.bind("<Leave>", self.hide_tooltip)

    def show_tooltip(self, event=None):
        """ツールチップウィンドウを表示します。"""
        if self.tooltip_window or not self.text:
            return
        
        # ウィジェットの座標を取得し、カーソルの近くにツールチップを表示
        x, y, _, _ = self.widget.bbox("insert")
        fontsize = self.settings.get_setting_value("ApplicationSettings.FontSize", default=10)
        x += self.widget.winfo_rootx() + int(fontsize*2.5)
        y += self.widget.winfo_rooty() + int(fontsize*2.5)

        self.tooltip_window = tw = tk.Toplevel(self.widget)
        tw.wm_overrideredirect(True)  # ウィンドウのタイトルバーなどを非表示に
        tw.wm_geometry(f"+{x}+{y}")

        # アプリケーション設定からフォントサイズを取得
        app_font_size = self.settings.get_setting_value("ApplicationSettings.FontSize", default=10)
        # ツールチップのフォントサイズを本文より少し小さく設定（最低8pt）
        tooltip_font_size = max(app_font_size - 2, 8)

        label = tk.Label(tw, text=self.text, justify='left',
                         background="#ffffe0", relief='solid', borderwidth=1,
                         font=("Yu Gothic UI", tooltip_font_size, "normal"))
        label.pack(ipadx=1)

    def hide_tooltip(self, event=None):
        """ツールチップウィンドウを非表示にします。"""
        if self.tooltip_window:
            self.tooltip_window.destroy()
        self.tooltip_window = None

# 設定オプションのUIを管理するクラス
class UI(tk.Toplevel):
    """
    アプリケーションの設定オプションを表示・変更するためのトップレベルウィンドウ。
    設定データは再帰的にUIに表示され、ユーザーの入力に応じてリアルタイムで更新されます。
    """
    def __init__(self, master, bus : EventBus, settings: config_controller.UserSettings):
        """
        UI_settingsウィンドウを初期化します。
        
        Args:
            ui (tk.Tk): tkinterのメインウィンドウインスタンス。
                        Toplevelの親として、また後で設定変更を通知する対象として利用されます。
            settings (config_controller.UserSettings): アプリケーション全体の設定を管理するオブジェクト。
                                                      このオブジェクトを通して設定値の取得と更新を行います。
        """
        super().__init__(master)
        self.title("設定")  # ウィンドウのタイトルを設定
        self.geometry("1000x700")  # ウィンドウの初期サイズを設定
        self.settings = settings  # UserSettingsオブジェクトをインスタンス変数として保持
        self.parent_ui = master # 親UIへの参照を保持
        self.bus = bus

        self._widget_vars: dict[str, tk.Variable] = {} # {full_path: tk.Variable_instance}

        # --- 設定表示領域のためのフレームとスクロールバー付きのキャンバスの配置 ---
        # メインフレーム: ウィンドウ全体に広がり、CanvasとScrollbarを格納
        main_frame = tk.Frame(self)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        # Canvas: スクロール可能な領域を提供。この上にscrollable_frameが配置される。
        self.canvas = tk.Canvas(main_frame)
        self.canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        # スクロールバー: Canvasと連動し、垂直スクロール機能を提供する
        self.bar_vertical_scroll = tk.Scrollbar(
            main_frame, orient=tk.VERTICAL, command=self.canvas.yview
        )
        self.bar_vertical_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        # Canvasのyviewコマンドをスクロールバーに設定し、双方向に連動させる
        self.canvas.configure(yscrollcommand=self.bar_vertical_scroll.set)

        # スクロール可能なフレーム: Canvas内に配置され、実際のUI要素がこの中に生成される
        self.scrollable_frame = ttk.Frame(self.canvas)
        # Canvas内にscrollable_frameをウィンドウとして作成し、初期位置を設定
        self.canvas_window = self.canvas.create_window((0, 0), window=self.scrollable_frame, anchor="nw")

        # イベントバインディング: スクロール可能なフレームとCanvasのサイズ変更を検知し、スクロール領域を調整
        self.scrollable_frame.bind("<Configure>", self._on_frame_configure)
        self.canvas.bind("<Configure>", self._on_canvas_configure)
        self.canvas.bind_all("<MouseWheel>", self._on_mousewheel)

        # --- 設定UIの再帰的な生成を開始 ---
        self.create_setting_ui_recursive()

        # --- 保存ボタンの配置 ---
        # ユーザーが変更を確定し、ウィンドウを閉じるためのボタン
        save_button = ttk.Button(self, text="設定を反映", command=self.save_and_apply_settings)
        save_button.pack(pady=10)
        #Xボタンで破棄しないように設定
        self.protocol("WM_DELETE_WINDOW", self.withdraw)

    def _on_frame_configure(self, event=None):
        """
        スクロール可能なフレームのサイズが変更されたときに呼び出されます。
        Canvasのスクロール領域を、フレームの現在のサイズに合わせて更新します。
        """
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))

    def _on_canvas_configure(self, event=None):
        """
        Canvas自体のサイズが変更されたときに呼び出されます。
        Canvas内に配置されたスクロール可能なフレーム（self.canvas_window）の幅を、
        Canvasの新しい幅に合わせることで、横スクロールが発生しないようにします。
        """
        self.canvas.itemconfig(self.canvas_window, width=event.width)

    def _on_mousewheel(self, event):
        """マウスホイールでCanvasをスクロールさせる"""
        # Windows/macOS では event.delta を使用
        # Linux では Button-4/5 を使用しますが、多くの環境に対応させる記述
        if event.num == 4: # Linux: Scroll Up
            self.canvas.yview_scroll(-1, "units")
        elif event.num == 5: # Linux: Scroll Down
            self.canvas.yview_scroll(1, "units")
        else: # Windows / macOS
            # event.delta は通常 120 の倍数で返ってくるため、
            # -1 * (delta / 120) でスクロール方向と量を調整
            self.canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")


    def create_setting_ui_recursive(self):
        """
        設定UIの再帰的な構築を開始する初期メソッドです。
        """
        self.scrollable_frame.columnconfigure(0, weight=1)
        # UI表示はself.settings._raw_config_dataから開始
        self.add_settings_to_frame(self.scrollable_frame, self.settings._raw_config_data, [])

    def _create_widget_for_item(self, parent_widget_frame, item_obj: config_controller.SettingItem, full_path: str, display_key: str):
        """
        指定されたSettingItemオブジェクトの型に基づき、対応するTkinterウィジェットを作成し、
        parent_widget_frame（設定項目ごとのフレーム）内に配置します。
        
        Args:
            parent_widget_frame (tk.Frame): ウィジェットを配置する親となるTkinterフレーム。
            item_obj (config_controller.SettingItem): 表示・編集する単一の設定項目を表すオブジェクト。
            full_path (str): 設定項目へのドット区切りの完全なパス（例: "applicationSettings.FontSize"）。
            display_key (str): JSONキーとしての名前。説明がない場合にラベルとして使われる。
        """
        
        # 設定項目の説明またはキーをラベルとして表示
        label = ttk.Label(parent_widget_frame, text=f"{display_key}:")
        label.grid(row=0, column=0, sticky="w", padx=5)

        # description があり、それが name と異なる場合のみツールチップを適用
        if item_obj.description and item_obj.description != item_obj.name:
            Tooltip(label, item_obj.description, self.settings)

        initial_value = item_obj.value

        # --- 各種設定項目のタイプに応じたウィジェットの作成 ---

        if item_obj.item_type == "choice":
            # 選択肢がある場合（例: ドロップダウンリスト）
            var = tk.StringVar(value=initial_value) # 現在の値をStringVarにセット
            if full_path == "ApplicationSettings.Model":
                item_obj.options = self.app.AI_Manager.get_models()
            if full_path == "ApplicationSettings.CharacterImage.Folder":
                item_obj.options = get_CharacterFolders()   
            elif full_path == "VoiceSettings.VOICEVOX.Model":
                item_obj.options = TTS_VoiceVoxEngine.get_speakers()
            elif full_path == "VoiceSettings.windowsNarrator.Model":
                item_obj.options = TTS_WindowsNarratorManager.get_SAPIVoice_names()
            combobox = ttk.Combobox(parent_widget_frame, textvariable=var, values=item_obj.options, state="readonly")
            combobox.grid(row=0, column=1, sticky="ew", padx=5)
            combobox.bind("<MouseWheel>", lambda e: "break")
            self._widget_vars[full_path] = var # 変数を保存

        # 関数で更新可能なコンボボックス
        elif item_obj.item_type == "choice_with_func":
            # ボタンとコンボボックスを格納するためのコンテナフレーム
            widget_container = ttk.Frame(parent_widget_frame)
            widget_container.grid(row=0, column=1, sticky="ew")
            # コンテナ内の列設定: column 0 はボタン用、column 1 はコンボボックス用で伸縮
            widget_container.columnconfigure(1, weight=1)

            # 初期メッセージとStringVar
            initial_message = "ボタンを押して項目を表示してください。"
            var = tk.StringVar(value=initial_value) # 現在の値をStringVarにセット
            self._widget_vars[full_path] = var

            # コンボボックスの作成
            combobox = ttk.Combobox(
                widget_container,
                textvariable=var,
                values=[initial_message],
                state="readonly"
            )
            combobox.grid(row=0, column=1, sticky="ew", padx=(5, 0)) # ボタンの右に配置
            combobox.bind("<MouseWheel>", lambda e: "break")
            # ボタンのコマンド関数
            def update_options():
                try:
                    # どの関数を呼び出すかを full_path に基づいて決定します。
                    # このアプローチは、既存の 'choice' タイプの実装スタイルを踏襲しています。
                    func_to_call = None

                    # --- ここに、パスと関数のマッピングを記述します ---
                        #キャラクターフォルダの選択
                    if full_path == "ApplicationSettings.CharacterImage.Folder":
                        func_to_call = get_CharacterFolders
                        #AIの選択
                    elif full_path == "LLMSettings.geminiAPI.model":
                        gemini = AI_geminiAPI.geminiAI(self.settings, debug=-1)
                        func_to_call = gemini.get_models
                    elif full_path == "LLMSettings.Ollama.model":
                        ollama = AI_ollama.ollamaAI(self.settings, debug=-1)
                        func_to_call = ollama.get_models

                        #音声モデルの選択
                    elif full_path == "VoiceSettings.VOICEVOX.Model":
                        if self.parent_ui.engine_process is not None:
                            func_to_call = TTS_VoiceVoxEngine.get_speakers
                        else:
                            # サーバーが起動していない場合は、その旨を表示して終了
                            combobox['values'] = ["サーバを起動していません。"]
                            var.set("サーバを起動していません。")
                            return
                    elif full_path == "VoiceSettings.windowsNarrator.Model":
                        func_to_call = TTS_WindowsNarratorManager.get_SAPIVoice_names
                    
                    
                    # 他のパスと関数のマッピングをここに追加できます
                    # elif full_path == "some.other.path":
                    #     func_to_call = some_other_function
                    
                    if func_to_call is None:
                        raise NotImplementedError(f"No function is mapped for path '{full_path}' with type 'choice_with_func'")
                    
                    # 関数を実行してオプションを取得
                    new_options = func_to_call()

                    if new_options and isinstance(new_options, (list, tuple)):
                        combobox['values'] = new_options
                        current_value = var.get()
                        # 更新後も同じ値があればそれを維持、なければ先頭を選択
                        if current_value in new_options:
                            var.set(current_value)
                        else:
                            var.set(new_options[0])
                    elif not new_options:
                        no_items_msg = "項目が見つかりませんでした"
                        combobox['values'] = [no_items_msg]
                        var.set(no_items_msg)
                    else:
                        raise TypeError(f"Function for '{full_path}' did not return a list or tuple.")
                
                except Exception as e:
                    error_msg = "設定UIの参照エラー"
                    logger.error(f"Error updating options for '{full_path}': {e}")
                    combobox['values'] = [error_msg]
                    var.set(error_msg)

            # ボタンの作成
            update_button = ttk.Button(
                widget_container,
                text="選択肢の更新",
                command=update_options
            )
            update_button.grid(row=0, column=0)









        elif item_obj.item_type == "int":
            # 整数値の入力フィールド
            var = tk.StringVar(value=str(initial_value)) # 現在の値を文字列としてStringVarにセット
            entry = ttk.Entry(parent_widget_frame, textvariable=var)
            entry.grid(row=0, column=1, sticky="ew", padx=5)
            self._widget_vars[full_path] = var # 変数を保存

        elif item_obj.item_type == "str":
            # 文字列の入力フィールド
            var = tk.StringVar(value=initial_value)
            entry = ttk.Entry(parent_widget_frame, textvariable=var)
            entry.grid(row=0, column=1, sticky="ew", padx=5)
            self._widget_vars[full_path] = var # 変数を保存

        elif item_obj.item_type == "bool":
            # 真偽値（オン/オフ）のチェックボタン
            var = tk.BooleanVar(value=initial_value)
            checkbutton = ttk.Checkbutton(parent_widget_frame, variable=var, text="有効" if initial_value else "無効")
            checkbutton.grid(row=0, column=1, sticky="w", padx=5)
            # チェックボタンのテキストを「有効」「無効」と切り替えるローカル関数
            # Note: チェックボックスはクリックされた時点で visual feedback が必要なので、テキストの更新は保持
            def toggle_text_local(bool_var, cb):
                cb.config(text="有効" if bool_var.get() else "無効")
            
            # BooleanVarの変更を検知し、トグル関数を呼び出す（テキスト表示のみ）
            var.trace_add("write", lambda *args, v=var, cb=checkbutton: toggle_text_local(v, cb))
            # 初期表示時にテキストを正しく設定
            toggle_text_local(var, checkbutton)
            self._widget_vars[full_path] = var # 変数を保存

        elif item_obj.item_type == "path":
            # 文字列の入力フィールド
            var = tk.StringVar(value=initial_value)
            entry = ttk.Entry(parent_widget_frame, textvariable=var)
            entry.grid(row=0, column=1, sticky="ew", padx=5)
            #フォルダ指定用のボタン
            if full_path == "VoiceSettings.VOICEVOX.path":
                _filetypes =[("VOICEVOXEngineの実行ファイル", "run.exe"),("すべてのファイル", "*.*")]
            else:
                _filetypes =[("すべてのファイル", "*.*")]
            
            # select_file_path 関数を修正して、`var` に値をセットした後に直接 `_widget_vars` にも反映するようにする
            def select_file_path_and_update(target_var, filetypes, path_for_var):
                selected_path = tkinter.filedialog.askopenfilename(filetypes=filetypes)
                if selected_path:
                    target_var.set(selected_path)
                    # ここで直接 _widget_vars の StringVar も更新する
                    self._widget_vars[path_for_var].set(selected_path)

            button = ttk.Button(parent_widget_frame, text="ファイルを選択", command=lambda p=full_path: select_file_path_and_update(var, _filetypes, p))
            button.grid(row=0, column=2, sticky="ew", padx=5)
            self._widget_vars[full_path] = var # 変数を保存
            
        # 未対応のタイプが検出された場合
        else:
            logger.error(f"未対応のタイプが検出されました。{item_obj.item_type} {full_path}")
            ttk.Label(parent_widget_frame, text=f"ERROR Unsupported type: {item_obj.item_type}").grid(row=0, column=1, sticky="w", padx=5)

    def add_settings_to_frame(self, parent_frame, config_node_dict, current_path_parts):
        """
        設定ノード（辞書）を再帰的に走査し、対応するUI要素（フレームやウィジェット）を
        parent_frame（親のTkinterフレーム）内に生成します。
        """
        row_num_in_parent = 0  # parent_frame 内でウィジェットを配置する現在の行番号カウンター

        for key, value_node in config_node_dict.items():
            new_path_parts = current_path_parts + [key] # 現在のパスにこのキーを追加
            full_path = ".".join(new_path_parts) # ドット区切りの完全パスを生成
            
            # ノードの名前（表示用）を決定
            display_name = value_node.get("name", key) if isinstance(value_node, dict) else key

            # Case 1: このノードがセクションである場合 ('type: "section"' と 'children' を持つ)
            if isinstance(value_node, dict) and value_node.get("type") == "section" and "children" in value_node and isinstance(value_node["children"], dict):
                # フレームタイトルの作成
                header_label = ttk.Label(parent_frame, text=display_name)
                if "description" in value_node and value_node["description"]:
                    Tooltip(header_label, value_node["description"], self.settings)
                # フレーム
                group_frame = ttk.LabelFrame(parent_frame, labelwidget=header_label, padding=(5,5))
                group_frame.grid(row=row_num_in_parent, column=0, sticky="ew", padx=5, pady=5)
                group_frame.columnconfigure(0, weight=1) # グループフレーム内の最初の列に重みを設定
                self.add_settings_to_frame(group_frame, value_node["children"], new_path_parts)
                row_num_in_parent += 1 # 親フレーム内の行カウンターを進める

            # Case 2: このノードが実際の設定項目である場合 ('value' を持つ)
            elif isinstance(value_node, dict) and "value" in value_node:
                item = self.settings.get_setting_item(full_path)
                if item: # SettingItemオブジェクトが取得できた場合
                    simple_item_frame = ttk.Frame(parent_frame)
                    simple_item_frame.grid(row=row_num_in_parent, column=0, sticky="ew", padx=5, pady=5)
                    simple_item_frame.columnconfigure(1, weight=1)
                    # UI生成時には、UserSettingsのオブジェクトを使用してウィジェットを構築
                    self._create_widget_for_item(simple_item_frame, item, full_path, display_name)
                    row_num_in_parent += 1
                else:
                    logger.error(f"警告: SettingItemが見つかりませんでした。設定のパスが間違っている可能性があります。{full_path}")
                    if any(isinstance(v, dict) for v in value_node.values()):
                        implicit_group_frame = ttk.LabelFrame(parent_frame, text=display_name, padding=(5,5))
                        implicit_group_frame.grid(row=row_num_in_parent, column=0, sticky="ew", padx=5, pady=5)
                        implicit_group_frame.columnconfigure(0, weight=1)
                        self.add_settings_to_frame(implicit_group_frame, value_node, new_path_parts)
                        row_num_in_parent += 1
                    else:
                        pass

            # Case 3: このノードが中間的な辞書である場合 (セクションでも設定項目でもない)
            elif isinstance(value_node, dict): 
                implicit_group_frame = ttk.LabelFrame(parent_frame, text=display_name, padding=(5,5))
                implicit_group_frame.grid(row=row_num_in_parent, column=0, sticky="ew", padx=5, pady=5)
                implicit_group_frame.columnconfigure(0, weight=1)
                self.add_settings_to_frame(implicit_group_frame, value_node, new_path_parts) # value_node自体を再帰
                row_num_in_parent += 1

        self.scrollable_frame.update_idletasks() # フレーム内のウィジェット配置後、フレームのサイズを更新
        self._on_frame_configure() # スクロール領域を更新し、初期スクロール位置を設定

    def save_and_apply_settings(self):
        """
        すべてのUIウィジェットから現在の値を取得し、それを実際のUserSettingsオブジェクトに適用、ファイルに保存。
        その後、設定更新を通知、ウィンドウを閉じる。
        """
        logger.debug("設定を反映ボタンが押されました。すべてのUI値を読み取り、設定に適用します。")
        for path, var_obj in self._widget_vars.items():
            item = self.settings.get_setting_item(path)
            if not item:
                logger.warning(f"警告: パス '{path}' の SettingItem が見つかりませんでした。スキップします。")
                continue
            new_value = var_obj.get()

            # 型に応じた値の変換とバリデーション
            if item.item_type == "int":
                try:
                    new_value = int(new_value)
                    # 範囲チェックとクランプ（必要に応じて）
                    min_val = item.value_range.get("min")
                    max_val = item.value_range.get("max")
                    if min_val is not None and new_value < min_val:
                        new_value = min_val
                        logger.warning(f"警告: '{path}' の値 {new_value} は最小値 {min_val} 未満のため、{min_val} に調整しました。")
                    if max_val is not None and new_value > max_val:
                        new_value = max_val
                        logger.warning(f"警告: '{path}' の値 {new_value} は最大値 {max_val} を超えているため、{max_val} に調整しました。")
                except ValueError:
                    logger.error(f"警告: '{path}' の値 '{new_value}' は整数ではありません。元の値を保持します。")
                    new_value = item.value # 無効な場合は元の値を保持
            elif item.item_type == "bool":
                # BooleanVar.get() は既に適切なブール値を返す
                pass
            # 他の型（str, choice, path）は StringVar.get() や Combobox.get() が適切な文字列値を返すため、特別な変換は不要

            # 更新された値を UserSettings にセット
            if self.settings.set_setting_value(path, new_value):
                pass
            else:
                logger.warning(f"警告: 設定 '{path}' の更新に失敗しました。元の値を保持します。")

        # UserSettingsオブジェクトに保持されている現在の設定データをファイルに書き込む
        config_controller.write_configfile(self.settings)
        # EventBusで設定更新を通知
        self.bus.publish("SettingsUpdated", self.settings)
        
        self.withdraw() # 設定ウィンドウを閉じる


#GUIを通してユーザーがファイルのパスを指定する際に利用する関数。(指定するStringVar、指定ファイルの種類の辞書？、)
# この関数はもはやUIクラスのメソッドではないため、UIクラスのインスタンスにアクセスできない。
# _create_widget_for_item 内でラムダ関数を使って select_file_path_and_update を定義し、
# その中で self._widget_vars を直接更新するように変更済み。
# よって、このグローバル関数は不要になるが、互換性のため残しておく。
def select_file_path(targetitem, filetype):
    target_path = tkinter.filedialog.askopenfilename(filetypes=filetype)
    if target_path:
        logger.info(f"ファイルパスが選択されました: {target_path}")
        targetitem.set(target_path)


if __name__ == "__main__":
    #全体テストができないので単体テスト
    pass
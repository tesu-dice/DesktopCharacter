# トップレベルウィンドウを使ったユーザーデータの変更・更新用プログラム。
# トップレベルウィンドウを使って、コンフィグの項目を再帰的に表示・変更できるようにする。

# このモジュールは、アプリケーションの設定値を動的に変更するためのGUIを提供します。
# 設定はJSON形式で管理され、ネストされた構造をUI上にツリー形式で表示し、
# ユーザーが各設定項目の値を変更・保存できるようにします。

# ライブラリのインポート
import tkinter as tk
import tkinter.filedialog
from tkinter import ttk  # スタイル付きウィジェットのため
import json  # object型を文字列として編集するために使用 (JSON文字列との相互変換)
import copy  # ディープコピーのために追加

# プログラム同士のインポート（これらは外部ファイルとして存在し、設定UIから利用される）
import config_controller # 設定ファイルの読み書きや、設定値の管理を行うモジュール
import talk_VoiceVoxEngine # VoiceVoxエンジンのスピーカーリストなどを取得するために使用
import talk_WindowsNarratorManager # Windowsナレーターの音声モデルなどを取得するために使用
from main import get_CharacterFolders # mainモジュールからget_CharacterFoldersをインポート

# 設定オプションのUIを管理するクラス
class UI(tk.Toplevel):
    """
    アプリケーションの設定オプションを表示・変更するためのトップレベルウィンドウ。
    設定データは再帰的にUIに表示され、ユーザーの入力に応じてリアルタイムで更新されます。
    """
    def __init__(self, ui, settings: config_controller.UserSettings):
        """
        UI_settingsウィンドウを初期化します。
        
        Args:
            ui (tk.Tk): tkinterのメインウィンドウインスタンス。
                        Toplevelの親として、また後で設定変更を通知する対象として利用されます。
            settings (config_controller.UserSettings): アプリケーション全体の設定を管理するオブジェクト。
                                                      このオブジェクトを通して設定値の取得と更新を行います。
        """
        # TkinterのToplevelウィジェットとして初期化（独立したサブウィンドウを作成）
        super().__init__(ui)
        self.title("設定")  # ウィンドウのタイトルを設定
        self.geometry("500x600")  # ウィンドウの初期サイズを設定
        self.settings = settings  # UserSettingsオブジェクトをインスタンス変数として保持
        self.parent_ui = ui # 親UIへの参照を保持

        # ★変更点1: 一時的な設定データ保持用辞書を初期化★
        # self.settings._raw_config_data のディープコピーを作成し、一時的な変更はこのコピーに対して行う
        self._temp_settings_data = copy.deepcopy(self.settings._raw_config_data)

        # 削除ボタンの上書き（WM_DELETE_WINDOW プロトコルを上書き）
        self.protocol("WM_DELETE_WINDOW", self.withdraw) 

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

        # --- 設定UIの再帰的な生成を開始 ---
        # ★変更点2: UIの初期表示は、元の設定データ(self.settings._raw_config_data)を使用する★
        self.create_setting_ui_recursive()

        # --- 保存ボタンの配置 ---
        # ユーザーが変更を確定し、ウィンドウを閉じるためのボタン
        save_button = ttk.Button(self, text="保存して閉じる", command=self.save_and_close)
        save_button.pack(pady=10)

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

    def create_setting_ui_recursive(self):
        """
        設定UIの再帰的な構築を開始する初期メソッドです。
        """
        self.scrollable_frame.columnconfigure(0, weight=1)
        self.add_settings_to_frame(self.scrollable_frame, self.settings._raw_config_data, [])

    # ★追加関数: 一時データ (_temp_settings_data) を更新するヘルパー関数★
    def _update_temp_setting_value(self, full_path, value):
        """
        指定されたパスの一時的な設定値を更新します。
        """
        parts = full_path.split('.')
        current_node = self._temp_settings_data
        for part in parts[:-1]:
            current_node = current_node.setdefault(part, {}) # 存在しない場合は作成
        
        last_part = parts[-1]
        
        # 最終ノードに到達したら値を更新
        # 設定が {"key": {"value": X, ...}} の形式か、{"key": X} の形式かを判断
        if isinstance(current_node.get(last_part), dict) and "value" in current_node[last_part]:
            current_node[last_part]['value'] = value
        else:
            current_node[last_part] = value

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
        ttk.Label(parent_widget_frame, text=f"{display_key}:").grid(row=0, column=0, sticky="w", padx=5)

        # ★変更点3: ウィジェットの初期値はitem_obj.valueから取得する★
        initial_value = item_obj.value

        # --- 各種設定項目のタイプに応じたウィジェットの作成 ---

        if item_obj.item_type == "choice":
            # 選択肢がある場合（例: ドロップダウンリスト）
            var = tk.StringVar(value=initial_value) # 現在の値をStringVarにセット
            if full_path == "ApplicationSettings.CharacterFolder":
                item_obj.options = get_CharacterFolders()
            elif full_path == "VoiceSettings.VOICEVOX.Model":
                item_obj.options = talk_VoiceVoxEngine.get_speakers()
            elif full_path == "VoiceSettings.windowsNarrator.Model":
                item_obj.options = talk_WindowsNarratorManager.get_SAPIVoice_names()
            combobox = ttk.Combobox(parent_widget_frame, textvariable=var, values=item_obj.options, state="readonly")
            combobox.grid(row=0, column=1, sticky="ew", padx=5)
            # ★変更点4: StringVarの変更を検知し、一時データを更新する★
            var.trace_add("write", lambda *args, p=full_path, v=var: self._update_temp_setting_value(p, v.get()))

        elif item_obj.item_type == "int":
            # 整数値の入力フィールド
            var = tk.StringVar(value=str(initial_value)) # 現在の値を文字列としてStringVarにセット
            entry = ttk.Entry(parent_widget_frame, textvariable=var)
            entry.grid(row=0, column=1, sticky="ew", padx=5)
            # 入力値のバリデーションと一時データ更新を行うローカル関数
            def validate_and_set_int_local(p_path, str_var):
                try:
                    val = int(str_var.get()) # 入力値を整数に変換
                    min_val = item_obj.value_range.get("min") # 最小値を取得
                    max_val = item_obj.value_range.get("max") # 最大値を取得
                    # 範囲チェックと値のクランプ（範囲外なら最小値/最大値に調整）
                    if min_val is not None and val < min_val: str_var.set(str(min_val)); val = min_val
                    elif max_val is not None and val > max_val: str_var.set(str(max_val)); val = max_val
                    # ★変更点5: UserSettingsではなく一時データを更新★
                    self._update_temp_setting_value(p_path, val) 
                except ValueError:
                    # 無効な入力（数値でない場合）は、設定オブジェクトの現在の値に戻す
                    # ここでは一時データの値に戻す
                    current_val_in_temp = self._get_setting_value_from_temp(p_path)
                    if current_val_in_temp is not None: str_var.set(str(current_val_in_temp))
            # StringVarの変更を検知し、バリデーション関数を呼び出す
            var.trace_add("write", lambda *args, p=full_path, v=var: validate_and_set_int_local(p,v))

        elif item_obj.item_type == "str":
            # 文字列の入力フィールド
            var = tk.StringVar(value=initial_value)
            entry = ttk.Entry(parent_widget_frame, textvariable=var)
            entry.grid(row=0, column=1, sticky="ew", padx=5)
            # ★変更点6: StringVarの変更を検知し、一時データを更新する★
            var.trace_add("write", lambda *args, p=full_path, v=var: self._update_temp_setting_value(p, v.get()))

        elif item_obj.item_type == "bool":
            # 真偽値（オン/オフ）のチェックボタン
            var = tk.BooleanVar(value=initial_value)
            checkbutton = ttk.Checkbutton(parent_widget_frame, variable=var, text="有効" if initial_value else "無効")
            checkbutton.grid(row=0, column=1, sticky="w", padx=5)
            # チェックボタンのテキストを「有効」「無効」と切り替え、一時データを更新するローカル関数
            def toggle_text_local(bool_var, cb, p_path):
                cb.config(text="有効" if bool_var.get() else "無効")
                # ★変更点7: UserSettingsではなく一時データを更新★
                self._update_temp_setting_value(p_path, bool_var.get())
            # BooleanVarの変更を検知し、トグル関数を呼び出す
            var.trace_add("write", lambda *args, p_path=full_path, v=var, cb=checkbutton: toggle_text_local(v, cb, p_path))
            # 初期表示時にテキストを正しく設定
            toggle_text_local(var, checkbutton, full_path)

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
            button = ttk.Button(parent_widget_frame, text="ファイルを選択", command=lambda:select_file_path(var, _filetypes))
            button.grid(row=0, column=2, sticky="ew", padx=5)
            # ★変更点8: 値の変化を追跡し、一時データを更新する★
            var.trace_add("write", lambda *args, p=full_path, v=var: self._update_temp_setting_value(p, v.get()))
            
        # 未対応のタイプが検出された場合
        else:
            print("未対応のタイプが検出されました。", item_obj.item_type, full_path)
            ttk.Label(parent_widget_frame, text=f"Unsupported type: {item_obj.item_type}").grid(row=0, column=1, sticky="w", padx=5)

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
                group_frame = ttk.LabelFrame(parent_frame, text=display_name, padding=(5,5))
                group_frame.grid(row=row_num_in_parent, column=0, sticky="ew", padx=5, pady=5)
                group_frame.columnconfigure(0, weight=1) # グループフレーム内の最初の列に重みを設定
                self.add_settings_to_frame(group_frame, value_node["children"], new_path_parts)
                row_num_in_parent += 1 # 親フレーム内の行カウンターを進める

            # Case 2: このノードが実際の設定項目である場合 ('value' を持つ)
            elif isinstance(value_node, dict) and "value" in value_node:
                item = self.settings.get_setting_item(full_path)
                if item: # SettingItemオブジェクトが取得できた場合
                    simple_item_frame = ttk.Frame(parent_frame)
                    simple_item_frame.grid(row=row_num_in_parent, column=0, sticky="ew", padx=5, pady=2)
                    simple_item_frame.columnconfigure(1, weight=1)
                    self._create_widget_for_item(simple_item_frame, item, full_path, display_name)
                    row_num_in_parent += 1
                else:
                    print(f"警告: パス '{full_path}' は 'value' を持ちますが、SettingItemとして登録されていません。")
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

    def save_and_close(self):
        """
        一時的な変更を実際のUserSettingsオブジェクトに適用し、ファイルに保存します。
        その後、設定ウィンドウを閉じ、親UIに通知します。
        """
        # ★変更点9: _temp_settings_data の内容を self.settings に一括で適用★
        self.settings._raw_config_data = copy.deepcopy(self._temp_settings_data)

        # UserSettingsオブジェクトに保持されている現在の設定データをファイルに書き込む
        config_controller.write_configfile(self.settings) 
        
        # 親のUIインスタンスに、設定が保存されたことを通知する
        self.parent_ui.app.setting = config_controller.read_configfile("config.json")
        
        self.withdraw() # 設定ウィンドウを閉じる


#GUIを通してユーザーがファイルのパスを指定する際に利用する関数。(指定するStringVar、指定ファイルの種類の辞書？、)
def select_file_path(targetitem, filetype):
    target_path = tkinter.filedialog.askopenfilename(filetypes=filetype)
    if target_path:
        print(target_path)
        targetitem.set(target_path)


if __name__ == "__main__":
    #全体テストができないので単体テスト
    pass
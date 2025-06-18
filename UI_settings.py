"""
トップレベルウィンドウを使ったユーザーデータの変更・更新用プログラム。
トップレベルウィンドウを使って、コンフィグの項目を再帰的に表示・変更できるようにする。

このモジュールは、アプリケーションの設定値を動的に変更するためのGUIを提供します。
設定はJSON形式で管理され、ネストされた構造をUI上にツリー形式で表示し、
ユーザーが各設定項目の値を変更・保存できるようにします。
"""

# ライブラリのインポート
import tkinter as tk
from tkinter import ttk  # スタイル付きウィジェットのため
import json  # object型を文字列として編集するために使用 (JSON文字列との相互変換)
# プログラム同士のインポート（これらは外部ファイルとして存在し、設定UIから利用される）
import config_controller # 設定ファイルの読み書きや、設定値の管理を行うモジュール
import talk_VoiceVoxEngine # VoiceVoxエンジンのスピーカーリストなどを取得するために使用
import talk_WindowsNarratorManager # Windowsナレーターの音声モデルなどを取得するために使用

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
            ui (tk.Tk): kinterのメインウィンドウインスタンス。
                        Toplevelの親として、また後で設定変更を通知する対象として利用されます。
            settings (config_controller.UserSettings): アプリケーション全体の設定を管理するオブジェクト。
                                                      このオブジェクトを通して設定値の取得と更新を行います。
        """
        # TkinterのToplevelウィジェットとして初期化（独立したサブウィンドウを作成）
        super().__init__(ui)
        self.title("設定")  # ウィンドウのタイトルを設定
        self.geometry("500x600")  # ウィンドウの初期サイズを設定
        self.settings = settings  # UserSettingsオブジェクトをインスタンス変数として保持
        # UserSettingsオ親となるTブジェクトから、UI表示用の生のJSONデータを取得
        # これを基にUIを構築し、変更を一時的に反映させる
        self.original_config_data = settings.rawjson 

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
        self.create_setting_ui_recursive()

        # --- 保存ボタンの配置 ---
        # ユーザーが変更を確定し、ウィンドウを閉じるためのボタン
        save_button = ttk.Button(self, text="保存して閉じる", command=self.save_and_close)
        save_button.pack(pady=10)

    def _on_frame_configure(self, event=None):
        """
        スクロール可能なフレームのサイズが変更されたときに呼び出されます。
        Canvasのスクロール領域を、フレームの現在のサイズに合わせて更新します。
        これにより、フレーム内のコンテンツが増減しても正しくスクロールできるようになります。
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
        scrollable_frame の最初の列に重み（weight=1）を設定し、利用可能な幅に広がるようにします。
        その後、実際のUI構築ロジックである add_settings_to_frame を呼び出します。
        """
        self.scrollable_frame.columnconfigure(0, weight=1)
        # UserSettingsオブジェクトから取得した生のconfigデータと、初期パス([])を渡してUI構築を開始
        self.add_settings_to_frame(self.scrollable_frame, self.original_config_data, [])

    def _create_widget_for_item(self, parent_widget_frame, item_obj: config_controller.SettingItem, full_path: str, display_key: str):
        """
        指定されたSettingItemオブジェクトの型に基づき、対応するTkinterウィジェットを作成し、
        parent_widget_frame（設定項目ごとのフレーム）内に配置します。
        ユーザーがウィジェットの値を変更すると、UserSettingsオブジェクト内の対応する設定値も更新されます。
        
        Args:
            parent_widget_frame (tk.Frame): ウィジェットを配置する親となるTkinterフレーム。
            item_obj (config_controller.SettingItem): 表示・編集する単一の設定項目を表すオブジェクト。
            full_path (str): 設定項目へのドット区切りの完全なパス（例: "applicationSettings.FontSize"）。
            display_key (str): JSONキーとしての名前。説明がない場合にラベルとして使われる。
        """
        #print("    UI_setting.py _create_widget_for_item was called. ->",display_key, item_obj.value, full_path)
        
        
        # 設定項目の説明またはキーをラベルとして表示
        ttk.Label(parent_widget_frame, text=f"{display_key}:").grid(row=0, column=0, sticky="w", padx=5)

        # --- 各種設定項目のタイプに応じたウィジェットの作成 ---

        if item_obj.item_type == "choice":
            #print("    UI_setting.py _create_widget...() was called.", full_path)
            # 選択肢がある場合（例: ドロップダウンリスト）
            var = tk.StringVar(value=item_obj.value) # 現在の値をStringVarにセット
            if full_path == "VoiceSettings.VOICEVOX.Model":
                item_obj.options = talk_VoiceVoxEngine.get_speakers()
            elif full_path == "VoiceSettings.windowsNarrator.Model":
                item_obj.options = talk_WindowsNarratorManager.get_SAPIVoice_names()
            combobox = ttk.Combobox(parent_widget_frame, textvariable=var, values=item_obj.options, state="readonly")
            combobox.grid(row=0, column=1, sticky="ew", padx=5)
            # StringVarの変更を検知し、UserSettingsオブジェクトの対応する値を更新
            var.trace_add("write", lambda *args, p=full_path, v=var: self.settings.set_setting_value(p, v.get()))

        elif item_obj.item_type == "int":
            # 整数値の入力フィールド
            var = tk.StringVar(value=str(item_obj.value)) # 現在の値を文字列としてStringVarにセット
            entry = ttk.Entry(parent_widget_frame, textvariable=var)
            entry.grid(row=0, column=1, sticky="ew", padx=5)
            # 入力値のバリデーションとUserSettingsオブジェクトの更新を行うローカル関数
            def validate_and_set_int_local(p_path, str_var):
                try:
                    val = int(str_var.get()) # 入力値を整数に変換
                    min_val = item_obj.value_range.get("min") # 最小値を取得
                    max_val = item_obj.value_range.get("max") # 最大値を取得
                    # 範囲チェックと値のクランプ（範囲外なら最小値/最大値に調整）
                    if min_val is not None and val < min_val: str_var.set(str(min_val)); val = min_val
                    elif max_val is not None and val > max_val: str_var.set(str(max_val)); val = max_val
                    self.settings.set_setting_value(p_path, val) # UserSettingsを更新
                except ValueError:
                    # 無効な入力（数値でない場合）は、設定オブジェクトの現在の値に戻す
                    current_val_in_settings = self.settings.get_setting_value(p_path)
                    if current_val_in_settings is not None: str_var.set(str(current_val_in_settings))
            # StringVarの変更を検知し、バリデーション関数を呼び出す
            var.trace_add("write", lambda *args, p=full_path, v=var: validate_and_set_int_local(p,v))

        elif item_obj.item_type == "string":
            # 文字列の入力フィールド
            var = tk.StringVar(value=item_obj.value)
            entry = ttk.Entry(parent_widget_frame, textvariable=var)
            entry.grid(row=0, column=1, sticky="ew", padx=5)
            # StringVarの変更を検知し、UserSettingsオブジェクトの対応する値を更新
            var.trace_add("write", lambda *args, p=full_path, v=var: self.settings.set_setting_value(p, v.get()))

        elif item_obj.item_type == "boolean":
            # 真偽値（オン/オフ）のチェックボタン
            var = tk.BooleanVar(value=item_obj.value)
            checkbutton = ttk.Checkbutton(parent_widget_frame, variable=var, text="有効" if item_obj.value else "無効")
            checkbutton.grid(row=0, column=1, sticky="w", padx=5)
            # チェックボタンのテキストを「有効」「無効」と切り替え、UserSettingsを更新するローカル関数
            def toggle_text_local(bool_var, cb, p_path):
                cb.config(text="有効" if bool_var.get() else "無効")
                self.settings.set_setting_value(p_path, bool_var.get())
            # BooleanVarの変更を検知し、トグル関数を呼び出す
            var.trace_add("write", lambda *args, p_path=full_path, v=var, cb=checkbutton: toggle_text_local(v, cb, p_path))
            # 初期表示時にテキストを正しく設定
            toggle_text_local(var, checkbutton, full_path)

        elif item_obj.item_type == "object":
            # JSONオブジェクトを直接テキストとして編集するフィールド
            var = tk.StringVar(value=json.dumps(item_obj.value, ensure_ascii=False, indent=2))
            entry = ttk.Entry(parent_widget_frame, textvariable=var, width=40)
            entry.grid(row=0, column=1, sticky="ew", padx=5)
            # 入力値のバリデーション（有効なJSONか）とUserSettingsオブジェクトの更新を行うローカル関数
            def validate_and_set_object_local(p_path, str_var):
                try:
                    val = json.loads(str_var.get()) # 入力文字列をJSONとしてパース
                    self.settings.set_setting_value(p_path, val) # UserSettingsを更新
                except json.JSONDecodeError:
                    # 無効なJSONが入力された場合は、設定オブジェクトの現在の値に戻す
                    current_val_in_settings = self.settings.get_setting_value(p_path)
                    if current_val_in_settings is not None: 
                        str_var.set(json.dumps(current_val_in_settings, ensure_ascii=False, indent=2))
            # StringVarの変更を検知し、バリデーション関数を呼び出す
            var.trace_add("write", lambda *args, p=full_path, v=var: validate_and_set_object_local(p,v))
            
        # 未対応のタイプが検出された場合
        else:
            print("未対応のタイプが検出されました。", item_obj.item_type, full_path)
            ttk.Label(parent_widget_frame, text=f"Unsupported type: {item_obj.item_type}").grid(row=0, column=1, sticky="w", padx=5)

    def add_settings_to_frame(self, parent_frame, config_node_dict, current_path_parts):
        """
        設定ノード（辞書）を再帰的に走査し、対応するUI要素（フレームやウィジェット）を
        parent_frame（親のTkinterフレーム）内に生成します。
        
        Args:
            parent_frame (tk.Frame): 現在のノードのUI要素を配置する親となるTkinterフレーム。
            config_node_dict (dict): 現在処理中の設定階層の辞書データ。
            current_path_parts (list): 現在の階層までのパスの各部分を格納したリスト。
                                       （例: ["applicationSettings", "appearance"]）
        """
        #print("UI_settings.py add_settings_to_frame() was called.", current_path_parts)
        row_num_in_parent = 0  # parent_frame 内でウィジェットを配置する現在の行番号カウンター
        # sorted_keys = sorted(config_node_dict.keys()) # 設定キーをソートして順序を保証

        for key in config_node_dict.keys(): # 元の順序を維持するためにソートしない
            value_node = config_node_dict[key] # 現在処理中のキーに対応する値（辞書または設定値）
            new_path_parts = current_path_parts + [key] # 現在のパスにこのキーを追加
            full_path = ".".join(new_path_parts) # ドット区切りの完全パスを生成
            
            node_name_from_json = key # JSONキーをデフォルトの名前とする
            node_type_from_json = None # JSONから取得した'type'属性を初期化

            if isinstance(value_node, dict):
                # value_nodeが辞書の場合、'name'と'type'属性を抽出（あれば）
                node_name_from_json = value_node.get("name", key)
                node_type_from_json = value_node.get("type")

            # 設定管理オブジェクトから対応するSettingItemオブジェクトを取得
            item = self.settings.get_setting_item(full_path)

            potential_children_dict = {}
            if isinstance(value_node, dict):
                # SettingItemが処理するキー（name, type, value, optionsなど）を除外して、
                # ネストされた子設定ノード（辞書）をpotential_children_dictに抽出
                keys_handled_by_item_or_structure = {"name", "type", "value", "value_init", "options", "min", "max", "description"} # descriptionも追加
                potential_children_dict = {
                    k: v for k, v in value_node.items()
                    if k not in keys_handled_by_item_or_structure and isinstance(v, dict)
                }

            if node_type_from_json == "None":
                # JSONで "type": "None" と指定された場合、これは単なるグループ（セクション）として扱う
                # LabelFrameを作成し、その中に子設定を再帰的に追加
                group_frame = ttk.LabelFrame(parent_frame, text=node_name_from_json, padding=(5,5))
                group_frame.grid(row=row_num_in_parent, column=0, sticky="ew", padx=5, pady=5)
                group_frame.columnconfigure(0, weight=1) # グループフレーム内の最初の列に重みを設定
                # "name"と"type"以外のすべてのキーを子ノードとして再帰処理
                children_to_render = {k: v for k, v in value_node.items() if k not in ["name", "type"]}
                self.add_settings_to_frame(group_frame, children_to_render, new_path_parts)
                row_num_in_parent += 1 # 親フレーム内の行カウンターを進める

            elif item: # config_controller.SettingItemオブジェクトが取得できた場合（単一の設定項目）
                if potential_children_dict:
                    # SettingItemであり、かつさらに子要素（ネストされた辞書）を持つ場合
                    # （例: "voiceSettings" の下に "engine" があり、それがさらに子を持つような場合）
                    container_label = node_name_from_json # 説明があればそれを使う、なければキー
                    item_group_frame = ttk.LabelFrame(parent_frame, text=container_label, padding=(5,5))
                    item_group_frame.grid(row=row_num_in_parent, column=0, sticky="ew", padx=5, pady=5)
                    item_group_frame.columnconfigure(0, weight=1)

                    # 1. 自身のウィジェットを配置するためのフレーム
                    widget_host_frame = ttk.Frame(item_group_frame)
                    widget_host_frame.grid(row=0, column=0, sticky="ew", pady=(0, 2))
                    widget_host_frame.columnconfigure(1, weight=1) # 値の入力ウィジェットに重み
                    self._create_widget_for_item(widget_host_frame, item, full_path, key)

                    # 2. その設定項目の子要素を再帰的に配置するためのフレーム
                    children_host_frame = ttk.Frame(item_group_frame)
                    children_host_frame.grid(row=1, column=0, sticky="ew", pady=(2,0))
                    children_host_frame.columnconfigure(0, weight=1)
                    # 抽出された子要素の辞書を渡して再帰呼び出し
                    self.add_settings_to_frame(children_host_frame, potential_children_dict, new_path_parts)
                    row_num_in_parent += 1

                else:
                    # SettingItemであり、子要素を持たないシンプルな設定項目
                    simple_item_frame = ttk.Frame(parent_frame)
                    simple_item_frame.grid(row=row_num_in_parent, column=0, sticky="ew", padx=5, pady=2)
                    simple_item_frame.columnconfigure(1, weight=1)
                    self._create_widget_for_item(simple_item_frame, item, full_path, key)
                    row_num_in_parent += 1

            elif isinstance(value_node, dict):
                # SettingItemとしては認識されなかったが、辞書型の子要素を持つ場合
                # 暗黙的なグループとしてLabelFrameを作成し、その中に子設定を再帰的に追加
                #print(value_node, current_path_parts)
                implicit_group_frame = ttk.LabelFrame(parent_frame, text=node_name_from_json, padding=(5,5))
                implicit_group_frame.grid(row=row_num_in_parent, column=0, sticky="ew", padx=5, pady=5)
                implicit_group_frame.columnconfigure(0, weight=1)
                self.add_settings_to_frame(implicit_group_frame, value_node, new_path_parts)
                row_num_in_parent += 1
            # else: # その他のケース (リストなど) はここでは処理されない

        self.scrollable_frame.update_idletasks() # フレーム内のウィジェット配置後、フレームのサイズを更新
        self._on_frame_configure() # スクロール領域を更新し、初期スクロール位置を設定

    def save_and_close(self):
        """
        現在の設定変更をconfig.jsonファイルに保存し、設定ウィンドウを閉じます。
        保存後、UserSettingsオブジェクトを最新の設定で再読み込みします。
        """
        # UserSettingsオブジェクトに保持されている現在の設定データをファイルに書き込む
        config_controller.write_configfile(self.settings)
        # ファイルに保存された最新の設定を再読み込みし、self.settingsを更新
        # （これにより、メインアプリケーション側で設定を再読み込む際にも最新の状態が反映される）
        self.settings = config_controller.read_configfile("config.json")
        self.destroy() # 設定ウィンドウを閉じる


if __name__ == "__main__":
    import main
    main.start_app()
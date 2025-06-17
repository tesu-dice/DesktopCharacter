"""
config.json ファイルを読み書きしてアプリケーション設定を管理します。
設定は UserSettings クラスを介して保存およびアクセスされ、個々の設定は
SettingItem オブジェクトとして表現されます。
"""
import json
import os
from typing import Any, Dict, List, Optional, Union


class SettingItem:
    """個々の設定項目を表します。"""
    def __init__(self,
                 path: str,
                 value: Any,
                 item_type: str,
                 raw_item_data: Dict[str, Any],
                 description: str = "",
                 options: Optional[List[Any]] = None,
                 value_range: Optional[Dict[str, Any]] = None):
        """
        SettingItem を初期化します。

        Args:
            path: 設定へのドット区切りパス (例: "audioSettings.windowsNarrator.voiceModel")。
            value: 設定の現在の値。
            item_type: 設定の型 ("choice", "integer", "string", "boolean", "object")。
            raw_item_data: この設定項目に対応する元のJSONノードのデータ。
            description: 設定の人間可読な説明 (JSON の "name" フィールドから)。
            options: 利用可能な選択肢のリスト ("choice" 型の場合)。
            value_range: min/max 制約を指定する辞書。
                         "integer" の場合: {"min": int, "max": int}。
                         "object" の場合: {"min": dict, "max": dict} (サブプロパティの制約)。
        """
        self.path: str = path
        self.description: str = description
        self.value: Any = value
        self.item_type: str = item_type
        self.options: List[Any] = options or []
        self.value_range: Dict[str, Any] = value_range or {}
        self.raw_item_data: Dict[str, Any] = raw_item_data

    def __repr__(self) -> str:
        return (f"SettingItem(path='{self.path}', value={repr(self.value)}, "
                f"type='{self.item_type}', description='{self.description}', "
                f"options={self.options}, range={self.value_range}, raw_data_keys={list(self.raw_item_data.keys())})")


class UserSettings:
    """JSON ファイルからロードおよび保存されるすべてのアプリケーション設定を管理します。"""

    def __init__(self):
        self._settings_map: Dict[str, SettingItem] = {}

    def _parse_json_node(self, node: Dict[str, Any], current_path_parts: List[str]):
        """
        JSON データからノードを再帰的に解析して _settings_map を設定します。
        """
        # 現在のノード自体が設定定義であるかを確認
        # ノードが "value" キーを直接含む場合、設定定義と見なされる
        if "value" in node:
            path_str = ".".join(current_path_parts)
            if not path_str: # 有効な設定構造では発生しないはず
                return

            value = node["value"]
            description = node.get("name", current_path_parts[-1])
            options = node.get("options")
            json_min = node.get("min")
            json_max = node.get("max")

            item_type = node.get("type") # デフォルト
            value_range_data = {}


            self._settings_map[path_str] = SettingItem(
                path=path_str,
                value=value,
                item_type=item_type,
                raw_item_data=node.copy(), # 元のノードデータをコピーして保持
                description=description,
                options=options,
                value_range=value_range_data
            )
            # このノードは設定項目なので、"name" や "value" などのキーにさらに再帰しない
            return

        # 直接の設定項目でない場合、その子に再帰する
        for key, sub_node in node.items():
            if isinstance(sub_node, dict):
                self._parse_json_node(sub_node, current_path_parts + [key])

    def load_from_dict(self, config_data: Dict[str, Any]):
        """辞書 (解析された JSON) から設定をロードします。"""
        self.rawjson = config_data.copy()
        self._settings_map.clear()
        self._parse_json_node(config_data, [])

    def get_setting_value(self, path: str, default: Any = None) -> Any:
        """パスによって設定の値を取得します。"""
        item = self._settings_map.get(path)
        return item.value if item else default

    def set_setting_value(self, path: str, new_value: Any) -> bool:
        """
        パスによって設定の値を設定し、基本的な検証を行います。
        成功した場合は True、それ以外の場合は False を返します。
        """
        item = self._settings_map.get(path)
        if not item:
            print(f"警告: パス '{path}' の設定が見つかりません。")
            return False

        # 基本的な型と制約の検証
        if item.item_type == "choice":
            if item.options and new_value not in item.options:
                print(f"警告: '{path}' の値 '{new_value}' は選択肢 {item.options} にありません。")
                return False
        elif item.item_type == "int":
            if not isinstance(new_value, int):
                print(f"警告: '{path}' の値 '{new_value}' は整数ではありません。")
                return False
            if "min" in item.value_range and new_value < item.value_range["min"]:
                print(f"警告: '{path}' の値 {new_value} は最小値 {item.value_range['min']} 未満です。")
                return False
            if "max" in item.value_range and new_value > item.value_range["max"]:
                print(f"警告: '{path}' の値 {new_value} は最大値 {item.value_range['max']} を超えています。")
                return False
        elif item.item_type == "object":
            if not isinstance(new_value, dict):
                print(f"警告: '{path}' (型 object) の値は辞書である必要があります。")
                return False
            # 範囲が定義されている場合はサブプロパティを検証
            if "min" in item.value_range and "max" in item.value_range:
                min_constraints = item.value_range["min"]
                max_constraints = item.value_range["max"]
                if isinstance(min_constraints, dict) and isinstance(max_constraints, dict):
                    for k, v_new in new_value.items():
                        if k in min_constraints and v_new < min_constraints[k]:
                            print(f"警告: '{path}' のサブプロパティ '{k}' の値 {v_new} は最小値 {min_constraints[k]} 未満です。")
                            return False
                        if k in max_constraints and v_new > max_constraints[k]:
                            print(f"警告: '{path}' のサブプロパティ '{k}' の値 {v_new} は最大値 {max_constraints[k]} を超えています。")
                            return False
        elif item.item_type == "boolean":
            if not isinstance(new_value, bool):
                print(f"警告: '{path}' の値 '{new_value}' はブール値ではありません。")
                return False
        elif item.item_type == "string":
            if not isinstance(new_value, str):
                print(f"警告: '{path}' の値 '{new_value}' は文字列ではありません。")
                return False

        item.value = new_value
        # raw_item_data内の 'value' も更新する
        if 'value' in item.raw_item_data:
            item.raw_item_data['value'] = new_value
        return True

    def get_setting_item(self, path: str) -> Optional[SettingItem]:
        """パスによって完全な SettingItem オブジェクトを取得します。"""
        return self._settings_map.get(path)

    def to_dict_for_save(self) -> Dict[str, Any]:
        """すべての設定を JSON 保存のためにネストされた辞書構造に変換し直します。"""
        output_root = {}
        # sorted_paths = sorted(self._settings_map.keys()) # 一貫した出力順序のためにソート

        for path in self._settings_map.keys(): # 元の順序を維持するためにソートしない
            item = self._settings_map[path]
            path_parts = path.split('.')
            
            current_node = output_root
            # 親ノードをたどる/作成する
            for part in path_parts[:-1]: # 最後の要素 (リーフキー) を除く
                current_node = current_node.setdefault(part, {})
            
            # リーフノードに item.raw_item_data を設定
            leaf_key = path_parts[-1]
            current_node[leaf_key] = item.raw_item_data
        return output_root

    def __repr__(self) -> str:
        items_repr = "\n".join(f"  {path}: {item!r}" for path, item in self._settings_map.items())
        return f"UserSettings(\n{items_repr}\n)"


def read_configfile(filepath: str = "config.json") -> UserSettings:
    """
    JSON ファイルから設定を読み込み、UserSettings インスタンスを返します。
    """
    settings = UserSettings()
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
        # print(data.keys())
        # print(data.values())
        # print(data.items())
        settings.load_from_dict(data)
    except FileNotFoundError:
        print(f"情報: 設定ファイル '{filepath}' が見つかりません。空の設定で初期化します。")
    except json.JSONDecodeError as e:
        print(f"エラー: '{filepath}' から JSON をデコードできませんでした。{e}。空の設定で初期化します。")
    except Exception as e:
        print(f"エラー: '{filepath}' の読み込み中に予期しないエラーが発生しました。{e}。空の設定で初期化します。")
    return settings


def write_configfile(usersettings: UserSettings, filepath: str = "config.json"):
    """
    UserSettings インスタンスから現在の設定を JSON ファイルに書き込みます。
    """
    try:
        data_to_save = usersettings.to_dict_for_save()
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data_to_save, f, ensure_ascii=False, indent=2) # indent=2 で整形
        print(f"情報: 設定が '{filepath}' に正常に書き込まれました。")
    except Exception as e:
        print(f"エラー: '{filepath}' への書き込み中に予期しないエラーが発生しました。{e}")


if __name__ == '__main__':
    # UserSettings の使用例です
    # config.json が同じディレクトリにあるか、有効なパスが指定されていることを前提とします。
    CONFIG_FILE_PATH = "config.json" # またはコンテキストから完全なパスを指定

    # テスト用にダミーの config.json が存在しない場合は作成します
    if not os.path.exists(CONFIG_FILE_PATH):
        print(f"警告: '{CONFIG_FILE_PATH}' が見つかりません。この例ではダミーは作成されません。")
        # 必要に応じて、スタンドアロンテスト用にここにサンプル config.json を作成できます。
    # 対象ファイルが見つかった場合
    else:
        print(f"--- '{CONFIG_FILE_PATH}' から設定を読み込み中 ---")
        my_settings = read_configfile(CONFIG_FILE_PATH)
        print(my_settings) # 非常に冗長になる可能性があります

        print("\n--- 特定の設定項目へのアクセス ---")
        narrator_model_path = "applicationSettings.CharacterSize"
        narrator_item = my_settings.get_setting_item(narrator_model_path)
        if narrator_item:
            print(f"設定: {narrator_item.description} (パス: {narrator_item.path})")
            print(f"  現在の値: {narrator_item.value}")
            print(f"  タイプ: {narrator_item.item_type}")
            print(f"  valueの型: {type(narrator_item.value)}")
            if narrator_item.options:
                print(f"  選択肢: {narrator_item.options}")
            if narrator_item.value_range:
                print(f"  範囲: {narrator_item.value_range}")
        else:
            print(f"警告: パス '{narrator_model_path}' の設定が見つかりません。")


        print("\n--- 特定の設定値の取得 ---")
        api_key = my_settings.get_setting_value("otherSettings.geminiAPIKey", "DEFAULT_KEY_IF_NOT_FOUND")
        print(f"Gemini API キー: {api_key}")

        print("\n--- 設定値の変更 ---")
        vv_speed_path = "audioSettings.voiceVox.readingSpeed"
        original_vv_speed = my_settings.get_setting_value(vv_speed_path)
        print(f"元の VoiceVox 速度: {original_vv_speed}")
        if my_settings.set_setting_value(vv_speed_path, 7): # 7 に設定してみる
            print(f"新しい VoiceVox 速度: {my_settings.get_setting_value(vv_speed_path)}")

        # 無効な値 (範囲外または誤った型) を設定してみる
        print("VoiceVox 速度を 15 (範囲外) に設定しようとしています:")
        my_settings.set_setting_value(vv_speed_path, 15)
        print(f"無効な試行後の VoiceVox 速度: {my_settings.get_setting_value(vv_speed_path)}")

        # textWindowSize (object 型) の変更
        text_win_path = "otherSettings.textWindowSize"
        original_text_win_size = my_settings.get_setting_value(text_win_path)
        print(f"元のテキストウィンドウサイズ: {original_text_win_size}")
        new_size = {"width": 900, "height": 700}
        if my_settings.set_setting_value(text_win_path, new_size):
            print(f"新しいテキストウィンドウサイズ: {my_settings.get_setting_value(text_win_path)}")

        # print("\n--- 新しいファイルへの設定の保存 (例) ---")
        # テスト中に元の config.json を上書きしないようにするため
        # TEST_OUTPUT_PATH = "config_modified.json"
        # write_configfile(my_settings, TEST_OUTPUT_PATH)
        # print(f"設定が '{TEST_OUTPUT_PATH}' に保存された可能性があります。ファイルを確認してください。")
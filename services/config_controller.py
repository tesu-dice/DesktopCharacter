import json
import os
import sys
from typing import Any, Dict, List, Optional
import logging
logger = logging.getLogger(__name__)
from pathlib import Path

# フリーズ時(exe実行)はexeファイルの隣、開発時はプロジェクトルートを指す
if getattr(sys, 'frozen', False):
    APP_DIR = Path(sys.executable).parent
else:
    APP_DIR = Path(__file__).resolve().parent.parent

print(f"APP_DIR = {APP_DIR}")


class SettingItem:
    """個々の設定項目を表します。"""
    def __init__(self,
                 name: str,
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
            name: 項目の名前
            path: 設定へのドット区切りパス (例: "audioSettings.windowsNarrator.voiceModel").
            value: 設定の現在の値.
            item_type: 設定の型 ("choice", "choice_with_func", "int", "string", "boolean", "object").
            raw_item_data: この設定項目に対応する元のJSONノードのデータ.
            description: 設定の人間可読な説明 (JSON の "name" フィールドから).
            options: 利用可能な選択肢のリスト ("choice" 型の場合).
            value_range: min/max 制約を指定する辞書.
                         "int" の場合: {"min": int, "max": int}.
                         "object" の場合: {"min": dict, "max": dict} (サブプロパティの制約).
        """
        self.name: str = name
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
        self._raw_config_data: Dict[str, Any] = {} # ロードしたJSON全体の構造を保持

    def _populate_settings_map(self, node: Dict[str, Any], current_path_parts: List[str]):
        """
        JSON データからノードを再帰的に解析して _settings_map を設定します。
        このメソッドは _raw_config_data を変更しません。
        """
        # Case 1: このノードがセクションである場合 ('type: "section"' と 'children' を持つ)
        if node.get("type") == "section" and "children" in node and isinstance(node["children"], dict):
            # このセクションの子を再帰的に処理する。
            # パスには "children" を含めない。
            for key, sub_node in node["children"].items():
                if isinstance(sub_node, dict):
                    self._populate_settings_map(sub_node, current_path_parts + [key])
            return # セクションノード自体は SettingItem ではない

        # Case 2: このノードが実際の設定項目である場合 ('value' を持つ)
        if "value" in node:
            path_str = ".".join(current_path_parts)
            if not path_str: # 有効な設定構造では発生しないはず
                return

            name = node.get("name", current_path_parts[-1]) # 'name' がない場合はキーを使用
            value = node["value"]
            item_type = node.get("type")
            options = node.get("options")
            value_range_data = {}
            if "min" in node:
                value_range_data["min"] = node["min"]
            if "max" in node:
                value_range_data["max"] = node["max"]

            # description は node の "description" を優先し、なければ name を使用
            description = node.get("description", name)

            # item_type のデフォルト値を設定
            if item_type is None:
                item_type = type(value).__name__ # Pythonの型名を使用

            self._settings_map[path_str] = SettingItem(
                name=name,
                path=path_str,
                value=value,
                item_type=item_type, # ここで item_type を使用
                raw_item_data=node, # _raw_config_data 内の実際のノードへの参照を保持
                description=description,
                options=options,
                value_range=value_range_data
            )
            return

        # Case 3: このノードが中間的な辞書である場合 (セクションでも設定項目でもない)
        # その直接の子を再帰的に処理する
        # 例: ApplicationSettings の直下にあるが、セクションでも設定項目でもない将来の構造
        # 現在の config.json では、このパスは通常、セクションまたは設定項目に直接つながる
        for key, sub_node in node.items():
            if isinstance(sub_node, dict):
                self._populate_settings_map(sub_node, current_path_parts + [key])

    def _populate_settings_map_with_merge(self, source_node: Dict[str, Any], current_path_parts: List[str]):
        """
        新しいJSONデータからノードを再帰的に解析し、既存の_settings_mapをマージ（上書き）します。
        このメソッドは_raw_config_dataの対応する'value'も更新します。
        """
        for key, sub_node in source_node.items():
            new_path_parts = current_path_parts + [key]
            path_str = ".".join(new_path_parts)

            if isinstance(sub_node, dict):
                # source_nodeがセクションまたは中間的な辞書の場合
                # ただし、デフォルト設定には存在しない新しいセクションや項目が
                # config.json にある場合は、ここでは処理しない
                # 既存のパスのみを更新するため、set_setting_valueを使用する
                if "value" in sub_node:
                    # これは設定項目なので、値を設定
                    self.set_setting_value(path_str, sub_node["value"])
                else:
                    # セクションまたは中間辞書なので、再帰的に処理
                    self._populate_settings_map_with_merge(sub_node, new_path_parts)
            else:
                # これは設定項目（値そのもの）なので、set_setting_valueを使用
                self.set_setting_value(path_str, sub_node)

    def load_from_dict(self, config_data: Dict[str, Any]):
        """辞書 (解析された JSON) から設定をロードします。"""
        self._raw_config_data = config_data.copy() # ロードしたJSONデータをコピーして保持
        self._settings_map.clear()
        self._populate_settings_map(self._raw_config_data, []) # 新しいヘルパーメソッドを呼び出す

    def get_setting_value(self, path: str, default: Any = None) -> Any:
        """パスによって設定の値を取得します。"""
        item = self._settings_map.get(path)
        if item:
            return item.value
        else:
            print(f"警告: パス '{path}' の設定が見つかりません。")
            logger.error(f"警告: パス '{path}' の設定が見つかりません。")
            return "参照エラー"

    def set_setting_value(self, path: str, new_value: Any) -> bool:
        """
        パスによって設定の値を設定し、基本的な検証を行います。
        成功した場合は True、それ以外の場合は False を返します。
        """
        item = self._settings_map.get(path) # SettingItem オブジェクトを取得
        if not item:
            # print(f"警告: パス '{path}' の設定が見つかりません。") # デバッグ用、マージ時にはスキップしたい場合がある
            return False

        # 基本的な型と制約の検証
        if item.item_type == "choice":
            if item.options and new_value not in item.options:
                print(f"警告: '{path}' の値 '{new_value}' は選択肢 {item.options} にありません。")
                return False
        
        if item.item_type == "choice_with_func":
            if new_value == "未選択" or new_value == "未設定":
                print("項目が未選択のためデフォルトの値を参照します。")
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
        elif item.item_type == "bool":
            if not isinstance(new_value, bool):
                print(f"警告: '{path}' の値 '{new_value}' はブール値ではありません。")
                return False
        elif item.item_type == "str":
            if not isinstance(new_value, str):
                print(f"警告: '{path}' の値 '{new_value}' は文字列ではありません。")
                return False
        # その他の型に対する検証はここに追加

        # SettingItem オブジェクトの値を更新
        item.value = new_value
        
        # _raw_config_data 内の対応する 'value' も更新する
        # item.raw_item_data は _raw_config_data 内の実際の辞書への参照なので、直接更新できる
        if 'value' in item.raw_item_data:
            item.raw_item_data['value'] = new_value

        return True # 成功した場合は True を返す

    def get_setting_item(self, path: str) -> Optional[SettingItem]:
        """パスによって完全な SettingItem オブジェクトを取得します。"""
        return self._settings_map.get(path)

    def to_dict_for_save_simple(self) -> Dict[str, Any]:
        """
        すべての設定をパスと値のみのネストされた辞書構造に変換し直します。
        """
        output_data = {}
        for path, item in self._settings_map.items():
            parts = path.split('.')
            current_level = output_data
            for i, part in enumerate(parts):
                if i == len(parts) - 1:
                    # 最後のパートは値
                    current_level[part] = item.value
                else:
                    # 途中は辞書
                    if part not in current_level:
                        current_level[part] = {}
                    current_level = current_level[part]
        return output_data

def read_configfile(filepath: str = "config.json") -> UserSettings:
    """
    JSON ファイルから設定を読み込み、UserSettings インスタンスを返します。
    """
    #設定データの初期化
    settings = UserSettings()
    default_data = get_default_data()
    settings.load_from_dict(default_data) # まずデフォルトデータをロード

    #設定ファイルを参照して値を変更
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            config_file_data = json.load(f)
        
        # config.json の内容を既存の設定にマージする
        # recursive_update_settingsのようなヘルパー関数を使用して、config_file_dataをsettingsに適用する
        settings._populate_settings_map_with_merge(config_file_data, [])

    except FileNotFoundError:
        logger.info(f"設定ファイル{filepath}が見つかりません。デフォルト設定を使用します。")
    except json.JSONDecodeError as e:
        logger.error(f"エラー: '{filepath}' から JSON をデコードできませんでした。{e}。デフォルト設定を使用します。")
    except Exception as e:
        logger.error(f"エラー: '{filepath}' の読み込み中に予期しないエラーが発生しました。{e}。デフォルト設定を使用します。")
    return settings


def write_configfile(usersettings: UserSettings, filepath: str = "config.json"):
    """
    UserSettings インスタンスから現在の設定を JSON ファイルに書き込みます。
    """
    try:
        data_to_save = usersettings.to_dict_for_save_simple()
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data_to_save, f, ensure_ascii=False, indent=2) # indent=2 で整形
        print(f"情報: 設定が '{filepath}' に正常に書き込まれました。")
    except Exception as e:
        print(f"エラー: '{filepath}' への書き込み中に予期しないエラーが発生しました。{e}")


def get_default_data() -> Dict[str, Any]:
    """
    origin_config.json を読み取った時と同じような形になるような
    デフォルトのJSON設定データを返します。
    """
    default_config = {
        "ApplicationSettings": {
            "name": "アプリケーション設定",
            "type": "section",
            "children": {
                "FontSize": {
                    "name": "フォントサイズ",
                    "description": "このアプリでのフォントサイズ",
                    "type": "int",
                    "min": 10,
                    "max": 50,
                    "value": 15
                },
                "ShowMetadatas":{
                    "name":"会話のメタデータを表示",
                    "description":"会話の際に利用したトークン数を表示します。",
                    "type":"bool",
                    "value":False
                },
                "CharacterImage":{
                    "name":"キャラクターの立ち絵",
                    "type":"section",
                    "children":{
                        "Folder": {
                            "name": "参照する立ち絵フォルダ",
                            "description": "キャラクター画像のフォルダを指定してください。",
                            "type": "choice_with_func",
                            "value": "CHARAT-MONO"
                        },
                        "Size": {
                            "name": "キャラクターサイズ",
                            "type": "int",
                            "value": 500
                        },
                        "Flip":{
                            "name": "キャラ画像の左右反転",
                            "type": "bool",
                            "value": False
                        },
                        "AlwaysOnTop": {
                            "name": "キャラ画像を常に最前面表示",
                            "description": "キャラ画像を常にほかウィンドウより前、最前面に表示します。",
                            "type": "bool",
                            "value": True
                        }
                    }
                },
                "ActiveSpeak": {
                    "name": "自発的な会話",
                    "description": "定期的にアプリ側から自動で話しかけます。",
                    "type": "section",
                    "children": {
                        "on/off": {
                            "name": "自発的な会話のon/off",
                            "type": "bool",
                            "value": True
                        },
                        "Time": {
                            "name": "会話の頻度（毎秒）",
                            "type": "int",
                            "value": 300
                        }
                    }
                },
                "Permission": {
                    "name": "アプリとAIの機能（情報アクセス許可）に関する設定項目",
                    "type": "section",
                    "children": {
                        "ReAct_response":{
                            "name" :"ReAct式の応答生成",
                            "description": "応答を生成するときに何度か繰り返し考えてから返事をします。AIサービスの利用量が増えます。",
                            "type": "bool",
                            "value": True
                        },
                        "get_current_time":{
                            "name": "現在時刻",
                            "type": "bool",
                            "value": True
                        },
                        "get_active_window": {
                            "name": "作業中のウィンドウ",
                            "description": "アクティブなウィンドウのソフト名、ウィンドウ名を取得・利用します",
                            "type": "bool",
                            "value": True
                        },
                        "get_playing_media": {
                            "name": "再生中のメディア",
                            "description": "再生中のメディアのタイトルを取得・利用します。",
                            "type": "bool",
                            "value": True
                        },
                        "get_user_activity_summary": {
                            "name": "ユーザログの活用",
                            "description": "アプリケーション利用中に収集したユーザ情報のログを利用します。",
                            "type": "bool",
                            "value": True
                        },
                        "UserActivityLog": {
                            "name": "ユーザーアクティビティログの記録とその閲覧",
                            "description": "許可された項目をアプリ内で記録・要約・保存して、必要に応じて利用します。\n個人情報を多大に含み、AIサービスの使用量が大きくなるためOllamaでの動作を推奨します。",
                            "type": "bool",
                            "value": True
                        }
                        
                    }
                }
            }
        },
        "LLMSettings": {
            "name": "会話AIについての設定",
            "type": "section",
            "children":{
                "Service": {
                    "name": "AIサービスの選択",
                    "type": "choice",
                    "value": "未選択",
                    "options": [
                        "geminiAPI",
                        "Ollama"
                    ]
                },
                "ActiveHistory":{
                    "name":"会話で使う履歴の数",
                    "description":"会話の際に覚えておく会話履歴の長さです。",
                    "type":"int",
                    "min": 1,
                    "max": 50,
                    "value": 10
                },
                "geminiAPI": {
                    "name": "Gemini",
                    "description": "Googleの提供しているAIサービスです。無料枠での利用では送信内容が学習に利用されます。",
                    "type": "section",
                    "children":{
                        "key": {
                            "name": "APIキー",
                            "description": "Google AI Studioで取得したAPIキーを入力してください。",
                            "type": "str",
                            "value": ""
                        },
                        "model":{
                            "name": "モデル",
                            "description": "会話で利用するモデルを選択してください。Textモデル以外も表示されています。\n2026年1月時点ではgemini-2.5-flash-lite推奨です。\n",
                            "type": "choice_with_func",
                            "value": "未選択"
                        }
                    }
                },
                "Ollama": {
                    "name": "Ollama",
                    "description": "中級車向け。\nローカルでのAI動作用サービスです。",
                    "type": "section",
                    "children":{
                        "URL": {
                            "name": "APIのURL",
                            "type": "str",
                            "value": "http://localhost:11434"
                        },
                        "model":{
                            "name": "モデル",
                            "type": "choice_with_func",
                            "value": "未選択"
                        }
                    }
                }
            }
        },
        "Speech2TextSettings" :{
            "name": "音声入力設定",
            "type": "section",
            "children": {
                "on/off":{
                    "name" : "音声入力のon/off" ,
                    "description": "ウェイクアップワードを検出したときに一時的に音声入力を使います。",
                    "type": "bool",
                    "value": True
                },
                "wakeupword": {
                    "name": "ウェイクアップワード",
                    "description": "音声認識を開始するときの合言葉を設定します。",
                    "type": "str",
                    "value": "もしもし"
                },
                "threshold": {
                    "name": "ウェイクアップワードのしきい値",
                    "description": "合言葉検出の際の判定をどの程度厳しくするかです。数値が大きいほど正確な発音が必要になります。",
                    "type": "int",
                    "min": 0,
                    "max": 100,
                    "value": 70
                }
            }
        },
        "VoiceSettings": {
            "name": "読み上げ音声設定",
            "type": "section",
            "children": {
                "engine": {
                    "name": "音声合成エンジン",
                    "type": "choice",
                    "value": "None",
                    "options": [
                        "None",
                        "windowsNarrator",
                        "VOICEVOX"
                    ]
                },
                "windowsNarrator": {
                    "name": "Windows Narrator 設定",
                    "type": "section",
                    "children": {
                        "Model": {
                            "name": "音声モデル",
                            "type": "choice_with_func",
                            "value": "Microsoft Sayaka - Japanese (Japan)",
                            "options": []
                        }
                    }
                },
                "VOICEVOX": {
                    "name": "VOICEVOX 設定",
                    "type": "section",
                    "children": {
                        "path": {
                            "type": "path",
                            "name": "VOICEVOXの起動パス",
                            "value": ""
                        },
                        "usegpu": {
                            "type": "bool",
                            "name": "音声合成にGPUを使用",
                            "value": True
                        },
                        "autorun": {
                            "type": "bool",
                            "name": "アプリ起動時にエンジンを自動で起動",
                            "value": False
                        },
                        "Model": {
                            "type": "choice_with_func",
                            "name": "音声モデル",
                            "value": "未選択",
                            "options": []
                        }
                    }
                }
            }
        }
    }

    return default_config


if __name__ == '__main__':
    pass






import os
import importlib
import inspect
import json
from typing import Dict, Any, List
import logging
logger = logging.getLogger(__name__)


#プログラムのインポート
if __name__ != "__main__":
    from services.config_controller import UserSettings
    from services.Event_Bus import EventBus
    from ai_tools.tool_base import BaseTool
else:
    #相対パスでプログラムのインポート
    import sys
    # 相対パスでプログラムのインポート
    # 現在のスクリプトのディレクトリを取得
    current_dir = os.path.dirname(os.path.abspath(__file__))
    # プロジェクトのルートディレクトリ（ここでは、現在のディレクトリの親ディレクトリを想定）
    # プロジェクトの構造に合わせて調整してください
    project_root = os.path.join(current_dir, '..')
    sys.path.append(project_root)

    # これで、project_rootからの相対パスでインポートできるようになります
    from services.config_controller import UserSettings
    from services.Event_Bus import EventBus
    from ai_tools.tool_base import BaseTool


class ToolExecutor:
    """
    AI_Toolsディレクトリ内のツールを動的に読み込み、実行を管理するクラス。
    """
    def __init__(self, bus: EventBus, setting: UserSettings, debug = -1):
        self.bus = bus
        self.setting = setting
        self.debug = debug
        self.tools: Dict[str, BaseTool] = self._discover_tools()
        self.tools_descriptions = self.init_tools_descriptions()
        if debug >= 0:
            indent = "  " * debug
            print(indent+"ToolExecutor.__init__() called.")
            print(self.get_tools_descriptions())
            for i in self.tools.keys():
                print(f"{indent}  {i} -> {self.execute_tool(i, {})}")

            

    def _discover_tools(self) -> Dict[str, BaseTool]:
        """AI_Toolsディレクトリからツールクラスを動的にインポートしてインスタンス化する。"""
        tools = {}
        tools_dir = os.path.dirname(__file__)

        for filename in os.listdir(tools_dir):
            # Pythonファイルで、特殊なファイルや自分自身を除外
            if filename.endswith(".py") and not filename.startswith("_") and filename not in ["tool_main.py", "tool_executor.py"]:
                module_name = f"ai_tools.{filename[:-3]}"
                try:
                    module = importlib.import_module(module_name)
                    # モジュール内のクラスを探索
                    for name, obj in inspect.getmembers(module, inspect.isclass):
                        # BaseToolを継承しており、BaseTool自身ではないクラスを探す
                        if issubclass(obj, BaseTool) and obj is not BaseTool:
                            instance = obj()
                            if instance.name in tools:
                                logger.warning(f"警告: ツール名 '{instance.name}' が重複しています。")
                                print(f"警告: ツール名 '{instance.name}' が重複しています。")
                                continue
                            tools[instance.name] = instance
                except Exception as e:
                    logger.error(f"エラー: モジュール '{module_name}' の読み込みに失敗しました: {e}")
                    print(f"エラー: モジュール '{module_name}' の読み込みに失敗しました: {e}")
        return tools

    def init_tools_descriptions(self) -> str:
        """AIのプロンプトに含めるための、全ツールの説明文を生成する。"""
        if not self.tools:
            return "利用可能なツールはありません。"
        descriptions = "【利用可能なツール】\n"
        for tool in self.tools.values():
            path = f"ApplicationSettings.Permission.{tool.name}"
            permisson = self.setting.get_setting_value(path)
            if permisson == True:
                args_str = json.dumps(tool.args_schema, ensure_ascii=False)
                descriptions += f"- {tool.name}: {tool.description} (引数: {args_str})\n"
            else:
                text = f"Toolの利用が制限されています。Tool名={tool.name}"
                #print(text)
                logger.info(text)
        return descriptions

    def get_tools_descriptions(self) -> str:
        return self.tools_descriptions

    def execute_tool(self, tool_name: str, args: Dict[str, Any]) -> str:
        """指定されたツール名と引数でツールを実行し、結果を返す。"""
        if tool_name not in self.tools:
            return f"エラー: ツール '{tool_name}' は存在しません。"

        tool = self.tools[tool_name]
        try:
            # TODO: argsがargs_schemaに適合しているかバリデーション
            return tool.execute(args)
        except Exception as e:
            # エラー内容をAIにフィードバックすることで、AIが自己修正する可能性がある
            return f"エラー: ツール '{tool_name}' の実行中に予期せぬエラーが発生しました: {e}"




if __name__ == "__main__":
    print(f"tools_main.pyの単体テストです。")
    bus = EventBus()
    setting = UserSettings()
    TE = ToolExecutor(setting=setting, bus=bus)
    print(TE.get_tools_descriptions())


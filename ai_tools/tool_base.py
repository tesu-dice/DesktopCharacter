from abc import ABC, abstractmethod
from typing import Dict, Any

class BaseTool(ABC):
    """AIが利用するツールのための抽象基底クラス。"""

    @property
    @abstractmethod
    def name(self) -> str:
        """
        ツールの名前。
        AIが `{"tool": "tool_name", ...}` の形式で呼び出す際に使用する識別子です。
        例: "get_current_time"
        """
        pass

    @property
    @abstractmethod
    def description(self) -> str:
        """
        ツールの機能に関する自然言語での説明。
        AIがいつ、どのようにこのツールを使うべきかを判断するために利用します。
        """
        pass

    @property
    @abstractmethod
    def args_schema(self) -> Dict[str, Any]:
        """
        ツールの引数を定義するJSON Schema。
        引数がない場合は {"type": "object", "properties": {}} を返します。
        """
        pass

    @abstractmethod
    def execute(self, args: Dict[str, Any]) -> str:
        """
        ツールを実行し、結果を文字列で返します。
        AIはこの文字列を「Observation」として認識します。
        """
        pass
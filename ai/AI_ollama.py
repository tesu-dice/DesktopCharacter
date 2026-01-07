import requests
import json
import base64
from io import BytesIO
from PIL import Image
import threading
import logging
logger = logging.getLogger(__name__)

# プログラムのインポート

# 画像を生成AIに渡す形に成形
def encode_image_to_base64(image_path: str):
    """画像ファイルをBase64文字列にエンコードする"""
    try:
        img = Image.open(image_path)
        
        # JPEGとして保存し、Base64エンコード
        buffered = BytesIO()
        img.save(buffered, format="JPEG")
        return base64.b64encode(buffered.getvalue()).decode('utf-8')
    except Exception as e:
        print(f"画像のエンコード中にエラーが発生しました: {e}")
        return None

# AI用のクラス
class ollamaAI():
    """
    Ollama APIを介してローカルLLMと会話するためのクラス。
    GeminiAPIクラスを参考にしてOllama向けに調整。
    """
    def __init__(self, usersetting, debug: int = -1): # UserSettingsの型ヒントを削除 (外部依存のため)
        # 初期化
        self.usersetting = usersetting
        self.debug = debug
        # 初期化読み取り
        # config_controllerが利用できない場合を考慮し、デフォルト値を設定
        self.ollama_api_base_url = self.usersetting.get_setting_value("LLMSettings.Ollama.URL") + "/api" \
                                    if hasattr(self.usersetting, 'get_setting_value') else "http://localhost:11434/api"
        self.model = self.usersetting.get_setting_value("LLMSettings.Ollama.model") \
                     if hasattr(self.usersetting, 'get_setting_value') else "llama3" # デフォルトモデルを設定

        if self.debug >= 0:
            indent = " " * self.debug
            print(f"{indent}ollamaAI.__init__() called.")
            print(f"{indent}Ollama API Base URL: {self.ollama_api_base_url}")
            print(f"{indent}Model: {self.model}")
            # テスト
            connected, message = self.test_connection()
            print(f"\n接続テスト結果: {connected}, メッセージ: {message}")
            if connected:
                # 利用可能なモデルの表示
                models = self.get_models()
                print(f"\n利用可能なOllamaモデル: {models}")
            self.debug = self.debug + 1 if self.debug >= 0 else -1

    # 入力文字列をAIに送信、返答を返す。画像パスが与えられれば画像も送信。
    def response(self, input_contents: list, image_path: str = None, debug: int = -1):
        # デバッグの設定
        debug = debug
        if debug >= 0:
            indent = " " * debug
            print(f"{indent}ollamaAI.py response() was called.")
            print(f"{indent}Input contents:")
            for i in input_contents:
                print(f"{indent}  {i}")
            print(f"{indent}Image path: '{image_path}'")
            debug += 1 # ネストされたデバッグ出力のためにインデントレベルを上げる

        # 会話履歴をOllama形式に変換
        ollama_messages = []
        for item in input_contents:
            #ロールの書き換え
            ollama_role = item["role"]
            if ollama_role == "model":
                ollama_role = "assistant"
            #コンテンツ (テキスト) の処理
            ollama_content = str(item["parts"][0])
            
            #デバック出力
            if debug >= 0:
                indent = " " * debug
                print(f"{indent}ollama形式に変換：{ollama_role},{ollama_content}")
            #メッセージの変換と追加
            ollama_messages.append({"role": ollama_role, "content": ollama_content})

        

        # 画像パスがあれば変換して最新のユーザー送信へ追加
        encoded_image = None
        if image_path:
            encoded_image = encode_image_to_base64(image_path)
            if encoded_image:
                ollama_messages[-1]["images"] = []
                ollama_messages[-1]["images"].append(encoded_image)
            else:
                if debug >= 0:
                    indent = " " * debug
                    print(f"{indent}AI_ollama.py ollamaAI.response() 画像を送信せずに会話を行います。")

        # 会話の設定
        url = self.ollama_api_base_url + "/chat"
        headers = {"Content-Type": "application/json"}
        stream = False # 生成データを一括で取得するか順次表示するか。今回は一括送信しか対応してない。
        payload = {
            "model": self.model,
            "messages": ollama_messages, # ここで正しく変換されたmessagesを使用
            "stream": stream
        }

        # 会話の処理
        response_text = ""
        result = {}
        try:
            response = requests.post(url, headers=headers, data=json.dumps(payload), timeout=60) # タイムアウトを追加
            response.raise_for_status() # HTTPエラー（4xx, 5xx）があれば例外を発生させる
            result = response.json()
            assistant_message = result.get("message", {})
            response_text = assistant_message.get('content', '').strip()

        except requests.exceptions.RequestException as e:
            print(f"エラーが発生しました: {e}")
            logger.error(f"AI_ollama.py ollamaAI.response() error: {e}")
            response_text = "エラーにより応答できませんでした。"
        except json.JSONDecodeError:
            print("Ollamaサーバーからの応答が不正なJSON形式です。")
            response_text = "Ollamaサーバーからの応答が不正です。"
        
        # Ollamaのレスポンスからトークン数を取得する
        prompt_tokens = result.get("prompt_eval_count", 0)
        completion_tokens = result.get("eval_count", 0)
        total_token_count = prompt_tokens + completion_tokens

        response_dict = {"text": response_text, "token_count": total_token_count}
        if debug >=0:
            indent = " " * debug
            print(f"{indent}response_dict: {response_dict}")
        return response_dict

    # 利用可能なOllamaモデルを配列で返す
    def get_models(self, debug: int = -1):
        if debug >= 0:
            print(f"  get_models() called to list Ollama models.")
        try:
            response = requests.get(f"{self.ollama_api_base_url}/tags", timeout=5)
            response.raise_for_status()
            models_data = response.json()
            names = [model["name"] for model in models_data.get("models", [])]
            if debug >= 0:
                print(f"  Available Ollama models: {names}")
            return names
        except requests.exceptions.ConnectionError:
            return "Ollamaサーバーに接続できません。Ollamaが実行されていることを確認してください。"
        except requests.exceptions.Timeout:
            return "Ollamaサーバーへの接続がタイムアウトしました。応答が遅いか、ネットワークに問題がある可能性があります。"
        except requests.exceptions.RequestException as e:
            return f"Ollamaモデルの取得中にエラーが発生しました: {e}"
        except json.JSONDecodeError:
            return "Ollamaサーバーからの応答が不正です。"

    # API接続のテストプログラム (Ollama向けに調整)
    def test_connection(self, debug: int = -1) -> tuple[bool, str]:
        debug = debug + 1 if debug >= 0 else -1
        indent = " " * debug

        if debug >= 0: print(f"{indent}ollamaAI.py test_connection: Attempting Ollama API connection test.")

        try:
            # Ollamaサーバーが起動しているかを確認するために/tagsエンドポイントを叩く
            response = requests.get(f"{self.ollama_api_base_url}/tags", timeout=5)
            response.raise_for_status() # HTTPエラー（4xx, 5xx）があれば例外を発生させる

            models_data = response.json()
            if "models" in models_data and len(models_data["models"]) > 0:
                if debug >= 0: print(f"{indent}ollamaAI.py test_connection: Ollama server connected and models found.")
                return True, f"Ollamaサーバーに接続し、利用可能なモデルが見つかりました ({len(models_data['models'])}個)。"
            else:
                if debug >= 0: print(f"{indent}ollamaAI.py test_connection: Ollama server connected but no models found.")
                return False, "Ollamaサーバーに接続できましたが、利用可能なモデルがありません。Ollamaでモデルをダウンロードしてください (例: ollama run llama3)。"

        except requests.exceptions.ConnectionError:
            if debug >= 0: print(f"{indent}ollamaAI.py test_connection: Connection error.")
            return False, f"Ollamaサーバーに接続できません。Ollamaが実行されているか、またはURL ({self.ollama_api_base_url}) が正しいか確認してください。"
        except requests.exceptions.Timeout:
            if debug >= 0: print(f"{indent}ollamaAI.py test_connection: Timeout error.")
            return False, f"Ollamaサーバーへの接続がタイムアウトしました。Ollamaサーバーの応答が遅いか、ネットワークに問題がある可能性があります。"
        except requests.exceptions.RequestException as e:
            if debug >= 0: print(f"{indent}ollamaAI.py test_connection: General request error: {e}")
            return False, f"Ollama API接続中に予期しないエラーが発生しました。\n詳細: {e}"
        except json.JSONDecodeError:
            if debug >= 0: print(f"{indent}ollamaAI.py test_connection: JSON decode error.")
            return False, "Ollamaサーバーからの応答が不正なJSON形式です。サーバーの状態を確認してください。"


if __name__ == "__main__":
    print("Ollama のプログラムは単体ではテストできません。")
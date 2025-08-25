"""
20250318 geminiのAPIをローカルでたたいて会話する

今後
VoiceVoxEngineから音声を引っ張ってくる。
立ち絵を表示してせりじゅと連携させる。
    現在はboidoll検討中、立ち絵素材は借りてくる

20250517
ライブラリが変わったりで仕様変更があったポイ？
https://ai.google.dev/gemini-api/docs/quickstart?hl=ja&lang=python
"""
#ライブラリの読み込み
import google.generativeai as genai
from google.api_core import exceptions
import threading
import logging
logger = logging.getLogger(__name__)

#プログラムの読み込み
from services.config_controller import UserSettings



class geminiAI():
        #初期化
        def __init__(self, usersetting:UserSettings, debug = -1):
            self.usersetting = usersetting

            yourAPIkey = usersetting.get_setting_value("LLMSettings.geminiAPI.key")#APIkeyの設定
            if debug >= 0:
                indent = "  " * debug
                print(f"{indent}geminiAPI.__init__() called.")
                print(f"{indent}yourAPIkey = {yourAPIkey}")
                debug = debug + 1 if debug >= 0 else -1

            
            genai.configure(api_key=yourAPIkey)

            
        

            

            # モデルを準備
            generation_config = {"temperature":1,
                                "top_p":0.95,
                                "top_k":40,
                                "response_mime_type":"text/plain"
            }#,
                    #            "max_output_tokens":5000
                    #            }
                                #
            safety_settings = [
                {
                    "category": "HARM_CATEGORY_HARASSMENT",
                    "threshold": "BLOCK_NONE"
                },
                {
                    "category": "HARM_CATEGORY_HATE_SPEECH",
                    "threshold": "BLOCK_NONE"
                },
                {
                    "category": "HARM_CATEGORY_SEXUALLY_EXPLICIT",
                    "threshold": "BLOCK_NONE"
                },
                {
                    "category": "HARM_CATEGORY_DANGEROUS_CONTENT",
                    "threshold": "BLOCK_NONE"
                }
            ]
            selected_model = usersetting.get_setting_value("LLMSettings.geminiAPI.model")
            self.model = genai.GenerativeModel(model_name = selected_model,#'gemini-2.0-pro-exp'上限ついた。5/15
                                        generation_config= generation_config,
                                        safety_settings=safety_settings)
        
        #googleAIの種類を羅列
        def get_models(self, debug = -1):
            #モデルの種類確認
            names = []
            if self.usersetting.get_setting_value("ApplicationSettings.geminiAPIkey") == "":
                return "APIキーが設定されていません。"
            for m in genai.list_models():
                if "generateContent" in m.supported_generation_methods:
                    name = m.name.split("/")[-1]
                    names.append(name)
            if debug >= 0:
                print(names)
            return names
        
        #入力文字列をAIに送信、返答を返す。
        def response(self, input_contents, debug=-1):
            if debug >= 0:
                indent = "  " * debug
                print(f"{indent}geminiAPI.py response() was called.")
                debug = debug + 1

            #送信するコンテンツの選別
            #会話とその記録
            response = self.model.generate_content(contents=input_contents)
            print(response.text)
            print(response.usage_metadata)
            response_dict = {"text": response.text, "token_count": response.usage_metadata.total_token_count}
            
            
            return response_dict
        
        
        #API接続のテストプログラム
        def test_connection(self, debug=-1) -> tuple[bool, str]:
            """
            Gemini APIへの接続テストを実行します。

            Returns:
                tuple[bool, str]: (成功/失敗を示すブール値, 詳細メッセージ) のタプル。
            """
            current_debug = debug + 1 if debug >= 0 else -1
            indent = "  " * current_debug

            # --- 実際にAPIを呼び出して接続を確認 ---
            # コストや速度を考慮し、最小限の処理で済む呼び出しを選ぶ
            # 例: generate_content に短いプロンプトと最小限の出力設定
            test_prompt = "[System] アプリケーション起動時のAPI接続テストです。応答内容は不要です。"
            timeout_seconds = 5 # APIからの応答を待つ最大秒数。環境に合わせて調整。

            if current_debug >= 0: print(f"{indent}geminiAPI.py test_connection: Attempting API call with timeout {timeout_seconds}s.")

            try:
                # generate_content を呼び出し、成功すれば接続OKとみなす
                # 最小限の応答を要求するため generation_config を設定
                response = self.model.generate_content(
                    test_prompt,
                    generation_config={"max_output_tokens": 1},
                    request_options={'timeout': timeout_seconds} # タイムアウト設定
                )

                # 応答オブジェクト自体が有効かを確認
                # generate_content の応答には candidates という属性が含まれることが多い
                if response and hasattr(response, 'candidates') and response.candidates:
                    if current_debug >= 0: print(f"{indent}geminiAPI.py test_connection: API call successful, candidates found.")
                    return True, "Gemini APIへの接続および基本的な応答生成に成功しました。"
                else:
                    # API呼び出し自体は成功したが、応答内容が予期しない形式の場合
                    if current_debug >= 0: print(f"{indent}geminiAPI.py test_connection: API call successful but no valid candidates. Response: {response}")
                    return False, f"Gemini APIから応答がありましたが、内容が不正です。APIキーや設定を確認してください。\n詳細: {response}"

            # APIライブラリが投げる可能性のある具体的な例外を捕捉
            except exceptions.DeadlineExceeded:
                if current_debug >= 0: print(f"{indent}geminiAPI.py test_connection: Timeout error.")
                return False, f"Gemini APIへの接続がタイムアウトしました ({timeout_seconds}秒)。ネットワークまたはAPIサービスに問題がある可能性があります。"
            except exceptions.ResourceExhausted:
                if current_debug >= 0: print(f"{indent}geminiAPI.py test_connection: Resource Exhausted error.")
                return False, f"Gemini APIの利用クォータまたはレート制限に達しました。時間をおいて再試行するか、Google Cloud Platformの利用状況を確認してください。"
            except exceptions.InvalidArgument as e:
                if current_debug >= 0: print(f"{indent}geminiAPI.py test_connection: Invalid Argument error: {e}")
                # APIキーが無効な場合などもこの例外に含まれる可能性がある
                return False, f"Gemini APIリクエストが無効です。APIキーやモデル名、設定を確認してください。\n詳細: {e}"
            except exceptions.InternalServerError as e:
                if current_debug >= 0: print(f"{indent}geminiAPI.py test_connection: Internal Server error: {e}")
                return False, f"Gemini API内部サーバーエラーが発生しました。時間をおいて再試行してください。\n詳細: {e}"
            except exceptions.ServiceUnavailable as e:
                if current_debug >= 0: print(f"{indent}geminiAPI.py test_connection: Service Unavailable error: {e}")
                return False, f"Gemini APIサービスが一時的に利用できません。時間をおいて再試行してください。\n詳細: {e}"
            except Exception as e:
                # その他の予期しないエラー
                if current_debug >= 0: print(f"{indent}geminiAPI.py test_connection: Unexpected error: {e}")
                return False, f"予期しないGemini API接続エラーが発生しました。\n詳細: {e}"


#プログラムの依存関係上テストできない
if __name__ == "__main__":
    pass
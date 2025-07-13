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

#プログラムの読み込み
import talk_VoiceVoxEngine
import talk_WindowsNarratorManager 
from config_controller import UserSettings



class geminiAI():
        #初期化
        def __init__(self, usersetting:UserSettings, app, debug = -1):
            self.app = app
            self.usersetting = usersetting

            yourAPIkey = usersetting.get_setting_value("ApplicationSettings.geminiAPIkey")#APIkeyの設定
            if debug >= 0:
                indent = "  " * debug
                print(f"{indent}geminiAPI.__init__() called.")
                print(f"{indent}yourAPIkey = {yourAPIkey}")
                debug = debug + 1 if debug >= 0 else -1

            
            genai.configure(api_key=yourAPIkey)

            #会話設定
            base_prompt =   "あなたはユーザのPC上で動作するキャラクターです。以下の応答規則、キャラクター設定に従って受け答えをしてください。\n" \
                            "#応答規則\n" \
                            "セリフはキャラクターとして会話するように応答し、文章量は最大で3文程度としてください。\n" \
                            "立ち絵ファイル名は下に示されたのみとし、セリフと合わせて適切なものを選択してください。\n" \
                            "###応答例（立ち絵ファイル名：セリフ）\n"\
                            "平穏.png：おはようございます。\n" \
                            "笑顔.tiff：今日もいい天気ですね。\n" \
                            "期待.png：今日も一日頑張りましょう。\n"\
                            "###立ち絵ファイル名\n"
            
            base_prompt += self.load_imgs(dir_name=usersetting.get_setting_value("ApplicationSettings.CharacterImage.Folder"))+"\n#キャラクター設定\n"
            f= open("Character_setting.txt", encoding="utf-8")
            Character_set_text=""
            for line in f:
                line.strip("\n")
                Character_set_text +=line
            
            f.close()
        

            

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
            selected_model = usersetting.get_setting_value("ApplicationSettings.Model")
            self.model = genai.GenerativeModel(model_name = selected_model,#'gemini-2.0-pro-exp'上限ついた。5/15
                                        generation_config= generation_config,
                                        safety_settings=safety_settings)
            #会話履歴を作成
            self.init_prompt= [{"role": "user", "parts":[base_prompt + Character_set_text]},({"role": "model", "parts":["了解しました。"]})]
            
        #キャラクター画像を読み込み、AIへ指示書として返す。
        def load_imgs(self, dir_name):
            import os
            dir_path = f"立ち絵/{dir_name}"
            files = os.listdir(dir_path)
            text = str(files)
            return text
            
        
        
        #googleAIの種類を羅列
        def get_models(self, debug = -1):
            #モデルの種類確認
            names = []
            for m in genai.list_models():
                if "generateContent" in m.supported_generation_methods:
                    name = m.name.split("/")[-1]
                    names.append(name)
            if debug >= 0:
                print(names)
            return names
        
        #入力文字列をAIに送信、返答を返す。
        def response(self, input_text, debug=-1):
            if debug >= 0:
                indent = "  " * debug
                print(f"{indent}geminiAPI.py response() was called.",input_text)
                if(input_text == "<<show histroy>>"):
                    self.view_conversation_log()
                
                print(f"{indent}self.app.TalkHistory = {self.app.TalkHistory}")
                debug = debug + 1

            input_content = [{"role": "user", "parts":[input_text]}]
            #送信するコンテンツの選別
            if len(self.app.TalkHistory) > 7:
                past_contets = self.init_prompt + self.app.TalkHistory[-5:]
            else:
                past_contets = self.init_prompt + self.app.TalkHistory
            contents = past_contets + input_content
            
            #会話とその記録
            response = self.model.generate_content(contents=contents)
            print(response.text)
            print(response.usage_metadata)
            
            #
            #threadを使って音声処理を並列化
            thread = threading.Thread(target=self.Reflecting_textResponsestoUI, args=(response.text, debug))
            thread.daemon = True
            thread.start()
            print("thread main keeped")
            return response.text, response.usage_metadata.total_token_count

        
        # 会話ログ表示用の関数
        def view_conversation_log(self):
            print("\n--- Full Conversation Log ---")
            if not self.app.TalkHistory:
                print("  Log is empty.")
            for message in self.app.TalkHistory:
                role = message.get("role", "Unknown Role")
                content = ""
                if "parts" in message and message["parts"]:
                    # partsがリストであることを想定し、最初の要素のテキスト部分を取得
                    if isinstance(message["parts"][0], str):
                        content = message["parts"][0]
                    elif hasattr(message["parts"][0], 'text'): # Partオブジェクトの場合など
                        content = message["parts"][0].text
                
                # 表示を見やすくするために、内容を100文字に丸め、改行をスペースに置換
                display_content = content.replace('\n', ' ').replace('\r', '')
                if len(display_content) > 100:
                    display_content = display_content[:97] + "..."
                print(f"  {role}: \"{display_content}\"")
            print("-----------------------------\n")
        
        
        def Reflecting_textResponsestoUI(self, texts, debug=-1):
            #テキストを読み上げモード別に読み上げる
            mode = self.usersetting.get_setting_value("VoiceSettings.engine")
            for text in texts.split("\n"):
                if text == "":
                    break
                if text.find("："):
                    self.app.ui.update_character_image(text.split("：")[0])
                    text = text.split("：")[-1]

                
                if(debug >= 0):
                    indent = "  " * debug
                    print(f"{indent}geminiAPI.py speech_text() was called.",mode, text)
                    debug = debug + 1
                if(mode == "None"):
                    return
                elif(mode == "WindowsNarrator"):
                    model_description = self.usersetting.get_setting_value("VoiceSettings.windowsNarrator.Model")
                    talk_WindowsNarratorManager.text_to_speech(text, model_description, debug=debug)
                elif(mode == "VOICEVOX"):
                    chosen_value = self.usersetting.get_setting_value("VoiceSettings.VOICEVOX.Model")
                    id = str(chosen_value).split("=")[-1]
                    talk_VoiceVoxEngine.text_to_speech(text, int(id), debug=debug)
                else:
                    self.app.show_message_box("エラー", f"音声読み上げにおいて対応していない読み上げモードが選択されています。{mode}")
                    
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
            timeout_seconds = 15 # APIからの応答を待つ最大秒数。環境に合わせて調整。

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
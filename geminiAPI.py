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
import threading

#プログラムの読み込み
import talk_VoiceVoxEngine as talkVoice


class geminiAI():
        #初期化
        def __init__(self):
            #APIkeyの設定
            f = open("myAPI.txt", "r")
            yourAPIkey = f.readline()
            f.close()
            genai.configure(api_key=yourAPIkey)

            #会話設定
            img_names_text = self.load_imgs()
            f= open("Character_setting.txt", encoding="utf-8")
            setting=""
            for line in f:
                line.strip("\n")
                setting +=line
            setting += img_names_text
            f.close()
            # print(setting)
            # input()

            

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
            self.model = genai.GenerativeModel(model_name = 'gemini-2.0-flash',#'gemini-2.0-pro-exp'上限ついた。5/15
                                        generation_config= generation_config,
                                        safety_settings=safety_settings)

            self.history = [{"role": "user", "parts":[setting]}, {"role": "model", "parts":["了解しました。"]}]
            

        def load_imgs(self):
            import os
            dir_path = "立ち絵/"
            files = os.listdir(dir_path)
            text = "また、表情の種類は次のようになっています。"+ str(files)
            return text
            
        
        
        #googleAIの種類を羅列
        def check_models(self):
            #モデルの種類確認
            for m in genai.list_models():
                if "generateContent" in m.supported_generation_methods:
                    print(m.name)
        
        #入力文字列をAIに送信、返答を返す。
        def response(self, input_text):
            input_content = [{"role": "user", "parts":[input_text]}]
            #送信するコンテンツの選別
            if len(self.history) > 7:
                past_contets = self.history[:1] + self.history[-5:]
            else:
                past_contets = self.history
            contents = past_contets + input_content
            
            #会話とその記録
            response = self.model.generate_content(contents=contents)
            self.history.append({"role": "user", "parts":[input_text]})
            self.history.append({"role": "model", "parts":[response.text]})



            print(response.text)
            print(response.usage_metadata)
            
            #会話処理
            if (response.text.find("：")):
                parts = response.text.split("：", 1)  # "："で分割、最大分割回数1
                #threadを使って音声処理を並列化
                thread = threading.Thread(target=talkVoice.text_to_speech, args=(parts[1],))
                thread.daemon = True
                thread.start()
                print("thread main keeped")
                return parts[0], parts[1]
            else:
                 return response.text
        

        # 会話ログ表示用の関数
        def view_conversation_log(self):
            print("\n--- Full Conversation Log ---")
            if not self.history:
                print("  Log is empty.")
            for message in self.history:
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

        


if __name__ == "__main__":
     ai = geminiAI()
     print(ai.response(input_text="こんにちは、これはAPI接続テストです。接続できていますか。"))

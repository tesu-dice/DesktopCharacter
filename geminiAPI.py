"""
20250318 geminiのAPIをローカルでたたいて会話する

今後
VoiceVoxEngineから音声を引っ張ってくる。
立ち絵を表示してせりじゅと連携させる。
    現在はboidoll検討中、立ち絵素材は借りてくる
"""
import pathlib
import textwrap
import google.generativeai as genai
import talk_VoiceVoxEngine as talkVoice



#APIkeyの設定
f = open("myAPI.txt", "r")
yourAPIkey = f.readline()
f.close()
genai.configure(api_key=yourAPIkey)

#会話設定
f= open("Character_setting.txt", encoding="utf-8")
setting=""
for line in f:
    line.strip("\n")
    setting +=line
# print(setting)
# input()

#モデルの種類確認
for m in genai.list_models():
    if "generateContent" in m.supported_generation_methods:
        print(m.name)

# モデルを準備
generation_config = {"temperature":1,
                     "top_p":0.95,
                     "top_k":40,
                     "response_mime_type":"text/plain"
                     }#, "max_output tokens=500":500}
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
model = genai.GenerativeModel(model_name = 'gemini-2.0-pro-exp',
                              generation_config= generation_config,
                              safety_settings=safety_settings)

chat_session = model.start_chat(history=[
    {"role":"user","parts":[setting]},
    {"role":"model","parts":["了解しました。"]}
    ])


while 1:
    input_text = input(":")
    response = chat_session.send_message(input_text)
    print(response.text)
    talkVoice.text_to_speech(response.text)
    print("history")
    print(chat_session.history)

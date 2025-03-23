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
genai.configure(api_key=yourAPIkey)

#モデルの種類確認
for m in genai.list_models():
    if "generateContent" in m.supported_generation_methods:
        print(m.name)

# モデルを準備
model = genai.GenerativeModel('gemini-2.0-flash')

task = " あなたは、コンピュータ上のサポートAIです。以下の会話に対しての返答を行ってください。また、その際、電話で話すような形でのみ返答し、文章量は3行程度にしてください。"

response = model.generate_content(task+"こんにちは、あなたにはどんなことができるのですか。")
print(response.text)
talkVoice.text_to_speech(response.text)

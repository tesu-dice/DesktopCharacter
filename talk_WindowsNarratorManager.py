"""
windowsのデフォルト機能のナレータを使った会話についての管理




"""

import win32com.client

#利用可能な音声モデル名を一覧で取得
def get_SAPIVoice_names():
    voice_names = []
    try:
        speakers = win32com.client.Dispatch("SAPI.SpObjectTokenCategory")
        speakers.SetID(r"HKEY_LOCAL_MACHINE\SOFTWARE\Microsoft\Speech_OneCore\Voices", False)
    except Exception as e:
        speakers.SetID(r"HKEY_LOCAL_MACHINE\SOFTWARE\Microsoft\Speech\Voices", False)

    speakers = speakers.EnumerateTokens()
    for model in speakers:
        voice_names.append(model.GetAttribute("Name"))
    return voice_names



#テキストをモデル名、速度に合わせて読み上げ。
def text_to_speech(text, voice_name = "sayaka", rate= 0):
    print(f"windowsNarrator.py text_to_speech(), text={text}, voice_name={voice_name}, rate-{rate}")
    sapi = win32com.client.Dispatch("SAPI.SpVoice")
    try:
        #読み上げモデル取得
        try:
            speakers = win32com.client.Dispatch("SAPI.SpObjectTokenCategory")
            speakers.SetID(r"HKEY_LOCAL_MACHINE\SOFTWARE\Microsoft\Speech_OneCore\Voices", False)
        except Exception as e:
            speakers.SetID(r"HKEY_LOCAL_MACHINE\SOFTWARE\Microsoft\Speech\Voices", False)
        #読み上げモデルの検索
        speakers = speakers.EnumerateTokens()
        model = None
        for model in speakers:
            #print(model.GetAttribute("Name"))
            if voice_name == model.GetAttribute("Name"):
                break
        sapi.Voice = model
        sapi.Rate = rate
        sapi.Speak(text)
    except Exception as e:
        print(f"SAPIを使った読み上げでエラーが発生しました。\n{ e }")
    

    
        




if __name__ == "__main__":
    models = get_SAPIVoice_names()
    print(models)
    for s in models :
        text_to_speech("こんにちは、これはSAPIを使った音声読み上げのテストです。", s )
    

    

        
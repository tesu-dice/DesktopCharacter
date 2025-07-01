"""
windowsのデフォルト機能のナレータを使った会話についての管理




"""

import win32com.client
import win32api
import locale


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
        # print(model.GetAttribute("Language"))
        # print(model.GetAttribute("Name"))
        # print(model.GetAttribute("Gender"))
        # print(model.GetDescription())
        voice_names.append(model.GetDescription())
    return voice_names





#テキストをモデル名、速度に合わせて読み上げ。
#読み上げる文字列、会話に使用するモデル名、読み上げ速度(-10.0~10.0)
def text_to_speech(text, model_description, rate= 2.0, debug=-1):
    if debug >= 0:
        indent = "  " * debug
        print(f"{indent}windowsNarrator.py text_to_speech() called.")
        print(f"{indent}text = {text}")
        print(f"{indent}model_description = {model_description}")
    #print(f"windowsNarrator.py text_to_speech(), text={text}, {model_description}, rate={rate}")
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
            if model_description == model.GetDescription():
                break

        sapi.Voice = model
        sapi.Rate = rate
        sapi.Speak(text)

    except Exception as e:
        print(f"SAPIを使った読み上げでエラーが発生しました。\n{ e }")
    


if __name__ == "__main__":
    models = get_SAPIVoice_names()
    print(models)
    for i in models:
        print(i)
        text_to_speech("Hello. 読み上げテストです。", i)
    """
    #2chのyoutubeShortsぽい読み上げテスト
    text_to_speech("とある会社の駐車場で休憩していた２人がいました。", models[0])
    text_to_speech("タバコ吸ってもよろしいですか。", models[2])
    text_to_speech("どうぞ。ところで１日に何本くらいお吸いに？", models[1])
    text_to_speech("ふた箱くらいですね。", models[2])
    text_to_speech("喫煙年数はどれくらいですか？", models[1])
    text_to_speech("30年くらいですね。", models[2])
    text_to_speech("なるほど。あそこにベンツが停まってますね。", models[1])
    text_to_speech("停まってますね。", models[2])
    text_to_speech("もしあなたが煙草を吸わなければ、", models[1])
    text_to_speech("ちくわ大明神", models[3])
    text_to_speech("あれくらい買えたんですよ。", models[1])
    text_to_speech("あれは私のベンツですけど。", models[2])
    text_to_speech("誰だ今の", models[1])
    """

        
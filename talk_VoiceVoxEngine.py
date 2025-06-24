"""
参考
https://note.com/key410/n/n1bf0e797da61#cda96522-a335-4d39-81ee-8c155b3d98af
https://note.com/__olender/n/n49f1d07c2c7d
https://haon-code.com/simple_zundamon/

"""

import requests
import json
import time
import re
import simpleaudio
import subprocess
def start_server(path):
    try:
        result = None
        result = subprocess.Popen(path)
    except Exception as e:
        print("VoiceVoxEngineの実行に失敗しました。")
        print(e)
    return result



def audio_query(text, speaker, max_retry):
    # 音声合成用のクエリを作成する
    query_payload = {"text": text, "speaker": speaker}
    for query_i in range(max_retry):
        try:
            r = requests.post("http://localhost:50021/audio_query", 
                            params=query_payload, timeout=(10.0, 300.0))
            if r.status_code == 200:
                query_data = r.json()
                break
                
            else:
                raise ConnectionError("リトライ回数が上限に到達しました。 audio_query : ", "/", text[:30], r.text)
        except requests.exceptions.ConnectionError as e:
            print("VOICEVOXサーバーにアクセスできませんでした。")
            print(e)
            return None

    return query_data
def synthesis(speaker, query_data,max_retry):
    synth_payload = {"speaker": speaker}
    for synth_i in range(max_retry):
        try:
            r = requests.post("http://localhost:50021/synthesis", params=synth_payload, 
                            data=json.dumps(query_data), timeout=(10.0, 300.0))
            if r.status_code == 200:
                #音声ファイルを返す
                return r.content
            else:
                raise ConnectionError("音声エラー：リトライ回数が上限に到達しました。 synthesis : ", r)
        except requests.exceptions.ConnectionError as e:
            print("VOICEVOXサーバーにアクセスできませんでした。")
            print(e)
            return None
            

def text_to_speech(texts, speaker=68, max_retry=20, debug=False):
    if not texts: # FalseやNone、空文字列をまとめてチェック
        texts = "ちょっと、通信状態が悪いかも？"
    
    # ★改善点1: re.splitで末尾に空文字列が生まれることがあるため、フィルタリングする
    sentences = [s for s in re.split("(?<=[！。？])", texts) if s.strip()]
    
    if not sentences: # 分割した結果、文章がなければ何もしない
        return

    # デバッグモードの場合、文章を上書き
    if debug:
        sentences = ["デバッグモードで読み上げのテストをしています。"]

    play_obj = None
    
    for sentence in sentences:
        # ★改善点2: 前の音声が再生中なら、終わるまで待つ
        if play_obj and play_obj.is_playing():
            play_obj.wait_done()
            
        # audio_queryとsynthesis
        try:
            query_data = audio_query(sentence, speaker, max_retry)
            if not query_data:
                print(f"警告: audio_queryに失敗しました。テキスト: {sentence}")
                continue # 次の文章へ

            voice_data = synthesis(speaker, query_data, max_retry)
            if not voice_data:
                print(f"警告: synthesisに失敗しました。テキスト: {sentence}")
                continue # 次の文章へ

        except Exception as e:
            print(f"エラー: 音声生成中に例外が発生しました。テキスト: {sentence}, エラー: {e}")
            continue

        # ★改善点3: 音声データが正常に取得できた場合のみ再生
        # 再生処理
        try:
            wave_obj = simpleaudio.WaveObject(voice_data, 1, 2, 24000)
            play_obj = wave_obj.play()
        except Exception as e:
            print(f"エラー: 音声の再生に失敗しました。エラー: {e}")

    # ★改善点4: 最後の文章が再生し終わるのを待つ
    if play_obj and play_obj.is_playing():
        play_obj.wait_done()

#VoiceVoxのローカルサーバーから音声モデルとそのIDを取得して配列で返す。
def get_speakers():
    url = "http://localhost:50021/speakers"  # VOICEVOX APIのエンドポイント
    try:
        response = requests.get(url)
        speakers_list = []
        if response.status_code == 200:
            speakers = response.json()
            for speaker in speakers:
                name = speaker['name']
                style_names = [style['name'] for style in speaker['styles']]
                style_ids = [style['id'] for style in speaker['styles']]
                for style_id, style_name in zip(style_ids, style_names):
                    #print(f"Speaker: {name}, {style_name} id: {style_id}")
                    speakers_list.append(f"{name}({style_name})={style_id}")
                
        else:
            print(f"Error: {response.status_code}")
            speakers_list = ["","VOICEVOXのローカルサーバーにアクセスできませんでした。"]
    except requests.exceptions.RequestException as e:
        print(f"Error: {e}")
        speakers_list = ["","VOICEVOXのローカルサーバーにアクセスできませんでした。"]
    
    return speakers_list



if __name__ == "__main__":
    get_speakers()
    text_to_speech("テスト、テスト。こんにちは、これはvoicevoxの音声テストです。誰がしゃべってるでしょうか？",
                   89
                   )

"""
# 概要
main.pyとAI関連のプログラムの中間についての管理
AIサービス管理のプログラムをインポート、AIクラスを生成して返す。

# 管理するもの  
- LLMとの会話履歴  
- 会話のサービスとして何を使うのか  
- 会話のモデルとして何を使うのか  
- 接続テストとその結果

# 各AIのクラスが持っておくべき関数  
- __init__(setting:UserSettings, debug = -1)  
AIの初期化関数  

- response(input_contents: dict, debug: int = -1) -> dict{"text": response_text, "token_count": total_token_count}
ここで管理した会話履歴を送信してAIからの返答を送ってもらう関数  

- get_models() -> list  
利用するAIサービスから使えるAIモデルを文字列のリストで返してもらう。

- test_connection(debug: int = -1) -> tuple[bool, str]  
AIサービスおよびそのモデルと接続できているのかをテストする関数  
True/Falseで接続、strで詳細なメッセージを返す。



"""
import os
import threading
import logging
logger = logging.getLogger(__name__)

#プログラム間でのやりとり
from ai import AI_geminiAPI
from ai import AI_ollama
from services.Event_Bus import EventBus
from services.config_controller import UserSettings



class AI_Manager():
    def __init__(self, _Bus:EventBus, _setting:UserSettings, TalkHistory = [], debug = -1):
        #初期化
        self.bus = _Bus
        self.usersetting = _setting
        self.history = TalkHistory
        self.debug = debug

        #設定を読み取った初期化
        self.active_history_num = self.usersetting.get_setting_value("LLMSettings.ActiveHistory")*2 #送信と返答の2組セット
        self.LLM_Service = self.usersetting.get_setting_value("LLMSettings.Service")
        if self.LLM_Service == "未選択":
            self.ai = None
        elif self.LLM_Service == "geminiAPI":
            self.ai = AI_geminiAPI.geminiAI(usersetting=self.usersetting, debug=debug)
        elif self.LLM_Service == "Ollama":
            self.ai = AI_ollama.ollamaAI(usersetting=self.usersetting, debug=debug)
        else:
            self.ai = None
            print("--- error ---\nAI_main.py AI_Manager.__init__ で適切なサービスを見つけることができませんでした。")

        #会話設定や履歴の管理
        #会話設定
        base_prompt =   "あなたはユーザのPC上で動作するキャラクターです。以下の応答規則、キャラクター設定に従って受け答えをしてください。\n" \
                            "# 応答規則\n" \
                            "セリフはキャラクターとして会話するように応答し、文章量は最大で3文程度としてください。\n" \
                            "立ち絵ファイル名は下に示されたのみとし、セリフと合わせて適切なものを選択してください。\n" \
                            "## 応答例（立ち絵ファイル名：セリフ）\n"\
                            "平穏.png：おはようございます。\n" \
                            "笑顔.tiff：今日もいい天気ですね。\n" \
                            "期待.png：今日も一日頑張りましょう。\n"\
                            "# 立ち絵ファイル名\n"
            
        base_prompt += self.load_imgs(dir_name=self.usersetting.get_setting_value("ApplicationSettings.CharacterImage.Folder"))+"\n#キャラクター設定\n"
        f= open("Character_setting.txt", encoding="utf-8")
        Character_set_text=""
        for line in f:
            line.strip("\n")
            Character_set_text +=line
        f.close()
        self.init_prompt= [{"role": "user", "parts":[base_prompt + Character_set_text]},({"role": "model", "parts":["了解しました。"]})]









        #デバックのテキスト表示
        if debug >= 0:
            indent = "  " * debug
            print(f"{indent}AI_Manager.__init__() called.")
            print(f"{indent}LLMService = {self.LLM_Service}")
            print(f"{indent}TalkHistory = {self.history}")
            debug = debug + 1

    def add_talkhistory(self,type, text, debug = -1):
        newhistory = {"role": f"{type}", "parts":[text]}
        self.history.append(newhistory)
        
        #会話が長くなりすぎたら削除
        max_history_length = 100
        if len(self.history) > max_history_length:
            self.history = self.history[-max_history_length:]

        #トークウィンドウがあればテキストを追加
        self.bus.publish("Req_AddTalkLog", newhistory)
        

    # キャラクター画像を読み込み、AIへ指示書として返す。
    def load_imgs(self, dir_name):
        # geminiAPI.py と同じロジック
        dir_path = f"立ち絵/{dir_name}"
        if not os.path.exists(dir_path):
            print(f"警告: 立ち絵フォルダ '{dir_path}' が見つかりません。")
            return "立ち絵ファイルが見つかりません。"
        files = os.listdir(dir_path)
        text = str(files)
        return text


#AI各プログラムへの仲介関数
    #LLM個別のプログラムからモデル名を配列で受け取る。
    def get_models(self):
        if self.ai is None:
            return ["AIサービスが選択されていません。"]
        return self.ai.get_models()
    
    def response(self, input_text: str, input_img_path: str = None, debug: int = -1):
        #AIの指定がなかった場合
        if self.ai is None:
            return {"text": "AIサービスが選択されていません。", "token_count": 0}
        
        #送信する会話履歴の処理
        self.add_talkhistory("user", input_text, debug)
        if len(self.history) > self.active_history_num:
            past_contents = self.history[-self.active_history_num:]
        else:
            past_contents = self.history
        #返答の生成
        response = self.ai.response(input_contents=self.init_prompt + past_contents, debug = debug)
        self.add_talkhistory("model", response["text"], debug)
        print(response)

        #イベント発行
        self.bus.publish("AIGenerateMessage", response["text"])
        



        
    
    def test_connection(self, debug: int = -1):
        if self.ai is None:
            return (False, "AIサービスが選択されていません。")
        if debug >= 0:
            indent = "  " * debug
            print(f"{indent}AI_main.py test_connection() called.")
            print(f"{indent}{self.LLM_Service}の接続テストを行います。")
            debug = debug + 1

        return self.ai.test_connection(debug)

if __name__ == "__main__":
    print("AI_main.pyは単体テストできません。")
    pass
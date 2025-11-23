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
from services.UserDataLogger import get_userhourlog



class AI_Manager():
    def __init__(self, bus: EventBus, setting: UserSettings, TalkHistory=[], debug=-1):
        self.bus = bus
        self.setting = setting
        self.history = TalkHistory
        self.AI_client = None # AIクライアントのインスタンスを保持

        self.bus.subscribe("SettingsUpdated", self.on_settings_updated)

        self._initialize_client()
        self.on_settings_updated(setting)

        

    def _initialize_client(self, debug=-1):
        self.active_history_num = self.setting.get_setting_value("LLMSettings.ActiveHistory") *2 -1
        """設定に基づいてAIクライアントを初期化または再初期化します。"""
        selected_service = self.setting.get_setting_value("LLMSettings.Service")
        logger.info(f"AIクライアントを初期化しています... サービス: {selected_service}")

        if selected_service == "geminiAPI":
            self.AI_client = AI_geminiAPI.geminiAI(self.setting, debug=debug)
        elif selected_service == "Ollama":
            self.AI_client = AI_ollama.ollamaAI(self.setting, debug=debug)
        else:
            self.AI_client = None
            logger.warning(f"選択されたAIサービス '{selected_service}' はサポートされていないため、AIクライアントは設定されませんでした。")

    def on_settings_updated(self, new_settings: UserSettings):
        """設定が更新されたときに呼び出され、AIクライアントを再初期化します。"""
        logger.info("AIマネージャーの設定を更新します...")
        self.setting = new_settings
        self._initialize_client()
        logger.info("AIマネージャーの設定更新が完了しました。")

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
            
        base_prompt += self.load_imgs(dir_name=self.setting.get_setting_value("ApplicationSettings.CharacterImage.Folder"))+"\n#キャラクター設定\n"
        f= open("Character_setting.txt", encoding="utf-8")
        Character_set_text=""
        for line in f:
            line.strip("\n")
            Character_set_text +=line
        f.close()
        self.init_prompt= [{"role": "user", "parts":[base_prompt + Character_set_text]},({"role": "model", "parts":["了解しました。"]})]


    def add_talkhistory(self, input_dict:dict, debug = -1):
        #会話履歴のリストに会話の辞書を追加する
        # dict{"role", "parts", "img", "token_count"}

        self.history.append(input_dict)
        
        #会話が長くなりすぎたら削除
        max_history_length = 100
        if len(self.history) > max_history_length:
            self.history = self.history[-max_history_length:]
        

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
        if self.AI_client is None:
            return ["AIサービスが選択されていません。"]
        return self.AI_client.get_models()
    
    def response(self, input_dict : dict, debug: int = -1):
        #AIの指定がなかった場合
        if self.AI_client is None:
            output_dict = {"role": "model", "parts":["AIサービスが選択されていません。"], "token_count": 0}
            #イベント発行
            self.bus.publish("AIGenerateMessage", output_dict, debug=debug)
            return
        
        #送信する会話履歴の処理
        self.add_talkhistory(input_dict, debug)
        if len(self.history) > self.active_history_num:
            past_contents = self.history[-self.active_history_num:]
        else:
            past_contents = self.history
        #返答の生成
        input_contents = self.init_prompt + past_contents
        #ユーザアクティビティのログおよび活用機能
        if self.setting.get_setting_value("ApplicationSettings.Permission.UserActivityLog"):
            _input = input_dict["parts"]
            _text =     f"あなたはアシスタントAIです。以下の例に従って出力を行い、ユーザの入力を確認して必要なユーザの活動記録について示してください。\
                        記録は日と時刻に依存して作成されています。もしも必要がない場合は「None」と返してください。\n\
                        # 応答の例：\n\
                        2025年11月10日の要約が欲しいとき->2025-11-10\n\
                        2025年11月10日18時の要約が欲しいとき->2025-11-10 18\n\
                        # ユーザの入力\n\
                        {_input}"
            _requesttext = str(self.response_onetime(_text))
            #要求に応じてコンテキストの追加
            addtext = get_userhourlog(time_str=_requesttext)
            #生成用のコンテキスト更新
            input_contents[-1]["parts"][0] += f"\n# ユーザ記録の参照情報\n{addtext}"
            print();print(_text);print()
            print();print(_requesttext);print()
            print();print(addtext);print()

            print();print(input_contents[-1]["parts"])


            
        response = self.AI_client.response(input_contents=input_contents, debug = debug)
        output_dict = {"role": "model", "parts":[response["text"]], "token_count": response["token_count"]}
        self.add_talkhistory(output_dict, debug)
        #イベント発行
        self.bus.publish("AIGenerateMessage", output_dict, debug=debug)
        
    def response_onetime(self, text, debug = -1):
        """
        LLMに入力された文字列を一度だけ応答してもらう。返すのも単純な文字列。
        """
        if self.AI_client is None:
            output_dict = {"role": "model", "parts":["AIサービスが選択されていません。"], "token_count": 0}
            #イベント発行
            self.bus.publish("AI.response_onetime end", output_dict, debug=debug)
            return

        #返答の生成
        input = [{"role": "user", "parts":[text]}]
        
        response = self.AI_client.response(input_contents=input, debug = debug)
        output_dict = {"role": "model", "parts":response["text"], "token_count": response["token_count"]}
        #self.bus.publish("AI.response_onetime end", output_dict, debug=debug)
        return output_dict["parts"]




        
    
    def test_connection(self, debug: int = -1):
        if self.AI_client is None:
            return (False, "AIサービスが選択されていません。")
        if debug >= 0:
            indent = "  " * debug
            print(f"{indent}AI_main.py test_connection() called.")
            print(f"{indent}{self.LLM_Service}の接続テストを行います。")
            debug = debug + 1

        return self.AI_client.test_connection(debug)

if __name__ == "__main__":
    print("AI_main.pyは単体テストできません。")
    pass
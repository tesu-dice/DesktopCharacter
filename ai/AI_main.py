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
import re
import json
import threading
import logging
logger = logging.getLogger(__name__)

#プログラム間でのやりとり
from ai import AI_geminiAPI
from ai import AI_ollama
from services.Event_Bus import EventBus
from services.config_controller import UserSettings
from ai_tools.tools_main import ToolExecutor


class AI_Manager():
    def __init__(self, bus: EventBus, setting: UserSettings, TalkHistory=[], debug=-1):
        self.bus = bus
        self.setting = setting
        self.history = TalkHistory
        self.AI_client = None # AIクライアントのインスタンスを保持
        self.tool_executor = ToolExecutor(self.bus, self.setting, debug=debug)
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
                            "期待.png：今日も一日頑張りましょう。\n"
                            
        #立ち絵ファイル名を追記
        self.character_img_list = self.load_imgs(dir_name=self.setting.get_setting_value("ApplicationSettings.CharacterImage.Folder"))
        base_prompt += f"# 立ち絵ファイル名\n{self.character_img_list}\n#キャラクター設定\n"
        f= open("Character_setting.txt", encoding="utf-8")
        self.Character_set_text=""
        for line in f:
            line.strip("\n")
            self.Character_set_text +=line
        f.close()
        self.init_prompt= [{"role": "user", "parts":[base_prompt + self.Character_set_text]},{"role": "model", "parts":["了解しました。"]}]


    def add_talkhistory(self, input_dict:dict, debug = -1):
        #会話履歴のリストに会話の辞書を追加する
        # dict{"role", "parts", "img", "token_count"}
        
        # APIに渡す会話履歴には "role" と "parts" のみ含める
        history_entry = {
            "role": input_dict["role"],
            "parts": input_dict["parts"]
        }
        self.history.append(history_entry)
        
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
            output_dict = {"role": "model", "parts":["AIサービスが選択されていません。"],  "token_count": 0}
            #イベント発行
            self.bus.publish("AIGenerateMessage", output_dict, debug=debug)
            return
        
        #送信する会話履歴の処理
        self.add_talkhistory(input_dict, debug)
        if len(self.history) > self.active_history_num:
            past_contents = self.history[-self.active_history_num:]
        else:
            past_contents = self.history

        
        #react動作を行う場合
        react_planing_is_on = self.setting.get_setting_value("ApplicationSettings.Permission.ReAct_response")
        if react_planing_is_on:
            react_resopnse = self.react_planing()
            character_response = self.character_response(base_dict=react_resopnse)
            total_token_count = react_resopnse["token_count"] + character_response["token_count"]

            result = {"role": "model", "parts": character_response["parts"], "token_count": total_token_count}
            self.add_talkhistory(result)
            self.bus.publish("AIGenerateMessage", result, debug=debug)
        
        #通常の応答
        else:
            #返答の生成
            input_contents = self.init_prompt + past_contents

            response = self.AI_client.response(input_contents=input_contents, debug = debug)
            output_dict = {"role": "model", "parts":[response["text"]], "token_count": response["token_count"]}
            self.add_talkhistory(output_dict, debug)
            #イベント発行
            self.bus.publish("AIGenerateMessage", output_dict, debug=debug)

    # react動作によって情報収集や方針決めを行う-> dict
    def react_planing(self,  max_react_steps: int = 10, debug: int = -1):
        if self.AI_client is None:
            self.bus.publish("AIGenerateMessage", {"role": "model", "parts": ["AIサービス未選択"], "token_count": 0})
            return

        def log_debug(message, level=-1):
            if debug > -1:
                print(f"{'  ' * level}{message}")

        # 準備
        tool_descriptions = self.tool_executor.get_tools_descriptions()#AIの利用するツールの情報一覧
        log_debug(tool_descriptions, level=debug)
        tool_use_sample =   {
                            "tools":[
                                {
                                    "name": "get_active_window",
                                    "arguments": {}
                                },
                                {
                                    "name": "get_current_time",
                                    "arguments": {}
                                },
                                {
                                    "name": "get_playing_media",
                                    "arguments": {}
                                }
                            ]
                            }
        tool_use_sample_text = json.dumps(tool_use_sample, indent=2)
        response_sample =   {
                                "response": "ユーザーはVisual Studio Codeで、sample.pyというファイルを開いているようです。現在時刻はyyyy年mm月dd日HH時MM分です。どのような手伝いをしましょうか？"
                            }
        response_sample_text = json.dumps(response_sample, ensure_ascii=False, indent=2)
        
        history_context = "\n".join([f"{m['role']}: {m['parts'][0]}" for m in self.history[-self.active_history_num:]])#ここまでの会話履歴を文章として成形
        tool_infos = ""# ツールの実行結果を格納する用
        react_history = [] #ツール利用などでの応答を与えるための履歴情報
       

        total_token_count = 0

        for step in range(max_react_steps):
            log_debug(f"--- LLM loop {step + 1} ---", 1)

            # Thought
            thought_content =[]
            thought_prompt = (f"あなたは思考専門のユニットです。ユーザーの入力を受け、応答に必要なツールを選択してJSON形式で応答を出力してください。\n"
                              f"必要な情報がそろったと判断した場合は、応答の際に必要な情報および応答の方針についてのみ出力してください。\n"
                              f"# 【現在の会話履歴】\n{history_context}\n\n"
                              f"# 【現在ツールを利用して取得している情報】\n{tool_infos}\n"
                              f"# 【利用可能なツール】\n{tool_descriptions}\n"
                              f"# 【ツール利用応答文の例】\n{tool_use_sample_text}\n"
                              f"# 【応答文の例】\n{response_sample_text}"
                              )
            thought_content.append({"role": "user", "parts": [thought_prompt]})
            if react_history:
                thought_content.extend(react_history)# リストの後ろにリストを付けるからextend
            resp = self.AI_client.response(thought_content)
            thought_text = resp["text"]
            total_token_count += resp["token_count"]
            react_history.append({"role": "model", "parts": [thought_text]})
            log_debug(f"Thought prompt:\n {thought_content}", level=debug)
            log_debug(f"Thought response:\n {thought_text}", level=1)

            # Action
            # JSON形式（{ ... }）が含まれているか正規表現で検索
            json_match = re.search(r'(\{.*\})', thought_text, re.DOTALL)
            llm_is_thinking = False
            if json_match :
                llm_is_thinking = True

            # Action: json部分を抽出
            if llm_is_thinking:
                try:
                    json_str = json_match.group(1)
                    data = json.loads(json_str)
                    tools_list = data.get("tools", [])
                    response = data.get("response", "")

                    for tool_call in tools_list:
                        t_name = tool_call.get("name")
                        t_args = tool_call.get("arguments", {})
                        obs = self.tool_executor.execute_tool(t_name, t_args)
                        log_debug(f"{t_name}: {obs}", level=debug)
                        # 履歴に結果を追加してループ継続
                        tool_infos += f"{t_name}: {obs}\n"

                    # ツールの利用結果をReAct用の会話履歴に追加
                    tooluse_content = {"role": "user", "parts": [f"ツール利用の結果\n{tool_infos}"]}
                    react_history.append(tooluse_content)



                    # responseを出力
                    if response != "":
                        log_debug("response json find.", level=debug)
                        output_dict = {"role": "model", "parts": [response], "token_count": total_token_count}
                        return output_dict

                except Exception as e:
                    logger.warning(f"Action Error: {e}")
                    log_debug(f"Action Error: {e}", level=debug)

            # 解析：Final Answer のチェック
            else:
                log_debug("llm thinking end.", level=debug)
                output_dict = {"role": "model", "parts": [thought_text], "token_count": total_token_count}
                return output_dict

        # 失敗時
        logger.warning(f"AI_main.py react_planing() failed. thought_text={thought_text}")
        output_dict = {"role": "model", "parts": [thought_text], "token_count": total_token_count}
        return output_dict

    # base_dictの文章をキャラクター設定に沿った文章に変更して返す
    def character_response(self, base_dict : dict, debug: int = -1):
        if debug != -1:
            indent = "  " * debug
            print(f"{indent}AI_main.py character_response() called.")
        history_context = "\n".join([f"{m['role']}: {m['parts'][0]}" for m in self.history[-self.active_history_num:]])#ここまでの会話履歴を文章として成形
        character_base_prompt = (f"あなたはユーザのPC上で動作するキャラクターです。「応答方針」に示す文章をキャラクター設定に従った受け答えに変更してください。\n"+
                                f"これまでの会話履歴および回答例は「これまでの文章」を参照してください。"
                                f"# 応答規則\n"+
                                f"- セリフはキャラクターとして会話するように応答し、文章量は最大で3文程度としてください。\n"+
                                f"- 立ち絵ファイル名は別項目で示されたもののみとし、セリフと合わせて適切なものを選択してください。\n"+
                                f"## 応答例（立ち絵ファイル名：セリフ）\n"+
                                f"平穏.png：おはようございます。\n"+
                                f"笑顔.jpg：今日もいい天気ですね。\n"+ 
                                f"期待.png：今日も一日頑張りましょう。\n"+
                                f"# キャラクター設定\n"+
                                f"{self.Character_set_text}\n"+
                                f"# 立ち絵ファイル一覧\n"+
                                f"{self.character_img_list}\n"+
                                f"# これまでの文章\n"+
                                f"{history_context}"+
                                f"# 応答方針\n"+
                                f"{base_dict['parts']}"
                                )
        response = self.AI_client.response(input_contents=[{"role": "user", "parts": [character_base_prompt]}], debug=debug)
        result = {"role": "model", "parts": [response["text"]], "token_count": response["token_count"]}
        return result 
    #RAG情報アリでの応答関数(基本はresponseのコピー)
    def response_withRAG(self, input_dict : dict, rag_info:str, debug: int = -1,):
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
        rag_contents = [{"role": "model", "parts":[f"# 応答の参考情報\n{rag_info}"]}]
        input_contents = self.init_prompt + rag_contents + past_contents 

        response = self.AI_client.response(input_contents=input_contents, debug = debug)
        output_dict = {"role": "model", "parts":[response["text"]], "token_count": response["token_count"]}
        self.add_talkhistory(output_dict, debug)
        #イベント発行
        self.bus.publish("AIGenerateMessage", output_dict, debug=debug)

    
    #入力された一文の会話辞書からRAGを使う際のデータを選択する。将来的にはリクエストを複数strのlist形式で生成するかも？
    def make_rag_request(self, input_dict : dict, debug: int = -1):
        #AIの指定がなかった場合
        if self.AI_client is None:
            output_dict = {"role": "model", "parts":["AIサービスが選択されていません。"]}
            #イベント発行
            self.bus.publish("AIGenerateMessage", output_dict, debug=debug)
            m = "error", "AIサービス", "AI(LLM)サービスが選択されていません。\nもしくはAIサービスへの接続に失敗しました。"
            self.bus.publish("Req_PopUpMessage", m)
            return
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
            self.bus.publish("Req_RAGInfo", _requesttext)
        else:
            logger.warning("RAG機能がONでないのに会話時にRAGの利用が要求されました。")
    

    #入力文字列に対して文字列形式で返す。一問一答用
    def response_onetime(self, text, debug = -1):
        """
        LLMに入力された文字列を一度だけ応答してもらう。返すのも単純な文字列。
        """
        if self.AI_client is None:
            output_dict = {"role": "model", "parts":["AIサービスが選択されていません。"]}
            #イベント発行
            self.bus.publish("AI.response_onetime end", output_dict, debug=debug)
            return
        if text == "":
            return ""
        

        #返答の生成
        input = [{"role": "user", "parts":[text]}]
        
        response = self.AI_client.response(input_contents=input, debug = debug)
        output_dict = {"role": "model", "parts":response["text"], "token_count": response["token_count"]}
        #self.bus.publish("AI.response_onetime end", output_dict, debug=debug)
        return str(output_dict["parts"])




        
    
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
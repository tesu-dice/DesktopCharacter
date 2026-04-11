import os
import threading
import logging
import json
import re
logger = logging.getLogger(__name__)

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
        self.AI_client = None
        self.tool_executor = ToolExecutor(self.bus, self.setting, debug=debug)
        self.char_settings = ""

        self.bus.subscribe("SettingsUpdated", self.on_settings_updated)
        self._initialize_client()
        self.on_settings_updated(setting)

    def _initialize_client(self, debug=-1):
        self.active_history_num = self.setting.get_setting_value("LLMSettings.ActiveHistory") * 2 - 1
        selected_service = self.setting.get_setting_value("LLMSettings.Service")
        logger.info(f"AIクライアントを初期化中: {selected_service}")

        if selected_service == "geminiAPI":
            self.AI_client = AI_geminiAPI.geminiAI(self.setting, debug=debug)
        elif selected_service == "Ollama":
            self.AI_client = AI_ollama.ollamaAI(self.setting, debug=debug)
        else:
            self.AI_client = None

    def on_settings_updated(self, new_settings: UserSettings):
        logger.info("AIマネージャーの設定を更新します...")
        self.setting = new_settings
        self._initialize_client()
        
        try:
            with open("Character_setting.txt", "r", encoding="utf-8") as f:
                self.char_settings = f.read()
        except FileNotFoundError:
            logger.warning("Character_setting.txt が見つかりません。")
            self.char_settings = "親切なアシスタント"

    def add_talkhistory(self, input_dict: dict, debug=-1):
        history_entry = {"role": input_dict["role"], "parts": input_dict["parts"]}
        self.history.append(history_entry)
        if len(self.history) > 100:
            self.history = self.history[-100:]

    def load_imgs(self, dir_name):
        dir_path = f"立ち絵/{dir_name}"
        if not os.path.exists(dir_path):
            return "立ち絵ファイルが見つかりません。"
        return str(os.listdir(dir_path))

    def response(self, input_dict: dict, debug: int = 1):
        print("response() called")
        if self.AI_client is None:
            self.bus.publish("AIGenerateMessage", {"role": "model", "parts": ["AIサービス未選択"], "token_count": 0})
            return

        def log_debug(message, level=0):
            print(f"{'  ' * level}{message}")

        # 準備
        tool_descriptions = self.tool_executor.get_tools_descriptions()#AIの利用するツールの情報一覧
        #print(tool_descriptions)
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
                                "response": "ユーザーはVisual Studio Codeで、main.pyというファイルを開いているようです。現在時刻は2026年03月29日16時21分です。どのような手伝いをしましょうか？"
                            }
        response_sample_text = json.dumps(response_sample, ensure_ascii=False, indent=2)
        char_img_list = self.load_imgs(self.setting.get_setting_value("ApplicationSettings.CharacterImage.Folder"))#キャラ画像一覧
        self.add_talkhistory(input_dict, debug)## history参照の前に追加
        history_context = "\n".join([f"{m['role']}: {m['parts'][0]}" for m in self.history[-self.active_history_num:]])#ここまでの会話履歴を文章として成形
        tool_infos = ""# ツールの実行結果を格納する用
        react_history = [] #ツール利用などでの応答を与えるための履歴情報
       

        total_token_count = 0
        max_react_steps = 5

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
            log_debug(f"Thought prompt:\n {thought_content}", 2)
            log_debug(f"Thought response:\n {thought_text}", 2)

            # Action
            # JSON形式（{ ... }）が含まれているか正規表現で検索
            json_match = re.search(r'(\{.*\})', thought_text, re.DOTALL)
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
                        log_debug(f"{t_name}: {obs}", 2)
                        # 履歴に結果を追加してループ継続
                        tool_infos += f"{t_name}: {obs}\n"

                    # ツールの利用結果をReAct用の会話履歴に追加
                    tooluse_content = {"role": "user", "parts": [f"ツール利用の結果\n{tool_infos}"]}
                    react_history.append(tooluse_content)



                    # responseを出力
                    if response != "":
                        print("response json find.")
                        output_dict = {"role": "model", "parts": [response], "token_count": total_token_count}
                        self.add_talkhistory(output_dict)
                        self.bus.publish("AIGenerateMessage", output_dict)
                        return 

                except Exception as e:
                    log_debug(f"Action Error: {e}", 2)

            # 解析：Final Answer のチェック
            else:
                print("llm thinking end")
                output_dict = {"role": "model", "parts": [thought_text], "token_count": total_token_count}
                self.add_talkhistory(output_dict)
                self.bus.publish("AIGenerateMessage", output_dict)
                return

            # フォールバック
            #history_context += f"\nSystem: 形式エラー。もう一度やり直してください。"

        # 失敗時
        self.bus.publish("AIGenerateMessage", {"role": "model", "parts": ["考えがまとまりませんでした。"], "token_count": total_token_count})


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


    def get_models(self):
        return self.AI_client.get_models() if self.AI_client else ["未接続"]

    def test_connection(self, debug=-1):
        return self.AI_client.test_connection(debug) if self.AI_client else (False, "未設定")
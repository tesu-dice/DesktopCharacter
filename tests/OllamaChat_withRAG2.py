"""
Ollama APIを使用して、RAG（Retrieval-Augmented Generation）を実装したチャットアプリケーション。
DuckDuckGo検索を利用して情報を取得し、ユーザーの質問に対して応答します。

変更点:
- ウィンドウタイトルからLLMで直接、多角的な検索クエリを複数生成するように仕様変更。
"""

import tkinter as tk
from tkinter import scrolledtext
import requests
import json
import threading

# duckduckgo-searchライブラリをインポート
from duckduckgo_search import DDGS

# --- Ollama APIの設定 ---
OLLAMA_API_URL = "http://localhost:11434/api/generate"
MODEL_NAME = "gemma3:4b" # ご利用のモデル名に合わせて変更してください (例: "llama3", "mistral")

# --- NEW: LLMを使ってウィンドウタイトルから直接、検索クエリを生成する関数 ---
def generate_search_queries_from_title(window_title, text_area):
    """
    Ollamaを使用してウィンドウタイトルを分析し、直接、多様な検索クエリを生成します。
    """
    text_area.insert(tk.END, "AI: ウィンドウタイトルを分析し、検索クエリを生成中...\n")
    text_area.see(tk.END)
    
    prompt = (
        f"あなたは優秀な検索エンジニアです。以下のウィンドウタイトルを分析し、その内容を多角的に調査するための効果的なWeb検索クエリを5つ作成してください。\n"
        f"クエリは、タイトルに含まれる固有名詞、トピックの概要、具体的な質問、関連技術や背景情報など、様々な観点から生成してください。\n"
        f"出力は検索クエリのみをカンマ区切りにしてください。余計な説明は不要です。\n\n"
        f"タイトル: '{window_title}'\n\n"
        f"出力:"
    )
    payload = {"model": MODEL_NAME, "prompt": prompt, "stream": False}
    try:
        response = requests.post(OLLAMA_API_URL, json=payload, timeout=60)
        response.raise_for_status()
        data = json.loads(response.text)
        # レスポンスからクエリを抽出・整形
        queries = [q.strip() for q in data.get("response", "").strip().split(',') if q.strip()]
        print(f"生成された検索クエリ: {queries[:5]}")
        text_area.delete("end-2l linestart", "end-1l")
        return queries[:5] # 最大5件に制限
    except requests.exceptions.RequestException as e:
        print(f"検索クエリ生成エラー: {e}")
        text_area.delete("end-2l linestart", "end-1l")
        text_area.insert(tk.END, f"エラー: 検索クエリの生成に失敗しました。\n")
        return []

# --- DuckDuckGo検索を実行する関数 ---
def duckduckgo_search_tool(query, num_results=2):
    """
    DuckDuckGo Searchを使用して指定された件数の検索結果を取得します。
    """
    print(f"DuckDuckGo検索 ({num_results}件): {query}")
    search_snippets = []
    try:
        with DDGS(timeout=10) as ddgs:
            results = list(ddgs.text(query, region='jp-jp', max_results=num_results))
            for item in results:
                search_snippets.append(f"タイトル: {item.get('title', 'N/A')}\nURL: {item.get('href', 'N/A')}\nスニペット: {item.get('body', 'N/A')}\n")
                print(f"タイトル: {item.get('title', 'N/A')}")
        return "\n".join(search_snippets) if search_snippets else "関連する情報は見つかりませんでした。"
    except Exception as e:
        print(f"DuckDuckGo検索エラー: {e}")
        return "検索に失敗しました。"

# --- RAGプロンプト作成関数 ---
def create_rag_prompt(user_message, active_window_title, search_results):
    context_info = f"ユーザーは現在「{active_window_title}」に関する作業をしています。" if active_window_title else ""
    return (
        f"あなたはAIアシスタントです。提供された情報に基づき、ユーザーへ返答をしてください。\n\n"
        f"### 作業コンテキスト\n{context_info}\n\n"
        f"### インターネットからの参考情報\n{search_results}\n\n"
        f"### ユーザーのメッセージ\n{user_message}\n\n"
        f"上記の情報を考慮して答えてください。"
    )

# --- MODIFIED: 新しい「直接クエリ生成」方式を実装したメイン処理関数 ---
def send_to_ollama_direct_query(user_message, active_window_title, text_area):
    """
    ウィンドウタイトルから直接検索クエリを生成し、Web検索を実行して応答を生成します。
    """
    if not active_window_title:
        text_area.insert(tk.END, "AI: 検索を行うにはアクティブウィンドウのタイトル入力が必要です。\n\n")
        text_area.see(tk.END)
        return

    # ステップ1: ウィンドウタイトルから直接検索クエリを生成
    search_queries = generate_search_queries_from_title(active_window_title, text_area)
    
    if not search_queries:
        text_area.insert(tk.END, "AI: ウィンドウタイトルから検索クエリを生成できませんでした。\n\n")
        text_area.see(tk.END)
        return

    all_search_results = []

    # ステップ2: 生成された各クエリで検索を実行
    text_area.insert(tk.END, "AI: 生成されたクエリでWeb検索を実行中...\n")
    text_area.see(tk.END)
    for query in search_queries:
        text_area.insert(tk.END, f"AI: 検索中: {query}\n")
        text_area.see(tk.END)
        # 1クエリあたり2件の結果を取得
        search_result = duckduckgo_search_tool(query, num_results=2)
        print(f"検索結果 ({query}): {search_result}")
        all_search_results.append(f"--- 検索クエリ '{query}' の結果 ---\n{search_result}")
        text_area.delete("end-2l linestart", "end-1l") # 進捗表示を削除
    text_area.delete("end-2l linestart", "end-1l") # 「検索中...」を削除


    search_results_context = "\n\n".join(all_search_results)

    # ステップ3: RAGプロンプトを作成し、Ollamaに応答を生成させる
    text_area.insert(tk.END, "AI: 応答を生成中...\n")
    text_area.see(tk.END)
    rag_prompt = create_rag_prompt(user_message, active_window_title, search_results_context)
    payload = {"model": MODEL_NAME, "prompt": rag_prompt, "stream": False}

    try:
        response = requests.post(OLLAMA_API_URL, json=payload, timeout=300)
        response.raise_for_status()
        data = json.loads(response.text)
        full_response = data.get("response", "応答がありませんでした。")
        text_area.delete("end-2l linestart", "end-1l")
        text_area.insert(tk.END, f"AI: {full_response.strip()}\n\n")
    except requests.exceptions.RequestException as e:
        text_area.delete("end-2l linestart", "end-1l")
        text_area.insert(tk.END, f"エラー: Ollama APIへの接続に失敗しました。\n詳細: {e}\n\n")
    finally:
        text_area.see(tk.END)

# --- GUIアプリケーションのメインクラス ---
class ChatApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Ollama RAG (直接クエリ生成)")
        self.geometry("800x600")
        self.create_widgets()

    def create_widgets(self):
        main_frame = tk.Frame(self, padx=10, pady=10)
        main_frame.pack(fill=tk.BOTH, expand=True)
        self.chat_log = scrolledtext.ScrolledText(main_frame, wrap=tk.WORD, state=tk.NORMAL, font=("Helvetica", 12))
        self.chat_log.pack(fill=tk.BOTH, expand=True, pady=(0, 10))
        input_frame = tk.Frame(main_frame)
        input_frame.pack(fill=tk.X, pady=(0, 10))
        tk.Label(input_frame, text="あなたの質問:", font=("Helvetica", 10)).grid(row=0, column=0, sticky="w", padx=5, pady=2)
        self.user_msg_entry = tk.Entry(input_frame, width=40, font=("Helvetica", 12))
        self.user_msg_entry.grid(row=1, column=0, sticky="ew", padx=5)
        self.user_msg_entry.focus_set()
        tk.Label(input_frame, text="アクティブウィンドウのタイトル (検索コンテキスト):", font=("Helvetica", 10)).grid(row=0, column=1, sticky="w", padx=5, pady=2)
        self.window_title_entry = tk.Entry(input_frame, width=40, font=("Helvetica", 12))
        self.window_title_entry.grid(row=1, column=1, sticky="ew", padx=5)
        send_button = tk.Button(input_frame, text="送信", command=self.on_send_click, font=("Helvetica", 12), bg="#4CAF50", fg="white")
        send_button.grid(row=1, column=2, padx=5, pady=5, sticky="e")
        input_frame.grid_columnconfigure(0, weight=1)
        input_frame.grid_columnconfigure(1, weight=1)
        self.user_msg_entry.bind("<Return>", self.on_send_click)
        self.window_title_entry.bind("<Return>", self.on_send_click)

    def on_send_click(self, event=None):
        user_msg = self.user_msg_entry.get()
        window_title = self.window_title_entry.get()
        if not user_msg: return
        self.chat_log.insert(tk.END, f"あなた: {user_msg}\n")
        self.user_msg_entry.delete(0, tk.END)
        # 修正した関数を呼び出す
        api_thread = threading.Thread(target=send_to_ollama_direct_query, args=(user_msg, window_title, self.chat_log))
        api_thread.daemon = True
        api_thread.start()

# --- アプリケーションの実行 ---
if __name__ == "__main__":
    app = ChatApp()
    app.mainloop()
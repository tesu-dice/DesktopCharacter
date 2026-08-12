# アプリケーション開発ガイドライン

このドキュメントは、デスクトップキャラクターアプリケーションに新しい機能を追加する際の基本的な考え方と手順をまとめたものです。プロジェクトのコード品質とメンテナンス性を高く保つために、このガイドラインに沿って開発を進めてください。

## 1. 新機能の基本的な実装フロー

新しい機能を実装する際は、以下の流れを意識すると、スムーズに開発を進めることができます。

### ① 企画・設計 (Planning & Design)
- **目的の明確化:** その機能が「誰の」「どんな課題を解決するのか」を具体的に考えます。
- **アーキテクチャの検討:** 新しい機能を、既存のどのモジュール（`ai/`, `collectors/`, `services/`など）に関連付けるのが最適か、あるいは新しいモジュールが必要かを考えます。

### ② ファイル構成の検討 (File Structure)
- **関心の分離:** 1つのファイルには、1つの責任（役割）だけを持たせるように心がけます。例えば、「データを集める機能」と「AIが応答を考える機能」は別のファイルに分けるべきです。
- **再利用性の意識:** 他の機能からも使えそうな部品は、独立したファイルやクラスとして作成します。

### ③ 実装 (Implementation)
- **コーディング:** 設計に基づいて、実際にコードを書いていきます。
- **可読性:** 未来の自分や他の人が読んでも理解しやすいように、変数名や関数名を分かりやすくし、必要に応じてコメントを追加します。

### ④ 統合 (Integration)
- 作成した新しい機能を、既存のメインの処理フローに組み込みます。例えば、`main.py`や`ai/AI_main.py`などから、新しく作ったクラスや関数を呼び出すようにします。

### ⑤ テスト (Testing)
- 新しい機能が正しく動作すること、そして既存の機能に悪影響（バグ）を与えていないことを確認します。

---

## 2. 実装例：RAG (Retrieval-Augmented Generation) 機能

上記のフローに基づき、具体的な機能として「RAG」を実装する手順を解説します。

### RAG機能とは？

一言でいうと、**「AIが外部の資料を参考にして、より賢く回答するための仕組み」**です。

ユーザーから質問された際に、
1.  インターネットやユーザーのパソコン内にあるファイルから、関連情報を探し出す（**Retrieval**）。
2.  探し出した情報と元の質問をセットでAIに渡し、より正確で文脈に沿った回答を生成させる（**Augmented Generation**）。

これにより、AIは学習データにない最新の情報や、ユーザー個人の情報に基づいた応答が可能になります。

### 手順1: 必要なライブラリのインストール

RAGを実装するために、便利な機能を提供してくれる外部ライブラリをインストールします。

- **`langchain`, `langchain-community`**: AIと外部データ（ファイル、Webサイトなど）を連携させるためのフレームワーク。複雑な処理を簡単に書けるようになります。
- **`faiss-cpu`**: Facebook AIが開発した、高速な類似検索ライブラリ。大量の文章の中から、質問に最も関連性の高いものを瞬時に見つけ出すために使います。
- **`sentence-transformers`**: 文章をコンピュータが意味を理解できる数値の配列（ベクトル）に変換するためのライブラリです。

ターミナル（コマンドプロンプト）で以下のコマンドを実行してインストールします。
```bash
pip install langchain langchain-community faiss-cpu sentence-transformers
```

### 手順2: ローカルファイル検索機能の作成

ユーザーのPC内にあるファイルを検索するための機能を作成します。

- **目的:** 指定されたフォルダ内のテキストファイルを読み込み、FAISSを使って高速に検索できる「索引（インデックス）」を作成する。
- **新規ファイル:** `collectors/LocalFileCollector.py`

```python
# collectors/LocalFileCollector.py

import os
from langchain_community.vectorstores import FAISS
from langchain_community.embeddings import SentenceTransformerEmbeddings
from langchain_community.document_loaders import TextLoader
from langchain.text_splitter import CharacterTextSplitter

class LocalFileCollector:
    """
    ローカルファイルを収集し、ベクトルストアを構築・検索するクラス
    """
    def __init__(self, file_paths, index_path="./faiss_index"):
        self.file_paths = file_paths
        self.index_path = index_path
        self.embeddings = SentenceTransformerEmbeddings(model_name='all-MiniLM-L6-v2')
        self.vector_store = None

    def build_index(self):
        """
        指定されたファイルからインデックスを構築する
        """
        documents = []
        for file_path in self.file_paths:
            if os.path.exists(file_path):
                loader = TextLoader(file_path, encoding='utf-8')
                documents.extend(loader.load())

        if not documents:
            print("インデックス対象のドキュメントが見つかりません。")
            return

        text_splitter = CharacterTextSplitter(chunk_size=1000, chunk_overlap=0)
        docs = text_splitter.split_documents(documents)

        # ベクトルストアを作成し、ローカルに保存
        self.vector_store = FAISS.from_documents(docs, self.embeddings)
        self.vector_store.save_local(self.index_path)
        print(f"インデックスが {self.index_path} に保存されました。")

    def search(self, query, k=5):
        """
        インデックスから関連情報を検索する
        """
        if self.vector_store is None:
            if os.path.exists(self.index_path):
                # 保存されたインデックスを読み込む
                self.vector_store = FAISS.load_local(self.index_path, self.embeddings, allow_dangerous_deserialization=True)
            else:
                print("インデックスが構築されていません。")
                return []
        
        # 類似度検索を実行
        results = self.vector_store.similarity_search(query, k=k)
        return [doc.page_content for doc in results]

```

### 手順3: RAG全体の管理機能の作成

Web検索とローカルファイル検索を組み合わせ、AIに応答を生成させる司令塔を作成します。

- **目的:** ユーザーの質問を受け取り、各情報源から情報を収集し、最終的なプロンプトを作成してAIに渡す。
- **新規ファイル:** `ai/AI_rag_manager.py`

```python
# ai/AI_rag_manager.py

from .AI_geminiAPI import GeminiAPI  # 仮のGeminiAPIクラス
from collectors.LocalFileCollector import LocalFileCollector
# from services.web_search import GoogleWebSearch # Web検索機能（別途実装想定）

class RAGManager:
    def __init__(self, config):
        self.config = config
        self.gemini_api = GeminiAPI(api_key=config.get('GEMINI_API_KEY'))
        
        # ローカルファイルコレクターの初期化
        local_files = config.get('RAG_LOCAL_FILES', [])
        self.local_collector = LocalFileCollector(file_paths=local_files)
        
        # Web検索機能の初期化
        # self.web_searcher = GoogleWebSearch()

    def generate_response(self, query):
        # 1. 情報検索 (Retrieval)
        # ローカルファイルから検索
        local_context = self.local_collector.search(query)
        
        # Webから検索 (実装例)
        # web_context = self.web_searcher.search(query)
        web_context = ["Web検索は現在開発中です。"] # 仮のデータ

        # 2. プロンプトの作成
        context = "以下の情報を参考にして、質問に日本語で回答してください。\n\n"
        context += "--- ローカルファイルからの情報 ---\n"
        context += "\n".join(local_context)
        context += "\n\n--- Webからの情報 ---\n"
        context += "\n".join(web_context)
        
        final_prompt = f"{context}\n\n--- 質問 ---\n{query}"

        # 3. AIによる応答生成 (Generation)
        response = self.gemini_api.generate_text(final_prompt)
        return response

```

### 手順4: 設定ファイルの更新

ユーザーがどのフォルダを検索対象にするかを指定できるように、設定機能を追加します。

- **目的:** アプリケーションの設定に、RAGで検索するファイルやフォルダのパスを追加する。
- **修正ファイル:** `services/config_controller.py`

```python
# services/config_controller.py の修正例

# (既存のコード...)

class ConfigController:
    def __init__(self, config_file='config.json'):
        # ... (既存の初期化処理) ...
        self.defaults = {
            'GEMINI_API_KEY': 'YOUR_API_KEY_HERE',
            'RAG_LOCAL_FILES': [
                'C:/Users/YourUser/Documents/memo.txt',
                'C:/Users/YourUser/Desktop/project_docs/'
            ]
            # ... (他の設定) ...
        }
        # ... (既存のロード処理) ...

# (既存のコード...)
```

### 手順5: メインアプリへの統合

最後に、作成したRAG機能をメインのAI処理に組み込みます。

- **目的:** `AI_main.py`が、直接AIを呼び出す代わりに、新しく作った`RAGManager`を呼び出すように変更する。
- **修正ファイル:** `ai/AI_main.py`

**修正前 (Before):**
```python
# ai/AI_main.py (修正前)
from .AI_geminiAPI import GeminiAPI

class AIMain:
    def __init__(self, config):
        self.gemini = GeminiAPI(api_key=config.get('GEMINI_API_KEY'))

    def get_response(self, user_prompt):
        # 直接Gemini APIを呼び出している
        response = self.gemini.generate_text(user_prompt)
        return response
```

**修正後 (After):**
```python
# ai/AI_main.py (修正後)
from .AI_rag_manager import RAGManager # RAGManagerをインポート

class AIMain:
    def __init__(self, config):
        # RAGManagerを初期化
        self.rag_manager = RAGManager(config)

    def get_response(self, user_prompt):
        # RAGManager経由で応答を生成
        response = self.rag_manager.generate_response(user_prompt)
        return response
```

---
## まとめ

以上が、新機能を追加する際の基本的な流れと、RAG機能を実装する具体的な手順です。

- **モジュール性:** 機能ごとにファイルを分けることで、コードの見通しが良くなり、修正や機能追加が容易になります。
- **再利用性:** `LocalFileCollector`のように、特定の役割を持つクラスとして作成することで、将来別の機能からも利用できる可能性が生まれます。

このガイドを参考に、ぜひ様々な機能開発に挑戦してみてください。

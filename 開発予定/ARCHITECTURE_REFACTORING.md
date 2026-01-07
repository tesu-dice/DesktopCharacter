# アーキテクチャ改善ガイド (AppContext & EventBus パターン)

このドキュメントは、アプリケーションの構造を改善し、将来の機能追加やメンテナンスを容易にするためのリファクタリング（構造改善）手順を、詳細な解説と共にまとめたものです。

## 1. はじめに

### 目的
現在のアプリケーションの優れたモジュール性（機能ごとのファイル分割）を活かしつつ、モジュール間の連携方法をより柔軟で堅牢なものに改善します。

### 現状の課題: 「密結合」
現状では、`AI`モジュールが`UI`モジュールのことを知っていたり、`UI`が`main`の処理を直接呼び出すなど、各モジュールがお互いを直接参照しあう「密結合」な部分があります。これにより、一部の修正が他の部分に影響を与えやすくなっています。

### 解決策: 2つのデザインパターンの導入
この課題を解決するため、以下の2つのデザインパターンを`main.py`に統合します。

1.  **`myapp`クラス as AppContext（アプリケーションの司令塔）**
    `myapp`クラスを、アプリケーションの全ての主要機能（UI, AI, Configなど）を管理する唯一の「司令塔」と位置づけます。

2.  **EventBus（イベント通知システム）**
    モジュール間の直接的なメソッド呼び出しをやめ、「イベント」を介して連携します。

---

## 2. 新しいアーキテクチャの全体像

リファクタリング後のアプリケーションは、以下の2つの中心的な考え方に基づいて動作します。

### 2.1. 司令塔 `myapp` (The `myapp` Command Center)
`myapp`クラスのインスタンスは、アプリケーションの全てのサービス（UI, AI, 設定コントローラー等）への参照を保持する、唯一無二の存在となります。各モジュールは、この`myapp`インスタンスを「コンテキスト(context)」として受け取ることで、他のサービスが必要になった場合に `context.ai_manager` のようにアクセスできます。これにより、モジュール間でインスタンスをバケツリレーする必要がなくなります。

### 2.2. 郵便局 `EventBus` (The `EventBus` Post Office)
`EventBus`は、モジュール間のコミュニケーションを仲介する「郵便局」の役割を果たします。この郵便局の仕組みは、`if...elif...`のような静的な分岐ではなく、動的な**「辞書（Dictionary）」**に基づいています。

-   **購読 (Subscribe)**: あるモジュールが `event_bus.subscribe("イベント名", 自分の関数)` を呼び出すと、`EventBus`の内部にある辞書（台帳）に「このイベント名の手紙が来たら、この関数に届けてください」という情報が登録されます。
-   **発行 (Publish)**: 別のモジュールが `event_bus.publish("イベント名", データ)` を呼び出すと、`EventBus`は台帳を見て、そのイベント名で登録されている全ての関数を、データと共に呼び出します。

この仕組みにより、`EventBus`自身はイベントの具体的な種類を知る必要がなく、ただの仲介役に徹することができます。これにより、モジュール同士がお互いの存在を意識することなく連携できる「疎結合」が実現されます。

---

## 3. 実装手順

以下に、具体的なコードの変更手順を示します。

### 3.1. `main.py` の全体的な変更
`EventBus`クラスを定義し、`myapp`クラスを司令塔として再構築します。

```python
# main.py (最終的な修正案)

import os
import threading

# --- 依存モジュールのインポート ---
from ui import UI_main
from ai import AI_main
# ... (他は同様)

# ▼▼▼ NEW: EventBusクラスをmain.pyに直接定義 ▼▼▼
class EventBus:
    """シンプルなイベント発行/購読システム"""
    def __init__(self):
        self._listeners = {}

    def subscribe(self, event_type: str, listener):
        if event_type not in self._listeners:
            self._listeners[event_type] = []
        self._listeners[event_type].append(listener)

    def publish(self, event_type: str, *args, **kwargs):
        if event_type in self._listeners:
            for listener in self._listeners[event_type]:
                thread = threading.Thread(target=listener, args=args, kwargs=kwargs)
                thread.daemon = True
                thread.start()

# ▼▼▼ MODIFIED: myappクラスの責務を拡張 ▼▼▼
class myapp():
    def __init__(self, engine_process=None, TalkHistory=[], debug=-1):
        # 1. AppContextとしての初期化
        self.debug = debug
        self.engine_process = engine_process
        self.event_bus = EventBus()

        # 2. サービスの読み込みとインスタンス化
        self.config = config_controller.read_configfile("config.json")
        # ... (VOICEVOXの起動処理など)
        self.win_info = WindowsInfoCollecter.win_info_collector(self, debug=debug)
        self.ai_manager = AI_main.AI_Manager(self, TalkHistory, debug=debug)
        self.ui = UI_main.UI(self, debug=debug)

        # 3. イベントリスナーのセットアップ
        self._setup_event_listeners()

        # 4. 起動シーケンス
        # ... (既存の起動メッセージ処理)

        self.update(debug=debug)

    def _setup_event_listeners(self):
        """アプリケーション内のイベント購読をここで一元管理する"""
        self.event_bus.subscribe("user_message_sent", self._on_user_message_sent)
        self.event_bus.subscribe("ai_response_generated", self.ui.handle_ai_response)

    def _on_user_message_sent(self, text: str):
        """UIからメッセージ送信イベントを受け取ったときの処理"""
        t, w, m = "", "", ""
        if self.config.get_setting_value("ApplicationSettings.Permission.CurrentTime"):
            t = "\n現在時刻：" + self.win_info.get_datetime()
        # ... (他のコンテキスト付与処理)
        send_text = text + t + w + m
        self.ai_manager.request_response(send_text, debug=self.debug)

    # ... (reboot, update メソッドは既存のまま)
```

### 3.2. `AI_main.py` の変更
`AI_Manager`がUIの機能を直接呼び出すのをやめ、イベントを発行するように変更します。

```python
# ai/AI_main.py の AI_Manager クラスを修正

class AI_Manager():
    def __init__(self, context, TalkHistory=[], debug=-1):
        self.context = context # myapp インスタンスを context として保持
        self.usersetting = self.context.config
        # ... (他の初期化)

    def request_response(self, input_text: str, debug: int = -1):
        # ... (AIへの送信、履歴追加などのロジック)
        response = self.ai.response(...)
        self.add_talkhistory("model", response["text"], debug)
        
        # 修正点: UIへの直接操作をやめ、イベントを発行する
        self.context.event_bus.publish("ai_response_generated", response["text"])
```

### 3.3. `UI`関連モジュールの変更
UIはイベントを発行、または購読して処理を実行するように変更します。

```python
# ui/UI_talk.py の送信ボタンのコールバック関数を修正
# self.app は myapp インスタンス (context)
self.app.event_bus.publish("user_message_sent", user_input)

# ui/UI_main.py の UI クラスにメソッドを追加
class UI(tk.Tk):
    def __init__(self, context, debug=-1):
        # ...

    def handle_ai_response(self, response_text: str):
        """ai_response_generated イベントを受け取ったときの処理"""
        # 以前 AI_Manager が行っていたUI更新と読み上げの処理をここに集約
        # ... (テキスト解析、画像更新、ログ追加、音声合成呼び出し)
```

---

## 4. 具体的な処理フローの追跡

「ユーザーがメッセージを送信してからAIの応答が反映されるまで」の、関数・変数レベルの詳細な流れは以下の通りです。

1.  **ステップ1: [場所: UI (会話ウィンドウ)] - イベントの発行**
    -   **トリガー:** ユーザーが「送信」ボタンをクリック。
    -   **関数:** ボタンのコールバック関数が実行される。
    -   **変数:** `user_input` に入力されたテキスト（例: `"こんにちは"`）が格納される。
    -   **アクション:** `self.app.event_bus.publish("user_message_sent", user_input)` が実行される。

2.  **ステップ2: [場所: EventBus] - イベントの仲介**
    -   **関数:** `publish`メソッドが実行される。
    -   **変数:** `event_type`は`"user_message_sent"`、`args`は `("こんにちは",)` となる。
    -   **アクション:** 内部の辞書`_listeners`からキー`"user_message_sent"`に対応する関数のリストを取得し、`myapp._on_user_message_sent`を呼び出す。

3.  **ステップ3: [場所: main.py (myappクラス)] - イベントの受信と司令塔の役割**
    -   **関数:** `_on_user_message_sent(self, text)` が実行される。
    -   **変数:** `text`は `"こんにちは"`。
    -   **アクション:** `self.win_info`等から補助情報を取得し、`send_text`（例: `"こんにちは\n現在時刻..."`）を作成。その後、`self.ai_manager.request_response(send_text)` を呼び出す。

4.  **ステップ4: [場所: AI_main.py (AI_Managerクラス)] - 応答の生成**
    -   **関数:** `request_response(self, input_text)` が実行される。
    -   **変数:** `input_text`は`send_text`の値。
    -   **アクション:** LLMにリクエストを送信し、応答`response`（例: `{"text": "笑顔.png：どうも！"}`）を取得。その後、`self.context.event_bus.publish("ai_response_generated", response["text"])` を実行。

5.  **ステップ5: [場所: EventBus] - 再びイベントの仲介**
    -   **関数:** `publish`メソッドが再び実行される。
    -   **変数:** `event_type`は`"ai_response_generated"`、`args`は `("笑顔.png：どうも！",)` となる。
    -   **アクション:** 辞書から`"ai_response_generated"`に対応する`UI.handle_ai_response`を呼び出す。

6.  **ステップ6: [場所: UI_main.py (UIクラス)] - 応答の反映**
    -   **関数:** `handle_ai_response(self, response_text)` が実行される。
    -   **変数:** `response_text`は `"笑顔.png：どうも！"`。
    -   **アクション:** `response_text`を`image_name`と`speech_text`に分割し、`update_character_image`や`add_log`、音声合成関数などを呼び出して、画面に結果を反映させる。

### 4.3. 複数のリスナーと並行実行について

一つのイベント名に対して複数の関数が登録されている場合、`EventBus`はそれらの関数を**並行して（concurrently）**実行します。これは、各リスナー関数をそれぞれ独立した新しいスレッドで実行することで実現されます。

```python
# EventBus.publish メソッドの一部
for listener in self._listeners[event_type]:
    # 各リスナーを新しいスレッドで実行
    thread = threading.Thread(target=listener, args=args, kwargs=kwargs)
    thread.daemon = True # アプリケーション終了時にスレッドも終了させる
    thread.start() # ここでスレッドが開始され、リスナー関数が実行される
```

#### なぜ並行実行させるのか？

*   **UIの応答性維持:** 最も重要な理由です。もしスレッドを使わずに順番に実行した場合、時間のかかる処理（例：AI応答の解析、ファイルI/O、ネットワーク通信）が一つでもあると、その処理が終わるまでUIがフリーズしてしまいます。各リスナーを別スレッドで実行することで、UIは常にスムーズに動作し続けることができます。
*   **処理の独立性:** 各リスナーは、他のリスナーがどれくらいの時間かかるか、あるいはエラーを起こすかを知る必要がありません。それぞれが独立したスレッドで実行されるため、一つのリスナーの遅延やエラーが、他のリスナーやアプリケーション全体をブロックするのを防ぎます。
*   **拡張性:** 新しい機能（例：AI応答をデータベースに保存する、特定のキーワードを検出して通知する）を追加したい場合、既存のコードに影響を与えることなく、新しいリスナー関数を作成してイベントに購読させるだけで済みます。

このように、一つのイベントに対して複数の関数が登録され、それらが並行して実行されることで、アプリケーションはより柔軟で、応答性が高く、拡張しやすい構造になります。

---

## 5. まとめ

このリファクタリングにより、各モジュールは自身の責務に集中し、`EventBus`を介して協調動作するようになります。これにより、コードの見通しが良くなり、将来の機能追加が格段に容易になります。
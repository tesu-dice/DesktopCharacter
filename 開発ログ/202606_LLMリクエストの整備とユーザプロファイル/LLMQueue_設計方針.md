# LLMリクエストキュー 設計方針

**作成日:** 2026年07月01日  
**最終更新日:** 2026年07月01日  
**対象:** DesktopCharacter / AI_main.py

---

## 1. 背景と課題

LLMへのリクエストが複数の発生源（ユーザー入力・サマリー生成など）から
EventBus経由で並行スレッドとして走るため、以下の問題が発生していた。

- ユーザー入力とサマリー生成が同時に走りタイムアウトが発生する
- 23:55に時間サマリーと日サマリーが重複してエラーになる
- どの生成結果がどのリクエストへの返答かをEventBus受信側が識別できない

---

## 2. 解決方針

`AI_Manager` 内に**優先度付きキュー**とワーカースレッドを実装し、
LLMへのリクエストを1件ずつ逐次処理する。  
実装は `ai/AI_main.py`、`main.py`、`services/UserDataLogger.py` の変更で完結させる。  
`EventBus` 本体は変更しない。  
これによって将来的にはPKMの恒常的なバックグラウンドでの分析やインターネットでの情報収集が行えるようになることが期待される。

---

## 3. 優先度の定義

| 定数名 | 値 | 種別 |
|--------|-----|------|
| `LLM_PRIORITY_USER`      | 1 | ユーザー入力への応答 |
| `LLM_PRIORITY_PROACTIVE` | 2 | 自発的会話 |
| `LLM_PRIORITY_SUMMARY`   | 3 | サマリー生成 |
| `LLM_PRIORITY_PROFILE`   | 4 | プロファイル更新（将来用） |

定数は `AI_main.py` のモジュールレベルで定義する。
数値が小さいほど優先度が高い。同一優先度内はFIFO順とする。

優先度は `req_LLM()` の呼び出し側では指定しない。
`response_event` 名と優先度の対応は `AI_Manager.__init__` 内の `self._route` で一元管理する。

---

## 4. キューのデータ構造

`queue.PriorityQueue` に `(priority, counter, task)` のタプルを積む。

| 要素 | 型 | 内容 |
|------|-----|------|
| `priority` | int | 優先度定数 |
| `counter`  | int | 単調増加カウンタ（同一優先度のFIFO保証用） |
| `task`     | callable | ワーカーが実行する処理関数 |

`counter` が常に一意なためタプル比較がcallableに到達しない。

---

## 5. 実装内容

### 5.1 ルーティングテーブル（`self._route`）

`AI_Manager.__init__` 内で定義し、`response_event` 名から `(priority, handler)` を決定する。

```python
self._route = {
    "OnUserResponse": (LLM_PRIORITY_USER,    self._do_response),
    "OnSummaryDone":  (LLM_PRIORITY_SUMMARY, self._do_summary),
}
```

新しい種別を追加する際はこのテーブルに1行加えるだけでよい。
優先度の管理も呼び出し側ではなくここに集約されている。

### 5.2 唯一の公開インターフェース：`req_LLM()`

全てのLLMリクエストは `req_LLM()` を経由する。

```python
def req_LLM(self, payload, response_event: str, debug: int = -1):
    entry = self._route.get(response_event)
    if entry is None:
        logger.warning(f"req_LLM: 未知のresponse_event '{response_event}'")
        return
    priority, handler = entry
    self._enqueue(priority, lambda: handler(payload, response_event, debug))
```

| 引数 | 内容 |
|------|------|
| `payload` | LLMに渡すデータ（input_dict・summaryデータ等） |
| `response_event` | 完了時にpublishするイベント名（ルーティング・優先度決定も兼ねる） |

呼び出しは即座にリターンし、ワーカースレッドが非同期に処理する。

### 5.3 処理関数の責務

#### `_do_response(payload, response_event, debug)`

ユーザー入力への通常応答。完了後に `bus.publish(response_event, output_dict)` を発行する。
イベント名はハードコードせず、引数の `response_event` を使う。

#### `_do_summary(payload, response_event, debug)`

サマリー生成専用ハンドラ。`payload` から `scope`・`time`・`data`・`reply_to` を展開し、
`scope` に応じたプロンプトを組み立ててLLMを呼び出す。
完了後に `bus.publish(response_event, time_str, scope, reply_to, result_text)` を発行する。

```python
# scope に応じたプロンプト生成
if scope == "hour":
    prompt = f"次のユーザの1時間のアクティビティを短く要約してください。\n{data_str}"
elif scope == "day":
    prompt = (
        "以下はユーザーの1日の活動記録です。\n"
        "'hour_summaries'には時間ごとの要約が、'unsummarized_raw_logs'には"
        "まだ要約されていない時間帯の生ログが含まれています。\n"
        "これらすべてを考慮して、1日の活動全体を3つ程度の主要な出来事にまとめてください。\n"
        f"{data_str}"
    )
```

プロンプト生成ロジックは `UserDataLogger` ではなくこの関数が持つ。
LLM関連の知識をAI側に集約するための設計。

---

## 6. イベントフローと受け取り先の分離

イベント名で「誰が受け取るか」を明確に分ける。

| response_event | 受け取り側 | 用途 |
|----------------|-----------|------|
| `OnUserResponse` | UI（talk_window / Reflect_Text） | ユーザーへの返答表示・TTS |
| `OnSummaryDone`  | UserDataLogger（add_summary_log） | サマリーの保存 |

### ユーザー入力フロー

```
MessageInput
  ↓ main.py: handle_user_message()
  ↓ AI_Manager.req_LLM(payload, "OnUserResponse")
  ↓ キューに積んで即リターン
ワーカースレッドが取り出す
  ↓ _do_response(payload, "OnUserResponse")
bus.publish("OnUserResponse", output_dict)
  ↓
talk_window.add_log / UI.Reflect_Text
```

### サマリー生成フロー

```
UserDataLogger._check_and_trigger_summary()
  ↓ request_summary(scope, target_time)
  ↓ bus.publish("Req_UserSummaryLog", json_str, scope, target_time, reply_to)
main.py: handle_summary_request()
  ↓ AI_Manager.req_LLM(payload_dict, "OnSummaryDone")
  ↓ キューに積んで即リターン
ワーカースレッドが取り出す
  ↓ _do_summary(payload, "OnSummaryDone")
  ↓ プロンプト生成 → LLM呼び出し
bus.publish("OnSummaryDone", time_str, scope, reply_to, result_text)
  ↓
UserDataLogger.add_summary_log()
```

サマリーリクエストは `"Req_UserSummaryLog"` の1イベントに統一されており、
`main.py` がペイロードをまとめて `req_LLM` に渡す。

---

## 7. 影響ファイル

| ファイル | 変更内容 |
|---------|---------|
| `ai/AI_main.py` | `_route` 追加、`req_LLM()` 追加、`_do_response()` を `response_event` 対応化、`_do_summary()` 追加、RAG関連メソッド削除 |
| `main.py` | `handle_user_message()` / `handle_summary_request()` 追加、RAG購読削除、サマリー購読を1イベントに統一 |
| `services/UserDataLogger.py` | `request_summary()` からプロンプト生成ロジックを除去、publishを1イベントに統一 |
| `services/Event_Bus.py` | 変更なし |

---

## 8. 削除した機能

| 削除対象 | 代替 |
|---------|------|
| `response()` | `req_LLM()` + `_do_response()` |
| `response_withRAG()` / `_do_response_withRAG()` / `make_rag_request()` | RAG機能ごと削除 |
| `response_onetime()` / `_do_onetime()` | `req_LLM()` + `_do_summary()` |
| RAG関連EventBus購読（`Response_RAGisON/OFF`, `Req_RAGInfo`, `RAGisReady`） | 削除 |
| `Check_responseMode()` | `handle_user_message()` に置き換え |
| `AIGenerateMessage` イベント | `OnUserResponse` に変更 |
| `Req_UserSummaryLog_context` / `Req_UserSummaryLog_TimeAndScope` の2イベント構成 | `Req_UserSummaryLog` の1イベントに統一 |

---

## 9. 未解決・将来課題

| 項目 | 内容 |
|------|------|
| サマリー生成の定刻依存からの脱却 | 起動時に未生成分をチェックしてキューに積む方式へ移行（23:55トリガーを廃止） |
| 自発的会話のキュー化 | 機能実装時に `LLM_PRIORITY_PROACTIVE` を使用し `req_LLM` 経由で呼び出す |
| プロファイル更新機能 | `LLM_PRIORITY_PROFILE` を使用、起動時チェックで週次更新、別設計書参照 |
| UI「処理中」表示 | ReActループは複数回のLLM呼び出しを1タスクとして実行するため、ループ中は次のキューアイテムが処理されない。長時間の処理中にユーザーが入力しても応答が遅延するため、キュー処理中であることをUIに表示する仕組みが必要。 |

---

## 10. 備考（実装中の方針変更）

### `priority` 引数の廃止

当初の設計では `req_LLM(payload, priority, response_event)` と呼び出し側が優先度を渡す仕様だった。
実装途中で「`response_event` が決まれば優先度も一意に決まる」ことから、
優先度の判断を呼び出し側に委ねる必要がないと判断。

`self._route` テーブルに `(priority, handler)` をまとめて定義し、
`req_LLM` は `response_event` のみ受け取る形に変更した。
これにより呼び出し側（`main.py`）が優先度定数を意識しなくてよくなった。

### サマリーリクエストの1イベント化

当初の実装では `UserDataLogger` が2つのイベントを発行し、
`main.py` 側で `subscribe_when` により合流させてから `req_LLM` に渡す設計だった。

- `"Req_UserSummaryLog_context"` → ログデータ（JSON文字列）
- `"Req_UserSummaryLog_TimeAndScope"` → 時刻・スコープ

`subscribe_when` は複数イベントが「どのペアが同一リクエストのものか」を識別できないため、
連続してサマリーが発行された際に混線するリスクがあった。

解決策として `"Req_UserSummaryLog"` の1イベントに統合し、
全引数 `(json_str, scope, target_time, reply_to)` を一度に渡す形に変更した。

### プロンプト生成の移動

旧実装では `UserDataLogger.request_summary()` がプロンプト文字列を組み立てて
`response_onetime()` に渡していた。
LLMに渡すプロンプトの知識がロガー側に存在するのは責務の分離として不適切であるため、
`_do_summary()` に移動してAI側で完結させた。

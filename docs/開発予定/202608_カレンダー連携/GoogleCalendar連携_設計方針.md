# GoogleCalendar連携 設計方針

**作成日:** 2026年08月07日
**最終更新日:** 2026年08月07日
**対象:** DesktopCharacter / collectors, ai_tools, main.py

---

## 1. 背景と課題

キャラクターがユーザーの予定を把握したうえで会話できるようにする。
現状、Googleカレンダー連携は `collectors/GoogleCalendarAPI.py`（および旧版の
`collectors/GoogleCalendarAPItest.py`）としてすでに存在するが、これは指定期間の
予定・タスクをMarkdown日記（`./diary/YYYY-MM-DD.md`）へバッチ出力するスタンドアロン
スクリプトであり、EventBus・AI_Manager・ai_tools のいずれとも接続されていない。

これをアプリ本体に向けとして新規作成し、`get_active_window` や `get_user_activity_summary` と同様に、AIが会話中に参照できる情報源（AI Tool）として使えるようにする。

### 主な方針

1. 認証は起動時に毎回要求する。`client_secret.json` がappdir直下にある場合にのみ要求し、user_tokenはファイルとして保存しない。
2. アプリ側で認証とAPIを叩いての情報取得を行い、カレンダー情報を保存する。基本的にはn分ごと(初期値5分)の定期的なタイミングと、AI会話を行う直前に行う。
3. 取得したカレンダー情報はJSON形式でファイル保存し、アプリの終了時に削除する、もしくは起動時に古いものをすべて削除する（安全性のため）。
4. AI Tools側はJSONファイルを参照してユーザーのカレンダー情報を確認する。

### スコープ

今回実装するのは以下の2ファイルを中心とした「会話コンテキストとしてのカレンダー参照」まで。

- アプリ側のカレンダー管理ファイル（認証・定期取得・キャッシュ管理を担うコレクター）
- AI_Toolとしてのカレンダー読み取りファイル

日次サマリー・日記自動生成機能（`services/UserDataLogger.py`）との統合は行わない。
既存の `collectors/GoogleCalendarAPI.py` によるMarkdown日記生成は、別用途の
スタンドアロンツールとして現状のまま残す。

---

## 2. 全体アーキテクチャ
- アプリ側のプログラムについて  
既存の `services/WindowsInfoCollecter.py` と同じ形で、`bus` / `setting` を初期化の際に引数として定義する。  
コレクタークラス `GoogleCalendarCollector` を新設する。  
EventBus配線は`Req_UserActivityLog` の定刻毎トリガーと同じものを利用する。

- AI_Tools側のプログラムについて  
`ai_tools` 配下のTool（`BaseTool` 継承クラス）は `ai_tools/tools_main.py:
ToolExecutor._discover_tools()` によって **引数なし (`obj()`)** でインスタンス化される
制約がある（`get_user_activity_summary_tool.py` も `bus`/`setting` を持たず、
`user_logs/` を直接ファイルとして読んでいるのと同じ形）。
そのため `GetCalendarInfoTool` は `GoogleCalendarCollector` の生存インスタンスを
参照できない。**キャッシュJSONファイルを介してのみ**両者は連携する。

```
main.py (myapp.__init__)
  └─ self.CalendarCollector = GoogleCalendarCollector(self.bus, self.setting, self.app_dir, debug=debug)

main.py (_setup_event_listeners)
  └─ self.bus.subscribe("Req_CalendarInfo", self.CalendarCollector.refresh_cache)

main.py (update() 内、5分毎 / handle_user_message() 内)
  └─ ユーザ設定のPermission.get_calendar_info が True の場合のみ
       self.bus.publish("Req_CalendarInfo")   ※非同期

GoogleCalendarCollector.refresh_cache()
  └─ Google Calendar/Tasks APIを叩き、google_calendar_cache.json を上書き

ai_tools/get_calendar_info_tool.py (GetCalendarInfoTool.execute)
  └─ google_calendar_cache.json を読むだけ（更新はトリガーしない）
  └─ target_dateで抽出・整形し、fetched_atから鮮度も付記してAIに返す
```

`Req_UserActivityLog` と異なり情報源は1つ（Googleカレンダー）だけなので、
`subscribe_workflow` / `subscribe_when` による合流は不要。`subscribe` で直結する。

---

## 3. 新規・変更・関連ファイル一覧

| ファイル | 種別 | 内容 |
|---------|------|------|
| `collectors/GoogleCalendarCollector.py` | 新規 | 認証・API取得・JSONキャッシュ書き込みを担うクラス。`GoogleCalendarAPI.py` の予定取得ロジック（`get_calendar_by_date` 等）を移植し、トークン非保存・EventBus対応の形に書き換える。 |
| `ai_tools/get_calendar_info_tool.py` | 新規 | `BaseTool` 継承。キャッシュJSONを読んでAIに整形して返す読み取り専用クラス。`get_user_activity_summary_tool.py` と同じ構造。 |
| `services/config_controller.py` | 変更 | `Permission.get_calendar_info` フラグ追加、`GoogleCalendar` セクション（取得範囲日数など）追加。クラス新設なし。 |
| `main.py` | 変更 | コレクターのインスタンス化、イベント購読、2つのトリガー追加、`exit()` でのキャッシュ削除。 |
| `requirements.txt` | 変更 | `google-auth-oauthlib`、`google-api-python-client` を追加（`googleapiclient` はこのパッケージ由来）。 |
| `.gitignore` | 変更 | `google_calendar_cache.json` を追加。 |
| `collectors/GoogleCalendarAPI.py` / `GoogleCalendarAPItest.py` | 変更なし | 日記生成バッチとして現状維持。 |

各ファイルのクラス定義・関数ごとの責任分担は10章にまとめる。

---

## 4. 認証仕様

### 4.1 起動条件

- `client_secret.json` がアプリ実行ディレクトリに存在し、`Permission.get_calendar_info` が `True`の場合にのみ認証を試みる。カレンダー機能自体を静かに無効化し（例外を投げない）、Tool実行時は「Googleカレンダー連携は設定されていません」という固定応答を返す。
- userconfigにも該当の設定項目を設ける。（T/F）

```python
"get_calendar_info": {
    "name": "Googleカレンダーの予定",
    "description": "Googleカレンダーの予定・タスクを取得・利用します。"
                    "利用にはclient_secret.jsonの配置と、起動時のGoogle認証が必要です。",
    "type": "bool",
    "value": False
}
```

`services/config_controller.py:get_default_data()` の `ApplicationSettings.Permission` に追加する。
既定値は `False`。他のPermission項目と異なり外部サービス連携かつ事前セットアップ
（`client_secret.json` 配置）が必要なため、明示的にオンにするまで一切の認証・通信を行わない。

- どちらのファイルも `.gitignore` 済み・`config.json` と同様にリポジトリへは含めない。

### 4.2 トークンの扱い

- `oauth_token.json` への書き込みは行わない（既存 `GoogleCalendarAPI.py`
  の `open(OAUTH_TOKEN_FILE, "w")` に相当する処理を削除する）。
- 取得した `Credentials` オブジェクトはプロセスメモリ上（`GoogleCalendarCollector`
  インスタンスの属性）にのみ保持し、アプリ終了とともに破棄される。
- トレードオフとして、起動のたびにブラウザでのOAuth同意画面（`run_local_server`）が
  開く。これは「トークンをファイルに残さない」という安全性要件を優先した結果であり、
  意図的な仕様とする。

### 4.3 認証タイミングの実装上の補足

草案の「起動時に毎回要求」を、Tkのメインループをブロックしないよう
**バックグラウンドスレッドでの非同期実行**として実装する。

- `myapp.__init__()` で `GoogleCalendarCollector` を生成した直後、認証開始を
  別スレッドに投げる（`threading.Thread(target=..., daemon=True).start()`）。
- 認証完了前に定期取得が走った場合は「未認証」を示す状態を返し、失敗として扱わない。
- 認証失敗（ユーザーがブラウザで同意しなかった、タイムアウト等）はログに記録し、
  そのセッション中はカレンダー機能を無効状態のまま継続する（再試行はしない）。

---

## 5. 取得タイミングの仕様

草案の「定刻毎」「AI会話を行う直前」の2つの非同期トリガーとして実装する。
Tool側からの同期トリガーは行わない。

| トリガー | 実装 | 目的 |
|---------|------|------|
| 定期取得 | `main.py update()` 内、既存の `mm_now % 5 == 0` 分岐に追加し `Req_CalendarInfo` を publish | バックグラウンドでキャッシュを鮮度良く保つ |
| ユーザーメッセージ受信時 | `main.py handle_user_message()` の冒頭で `Req_CalendarInfo` を publish（`AI_Manager.req_LLM()` 呼び出しと並行、レスポンスは待たない） | 会話が始まったタイミングでも鮮度を上げておく |

いずれも `bus.publish` は非同期（fire-and-forget）で、  
`GetCalendarInfoTool.execute()`はその時点でのキャッシュをそのまま読む。  
ReActの1ステップ内でGoogle APIへの同期的なネットワーク呼び出しを発生させない設計として、  
Tool呼び出しによる応答遅延を避ける。
その代わり、Toolの出力には必ず `fetched_at`（最終取得時刻）を含め、AIが
「この情報は少し古いかもしれない」と判断できるようにする。

---

## 6. キャッシュ仕様

### 6.1 保存場所・削除タイミング

- ファイル: `google_calendar_cache.json`（アプリ実行ディレクトリ直下。`client_secret.json`
  等と同階層）
- 起動時（`GoogleCalendarCollector.__init__`）に既存ファイルがあれば削除してから開始
- 終了時（`myapp.exit()`）にも削除する
- 取得のたびに同一ファイルを上書き（`user_logs/` のような日付別ファイルにはしない。
  ローリングウィンドウの予定情報であり、履歴として残す必要がないため）

### 6.2 取得範囲

- 既定: 本日 −1日 〜 +7日
- 設定可能にする: `ApplicationSettings.GoogleCalendar.FetchRangeDays`（int、既定 `7`）

```python
"GoogleCalendar": {
    "name": "Googleカレンダー連携の詳細設定",
    "type": "section",
    "children": {
        "FetchRangeDays": {
            "name": "予定を取得する日数（本日から先）",
            "type": "int",
            "value": 7
        }
    }
}
```

`services/config_controller.py:get_default_data()` の `ApplicationSettings` に新規セクションとして追加する。

### 6.3 スキーマ
アプリ側（Collector）は取得したGoogle API応答をほぼそのままの形でキャッシュファイルとして残す。
通信用のノイズフィールド（`kind`/`etag`/`htmlLink`/`sequence`/`creator`/`organizer`等）のみ間引き、
`start`/`end`/`recurringEventId`等は元の構造のまま保持する。
LLM向けの抽出・成型（時刻表示への変換、直近±24時間での絞り込み等）はAI_Tools側（10.2章）で行う。

```json
{
  "fetched_at": "2026-08-07T13:05:00+09:00",
  "range": { "from": "2026-08-06", "to": "2026-08-14" },
  "events": [
    {
      "id": "...",
      "status": "confirmed",
      "summary": "定例MTG",
      "description": "",
      "location": "",
      "start": { "dateTime": "2026-08-07T10:00:00+09:00", "timeZone": "Asia/Tokyo" },
      "end":   { "dateTime": "2026-08-07T11:00:00+09:00", "timeZone": "Asia/Tokyo" },
      "recurringEventId": null
    }
  ],
  "tasks": [
    {
      "id": "...",
      "title": "資料作成",
      "notes": "",
      "status": "needsAction",
      "due": "2026-08-08T00:00:00.000Z",
      "completed": null
    }
  ]
}
```

終日イベントの場合、Google側の仕様どおり `start`/`end` は `dateTime` の代わりに
`date`（`"YYYY-MM-DD"`のみ）を持つ。この判定もCollectorでは行わず、Tool側の
`_format_event_time`（10.2章）が担う。`tasks.google.com` を含む`description`の
除外処理も、キャッシュ書き込み時点ではなくTool側の整形時に行う。

---

## 7. AI Tool仕様（概要）

`get_calendar_info_tool.py` は `get_user_activity_summary_tool.py` と同じ構造とし、
**読み取り専用**（キャッシュ更新のトリガーは行わない）とする。

- 引数はなく、直近24時間と今後の24時間、合計48時間分のカレンダー情報を成型して渡す。
- キャッシュが存在しない（未認証・未設定・取得未完了）場合は、その旨を明記した
  固定文言を返す。AIに「機能自体が使えない」ことを伝え、以後同一会話内で
  無駄なTool呼び出しを繰り返させないようにする。
- 権限キーは `tool.name` と一致させる必要があるため、`ApplicationSettings.Permission.get_calendar_info`
  という名前で登録する（`ToolExecutor.init_tools_descriptions()` の仕様どおり）。
- メソッド単位の詳細は10.2章。

---


## 8. 未解決・将来課題

| 項目 | 内容 |
|------|------|
| 日記・日次サマリー統合 | `20250914_ユーザデータ収集機能_要件定義.md` に記載のとおり、23:55の日次サマリー生成とGoogleCalendarの日記生成機能（`GoogleCalendarAPI.py`）を統合するかは別途検討。統合する場合、プロンプト生成の責務は `LLMQueue_設計方針.md` の方針に倣い `AI_Manager._do_summary()` 側に置く。 |
| 既存スクリプトの扱い | `collectors/GoogleCalendarAPI.py` と `GoogleCalendarAPItest.py` はほぼ重複しているため、日記統合に着手する際に一本化する。それまでは手動実行バッチとして現状維持。 |
| ~~複数カレンダー対応~~ | **実装済み。** `calendarList().list()`で`accessRole=="owner"`（マイカレンダー内の全カレンダー）を自動列挙して統合取得するよう変更。共有・購読カレンダー（`accessRole`がowner以外）は既定では含めないが、`ApplicationSettings.GoogleCalendar.CalendarIds`（カンマ区切り）で個別に追加できる。 |
| 認証失敗のUI通知 | 現在は起動時認証失敗をログのみに記録する設計。ポップアップ等でユーザーに知らせるかは未定（`Req_PopUpMessage` イベントの活用を検討）。 |
| 認証毎起動によるUX | 「トークン非保存」により毎起動でブラウザの同意画面が開く。カレンダー連携をオフにしているユーザーには影響しないが、オンにしているユーザーへの体験としては要検証。 |
| Toolからの能動的な取得 | 2章の制約により、Tool呼び出しをトリガーにした同期取得は現設計では行わない。`ToolExecutor`が将来`bus`/`setting`をTool生成時に注入できるように拡張されれば、Tool側から`Req_CalendarInfo`をpublishする形に変更できる。 |
| `_filter_within_window`の幅の設定化 | 現状`hours=24`固定（now基準の前後24h）。now基準のスライド窓なので個人の生活リズム（就寝・起床時刻）による偏りは原理上吸収されるため必須の変更ではないが、「翌日以降の予定をもっと先まで見たい」等のニーズが出た場合は`ApplicationSettings.GoogleCalendar.WindowHours`のような設定項目を追加する。Toolは無引数インスタンス化の制約で`setting`を保持できないため、`services.config_controller.read_configfile("config.json")`をTool内から直接呼んで値を取得する形になる（`user_logs/`をパス直読みする既存Toolと同じパターン）。 |
| その日の活動時間に合わせたタイムテーブル生成 | 将来的に「その日の活動時間（起床〜就寝）」を1単位としたタイムテーブルを生成・保存できるようにしたい。実装時にはUTCとのローカル時差の扱い（Google APIレスポンスは`dateTime`はタイムゾーン付きだが、終日イベントの`date`はタイムゾーンを持たないため注意）、タイムテーブルを生成する目安時刻（例: 1日の終わり・区切りをどの時刻とみなすか）、および「活動日」の区切りを判定するメソッドの設計が必要になる。現行の`_filter_within_window`（now基準±24h）とは別軸の機能になる想定。 |

---

## 11. 実装状況（2026-08-12 追記）

7章・10章の実装中に、当初案から以下の点を変更・拡張した（コードが最新の実態）。

- **Tool出力フォーマット**: 当初の箇条書きテキストから、`services/UserDataLogger.py:_to_markdown_table()`と同じ書式のMarkdownテーブル（予定: 日付/時刻/カレンダー/予定/詳細、タスク: 状態/タスク/期限）に変更。
- **日付の明示**: 前後24hの窓が最大3暦日にまたがるため、時刻(`HH:MM`)だけでは日付が一意に決まらず「前日の予定を当日と誤認する」不具合が実機確認で見つかった。各行に日付列（実日付＋曜日＋今日/昨日/明日の相対ラベル）を持たせ、相対日付の計算はコード側（`_format_date_label`）で確定させてからAIに渡す形にした。
- **複数カレンダー対応**: 8章の課題を前倒しで実装（上表参照）。
- **カレンダー表示名**: `summaryOverride`優先、`primary`カレンダーでリネームされていない場合は生のメールアドレスを渡さず固定の代替名「メインカレンダー」にフォールバックする（`_resolve_calendar_display_name`）。外部AIサービス（Gemini等）にメールアドレスを渡さないための対応。
- **終日イベントの日数判定**: Googleの終日イベントは`end.date`が「最終日の翌日（排他的）」で返る仕様のため、単純な`start_date == end_date`比較では単日イベントを検出できない不具合があった。`end.date`から1日引いた値で単日/複数日を判定するよう修正済み。

## 9. 影響を受けないもの

- `EventBus` 本体（`services/Event_Bus.py`）は変更しない。
- `config.json` のGemini APIキーには触れない。
- `services/UserDataLogger.py` は変更しない（8章の統合が実施されるまで）。

---

## 10. クラス設計・関数責任分担

### 10.1 `collectors/GoogleCalendarCollector.py`

モジュールレベル定数（`GoogleCalendarAPI.py` から移植）:

```python
SCOPES = [
    "https://www.googleapis.com/auth/calendar",
    "https://www.googleapis.com/auth/tasks",
]
CLIENT_SECRET_FILENAME = "client_secret.json"
CACHE_FILENAME = "google_calendar_cache.json"
```

クラス: `GoogleCalendarCollector`

責務は「認証状態の管理」「API呼び出し」「キャッシュファイルの読み書き」の3つに分離する。
`services/WindowsInfoCollecter.py:win_info_collector` と同様に `bus` / `setting` を
コンストラクタで受け取る。

```python
class GoogleCalendarCollector:
    def __init__(self, bus: EventBus, setting: UserSettings, app_dir: str, debug: int = -1):
        ...
```

| メソッド | 引数 | 戻り値 | 責任 |
|---------|------|--------|------|
| `__init__` | `bus, setting, app_dir, debug=-1` | – | `bus`/`setting`/`app_dir`/`cache_path`（`os.path.join(app_dir, CACHE_FILENAME)`）を保持。`auth_state`（`"disabled" \| "not_started" \| "in_progress" \| "authenticated" \| "failed"`）を初期化。`clear_cache()` で起動時キャッシュ削除。`_is_configured()` が真なら `_start_auth_async()` を呼ぶ。 |
| `_is_configured(self) -> bool` | – | bool | `Permission.get_calendar_info` が `True` かつ `client_secret.json` が `app_dir` に存在するかを判定。両方揃わない限り以降のメソッドは何もしない。 |
| `_start_auth_async(self)` | – | – | `_authenticate` を `daemon=True` の別スレッドで起動する。Tkメインループや`myapp.__init__`をブロックしないことだけが責任。 |
| `_authenticate(self, debug=-1)` | – | – | 実際のOAuthフロー（`InstalledAppFlow.from_client_secrets_file` → `flow.run_local_server`）を実行し、`self.calendar_service` / `self.tasks_service` を構築。成功時 `auth_state="authenticated"`、失敗時 `auth_state="failed"` を設定してログ出力。トークンファイルへの書き込みは行わない。`threading.Lock` で多重実行を防止。 |
| `is_available(self) -> bool` | – | bool | `auth_state == "authenticated"` を返すだけの単純な問い合わせ。他メソッドや将来のUI表示から使う。 |
| `refresh_cache(self, debug=-1)` | （`bus.subscribe`のハンドラとして呼ばれる） | – | `Req_CalendarInfo` の購読ハンドラ本体。`is_available()`が偽なら即return。真なら `_fetch_events_and_tasks()` → `_write_cache()` を順に呼ぶだけで、フォーマットや取得範囲計算などの詳細は持たない（オーケストレーションのみ）。 |
| `_fetch_events_and_tasks(self) -> dict` | – | dict | `FetchRangeDays`設定から取得範囲を計算し、`calendar_service.events().list()` と `tasks_service.tasklists()/tasks()` を呼ぶ。取得した生データはフォーマット変換せず、`_trim_event_fields()` / `_trim_task_fields()` でノイズフィールドを間引いた上で6.3のスキーマ（Google生レスポンス構造を保持した形）に沿った `dict` を組み立てて返す。ネットワークI/Oとフィールド選別のみに責任を絞り、時刻表示変換やテキスト整形（旧`_format_event_time`相当）は一切行わない（10.2章のTool側が担う）。 |
| `_trim_event_fields(self, raw_event: dict) -> dict` | – | dict | `id`/`status`/`summary`/`description`/`location`/`start`/`end`/`recurringEventId`のみを残し、`kind`/`etag`/`htmlLink`/`creator`/`organizer`/`sequence`等の通信用ノイズフィールドを除外する純粋関数。 |
| `_trim_task_fields(self, raw_task: dict) -> dict` | – | dict | `id`/`title`/`notes`/`status`/`due`/`completed`のみを残す純粋関数。 |
| `_write_cache(self, data: dict) -> None` | – | – | `data`を`json.dumps`し、一時ファイルへ書いてから`os.replace`で`cache_path`に反映する（Tool側が読んでいる最中に不完全なJSONを掴まないためのアトミック書き込み）。整形・取得ロジックは持たない。 |
| `read_cache(self) -> dict \| None` | – | dict or None | `cache_path`を読み`json.load`する。存在しない/壊れている場合は`None`を返す。`GetCalendarInfoTool`と同じ読み込みロジックを重複させないため、将来的にはTool側からも参照できるよう純粋な読み取り関数として独立させる（ただし2章の制約でTool側からは直接importして使う形になる。10.2参照）。 |
| `clear_cache(self) -> None` | – | – | `cache_path`が存在すれば削除。`__init__`（起動時）と`main.py: myapp.exit()`（終了時）の両方から呼ばれる。 |

### 10.2 `ai_tools/get_calendar_info_tool.py`

クラス: `GetCalendarInfoTool(BaseTool)`

`get_user_activity_summary_tool.py` と同様、コンストラクタ引数を持たず、
ファイルパスは `__file__` からの相対パスで解決する。
6.3章の方針転換（Collectorは生データをそのまま保存）に伴い、時刻表示への変換や
テキスト整形（旧`_format_event_time`相当）はこちらに置く。

| メソッド | 引数 | 戻り値 | 責任 |
|---------|------|--------|------|
| `name`（property） | – | `"get_calendar_info"` | Tool識別子。`Permission.get_calendar_info`と一致させる。 |
| `description`（property） | – | str | AIへのTool説明文。「直近24時間・今後24時間の予定/タスクを確認できる」「情報が古い場合がある」旨を含める。 |
| `args_schema`（property） | – | dict | 引数なし（`{"type": "object", "properties": {}}`）。7章の方針どおり固定で直近±24時間を返す。 |
| `_get_cache_path(self) -> str` | – | str | `os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "google_calendar_cache.json")`。`get_user_activity_summary_tool._get_user_logs_dir()`と同じパターン。 |
| `_load_cache(self) -> dict \| None` | – | dict or None | キャッシュJSONを読み`json.load`。`FileNotFoundError`/`JSONDecodeError`を捕捉して`None`を返す（`GoogleCalendarCollector.read_cache()`とロジックは同じだが、Toolはコレクターを参照できないためファイルI/Oを自前で持つ）。 |
| `_filter_within_window(self, data: dict, hours: int = 24) -> dict` | – | dict | 現在時刻を基準に前後`hours`時間以内に該当する`events`/`tasks`のみを抽出する。`event["start"]`の`date`/`dateTime`、`task["due"]`をパースして判定する（旧`target_date`指定方式は廃止）。 |
| `_format_event_time(self, start: dict, end: dict) -> str` | – | str | `GoogleCalendarAPI.py`の同名メソッドを移植（Collectorではなくこちらに置く）。`start`/`end`の`date`または`dateTime`から終日判定・時刻表示文字列（例:`"10:00-11:00"`）を組み立てる純粋関数。 |
| `_normalize_text(self, text: str) -> str` | – | str | 改行・制御文字の除去、`tasks.google.com`を含む`description`の除外判定を行う（Collectorではなくこちらに置く）。 |
| `_format_text(self, filtered: dict, fetched_at: str) -> str` | – | str | `_format_event_time`/`_normalize_text`を使って`events`/`tasks`を箇条書きテキストに整形し、末尾に「（取得時刻: {fetched_at}）」を付記する。LLMへの返答テキストを組み立てる唯一の場所。 |
| `execute(self, args: Dict[str, Any]) -> str` | `args` | str | オーケストレーションのみ：`_load_cache()`→`None`なら未設定/未認証メッセージを返す→`_filter_within_window()`→`_format_text()`。ネットワークI/Oや認証状態の判断は一切行わない（読み取り専用）。 |

### 10.3 `main.py`（`myapp`クラスへの変更点）

新規クラスは作らず、既存の`myapp`に以下を追加・変更する。

| 箇所 | 変更内容 | 責任 |
|------|---------|------|
| `__init__` | `self.CalendarCollector = GoogleCalendarCollector(self.bus, self.setting, self.app_dir, debug=debug)` を、`self.WinInfo`/`self.UserDataLoger`と同じ並びで追加。 | インスタンス化のみ。他の初期化順序（`bus`/`setting`が先に存在すること）に依存。 |
| `_setup_event_listeners` | `self.bus.subscribe("Req_CalendarInfo", self.CalendarCollector.refresh_cache)` を追加。 | 配線のみ。ハンドラの中身には関与しない（既存方針どおり）。 |
| `update()` | 既存の`mm_now % 5 == 0`ブロック内に、`Permission.get_calendar_info`を確認して`self.bus.publish("Req_CalendarInfo")`を追加する分岐を1つ増やす。 | 5分毎トリガーの発火のみ。既存の`Req_UserActivityLog`発行部分とは独立した`if`文にする（権限が別概念のため）。 |
| `handle_user_message` | 冒頭で`Permission.get_calendar_info`が`True`なら`self.bus.publish("Req_CalendarInfo")`を追加してから、既存の`self.AI_Manager.req_LLM(...)`を呼ぶ。 | 「会話開始タイミングでの非同期更新」の発火のみ。`req_LLM`の呼び出し自体は変更しない。 |
| `exit()` | `self.ui.destroy()`の前後いずれかで`self.CalendarCollector.clear_cache()`を追加。 | 終了時のキャッシュ削除のみ。 |

### 10.4 `services/config_controller.py`

クラス新設なし。`UserSettings.get_default_data()`が返す辞書に8章の2項目
（`Permission.get_calendar_info`、`GoogleCalendar`セクション）を追加するのみ。
既存の`UserSettings`クラスのメソッド（`get_setting_value`等）は変更不要。

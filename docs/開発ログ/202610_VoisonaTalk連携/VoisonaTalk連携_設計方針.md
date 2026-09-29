# VoisonaTalk連携 設計方針

**作成日:** 2026年10月
**対象:** DesktopCharacter / `ui/TTS_VoisonaTalkEngine.py`, `ai/AI_main.py`, `ui/UI_main.py`, `ui/UI_talk.py`, `services/config_controller.py`, `main.py`
**前提:** `202610_VoisonaTalk連携要件定義.md`の決定事項（章番号は同ドキュメントの対応節を指す）

---

## 1. 背景と課題

`202610_VoisonaTalk連携要件定義.md`で「何を・なぜ」は決定済み。本ドキュメントは、実装に必要な「どのファイルに何のクラス・関数を作り、どこが何を呼ぶか」を定義する。既存の`collectors/GoogleCalendarCollector.py`・`ui/TTS_VoiceVoxEngine.py`・`ai/AI_geminiAPI.py`と同じ粒度で、新規ファイルの責任分担・関数シグネチャを明文化する。

### 1.1 モジュール構造の方針
`ui/TTS_VoiceVoxEngine.py`はモジュールレベル関数のみで構成されている。これは VOICEVOX が「base_urlが`localhost:50021`固定・認証なし」で状態を持つ必要がないためであり、そのままVoisonaTalkに当てはめるのは適切ではない。VoisonaTalkは**base_url（ポート可変）＋Basic認証（アカウント情報）**を毎回必要とし、これは既存コードでは`ai/AI_geminiAPI.py:geminiAI`・`ai/AI_ollama.py:ollamaAI`が持つ「`__init__(usersetting, debug)`で設定を一度読み込み、以降はメソッドで使う」パターンに近い。そのため本モジュールは以下のように構成する。

- **プロセス起動・終了**（`start_server`/`kill_server`）: 認証もbase_urlも不要な純粋なローカル操作のため、`TTS_VoiceVoxEngine.py`と同じ**モジュールレベル関数**のままとする。
- **API通信部分**（疎通確認・音声ライブラリ取得・音声合成）: `VoisonaTalkClient`という**クラス**にまとめる。`geminiAI`/`ollamaAI`と同型の`__init__(usersetting, debug=-1)`とし、`base_url`・`auth`・`voice_name`・`voice_version`をインスタンス属性として保持する。
- `ui/UI_main.py:_initialize_tts`は`self.TTS = TTS_VoiceVoxEngine`（モジュール参照）ではなく`self.TTS = VoisonaTalkClient(self.setting, debug=self.debug)`（インスタンス）とする。これは`ai/AI_main.py:AI_Manager._initialize_client`が`self.AI_client = AI_geminiAPI.geminiAI(self.setting, debug=debug)`とするのと同型になる。
- `ai/AI_main.py`側がスタイル名一覧を取得する際も、`VoisonaTalkClient(self.setting)`を都度生成して使う。これは`ui/UI_settings.py`が設定ドロップダウン用に`AI_geminiAPI.geminiAI(self.settings, debug=-1)`・`AI_ollama.ollamaAI(self.settings, debug=-1)`を都度生成しているのと同じ、既存の前例に沿った形である（`AI_Manager`と`UI`はEventBus越しにしか繋がらないため、インスタンスを共有せず、必要な側がそれぞれ生成する）。

---

## 2. 全体アーキテクチャ

### 2.1 起動シーケンス

```
main.py (myapp.__init__)
  └─ ui.start_TTS_Server() … 既存呼び出し箇所（application start → Start_TTS_Server）

ui/UI_main.py: UI.start_TTS_Server()
  └─ engine == "VoisonaTalk" かつ autorun == True の場合
       └─ self.TTS.is_available() で疎通確認（self.TTS は VoisonaTalkClient インスタンス）
            ├─ True  → 何もしない（手動起動済みとして扱う）
            └─ False → TTS_VoisonaTalkEngine.start_server(path, launch_option, debug)  ※モジュール関数
                         └─ threading.Thread(daemon=True) で
                              self.TTS.wait_until_available(...) を実行
                              → タイムアウト時は Req_PopUpMessage ＋ セッション内無効化フラグON
```

### 2.2 発話シーケンス（1件のJSON配列に対して）

```
ai/AI_main.py: AI_Manager._do_response()
  └─ AIバックエンドから応答文字列を取得
  └─ AI_Manager._parse_ai_response(raw_text) … 新規ヘルパー（5章）
       ├─ 成功 → add_talkhistory(raw_json_str) / bus.publish(response_event, {parts:[raw_json_str], segments:[...]})
       └─ 失敗 → bus.publish("Req_PopUpMessage", ...) / bus.publish(response_event, {parts:[...], segments:None, error:"..."})

ui/UI_talk.py: add_log(talkhistory)
  └─ segments があれば Text のみ連結して表示、error があればエラー文言を表示

ui/UI_main.py: Reflect_Text(talk_dict)
  └─ segments を1件ずつ処理
       ├─ update_character_image(Image)
       └─ engine == "VoisonaTalk" の場合:
            self.TTS.text_to_speech(text, emotion, debug)  … self.TTS は VoisonaTalkClient インスタンス
            → 戻り値がエラーを示す場合、Req_PopUpMessage をpublish
```

---

## 3. 新規・変更・関連ファイル一覧

| ファイル | 種別 | 内容 |
|---|---|---|
| `ui/TTS_VoisonaTalkEngine.py` | 新規 | `start_server`/`kill_server`（モジュール関数、プロセス起動・終了）と`VoisonaTalkClient`クラス（API通信一式）の2構成。単体実行時にモデル・スタイル一覧を表示する`__main__`ブロックを含む（11.1節）。 |
| `ai/AI_main.py` | 変更 | `on_settings_updated`にスタイル名一覧のプロンプト注入を追加。`_parse_ai_response`（新規）でJSONパース・検証を共通化し、`_do_response`のReAct分岐・通常分岐の両方から呼ぶ。 |
| `ai/AI_geminiAPI.py` | 変更 | `generation_config`に`response_mime_type`追加。 |
| `ai/AI_ollama.py` | 変更 | `payload`に`format`追加。 |
| `ui/UI_talk.py` | 変更 | `add_log`にsegments/error分岐を追加。 |
| `ui/UI_main.py` | 変更 | `_initialize_tts`・`start_TTS_Server`・`Reflect_Text`にVoisonaTalk分岐を追加。セッション内無効化フラグを保持。 |
| `ui/UI_settings.py` | 変更 | `choice_with_func`の`VoiceSettings.VoisonaTalk.Model`分岐を追加（`VoisonaTalkClient(self.settings).get_voices`にマッピング。疎通確認できない場合はエラー文言を表示）。実装時に判明（当初の要件定義6章のファイル一覧には未記載）。 |
| `services/config_controller.py` | 変更 | `VoiceSettings.engine`選択肢・`VoiceSettings.VoisonaTalk`セクション追加（要件定義5章のスキーマをそのまま反映）。 |
| `main.py` | 変更 | VoisonaTalkプロセスの参照保持、`exit()`での終了処理。 |

---

## 4. 起動・疎通確認仕様

- **疎通確認は`GET /languages`を使う**（レスポンスが軽量で認証確認も兼ねるため）。
- 起動オプションは`start_server`の引数として渡すが、**具体的なオプション名はVoisonaTalk側の対応状況を実装時に確認してから決める**（要件定義4.1.1節・8章）。対応するオプションが不明/存在しない場合は追加引数なしで起動する。
- 疎通確認・起動待ちはいずれもブロッキングI/Oを含むため、`ui/UI_main.py`側から**必ず`threading.Thread(daemon=True)`経由で呼び出す**（Tkメインループをブロックしないため。`collectors/GoogleCalendarCollector._start_auth_async`と同じ考え方）。
- 起動失敗・タイムアウト時は「VoisonaTalk未起動・API無効時のフォールバック」（要件定義4.1.3節）を適用: `UI`インスタンスに`self._voisona_session_disabled = True`をセットし、以後の`Reflect_Text`呼び出しではVoisonaTalkへの呼び出し自体をスキップする。

---

## 5. AI応答パース仕様（AI_main.py）

`AI_Manager`に以下を追加する。

- **`_parse_ai_response(self, raw_text: str, debug=-1) -> dict`**
  1. 正規表現でコードフェンス（`` ```json `` ... `` ``` ``）を除去する。
  2. `json.loads`を試みる。失敗したら`{"ok": False, "error": "invalid_json"}`を返す。
  3. トップレベルがlistであること、各要素が`dict`かつ`"Text"`・`"Image"`キーを持つことを検証する。`"Emotion"`は省略可（省略時は`{}`扱い）。スキーマ不備があれば`{"ok": False, "error": "invalid_schema"}`を返す。
  4. 成功時は`{"ok": True, "raw_text": <整形後のJSON文字列>, "segments": [{"Text":..., "Image":..., "Emotion": {...}}, ...]}`を返す。

- **`_do_response`の変更点**（ReAct分岐・通常分岐とも同じ処理に置き換える）:
  ```python
  parsed = self._parse_ai_response(response["text"], debug)
  if parsed["ok"]:
      output_dict = {"role": "model", "parts": [parsed["raw_text"]],
                      "segments": parsed["segments"], "token_count": response["token_count"]}
      self.add_talkhistory(output_dict, debug)
      self.bus.publish(response_event, output_dict, debug=debug)
  else:
      error_dict = {"role": "model", "parts": [""], "segments": None,
                     "error": "生成に失敗しました。モデルの変更を推奨します。", "token_count": response["token_count"]}
      self.bus.publish(response_event, error_dict, debug=debug)
      self.bus.publish("Req_PopUpMessage", ("error", "AI応答エラー", error_dict["error"]))
  ```
  `add_talkhistory`は失敗時に呼ばない（要件定義4.2.2節の決定どおり）。

- **スタイル名一覧のプロンプト注入**: `on_settings_updated`内、`load_imgs`呼び出しの直後に追加する。
  - `_load_voisona_style_names(self) -> list[str] | None`: `VoiceSettings.engine == "VoisonaTalk"`かつ`Model`（`voice_name=voice_version`形式）が設定されている場合のみ、`VoisonaTalkClient(self.setting).get_voice_detail()`を呼び`style_names`を返す。それ以外は`None`。
  - `None`でなければ、`base_prompt`にスタイル名一覧とEmotionのJSONスキーマ説明（0.00〜1.00・比率合成である旨）を追記する。

---

## 6. Emotion変換仕様

- **`build_style_weights(emotion: dict, style_names: list[str]) -> list[float]`**（モジュールレベルの純粋関数。`VoisonaTalkClient`の外に置き、単体テストしやすくする）
  - `style_names`と同じ長さの配列を`0.0`で初期化する。
  - `emotion`の各キーについて、`style_names.index(key)`が存在すればその位置に値を代入。存在しなければ無視する。
  - 各値は`max(0.0, min(1.0, value))`でクランプする。
  - `emotion`が空/Noneの場合は全`0.0`の配列を返す（呼び出し側で`default_style_weights`にフォールバックするかはTTS呼び出し側の責務とする）。

---

## 7. TTS呼び出しシーケンス仕様

`VoisonaTalkClient.text_to_speech`のオーケストレーション:

1. `build_style_weights(emotion, self.style_names)`
2. `POST /speech-syntheses`（`destination: "memory"`, `language="ja_JP"`, `voice_name`, `voice_version`, `global_parameters.style_weights`）→ `uuid`取得。ネットワークエラー時は`max_retry`回リトライする（`ui/TTS_VoiceVoxEngine.audio_query`と同じ考え方）。400/401/403/409/500/503等のHTTPエラー応答は`{"ok": False, "status_code": ...}`を返す。
3. `GET /speech-syntheses/{uuid}`を`state`が終端（`succeeded`/`failed`、正確な値は9章参照）になるまでポーリング（タイムアウトあり）。
4. `succeeded`なら`GET /speech-syntheses/{uuid}/wav`でWAV取得→`simpleaudio.WaveObject`で再生・`wait_done()`（`ui/TTS_VoiceVoxEngine.text_to_speech`と同じ再生方式）。
5. 成否によらず最後に`DELETE /speech-syntheses/{uuid}`でクリーンアップ（ベストエフォート、例外は握りつぶす）。
6. `{"ok": True}`または`{"ok": False, "status_code": ..., "reason": ...}`を返す。

`bus`は`VoisonaTalkClient`に持たせず、成否は戻り値で表現する。ポップアップ発行の要否は呼び出し元（`ui/UI_main.py:Reflect_Text`、`self.bus`を持つ）が判断する。

---

## 8. エラー通知・状態管理仕様（UI_main.py）

- `UI`クラスに`self._voisona_session_disabled = False`を追加。VoisonaTalk未起動・API無効を検知した時点（4章の起動シーケンス、またはTTS呼び出し時の初回失敗）で`True`にする。
- `Reflect_Text`内、`engine == "VoisonaTalk"`かつ`self._voisona_session_disabled == True`の場合は、`self.TTS`の呼び出し自体をスキップする（ログ出力のみ、要件定義4.1.3節）。
- `text_to_speech`の戻り値が`{"ok": False, ...}`の場合:
  - 初回失敗であれば`self._voisona_session_disabled = True`にし、`Req_PopUpMessage`をpublish。
  - 409 (Conflict)の場合は要件定義4.4.4節どおり都度ポップアップ（`_voisona_session_disabled`はセットしない。輻輳は一時的なものであり機能自体は無効化しないため）。

---

## 9. 未解決・将来課題

| 項目 | 内容 |
|---|---|
| OpenAPIスペックの精査 | 実機Talk API Referenceページ上部の「Download OpenAPI specification」から取得できる正式なスキーマファイルを確認していない（HTMLをタグ除去したテキストからの読み取りのため、`style_weights`の型制約や`state`の全enum値など細部を取りこぼしている可能性がある）。実装着手前にダウンロードして照合する。 |
| 起動オプション名の確定 | VoisonaTalk側にウィンドウ非表示の起動オプションが存在するかは未確認。実装着手時にVoisonaTalk本体のドキュメント・ヘルプを確認する。 |
| OSレベルでのウィンドウ非表示 | 要件定義8章のとおり、起動オプションが効かない場合の代替として`STARTUPINFO`/`SW_HIDE`が候補として残るが、今回は不採用。 |
| `default_style_weights`へのフォールバック | 6章の`build_style_weights`は`Emotion`空時に全`0.0`を返す設計だが、`0.0`配列（＝どのスタイルも適用しない）とライブラリの`default_style_weights`のどちらをAPIに送るべきかは実機で音声への影響を確認して決める。 |
| `state`の全enum値 | 実機Referenceのテキスト抽出では`"queued"`の例しか確認できていない。`running`/`succeeded`/`failed`等の正確な値は上記OpenAPIスペック確認、または`poll_until_done`実装時に実機で確認する。 |
| アカウント情報の実体確認 | 「アカウント情報」がソフトウェアのライセンスアカウントなのか、VoisonaTalk側のAPI設定画面で個別発行するAPIパスワードなのかを実機で確認し、設定UIの文言に反映する。 |

---

## 10. 影響を受けないもの

- `EventBus`本体（`services/Event_Bus.py`）は変更しない。
- `config.json`のGemini APIキーには触れない。
- VOICEVOX／Windows Narratorの既存コードパス（`ui/TTS_VoiceVoxEngine.py`、`ui/TTS_WindowsNarratorManager.py`）は変更しない。`Emotion`フィールドはこの2エンジンでは無視されるのみ。

---

## 11. クラス設計・関数責任分担

### 11.1 `ui/TTS_VoisonaTalkEngine.py`

モジュールレベル定数:
```python
DEFAULT_PORT = 32766
```

**モジュールレベル関数**（プロセス管理。認証・base_urlは不要）

| 関数 | 引数 | 戻り値 | 責任 |
|---|---|---|---|
| `start_server` | `path, launch_option=None, debug=-1` | `subprocess.Popen \| None` | プロセス起動のみ。疎通確認・待機は行わない。`launch_option`はウィンドウ非表示要求用（未確定、9章参照）。実装時点で`ui/UI_main.py`からは`launch_option`を渡さずに呼んでおり、常にウィンドウ表示ありで起動する。 |
| `kill_server` | `process, debug=-1` | `None` | プロセス終了（terminate→timeout待ち→kill）。`ui/TTS_VoiceVoxEngine.kill_server`と同じ実装。 |
| `_test_launch` | `path, startupinfo=None, wait_seconds=8, debug=-1` | `int \| None` | `test_hidden_launch`/`test_windowed_launch`の共通処理。指定した`startupinfo`で起動→ウィンドウ生成待ち→可視ウィンドウ数の確認→`kill_server`での後始末までを行い、可視ウィンドウ数を返す（起動自体に失敗、または起動直後にプロセスが終了した場合は`None`）。 |
| `test_hidden_launch` | `path, wait_seconds=8, debug=-1` | `bool` | `_test_launch`に`STARTF_USESHOWWINDOW`＋`SW_HIDE`の`STARTUPINFO`を渡して非表示起動を試す。要件定義8章「OSレベルでのウィンドウ非表示処理」の検証用。 |
| `test_windowed_launch` | `path, wait_seconds=8, debug=-1` | `bool` | `_test_launch`に`startupinfo=None`（通常起動）を渡す比較用テスト。`test_hidden_launch`の結果が「起動失敗」なのか「起動はできているがSW_HIDEだけ効いていない」のかを切り分けるために追加。 |

`test_hidden_launch`／`test_windowed_launch`はいずれも**単体実行専用**（`__main__`ブロック内。VSCode等のデバッガから直接このモジュールを実行する運用を想定し、コマンドライン引数ではなく`__main__`内の`RUN_HIDDEN_LAUNCH_TEST`/`RUN_WINDOWED_LAUNCH_TEST`定数で実行有無を切り替える）で、`start_server`／通常の起動フローからは呼ばない。

**`VoisonaTalkClient`クラス**（API通信。`ai/AI_geminiAPI.py:geminiAI`と同型）

```python
class VoisonaTalkClient:
    def __init__(self, usersetting: UserSettings, debug: int = -1):
        # base_url, auth(email, password), voice_name, voice_version, style_names をここで解決・保持
```

| メソッド | 引数 | 戻り値 | 責任 |
|---|---|---|---|
| `__init__` | `usersetting, debug=-1` | – | `VoiceSettings.VoisonaTalk`から`port`・`account_email`・`account_password`・`Model`（`voice_name=voice_version`形式、`.split("=")`で分解）・`speed`を読み込み、`self.base_url`・`self.auth`・`self.voice_name`・`self.voice_version`・`self.speed`を保持。`speed`はAPI仕様の`minimum:0.2`/`maximum:5`でクランプし、値が不正な場合は既定値`1.0`にフォールバックする（`config.json`の手編集等による不正値を許容するため）。**続けて`self.get_voice_detail()`を呼び`self.style_names`を即時取得する**（コンストラクタ内、`ollamaAI.__init__`が`test_connection`を`debug>=0`時に呼ぶのと同様の即時初期化）。VoisonaTalk未起動等で取得に失敗した場合は`self.style_names = None`のまま保持し、例外は投げない。 |
| `is_available` | `timeout=3, debug=-1` | `bool` | `GET /languages`を呼び200なら`True`。 |
| `wait_until_available` | `timeout_seconds=30, interval=1.0, debug=-1` | `bool` | `is_available`を`interval`秒間隔でポーリング。 |
| `get_voices` | `debug=-1` | `list[str] \| None` | `GET /voices`を呼び、`ui/TTS_VoiceVoxEngine.get_speakers()`と同じ契約で**表示用に整形済みの文字列リスト**（例: `"田中傘 (tanaka-san_ja_JP / 2.0.1)=tanaka-san_ja_JP=2.0.1"`）を返す。設定UIの`choice_with_func`はこの戻り値をそのまま`combobox['values']`に使え、選択後は`.split("=")`で`voice_name`/`voice_version`を取り出す。生データの`dict`が別途必要な場面はない想定のため、`list[dict]`は返さない。 |
| `get_voice_detail` | `voice_name=None, voice_version=None, debug=-1` | `dict \| None` | `GET /voices/{voice_name}/{voice_version}`（引数省略時は`self.voice_name`/`self.voice_version`を使う）。`style_names`・`default_style_weights`を含む生データの`dict`を返す（UIの選択肢用ではなく、プログラム内部で使うため整形しない）。引数省略呼び出し（＝自分自身の設定に対する呼び出し）で成功した場合のみ`self.style_names`を更新する。 |
| `get_default_audio_device` | `debug=-1` | `dict \| None` | `GET /audio-devices/default`（参考情報、必須ではない）。 |
| `text_to_speech` | `text, emotion, max_retry=20, debug=-1` | `dict`（`{"ok": bool, ...}`） | 7章のオーケストレーション。呼び出し時点で`self.style_names`が`None`（コンストラクタ時点で未起動だった等）であれば、まず`self.get_voice_detail()`を再試行する。それでも`None`なら`Emotion`を適用せず`style_weights`を送らずに合成する。**`global_parameters.speed`には`Emotion`・`style_names`の有無、文章量、選択中の音声ライブラリに関わらず常に`self.speed`を設定する**（設定UIで決めた値を一律適用。要件定義8章「読み上げ速度」参照）。内部で`_request_speech_synthesis`・`_poll_until_done`・`_get_wav`・`_delete_request`（いずれも`self`のprivateメソッド）を呼ぶ。`max_retry`は`ui/TTS_VoiceVoxEngine.text_to_speech`の`max_retry`引数と同じ役割（HTTP呼び出しのリトライ回数）。 |

**モジュールレベルの純粋関数**

| 関数 | 引数 | 戻り値 | 責任 |
|---|---|---|---|
| `build_style_weights` | `emotion: dict, style_names: list[str]` | `list[float]` | 6章。名前付きEmotion→配列変換。`VoisonaTalkClient`の状態に依存しないため独立させ、単体テスト可能にする。 |

**単体動作確認（`if __name__ == "__main__":`ブロック）**

`ui/TTS_VoiceVoxEngine.py`末尾の`get_speakers()`／`text_to_speech()`呼び出しと同じ位置づけで、本ファイル単体を`python ui/TTS_VoisonaTalkEngine.py`のように直接実行した際に、**音声ライブラリ（モデル）とその配下のスタイル一覧を一覧表示する**確認コードを追加する。自動テストではなく、`services/config_controller.py`の`config.json`から設定を読み込んだ`VoisonaTalkClient`を使い、実機のVoisonaTalk（起動・API有効化済み）に対して疎通確認する手動検証スクリプトとする。

```python
if __name__ == "__main__":
    # このプログラムのみの動作確認: モデル(音声ライブラリ)とスタイル一覧を表示
    # 実行にはVoisonaTalkアプリが起動しAPIが有効になっている必要がある
    from services.config_controller import read_configfile

    # UserSettings()単体では_settings_mapが空のまま（get_setting_valueが全て参照エラーになる）ため、
    # main.pyと同じくread_configfile("config.json")でデフォルト値＋config.jsonをマージしたインスタンスを使う。
    setting = read_configfile("config.json")
    client = VoisonaTalkClient(setting, debug=0)

    if not client.is_available(debug=0):
        print("VoisonaTalk APIに接続できません。起動・API設定・認証情報を確認してください。")
    else:
        # get_voices()はVOICEVOXのget_speakers()と同じ契約で、
        # "表示名 (voice_name / voice_version)=voice_name=voice_version" 形式の文字列リストを返す（4章参照）。
        voices = client.get_voices(debug=0) or []
        for v in voices:
            display_part, voice_name, voice_version = v.split("=")[0], v.split("=")[-2], v.split("=")[-1]
            print(f"{display_part}  (voice_name={voice_name}, voice_version={voice_version})")
            detail = client.get_voice_detail(voice_name, voice_version, debug=0)
            if detail:
                print(f"  styles: {detail.get('style_names')}")
```

7章の「テスト観点」チェックリスト（要件定義側）における「設定UIでVoisonaTalkの音声ライブラリ一覧が正しく取得・選択できること」の確認は、設定UIを介さずこのスクリプト単体でも先に検証できる。

### 11.2 `ai/AI_main.py`（`AI_Manager`への追加）

| メソッド | 引数 | 戻り値 | 責任 |
|---|---|---|---|
| `_parse_ai_response` | `raw_text: str, debug=-1` | `dict` | 5章のJSONパース・検証。コードフェンス除去含む。 |
| `_load_voisona_style_names` | – | `list[str] \| None` | `VoiceSettings.engine=="VoisonaTalk"`時のみ`VoisonaTalkClient(self.setting).get_voice_detail()`を呼びスタイル名を返す。 |
| `on_settings_updated`（変更） | `new_settings` | – | `load_imgs`と同様の箇所で`_load_voisona_style_names`を呼び、`base_prompt`にスタイル名一覧とEmotionスキーマ説明を追記。 |
| `_do_response`（変更） | 既存シグネチャ | – | `_parse_ai_response`の結果で分岐（5章のコード例）。ReAct分岐・通常分岐の両方から共通で呼ぶ。 |

### 11.3 `ui/UI_main.py`（`UI`クラスへの変更）

| 箇所 | 変更内容 |
|---|---|
| `__init__` | `self._voisona_session_disabled = False`、`self.voisona_process = None`を追加。 |
| `_initialize_tts` | `engine == "VoisonaTalk"`分岐を追加し`self.TTS = VoisonaTalkClient(self.setting, debug=self.debug)`（インスタンス化。`AI_Manager._initialize_client`と同型）。 |
| `start_TTS_Server` | 4章の起動シーケンスを追加（`threading.Thread`経由）。 |
| `Reflect_Text` | `segments`を1件ずつ処理する形に書き換え、`engine=="VoisonaTalk"`時は`self.TTS.text_to_speech(text, emotion, debug=debug)`を呼び、戻り値に応じて8章のエラー処理を行う。`talk_dict.get("error")`がある場合はTTS呼び出し自体を行わない。 |

### 11.4 `ui/UI_talk.py`（`add_log`の変更）

| 分岐 | 表示内容 |
|---|---|
| `role=="user"` | 既存どおりプレーンテキスト表示。 |
| `role=="model"`かつ`segments`あり | `segments`の`Text`を連結して表示。 |
| `role=="model"`かつ`error`あり | 「[ 出力エラー ]」等のプレフィックス＋`error`の文言を表示。 |

### 11.5 `services/config_controller.py`

クラス新設なし。`get_default_data()`に要件定義5章のスキーマ（`Model`は`voice_name=voice_version`形式の1項目）をそのまま追加する。

### 11.6 `main.py`（`myapp`クラスへの変更）

| 箇所 | 変更内容 |
|---|---|
| `__init__` | `self.voisona_process`の保持場所を`ui.voisona_process`経由で参照できるようにする（VOICEVOXの`engine_process`と同様、実体は`UI`側が保持）。 |
| `exit` | `engine=="VoisonaTalk"`かつ`ui.voisona_process`が自アプリ起動由来の場合、`TTS_VoisonaTalkEngine.kill_server(ui.voisona_process)`を呼ぶ。 |

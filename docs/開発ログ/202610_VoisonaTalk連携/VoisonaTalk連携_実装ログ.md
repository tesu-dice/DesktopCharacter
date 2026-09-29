# VoisonaTalk連携 実装ログ

**対象:** `ai/AI_main.py`, `ai/AI_geminiAPI.py`, `ai/AI_ollama.py`, `ui/UI_main.py`, `ui/UI_talk.py`, `ui/UI_settings.py`, `ui/TTS_VoisonaTalkEngine.py`, `services/config_controller.py`, `main.py`
**参照:** `202610_VoisonaTalk連携要件定義.md`, `VoisonaTalk連携_設計方針.md`（両ファイルとも実装中に判明した差分を随時反映済み）

このファイルは、要件定義・設計方針に基づく実装作業の中で実機検証を通じて判明した事象・原因・対応を時系列で記録する。方針ファイル自体の記述は本ログの内容を踏まえて修正済みのものもあるため、最新の正とする情報は要件定義／設計方針側を参照し、本ログは「なぜそうなったか」の経緯記録として使う。

---

## 1. 概要（実装したファイル）

| ファイル | 種別 | 内容 |
|---|---|---|
| `ui/TTS_VoisonaTalkEngine.py` | 新規 | `start_server`/`kill_server`/`test_hidden_launch`、`VoisonaTalkClient`クラス（`speed`対応含む）、`build_style_weights`、単体確認用`__main__`（`--test-hidden-launch`オプション対応） |
| `services/config_controller.py` | 変更 | `VoiceSettings.engine`に`"VoisonaTalk"`追加、`VoiceSettings.VoisonaTalk`セクション（`speed`含む）追加、`SettingItem`に`"float"`型を新設 |
| `ai/AI_geminiAPI.py` | 変更 | `response_mime_type`/`response_schema`によるJSON構造の強制 |
| `ai/AI_ollama.py` | 変更 | `format`にJSON Schemaを渡すことによるJSON構造の強制 |
| `ai/AI_main.py` | 変更 | `base_prompt`のJSON配列スキーマ化、VOISONAスタイル名注入、`_parse_ai_response`によるパース・検証、`_initialize_client`でのスキーマ用スタイル名受け渡し |
| `ui/UI_talk.py` | 変更 | `add_log`のsegments/error分岐対応 |
| `ui/UI_main.py` | 変更 | VoisonaTalk起動シーケンス、`Reflect_Text`のsegments対応 |
| `ui/UI_settings.py` | 変更（当初のファイル一覧に記載漏れ） | `VoiceSettings.VoisonaTalk.Model`の`choice_with_func`マッピング追加、`"float"`型の入力欄・保存時クランプ処理追加 |
| `main.py` | 変更 | `exit()`でのVoisonaTalkプロセス終了処理 |

---

## 2. 実機検証で判明した事象と対応

### 2.1 単体実行時に`services`がimportできない（2026-09-24）
**事象:** `python ui/TTS_VoisonaTalkEngine.py`のように直接実行すると`ModuleNotFoundError: No module named 'services'`。
**原因:** 直接実行時は`sys.path[0]`が`ui/`になり、兄弟パッケージの`services`が見つからない。
**対応:** 既存の`ai_tools/tools_main.py`・`services/speech2text.py`と同じ「`__main__`ブロック内でプロジェクトルートを`sys.path`に追加する」パターンを`TTS_VoisonaTalkEngine.py`にも適用。`python ui/TTS_VoisonaTalkEngine.py`・`python -m ui.TTS_VoisonaTalkEngine`のどちらでも動作することを確認。

### 2.2 設定UIでVoisonaTalkの音声ライブラリ一覧取得に失敗（2026-09-24）
**事象:** 設定UIで「VoisonaTalk APIへの接続が行えず、項目の取得に失敗しました」。
**調査:** `curl`で`http://localhost:32766/api/talk/v1/languages`を直接叩いたところ、`401 Unauthorized`（サーバー自体は生きている）。config.json記載のメール・パスワードで`requests`から叩いても401。
**原因:** VoisonaTalkアプリのログイン用アカウント情報と、Talk API用のBasic認証情報が別物だった（設計方針9章の未解決課題「アカウント情報の実体確認」が実際に顕在化）。
**対応:** VoisonaTalkアプリ側のAPI設定画面で発行されるAPI専用の認証情報を設定UIに入力し直すことで解決（コード側の修正は不要だった）。

### 2.3 `GET /voices`のレスポンス形式が想定と異なる（2026-09-24）
**事象:** 認証成功後、`get_voices()`が`AttributeError: 'str' object has no attribute 'get'`で例外。
**調査方法:** ユーザーの指示により、`get_voices`/`get_voice_detail`に`debug>=0`時のみ生JSONをそのままprintする処理を追加し、`__main__`ブロック（`debug=0`）経由で実機の生レスポンスを確認。
**判明した実際のレスポンス形状**（設計時の想定と異なっていた2点）:
1. トップレベルは配列そのものではなく`{"items": [ ... ]}`でラップされている。
2. 各要素の`display_names`は`[{"language": "ja_JP", "name": "..."}, {"language": "en_US", "name": "..."}]`という言語別オブジェクトの配列。
3. （想定通りだった点）`GET /voices/{voice_name}/{voice_version}`の`style_names`・`default_style_weights`はフラットな配列で、補正不要だった。
**対応:** `get_voices()`で`raw_json.get("items", [])`を経由するよう修正し、`_extract_display_name()`を言語別オブジェクト配列に対応させた。修正後、実機の2音声ライブラリ（田中さん／LeuR）とスタイル一覧が正しく取得できることを確認。デバッグ用の生JSON print処理はそのまま常設（`debug>=0`時のみ）とし、今後同種の形式ずれの調査に使えるようにしている。

### 2.4 Emotionの「0.00は省略可」指示を撤回（2026-09-24）
**経緯:** 当初「未指定スタイルは自動的に0.00として扱われるので書かなくてよい」という指示にしていたが、この省略可ルールがLLMのJSON生成を不安定にする一因になり得ると判断し、「注入したスタイル名一覧の全スタイルを、使用しないものも含めて必ず明記する」指示に変更（`ai/AI_main.py:on_settings_updated`）。選択中ライブラリの実際のスタイル名から動的に生成した記載例（1つ目のスタイルのみ1.00、残りは全て0.00）をプロンプトに追加。
**補足:** `ui/TTS_VoisonaTalkEngine.py:build_style_weights`自体は、`Emotion`に含まれなかったスタイルを`0.0`として扱うフォールバックを引き続き保持している（AIの出力漏れ・スキーマ逸脱に対する安全網）。プロンプト上でAIに求めるルールと、コード側の安全網は別レイヤーとして両立させている。

### 2.5 Ollama（ローカルモデル）でJSON生成エラー（2026-09-24）
**事象:** 2.4の修正後も生成エラー（ポップアップ「生成に失敗しました。モデルの変更を推奨します。」）が発生。
**調査:** `application.log`を確認したところ、
```
_parse_ai_response: トップレベルがlistではありません。type=<class 'dict'>
raw_text={"Text": "...", "Image": "SD等身_関心.png", "Emotion": {"Happy": 0.80, "Normal": 0.20}}
```
セリフ1件のみの応答で、AIがJSON配列`[{...}]`ではなくオブジェクト`{...}`をトップレベルに直接返していた。`Emotion`の値自体は正しい形式であり、スタイルパラメータの変換とは無関係の失敗だった。
**原因の切り分け:** 使用中のOllamaモデルが`hf.co/unsloth/Qwen3.6-35B-A3B-GGUF:UD-IQ1_M`（35B MoEを実質1bit級の`IQ1_M`まで量子化）であることを確認。この強い量子化は構造化出力・指示追従性能を大きく劣化させることが知られており、プロンプトの文章指示（「必ず配列にする」等）だけでは安定して守らせるのが難しいと判断。
**暫定対応:** GeminiAPIに切り替えたところ正常に動作することをユーザーが確認。ただし恒常的な対策として、プロンプトの文章指示だけに頼らずJSON Schemaでの構造強制を行う方針に変更（3章）。

---

## 3. JSON Schemaによる構造強制の追加（2026-09-24）

### 3.1 方針
プロンプトの文章指示（「必ず配列にする」「全スタイルを明記する」等）だけでは、性能の低いモデル（特に強く量子化されたローカルモデル）でJSON構造を安定して守らせるのが難しいことが2.5で分かったため、両バックエンドともAPI側の構造化出力機能（Gemini: `response_schema`、Ollama: `format`へのJSON Schema指定）で配列・必須キーを強制するように変更した。プロンプトの文章指示は维持しつつ、構造面はAPI側の制約でも二重に担保する形。

### 3.2 実機検証（Gemini）
`google-generativeai` 0.8.5の`GenerationConfig.response_schema`は`protos.Schema | Mapping[str, Any] | type`を受け付け、小文字の`"type": "string"/"object"/"array"`を使ったプレーンなdictをそのまま渡せることを確認。

- **`additionalProperties`は未対応。** `Emotion`に`{"type": "object", "additionalProperties": {"type": "number"}}`を渡すと`ValueError: Unknown field for Schema: additionalProperties`で例外になる。
- **`properties`を空にした`{"type": "object"}`は通るが、モデルが常に空の`Emotion: {}`を返す。** スキーマに列挙されていないキーをモデルが自発的に埋めることはない（プロンプト側の指示より、スキーマの`properties`列挙が優先される）。
- そのため、`Emotion`の`properties`に実際のスタイル名を明示的に列挙する必要がある。実機で`{"Normal": {"type":"number"}, "Happy": {"type":"number"}}`を指定したところ、`Emotion`に正しく`{"Happy": 0.8, "Normal": 0.2}`のような値が入ることを確認。

この結果を踏まえ、`ai/AI_geminiAPI.py`に`_build_response_schema(style_names)`を追加し、`AI_Manager._initialize_client`から取得した現在選択中のVOISONAスタイル名一覧を渡してスキーマを動的に構築するようにした（VoisonaTalk未使用時・スタイル名未取得時は`Emotion: {"type": "object"}`のみのゆるいスキーマにフォールバック）。

### 3.3 実機検証（Ollama）
Ollama 0.34.3にて`/api/chat`の`format`に文字列`"json"`ではなくJSON Schemaオブジェクトを渡せることを確認（即時400エラーにはならず受理される）。`ai/AI_ollama.py`にも`AI_geminiAPI.py`と同型の`_build_response_schema(style_names)`を追加し、`payload["format"]`に渡すよう変更した。

実機の`hf.co/unsloth/Qwen3.6-35B-A3B-GGUF:UD-IQ1_M`（生成が非常に低速）に対し、`Emotion`のプロパティに`Normal`/`Happy`を指定したスキーマで実際にリクエストしたところ、以下のように**トップレベルが正しく配列**になったレスポンスが返ってきた（ステータス200）。

```json
[
  {
    "Image": "img_001_random",
    "Text": "（自己紹介のセリフ）",
    "Emotion": {
      "Normal": 0.85
    }
  }
]
```

2.5節で発生していた「トップレベルがオブジェクトになる」問題は、スキーマ制約によって解消されることを確認した。なお`Emotion`に`Happy`が含まれていない（`properties`に列挙してあっても`required`にしていないため許容される）等、内容面の精度はモデルの性能に依存し引き続き完全ではないが、`_parse_ai_response`が弾く原因だった「トップレベルがlistでない」という構造面の失敗は解消される。

### 3.4 コード変更点まとめ（初期実装、3.5節で修正）
- `ai/AI_geminiAPI.py` / `ai/AI_ollama.py`: `_build_response_schema(style_names=None)`（両ファイルにほぼ同じ内容で個別実装。既存の「バックエンドごとに独立実装し共通基底クラスは持たない」という既存方針に合わせた）。
- `geminiAI.__init__` / `ollamaAI.__init__`: `style_names`引数を追加（デフォルト`None`、後方互換）。`ollamaAI`は`self.response_schema`をインスタンス属性として保持し、`response()`内で`payload["format"]`に使用。
- `ai/AI_main.py:_initialize_client`: `self._load_voisona_style_names(debug)`を呼び、その結果を`AI_client`のコンストラクタに渡すよう変更。`on_settings_updated`側でプロンプト注入用に同関数をもう一度呼んでいるため、設定更新のたびにVoisonaTalk APIへの問い合わせが2回（スキーマ用・プロンプト注入用）発生する。頻度は起動時・設定適用時のみで低頻度のため、現時点では許容している。

**この時点の実装には重大な問題があった**（3.5節参照）: スキーマをモデル／`payload`レベルに恒久的に焼き込んでいたため、同じ`AI_client`インスタンスを使い回す`_do_summary()`（要約生成）・`react_planing()`のThoughtステップ（ツール選択用の別形式JSON）にまで無差別に適用されてしまっていた。

### 3.5 スキーマ適用範囲の是正（2026-09-24、ユーザー指摘により発覚）

**発覚の経緯:**
1. ユーザーが要約機能の動作確認中、要約結果にJSON形式の出力が混ざることを発見。`application.log`で`_do_summary`の呼び出しがText/Image/Emotionスキーマを継承していたことを確認。
2. 修正直後、別件で「テキスト生成時のトークン数が4万になっている」という報告があり、調査の結果`react_planing()`のThoughtステップ（本来`{"tools":[...],"response":"..."}`という別形式JSONを期待する）にも同じスキーマが誤って強制されており、モデルが指示の矛盾（自然文プロンプト vs 強制スキーマ）で出力が不安定・長大化していたことが同一原因と判明。

**修正内容（最終形）:**
- `geminiAI.__init__`: モデルに焼き込む既定の`generation_config`を`response_mime_type: "text/plain"`（プレーンテキスト）に戻した。JSON用の設定は`self._json_generation_config`として別途保持するのみに変更。
- `geminiAI.response(self, input_contents, response_format=None, debug=-1)`: `response_format="json"`が明示された場合のみ、`generate_content(..., generation_config=self._json_generation_config)`のように呼び出し単位でJSON Schemaを上書き適用する。指定がなければプレーンテキストのまま。
- `ollamaAI.response(self, input_contents, image_path=None, response_format=None, debug=-1)`: 同様に`response_format="json"`のときだけ`payload["format"] = self.response_schema`を設定する（それ以外は`format`キー自体を含めない）。
- `ai/AI_main.py`: `_do_response()`の通常応答分岐と`character_response()`の2箇所だけに`response_format="json"`を追加。`_do_summary()`と`react_planing()`のThoughtステップは変更せず（=プレーンテキストのまま）。

**検証結果:** `ReAct_response=True`の状態で実際に発話→ReAct思考→キャラクター応答の一連の流れを実行し、Thoughtステップが1回のループで正しく収束（`{"response": "..."}`形式）、最終応答も正しいJSON配列形式、`token_count: 3930`（正常範囲）であることを確認。要約機能側も、プレーンテキストの要約プロンプトに対してJSON配列を含まない素のテキストが返ることを実機確認済み。

**教訓:** クライアントの生成設定（`generation_config`/`payload`のデフォルト）に用途固有の制約を焼き込むと、同じクライアントインスタンスを使い回す他の呼び出し（要約・ReAct思考など、フォーマットの異なる用途）を意図せず巻き込む。構造化出力のような「特定の呼び出しだけに必要な制約」は、クライアント初期化時ではなく呼び出し単位（`response()`の引数）で明示的に指定する設計にすべきだった。[[feedback_llm_structured_output]]にも追記。

---

## 5. OSレベル非表示起動テスト・読み上げ速度設定の追加（2026-09-24）

### 5.1 OSレベル非表示起動のテスト関数
`ui/UI_main.py:_start_voisona_server`は実際には`launch_option`を渡さずに`start_server`を呼んでおり、現状VoisonaTalkは常にウィンドウ表示ありで起動する（VoisonaTalk側の非表示専用オプション名は未確定のまま、要件定義4.1.1節・8章のフォールバック）。

要件定義8章の「OSレベルでのウィンドウ非表示処理」（`STARTUPINFO`/`SW_HIDE`）が実際に効くかを検証するため、`ui/TTS_VoisonaTalkEngine.py`に`test_hidden_launch(path, wait_seconds=8, debug=-1)`を追加した。`subprocess.STARTUPINFO`＋`SW_HIDE`で起動し、`win32gui.EnumWindows`／`win32process.GetWindowThreadProcessId`でそのプロセスに属する可視ウィンドウの有無を実際に確認する（目視ではなく自動判定）。**単体実行専用**とし、`start_server`や通常の起動フローからは呼ばれないようにした（新規にVoisonaTalkプロセスを起動する破壊的な処理のため）。

**追記（2026-09-24、比較用テストの追加と実機検証結果）:**
- ユーザーが単体テスト（VSCodeのデバッガから直接このモジュールを実行する運用）で非表示起動を試したところ、期待通りに動かなかった。共通処理を`_test_launch(path, startupinfo, wait_seconds, debug)`に切り出し、`test_hidden_launch`に加えて**比較用の`test_windowed_launch`（通常＝ウィンドウ表示ありでの起動）を追加**し、両方の結果を突き合わせて「起動自体が失敗しているのか」「SW_HIDEだけが効いていないのか」を切り分けられるようにした。
- **単体テストの起動方法もコマンドライン引数（`--test-hidden-launch`）からハードコーディングの定数（`__main__`内の`RUN_HIDDEN_LAUNCH_TEST`/`RUN_WINDOWED_LAUNCH_TEST`）に変更した。** ユーザーの実際の運用（VSCodeでこのファイルをデバッグ実行）はコマンドライン引数を渡す想定ではないため。
- 実機で両テストを実行した結果: **非表示起動テストも通常起動テストも、起動処理自体は正常終了（クラッシュなし）。ただし非表示起動テストでも可視ウィンドウが1個検出され、SW_HIDEは効かないことを確認した。** 通常起動テストでは想定通り可視ウィンドウが検出されており、テストコード自体の不備ではないことを確認済み。VoiSona Talk.exeはWPF系アプリと見られ、起動時に自前でウィンドウ表示処理を行い、親プロセスが渡した`STARTUPINFO`の初期表示状態を上書きしていると考えられる。要件定義8章に「効果なしと判明」として反映済み。

### 5.2 読み上げ速度（`speed`）の設定項目化
**実機確認方法の反省点:** 当初`talk_api.html`をHTMLタグ除去で読んでいた際は`<script>`タグごと除去していたため、Redocが埋め込むOpenAPIスキーマ本体（`speed`の`minimum`/`maximum`等）が見えていなかった。`grep`で`<script>`を残したまま生HTMLを検索し直したところ、
```
"speed":{"type":"number","description":"...","default":1,"minimum":0.2,"maximum":5}
```
という正式な制約を発見した（`pitch`は`minimum:-600, maximum:600`）。**HTMLタグ除去だけに頼ると、Redoc系のAPIリファレンスに埋め込まれた実際のスキーマ制約を見落とす**ことが分かったため、今後同様の調査をする際は生HTML（`<script>`込み）も確認する。

**実装:**
- `services/config_controller.py`: `SettingItem`に`"float"`型を新設（`"int"`型と同じ`min`/`max`クランプの仕組みを流用、`set_setting_value`に分岐追加）。`VoiceSettings.VoisonaTalk.speed`（`min:0.2, max:5, value:1.0`）を追加。
- `ui/UI_settings.py`: `"float"`型の入力欄（`"int"`と同じくEntry+StringVar）と、`save_and_apply_settings`での`float()`変換・クランプ処理を追加。
- `ui/TTS_VoisonaTalkEngine.py`: `VoisonaTalkClient.__init__`で`speed`設定を読み込み、`SPEED_MIN`/`SPEED_MAX`（0.2/5.0）でクランプして`self.speed`に保持（不正値は既定`1.0`にフォールバック）。`text_to_speech`は`Emotion`・`style_names`の有無や文章量、音声ライブラリに関わらず**常に**`global_parameters.speed`に`self.speed`を送るよう変更（ユーザーの要望どおり一律適用）。
- 実機（`speed=1.6`）で発話テストを行い、正常に合成・再生されることを確認済み（`{"ok": True}`）。テスト中に数回接続リトライが発生したが、最終的に成功しており一時的な接続の詰まりだったと考えられる。

---

## 6. 未解決・今後の課題

| 項目 | 内容 |
|---|---|
| スキーマとプロンプト文章指示の二重管理 | Emotionの「全スタイル明記」ルールは、スキーマの`properties`列挙（構造強制）とプロンプト文章（内容の指示）の両方で表現している。スタイル名一覧が変わった場合、両方が連動して更新されることを実装（`_load_voisona_style_names`の共通利用）で担保しているが、スキーマ生成ロジックが2ファイルに重複している点は将来的に整理の余地がある。 |
| VoisonaTalk API問い合わせの重複 | 上記3.4のとおり、設定更新のたびに`_load_voisona_style_names`が2回呼ばれる。低頻度の操作のため現状は未対応。 |
| 低量子化ローカルモデルでの内容精度 | 3.3節の実機テストでは構造（配列であること）は解消されたが、`Emotion`に本来指定してほしいスタイルの一部が欠落するなど内容面の精度はモデル性能に依存する。`build_style_weights`側のフォールバック（未指定スタイルは0.0）で実害は抑えられるが、根本的にはモデル側の性能向上・量子化レベルの見直しが必要。 |
| OSレベル非表示起動テストの結果確認 | 5.1節の`test_hidden_launch`はユーザーが後日実行して結果を確認する予定。結果次第で要件定義4.1.1節の起動方針（起動オプション要求のみ）を見直すかどうかを判断する。 |
| `pitch`・`intonation`・`huskiness`・`alp`の扱い | 5.2節で存在が判明した他のglobal_parametersは今回未対応のまま。ユーザーからの要望があれば`speed`と同様の方式（設定UI項目＋実機スキーマのmin/max）で追加する。 |

# VoisonaTalk連携 要件定義

**対象:** DesktopCharacter / `ai/AI_main.py`, `ai/AI_geminiAPI.py`, `ai/AI_ollama.py`, `ui/UI_main.py`, `ui/UI_talk.py`, `services/config_controller.py`, `main.py`

## 1. 目的・要件

キャラクターの読み上げエンジンとして、既存のVOICEVOX／Windows Narratorに加えて **VoisonaTalk API** を追加する。VoisonaTalkは感情（スタイル）を数値パラメータとして指定できるため、これに合わせてAIの応答生成フォーマット自体も見直す。

- VoisonaTalk APIを使ったText2Speech機能の追加
- 起動時にVoisonaTalkアプリをバックグラウンドで起動する（詳細は4.1節）
- 設定項目: VoisonaTalkアプリの実行パス、APIポート番号、アカウント情報（メールアドレス）、アカウントパスワード、音声ライブラリ選択

---

## 2. VOISONA Talk APIの前提知識

### 2.1 公式マニュアルからの知見
- スタイル（感情）は文全体への適用のほか、文中の位置ごとに細かく変える機能もある（STYタブ）が、今回は使わない。
- VOICEVOX・VoisonaTalkのいずれのAPIも、テキスト内容から感情を自動推定する機能は持っていない（スタイル値は外部から明示的に指定する必要がある）。
- 2026年9月時点でベータ版機能。仕様変更の可能性がある点に留意。

### 2.2 実機Talk API Reference確認結果
`http://localhost:32766/docs/talk_api.html`（v0.9.1、VoisonaTalkアプリのREST API有効化時にのみ表示）を実機で取得し確認した。

**エンドポイント一覧**（ベースURL: `http://localhost:32766/api/talk/v1`、認証: HTTP Basic認証 `email:password`）

| メソッド/パス | 用途 |
|---|---|
| `POST /speech-syntheses` | 音声合成リクエストをキューに追加。`{"uuid": "..."}`を返す（非同期） |
| `GET /speech-syntheses/{uuid}` | 状態確認（`state`, `progress_percentage`、成功時は`duration`等）。ポーリング先 |
| `GET /speech-syntheses/{uuid}/wav` | WAVデータ取得。**`destination=memory`かつ`state=succeeded`のときのみ有効**（それ以外409） |
| `DELETE /speech-syntheses/{uuid}` | リクエストの削除（後片付け） |
| `GET /voices` | 音声ライブラリ一覧（`voice_name`/`voice_version`/`languages`/`display_names`のみ。`style_names`は含まない）。**実機確認（後述）の結果、レスポンスは配列そのものではなく`{"items": [...]}`でラップされている。** |
| `GET /voices/{voice_name}/{voice_version}` | 個別ライブラリ詳細。`style_names`（例: `["Normal","Happy","Bashful","Angry","Sad"]`）と`default_style_weights`はここで取得 |
| `GET /languages` | 対応言語一覧（例: `ja_JP`, `en_US`） |
| `GET /audio-devices/default` | 既定オーディオ出力デバイス情報 |
| `/text-analyses` 系 | 高度な発音・アクセント制御用。「シンプルなTTSには不要」と明記。**今回はスコープ外** |

**実装後の実機テストで判明した追加の補正**（`ui/TTS_VoisonaTalkEngine.py`実装・単体実行確認時、`get_voices`/`get_voice_detail`の生JSONを`debug>=0`でprintして確認）
- `GET /voices`のレスポンスは`{"items": [{...}, {...}]}`形式で、配列は`items`キーの下にある。
- 各要素の`display_names`は`[{"language": "ja_JP", "name": "田中さん"}, {"language": "en_US", "name": "Tanaka San"}]`のような、言語ごとのオブジェクトを持つ配列で返る。
- `GET /voices/{voice_name}/{voice_version}`（詳細）の`style_names`・`default_style_weights`は想定通りフラットな配列で返り、補正は不要だった。

**リクエスト/レスポンス上の要点**
- `POST /speech-syntheses`の必須パラメータ: `language`（例: `"ja_JP"`）。任意で`text`、`voice_name`、`voice_version`、`destination`（`audio_device`/`file`/`memory`、既定`audio_device`）、`global_parameters`（`style_weights`等）。
- **スタイル指定は名前付きdictではなく順序付き配列。** `global_parameters.style_weights`は数値配列（例: `[1, 0, 0, 0, 0]`）で、どの位置がどのスタイルに対応するかは対象ライブラリの`style_names`の並び順とインデックスで対応する。
- **音声ライブラリは`voice_name`＋`voice_version`の2フィールドで一意に識別される**（VOICEVOXの単一speaker IDとは異なる）。両方省略時は言語一致等による自動選択ロジックもあるが、本アプリでは明示的に両方指定する。
- リクエストキューには上限があり、`force_enqueue`フラグと409 (Conflict)エラーの仕組みがある。
- エラーレスポンスの一部（例: WAV取得404）は`application/problem+json`形式（`status`/`title`/`detail`/`meta`）で返る。

---

## 3. 全体像（処理フロー）

### 3.1 起動時
```
myapp起動 (main.py)
  └─ VoiceSettings.engine == "VoisonaTalk" かつ autorun == True の場合
       └─ ui.start_TTS_Server() 内でVoisonaTalk起動シーケンスを実行（4.1節）
```

### 3.2 発話時（1回のAI応答につき）
```
AI_Manager._do_response()
  └─ AIバックエンド(Gemini/Ollama)から応答文字列を取得
  └─ JSONパース・検証（4.2.2節）
       ├─ 成功 → add_talkhistory(生JSON文字列) / add_log・Reflect_Textへパース済み配列を渡す
       │         └─ Reflect_Text: 配列の要素ごとに
       │              Image → update_character_image()
       │              Text + Emotion → self.TTS.text_to_speech()（VoisonaTalkClientインスタンス、4.4節、1件ずつ同期処理）
       └─ 失敗 → 履歴に残さず、add_logへエラー表示、Req_PopUpMessageでポップアップ
```

---

## 4. 決定事項

### 4.1 起動・接続

#### 4.1.1 アプリの自動起動（実行パス経由）
既存のVOICEVOX起動処理（`ui/UI_main.py:start_TTS_Server`、`ui/TTS_VoiceVoxEngine.py:start_server`/`kill_server`）と同じパターンを踏襲し、VoisonaTalk用に拡張する。

- 設定: `VoiceSettings.VoisonaTalk.path`（実行ファイルパス）、`VoiceSettings.VoisonaTalk.autorun`（bool、既定`False`。VOICEVOXの`autorun`に倣う）。
- `start_TTS_Server()`に`engine == "VoisonaTalk"`の分岐を追加し、`autorun == True`の場合に起動シーケンスを実行する。
- **起動シーケンス**:
  1. まず軽量なAPI呼び出し（例: `GET /languages`）で疎通確認する。成功すれば「既に起動済み」とみなし、新規プロセスは起動しない（ユーザーが手動で起動済みのVoisonaTalkに対して二重起動しないため）。
  2. 疎通できなければ、設定された`path`から`subprocess.Popen`でVoisonaTalkを起動する。
  3. 起動後、APIが応答可能になるまで**非同期スレッド**（Tkのメインループをブロックしないよう、`GoogleCalendarCollector._start_auth_async`と同様の方式）でポーリングし、タイムアウトした場合は4.1.3節のフォールバック（ポップアップ＋セッション内無効化）を適用する。
- **バックグラウンド起動（ウィンドウ非表示）は、起動オプションとして要求するのみとする。** VoisonaTalk起動時の`subprocess.Popen`引数に、ウィンドウを表示しないよう要求する起動オプションを渡して起動を試みる（具体的なオプション名はVoisonaTalk側の対応状況を実装時に確認する）。VoisonaTalk側がそのオプションに対応していない、または非対応で無視される場合は、**通常通りウィンドウ表示ありで起動されることを許容する**（`STARTUPINFO`/`SW_HIDE`のようなOS側の強制非表示処理は行わない）。
- **プロセス終了**: 自分（本アプリ）が起動したVoisonaTalkプロセスに限り、`main.py:exit()`で終了させる。保持先はVOICEVOXの`self.engine_process`とは**別の専用属性`self.voisona_process`**とする（同じ`engine_process`を使い回すと、エンジン切替時にどちらのプロセスを指すか曖昧になるため）。**現行のVOICEVOX実装では`exit()`時にプロセス終了処理が呼ばれておらず**（`kill_server`は存在するが未使用）、これは既存コードのギャップだが本要件のスコープ外とする。VoisonaTalkは重量級のGUIアプリであるため、放置される影響がVOICEVOXより大きく、**VoisonaTalkについては新規にexit()への終端処理追加を行う**。
- 手動で起動していた（本アプリが起動主体でない）インスタンスは終了させない。

#### 4.1.2 音声ライブラリ・スタイル一覧の取得方法
アプリ起動中のVoisonaTalk APIから動的取得する。VOICEVOXの`VoiceSettings.VOICEVOX.Model`（`choice_with_func`でAPIから選択肢を取得）と同じUIパターンを踏襲するが、以下の点が異なる。
- 取得は`GET /voices`（一覧）→（スタイル名が必要な場面でのみ）`GET /voices/{voice_name}/{voice_version}`（詳細・`style_names`取得）の2段階。
- **音声ライブラリの識別は`voice_name`＋`voice_version`のペアだが、設定項目としてはVOICEVOXの`Model`と同じ「1つの`choice_with_func`項目」にまとめる。** `voice_name`と`voice_version`は独立した軸ではなく（あるライブラリのバージョンは他のライブラリでは意味を持たない）、2つの独立したドロップダウンにすると存在しない組み合わせを選べてしまうため。表示は`"田中傘 (tanaka-san_ja_JP / 2.0.1)"`のように人間可読な表示名を含め、値は`"tanaka-san_ja_JP=2.0.1"`のように`voice_name=voice_version`形式の文字列とし、使用時に`.split("=")`で分解する（VOICEVOXの`speaker.split("=")[-1]`と同じ考え方）。
- **設定UIの選択肢取得判定を、VOICEVOXのように`self.engine_process is not None`（自プロセスが起動したかどうか）に依存させず、実際のAPI疎通確認で行う**（4.1.1節の理由と同じ。手動起動されたVoisonaTalkにも対応するため）。

#### 4.1.3 VoisonaTalk未起動・API無効時のフォールバック
ポップアップメッセージを表示する。`Req_PopUpMessage`イベント（`ai/new_AI_main.py`等で既に使われているパターン）を踏襲し、接続・認証に失敗した場合はその旨を通知する。
- トリガー条件: 毎回の読み上げごとに接続を試みて都度ポップアップを出すとUXを損なうため、`GoogleCalendarCollector`の認証失敗時の扱い（ログのみ記録し、そのセッション中は機能を無効化して再試行しない）に倣い、**セッション中で最初に失敗を検知した時点で1回だけポップアップ**を表示し、以降は同一セッション中ログ記録のみに留める。機能自体は無効化されたままにし、再度有効にするには設定変更・アプリ再起動を促す。

#### 4.1.4 認証情報・接続設定の保存方法
`config.json`ファイルおよび設定UIで保持・確認する。現行のGemini APIキーと同様の扱い（平文保存、設定UIから入力・表示）とする。`CLAUDE.md`の「config.jsonの取り扱い注意」（ログ出力・コミットへの混入を避ける）は本項目にも同様に適用する。ポート番号（既定`32766`）も同様に設定項目として持つ。

---

### 4.2 AI応答フォーマット

#### 4.2.1 JSON化（方針転換）
AIの応答形式を、現行の「`立ち絵ファイル名：セリフ`を改行区切りで並べたテキスト」から、`Text`（セリフ）・`Image`（立ち絵ファイル名）・`Emotion`（感情パラメータ）を持つオブジェクトの配列（JSON）に変更する。1件のJSONに複数オブジェクトを含めることで、連続した複数文の生成（＝現行の複数行出力に相当）を表現する。

```json
[
  { "Text": "おはようございます。", "Image": "平穏.png", "Emotion": { "Normal": 1.00 } },
  { "Text": "今日もいい天気ですね。", "Image": "笑顔.tiff", "Emotion": { "Happy": 0.70, "Normal": 0.30 } }
]
```

- **ImageとEmotionを分離する。** 従来は立ち絵ファイル名が感情ラベルを兼ねていたが、Imageは引き続きAIが立ち絵ファイル名一覧から選びキャラクター画像切替にのみ使い、Emotionは独立してVoisonaTalkのスタイル指定に使う。
- VOICEVOX／Windows Narrator使用時は`Emotion`フィールドを無視する（両エンジンとも感情によるスタイル切り替えの仕組みを持たないため、今回はスコープ外）。

**影響範囲**
- `ai/AI_main.py`（`on_settings_updated`内の`base_prompt`）: 応答規則・応答例をJSONスキーマの指定に書き換える。ReAct時の`character_response()`が生成する最終応答も同じフォーマットに統一する。`load_imgs`が立ち絵ファイル名一覧をプロンプトに注入しているのと同じ要領で、選択中の音声ライブラリのVOISONAスタイル名一覧もプロンプトに注入する（4.3.1節）。
- `ui/UI_talk.py:add_log`: 現状`talkhistory.get("parts")[0]`を素の文字列としてチャットログに表示している。AI_main.py側でパース済みのText/Image/Emotion配列を渡すよう変更するのに合わせ、`Text`フィールドのみを連結して表示するように変更する（生JSONをユーザーに見せない）。
- `ui/UI_main.py:Reflect_Text`: 現状の「改行→`：`で分割」処理を廃止し、AI_main.py側でパース済みの配列を受け取り、要素ごとに`Image`で画像更新、`Text`を読み上げ、`Emotion`をTTSバックエンド（VoisonaTalk）に渡す処理に書き換える。

#### 4.2.2 既存箇所の改修方針（AI_main.pyへの集約）
JSON応答の読み分け（パース・検証・エラー判定）は`ai/AI_main.py:_do_response`に集約する。`add_log`・`Reflect_Text`など個々の消費側では生JSON文字列を直接パースさせず、AI_main.py側で判定・変換した結果を渡す。

1. AIバックエンド（Gemini/Ollama）から応答文字列を受け取ったら、まず正規表現でコードフェンス（```` ```json ````等）の除去といった整形を行い、JSONとしてのパースを試みる。
2. **パースに成功し、`Text`/`Image`/`Emotion`のスキーマにも問題がなければ**、JSON配列をPythonのlist/dict（各関数がそのまま扱える「従来の辞書形式」）に読み分けたうえで、
   - `add_talkhistory`には、次回LLM呼び出し時にAPIへそのまま送信されるテキストが必要なため、**正規表現で整形した後の生JSON文字列**を`parts`として渡す（会話履歴のデータ構造・LLMへの送信形式は変更しない）。
   - `add_log`・`Reflect_Text`には、パース済みのText/Image/Emotion配列を渡す。
3. **パース・検証に問題があった場合**:
   - `add_talkhistory`は呼ばない（会話履歴に残さない）。次のユーザー発言時に会話履歴上でuser役が2連続する形になるが、Gemini/Ollamaいずれも役割の厳密な交互性を必須としないため許容する。
   - `add_log`は呼ぶが、実際の生成内容ではなく「エラーにより応答が無効になった」旨のメッセージを渡す。
   - `Reflect_Text`（読み上げ・画像更新）は呼ばない。
   - 「生成に失敗しました。モデルの変更を推奨します。」という趣旨のメッセージを`Req_PopUpMessage`でポップアップ表示する。

ReAct分岐（`character_response()`が最終応答を生成するケース）・通常応答分岐のどちらから来た応答も同じ処理を通す必要があるため、1〜3の処理は共通のヘルパー関数として実装し、`_do_response`内の両分岐から呼び出す。

#### 4.2.3 LLM呼び出し方式（chat/generateの整理）
JSON形式での出力を安定させるため、当初「chatではなくgenerateで、履歴はコンテキストとして都度含める」方式を検討したが、コード確認の結果、**両バックエンドとも既に同等の方式で実装済み**であることを確認した。

- Gemini (`ai/AI_geminiAPI.py:84 response()`): `model.start_chat()`のようなステートフルなChatSessionは使わず、`self.model.generate_content(contents=input_contents)`を毎回呼んでいる。`input_contents`は`AI_Manager.history`から組み立て直した全履歴。
- Ollama (`ai/AI_ollama.py:102 response()`): `/api/chat`エンドポイントを使うが、サーバー側にセッション状態は持たず、`messages`に全履歴を積んで単発リクエストしている。

したがって**エンドポイントの変更（`/api/generate`への切り替え等）は行わない**。`/api/chat`はモデルのチャットテンプレート（system/user/assistantの役割整形）を自動適用してくれるため、これを自前の`/api/generate`呼び出しで代替すると、モデルごとに異なるテンプレートを再現する必要が生じ、JSON出力の安定性という目的に対してはむしろ悪化リスクがある。

ただし`ai/AI_geminiAPI.py`・`ai/AI_ollama.py`への変更が完全に不要というわけではなく、JSON出力を安定させるための**生成設定への1パラメータ追加は両ファイルに必要**。
- Gemini: `generation_config`に`response_mime_type: "application/json"`を追加。可能であれば`response_schema`でText/Image/Emotionの構造を指定する。
- Ollama: `/api/chat`のペイロードに`"format": "json"`（対応バージョンではJSON Schemaを`format`に直接渡すことも可能）を追加する。

#### 4.2.4 JSON出力の残存リスクへの対応
リトライや自動補正は行わず、単純にエラー扱いとする。`response_mime_type`/`format:json`等の構造化出力オプションを使ってもなお、パース失敗またはスキーマ逸脱（`Text`/`Image`/`Emotion`キーの欠落等）が発生した場合は、4.2.2節の「パース・検証に問題があった場合」の処理を実行する。

**実機で確認された実際の失敗例**（`application.log`、`LLMSettings.Service=Ollama`使用時）: セリフが1件のみの応答で、AIがJSON配列`[{...}]`ではなくオブジェクト`{...}`を直接トップレベルに出力し、「トップレベルがlistではない」として`invalid_schema`エラーになった。`Emotion`の値自体（例: `{"Happy": 0.80, "Normal": 0.20}`）は正しい形式だったため、原因はEmotion/style変換ではなく配列/オブジェクトの取り違えだった。設計方針としては引き続き自動補正（オブジェクトを配列へ自動的にラップする等）は行わず、プロンプト側で「セリフが1件でも必ず配列にする」ことと単一要素の応答例を明示することで対応する（`ai/AI_main.py:on_settings_updated`）。性能の低いモデルでは改善しない場合があり、その際はポップアップの案内どおりモデル変更で対応する。

---

### 4.3 Emotion（感情パラメータ）の扱い

#### 4.3.1 出力方式
Emotionは、選択中の音声ライブラリからAPI経由で取得したスタイル名をキーとし、それぞれ数値を持つオブジェクトとして、AIに直接出力させる（固定語彙＋対応表を介する方式は検討の末に不採用）。

- スタイル名一覧は`GET /voices`→`GET /voices/{voice_name}/{voice_version}`の2段階のAPI呼び出しで動的取得し、`ai/AI_main.py:on_settings_updated`で立ち絵ファイル名一覧と同様にシステムプロンプトへ注入する。
  - 注入タイミングは「アプリ起動後」と「設定適用時」。`AI_Manager.__init__`が末尾で`self.on_settings_updated(setting)`を直接呼び、かつ`SettingsUpdated`イベントにも同関数を購読させている（既存コード、`ai/AI_main.py:64,79`）ため、新たな配線は不要。VOISONAスタイル一覧の取得・注入処理を`load_imgs`と同じ関数内に追加するだけでよい。
- VOISONA側の仕様どおり、複数スタイル指定時は「指定値の合計に対する比率」で合成される（例: `{"Happy":0.70,"Normal":0.30}` は Happy 70% / Normal 30%）ことをプロンプト内で説明する。
- **Emotionオブジェクトには、注入したスタイル名一覧に含まれる全スタイルを、使用しない（0.00にしたい）ものも含めて必ず明記させる。** 当初は「未指定＝0.00扱いなので0.00のスタイルは書かなくてよい」という指示にしていたが、この曖昧さがLLM（特にOllamaのローカルモデルなど性能が高くない場合）のJSON生成を不安定にする一因になったため、全スタイル明記の方針に変更した。プロンプトには、選択中ライブラリの実際のスタイル名一覧を使った具体的な記載例（1つ目のスタイルのみ1.00、残りは全て0.00）を動的に生成して含める。

#### 4.3.2 数値スケール
**0.00〜1.00に確定する。** AIには`{"Happy": 0.70, "Normal": 0.30}`のように0.00〜1.00の範囲で出力させる（0〜100スケールは不採用）。

#### 4.3.3 API呼び出し用の変換
API呼び出し直前に、名前付きEmotionオブジェクトを`style_weights`配列へ変換する処理が必要。選択中ライブラリの`style_names`（例: `["Normal","Happy","Bashful","Angry","Sad"]`）でインデックスを引き、該当位置に値を入れ、指定のなかったスタイルは`0.0`とする。

#### 4.3.4 異常値の扱い
- AIが存在しないスタイル名を出力した場合はそのキーを無視する。
- 値が0.00〜1.00の範囲外の場合はクランプする。
- `Emotion`が空/欠落の場合は全スタイル`0.0`（またはライブラリの`default_style_weights`）を使う。
- **AIには`Emotion`オブジェクトに全スタイルを明記させる（4.3.1節）。** `build_style_weights`自体は`Emotion`に含まれなかったスタイルを`0.0`として扱うフォールバックを引き続き持つ（AIの出力漏れやスキーマ逸脱に対する安全網、および将来的な仕様変更への耐性のため）が、プロンプト上でAIに求める記載ルールとしては「全スタイルを明記」を正としている。

#### 4.3.5 妥当性検証の範囲
専用の自動検証・監視の仕組みは作らず、既存の`debug=-1`慣習（`debug`が0以上でインデント付き`print()`トレースを有効化する既存パターン）に従って、AIが出力した`Emotion`の内容とVOISONA API呼び出しへの変換結果をデバッグ出力で確認できるようにするに留める。実機での安定性検証自体は実装後に手動で行う。

---

### 4.4 音声合成呼び出し

#### 4.4.1 音声出力先（destination）
**`memory`を指定し、WAVデータを取得して自前で再生する。** `POST /speech-syntheses`の`destination`（`audio_device`/`file`/`memory`）に`memory`を選び、`state`が`succeeded`になった後に`GET /speech-syntheses/{uuid}/wav`でWAVデータを取得し、現行VOICEVOX実装（`ui/TTS_VoiceVoxEngine.py`の`simpleaudio.WaveObject`による再生・`wait_done()`）と同じ方式で再生する。
- `audio_device`（VoisonaTalk自身に再生を任せる方式）は不採用。理由: このアプリはWAVを受け取れず、「同期的にブロッキング待機する」際の完了判定が「合成完了（`state=succeeded`）」までしか取れず「再生完了」までは取れないため。
- 使用後は`DELETE /speech-syntheses/{uuid}`でリクエストを削除し、キューを汚さないようにする。

#### 4.4.2 API呼び出し方針
同期的にブロッキング待機する。`EventBus`のリスナーは元々daemonスレッドで動作するため、TTSバックエンド内でUUIDのポーリングが完了するまで待ってから音声再生する実装とし、現行VOICEVOX実装と同じ呼び出し形（`text_to_speech()`が完了するまでブロックする）に揃える。EventBus側の配線変更は不要。

#### 4.4.3 言語パラメータ
`POST /speech-syntheses`の必須パラメータ`language`には固定で`"ja_JP"`を指定する。キャラクターとの会話は日本語のみを想定しているため、設定項目化はせずコード内で固定値とする。

#### 4.4.4 リクエストキューの輻輳への対応
`force_enqueue`は使わず、Text2Speech関数内でリクエストを順序立てて（1件ずつ完了を待ってから次を送る形で）発行する。4.4.2節の同期呼び出し方針に沿って、複数セリフがある場合も前のリクエストの`state`が`succeeded`になり音声取得・再生・`DELETE`が完了してから次のセリフのリクエストを送るため、輻輳（409 Conflict）は基本的に発生しない設計とする。それでも409が発生した場合は、4.2.4節のJSON生成失敗時と同様に`Req_PopUpMessage`でエラーをポップアップ表示する（リトライは行わない）。

---

### 4.5 通知トリガー条件のまとめ

| 失敗の種類 | トリガー条件 |
|---|---|
| JSON生成失敗（4.2.4節） | 発話のたびに起こり得るため**都度**ポップアップ表示 |
| VoisonaTalk未起動・API無効（4.1.3節） | **セッション中で最初の1回だけ**ポップアップ、以降はログのみ |
| リクエストキュー輻輳・409（4.4.4節） | JSON生成失敗と同様に都度ポップアップ（リトライなし） |

---

## 5. 設定項目一覧（`services/config_controller.py`への追加イメージ）

```python
"VoisonaTalk": {
    "name": "VoisonaTalk 設定",
    "type": "section",
    "children": {
        "path": {
            "type": "path",
            "name": "VoisonaTalkの実行パス",
            "value": ""
        },
        "autorun": {
            "type": "bool",
            "name": "アプリ起動時にVoisonaTalkを自動で起動",
            "value": False
        },
        "port": {
            "type": "int",
            "name": "APIポート番号",
            "value": 32766
        },
        "account_email": {
            "type": "str",
            "name": "アカウント（メールアドレス）",
            "value": ""
        },
        "account_password": {
            "type": "str",
            "name": "APIパスワード",
            "value": ""
        },
        "speed": {
            "type": "float",
            "name": "読み上げ速度",
            "description": "設定可能範囲は0.2〜5.0。1.0が標準速度、最大5.0で標準の5倍速、最小0.2で標準の1/5倍速。",
            "min": 0.2,
            "max": 5,
            "value": 1.0
        },
        "Model": {
            "type": "choice_with_func",
            "name": "音声ライブラリ",
            "value": "未選択",
            "options": []
        }
    }
}
```

`VoiceSettings.engine`の`options`（現状`["None","windowsNarrator","VOICEVOX"]`）に`"VoisonaTalk"`を追加する。

---

## 6. 影響を受けるファイル一覧

| ファイル | 種別 | 内容 |
|---|---|---|
| `ui/TTS_VoisonaTalkEngine.py` | 新規 | プロセス起動・終了（`start_server`/`kill_server`、`TTS_VoiceVoxEngine.py`と同じモジュール関数）と、API通信を担う`VoisonaTalkClient`クラス（`ai/AI_geminiAPI.py:geminiAI`・`ai/AI_ollama.py:ollamaAI`と同じ`__init__(usersetting, debug)`パターン）の2構成。詳細は設計方針ドキュメント参照。 |
| `ai/AI_main.py` | 変更 | `on_settings_updated`の`base_prompt`をJSONスキーマ指定に書き換え、VOISONAスタイル名一覧の注入を追加。`_do_response`にJSONパース・検証・エラー処理の共通ヘルパーを追加し、ReAct分岐・通常分岐の両方から呼び出す。 |
| `ai/AI_geminiAPI.py` | 変更 | `generation_config`に`response_mime_type: "application/json"`を追加。 |
| `ai/AI_ollama.py` | 変更 | `payload`に`"format": "json"`を追加。 |
| `ui/UI_talk.py` | 変更 | `add_log`のmodel応答表示を、パース済み配列から`Text`のみを連結する形に変更。 |
| `ui/UI_main.py` | 変更 | `_initialize_tts`に`VoisonaTalk`分岐を追加。`start_TTS_Server`にVoisonaTalk起動シーケンス（4.1.1節）を追加。`Reflect_Text`をJSON配列対応に書き換え、`Emotion`をTTSバックエンドへ渡す。 |
| `ui/UI_settings.py` | 変更 | `VoiceSettings.VoisonaTalk.Model`（`choice_with_func`）の選択肢更新を、VOICEVOXの`Model`と同じ要領で`VoisonaTalkClient.get_voices`にマッピング。実装時に判明した追加要件（当初のファイル一覧に未記載だったが、設定UIの動作に必須）。加えて`speed`用に新設した`"float"`型の入力欄・保存時クランプ処理を追加。 |
| `services/config_controller.py` | 変更 | `VoiceSettings.engine`の選択肢に`"VoisonaTalk"`追加、`VoiceSettings.VoisonaTalk`セクション追加（5章）。`speed`設定のため`SettingItem`に`"float"`型（`"int"`型と同じ`min`/`max`クランプの仕組み）を新設。 |
| `main.py` | 変更 | VoisonaTalkプロセスの参照保持と、`exit()`での終了処理を追加（4.1.1節）。 |

---

## 7. テスト観点（実装後の動作確認チェックリスト）

本プロジェクトに自動テストはなく手動検証が前提（`CLAUDE.md`）のため、実装後に以下を確認する。

**起動・接続**
- [ ] VoisonaTalk未起動の状態でアプリを起動し、`autorun`有効なら自動起動されること
- [ ] ウィンドウ非表示の起動オプションが効く場合・効かない場合それぞれで、起動自体は成功すること（非対応時はウィンドウ表示ありでの起動を許容）
- [ ] VoisonaTalkを事前に手動起動した状態でアプリを起動し、二重起動されないこと
- [ ] 実行パスが未設定・誤っている場合に起動失敗のポップアップが出ること
- [ ] アプリ終了時、自アプリが起動したVoisonaTalkプロセスが終了すること（手動起動していた場合は終了させないこと）
- [ ] 認証情報（メール・パスワード）が誤っている場合の挙動（ポップアップ＋セッション内無効化）

**音声ライブラリ・スタイル**
- [ ] `ui/TTS_VoisonaTalkEngine.py`を単体実行し、モデル（音声ライブラリ）とスタイル一覧が正しく表示されること（設計方針11.1節の`__main__`ブロック。UI統合前に先に確認できる）
- [ ] 設定UIでVoisonaTalkの音声ライブラリ一覧（`voice_name`＋`voice_version`、`Model`項目）が取得・選択できること
- [ ] ライブラリ切替時、プロンプトに注入されるスタイル名一覧が更新されること
- [ ] スタイル数・名称の異なるライブラリに切り替えた際、旧ライブラリにのみ存在したスタイル名をAIが誤って出力しても無視されること

**AI応答・JSON処理**
- [ ] 正常なJSON応答でText読み上げ・Image切替・Emotion反映が期待通り動くこと
- [ ] 複数要素を含むJSON配列（連続する複数文）が順番通りに処理されること
- [ ] コードフェンス付きJSON（` ```json `等）が正しく除去されパースされること
- [ ] 意図的に壊れたJSON（キー欠落・構文エラー）の場合、会話履歴に残らず、チャットログにエラー表示、ポップアップが出ること
- [ ] ReAct有効時の最終応答も同じJSON形式で処理されること

**Emotion→VOISONA変換**
- [ ] Emotionの値が0.00〜1.00の範囲外（例: 1.5や-0.2）の場合にクランプされること
- [ ] 存在しないスタイル名を指定した場合に無視されること
- [ ] Emotion省略時にデフォルト（全0または`default_style_weights`）が使われること

**TTS呼び出し**
- [ ] 前の発話の再生完了（`DELETE`まで）後に次のリクエストが送られること（同期ブロッキングの確認）
- [ ] `destination=memory`でWAV取得→`simpleaudio`再生が正常に行われること
- [ ] 使用済みリクエストが`DELETE`されること
- [ ] 連続発話で409 Conflictが発生しても異常終了せず、ポップアップで通知されること

**リグレッション確認**
- [ ] `VoiceSettings.engine`をVOICEVOX／Windows Narratorに戻した場合、`Emotion`フィールドが無視され従来通り動作すること
- [ ] `config.json`・ログにパスワードが平文で残るが、コンソール出力やコミットに混入していないこと（目視確認）

---

## 8. 未定義及び検討中の事項
- **OSレベルでのウィンドウ非表示処理: 実機検証の結果、効果なしと判明。** 4.1.1節の方針は「起動オプションで非表示を要求し、非対応ならウィンドウ表示ありを許容する」とした。それでもウィンドウ表示が問題になる場合の代替手段として、`subprocess.STARTUPINFO`に`wShowWindow=SW_HIDE`・`dwFlags|=STARTF_USESHOWWINDOW`を設定してOS側から強制的に非表示にする方式を検討候補として残していたが、`ui/TTS_VoisonaTalkEngine.py:test_hidden_launch`で実機検証したところ、**VoiSona Talk.exe起動後も可視ウィンドウが生成され、SW_HIDEは効かないことを確認した**。比較用の通常起動テスト（`test_windowed_launch`）では想定通り可視ウィンドウが生成されており、テストコード自体の不備ではなく、アプリ側が起動時に自前でウィンドウ表示処理を行い親プロセスの初期表示状態を上書きしている（WPF系アプリで一般的な挙動）と考えられる。今回はこの代替案も不採用のままとし、ウィンドウ非表示はVoisonaTalk側の起動オプション対応状況に委ねる（オプション名が判明した場合は4.1.1節の方針で再検討する）。
- **読み上げ速度（`speed`パラメータ）の設定項目化: 実装済み。** 実機確認の結果、`POST /speech-syntheses`の`global_parameters`には`style_weights`以外に`speed`・`pitch`・`intonation`・`huskiness`・`alp`が存在し、`speed`は実機のOpenAPIスキーマ上`type: number, default: 1, minimum: 0.2, maximum: 5`と定義されていることを確認した（`pitch`等は現状未対応のまま）。
  - `VoiceSettings.VoisonaTalk.speed`（`float`型、既定`1.0`、`min: 0.2`/`max: 5`）を設定項目として追加し、設定UIから変更できるようにした。範囲はAPI仕様の`minimum`/`maximum`をそのまま使用する。
  - `VoisonaTalkClient.text_to_speech`は、`Emotion`（スタイル）や`style_names`の有無、文章量、選択中の音声ライブラリに関わらず、常に設定値の`speed`を`global_parameters.speed`として送信する（一律適用）。
  - `config_controller.py`にはこれまでなかった`"float"`型のSettingItemを新設し（`"int"`型と同じ`min`/`max`クランプの仕組みを流用）、`ui/UI_settings.py`にも対応する入力欄・保存時のクランプ処理を追加した。

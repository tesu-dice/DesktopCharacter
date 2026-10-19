# ClaudeCode連携 要件定義

> **2026-10-13 凍結。** 経緯・理由・再開条件は `202610_ClaudeCode連携_凍結の経緯.md` を参照。

**対象:** DesktopCharacter / `main.py`, `ai/AI_main.py`, `ui/UI_settings.py`, `services/config_controller.py`, `main.spec`, `scripts/make_portfolio_repo.py`, 新規ClaudeCode連携ファイル（配布・公開時に除外）

# 概要
ローカルのLLMでは動作に時間がかかる。GeminiAPIだと従量課金で金額がかさむ。
なのでClaudeCodeの-pオプションを利用した一定金額での利用量をうまく使って再現したいという課題とアプローチ。
ClaudeCodeとの連携機能を追加する。  
プログラムについてはこれまでのAI_XXXX.pyとして実装するが、アプリ配布版などにおいては利用規約などを加味して含んではいけない。  
従来のLLMサービスとの接続と同様のクラスや関数分けを行いつつ、Claudeに関しての該当ファイルが存在しない場合もしっかりと動作が行えるようにする必要がある。  
また、ClaudeCodeとの連携を行う際の設定についてはGeminiAPIキーの入力欄を利用し、アカウント情報やワーキングフォルダ、許可を行う動作などのパーミッションなども設定を行う必要があると思われる。  

> 上記は初期メモ。以降の節は2026-10-13のClaudeCodeとの検討結果を反映したもの。
> 「従来と同様のクラス分け（AI_XXXX.py）」「GeminiAPIキー欄の流用」は検討の結果見直している（4.1節・6章）。

---

## 1. 目的・スコープ

- ClaudeCodeに期待する能力は **LLMとしてのテキスト生成のみ**。ただしClaudeCodeのThinking（推論）を含んだ動作は有用なので活用する。
- 利用範囲は **会話応答** と **アクティビティ要約（hour/day）** の両方。
- PKMフォルダ（Obsidian）を **読み取り専用** で参照させる。書き足し・編集・新規作成は許可しない。
- アプリ側のReAct動作はClaudeCodeラインではオミットする（ClaudeCode自体が内部で推論・ツール実行ループを持つため）。
- 配布版（PyInstallerビルド）および公開用リポジトリには一切含めない。本体リポジトリ（非公開）には通常どおり含める。

### スコープ外
- ClaudeCodeにPC操作・ファイル編集・コマンド実行をさせるエージェント用途。
- アプリの`ai_tools`をMCPサーバー化してClaudeCodeから呼ばせる方式（将来検討）。
- Claude Agent SDK / Anthropic API（従量課金）での接続。

---

## 2. 前提知識

### 2.1 方式の選択
| 方式 | 採否 | 理由 |
|---|---|---|
| `claude -p` をsubprocessで呼び出す | 採用 | Python 3.9のまま利用可能。サブスクリプション（OAuth）認証で動く |
| Claude Agent SDK (Python) | 不採用 | Python 3.10以上が必要。winrtの制約で3.9固定の本アプリでは使えない |
| Anthropic API | 不採用 | 従量課金であり本機能の目的に反する |

### 2.2 CLIオプションの確認結果（Claude Code 2.1.295、`claude --help`で確認）
| オプション | 用途 |
|---|---|
| `-p` / `--output-format json` | 非対話実行。結果・usage・session_id等をJSONで受け取る |
| `--output-format stream-json` / `--include-partial-messages` | 逐次出力。進捗表示やthinkingの取得に使える可能性あり |
| `--json-schema <schema>` | 構造化出力の強制（会話応答のText/Image/Emotion配列に利用） |
| `--effort low〜max` | 推論の深さ。会話・要約で使い分ける |
| `--model <alias>` | `haiku`/`sonnet`/`opus` 等のエイリアス指定が可能 |
| `--tools <names>` | 使用可能な組み込みツールを限定。`""` で全無効 |
| `--disallowedTools` | 明示的な禁止（多重防御用） |
| `--add-dir` | 追加でツールアクセスを許可するディレクトリ |
| `--system-prompt[-file]` / `--append-system-prompt[-file]` | システムプロンプトの置換・追記 |
| `--setting-sources user,project,local` | 読み込む設定ソースの限定 |
| `--strict-mcp-config` | ユーザー環境のMCPサーバーを読み込まない |
| `--no-session-persistence` | セッション履歴を `~/.claude/projects/` に保存しない |
| `--agent <agent>` | エージェント定義（システムプロンプト・ツール・モデル）を指定 |

- **`--bare` は使用不可。** OAuth/キーチェーンを読まず `ANTHROPIC_API_KEY` のみで認証するため、サブスクリプション利用ができなくなる。

### 2.3 規約上の前提
- Anthropicは、承認のない第三者製品がClaude.aiのログイン／利用枠を提供することを認めていない。よって配布物には含めず、**作者個人の環境でのみ動作する機能**とする。
- 要約の定期実行は無人の自動実行にあたる。最新の利用規約を各自確認のうえ運用する。

---

## 3. 全体像（処理フロー）

### 3.1 方針：処理の中身は別ライン、入口と出口は共通
既存の `main.py` では、会話（`handle_user_message`）と要約（`handle_summary_request`）が共に `AI_Manager.req_LLM(payload, response_event)` を呼んでいる。
ClaudeCodeラインも **同じ `req_LLM` の呼び出し規約と同じ応答イベント** を持たせ、`main.py` 側で振り分けるだけにする。UI・UserDataLogger側は無改修。

```
MessageInput ──→ handle_user_message ─┬─(Service=geminiAPI/Ollama)→ AI_Manager.req_LLM ───────┐
Req_UserSummaryLog → handle_summary_request ┤                     （従来どおり・ReAct可）       │
                                       └─(Service=ClaudeCode)──→ ClaudeCodeManager.req_LLM ─┤
                                                                （ReActなし・PKM読み取り可）   ↓
                                                   OnUserResponse / OnSummaryDone / OnSummaryLLMError
                                                   （ペイロード形式は従来と同一）
```

### 3.2 会話応答時
```
ClaudeCodeManager（会話）
  ├─ 状況情報の事前注入：時刻・アクティブウィンドウ・再生中メディア・カレンダー等を
  │   アプリ側で収集し、プロンプトに含める（ツール呼び出しはさせない）
  ├─ stdin で渡す内容：キャラクター設定 + 立ち絵ファイル名一覧 + ユーザープロファイル + 状況情報 + 会話履歴 + 入力
  ├─ claude -p 実行（cwd=PKMフォルダ / tools=Read,Glob,Grep / --json-schema / --effort 会話用）
  ├─ 応答をJSON検証（既存 _parse_ai_response と同じ処理）
  └─ OnUserResponse を publish
```

### 3.3 要約時
```
ClaudeCodeManager（要約）
  ├─ stdin で渡す内容：要約プロンプト + 対象ログ
  ├─ claude -p 実行（PKM参照の要否は5章で決定 / --effort 要約用 / 軽量モデル）
  ├─ 成功 → OnSummaryDone を publish（従来と同じ引数）
  └─ 失敗・利用枠超過 → Req_PopUpMessage + OnSummaryLLMError（既存のキャッチアップ停止処理に乗せる）
```

---

## 4. 決定事項

### 4.1 配置と配布物からの除外
- ~~実装は `private/` 配下に置く~~ → **（2026-10-13修正）専用フォルダは作らず、通常のフォルダ構成（`ai/` 等）にファイルを設置する。** 本体リポジトリ（非公開）では通常どおりgit管理する。
- 除外は **配布ビルド時** と **公開用リポジトリ作成時** に行う。
  - 公開用リポジトリ：`scripts/make_portfolio_repo.py` の `EXCLUDE_PATHS` / `EXCLUDE_GLOBS` に該当ファイルを追加し、履歴ごと除外する。
  - 配布ビルド：`main.spec` の `excludes` に該当モジュールを追加する。
- 除外漏れを防ぐため、ClaudeCode連携のファイルは **ファイル名に `ClaudeCode` を含める命名規則** とし、globで一括除外できるようにする（具体的なファイル名は詳細設計で決定）。
- `ai_tools/` には置かない（`main.spec` が `ai_tools/*.py` をdatasとして丸ごと同梱するため、excludesでは防げない）。
- 本体側からは **文字列指定の動的import**（`importlib.import_module`）で読み込む。静的importはPyInstallerの解析で同梱されてしまうため使わない。
- `sys.frozen` 時は読み込まない（excludesと合わせた二重の除外）。
- 該当ファイルが存在しない場合（公開用リポジトリ・配布版）、`LLMSettings.Service` の選択肢に `ClaudeCode` が現れず、従来どおり動作すること。
- ClaudeCode用の設定定義は `config_controller.get_default_data()` には書かず、**privateモジュール側が提供し、読み込めた時だけマージ**する（配布版の設定画面に現れないようにするため）。

### 4.2 AI_Managerとの関係
- `AI_XXXX.py`（`response()`/`get_models()`/`test_connection()` を持つバックエンドクラス）としてではなく、`AI_Manager` と並ぶ **別ラインのマネージャー** として実装する。
- 共通化するもの：
  - 応答ペイロード形式（`segments` 含む）と応答イベント名
  - 応答JSONの検証処理（`_parse_ai_response` を関数として切り出して共用）
  - キャラクター設定・立ち絵一覧・ユーザープロファイルの読み込み
  - 会話履歴はアプリ側で管理（ClaudeCodeのセッション `--resume` は使わない）
- 分離するもの：プロンプト構築、subprocess実行管理（キュー・タイムアウト・終了処理）、effort/モデルの選択、利用枠超過時の処理。

### 4.3 作業フォルダとCLAUDE.md
- 作業フォルダ（cwd）は **PKMフォルダ直下** とする（PKMフォルダでは普段ClaudeCodeを使っていないため、CLAUDE.mdの衝突は当面問題にならない）。
- PKM直下の `CLAUDE.md` には **変化しないアプリ用要件** を記載する（役割、PKMの構成と探し方、要約の観点など）。
- 毎回変わる情報（キャラクター設定・履歴・状況情報）はstdinで渡す。出力構造は `--json-schema` で強制し、CLAUDE.mdの文章には頼らない。

### 4.4 PKMへのアクセス権限
- 許可：`Read` / `Glob` / `Grep` のみ。
- 禁止：`Edit` / `Write` / `NotebookEdit` / `Bash` / `WebFetch` / `WebSearch` 等。`--tools` による限定に加え `--disallowedTools` でも明示する（多重防御）。
- `-p` モードでは許可していないツールは自動で拒否される前提。

### 4.5 Thinkingの扱い
- `--effort` で会話・要約ごとに推論の深さを設定可能にする。
- thinkingの内容はキャラクターの発話には使わない（必要に応じてログ出力のみ）。
- 応答待ちが長くなるため、処理中であることをキャラクター側で示すUXを用意する（方法は詳細設計で決定）。

### 4.6 subprocess実行時の必須対策
| 項目 | 対策 |
|---|---|
| 実行ファイル解決 | `claude` はnpmシム（`claude.cmd`）のため `shutil.which` で解決、または設定で実行パスを指定 |
| コマンドライン長制限（cmd.exe 8191文字） | プロンプトは引数ではなく **stdinにUTF-8で渡す** |
| 文字コード | 入出力とも `encoding="utf-8"` を明示（cp932化け防止） |
| コンソール窓の表示 | `creationflags=CREATE_NO_WINDOW` |
| 子プロセス残留 | タイムアウト・アプリ終了時はプロセスツリーごと終了（`.cmd`→node） |
| 意図しない従量課金 | 子プロセスの環境変数から `ANTHROPIC_API_KEY` を除去 |
| 余計なコンテキスト読込 | `--strict-mcp-config`、`--setting-sources` の限定、`--system-prompt` で既定プロンプトを置換 |
| 個人情報の蓄積 | `--no-session-persistence` |

### 4.7 接続テスト
- 起動時の接続テストでは実際のLLM呼び出しは行わない（時間と利用枠の消費を避ける）。`claude --version` と認証状態の確認に留める。

---

## 5. 課題・リスク

- **応答の遅さ**：CLI起動のオーバーヘッド（数秒）に加え、thinkingの分だけ待ち時間が伸びる。会話で30秒以上かかる可能性がある。
- **利用枠（5時間枠）の消費**：要約もClaudeCodeで行うため、会話用の枠を圧迫する。特に起動時のキャッチアップで未要約分が溜まっていると、連続して多数の呼び出しが発生する。
  - 対応候補：要約は軽量モデル・低effort、キャッチアップはまとめて1回で投げる、枠超過を検出したら停止。
- **要約のPKM参照**：要約時にPKMを読ませると精度は上がりうるが、トークン消費と時間が増える。
- **プロンプトインジェクション**：ウィンドウタイトル・メディア名など外部由来の文字列がプロンプトに入る。ツールを読み取り専用に限定しているため、影響はPKMの読み取りまでに抑えられる。
- **PKMの内容がAnthropicへ送信される**：読み取りを許可した範囲は送信対象になる。見せたくないフォルダがある場合の除外方法を検討する。
- **CLAUDE.mdの将来的な衝突**：PKMフォルダで手作業のClaudeCodeを使い始めた場合、アプリ用CLAUDE.mdが干渉する。その際は専用サブフォルダへの移行を検討する。

---

## 6. 未決事項（設計方針・詳細設計で決める）

1. **設定項目の置き場所**：初期メモではGeminiAPIキー欄の流用としていたが、サブスクリプション認証ではキーが不要で意味が混乱するため、専用セクション（例：`LLMSettings.ClaudeCode.*`）を推奨。候補項目：実行パス、PKMフォルダ、会話用モデル/effort、要約用モデル/effort、タイムアウト。
2. **要約時にPKM参照を許可するか**（`--tools ""` で純テキスト生成にするか）。
3. **処理中のUX**（考え中の表情・一言、stream-jsonによる進捗表示の要否）。
4. **利用枠超過時の挙動**（停止のみ／他のAIサービスへのフォールバック）。
5. **PKM内の除外フォルダの扱い**。

### 6.1 実機で要検証
- `--system-prompt` で既定プロンプトを置換した場合でも、cwdの `CLAUDE.md` が読み込まれるか。
- `--json-schema` 使用時の出力JSONにおける結果フィールド名（`structured_output` 等）。
- 各モデル（特にhaiku）での `--effort` 指定の可否。
- stream-jsonでthinkingブロックが取得できるか。
- 利用枠超過時・未ログイン時のCLIのエラー出力形式（`is_error` 等）。
- 1回あたりの起動オーバーヘッドの実測値。

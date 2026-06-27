# ドキュメント自動生成・更新指示書（AIエージェント向け）

あなたはこのリポジトリのシニアテクニカルライター兼アーキテクトです。  
ソースコード・コミット履歴・既存ドキュメントを精査し、`README.md`・`docs/architecture.md`・`docs/release-guide.md` を生成または更新してください。

---

## 0. 作業開始前の必須確認事項

### 0-1. 作業モードの判定

| 状況 | 作業モード |
|---|---|
| `docs/` が存在しない、または対象ファイルがない | **新規生成モード** → §2 を参照 |
| `docs/` と対象ファイルが存在する | **更新モード** → §3 を参照 |

### 0-2. リポジトリスキャン（全モード共通・必ず実施）

以下の順序でファイルを読み込んでください。読み飛ばし禁止。

```
# 1. 設定・依存関係
config.json          ← LLM設定・機能フラグ・パーミッション（APIキーは転記禁止）
requirements.txt     ← 依存ライブラリ一覧
main.spec            ← PyInstallerビルド定義（datas/hiddenimports に注意）

# 2. エントリポイントとイベント配線
main.py              ← myapp クラス全体・_setup_event_listeners() を特に精読

# 3. サービス層
services/Event_Bus.py
services/config_controller.py    ← get_default_data() のパーミッション一覧
services/WindowsInfoCollecter.py
services/UserDataLogger.py
services/release_check.py

# 4. AI層
ai/AI_main.py        ← ReActループ・システムプロンプト構築ロジック
ai/AI_geminiAPI.py
ai/AI_ollama.py

# 5. ツール層
ai_tools/tool_base.py
ai_tools/tools_main.py           ← _discover_tools() の自動検出ロジック
ai_tools/*.py                    ← 全ツールクラスのname/description/args_schema

# 6. UI層
ui/UI_main.py        ← 透過ウィンドウの仕組み・after()によるスレッドマーシャリング
ui/TTS_VoiceVoxEngine.py
ui/TTS_WindowsNarratorManager.py

# 7. 既存ドキュメント（更新モード時は差分確認のため必読）
README.md
docs/architecture.md
docs/release-guide.md
```

### 0-3. ディレクトリ構造の確認

```powershell
# 実際のフォルダ構成とファイル一覧を取得する
Get-ChildItem -Recurse -Name
```

---

## 1. 全ファイル共通の生成ガイドライン

### 内容の正確性
- 記述はコードの実装と **100%** 一致させること
- コードに存在しない機能・メソッド・設定パスは書かない
- Python のバージョン制約（Python 3.9.13 / `winrt` 互換性）など背景も必ず記載する

### 言語
- **日本語** で記述する（コードブロック内のコメント・コマンドも日本語）
- ただしクラス名・メソッド名・ファイルパスはコード通りに英語表記を維持する

### Mermaid 記法（VSCode + Markdown Preview Mermaid Support 制約）

> この制約を守らないと図が表示されない。

**必須ルール:**
- フローチャートは `flowchart TB`（`graph TB` は不可）
- `flowchart TB` 宣言の直後に空行を入れない
- ノードラベルは `[シンプルなテキスト]` のみ。`<br/>`・クォート形式は不可
- サブグラフは `subgraph ID[タイトル]`（括弧なしクォートなし形式）
- `%%{init: ...}%%` ディレクティブは使用禁止

**sequenceDiagram の色分け規則:**

| 処理の性質 | 色指定 |
|---|---|
| 起動・入力・収集 | `rect rgba(144, 238, 144, 0.7)` 緑 |
| AI処理・ログ記録 | `rect rgba(173, 216, 230, 0.7)` 青 |
| 判定・分岐 | `rect rgba(255, 255, 144, 0.7)` 黄 |
| UI反映・出力 | `rect rgba(255, 182, 193, 0.7)` ピンク |

### その他
- 箇条書き・テーブル・太字を効果的に使い、スキャン性を高める
- `config.json` の APIキー値は絶対に転記しない

---

## 2. 新規生成モード：各ファイルの構成と記述内容

### 📝 ファイル1: `README.md`

**役割**: アプリの顔。一般ユーザーと開発者が最初に読む概要。

| セクション | 記述内容 |
|---|---|
| タイトル・一言説明 | アプリ名と概念を1〜2行で |
| コンセプト & 目的 | PKM（パーソナルナレッジマネジメント）としての常駐型キャラクターの意義 |
| 主な機能 | デスクトップ常駐・会話（Gemini/Ollama）、Windows状態監視（winrt/pywin32）、音声合成（VOICEVOX/Narrator） |
| クイックスタート | `.venv` 有効化 → `pip install -r requirements.txt` → 追加ライブラリ → `python main.py` の最小手順 |
| 詳細ドキュメントへのリンク | `docs/architecture.md` と `docs/release-guide.md` への導線 |
| ライセンス | LICENSE の内容を要約 |

---

### 🏛️ ファイル2: `docs/architecture.md`

**役割**: システムの静的構造・動的データフロー・モジュール責務の解説。

#### 2-1. システム全体構成（flowchart TB）

DesktopCharacter アプリを中心に、以下を `flowchart TB` で図示する：
- 外部サービス（Gemini API / Ollama / Google Calendar API）
- ローカルサーバー（VOICEVOX subprocess）
- Windows OS API（win32gui / winrt / screeninfo / SAPI）
- ユーザー入出力（テキスト / 音声 / 立ち絵）

#### 2-2. ディレクトリ構造

実際の `Get-ChildItem` 結果をもとに、主要フォルダとファイルを木構造で列挙し、各行に役割コメントを付ける。

#### 2-3. コアアーキテクチャ: myapp + EventBus

- `myapp`（AppContext）: 保持するインスタンス一覧と役割
- EventBus の3種類の購読スタイルを表形式で説明
- スレッドとTkの注意点（`self.ui.after(...)` マーシャリング）
- `_setup_event_listeners()` が唯一の配線定義箇所である旨

#### 2-4. データフロー（sequenceDiagram）

以下の4ケースを個別に図示する：

| ケース | 内容 |
|---|---|
| 4-A: 起動シーケンス | `application start` → VOICEVOX起動 → AI接続テスト → 起動メッセージ |
| 4-B: ユーザーメッセージ（RAG OFF / ReAct OFF） | 入力 → RAG判定 → AI応答 → TTS + 立ち絵更新 |
| 4-C: アクティビティログ（5分毎） | `Req_UserActivityLog` → 並列収集 → join → `add_userlog` |
| 4-D: RAG付き応答（コード上に存在する場合のみ） | RAGリクエスト生成 → `UserDataLogger` → `RAGisReady` → AI応答 |

#### 2-5. サブシステムの詳細

各モジュールについて、責務・主要メソッド・制約を記載する：

- `UserSettings`（services/config_controller.py）: 設定パスの読み書き方法
- `AI_Manager`（ai/AI_main.py）: バックエンド切替・システムプロンプト構築・ReActループ
- `ReActツール`（ai_tools/）: パーミッション制御・自動検出の仕組み・追加手順
- `win_info_collector`（services/WindowsInfoCollecter.py）: 各メソッドと取得情報のテーブル
- `UI`（ui/UI_main.py）: 透過ウィンドウの実現方法（`-transparentcolor #888888`）

#### 2-6. 技術選定の記録

| 技術 | 理由と制約 |
|---|---|
| Python 3.9.13 | winrt の互換性制約（3.7〜3.9のみ） |
| tkinter | 標準ライブラリ・透過ウィンドウ対応 |
| EventBus（自前実装） | モジュール分離・並列処理・Tkブロック回避 |
| PyInstaller | 単一exe化・main.spec で ai_tools の動的スキャンに対応 |

---

### 🚀 ファイル3: `docs/release-guide.md`

**役割**: 開発環境構築・ビルド・配布に特化した手順書。

| セクション | 記述内容 |
|---|---|
| 1. 開発環境の構築 | 必要OS/Python・venv作成・pip install・config.json の設定パス一覧（APIキー値は空欄） |
| 2. ビルド手順 | `pip install pyinstaller` → `pyinstaller main.spec` → `dist/DesktopCharacter.exe` |
| 3. ビルド時の注意点 | 別PCでの動作確認必須・config.json の配置・VOICEVOX は別インストール |
| 4. 配布パッケージの作成 | 同梱ファイル一覧（APIキー除去を強調）・圧縮手順 |
| 5. リリース手順チェックリスト | 以下の5ステップをチェックボックス形式で |

チェックリストの5ステップ：
1. 手動デバッグ（主要操作の一通り確認）
2. `配布時添付ファイル/readme_説明.html` の更新
3. `main.py` の `CURRENT_APP_VERSION` を `YYYYMMDD` 形式で更新
4. ビルド → 配布パッケージ作成 → 別環境で動作確認
5. `tesu-dice/DesktopCharacter_forRelease` に GitHub リリース作成（タグ名 = バージョン番号）
6. Booth の商品ファイルを差し替え

---

## 3. 更新モード：差分ベースの判断フロー

### 3-1. 変更の影響範囲を特定する

```powershell
# 前回ドキュメント更新以降のコミット一覧を確認
git log --oneline docs/

# 変更されたソースファイルの一覧
git diff --name-only HEAD~10 HEAD
```

### 3-2. 変更パターン別の更新箇所

| 変更内容 | 更新が必要なファイル |
|---|---|
| 新しい `ai_tools/*.py` を追加 | `docs/architecture.md` §5（ReActツール）+ §2（ディレクトリ構造） |
| `_setup_event_listeners()` のイベント配線変更 | `docs/architecture.md` §4（データフロー） |
| `config.json` / `get_default_data()` の設定追加 | `docs/release-guide.md` §1（設定ファイル一覧） |
| 新機能・新サービス追加 | `README.md` 機能一覧 + `docs/architecture.md` §1（構成図）§5（サブシステム） |
| PyInstaller / ビルドプロセス変更 | `docs/release-guide.md` §2〜§4 |
| リリース手順変更 | `docs/release-guide.md` §5（チェックリスト） |
| Python バージョン・依存ライブラリ変更 | `README.md` クイックスタート + `docs/release-guide.md` §1 |

### 3-3. 更新時の注意事項

- 既存ドキュメントのセクション構造・ファイル名・見出しレベルは維持する
- 変更のないセクションは **編集しない**（不必要な差分を作らない）
- Mermaid 図を更新する場合は §1 の制約を再確認してから書く
- 「更新箇所なし」と判断した場合は、その根拠を明示して作業を終了する

---

## 4. 品質チェックリスト（出力前に必ず確認）

### 内容の正確性
- [ ] クラス名・メソッド名・設定パスがコードと完全に一致している
- [ ] 存在しない機能・メソッドを記述していない
- [ ] Python 3.9 / winrt の互換性制約が明記されている
- [ ] APIキーの値が含まれていない

### Mermaid 図
- [ ] フローチャートが `flowchart TB` で始まっている（`graph TB` でない）
- [ ] `flowchart TB` 直後に空行がない
- [ ] ノードラベルに `<br/>` や複数行テキストがない
- [ ] `%%{init: ...}%%` ディレクティブを使用していない
- [ ] sequenceDiagram の色分けが§1の規則に従っている

### 構造・フォーマット
- [ ] 日本語で書かれている（コード・パス・クラス名を除く）
- [ ] 各ファイルに目次またはセクション見出しがある
- [ ] テーブル・箇条書きを使ってスキャン性が高い
- [ ] `docs/architecture.md` と `docs/release-guide.md` への相互リンクがある（README.md から）

---

## 5. 呼び出し方のテンプレート

### ケースA: 全ドキュメントを新規生成する

```
この指示書（ドキュメント自動生成・更新指示書.md）に従い、
README.md・docs/architecture.md・docs/release-guide.md を新規生成してください。
作業前に §0 のスキャン手順をすべて実施してください。
```

### ケースB: コード変更後にドキュメントを更新する

```
この指示書（ドキュメント自動生成・更新指示書.md）に従い、
以下のコード変更を反映させるためにドキュメントを更新してください。

変更内容: [変更の概要を記載]
変更ファイル: [変更したファイル名を列挙]

更新モード（§3）で影響範囲を判断し、最小限の差分で更新してください。
```

### ケースC: 特定のファイルだけ再生成する

```
この指示書（ドキュメント自動生成・更新指示書.md）に従い、
docs/architecture.md のみを最新のコードをもとに再生成してください。
§0 のスキャン、§2-ファイル2 の構成、§4 の品質チェックを実施してください。
```

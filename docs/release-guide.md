# リリースガイド

開発環境の構築からビルド・配布までの手順書です。

---

## 1. 開発環境の構築

### 必要環境

- **OS**: Windows 10/11
- **Python**: 3.9.13（`winrt` の互換性制約。他バージョンでは `winrt` が動作しない）

### セットアップ手順

```powershell
# 仮想環境を作成
python -m venv .venv

# 仮想環境を有効化
.venv\Scripts\Activate.ps1

# 依存ライブラリをインストール
pip install -r requirements.txt

# requirements.txt に含まれていない追加ライブラリ
pip install pywin32 simpleaudio google-generativeai Pillow
```

### 設定ファイル

`config.json` を編集して以下を設定します。

| 設定パス | 内容 |
|---|---|
| `LLMSettings.Service` | `geminiAPI` または `Ollama` |
| `LLMSettings.geminiAPI.key` | Google AI Studio で取得した API キー |
| `LLMSettings.geminiAPI.model` | 使用する Gemini モデル名（例: `gemini-2.5-flash-lite`） |
| `LLMSettings.Ollama.URL` | Ollama サーバーの URL（デフォルト: `http://localhost:11434`） |
| `VoiceSettings.engine` | `None` / `windowsNarrator` / `VOICEVOX` |
| `VoiceSettings.VOICEVOX.path` | VOICEVOX の実行ファイルパス |

> **注意**: `config.json` には API キーが含まれます。git にコミットしないように注意してください。

### アプリの起動（開発時）

```powershell
python main.py
```

---

## 2. ビルド手順

### 前提

PyInstaller がインストールされていること。

```powershell
pip install pyinstaller
```

### ビルドコマンド

```powershell
pyinstaller main.spec
```

`main.spec` には以下の設定が含まれています。

- `--noconsole` 相当（コンソールウィンドウを非表示）
- `--onefile` 相当（単一 exe ファイルとして出力）
- `ai_tools/*.py` を `datas` として同梱（`ToolExecutor` の動的スキャンに対応）
- `collect_submodules('ai_tools')` で隠れインポートを明示

ビルド成果物は `dist/DesktopCharacter.exe` に出力されます。

### ビルド時の注意点

- **別 PC での動作確認が必須**: ビルドしたマシンの環境が exe に持ち込まれることがあります。ノート PC などの別環境に移して必ず動作確認を行ってください。
- `config.json` は exe と同じフォルダに置く必要があります（`config_controller.py` が `APP_DIR / "config.json"` を参照）。
- VOICEVOX を利用する場合、exe とは別に VOICEVOX 本体のインストールが必要です。

---

## 3. 配布パッケージの作成

配布物は以下のファイル・フォルダをひとつのフォルダにまとめて圧縮します。

```
配布フォルダ/
├── DesktopCharacter.exe        ← dist/ から取得
├── config.json                 ← API キーを空にしたもの
├── Character_setting.txt       ← キャラクター設定（同梱必須）
├── 立ち絵/                     ← キャラクター画像フォルダ
└── 配布時添付ファイル/
    ├── readme_説明.html         ← ユーザー向け説明書
    └── licenses/               ← ライセンスファイル
```

> **config.json の API キーを必ず空にしてから配布すること。**

---

## 4. リリース手順チェックリスト

### 1. デバッグ

- [ ] 自分で実際に使用し、主要な操作（会話・設定変更・終了）を一通り確認する

### 2. ユーザー向けドキュメントの更新

- [ ] `配布時添付ファイル/readme_説明.html` を更新する

### 3. バージョン情報の更新

- [ ] `main.py` の `app_start_message()` 内の `CURRENT_APP_VERSION` を更新する（形式: `YYYYMMDD`）

```python
# main.py の該当箇所
CURRENT_APP_VERSION = "20260201"  # ← ここを更新
```

### 4. ビルドと動作確認

- [ ] `pyinstaller main.spec` でビルド
- [ ] 配布パッケージを作成（API キー除去を確認）
- [ ] ノート PC 等の別環境に移して動作確認

### 5. GitHub リリースの作成

`services/release_check.py` がアプリ起動時に `tesu-dice/DesktopCharacter_forRelease` リポジトリの最新タグを確認し、バージョンを比較します。

- [ ] `tesu-dice/DesktopCharacter_forRelease` に新しいリリースを作成する
- [ ] タグ名を `CURRENT_APP_VERSION` と一致させる

### 6. Booth の商品ファイルを更新

- [ ] Booth の商品ページで配布ファイルを最新バージョンに差し替える

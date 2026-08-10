# DesktopCharacter

デスクトップ上に常駐するAIキャラクターとの会話・パーソナルナレッジマネジメント支援アプリ（Windows専用）

---

## コンセプト

情報化社会において、ユーザー自身が自分の行動や思考を振り返る時間は失われがちです。  
**DesktopCharacter** は、PCの作業画面に常駐するキャラクターがユーザーの作業状況を把握しながら自然に話しかけ、日常の記録を蓄積していくことで、パーソナルナレッジマネジメント（PKM）の助けとなることを目指しています。

仕事の直接的なアシスタントではなく、**「傍にいてくれる存在」** として、長時間作業への声かけや、視聴中のメディアへの感想など、にぎやかしとしての会話を重視しています。

曲でいうと：
[Be with Master](https://youtu.be/ZwMvF-PnUFc?si=irfstSJiNh7jo2Dh)
ミーティア
ビッグ・ラヴ・ミュージック
センス・オブ・ワンダー
---

## 主な機能

| 機能 | 概要 |
|---|---|
| **デスクトップ常駐キャラクター** | 透過ウィンドウで立ち絵を常時最前面表示。ドラッグで位置変更可能 |
| **AI会話** | Gemini API（クラウド）または Ollama（ローカル）を使ったキャラクター会話 |
| **音声合成（TTS）** | VOICEVOX または Windows Narrator でセリフを読み上げ |
| **音声入力（STT）** | ウェイクアップワード検知後にマイク入力を受け付け |
| **作業状況の監視** | アクティブウィンドウ・再生中のメディアをWindows APIで取得してAIに提供 |
| **ユーザーアクティビティログ** | 5分毎に作業状況を記録、1時間・1日単位でAIが要約 |
| **RAG（ログ参照会話）** | 蓄積したログをもとに過去の作業について会話できる |
| **ReActエージェント** | 複数のツールを組み合わせながら段階的に考えてから回答する応答モード |

---

## クイックスタート

### 必要環境

- **Windows 10/11**
- **Python 3.9.13**（`winrt` の互換性制約により3.9系が必須）
- VOICEVOX を利用する場合は別途インストールが必要

### セットアップ

```powershell
# 1. 仮想環境を作成・有効化
python -m venv .venv
.venv\Scripts\Activate.ps1

# 2. 依存ライブラリをインストール
pip install -r requirements.txt
pip install pywin32 simpleaudio google-generativeai Pillow
```

### 設定

`config.json` を開き、以下の項目を設定してください。

- **LLMSettings.geminiAPI.key** — Google AI Studio で取得した Gemini API キー
- **LLMSettings.Service** — `geminiAPI` または `Ollama` を選択
- **VoiceSettings.VOICEVOX.path** — VOICEVOX のインストールパス（使用する場合）

### 起動

```powershell
python main.py
```

---

## ドキュメント

| ドキュメント | 内容 |
|---|---|
| [アーキテクチャ](docs/architecture.md) | システム構成・モジュール構造・データフロー |
| [リリースガイド](docs/release-guide.md) | 開発環境構築・ビルド・配布手順 |

---

## 更新履歴

| バージョン | 内容 |
|---|---|
| 20260201 | 現行バージョン |
| 20250910 (1.02) | Ollama連携追加、UI改善、エラー出力・ログ機能追加 |
| 202507xx | Booth での配布開始（Gemini API会話・VOICEVOXによる音声） |

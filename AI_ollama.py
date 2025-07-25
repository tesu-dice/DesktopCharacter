import requests
import json
import base64
from io import BytesIO
from PIL import Image

# --- 設定 ---
OLLAMA_API_BASE_URL = "http://localhost:11434/api"
TEXT_MODEL_NAME = "gemma3:12b" # テキスト専用モデル。例: llama3, gemma:7b, elyza/elyza-japanese-llama-2-7b
VISION_MODEL_NAME = "llava" # 画像も扱えるモデル。例: llava, moondream (要ダウンロード: ollama run llava)

# --- 基本的なチャット機能 ---
def chat_with_llm(model_name: str, messages: list, stream: bool = False):
    """
    指定されたモデルとチャットを行う関数。
    messages: 会話履歴のリスト。例: [{"role": "user", "content": "こんにちは"}]
    stream: リアルタイムで応答を受け取るか (True) 、全て受け取ってから表示するか (False)
    """
    url = f"{OLLAMA_API_BASE_URL}/chat"
    headers = {"Content-Type": "application/json"}

    payload = {
        "model": model_name,
        "messages": messages,
        "stream": stream,
    }

    print(f"\n--- {model_name} モデルで応答を生成中... ---")
    try:
        if stream:
            # ストリーミングモードの場合
            with requests.post(url, headers=headers, data=json.dumps(payload), stream=True) as response:
                response.raise_for_status()
                full_response_content = ""
                for line in response.iter_lines():
                    if line:
                        try:
                            json_response = json.loads(line.decode('utf-8'))
                            content = json_response.get("message", {}).get("content", "")
                            full_response_content += content
                            print(content, end='', flush=True) # 少しずつ表示
                        except json.JSONDecodeError:
                            continue # 不完全なJSON行はスキップ
                print("\n") # 最後に改行
                return {"role": "assistant", "content": full_response_content.strip()}
        else:
            # 非ストリーミングモードの場合
            response = requests.post(url, headers=headers, data=json.dumps(payload))
            response.raise_for_status()
            result = response.json()
            assistant_message = result.get("message", {})
            print(f"アシスタント: {assistant_message.get('content', '').strip()}")
            return assistant_message

    except requests.exceptions.RequestException as e:
        print(f"エラーが発生しました: {e}")
        return {"role": "assistant", "content": "エラーにより応答できませんでした。"}

# --- 画像をBase64エンコードするヘルパー関数 ---
def encode_image_to_base64(image_path: str):
    """画像ファイルをBase64文字列にエンコードする"""
    try:
        # 画像を開き、サイズを調整して効率化することも検討
        # 例: img = Image.open(image_path).resize((512, 512))
        img = Image.open(image_path)
        
        # JPEGとして保存し、Base64エンコード
        buffered = BytesIO()
        img.save(buffered, format="JPEG")
        return base64.b64encode(buffered.getvalue()).decode('utf-8')
    except Exception as e:
        print(f"画像のエンコード中にエラーが発生しました: {e}")
        return None

# --- メインチャットループ ---
def main_chat_loop():
    print("Ollama LLM チャットプログラムを開始します。")
    print("終了するには 'exit' または 'quit' と入力してください。")
    print("画像を添付するには 'image:<画像ファイルパス>' と入力してください。")
    print(f"現在のテキストモデル: {TEXT_MODEL_NAME}")
    print(f"現在のVisionモデル: {VISION_MODEL_NAME}")

    # 会話履歴を格納するリスト
    # Ollama API の messages フォーマットに従う
    # [{"role": "user", "content": "Hello!"}, {"role": "assistant", "content": "Hi there!"}]
    conversation_history = []

    while True:
        user_input = input("\nあなた: ")

        if user_input.lower() in ["exit", "quit"]:
            print("チャットを終了します。")
            break

        # 画像入力の処理
        if user_input.lower().startswith("image:"):
            image_path = user_input[len("image:"):].strip()
            encoded_image = encode_image_to_base64(image_path)
            if encoded_image:
                # 画像とテキストを同時に送信（Visionモデルが必要）
                text_prompt = input("画像に関する質問や指示を入力してください: ")
                # LlavaのようなVisionモデルは 'images' キーでBase64画像を受け取ります
                conversation_history.append({"role": "user", "content": text_prompt, "images": [encoded_image]})
                response_message = chat_with_llm(VISION_MODEL_NAME, conversation_history, stream=True)
                conversation_history.append(response_message)
            else:
                print("指定された画像ファイルを読み込めませんでした。パスを確認してください。")
                continue # 次のループへ
        else:
            # テキスト入力の処理
            conversation_history.append({"role": "user", "content": user_input})
            # テキスト専用モデルを使用
            response_message = chat_with_llm(TEXT_MODEL_NAME, conversation_history, stream=True)
            conversation_history.append(response_message)

        # 必要に応じて、会話履歴が長くなりすぎないように管理
        # 例: 直近のN個のメッセージに制限するなど
        # if len(conversation_history) > 10:
        #     conversation_history = conversation_history[-10:] # 直近10件に制限する例

if __name__ == "__main__":
    main_chat_loop()
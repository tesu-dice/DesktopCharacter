"""
VOISONA Talk (VoisonaTalk) REST APIを利用したTTSエンジン連携。

参考: docs/開発予定/202610_VoisonaTalk連携/202610_VoisonaTalk連携要件定義.md
      docs/開発予定/202610_VoisonaTalk連携/VoisonaTalk連携_設計方針.md
"""

import subprocess
import time
import json
import wave
from io import BytesIO

import requests
from requests.auth import HTTPBasicAuth
import simpleaudio

DEFAULT_PORT = 32766
# POST /speech-syntheses の global_parameters.speed の実機確認済み制約（type:number, default:1, minimum:0.2, maximum:5）
SPEED_MIN = 0.2
SPEED_MAX = 5.0
SPEED_DEFAULT = 1.0


# VoisonaTalkアプリの起動（疎通確認・起動待機は行わない）
def start_server(path, launch_option=None, debug=-1):
    command = [path]
    if launch_option:
        command.append(launch_option)
    if debug >= 0:
        indent = "  " * debug
        print(f"{indent}TTS_VoisonaTalkEngine.py start_server() called. command = {command}")
        debug = debug + 1 if debug >= 0 else -1

    try:
        process = subprocess.Popen(command)
    except Exception as e:
        print("VoisonaTalkの実行に失敗しました。")
        print(e)
        return None
    return process


def kill_server(process, debug=-1):
    if process is None:
        print("終了対象のVoisonaTalkプロセスが存在しません。")
        return

    print(f"VoisonaTalkプロセスID: {process.pid} を終了します...")
    try:
        process.terminate()
        process.wait(timeout=5)
        print("VoisonaTalkプロセスは正常に終了しました。")
    except subprocess.TimeoutExpired:
        print("VoisonaTalkプロセスが時間内に終了しませんでした。強制終了を試みます。")
        process.kill()
        print("VoisonaTalkプロセスを強制終了しました。")
    except Exception as e:
        print(f"VoisonaTalkプロセスの終了中にエラーが発生しました: {e}")


# OSレベルでの起動テストの共通ロジック。startupinfoを渡せば非表示起動、Noneなら通常（ウィンドウ表示あり）起動になる。
# 起動→ウィンドウ生成待ち→可視ウィンドウ数の確認→後始末、までを行い、可視ウィンドウ数（int）を返す。
# 起動そのものに失敗した場合、または起動後すぐにプロセスが終了した場合はNoneを返す。
def _test_launch(path, startupinfo=None, wait_seconds=8, debug=-1):
    mode_label = "非表示(SW_HIDE)" if startupinfo is not None else "通常（ウィンドウ表示あり）"
    print(f"[{mode_label}] VoisonaTalkを起動します。path={path}")

    try:
        process = subprocess.Popen([path], startupinfo=startupinfo)
    except Exception:
        import traceback
        print(f"[{mode_label}] 起動に失敗しました。")
        traceback.print_exc()
        return None

    print(f"[{mode_label}] 起動しました（PID={process.pid}）。ウィンドウ生成を{wait_seconds}秒待ちます...")
    time.sleep(wait_seconds)

    if process.poll() is not None:
        print(f"[{mode_label}] 警告: プロセスが起動直後に終了しました（終了コード={process.returncode}）。")
        return None

    # 起動したプロセスに属する「可視」ウィンドウが存在するかを実際に調べる
    try:
        import win32gui
        import win32process
    except Exception:
        import traceback
        print(f"[{mode_label}] win32gui/win32processのimportに失敗しました（pywin32が未導入の可能性）。")
        traceback.print_exc()
        print(f"[{mode_label}] テスト用に起動したプロセスを終了します。")
        kill_server(process, debug=debug)
        return None

    visible_windows = []

    def _enum_handler(hwnd, _):
        _, pid = win32process.GetWindowThreadProcessId(hwnd)
        if pid == process.pid and win32gui.IsWindowVisible(hwnd):
            visible_windows.append(hwnd)

    try:
        win32gui.EnumWindows(_enum_handler, None)
    except Exception:
        import traceback
        print(f"[{mode_label}] ウィンドウ列挙中にエラーが発生しました。")
        traceback.print_exc()

    print(f"[{mode_label}] 結果: 可視ウィンドウが{len(visible_windows)}個見つかりました。")

    print(f"[{mode_label}] テスト用に起動したプロセスを終了します。")
    kill_server(process, debug=debug)
    return len(visible_windows)


# OSレベルでの強制非表示起動（subprocess.STARTUPINFO + SW_HIDE）が有効かどうかを確認するテスト関数。
# 要件定義8章「OSレベルでのウィンドウ非表示処理」の検証用。
# 単体実行（__main__ブロック内、VSCode等のデバッガからの直接実行を想定）専用であり、
# start_server/ui.UI_main._start_voisona_serverなど通常の起動フローからは呼ばない。
def test_hidden_launch(path, wait_seconds=8, debug=-1):
    startupinfo = subprocess.STARTUPINFO()
    startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    startupinfo.wShowWindow = subprocess.SW_HIDE

    visible_count = _test_launch(path, startupinfo=startupinfo, wait_seconds=wait_seconds, debug=debug)
    if visible_count is None:
        print("非表示起動テストは起動自体に失敗したため判定できませんでした。")
        return False
    if visible_count > 0:
        print("SW_HIDEは効いていません（可視ウィンドウが見つかりました）。")
        return False
    print("SW_HIDEによる非表示起動が有効な可能性があります。")
    return True


# 比較用: 通常（ウィンドウ表示あり）の起動テスト。
# 「非表示起動テストがそもそも起動自体に失敗しているのか」「起動はできているがSW_HIDEが効いていないだけなのか」を
# 切り分けるために、test_hidden_launchと同じ手順で通常起動側も確認できるようにしたもの。
# こちらも単体実行専用（--test-windowed-launch指定時）。
def test_windowed_launch(path, wait_seconds=8, debug=-1):
    visible_count = _test_launch(path, startupinfo=None, wait_seconds=wait_seconds, debug=debug)
    if visible_count is None:
        print("通常起動テストが起動自体に失敗しました。pathの設定やVoisonaTalk本体を確認してください。")
        return False
    if visible_count == 0:
        print("警告: 通常起動のはずが可視ウィンドウが見つかりませんでした。起動が完了していない、"
              "またはウィンドウ生成に時間がかかっている可能性があります（wait_secondsを増やして再試行してください）。")
        return False
    print("通常起動は想定通り可視ウィンドウありで起動しました。")
    return True


# 音声ライブラリ一覧レスポンスのdisplay_namesから表示名を取り出す。
# 実機確認結果: [{"language": "ja_JP", "name": "..."}, {"language": "en_US", "name": "..."}] という
# 言語ごとのオブジェクト配列で返ってくる（設計時に想定していたdict/単純listとは異なる）。
def _extract_display_name(display_names):
    if isinstance(display_names, list):
        for entry in display_names:
            if isinstance(entry, dict) and entry.get("language") == "ja_JP":
                return entry.get("name", "")
        if display_names:
            first = display_names[0]
            return first.get("name", "") if isinstance(first, dict) else str(first)
        return ""
    if isinstance(display_names, dict):
        if "ja_JP" in display_names:
            return display_names["ja_JP"]
        return next(iter(display_names.values()), "")
    if display_names:
        return str(display_names)
    return ""


# 名前付きEmotionオブジェクトをstyle_names順の数値配列(style_weights)に変換する純粋関数
def build_style_weights(emotion: dict, style_names: list) -> list:
    weights = [0.0] * len(style_names)
    if not emotion:
        return weights
    for name, value in emotion.items():
        if name not in style_names:
            continue
        idx = style_names.index(name)
        try:
            weights[idx] = max(0.0, min(1.0, float(value)))
        except (TypeError, ValueError):
            continue
    return weights


class VoisonaTalkClient:
    """VoisonaTalk Talk APIとの通信を担うクライアント。"""

    def __init__(self, usersetting, debug: int = -1):
        self.usersetting = usersetting

        port = usersetting.get_setting_value("VoiceSettings.VoisonaTalk.port")
        email = usersetting.get_setting_value("VoiceSettings.VoisonaTalk.account_email")
        password = usersetting.get_setting_value("VoiceSettings.VoisonaTalk.account_password")
        model = usersetting.get_setting_value("VoiceSettings.VoisonaTalk.Model")
        speed = usersetting.get_setting_value("VoiceSettings.VoisonaTalk.speed")

        self.base_url = f"http://localhost:{port}/api/talk/v1"
        self.auth = HTTPBasicAuth(email, password)

        # 設定UIの値をそのまま信頼せず、config.json手編集等による不正値もAPIの実際の制約でクランプしておく
        try:
            self.speed = max(SPEED_MIN, min(SPEED_MAX, float(speed)))
        except (TypeError, ValueError):
            self.speed = SPEED_DEFAULT

        # Modelは "表示名 (voice_name / voice_version)=voice_name=voice_version" 形式
        self.voice_name = None
        self.voice_version = None
        if model and "=" in model:
            parts = model.split("=")
            if len(parts) >= 3:
                self.voice_name, self.voice_version = parts[-2], parts[-1]

        if debug >= 0:
            indent = "  " * debug
            print(f"{indent}VoisonaTalkClient.__init__() called.")
            print(f"{indent}base_url = {self.base_url}, voice_name = {self.voice_name}, voice_version = {self.voice_version}")
            debug = debug + 1 if debug >= 0 else -1

        # 起動確認を兼ねてスタイル名一覧を即時取得しておく（未起動時は失敗を許容しNoneのまま）
        self.style_names = None
        self.get_voice_detail(debug=debug)

    def is_available(self, timeout=3, debug=-1) -> bool:
        try:
            r = requests.get(f"{self.base_url}/languages", auth=self.auth, timeout=timeout)
            return r.status_code == 200
        except requests.exceptions.RequestException:
            return False

    def wait_until_available(self, timeout_seconds=30, interval=1.0, debug=-1) -> bool:
        start = time.time()
        while time.time() - start < timeout_seconds:
            if self.is_available(debug=debug):
                return True
            time.sleep(interval)
        return False

    # 音声ライブラリ一覧を、VOICEVOXのget_speakers()と同じ契約で表示用文字列のリストとして返す
    def get_voices(self, debug=-1):
        try:
            r = requests.get(f"{self.base_url}/voices", auth=self.auth, timeout=10)
        except requests.exceptions.RequestException as e:
            print(f"VoisonaTalk音声ライブラリ一覧の取得に失敗しました。: {e}")
            return None
        if r.status_code != 200:
            print(f"VoisonaTalk音声ライブラリ一覧の取得に失敗しました。status_code={r.status_code}")
            return None

        raw_json = r.json()
        if debug >= 0:
            indent = "  " * debug
            print(f"{indent}GET /voices raw response = {json.dumps(raw_json, ensure_ascii=False, indent=2)}")

        # 実機確認結果: トップレベルは配列そのものではなく {"items": [...]} でラップされて返ってくる
        items = raw_json.get("items", []) if isinstance(raw_json, dict) else raw_json

        voices_list = []
        for v in items:
            voice_name = v.get("voice_name")
            voice_version = v.get("voice_version")
            display_name = _extract_display_name(v.get("display_names"))
            voices_list.append(f"{display_name} ({voice_name} / {voice_version})={voice_name}={voice_version}")
        return voices_list

    # 音声ライブラリの詳細（style_names等）を生データのdictで返す
    def get_voice_detail(self, voice_name=None, voice_version=None, debug=-1):
        is_self_target = voice_name is None and voice_version is None
        target_name = voice_name or self.voice_name
        target_version = voice_version or self.voice_version
        if not target_name or not target_version:
            return None

        try:
            r = requests.get(f"{self.base_url}/voices/{target_name}/{target_version}", auth=self.auth, timeout=10)
        except requests.exceptions.RequestException as e:
            if debug >= 0:
                print(f"VoisonaTalk音声ライブラリ詳細の取得に失敗しました。: {e}")
            return None
        if r.status_code != 200:
            if debug >= 0:
                print(f"VoisonaTalk音声ライブラリ詳細の取得に失敗しました。status_code={r.status_code}")
            return None

        detail = r.json()
        if debug >= 0:
            indent = "  " * debug
            print(f"{indent}GET /voices/{target_name}/{target_version} raw response = {json.dumps(detail, ensure_ascii=False, indent=2)}")
        if is_self_target:
            self.style_names = detail.get("style_names")
        return detail

    def get_default_audio_device(self, debug=-1):
        try:
            r = requests.get(f"{self.base_url}/audio-devices/default", auth=self.auth, timeout=10)
            if r.status_code == 200:
                return r.json()
        except requests.exceptions.RequestException:
            pass
        return None

    # destination=memoryで取得したWAVバイト列をsimpleaudioで再生し、完了を待つ
    def _play_wav_bytes(self, wav_bytes, debug=-1):
        with wave.open(BytesIO(wav_bytes), "rb") as wf:
            num_channels = wf.getnchannels()
            bytes_per_sample = wf.getsampwidth()
            sample_rate = wf.getframerate()
            frames = wf.readframes(wf.getnframes())
        wave_obj = simpleaudio.WaveObject(frames, num_channels, bytes_per_sample, sample_rate)
        play_obj = wave_obj.play()
        play_obj.wait_done()

    def _poll_until_done(self, request_uuid, timeout_seconds=60, interval=0.5, debug=-1):
        start = time.time()
        while time.time() - start < timeout_seconds:
            try:
                r = requests.get(f"{self.base_url}/speech-syntheses/{request_uuid}", auth=self.auth, timeout=(10.0, 30.0))
            except requests.exceptions.RequestException as e:
                return {"ok": False, "status_code": None, "reason": str(e)}
            if r.status_code != 200:
                return {"ok": False, "status_code": r.status_code, "reason": r.text}
            data = r.json()
            state = data.get("state")
            if state == "succeeded":
                return {"ok": True}
            if state == "failed":
                return {"ok": False, "status_code": None, "reason": data.get("error", "synthesis_failed")}
            time.sleep(interval)
        return {"ok": False, "status_code": None, "reason": "poll_timeout"}

    def _get_wav(self, request_uuid, debug=-1):
        try:
            r = requests.get(f"{self.base_url}/speech-syntheses/{request_uuid}/wav", auth=self.auth, timeout=(10.0, 60.0))
            if r.status_code == 200:
                return r.content
            print(f"VoisonaTalk WAV取得エラー: {r.status_code} {r.text}")
            return None
        except requests.exceptions.RequestException as e:
            print(f"VoisonaTalk WAV取得中に例外が発生しました。: {e}")
            return None

    def _delete_request(self, request_uuid, debug=-1):
        try:
            requests.delete(f"{self.base_url}/speech-syntheses/{request_uuid}", auth=self.auth, timeout=(5.0, 30.0))
        except Exception as e:
            print(f"VoisonaTalkリクエストの削除に失敗しました（無視して続行します）。: {e}")

    def text_to_speech(self, text, emotion, max_retry=20, debug=-1) -> dict:
        if debug >= 0:
            indent = "  " * debug
            print(f"{indent}TTS_VoisonaTalkEngine.py VoisonaTalkClient.text_to_speech() called.")
            print(f"{indent}text = {text}, emotion = {emotion}")
            debug = debug + 1 if debug >= 0 else -1

        if not text:
            return {"ok": True}

        # コンストラクタ時点で未起動だった等の理由でstyle_namesが未取得なら再試行する
        if self.style_names is None:
            self.get_voice_detail(debug=debug)

        payload = {
            "language": "ja_JP",
            "text": text,
            "voice_name": self.voice_name,
            "voice_version": self.voice_version,
            "destination": "memory",
        }
        # speedは設定UIで決めた値をスタイル・文章量・音声ライブラリに関わらず常に一律で適用する
        global_parameters = {"speed": self.speed}
        if self.style_names:
            global_parameters["style_weights"] = build_style_weights(emotion or {}, self.style_names)
        payload["global_parameters"] = global_parameters

        request_uuid = None
        last_error = None
        for attempt in range(max_retry):
            try:
                r = requests.post(f"{self.base_url}/speech-syntheses", json=payload, auth=self.auth, timeout=(10.0, 300.0))
            except requests.exceptions.RequestException as e:
                last_error = str(e)
                print(f"VoisonaTalk APIにアクセスできませんでした。リトライします。: {e}")
                continue

            if r.status_code in (200, 201):
                request_uuid = r.json().get("uuid")
                break
            elif r.status_code == 409:
                return {"ok": False, "status_code": 409, "reason": "queue_conflict"}
            else:
                return {"ok": False, "status_code": r.status_code, "reason": r.text}

        if request_uuid is None:
            return {"ok": False, "status_code": None, "reason": last_error or "connection_failed"}

        try:
            poll_result = self._poll_until_done(request_uuid, debug=debug)
            if not poll_result["ok"]:
                return poll_result

            wav_bytes = self._get_wav(request_uuid, debug=debug)
            if wav_bytes is None:
                return {"ok": False, "status_code": None, "reason": "wav_fetch_failed"}

            self._play_wav_bytes(wav_bytes, debug=debug)
            return {"ok": True}
        finally:
            self._delete_request(request_uuid, debug=debug)


if __name__ == "__main__":
    # このプログラムのみの動作確認: モデル(音声ライブラリ)とスタイル一覧を表示
    # 実行にはVoisonaTalkアプリが起動しAPIが有効になっている必要がある

    # 単体実行用: `python ui/TTS_VoisonaTalkEngine.py`のように直接実行した場合、
    # このファイルのあるui/がsys.path[0]になり "services" パッケージが見つからないため、
    # ai_tools/tools_main.py・services/speech2text.py と同じ方式でプロジェクトルートをパスに追加する。
    import sys
    import os
    _current_dir = os.path.dirname(os.path.abspath(__file__))
    _project_root = os.path.join(_current_dir, '..')
    if _project_root not in sys.path:
        sys.path.append(_project_root)

    from services.config_controller import read_configfile

    setting = read_configfile("config.json")
    client = VoisonaTalkClient(setting, debug=0)

    if not client.is_available(debug=0):
        print("VoisonaTalk APIに接続できません。起動・API設定・認証情報を確認してください。")
    else:
        voices = client.get_voices(debug=0) or []
        for v in voices:
            display_part, voice_name, voice_version = v.split("=")[0], v.split("=")[-2], v.split("=")[-1]
            print(f"{display_part}  (voice_name={voice_name}, voice_version={voice_version})")
            detail = client.get_voice_detail(voice_name, voice_version, debug=0)
            if detail:
                print(f"  styles: {detail.get('style_names')}")

    # --- OSレベル起動テスト（STARTUPINFO/SW_HIDE） ---
    # VSCode等のデバッガから直接このモジュールを実行する運用を想定し、コマンドライン引数ではなく
    # ここの定数を書き換えてテストパターンを選ぶ（新規にVoisonaTalkプロセスを起動するため、
    # 多重起動を避けたい場合は事前に既存のVoisonaTalkを終了しておくこと）。
    RUN_HIDDEN_LAUNCH_TEST = True      # 非表示起動（STARTUPINFO/SW_HIDE）のテストを実行するか
    RUN_WINDOWED_LAUNCH_TEST = True    # 比較用の通常起動（ウィンドウ表示あり）のテストを実行するか

    voisona_path = setting.get_setting_value("VoiceSettings.VoisonaTalk.path")
    if not voisona_path:
        print("\nVoiceSettings.VoisonaTalk.pathが未設定のため、起動テストをスキップします。")
    else:
        if RUN_HIDDEN_LAUNCH_TEST:
            print("\n--- OSレベル非表示起動（STARTUPINFO/SW_HIDE）のテスト ---")
            test_hidden_launch(voisona_path, debug=0)

        if RUN_WINDOWED_LAUNCH_TEST:
            print("\n--- 比較用: 通常起動（ウィンドウ表示あり）のテスト ---")
            test_windowed_launch(voisona_path, debug=0)

"""
# 概要
ユーザの音声入力をテキスト化してアプリケーションへ渡すSTT(Speech-To-Text)マネージャ。
キーボード操作なしでキャラクターに話しかけられるようにするための窓口モジュール。

# 設計の前提
継続的に外部APIへ音声を送信し続けるのは利用規約・帯域・遅延の面で問題があるため、
2段構成にしている。
    第1段: Windows SAPI のローカル認識で「ウェイクワード」だけを監視（軽量・常時動作）
    第2段: ウェイクワード検出後にだけ speech_recognition + Google Web Speech API を呼び、
           直後に話された本文を1回ぶん文字起こしする
これにより常時はオフラインで動作し、APIアクセスはユーザが意図して話しかけたときだけ発生する。

# 構成要素
- SapiEvents:
    SAPI(COM)のイベントハンドラ。`win32com.client.WithEvents` がコンストラクタ引数を
    受け取れない仕様のため、マネージャからの設定（コールバック・信頼度しきい値）は
    クラス属性 `_callback` / `_threshold` を介して受け渡す。
- SapiGrammarRecognizer:
    SAPIのインプロセス認識器を初期化し、ウェイクワード1語だけを文法に登録する。
    ディクテーション(自由発話)は明示的に無効化して負荷を抑えている。
- speech2text_manager:
    外部から扱うメインのクラス。EventBus と UserSettings を受け取り、
    監視スレッドの起動/停止、SAPI 検出後の本文取得、EventBus への結果発行までを担う。

# 処理フロー
1. `start_wakeup_waiting()` で監視スレッドを起動
2. スレッド内 `loop_wakeup_waiting()` が COM を初期化し、SAPI が常時マイクを聴取
3. ウェイクワードを検出すると `SapiEvents.OnRecognition` 経由で`_on_wakeup_detected()` が呼ばれる
4. `speech2text()` が speech_recognition でマイクから本文を録音し、Google API で文字起こし
5. `input_text()` が結果を EventBus の "MessageInput" イベントとして発行
   （以降は main.py の既存配線で RAG/ReAct 判定 → AI応答 → UI/TTS反映 と流れる）

# 依存ライブラリ
- pywin32 (win32com.client, pythoncom): SAPI(COM)制御
- SpeechRecognition: マイク入力ラップと Google Web Speech API クライアント
- pyaudio: SpeechRecognition がマイク入力を取るために必要

# 設定の連動
ウェイクワード・検出しきい値・マイクデバイスは UserSettings から読み出す:
    - ApplicationSettings.SpeechInput.WakeUpWord  (str)  : SAPI に登録するウェイクワード
    - ApplicationSettings.SpeechInput.Threshold   (float): EngineConfidence のしきい値
    - ApplicationSettings.SpeechInput.MicDevice   (int/str): PyAudio のデバイスインデックス
                                                            ("default"/""/None で既定の入力デバイス)
未登録パスはクラス側のデフォルトにフォールバックする（警告ログを出さない _get_setting_item 経由）。
EventBus("SettingsUpdated") を購読しており、設定変更時に on_settings_updated() が呼ばれて:
    - マイク変更 → _mic / _target_energy をリセット（次回 speech2text() で再構築）
    - ウェイクワード変更 → SAPI 文法は構築時固定のため監視ループを再起動
    - しきい値変更 → SapiEvents._threshold をクラス属性経由で即時反映（ループ継続のまま）

# 既知の注意点
- SAPI と PyAudio が同じ既定マイクを共有するため、本文取得中はデバイス競合の可能性あり。
- 本文取得中 (`speech2text()` 実行中) は `PumpWaitingMessages` が走らないため、
  その間に飛んできた SAPI イベントは取りこぼし扱いとなる（仕様として許容）。
- 上記3つの設定パスは現時点で services/config_controller.py:get_default_data() に未定義。
  読み出しはフォールバック対応済みのため動作はするが、設定UIから操作可能にするには
  config_controller 側の default_data へ同パスを追加する必要がある。
"""
# =============================================================================
# import について
# 既存コードベースで利用済みの標準ライブラリ
#   - threading, time, logging: 既に Event_Bus / UserDataLogger 等で利用。
#
# このモジュールで新規追加（いずれも tests/ 配下のサンプルコードに由来）
#   - win32com.client (pywin32 同梱):
#       tests/文字起こし_windowsSAPIワード検出.py で採用。SAPI(COM)に
#       Dispatchするために必須。requirements.txt の pywin32 でカバー済み。
#   - pythoncom (pywin32 同梱):
#       同テストコードで採用。スレッドごとの CoInitialize と
#       PumpWaitingMessages を回すために必須。
#   - speech_recognition (sr):
#       tests/文字起こし_google.py で採用。マイク取得と Google Web Speech API
#       呼び出しをラップ。requirements.txt に追加済み。
#   - gc:
#       tests/文字起こし_google.py で採用（テスト側コメント: 「徹底したメモリ解放」）。
#       recognize_google() ごとに audio バッファが残留するため、テスト側の設計に
#       倣い呼び出し終了ごとに即時回収して常駐メモリを抑える。標準ライブラリのため
#       requirements.txt 追加は不要。
# =============================================================================
if __name__ != "__main__":
    import threading
    import time
    import gc
    import logging

    import win32com.client
    import pythoncom
    import speech_recognition as sr  # pip install SpeechRecognition

    from services.config_controller import UserSettings
    from services.Event_Bus import EventBus
else:
    # 単体テスト用: services/speech2text.py を直接実行できるようにパスを通す
    import sys
    import os
    _current_dir = os.path.dirname(os.path.abspath(__file__))
    _project_root = os.path.join(_current_dir, '..')
    if _project_root not in sys.path:
        sys.path.insert(0, _project_root)

    import threading
    import time
    import gc
    import logging

    import win32com.client
    import pythoncom
    import speech_recognition as sr  # pip install SpeechRecognition

    from services.config_controller import UserSettings, read_configfile
    from services.Event_Bus import EventBus

logger = logging.getLogger(__name__)


class SapiEvents:
    """SAPIのCOMイベントハンドラ。
    win32com.client.WithEvents はコンストラクタ引数を渡せないため、
    マネージャからの設定はクラス属性経由で行う。"""
    _callback = None    # detected_text, confidence -> None
    _threshold = 0.9

    def OnRecognition(self, StreamNumber, StreamPosition, RecognitionType, Result):
        try:
            res = win32com.client.Dispatch(Result)
            phrase_info = res.PhraseInfo
            elements = phrase_info.Elements
            if elements.Count <= 0:
                return

            el = elements.Item(0)
            try:
                conf = el.EngineConfidence  # 0.0 ~ 1.0
            except AttributeError:
                conf = 0.0

            text = phrase_info.GetText()
            logger.debug(f"SAPI検知: '{text}' (Confidence: {conf})")

            if conf >= SapiEvents._threshold and SapiEvents._callback is not None:
                SapiEvents._callback(text, conf)
        except Exception as e:
            logger.warning(f"SapiEvents.OnRecognition Error: {e}")


class SapiGrammarRecognizer:
    """ウェイクワードのみを文法登録した SAPI インプロセス認識器。"""
    def __init__(self, wakeup_word: str):
        self.wakeup_word = wakeup_word
        self.recognizer = win32com.client.Dispatch("SAPI.SpInprocRecognizer")

        # マイク（既定の入力デバイス）
        category = win32com.client.Dispatch("SAPI.SpObjectTokenCategory")
        category.SetId(r"HKEY_LOCAL_MACHINE\SOFTWARE\Microsoft\Speech\AudioInput")
        token = win32com.client.Dispatch("SAPI.SpObjectToken")
        token.SetId(category.Default)
        self.recognizer.AudioInput = token

        # 認識コンテキストとイベント
        self.context = self.recognizer.CreateRecoContext()
        self.event_handler = win32com.client.WithEvents(self.context, SapiEvents)

        # 文法（ディクテーションは無効化し、ウェイクワード1語だけを登録）
        self.grammar = self.context.CreateGrammar()
        self.grammar.DictationLoad("", 0)
        rule = self.grammar.Rules.Add("WakeUpRule", 0x1, 1)  # 0x1 = TopLevel
        rule.InitialState.AddWordTransition(None, wakeup_word)
        self.grammar.Rules.Commit()
        self.grammar.CmdSetRuleState("WakeUpRule", 1)

        logger.info(f"SAPI: '{wakeup_word}' を監視中")


class speech2text_manager():

    def __init__(self, bus: EventBus, setting: UserSettings, debug: int = -1):
        self.bus = bus
        self.setting = setting
        self._thread = None
        self.debug = debug

        # config から値を読み出す。
        self._load_settings()

        # speech2text() のリソース。
        # テストコード tests/文字起こし_google.py では Microphone と環境音ベースライン
        # (target_energy) をループ外で1度だけ生成・測定している。本実装ではマネージャ
        # 寿命 = 監視セッションと見なし、インスタンス属性としてキャッシュする。
        # 初回 speech2text() 呼び出し時に遅延初期化し、マイク設定が変わった際は
        # on_settings_updated() でリセットして再構築する。
        self._mic = None
        self._target_energy = None
        self._is_processing = False  # 二重検出防止フラグ

        # 設定更新イベントを購読
        self.bus.subscribe("SettingsUpdated", self.on_settings_updated)

    # 設定から各値を取得して設定
    def _load_settings(self):
        #読み取り
        self.is_running = self.setting.get_setting_value("Speech2TextSettings.on/off")
        self.wakeup_word = self.setting.get_setting_value("Speech2TextSettings.wakeupword")
        self.threshold = 0.01 * self.setting.get_setting_value("Speech2TextSettings.threshold")
        self._mic_device_index = 0 #self.setting.get_setting_value("") #いったんシステム準拠のマイクを利用
        
        #各値のエラーハンドリング

        # しきい値はクラス属性経由でSAPIイベントハンドラへ即時反映可能（ループ稼働中でもOK）
        SapiEvents._threshold = self.threshold

        if self.is_running:
            self.start_wakeup_waiting()
        else:
            self.stop_wakeup_waiting()


    def on_settings_updated(self, new_settings: UserSettings):
        """設定更新時のフック。EventBus("SettingsUpdated") で呼ばれる。
        - マイク変更時: _mic と _target_energy をリセット（次回 speech2text() で再構築）
        - ウェイクワード変更時: SAPI 文法は構築時固定のため監視ループを再起動
        - しきい値のみの変更: _load_settings 内で SapiEvents._threshold を更新するだけで反映
        """
        logger.info("speech2text_manager の設定を更新します...")
        old_wakeup = self.wakeup_word
        old_mic_index = self._mic_device_index

        self.setting = new_settings
        self._load_settings()

        if old_mic_index != self._mic_device_index:
            logger.info(f"マイクデバイス変更を検知: {old_mic_index} -> {self._mic_device_index} 次回 speech2text() で再構築します")
            self._mic = None
            self._target_energy = None

        if old_wakeup != self.wakeup_word and self.is_running:
            logger.info(f"ウェイクワード変更を検知: '{old_wakeup}' -> '{self.wakeup_word}' 監視ループを再起動します")
            self.stop_wakeup_waiting()
            if self._thread is not None:
                self._thread.join(timeout=1.0)
            self.start_wakeup_waiting()

        logger.info("speech2text_manager の設定更新が完了しました。")

    def start_wakeup_waiting(self):
        """スレッドを立ててウェイクワード監視を開始する"""
        if (self.is_running):
            self._thread = threading.Thread(target=self.loop_wakeup_waiting, daemon=True)
            self._thread.start()
            logger.info(f"SpeechToText: 監視スレッドを開始しました (Word: {self.wakeup_word})")

    def stop_wakeup_waiting(self):
        """監視を停止する"""
        self.is_running = False
        logger.info("SpeechToText: 停止要請を受け付けました")

    def loop_wakeup_waiting(self):
        """スレッド内で実行されるメインループ。
        COMの初期化はスレッドごとに必要。"""
        pythoncom.CoInitialize()
        try:
            SapiEvents._callback = self._on_wakeup_detected
            SapiEvents._threshold = self.threshold

            recognizer = SapiGrammarRecognizer(self.wakeup_word)

            while self.is_running:
                # Windowsのメッセージキューを処理してSAPIイベントを発火
                pythoncom.PumpWaitingMessages()
                # speech2text 完了後のフラグリセット。
                # PumpWaitingMessages() が返ってからリセットすることで、
                # 同一ポンプ内に積まれていた二重検出イベントを確実にスキップできる。
                if self._is_processing:
                    self._is_processing = False
                time.sleep(0.1)
        except Exception as e:
            logger.error(f"SpeechToText Loop Error: {e}")
        finally:
            SapiEvents._callback = None
            pythoncom.CoUninitialize()

    def _on_wakeup_detected(self, detected_text: str, confidence):
        """SapiEvents から呼ばれる。ウェイクワード検出後、本文を1回取りに行く。
        _is_processing フラグが立っている間は二重実行をスキップする。
        フラグのリセットは呼び出し元の loop_wakeup_waiting で行う。"""
        if self._is_processing:
            logger.info(f"ウェイクワード検出をスキップ: 処理中 ('{detected_text}' conf={confidence})")
            return
        self._is_processing = True
        if self.debug > 0:
            print("ウェイクアップワードを検出しました。")
        logger.info(f"ウェイクワード検出: '{detected_text}' (conf={confidence})")
        print("ウェイクアップワードを検出しました。")
        text = self.speech2text()
        if text:
            self.input_text(text)
        # フラグのリセットはここで行わない。
        # PumpWaitingMessages() は同一呼び出し内でキューに積まれたイベントも処理するため、
        # この関数が返った直後に2回目のイベントが発火する可能性がある。
        # フラグを True のまま返し、PumpWaitingMessages() が戻った後のメインループでリセットする。

    def speech2text(self) -> str:
        """googleRecognizerで一回だけ文字起こしして文字列を返す。

        tests/文字起こし_google.py の `light_wake_word_monitor` に準拠した構造:
          - Microphone はループ外（本実装ではインスタンス属性）で1度だけ生成
          - 環境音は専用 Recognizer(r_init) で1度だけ測定し target_energy を保持
          - 呼び出しごとに Recognizer を新規生成し target_energy を流用
          - listen() の引数: timeout=1.0, phrase_time_limit=3
          - finally で del + gc.collect() による即時メモリ解放
        """
        audio = None
        r = None
        try:
            # Microphone はインスタンス寿命中キャッシュ（マイク設定変更時のみ on_settings_updated で破棄）
            if self._mic is None:
                self._mic = sr.Microphone(device_index=self._mic_device_index)

            # 環境音ベースラインは初回のみ測定（テストコード踏襲: 専用 r_init、duration=2、×1.2）
            if self._target_energy is None:
                with self._mic as source:
                    r_init = sr.Recognizer()
                    r_init.adjust_for_ambient_noise(source, duration=2)
                    self._target_energy = r_init.energy_threshold * 1.2  # 感度を下げて誤作動防止
                    del r_init

            # 呼び出しごとに Recognizer を新規生成（テストコードのループ内パターン）
            r = sr.Recognizer()
            r.energy_threshold = self._target_energy
            r.dynamic_energy_threshold = False

            with self._mic as source:
                #検出の際の設定。timeout:無音が何秒続いたら終了するか。phrase_time_limit:最大何秒までの長さ検出するか。
                audio = r.listen(source, timeout=3.0, phrase_time_limit=10)
            text = r.recognize_google(audio, language='ja-JP')
            logger.info(f"STT: {text}")
            return text
        except sr.WaitTimeoutError:
            logger.info("STT: 音声入力タイムアウト")
            return ""
        except sr.UnknownValueError:
            logger.info("STT: 音声を認識できませんでした")
            return ""
        except sr.RequestError as e:
            logger.warning(f"STT: API/ネットワークエラー: {e}")
            return ""
        except Exception as e:
            logger.warning(f"STT: 予期せぬエラー: {e}")
            return ""
        finally:
            # テストコードに準拠した即時メモリ解放（recognize_google が audio バッファを残留させるため）
            if audio is not None:
                del audio
            if r is not None:
                del r
            gc.collect()

    def input_text(self, text: str):
        """文字起こし結果を EventBus へ発行する。
        既存のテキスト入力と同じ "MessageInput" に乗せて以降のフローを再利用する。"""
        if not text:
            return
        self.bus.publish("MessageInput", {"role": "user", "parts": [text]})


if __name__ == "__main__":
    """
    単体テスト。
    1. EventBus と UserSettings を最小構成で組み立て、speech2text_manager を
       設定に従って初期化できることを確認する。
    2. start_wakeup_waiting() でウェイクワード待機を起動できることを確認する。
       Ctrl+C で停止。
    """
    print("=== speech2text.py 単体テスト ===\n")

    bus = EventBus()
    setting =read_configfile()  # config 未登録項目はクラス側のデフォルトにフォールバック
    manager = speech2text_manager(bus, setting)

    print("初期化完了:")
    print(f"  wakeup_word      = {manager.wakeup_word!r}")
    print(f"  threshold        = {manager.threshold}")
    print(f"  mic_device_index = {manager._mic_device_index} (None=既定の入力デバイス)")

    print(f"\nウェイクワード待機を開始しました。'{manager.wakeup_word}' と話しかけてください。")
    print("Ctrl+C で停止します。")
    try:
        while manager.is_running:
            time.sleep(0.5)
    except KeyboardInterrupt:
        print("\n停止要請を送信...")
        manager.stop_wakeup_waiting()
        time.sleep(0.5)

    print("\n=== 単体テスト完了 ===")

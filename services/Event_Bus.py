"""
# 設計思想
ソフトウェア設計のルールである  
「オープン・クローズドの原則」、「関心の分離」、「単一責任の原則」？  
に従って各アプリケーションの動作を分離する目的として作成。  

# 想定動作
main.pyで初期化された後、各サービスおよびクラスに渡され、  
各モジュールの初期化でこのクラスに対するSubscribe（イベント名と関数）を行う。
その後、対応した名前のPublish(発行)が行われる。
このとき登録された関数が購読されたリストに従って呼び出し・処理される。


"""
import threading
import time

class EventBus:
    def __init__(self):
        self._listeners = {}
        self._conditional_listeners = {}

    def subscribe(self, event_type: str, listener):
        print("EvnetBus.subscribe() called", event_type, listener)
        if event_type not in self._listeners:
            self._listeners[event_type] = []
        self._listeners[event_type].append(listener)

    def publish(self, event_type: str, *args, **kwargs):
        print("EvnetBus.publish() called", event_type, args, kwargs)
        if event_type in self._listeners:
            for listener in self._listeners[event_type]:
                thread = threading.Thread(target=listener, args=args, kwargs=kwargs)
                thread.daemon = True
                thread.start()

        self._check_conditional_listeners(event_type, *args, **kwargs)

    def subscribe_when(self, event_types: list, callback):
        """
        複数のイベントがすべて発行されたときにコールバックを実行するよう購読する。
        """
        key = tuple(sorted(event_types))
        if key not in self._conditional_listeners:
            self._conditional_listeners[key] = {
                'callback': callback,
                'required_events': set(event_types),
                'event_order': event_types,  # 引数の順序を保証するためのリスト
                'received_data': {}  # 受信したイベントの引数を保存する辞書
            }
        
    def _check_conditional_listeners(self, published_event_type, *args, **kwargs):
        for key, config in self._conditional_listeners.items():
            if published_event_type in config['required_events']:
                # 発行されたイベントの引数を保存
                config['received_data'][published_event_type] = (args, kwargs)
                
                # 必要なイベントがすべて揃ったかチェック
                if len(config['received_data']) == len(config['required_events']):
                    print(f"All required events {key} have been received. Executing callback.")
                    
                    # 保存した引数を指定された順序でリストアップ
                    ordered_args = []
                    for event in config['event_order']:
                        # argsのみを単純化して追加
                        if config['received_data'][event][0]:
                           ordered_args.extend(config['received_data'][event][0])
                    
                    callback = config['callback']
                    thread = threading.Thread(target=callback, args=ordered_args)
                    thread.daemon = True
                    thread.start()
                    
                    # イベントを再受信できるように状態をリセット
                    config['received_data'].clear()

if __name__ == "__main__":    # テストコード
    # EventBusのインスタンスを取得
    event_bus = EventBus()

    # 複数のイベントが揃ったときに実行される関数を定義
    # 受け取った引数を順に表示する
    def on_a_b_c_received(arg_a, arg_b, arg_c):
        print("--- Callback function started ---")
        print(f"Argument from 'a': {arg_a}")
        print(f"Argument from 'b': {arg_b}")
        print(f"Argument from 'c': {arg_c}")
        print("--- Callback function finished ---")
    
    def on_a_d_received(arg_a, arg_d):
        print("--- Callback function started ---")
        print(f"Argument from 'a': {arg_a}")
        print(f"Argument from 'd': {arg_d}")
        print("--- Callback function finished ---")

    # イベントバスに購読を登録
    # "a", "b", "c" のイベントがすべて発行されたら on_a_b_c_received を実行
    event_bus.subscribe_when(["a", "b", "c"], on_a_b_c_received)
    event_bus.subscribe_when(["a", "d"], on_a_d_received)

    # 各モジュールが初期化を完了したらイベントを発行
    event_bus.publish("a", ["a was published", 1])
    event_bus.publish("b", ["b was published", 1, 2])
    event_bus.publish("c", ["c was published", 1, 2, 3] ) # これは条件に含まれないので無視される
    event_bus.publish("d", ["d was published"]) # これで条件が満たされる
    event_bus.subscribe_when(["a", "b", "c"], on_a_b_c_received)
    event_bus.publish("a", ["a was published", 1])
    event_bus.publish("b", ["b was published", 1, 2])
    event_bus.publish("c", ["c was published", 1, 2, 3] ) # これは条件に含まれないので無視される
    
    # スレッド処理が完了するのを待つ
    time.sleep(1)
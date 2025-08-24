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

class EventBus:
    """シンプルなイベント発行/購読システム"""
    def __init__(self):
        self._listeners = {}

    def subscribe(self, event_type: str, listener):
        if event_type not in self._listeners:
            self._listeners[event_type] = []
        self._listeners[event_type].append(listener)

    def publish(self, event_type: str, *args, **kwargs):
        if event_type in self._listeners:
            for listener in self._listeners[event_type]:
                thread = threading.Thread(target=listener, args=args, kwargs=kwargs)
                thread.daemon = True
                thread.start()
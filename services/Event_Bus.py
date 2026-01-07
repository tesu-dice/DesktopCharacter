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
import traceback

class EventBus:
    def __init__(self):
        self._listeners = {}
        self._conditional_listeners = {}
        self._workflows = {}

    def subscribe(self, event_type: str, listener):
        print(f"EvnetBus.subscribe() called: event='{event_type}', listener='{listener.__name__}'")
        if event_type not in self._listeners:
            self._listeners[event_type] = []
        self._listeners[event_type].append(listener)

    def subscribe_workflow(self, trigger_event: str, handler, response_event: str):
        """
        トリガーイベント、処理ハンドラ、レスポンスイベントを登録してワークフローを定義する。
        1つのトリガーに複数のワークフローを登録可能。
        """
        print(f"EvnetBus.subscribe_workflow() called: trigger='{trigger_event}', handler='{handler.__name__}', response='{response_event}'")
        if trigger_event not in self._workflows:
            self._workflows[trigger_event] = []
        self._workflows[trigger_event].append({
            'handler': handler,
            'response_event': response_event
        })

    def publish(self, event_type: str, *args, **kwargs):
        print(f"EvnetBus.publish() called: event='{event_type}', args={args}, kwargs={kwargs}")
        
        # 通常のリスナーを実行
        if event_type in self._listeners:
            for listener in self._listeners[event_type]:
                thread = threading.Thread(target=listener, args=args, kwargs=kwargs)
                thread.daemon = True
                thread.start()

        # ワークフローを実行 (複数の場合も対応)
        if event_type in self._workflows:
            # 同じトリガーに紐づく全てのワークフロー定義をループ処理
            for workflow_config in self._workflows[event_type]:
                
                # 各ワークフローを独立したスレッドで実行するためのラッパー関数
                def _workflow_executor(config, thread_args, thread_kwargs):
                    try:
                        handler = config['handler']
                        response_event = config['response_event']
                        
                        # ハンドラを実行して結果を取得
                        result = handler(*thread_args, **thread_kwargs)
                        
                        # 戻り値をそのまま次のイベントに渡す
                        if isinstance(result, tuple):
                            self.publish(response_event, *result)
                        elif result is not None:
                            self.publish(response_event, result)
                        else:
                            self.publish(response_event)
                        
                    except Exception as e:
                        print(f"--- WORKFLOW ERROR in event '{event_type}' ---")
                        traceback.print_exc()
                        print("-----------------------------------------")
                        
                        # エラーイベントを発行
                        error_kwargs = thread_kwargs.copy()
                        error_kwargs['error'] = e
                        error_kwargs['original_event'] = event_type
                        self.publish("WORKFLOW_ERROR", **error_kwargs)

                # ループの各イテレーションで、その時点の workflow_config をラッパーに渡す
                thread = threading.Thread(target=_workflow_executor, args=(workflow_config, args, kwargs))
                thread.daemon = True
                thread.start()

        # 条件付きリスナーをチェック
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
                'event_order': event_types,
                'received_data': {}
            }
        
    def _check_conditional_listeners(self, published_event_type, *args, **kwargs):
        for key, config in self._conditional_listeners.items():
            if published_event_type in config['required_events']:
                # イベントから渡された引数を保存
                config['received_data'][published_event_type] = {'args': args, 'kwargs': kwargs}
                
                if len(config['received_data']) == len(config['required_events']):
                    print(f"All required events {key} have been received. Executing callback.")
                    
                    # イベント順序に従って引数を整理
                    final_args = []
                    final_kwargs = {}
                    for event in config['event_order']:
                        data = config['received_data'][event]
                        final_args.extend(data['args'])
                        final_kwargs.update(data['kwargs'])
                    
                    callback = config['callback']
                    # スレッドでコールバックを実行
                    thread = threading.Thread(target=callback, args=final_args, kwargs=final_kwargs)
                    thread.daemon = True
                    thread.start()
                    
                    # 使用済みのデータをクリア
                    config['received_data'].clear()

if __name__ == "__main__":
    # EventBusのインスタンスを取得
    event_bus = EventBus()

    # --- ワークフロー機能のテスト ---
    print("\n--- Workflow Test ---")

    # 1. 処理ハンドラを定義
    def get_user_name(**kwargs):
        print("  [Handler] get_user_name called.")
        return "Taro"

    def get_user_activity(**kwargs):
        print("  [Handler] get_user_activity called.")
        return "programming"

    # 2. レスポンス受信者を定義
    def on_user_data_ready(**kwargs):
        print(f"  [Receiver] Event '{kwargs.get('event_type')}' received data: {kwargs.get('data')}")

    # 3. 合流処理のハンドラを定義
    def on_all_user_data_ready(name, activity):
        print(f"\n  [Join Receiver] All data received! Name: {name}, Activity: {activity}")

    # 4. ワークフローとリスナーを登録
    # 同じトリガーに複数のワークフローを登録
    event_bus.subscribe_workflow("REQUEST_USER_DATA", get_user_name, "USER_NAME_READY")
    event_bus.subscribe_workflow("REQUEST_USER_DATA", get_user_activity, "USER_ACTIVITY_READY")

    # 各レスポンスイベントを購読
    event_bus.subscribe("USER_NAME_READY", on_user_data_ready)
    event_bus.subscribe("USER_ACTIVITY_READY", on_user_data_ready)

    # 合流リスナーを登録
    event_bus.subscribe_when(["USER_NAME_READY", "USER_ACTIVITY_READY"], on_all_user_data_ready)

    # 5. ワークフローを起動
    print("\nStep 5: Publishing REQUEST_USER_DATA to trigger multiple workflows...")
    event_bus.publish("REQUEST_USER_DATA", requester_id="AI_Agent")
    
    time.sleep(1)
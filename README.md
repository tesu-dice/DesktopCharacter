デスクトっプにキャラクターを設置、会話できるようにする。

main		プログラムの初期化、設定の読み込み等

textsystem	geminiからのリマインドや感情のコマンドの読み分け、characterへの更新,UIのUpdate, Calenderからタスクや予定の取得・追加

gemini		geminiAPIをたたいてセリフを取得、また、コマンドを指示した形で返してもらってキャラの状態変更

character	キャラクターの立ち絵や声、そのほかステータスの管理、保持

VoiceVox 	キャラクターの音声生成

UI		ユーザへの出力

Calendar	GoogleCalendar,Taskから予定を取得、場合によっては追加によって現状の記録を残す。








・初期構想
tkinterでデスクトップマスコット
    pyTorchで自然言語処理できるようにする。

・実装したい機能
日にちと時間を言って挨拶する機能（テキスト表示）
時計を画面端に表示
各種UIの表示設定をするウィンドウを作成。
カレンダー機能＋予定入力
n分ごとのアクティブウィンドウの取得および日々の記録作成機能
メモ機能	閉じてるときは画面の端に見えるように、
		開くとスライドして見える。











20250321ローカルからgithub管理に切り替え

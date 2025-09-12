import sys
import csv
from duckduckgo_search import DDGS

# --- DuckDuckGo検索を実行する関数 ---
def duckduckgo_search(query, num_results):
    """
    DuckDuckGo Searchを使用して指定された件数の検索結果を取得します。
    """
    search_results = []
    try:
        print(f"検索中: '{query}' ({num_results} 件)")
        with DDGS(timeout=10) as ddgs:
            results = list(ddgs.text(keywords=query, region='jp-jp', max_results=num_results))
            for item in results:
                search_results.append({
                    "title": item.get('title', 'N/A'),
                    "url": item.get('href', 'N/A'),
                    "snippet": item.get('body', 'N/A')
                })
        return search_results
    except Exception as e:
        print(f"検索エラー: {e}")
        return []

# --- 検索結果をCSVファイルに書き込む関数 ---
def save_to_csv(data, filename="search_results.csv"):
    """
    検索結果のリストをCSVファイルに保存します。
    """
    if not data:
        print("保存するデータがありません。")
        return
        
    keys = data[0].keys()
    with open(filename, 'w', newline='', encoding='utf-8') as f:
        dict_writer = csv.DictWriter(f, fieldnames=keys)
        dict_writer.writeheader()
        dict_writer.writerows(data)
    print(f"検索結果が '{filename}' に保存されました。")

# --- メイン処理 ---
if __name__ == "__main__":
    print("DuckDuckGo CLI 検索ツールへようこそ！")
    print("検索結果は 'search_results.csv' に保存されます。")
    print("終了するには 'exit' と入力してください。")
    
    # 無限ループでユーザーからの入力を待つ
    while True:
        try:
            # 検索ワードと取得件数をユーザーに入力させる
            search_query = input("\n検索ワードを入力してください: ")
            
            # 終了コマンド
            if search_query.lower() == 'exit':
                print("ツールを終了します。")
                break

            results_count_input = input("取得件数を入力してください (例: 5): ")
            results_count = int(results_count_input)

            # 検索を実行
            results = duckduckgo_search(search_query, results_count)

            # 検索結果をCSVに保存
            save_to_csv(results)

        except ValueError:
            print("エラー: 取得件数は整数で入力してください。")
        except Exception as e:
            print(f"予期せぬエラーが発生しました: {e}")
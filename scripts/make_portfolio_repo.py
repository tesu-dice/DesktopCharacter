"""
公開用（ポートフォリオ / リリース通知用）リポジトリを生成するスクリプト。

本体リポジトリ(非公開)を別フォルダへcloneし、公開したくないファイルを
「履歴ごと」取り除いたコピーを作る。本体リポジトリには一切手を加えない。

必要なもの:
    pip install git-filter-repo

使い方（本体リポジトリのルートで実行）:
    python scripts/make_portfolio_repo.py

    生成と検査のみ行い、pushはしない（push先のリモート登録だけ行う）。
    pushは作業フォルダで手動で行うこと。
"""

import argparse
import fnmatch
import os
import shutil
import stat
import subprocess
import sys
import tempfile

# ===== 設定 =====
# 公開用にするブランチ
SOURCE_BRANCH = "main"

# 履歴ごと削除するパス（フォルダは末尾に / を付ける）
EXCLUDE_PATHS = [
    # 設定・認証情報
    "config.json",
    "origin_config.json",
    "client_secret.json",
    "oauth_token.json",
    # 個人用機能（ClaudeCode連携など）
    "private/",
    # 開発予定（過去のフォルダ配置も含む）
    # ※開発ログフォルダは要件定義・設計方針などを公開するため除外しない（作業ログはEXCLUDE_GLOBSで除外）
    "docs/",
    # 立ち絵などの画像素材
    "立ち絵/",
    "bb.png",
    "character.png",
    "character0000.png",
    # 過去に誤ってコミットされた仮想環境・キャッシュ・実験ファイル
    "python3.9_forDesktopCharacter/",
    "__pycache__/",
    "tests/",
    "search_results.csv",
    "memo.txt",
    # このスクリプト自身
    "scripts/",
]

# 履歴ごと削除するファイル名パターン（全フォルダが対象）
EXCLUDE_GLOBS = [
    "*ログ.md",          # 開発作業ログ（〜_ログ.md、〜_実装ログ.md など）
    "*ClaudeCode連携*",  # ClaudeCode連携の資料（開発予定→開発ログへ移動しても除外されるように）
    "*.log",
    "*.pyc",
    "CLAUDE.md"
]

# 履歴中の文字列を置換する（念のための保険。消し忘れたキーなどを潰す）
REPLACE_RULES = [
    r"regex:AIza[0-9A-Za-z_\-]{35}==>***REMOVED_API_KEY***",   # Google系APIキー
]

# コミット作成者のメールアドレスの置換（個人のメールアドレスをGitHubのnoreplyに置き換える）
# 書式: "公開する名前 <公開するメール> <元のメール>"
MAILMAP = [
    "tesu-dice <105336475+tesu-dice@users.noreply.github.com> <terariadaiki@gmail.com>",
]
# 検査用：公開用の履歴に含まれていてはいけないメールアドレス
FORBIDDEN_EMAILS = ["terariadaiki@gmail.com"]

# 作業フォルダ（本体リポジトリと同じ階層に作る）
WORK_DIR_NAME = "DesktopCharacter_portfolio_work"

# push先（作業フォルダに "publish" という名前で登録するだけで、pushはしない）
PUBLISH_REMOTE_URL = "https://github.com/tesu-dice/DesktopCharacter_forRelease.git"
PUBLISH_BRANCH = "main"
# ================


def run(cmd, cwd=None, check=True):
    print("  $ " + " ".join(cmd))
    result = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if check and result.returncode != 0:
        print(result.stdout)
        print(result.stderr, file=sys.stderr)
        sys.exit(f"コマンドが失敗しました: {' '.join(cmd)}")
    return result.stdout


def find_filter_repo():
    """git-filter-repo の実行方法を返す（pip版をpythonから直接起動する）"""
    try:
        import git_filter_repo
    except ImportError:
        sys.exit("git-filter-repo が見つかりません。 pip install git-filter-repo を実行してください。")
    return [sys.executable, git_filter_repo.__file__]


def remove_dir(path):
    """Windowsでは.git内が読み取り専用になっていることがあるので解除しながら削除する"""
    def onerror(func, p, _):
        os.chmod(p, stat.S_IWRITE)
        func(p)
    shutil.rmtree(path, onerror=onerror)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--work-dir", default=None, help="作業フォルダの場所（省略時は本体と同じ階層）")
    args = parser.parse_args()

    src = run(["git", "rev-parse", "--show-toplevel"]).strip()
    work = args.work_dir or os.path.join(os.path.dirname(src), WORK_DIR_NAME)
    filter_repo = find_filter_repo()

    # 1. 作業フォルダの準備
    print(f"[1/4] 作業フォルダ: {work}")
    if os.path.exists(work):
        ans = input("  作業フォルダが既に存在します。削除して作り直しますか？ [y/N]: ")
        if ans.lower() != "y":
            sys.exit("中止しました。")
        remove_dir(work)

    # 2. 本体をclone（filter-repoは新規cloneに対して実行する必要がある）
    print("[2/4] 本体リポジトリをclone")
    run(["git", "clone", "--no-local", "--single-branch", "--branch", SOURCE_BRANCH, src, work])

    # 3. 履歴から除外パスを削除、文字列を置換
    print("[3/4] 履歴から除外パスを削除")
    with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False, encoding="utf-8") as f:
        f.write("\n".join(REPLACE_RULES) + "\n")
        replace_file = f.name
    with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False, encoding="utf-8") as f:
        f.write("\n".join(MAILMAP) + "\n")
        mailmap_file = f.name
    try:
        cmd = filter_repo + ["--force", "--invert-paths", "--replace-text", replace_file, "--mailmap", mailmap_file]
        for p in EXCLUDE_PATHS:
            cmd += ["--path", p]
        for g in EXCLUDE_GLOBS:
            cmd += ["--path-glob", g]
        run(cmd, cwd=work)
    finally:
        os.remove(replace_file)
        os.remove(mailmap_file)

    # 4. 検査：除外パスやキーが履歴に残っていないか
    print("[4/4] 検査")
    ok = True
    for p in EXCLUDE_PATHS:
        if run(["git", "log", "--all", "--oneline", "--", p], cwd=work).strip():
            print(f"  NG: {p} が履歴に残っています")
            ok = False
    all_files = run(["git", "-c", "core.quotepath=false", "log", "--all", "--name-only", "--format="], cwd=work).splitlines()
    for g in EXCLUDE_GLOBS:
        hits = sorted({f for f in all_files if fnmatch.fnmatch(f, g)})
        if hits:
            print(f"  NG: {g} に一致するファイルが履歴に残っています: {hits[:3]}")
            ok = False
    if run(["git", "log", "--all", "--oneline", "-G", r"AIza[0-9A-Za-z_-]{35}"], cwd=work).strip():
        print("  NG: APIキーらしき文字列が履歴に残っています")
        ok = False
    emails = run(["git", "log", "--all", "--format=%ae%n%ce"], cwd=work)
    for e in FORBIDDEN_EMAILS:
        if e in emails:
            print(f"  NG: コミット情報に {e} が残っています")
            ok = False
    if not ok:
        sys.exit("検査NGです。作業フォルダの内容を公開しないでください。")
    print("  OK: 除外パス・APIキー・メールアドレスは履歴に含まれていません")

    # push先を登録だけしておく（pushは手動で行う）
    run(["git", "remote", "add", "publish", PUBLISH_REMOTE_URL], cwd=work)

    count = run(["git", "rev-list", "--count", "HEAD"], cwd=work).strip()
    print(f"\n生成完了: {work}（{count}コミット）")
    print("内容を確認後、作業フォルダで以下を実行するとpushできます（push先の履歴は上書きされます）:")
    print(f"    git push --force publish HEAD:{PUBLISH_BRANCH}")


if __name__ == "__main__":
    main()

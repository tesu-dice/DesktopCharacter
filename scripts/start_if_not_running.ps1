# DesktopCharacter をまだ起動していなければ起動するランチャー。
# タスクスケジューラ(「朝のアプリ起動」「朝の目覚まし音声再生」の両方)から呼ばれる想定。
#   - スリープ復帰直後はネットワーク・オーディオデバイスが未準備のことがあるため、少し待ってから起動する
#   - すでに main.py が動いている場合(スリープ前から起動しっぱなし等)は二重起動しない
#   - 2つのタスクから同時に呼ばれても二重起動しないよう、名前付きMutexで排他する
#   - -Detach を付けると自身をバックグラウンドで起動し直してすぐ終了する
#     (タスクの操作は順番に実行され前の操作の終了を待つため、VLCなど後続の操作を待たせないための指定)
#   - 実行結果はプロジェクト直下の launcher.log に追記する
param(
    [int]$DelaySec = 10,
    [switch]$Detach
)

$ProjectDir = Split-Path -Parent $PSScriptRoot
$Pythonw    = Join-Path $ProjectDir ".venv\Scripts\pythonw.exe"
$MainPy     = Join-Path $ProjectDir "main.py"
$LogFile    = Join-Path $ProjectDir "launcher.log"

function Write-Log([string]$msg) {
    $line = "{0} [pid {1}] {2}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $PID, $msg
    Add-Content -Path $LogFile -Value $line -Encoding UTF8
}

if ($Detach) {
    Start-Process -FilePath "powershell.exe" -WindowStyle Hidden -ArgumentList `
        "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$PSCommandPath`" -DelaySec $DelaySec"
    Write-Log "Detach: バックグラウンドで起動し直しました"
    exit 0
}

Write-Log "開始 (DelaySec=$DelaySec)"

$mutex = New-Object System.Threading.Mutex($false, "Local\DesktopCharacter_Launcher")
if (-not $mutex.WaitOne(0)) {
    Write-Log "別のランチャーが実行中のため終了します"
    exit 0
}

try {
    Start-Sleep -Seconds $DelaySec

    # タイマー復帰時はディスプレイが消えたままなので、疑似的なマウス入力で画面を点灯させる
    Add-Type -Namespace Win32 -Name Input -MemberDefinition @'
[DllImport("user32.dll")] public static extern void mouse_event(uint f, int dx, int dy, uint d, System.UIntPtr e);
[DllImport("kernel32.dll")] public static extern uint SetThreadExecutionState(uint f);
'@
    [Win32.Input]::SetThreadExecutionState(0x00000003) | Out-Null   # ES_SYSTEM_REQUIRED | ES_DISPLAY_REQUIRED
    [Win32.Input]::mouse_event(0x0001, 1, 0, 0, [UIntPtr]::Zero)     # MOUSEEVENTF_MOVE
    [Win32.Input]::mouse_event(0x0001, -1, 0, 0, [UIntPtr]::Zero)
    Start-Sleep -Seconds 5   # モニターとHDMI/DPの音声出力が復帰するのを待つ

    # python.exe / pythonw.exe のうち、コマンドラインに main.py を含むものを起動済みとみなす
    $running = Get-CimInstance Win32_Process -Filter "Name='pythonw.exe' OR Name='python.exe'" |
        Where-Object { $_.CommandLine -like "*main.py*" }

    if ($running) {
        Write-Log "起動済みのためスキップ (pid $($running.ProcessId -join ','))"
        exit 0
    }

    $p = Start-Process -FilePath $Pythonw -ArgumentList "`"$MainPy`"" -WorkingDirectory $ProjectDir -PassThru
    Write-Log "アプリを起動しました (pid $($p.Id))"
    Start-Sleep -Seconds 10   # 直後に別タスクのランチャーが来てもプロセス一覧に載るまでMutexを保持する
}
catch {
    Write-Log "エラー: $_"
}
finally {
    $mutex.ReleaseMutex()
}

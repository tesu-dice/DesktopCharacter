# DesktopCharacter をまだ起動していなければ起動するランチャー。
# タスクスケジューラ(register_wake_task.ps1 で登録)から呼ばれる想定。
#   - スリープ復帰直後はネットワーク・オーディオデバイスが未準備のことがあるため、少し待ってから起動する
#   - すでに main.py が動いている場合(スリープ前から起動しっぱなし等)は二重起動しない
param(
    [int]$DelaySec = 30
)

$ProjectDir = Split-Path -Parent $PSScriptRoot
$Pythonw    = Join-Path $ProjectDir ".venv\Scripts\pythonw.exe"
$MainPy     = Join-Path $ProjectDir "main.py"

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
    exit 0
}

Start-Process -FilePath $Pythonw -ArgumentList "`"$MainPy`"" -WorkingDirectory $ProjectDir

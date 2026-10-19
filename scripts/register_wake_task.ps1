# 指定時刻にPCをスリープ解除して DesktopCharacter を起動するタスクを登録する。
#
# 使い方(管理者権限は不要):
#   powershell -ExecutionPolicy Bypass -File scripts\register_wake_task.ps1 -Time 07:00
#   powershell -ExecutionPolicy Bypass -File scripts\register_wake_task.ps1 -Unregister
#
# ポイント:
#   - LogonType Interactive =「ユーザーがログオンしているときのみ実行する」。
#     「ログオンしているかどうかにかかわらず実行」にすると非対話セッションで起動し、
#     SAPI が SPERR_NOT_ACTIVE_SESSION を返す・ウィンドウが見えない、という問題が起きる。
#   - WakeToRun =「タスクを実行するためにスリープを解除する」。
#     電源オプションの「スリープ解除タイマーの許可」が有効である必要がある。
param(
    [string]$Time,                                   # 起動時刻 (例: "07:00")
    [string]$TaskName = "DesktopCharacter_WakeStart",
    [int]$DelaySec = 30,                             # 復帰後、起動までの待ち時間(秒)
    [switch]$Unregister
)

if ($Unregister) {
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
    Write-Host "タスク '$TaskName' を削除しました。"
    exit 0
}

if (-not $Time) {
    Write-Error "-Time を指定してください (例: -Time 07:00)"
    exit 1
}

$Launcher = Join-Path $PSScriptRoot "start_if_not_running.ps1"

$action = New-ScheduledTaskAction -Execute "powershell.exe" `
    -Argument "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$Launcher`" -DelaySec $DelaySec"

$trigger = New-ScheduledTaskTrigger -Daily -At $Time

$principal = New-ScheduledTaskPrincipal -UserId "$env:USERDOMAIN\$env:USERNAME" `
    -LogonType Interactive -RunLevel Limited

$settings = New-ScheduledTaskSettingsSet `
    -WakeToRun `
    -StartWhenAvailable `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -MultipleInstances IgnoreNew

Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger `
    -Principal $principal -Settings $settings -Force | Out-Null

Write-Host "タスク '$TaskName' を登録しました。毎日 $Time にスリープ解除して起動します。"

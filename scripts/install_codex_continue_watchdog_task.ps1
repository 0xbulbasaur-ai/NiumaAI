$ErrorActionPreference = "Stop"

$taskName = "NiumaAI"
$watchdogScript = Join-Path (Join-Path $env:USERPROFILE ".codex") "scripts\codex_continue_watchdog.ps1"

if (-not (Test-Path -LiteralPath $watchdogScript)) {
    throw "Watchdog control script was not found at $watchdogScript"
}

$userId = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
$action = New-ScheduledTaskAction -Execute "powershell.exe" -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$watchdogScript`" start"
$trigger = New-ScheduledTaskTrigger -AtLogOn
$principal = New-ScheduledTaskPrincipal -UserId $userId -LogonType Interactive -RunLevel Limited
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -MultipleInstances IgnoreNew

try {
  Register-ScheduledTask `
    -TaskName $taskName `
    -Action $action `
    -Trigger $trigger `
    -Principal $principal `
    -Settings $settings `
    -Description "Launch the NiumaAI Codex continue watchdog at logon." `
    -Force | Out-Null

  Write-Output "Installed scheduled task: $taskName"
}
catch {
  Write-Output "Could not install scheduled task: $($_.Exception.Message)"
}

$ErrorActionPreference = "Stop"

$CodexHome = Join-Path $env:USERPROFILE ".codex"
$ServiceScript = Join-Path $CodexHome "scripts\codex_continue_watchdog_service.py"
$StateDir = Join-Path $CodexHome "tmp\codex-continue-watchdog"
$ControlDir = Join-Path $StateDir "control"
$StatePath = Join-Path $StateDir "state.json"
$LockPath = Join-Path $StateDir "watchdog.lock"

function Ensure-WatchdogPaths {
    New-Item -ItemType Directory -Path $StateDir -Force | Out-Null
    New-Item -ItemType Directory -Path $ControlDir -Force | Out-Null
}

function Get-LockData {
    if (-not (Test-Path -LiteralPath $LockPath)) {
        return $null
    }
    try {
        return Get-Content -LiteralPath $LockPath -Raw | ConvertFrom-Json
    }
    catch {
        return $null
    }
}

function Get-StateData {
    if (-not (Test-Path -LiteralPath $StatePath)) {
        return $null
    }
    try {
        return Get-Content -LiteralPath $StatePath -Raw | ConvertFrom-Json
    }
    catch {
        return $null
    }
}

function Test-ProcessRunning {
    param(
        [int]$ProcessId
    )
    if ($ProcessId -le 0) {
        return $false
    }
    return ($null -ne (Get-Process -Id $ProcessId -ErrorAction SilentlyContinue))
}

function Get-WatchdogStatus {
    $state = Get-StateData
    $lock = Get-LockData
    $running = $false
    $watchdogPid = $null
    if ($state -and $state.pid) {
        $watchdogPid = [int]$state.pid
        $running = Test-ProcessRunning -ProcessId $watchdogPid
    }
    elseif ($lock -and $lock.pid) {
        $watchdogPid = [int]$lock.pid
        $running = Test-ProcessRunning -ProcessId $watchdogPid
    }

    if (-not $state) {
        return [ordered]@{
            running = $running
            pid = $watchdogPid
            status = $(if ($running) { "starting" } else { "stopped" })
            state_path = $StatePath
            lock_path = $LockPath
        }
    }

    $ordered = [ordered]@{}
    foreach ($property in $state.PSObject.Properties) {
        $ordered[$property.Name] = $property.Value
    }
    $ordered["running"] = $running
    $ordered["state_path"] = $StatePath
    $ordered["lock_path"] = $LockPath
    return $ordered
}

function Write-ControlCommand {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Command
    )

    Ensure-WatchdogPaths
    $commandId = [guid]::NewGuid().ToString()
    $path = Join-Path $ControlDir "$commandId.json"
    $payload = [ordered]@{
        id = $commandId
        command = $Command
        created_at = (Get-Date).ToString("o")
    }
    $json = $payload | ConvertTo-Json -Depth 5
    $utf8NoBom = New-Object System.Text.UTF8Encoding($false)
    [System.IO.File]::WriteAllText($path, $json, $utf8NoBom)
    return $commandId
}

function Start-Watchdog {
    Ensure-WatchdogPaths
    $status = Get-WatchdogStatus
    if ($status.running) {
        return $status
    }

    $pythonw = (Get-Command pythonw.exe -ErrorAction SilentlyContinue).Source
    if (-not $pythonw) {
        throw "pythonw.exe was not found on PATH."
    }
    if (-not (Test-Path -LiteralPath $ServiceScript)) {
        throw "Watchdog service script was not found at $ServiceScript"
    }

    Start-Process -FilePath $pythonw -ArgumentList @($ServiceScript, "--service") -WindowStyle Hidden

    $deadline = (Get-Date).AddSeconds(20)
    do {
        Start-Sleep -Milliseconds 500
        $status = Get-WatchdogStatus
        if ($status.running -or $status.status -eq "running" -or $status.status -eq "cli_unavailable" -or $status.status -eq "paused") {
            return $status
        }
    } while ((Get-Date) -lt $deadline)

    return Get-WatchdogStatus
}

function Wait-ForStatus {
    param(
        [Parameter(Mandatory = $true)]
        [ScriptBlock]$Condition,
        [int]$TimeoutSeconds = 15
    )

    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    do {
        $status = Get-WatchdogStatus
        if (& $Condition $status) {
            return $status
        }
        Start-Sleep -Milliseconds 500
    } while ((Get-Date) -lt $deadline)
    return Get-WatchdogStatus
}

function Invoke-WatchdogCommand {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Command
    )

    $status = Get-WatchdogStatus
    if (-not $status.running -and $Command -notin @("status", "start")) {
        return $status
    }

    switch ($Command) {
        "pause" {
            [void](Write-ControlCommand -Command "pause")
            return Wait-ForStatus -Condition { param($s) $s.status -eq "paused" }
        }
        "resume" {
            [void](Write-ControlCommand -Command "resume")
            return Wait-ForStatus -Condition { param($s) $s.status -ne "paused" }
        }
        "stop" {
            [void](Write-ControlCommand -Command "stop")
            return Wait-ForStatus -Condition { param($s) -not $s.running -or $s.status -eq "stopped" }
        }
        "status" {
            return Get-WatchdogStatus
        }
        default {
            throw "Unsupported command: $Command"
        }
    }
}

$command = if ($args.Count -gt 0) { [string]$args[0] } else { "status" }

$result = switch ($command.ToLowerInvariant()) {
    "start" { Start-Watchdog }
    "pause" { Invoke-WatchdogCommand -Command "pause" }
    "resume" { Invoke-WatchdogCommand -Command "resume" }
    "status" { Invoke-WatchdogCommand -Command "status" }
    "stop" { Invoke-WatchdogCommand -Command "stop" }
    default { throw "Usage: codex_continue_watchdog.ps1 start|pause|resume|status|stop" }
}

$result | ConvertTo-Json -Depth 8

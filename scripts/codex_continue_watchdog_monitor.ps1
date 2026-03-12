param(
    [string]$StatePath = $(Join-Path (Join-Path $env:USERPROFILE ".codex") "tmp\codex-continue-watchdog\state.json"),
    [string]$MonitorUrl = "",
    [int]$RefreshSeconds = 1,
    [int]$InitialDisplayLines = 48,
    [int]$MaxIterations = 0
)

$ErrorActionPreference = "SilentlyContinue"
$utf8NoBom = [System.Text.UTF8Encoding]::new($false)
try {
    chcp 65001 > $null
}
catch {
}
[Console]::InputEncoding = $utf8NoBom
[Console]::OutputEncoding = $utf8NoBom
[System.Console]::InputEncoding = $utf8NoBom
[System.Console]::OutputEncoding = $utf8NoBom
$OutputEncoding = $utf8NoBom
$Host.UI.RawUI.WindowTitle = "NiumaAI Session Monitor"

$script:LastThreadId = $null
$script:LastStatus = $null
$script:LastApiUrl = $null
$script:LastRevision = ""
$script:LastEntryKeys = @()
$script:StateUnavailable = $false
$script:ApiUnavailable = $false
$script:LastApiError = ""

function Get-JsonFile {
    param([string]$Path)
    if (-not (Test-Path -LiteralPath $Path)) {
        return $null
    }
    try {
        return Get-Content -LiteralPath $Path -Raw -Encoding UTF8 | ConvertFrom-Json
    }
    catch {
        $script:LastApiError = $_.Exception.Message
        return $null
    }
}

function Write-MonitorLine {
    param(
        [string]$Message,
        [System.ConsoleColor]$Color = [System.ConsoleColor]::Gray
    )
    $stamp = Get-Date -Format "HH:mm:ss"
    Write-Host "[$stamp] $Message" -ForegroundColor $Color
}

function Normalize-MonitorUrl {
    param([string]$Value)
    if (-not $Value) {
        return ""
    }
    $trimmed = $Value.Trim()
    if (-not $trimmed) {
        return ""
    }
    return $trimmed.TrimEnd("/")
}

function Get-SessionApiUrl {
    param([object]$State)
    if ($MonitorUrl) {
        return (Normalize-MonitorUrl -Value $MonitorUrl) + "/api/session"
    }
    if ($State -and $State.monitor_url) {
        return (Normalize-MonitorUrl -Value ([string]$State.monitor_url)) + "/api/session"
    }
    return ""
}

function Invoke-SessionApi {
    param([string]$ApiUrl)
    if (-not $ApiUrl) {
        return $null
    }
    try {
        $stamp = [DateTimeOffset]::UtcNow.ToUnixTimeMilliseconds()
        $raw = & curl.exe -s --fail --max-time 10 "$ApiUrl?t=$stamp" 2>$null
        if (-not $raw) {
            return $null
        }
        $payload = ($raw | Out-String) | ConvertFrom-Json
        $script:LastApiError = ""
        return $payload
    }
    catch {
        return $null
    }
}

function Get-EntryKey {
    param([object]$Entry)
    $at = if ($Entry.at) { [string]$Entry.at } else { "" }
    $kind = if ($Entry.kind) { [string]$Entry.kind } else { "" }
    $text = if ($Entry.text) { [string]$Entry.text } else { "" }
    return "$at`n$kind`n$text"
}

function Get-EntryColor {
    param([object]$Entry)
    switch ([string]$Entry.kind) {
        "task_started" { return [System.ConsoleColor]::Cyan }
        "task_complete" { return [System.ConsoleColor]::Green }
        "user" { return [System.ConsoleColor]::Yellow }
        "agent" { return [System.ConsoleColor]::White }
        "assistant" { return [System.ConsoleColor]::Gray }
        "developer" { return [System.ConsoleColor]::DarkGray }
        "tool_call" { return [System.ConsoleColor]::DarkCyan }
        "tool_output" {
            $text = [string]$Entry.text
            if ($text -match "(?i)(error:|failed|exit code)") {
                return [System.ConsoleColor]::Red
            }
            if ($text -match "(?i)\bok\b|\bdone\b") {
                return [System.ConsoleColor]::DarkGray
            }
            return [System.ConsoleColor]::DarkYellow
        }
        "reasoning" { return [System.ConsoleColor]::DarkGray }
        "usage" { return [System.ConsoleColor]::DarkGray }
        default { return [System.ConsoleColor]::Gray }
    }
}

function Reset-MonitorCursor {
    $script:LastRevision = ""
    $script:LastEntryKeys = @()
}

function Get-NewEntries {
    param(
        [object[]]$Entries,
        [int]$TailCount
    )
    $entriesList = @($Entries)
    if ($entriesList.Count -eq 0) {
        $script:LastEntryKeys = @()
        return @()
    }

    $keys = @($entriesList | ForEach-Object { Get-EntryKey -Entry $_ })
    $result = @()

    if (-not $script:LastRevision) {
        if ($entriesList.Count -gt $TailCount) {
            $result = @($entriesList | Select-Object -Last $TailCount)
        }
        else {
            $result = $entriesList
        }
    }
    else {
        $lastKey = if ($script:LastEntryKeys.Count -gt 0) { $script:LastEntryKeys[-1] } else { "" }
        $lastIndex = -1
        if ($lastKey) {
            for ($i = $keys.Count - 1; $i -ge 0; $i--) {
                if ($keys[$i] -eq $lastKey) {
                    $lastIndex = $i
                    break
                }
            }
        }

        if ($lastIndex -ge 0 -and $lastIndex -lt ($entriesList.Count - 1)) {
            $result = @($entriesList[($lastIndex + 1)..($entriesList.Count - 1)])
        }
        elseif ($lastIndex -lt 0) {
            Write-MonitorLine -Message "resynced monitor tail." -Color DarkYellow
            if ($entriesList.Count -gt $TailCount) {
                $result = @($entriesList | Select-Object -Last $TailCount)
            }
            else {
                $result = $entriesList
            }
        }
    }

    $script:LastEntryKeys = $keys
    return @($result)
}

Write-Host "NiumaAI Session Monitor (WT)" -ForegroundColor Green
Write-Host "API-backed mode. Ctrl+C to close." -ForegroundColor DarkGray
Write-Host ""

$iteration = 0
while ($true) {
    $iteration++
    $state = Get-JsonFile -Path $StatePath
    if ($null -eq $state -and -not $MonitorUrl) {
        if (-not $script:StateUnavailable) {
            Write-MonitorLine -Message "waiting for state.json..." -Color Yellow
            $script:StateUnavailable = $true
        }
        if ($MaxIterations -gt 0 -and $iteration -ge $MaxIterations) {
            break
        }
        Start-Sleep -Seconds $RefreshSeconds
        continue
    }

    if ($script:StateUnavailable) {
        Write-MonitorLine -Message "watchdog state loaded." -Color Green
        $script:StateUnavailable = $false
    }

    $apiUrl = Get-SessionApiUrl -State $state
    if (-not $apiUrl) {
        if (-not $script:ApiUnavailable) {
            Write-MonitorLine -Message "waiting for monitor API..." -Color Yellow
            $script:ApiUnavailable = $true
        }
        if ($MaxIterations -gt 0 -and $iteration -ge $MaxIterations) {
            break
        }
        Start-Sleep -Seconds $RefreshSeconds
        continue
    }

    if ($apiUrl -ne $script:LastApiUrl) {
        $script:LastApiUrl = $apiUrl
        Reset-MonitorCursor
        Write-MonitorLine -Message "monitor api: $apiUrl" -Color DarkCyan
    }

    $data = Invoke-SessionApi -ApiUrl $apiUrl
    if ($null -eq $data) {
        if (-not $script:ApiUnavailable) {
            Write-MonitorLine -Message "monitor API unavailable." -Color Yellow
            if ($script:LastApiError) {
                Write-MonitorLine -Message "api error: $($script:LastApiError)" -Color DarkYellow
            }
            $script:ApiUnavailable = $true
        }
        if ($MaxIterations -gt 0 -and $iteration -ge $MaxIterations) {
            break
        }
        Start-Sleep -Seconds $RefreshSeconds
        continue
    }

    if ($script:ApiUnavailable) {
        Write-MonitorLine -Message "monitor API connected." -Color Green
        $script:ApiUnavailable = $false
        $script:LastApiError = ""
    }

    if ($data.thread_id -ne $script:LastThreadId) {
        $script:LastThreadId = $data.thread_id
        Write-MonitorLine -Message "thread: $($data.thread_id)" -Color Magenta
    }

    if ($data.status -ne $script:LastStatus) {
        $script:LastStatus = $data.status
        Write-MonitorLine -Message "status: $($data.status)" -Color Cyan
    }

    if ($data.entries_revision -ne $script:LastRevision) {
        foreach ($entry in Get-NewEntries -Entries $data.entries -TailCount $InitialDisplayLines) {
            Write-Host ([string]$entry.text) -ForegroundColor (Get-EntryColor -Entry $entry)
        }
        $script:LastRevision = [string]$data.entries_revision
    }

    if ($MaxIterations -gt 0 -and $iteration -ge $MaxIterations) {
        break
    }
    Start-Sleep -Seconds $RefreshSeconds
}

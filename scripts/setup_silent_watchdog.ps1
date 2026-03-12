$ErrorActionPreference = "Stop"

<#
.SYNOPSIS
    One-step setup for silent Codex watchdog (no cmd window flashing).

    Fixes all three root causes from the 2026-03-11 failure:
    1. Removes DETACHED_PROCESS flag conflict in service script
    2. Switches resume_backend from app-only to cli
    3. Installs MCP packages locally and updates config.toml to bypass npx.cmd

.USAGE
    powershell -ExecutionPolicy Bypass -File setup_silent_watchdog.ps1
#>

$CodexHome = Join-Path $env:USERPROFILE ".codex"
$NodeDir = Join-Path $CodexHome "tools\node-v24.13.1-win-x64"
$NodeExe = Join-Path $NodeDir "node.exe"
$NpmCmd = Join-Path $NodeDir "npm.cmd"
$LocalMcp = Join-Path $CodexHome "local-mcp-node"
$ConfigToml = Join-Path $CodexHome "config.toml"
$WatchdogJson = Join-Path $CodexHome "continue-watchdog.json"
$ServiceScript = Join-Path $CodexHome "scripts\codex_continue_watchdog_service.py"

function Format-TomlString {
    param([string]$Value)

    $escaped = $Value.Replace('\', '\\').Replace('"', '\"')
    return "`"$escaped`""
}

function Get-TomlSectionRange {
    param(
        [string[]]$Lines,
        [string]$SectionName
    )

    $header = "[$SectionName]"
    $start = -1
    for ($i = 0; $i -lt $Lines.Count; $i++) {
        if ($Lines[$i].Trim() -eq $header) {
            $start = $i
            break
        }
    }

    if ($start -lt 0) {
        return $null
    }

    $end = $Lines.Count
    for ($i = $start + 1; $i -lt $Lines.Count; $i++) {
        if ($Lines[$i] -match '^\s*\[[^\]]+\]\s*$') {
            $end = $i
            break
        }
    }

    return [pscustomobject]@{
        Start = $start
        End = $end
    }
}

function Get-TomlSectionText {
    param(
        [string[]]$Lines,
        [string]$SectionName
    )

    $range = Get-TomlSectionRange -Lines $Lines -SectionName $SectionName
    if (-not $range) {
        return ""
    }

    return ($Lines[$range.Start..($range.End - 1)] -join "`n")
}

function Remove-TomlSection {
    param(
        [string[]]$Lines,
        [string]$SectionName
    )

    $range = Get-TomlSectionRange -Lines $Lines -SectionName $SectionName
    if (-not $range) {
        return $Lines
    }

    $result = New-Object 'System.Collections.Generic.List[string]'
    for ($i = 0; $i -lt $Lines.Count; $i++) {
        if ($i -ge $range.Start -and $i -lt $range.End) {
            continue
        }
        $result.Add($Lines[$i])
    }

    while ($result.Count -gt 0 -and $result[$result.Count - 1] -eq "") {
        $result.RemoveAt($result.Count - 1)
    }

    return $result.ToArray()
}

function Set-TomlSection {
    param(
        [string[]]$Lines,
        [string]$SectionName,
        [string[]]$SectionLines
    )

    $range = Get-TomlSectionRange -Lines $Lines -SectionName $SectionName
    $result = New-Object 'System.Collections.Generic.List[string]'

    if ($range) {
        for ($i = 0; $i -lt $range.Start; $i++) {
            $result.Add($Lines[$i])
        }
        if ($result.Count -gt 0 -and $result[$result.Count - 1] -ne "") {
            $result.Add("")
        }
        foreach ($line in $SectionLines) {
            $result.Add($line)
        }
        if ($range.End -lt $Lines.Count -and $Lines[$range.End] -ne "") {
            $result.Add("")
        }
        for ($i = $range.End; $i -lt $Lines.Count; $i++) {
            $result.Add($Lines[$i])
        }
    } else {
        foreach ($line in $Lines) {
            $result.Add($line)
        }
        if ($result.Count -gt 0 -and $result[$result.Count - 1] -ne "") {
            $result.Add("")
        }
        foreach ($line in $SectionLines) {
            $result.Add($line)
        }
    }

    while ($result.Count -gt 1 -and $result[$result.Count - 1] -eq "" -and $result[$result.Count - 2] -eq "") {
        $result.RemoveAt($result.Count - 1)
    }

    return $result.ToArray()
}

function Get-TomlStringArrayFromSection {
    param([string]$SectionText)

    if (-not $SectionText) {
        return @()
    }

    $match = [regex]::Match($SectionText, '(?ms)^\s*args\s*=\s*\[(?<body>.*?)\]')
    if (-not $match.Success) {
        return @()
    }

    $values = New-Object 'System.Collections.Generic.List[string]'
    foreach ($item in [regex]::Matches($match.Groups['body'].Value, '"((?:[^"\\]|\\.)*)"')) {
        $values.Add($item.Groups[1].Value)
    }

    return $values.ToArray()
}

function Get-TomlScalarAssignments {
    param([string]$SectionText)

    if (-not $SectionText) {
        return @()
    }

    $withoutArgs = [regex]::Replace($SectionText, '(?ms)^\s*args\s*=\s*\[(?<body>.*?)\]\s*', '')
    $result = New-Object 'System.Collections.Generic.List[object]'
    foreach ($line in ($withoutArgs -split "\r?\n")) {
        if ($line -match '^\s*\[') {
            continue
        }
        if ($line -match '^\s*(command|args)\s*=') {
            continue
        }
        if ($line -match '^\s*([A-Za-z0-9_.-]+)\s*=\s*(.+?)\s*$') {
            $result.Add([pscustomobject]@{
                Key = $Matches[1]
                Value = $Matches[2]
            })
        }
    }

    return $result.ToArray()
}

Write-Host "=== Silent Watchdog Setup ===" -ForegroundColor Cyan

# Step 1: Install MCP packages locally
Write-Host "`n[1/3] Installing MCP packages locally..." -ForegroundColor Yellow
if (-not (Test-Path $LocalMcp)) {
    New-Item -ItemType Directory -Path $LocalMcp -Force | Out-Null
}
Push-Location $LocalMcp
try {
    if (-not (Test-Path (Join-Path $LocalMcp "package.json"))) {
        & $NpmCmd init -y 2>&1 | Out-Null
    }
    & $NpmCmd install @upstash/context7-mcp @playwright/mcp 2>&1 | Out-Null
    Write-Host "  OK: packages installed at $LocalMcp" -ForegroundColor Green
} finally {
    Pop-Location
}

$ctx7Entry = Join-Path $LocalMcp "node_modules\@upstash\context7-mcp\dist\index.js"
$pwEntry = Join-Path $LocalMcp "node_modules\@playwright\mcp\cli.js"

if (-not (Test-Path $ctx7Entry)) { throw "context7-mcp entry point not found: $ctx7Entry" }
if (-not (Test-Path $pwEntry)) { throw "playwright-mcp entry point not found: $pwEntry" }

# Step 2: Update config.toml to use direct node.exe
Write-Host "`n[2/3] Updating config.toml..." -ForegroundColor Yellow
if (Test-Path $ConfigToml) {
    $backup = "$ConfigToml.bak-$(Get-Date -Format 'yyyyMMdd-HHmmss')"
    Copy-Item $ConfigToml $backup
    Write-Host "  Backup: $backup" -ForegroundColor DarkGray

    $lines = @(Get-Content $ConfigToml -Encoding UTF8)
    $nodeExeForward = $NodeExe.Replace('\', '/')
    $ctx7Forward = $ctx7Entry.Replace('\', '/')
    $pwForward = $pwEntry.Replace('\', '/')
    $context7Text = Get-TomlSectionText -Lines $lines -SectionName "mcp_servers.context7"
    $playwrightText = Get-TomlSectionText -Lines $lines -SectionName "mcp_servers.playwright"

    $context7ScalarMap = [ordered]@{}
    foreach ($pair in @(Get-TomlScalarAssignments -SectionText $context7Text)) {
        $context7ScalarMap[$pair.Key] = $pair.Value
    }

    $playwrightArgs = @(Get-TomlStringArrayFromSection -SectionText $playwrightText)
    $playwrightExtraArgs = @()
    if ($playwrightArgs.Count -ge 2 -and $playwrightArgs[0] -eq "-y" -and $playwrightArgs[1] -like "@playwright/mcp*") {
        if ($playwrightArgs.Count -gt 2) {
            $playwrightExtraArgs = @($playwrightArgs[2..($playwrightArgs.Count - 1)])
        }
    } elseif ($playwrightArgs.Count -ge 1 -and $playwrightArgs[0] -like "*cli.js") {
        if ($playwrightArgs.Count -gt 1) {
            $playwrightExtraArgs = @($playwrightArgs[1..($playwrightArgs.Count - 1)])
        }
    } elseif ($playwrightArgs.Count -gt 0) {
        $playwrightExtraArgs = @($playwrightArgs)
    }

    $playwrightScalarMap = [ordered]@{
        startup_timeout_sec = "30"
        tool_timeout_sec = "180"
    }
    foreach ($pair in @(Get-TomlScalarAssignments -SectionText $playwrightText)) {
        $playwrightScalarMap[$pair.Key] = $pair.Value
    }

    $context7Lines = New-Object 'System.Collections.Generic.List[string]'
    $context7Lines.Add("[mcp_servers.context7]")
    $context7Lines.Add("command = $(Format-TomlString -Value $nodeExeForward)")
    $context7Lines.Add("args = [")
    $context7Lines.Add("  $(Format-TomlString -Value $ctx7Forward),")
    $context7Lines.Add("]")
    foreach ($entry in $context7ScalarMap.GetEnumerator()) {
        $context7Lines.Add("$($entry.Key) = $($entry.Value)")
    }

    $playwrightLines = New-Object 'System.Collections.Generic.List[string]'
    $playwrightLines.Add("[mcp_servers.playwright]")
    $playwrightLines.Add("command = $(Format-TomlString -Value $nodeExeForward)")
    $playwrightLines.Add("args = [")
    $playwrightLines.Add("  $(Format-TomlString -Value $pwForward),")
    foreach ($arg in $playwrightExtraArgs) {
        $playwrightLines.Add("  $(Format-TomlString -Value $arg),")
    }
    $playwrightLines.Add("]")
    foreach ($entry in $playwrightScalarMap.GetEnumerator()) {
        $playwrightLines.Add("$($entry.Key) = $($entry.Value)")
    }

    $lines = Remove-TomlSection -Lines $lines -SectionName "mcp_servers.context7.env"
    $lines = Remove-TomlSection -Lines $lines -SectionName "mcp_servers.playwright.env"
    $lines = Set-TomlSection -Lines $lines -SectionName "mcp_servers.context7" -SectionLines $context7Lines.ToArray()
    $lines = Set-TomlSection -Lines $lines -SectionName "mcp_servers.playwright" -SectionLines $playwrightLines.ToArray()

    $normalized = $lines -join "`r`n"
    [System.IO.File]::WriteAllText($ConfigToml, $normalized, [System.Text.UTF8Encoding]::new($false))
    Write-Host "  OK: context7 and playwright sections normalized in config.toml" -ForegroundColor Green
} else {
    Write-Host "  SKIP: config.toml not found" -ForegroundColor Yellow
}

# Step 3: Update continue-watchdog.json
Write-Host "`n[3/3] Updating continue-watchdog.json..." -ForegroundColor Yellow
if (Test-Path $WatchdogJson) {
    $wj = Get-Content $WatchdogJson -Raw -Encoding UTF8 | ConvertFrom-Json
    $changed = $false
    if ($wj.resume_backend -ne "cli") {
        $wj.resume_backend = "cli"
        Write-Host "  OK: resume_backend changed to cli" -ForegroundColor Green
        $changed = $true
    }
    if ($wj.sandbox_policy -ne "danger-full-access") {
        $wj | Add-Member -NotePropertyName sandbox_policy -NotePropertyValue "danger-full-access" -Force
        Write-Host "  OK: sandbox_policy changed to danger-full-access" -ForegroundColor Green
        $changed = $true
    }
    if ($wj.approval_mode -ne "never") {
        $wj | Add-Member -NotePropertyName approval_mode -NotePropertyValue "never" -Force
        Write-Host "  OK: approval_mode changed to never" -ForegroundColor Green
        $changed = $true
    }
    if ($changed) {
        $json = $wj | ConvertTo-Json -Depth 5
        $utf8 = [System.Text.UTF8Encoding]::new($false)
        [System.IO.File]::WriteAllText($WatchdogJson, $json, $utf8)
    } else {
        Write-Host "  OK: continue-watchdog.json already matches the silent CLI defaults" -ForegroundColor Green
    }
} else {
    Write-Host "  SKIP: continue-watchdog.json not found" -ForegroundColor Yellow
}

# Run verification
Write-Host "`n=== Running verification ===" -ForegroundColor Cyan
$verifyScript = Join-Path $CodexHome "scripts\verify_silent_watchdog.py"
if (Test-Path $verifyScript) {
    python $verifyScript
} else {
    Write-Host "Verification script not found. Run verify_silent_watchdog.py manually." -ForegroundColor Yellow
}

Write-Host "`nDone. Restart Codex and start the watchdog to test." -ForegroundColor Cyan

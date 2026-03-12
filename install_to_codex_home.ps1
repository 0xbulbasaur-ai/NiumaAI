$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$codexHome = Join-Path $env:USERPROFILE ".codex"
$skillsDir = Join-Path $codexHome "skills\codex-continue-watchdog"
$scriptsDir = Join-Path $codexHome "scripts"

New-Item -ItemType Directory -Path $skillsDir -Force | Out-Null
New-Item -ItemType Directory -Path (Join-Path $skillsDir "agents") -Force | Out-Null
New-Item -ItemType Directory -Path $scriptsDir -Force | Out-Null

Copy-Item (Join-Path $repoRoot "skill\SKILL.md") (Join-Path $skillsDir "SKILL.md") -Force
Copy-Item (Join-Path $repoRoot "skill\agents\openai.yaml") (Join-Path $skillsDir "agents\openai.yaml") -Force

Get-ChildItem (Join-Path $repoRoot "scripts") -File | ForEach-Object {
    Copy-Item $_.FullName (Join-Path $scriptsDir $_.Name) -Force
}

Write-Host "Installed skill files to $skillsDir"
Write-Host "Installed scripts to $scriptsDir"
Write-Host ""
Write-Host "Next:"
Write-Host "1. pip install -r requirements.txt"
Write-Host "2. Copy examples\\continue-watchdog.example.json to $env:USERPROFILE\\.codex\\continue-watchdog.json"
Write-Host "3. Run the setup and verify scripts"

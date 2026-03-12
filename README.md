# NiumaAI Codex Watchdog

Silent auto-continue watchdog for Codex on Windows. It resumes the first pinned thread through hidden `codex.exe` CLI calls and avoids visible `cmd.exe` flashes.

## What This Repo Contains

- `skill/`: the Codex skill definition and agent metadata
- `scripts/`: PowerShell and Python scripts used by the watchdog
- `examples/`: sample config you can adapt locally

## Why This Exists

The local Codex app can stop on long-running threads. This watchdog keeps a pinned thread moving without opening visible console windows, and it includes verification and repair scripts for the common Windows failure modes.

## Features

- Hidden CLI resume via native `codex.exe`
- Pause, resume, status, and stop controls
- Local monitor scripts for the active thread
- Verification script for the silent-mode prerequisites
- Repair script for common MCP and config issues
- Scheduled-task installer for auto-start at logon

## Privacy And Portability

This public copy removes hardcoded user-specific absolute paths. Runtime paths now resolve from `%USERPROFILE%` or `Path.home()`.

Machine-specific items are intentionally not included:

- your live `.codex` state database
- logs and attempt history
- pinned thread IDs
- local account details

## Prerequisites

- Windows
- Python 3.12+
- Codex installed locally
- Node runtime under `%USERPROFILE%\.codex\tools\node-v24.13.1-win-x64`
- A working Codex login

Python packages:

```powershell
pip install -r requirements.txt
```

## Install Into Codex Home

From the repository root:

```powershell
powershell -ExecutionPolicy Bypass -File .\install_to_codex_home.ps1
```

This copies the skill into `%USERPROFILE%\.codex\skills\codex-continue-watchdog` and the scripts into `%USERPROFILE%\.codex\scripts`.

## Configure

Copy the example config and adapt it if needed:

```powershell
Copy-Item .\examples\continue-watchdog.example.json "$env:USERPROFILE\.codex\continue-watchdog.json"
```

If your normal workspace is not `%USERPROFILE%\Desktop\Projects`, set:

```powershell
$env:NIUMAAI_DEFAULT_CWD = "D:\path\to\workspace"
```

## Usage

```powershell
powershell -File "$env:USERPROFILE\.codex\scripts\codex_continue_watchdog.ps1" start
powershell -File "$env:USERPROFILE\.codex\scripts\codex_continue_watchdog.ps1" status
powershell -File "$env:USERPROFILE\.codex\scripts\codex_continue_watchdog.ps1" pause
powershell -File "$env:USERPROFILE\.codex\scripts\codex_continue_watchdog.ps1" resume
powershell -File "$env:USERPROFILE\.codex\scripts\codex_continue_watchdog.ps1" stop
```

Verification:

```powershell
python "$env:USERPROFILE\.codex\scripts\verify_silent_watchdog.py"
```

Repair:

```powershell
powershell -ExecutionPolicy Bypass -File "$env:USERPROFILE\.codex\scripts\setup_silent_watchdog.ps1"
```

## Known Constraints

- Windows-specific
- Assumes Codex CLI is installed in the standard npm-backed location
- Assumes the user pins the target thread in Codex
- MCP setup logic is opinionated and tailored to local direct-`node.exe` execution

## Repository Topics

Suggested GitHub topics:

`codex`, `openai`, `windows`, `watchdog`, `automation`, `powershell`, `python`, `desktop-automation`

## License

MIT

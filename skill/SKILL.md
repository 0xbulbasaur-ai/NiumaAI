---
name: codex-continue-watchdog
description: Use this skill when the user wants to start, pause, resume, inspect, stop, verify, or repair the local NiumaAI Codex auto-continue watchdog. The watchdog uses hidden CLI resume (codex.exe) to continue the first pinned thread without any visible cmd windows.
---

# NiumaAI Watchdog

Use this skill for any request about the local Codex auto-continue watchdog.

## Commands

Run the global control script instead of recreating the workflow:

```powershell
powershell -File "$env:USERPROFILE\.codex\scripts\codex_continue_watchdog.ps1" start
powershell -File "$env:USERPROFILE\.codex\scripts\codex_continue_watchdog.ps1" pause
powershell -File "$env:USERPROFILE\.codex\scripts\codex_continue_watchdog.ps1" resume
powershell -File "$env:USERPROFILE\.codex\scripts\codex_continue_watchdog.ps1" status
powershell -File "$env:USERPROFILE\.codex\scripts\codex_continue_watchdog.ps1" stop
```

## Verify & Repair

Run the verification script to check all 9 preconditions:

```bash
python %USERPROFILE%\.codex\scripts\verify_silent_watchdog.py
```

If any checks fail, run the one-step repair:

```powershell
powershell -ExecutionPolicy Bypass -File "$env:USERPROFILE\.codex\scripts\setup_silent_watchdog.ps1"
```

## Architecture (Silent Mode)

The watchdog uses **hidden CLI resume** — NOT app-only, NOT deep links. This is the only path verified to work on this machine without flashing cmd windows.

### Resume chain (zero visible windows)

```
pythonw.exe (watchdog service, no console)
  └─ codex.exe exec resume <thread_id> continue  (CREATE_NO_WINDOW flag)
```

### MCP startup chain (zero visible windows)

```
node.exe  (direct binary, NOT npx.cmd)
  └─ @upstash/context7-mcp/dist/index.js
  └─ @playwright/mcp/cli.js
```

### Why NOT these alternatives

| Path | Problem on this machine |
|---|---|
| `resume_backend: app-only` | Relies on `codex://` deep link which is NOT registered |
| `codex.cmd` / `npx.cmd` | Spawns `cmd.exe` → visible window flash |
| `CREATE_NO_WINDOW \| DETACHED_PROCESS` | Flag conflict causes unpredictable flashing |

## Configuration

### `~/.codex/continue-watchdog.json`

```json
{
  "thread_scope": "pinned:first",
  "poll_seconds": 2,
  "idle_stop_seconds": 180,
  "max_resume_attempts": 5,
  "resume_window_minutes": 15,
  "cooldown_minutes": 30,
  "window_title": "Codex",
  "toast_notifications": true,
  "tray_enabled": true,
  "resume_backend": "cli",
  "stop_detection_mode": "task_complete_only"
}
```

**Critical**: `resume_backend` MUST be `"cli"`, never `"app-only"`.

### `~/.codex/config.toml` (MCP sections)

The `context7` and `playwright` MCP servers MUST use direct `node.exe` pointing to locally installed JS entry files:

```toml
[mcp_servers.context7]
command = "<USERPROFILE>/.codex/tools/node-v24.13.1-win-x64/node.exe"
args = ["<USERPROFILE>/.codex/local-mcp-node/node_modules/@upstash/context7-mcp/dist/index.js"]

[mcp_servers.playwright]
command = "<USERPROFILE>/.codex/tools/node-v24.13.1-win-x64/node.exe"
args = ["<USERPROFILE>/.codex/local-mcp-node/node_modules/@playwright/mcp/cli.js", ...]
```

**Critical**: NO `npx.cmd` references in any `command =` line.

### Process creation flags (in service script)

```python
CREATE_NO_WINDOW = 0x08000000
PROCESS_CREATION_FLAGS = CREATE_NO_WINDOW
```

**Critical**: NEVER combine with `DETACHED_PROCESS (0x8)` or `CREATE_NEW_PROCESS_GROUP (0x200)`.

## Files

| File | Purpose |
|---|---|
| `~/.codex/continue-watchdog.json` | Watchdog config |
| `~/.codex/scripts/codex_continue_watchdog_service.py` | Core watchdog daemon (1147 lines) |
| `~/.codex/scripts/codex_continue_watchdog.ps1` | PowerShell control interface |
| `~/.codex/scripts/verify_silent_watchdog.py` | 9-check verification script |
| `~/.codex/scripts/setup_silent_watchdog.ps1` | One-step repair script |
| `~/.codex/local-mcp-node/` | Locally installed MCP npm packages |
| `~/.codex/tmp/codex-continue-watchdog/state.json` | Runtime state |
| `~/.codex/tmp/codex-continue-watchdog/watchdog.log` | Runtime log |

## Invariants (NEVER violate these)

1. **No `.cmd` files** in any process launch chain (not `codex.cmd`, not `npx.cmd`, not any `.cmd`)
2. **No `DETACHED_PROCESS`** flag on any `subprocess.Popen` or `subprocess.run` call
3. **All `subprocess.run`** calls that invoke external tools (tasklist, taskkill, powershell) MUST include `creationflags=CREATE_NO_WINDOW` and `startupinfo=hidden_startupinfo()`
4. **`resume_backend`** must be `"cli"`, not `"app-only"`
5. **MCP servers** that were previously `npx.cmd` must use `node.exe` + local JS entry

## Response pattern

- For `status`: summarize `status`, `target_thread_id`, `cli_path`, `last_action`, `last_resume_outcome`, and cooldown/pause state.
- For `verify`: run `verify_silent_watchdog.py` and report pass/fail for each check.
- For control commands: execute the script and report the resulting status.
- If user reports cmd flashing: FIRST run verify, THEN check the watchdog log, THEN diagnose.

## Failure history

See the local failure notes markdown from 2026-03-11 for the full post-mortem. Key lesson: do not mix multiple problem domains (stuck thread repair + watchdog logic + MCP config) in a single debugging session.

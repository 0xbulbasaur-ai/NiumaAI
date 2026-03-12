"""Verify that the silent watchdog setup is correctly configured.

Run: python verify_silent_watchdog.py
This checks the silent CLI defaults and the conditions that caused the 2026-03-11 failure.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

CODEX_HOME = Path.home() / ".codex"
NODE_DIR = CODEX_HOME / "tools" / "node-v24.13.1-win-x64"
LOCAL_MCP = CODEX_HOME / "local-mcp-node"
NPM_ROOT = Path.home() / "AppData" / "Roaming" / "npm"
NATIVE_CLI = (
    NPM_ROOT / "node_modules" / "@openai" / "codex"
    / "node_modules" / "@openai" / "codex-win32-x64"
    / "vendor" / "x86_64-pc-windows-msvc" / "codex" / "codex.exe"
)

RED = "\033[91m"
GREEN = "\033[92m"
YELLOW = "\033[93m"
RESET = "\033[0m"

results: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    results.append((name, ok, detail))
    mark = f"{GREEN}PASS{RESET}" if ok else f"{RED}FAIL{RESET}"
    line = f"  [{mark}] {name}"
    if detail:
        line += f"  -- {detail}"
    print(line)


def service_has_detached_process_usage(source: str) -> tuple[bool, str]:
    for raw_line in source.splitlines():
        code_only = raw_line.split("#", 1)[0].strip()
        if not code_only:
            continue
        if "DETACHED_PROCESS" in code_only or "0x00000008" in code_only:
            return True, code_only
    return False, "service script checked"


def main() -> int:
    print("=== Silent Watchdog Verification ===\n")

    # 1. Native codex.exe exists
    check("native codex.exe exists", NATIVE_CLI.exists(), str(NATIVE_CLI))

    # 2. Native codex.exe responds to login status (hidden)
    if NATIVE_CLI.exists():
        try:
            si = subprocess.STARTUPINFO()
            si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            si.wShowWindow = subprocess.SW_HIDE
            r = subprocess.run(
                [str(NATIVE_CLI), "login", "status"],
                capture_output=True, text=True, timeout=20,
                creationflags=0x08000000,  # CREATE_NO_WINDOW
                startupinfo=si,
            )
            check("codex.exe login status", r.returncode == 0,
                  f"rc={r.returncode}" + (f" stderr={r.stderr.strip()[:80]}" if r.returncode else ""))
        except Exception as e:
            check("codex.exe login status", False, str(e))
    else:
        check("codex.exe login status", False, "binary missing")

    # 3. continue-watchdog.json uses silent CLI defaults
    wj = CODEX_HOME / "continue-watchdog.json"
    if wj.exists():
        cfg = json.loads(wj.read_text(encoding="utf-8"))
        backend = cfg.get("resume_backend", "app-only")
        check("resume_backend == cli", backend == "cli", f"current: {backend}")
        sandbox_policy = cfg.get("sandbox_policy", "")
        check(
            "sandbox_policy == danger-full-access",
            sandbox_policy == "danger-full-access",
            f"current: {sandbox_policy or '<missing>'}",
        )
        approval_mode = cfg.get("approval_mode", "")
        check(
            "approval_mode == never",
            approval_mode == "never",
            f"current: {approval_mode or '<missing>'}",
        )
    else:
        check("resume_backend == cli", False, "config missing")
        check("sandbox_policy == danger-full-access", False, "config missing")
        check("approval_mode == never", False, "config missing")

    # 4. Service script uses CREATE_NO_WINDOW only (no DETACHED_PROCESS)
    svc = CODEX_HOME / "scripts" / "codex_continue_watchdog_service.py"
    if svc.exists():
        src = svc.read_text(encoding="utf-8")
        has_detached, detail = service_has_detached_process_usage(src)
        check("no DETACHED_PROCESS in flags", not has_detached, detail)
    else:
        check("no DETACHED_PROCESS in flags", False, "service script missing")

    # 5. node.exe exists (for MCP)
    node = NODE_DIR / "node.exe"
    check("standalone node.exe exists", node.exists(), str(node))

    # 6. MCP packages installed locally
    ctx7 = LOCAL_MCP / "node_modules" / "@upstash" / "context7-mcp" / "dist" / "index.js"
    pw = LOCAL_MCP / "node_modules" / "@playwright" / "mcp" / "cli.js"
    check("context7-mcp installed locally", ctx7.exists(), str(ctx7))
    check("playwright-mcp installed locally", pw.exists(), str(pw))

    # 7. config.toml does NOT reference npx.cmd
    cfg_toml = CODEX_HOME / "config.toml"
    if cfg_toml.exists():
        toml_text = cfg_toml.read_text(encoding="utf-8")
        # Only check non-comment lines for npx.cmd references
        active_npx = [ln for ln in toml_text.splitlines()
                      if ("npx.cmd" in ln or "npx-cli.js" in ln)
                      and not ln.strip().startswith("#")]
        check("config.toml has no npx.cmd references", len(active_npx) == 0,
              f"found: {active_npx[0].strip()}" if active_npx else "clean")
    else:
        check("config.toml has no npx.cmd references", False, "file missing")

    # 8. No .cmd in MCP command paths (check for any .cmd command entries)
    if cfg_toml.exists():
        cmd_refs = [ln.strip() for ln in toml_text.splitlines()
                    if ln.strip().startswith("command") and ".cmd" in ln]
        check("no .cmd wrappers in MCP commands", len(cmd_refs) == 0,
              f"{len(cmd_refs)} .cmd refs found" if cmd_refs else "clean")

    print("\n=== Summary ===")
    passed = sum(1 for _, ok, _ in results if ok)
    total = len(results)
    if passed == total:
        print(f"{GREEN}All {total} checks passed.{RESET}")
        print("The watchdog should operate without visible cmd windows.")
        return 0
    else:
        print(f"{YELLOW}{passed}/{total} checks passed. Fix the failures above.{RESET}")
        return 1


if __name__ == "__main__":
    sys.exit(main())

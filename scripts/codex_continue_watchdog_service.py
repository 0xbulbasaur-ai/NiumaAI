from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import threading
import time
import traceback
import uuid
import ctypes
from collections import deque
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw
from pystray import Icon, Menu, MenuItem
from pywinauto import Desktop, keyboard


APP_ID = "OpenAI.Codex_2p2nqsd0c76g0!App"
CODEX_HOME = Path.home() / ".codex"
CONFIG_PATH = CODEX_HOME / "continue-watchdog.json"
STATE_DIR = CODEX_HOME / "tmp" / "codex-continue-watchdog"
CONTROL_DIR = STATE_DIR / "control"
ATTEMPT_DIR = STATE_DIR / "attempts"
LOCK_PATH = STATE_DIR / "watchdog.lock"
STATE_PATH = STATE_DIR / "state.json"
LOG_PATH = STATE_DIR / "watchdog.log"
GLOBAL_STATE_PATH = CODEX_HOME / ".codex-global-state.json"
STATE_DB_PATH = CODEX_HOME / "state_5.sqlite"
WINDOWS_NPM_ROOT = Path.home() / "AppData" / "Roaming" / "npm"
WINDOWS_NPM_CLI = WINDOWS_NPM_ROOT / "codex.cmd"
WINDOWS_NPM_NATIVE_CLI = (
    WINDOWS_NPM_ROOT
    / "node_modules"
    / "@openai"
    / "codex"
    / "node_modules"
    / "@openai"
    / "codex-win32-x64"
    / "vendor"
    / "x86_64-pc-windows-msvc"
    / "codex"
    / "codex.exe"
)
MONITOR_PY_PATH = CODEX_HOME / "scripts" / "codex_continue_watchdog_monitor.py"
POWERSHELL_EXE = shutil.which("powershell.exe") or "powershell.exe"
WINDOWS_TERMINAL_EXE = shutil.which("wt.exe")
PROCESS_NAMES = ("Codex.exe", "codex.exe")
DISPLAY_NAME = "NiumaAI"
MONITOR_HOST = "127.0.0.1"
MONITOR_PORT = 64906
CLI_FAILURE_THRESHOLD = 3
CLI_CONFIRM_SECONDS = 20
CLI_RETRY_SECONDS = 10
MAX_CONFIRM_SECONDS = 60
BOOTSTRAP_BYTES = 512 * 1024
BOOTSTRAP_LINES = 1200
# NOTE: CREATE_NO_WINDOW alone is the only reliable way to hide console
# processes on Windows. Combining it with DETACHED_PROCESS (0x8) causes
# unpredictable behavior where cmd windows may still flash.
# See: codex-watchdog-failure-notes-2026-03-11.md, Wrong Assumption #3.
CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)
PROCESS_CREATION_FLAGS = CREATE_NO_WINDOW


def default_workspace() -> Path:
    configured = os.environ.get("NIUMAAI_DEFAULT_CWD", "").strip()
    if configured:
        return Path(configured).expanduser()
    desktop_projects = Path.home() / "Desktop" / "Projects"
    if desktop_projects.exists():
        return desktop_projects
    return Path.home()


DEFAULT_CWD = default_workspace()

DEFAULT_CONFIG: dict[str, Any] = {
    "thread_scope": "pinned:first",
    "poll_seconds": 2,
    "idle_stop_seconds": 180,
    "max_resume_attempts": 5,
    "resume_window_minutes": 15,
    "cooldown_minutes": 30,
    "window_title": "Codex",
    "toast_notifications": True,
    "tray_enabled": True,
    "resume_backend": "cli",
    "stop_detection_mode": "task_complete_only",
    "monitor_port": MONITOR_PORT,
}


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def now_iso() -> str:
    return utc_now().isoformat().replace("+00:00", "Z")


def parse_ts(raw: str | None) -> datetime | None:
    if not raw:
        return None
    try:
        if raw.endswith("Z"):
            raw = raw[:-1] + "+00:00"
        return datetime.fromisoformat(raw)
    except ValueError:
        return None


def dt_to_str(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def active_window_title() -> str:
    user32 = ctypes.windll.user32
    hwnd = user32.GetForegroundWindow()
    if not hwnd:
        return ""
    length = user32.GetWindowTextLengthW(hwnd)
    if length <= 0:
        return ""
    buffer = ctypes.create_unicode_buffer(length + 1)
    user32.GetWindowTextW(hwnd, buffer, length + 1)
    return buffer.value


def ensure_dirs() -> None:
    for path in (STATE_DIR, CONTROL_DIR, ATTEMPT_DIR):
        path.mkdir(parents=True, exist_ok=True)


def atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    last_error: PermissionError | None = None
    for _attempt in range(5):
        try:
            tmp.replace(path)
            return
        except PermissionError as exc:
            last_error = exc
            time.sleep(0.05)
    if last_error is not None:
        raise last_error


def write_control_command(command: str) -> str:
    ensure_dirs()
    command_id = uuid.uuid4().hex
    payload = {"id": command_id, "command": command, "created_at": now_iso()}
    atomic_write_json(CONTROL_DIR / f"{command_id}.json", payload)
    return command_id


def read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def load_config() -> dict[str, Any]:
    config = dict(DEFAULT_CONFIG)
    raw = read_json(CONFIG_PATH, {})
    if isinstance(raw, dict):
        for key, value in raw.items():
            if key in DEFAULT_CONFIG:
                config[key] = value
    return config


def log(message: str) -> None:
    ensure_dirs()
    stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with LOG_PATH.open("a", encoding="utf-8") as handle:
        handle.write(f"[{stamp}] {message}\n")


def create_tray_image() -> Image.Image:
    image = Image.new("RGBA", (64, 64), (34, 41, 54, 255))
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((6, 6, 58, 58), radius=12, fill=(21, 128, 61, 255))
    draw.rectangle((18, 18, 46, 46), outline=(255, 255, 255, 255), width=4)
    draw.line((22, 32, 30, 40, 44, 24), fill=(255, 255, 255, 255), width=4)
    return image


def pid_exists(pid: int | None) -> bool:
    if not pid or pid <= 0:
        return False
    try:
        completed = subprocess.run(
            ["tasklist", "/FI", f"PID eq {pid}", "/FO", "CSV", "/NH"],
            check=False,
            capture_output=True,
            text=True,
            timeout=10,
            creationflags=CREATE_NO_WINDOW,
            startupinfo=hidden_startupinfo(),
        )
    except Exception:
        return False
    output = (completed.stdout or "").strip()
    return bool(output) and "No tasks are running" not in output


def is_codex_process_running() -> bool:
    for name in PROCESS_NAMES:
        try:
            completed = subprocess.run(
                ["tasklist", "/FI", f"IMAGENAME eq {name}", "/FO", "CSV", "/NH"],
                check=False,
                capture_output=True,
                text=True,
                timeout=10,
                creationflags=CREATE_NO_WINDOW,
                startupinfo=hidden_startupinfo(),
            )
        except Exception:
            continue
        output = (completed.stdout or "").strip()
        if output and "No tasks are running" not in output:
            return True
    return False


def terminate_process(pid: int | None) -> None:
    if not pid or pid <= 0:
        return
    try:
        subprocess.run(
            ["taskkill", "/F", "/T", "/PID", str(pid)],
            check=False,
            capture_output=True,
            text=True,
            timeout=10,
            creationflags=CREATE_NO_WINDOW,
            startupinfo=hidden_startupinfo(),
        )
    except Exception:
        pass


def hidden_startupinfo() -> subprocess.STARTUPINFO | None:
    if not hasattr(subprocess, "STARTUPINFO"):
        return None
    info = subprocess.STARTUPINFO()
    if hasattr(subprocess, "STARTF_USESHOWWINDOW"):
        info.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    if hasattr(subprocess, "SW_HIDE"):
        info.wShowWindow = subprocess.SW_HIDE
    return info


def run_hidden_process(args: list[str], *, timeout: int = 20) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        args,
        check=False,
        capture_output=True,
        text=True,
        timeout=timeout,
        creationflags=PROCESS_CREATION_FLAGS,
        startupinfo=hidden_startupinfo(),
    )


def open_visible_terminal(command: list[str], *, cwd: str, title: str) -> None:
    if WINDOWS_TERMINAL_EXE:
        subprocess.Popen(
            [
                WINDOWS_TERMINAL_EXE,
                "-w",
                "new",
                "new-tab",
                "--title",
                title,
                *command,
            ],
            cwd=cwd,
            close_fds=True,
        )
        return
    subprocess.Popen(command, cwd=cwd, close_fds=True)


def console_python_executable() -> str:
    current = Path(sys.executable)
    if current.name.lower() == "pythonw.exe":
        candidate = current.with_name("python.exe")
        if candidate.exists():
            return str(candidate)
    return str(current)


def monitor_text_preview(value: Any, max_length: int = 140) -> str:
    text = ""
    if value is None:
        return text
    if isinstance(value, str):
        text = value
    elif isinstance(value, list):
        for item in value:
            if isinstance(item, dict) and item.get("type") in {"output_text", "input_text"} and item.get("text"):
                text = str(item["text"])
                break
    else:
        text = str(value)
    text = " ".join(text.split())
    if len(text) > max_length:
        return text[:max_length] + "..."
    return text


def monitor_tool_output_summary(output: str) -> str:
    text = (output or "").strip()
    if not text:
        return "done"
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        payload = None
    if isinstance(payload, dict):
        ok = payload.get("ok")
        if ok is True:
            return "ok"
        if ok is False:
            error = payload.get("error")
            return f"error: {error}" if error else "failed"
    if "Exit code:" in text:
        return monitor_text_preview(text, max_length=110)
    lowered = text.lower()
    if any(token in lowered for token in ("failed", "error", "traceback", "exception")):
        return monitor_text_preview(text, max_length=110)
    return "done"


@dataclass
class MonitorRolloutSnapshot:
    entries: list[dict[str, str]]
    entry_count: int
    last_event_at: str | None
    last_event_kind: str | None
    rollout_last_write_at: str | None
    rollout_size: int
    revision: str


def format_monitor_rollout_entry(line: str, call_names: dict[str, str]) -> dict[str, str] | None:
    line = line.strip()
    if not line:
        return None
    try:
        item = json.loads(line)
    except json.JSONDecodeError:
        return None
    stamp = ""
    timestamp = parse_ts(item.get("timestamp"))
    if timestamp is not None:
        stamp = timestamp.astimezone().strftime("%H:%M:%S")
    at = dt_to_str(timestamp)
    item_type = str(item.get("type") or "")
    payload = item.get("payload")
    if item_type == "event_msg" and isinstance(payload, dict):
        payload_type = str(payload.get("type") or "")
        if payload_type == "task_started":
            return {
                "kind": "task_started",
                "at": at or "",
                "text": f"[{stamp}] task_started turn={payload.get('turn_id') or 'unknown'}",
            }
        if payload_type == "task_complete":
            return {
                "kind": "task_complete",
                "at": at or "",
                "text": f"[{stamp}] task_complete turn={payload.get('turn_id') or 'unknown'}",
            }
        if payload_type == "agent_message":
            message = monitor_text_preview(payload.get("message"))
            if message:
                return {"kind": "agent", "at": at or "", "text": f"[{stamp}] agent: {message}"}
        if payload_type == "user_message":
            message = monitor_text_preview(payload.get("message"))
            if message:
                return {"kind": "user", "at": at or "", "text": f"[{stamp}] user: {message}"}
        if payload_type == "token_count":
            return {"kind": "usage", "at": at or "", "text": f"[{stamp}] usage updated"}
        if payload_type:
            return {"kind": "event", "at": at or "", "text": f"[{stamp}] event: {payload_type}"}
        return None
    if item_type == "response_item" and isinstance(payload, dict):
        payload_type = str(payload.get("type") or "")
        if payload_type == "message":
            role = str(payload.get("role") or "message")
            message = monitor_text_preview(payload.get("content"))
            if message:
                return {"kind": role, "at": at or "", "text": f"[{stamp}] {role}: {message}"}
        if payload_type == "function_call":
            name = str(payload.get("name") or "")
            call_id = str(payload.get("call_id") or "")
            if call_id and name:
                call_names[call_id] = name
            if name:
                return {"kind": "tool_call", "at": at or "", "text": f"[{stamp}] tool -> {name}"}
        if payload_type == "function_call_output":
            call_id = str(payload.get("call_id") or "")
            tool_name = call_names.get(call_id, "tool")
            summary = monitor_tool_output_summary(str(payload.get("output") or ""))
            return {
                "kind": "tool_output",
                "at": at or "",
                "text": f"[{stamp}] tool <- {tool_name}: {summary}",
            }
        if payload_type == "reasoning":
            return {"kind": "reasoning", "at": at or "", "text": f"[{stamp}] reasoning"}
        if payload_type:
            return {"kind": "item", "at": at or "", "text": f"[{stamp}] item: {payload_type}"}
    return None


def read_monitor_rollout_entries(
    path: Path | None, *, tail_lines: int = 400, max_display: int = 180
) -> MonitorRolloutSnapshot:
    if path is None or not path.exists():
        return MonitorRolloutSnapshot(
            entries=[],
            entry_count=0,
            last_event_at=None,
            last_event_kind=None,
            rollout_last_write_at=None,
            rollout_size=0,
            revision="missing",
        )
    call_names: dict[str, str] = {}
    entries: deque[dict[str, str]] = deque(maxlen=max_display)
    total_entries = 0
    try:
        stat = path.stat()
        with path.open("r", encoding="utf-8", errors="replace") as handle:
            for line in deque(handle, maxlen=tail_lines):
                entry = format_monitor_rollout_entry(line, call_names)
                if entry:
                    entries.append(entry)
                    total_entries += 1
    except OSError:
        return MonitorRolloutSnapshot(
            entries=[],
            entry_count=0,
            last_event_at=None,
            last_event_kind=None,
            rollout_last_write_at=None,
            rollout_size=0,
            revision="error",
        )
    rendered_entries = list(entries)
    last_entry = rendered_entries[-1] if rendered_entries else None
    last_entry_at = str(last_entry.get("at") or "") if last_entry else ""
    last_entry_kind = str(last_entry.get("kind") or "") if last_entry else ""
    last_write_at = datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc)
    return MonitorRolloutSnapshot(
        entries=rendered_entries,
        entry_count=total_entries,
        last_event_at=last_entry_at or None,
        last_event_kind=last_entry_kind or None,
        rollout_last_write_at=dt_to_str(last_write_at),
        rollout_size=stat.st_size,
        revision=f"{stat.st_mtime_ns}:{stat.st_size}:{len(rendered_entries)}",
    )


class MonitorHttpServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, server_address: tuple[str, int], service: "WatchdogService") -> None:
        super().__init__(server_address, MonitorRequestHandler)
        self.service = service


class MonitorRequestHandler(BaseHTTPRequestHandler):
    server_version = "NiumaAIMonitor/1.0"

    def do_GET(self) -> None:
        path = self.path.split("?", 1)[0]
        service = self.server.service
        if path in {"/", "/index.html"}:
            self._send_html(service.monitor_page_html())
            return
        if path == "/api/session":
            self._send_json(service.monitor_api_payload())
            return
        self.send_error(404)

    def log_message(self, _format: str, *_args: Any) -> None:
        return

    def _send_html(self, body: str) -> None:
        encoded = body.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def _send_json(self, payload: dict[str, Any]) -> None:
        encoded = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)


def _find_process_ids_via_powershell(where_clause: str) -> list[int]:
    command = (
        "$procs = Get-CimInstance Win32_Process | Where-Object { "
        + where_clause
        + " } | Select-Object -ExpandProperty ProcessId; "
        "$procs | ConvertTo-Json -Compress"
    )
    try:
        completed = run_hidden_process(
            [POWERSHELL_EXE, "-NoProfile", "-NoLogo", "-NonInteractive", "-Command", command],
            timeout=15,
        )
    except Exception:
        return []
    if completed.returncode != 0:
        return []
    raw = (completed.stdout or "").strip()
    if not raw:
        return []
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return []
    if isinstance(parsed, int):
        return [parsed]
    if isinstance(parsed, list):
        return [int(item) for item in parsed if isinstance(item, int)]
    return []


def find_session_monitor_pids() -> list[int]:
    pids: set[int] = set()
    pids.update(
        _find_process_ids_via_powershell(
            "$_.Name -eq 'powershell.exe' -and $_.CommandLine -like '*codex_continue_watchdog_monitor.ps1*'"
        )
    )
    pids.update(
        _find_process_ids_via_powershell(
            "$_.Name -eq 'python.exe' -and $_.CommandLine -like '*codex_continue_watchdog_monitor.py*'"
        )
    )
    pids.update(
        _find_process_ids_via_powershell(
            "$_.Name -eq 'pythonw.exe' -and $_.CommandLine -like '*codex_continue_watchdog_monitor.py*'"
        )
    )
    pids.update(
        _find_process_ids_via_powershell(
            "$_.Name -eq 'WindowsTerminal.exe' -and $_.CommandLine -like '*NiumaAI Session Monitor*'"
        )
    )
    return sorted(pid for pid in pids if pid > 0)


def discover_cli() -> tuple[Path | None, str | None]:
    candidates = [WINDOWS_NPM_NATIVE_CLI, WINDOWS_NPM_CLI]
    for command_name in ("codex.exe", "codex.cmd", "codex"):
        resolved = shutil.which(command_name)
        if resolved:
            candidates.append(Path(resolved))
    seen: set[str] = set()
    errors: list[str] = []
    for candidate in candidates:
        if not candidate:
            continue
        key = str(candidate).lower()
        if key in seen or not candidate.exists():
            continue
        seen.add(key)
        try:
            completed = run_hidden_process([str(candidate), "login", "status"], timeout=20)
        except Exception as exc:
            errors.append(f"{candidate}: {exc}")
            continue
        if completed.returncode == 0:
            return candidate, None
        stderr = (completed.stderr or completed.stdout or "").strip() or "Unknown login error."
        errors.append(f"{candidate}: {stderr}")
    if errors:
        return None, "Codex CLI is installed but unavailable: " + " | ".join(errors)
    return None, "Codex CLI was not found. Install @openai/codex with npm."


def find_matching_resume_pids(cli_path: Path | None, thread_id: str | None) -> list[int]:
    if cli_path is None:
        return []
    exe = str(cli_path).replace("'", "''")
    thread_fragment = thread_id or ""
    command = (
        "$procs = Get-CimInstance Win32_Process | Where-Object { "
        "$_.Name -eq 'codex.exe' -and "
        f"$_.ExecutablePath -eq '{exe}' -and "
        "$_.CommandLine -like '*exec resume*continue*' "
    )
    if thread_fragment:
        thread_fragment = thread_fragment.replace("'", "''")
        command += f"-and $_.CommandLine -like '*{thread_fragment}*' "
    command += "} | Select-Object -ExpandProperty ProcessId; $procs | ConvertTo-Json -Compress"
    try:
        completed = run_hidden_process(
            ["powershell.exe", "-NoProfile", "-NoLogo", "-NonInteractive", "-Command", command],
            timeout=15,
        )
    except Exception:
        return []
    if completed.returncode != 0:
        return []
    raw = (completed.stdout or "").strip()
    if not raw:
        return []
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return []
    if isinstance(parsed, int):
        return [parsed]
    if isinstance(parsed, list):
        return [int(item) for item in parsed if isinstance(item, int)]
    return []


def ensure_codex_app_running() -> None:
    if is_codex_process_running():
        return
    subprocess.Popen(
        ["explorer.exe", fr"shell:AppsFolder\{APP_ID}"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        close_fds=True,
    )
    log("Launched Codex app.")


def try_open_thread(thread_id: str) -> None:
    try:
        os.startfile(f"codex://threads/{thread_id}")
        log(f"Opened thread via codex://threads/{thread_id}")
    except Exception as exc:
        log(f"Thread deep link unavailable for {thread_id}: {exc}")


def focus_codex_and_send_continue(window_title: str, thread_id: str) -> None:
    ensure_codex_app_running()
    deadline = time.time() + 10
    window = None
    while time.time() < deadline:
        windows = [item for item in Desktop(backend="uia").windows() if item.window_text() and window_title.lower() in item.window_text().lower()]
        if windows:
            window = max(windows, key=lambda item: item.rectangle().width() * item.rectangle().height())
            break
        time.sleep(0.5)
    if window is None:
        raise RuntimeError(f'No visible window matching "{window_title}" appeared.')
    try_open_thread(thread_id)
    time.sleep(0.6)
    window.set_focus()
    time.sleep(0.2)
    rect = window.rectangle()
    click_x = max(60, rect.width() // 2)
    click_y = max(60, rect.height() - 110)
    window.click_input(coords=(click_x, click_y))
    time.sleep(0.2)
    keyboard.send_keys("^a{BACKSPACE}")
    keyboard.send_keys("continue{ENTER}", with_spaces=True, pause=0.02)


@dataclass
class ThreadSnapshot:
    thread_id: str | None = None
    rollout_path: str | None = None
    last_event_at: datetime | None = None
    last_event_type: str | None = None
    last_task_started_at: datetime | None = None
    last_task_started_turn_id: str | None = None
    last_task_complete_at: datetime | None = None
    last_task_complete_turn_id: str | None = None
    last_loaded_size: int = 0


@dataclass
class StopContext:
    key: str
    thread_id: str
    reason: str
    detected_at: datetime
    last_attempt_at: datetime | None = None
    cli_failures: int = 0
    fallback_used: bool = False
    waiting_for_confirmation: bool = False
    confirmation_deadline: datetime | None = None
    confirmation_max_deadline: datetime | None = None
    confirmation_started_at: datetime | None = None
    active_cli_pid: int | None = None
    active_cli_command: list[str] = field(default_factory=list)
    resume_method: str | None = None


@dataclass
class ThreadRecord:
    thread_id: str
    rollout_path: str | None = None
    source: str | None = None
    cwd: str | None = None
    title: str | None = None
    sandbox_policy: str | None = None
    approval_mode: str | None = None
    updated_at: int | None = None


class RolloutTracker:
    def __init__(self) -> None:
        self.thread_id: str | None = None
        self.path: Path | None = None
        self.offset = 0
        self.partial = ""
        self.snapshot = ThreadSnapshot()

    def update_target(self, thread_id: str | None, path: Path | None) -> None:
        if self.thread_id == thread_id and self.path == path:
            return
        self.thread_id = thread_id
        self.path = path
        self.offset = 0
        self.partial = ""
        self.snapshot = ThreadSnapshot(thread_id=thread_id, rollout_path=str(path) if path else None)
        if path and path.exists():
            self._bootstrap()

    def refresh(self) -> ThreadSnapshot:
        if not self.path or not self.path.exists():
            self.snapshot.thread_id = self.thread_id
            self.snapshot.rollout_path = str(self.path) if self.path else None
            return self.snapshot
        if self.offset == 0:
            self._bootstrap()
        size = self.path.stat().st_size
        if size < self.offset:
            self.offset = 0
            self.partial = ""
            self.snapshot = ThreadSnapshot(thread_id=self.thread_id, rollout_path=str(self.path))
            self._bootstrap()
            return self.snapshot
        if size == self.offset:
            self.snapshot.last_loaded_size = size
            return self.snapshot
        with self.path.open("r", encoding="utf-8", errors="replace") as handle:
            handle.seek(self.offset)
            chunk = handle.read()
        self.offset = size
        self._consume_text(chunk)
        self.snapshot.last_loaded_size = size
        return self.snapshot

    def _bootstrap(self) -> None:
        assert self.path is not None
        size = self.path.stat().st_size
        read_size = min(size, BOOTSTRAP_BYTES)
        with self.path.open("rb") as handle:
            handle.seek(max(0, size - read_size))
            raw = handle.read().decode("utf-8", errors="replace")
        lines = raw.splitlines()[-BOOTSTRAP_LINES:]
        self.snapshot = ThreadSnapshot(thread_id=self.thread_id, rollout_path=str(self.path), last_loaded_size=size)
        for line in lines:
            self._consume_line(line)
        if size > read_size and (
            self.snapshot.last_task_started_at is None or self.snapshot.last_task_complete_at is None
        ):
            self._recover_task_markers_from_full_scan()
        self.offset = size
        self.partial = ""

    def _recover_task_markers_from_full_scan(self) -> None:
        assert self.path is not None
        last_task_started_at = self.snapshot.last_task_started_at
        last_task_started_turn_id = self.snapshot.last_task_started_turn_id
        last_task_complete_at = self.snapshot.last_task_complete_at
        last_task_complete_turn_id = self.snapshot.last_task_complete_turn_id
        with self.path.open("r", encoding="utf-8", errors="replace") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                try:
                    item = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if str(item.get("type") or "") != "event_msg":
                    continue
                payload = item.get("payload")
                if not isinstance(payload, dict):
                    continue
                payload_type = str(payload.get("type") or "")
                timestamp = parse_ts(item.get("timestamp"))
                if payload_type == "task_started":
                    last_task_started_at = timestamp
                    last_task_started_turn_id = str(payload.get("turn_id") or "")
                elif payload_type == "task_complete":
                    last_task_complete_at = timestamp
                    last_task_complete_turn_id = str(payload.get("turn_id") or "")
        self.snapshot.last_task_started_at = last_task_started_at
        self.snapshot.last_task_started_turn_id = last_task_started_turn_id
        self.snapshot.last_task_complete_at = last_task_complete_at
        self.snapshot.last_task_complete_turn_id = last_task_complete_turn_id

    def _consume_text(self, text: str) -> None:
        blob = self.partial + text
        lines = blob.splitlines(keepends=False)
        if blob and not blob.endswith(("\n", "\r")):
            self.partial = lines.pop() if lines else blob
        else:
            self.partial = ""
        for line in lines:
            self._consume_line(line)

    def _consume_line(self, line: str) -> None:
        line = line.strip()
        if not line:
            return
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            return
        timestamp = parse_ts(item.get("timestamp"))
        item_type = str(item.get("type") or "")
        event_type = item_type
        payload = item.get("payload")
        if item_type == "event_msg" and isinstance(payload, dict):
            payload_type = str(payload.get("type") or "")
            event_type = payload_type or item_type
            if payload_type == "task_started":
                self.snapshot.last_task_started_at = timestamp
                self.snapshot.last_task_started_turn_id = str(payload.get("turn_id") or "")
            elif payload_type == "task_complete":
                self.snapshot.last_task_complete_at = timestamp
                self.snapshot.last_task_complete_turn_id = str(payload.get("turn_id") or "")
        if timestamp is not None:
            self.snapshot.last_event_at = timestamp
        self.snapshot.last_event_type = event_type


class WatchdogService:
    def __init__(self) -> None:
        ensure_dirs()
        self.config = load_config()
        self.started_at = utc_now()
        self.tracker = RolloutTracker()
        self.stop_requested = False
        self.paused = False
        self.cooling_down_until: datetime | None = None
        self.resume_attempts: deque[datetime] = deque()
        self.last_notification: str | None = None
        self.last_action: str | None = None
        self.last_resume_at: datetime | None = None
        self.last_resume_outcome: str | None = None
        self.current_stop: StopContext | None = None
        self.active_cli_pid: int | None = None
        self.active_cli_command: list[str] = []
        self.target_record: ThreadRecord | None = None
        self.arm_thread_id: str | None = None
        self.arm_started_at: datetime = utc_now()
        self.arm_fresh_task_seen = False
        self.arm_ignored_stop_key: str | None = None
        if str(self.config.get("resume_backend", "app-only")) == "app-only":
            self.cli_path, self.cli_error = None, None
        else:
            self.cli_path, self.cli_error = discover_cli()
        self.icon: Icon | None = None
        self.monitor_server: MonitorHttpServer | None = None
        self.monitor_server_thread: threading.Thread | None = None
        self.monitor_url: str | None = None
        self.state_version = 1

    def _cancel_active_resume(self, reason: str) -> None:
        thread_id = self.tracker.snapshot.thread_id
        pids_to_kill: set[int] = set(find_matching_resume_pids(self.cli_path, thread_id))
        pid = None
        if self.current_stop and self.current_stop.active_cli_pid:
            pid = self.current_stop.active_cli_pid
            self.current_stop.active_cli_pid = None
            self.current_stop.active_cli_command = []
            self.current_stop.waiting_for_confirmation = False
            self.current_stop.confirmation_deadline = None
            self.current_stop.confirmation_max_deadline = None
            self.current_stop.confirmation_started_at = None
        elif self.active_cli_pid:
            pid = self.active_cli_pid
        if pid:
            pids_to_kill.add(pid)
        for active_pid in sorted(pids_to_kill):
            terminate_process(active_pid)
            log(f"Cancelled active CLI resume pid {active_pid} ({reason}).")
        self.active_cli_pid = None
        self.active_cli_command = []

    def _refresh_active_resume_process(self) -> None:
        if not self.active_cli_pid:
            return
        if pid_exists(self.active_cli_pid):
            return
        self.active_cli_pid = None
        self.active_cli_command = []

    def run(self) -> int:
        if not self._acquire_lock():
            log("Another watchdog instance is already running.")
            return 1
        self._purge_stale_control_commands()
        self._start_monitor_server()
        log("Watchdog service starting.")
        self._start_tray()
        try:
            while not self.stop_requested:
                try:
                    self._loop_once()
                except Exception:
                    error_text = traceback.format_exc()
                    log("Unhandled watchdog error:\n" + error_text.rstrip())
                    self.last_resume_outcome = "service_error"
                    self._write_state(status="stopped")
                    time.sleep(max(1, int(self.config["poll_seconds"])))
                time.sleep(max(1, int(self.config["poll_seconds"])))
        finally:
            self.stop_requested = True
            self._cancel_active_resume("shutdown")
            if self.icon:
                try:
                    self.icon.stop()
                except Exception:
                    pass
            self._stop_monitor_server()
            self._write_state(status="stopped")
            self._release_lock()
            log("Watchdog service stopped.")
        return 0

    def _acquire_lock(self) -> bool:
        existing = read_json(LOCK_PATH, {})
        if isinstance(existing, dict) and pid_exists(int(existing.get("pid") or 0)):
            return False
        atomic_write_json(LOCK_PATH, {"pid": os.getpid(), "started_at": now_iso()})
        return True

    def _release_lock(self) -> None:
        try:
            if LOCK_PATH.exists():
                LOCK_PATH.unlink()
        except OSError:
            pass

    def _purge_stale_control_commands(self) -> None:
        for path in CONTROL_DIR.glob("*.json"):
            try:
                path.unlink(missing_ok=True)
            except OSError:
                pass

    def _start_tray(self) -> None:
        if not self.config.get("tray_enabled", True):
            return
        self.icon = Icon(
            "codex-continue-watchdog",
            icon=create_tray_image(),
            title=DISPLAY_NAME,
            menu=Menu(
                MenuItem("Open Session Monitor", self._tray_open_session_monitor, default=True),
                MenuItem("Open Codex CLI (Interactive)", self._tray_open_codex_cli),
                MenuItem("Pause", self._tray_pause, visible=self._tray_pause_visible),
                MenuItem("Continue", self._tray_continue, visible=self._tray_continue_visible),
                MenuItem("Exit", self._tray_exit),
            ),
        )
        threading.Thread(target=self.icon.run, name="watchdog-tray", daemon=True).start()

    def _start_monitor_server(self) -> None:
        preferred_port = int(self.config.get("monitor_port") or MONITOR_PORT)
        last_error: OSError | None = None
        for port in (preferred_port, 0):
            if port == preferred_port and port < 0:
                continue
            try:
                self.monitor_server = MonitorHttpServer((MONITOR_HOST, port), self)
                break
            except OSError as exc:
                last_error = exc
                self.monitor_server = None
                if port == 0:
                    self.monitor_url = None
                    log(f"Failed to start monitor server: {exc}")
                    return
        if not self.monitor_server:
            self.monitor_url = None
            if last_error is not None:
                log(f"Failed to start monitor server: {last_error}")
            return
        actual_port = int(self.monitor_server.server_address[1])
        self.monitor_url = f"http://{MONITOR_HOST}:{actual_port}/"
        self.monitor_server_thread = threading.Thread(
            target=self.monitor_server.serve_forever,
            name="watchdog-monitor-http",
            daemon=True,
        )
        self.monitor_server_thread.start()
        if actual_port == preferred_port:
            log(f"Monitor server listening on {self.monitor_url}")
        else:
            log(
                f"Monitor server listening on fallback {self.monitor_url} "
                f"(preferred {preferred_port} unavailable)"
            )

    def _stop_monitor_server(self) -> None:
        if not self.monitor_server:
            return
        try:
            self.monitor_server.shutdown()
            self.monitor_server.server_close()
        except Exception:
            pass
        self.monitor_server = None
        self.monitor_server_thread = None

    def monitor_api_payload(self) -> dict[str, Any]:
        snapshot = self.tracker.snapshot
        rollout_path = Path(snapshot.rollout_path) if snapshot.rollout_path else None
        rollout_snapshot = read_monitor_rollout_entries(rollout_path)
        return {
            "thread_id": snapshot.thread_id,
            "status": self._compute_status_name(),
            "rollout_path": snapshot.rollout_path,
            "last_event_at": rollout_snapshot.last_event_at or dt_to_str(snapshot.last_event_at),
            "last_event_type": rollout_snapshot.last_event_kind or snapshot.last_event_type,
            "last_task_started_at": dt_to_str(snapshot.last_task_started_at),
            "last_task_complete_at": dt_to_str(snapshot.last_task_complete_at),
            "rollout_last_write_at": rollout_snapshot.rollout_last_write_at,
            "rollout_size": rollout_snapshot.rollout_size,
            "entry_count": rollout_snapshot.entry_count,
            "entries_revision": rollout_snapshot.revision,
            "updated_at": now_iso(),
            "entries": rollout_snapshot.entries,
        }

    def monitor_page_html(self) -> str:
        return """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>NiumaAI Session Monitor</title>
  <style>
    :root {
      --bg: #0b0e12;
      --panel: #121821;
      --line: #1e2733;
      --text: #e7edf6;
      --muted: #93a3b8;
      --accent: #4cc2ff;
      --accent-2: #7ef0c3;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      min-height: 100vh;
      background:
        radial-gradient(circle at top right, rgba(76, 194, 255, 0.12), transparent 28%),
        radial-gradient(circle at bottom left, rgba(126, 240, 195, 0.09), transparent 32%),
        var(--bg);
      color: var(--text);
      font: 14px/1.45 "Consolas", "Cascadia Mono", "Microsoft YaHei UI", monospace;
    }
    .wrap {
      width: min(1200px, calc(100vw - 32px));
      margin: 24px auto;
    }
    .header {
      margin-bottom: 16px;
      padding: 16px 18px;
      border: 1px solid var(--line);
      border-radius: 16px;
      background: rgba(18, 24, 33, 0.9);
      backdrop-filter: blur(12px);
    }
    .title {
      margin: 0 0 10px;
      font-size: 20px;
      font-weight: 700;
      letter-spacing: 0.02em;
    }
    .meta {
      display: grid;
      gap: 8px;
      color: var(--muted);
    }
    .meta strong { color: var(--text); }
    .board {
      border: 1px solid var(--line);
      border-radius: 16px;
      background: rgba(12, 16, 22, 0.94);
      overflow: hidden;
    }
    .toolbar {
      display: flex;
      justify-content: space-between;
      gap: 12px;
      padding: 12px 16px;
      border-bottom: 1px solid var(--line);
      color: var(--muted);
    }
    .pill {
      display: inline-flex;
      align-items: center;
      gap: 8px;
      padding: 6px 10px;
      border-radius: 999px;
      background: rgba(76, 194, 255, 0.08);
      color: var(--accent);
    }
    pre {
      margin: 0;
      padding: 18px 20px 28px;
      min-height: 70vh;
      max-height: 76vh;
      overflow: auto;
      white-space: pre-wrap;
      word-break: break-word;
    }
    .empty {
      color: var(--muted);
    }
  </style>
</head>
<body>
  <div class="wrap">
    <section class="header">
      <h1 class="title">NiumaAI Session Monitor</h1>
      <div class="meta" id="meta">Loading...</div>
    </section>
    <section class="board">
      <div class="toolbar">
        <div class="pill" id="status-pill">Connecting</div>
        <div id="updated">...</div>
      </div>
      <pre id="entries" class="empty">Loading...</pre>
    </section>
  </div>
  <script>
    const metaEl = document.getElementById("meta");
    const entriesEl = document.getElementById("entries");
    const updatedEl = document.getElementById("updated");
    const statusPill = document.getElementById("status-pill");
    let refreshTimer = null;
    let refreshInFlight = false;
    let requestSeq = 0;
    let appliedSeq = 0;
    let lastRevision = "";
    function scheduleRefresh(delayMs) {
      if (refreshTimer) {
        clearTimeout(refreshTimer);
      }
      refreshTimer = setTimeout(refresh, delayMs);
    }
    function fmt(raw) {
      if (!raw) return "n/a";
      try { return new Date(raw).toLocaleString(); } catch { return raw; }
    }
    function render(data) {
      metaEl.innerHTML =
        "<div><strong>Thread:</strong> " + (data.thread_id || "none") + "</div>" +
        "<div><strong>Last session event:</strong> " + fmt(data.last_event_at) + " (" + (data.last_event_type || "n/a") + ")</div>" +
        "<div><strong>Rollout updated:</strong> " + fmt(data.rollout_last_write_at) + "</div>" +
        "<div><strong>Rollout:</strong> " + (data.rollout_path || "unavailable") + "</div>";
      statusPill.textContent =
        "Status: " + (data.status || "unknown") +
        " | tail entries: " + String(data.entry_count || 0);
      updatedEl.textContent =
        "Polled: " + fmt(data.updated_at) +
        " | file bytes: " + String(data.rollout_size || 0);
      const rendered = (data.entries || []).map(item => item.text).join("\\n");
      const isNearBottom =
        entriesEl.scrollHeight - entriesEl.clientHeight - entriesEl.scrollTop < 24;
      entriesEl.textContent = rendered || "No session events yet.";
      entriesEl.className = rendered ? "" : "empty";
      if (isNearBottom || !lastRevision) {
        entriesEl.scrollTop = entriesEl.scrollHeight;
      }
      lastRevision = data.entries_revision || "";
    }
    async function refresh() {
      if (refreshInFlight) {
        return;
      }
      refreshInFlight = true;
      const seq = ++requestSeq;
      try {
        const res = await fetch("/api/session?t=" + Date.now(), { cache: "no-store" });
        if (!res.ok) throw new Error("HTTP " + res.status);
        const data = await res.json();
        if (seq >= appliedSeq) {
          appliedSeq = seq;
          render(data);
        }
      } catch (error) {
        metaEl.textContent = "Monitor API unavailable.";
        entriesEl.textContent = String(error);
        entriesEl.className = "empty";
        statusPill.textContent = "Disconnected";
        updatedEl.textContent = "Last poll failed";
      } finally {
        refreshInFlight = false;
        scheduleRefresh(1000);
      }
    }
    refresh();
  </script>
</body>
</html>
"""

    def _notify(self, message: str) -> None:
        self.last_notification = message
        log(message)
        if self.config.get("toast_notifications") and self.icon:
            try:
                self.icon.notify(message, DISPLAY_NAME)
            except Exception:
                pass

    def _refresh_tray_menu(self) -> None:
        if not self.icon:
            return
        try:
            self.icon.update_menu()
        except Exception:
            pass

    def _tray_status(self, icon: Icon, _item: MenuItem) -> None:
        state = self._state_payload(self._compute_status_name())
        summary = "\n".join(
            [
                f"status={state['status']}",
                f"running={state['running']}",
                f"paused={state['paused']}",
                f"thread={state['target_thread_id'] or 'none'}",
                f"active_cli_pid={state['active_cli_pid'] or 'none'}",
                f"last_action={state['last_action'] or 'none'}",
                f"last_outcome={state['last_resume_outcome'] or 'none'}",
                f"cooldown_until={state['cooling_down_until'] or 'none'}",
            ]
        )
        try:
            icon.notify(summary, DISPLAY_NAME)
        except Exception:
            pass

    def _tray_pause_visible(self, _item: MenuItem) -> bool:
        return not self.paused

    def _tray_continue_visible(self, _item: MenuItem) -> bool:
        return self.paused

    def _tray_pause(self, _icon: Icon, _item: MenuItem) -> None:
        write_control_command("pause")

    def _tray_continue(self, _icon: Icon, _item: MenuItem) -> None:
        write_control_command("resume")

    def _tray_open_session_monitor(self, _icon: Icon, _item: MenuItem) -> None:
        if not self.monitor_url:
            self._notify("Session monitor is unavailable.")
            return
        try:
            for pid in find_session_monitor_pids():
                terminate_process(pid)
            command = [
                console_python_executable(),
                "-u",
                str(MONITOR_PY_PATH),
                "--state-path",
                str(STATE_PATH),
                "--monitor-url",
                self.monitor_url,
            ]
            open_visible_terminal(command, cwd=str(DEFAULT_CWD), title="NiumaAI Session Monitor")
            log(f"Opened session monitor terminal at {self.monitor_url}")
        except Exception as exc:
            log(f"Failed to open session monitor terminal: {exc}")
            self._notify("Failed to open session monitor.")

    def _tray_open_codex_cli(self, _icon: Icon, _item: MenuItem) -> None:
        thread_id = self.tracker.snapshot.thread_id or (self.target_record.thread_id if self.target_record else None)
        if not thread_id:
            self._notify("No pinned Codex thread is available to open.")
            return
        cli_path = str(self.cli_path or WINDOWS_NPM_NATIVE_CLI)
        cwd = str(Path(self.target_record.cwd)) if self.target_record and self.target_record.cwd else str(DEFAULT_CWD)
        try:
            open_visible_terminal(
                [
                    POWERSHELL_EXE,
                    "-NoExit",
                    "-ExecutionPolicy",
                    "Bypass",
                    "-Command",
                    f"& '{cli_path}' resume {thread_id} -C '{cwd}' -s danger-full-access -a never --no-alt-screen",
                ],
                cwd=cwd,
                title="NiumaAI Codex CLI",
            )
            log(f"Opened interactive Codex CLI for thread {thread_id}.")
        except Exception as exc:
            log(f"Failed to open interactive Codex CLI for thread {thread_id}: {exc}")
            self._notify("Failed to open Codex CLI window.")

    def _tray_exit(self, _icon: Icon, _item: MenuItem) -> None:
        write_control_command("stop")

    def _has_resumable_task_complete(self, snapshot: ThreadSnapshot) -> bool:
        return bool(
            snapshot.thread_id
            and snapshot.last_task_complete_at
            and (
                snapshot.last_task_started_at is None
                or snapshot.last_task_complete_at >= snapshot.last_task_started_at
            )
        )

    def _has_active_task_history(self, snapshot: ThreadSnapshot) -> bool:
        return bool(snapshot.thread_id and snapshot.last_task_started_at)

    def _refresh_arm_state(self, snapshot: ThreadSnapshot) -> None:
        thread_id = snapshot.thread_id
        if thread_id != self.arm_thread_id:
            self.arm_thread_id = thread_id
            self.arm_started_at = utc_now()
            self.arm_fresh_task_seen = False
            self.arm_ignored_stop_key = None
        if self.arm_fresh_task_seen:
            return
        if snapshot.last_task_started_at and snapshot.last_task_started_at >= self.arm_started_at:
            self.arm_fresh_task_seen = True
            self.arm_ignored_stop_key = None
            if thread_id:
                log(f"Armed watchdog for {thread_id} after fresh task_started.")
            return
        if self._has_resumable_task_complete(snapshot):
            self.arm_fresh_task_seen = True
            self.arm_ignored_stop_key = None
            if thread_id:
                log(f"Armed watchdog for {thread_id} from existing task_complete.")
            return
        if self._has_active_task_history(snapshot):
            self.arm_fresh_task_seen = True
            self.arm_ignored_stop_key = None
            if thread_id:
                log(f"Armed watchdog for {thread_id} from existing task_started.")

    def _loop_once(self) -> None:
        self._process_control_commands()
        self._refresh_active_resume_process()
        if not self.stop_requested:
            self.config = load_config()
        thread = self._select_target_thread()
        self.target_record = thread
        thread_id = thread.thread_id if thread else None
        rollout_path = Path(thread.rollout_path) if thread and thread.rollout_path else self._find_rollout_path(thread_id)
        self.tracker.update_target(thread_id, rollout_path)
        snapshot = self.tracker.refresh()
        self._refresh_arm_state(snapshot)
        if self.current_stop and self.current_stop.thread_id != snapshot.thread_id:
            self._cancel_active_resume("target changed")
            self.current_stop = None
        self._refresh_confirmation(snapshot)
        stop_signal = self._detect_stop(snapshot)
        if not self.arm_fresh_task_seen:
            if stop_signal and stop_signal["key"] != self.arm_ignored_stop_key:
                self.arm_ignored_stop_key = stop_signal["key"]
                log(
                    f"Ignoring pre-existing stop condition: {stop_signal['reason']} for "
                    f"{snapshot.thread_id or 'none'} until a fresh task_started is observed."
                )
            status = "paused" if self.paused else (
                "running"
                if str(self.config.get("resume_backend", "app-only")) == "app-only"
                else ("cli_unavailable" if self.cli_path is None else "running")
            )
            self._write_state(status=status, snapshot=snapshot)
            return
        if self.paused:
            self._write_state(status="paused", snapshot=snapshot)
            return
        if self.cooling_down_until and utc_now() < self.cooling_down_until:
            self._write_state(status="cooling_down", snapshot=snapshot)
            return
        if self.cooling_down_until and utc_now() >= self.cooling_down_until:
            self.cooling_down_until = None
        if stop_signal is None:
            self.current_stop = None
            status = "running" if str(self.config.get("resume_backend", "app-only")) == "app-only" else ("cli_unavailable" if self.cli_path is None else "running")
            self._write_state(status=status, snapshot=snapshot)
            return
        if str(self.config.get("resume_backend", "app-only")) != "app-only" and self.cli_path is None:
            self._write_state(status="cli_unavailable", snapshot=snapshot)
            return
        if not self.current_stop or self.current_stop.key != stop_signal["key"]:
            self.current_stop = StopContext(
                key=stop_signal["key"],
                thread_id=thread_id or "",
                reason=stop_signal["reason"],
                detected_at=utc_now(),
            )
            log(f"Detected stop condition: {stop_signal['reason']} for {thread_id}")
        if self.current_stop.waiting_for_confirmation:
            status = "fallback_pending" if self.current_stop.fallback_used else "running"
            self._write_state(status=status, snapshot=snapshot)
            return
        if self.current_stop.last_attempt_at and utc_now() < self.current_stop.last_attempt_at + timedelta(seconds=CLI_RETRY_SECONDS):
            status = "fallback_pending" if self.current_stop.fallback_used else "running"
            self._write_state(status=status, snapshot=snapshot)
            return
        if self._attempt_budget_exhausted():
            self.cooling_down_until = utc_now() + timedelta(minutes=int(self.config["cooldown_minutes"]))
            self._notify("Auto resume paused: attempt budget exhausted, entering cooldown.")
            self._write_state(status="cooling_down", snapshot=snapshot)
            return
        if str(self.config.get("resume_backend", "app-only")) == "app-only":
            self._attempt_app_resume(snapshot)
            self._write_state(status="running", snapshot=snapshot)
            return
        if self.current_stop.cli_failures < CLI_FAILURE_THRESHOLD:
            self._attempt_cli_resume(snapshot)
            self._write_state(status="running", snapshot=snapshot)
            return
        if not self.current_stop.fallback_used:
            self._attempt_foreground_fallback(snapshot)
            self._write_state(status="fallback_pending", snapshot=snapshot)
            return
        self._write_state(status="cooling_down", snapshot=snapshot)

    def _attempt_budget_exhausted(self) -> bool:
        now = utc_now()
        window = timedelta(minutes=int(self.config["resume_window_minutes"]))
        while self.resume_attempts and now - self.resume_attempts[0] > window:
            self.resume_attempts.popleft()
        return len(self.resume_attempts) >= int(self.config["max_resume_attempts"])

    def _record_attempt(self) -> None:
        self.resume_attempts.append(utc_now())

    def _attempt_cli_resume(self, snapshot: ThreadSnapshot) -> None:
        assert self.cli_path is not None
        if not snapshot.thread_id:
            return
        self._record_attempt()
        self.current_stop.last_attempt_at = utc_now()
        self.current_stop.resume_method = "cli"
        self.current_stop.waiting_for_confirmation = True
        self.current_stop.confirmation_started_at = utc_now()
        self.current_stop.confirmation_deadline = utc_now() + timedelta(seconds=CLI_CONFIRM_SECONDS)
        self.current_stop.confirmation_max_deadline = utc_now() + timedelta(seconds=MAX_CONFIRM_SECONDS)
        attempt_id = datetime.now().strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:8]
        stdout_path = ATTEMPT_DIR / f"{attempt_id}.stdout.log"
        stderr_path = ATTEMPT_DIR / f"{attempt_id}.stderr.log"
        command = [
            str(self.cli_path),
            "-C",
            str(DEFAULT_CWD),
            "-a",
            "never",
            "-s",
            "danger-full-access",
            "exec",
            "resume",
            snapshot.thread_id,
            "continue",
            "--skip-git-repo-check",
            "--json",
        ]
        self.current_stop.active_cli_command = command
        stdout_handle = stdout_path.open("w", encoding="utf-8")
        stderr_handle = stderr_path.open("w", encoding="utf-8")
        try:
            process = subprocess.Popen(
                command,
                stdout=stdout_handle,
                stderr=stderr_handle,
                cwd=str(DEFAULT_CWD),
                creationflags=PROCESS_CREATION_FLAGS,
                startupinfo=hidden_startupinfo(),
                close_fds=True,
            )
        except Exception as exc:
            stdout_handle.close()
            stderr_handle.close()
            self.current_stop.waiting_for_confirmation = False
            self.current_stop.cli_failures += 1
            self.last_resume_outcome = f"cli spawn failed: {exc}"
            log(self.last_resume_outcome)
            return
        stdout_handle.close()
        stderr_handle.close()
        self.current_stop.active_cli_pid = process.pid
        self.active_cli_pid = process.pid
        self.active_cli_command = list(command)
        self.last_action = "cli_resume"
        self.last_resume_at = utc_now()
        log(f"Spawned CLI resume for {snapshot.thread_id} with pid {process.pid}")

    def _attempt_app_resume(self, snapshot: ThreadSnapshot) -> None:
        if not snapshot.thread_id:
            return
        self._record_attempt()
        self.current_stop.last_attempt_at = utc_now()
        self.current_stop.resume_method = "app"
        self.current_stop.waiting_for_confirmation = True
        self.current_stop.confirmation_started_at = utc_now()
        self.current_stop.confirmation_deadline = utc_now() + timedelta(seconds=CLI_CONFIRM_SECONDS)
        self.current_stop.confirmation_max_deadline = utc_now() + timedelta(seconds=CLI_CONFIRM_SECONDS)
        try:
            focus_codex_and_send_continue(str(self.config["window_title"]), snapshot.thread_id)
            self.last_action = "app_continue"
            self.last_resume_at = utc_now()
            log(f"App continue sent for {snapshot.thread_id}")
        except Exception as exc:
            self.current_stop.waiting_for_confirmation = False
            self.last_resume_outcome = f"app continue failed: {exc}"
            self._notify(self.last_resume_outcome)

    def _attempt_foreground_fallback(self, snapshot: ThreadSnapshot) -> None:
        if not snapshot.thread_id:
            return
        self._record_attempt()
        self.current_stop.last_attempt_at = utc_now()
        self.current_stop.fallback_used = True
        self.current_stop.resume_method = "app"
        self.current_stop.waiting_for_confirmation = True
        self.current_stop.confirmation_started_at = utc_now()
        self.current_stop.confirmation_deadline = utc_now() + timedelta(seconds=CLI_CONFIRM_SECONDS)
        self.current_stop.confirmation_max_deadline = utc_now() + timedelta(seconds=CLI_CONFIRM_SECONDS)
        try:
            focus_codex_and_send_continue(str(self.config["window_title"]), snapshot.thread_id)
            self.last_action = "foreground_continue"
            self.last_resume_at = utc_now()
            self.cooling_down_until = utc_now() + timedelta(minutes=int(self.config["cooldown_minutes"]))
            log(f"Foreground fallback sent continue for {snapshot.thread_id}")
        except Exception as exc:
            self.current_stop.waiting_for_confirmation = False
            self.last_resume_outcome = f"foreground fallback failed: {exc}"
            self.cooling_down_until = utc_now() + timedelta(minutes=int(self.config["cooldown_minutes"]))
            self._notify(self.last_resume_outcome)

    def _refresh_confirmation(self, snapshot: ThreadSnapshot) -> None:
        if not self.current_stop or not self.current_stop.waiting_for_confirmation:
            return
        started_after_attempt = (
            snapshot.last_task_started_at is not None
            and self.current_stop.confirmation_started_at is not None
            and snapshot.last_task_started_at >= self.current_stop.confirmation_started_at
        )
        if started_after_attempt:
            self.current_stop.waiting_for_confirmation = False
            self.current_stop.active_cli_pid = None
            self.current_stop.active_cli_command = []
            self.current_stop.cli_failures = 0
            self.last_resume_outcome = "confirmed"
            log(f"Confirmed resume for {snapshot.thread_id}")
            return
        now = utc_now()
        if self.current_stop.active_cli_pid and pid_exists(self.current_stop.active_cli_pid):
            if self.current_stop.confirmation_max_deadline and now < self.current_stop.confirmation_max_deadline:
                return
        if self.current_stop.confirmation_deadline and now < self.current_stop.confirmation_deadline:
            return
        self.current_stop.waiting_for_confirmation = False
        if self.current_stop.resume_method == "cli" and self.current_stop.active_cli_pid:
            terminate_process(self.current_stop.active_cli_pid)
            log(f"Terminated stale CLI resume pid {self.current_stop.active_cli_pid} after confirmation timeout.")
            self.current_stop.active_cli_pid = None
            self.current_stop.active_cli_command = []
        if self.current_stop.resume_method == "cli":
            self.active_cli_pid = None
            self.active_cli_command = []
        if self.current_stop.resume_method == "app" or self.current_stop.fallback_used:
            self.last_resume_outcome = "fallback confirmation timed out"
            self._notify("App continue sent but no new task_started was observed.")
            return
        self.current_stop.cli_failures += 1
        self.last_resume_outcome = f"cli confirmation timed out ({self.current_stop.cli_failures}/{CLI_FAILURE_THRESHOLD})"
        log(self.last_resume_outcome)

    def _detect_stop(self, snapshot: ThreadSnapshot) -> dict[str, str] | None:
        if not snapshot.thread_id:
            return None
        detection_mode = str(self.config.get("stop_detection_mode", "task_complete_only"))
        in_flight = bool(
            snapshot.last_task_started_at
            and (
                snapshot.last_task_complete_at is None
                or snapshot.last_task_started_at > snapshot.last_task_complete_at
            )
        )
        if snapshot.last_task_complete_at and (
            snapshot.last_task_started_at is None or snapshot.last_task_complete_at >= snapshot.last_task_started_at
        ):
            stamp = dt_to_str(snapshot.last_task_complete_at) or "unknown"
            turn_id = snapshot.last_task_complete_turn_id or "unknown"
            return {"key": f"task_complete:{turn_id}:{stamp}", "reason": "task_complete"}
        if not is_codex_process_running() and snapshot.last_event_at:
            stamp = dt_to_str(snapshot.last_event_at) or "unknown"
            return {"key": f"process_missing:{snapshot.thread_id}:{stamp}", "reason": "process_missing"}
        if detection_mode == "task_complete_only":
            return None
        if in_flight and snapshot.last_event_at:
            idle_for = utc_now() - snapshot.last_event_at
            if idle_for >= timedelta(seconds=int(self.config["idle_stop_seconds"])):
                stamp = dt_to_str(snapshot.last_event_at) or "unknown"
                turn_id = snapshot.last_task_started_turn_id or "unknown"
                return {"key": f"idle:{turn_id}:{stamp}", "reason": "idle_timeout"}
        return None

    def _get_target_thread_id(self) -> str | None:
        data = read_json(GLOBAL_STATE_PATH, {})
        pinned = data.get("pinned-thread-ids") if isinstance(data, dict) else None
        if isinstance(pinned, list) and pinned:
            first = pinned[0]
            if isinstance(first, str) and first.strip():
                return first.strip()
        return None

    def _load_thread_record(self, thread_id: str | None) -> ThreadRecord | None:
        if not thread_id or not STATE_DB_PATH.exists():
            return None
        import sqlite3

        conn = sqlite3.connect(STATE_DB_PATH)
        conn.row_factory = sqlite3.Row
        try:
            cur = conn.cursor()
            cur.execute(
                """
                select id, rollout_path, source, cwd, title, sandbox_policy, approval_mode, updated_at
                from threads
                where id = ? and archived = 0
                limit 1
                """,
                (thread_id,),
            )
            row = cur.fetchone()
        finally:
            conn.close()
        if not row:
            return None
        return ThreadRecord(
            thread_id=str(row["id"]),
            rollout_path=str(row["rollout_path"]) if row["rollout_path"] else None,
            source=str(row["source"]) if row["source"] else None,
            cwd=str(row["cwd"]) if row["cwd"] else None,
            title=str(row["title"]) if row["title"] else None,
            sandbox_policy=str(row["sandbox_policy"]) if row["sandbox_policy"] else None,
            approval_mode=str(row["approval_mode"]) if row["approval_mode"] else None,
            updated_at=int(row["updated_at"]) if row["updated_at"] is not None else None,
        )

    def _load_recent_thread_record(self) -> ThreadRecord | None:
        if not STATE_DB_PATH.exists():
            return None
        import sqlite3

        conn = sqlite3.connect(STATE_DB_PATH)
        conn.row_factory = sqlite3.Row
        try:
            cur = conn.cursor()
            cur.execute(
                """
                select id, rollout_path, source, cwd, title, sandbox_policy, approval_mode, updated_at
                from threads
                where archived = 0
                order by updated_at desc
                limit 1
                """
            )
            row = cur.fetchone()
        finally:
            conn.close()
        if not row:
            return None
        return ThreadRecord(
            thread_id=str(row["id"]),
            rollout_path=str(row["rollout_path"]) if row["rollout_path"] else None,
            source=str(row["source"]) if row["source"] else None,
            cwd=str(row["cwd"]) if row["cwd"] else None,
            title=str(row["title"]) if row["title"] else None,
            sandbox_policy=str(row["sandbox_policy"]) if row["sandbox_policy"] else None,
            approval_mode=str(row["approval_mode"]) if row["approval_mode"] else None,
            updated_at=int(row["updated_at"]) if row["updated_at"] is not None else None,
        )

    def _select_target_thread(self) -> ThreadRecord | None:
        thread_scope = str(self.config.get("thread_scope", "pinned:first"))
        pinned_id = self._get_target_thread_id()
        pinned = self._load_thread_record(pinned_id)
        recent = self._load_recent_thread_record()
        if thread_scope == "foreground_recent_or_pinned":
            title = active_window_title()
            if title and str(self.config.get("window_title", "Codex")).lower() in title.lower() and recent:
                return recent
            if pinned:
                return pinned
            return recent
        return pinned or recent

    def _find_rollout_path(self, thread_id: str | None) -> Path | None:
        if not thread_id:
            return None
        sessions_dir = CODEX_HOME / "sessions"
        if not sessions_dir.exists():
            return None
        candidates = [
            path
            for path in sessions_dir.rglob(f"*{thread_id}.jsonl")
            if path.is_file() and ".bak-" not in path.name
        ]
        if not candidates:
            return None
        return max(candidates, key=lambda item: item.stat().st_mtime)

    def _process_control_commands(self) -> None:
        for path in sorted(CONTROL_DIR.glob("*.json")):
            payload = read_json(path, {})
            command = str(payload.get("command") or "").strip().lower()
            try:
                if command == "pause":
                    self._cancel_active_resume("pause")
                    self.paused = True
                    self.last_action = "pause"
                    log("Received pause command.")
                    self._notify("Watchdog paused.")
                    self._refresh_tray_menu()
                elif command == "resume":
                    self.paused = False
                    self.last_action = "resume"
                    log("Received resume command.")
                    self._notify("Watchdog resumed.")
                    self._refresh_tray_menu()
                elif command == "stop":
                    self._cancel_active_resume("stop")
                    self.last_action = "stop"
                    log("Received stop command.")
                    self.stop_requested = True
                    self._refresh_tray_menu()
            except Exception as exc:
                log(f"Failed to process control file {path}: {exc}")
            else:
                path.unlink(missing_ok=True)

    def _compute_status_name(self) -> str:
        if self.stop_requested:
            return "stopped"
        if self.paused:
            return "paused"
        if self.cooling_down_until and utc_now() < self.cooling_down_until:
            return "cooling_down"
        if self.current_stop and self.current_stop.waiting_for_confirmation and self.current_stop.fallback_used:
            return "fallback_pending"
        if str(self.config.get("resume_backend", "app-only")) == "app-only":
            return "running"
        if self.cli_path is None:
            return "cli_unavailable"
        return "running"

    def _state_payload(self, status: str, snapshot: ThreadSnapshot | None = None) -> dict[str, Any]:
        snapshot = snapshot or self.tracker.snapshot
        current_stop = asdict(self.current_stop) if self.current_stop else None
        if current_stop:
            for key in ("detected_at", "last_attempt_at", "confirmation_deadline", "confirmation_max_deadline", "confirmation_started_at"):
                current_stop[key] = dt_to_str(current_stop[key]) if current_stop[key] else None
        return {
            "version": self.state_version,
            "pid": os.getpid(),
            "status": status,
            "paused": self.paused,
            "monitor_url": self.monitor_url,
            "cli_path": str(self.cli_path) if self.cli_path else None,
            "cli_error": self.cli_error,
            "target_thread_id": snapshot.thread_id,
            "target_thread_title": self.target_record.title if self.target_record else None,
            "target_thread_sandbox_policy": self.target_record.sandbox_policy if self.target_record else None,
            "target_thread_source": self.target_record.source if self.target_record else None,
            "target_selection_mode": self.config.get("thread_scope"),
            "resume_backend": self.config.get("resume_backend"),
            "stop_detection_mode": self.config.get("stop_detection_mode"),
            "armed_thread_id": self.arm_thread_id,
            "armed_at": dt_to_str(self.arm_started_at),
            "armed_after_fresh_task": self.arm_fresh_task_seen,
            "rollout_path": snapshot.rollout_path,
            "last_event_at": dt_to_str(snapshot.last_event_at),
            "last_event_type": snapshot.last_event_type,
            "last_task_started_at": dt_to_str(snapshot.last_task_started_at),
            "last_task_started_turn_id": snapshot.last_task_started_turn_id,
            "last_task_complete_at": dt_to_str(snapshot.last_task_complete_at),
            "last_task_complete_turn_id": snapshot.last_task_complete_turn_id,
            "cooling_down_until": dt_to_str(self.cooling_down_until),
            "last_action": self.last_action,
            "last_resume_at": dt_to_str(self.last_resume_at),
            "last_resume_outcome": self.last_resume_outcome,
            "last_notification": self.last_notification,
            "resume_attempts_in_window": len(self.resume_attempts),
            "active_cli_pid": self.active_cli_pid,
            "active_cli_command": self.active_cli_command,
            "current_stop": current_stop,
            "updated_at": now_iso(),
        }

    def _write_state(self, status: str, snapshot: ThreadSnapshot | None = None) -> None:
        atomic_write_json(STATE_PATH, self._state_payload(status, snapshot=snapshot))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--service", action="store_true", help="Run the background watchdog service.")
    args = parser.parse_args()
    if not args.service:
        print("Use --service to run the Codex continue watchdog.")
        return 0
    return WatchdogService().run()


if __name__ == "__main__":
    raise SystemExit(main())

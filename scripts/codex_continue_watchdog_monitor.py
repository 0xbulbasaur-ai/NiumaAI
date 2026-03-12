from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Any


def configure_stdio() -> None:
    for stream_name in ("stdout", "stderr"):
        stream = getattr(sys, stream_name, None)
        if stream and hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")


def now_stamp() -> str:
    return datetime.now().strftime("%H:%M:%S")


def write_line(message: str) -> None:
    print(f"[{now_stamp()}] {message}", flush=True)


def read_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def normalize_monitor_url(raw: str | None) -> str:
    if not raw:
        return ""
    return raw.strip().rstrip("/")


def session_api_url(explicit_monitor_url: str, state: dict[str, Any] | None) -> str:
    if explicit_monitor_url:
        return normalize_monitor_url(explicit_monitor_url) + "/api/session"
    if state and state.get("monitor_url"):
        return normalize_monitor_url(str(state["monitor_url"])) + "/api/session"
    return ""


def fetch_session_payload(api_url: str) -> tuple[dict[str, Any] | None, str]:
    if not api_url:
        return None, "missing api url"
    request_url = f"{api_url}?t={time.time_ns()}"
    request = urllib.request.Request(
        request_url,
        headers={"Cache-Control": "no-store", "Pragma": "no-cache"},
    )
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            payload = response.read().decode("utf-8", errors="replace")
        return json.loads(payload), ""
    except urllib.error.URLError as exc:
        return None, str(exc.reason or exc)
    except Exception as exc:
        return None, str(exc)


def entry_key(entry: dict[str, Any]) -> str:
    return "\n".join(
        (
            str(entry.get("at") or ""),
            str(entry.get("kind") or ""),
            str(entry.get("text") or ""),
        )
    )


def tail_entries(entries: list[dict[str, Any]], count: int) -> list[dict[str, Any]]:
    if len(entries) <= count:
        return entries
    return entries[-count:]


def new_entries_since(
    entries: list[dict[str, Any]], previous_keys: list[str], initial_count: int
) -> tuple[list[dict[str, Any]], list[str], bool]:
    keys = [entry_key(entry) for entry in entries]
    if not previous_keys:
        return tail_entries(entries, initial_count), keys, False
    last_key = previous_keys[-1]
    try:
        last_index = len(keys) - 1 - keys[::-1].index(last_key)
    except ValueError:
        return tail_entries(entries, initial_count), keys, True
    if last_index >= len(entries) - 1:
        return [], keys, False
    return entries[last_index + 1 :], keys, False


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--state-path",
        default=str(Path.home() / ".codex" / "tmp" / "codex-continue-watchdog" / "state.json"),
    )
    parser.add_argument("--monitor-url", default="")
    parser.add_argument("--refresh-seconds", type=float, default=1.0)
    parser.add_argument("--initial-display-lines", type=int, default=48)
    parser.add_argument("--max-iterations", type=int, default=0)
    args = parser.parse_args()

    configure_stdio()
    state_path = Path(args.state_path)

    print("NiumaAI Session Monitor (WT)", flush=True)
    print("API-backed mode. Ctrl+C to close.", flush=True)
    print("", flush=True)

    last_thread_id = ""
    last_status = ""
    last_api_url = ""
    last_revision = ""
    last_entry_keys: list[str] = []
    state_unavailable = False
    api_unavailable = False
    last_api_error = ""
    iteration = 0

    try:
        while True:
            iteration += 1
            state = read_json(state_path)
            if state is None and not args.monitor_url:
                if not state_unavailable:
                    write_line("waiting for state.json...")
                    state_unavailable = True
                if args.max_iterations > 0 and iteration >= args.max_iterations:
                    break
                time.sleep(args.refresh_seconds)
                continue

            if state_unavailable:
                write_line("watchdog state loaded.")
                state_unavailable = False

            api_url = session_api_url(args.monitor_url, state)
            if not api_url:
                if not api_unavailable:
                    write_line("waiting for monitor API...")
                    api_unavailable = True
                if args.max_iterations > 0 and iteration >= args.max_iterations:
                    break
                time.sleep(args.refresh_seconds)
                continue

            if api_url != last_api_url:
                last_api_url = api_url
                last_revision = ""
                last_entry_keys = []
                write_line(f"monitor api: {api_url}")

            payload, error_text = fetch_session_payload(api_url)
            if payload is None:
                if not api_unavailable:
                    write_line("monitor API unavailable.")
                    if error_text:
                        write_line(f"api error: {error_text}")
                    api_unavailable = True
                last_api_error = error_text
                if args.max_iterations > 0 and iteration >= args.max_iterations:
                    break
                time.sleep(args.refresh_seconds)
                continue

            if api_unavailable:
                write_line("monitor API connected.")
                api_unavailable = False
            last_api_error = ""

            thread_id = str(payload.get("thread_id") or "")
            status = str(payload.get("status") or "")
            revision = str(payload.get("entries_revision") or "")
            entries = payload.get("entries") or []
            if not isinstance(entries, list):
                entries = []

            if thread_id != last_thread_id:
                last_thread_id = thread_id
                write_line(f"thread: {thread_id or 'none'}")

            if status != last_status:
                last_status = status
                write_line(f"status: {status or 'unknown'}")

            if revision != last_revision:
                fresh_entries, last_entry_keys, resynced = new_entries_since(
                    [entry for entry in entries if isinstance(entry, dict)],
                    last_entry_keys,
                    args.initial_display_lines,
                )
                if resynced:
                    write_line("resynced monitor tail.")
                for entry in fresh_entries:
                    text = str(entry.get("text") or "").strip()
                    if text:
                        print(text, flush=True)
                last_revision = revision

            if args.max_iterations > 0 and iteration >= args.max_iterations:
                break
            time.sleep(args.refresh_seconds)
    except KeyboardInterrupt:
        return 0

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

from __future__ import annotations

import os
import re
import sys
import threading
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

ANSI_RESET = "\x1b[0m"
TAG_COLOR_MAP = {
    "SYSTEM": "\x1b[36m",
    "AUTO": "\x1b[34m",
    "HEARTBEAT": "\x1b[2m",
    "GIT": "\x1b[33m",
    "ERROR": "\x1b[31m",
    "WARN": "\x1b[93m",
    "RECONNECT": "\x1b[93m",
    "CLI": "\x1b[96m",
    "CODEX-PHASE": "\x1b[96m",
    "CODEX-PROMPT": "\x1b[95m",
    "CODEX-RESP": "\x1b[92m",
    "CODEX-THINK": "\x1b[90m",
    "CODEX-META": "\x1b[90m",
    "CODEX-MCP": "\x1b[36m",
    "CODEX-WARN": "\x1b[93m",
    "CODEX-ERR": "\x1b[31m",
    "CODEX-EXEC": "\x1b[94m",
    "CODEX-STDOUT": "\x1b[37m",
    "CODEX-STDERR": "\x1b[31m",
    "INFO": "\x1b[37m",
}

CODEX_PHASE_TOKENS = {"user", "thinking", "codex", "exec", "assistant"}
CODEX_META_LINE_REGEXP = re.compile(
    r"^(workdir|model|provider|approval|sandbox|session id|reasoning effort|reasoning summaries):",
    re.IGNORECASE,
)
LOGS_DIR = Path(__file__).resolve().parent.parent / "logs"
_LOG_FILE_LOCK = threading.Lock()
_SCOPE_LOCK = threading.Lock()
_CURRENT_SCOPE = "SYSTEM"


@dataclass
class TaggedMessage:
    has_tag: bool
    tag: str
    body: str


@dataclass
class CodexStreamState:
    phase: str = ""


def _normalize_scope(scope: str) -> str:
    candidate = re.sub(r"[^a-zA-Z0-9_-]+", "_", str(scope or "").strip()).strip("_")
    if not candidate:
        return "SYSTEM"
    return candidate.upper()[:48]


@contextmanager
def log_scope(scope: str):
    global _CURRENT_SCOPE
    normalized = _normalize_scope(scope)
    with _SCOPE_LOCK:
        previous = _CURRENT_SCOPE
        _CURRENT_SCOPE = normalized
    try:
        yield
    finally:
        with _SCOPE_LOCK:
            _CURRENT_SCOPE = previous


def get_current_scope() -> str:
    with _SCOPE_LOCK:
        return _CURRENT_SCOPE


def _supports_ansi_color(stream: object) -> bool:
    return bool(getattr(stream, "isatty", lambda: False)()) and "NO_COLOR" not in os.environ


def _colorize(text: str, color_code: str | None, stream: object) -> str:
    if not color_code or not _supports_ansi_color(stream):
        return text
    return f"{color_code}{text}{ANSI_RESET}"


def parse_tagged_message(raw_message: str) -> TaggedMessage:
    message = str(raw_message or "")
    match = re.match(r"^\[([A-Z0-9-]+)\]\s*(.*)$", message)
    if not match:
        return TaggedMessage(has_tag=False, tag="INFO", body=message)
    return TaggedMessage(has_tag=True, tag=match.group(1), body=match.group(2) or "")


def format_auto_evolve_console_line(message: str, use_stderr: bool = False, scope: str | None = None) -> str:
    stream = sys.stderr if use_stderr else sys.stdout
    parsed = parse_tagged_message(message)
    resolved_scope = _normalize_scope(scope or get_current_scope())
    prefix = _colorize(f"[AE:{resolved_scope}]", "\x1b[1;36m", stream)

    if not parsed.has_tag:
        return f"{prefix} {parsed.body}"

    tag_color = TAG_COLOR_MAP.get(parsed.tag, TAG_COLOR_MAP["INFO"])
    colored_tag = _colorize(f"[{parsed.tag}]", tag_color, stream)
    return f"{prefix} {colored_tag} {parsed.body}"


def format_auto_evolve_plain_line(message: str, scope: str | None = None) -> str:
    parsed = parse_tagged_message(message)
    resolved_scope = _normalize_scope(scope or get_current_scope())
    prefix = f"[AE:{resolved_scope}]"
    if not parsed.has_tag:
        return f"{prefix} {parsed.body}"
    return f"{prefix} [{parsed.tag}] {parsed.body}"


def _append_local_log(line: str) -> None:
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    logfile = LOGS_DIR / f"auto-evolution-{datetime.now().strftime('%Y%m%d')}.log"
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with _LOG_FILE_LOCK:
        with logfile.open("a", encoding="utf-8") as file:
            file.write(f"{timestamp} {line}\n")


def log(message: str) -> None:
    scope = get_current_scope()
    print(format_auto_evolve_console_line(message, scope=scope))
    _append_local_log(format_auto_evolve_plain_line(message, scope=scope))


def log_error(message: str) -> None:
    scope = get_current_scope()
    print(format_auto_evolve_console_line(message, use_stderr=True, scope=scope), file=sys.stderr)
    _append_local_log(format_auto_evolve_plain_line(message, scope=scope))


def classify_codex_stream_line(line: str, source: str, state: CodexStreamState) -> str | None:
    content = str(line or "").strip()
    if not content:
        return None

    lower = content.lower()
    if lower in CODEX_PHASE_TOKENS:
        state.phase = lower
        return f"[CODEX-PHASE] {content}"

    if re.match(r"^OpenAI Codex v", content, flags=re.IGNORECASE):
        return f"[CODEX-META] {content}"
    if re.match(r"^-+$", content):
        return f"[CODEX-META] {content}"
    if CODEX_META_LINE_REGEXP.search(content):
        return f"[CODEX-META] {content}"

    if re.match(r"^mcp\b", content, flags=re.IGNORECASE):
        return f"[CODEX-MCP] {content}"

    if re.search(r"^reconnecting\.\.\.\s*\d+/\d+", content, flags=re.IGNORECASE):
        return f"[CODEX-WARN] {content}"
    if re.search(r"stream disconnected before completion", content, flags=re.IGNORECASE):
        return f"[CODEX-WARN] {content}"

    if state.phase == "user":
        return f"[CODEX-PROMPT] {content}"
    if state.phase == "thinking":
        return f"[CODEX-THINK] {content}"
    if state.phase in {"codex", "assistant"}:
        return f"[CODEX-RESP] {content}"
    if state.phase == "exec":
        return f"[CODEX-EXEC] {content}"

    if re.match(r"^(warn(ing)?|caution)\b", content, flags=re.IGNORECASE):
        return f"[CODEX-WARN] {content}"

    if re.match(r"^(error|fatal|exception)\b", content, flags=re.IGNORECASE):
        return f"[CODEX-ERR] {content}"

    if source == "stderr" and re.search(r"(\berror\b|\bfatal\b|\bexception\b)", content, flags=re.IGNORECASE):
        return f"[CODEX-ERR] {content}"

    return f"[CODEX-STDERR] {content}" if source == "stderr" else f"[CODEX-STDOUT] {content}"

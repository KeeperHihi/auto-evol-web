from __future__ import annotations

import os
import queue
import re
import shlex
import shutil
import subprocess
import threading
import time
from pathlib import Path

from auto_evolution.logging_utils import (
    CodexStreamState,
    classify_codex_stream_line,
    log,
    log_error,
)
from auto_evolution.models import AppConfig
from auto_evolution.text_tools import extract_tail, sanitize_commit_message

SESSION_ID_PATTERN = re.compile(r"session id:\s*([0-9a-f-]{36})", re.IGNORECASE)
HANDOFF_FILE_PATTERN = re.compile(
    r"^\s*HANDOFF_FILE\s*[:：]\s*(.+)$", re.IGNORECASE | re.MULTILINE
)
WORK_SUMMARY_PATTERNS = [
    re.compile(r"^\s*WORK_SUMMARY\s*[:：]\s*(.+)$", re.IGNORECASE | re.MULTILINE),
    re.compile(r"^\s*SUMMARY\s*[:：]\s*(.+)$", re.IGNORECASE | re.MULTILINE),
    re.compile(r"^\s*工作摘要\s*[:：]\s*(.+)$", re.IGNORECASE | re.MULTILINE),
]


def extract_codex_content_lines(output: str) -> list[str]:
    state = CodexStreamState()
    lines: list[str] = []
    for raw_line in str(output or "").splitlines():
        tagged = classify_codex_stream_line(raw_line, "stdout", state)
        if not tagged or "] " not in tagged:
            continue
        _, body = tagged.split("] ", 1)
        text = body.strip()
        if not text:
            continue
        if (
            tagged.startswith("[CODEX-RESP]")
            or tagged.startswith("[CODEX-EXEC]")
            or tagged.startswith("[CODEX-STDOUT]")
        ):
            lines.append(text)
    return lines


def _resolve_command_on_windows(command: str) -> str:
    # Prefer PATH lookup first, then try common executable suffixes and npm global bin.
    found = shutil.which(command)
    if found:
        return found

    base = str(command or "").strip().strip('"')
    if not base:
        return command

    for suffix in (".cmd", ".exe", ".bat"):
        candidate = f"{base}{suffix}" if not base.lower().endswith(suffix) else base
        found = shutil.which(candidate)
        if found:
            return found

    appdata = os.environ.get("APPDATA", "").strip()
    if appdata:
        npm_bin = Path(appdata) / "npm"
        for suffix in (".cmd", ".exe", ".bat"):
            candidate = npm_bin / f"{base}{suffix}"
            if candidate.exists():
                return str(candidate)

    return command


def resolve_codex_command(command: str) -> str:
    if os.name != "nt":
        return shutil.which(command) or command
    return _resolve_command_on_windows(command)


def extract_session_id(text: str) -> str:
    match = SESSION_ID_PATTERN.search(str(text or ""))
    return match.group(1) if match else ""


def extract_codex_commit_message(output: str) -> str:
    searchable_text = "\n".join(extract_codex_content_lines(output))
    patterns = [
        re.compile(r"^\s*COMMIT_MESSAGE\s*[:：]\s*(.+)$", re.IGNORECASE | re.MULTILINE),
        re.compile(r"^\s*提交信息\s*[:：]\s*(.+)$", re.IGNORECASE | re.MULTILINE),
        re.compile(r"^\s*commit\s+message\s*[:：]\s*(.+)$", re.IGNORECASE | re.MULTILINE),
    ]

    for pattern in patterns:
        match = pattern.search(searchable_text)
        if not match:
            continue
        normalized = sanitize_commit_message(match.group(1))
        if normalized:
            return normalized

    return ""


def extract_work_summary(output: str) -> str:
    searchable_text = "\n".join(extract_codex_content_lines(output))
    for pattern in WORK_SUMMARY_PATTERNS:
        match = pattern.search(searchable_text)
        if not match:
            continue
        summary = re.sub(r"\s+", " ", str(match.group(1) or "").strip())
        if summary:
            return extract_tail(summary, 320)
    return ""


def extract_handoff_files(output: str) -> list[str]:
    searchable_text = "\n".join(extract_codex_content_lines(output))
    candidates: list[str] = []
    for match in HANDOFF_FILE_PATTERN.findall(searchable_text):
        value = str(match or "").strip()
        if value:
            candidates.append(value)
    # Keep order and remove duplicates.
    seen: set[str] = set()
    deduped: list[str] = []
    for item in candidates:
        if item in seen:
            continue
        seen.add(item)
        deduped.append(item)
    return deduped


def extract_codex_response_tail(output: str, max_length: int = 2000) -> str:
    state = CodexStreamState()
    preferred_lines: list[str] = []
    fallback_lines: list[str] = []

    for raw_line in str(output or "").splitlines():
        tagged = classify_codex_stream_line(raw_line, "stdout", state)
        if not tagged:
            continue

        if "] " not in tagged:
            continue
        _, body = tagged.split("] ", 1)
        text = body.strip()
        if not text:
            continue

        if tagged.startswith("[CODEX-RESP]") or tagged.startswith("[CODEX-EXEC]"):
            preferred_lines.append(text)
        elif tagged.startswith("[CODEX-STDOUT]"):
            fallback_lines.append(text)

    if preferred_lines:
        return extract_tail("\n".join(preferred_lines), max_length)
    if fallback_lines:
        return extract_tail("\n".join(fallback_lines), max_length)
    return extract_tail(output, max_length)


def build_codex_args(config: AppConfig, workspace: Path, resume_session_id: str) -> list[str]:
    args = (
        ["exec", "resume", resume_session_id]
        if resume_session_id
        else ["exec", "--cd", str(workspace), "--color", "never"]
    )

    if config.codex.model:
        args.extend(["--model", config.codex.model])
    if config.codex.profile:
        args.extend(["--profile", config.codex.profile])
    if config.codex.dangerous_bypass:
        args.append("--dangerously-bypass-approvals-and-sandbox")

    args.extend(config.codex.extra_args)
    args.append("-")
    return args


def build_codex_env(config: AppConfig) -> dict[str, str]:
    env = os.environ.copy()
    if config.llm_access.api_key:
        env["LLM_ACCESS_API_KEY"] = config.llm_access.api_key
    return env


def _stream_reader(
    stream: object,
    source: str,
    line_queue: queue.Queue[tuple[str, str | None]],
) -> None:
    try:
        while True:
            line = stream.readline()
            if line == "":
                break
            normalized = line.rstrip("\r\n")
            line_queue.put((source, normalized))
    finally:
        line_queue.put((source, None))


def _terminate_subprocess(process: subprocess.Popen[str], grace_seconds: int = 3) -> None:
    if process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=grace_seconds)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=grace_seconds)


def run_codex_process_with_stream(
    command: str,
    args: list[str],
    workspace: Path,
    env: dict[str, str],
    prompt: str,
    timeout_seconds: int,
) -> tuple[int, str, str]:
    process = subprocess.Popen(
        [command, *args],
        cwd=str(workspace),
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        bufsize=1,
        env=env,
    )

    if process.stdin is None or process.stdout is None or process.stderr is None:
        raise RuntimeError("Codex 子进程管道初始化失败")

    try:
        process.stdin.write(prompt)
        process.stdin.flush()
    except BrokenPipeError:
        # 子进程提前退出时允许继续走后续错误处理。
        pass
    finally:
        process.stdin.close()

    line_queue: queue.Queue[tuple[str, str | None]] = queue.Queue()
    stdout_thread = threading.Thread(
        target=_stream_reader,
        args=(process.stdout, "stdout", line_queue),
        daemon=True,
    )
    stderr_thread = threading.Thread(
        target=_stream_reader,
        args=(process.stderr, "stderr", line_queue),
        daemon=True,
    )
    stdout_thread.start()
    stderr_thread.start()

    state = CodexStreamState()
    stdout_lines: list[str] = []
    stderr_lines: list[str] = []
    finished_streams: set[str] = set()
    start_at = time.monotonic()
    next_heartbeat_at = start_at + 15

    try:
        while True:
            now = time.monotonic()
            if now - start_at > timeout_seconds:
                _terminate_subprocess(process)
                raise subprocess.TimeoutExpired(
                    cmd=[command, *args],
                    timeout=timeout_seconds,
                    output="\n".join(stdout_lines),
                    stderr="\n".join(stderr_lines),
                )

            if now >= next_heartbeat_at:
                elapsed = int(now - start_at)
                log(f"[HEARTBEAT] Codex 正在执行中（{elapsed}s）...")
                next_heartbeat_at = now + 15

            try:
                source, payload = line_queue.get(timeout=0.2)
            except queue.Empty:
                if process.poll() is not None and len(finished_streams) >= 2:
                    break
                continue

            if payload is None:
                finished_streams.add(source)
                if process.poll() is not None and len(finished_streams) >= 2:
                    break
                continue

            if source == "stdout":
                stdout_lines.append(payload)
            else:
                stderr_lines.append(payload)

            tagged = classify_codex_stream_line(payload, source, state)
            if not tagged:
                continue
            if tagged.startswith("[CODEX-ERR]") or tagged.startswith("[CODEX-STDERR]"):
                log_error(tagged)
            else:
                log(tagged)
    except KeyboardInterrupt:
        _terminate_subprocess(process)
        log("[SYSTEM] 检测到 Ctrl+C，已中断当前 Codex 子进程")
        raise
    finally:
        stdout_thread.join(timeout=1)
        stderr_thread.join(timeout=1)

    return_code = process.wait()
    return return_code, "\n".join(stdout_lines), "\n".join(stderr_lines)


def run_codex_iteration(
    config: AppConfig,
    workspace: Path,
    prompt: str,
    incoming_session_id: str,
    require_work_summary: bool = False,
) -> tuple[str, str, str, str, list[str]]:
    command = resolve_codex_command(config.codex.command)
    timeout_seconds = config.codex.timeout_seconds
    retries = config.codex.retries
    session_id = incoming_session_id
    env = build_codex_env(config)

    for attempt in range(retries + 1):
        args = build_codex_args(config, workspace, session_id)
        rendered_cmd = " ".join([shlex.quote(command), *[shlex.quote(item) for item in args]])
        log(f"[SYSTEM] 启动命令（{attempt + 1}/{retries + 1}）：{rendered_cmd}")

        try:
            return_code, stdout_text, stderr_text = run_codex_process_with_stream(
                command=command,
                args=args,
                workspace=workspace,
                env=env,
                prompt=prompt,
                timeout_seconds=timeout_seconds,
            )
        except FileNotFoundError as exc:
            raise RuntimeError(
                "未找到 Codex 命令："
                f"{config.codex.command}（解析后：{command}）。"
                "请先确认 Codex CLI 可用，或在 config.json 的 codex.command 中填写可执行文件绝对路径。"
            ) from exc
        except subprocess.TimeoutExpired as exc:
            partial_stdout = getattr(exc, "stdout", None) or getattr(exc, "output", None) or ""
            partial_stderr = getattr(exc, "stderr", None) or ""
            combined = f"{partial_stdout}\n{partial_stderr}"
            observed = extract_session_id(combined)
            if observed:
                session_id = observed

            if attempt >= retries:
                raise RuntimeError(f"Codex 执行超时（{timeout_seconds} 秒），且重试次数已耗尽") from exc

            log(f"[RECONNECT] Codex 超时，2 秒后重试（{attempt + 1}/{retries}）")
            time.sleep(2)
            continue

        combined = f"{stdout_text}\n{stderr_text}"
        observed = extract_session_id(combined)
        if observed:
            session_id = observed

        commit_message = extract_codex_commit_message(combined)
        work_summary = extract_work_summary(combined)
        handoff_files = extract_handoff_files(combined)
        if return_code == 0:
            if not work_summary:
                work_summary = extract_tail(extract_codex_response_tail(combined, max_length=800), 320)
                if require_work_summary:
                    log(
                        "[WARN] 未检测到 `WORK_SUMMARY` 字段，已回退到响应摘要截断；建议在角色输出中补齐该字段"
                    )
            return (
                session_id,
                extract_codex_response_tail(combined),
                commit_message,
                work_summary,
                handoff_files,
            )

        if attempt >= retries:
            raise RuntimeError(
                f"Codex 执行失败（退出码 {return_code}）：{extract_tail(combined, 1500)}"
            )

        log(f"[RECONNECT] Codex 执行失败，2 秒后重试（{attempt + 1}/{retries}）")
        time.sleep(2)

    raise RuntimeError("重试循环异常结束")

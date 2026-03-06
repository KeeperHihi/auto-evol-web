#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import subprocess
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


APP_ROOT = Path(__file__).resolve().parent
CONFIG_FILE = APP_ROOT / "config.json"
DEFAULT_SYSTEM_PROMPT_FILE = "prompts/sys-prompt.md"
DEFAULT_USER_PROMPT_FILE = "prompts/user-prompt.md"
SESSION_ID_PATTERN = re.compile(r"session id:\s*([0-9a-f-]{36})", re.IGNORECASE)


@dataclass
class LlmAccessConfig:
    url: str = ""
    api_key: str = ""
    model: str = ""


@dataclass
class CodexConfig:
    command: str = "codex"
    model: str = "gpt-5.3-codex-xhigh"
    profile: str = ""
    dangerous_bypass: bool = True
    timeout_seconds: int = 1800
    retries: int = 3
    extra_args: list[str] = field(
        default_factory=lambda: ["-c", 'model_reasoning_effort="xhigh"']
    )
    dry_run: bool = False


@dataclass
class AppConfig:
    site_name: str = "demo"
    iterations: int = 3
    interval_seconds: int = 30
    append_iteration_context: bool = True
    system_prompt_file: str = DEFAULT_SYSTEM_PROMPT_FILE
    user_prompt_file: str = DEFAULT_USER_PROMPT_FILE
    llm_access: LlmAccessConfig = field(default_factory=LlmAccessConfig)
    codex: CodexConfig = field(default_factory=CodexConfig)


def strip_json_comments(content: str) -> str:
    result: list[str] = []
    in_string = False
    string_char = ""
    in_single_line_comment = False
    in_multi_line_comment = False

    i = 0
    while i < len(content):
        char = content[i]
        next_char = content[i + 1] if i + 1 < len(content) else ""

        if in_single_line_comment:
            if char == "\n":
                in_single_line_comment = False
                result.append(char)
            i += 1
            continue

        if in_multi_line_comment:
            if char == "*" and next_char == "/":
                in_multi_line_comment = False
                i += 2
                continue
            i += 1
            continue

        if in_string:
            result.append(char)
            if char == "\\" and next_char:
                result.append(next_char)
                i += 2
                continue
            if char == string_char:
                in_string = False
                string_char = ""
            i += 1
            continue

        if char in ('"', "'"):
            in_string = True
            string_char = char
            result.append(char)
            i += 1
            continue

        if char == "/" and next_char == "/":
            in_single_line_comment = True
            i += 2
            continue

        if char == "/" and next_char == "*":
            in_multi_line_comment = True
            i += 2
            continue

        result.append(char)
        i += 1

    return "".join(result)


def to_int(value: Any, default: int, minimum: int = 0) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        return max(minimum, default)
    return max(minimum, number)


def to_bool(value: Any, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        text = value.strip().lower()
        if text in {"1", "true", "yes", "y", "on"}:
            return True
        if text in {"0", "false", "no", "n", "off"}:
            return False
    return default


def to_str(value: Any, default: str = "") -> str:
    if value is None:
        return default
    text = str(value).strip()
    return text if text else default


def to_str_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if str(item).strip()]


def normalize_config(raw: dict[str, Any]) -> AppConfig:
    config = AppConfig()

    evolution = raw.get("evolution", {}) if isinstance(raw.get("evolution"), dict) else {}
    old_codex = raw.get("codex", {}) if isinstance(raw.get("codex"), dict) else {}
    old_llm = raw.get("llmAccess", {}) if isinstance(raw.get("llmAccess"), dict) else {}
    new_llm = raw.get("llmAccess", {}) if isinstance(raw.get("llmAccess"), dict) else {}

    # Backward compatibility with old JS config.
    if "gitBranch" in old_codex:
        config.site_name = to_str(old_codex.get("gitBranch"), config.site_name)
    if "defaultIterations" in evolution:
        config.iterations = to_int(evolution.get("defaultIterations"), config.iterations, minimum=1)
    if "intervalMs" in evolution:
        ms_value = to_int(evolution.get("intervalMs"), config.interval_seconds * 1000, minimum=0)
        config.interval_seconds = ms_value // 1000
    if "appendIterationContext" in evolution:
        config.append_iteration_context = to_bool(
            evolution.get("appendIterationContext"), config.append_iteration_context
        )
    if "systemPromptFile" in evolution:
        config.system_prompt_file = to_str(
            evolution.get("systemPromptFile"), config.system_prompt_file
        )
    if "command" in old_codex:
        config.codex.command = to_str(old_codex.get("command"), config.codex.command)
    if "model" in old_codex:
        config.codex.model = to_str(old_codex.get("model"), config.codex.model)
    if "profile" in old_codex:
        config.codex.profile = to_str(old_codex.get("profile"), config.codex.profile)
    if "dangerouslyBypassApprovalsAndSandbox" in old_codex:
        config.codex.dangerous_bypass = to_bool(
            old_codex.get("dangerouslyBypassApprovalsAndSandbox"), config.codex.dangerous_bypass
        )
    if "timeoutMs" in old_codex:
        timeout_ms = to_int(old_codex.get("timeoutMs"), config.codex.timeout_seconds * 1000, minimum=1000)
        config.codex.timeout_seconds = timeout_ms // 1000
    if "reconnectingRounds" in old_codex:
        config.codex.retries = to_int(old_codex.get("reconnectingRounds"), config.codex.retries, minimum=0)
    if "extraArgs" in old_codex:
        extra_args = to_str_list(old_codex.get("extraArgs"))
        if extra_args:
            config.codex.extra_args = extra_args
    if "dryRun" in old_codex:
        config.codex.dry_run = to_bool(old_codex.get("dryRun"), config.codex.dry_run)

    if old_llm:
        config.llm_access.url = to_str(old_llm.get("url"), config.llm_access.url)
        config.llm_access.api_key = to_str(old_llm.get("apiKey"), config.llm_access.api_key)
        config.llm_access.model = to_str(old_llm.get("model"), config.llm_access.model)

    # New compact config schema overrides backward-compatible values.
    if "siteName" in raw:
        config.site_name = to_str(raw.get("siteName"), config.site_name)
    if "iterations" in raw:
        config.iterations = to_int(raw.get("iterations"), config.iterations, minimum=1)
    if "intervalSeconds" in raw:
        config.interval_seconds = to_int(raw.get("intervalSeconds"), config.interval_seconds, minimum=0)
    if "appendIterationContext" in raw:
        config.append_iteration_context = to_bool(
            raw.get("appendIterationContext"), config.append_iteration_context
        )
    if "systemPromptFile" in raw:
        config.system_prompt_file = to_str(raw.get("systemPromptFile"), config.system_prompt_file)
    if "userPromptFile" in raw:
        config.user_prompt_file = to_str(raw.get("userPromptFile"), config.user_prompt_file)

    if new_llm:
        config.llm_access.url = to_str(new_llm.get("url"), config.llm_access.url)
        config.llm_access.api_key = to_str(new_llm.get("apiKey"), config.llm_access.api_key)
        config.llm_access.model = to_str(new_llm.get("model"), config.llm_access.model)

    new_codex = raw.get("codex", {}) if isinstance(raw.get("codex"), dict) else {}
    if new_codex:
        if "command" in new_codex:
            config.codex.command = to_str(new_codex.get("command"), config.codex.command)
        if "model" in new_codex:
            config.codex.model = to_str(new_codex.get("model"), config.codex.model)
        if "profile" in new_codex:
            config.codex.profile = to_str(new_codex.get("profile"), config.codex.profile)
        if "dangerouslyBypassApprovalsAndSandbox" in new_codex:
            config.codex.dangerous_bypass = to_bool(
                new_codex.get("dangerouslyBypassApprovalsAndSandbox"), config.codex.dangerous_bypass
            )
        if "timeoutSeconds" in new_codex:
            config.codex.timeout_seconds = to_int(
                new_codex.get("timeoutSeconds"), config.codex.timeout_seconds, minimum=1
            )
        if "retries" in new_codex:
            config.codex.retries = to_int(new_codex.get("retries"), config.codex.retries, minimum=0)
        if "extraArgs" in new_codex:
            extra_args = to_str_list(new_codex.get("extraArgs"))
            if extra_args:
                config.codex.extra_args = extra_args
        if "dryRun" in new_codex:
            config.codex.dry_run = to_bool(new_codex.get("dryRun"), config.codex.dry_run)

    config.iterations = max(1, config.iterations)
    config.interval_seconds = max(0, config.interval_seconds)
    config.codex.timeout_seconds = max(1, config.codex.timeout_seconds)
    config.codex.retries = max(0, config.codex.retries)
    config.site_name = config.site_name.strip()
    if not config.site_name:
        raise ValueError("siteName cannot be empty")
    return config


def load_config(config_file: Path) -> AppConfig:
    if not config_file.exists():
        raise FileNotFoundError(
            f"Config file not found: {config_file}. "
            "Copy config.template.json to config.json first."
        )
    raw_content = config_file.read_text(encoding="utf-8")
    try:
        parsed = json.loads(strip_json_comments(raw_content))
    except json.JSONDecodeError as exc:
        raise ValueError(f"config.json is invalid JSON: {exc}") from exc
    if not isinstance(parsed, dict):
        raise ValueError("config.json root must be an object")
    return normalize_config(parsed)


def resolve_path_from_root(path_value: str, field_name: str) -> Path:
    if not path_value:
        raise ValueError(f"{field_name} cannot be empty")

    candidate = Path(path_value)
    absolute = candidate.resolve() if candidate.is_absolute() else (APP_ROOT / candidate).resolve()
    root = APP_ROOT.resolve()

    if absolute != root and root not in absolute.parents:
        raise ValueError(f"{field_name} must stay inside project root")
    return absolute


def resolve_workspace(site_name: str) -> Path:
    webs_root = (APP_ROOT / "webs").resolve()
    webs_root.mkdir(parents=True, exist_ok=True)
    workspace = (webs_root / site_name).resolve()
    if workspace != webs_root and webs_root not in workspace.parents:
        raise ValueError("siteName must stay inside ./webs")
    if not workspace.exists() or not workspace.is_dir():
        raise FileNotFoundError(
            f"Website workspace not found: {workspace}\n"
            "Create your website repo under ./webs/<siteName> first."
        )
    return workspace


def is_git_repo(path: Path) -> bool:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--is-inside-work-tree"],
            cwd=str(path),
            capture_output=True,
            text=True,
            check=False,
        )
    except FileNotFoundError:
        return False
    return result.returncode == 0 and result.stdout.strip() == "true"


def read_text_file(path: Path, field_name: str) -> str:
    try:
        content = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise RuntimeError(f"Failed to read {field_name}: {exc}") from exc
    text = content.strip()
    if not text:
        raise ValueError(f"{field_name} is empty: {path}")
    return text


def build_llm_runtime_hint(config: LlmAccessConfig) -> str:
    if not (config.url and config.api_key and config.model):
        return ""
    return "\n".join(
        [
            "- Optional runtime LLM access:",
            f"  - url: {config.url}",
            f"  - model: {config.model}",
            "  - api_key_env: LLM_ACCESS_API_KEY",
        ]
    )


def render_system_prompt(template: str, llm_config: LlmAccessConfig) -> str:
    runtime_hint = build_llm_runtime_hint(llm_config)
    token = "{{LLM_RUNTIME_HINT}}"
    if token in template:
        rendered = template.replace(token, runtime_hint)
    else:
        rendered = f"{template.strip()}\n\n{runtime_hint}".strip() if runtime_hint else template.strip()
    return re.sub(r"\n{3,}", "\n\n", rendered).strip()


def extract_tail(text: str, max_length: int = 1200) -> str:
    if len(text) <= max_length:
        return text.strip()
    return f"...{text[-max_length:].strip()}"


def extract_session_id(text: str) -> str:
    match = SESSION_ID_PATTERN.search(text or "")
    return match.group(1) if match else ""


def get_prompt_from_file(path: Path) -> str:
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8").strip()


def ask_user_prompt() -> str:
    try:
        return input("Enter website direction prompt: ").strip()
    except EOFError:
        return ""


def build_iteration_prompt(
    system_prompt: str,
    user_prompt: str,
    iteration: int,
    total_iterations: int,
    previous_tail: str,
    append_context: bool,
) -> str:
    sections: list[str] = [
        "## System Prompt",
        system_prompt.strip(),
        "",
        "## User Goal",
        user_prompt.strip() or "None",
        "",
    ]

    if append_context:
        sections.extend(
            [
                "## Iteration Context",
                f"- round: {iteration}/{total_iterations}",
                f"- timestamp: {datetime.now(timezone.utc).isoformat()}",
            ]
        )
        if previous_tail:
            sections.extend(["- previous output tail:", previous_tail])
        sections.extend(
            [
                "- requirement: continue from current repo state and avoid repeating previous work.",
                "",
            ]
        )

    sections.extend(
        [
            "## Execution Requirements",
            "1. Analyze current code and pick one high-value, shippable upgrade.",
            "2. Directly modify files in the current repository.",
            "3. Run at least one meaningful validation command.",
            "4. End with: what changed, how it was validated, and next-step suggestion.",
            "5. If files changed, output one line: COMMIT_MESSAGE: <message>.",
        ]
    )

    return "\n".join(sections).strip()


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


def count_changed_files(workspace: Path) -> int:
    result = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=str(workspace),
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        return -1
    lines = [line for line in result.stdout.splitlines() if line.strip()]
    return len(lines)


def run_codex_iteration(
    config: AppConfig,
    workspace: Path,
    prompt: str,
    incoming_session_id: str,
) -> tuple[str, str]:
    command = config.codex.command
    timeout_seconds = config.codex.timeout_seconds
    retries = config.codex.retries
    session_id = incoming_session_id
    env = build_codex_env(config)

    for attempt in range(retries + 1):
        args = build_codex_args(config, workspace, session_id)
        rendered_cmd = " ".join([shlex.quote(command), *[shlex.quote(item) for item in args]])
        print(f"[SYSTEM] Running ({attempt + 1}/{retries + 1}): {rendered_cmd}")

        try:
            result = subprocess.run(
                [command, *args],
                cwd=str(workspace),
                input=prompt,
                capture_output=True,
                text=True,
                timeout=timeout_seconds,
                env=env,
                check=False,
            )
        except FileNotFoundError as exc:
            raise RuntimeError(
                f"Codex command not found: {command}. Ensure Codex CLI is installed."
            ) from exc
        except subprocess.TimeoutExpired as exc:
            partial_output = (exc.stdout or "") + "\n" + (exc.stderr or "")
            observed = extract_session_id(partial_output)
            if observed:
                session_id = observed
            if attempt >= retries:
                raise RuntimeError(
                    f"Codex timed out after {timeout_seconds}s and retries were exhausted."
                ) from exc
            print(f"[WARN] Codex timed out. Retrying in 2s ({attempt + 1}/{retries}).")
            time.sleep(2)
            continue

        combined = f"{result.stdout}\n{result.stderr}"
        observed = extract_session_id(combined)
        if observed:
            session_id = observed

        if result.stdout.strip():
            print("[CODEX-STDOUT]")
            print(result.stdout.rstrip())
        if result.stderr.strip():
            print("[CODEX-STDERR]", file=sys.stderr)
            print(result.stderr.rstrip(), file=sys.stderr)

        if result.returncode == 0:
            return session_id, extract_tail(combined)

        if attempt >= retries:
            raise RuntimeError(
                f"Codex failed with exit code {result.returncode}: {extract_tail(combined, 1200)}"
            )

        print(f"[WARN] Codex failed. Retrying in 2s ({attempt + 1}/{retries}).")
        time.sleep(2)

    raise RuntimeError("Unexpected retry loop termination")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Auto-Evolution Python runner for websites in ./webs/<siteName>"
    )
    parser.add_argument("--site", help="Override siteName from config.json")
    parser.add_argument(
        "--iterations",
        type=int,
        help="Override iterations from config.json",
    )
    parser.add_argument("--prompt", help="Direct user goal prompt (skip prompt file)")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Build prompts and iterate without calling Codex",
    )
    return parser.parse_args()


def resolve_user_prompt(cli_prompt: str | None, config: AppConfig) -> str:
    if cli_prompt and cli_prompt.strip():
        return cli_prompt.strip()

    prompt_file_path = resolve_path_from_root(config.user_prompt_file, "userPromptFile")
    from_file = get_prompt_from_file(prompt_file_path)
    if from_file:
        print(f"[SYSTEM] Loaded user prompt from: {prompt_file_path}")
        return from_file

    if sys.stdin.isatty():
        prompt = ask_user_prompt()
        if prompt:
            return prompt

    raise ValueError(
        f"Prompt is empty. Fill {prompt_file_path} or pass --prompt explicitly."
    )


def run() -> int:
    args = parse_args()
    config = load_config(CONFIG_FILE)

    if args.site:
        config.site_name = args.site.strip()
    if args.iterations is not None:
        config.iterations = max(1, int(args.iterations))

    workspace = resolve_workspace(config.site_name)
    if not is_git_repo(workspace):
        raise RuntimeError(
            f"{workspace} is not a git repository. "
            "Clone or initialize your website repo under ./webs/<siteName> first."
        )

    system_prompt_path = resolve_path_from_root(config.system_prompt_file, "systemPromptFile")
    system_prompt_template = read_text_file(system_prompt_path, "systemPromptFile")
    system_prompt = render_system_prompt(system_prompt_template, config.llm_access)
    user_prompt = resolve_user_prompt(args.prompt, config)

    dry_run = args.dry_run or config.codex.dry_run
    total_iterations = config.iterations

    print(f"[SYSTEM] Workspace: {workspace}")
    print(f"[SYSTEM] Iterations: {total_iterations}")
    print(f"[SYSTEM] Dry run: {dry_run}")
    print(f"[SYSTEM] System prompt file: {system_prompt_path}")
    print("[SYSTEM] Evolution loop started.")

    previous_tail = ""
    resume_session_id = ""

    for iteration in range(1, total_iterations + 1):
        print(f"[AUTO] Round {iteration}/{total_iterations} started.")
        full_prompt = build_iteration_prompt(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            iteration=iteration,
            total_iterations=total_iterations,
            previous_tail=previous_tail,
            append_context=config.append_iteration_context,
        )

        if dry_run:
            preview = extract_tail(full_prompt, 800)
            previous_tail = preview
            print("[DRY-RUN] Prompt preview tail:")
            print(preview)
        else:
            resume_session_id, previous_tail = run_codex_iteration(
                config=config,
                workspace=workspace,
                prompt=full_prompt,
                incoming_session_id=resume_session_id,
            )

        changed_count = count_changed_files(workspace)
        if changed_count >= 0:
            print(f"[AUTO] Round {iteration} completed. Changed files in repo: {changed_count}.")
        else:
            print(f"[AUTO] Round {iteration} completed.")

        if iteration < total_iterations and config.interval_seconds > 0:
            print(f"[AUTO] Sleeping {config.interval_seconds}s before next round.")
            time.sleep(config.interval_seconds)

    print(f"[SYSTEM] Evolution finished. Executed rounds: {total_iterations}.")
    return 0


def main() -> None:
    try:
        sys.exit(run())
    except Exception as exc:  # noqa: BLE001
        print(f"[ERROR] {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()

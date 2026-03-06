from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from auto_evolution.models import AppConfig


def strip_json_comments(content: str) -> str:
    result: list[str] = []
    in_string = False
    string_char = ""
    in_single_comment = False
    in_multi_comment = False

    i = 0
    while i < len(content):
        char = content[i]
        next_char = content[i + 1] if i + 1 < len(content) else ""

        if in_single_comment:
            if char == "\n":
                in_single_comment = False
                result.append(char)
            i += 1
            continue

        if in_multi_comment:
            if char == "*" and next_char == "/":
                in_multi_comment = False
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
            in_single_comment = True
            i += 2
            continue

        if char == "/" and next_char == "*":
            in_multi_comment = True
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


def normalize_branch_name(branch_name: str) -> str:
    return str(branch_name or "").strip().replace("refs/heads/", "")


def normalize_config(raw: dict[str, Any]) -> AppConfig:
    config = AppConfig()

    llm_access_raw = raw.get("llmAccess", {}) if isinstance(raw.get("llmAccess"), dict) else {}
    codex_raw = raw.get("codex", {}) if isinstance(raw.get("codex"), dict) else {}

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

    if llm_access_raw:
        config.llm_access.url = to_str(llm_access_raw.get("url"), config.llm_access.url)
        config.llm_access.api_key = to_str(llm_access_raw.get("apiKey"), config.llm_access.api_key)
        config.llm_access.model = to_str(llm_access_raw.get("model"), config.llm_access.model)

    if codex_raw:
        if "command" in codex_raw:
            config.codex.command = to_str(codex_raw.get("command"), config.codex.command)
        if "model" in codex_raw:
            config.codex.model = to_str(codex_raw.get("model"), config.codex.model)
        if "profile" in codex_raw:
            config.codex.profile = to_str(codex_raw.get("profile"), config.codex.profile)
        if "dangerouslyBypassApprovalsAndSandbox" in codex_raw:
            config.codex.dangerous_bypass = to_bool(
                codex_raw.get("dangerouslyBypassApprovalsAndSandbox"), config.codex.dangerous_bypass
            )
        if "timeoutSeconds" in codex_raw:
            config.codex.timeout_seconds = to_int(
                codex_raw.get("timeoutSeconds"), config.codex.timeout_seconds, minimum=1
            )
        if "retries" in codex_raw:
            config.codex.retries = to_int(codex_raw.get("retries"), config.codex.retries, minimum=0)
        if "extraArgs" in codex_raw:
            extra_args = to_str_list(codex_raw.get("extraArgs"))
            if extra_args:
                config.codex.extra_args = extra_args
        if "dryRun" in codex_raw:
            config.codex.dry_run = to_bool(codex_raw.get("dryRun"), config.codex.dry_run)
        if "autoGitInit" in codex_raw:
            config.codex.auto_git_init = to_bool(codex_raw.get("autoGitInit"), config.codex.auto_git_init)
        if "autoGitCommit" in codex_raw:
            config.codex.auto_git_commit = to_bool(
                codex_raw.get("autoGitCommit"), config.codex.auto_git_commit
            )
        if "autoGitPush" in codex_raw:
            config.codex.auto_git_push = to_bool(codex_raw.get("autoGitPush"), config.codex.auto_git_push)
        if "gitRemote" in codex_raw:
            config.codex.git_remote = to_str(codex_raw.get("gitRemote"), config.codex.git_remote)
        if "gitBranch" in codex_raw:
            config.codex.git_branch = to_str(codex_raw.get("gitBranch"), config.codex.git_branch)
        if "gitCommitPrefix" in codex_raw:
            config.codex.git_commit_prefix = to_str(
                codex_raw.get("gitCommitPrefix"), config.codex.git_commit_prefix
            )

    config.site_name = config.site_name.strip()
    config.iterations = max(1, config.iterations)
    config.interval_seconds = max(0, config.interval_seconds)
    config.codex.timeout_seconds = max(1, config.codex.timeout_seconds)
    config.codex.retries = max(0, config.codex.retries)
    config.codex.git_remote = config.codex.git_remote.strip() or "origin"
    config.codex.git_branch = normalize_branch_name(config.codex.git_branch) or "main"

    if not config.site_name:
        raise ValueError("siteName 不能为空")

    return config


def load_config(config_file: Path) -> AppConfig:
    if not config_file.exists():
        raise FileNotFoundError(
            f"未找到配置文件: {config_file}，请先从 config.template.json 复制生成 config.json"
        )

    content = config_file.read_text(encoding="utf-8")
    try:
        parsed = json.loads(strip_json_comments(content))
    except json.JSONDecodeError as exc:
        raise ValueError(f"config.json 格式错误: {exc}") from exc

    if not isinstance(parsed, dict):
        raise ValueError("config.json 根节点必须是对象")

    return normalize_config(parsed)


def resolve_local_path_from_root(app_root: Path, path_value: str, field_name: str) -> Path:
    if not path_value:
        raise ValueError(f"{field_name} 不能为空")

    candidate = Path(path_value)
    absolute = candidate.resolve() if candidate.is_absolute() else (app_root / candidate).resolve()
    root = app_root.resolve()

    if absolute != root and root not in absolute.parents:
        raise ValueError(f"{field_name} 必须位于项目根目录内部")

    return absolute

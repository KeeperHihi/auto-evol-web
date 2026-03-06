from __future__ import annotations

from dataclasses import dataclass, field


DEFAULT_SYSTEM_PROMPT_FILE = "prompts/sys-prompt.md"
DEFAULT_USER_PROMPT_FILE = "prompts/user-prompt.md"


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
    auto_git_init: bool = False
    auto_git_commit: bool = True
    auto_git_push: bool = True
    git_remote: str = "origin"
    git_branch: str = "main"
    git_commit_prefix: str = ""


@dataclass
class AppConfig:
    project_name: str = "demo"
    need_auto_upgrade: bool = True
    iterations: int = 3
    interval_seconds: int = 30
    append_iteration_context: bool = True
    system_prompt_file: str = DEFAULT_SYSTEM_PROMPT_FILE
    user_prompt_file: str = DEFAULT_USER_PROMPT_FILE
    llm_access: LlmAccessConfig = field(default_factory=LlmAccessConfig)
    codex: CodexConfig = field(default_factory=CodexConfig)

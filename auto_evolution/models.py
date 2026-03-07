from __future__ import annotations

from dataclasses import dataclass, field


DEFAULT_SYSTEM_PROMPT_FILE = "prompts/sys-prompt.md"
DEFAULT_USER_PROMPT_FILE = "prompts/user-prompt.md"


@dataclass
class AgentSpec:
    name: str
    role: str
    goal: str
    can_edit_code: bool = True
    system_prompt_file: str = ""
    system_prompt: str = ""


def default_multi_agent_specs() -> list[AgentSpec]:
    return [
        AgentSpec(
            name="innovation_analyst",
            role="Innovation Analyst",
            goal="澄清需求并产出可直接执行的实现方案。",
            can_edit_code=False,
            system_prompt_file="prompts/roles/architect.zh.md",
        ),
        AgentSpec(
            name="implementation_engineer",
            role="Implementation Engineer",
            goal="以最小且可上线的代码改动实现方案。",
            can_edit_code=True,
            system_prompt_file="prompts/roles/engineer.zh.md",
        ),
        AgentSpec(
            name="verification_repair_engineer",
            role="Verification & Repair Engineer",
            goal="验证结果并修复缺陷，直至满足需求。",
            can_edit_code=True,
            system_prompt_file="prompts/roles/qa_engineer.zh.md",
        ),
    ]


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
class MultiAgentConfig:
    enabled: bool = True
    max_context_chars: int = 2800
    agents: list[AgentSpec] = field(default_factory=default_multi_agent_specs)


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
    multi_agent: MultiAgentConfig = field(default_factory=MultiAgentConfig)
    codex: CodexConfig = field(default_factory=CodexConfig)

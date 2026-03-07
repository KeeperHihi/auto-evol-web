from __future__ import annotations

import re
import sys
from datetime import datetime, timezone
from pathlib import Path

from auto_evolution.config_loader import resolve_local_path_from_root
from auto_evolution.logging_utils import log
from auto_evolution.models import AgentSpec, AppConfig, LlmAccessConfig
from auto_evolution.text_tools import extract_tail


def read_text_file(path: Path, field_name: str, allow_empty: bool = False) -> str:
    try:
        content = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise RuntimeError(f"读取 {field_name} 失败: {exc}") from exc

    text = content.strip()
    if not allow_empty and not text:
        raise ValueError(f"{field_name} 为空: {path}")
    return text


def build_llm_runtime_hint(config: LlmAccessConfig) -> str:
    if not (config.url and config.api_key and config.model):
        return ""

    return "\n".join(
        [
            "- 可选外部模型调用（运行时注入）：",
            f"  - url: {config.url}",
            f"  - model: {config.model}",
            "  - api_key_env: LLM_ACCESS_API_KEY（只读环境变量，禁止输出明文）",
        ]
    )


def render_system_prompt(template: str, llm_config: LlmAccessConfig) -> str:
    runtime_hint = build_llm_runtime_hint(llm_config)
    token = "{{LLM_RUNTIME_HINT}}"
    rendered = template
    if token in rendered:
        rendered = rendered.replace(token, runtime_hint)
    elif runtime_hint:
        rendered = f"{rendered.strip()}\n\n{runtime_hint}".strip()

    return re.sub(r"\n{3,}", "\n\n", rendered).strip()


def ask_user_prompt() -> str:
    try:
        return input("请输入你的一句话项目创意：").strip()
    except EOFError:
        return ""


def resolve_user_prompt(app_root: Path, cli_prompt: str | None, config: AppConfig) -> str:
    if cli_prompt and cli_prompt.strip():
        return cli_prompt.strip()

    prompt_file = resolve_local_path_from_root(app_root, config.user_prompt_file, "userPromptFile")
    file_prompt = read_text_file(prompt_file, "userPromptFile", allow_empty=True)
    if file_prompt:
        log(f"[SYSTEM] 已从文件读取用户创意：{prompt_file}")
        return file_prompt

    if sys.stdin.isatty():
        interactive_prompt = ask_user_prompt()
        if interactive_prompt:
            return interactive_prompt

    raise ValueError(
        f"用户创意为空，请填写 {prompt_file}，或通过 --prompt 参数传入一句项目创意"
    )


def hydrate_agent_system_prompts(app_root: Path, config: AppConfig) -> None:
    for agent in config.multi_agent.agents:
        if agent.system_prompt.strip():
            continue
        if not agent.system_prompt_file.strip():
            continue

        field_name = f"multiAgent.agents[{agent.name}].systemPromptFile"
        try:
            file_path = resolve_local_path_from_root(app_root, agent.system_prompt_file, field_name)
            agent.system_prompt = read_text_file(file_path, field_name)
        except Exception as exc:
            log(f"[WARN] 读取角色提示词失败（{agent.name}）：{exc}；将使用精简默认约束继续执行")


def build_iteration_prompt(
    system_prompt: str,
    user_prompt: str,
    iteration: int,
    total_iterations: int,
    previous_tail: str,
    append_iteration_context: bool,
) -> str:
    sections: list[str] = [
        "【系统提示词】",
        system_prompt.strip(),
        "",
        "【用户创意】",
        user_prompt.strip(),
        "",
    ]

    if append_iteration_context:
        sections.extend(
            [
                "【本轮迭代上下文】",
                f"- 轮次：第 {iteration}/{total_iterations} 轮",
                f"- 时间：{datetime.now(timezone.utc).isoformat()}",
            ]
        )
        if previous_tail:
            sections.extend(["- 上轮输出摘要（截断）：", previous_tail])
        sections.extend(
            [
                "- 要求：基于当前仓库最新状态继续推进，不要重复上一轮内容。",
                "",
            ]
        )

    sections.extend(
        [
            "【执行要求】",
            "1. 先审查当前仓库状态，选出本轮最有价值且可交付的改进。",
            "2. 直接修改代码并确保项目可运行。",
            "3. 至少执行一条有效验证命令（例如构建、测试或语法检查）。",
            "4. 结尾说明：本轮改动、验证结果、下一轮建议。",
            "5. 若本轮有代码变更，请最后单独输出：COMMIT_MESSAGE: <提交信息>。",
        ]
    )

    return "\n".join(sections).strip()


def build_multi_agent_context(
    previous_iteration_tail: str,
    previous_agent_outputs: list[tuple[str, str, str]],
    previous_handoff_files: list[str],
    max_context_chars: int,
) -> str:
    blocks: list[str] = []

    if previous_iteration_tail:
        blocks.extend(
            [
                "【上一轮结论摘要】",
                extract_tail(previous_iteration_tail, max(320, max_context_chars // 2)),
            ]
        )

    if previous_agent_outputs:
        blocks.append("【前序角色摘要】")
        per_agent_budget = max(220, max_context_chars // max(2, len(previous_agent_outputs) + 1))
        for name, role, summary in previous_agent_outputs:
            blocks.append(f"- {name} ({role})")
            blocks.append(extract_tail(summary, per_agent_budget))

    if previous_handoff_files:
        blocks.append("【可读取交接文档】")
        for filename in previous_handoff_files[-8:]:
            blocks.append(f"- {filename}")

    if not blocks:
        return "无（你是本轮首个角色）"

    return extract_tail("\n".join(blocks), max_context_chars)


def build_multi_agent_prompt(
    system_prompt: str,
    user_prompt: str,
    iteration: int,
    total_iterations: int,
    append_iteration_context: bool,
    previous_iteration_tail: str,
    previous_agent_outputs: list[tuple[str, str, str]],
    previous_handoff_files: list[str],
    max_context_chars: int,
    agent: AgentSpec,
    agent_index: int,
    total_agents: int,
    handoff_root: Path,
    suggested_handoff_file: Path,
    require_commit_message: bool,
) -> str:
    can_edit = "是" if agent.can_edit_code else "否"
    context_text = build_multi_agent_context(
        previous_iteration_tail=previous_iteration_tail,
        previous_agent_outputs=previous_agent_outputs,
        previous_handoff_files=previous_handoff_files,
        max_context_chars=max_context_chars,
    )

    sections: list[str] = [
        "【系统规则】",
        system_prompt.strip(),
        "",
    ]

    if agent.system_prompt.strip():
        sections.extend(
            [
                "【角色规则】",
                agent.system_prompt.strip(),
                "",
            ]
        )

    sections.extend(
        [
        "【用户需求】",
        user_prompt.strip(),
        "",
        "【当前任务卡】",
        f"- 角色：{agent.name} ({agent.role})",
        f"- 顺位：{agent_index}/{total_agents}",
        f"- 本角色是否可改代码：{can_edit}",
        f"- 本角色目标：{agent.goal.strip()}",
        "",
        ]
    )

    if append_iteration_context:
        sections.extend(
            [
                "【轮次】",
                f"- 第 {iteration}/{total_iterations} 轮",
                "",
            ]
        )

    sections.extend(
        [
            "【上游输入】",
            context_text,
            "",
            "【执行约束】",
        ]
    )

    if agent.can_edit_code:
        sections.extend(
            [
                "1. 先阅读上游摘要/交接文档，再改代码。",
                "2. 只做和用户需求强相关的改动，不做无关重构。",
                "3. 至少执行一条有效验证命令。",
            ]
        )
    else:
        sections.extend(
            [
                "1. 不改业务代码。",
                "2. 必须在临时交接目录创建一份交接文档。",
                "3. 临时交接目录："
                f" {handoff_root}",
                "4. 建议交接文件名："
                f" {suggested_handoff_file}",
                "5. 交接文档只写分析结论、下一角色操作建议、风险点。",
            ]
        )

    output_protocol = [
        "",
        "【输出协议】",
        "1. 必须输出 `RESULT:` 段，简述本角色完成内容。",
        "2. 必须输出 `WORK_SUMMARY: <一句话摘要>`（单行，供后续角色直接读取）。",
        "3. 必须输出 `NEXT_HINT:` 段，给下一角色明确指令。",
    ]
    if agent.can_edit_code:
        output_protocol.append("4. 若写了交接文档，必须额外输出：`HANDOFF_FILE: <文件路径>`。")
    else:
        output_protocol.append("4. 必须输出：`HANDOFF_FILE: <文件路径>`。")

    sections.extend(output_protocol)
    if require_commit_message:
        sections.append(
            "5. 若有代码改动，必须额外输出：`COMMIT_MESSAGE: <提交信息>`。"
        )

    return "\n".join(sections).strip()

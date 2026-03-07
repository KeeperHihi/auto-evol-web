from __future__ import annotations

import re
import time
from dataclasses import dataclass
from pathlib import Path

from auto_evolution.codex_runner import run_codex_iteration
from auto_evolution.config_loader import (
    load_config,
    normalize_branch_name,
    resolve_local_path_with_template_fallback,
)
from auto_evolution.git_tools import (
    commit_and_push_changes,
    count_changed_files,
    ensure_branch_ready,
    ensure_project_is_latest,
    ensure_remote_ready,
    ensure_workspace_is_git_repo,
    inspect_workspace_state,
    prepare_workspace_with_auto_git_init,
    resolve_workspace,
)
from auto_evolution.logging_utils import log, log_scope
from auto_evolution.models import AppConfig
from auto_evolution.paths import APP_ROOT, CONFIG_FILE
from auto_evolution.prompt_tools import (
    build_iteration_prompt,
    build_multi_agent_prompt,
    hydrate_agent_system_prompts,
    read_text_file,
    read_user_temp_prompt,
    render_system_prompt,
    resolve_user_prompt,
)
from auto_evolution.text_tools import extract_tail

TEMP_PROMPT_DONE_IDS_PATTERN = re.compile(
    r"^\s*TEMP_PROMPT_DONE_IDS\s*[:：]\s*(.+)$",
    re.IGNORECASE | re.MULTILINE,
)
TEMP_PROMPT_ITEM_PATTERN = re.compile(r"(?m)^[ \t]*(\d+)[\.\)\）、]\s+")


@dataclass
class AgentTurnResult:
    agent_name: str
    role: str
    work_summary: str
    output_tail: str
    commit_message: str
    handoff_files: list[str]


class EvolutionInterrupted(RuntimeError):
    def __init__(self, workspace: Path | None):
        super().__init__("检测到用户中断（Ctrl+C）")
        self.workspace = workspace


def get_handoff_root(workspace: Path, iteration: int) -> Path:
    return workspace / ".git" / "auto-evolution-handoffs" / f"iter-{iteration:03d}"


def normalize_handoff_files(
    workspace: Path,
    handoff_root: Path,
    raw_handoff_files: list[str],
) -> list[str]:
    root = handoff_root.resolve()
    normalized: list[str] = []
    seen: set[str] = set()
    for item in raw_handoff_files:
        candidate = Path(str(item or "").strip().strip('"').strip("'"))
        if not str(candidate):
            continue
        absolute = candidate if candidate.is_absolute() else (workspace / candidate)
        resolved = absolute.resolve()
        if resolved != root and root not in resolved.parents:
            continue
        if not resolved.exists() or not resolved.is_file():
            continue
        relative = str(resolved.relative_to(workspace))
        if relative in seen:
            continue
        seen.add(relative)
        normalized.append(relative)
    return normalized


def summarize_multi_agent_results(
    turn_results: list[AgentTurnResult],
    max_context_chars: int,
) -> str:
    if not turn_results:
        return ""

    per_agent_budget = max(260, max_context_chars // max(2, len(turn_results) + 1))
    lines: list[str] = []
    for result in turn_results:
        lines.append(f"[{result.agent_name} | {result.role}]")
        summary_text = result.work_summary.strip() or extract_tail(result.output_tail, per_agent_budget)
        lines.append(summary_text)
        for handoff_file in result.handoff_files:
            lines.append(f"HANDOFF_FILE: {handoff_file}")

    return extract_tail("\n".join(lines), max_context_chars)


def extract_temp_prompt_done_ids(output_tail: str) -> list[int]:
    match = TEMP_PROMPT_DONE_IDS_PATTERN.search(str(output_tail or ""))
    if not match:
        return []

    value = str(match.group(1) or "").strip()
    if not value:
        return []
    if value.upper() in {"NONE", "N/A", "NA"} or value in {"无", "无完成项", "没有"}:
        return []

    ids: list[int] = []
    seen: set[int] = set()
    for token in re.split(r"[,\s，、]+", value):
        if not token:
            continue
        if not token.isdigit():
            continue
        number = int(token)
        if number <= 0 or number in seen:
            continue
        seen.add(number)
        ids.append(number)
    return ids


def prune_user_temp_prompt_completed_items(path: Path, done_ids: list[int]) -> tuple[int, int]:
    if not done_ids:
        return 0, 0
    if not path.exists():
        return 0, 0

    raw_text = path.read_text(encoding="utf-8")
    matches = list(TEMP_PROMPT_ITEM_PATTERN.finditer(raw_text))
    if not matches:
        return 0, 0

    done_set = {item for item in done_ids if item > 0}
    if not done_set:
        return 0, len(matches)

    prefix = raw_text[: matches[0].start()]
    kept_blocks: list[str] = []
    removed_count = 0
    remaining_count = 0

    for idx, match in enumerate(matches):
        start = match.start()
        end = matches[idx + 1].start() if idx + 1 < len(matches) else len(raw_text)
        block = raw_text[start:end]
        item_id = int(match.group(1))
        if item_id in done_set:
            removed_count += 1
            continue
        kept_blocks.append(block)
        remaining_count += 1

    if removed_count <= 0:
        return 0, len(matches)

    new_text = ""
    if kept_blocks:
        new_text = prefix + "".join(kept_blocks)
    path.write_text(new_text, encoding="utf-8")
    return removed_count, remaining_count


def run_single_agent_round(
    *,
    system_prompt: str,
    user_prompt: str,
    iteration: int,
    total_iterations: int,
    previous_tail: str,
    append_iteration_context: bool,
    dry_run: bool,
    config: AppConfig,
    workspace: Path,
    resume_session_id: str,
) -> tuple[str, str, str]:
    prompt = build_iteration_prompt(
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        iteration=iteration,
        total_iterations=total_iterations,
        previous_tail=previous_tail,
        append_iteration_context=append_iteration_context,
    )

    if dry_run:
        preview = extract_tail(prompt, 900)
        log("[AUTO] 演练模式：输出本轮提示词摘要")
        for line in preview.splitlines():
            log(f"[INFO] {line}")
        return resume_session_id, preview, ""

    with log_scope("single_agent"):
        session_id, output_tail, commit_message, _, _ = run_codex_iteration(
            config=config,
            workspace=workspace,
            prompt=prompt,
            incoming_session_id=resume_session_id,
            require_work_summary=False,
        )
    return session_id, output_tail, commit_message


def run_multi_agent_round(
    *,
    system_prompt: str,
    user_prompt: str,
    iteration: int,
    total_iterations: int,
    previous_tail: str,
    append_iteration_context: bool,
    dry_run: bool,
    config: AppConfig,
    workspace: Path,
    agent_session_ids: dict[str, str],
    user_temp_prompt: str,
    user_temp_prompt_path: Path,
) -> tuple[str, str]:
    total_agents = len(config.multi_agent.agents)
    turn_results: list[AgentTurnResult] = []
    latest_commit_message = ""
    handoff_root = get_handoff_root(workspace, iteration)
    if not dry_run:
        handoff_root.mkdir(parents=True, exist_ok=True)

    for index, agent in enumerate(config.multi_agent.agents, start=1):
        current_user_temp_prompt = (
            read_text_file(
                user_temp_prompt_path,
                "userTempPromptFile",
                allow_empty=True,
            )
            if user_temp_prompt_path.exists()
            else user_temp_prompt
        )
        previous_handoff_files = [
            filename for result in turn_results for filename in result.handoff_files
        ]
        suggested_handoff_file = handoff_root / f"{index:02d}_{agent.name}.md"
        prompt = build_multi_agent_prompt(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            iteration=iteration,
            total_iterations=total_iterations,
            append_iteration_context=append_iteration_context,
            previous_iteration_tail=previous_tail,
            previous_agent_outputs=[
                (item.agent_name, item.role, item.work_summary or item.output_tail)
                for item in turn_results
            ],
            previous_handoff_files=previous_handoff_files,
            max_context_chars=config.multi_agent.max_context_chars,
            agent=agent,
            agent_index=index,
            total_agents=total_agents,
            handoff_root=handoff_root,
            suggested_handoff_file=suggested_handoff_file,
            require_commit_message=agent.can_edit_code and index == total_agents,
            user_temp_prompt=current_user_temp_prompt,
            user_temp_prompt_path=user_temp_prompt_path,
        )
        with log_scope(agent.name):
            log(f"[AUTO] Agent {index}/{total_agents} 开始：{agent.name} ({agent.role})")

            if dry_run:
                preview = extract_tail(prompt, 700)
                for line in preview.splitlines():
                    log(f"[INFO] [{agent.name}] {line}")
                turn_results.append(
                    AgentTurnResult(
                        agent_name=agent.name,
                        role=agent.role,
                        work_summary=f"[DRY-RUN] {agent.name} summary unavailable.",
                        output_tail=f"[DRY-RUN] {agent.name} completed prompt preview without Codex execution.",
                        commit_message="",
                        handoff_files=[],
                    )
                )
                log(f"[AUTO] Agent {agent.name} 演练完成")
                continue

            incoming_session_id = agent_session_ids.get(agent.name, "")
            session_id, output_tail, commit_message, work_summary, raw_handoff_files = run_codex_iteration(
                config=config,
                workspace=workspace,
                prompt=prompt,
                incoming_session_id=incoming_session_id,
                require_work_summary=True,
            )
            if session_id:
                agent_session_ids[agent.name] = session_id
            if commit_message:
                latest_commit_message = commit_message

            handoff_files = normalize_handoff_files(
                workspace=workspace,
                handoff_root=handoff_root,
                raw_handoff_files=raw_handoff_files,
            )

            turn_results.append(
                AgentTurnResult(
                    agent_name=agent.name,
                    role=agent.role,
                    work_summary=work_summary,
                    output_tail=output_tail,
                    commit_message=commit_message,
                    handoff_files=handoff_files,
                )
            )
            if handoff_files:
                log(f"[AUTO] Agent {agent.name} 已产出交接文档：{', '.join(handoff_files)}")

            if current_user_temp_prompt.strip() and index == total_agents:
                done_ids = extract_temp_prompt_done_ids(output_tail)
                if not done_ids:
                    log("[WARN] 第三角色未给出已完成条目编号，临时需求文件保持不变")
                else:
                    removed_count, remaining_count = prune_user_temp_prompt_completed_items(
                        user_temp_prompt_path,
                        done_ids,
                    )
                    if removed_count > 0:
                        log(
                            "[AUTO] 第三角色已移除临时需求完成条目："
                            f"{done_ids}；剩余 {remaining_count} 条"
                        )
                    else:
                        log(
                            "[WARN] 第三角色给出的完成编号未匹配到有效条目，临时需求文件保持不变"
                        )
            log(f"[AUTO] Agent {agent.name} 完成")

    return (
        summarize_multi_agent_results(turn_results, config.multi_agent.max_context_chars),
        latest_commit_message,
    )


def run_evolution(
    project_override: str | None,
    iterations_override: int | None,
    prompt_override: str | None,
    dry_run_override: bool,
) -> int:
    workspace: Path | None = None
    try:
        config = load_config(CONFIG_FILE)
        if config.need_auto_upgrade:
            ensure_project_is_latest(APP_ROOT, remote_name="origin", branch_name="main")
        else:
            log("[GIT] needAutoUpgrade=false，跳过框架仓库更新检查")

        if project_override:
            config.project_name = project_override.strip()
        if iterations_override is not None:
            config.iterations = max(1, int(iterations_override))

        dry_run = dry_run_override or config.codex.dry_run
        if dry_run:
            workspace = resolve_workspace(APP_ROOT, config.project_name)
            ensure_workspace_is_git_repo(workspace)
            if config.codex.auto_git_init:
                log("[GIT] dry-run 模式下跳过 autoGitInit，仅校验本地仓库状态")
        else:
            if config.codex.auto_git_init:
                log("[GIT] autoGitInit=true，启用自动仓库初始化流程")
                workspace = prepare_workspace_with_auto_git_init(APP_ROOT, config)
            else:
                workspace = resolve_workspace(APP_ROOT, config.project_name)
                ensure_workspace_is_git_repo(workspace)

        system_prompt_path = resolve_local_path_with_template_fallback(
            APP_ROOT, config.system_prompt_file, "systemPromptFile"
        )
        system_prompt_template = read_text_file(system_prompt_path, "systemPromptFile")
        system_prompt = render_system_prompt(system_prompt_template, config.llm_access)

        user_prompt = resolve_user_prompt(APP_ROOT, prompt_override, config)
        user_temp_prompt_path, _ = read_user_temp_prompt(APP_ROOT)
        hydrate_agent_system_prompts(APP_ROOT, config)

        total_iterations = config.iterations

        log(f"[SYSTEM] 目标项目仓库目录：{workspace}")
        log(f"[SYSTEM] 迭代轮次：{total_iterations}")
        log(f"[SYSTEM] 演练模式：{dry_run}")
        if config.multi_agent.enabled and config.multi_agent.agents:
            log(f"[SYSTEM] 执行模式：multi-agent（{len(config.multi_agent.agents)} 个角色）")
        else:
            log("[SYSTEM] 执行模式：single-agent")

        if config.codex.auto_git_push and not config.codex.auto_git_commit:
            raise ValueError("配置错误：autoGitPush=true 时必须同时设置 autoGitCommit=true")

        target_branch = normalize_branch_name(config.codex.git_branch)
        if dry_run:
            log(f"[GIT] dry-run 模式下跳过分支切换与远端检查（目标分支：{target_branch}）")
        else:
            ensure_branch_ready(workspace, target_branch)
            if config.codex.auto_git_push:
                ensure_remote_ready(workspace, config.codex.git_remote)

        workspace_state = inspect_workspace_state(workspace)
        if workspace_state == "empty":
            log("[SYSTEM] 检测到空仓库，将从 0 开始生成项目")
        else:
            log("[SYSTEM] 检测到仓库已有内容，将在现有基础上继续进化")

        previous_tail = ""
        single_agent_session_id = ""
        agent_session_ids: dict[str, str] = {}
        use_multi_agent = bool(config.multi_agent.enabled and config.multi_agent.agents)

        for iteration in range(1, total_iterations + 1):
            _, user_temp_prompt = read_user_temp_prompt(APP_ROOT)
            log(f"[AUTO] 第 {iteration}/{total_iterations} 轮开始")
            if use_multi_agent and user_temp_prompt.strip():
                log("[AUTO] 检测到 user-temp-prompt.md 非空：本轮将以最高优先级处理临时需求")
            codex_commit_message = ""

            if use_multi_agent:
                previous_tail, codex_commit_message = run_multi_agent_round(
                    system_prompt=system_prompt,
                    user_prompt=user_prompt,
                    iteration=iteration,
                    total_iterations=total_iterations,
                    previous_tail=previous_tail,
                    append_iteration_context=config.append_iteration_context,
                    dry_run=dry_run,
                    config=config,
                    workspace=workspace,
                    agent_session_ids=agent_session_ids,
                    user_temp_prompt=user_temp_prompt,
                    user_temp_prompt_path=user_temp_prompt_path,
                )
            else:
                single_agent_session_id, previous_tail, codex_commit_message = run_single_agent_round(
                    system_prompt=system_prompt,
                    user_prompt=user_prompt,
                    iteration=iteration,
                    total_iterations=total_iterations,
                    previous_tail=previous_tail,
                    append_iteration_context=config.append_iteration_context,
                    dry_run=dry_run,
                    config=config,
                    workspace=workspace,
                    resume_session_id=single_agent_session_id,
                )

            if not dry_run:
                commit_and_push_changes(
                    config=config,
                    workspace=workspace,
                    codex_message=codex_commit_message,
                    iteration=iteration,
                )

            changed_count = count_changed_files(workspace)
            if changed_count >= 0:
                log(f"[AUTO] 第 {iteration} 轮完成，当前仓库未提交文件数：{changed_count}")
            else:
                log(f"[AUTO] 第 {iteration} 轮完成")

            if iteration < total_iterations and config.interval_seconds > 0:
                log(f"[AUTO] 等待 {config.interval_seconds} 秒后进入下一轮")
                time.sleep(config.interval_seconds)

        log(f"[SYSTEM] 进化结束，共执行 {total_iterations} 轮")
        return 0
    except KeyboardInterrupt as exc:
        raise EvolutionInterrupted(workspace=workspace) from exc

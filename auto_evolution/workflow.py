from __future__ import annotations

import time

from auto_evolution.codex_runner import run_codex_iteration
from auto_evolution.config_loader import (
    load_config,
    normalize_branch_name,
    resolve_local_path_from_root,
)
from auto_evolution.git_tools import (
    commit_and_push_changes,
    count_changed_files,
    ensure_branch_ready,
    ensure_remote_ready,
    ensure_workspace_is_git_repo,
    inspect_workspace_state,
    prepare_workspace_with_auto_git_init,
    resolve_workspace,
)
from auto_evolution.logging_utils import log
from auto_evolution.paths import APP_ROOT, CONFIG_FILE
from auto_evolution.prompt_tools import (
    build_iteration_prompt,
    read_text_file,
    render_system_prompt,
    resolve_user_prompt,
)
from auto_evolution.text_tools import extract_tail


def run_evolution(
    site_override: str | None,
    iterations_override: int | None,
    prompt_override: str | None,
    dry_run_override: bool,
) -> int:
    config = load_config(CONFIG_FILE)

    if site_override:
        config.site_name = site_override.strip()
    if iterations_override is not None:
        config.iterations = max(1, int(iterations_override))

    dry_run = dry_run_override or config.codex.dry_run
    if dry_run:
        workspace = resolve_workspace(APP_ROOT, config.site_name)
        ensure_workspace_is_git_repo(workspace)
        if config.codex.auto_git_init:
            log("[GIT] dry-run 模式下跳过 autoGitInit，仅校验本地仓库状态")
    else:
        if config.codex.auto_git_init:
            log("[GIT] autoGitInit=true，启用自动仓库初始化流程")
            workspace = prepare_workspace_with_auto_git_init(APP_ROOT, config)
        else:
            workspace = resolve_workspace(APP_ROOT, config.site_name)
            ensure_workspace_is_git_repo(workspace)

    system_prompt_path = resolve_local_path_from_root(
        APP_ROOT, config.system_prompt_file, "systemPromptFile"
    )
    system_prompt_template = read_text_file(system_prompt_path, "systemPromptFile")
    system_prompt = render_system_prompt(system_prompt_template, config.llm_access)

    user_prompt = resolve_user_prompt(APP_ROOT, prompt_override, config)

    total_iterations = config.iterations

    log(f"[SYSTEM] 目标站点目录：{workspace}")
    log(f"[SYSTEM] 迭代轮次：{total_iterations}")
    log(f"[SYSTEM] 演练模式：{dry_run}")

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
        log("[SYSTEM] 检测到空仓库，将从 0 开始生成网站")
    else:
        log("[SYSTEM] 检测到仓库已有内容，将在现有基础上继续进化")

    previous_tail = ""
    resume_session_id = ""

    for iteration in range(1, total_iterations + 1):
        log(f"[AUTO] 第 {iteration}/{total_iterations} 轮开始")
        prompt = build_iteration_prompt(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            iteration=iteration,
            total_iterations=total_iterations,
            previous_tail=previous_tail,
            append_iteration_context=config.append_iteration_context,
        )

        codex_commit_message = ""
        if dry_run:
            preview = extract_tail(prompt, 800)
            previous_tail = preview
            log("[AUTO] 演练模式：输出本轮提示词摘要")
            for line in preview.splitlines():
                log(f"[INFO] {line}")
        else:
            resume_session_id, previous_tail, codex_commit_message = run_codex_iteration(
                config=config,
                workspace=workspace,
                prompt=prompt,
                incoming_session_id=resume_session_id,
            )
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

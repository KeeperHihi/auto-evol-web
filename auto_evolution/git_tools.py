from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from auto_evolution.config_loader import normalize_branch_name
from auto_evolution.logging_utils import log
from auto_evolution.models import AppConfig
from auto_evolution.text_tools import extract_tail, sanitize_commit_message


def run_git(workspace: Path, args: list[str], timeout_seconds: int = 60) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            ["git", *args],
            cwd=str(workspace),
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            check=False,
        )
    except FileNotFoundError as exc:
        raise RuntimeError("未找到 git 命令，请先安装 git") from exc


def run_command(
    command: list[str],
    cwd: Path | None = None,
    timeout_seconds: int = 60,
) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            command,
            cwd=str(cwd) if cwd else None,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            check=False,
        )
    except FileNotFoundError as exc:
        raise RuntimeError(f"未找到命令: {command[0]}") from exc


def run_gh(args: list[str], timeout_seconds: int = 60) -> subprocess.CompletedProcess[str]:
    return run_command(["gh", *args], timeout_seconds=timeout_seconds)


def ensure_project_is_latest(
    project_root: Path,
    remote_name: str = "origin",
    branch_name: str = "main",
) -> None:
    branch = normalize_branch_name(branch_name) or "main"
    root = project_root.resolve()
    top_level = detect_repo_top_level(root)
    if top_level != root:
        log("[GIT] 当前目录不是项目仓库根目录，跳过项目更新检查")
        return

    remote_result = run_git(root, ["remote", "get-url", remote_name], timeout_seconds=30)
    if remote_result.returncode != 0:
        log(f"[GIT] 未检测到远端 {remote_name}，跳过项目更新检查")
        return

    status_result = run_git(root, ["status", "--porcelain"], timeout_seconds=30)
    if status_result.returncode != 0:
        details = extract_tail(status_result.stderr or status_result.stdout, 300)
        log(f"[WARN] 无法读取项目仓库状态，跳过项目更新检查：{details}")
        return
    if (status_result.stdout or "").strip():
        log("[GIT] 检测到项目仓库有未提交改动，跳过自动 git pull")
        return

    fetch_result = run_git(root, ["fetch", remote_name, branch], timeout_seconds=120)
    if fetch_result.returncode != 0:
        details = extract_tail(fetch_result.stderr or fetch_result.stdout, 400)
        raise RuntimeError(f"项目启动前检查远端更新失败：{details}")

    local_head = run_git(root, ["rev-parse", "HEAD"], timeout_seconds=30)
    remote_head = run_git(root, ["rev-parse", f"{remote_name}/{branch}"], timeout_seconds=30)
    if local_head.returncode != 0 or remote_head.returncode != 0:
        details = extract_tail(
            (local_head.stderr or local_head.stdout or "")
            + "\n"
            + (remote_head.stderr or remote_head.stdout or ""),
            400,
        )
        raise RuntimeError(f"项目启动前读取版本信息失败：{details}")

    local_sha = (local_head.stdout or "").strip()
    remote_sha = (remote_head.stdout or "").strip()
    if local_sha == remote_sha:
        log("[GIT] 项目仓库已是最新版本")
        return

    log(f"[GIT] 检测到项目仓库有更新，执行：git pull {remote_name} {branch}")
    pull_result = run_git(root, ["pull", remote_name, branch], timeout_seconds=180)
    if pull_result.returncode != 0:
        details = extract_tail(pull_result.stderr or pull_result.stdout, 800)
        raise RuntimeError(f"项目启动前自动拉取更新失败：{details}")
    log("[GIT] 项目仓库更新完成")


def ensure_gh_cli_ready() -> None:
    if shutil.which("gh") is None:
        raise RuntimeError(
            "autoGitInit 已启用，但未检测到 gh CLI。\n"
            "请先安装 GitHub CLI，并执行 gh auth login 完成登录。"
        )


def detect_github_login() -> str:
    result = run_gh(["api", "user", "--jq", ".login"], timeout_seconds=30)
    if result.returncode != 0:
        details = extract_tail(result.stderr or result.stdout, 400)
        raise RuntimeError(
            "无法获取当前 GitHub 用户名，请先执行 gh auth login。\n"
            f"详细信息: {details}"
        )
    login = (result.stdout or "").strip()
    if not login:
        raise RuntimeError("无法获取 GitHub 用户名，请检查 gh 登录状态。")
    return login


def github_repo_exists(owner: str, repo_name: str) -> bool:
    result = run_gh(
        ["repo", "view", f"{owner}/{repo_name}", "--json", "name", "--jq", ".name"],
        timeout_seconds=30,
    )
    return result.returncode == 0


def github_create_repo(owner: str, repo_name: str) -> None:
    result = run_gh(
        ["repo", "create", f"{owner}/{repo_name}", "--private", "--clone=false"],
        timeout_seconds=120,
    )
    if result.returncode != 0:
        details = extract_tail(result.stderr or result.stdout, 600)
        raise RuntimeError(f"创建 GitHub 仓库失败: {details}")
    log(f"[GIT] 已创建 GitHub 仓库: {owner}/{repo_name}")


def resolve_workspace_path(app_root: Path, project_name: str) -> Path:
    projects_root = (app_root / "projects").resolve()
    projects_root.mkdir(parents=True, exist_ok=True)
    workspace = (projects_root / project_name).resolve()

    if workspace != projects_root and projects_root not in workspace.parents:
        raise ValueError("projectName 非法，必须位于 projects 目录内")

    return workspace


def resolve_workspace(app_root: Path, project_name: str) -> Path:
    workspace = resolve_workspace_path(app_root, project_name)
    if not workspace.exists() or not workspace.is_dir():
        raise FileNotFoundError(
            f"未找到项目仓库目录: {workspace}\n"
            "请先创建空仓库目录，例如: mkdir -p projects/<projectName> && cd projects/<projectName> && git init"
        )

    return workspace


def ensure_workspace_is_git_repo(workspace: Path) -> None:
    top_level = detect_repo_top_level(workspace)
    resolved_workspace = workspace.resolve()
    if top_level is None:
        raise RuntimeError(
            f"{workspace} 不是 git 仓库根目录。\n"
            "请先在该目录执行 git init，并按需配置远端。"
        )
    if top_level != resolved_workspace:
        raise RuntimeError(
            f"{workspace} 不是独立 git 仓库（当前仓库根目录: {top_level}）。\n"
            "请确保 projects/<projectName> 是独立仓库目录。"
        )


def detect_repo_top_level(workspace: Path) -> Path | None:
    result = run_git(workspace, ["rev-parse", "--show-toplevel"], timeout_seconds=30)
    if result.returncode != 0:
        return None
    output = (result.stdout or "").strip()
    if not output:
        return None
    return Path(output).resolve()


def workspace_has_any_files(workspace: Path) -> bool:
    try:
        next(workspace.iterdir())
    except StopIteration:
        return False
    return True


def git_repo_has_remote(workspace: Path, remote_name: str) -> bool:
    result = run_git(workspace, ["remote", "get-url", remote_name], timeout_seconds=30)
    return result.returncode == 0


def add_git_remote(workspace: Path, remote_name: str, remote_url: str) -> None:
    result = run_git(workspace, ["remote", "add", remote_name, remote_url], timeout_seconds=30)
    if result.returncode != 0:
        details = extract_tail(result.stderr or result.stdout, 500)
        raise RuntimeError(f"绑定远端失败: {details}")
    log(f"[GIT] 已绑定远端 {remote_name}: {remote_url}")


def clone_repo_to_workspace(workspace: Path, remote_url: str) -> None:
    parent = workspace.parent
    result = run_command(
        ["git", "clone", remote_url, workspace.name],
        cwd=parent,
        timeout_seconds=180,
    )
    if result.returncode != 0:
        details = extract_tail(result.stderr or result.stdout, 800)
        raise RuntimeError(f"克隆仓库失败: {details}")
    log(f"[GIT] 已克隆仓库到: {workspace}")


def pull_remote_branch_if_exists(workspace: Path, remote_name: str, branch_name: str) -> None:
    has_remote_branch = run_git(
        workspace,
        ["ls-remote", "--heads", remote_name, branch_name],
        timeout_seconds=30,
    )
    if has_remote_branch.returncode != 0:
        details = extract_tail(has_remote_branch.stderr or has_remote_branch.stdout, 500)
        raise RuntimeError(f"检查远端分支失败: {details}")

    if not (has_remote_branch.stdout or "").strip():
        log(f"[GIT] 远端分支 {remote_name}/{branch_name} 不存在，跳过 pull")
        return

    pull_result = run_git(workspace, ["pull", remote_name, branch_name], timeout_seconds=180)
    if pull_result.returncode != 0:
        details = extract_tail(pull_result.stderr or pull_result.stdout, 800)
        raise RuntimeError(f"拉取远端分支失败: {details}")
    log(f"[GIT] 已拉取最新代码: {remote_name}/{branch_name}")


def get_current_branch_name(workspace: Path) -> str:
    result = run_git(workspace, ["symbolic-ref", "--quiet", "--short", "HEAD"])
    if result.returncode != 0:
        details = (result.stderr or result.stdout).strip()
        raise RuntimeError(f"读取当前分支失败: {details}")
    return normalize_branch_name(result.stdout)


def ensure_branch_ready(workspace: Path, branch_name: str) -> None:
    current = get_current_branch_name(workspace)
    target = normalize_branch_name(branch_name)
    if current == target:
        return

    exists = run_git(workspace, ["show-ref", "--verify", "--quiet", f"refs/heads/{target}"])
    if exists.returncode == 0:
        switch = run_git(workspace, ["checkout", target])
    else:
        switch = run_git(workspace, ["checkout", "-B", target])

    if switch.returncode != 0:
        details = (switch.stderr or switch.stdout).strip()
        raise RuntimeError(f"切换到分支 {target} 失败: {details}")

    log(f"[GIT] 已切换到分支: {target}")


def ensure_remote_ready(workspace: Path, remote_name: str) -> None:
    result = run_git(workspace, ["remote", "get-url", remote_name])
    if result.returncode != 0:
        raise RuntimeError(
            f"未找到远端 {remote_name}。\n"
            f"请先在 {workspace} 执行: git remote add {remote_name} <你的仓库地址>"
        )


def prepare_workspace_with_auto_git_init(app_root: Path, config: AppConfig) -> Path:
    workspace = resolve_workspace_path(app_root, config.project_name)
    remote_name = config.codex.git_remote
    target_branch = normalize_branch_name(config.codex.git_branch)

    github_login: str | None = None

    def ensure_remote_repo_and_url() -> str:
        nonlocal github_login
        ensure_gh_cli_ready()
        if not github_login:
            github_login = detect_github_login()

        repo_name = config.project_name
        exists = github_repo_exists(github_login, repo_name)
        if not exists:
            log(f"[GIT] 未检测到远端仓库 {github_login}/{repo_name}，正在创建")
            github_create_repo(github_login, repo_name)
        else:
            log(f"[GIT] 检测到远端仓库已存在: {github_login}/{repo_name}")
        return f"https://github.com/{github_login}/{repo_name}.git"

    if not workspace.exists():
        remote_url = ensure_remote_repo_and_url()
        clone_repo_to_workspace(workspace, remote_url)
        return workspace

    if not workspace.is_dir():
        raise RuntimeError(f"目标路径不是目录: {workspace}")

    repo_top_level = detect_repo_top_level(workspace)
    resolved_workspace = workspace.resolve()
    if repo_top_level and repo_top_level != resolved_workspace:
        raise RuntimeError(
            f"{workspace} 位于另一个 git 仓库中（根目录: {repo_top_level}）。\n"
            "为避免误操作，请更换 projectName 或将目标目录独立初始化为仓库。"
        )

    is_git_repo = repo_top_level == resolved_workspace

    if not is_git_repo:
        if workspace_has_any_files(workspace):
            raise RuntimeError(
                f"{workspace} 已存在且不是 git 仓库，并且目录非空。\n"
                "为避免覆盖用户文件，请清空目录或更换 projectName 后重试。"
            )
        init_result = run_git(workspace, ["init"], timeout_seconds=30)
        if init_result.returncode != 0:
            details = extract_tail(init_result.stderr or init_result.stdout, 500)
            raise RuntimeError(f"初始化 git 仓库失败: {details}")
        log(f"[GIT] 已初始化本地仓库: {workspace}")

    if not git_repo_has_remote(workspace, remote_name):
        remote_url = ensure_remote_repo_and_url()
        add_git_remote(workspace, remote_name, remote_url)

    pull_remote_branch_if_exists(workspace, remote_name, target_branch)
    return workspace


def inspect_workspace_state(workspace: Path) -> str:
    has_commit = run_git(workspace, ["rev-parse", "--verify", "HEAD"]).returncode == 0

    tracked = run_git(workspace, ["ls-files"])
    if tracked.returncode != 0:
        raise RuntimeError(f"读取仓库文件列表失败：{extract_tail(tracked.stderr or tracked.stdout, 400)}")
    tracked_files = [line.strip() for line in tracked.stdout.splitlines() if line.strip()]

    uncommitted = run_git(workspace, ["status", "--porcelain"])
    if uncommitted.returncode != 0:
        raise RuntimeError(
            f"读取仓库状态失败：{extract_tail(uncommitted.stderr or uncommitted.stdout, 400)}"
        )
    pending = [line.strip() for line in uncommitted.stdout.splitlines() if line.strip()]

    if not has_commit and not tracked_files and not pending:
        return "empty"
    return "non_empty"


def count_changed_files(workspace: Path) -> int:
    status = run_git(workspace, ["status", "--porcelain"])
    if status.returncode != 0:
        return -1
    return len([line for line in status.stdout.splitlines() if line.strip()])


def rollback_uncommitted_changes(workspace: Path) -> tuple[bool, int]:
    resolved_workspace = workspace.resolve()
    top_level = detect_repo_top_level(resolved_workspace)
    if top_level is None:
        raise RuntimeError(f"{resolved_workspace} 不是 git 仓库，无法执行回滚")
    if top_level != resolved_workspace:
        raise RuntimeError(
            f"{resolved_workspace} 不是独立仓库根目录（当前仓库根目录: {top_level}），拒绝回滚"
        )

    status = run_git(resolved_workspace, ["status", "--porcelain"])
    if status.returncode != 0:
        raise RuntimeError(f"读取仓库状态失败：{extract_tail(status.stderr or status.stdout, 400)}")
    pending_lines = [line for line in status.stdout.splitlines() if line.strip()]
    if not pending_lines:
        return False, 0

    has_commit = run_git(resolved_workspace, ["rev-parse", "--verify", "HEAD"]).returncode == 0
    if has_commit:
        reset_result = run_git(resolved_workspace, ["reset", "--hard", "HEAD"], timeout_seconds=120)
    else:
        # 无提交历史时先撤销暂存，再配合 clean 删除未跟踪文件。
        reset_result = run_git(resolved_workspace, ["reset", "--quiet"], timeout_seconds=120)
    if reset_result.returncode != 0:
        raise RuntimeError(f"回滚工作区失败：{extract_tail(reset_result.stderr or reset_result.stdout, 600)}")

    clean_result = run_git(resolved_workspace, ["clean", "-fd"], timeout_seconds=120)
    if clean_result.returncode != 0:
        raise RuntimeError(f"清理未跟踪文件失败：{extract_tail(clean_result.stderr or clean_result.stdout, 600)}")

    remaining = count_changed_files(resolved_workspace)
    if remaining > 0:
        raise RuntimeError(f"回滚后仍有未提交改动（{remaining} 项）")

    return True, len(pending_lines)


def build_commit_message(config: AppConfig, codex_message: str, iteration: int) -> str:
    base = sanitize_commit_message(codex_message) or f"第{iteration}轮自动进化更新"
    prefix = sanitize_commit_message(config.codex.git_commit_prefix)
    if prefix and not base.startswith(prefix):
        return f"{prefix} {base}".strip()
    return base


def commit_and_push_changes(
    config: AppConfig,
    workspace: Path,
    codex_message: str,
    iteration: int,
) -> tuple[bool, bool]:
    if not config.codex.auto_git_commit:
        log("[GIT] 已关闭自动提交（autoGitCommit=false）")
        return False, False

    add_result = run_git(workspace, ["add", "-A"], timeout_seconds=120)
    if add_result.returncode != 0:
        raise RuntimeError(f"git add 失败：{extract_tail(add_result.stderr or add_result.stdout, 600)}")

    staged = run_git(workspace, ["diff", "--cached", "--name-only"])
    if staged.returncode != 0:
        raise RuntimeError(f"读取暂存区失败：{extract_tail(staged.stderr or staged.stdout, 600)}")

    staged_files = [line.strip() for line in staged.stdout.splitlines() if line.strip()]
    if not staged_files:
        log("[GIT] 未检测到可提交改动，跳过提交与推送")
        return False, False

    message = build_commit_message(config, codex_message, iteration)
    commit_result = run_git(workspace, ["commit", "-m", message], timeout_seconds=120)
    if commit_result.returncode != 0:
        details = extract_tail(commit_result.stderr or commit_result.stdout, 1000)
        if "Author identity unknown" in details:
            raise RuntimeError(
                "git commit 失败：未配置用户信息，请先执行\n"
                'git config user.name "<你的名字>"\n'
                'git config user.email "<你的邮箱>"'
            )
        raise RuntimeError(f"git commit 失败：{details}")

    log(f"[GIT] 已提交：{message}")

    if not config.codex.auto_git_push:
        log("[GIT] 已关闭自动推送（autoGitPush=false）")
        return True, False

    remote = config.codex.git_remote
    branch = normalize_branch_name(config.codex.git_branch)
    push_result = run_git(workspace, ["push", "-u", remote, branch], timeout_seconds=180)
    if push_result.returncode != 0:
        raise RuntimeError(f"git push 失败：{extract_tail(push_result.stderr or push_result.stdout, 1000)}")

    log(f"[GIT] 已推送到 {remote}/{branch}")
    return True, True

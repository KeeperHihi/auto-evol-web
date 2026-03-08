# Auto-Evolution-Project ---- Idea is all you need!

`Codex` 驱动的自进化项目框架

## 作品展示

## TODO
- [ ] 适配 `claude code` 等更多平台

## 工作流

- `projects` 下的每个子目录都是一个独立项目仓库，形如 `projects/<projectName>`。
- 你可以从空仓库开始，只提供一句创意 `idea` 逐轮进化。
- 默认使用 `multi-agent` 串行协作，每轮按 3 角色流水线推进：
  - `Innovation Analyst`：读源码并提出创新改进方案
  - `Implementation Engineer`：实施改动
  - `Verification & Repair Engineer`：测试、发现问题并修复
- 所有 Agent 都统一使用同一个 `codex CLI` 和 `codex.model`。
- 每轮迭代结束后，脚本会在该子仓库内自动提交并推送（可通过配置关闭）。

## 代码结构

- `evolution.py`：命令行入口。
- `auto_evolution/cli.py`：参数解析。
- `auto_evolution/workflow.py`：主流程编排。
- `auto_evolution/config_loader.py`：配置读取与兼容性归一化。
- `auto_evolution/logging_utils.py`：彩色日志与 Codex 输出分类。
- `auto_evolution/prompt_tools.py`：提示词读取与迭代 Prompt 组装。
- `auto_evolution/codex_runner.py`：Codex 执行、重试、会话恢复、提交信息提取。
- `auto_evolution/git_tools.py`：项目仓库检查、分支与远端检查，自动创建仓库、提交推送。

## 环境要求

- `python`，基础环境即可
- `git`，保证本机的 `user.name` 和 `user.email` 字段配置正确，且可以免密操作
- 本机必须配置好 `codex CLI`
- （非常建议）安装 `gh` 并登录：`gh auth login`，便于自动化创建 `GitHub` 仓库，[安装链接](https://cli.github.com/)

## 快速开始

### 0. 务必保证本机的 `codex CLI` 可以使用

配置教程见 [codex 配置教程](https://docs.right.codes/docs/rc_cli_config/codex.html)

只需要将 `RightCode` 教程中的 `config.toml` 和 `auth.json` 两个文件按照你自己运营商的相关配置写好即可。

### 1. 初始化本地配置与 prompts

在项目根目录执行：

```bash
cp -rn .template/. .
```

说明：
- 这条命令会把 `.template/` 下的 `config.json` 和 `prompts/*` 复制到项目根目录。
- `-n` 表示不覆盖你已修改过的本地文件，可重复执行。
- 运行时会优先读取根目录文件；若根目录缺失，才会回退读取 `.template/` 下对应文件。

`config.json` 中要修改的字段：

- `projectName`: 你希望进化的项目仓库名。
- `iterations`: 你希望进化的迭代次数。
- `multiAgent.enabled`: 是否启用多 Agent 协作（默认 `true`）。
- (推荐) `autoGitInit`: 是否愿意自动化创建仓库（默认为 `false`，必须 `gh` 登录才能为 `true`，建议改为 `true`）
- (可选) `llmAccess`: 如果你希望进化过程中可以加入调用大模型的功能，请提供一个可调用的大模型配置，其中 `apiKey` 会以环境变量的形式加载，无需担心泄漏问题。
- (可选) `needAutoUpgrade`: 是否在每次启动时自动检查并拉取当前框架仓库更新（默认 `true`）,若你希望修改代码，可设置此参数为 `false`。

### 2. 准备承载项目的空仓库（若已登录 `gh` 并配置 `autoGitInit=true` 则可跳过本节）

在 `GitHub` 上创建一个空仓库，然后在项目根目录执行：

```bash
mkdir -p projects/<你的空仓库名>
cd projects/<你的空仓库名>
git init
git checkout -B main
git remote add origin <你的空仓库地址>
```

### 3. 设置好 prompts

按需改写 `prompts/sys-prompt.md`（当前模板是通用系统规则）。
多 Agent 角色提示词位于 `prompts/roles/*.zh.md`。

记得填写你的创意 `idea` 到 `prompts/user-prompt.md`。

（重要！）如果你在迭代中途有新想法 / 新问题，可随时写入 `prompts/user-temp-prompt.md`，系统会在每轮开始时按最高优先级处理：
- 第 1 角色先将你的需求重构成编号条目
- 第 3 角色删除已完成条目并保留未完成条目。

若你没有在根目录创建这些文件，程序会读取 `.template/` 中的默认内容，建议始终维护根目录文件。

### 4. 启动进化

在项目根目录执行：

```bash
python evolution.py
```

常用可选参数：

```bash
python evolution.py --iterations 10 # 传入迭代次数
python evolution.py --project <YOUR_REPO_NAME> # 传入项目仓库名
python evolution.py --prompt "请做一坨💩" # 直接传入创意，但更推荐用 user-prompt.md 传输，不传入 --prompt 参数即自动读取 user-prompt.md
python evolution.py --dry-run # 测试本地流程是否能跑通
```

中断说明：
- 运行中按 `Ctrl+C` 会中断当前 Codex 执行。
- 脚本会检测当前子仓库是否存在未提交改动，若存在会自动回滚这些未完成改动，然后正常退出。

## 配置字段（`config.json`）

- `projectName`：你的项目仓库名，对应 `projects/<projectName>`。
- `needAutoUpgrade`：是否在每次启动时自动检查并拉取当前框架仓库更新，默认 `true`。
- `iterations`：迭代轮次。
- `intervalSeconds`：轮次间隔秒数。
- `appendIterationContext`：是否在每轮 Prompt 附带迭代上下文。
- `systemPromptFile`：系统提示词路径。
- `userPromptFile`：你创意提示词路径。
- `llmAccess`：（可选）提供给 `codex` 的大模型调用接口。
- `multiAgent.enabled`：是否启用多 Agent 协作流程。
- `multiAgent.maxContextChars`：多 Agent 协作记忆的截断长度（避免上下文无限增长）。
- `multiAgent.agents`：角色列表，每项包含：
  - `name`：角色唯一标识。
  - `role`：角色名称，用于提示词角色卡。
  - `goal`：角色目标，定义该角色在流水线中的职责。
  - `canEditCode`：该角色是否允许直接改代码。
  - `systemPromptFile`：（可选）角色系统提示词文件路径（建议放在 `prompts/roles/`）。
- 只读角色可使用项目临时交接目录：`.git/auto-evolution-handoffs/iter-xxx/`，通过 `HANDOFF_FILE: <path>` 传递分析结论。
- 运行日志会落盘到框架目录 `./logs/`。
- `codex.command`：Codex 命令名。
- `codex.model`：Codex 模型参数。
- `codex.profile`：（可选）profile。
- `codex.dangerouslyBypassApprovalsAndSandbox`：是否给予 `codex` 最高权限，此项默认为 `true`，为 `false` 则无法改动代码。
- `codex.timeoutSeconds`：单轮超时秒数。
- `codex.retries`：单轮失败重试次数。
- `codex.extraArgs`：追加给 Codex 的参数。
- `codex.dryRun`：测试本地流程是否能跑通，不调用 Codex，不触发 autoGitInit，不切换分支，不做远端检查。
- `codex.autoGitCommit`：每轮迭代后是否自动提交。
- `codex.autoGitPush`：每轮迭代后是否自动推送。（若为 `true` 则要求 `autoGitCommit=true`）
- `codex.gitRemote`：推送远端名，默认 `origin`。
- `codex.gitBranch`：推送分支名，默认 `main`。
- `codex.gitCommitPrefix`：提交信息前缀（可留空）。
- `codex.autoGitInit`：自动初始化仓库机制。启用后若本地项目目录未绑定远端，会自动检测当前 `GitHub` 账号下是否有同名仓库，有则绑定并拉取，无则自动创建后绑定。（若为 `true` 必须提前登录 `gh`）

## 版权声明

本项目版权归 [KeeperHihi](https://github.com/KeeperHihi) 所有。

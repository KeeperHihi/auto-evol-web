# Auto-Evolution-Web ---- 一句话实现你心目中的网页

`Codex` 驱动的自进化网页框架

## TODO
- [ ] 适配 `claude code` 等更多平台

## 工作流

- `webs/<siteName>` 下每个子目录都是一个独立网站仓库。
- 你可以从空仓库开始，只提供一句创意 `idea` 逐轮进化。
- 每轮迭代后，脚本会在该子仓库内自动推送到远程仓库。
- 每次启动项目时，会自动 `git pull` 同步最新项目版本，所以建议不要擅改项目代码。

## 代码结构

- `evolution.py`：命令行入口。
- `auto_evolution/cli.py`：参数解析。
- `auto_evolution/workflow.py`：主流程编排。
- `auto_evolution/config_loader.py`：配置读取与兼容性归一化。
- `auto_evolution/logging_utils.py`：彩色日志与 Codex 输出分类。
- `auto_evolution/prompt_tools.py`：提示词读取与迭代 Prompt 组装。
- `auto_evolution/codex_runner.py`：Codex 执行、重试、会话恢复、提交信息提取。
- `auto_evolution/git_tools.py`：网站仓库检查、分支与远端检查，自动创建仓库、提交推送。

## 环境要求

- `python`，基础环境即可
- `git`，保证本机的 `user.name` 和 `user.email` 字段配置正确，且可以免密操作
- 本机必须配置好 `codex CLI`
- （非常建议）安装 `gh` 并登录：`gh auth login`，便于自动化 `git` 创建仓库等操作。

## 快速开始

### 0. 务必保证本机的 `codex CLI` 可以使用

配置教程见 [codex 配置教程](https://docs.right.codes/docs/rc_cli_config/codex.html)

只需要将 `RightCode` 教程中的 `config.toml` 和 `auth.json` 两个文件按照你自己运营商的相关配置写好即可。

### 1. 准备配置文件
在项目根目录执行：
```bash
cp config.template.json config.json
```
`config.json` 中要修改的字段：
- `siteName`: 你希望进化的网站仓库名。
- `iterations`: 你希望进化的迭代次数。
- (推荐) `autoGitInit`: 是否愿意自动化创建仓库（默认为 `false`，必须 `gh` 登录才能为 `true`，建议改为 `true`）
- (可选) `llmAccess`: 如果你希望进化过程中可以加入调用大模型的功能，请提供一个可调用的大模型配置，其中 `apiKey` 会以环境变量的形式加载，无需担心泄漏问题。

### 2. 准备承载网站的空仓库（若已登录 `gh` 并配置 `autoGitInit=True` 则可跳过本节）

在 `github` 上创建一个空仓库，然后在项目根目录执行：
```bash
mkdir -p webs/<你的空仓库名>
cd webs/<你的空仓库名>
git init
git checkout -B main
git remote add origin <你的空仓库地址>
```

### 3. 设置好 prompts
在项目根目录执行：
```bash
cp prompts/sys-prompt.template.md prompts/sys-prompt.md
cp prompts/user-prompt.template.md prompts/user-prompt.md
```
可以改写 `prompts/sys-prompt.md` 更加适配你的需求。

记得填写你的创意 `idea` 到 `prompts/user-prompt.md`。

### 4. 启动进化
在项目根目录执行：
```bash
python evolution.py
```

常用可选参数：

```bash
python evolution.py --iterations 10 # 传入迭代次数
python evolution.py --site <YOUR_REPO_NAME> # 传入仓库名
python evolution.py --prompt "做一个极简但高级的作品集网站" # 传入prompt，更推荐用 user-prompt.md 传输，不传入 prompt 参数即自动读取 user-prompt.md
python evolution.py --dry-run # 测试本地流程是否能跑通
```

## 配置字段（`config.json`）

- `siteName`：你的网站仓库名，对应 `webs/<siteName>`。
- `iterations`：迭代轮次。
- `intervalSeconds`：轮次间隔秒数。
- `appendIterationContext`：是否在每轮 Prompt 附带迭代上下文。
- `systemPromptFile`：系统提示词路径。
- `userPromptFile`：你创意提示词路径。
- `llmAccess`：（可选）提供给 `codex` 的大模型调用接口。
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
- `codex.autoGitInit`：自动初始化仓库机制。启用后若本地网站目录未绑定远端，会自动检测当前 `github` 账号下是否有同名仓库，有则绑定并拉取，无则自动创建后绑定。（若为 `true` 必须提前登录 `gh`）

## 版权声明

本项目版权归 [KeeperHihi](https://github.com/KeeperHihi) 所有。

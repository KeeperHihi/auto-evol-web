# Auto-Evolution-Web ---- 一句话实现你心目中的网页

`Codex` 驱动的自进化网页框架

## TODO
- [ ] 适配 `claude code` 等更多平台

## 工作流

- `webs/<siteName>` 下每个子目录都是一个独立网站仓库。
- 用户可以从空仓库开始，只提供一句创意 `idea` 逐轮进化。
- 每轮执行后，脚本会在该子仓库内自动执行：
  - `git add -A`
  - `git commit -m "<Codex 提供的提交信息>"`
  - `git push -u origin main`

## 代码结构

- `evolution.py`：命令行入口。
- `auto_evolution/cli.py`：参数解析。
- `auto_evolution/workflow.py`：主流程编排。
- `auto_evolution/config_loader.py`：配置读取与兼容性归一化。
- `auto_evolution/logging_utils.py`：彩色日志与 Codex 输出分类。
- `auto_evolution/prompt_tools.py`：提示词读取与迭代 Prompt 组装。
- `auto_evolution/codex_runner.py`：Codex 执行、重试、会话恢复、提交信息提取。
- `auto_evolution/git_tools.py`：站点仓库检查、分支与远端检查，自动创建仓库、提交推送。

## 环境要求

- `python`
- `git`
- 本机必须配置好 `codex CLI`
- （非常建议）若要启用 `autoGitInit`，还需安装 `gh` 并登录：`gh auth login`，便于自动化 `git` 操作

## 快速开始

### 0. 务必保证本机的 `codex CLI` 可以使用

配置教程见 [codex 配置教程](https://docs.right.codes/docs/rc_cli_config/codex.html)

只需要将 `RightCode` 教程中的 `config.toml` 和 `auth.json` 两个文件按照你自己运营商的相关配置写好即可。


### 1. 准备配置文件：

```bash
cp config.template.json config.json
```
`config.json` 中要修改的字段：
- `siteName` 你希望进化网站的仓库名。
- `iterations` 你希望进化的迭代次数。
- (可选) `llmAccess` 如果你希望进化过程中可以加入调用大模型的功能，请提供一个可调用的大模型配置，其中 `apiKey` 会以环境变量的形式加载，无需担心泄漏问题。

### 2. 准备站点空仓库（若已登录 `gh` 并配置 `autoGitInit=True` 则可跳过本节）：

在 `github` 上创建一个空仓库，假设仓库名叫 `demo`，然后在项目根目录执行：
```bash
# 示例站点名：`demo`
mkdir -p webs/demo
cd webs/demo
git init
git checkout -B main
git remote add origin <你的空仓库地址>
```

### 3. 填写你的创意 `idea` 到 `prompts/user-prompt.md`。

### 4. 回到项目根目录，启动进化：

```bash
python evolution.py
```

常用可选参数：

```bash
python evolution.py --iterations 10 # 传入迭代次数
python evolution.py --site demo # 传入仓库名
python evolution.py --prompt "做一个极简但高级的作品集网站" # 传入prompt，更推荐用 user-prompt.md 传输
python evolution.py --dry-run # 只做本地只读校验（不调用 Codex、不触发 autoGitInit、不切换分支、不做远端检查）
```

## 配置字段（`config.json`）

- `siteName`：目标站点目录名，对应 `webs/<siteName>`。
- `iterations`：默认迭代轮次。
- `intervalSeconds`：轮次间隔秒数。
- `appendIterationContext`：是否在每轮 Prompt 附带迭代上下文。
- `systemPromptFile`：系统提示词路径。
- `userPromptFile`：用户创意提示词路径。
- `llmAccess`：可选运行时外部模型注入信息。
- `codex.command`：Codex 命令名。
- `codex.model`：Codex 模型参数。
- `codex.profile`：可选 profile。
- `codex.dangerouslyBypassApprovalsAndSandbox`：是否追加该参数。
- `codex.timeoutSeconds`：单轮超时秒数。
- `codex.retries`：单轮失败重试次数。
- `codex.extraArgs`：追加给 Codex 的参数。
- `codex.dryRun`：仅做本地只读演练，不调用 Codex，不触发 autoGitInit，不切换分支，不做远端检查。
- `codex.autoGitCommit`：每轮后是否自动提交。
- `codex.autoGitPush`：每轮后是否自动推送。
- `codex.gitRemote`：推送远端名，默认 `origin`。
- `codex.gitBranch`：推送分支名，默认 `main`。
- `codex.gitCommitPrefix`：提交信息前缀（可留空）。
- `codex.autoGitInit`：自动初始化仓库机制。启用后若本地站点目录未绑定远端，会自动检测当前 GitHub 账号下是否有同名仓库；有则绑定并拉取，无则自动创建后绑定。`dry-run` 模式下该流程不会执行。

## 版权声明

本项目版权归 [KeeperHihi](https://github.com/KeeperHihi) 所有。

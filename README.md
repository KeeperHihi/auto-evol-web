# Auto-Evolution-Web (Python)

当前主版本已迁移到 Python，核心入口是 `evolution.py`。  
旧版 JavaScript 实现保留在 `JS-version/`，仅作为历史参考。

## 核心变化

旧模式：
- 一个仓库，通过多个 git 分支（`codex.gitBranch`）区分不同网站。

新模式：
- 每个网站对应 `./webs/<siteName>` 下的一个子目录。
- 每个子目录就是用户自己的 git 仓库。
- `evolution.py` 会在该子目录内直接调用 Codex 进行自进化。

## 快速开始

1. 确保本机可直接使用 Codex CLI。

2. 准备配置文件：

```bash
cp config.template.json config.json
```

3. 将你的网站仓库放到 `webs/` 下：

```bash
mkdir -p webs
git clone <your-repo-url> webs/<siteName>
```

4. 修改 `config.json`：
- 将 `siteName` 设为 `webs/` 下的目录名。
- 设置 `iterations` / `intervalSeconds`。
- 按需修改 `prompts/user-prompt.md`。

5. 启动自进化：

```bash
python3 evolution.py
```

可选覆盖参数：

```bash
python3 evolution.py --site=my-site --iterations=10
python3 evolution.py --prompt "Build a polished SaaS landing page"
python3 evolution.py --dry-run
```

## 配置字段（`config.json`）

- `siteName`：目标网站目录名（位于 `./webs` 下）。
- `iterations`：迭代轮次。
- `intervalSeconds`：轮次之间等待秒数。
- `appendIterationContext`：是否在每轮 Prompt 中附加轮次上下文。
- `systemPromptFile`：系统提示词文件路径。
- `userPromptFile`：用户方向提示词文件路径。
- `llmAccess`：可选的运行时 LLM 提示信息（`url`、`apiKey`、`model`）。
- `codex.command`：Codex 命令名。
- `codex.model`：传给 Codex 的模型参数。
- `codex.profile`：可选 Codex profile。
- `codex.dangerouslyBypassApprovalsAndSandbox`：是否附加对应 Codex 参数。
- `codex.timeoutSeconds`：单轮超时秒数。
- `codex.retries`：单轮失败重试次数（支持 `codex exec resume`）。
- `codex.extraArgs`：附加给 Codex 的额外参数。
- `codex.dryRun`：是否仅组装 Prompt 而不调用 Codex。

## 说明

- `webs/**` 已在本仓库 `.gitignore` 中忽略，因为该目录属于用户网站仓库。
- `config.json` 已忽略，避免本地密钥被提交。

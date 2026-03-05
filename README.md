# auto-revo-web

AI 自进化网站框架：接收用户 Prompt，拼接系统提示词，调用 Codex 持续迭代当前仓库，并通过 Web/CLI 展示实时日志。

## 核心能力

1. Web 模式：前端输入网站方向 Prompt，后端执行多轮迭代。
2. CLI 模式：终端直接触发迭代并实时打印日志。
3. 配置驱动：通过 `config.json` 控制轮次、超时、Codex 参数、可选 Git 自动提交等。
4. SSE 日志流：Web 端可以实时看到每轮执行过程。

## 目录结构

- `server.js`：后端核心（配置读取、Prompt 组装、Codex 执行、轮次调度、SSE）
- `public/`：最小前端页面
- `prompts/sys-prompt.md`：系统提示词模板
- `config.example.json`：配置示例
- `config.json`：本地实际配置（已在 `.gitignore` 中忽略）

## 环境要求

- Node.js 18+（推荐 22 LTS）
- npm 9+
- 必需：`codex` CLI（执行 AI 进化）
- 必需：本机已完成 Codex 登录与配置（`~/.codex/config.toml`、`~/.codex/auth.json`）

## 快速开始（首次运行必看）

1. 安装依赖

```bash
npm install
```

2. 先在本机验证 Codex 可用（必须先完成）

请先在本机完成 `~/.codex/config.toml` 和 `~/.codex/auth.json` 配置，然后在项目外任意目录执行：

```bash
codex -m gpt-5.3-codex-xhigh -c model_reasoning_effort="xhigh"
```

该命令可以正常运行后，再继续下面步骤。

3. 准备配置

```bash
cp config.example.json config.json
```

如果你在 Windows PowerShell，可用：

```powershell
Copy-Item config.example.json config.json
```

4. 按需修改 `config.json`

- `server.port`：服务端口
- `evolution.defaultIterations` / `maxIterations`：默认与最大迭代轮次
- `codex.*`：Codex CLI 执行行为（不包含密钥配置，密钥来源为本机 `~/.codex`）
- `llmAccess.*`：可选外部模型调用信息（仅三项都配置才注入提示词）
- 若启用 `codex.autoGitCommit/autoGitPush`，`codex.gitBranch` 必须是非 `main` 分支（例如 `evolution/auto-revo`）

5. 运行

Web 模式：

```bash
npm run dev
```

浏览器打开：`http://localhost:6161`

CLI 模式（交互输入 Prompt）：

```bash
npm run cli-evolve
```

CLI 模式（脚本传参）：

```bash
npm run cli-evolve -- --prompt="做一个极简 AI 作品集网站" --iterations=3
```

开发热重启：

```bash
npm run dev:watch
```

## 常用脚本

- `npm run dev`：启动 Web 服务
- `npm run dev:watch`：使用 nodemon 热重启
- `npm run cli-evolve`：CLI 触发进化
- `npm run check`：检查 `server.js` 语法
- `npm run start`：生产模式启动

## Git 进化分支机制

为防止进化流程污染主分支，项目采用以下规则：

1. 只要启用了 `codex.autoGitCommit` 或 `codex.autoGitPush`，系统都会先校验 `codex.gitBranch`。
2. `codex.gitBranch` 不能是 `main`；否则任务会直接失败并给出提示。
3. 任务启动前会自动切换到 `codex.gitBranch`。
4. 如果该分支本地不存在，会自动创建并切换。
5. 如果本地不存在但检测到远端跟踪分支，会自动创建本地分支并建立跟踪关系。
6. 自动提交前会再次校验当前分支，若仍在 `main` 或与 `codex.gitBranch` 不一致，会拒绝提交。
7. 自动推送使用 `git push -u <gitRemote> <gitBranch>`，首次推送可自动创建远端分支。

建议配置：

```json
{
  "codex": {
    "autoGitCommit": true,
    "autoGitPush": true,
    "gitRemote": "origin",
    "gitBranch": "evolution/auto-revo"
  }
}
```

## 常见报错与排查

### 1) `spawn codex ENOENT`

原因：系统中找不到 `codex` 命令。

处理：

1. 先确认本机可直接执行 `codex --version`。
2. 如命令名不同，在 `config.json` 中改 `codex.command`。
3. 确认当前终端环境变量能找到该命令。
4. 再验证一次：`codex -m gpt-5.3-codex-xhigh -c model_reasoning_effort="xhigh"`。

### 2) Codex 执行中网络/权限失败

常见于受限沙箱或网络代理环境，表现为连接失败、只读目录报错等。

处理建议：

1. 检查网络代理配置是否可访问模型服务。
2. 确认 `~/.codex/config.toml` 与 `~/.codex/auth.json` 可被当前用户读取，且 Codex 可写其状态目录（如 `$HOME/.codex`）。
3. 在受限容器中运行时，先验证最小命令是否可执行。

### 3) 提示 `codex.gitBranch 不能是 main`

原因：自动提交/推送保护机制，防止污染主分支。

处理：

1. 在 `config.json` 把 `codex.gitBranch` 改成独立分支（如 `demo`）。
2. 重新执行进化任务。

## 安全说明

1. `config.json` 可能包含密钥（如 `llmAccess.apiKey` 或 `codex.environment` 中的敏感变量），不要提交到仓库。
2. 当前实现不会把 `llmAccess.apiKey` 明文注入到系统提示词；会通过环境变量 `LLM_ACCESS_API_KEY` 提供给 Codex 子进程。
3. 当前实现不再从 `config.json` 注入 `OPENAI_API_KEY/OPENAI_BASE_URL`；Codex 凭证统一从本机 `~/.codex` 读取。

## 运行流程

1. 读取 `config.json` 与 `prompts/sys-prompt.md`
2. 组装本轮 Prompt（系统提示词 + 用户方向 + 轮次上下文）
3. 调用 `codex exec`
4. 推送日志到 CLI 或 SSE
5. 根据设定轮次重复执行

## 配置字段说明（`config.json`）

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `server.port` | number | Web 服务端口 |
| `evolution.defaultIterations` | number | 默认迭代轮次 |
| `evolution.maxIterations` | number | 单次任务最大轮次 |
| `evolution.intervalMs` | number | 轮次间隔（ms） |
| `evolution.appendIterationContext` | boolean | 是否附加轮次上下文 |
| `evolution.systemPromptFile` | string | 系统提示词文件（相对项目根目录） |
| `llmAccess.url` | string | 可选外部模型 URL |
| `llmAccess.apiKey` | string | 可选外部模型密钥（通过环境变量注入） |
| `llmAccess.model` | string | 可选外部模型名称 |
| `codex.enabled` | boolean | 是否启用 Codex 执行 |
| `codex.command` | string | Codex 命令名 |
| `codex.model` | string | Codex 模型参数 |
| `codex.profile` | string | Codex profile |
| `codex.fullAuto` | boolean | 是否启用 `--full-auto` |
| `codex.dangerouslyBypassApprovalsAndSandbox` | boolean | 是否启用高风险放开参数 |
| `codex.timeoutMs` | number | 单轮执行超时（ms） |
| `codex.environment` | object | 额外环境变量 |
| `codex.extraArgs` | string[] | 追加给 Codex 的参数 |
| `codex.additionalWritableDirs` | string[] | 额外可写目录（仅允许项目内路径） |
| `codex.autoGitCommit` | boolean | 每轮完成后自动提交（仅允许在非 `main` 分支执行） |
| `codex.autoGitPush` | boolean | 自动提交后是否推送（要求 `autoGitCommit=true`） |
| `codex.gitRemote` | string | 推送远端名 |
| `codex.gitBranch` | string | 进化分支名（禁止 `main`，不存在时会自动创建并切换） |
| `codex.gitCommitPrefix` | string | 自动提交消息前缀 |

说明：Codex 的账号与模型访问配置由本机 `~/.codex/config.toml` 与 `~/.codex/auth.json` 管理。

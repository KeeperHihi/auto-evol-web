# auto-revo-web

终端驱动的 Codex 自进化项目：
- 自进化任务只能通过 CLI 启动。
- Web 页面仅用于静态展示文本，不提供任何进化入口。

## 核心约束

1. 禁止从网页端启动进化。
2. 进化流程仅支持 CLI（`npm run cli-evolve`）。
3. 浏览器访问首页仅显示静态文案，不承载任务控制与日志流。

## 目录结构

- `server.js`：后端核心（配置读取、Prompt 组装、Codex 执行、轮次调度、Git 自动提交/推送）
- `public/`：静态页面（仅展示文案）
- `prompts/sys-prompt.md`：系统提示词模板
- `config.example.json`：配置示例
- `config.json`：本地实际配置（已在 `.gitignore` 中忽略）

## 环境要求

- Node.js 18+（推荐 22 LTS）
- npm 9+
- 必需：`codex` CLI
- 必需：本机已完成 Codex 登录与配置（`~/.codex/config.toml`、`~/.codex/auth.json`）

## 快速开始

1. 安装依赖

```bash
npm install
```

2. 准备配置

```bash
cp config.example.json config.json
```

3. 启动服务（用于提供静态首页）

```bash
npm run dev
```

4. 启动自进化（CLI）

交互模式：

```bash
npm run cli-evolve
```

传参模式：

```bash
npm run cli-evolve -- --prompt="做一个极简 AI 作品集网站" --iterations=3
```

dry-run（仅校验流程，不执行 Codex，不修改仓库）：

```bash
npm run cli-evolve -- --prompt="做一个极简 AI 作品集网站" --iterations=1 --dry-run
```

## 常用脚本

- `npm run dev`：启动服务
- `npm run dev:watch`：热重启
- `npm run cli-evolve`：CLI 触发进化
- `npm run check`：检查 `server.js` 语法
- `npm run start`：生产模式启动

## 运行流程（CLI 唯一）

1. 读取 `config.json` 与 `prompts/sys-prompt.md`
2. 组装本轮 Prompt（系统提示词 + 用户方向 + 轮次上下文）
3. 调用 `codex exec`
4. 在终端打印日志
5. 根据设定轮次重复执行

## 配置字段说明（`config.json`）

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `server.port` | number | 服务端口（仅静态页面展示） |
| `evolution.defaultIterations` | number | 默认迭代轮次 |
| `evolution.maxIterations` | number | 单次任务最大轮次 |
| `evolution.intervalMs` | number | 轮次间隔（ms） |
| `evolution.appendIterationContext` | boolean | 是否附加轮次上下文 |
| `evolution.systemPromptFile` | string | 系统提示词文件（相对项目根目录） |
| `llmAccess.url` | string | 可选外部模型 URL |
| `llmAccess.apiKey` | string | 可选外部模型密钥（通过环境变量注入） |
| `llmAccess.model` | string | 可选外部模型名称 |
| `codex.enabled` | boolean | 是否启用 Codex 执行 |
| `codex.dryRun` | boolean | 是否启用 dry-run |
| `codex.command` | string | Codex 命令名 |
| `codex.model` | string | Codex 模型参数 |
| `codex.profile` | string | Codex profile |
| `codex.fullAuto` | boolean | 是否启用 `--full-auto` |
| `codex.dangerouslyBypassApprovalsAndSandbox` | boolean | 是否启用高风险放开参数 |
| `codex.timeoutMs` | number | 单轮执行超时（ms） |
| `codex.reconnectingRounds` | number | 单轮失败后自动重连重试次数 |
| `codex.environment` | object | 额外环境变量 |
| `codex.extraArgs` | string[] | 追加给 Codex 的参数 |
| `codex.additionalWritableDirs` | string[] | 额外可写目录（仅允许项目内路径） |
| `codex.autoGitCommit` | boolean | 每轮完成后自动提交（仅非 `main`） |
| `codex.autoGitPush` | boolean | 自动提交后是否推送（要求 `autoGitCommit=true`） |
| `codex.gitRemote` | string | 推送远端名 |
| `codex.gitBranch` | string | 进化分支名（禁止 `main`） |
| `codex.gitCommitPrefix` | string | 自动提交消息前缀 |

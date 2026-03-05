# Auto-Revolution-Web

`Codex` 驱动的自进化网页框架

## 目录结构

- `server.js`：后端
- `public/`：静态页面
- `prompts/sys-prompt.md`：系统提示词
- `config.example.json`：配置示例

## 环境要求

- `Node.js`
- `npm`
- 本机必须配置好 `codex CLI`

## 快速开始

### 1. 务必保证本机的 `codex CLI` 可以使用

配置教程见 [codex 配置教程](https://docs.right.codes/docs/rc_cli_config/codex.html)

只需要将 `RightCode` 教程中的 `config.toml` 和 `auth.json` 两个文件按照你自己运营商的相关配置写好即可。

### 2. 部署源码
   
先 `clone` 本仓库的 `main` 分支：
```bash
# 只需要 main 分支，demo 分支为生成的样例，想查看者也可以一起 clone 下来看看 
git clone --branch main --single-branch https://github.com/KeeperHihi/auto-revo-web.git
```
然后**新建**一个你自己的 `github` 仓库，比如叫 demo

然后把本项目目录下的 `.git` 目录删掉，进入终端，依次执行：
```bash
git init
git remote add origin https://github.com/xxx/demo.git
git branch -M main
git add .
git commit -m "init"
git push origin main
```


### 3. 安装依赖

```bash
# 终端进入项目根目录，然后
npm install
```

### 4. 准备配置

```bash
# 执行下面指令
cp config.example.json config.json

# 然后在 config.json 中修改参数:

# gitBranch: 你希望新项目的分支名

# 如果你希望进化的网页可以调用大模型服务，需要把 config.json 中的 llmAccess 字段填好，
# 随意提供一个可以调用的大模型服务即可。放心 api-key 绝对不会暴露。

# 其余参数不改即可，有需求再改。
# 配置文件各个参数解释见 README 最下方。
```

### 5. 测试网页启动

```bash
npm run dev
# 然后打开本地 localhost:6161，测试网页是否能正常显示。
```

### 6. 启动自进化

交互模式：

```bash
npm run cli-evolve
# 会让你现场输入你希望网站进化的方向
```

传参模式：

```bash
# 新建 run.sh，写上你希望进化的方向和迭代次数
npm run cli-evolve -- \
    --prompt="一个支持多用户在线匹配对战的五子棋网页，特点是UI非常科幻、丝滑，给用户最爽的对局体验" \
    --iterations=10
```

dry-run（仅校验流程，不执行 Codex，不修改仓库）：

```bash
npm run cli-evolve -- \
    --prompt="做一个网站" \
    --iterations=1 \
    --dry-run
```

## 常用指令

- `npm run dev`：启动服务
- `npm run cli-evolve`：进化

## 运行流程

1. 读取 `config.json` 与 `prompts/sys-prompt.md`
2. 组装本轮 Prompt（系统提示词 + 用户方向 + 轮次上下文）
3. 调用 `codex exec`
4. 在终端打印日志
5. 根据设定轮次重复执行

## 配置字段说明 (`config.json`)

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `server.port` | number | 服务端口 |
| `evolution.defaultIterations` | number | 默认迭代轮次 (若启动时未指定 --iterations 参数) |
| `evolution.maxIterations` | number | 单次任务最大轮次 (会与启动时指定的 --iterations 参数取 min) |
| `evolution.intervalMs` | number | 轮次间隔 (ms) |
| `evolution.appendIterationContext` | boolean | 是否附加轮次上下文 |
| `evolution.systemPromptFile` | string | 系统提示词文件 |
| `llmAccess.url` | string | 可选外部模型 URL |
| `llmAccess.apiKey` | string | 可选外部模型密钥 (通过环境变量注入) |
| `llmAccess.model` | string | 可选外部模型名称 |
| `codex.enabled` | boolean | 是否启用 Codex 执行 |
| `codex.dryRun` | boolean | 是否启用 dry-run |
| `codex.command` | string | Codex 命令名 |
| `codex.model` | string | Codex 模型参数 |
| `codex.profile` | string | Codex profile |
| `codex.fullAuto` | boolean | 是否启用 `--full-auto` |
| `codex.dangerouslyBypassApprovalsAndSandbox` | boolean | 是否启用高风险放开参数 (建议为 true，否则可能无法修改代码) |
| `codex.timeoutMs` | number | 单轮执行超时 (ms) |
| `codex.reconnectingRounds` | number | 单轮失败后自动重连重试次数 |
| `codex.environment` | object | 额外环境变量 |
| `codex.extraArgs` | string[] | 追加给 Codex 的参数 |
| `codex.additionalWritableDirs` | string[] | 额外可写目录 |
| `codex.autoGitCommit` | boolean | 每轮完成后自动提交 (仅 `codex.gitBranch != main` 时有效) |
| `codex.autoGitPush` | boolean | 自动提交后是否推送 (若为 `true` 要求 `autoGitCommit=true`) |
| `codex.gitRemote` | string | 推送远端名 |
| `codex.gitBranch` | string | 进化分支名 (禁止为 `main`) |
| `codex.gitCommitPrefix` | string | 自动提交消息前缀 |

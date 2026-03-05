const path = require('path');
const fs = require('fs/promises');
const { spawn } = require('child_process');
const readline = require('readline');

function loadExpressOrExit() {
    try {
        return require('express');
    } catch (error) {
        const isExpressMissing = Boolean(
            error
            && error.code === 'MODULE_NOT_FOUND'
            && /Cannot find module 'express'/.test(String(error.message || ''))
        );

        if (isExpressMissing) {
            console.error('[auto-revo-web] 缺少依赖: express');
            console.error('[auto-revo-web] 请先执行: npm install');
            process.exit(1);
        }

        throw error;
    }
}

const express = loadExpressOrExit();
const app = express();
const APP_ROOT = __dirname;
const CONFIG_FILE = path.join(APP_ROOT, 'config.json');

let activeRunId = null;

function normalizeGitBranchName(branchName) {
    const raw = String(branchName || '').trim();
    return raw.replace(/^refs\/heads\//, '');
}

function isMainBranchName(branchName) {
    return normalizeGitBranchName(branchName).toLowerCase() === 'main';
}

function stripJsonComments(input) {
    const source = String(input || '');
    let output = '';
    let inString = false;
    let stringChar = '';
    let inSingleLineComment = false;
    let inMultiLineComment = false;

    for (let i = 0; i < source.length; i += 1) {
        const char = source[i];
        const nextChar = source[i + 1];

        if (inSingleLineComment) {
            if (char === '\n') {
                inSingleLineComment = false;
                output += char;
            }
            continue;
        }

        if (inMultiLineComment) {
            if (char === '*' && nextChar === '/') {
                inMultiLineComment = false;
                i += 1;
            }
            continue;
        }

        if (inString) {
            output += char;
            if (char === '\\' && nextChar) {
                output += nextChar;
                i += 1;
                continue;
            }
            if (char === stringChar) {
                inString = false;
                stringChar = '';
            }
            continue;
        }

        if (char === '"' || char === '\'') {
            inString = true;
            stringChar = char;
            output += char;
            continue;
        }

        if (char === '/' && nextChar === '/') {
            inSingleLineComment = true;
            i += 1;
            continue;
        }

        if (char === '/' && nextChar === '*') {
            inMultiLineComment = true;
            i += 1;
            continue;
        }

        output += char;
    }

    return output;
}

function getDefaultConfig() {
    return {
        server: {
            port: 6161
        },
        evolution: {
            defaultIterations: 3,
            maxIterations: 10,
            intervalMs: 3000,
            appendIterationContext: true,
            systemPromptFile: 'prompts/sys-prompt.md'
        },
        llmAccess: {
            url: '',
            apiKey: '',
            model: ''
        },
        codex: {
            enabled: true,
            command: 'codex',
            model: 'gpt-5.3-codex-xhigh',
            profile: '',
            fullAuto: false,
            dangerouslyBypassApprovalsAndSandbox: false,
            timeoutMs: 1800000,
            reconnectingRounds: 10,
            environment: {},
            extraArgs: ['-c', 'model_reasoning_effort="xhigh"'],
            additionalWritableDirs: [],
            autoGitCommit: false,
            autoGitPush: false,
            gitRemote: 'origin',
            gitBranch: 'evolution/auto-revo',
            gitCommitPrefix: 'Codex Evolution:'
        }
    };
}

function normalizeConfig(rawConfig) {
    const defaults = getDefaultConfig();
    const source = rawConfig && typeof rawConfig === 'object' ? rawConfig : {};

    const server = source.server && typeof source.server === 'object' ? source.server : {};
    const codex = source.codex && typeof source.codex === 'object' ? source.codex : {};
    const evolution = source.evolution && typeof source.evolution === 'object' ? source.evolution : {};
    const llmAccess = source.llmAccess && typeof source.llmAccess === 'object' ? source.llmAccess : {};

    const normalized = {
        ...defaults,
        ...source,
        server: {
            ...defaults.server,
            ...server
        },
        evolution: {
            ...defaults.evolution,
            ...evolution
        },
        llmAccess: {
            ...defaults.llmAccess,
            ...llmAccess
        },
        codex: {
            ...defaults.codex,
            ...codex
        }
    };

    normalized.server.port = Number.isFinite(Number(normalized.server.port))
        ? Math.floor(Number(normalized.server.port))
        : defaults.server.port;

    normalized.evolution.defaultIterations = Math.max(1, Math.floor(Number(normalized.evolution.defaultIterations) || defaults.evolution.defaultIterations));
    normalized.evolution.maxIterations = Math.max(1, Math.floor(Number(normalized.evolution.maxIterations) || defaults.evolution.maxIterations));
    normalized.evolution.intervalMs = Math.max(0, Math.floor(Number(normalized.evolution.intervalMs) || defaults.evolution.intervalMs));
    normalized.evolution.appendIterationContext = Boolean(normalized.evolution.appendIterationContext);
    normalized.evolution.systemPromptFile = String(normalized.evolution.systemPromptFile || defaults.evolution.systemPromptFile).trim();

    normalized.llmAccess.url = String(normalized.llmAccess.url || '').trim();
    normalized.llmAccess.apiKey = String(normalized.llmAccess.apiKey || '').trim();
    normalized.llmAccess.model = String(normalized.llmAccess.model || '').trim();

    normalized.codex.enabled = Boolean(normalized.codex.enabled);
    normalized.codex.command = String(normalized.codex.command || defaults.codex.command).trim() || defaults.codex.command;
    normalized.codex.model = String(normalized.codex.model || '').trim();
    normalized.codex.profile = String(normalized.codex.profile || '').trim();
    normalized.codex.fullAuto = Boolean(normalized.codex.fullAuto);
    normalized.codex.dangerouslyBypassApprovalsAndSandbox = Boolean(normalized.codex.dangerouslyBypassApprovalsAndSandbox);
    normalized.codex.timeoutMs = Math.max(1000, Math.floor(Number(normalized.codex.timeoutMs) || defaults.codex.timeoutMs));
    {
        const reconnectingRoundsValue = Number(normalized.codex.reconnectingRounds);
        normalized.codex.reconnectingRounds = Number.isFinite(reconnectingRoundsValue)
            ? Math.max(0, Math.floor(reconnectingRoundsValue))
            : defaults.codex.reconnectingRounds;
    }
    normalized.codex.environment = normalized.codex.environment && typeof normalized.codex.environment === 'object' && !Array.isArray(normalized.codex.environment)
        ? normalized.codex.environment
        : {};
    normalized.codex.extraArgs = Array.isArray(normalized.codex.extraArgs)
        ? normalized.codex.extraArgs.map(String).filter(Boolean)
        : [];
    normalized.codex.additionalWritableDirs = Array.isArray(normalized.codex.additionalWritableDirs)
        ? normalized.codex.additionalWritableDirs.map(String).filter(Boolean)
        : [];
    normalized.codex.autoGitCommit = Boolean(normalized.codex.autoGitCommit);
    normalized.codex.autoGitPush = Boolean(normalized.codex.autoGitPush);
    normalized.codex.gitRemote = String(normalized.codex.gitRemote || defaults.codex.gitRemote).trim() || defaults.codex.gitRemote;
    normalized.codex.gitBranch = normalizeGitBranchName(normalized.codex.gitBranch || defaults.codex.gitBranch)
        || normalizeGitBranchName(defaults.codex.gitBranch);
    normalized.codex.gitCommitPrefix = String(normalized.codex.gitCommitPrefix || defaults.codex.gitCommitPrefix).trim() || defaults.codex.gitCommitPrefix;

    return normalized;
}

async function loadConfig() {
    try {
        const content = await fs.readFile(CONFIG_FILE, 'utf8');
        const parsed = JSON.parse(stripJsonComments(content));
        return normalizeConfig(parsed);
    } catch (error) {
        return normalizeConfig({});
    }
}

function getCliArgValue(flagName) {
    const withEqual = process.argv.find((arg) => arg.startsWith(`${flagName}=`));
    if (withEqual) {
        return withEqual.slice(flagName.length + 1).trim();
    }

    const index = process.argv.indexOf(flagName);
    if (index !== -1 && index + 1 < process.argv.length) {
        return String(process.argv[index + 1] || '').trim();
    }

    return '';
}

function hasCliFlag(flagName) {
    return process.argv.includes(flagName) || process.argv.some((arg) => arg.startsWith(`${flagName}=`));
}

function resolveLocalPathFromAppRoot(filePath, fieldName) {
    if (!filePath) {
        return '';
    }

    const root = path.resolve(APP_ROOT);
    const absolutePath = path.resolve(path.isAbsolute(filePath) ? filePath : path.join(APP_ROOT, filePath));
    const insideRoot = absolutePath === root || absolutePath.startsWith(`${root}${path.sep}`);

    if (!insideRoot) {
        throw new Error(`${fieldName} 必须位于 auto-revo-web 目录内，禁止引用外部路径`);
    }

    return absolutePath;
}

async function loadSystemPrompt(config) {
    const configuredPath = String(config.evolution.systemPromptFile || '').trim();
    if (!configuredPath) {
        throw new Error('evolution.systemPromptFile 不能为空');
    }

    const absolutePath = resolveLocalPathFromAppRoot(configuredPath, 'evolution.systemPromptFile');

    try {
        const content = await fs.readFile(absolutePath, 'utf8');
        const text = String(content || '').trim();
        if (!text) {
            throw new Error('系统提示词文件为空');
        }
        return {
            path: absolutePath,
            text
        };
    } catch (error) {
        if (error.message.includes('必须位于 auto-revo-web 目录内')) {
            throw error;
        }
        throw new Error(`读取系统提示词失败: ${error.message}`);
    }
}

function buildLlmRuntimeHint(config) {
    const llmAccess = config.llmAccess || {};
    const url = String(llmAccess.url || '').trim();
    const apiKey = String(llmAccess.apiKey || '').trim();
    const model = String(llmAccess.model || '').trim();
    const apiKeyEnvName = 'LLM_ACCESS_API_KEY';

    // 仅当三项都配置时注入，并避免把明文密钥写入日志或提示词。
    if (!url || !apiKey || !model) {
        return '';
    }

    return [
        '- **可选外部模型调用（运行时注入）:** 如需调用大模型，可使用以下信息：',
        `  - url: ${url}`,
        `  - model: ${model}`,
        `  - api_key_env: ${apiKeyEnvName}（从环境变量读取，不要在日志中输出明文）`
    ].join('\n');
}

function renderSystemPrompt(template, config) {
    const rawTemplate = String(template || '').trim();
    const token = '{{LLM_RUNTIME_HINT}}';
    const runtimeHint = buildLlmRuntimeHint(config);
    const tokenPresent = rawTemplate.includes(token);

    let rendered = tokenPresent
        ? rawTemplate.split(token).join(runtimeHint)
        : rawTemplate;

    if (!tokenPresent && runtimeHint) {
        rendered = `${rendered}\n\n${runtimeHint}`;
    }

    return rendered
        .replace(/\n{3,}/g, '\n\n')
        .trim();
}

function buildIterationPrompt(input) {
    const {
        systemPrompt,
        userPrompt,
        iteration,
        totalIterations,
        previousTail,
        appendIterationContext
    } = input;

    const sections = [
        '【系统提示词（sys-prompt）】',
        String(systemPrompt || '').trim(),
        '',
        '【用户网站方向 Prompt】',
        String(userPrompt || '').trim() || '无',
        ''
    ];

    if (appendIterationContext) {
        sections.push('【本轮迭代上下文】');
        sections.push(`- 轮次: 第 ${iteration} / ${totalIterations} 轮`);
        sections.push(`- 时间: ${new Date().toISOString()}`);
        if (previousTail) {
            sections.push('- 上轮输出摘要（截断）:');
            sections.push(String(previousTail));
        }
        sections.push('- 要求: 基于当前仓库最新代码继续推进，不要重复上一轮。');
        sections.push('');
    }

    sections.push('【执行要求】');
    sections.push('1. 先快速分析当前代码状态和可落地方向。');
    sections.push('2. 直接修改代码实现本轮演进。');
    sections.push('3. 尽量执行必要验证命令（至少语法检查）。');
    sections.push('4. 在输出末尾说明本轮核心改动、验证结果和下一轮建议。');

    return sections.join('\n');
}

function extractTail(text, maxLength) {
    const raw = String(text || '');
    const limit = Number.isFinite(Number(maxLength)) ? Math.max(120, Math.floor(Number(maxLength))) : 1200;
    if (raw.length <= limit) {
        return raw.trim();
    }
    return `...${raw.slice(-limit).trim()}`;
}

function extractCodexSessionId(text) {
    const match = String(text || '').match(/session id:\s*([0-9a-f-]{36})/i);
    return match ? match[1] : '';
}

function buildCodexExecArgs(config, workspaceDir, resumeSessionId) {
    const codexConfig = config.codex || {};
    const normalizedResume = String(resumeSessionId || '').trim();
    const args = normalizedResume
        ? ['exec', 'resume', normalizedResume]
        : ['exec', '--cd', workspaceDir, '--color', 'never'];

    if (codexConfig.model) {
        args.push('--model', codexConfig.model);
    }
    if (codexConfig.profile) {
        args.push('--profile', codexConfig.profile);
    }

    if (codexConfig.dangerouslyBypassApprovalsAndSandbox) {
        args.push('--dangerously-bypass-approvals-and-sandbox');
    } else if (codexConfig.fullAuto) {
        args.push('--full-auto');
    }

    for (const dir of codexConfig.additionalWritableDirs || []) {
        const absoluteDir = resolveLocalPathFromAppRoot(dir, 'codex.additionalWritableDirs');
        args.push('--add-dir', absoluteDir);
    }

    for (const extra of codexConfig.extraArgs || []) {
        args.push(String(extra));
    }

    args.push('-');
    return args;
}

function buildCodexEnvironment(config) {
    const codexConfig = config.codex || {};
    const llmAccess = config.llmAccess || {};
    const env = { ...process.env };

    if (llmAccess.apiKey) {
        env.LLM_ACCESS_API_KEY = String(llmAccess.apiKey).trim();
    }

    for (const [key, value] of Object.entries(codexConfig.environment || {})) {
        if (typeof value === 'string' || typeof value === 'number' || typeof value === 'boolean') {
            env[key] = String(value);
        }
    }

    return env;
}

function runChildProcess(command, args, options) {
    const {
        cwd,
        env,
        stdinData,
        timeoutMs,
        onStdoutLine,
        onStderrLine
    } = options;

    return new Promise((resolve, reject) => {
        const child = spawn(command, args, {
            cwd,
            env,
            stdio: ['pipe', 'pipe', 'pipe']
        });

        let stdout = '';
        let stderr = '';
        let stdoutBuffer = '';
        let stderrBuffer = '';
        let timedOut = false;
        let timeoutId = null;

        function flushLines(buffer, onLine) {
            if (!onLine) {
                return buffer;
            }
            let rest = buffer;
            let splitAt = rest.indexOf('\n');
            while (splitAt !== -1) {
                const line = rest.slice(0, splitAt).replace(/\r$/, '');
                onLine(line);
                rest = rest.slice(splitAt + 1);
                splitAt = rest.indexOf('\n');
            }
            return rest;
        }

        if (Number.isFinite(timeoutMs) && timeoutMs > 0) {
            timeoutId = setTimeout(() => {
                timedOut = true;
                child.kill('SIGTERM');
                setTimeout(() => {
                    if (!child.killed) {
                        child.kill('SIGKILL');
                    }
                }, 3000);
            }, timeoutMs);
        }

        child.stdout.on('data', (chunk) => {
            const text = chunk.toString();
            stdout += text;
            stdoutBuffer += text;
            stdoutBuffer = flushLines(stdoutBuffer, onStdoutLine);
        });

        child.stderr.on('data', (chunk) => {
            const text = chunk.toString();
            stderr += text;
            stderrBuffer += text;
            stderrBuffer = flushLines(stderrBuffer, onStderrLine);
        });

        child.on('error', (error) => {
            if (timeoutId) {
                clearTimeout(timeoutId);
            }
            reject(new Error(`执行命令失败: ${command} ${args.join(' ')} -> ${error.message}`));
        });

        child.on('close', (code) => {
            if (timeoutId) {
                clearTimeout(timeoutId);
            }

            if (onStdoutLine && stdoutBuffer.trim()) {
                onStdoutLine(stdoutBuffer.trim());
            }
            if (onStderrLine && stderrBuffer.trim()) {
                onStderrLine(stderrBuffer.trim());
            }

            resolve({
                code,
                stdout,
                stderr,
                timedOut
            });
        });

        if (stdinData) {
            child.stdin.write(stdinData);
        }
        child.stdin.end();
    });
}

function classifyCodexStreamLine(line, source, state) {
    const content = String(line || '').trim();
    if (!content) {
        return null;
    }

    const lower = content.toLowerCase();
    const phaseTokens = new Set(['user', 'thinking', 'codex', 'exec', 'assistant']);
    if (phaseTokens.has(lower)) {
        state.phase = lower;
        return `[CODEX-PHASE] ${content}`;
    }

    if (/^OpenAI Codex v/i.test(content) || /^(workdir|model|approval|sandbox|session id):/i.test(content)) {
        return `[CODEX-META] ${content}`;
    }

    if (state.phase === 'thinking') {
        return `[CODEX-THINK] ${content}`;
    }
    if (state.phase === 'codex' || state.phase === 'assistant') {
        return `[CODEX-RESP] ${content}`;
    }
    if (state.phase === 'exec') {
        return `[CODEX-EXEC] ${content}`;
    }

    return source === 'stderr' ? `[CODEX-STDERR] ${content}` : `[CODEX-STDOUT] ${content}`;
}

async function runGitCommand(workspaceDir, args, timeoutMs = 30000) {
    return runChildProcess('git', args, {
        cwd: workspaceDir,
        env: process.env,
        stdinData: '',
        timeoutMs
    });
}

async function ensureGitRepositoryAvailable(workspaceDir) {
    const check = await runGitCommand(workspaceDir, ['rev-parse', '--is-inside-work-tree']);
    if (check.code !== 0 || String(check.stdout || '').trim() !== 'true') {
        throw new Error('当前目录不是有效的 git 仓库，无法执行自动提交/推送');
    }
}

async function getCurrentGitBranchName(workspaceDir) {
    const result = await runGitCommand(workspaceDir, ['rev-parse', '--abbrev-ref', 'HEAD']);
    if (result.code !== 0) {
        throw new Error(`读取当前分支失败: ${extractTail(result.stderr || result.stdout, 500)}`);
    }
    return normalizeGitBranchName(result.stdout || '');
}

async function gitRefExists(workspaceDir, refName) {
    const result = await runGitCommand(workspaceDir, ['show-ref', '--verify', '--quiet', refName]);
    if (result.code === 0) {
        return true;
    }
    if (result.code === 1) {
        return false;
    }
    throw new Error(`检查 git 引用失败(${refName}): ${extractTail(result.stderr || result.stdout, 500)}`);
}

async function ensureEvolutionBranchReady(config, workspaceDir, sendUpdate) {
    const codex = config.codex || {};
    const shouldProtectBranch = Boolean(codex.autoGitCommit || codex.autoGitPush);
    if (!shouldProtectBranch) {
        return;
    }

    if (codex.autoGitPush && !codex.autoGitCommit) {
        throw new Error('codex.autoGitPush=true 时必须同时启用 codex.autoGitCommit');
    }

    const targetBranch = normalizeGitBranchName(codex.gitBranch || '');
    if (!targetBranch) {
        throw new Error('codex.gitBranch 不能为空（建议使用 evolution/auto-revo 这类进化分支）');
    }
    if (isMainBranchName(targetBranch)) {
        throw new Error('为避免污染 main 分支，codex.gitBranch 不能是 main，请配置独立分支后再执行');
    }

    await ensureGitRepositoryAvailable(workspaceDir);

    const currentBranch = await getCurrentGitBranchName(workspaceDir);
    if (isMainBranchName(currentBranch)) {
        sendUpdate(`[GIT] 当前分支是 ${currentBranch}，将切换到进化分支 ${targetBranch}`);
    }

    if (currentBranch === targetBranch) {
        sendUpdate(`[GIT] 已位于进化分支: ${targetBranch}`);
        return;
    }

    const localBranchRef = `refs/heads/${targetBranch}`;
    const localBranchExists = await gitRefExists(workspaceDir, localBranchRef);
    if (localBranchExists) {
        const checkoutResult = await runGitCommand(workspaceDir, ['checkout', targetBranch], 60000);
        if (checkoutResult.code !== 0) {
            throw new Error(`切换到分支 ${targetBranch} 失败: ${extractTail(checkoutResult.stderr || checkoutResult.stdout, 600)}`);
        }
        sendUpdate(`[GIT] 已切换到进化分支: ${targetBranch}`);
        return;
    }

    const remoteName = String(codex.gitRemote || 'origin').trim() || 'origin';
    const remoteBranchRef = `refs/remotes/${remoteName}/${targetBranch}`;
    const remoteBranchExists = await gitRefExists(workspaceDir, remoteBranchRef);

    if (remoteBranchExists) {
        sendUpdate(`[GIT] 本地不存在分支 ${targetBranch}，检测到远端分支，正在创建并建立跟踪关系`);
        const createTrackResult = await runGitCommand(workspaceDir, ['checkout', '-b', targetBranch, '--track', `${remoteName}/${targetBranch}`], 60000);
        if (createTrackResult.code !== 0) {
            throw new Error(`创建并跟踪分支 ${targetBranch} 失败: ${extractTail(createTrackResult.stderr || createTrackResult.stdout, 600)}`);
        }
        sendUpdate(`[GIT] 已创建并切换到进化分支: ${targetBranch}（跟踪 ${remoteName}/${targetBranch}）`);
        return;
    }

    sendUpdate(`[GIT] 分支 ${targetBranch} 不存在，正在基于当前提交自动创建`);
    const createResult = await runGitCommand(workspaceDir, ['checkout', '-b', targetBranch], 60000);
    if (createResult.code !== 0) {
        throw new Error(`创建分支 ${targetBranch} 失败: ${extractTail(createResult.stderr || createResult.stdout, 600)}`);
    }
    sendUpdate(`[GIT] 已创建并切换到进化分支: ${targetBranch}`);
}

async function getChangedFilesFromGit(workspaceDir) {
    const status = await runGitCommand(workspaceDir, ['status', '--porcelain']);
    if (status.code !== 0) {
        throw new Error(`读取 git 状态失败: ${extractTail(status.stderr || status.stdout, 600)}`);
    }

    return String(status.stdout || '')
        .split('\n')
        .map((line) => line.trimEnd())
        .filter(Boolean)
        .map((line) => {
            const rawPath = line.slice(3).trim();
            if (rawPath.includes(' -> ')) {
                const parts = rawPath.split(' -> ');
                return parts[parts.length - 1].trim();
            }
            return rawPath;
        });
}

async function commitAndPushChanges(config, workspaceDir, taskPrompt, changedFiles, sendUpdate) {
    const codex = config.codex || {};
    if (!codex.autoGitCommit) {
        sendUpdate('[GIT] autoGitCommit=false，跳过自动提交。');
        return { committed: false, pushed: false, stagedFiles: [] };
    }
    if (!Array.isArray(changedFiles) || changedFiles.length === 0) {
        sendUpdate('[GIT] 未检测到变更，跳过提交。');
        return { committed: false, pushed: false, stagedFiles: [] };
    }

    const targetBranch = normalizeGitBranchName(codex.gitBranch || '');
    if (!targetBranch) {
        throw new Error('codex.gitBranch 不能为空，自动提交已中止');
    }
    if (isMainBranchName(targetBranch)) {
        throw new Error('检测到 codex.gitBranch=main，已阻止自动提交以避免污染主分支');
    }

    await ensureGitRepositoryAvailable(workspaceDir);
    const currentBranch = await getCurrentGitBranchName(workspaceDir);
    if (isMainBranchName(currentBranch)) {
        throw new Error('检测到当前分支为 main，已阻止自动提交以避免污染主分支');
    }
    if (currentBranch !== targetBranch) {
        throw new Error(`当前分支(${currentBranch})与 codex.gitBranch(${targetBranch})不一致，已阻止自动提交`);
    }

    const addResult = await runGitCommand(workspaceDir, ['add', '-A'], 60000);
    if (addResult.code !== 0) {
        throw new Error(`git add 失败: ${extractTail(addResult.stderr || addResult.stdout, 500)}`);
    }

    const stagedResult = await runGitCommand(workspaceDir, ['diff', '--cached', '--name-only']);
    if (stagedResult.code !== 0) {
        throw new Error(`读取暂存区失败: ${extractTail(stagedResult.stderr || stagedResult.stdout, 500)}`);
    }

    const stagedFiles = String(stagedResult.stdout || '').split('\n').map((s) => s.trim()).filter(Boolean);
    if (stagedFiles.length === 0) {
        sendUpdate('[GIT] 暂存区为空，跳过提交。');
        return { committed: false, pushed: false, stagedFiles: [] };
    }

    const summary = String(taskPrompt || '').replace(/\s+/g, ' ').trim().slice(0, 80);
    const commitMessage = `${codex.gitCommitPrefix || 'Codex Evolution:'} ${summary || 'autonomous evolution'}`.trim();
    sendUpdate(`[GIT] 提交变更到分支 ${targetBranch}: ${commitMessage}`);

    const commitResult = await runGitCommand(workspaceDir, ['commit', '-m', commitMessage], 60000);
    if (commitResult.code !== 0) {
        throw new Error(`git commit 失败: ${extractTail(commitResult.stderr || commitResult.stdout, 500)}`);
    }

    if (!codex.autoGitPush) {
        sendUpdate('[GIT] autoGitPush=false，仅保留本地提交。');
        return { committed: true, pushed: false, stagedFiles };
    }

    if (isMainBranchName(targetBranch)) {
        throw new Error('为避免污染 main 分支，禁止自动推送到 main');
    }

    const remoteName = String(codex.gitRemote || 'origin').trim() || 'origin';
    const remoteCheckResult = await runGitCommand(workspaceDir, ['remote', 'get-url', remoteName]);
    if (remoteCheckResult.code !== 0) {
        throw new Error(`git remote(${remoteName}) 不存在或不可用: ${extractTail(remoteCheckResult.stderr || remoteCheckResult.stdout, 500)}`);
    }

    const pushResult = await runGitCommand(workspaceDir, ['push', '-u', remoteName, targetBranch], 120000);
    if (pushResult.code !== 0) {
        throw new Error(`git push 失败: ${extractTail(pushResult.stderr || pushResult.stdout, 500)}`);
    }

    sendUpdate(`[GIT] 已推送到 ${remoteName}/${targetBranch}`);
    return { committed: true, pushed: true, stagedFiles };
}

async function runCodexIteration(input) {
    const {
        config,
        workspaceDir,
        prompt,
        sendUpdate,
        resumeSessionId
    } = input;

    const codex = config.codex || {};
    if (!codex.enabled) {
        throw new Error('codex.enabled=false，已禁用进化执行');
    }

    const command = String(codex.command || 'codex').trim() || 'codex';
    const args = buildCodexExecArgs(config, workspaceDir, resumeSessionId);
    const env = buildCodexEnvironment(config);

    let observedSessionId = '';
    const codexStreamState = { phase: '' };

    sendUpdate(`[SYSTEM] 启动命令: ${command} ${args.join(' ')}`);
    const startAt = Date.now();
    const heartbeat = setInterval(() => {
        const seconds = Math.floor((Date.now() - startAt) / 1000);
        sendUpdate(`[HEARTBEAT] Codex 正在执行中 (${seconds}s)...`);
    }, 15000);

    try {
        const result = await runChildProcess(command, args, {
            cwd: workspaceDir,
            env,
            stdinData: prompt,
            timeoutMs: codex.timeoutMs,
            onStdoutLine: (line) => {
                const message = classifyCodexStreamLine(line, 'stdout', codexStreamState);
                if (!message) {
                    return;
                }
                const sessionId = extractCodexSessionId(message);
                if (sessionId) {
                    observedSessionId = sessionId;
                }
                sendUpdate(message);
            },
            onStderrLine: (line) => {
                const message = classifyCodexStreamLine(line, 'stderr', codexStreamState);
                if (!message) {
                    return;
                }
                const sessionId = extractCodexSessionId(message);
                if (sessionId) {
                    observedSessionId = sessionId;
                }
                sendUpdate(message);
            }
        });

        if (result.timedOut) {
            throw new Error(`Codex 执行超时（${Math.round(codex.timeoutMs / 1000)}s）`);
        }
        if (result.code !== 0) {
            throw new Error(`Codex 执行失败 (exit ${result.code}): ${extractTail(result.stderr || result.stdout, 1200)}`);
        }

        const changedFiles = await getChangedFilesFromGit(workspaceDir);
        const gitResult = await commitAndPushChanges(config, workspaceDir, prompt, changedFiles, sendUpdate);
        const sessionId = observedSessionId || extractCodexSessionId(`${result.stdout}\n${result.stderr}`) || String(resumeSessionId || '');

        return {
            sessionId,
            changedFiles,
            gitResult,
            outputTail: extractTail(result.stdout || result.stderr, 1200)
        };
    } finally {
        clearInterval(heartbeat);
    }
}

function wait(ms) {
    return new Promise((resolve) => setTimeout(resolve, ms));
}

function buildSseWriter(res) {
    function send(payload) {
        const data = typeof payload === 'string' ? { message: payload } : payload;
        res.write(`data: ${JSON.stringify(data)}\n\n`);
    }

    function done() {
        res.write('data: [DONE]\n\n');
        res.end();
    }

    return { send, done };
}

function clampIterations(rawIterations, defaultIterations, maxIterations) {
    const parsed = Number(rawIterations);
    const fallback = Number(defaultIterations);
    const normalized = Number.isFinite(parsed) && parsed > 0 ? Math.floor(parsed) : Math.max(1, Math.floor(fallback || 1));
    return Math.max(1, Math.min(Math.max(1, Math.floor(maxIterations || 1)), normalized));
}

async function executeEvolutionJob(input) {
    const {
        userPrompt,
        requestedIterations,
        sendUpdate,
        shouldStop = () => false
    } = input;

    const config = await loadConfig();
    const workspaceDir = APP_ROOT;
    await ensureEvolutionBranchReady(config, workspaceDir, (message) => {
        sendUpdate(message, { loading: true, status: 'git_prepare' });
    });

    const { text: systemPromptTemplate, path: systemPromptPath } = await loadSystemPrompt(config);
    const systemPrompt = renderSystemPrompt(systemPromptTemplate, config);
    const llmHintEnabled = Boolean(buildLlmRuntimeHint(config));
    const totalIterations = clampIterations(
        requestedIterations,
        config.evolution.defaultIterations,
        config.evolution.maxIterations
    );

    sendUpdate(`[SYSTEM] 系统提示词已加载: ${systemPromptPath}`, { loading: true });
    sendUpdate(`[SYSTEM] 目标工作区: ${workspaceDir}`, { loading: true });
    if (llmHintEnabled) {
        sendUpdate('[SYSTEM] 已启用运行时外部模型调用信息注入（llmAccess）', { loading: true });
    } else {
        sendUpdate('[SYSTEM] 未配置 llmAccess，系统提示词中不包含外部模型调用信息', { loading: true });
    }
    sendUpdate(`[SYSTEM] 已开始迭代，总轮次: ${totalIterations}`, { loading: true, iterations: totalIterations });

    let previousTail = '';
    let resumeSessionId = '';
    let changedCountTotal = 0;
    let executedIterations = 0;
    const reconnectingRounds = Math.max(0, Math.floor(Number(config.codex?.reconnectingRounds) || 0));

    for (let i = 1; i <= totalIterations; i += 1) {
        if (shouldStop()) {
            sendUpdate('[SYSTEM] 客户端连接已断开，已提前停止后续轮次。', {
                loading: false,
                status: 'stopped',
                iterations: executedIterations,
                changedFiles: changedCountTotal
            });
            return {
                status: 'stopped',
                requestedIterations: totalIterations,
                executedIterations,
                changedFiles: changedCountTotal
            };
        }

        sendUpdate(`[AUTO] 第 ${i}/${totalIterations} 轮开始`, {
            loading: true,
            status: 'round_start',
            iteration: i
        });

        const iterationPrompt = buildIterationPrompt({
            systemPrompt,
            userPrompt,
            iteration: i,
            totalIterations,
            previousTail,
            appendIterationContext: config.evolution.appendIterationContext
        });

        let result = null;
        let iterationError = null;
        for (let attempt = 0; attempt <= reconnectingRounds; attempt += 1) {
            try {
                result = await runCodexIteration({
                    config,
                    workspaceDir,
                    prompt: iterationPrompt,
                    sendUpdate: (message) => sendUpdate(message, { loading: true, iteration: i }),
                    resumeSessionId
                });
                iterationError = null;
                break;
            } catch (error) {
                iterationError = error;
                if (attempt >= reconnectingRounds) {
                    break;
                }

                const nextAttempt = attempt + 1;
                sendUpdate(
                    `[RECONNECT] 第 ${i} 轮执行失败，准备重连重试 ${nextAttempt}/${reconnectingRounds}: ${error.message}`,
                    {
                        loading: true,
                        status: 'reconnecting',
                        iteration: i,
                        reconnectAttempt: nextAttempt,
                        reconnectTotal: reconnectingRounds
                    }
                );
                await wait(2000);
            }
        }

        if (!result) {
            throw new Error(`第 ${i} 轮失败: ${iterationError ? iterationError.message : '未知错误'}`);
        }

        previousTail = result.outputTail || '';
        resumeSessionId = result.sessionId || resumeSessionId;
        changedCountTotal += result.changedFiles.length;
        executedIterations = i;

        sendUpdate(`[AUTO] 第 ${i} 轮完成，变更文件: ${result.changedFiles.length}`, {
            loading: true,
            status: 'round_done',
            iteration: i,
            changedFiles: result.changedFiles.length,
            committed: Boolean(result.gitResult?.committed),
            pushed: Boolean(result.gitResult?.pushed)
        });

        if (i < totalIterations && config.evolution.intervalMs > 0) {
            sendUpdate(`[AUTO] 等待 ${config.evolution.intervalMs}ms 进入下一轮`, {
                loading: true,
                status: 'waiting_next_round',
                iteration: i
            });
            await wait(config.evolution.intervalMs);
        }
    }

    sendUpdate(`[SYSTEM] 进化完成，共执行 ${executedIterations} 轮，总变更文件数: ${changedCountTotal}`, {
        loading: false,
        status: 'success',
        iterations: executedIterations,
        changedFiles: changedCountTotal
    });

    return {
        status: 'success',
        requestedIterations: totalIterations,
        executedIterations,
        changedFiles: changedCountTotal
    };
}

function askQuestion(question) {
    return new Promise((resolve) => {
        const rl = readline.createInterface({
            input: process.stdin,
            output: process.stdout
        });
        rl.question(question, (answer) => {
            rl.close();
            resolve(String(answer || '').trim());
        });
    });
}

async function runCliEvolutionMode() {
    if (activeRunId) {
        throw new Error('已有进化任务在运行，请稍后再试');
    }

    const config = await loadConfig();
    let userPrompt = String(getCliArgValue('--prompt') || '').trim();
    if (!userPrompt) {
        if (!process.stdin.isTTY) {
            throw new Error('终端模式未提供 --prompt，且当前不是交互终端');
        }
        userPrompt = await askQuestion('请输入网站方向 Prompt: ');
    }

    if (!userPrompt) {
        throw new Error('Prompt 不能为空');
    }

    const runId = `cli-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
    activeRunId = runId;
    const requestedIterations = getCliArgValue('--iterations') || config.evolution.defaultIterations;

    console.log(`[CLI] 已启动终端自进化模式，runId=${runId}`);
    console.log(`[CLI] 目标轮次=${requestedIterations}`);
    console.log(`[CLI] 用户方向 Prompt=${userPrompt}`);

    try {
        const summary = await executeEvolutionJob({
            userPrompt,
            requestedIterations,
            sendUpdate: (message) => {
                console.log(message);
            },
            shouldStop: () => false
        });

        if (summary.status === 'success') {
            console.log(`[CLI] 完成：执行 ${summary.executedIterations} 轮，总变更文件数=${summary.changedFiles}`);
        } else {
            console.log(`[CLI] 已停止：执行 ${summary.executedIterations} 轮，总变更文件数=${summary.changedFiles}`);
        }
    } finally {
        if (activeRunId === runId) {
            activeRunId = null;
        }
    }
}

app.use(express.json({ limit: '1mb' }));
app.use(express.static(path.join(APP_ROOT, 'public')));

app.get('/api/status', async (req, res) => {
    const config = await loadConfig();
    res.json({
        ok: true,
        running: Boolean(activeRunId),
        defaultIterations: config.evolution.defaultIterations,
        maxIterations: config.evolution.maxIterations
    });
});

app.post('/api/evolve', async (req, res) => {
    const userPrompt = String(req.body?.prompt || '').trim();
    if (!userPrompt) {
        return res.status(400).json({ error: '缺少 prompt 参数' });
    }

    if (activeRunId) {
        return res.status(409).json({ error: '已有进化任务在运行，请等待完成' });
    }

    res.setHeader('Content-Type', 'text/event-stream; charset=utf-8');
    res.setHeader('Cache-Control', 'no-cache');
    res.setHeader('Connection', 'keep-alive');

    const runId = `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
    activeRunId = runId;
    const { send, done } = buildSseWriter(res);

    let clientClosed = false;
    req.on('close', () => {
        clientClosed = true;
    });

    try {
        await executeEvolutionJob({
            userPrompt,
            requestedIterations: req.body?.iterations,
            sendUpdate: (message, extra = {}) => {
                const payload = {
                    message,
                    loading: typeof extra.loading === 'boolean' ? extra.loading : true,
                    runId,
                    ...extra
                };
                send(payload);
            },
            shouldStop: () => clientClosed
        });
        done();
    } catch (error) {
        send({ message: `[ERROR] ${error.message}`, loading: false, status: 'failed', runId });
        done();
    } finally {
        if (activeRunId === runId) {
            activeRunId = null;
        }
    }
});

app.get('*', (req, res) => {
    res.sendFile(path.join(APP_ROOT, 'public', 'index.html'));
});

function describeListenError(error, port) {
    if (!error) {
        return `端口 ${port} 监听失败`;
    }
    if (error.code === 'EADDRINUSE') {
        return `端口 ${port} 已被占用，请更换 server.port 或关闭占用进程`;
    }
    if (error.code === 'EACCES' || error.code === 'EPERM') {
        return `当前环境无权限监听端口 ${port}`;
    }
    return String(error.message || error);
}

async function start() {
    const config = await loadConfig();
    const port = config.server.port || 6161;

    await new Promise((resolve, reject) => {
        const server = app.listen(port, () => {
            console.log(`[auto-revo-web] listening on http://localhost:${port}`);
            resolve();
        });
        server.on('error', (error) => {
            reject(new Error(describeListenError(error, port)));
        });
    });
}

async function main() {
    if (hasCliFlag('--cli-evolve')) {
        await runCliEvolutionMode();
        return;
    }

    await start();
}

main().catch((error) => {
    console.error('[auto-revo-web] start failed:', error);
    process.exitCode = 1;
});

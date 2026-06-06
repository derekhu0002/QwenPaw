import { execFile } from 'node:child_process';
import fs from 'node:fs';
import path from 'node:path';
import { promisify } from 'node:util';
import { tool, type ToolContext, type ToolResult } from '@opencode-ai/plugin';

const execFileAsync = promisify(execFile);

const HANDOFF_STAGES = ['intent-to-implementation', 'implementation-to-coding'];
const SYSTEM_ARCHITECTURE_SCRIPT_CANDIDATES = [
    '.opencode/validator/script/validateSystemArchitecture.js',
    'plugins/.opencode/validator/script/validateSystemArchitecture.js',
    'plugins/opencode/validator/script/validateSystemArchitecture.js',
    'scripts/validateSystemArchitecture.js',
];
const STAGE_HANDOFF_SCRIPT_CANDIDATES = [
    '.opencode/validator/script/validateStageHandoff.js',
    'plugins/.opencode/validator/script/validateStageHandoff.js',
    'plugins/opencode/validator/script/validateStageHandoff.js',
    'scripts/validateStageHandoff.js',
];

function resolveWorkspaceRoot(context: Pick<ToolContext, 'worktree' | 'directory'>): string {
    return process.env.ARGO_REPO_ROOT || context.worktree || context.directory || process.cwd();
}

function resolveScriptPath(workspaceRoot: string, candidates: readonly string[]): { absolutePath: string; relativePath: string } {
    for (const relativePath of candidates) {
        const absolutePath = path.join(workspaceRoot, relativePath);
        if (fs.existsSync(absolutePath)) {
            return { absolutePath, relativePath };
        }
    }

    throw new Error(`Unable to locate validator script. Checked: ${candidates.join(', ')}`);
}

async function runValidatorScript(
    workspaceRoot: string,
    candidates: readonly string[],
    args: readonly string[],
): Promise<ToolResult> {
    const { absolutePath, relativePath } = resolveScriptPath(workspaceRoot, candidates);
    const command = ['node', absolutePath, ...args];
    let stdout = '';
    let stderr = '';
    let exitCode = 0;

    try {
        const result = await execFileAsync(command[0], command.slice(1), {
            cwd: workspaceRoot,
            env: {
                ...process.env,
                ARGO_REPO_ROOT: workspaceRoot,
            },
        });
        stdout = result.stdout || '';
        stderr = result.stderr || '';
    } catch (error) {
        const processError = error as {
            code?: number | string;
            stdout?: string;
            stderr?: string;
            message?: string;
        };
        stdout = processError.stdout || '';
        stderr = processError.stderr || processError.message || '';
        exitCode = typeof processError.code === 'number' ? processError.code : 1;
    }

    return toToolResult('validator', {
        workspaceRoot,
        scriptPath: relativePath,
        command,
        exitCode,
        status: exitCode === 0 ? 'passed' : 'failed',
        stdout: stdout.trim(),
        stderr: stderr.trim(),
    });
}

function normalizeStage(stage: string | undefined): string | undefined {
    if (!stage) {
        return undefined;
    }

    if (!HANDOFF_STAGES.includes(stage)) {
        throw new Error(`Unsupported handoff stage '${stage}'. Expected one of: ${HANDOFF_STAGES.join(', ')}`);
    }

    return stage;
}

function toToolResult(title: string, output: Record<string, unknown>): ToolResult {
    return {
        title,
        output: JSON.stringify(output, null, 2),
        metadata: output,
    };
}

export const validateSystemArchitecture = tool({
    description: 'Run the Argo SystemArchitecture validator from the local opencode validator bundle.',
    args: {},
    async execute(_args, context) {
        return runValidatorScript(
            resolveWorkspaceRoot(context),
            SYSTEM_ARCHITECTURE_SCRIPT_CANDIDATES,
            [],
        );
    },
});

export const validateStageHandoff = tool({
    description: 'Run the Argo stage handoff validator from the local opencode validator bundle.',
    args: {
        stage: tool.schema.string().optional().describe(`Optional handoff stage to validate. Supported values: ${HANDOFF_STAGES.join(', ')}. Omit to validate all supported stages.`),
    },
    async execute(args, context) {
        const stage = normalizeStage(args.stage);
        return runValidatorScript(
            resolveWorkspaceRoot(context),
            STAGE_HANDOFF_SCRIPT_CANDIDATES,
            stage ? [stage] : [],
        );
    },
});

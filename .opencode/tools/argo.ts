import { execFile } from 'node:child_process';
import fs from 'node:fs';
import path from 'node:path';
import { promisify } from 'node:util';
import { tool } from '@opencode-ai/plugin';

const execFileAsync = promisify(execFile);

const DEFAULT_ARCHITECTURE_GRAPH_PATH = 'design/KG/SystemArchitecture.json';
const FAILURE_RECORDS_PATH = 'design/KG/test-failure-records.json';
const EA_TEMPLATE_PATH_CANDIDATES = [
    ['.opencode', 'customtools', 'EA-model-template.feap'],
    ['.opencode', 'EA-model-template.feap'],
    ['eatool', 'EA-model-template.feap'],
    ['EA-model-template.feap'],
    ['Argo.feap'],
] as const;
const HANDOFF_FILES_TO_RESET = [
    ['design', 'KG', 'IntentToImplementationHandoff.json'],
    ['design', 'KG', 'ImplementationToCodingHandoff.json'],
] as const;
const WINDOWS_RESERVED_NAMES = new Set([
    'CON', 'PRN', 'AUX', 'NUL',
    'COM1', 'COM2', 'COM3', 'COM4', 'COM5', 'COM6', 'COM7', 'COM8', 'COM9',
    'LPT1', 'LPT2', 'LPT3', 'LPT4', 'LPT5', 'LPT6', 'LPT7', 'LPT8', 'LPT9',
]);
const SUPPORTED_TEST_SCRIPT_EXTENSIONS = new Set([
    '.js',
    '.cjs',
    '.mjs',
    '.py',
    '.ps1',
    '.cmd',
    '.bat',
]);
const DISALLOWED_ACCEPTANCE_CRITERIA_PATTERNS = [
    /[\r\n]/,
    /[|&;<>]/,
    /^['"].*['"]$/,
    /^(?:npm|pnpm|yarn|npx|node|python|py|powershell|pwsh|cmd|bash|sh)\b/i,
];

type TestStatus = 'passed' | 'failed' | 'missing-criteria' | 'invalid-criteria' | 'missing-file';

interface RawArchitectureGraph {
    elements?: RawArchitectureElement[];
}

interface RawArchitectureElement {
    id?: unknown;
    testcases?: RawArchitectureTestcase[];
}

interface RawArchitectureTestcase {
    name?: unknown;
    description?: unknown;
    type?: unknown;
    acceptanceCriteria?: unknown;
}

interface ExplicitArchitectureTestcase {
    elementId: string;
    testcaseName: string;
    testDescription: string;
    acceptanceCriteria: string;
}

interface ParsedAcceptanceCriteria {
    scriptRelativePath: string;
    selector?: string;
}

interface CommandExecutionResult {
    exitCode: number | null;
    stdout: string;
    stderr: string;
}

interface ArchitectureTestExecutionResult {
    testcaseName: string;
    testDescription: string;
    acceptanceCriteria: string;
    elementId: string;
    resolvedScriptPath: string;
    executionCommand: string;
    status: TestStatus;
    passed: boolean;
    exitCode: number | null;
    durationMs: number;
    stdout: string;
    stderr: string;
}

interface FailedTestRecord {
    testcasename: string;
    testdescription: string;
    acceptanceCriteria: string;
    relatedIntentElementId: string;
    status: Exclude<TestStatus, 'passed'>;
    resolvedScriptPath: string;
    executionCommand: string;
    exitCode: number | null;
    failureError: string;
    stdout: string;
    stderr: string;
}

export const init = tool({
    description: 'OpenCode equivalent of the Copilot /argo-init command. Bootstraps the current workspace with EA template, schema target, handoff reset, and package.json validator scripts.',
    args: {},
    async execute(_args, context) {
        const workspaceRoot = resolveWorkspaceRoot(context);
        const result = await ensureWorkspaceBootstrap(workspaceRoot);
        return toToolResult('command_init', result);
    },
});

export const test = tool({
    description: 'OpenCode equivalent of the Copilot /test command. Executes explicit testcase entries from design/KG/SystemArchitecture.json and refreshes design/KG/test-failure-records.json.',
    args: {
        architecturePath: tool.schema.string().optional().describe('Optional workspace-relative path to the architecture graph. Defaults to design/KG/SystemArchitecture.json.'),
    },
    async execute(args, context) {
        const workspaceRoot = resolveWorkspaceRoot(context);
        const result = await runArchitectureTests(workspaceRoot, args.architecturePath || DEFAULT_ARCHITECTURE_GRAPH_PATH);
        return toToolResult('command_test', result);
    },
});

function resolveWorkspaceRoot(context: { worktree?: string; directory?: string }): string {
    return process.env.ARGO_REPO_ROOT || context.worktree || context.directory || process.cwd();
}

function toToolResult(title: string, output: unknown) {
    return {
        title,
        output: JSON.stringify(output, null, 2),
        metadata: typeof output === 'object' && output !== null ? output as Record<string, unknown> : undefined,
    };
}

async function ensureWorkspaceBootstrap(workspaceRoot: string) {
    const workspaceName = path.basename(workspaceRoot);
    const createdFiles: string[] = [];
    const updatedFiles: string[] = [];
    const removedFiles: string[] = [];
    const skippedSteps: string[] = [];

    const templateSourcePath = resolveTemplateSourcePath(workspaceRoot);
    const targetFeapName = buildTargetFileName(workspaceName);
    const targetFeapPath = path.join(workspaceRoot, targetFeapName);
    if (!fs.existsSync(targetFeapPath)) {
        await fs.promises.copyFile(templateSourcePath, targetFeapPath);
        createdFiles.push(normalizeRelativePath(targetFeapName));
    } else {
        skippedSteps.push(`${normalizeRelativePath(targetFeapName)} already exists`);
    }

    for (const handoffPath of HANDOFF_FILES_TO_RESET) {
        const absolutePath = path.join(workspaceRoot, ...handoffPath);
        if (fs.existsSync(absolutePath)) {
            await fs.promises.rm(absolutePath, { force: true });
            removedFiles.push(normalizeRelativePath(path.relative(workspaceRoot, absolutePath)));
        }
    }

    return {
        workspaceRoot,
        targetFeapName,
        createdFiles,
        updatedFiles,
        removedFiles,
        skippedSteps,
        status: 'ok',
    };
}

function buildTargetFileName(workspaceName: string): string {
    const sanitized = sanitizeFileName(workspaceName) || 'workspace';
    const safeBaseName = WINDOWS_RESERVED_NAMES.has(sanitized.toUpperCase())
        ? `${sanitized}_workspace`
        : sanitized;
    return `${safeBaseName}.feap`;
}

function sanitizeFileName(value: string): string {
    return value
        .replace(/[<>:"/\\|?*\x00-\x1F]/g, '_')
        .replace(/[.\s]+$/g, '')
        .trim();
}

async function runArchitectureTests(workspaceRoot: string, architecturePath: string) {
    const resolvedArchitecturePath = normalizeRelativePath(architecturePath || DEFAULT_ARCHITECTURE_GRAPH_PATH);
    const graphPath = path.join(workspaceRoot, ...resolvedArchitecturePath.split('/'));
    const graph = await readArchitectureGraph(graphPath);
    const explicitTestcases = collectExplicitTestcases(graph);
    const results: ArchitectureTestExecutionResult[] = [];
    const failureRecords: FailedTestRecord[] = [];

    for (const [index, testcase] of explicitTestcases.entries()) {
        logTestcaseStart(index, explicitTestcases.length, testcase);
        const resolvedScriptPath = testcase.acceptanceCriteria
            ? normalizeRelativePath(testcase.acceptanceCriteria)
            : '';

        if (!testcase.acceptanceCriteria) {
            const result = buildExecutionResult({
                testcase,
                resolvedScriptPath: '',
                executionCommand: '',
                status: 'missing-criteria',
                exitCode: null,
                durationMs: 0,
                stdout: '',
                stderr: 'acceptanceCriteria is empty',
            });
            results.push(result);
            logTestcaseFinish(index, explicitTestcases.length, result);
            failureRecords.push(toFailedTestRecord(result));
            continue;
        }

        const validation = validateAcceptanceCriteria(resolvedScriptPath);
        if (!validation.valid) {
            const result = buildExecutionResult({
                testcase,
                resolvedScriptPath,
                executionCommand: '',
                status: 'invalid-criteria',
                exitCode: null,
                durationMs: 0,
                stdout: '',
                stderr: validation.reason || 'acceptanceCriteria must be a direct script file path',
            });
            results.push(result);
            logTestcaseFinish(index, explicitTestcases.length, result);
            failureRecords.push(toFailedTestRecord(result));
            continue;
        }

        const parsedAcceptanceCriteria = parseAcceptanceCriteria(resolvedScriptPath);
        const executionCommand = buildExecutionCommandPreview(parsedAcceptanceCriteria);
        const scriptPath = path.join(workspaceRoot, ...parsedAcceptanceCriteria.scriptRelativePath.split('/'));
        if (!fs.existsSync(scriptPath)) {
            const result = buildExecutionResult({
                testcase,
                resolvedScriptPath,
                executionCommand,
                status: 'missing-file',
                exitCode: null,
                durationMs: 0,
                stdout: '',
                stderr: `test script not found: ${resolvedScriptPath}`,
            });
            results.push(result);
            logTestcaseFinish(index, explicitTestcases.length, result);
            failureRecords.push(toFailedTestRecord(result));
            continue;
        }

        const start = Date.now();
        const execution = await executeAcceptanceScript(parsedAcceptanceCriteria, workspaceRoot, scriptPath);
        const passed = execution.exitCode === 0;
        const result = buildExecutionResult({
            testcase,
            resolvedScriptPath,
            executionCommand,
            status: passed ? 'passed' : 'failed',
            exitCode: execution.exitCode,
            durationMs: Date.now() - start,
            stdout: execution.stdout,
            stderr: execution.stderr,
        });
        results.push(result);
        logTestcaseFinish(index, explicitTestcases.length, result);
        if (!passed) {
            failureRecords.push(toFailedTestRecord(result));
        }
    }

    await writeFailureRecords(workspaceRoot, failureRecords);

    return {
        architecturePath: resolvedArchitecturePath,
        failureRecordsPath: FAILURE_RECORDS_PATH,
        totalTestCases: explicitTestcases.length,
        passedCount: results.filter(result => result.passed).length,
        failedCount: failureRecords.length,
        missingCriteriaCount: results.filter(result => result.status === 'missing-criteria').length,
        results,
        failureRecords,
    };
}

async function readArchitectureGraph(graphPath: string): Promise<RawArchitectureGraph> {
    try {
        return JSON.parse(await fs.promises.readFile(graphPath, 'utf8')) as RawArchitectureGraph;
    } catch (error) {
        throw new Error(`Failed to read architecture graph: ${graphPath}. ${String(error)}`);
    }
}

function buildExecutionResult(input: {
    testcase: ExplicitArchitectureTestcase;
    resolvedScriptPath: string;
    executionCommand: string;
    status: TestStatus;
    exitCode: number | null;
    durationMs: number;
    stdout: string;
    stderr: string;
}): ArchitectureTestExecutionResult {
    return {
        testcaseName: input.testcase.testcaseName,
        testDescription: input.testcase.testDescription,
        acceptanceCriteria: input.testcase.acceptanceCriteria,
        elementId: input.testcase.elementId,
        resolvedScriptPath: input.resolvedScriptPath,
        executionCommand: input.executionCommand,
        status: input.status,
        passed: input.status === 'passed',
        exitCode: input.exitCode,
        durationMs: input.durationMs,
        stdout: input.stdout,
        stderr: input.stderr,
    };
}

async function writeFailureRecords(workspaceRoot: string, records: FailedTestRecord[]): Promise<void> {
    const targetPath = path.join(workspaceRoot, ...FAILURE_RECORDS_PATH.split('/'));
    await fs.promises.mkdir(path.dirname(targetPath), { recursive: true });
    await fs.promises.writeFile(targetPath, JSON.stringify(records, null, 2) + '\n', 'utf8');
}

function toFailedTestRecord(result: ArchitectureTestExecutionResult): FailedTestRecord {
    return {
        testcasename: result.testcaseName,
        testdescription: result.testDescription,
        acceptanceCriteria: result.acceptanceCriteria,
        relatedIntentElementId: result.elementId,
        status: result.status as Exclude<TestStatus, 'passed'>,
        resolvedScriptPath: result.resolvedScriptPath,
        executionCommand: result.executionCommand,
        exitCode: result.exitCode,
        failureError: buildFailureError(result),
        stdout: result.stdout,
        stderr: result.stderr,
    };
}

function buildFailureError(result: ArchitectureTestExecutionResult): string {
    const stderr = result.stderr.trim();
    if (stderr) {
        return stderr;
    }

    const stdout = result.stdout.trim();
    if (stdout) {
        return stdout;
    }

    if (result.exitCode !== null) {
        return `Command exited with code ${result.exitCode}`;
    }

    return `Test status: ${result.status}`;
}

async function executeAcceptanceScript(
    criteria: ParsedAcceptanceCriteria,
    cwd: string,
    scriptPath: string,
): Promise<CommandExecutionResult> {
    if (criteria.selector) {
        return runPythonPytestNodeId(criteria, cwd);
    }

    const extension = path.extname(scriptPath).toLowerCase();
    switch (extension) {
        case '.js':
        case '.cjs':
        case '.mjs':
            return runCommand(process.execPath, [scriptPath], cwd);
        case '.py':
            return runCommand('python', [scriptPath], cwd);
        case '.ps1':
            return runCommand('powershell', ['-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', scriptPath], cwd);
        case '.cmd':
        case '.bat':
            return runCommand(scriptPath, [], cwd);
        default:
            return runCommand(scriptPath, [], cwd);
    }
}

async function runPythonPytestNodeId(
    criteria: ParsedAcceptanceCriteria,
    cwd: string,
): Promise<CommandExecutionResult> {
    return runCommand('python', ['-m', 'pytest', buildPytestNodeId(criteria)], cwd);
}

async function runCommand(command: string, args: string[], cwd: string): Promise<CommandExecutionResult> {
    try {
        const { stdout, stderr } = await execFileAsync(command, args, {
            cwd,
            windowsHide: true,
            maxBuffer: 1024 * 1024 * 10,
        });
        return {
            exitCode: 0,
            stdout: stdout.trim(),
            stderr: stderr.trim(),
        };
    } catch (error) {
        const failure = error as NodeJS.ErrnoException & { stdout?: string; stderr?: string; code?: number | string };
        return {
            exitCode: typeof failure.code === 'number' ? failure.code : 1,
            stdout: String(failure.stdout ?? '').trim(),
            stderr: String(failure.stderr ?? failure.message ?? error).trim(),
        };
    }
}

function validateAcceptanceCriteria(value: string): { valid: boolean; reason?: string } {
    if (!value) {
        return { valid: false, reason: 'acceptanceCriteria is empty' };
    }

    for (const pattern of DISALLOWED_ACCEPTANCE_CRITERIA_PATTERNS) {
        if (pattern.test(value)) {
            return {
                valid: false,
                reason: 'acceptanceCriteria must be a single workspace-relative test entry only, without extra command wrappers or arguments',
            };
        }
    }

    const parsed = parseAcceptanceCriteria(value);
    const extension = path.extname(parsed.scriptRelativePath).toLowerCase();
    if (!SUPPORTED_TEST_SCRIPT_EXTENSIONS.has(extension)) {
        return {
            valid: false,
            reason: `acceptanceCriteria must point to a single executable script file (${Array.from(SUPPORTED_TEST_SCRIPT_EXTENSIONS).join(', ')})`,
        };
    }

    if (parsed.selector && extension !== '.py') {
        return {
            valid: false,
            reason: 'only Python pytest node ids like tests/test_x.py::test_y are supported when acceptanceCriteria includes :: selectors',
        };
    }

    if (parsed.selector && !parsed.selector.trim()) {
        return {
            valid: false,
            reason: 'pytest node id selectors cannot be empty',
        };
    }

    return { valid: true };
}

function parseAcceptanceCriteria(value: string): ParsedAcceptanceCriteria {
    const [scriptRelativePath, ...selectorParts] = value.split('::');
    const normalizedScriptPath = normalizeRelativePath(scriptRelativePath);
    const selector = selectorParts.length > 0 ? selectorParts.join('::').trim() : undefined;
    return {
        scriptRelativePath: normalizedScriptPath,
        selector,
    };
}

function buildPytestNodeId(criteria: ParsedAcceptanceCriteria): string {
    return criteria.selector
        ? `${criteria.scriptRelativePath}::${criteria.selector}`
        : criteria.scriptRelativePath;
}

function buildExecutionCommandPreview(criteria: ParsedAcceptanceCriteria): string {
    if (criteria.selector) {
        return formatCommand('python', ['-m', 'pytest', buildPytestNodeId(criteria)]);
    }

    const scriptPath = criteria.scriptRelativePath;
    const extension = path.extname(scriptPath).toLowerCase();
    switch (extension) {
        case '.js':
        case '.cjs':
        case '.mjs':
            return formatCommand(process.execPath, [scriptPath]);
        case '.py':
            return formatCommand('python', [scriptPath]);
        case '.ps1':
            return formatCommand('powershell', ['-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', scriptPath]);
        case '.cmd':
        case '.bat':
            return formatCommand(scriptPath, []);
        default:
            return formatCommand(scriptPath, []);
    }
}

function formatCommand(command: string, args: string[]): string {
    return [quoteCommandPart(command), ...args.map(quoteCommandPart)].join(' ');
}

function quoteCommandPart(value: string): string {
    return /\s/.test(value) ? `"${value}"` : value;
}

function logTestcaseStart(index: number, total: number, testcase: ExplicitArchitectureTestcase): void {
    const label = formatTestcaseLabel(index, total, testcase.testcaseName);
    console.log(`[START] ${label}`);
    console.log(`        script: ${testcase.acceptanceCriteria || '(missing acceptanceCriteria)'}`);
}

function logTestcaseFinish(index: number, total: number, result: ArchitectureTestExecutionResult): void {
    const label = formatTestcaseLabel(index, total, result.testcaseName);
    const exitCode = result.exitCode === null ? 'n/a' : String(result.exitCode);
    console.log(`[END]   ${label}`);
    console.log(`        result: ${result.status}; exitCode=${exitCode}; durationMs=${result.durationMs}`);
    console.log(`        command: ${result.executionCommand || '(n/a)'}`);
    if (result.stderr) {
        console.log(`        stderr: ${truncateSingleLine(result.stderr)}`);
    } else if (result.stdout) {
        console.log(`        stdout: ${truncateSingleLine(result.stdout)}`);
    }
}

function formatTestcaseLabel(index: number, total: number, testcaseName: string): string {
    return `[${index + 1}/${total}] ${testcaseName || '(unnamed testcase)'}`;
}

function truncateSingleLine(value: string): string {
    const singleLine = String(value).replace(/\s+/g, ' ').trim();
    return singleLine.length > 240 ? `${singleLine.slice(0, 237)}...` : singleLine;
}

function collectExplicitTestcases(graph: RawArchitectureGraph): ExplicitArchitectureTestcase[] {
    const testcases: ExplicitArchitectureTestcase[] = [];

    for (const element of graph.elements ?? []) {
        const elementId = String(element.id ?? '');
        for (const testcase of element.testcases ?? []) {
            testcases.push({
                elementId,
                testcaseName: String(testcase.name ?? ''),
                testDescription: String(testcase.description ?? ''),
                acceptanceCriteria: String(testcase.acceptanceCriteria ?? '').trim(),
            });
        }
    }

    return testcases;
}

function normalizeRelativePath(value: string): string {
    return value.replace(/\\/g, '/').replace(/^\.\//, '').trim();
}

function resolveTemplateSourcePath(workspaceRoot: string): string {
    for (const relativePath of EA_TEMPLATE_PATH_CANDIDATES) {
        const absolutePath = path.join(workspaceRoot, ...relativePath);
        if (fs.existsSync(absolutePath)) {
            return absolutePath;
        }
    }

    throw new Error(
        `EA model template not found. Checked: ${EA_TEMPLATE_PATH_CANDIDATES
            .map(parts => normalizeRelativePath(parts.join('/')))
            .join(', ')}`,
    );
}

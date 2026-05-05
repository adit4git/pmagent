# Legacy Modernizer — Complete Rebuild Specification

> A single document containing everything an autonomous coding agent needs to rebuild this VS Code extension from scratch. No external context required.

---

## 0. What you are building

A **VS Code extension** that converts legacy .NET applications (ASP.NET Core Web APIs + ASP.NET WebForms) into modern Java Spring Boot 3 multi-module projects with React or Angular SPAs and OpenShift CI/CD manifests. The conversion is driven by an **agentic LLM pipeline** with three human review gates and a defect-resolution loop integrated with Jira and Bitbucket via MCP.

The extension activates from VS Code's activity bar, presents a click-driven menu (no typing required), and orchestrates a 9-step pipeline that produces compilable, deployable code from a sample legacy codebase in roughly 15-30 minutes including review.

The user is technical (developer / platform engineer) but lazy. Every interaction is a button click, never a typed command. The output goes into a folder the user picks; the extension never modifies the legacy source.

---

## 1. End-to-end architecture

### 1.1 The three layers

```
┌─────────────────────────────────────────────────────────┐
│  USER LAYER                                             │
│  Activity-bar webview menu · 3 modal review gates      │
│  Live status tree · Output channel logging             │
└─────────────────────────────────────────────────────────┘
                           ▼
┌─────────────────────────────────────────────────────────┐
│  ORCHESTRATOR LAYER                                     │
│  Pipeline state machine (9 steps + 3 gates)            │
│  Generic agent loop (tool dispatch, multi-turn)        │
│  Template copier (variable substitution)               │
│  MCP clients (Jira + Bitbucket via JSON-RPC)           │
│  Resume / delta detection (plan-vs-disk reconciliation)│
└─────────────────────────────────────────────────────────┘
                           ▼
┌─────────────────────────────────────────────────────────┐
│  MODEL LAYER (provider-agnostic)                        │
│  Anthropic Claude · OpenAI · VS Code Copilot LM · Ollama│
└─────────────────────────────────────────────────────────┘
```

### 1.2 The pipeline (9 steps, 3 gates)

```
1. Analyze legacy codebase    → writes _modernizer/inventory.json
2. Generate documentation     → writes _modernizer/LEGACY_DOCUMENTATION.md
3. ⛔ HUMAN GATE: Review docs
4. Convert API                → writes <output>/api/ (Spring Boot 3 multi-module)
5. Convert UI                 → writes <output>/ui/ (React or Angular SPA)
6. ⛔ HUMAN GATE: Review code
7. Generate tests             → writes JUnit, Mockito, Vitest, Testcontainers
8. Generate CI/CD             → writes <output>/deploy/ (Helm + Tekton + Bitbucket)
9. ⛔ HUMAN GATE: Review CI/CD
```

Plus a **defect loop** parallel to the pipeline:

```
Fetch Jira defects (via MCP) → user picks one → defectResolver agent runs →
git checkout -B fix/<JIRA-KEY> → commit → push → Bitbucket MCP opens PR
```

### 1.3 Six-layer agent foundation

This is the most important part of the spec. Every agentic step in this system stacks on these six layers. Skip any of layers 1-4 and you'll reproduce the bugs we spent days finding. Layers 5-6 are polish that earn their place after the foundation works.

| # | Layer | What it does | Symptom if absent |
|---|---|---|---|
| 1 | **Iteration cap ≥ 30** | Lets agent run long enough to do multi-file work | Agent quits at iteration 4-6 with one file written |
| 2 | **Plan-and-verify protocol** | Agent writes JSON plan first, reconciles vs disk before finish | Agent calls `finish` early thinking it's done |
| 3 | **Multi-turn fixup loop** | Verifier finds gaps; fixup is a *loop* not one shot | Verifier identifies missing files but only one gets written per pass |
| 4 | **Structured tool messages** | Anthropic content blocks preserved across turns (not stringified) | Tool calls reappear as text on next turn; conversation rots |
| 5 | **Resume / delta runs** | Detect existing plan, compute delta, run only missing files | 30-min reruns instead of 2-min deltas |
| 6 | **Linter / compiler in loop** | Auto-fix compile errors before declaring done | Agent declares done with code that doesn't compile |

Implementation order is foundation first (1→2→3→4), polish second (5, then 6). Don't ship without 1-4. Layer 6 is optional even at v1.

---

## 2. File and folder layout

Rebuild this exact structure:

```
legacy-modernizer/
├── package.json                      VS Code extension manifest + scripts
├── tsconfig.json                     TS compiler config — outDir: "out"
├── README.md
├── .gitignore                        Must include: out/, node_modules/, .vscode-test/
├── .vscode/
│   ├── launch.json                   Debug config: launches dev host with --extensionDevelopmentPath=${workspaceFolder}
│   └── tasks.json                    Build task: "npm: compile" (runs tsc -p ./)
│
├── src/                              TypeScript source
│   ├── extension.ts                  activate() + deactivate()
│   ├── commands/
│   │   └── index.ts                  Registers every command listed in package.json contributes.commands
│   ├── ui/
│   │   ├── menuProvider.ts           Webview activity-bar panel (the click menu)
│   │   └── statusProvider.ts         Tree view showing per-step status (idle / running / done / failed / awaiting-review)
│   ├── orchestrator/
│   │   ├── orchestrator.ts           Pipeline state machine + step methods
│   │   └── agentLoop.ts              Generic agent loop (THE critical file — see §5)
│   ├── mcp/
│   │   ├── jira.ts                   Jira MCP client (fetch issues by JQL or key)
│   │   └── bitbucket.ts              Bitbucket MCP client (open PR)
│   └── utils/
│       ├── llmClient.ts              LlmClient interface + 4 implementations
│       └── templateCopier.ts         Recursive copy with {{var}} substitution
│
├── skills/                           Agent behavior — markdown playbooks
│   ├── documentation-generator/SKILL.md
│   ├── api-converter/SKILL.md
│   ├── ui-converter/SKILL-react.md
│   ├── ui-converter/SKILL-angular.md
│   ├── test-generator/SKILL.md
│   ├── cicd-generator/SKILL.md
│   └── defect-resolver/SKILL.md
│
├── templates/                        Stable scaffolding (hybrid templates+generation strategy)
│   ├── EXAMPLE_TARGET_ARCHITECTURE.md   The user's intended target stack/conventions
│   ├── README.md                     What's in this folder and how it gets used
│   ├── springboot/
│   │   ├── pom.xml.template          Parent POM with {{artifactId}} {{groupId}} {{javaVersion}} placeholders
│   │   ├── app/
│   │   │   ├── pom.xml.template      Module POM
│   │   │   └── src/main/
│   │   │       ├── java/{{basePackagePath}}/
│   │   │       │   ├── Application.java.template
│   │   │       │   ├── config/CorrelationIdFilter.java.template
│   │   │       │   └── exception/GlobalExceptionHandler.java.template
│   │   │       └── resources/
│   │   │           └── application.yml.template
│   │   ├── .gitignore
│   │   └── .editorconfig
│   ├── react/
│   │   ├── package.json.template
│   │   ├── vite.config.ts
│   │   ├── tsconfig.json
│   │   ├── tailwind.config.js
│   │   ├── postcss.config.js
│   │   ├── index.html.template
│   │   └── src/
│   │       ├── main.tsx.template
│   │       └── lib/
│   │           ├── apiClient.ts.template
│   │           └── auth.ts.template
│   ├── angular/
│   │   ├── package.json.template
│   │   ├── tsconfig.json
│   │   ├── angular.json.template
│   │   └── src/main.ts.template
│   └── openshift/
│       ├── Dockerfile.api            Multi-stage: maven build → JRE 21 runtime
│       ├── Dockerfile.ui             Multi-stage: node build → nginx static
│       ├── helm/
│       │   ├── Chart.yaml.template
│       │   ├── values.yaml.template
│       │   ├── values-dev.yaml.template
│       │   ├── values-prod.yaml.template
│       │   └── templates/
│       │       ├── deployment-api.yaml
│       │       ├── deployment-ui.yaml
│       │       ├── service.yaml
│       │       ├── route.yaml         (OpenShift-specific Route, not Ingress)
│       │       └── configmap.yaml
│       ├── kustomize/                 (alternative to Helm — same shape, kustomize style)
│       ├── tekton/
│       │   ├── pipeline.yaml          build → test → image → deploy → smoke-test
│       │   └── tasks/
│       │       ├── maven-build.yaml
│       │       ├── npm-build.yaml
│       │       ├── buildah-image.yaml
│       │       └── helm-deploy.yaml
│       ├── Jenkinsfile                Equivalent pipeline in Jenkins DSL (alternative)
│       └── bitbucket-pipelines.yml   Equivalent in Bitbucket Pipelines (alternative)
│
├── sample-legacy-code/               Bundled .NET 6 + ASP.NET WebForms example
│   ├── ContosoStore.sln
│   ├── ContosoStore.Api/
│   │   ├── ContosoStore.Api.csproj   net6.0, EF Core SqlServer, JWT auth, AutoMapper
│   │   ├── Controllers/
│   │   │   ├── ProductsController.cs CRUD, [Authorize(Roles="Admin,ProductManager")]
│   │   │   └── OrdersController.cs   [Authorize], pagination, customer/{email} lookup
│   │   ├── Services/
│   │   ├── Models/                    Product, Order, OrderItem, OrderStatus enum
│   │   ├── Data/StoreDbContext.cs
│   │   └── Program.cs
│   └── ContosoStore.Web/
│       ├── ContosoStore.Web.csproj   net48, ASP.NET WebForms
│       ├── Default.aspx + .cs
│       ├── Products.aspx + .cs
│       ├── Cart.aspx + .cs
│       └── Web.config
│
├── docs/                             Reference docs the rebuilder should also produce
│   ├── ARCHITECTURE.md               State-machine diagram + tool overview
│   ├── EXTENDING.md                  Agent-readiness checklist (the 6-layer stack)
│   ├── EXTENDING_AGENT_CAPABILITY.md When to promote SKILL.md to a TS class
│   ├── HUMAN_GATES.md                Per-gate review checklist
│   ├── HYBRID_TEMPLATES_AND_GENERATION.md
│   ├── MCP_SETUP.md                  Connecting Jira + Bitbucket MCP servers
│   ├── TROUBLESHOOTING_INCOMPLETE_CONVERSION.md
│   ├── TROUBLESHOOTING_AGENT_OUTPUT_CHANNELS.md
│   ├── TROUBLESHOOTING_QUOTA_AND_COST.md
│   ├── TROUBLESHOOTING_THROTTLING.md
│   └── TROUBLESHOOTING_RESUMING_PARTIAL_RUNS.md
│
└── out/                              Generated by tsc — gitignored
```

---

## 3. `package.json` — the extension manifest

This is the contract VS Code reads. The rebuilder must produce this with all fields populated. Skipping any field breaks activation, command registration, or settings persistence.

```json
{
  "name": "legacy-modernizer",
  "displayName": "Legacy Modernizer",
  "description": "Agentic .NET → Java Spring Boot + React/Angular + OpenShift converter",
  "version": "0.1.0",
  "publisher": "your-org",
  "engines": { "vscode": "^1.85.0" },
  "categories": ["Other"],
  "main": "./out/extension.js",
  "activationEvents": [
    "onView:modernizer.menuView",
    "onView:modernizer.statusView",
    "onCommand:modernizer.runFullPipeline"
  ],
  "contributes": {
    "viewsContainers": {
      "activitybar": [
        { "id": "modernizer", "title": "Legacy Modernizer", "icon": "$(rocket)" }
      ]
    },
    "views": {
      "modernizer": [
        { "type": "webview", "id": "modernizer.menuView", "name": "Modernization Menu" },
        { "id": "modernizer.statusView", "name": "Pipeline Status" }
      ]
    },
    "commands": [
      { "command": "modernizer.pickLegacyRoot",       "title": "Modernizer: Pick Legacy .NET Codebase" },
      { "command": "modernizer.pickTargetRoot",       "title": "Modernizer: Pick Target Output Folder" },
      { "command": "modernizer.pickArchitectureMd",   "title": "Modernizer: Pick Target Architecture .md" },
      { "command": "modernizer.runFullPipeline",      "title": "Modernizer: Run Full Pipeline" },
      { "command": "modernizer.stepAnalyze",          "title": "Modernizer: Analyze Legacy" },
      { "command": "modernizer.stepGenerateDocs",     "title": "Modernizer: Generate Documentation" },
      { "command": "modernizer.stepReviewDocs",       "title": "Modernizer: Review Docs Gate" },
      { "command": "modernizer.stepConvertApi",       "title": "Modernizer: Convert API to Spring Boot" },
      { "command": "modernizer.stepConvertUi",        "title": "Modernizer: Convert UI to SPA" },
      { "command": "modernizer.stepReviewCode",       "title": "Modernizer: Review Code Gate" },
      { "command": "modernizer.stepGenerateTests",    "title": "Modernizer: Generate Tests" },
      { "command": "modernizer.stepGenerateCicd",     "title": "Modernizer: Generate CI/CD" },
      { "command": "modernizer.stepReviewCicd",       "title": "Modernizer: Review CI/CD Gate" },
      { "command": "modernizer.fetchJiraDefects",     "title": "Modernizer: Fetch Jira Defects" },
      { "command": "modernizer.resolveDefect",        "title": "Modernizer: Resolve Defect → Bitbucket PR" },
      { "command": "modernizer.loadBundledSample",    "title": "Modernizer: Load Bundled Sample Legacy Code" }
    ],
    "configuration": {
      "title": "Legacy Modernizer",
      "properties": {
        "modernizer.modelProvider": {
          "type": "string",
          "enum": ["vscode-copilot", "claude-sonnet", "openai-codex", "local-ollama"],
          "default": "claude-sonnet"
        },
        "modernizer.anthropicModel":      { "type": "string", "default": "claude-sonnet-4-6" },
        "modernizer.anthropicMaxTokens":  { "type": "number", "default": 8192 },
        "modernizer.openaiModel":         { "type": "string", "default": "gpt-4.1" },
        "modernizer.ollamaModel":         { "type": "string", "default": "qwen2.5-coder:32b" },
        "modernizer.ollamaBaseUrl":       { "type": "string", "default": "http://localhost:11434" },
        "modernizer.uiTarget":            { "type": "string", "enum": ["react", "angular"], "default": "react" },
        "modernizer.targetApiStack":      { "type": "string", "enum": ["springboot", "quarkus"], "default": "springboot" },
        "modernizer.maxIterations":       { "type": "number", "default": 40 },
        "modernizer.historyTurns":        { "type": "number", "default": 12 },
        "modernizer.toolResultMaxChars":  { "type": "number", "default": 30000 },
        "modernizer.readFileDefaultMaxBytes": { "type": "number", "default": 100000 },
        "modernizer.readFileHardMaxBytes":    { "type": "number", "default": 250000 },
        "modernizer.interRequestDelayMs": { "type": "number", "default": 1000 },
        "modernizer.enableCritiquePass":  { "type": "boolean", "default": true },
        "modernizer.jiraMcpUrl":          { "type": "string", "default": "" },
        "modernizer.bitbucketMcpUrl":     { "type": "string", "default": "" }
      }
    }
  },
  "scripts": {
    "vscode:prepublish": "npm run compile",
    "compile": "tsc -p ./",
    "watch":   "tsc -watch -p ./",
    "package": "vsce package"
  },
  "devDependencies": {
    "@types/node":   "^20.0.0",
    "@types/vscode": "^1.85.0",
    "typescript":    "^5.3.0",
    "vsce":          "^2.15.0"
  }
}
```

The defaults shown above are the **Balanced preset** — these values produce reliable runs on a mid-sized codebase. Lower values strangle the agent (see §5.3 for why).

---

## 4. `src/extension.ts` — activation

Single responsibility: register everything, then get out of the way.

```ts
import * as vscode from 'vscode';
import { Orchestrator } from './orchestrator/orchestrator';
import { MenuProvider } from './ui/menuProvider';
import { StatusProvider } from './ui/statusProvider';
import { registerCommands } from './commands';

let orchestrator: Orchestrator;

export function activate(context: vscode.ExtensionContext) {
  const output = vscode.window.createOutputChannel('Legacy Modernizer');
  orchestrator = new Orchestrator(context, output);

  const menuProvider = new MenuProvider(context, orchestrator);
  const statusProvider = new StatusProvider(orchestrator);

  context.subscriptions.push(
    vscode.window.registerWebviewViewProvider('modernizer.menuView', menuProvider),
    vscode.window.registerTreeDataProvider('modernizer.statusView', statusProvider),
    output
  );

  registerCommands(context, orchestrator, menuProvider, statusProvider);
}

export function deactivate() { /* nothing to clean up */ }
```

---

## 5. `src/orchestrator/agentLoop.ts` — THE critical file

This is where every bug we found lived. Build it right and most of the system works. Build it wrong and you'll spend days debugging.

### 5.1 Public surface

```ts
export interface AgentLoopOpts {
  orchestrator: Orchestrator;
  agent: string;                    // e.g. 'apiConverter' — used in log lines
  skillPath: string;                // absolute path to skills/<agent>/SKILL.md
  userGoal: string;                 // step-specific instructions; see §5.5
  maxIterations: number;
  writeFiles: boolean;              // true for converter steps; false for read-only steps
  writeRoot?: string;               // sandbox: write_file rejects paths outside this
  legacyRoot?: string;              // sandbox: read_file restricted to this when writeFiles=true
  enableCritiquePass?: boolean;     // default true
  fixupPlanPath?: string;           // absolute path to where the agent's plan is read for verification
}

export async function runAgentLoop(opts: AgentLoopOpts): Promise<string>;
```

### 5.2 Tool schemas (the five tools)

Every agent has the same five tools. Define them once.

```ts
const TOOL_SCHEMAS = [
  {
    name: 'list_dir',
    description: 'List files and subdirectories of a path. Returns names + types.',
    input_schema: {
      type: 'object',
      properties: { path: { type: 'string', description: 'Absolute or workspace-relative path' } },
      required: ['path']
    }
  },
  {
    name: 'read_file',
    description: 'Read a UTF-8 text file. Returns content (truncated if very large).',
    input_schema: {
      type: 'object',
      properties: {
        path: { type: 'string' },
        maxBytes: { type: 'number', description: 'Optional cap; default from settings' }
      },
      required: ['path']
    }
  },
  {
    name: 'search_text',
    description: 'Recursive text search under a path. Returns up to 50 hits with line numbers.',
    input_schema: {
      type: 'object',
      properties: {
        root: { type: 'string' },
        query: { type: 'string' },
        glob: { type: 'string', description: 'Optional file glob filter, e.g. "*.cs"' }
      },
      required: ['root', 'query']
    }
  },
  {
    name: 'write_file',
    description: 'Create or overwrite a file. Path must be inside writeRoot. Parent dirs auto-created.',
    input_schema: {
      type: 'object',
      properties: {
        path: { type: 'string', description: 'Absolute or workspace-relative path inside writeRoot' },
        content: { type: 'string' }
      },
      required: ['path', 'content']
    }
  },
  {
    name: 'finish',
    description: 'Signal the agent has completed its goal. Pass a brief summary.',
    input_schema: {
      type: 'object',
      properties: { summary: { type: 'string' } },
      required: ['summary']
    }
  }
];
```

`dispatchTool` enforces the sandbox: `write_file` rejects any path that resolves outside `writeRoot`. `read_file` warns if reading outside `legacyRoot` ∪ `writeRoot` but allows it (some skills need to read inventory.json from elsewhere).

### 5.3 The main loop — including layer 4 (structured tool messages)

This is the part that took five debugging rounds to get right. Implement it exactly as shown.

```ts
export async function runAgentLoop(opts: AgentLoopOpts): Promise<string> {
  const { orchestrator, agent, skillPath, userGoal, maxIterations,
          writeFiles, writeRoot, legacyRoot, enableCritiquePass = true } = opts;

  const log = (msg: string) => orchestrator.log(`[${agent}] ${msg}`);

  const skill = fs.readFileSync(skillPath, 'utf8');
  const system = buildSystemPrompt(skill);
  const llm = orchestrator.getLlmClient();

  // Conversation as Anthropic-shaped content blocks (CRITICAL — see §5.4)
  const messages: Array<{ role: 'user' | 'assistant'; content: string | any[] }> = [
    { role: 'user', content: userGoal }
  ];

  let finished = false;
  let finishSummary = '';

  for (let i = 0; i < maxIterations && !finished; i++) {
    log(`iteration ${i + 1}/${maxIterations}`);

    // Throttle BETWEEN calls — never inside them
    if (i > 0) await sleep(orchestrator.cfg().get<number>('interRequestDelayMs') ?? 1000);

    const resp = await llm.complete({
      system,
      messages: trimHistory(messages, orchestrator.cfg().get<number>('historyTurns') ?? 12),
      tools: TOOL_SCHEMAS
    });

    if (!resp.toolCalls || resp.toolCalls.length === 0) {
      log(`iteration ${i + 1}: no tool calls, ending main loop`);
      break;
    }

    log(`iteration ${i + 1}: ${resp.toolCalls.length} tool call(s)`);

    // Dispatch every tool in this turn
    const toolResults: Array<{ id: string; name: string; result: string }> = [];
    for (const call of resp.toolCalls) {
      try {
        const result = await dispatchTool(call, { legacyRoot, writeRoot, writeFiles, orchestrator });
        toolResults.push({ id: call.id, name: call.name, result });
        if (call.name === 'finish') { finished = true; finishSummary = call.input.summary || ''; }
      } catch (e: any) {
        log(`tool error (${call.name}): ${e.message}`);
        toolResults.push({ id: call.id, name: call.name, result: `ERROR: ${e.message}` });
      }
    }

    // === LAYER 4 — STRUCTURED TOOL MESSAGES ===
    // The assistant turn must be appended as content BLOCKS (text + tool_use blocks),
    // not as JSON.stringify(toolCalls). Anthropic strictly validates the shape.
    messages.push({
      role: 'assistant',
      content: resp.rawContent ?? buildAssistantContent(resp)
    });
    messages.push({
      role: 'user',
      content: toolResults.map(tr => ({
        type: 'tool_result',
        tool_use_id: tr.id,
        content: truncate(tr.result, orchestrator.cfg().get<number>('toolResultMaxChars') ?? 30000)
      }))
    });
  }

  // === LAYER 3 — VERIFICATION + MULTI-TURN FIXUP LOOP ===
  if (writeFiles && writeRoot && enableCritiquePass) {
    log('critique pass');
    await runVerificationLoop({
      ...opts,
      seedMessages: messages,
      llm,
      system,
      log
    });
  }

  return finishSummary;
}
```

### 5.4 `buildAssistantContent` and the message-shape contract

Every LLM provider must return `rawContent` (Anthropic's content blocks shape). When a provider doesn't (Copilot, OpenAI), the agent loop reconstructs equivalent blocks:

```ts
function buildAssistantContent(resp: CompleteResult): any[] {
  const blocks: any[] = [];
  if (resp.text) blocks.push({ type: 'text', text: resp.text });
  if (resp.toolCalls) {
    for (const tc of resp.toolCalls) {
      blocks.push({ type: 'tool_use', id: tc.id, name: tc.name, input: tc.input });
    }
  }
  if (blocks.length === 0) blocks.push({ type: 'text', text: '(no output)' });
  return blocks;
}
```

The wrong way (which produces silent corruption — we hit this bug):

```ts
// ❌ DON'T DO THIS
messages.push({ role: 'assistant', content: JSON.stringify(resp.toolCalls) });
messages.push({ role: 'user', content: JSON.stringify(toolResults) });
```

Anthropic's API will accept stringified JSON for one or two turns and then start emitting tool calls *as text* on the next turn. The agent appears to stop tool-calling. There's no error message — just a degrading conversation.

### 5.5 Verification loop with multi-turn fixup

```ts
async function runVerificationLoop({
  seedMessages, llm, system, log, agent, fixupPlanPath, writeRoot, ...
}): Promise<void> {
  // Use seedMessages as the basis; reset per pass to avoid stale tool_result chains
  for (let pass = 1; pass <= 3; pass++) {
    log(`verification pass ${pass}/3`);

    // Read the agent's plan
    if (!fs.existsSync(fixupPlanPath)) {
      log(`no plan file at ${fixupPlanPath}; skipping reconciliation`);
      break;
    }
    const plan = JSON.parse(fs.readFileSync(fixupPlanPath, 'utf8'));
    const plannedFiles: Array<{ path: string }> = plan.files ?? [];

    // Reconcile against disk
    const missing = plannedFiles.filter(f => !resolvePlannedPath(f.path, writeRoot));
    if (missing.length === 0) {
      log(`verification clean — all ${plannedFiles.length} planned files exist`);
      return;
    }
    log(`${missing.length}/${plannedFiles.length} planned files missing`);
    missing.slice(0, 10).forEach(m => log(`  - ${m.path}`));
    if (missing.length > 10) log(`  ... and ${missing.length - 10} more`);

    // Build fresh fixup conversation per pass — avoids dangling tool_result blocks
    const fixupMessages: any[] = [
      ...seedMessages.filter(isCleanMessage),
      { role: 'user', content: buildFixupGoal(missing, plannedFiles.length) }
    ];

    const FIXUP_TURNS = Math.min(missing.length * 2 + 5, 50);
    let noToolStreak = 0;
    let fixupDone = false;

    for (let t = 0; t < FIXUP_TURNS && !fixupDone; t++) {
      const resp = await llm.complete({ system, messages: fixupMessages, tools: TOOL_SCHEMAS });

      if (!resp.toolCalls || resp.toolCalls.length === 0) {
        noToolStreak++;
        log(`fixup turn ${t + 1}: no tool calls (streak ${noToolStreak}); nudging`);
        if (noToolStreak >= 3) { log(`fixup: stopping pass after 3 consecutive no-tool turns`); break; }

        // Push back: append the model's text and a sharper user message
        fixupMessages.push({ role: 'assistant', content: buildAssistantContent(resp) });
        fixupMessages.push({
          role: 'user',
          content: `You replied with text instead of tool calls. There are still ${
            recomputeMissing(plannedFiles, writeRoot).length
          } files to write. Issue write_file calls now. Do not summarize.`
        });
        continue;
      }
      noToolStreak = 0;
      log(`fixup turn ${t + 1}: ${resp.toolCalls.length} tool call(s)`);

      const toolResults: any[] = [];
      for (const call of resp.toolCalls) {
        try {
          const result = await dispatchTool(call, { writeRoot, writeFiles: true, orchestrator });
          toolResults.push({ id: call.id, name: call.name, result });
          if (call.name === 'finish') fixupDone = true;
        } catch (e: any) {
          toolResults.push({ id: call.id, name: call.name, result: `ERROR: ${e.message}` });
        }
      }
      fixupMessages.push({ role: 'assistant', content: buildAssistantContent(resp) });
      fixupMessages.push({
        role: 'user',
        content: toolResults.map(tr => ({ type: 'tool_result', tool_use_id: tr.id, content: tr.result }))
      });
    }
  }
}

function buildFixupGoal(missing: any[], total: number): string {
  return `Your plan listed ${total} files but only ${total - missing.length} exist on disk. ` +
         `Write the ${missing.length} missing files now via write_file. ` +
         `Do not call finish until every missing file is written.\n\nMISSING FILES:\n` +
         missing.map(m => `  - ${m.path}`).join('\n');
}

function isCleanMessage(m: any): boolean {
  // Filter out trailing tool_result-only user messages from the seed conversation
  // to prevent unmatched-tool_use_id errors.
  if (m.role !== 'user') return true;
  if (typeof m.content === 'string') return true;
  if (!Array.isArray(m.content)) return true;
  return !m.content.every((b: any) => b.type === 'tool_result');
}
```

---

## 6. `src/orchestrator/orchestrator.ts` — pipeline state machine

### 6.1 State and step list

```ts
type StepId = 'analyze' | 'docs' | 'reviewDocs' | 'convertApi' | 'convertUi'
            | 'reviewCode' | 'tests' | 'cicd' | 'reviewCicd';
type StepStatus = 'idle' | 'running' | 'done' | 'failed' | 'awaiting-review';

const DEFAULT_STEPS: Array<{ id: StepId; label: string; isGate: boolean }> = [
  { id: 'analyze',     label: '① Analyze Legacy Codebase',                 isGate: false },
  { id: 'docs',        label: '② Generate Legacy Documentation',           isGate: false },
  { id: 'reviewDocs',  label: '③ HUMAN GATE: Review Docs',                 isGate: true  },
  { id: 'convertApi',  label: '④ Convert .NET API → Spring Boot',          isGate: false },
  { id: 'convertUi',   label: '⑤ Convert ASP.NET Web → SPA',               isGate: false },
  { id: 'reviewCode',  label: '⑥ HUMAN GATE: Review Generated Code',       isGate: true  },
  { id: 'tests',       label: '⑦ Generate Unit & Integration Tests',       isGate: false },
  { id: 'cicd',        label: '⑧ Generate OpenShift CI/CD Manifests',      isGate: false },
  { id: 'reviewCicd',  label: '⑨ HUMAN GATE: Review CI/CD',                isGate: true  }
];
```

The orchestrator keeps state per step (status, optional output path, optional message) in `vscode.ExtensionContext.workspaceState` so it survives reloads.

### 6.2 The step methods — pattern

Every conversion step follows this pattern:

```ts
async stepConvertApi(): Promise<void> {
  if (!this.ensureSetup()) return;
  this.setStatus('convertApi', 'running');
  const apiRoot = path.join(this.targetRoot(), 'api');

  try {
    // 1. Copy templates with variable substitution (hybrid approach — see §10)
    const archMd = fs.readFileSync(this.archFile(), 'utf8');
    const vars = deriveVarsFromArchitectureMd(archMd, {
      artifactId: path.basename(this.targetRoot()).toLowerCase(),
      groupId: 'com.example',
      basePackage: 'com.example.' + path.basename(this.targetRoot()).toLowerCase()
    });
    const written = copyTemplates(
      path.join(this.context.extensionPath, 'templates/springboot'),
      apiRoot, vars
    );
    this.log(`[apiConverter] copied ${written.length} template files (basePackage=${vars.basePackage})`);

    // 2. Resume / delta detection (Layer 5)
    const planPath = path.join(apiRoot, '_modernizer/api-conversion-plan.json');
    let resumeMode: 'full' | 'resume' | 'reuse' = 'full';
    let missingFromPlan: string[] | null = null;

    if (fs.existsSync(planPath)) {
      const coverage = planCoverage(planPath, apiRoot);
      this.log(`[apiConverter] found existing plan (${coverage.existing}/${coverage.total} files already present)`);

      if (coverage.missing.length === 0) {
        const choice = await vscode.window.showInformationMessage(
          `All ${coverage.total} planned files already exist. Reuse?`,
          { modal: true }, 'Reuse', 'Regenerate', 'Cancel'
        );
        if (choice === 'Cancel' || !choice) { this.setStatus('convertApi', 'idle'); return; }
        if (choice === 'Reuse') resumeMode = 'reuse';
        if (choice === 'Regenerate') { /* delete plan + planned files; resumeMode stays 'full' */ }
      } else {
        const choice = await vscode.window.showInformationMessage(
          `Plan has ${coverage.existing}/${coverage.total} files on disk. Resume the missing ${coverage.missing.length}?`,
          { modal: true }, 'Resume', 'Regenerate', 'Cancel'
        );
        if (choice === 'Cancel' || !choice) { this.setStatus('convertApi', 'idle'); return; }
        if (choice === 'Resume') { resumeMode = 'resume'; missingFromPlan = coverage.missing; }
      }
    }

    if (resumeMode === 'reuse') {
      this.setStatus('convertApi', 'done', 'Reused existing artifacts', apiRoot);
      return;
    }

    // 3. Build user goal — full or delta
    const userGoal = resumeMode === 'resume'
      ? buildResumeGoal(missingFromPlan!, vars)
      : buildFullConversionGoal(vars, this.archFile());

    // 4. Run agent loop with appropriate iteration budget
    const cap = this.cfg().get<number>('maxIterations') ?? 40;
    const iterations = resumeMode === 'resume'
      ? Math.min(cap, Math.max(12, missingFromPlan!.length * 2 + 6))
      : cap;

    await runAgentLoop({
      orchestrator: this,
      agent: 'apiConverter',
      skillPath: path.join(this.context.extensionPath, 'skills/api-converter/SKILL.md'),
      userGoal,
      maxIterations: iterations,
      writeFiles: true,
      writeRoot: apiRoot,
      legacyRoot: this.legacyRoot(),
      fixupPlanPath: planPath
    });

    // 5. Mark done
    this.setStatus('convertApi', 'done', 'Spring Boot generated', apiRoot);
  } catch (e: any) {
    this.setStatus('convertApi', 'failed', e.message);
    this.log(`[apiConverter] FAILED: ${e.message}`);
  }
}
```

The orchestrator's `userGoal` builders are critical. They must enumerate exactly what the agent must produce. See §7 below.

### 6.3 Plan coverage helpers

```ts
export function loadPlannedFiles(planPath: string): Array<{ path: string; type?: string }> {
  if (!fs.existsSync(planPath)) return [];
  try {
    const plan = JSON.parse(fs.readFileSync(planPath, 'utf8'));
    return Array.isArray(plan) ? plan : (plan.files ?? []);
  } catch { return []; }
}

export function resolvePlannedPath(plannedPath: string, writeRoot: string): string | null {
  const workspaceRoot = path.dirname(writeRoot);
  const candidates = [
    path.isAbsolute(plannedPath) ? plannedPath : null,
    path.join(workspaceRoot, plannedPath),
    path.join(writeRoot, plannedPath)
  ].filter(Boolean) as string[];
  for (const c of candidates) if (fs.existsSync(c)) return c;
  return null;
}

export function planCoverage(planPath: string, writeRoot: string) {
  const files = loadPlannedFiles(planPath);
  const missing = files.filter(f => !resolvePlannedPath(f.path, writeRoot)).map(f => f.path);
  return { total: files.length, existing: files.length - missing.length, missing };
}
```

The same `resolvePlannedPath` must be used by the verification loop (§5.5) and by resume detection. They cannot drift.

---

## 7. `userGoal` patterns — the make-or-break prompts

The single most common failure mode in agent-driven code generation is "agent does the easy 10% and stops." Defeat this with **enumerated goals**.

### 7.1 What does NOT work

```
❌ "Convert the legacy .NET API to Spring Boot. Templates already exist; do not regenerate them."
```

The agent over-applies "do not regenerate" and concludes "I shouldn't generate anything except what's missing." It writes one entity and stops.

### 7.2 What works (Layer 2 — plan-and-verify protocol)

```
=== Scaffolding already present (read-only for you) ===
Application.java, application.yml, pom.xml, app/pom.xml,
<basePackagePath>/config/CorrelationIdFilter.java,
<basePackagePath>/exception/GlobalExceptionHandler.java,
.gitignore, .editorconfig.

=== Files YOU MUST PRODUCE — one of each per controller ===
For EVERY controller in inventory.json (currently: ProductsController, OrdersController):
  1. Controller class:    <basePackage>.controller.<Name>Controller
  2. Service interface:   <basePackage>.service.<Name>Service
  3. Service impl:        <basePackage>.service.impl.<Name>ServiceImpl
  4. JPA repository:      <basePackage>.repository.<Name>Repository
  5. JPA entity:          <basePackage>.domain.<Name>
  6. Request DTO record:  <basePackage>.dto.<Name>Request
  7. Response DTO record: <basePackage>.dto.<Name>Response
  8. MapStruct mapper:    <basePackage>.mapper.<Name>Mapper

Plus, ONCE for the whole project:
  - SecurityConfig at <basePackage>.config.SecurityConfig
  - Flyway migration at app/src/main/resources/db/migration/V1__init.sql

=== Path rule (CRITICAL) ===
basePackage is "<basePackage>". Every Java file lives at:
app/src/main/java/<basePackagePath>/<subpackage>/<File>.java
Each file's first non-comment line is "package <basePackage>.<subpackage>;"

=== Procedure (mandatory) ===
1. read_file inventory.json at <writeRoot>/_modernizer/inventory.json (or pipeline-level _modernizer/).
2. read_file each legacy controller in the inventory.
3. write_file a plan to <writeRoot>/_modernizer/api-conversion-plan.json listing
   every Java file you will create with full path. Plan must contain at LEAST 18 files
   for a 2-controller inventory (8 per controller + SecurityConfig + V1__init.sql).
4. Generate every planned file via write_file.
5. Before finish: list_dir and reconcile against the plan. Missing files = write them now.
6. Call finish ONLY when zero files are missing AND the plan threshold is met.

Calling finish with fewer than 18 generated files for this inventory is a FAILURE.
```

The patterns that matter:

- **Enumerate every output type by name.** "8 files per controller" — agents respond strongly to numbered checklists.
- **Replace negatives with positives.** "Scaffolding present (read-only)" instead of "do not regenerate."
- **Name the controllers explicitly** — frequency wins.
- **Set a numerical floor** — "at least 18 files." Then declare anything less a FAILURE.
- **Procedure step 3 forces a written plan** to a known path. The plan is the commitment device that the verifier reconciles against.
- **The plan path must be inside writeRoot** (write_file rejects writes outside writeRoot — an early bug).

### 7.3 Resume / delta `userGoal`

```
You are RESUMING a partial conversion. Most files already exist on disk.
Your only job is to write these <N> missing files:

<basePackage>/service/ProductService.java
<basePackage>/service/impl/ProductServiceImpl.java
... (etc, exact paths from the plan)

Procedure:
1. Read the existing plan at <writeRoot>/_modernizer/api-conversion-plan.json
2. Read inventory.json for context
3. For each missing file, write_file with correct package and content
4. Call finish when all <N> are written.

Do NOT regenerate any other files. Do NOT modify the plan file.
```

---

## 8. `src/utils/llmClient.ts` — provider abstraction

### 8.1 Interface

```ts
export interface ToolCall { id: string; name: string; input: any }

export interface CompleteArgs {
  system: string;
  messages: Array<{ role: 'user' | 'assistant'; content: string | any[] }>;
  tools?: any[];
}

export interface CompleteResult {
  text: string;
  toolCalls?: ToolCall[];
  rawContent?: any[];   // Anthropic content blocks — REQUIRED for layer-4 correctness
}

export interface LlmClient {
  complete(args: CompleteArgs): Promise<CompleteResult>;
}
```

### 8.2 ClaudeSonnetClient (the reference implementation)

```ts
class ClaudeSonnetClient implements LlmClient {
  constructor(private apiKey: string, private model: string, private maxTokens: number) {}

  async complete(args: CompleteArgs): Promise<CompleteResult> {
    const body = {
      model: this.model,
      max_tokens: this.maxTokens,
      system: args.system,
      messages: args.messages,           // Anthropic accepts string OR array content
      tools: args.tools?.map(t => ({
        name: t.name,
        description: t.description,
        input_schema: t.input_schema
      }))
    };

    const resp = await fetch('https://api.anthropic.com/v1/messages', {
      method: 'POST',
      headers: {
        'x-api-key': this.apiKey,
        'anthropic-version': '2023-06-01',
        'content-type': 'application/json'
      },
      body: JSON.stringify(body)
    });

    if (!resp.ok) {
      throw new Error(`Anthropic ${resp.status}: ${await resp.text()}`);
    }
    const data = await resp.json();

    const text = (data.content || [])
      .filter((c: any) => c.type === 'text')
      .map((c: any) => c.text)
      .join('\n');

    const toolCalls: ToolCall[] = (data.content || [])
      .filter((c: any) => c.type === 'tool_use')
      .map((c: any) => ({ id: c.id, name: c.name, input: c.input }));

    return { text, toolCalls, rawContent: data.content || [] };
  }
}
```

**Key**: `rawContent: data.content` — without this the agent loop can't preserve structured tool_use blocks across turns.

### 8.3 Other providers

- **VS Code Copilot LM**: uses `vscode.lm.selectChatModels` + `sendRequest`. Tools are second-class; you pass them as part of the request and parse `tool_calls` from the response. No `rawContent` — `buildAssistantContent` reconstructs equivalent blocks.
- **OpenAI**: standard `/v1/chat/completions` with `tools` and `tool_choice`. Convert OpenAI's `tool_calls[].function.arguments` (JSON string) to `input` object. Use OpenAI message shape (`role: 'tool'`) when feeding tool results back.
- **Local Ollama**: `/api/chat` endpoint. Models like `qwen2.5-coder` and `deepseek-coder` support tool calls. Lower max iterations (slower).

### 8.4 Factory

```ts
export function makeLlmClient(cfg: vscode.WorkspaceConfiguration): LlmClient {
  const provider = cfg.get<string>('modelProvider') ?? 'claude-sonnet';
  switch (provider) {
    case 'claude-sonnet': {
      const apiKey = process.env.ANTHROPIC_API_KEY;
      if (!apiKey) throw new Error('ANTHROPIC_API_KEY not set');
      return new ClaudeSonnetClient(
        apiKey,
        cfg.get<string>('anthropicModel') ?? 'claude-sonnet-4-6',
        cfg.get<number>('anthropicMaxTokens') ?? 8192
      );
    }
    case 'vscode-copilot': return new CopilotLmClient(/* ... */);
    case 'openai-codex':   return new OpenAiCodexClient(/* ... */);
    case 'local-ollama':   return new OllamaClient(/* ... */);
    default: throw new Error(`unknown provider: ${provider}`);
  }
}
```

---

## 9. SKILL.md — agent behavior in markdown

Each skill is a markdown file with a fixed structure. The agent loop reads it as the system prompt, expanded with tool docs.

### 9.1 Skill template

```markdown
# <Agent Name> Skill

## Inputs
What this agent reads. Files, formats, locations.

## Outputs
What this agent writes. Exact paths, file structures.

## Conversion Mapping
Source-to-target mapping table. For api-converter: .NET concepts → Spring Boot equivalents.
For ui-converter: ASP.NET WebForms patterns → React component patterns.

## Procedure
The MANDATORY plan-and-verify steps:
1. Read inputs
2. Write a plan file enumerating outputs
3. Generate each planned output via write_file
4. Reconcile plan against disk (list_dir)
5. Call finish only when reconciled

## Quality bar
Concrete checks the agent should run before finish.
For Java: package declaration matches path; imports resolve; no TODOs.
For React: no inline styles; props typed; api calls go through apiClient.

## Hard rules
Things to NEVER do:
- Never write outside writeRoot
- Never use markdown links inside JSON values (e.g. ASP.NET stays as ASP.NET, not [ASP.NET](http://ASP.NET))
- Never escape \n inside JSON; use real newlines
- For Mermaid: no special chars in node labels; no quotes; no markdown
```

### 9.2 The api-converter SKILL.md (sketch)

```markdown
# API Converter Skill

## Inputs
- inventory.json at <pipeline>/_modernizer/inventory.json
- Legacy .cs files under <legacyRoot>/

## Outputs
- Spring Boot 3 multi-module Maven project under <writeRoot>/
- Plan file at <writeRoot>/_modernizer/api-conversion-plan.json

## Conversion Mapping
| .NET concept                    | Spring Boot equivalent                       |
|---------------------------------|----------------------------------------------|
| [ApiController]                 | @RestController + @RequestMapping            |
| [Authorize(Roles="X")]          | @PreAuthorize("hasRole('X')")                |
| DbContext                       | JpaRepository<Entity, Long>                  |
| EF Core entity                  | @Entity + @Table + @Id                       |
| AutoMapper Profile              | MapStruct interface with @Mapper             |
| IActionResult / Ok() / NotFound | ResponseEntity<T>                            |
| [HttpPost] [Route("...")]       | @PostMapping("...")                          |
| Program.cs / Startup.cs         | Application.java + SecurityConfig.java       |
| appsettings.json                | application.yml                              |

## Procedure
[See §7.2 above — this is the canonical procedure block]

## Quality bar
- Every .java file starts with "package <basePackage>.<sub>;"
- Every entity has @Id and @Table
- Every controller method returns ResponseEntity<T>
- SecurityConfig uses Spring Security 6 (no WebSecurityConfigurerAdapter)
- Flyway V1__init.sql contains CREATE TABLE for every entity

## Hard rules
- Never write outside writeRoot
- Never invent fields not in the legacy entity
- Use Java 21 features where appropriate (records for DTOs, switch expressions)
- Never use javax.* — use jakarta.* (Spring Boot 3)
```

### 9.3 Other skills (one-liner each)

- **documentation-generator**: reads inventory.json, writes LEGACY_DOCUMENTATION.md with Mermaid component diagrams. Mermaid hard rule: no special chars in node labels, no quotes.
- **ui-converter (React)**: ASP.NET WebForm → React functional component. WebForm event handlers → onClick. Server controls → controlled inputs. Sessions → React Query / Zustand.
- **ui-converter (Angular)**: WebForm → Angular component. CodeBehind logic → service injection. Same plan-and-verify procedure.
- **test-generator**: reads generated source, writes JUnit + Mockito for services, @SpringBootTest + Testcontainers for integration, Vitest + RTL for React, Karma for Angular.
- **cicd-generator**: reads target structure, writes Helm chart + Tekton pipeline + Jenkinsfile + bitbucket-pipelines.yml. Multi-stage Dockerfiles.
- **defect-resolver**: reads Jira issue + target code, locates the bug minimally, fixes it, adds a regression test, commits + pushes + opens Bitbucket PR.

---

## 10. Hybrid templates + generation

### 10.1 Why hybrid

Templates are stable across projects: pom.xml, application.yml, Dockerfile, Helm chart skeleton, tsconfig.json. These don't depend on the legacy code. Generating them via LLM wastes tokens and produces inconsistencies between runs.

Generation is project-specific: controllers, services, entities, business components. These depend entirely on the legacy code.

The hybrid strategy: **copy templates first, generate only what the templates can't produce.**

Result: ~50% fewer LLM calls, more deterministic output, lower 429 risk.

### 10.2 templateCopier.ts

```ts
export function copyTemplates(
  templateRoot: string,
  outputRoot: string,
  vars: Record<string, string>
): string[] {
  const written: string[] = [];

  function walk(srcDir: string, dstDir: string) {
    for (const entry of fs.readdirSync(srcDir, { withFileTypes: true })) {
      // Substitute {{var}} in directory names too — for {{basePackagePath}}/
      const dstName = substitute(entry.name, vars);
      const srcPath = path.join(srcDir, entry.name);
      const dstPath = path.join(dstDir, dstName.replace(/\.template$/, ''));

      if (entry.isDirectory()) {
        fs.mkdirSync(dstPath, { recursive: true });
        walk(srcPath, dstPath);
      } else {
        const content = fs.readFileSync(srcPath, 'utf8');
        fs.writeFileSync(dstPath, substitute(content, vars));
        written.push(dstPath);
      }
    }
  }

  walk(templateRoot, outputRoot);
  return written;
}

function substitute(text: string, vars: Record<string, string>): string {
  return text.replace(/\{\{(\w+)\}\}/g, (_, key) => vars[key] ?? `{{${key}}}`);
}
```

Common vars:
- `{{groupId}}` — e.g. `com.example`
- `{{artifactId}}` — derived from output folder name
- `{{basePackage}}` — `groupId.artifactId`
- `{{basePackagePath}}` — `basePackage` with dots → slashes
- `{{javaVersion}}` — `21`
- `{{springBootVersion}}` — `3.3.0`
- `{{appName}}`, `{{namespace}}`, `{{registry}}` for Helm/OpenShift

`deriveVarsFromArchitectureMd(archMd, defaults)` parses simple `Key: Value` lines from the architecture markdown to override defaults.

---

## 11. UI components

### 11.1 menuProvider.ts (the click menu)

A `WebviewViewProvider` that renders an HTML form with sections:

```
1. SETUP
   - Pick Legacy .NET Codebase     → modernizer.pickLegacyRoot
   - Pick Target Output Folder     → modernizer.pickTargetRoot
   - Pick Target Architecture .md  → modernizer.pickArchitectureMd
   - UI Target dropdown (react / angular)
   - Model dropdown (4 providers)

2. PIPELINE (CLICK IN ORDER)
   - 🚀 Run Full Pipeline
   - ① Analyze Legacy Codebase
   - ② Generate Legacy Documentation (requires ①)
   - ⛔ HUMAN GATE: Review Docs (requires ②)
   - ④ Convert .NET API → Spring Boot (requires ③)
   - ⑤ Convert ASP.NET Web → SPA (requires ③)
   - ⛔ HUMAN GATE: Review Generated Code (requires ④ + ⑤)
   - ⑦ Generate Unit & Integration Tests (requires ⑥)
   - ⑧ Generate OpenShift CI/CD Manifests (requires ⑦)
   - ⛔ HUMAN GATE: Review CI/CD (requires ⑧)

3. DEFECT LOOP (JIRA + BITBUCKET VIA MCP)
   - 🐛 Fetch Jira Defects
   - 🔧 Resolve Defect → Bitbucket PR

4. UTILITIES
   - 📦 Load Bundled Sample Legacy Code
```

Each button posts a message to the extension; the extension runs the matching command. Path labels under setup buttons should display `~/...` not `/Users/<username>/...` (privacy + screenshot-friendliness):

```ts
function displayPath(absPath: string): string {
  const home = process.env.HOME || process.env.USERPROFILE || '';
  return home && absPath.startsWith(home) ? '~' + absPath.slice(home.length) : absPath;
}
```

### 11.2 statusProvider.ts (the live status tree)

Implements `vscode.TreeDataProvider` showing each step with an icon:
- `idle`: $(circle-outline)
- `running`: $(sync~spin)
- `done`: $(check) green
- `failed`: $(error) red
- `awaiting-review`: $(eye) orange

Each item's tooltip shows the output path or error message. Clicking a `done` item with a path opens that path in the explorer.

The provider exposes `refresh()` that the orchestrator calls on every state change.

### 11.3 Human gates

When a step transitions to `awaiting-review`, the orchestrator calls:

```ts
const choice = await vscode.window.showInformationMessage(
  `Review <step name> output before proceeding.`,
  { modal: true },
  'Approve', 'Re-run', 'Stop'
);
```

`Approve` flips both the gate AND the upstream generation step to `done` (so the status tree reflects review completion). `Re-run` resets the upstream step to `idle` and re-fires it. `Stop` halts the pipeline.

---

## 12. MCP integration

### 12.1 Pattern

Both Jira and Bitbucket clients are thin JSON-RPC over HTTP wrappers around an MCP server URL the user configures in settings. They expose `tools/call` and the orchestrator invokes specific tools by name.

```ts
async callMcpTool(serverUrl: string, toolName: string, args: any): Promise<any> {
  const resp = await fetch(serverUrl, {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify({
      jsonrpc: '2.0',
      id: Date.now(),
      method: 'tools/call',
      params: { name: toolName, arguments: args }
    })
  });
  const data = await resp.json();
  if (data.error) throw new Error(`MCP ${toolName}: ${data.error.message}`);
  return data.result;
}
```

### 12.2 Jira flow

```
fetchJiraDefects → MCP tool "search_issues" with JQL "project = X AND status = 'Open'"
                 → returns array of issues
                 → vscode.window.showQuickPick to let user pick one
                 → returns picked issue to caller

resolveDefect    → user picks issue from QuickPick
                 → call defectResolver agent with userGoal containing issue summary + description
                 → agent locates code, fixes minimally, adds regression test
                 → orchestrator runs git checkout -B fix/<KEY> + commit + push
                 → MCP tool "create_pr" on Bitbucket → returns PR URL
                 → vscode.window.showInformationMessage with PR link
```

---

## 13. Sample legacy code (ContosoStore)

Bundled in `sample-legacy-code/`. Two projects:

**ContosoStore.Api** (.NET 6):
- `ProductsController.cs`: GET /api/products (with pagination + category filter), GET/{id}, POST [Admin/PM], PUT/{id} [Admin/PM], DELETE/{id} [Admin]
- `OrdersController.cs`: GET/{id} [Authenticated], GET /customer/{email} [Authenticated], POST place-order, PUT/{id}/status [Admin]
- `ProductService.cs`, `OrderService.cs` — IService + Service pattern
- `StoreDbContext.cs` with Product, Order, OrderItem entities + OrderStatus enum
- JWT auth via `Microsoft.AspNetCore.Authentication.JwtBearer`
- AutoMapper profiles

**ContosoStore.Web** (.NET Framework 4.8, ASP.NET WebForms):
- `Default.aspx` (home), `Products.aspx` (catalog with paging), `Cart.aspx` (session-based cart)
- Code-behind in C#
- Web.config with auth + appSettings

This lets the demo run end-to-end without the user supplying their own code. The "Load Bundled Sample" button copies this folder to a target the user picks.

---

## 14. Settings reference (the Balanced preset)

These defaults produce reliable runs on the ContosoStore sample. Document in README.

```json
{
  "modernizer.modelProvider": "claude-sonnet",
  "modernizer.anthropicModel": "claude-sonnet-4-6",
  "modernizer.anthropicMaxTokens": 8192,
  "modernizer.maxIterations": 40,
  "modernizer.historyTurns": 12,
  "modernizer.toolResultMaxChars": 30000,
  "modernizer.readFileDefaultMaxBytes": 100000,
  "modernizer.readFileHardMaxBytes": 250000,
  "modernizer.interRequestDelayMs": 1000,
  "modernizer.enableCritiquePass": true
}
```

**Anti-patterns** (these settings cause silent failures):
- `anthropicMaxTokens < 4096` — truncated code mid-file
- `historyTurns < 8` — agent forgets its own plan
- `maxIterations < 30` for converters — agent quits before finishing
- Dropping `messages[0]` in any history-trim function — loses the user goal
- Throttling *inside* the LLM call (lowering max_tokens) — wrong; throttle *between* calls (`interRequestDelayMs`)

---

## 15. Build, package, run

### 15.1 Local development

```bash
npm install
npm run compile      # populates out/ — VS Code loads from out/extension.js
# Open in VS Code, press F5 → opens dev host with extension loaded
```

`.vscode/launch.json`:

```json
{
  "version": "0.2.0",
  "configurations": [
    {
      "name": "Run Extension",
      "type": "extensionHost",
      "request": "launch",
      "args": ["--extensionDevelopmentPath=${workspaceFolder}"],
      "outFiles": ["${workspaceFolder}/out/**/*.js"],
      "preLaunchTask": "npm: compile"
    }
  ]
}
```

`.vscode/tasks.json`:

```json
{
  "version": "2.0.0",
  "tasks": [
    {
      "type": "npm",
      "script": "compile",
      "group": { "kind": "build", "isDefault": true },
      "problemMatcher": "$tsc"
    }
  ]
}
```

### 15.2 Packaging

```bash
npm install -g vsce
vsce package           # produces legacy-modernizer-0.1.0.vsix
code --install-extension legacy-modernizer-0.1.0.vsix
```

### 15.3 `.gitignore` essentials

```
out/
node_modules/
.vscode-test/
*.vsix
```

---

## 16. Build order (suggested for the rebuilder)

This is the order I'd build it in, working iteratively:

1. **Skeleton** — `package.json`, `tsconfig.json`, `extension.ts` that just registers an output channel. Verify F5 launches the dev host.
2. **Menu webview** — `menuProvider.ts` with all four sections. Buttons can be no-ops; just verify the activity bar icon appears.
3. **Status tree** — `statusProvider.ts` showing 9 step rows. Status updates via stub orchestrator.
4. **`LlmClient` (Claude only)** — interface + `ClaudeSonnetClient.complete()`. Test against Anthropic API directly.
5. **`agentLoop.ts`** — main loop only (no verification yet). Test against a simple "list a directory" goal.
6. **`Orchestrator`** — wire steps 1-2 (analyze + docs). Get the first end-to-end "no human" run working with the sample.
7. **Plan-and-verify** — add the verification loop with multi-turn fixup. Test Step 4 (API converter) until it produces a complete output.
8. **Templates + hybrid** — populate `templates/springboot/`. Wire `copyTemplates()` into `stepConvertApi`.
9. **Human gates** — modal dialogs between steps. Status tree updates.
10. **UI converter, tests, CI/CD** — same loop, different skills.
11. **Resume mode** — plan coverage helpers, three-option prompt.
12. **MCP + defect loop** — Jira fetcher, defect agent, Bitbucket PR.
13. **All four LLM providers** — Copilot, OpenAI, Ollama. Each must return `rawContent` or buildable equivalent.
14. **Polish** — `displayPath()`, `.vscode/launch.json`, README, troubleshooting docs.

If any step from 5-7 misbehaves, walk the six-layer foundation (§1.3) in order. The earliest broken layer explains the symptom.

---

## 17. Acceptance tests

After the rebuild, the tool must pass these:

### Test 1: First-run full pipeline
1. Click "Load Bundled Sample" → picks ContosoStore
2. Click "Run Full Pipeline"
3. Wait ~15 minutes
4. Three modal gates appear in order; approve each
5. Verify: `<output>/api/` has 22+ Java files, compiles with `mvn -DskipTests compile`
6. Verify: `<output>/ui/` has React or Angular SPA, builds with `npm run build`
7. Verify: `<output>/deploy/helm/` has Chart.yaml, values, deployment templates

### Test 2: Resume after interruption
1. Run pipeline; cancel mid-Step-4 (kill the dev host)
2. Re-launch, click Step 4 again
3. Verify: dialog says "X/24 files present. Resume?"
4. Click Resume
5. Verify: completes in <2 minutes; final state matches Test 1

### Test 3: Defect loop
1. Configure Jira MCP URL + Bitbucket MCP URL in settings
2. Click "Fetch Jira Defects"
3. Pick an open defect
4. Click "Resolve Defect"
5. Verify: minimal fix made; regression test added; PR appears in Bitbucket linked to the issue

### Test 4: Provider portability
Run Test 1 with each of the four providers configured. Each should produce a working build.

### Test 5: The six layers (regression check)
- **Layer 1**: with `maxIterations: 6`, Step 4 should fail loudly (not silently truncate). Restore to 40, succeed.
- **Layer 2**: temporarily remove the "write a plan" instruction from the api-converter SKILL.md. Step 4 should produce <10 files. Restore, succeed.
- **Layer 3**: temporarily disable the verification loop. Step 4 should produce 60-80% of files; verifier won't recover. Restore, succeed.
- **Layer 4**: temporarily replace the structured-content append with `JSON.stringify`. Multi-turn conversations degrade after 5-10 turns. Restore, succeed.

If any of these regressions don't reproduce, the corresponding layer isn't actually wired in.

---

## 18. Things the rebuilder should NOT do

- **Don't create `src/agents/` or `src/prompts/` as folders.** Agent behavior lives in `skills/<agent>/SKILL.md` (data, not code) and pipeline plumbing lives in `orchestrator.ts`. Empty scaffold folders age into confusion. Only create folders for files that exist.
- **Don't promote SKILL.md to TypeScript classes** until you have a concrete reason (per-agent tool schemas, per-agent model selection, per-agent pre/post hooks). One-loop-many-skills is the right v1 architecture.
- **Don't centralize all per-agent config into a single `agents.json`.** Per-agent code in a per-agent class is more discoverable than per-agent config in a shared file (when classes are eventually justified).
- **Don't smuggle artifacts through `finish.summary`.** `write_file` is for files; `finish` is for wrap-up text. Smaller models follow this literally; bigger ones mask the bug. Keep channels semantically clean.
- **Don't lower max_tokens to throttle.** Throttle between calls (`interRequestDelayMs`), never inside them. Per-call quality is non-negotiable.
- **Don't reproduce file contents from search/web results in skill files or templates.** Keep templates free of copyrighted material.

---

## 19. The success log line

When the rebuild is complete, a successful Step 4 run produces this log shape:

```
[apiConverter] copied 8 template files (basePackage=com.example.<name>)
[apiConverter] iteration 1/40 → 1: 2 tool call(s)
[apiConverter] iteration 2/40 → 2: 3 tool call(s)
... (typically 8-15 productive iterations) ...
[apiConverter] critique pass
[apiConverter] verification pass 1/3
[apiConverter] verification clean — all 24 planned files exist
```

If a re-run with a present plan:

```
[apiConverter] copied 8 template files
[apiConverter] found existing plan (23/24 files already present)
[apiConverter] iteration 1/12 → 1: 2 tool call(s)
... (typically 4-8 iterations) ...
[apiConverter] verification pass 1/3
[apiConverter] verification clean — all 24 planned files exist
```

Wall time first run: 6-15 minutes. Resume: 1-3 minutes. If your numbers are 5-10× outside these, something in the six-layer foundation is broken.

---

## 20. Final checklist before declaring done

- [ ] F5 launches the dev host and the rocket icon appears in the activity bar
- [ ] All four setup buttons in the menu webview pick paths and persist them across reloads
- [ ] Status tree shows 9 rows and updates live as steps run
- [ ] Step 4 produces 22+ Java files on the first run from the bundled ContosoStore sample
- [ ] `mvn -q -DskipTests compile` succeeds in the generated `api/` folder
- [ ] Re-running Step 4 with an existing plan completes in <3 minutes
- [ ] Three human gates appear as modal dialogs, in order
- [ ] All four model providers (`claude-sonnet`, `vscode-copilot`, `openai-codex`, `local-ollama`) work end-to-end
- [ ] `interRequestDelayMs: 1000` produces no 429s on a Pro Anthropic plan
- [ ] Status tree's `awaiting-review` items flip to `done` on Approve
- [ ] No file path in the menu shows `/Users/<username>/...` — all use `~`
- [ ] `.gitignore` excludes `out/`, `node_modules/`, `.vscode-test/`, `*.vsix`
- [ ] All five troubleshooting docs exist under `docs/`

When all twelve check, you have a working modernizer.

---

## 21. Why this document is enough

Everything above is the result of building this tool, debugging it through five distinct failure modes, and writing down what worked. The six-layer foundation isn't a design choice — it's a list of bugs we hit, in the order we hit them, with the fix for each. The skill files aren't templates we picked — they're prompts that survived contact with real legacy code. The settings aren't defaults from a config wizard — they're values that produced reliable runs after each lower setting produced an outage.

A rebuilder who follows this spec literally will reproduce a working tool. A rebuilder who deviates should expect to rediscover the same bugs in roughly the same order, because the failure modes are intrinsic to agent-driven multi-file code generation, not specific to this implementation.

The gift of this document is not the code. The gift is the *order* — what to build first, what to add second, what looks important but isn't, and what looks unimportant but is the difference between shipping and not.

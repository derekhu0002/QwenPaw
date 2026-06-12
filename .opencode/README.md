# Argo HARNESS for OpenCode

Argo HARNESS 是一套运行在 OpenCode 之上的多 Agent 架构交付工作流。它把一次需求或缺陷处理拆成 **意图设计（Intent Design）-> 实现设计（Implementation Design）-> 编码/修复（Coding/Repair）-> 双层验收审计** 的可追踪流水线，并用知识图谱、交接物、测试入口和校验脚本形成确定性护栏。

核心目标不是让 Agent 直接“写代码试试看”，而是让 Agent 在明确的架构契约、阶段边界和可执行测试信号中协作，持续防止需求漂移、架构漂移、测试漂移和上下文丢失。

## 目录结构概览

```text
.opencode/agents/          Agent 角色定义与权限边界
.opencode/skills/          可触发的工作流能力与专项流程
.opencode/tools/           OpenCode 插件工具：argo、validator
.opencode/validator/script/确定性校验脚本
.opencode/argoschema/      Argo 知识图谱与交接物 JSON Schema
.opencode/commands/        /argoinit、/argotest 命令入口
.opencode/opencode.json    OpenCode 项目配置
```

## Agent 能力总结

| Agent | 定位 | 核心能力 | 关键边界 |
| --- | --- | --- | --- |
| `Orchestrator` | 总调度者 | 接收用户需求或问题，按阶段转交给对应子 Agent；在审计失败时要求对应阶段返工；防止主 Agent 越权直接处理需求或修改实现。 | 禁止直接处理需求、禁止编辑实现产物；只允许调度 `IntentionDesign`、`ImplementationDesign`、`CodingAndReparing`。 |
| `IntentionDesign` | 意图架构设计师 | 以 `design/KG/SystemArchitecture.json` 为第一真相源，澄清需求、维护意图元素/关系/视图/原则/约束/显性验收 testcase，并产出 `IntentToImplementationHandoff.json`。 | 禁止修改业务代码、测试代码、脚本等实现产物；图谱修改必须符合 schema 并通过 validator。 |
| `ImplementationDesign` | 实现架构设计师 | 将意图架构转成仓库内实现架构契约：`OVERALL_ARCHITECTURE.md`、局部 `ARCHITECTURE.md`、显性 testcase 物理入口、关键非显性测试护栏和 `ImplementationToCodingHandoff.json`。 | 禁止修改 `SystemArchitecture.json`；除非明确要求，不直接做业务功能实现；显性测试入口必须具备控制点、观测点和可执行断言。 |
| `CodingAndReparing` | 编码/修复执行者 | 根据 `ImplementationToCodingHandoff.json` 与 `test-failure-records.json` 修复真实实现，执行既有测试入口直到显性测试通过。 | 禁止修改意图图谱、冻结测试资产和冻结契约；禁止通过测试后门、mock 捷径或业务代码测试分支绕过验收。 |
| `ArchimateLanguagistAudit` | ArchiMate 语义审计者 | 审计 `SystemArchitecture.json` 的 schema 合规、ArchiMate 元素/关系语义、语言精确性、视图一致性和追踪质量。 | 默认只审计不改文件；语义正确性高于“看起来能跑”。 |
| `BusinessPartner` | 业务方案拷问者 | 以 MECE 决策树和 SMART 标准严苛拆解业务问题，产出从验收方视角可验证的控制点与观测点。 | 聚焦业务本身，不进入软件架构和代码实现。 |
| `Init` | 初始化命令 Agent | 承接 `/argoinit`，调用 `argo_init` 初始化 Argo 工作区。 | 主要用于启动准备。 |
| `Test` | 测试命令 Agent | 承接 `/argotest`，调用 `argo_test` 执行显性 testcase 并刷新失败记录。 | 主要用于验收测试执行。 |
| `teacher` | 教学型 Agent | 以循序渐进方式解释复杂主题，帮助形成共同理解。 | 辅助学习，不承担主交付链路。 |

## Skills 能力补充

- `orchestrating`：固化总调度规则，要求需求先交给 `IntentionDesign`，意图完成后交给 `ImplementationDesign`，编码完成后双向审计。
- `handoff`：生成阶段交接 markdown，强调只告诉下一阶段“下一步做什么”和“先读哪些具体路径”。
- `coding-delivery-acceptance` / `coding-gap-report`：围绕编码交付是否满足实现架构契约进行验收与返工闭环。
- `implementation-delivery-acceptance` / `impl-gap-report`：围绕实现交付是否满足意图架构契约进行验收与返工闭环。
- `arch-viewer`：用本地 Web Viewer 打开 `SystemArchitecture.json`，按 schema 驱动展示元素、关系、视图和详情。
- `brief`：只基于架构来源更新面向外部采用者的 `INTRODUCTION.md`。
- `grill-me`、`BusinessPartner`：用于方案拷问、决策树遍历和高杠杆问题收敛。
- `improve-codebase-architecture`：在不引入功能需求时，先识别架构优化候选，再交给 grill-me 深挖。
- `distill-agent-rules`：当 Agent 行为偏航时，把一次事故沉淀为可复用规则、约束或 hook 建议。
- `market-research`：做市场、竞品、投资人或技术趋势研究，并要求事实、推断、建议分离。

## 脚本与工具作为护栏的作用

### `validator` 工具与脚本

- `.opencode/tools/validator.ts` 将本地校验脚本包装成 OpenCode 工具：
  - `validator_validateSystemArchitecture`
  - `validator_validateStageHandoff`
- `.opencode/validator/script/validateSystemArchitecture.js` 校验：
  - `design/KG/SystemArchitecture.json` 是否存在、可解析、符合 schema；
  - 元素类型是否匹配 ArchiMate layer/aspect；
  - 关系类型是否匹配 ArchiMate category；
  - 元素、关系、父子、视图引用是否一致。
- `.opencode/validator/script/validateStageHandoff.js` 校验：
  - `IntentToImplementationHandoff.json` 是否包含意图元素、显性 testcase、冻结基线、实现产物要求；
  - `ImplementationToCodingHandoff.json` 是否包含实现契约、显性测试入口、控制点、观测点、失败信号、编码任务计划、冻结文件；
  - 显性 testcase 的 `acceptanceCriteria` 是否是单一工作区相对入口，而不是描述性文本或包裹命令。

这些脚本把“阶段完成”从自然语言承诺变成可执行门禁：validator 不通过，就不能宣称可交接。

### `argo` 工具

- `.opencode/tools/argo.ts` 提供：
  - `argo_init`：初始化工作区，复制 EA 模板，重置阶段交接文件。
  - `argo_test`：读取 `SystemArchitecture.json` 中的显性 testcase，执行其 `acceptanceCriteria` 指向的脚本入口，并刷新 `design/KG/test-failure-records.json`。
- `argo_test` 还会拦截不安全或不稳定的验收入口，例如包含命令包装、管道、换行、shell 操作符、非支持扩展名等情况。

其价值是把“验收测试”固定为图谱中的显性 testcase，而不是让编码 Agent 临时选择测试范围；失败记录也成为 Coding/Repair 的唯一修复队列。

### Schema 作为静态契约

- `.opencode/argoschema/SystemArchitecture.schema.json`：约束意图知识图谱结构。
- `.opencode/argoschema/IntentToImplementationHandoff.schema.json`：约束意图到实现设计的交接物。
- `.opencode/argoschema/ImplementationToCodingHandoff.schema.json`：约束实现设计到编码阶段的交接物。

Schema 与 validator 共同解决两个问题：一是 Agent 不能随意发明字段；二是跨阶段交接必须携带足够上下文，不能只靠对话记忆。

## 整体协作关键流程

1. **用户提出需求或问题**
   - `Orchestrator` 不直接处理，而是交给 `IntentionDesign`。

2. **意图设计阶段**
   - 读取持久记忆、`SystemArchitecture.json`、实现契约和必要仓库证据。
   - 判断是否需要更新意图图谱、实现架构或仅需代码修复。
   - 如果更新图谱，必须遵守 schema 并运行 `validator_validateSystemArchitecture`。
   - 产出并校验 `design/KG/IntentToImplementationHandoff.json`。

3. **实现设计阶段**
   - `ImplementationDesign` 读取意图图谱与上游 handoff。
   - 落盘实现架构契约、稳定边界、测试归属和显性 testcase 入口。
   - 显性 testcase 必须具备控制点、观测点、GIVEN/WHEN/THEN、业务可读断言，并允许在实现缺失时以“正确原因”失败。
   - 产出并校验 `design/KG/ImplementationToCodingHandoff.json`。
   - 显性 testcase 设计在交给编码前需由 `IntentionDesign` 审计。

4. **编码/修复阶段**
   - `CodingAndReparing` 读取实现到编码 handoff、失败记录和架构契约。
   - 只修复 handoff 与 `test-failure-records.json` 指向的问题。
   - 不修改冻结测试和架构契约，不通过 mock 或测试后门伪造通过。
   - 使用 `argo_test` 执行全量显性 testcase，直到全部通过。

5. **双层验收与返工闭环**
   - 编码完成后，`ImplementationDesign` 审计编码交付是否满足实现架构契约。
   - 通过后，`IntentionDesign` 审计实现交付是否满足意图架构。
   - 任一审计失败，交回对应 Agent 修复，直到通过。

## 关键亮点

- **架构图谱优先**：`SystemArchitecture.json` 是意图、约束、语义和验收边界的第一真相源，代码现实不能自动覆盖意图。
- **阶段边界强制化**：意图设计、实现设计、编码修复分别拥有不同可编辑范围，降低 Agent 越权和上下文混乱。
- **显性 testcase 契约化**：验收用例在意图层定义，在实现设计层物理化，在编码层只被执行和满足，避免测试随实现漂移。
- **控制点/观测点标准化**：每个 testcase 必须说明如何触发、观察什么结果，减少“测了但不知道验证什么”的伪测试。
- **预期失败驱动开发**：实现设计阶段可先产出会失败但失败原因正确的测试入口，再把失败记录交给编码阶段作为修复队列。
- **双重审计闭环**：实现架构审计代码，意图架构审计实现，形成从底层交付回到高层意图的闭环。
- **确定性 validator 门禁**：Schema、脚本和工具把自然语言流程变成可执行校验，降低 Agent 幻觉和格式漂移。
- **可视化知识图谱**：`arch-viewer` 让大型架构图谱可浏览、可搜索、可按视图理解。
- **规则可进化**：`distill-agent-rules` 把 Agent 偏航沉淀为后续可执行规则，而不是只做一次性抱怨。

## 解决的业界难题

1. **AI 编码缺少产品意图锚点**
   - 传统 AI 编码常从 issue 直接跳到代码修改，容易满足字面需求却偏离业务意图。Argo 用意图知识图谱和显性 testcase 把“为什么做、验收什么”固定下来。

2. **架构文档与代码长期漂移**
   - Argo 把实现架构契约落到仓库文件，把显性测试入口和失败记录纳入交付链路，并在编码后强制审计，减少文档沦为静态说明。

3. **多 Agent 协作缺少责任边界**
   - 每个 Agent 有明确阶段、权限和产物，Orchestrator 负责调度而不越权，避免多个 Agent 同时改同一层导致语义混乱。

4. **测试被 Agent 随意改弱**
   - 冻结显性 testcase、关键非显性测试和契约文件，编码阶段只能让实现满足测试，不能通过改测试、mock 或后门绕过。

5. **交接依赖聊天上下文，难以复现**
   - 两级 handoff JSON 和持久记忆文件把阶段输出结构化落盘，validator 再确保交接物包含下一阶段必需信息。

6. **验收入口不稳定、不安全或不可执行**
   - `argo_test` 和 handoff validator 要求 `acceptanceCriteria` 是单一工作区相对入口，避免 shell 包装、描述性文本和不可复现命令。

7. **架构语义被自然语言误读**
   - `ArchimateLanguagistAudit` 与 SystemArchitecture validator 同时关注 schema 和 ArchiMate 语义，防止元素类型、关系方向、视图表达被随意解释。

## 推荐使用方式

- 初始化：使用 `/argoinit` 或 `argo_init`。
- 浏览架构：使用 `arch-viewer` skill。
- 新需求/缺陷：交给 `Orchestrator`，由其从 `IntentionDesign` 开始调度。
- 阶段交接：确保对应 handoff JSON 通过 `validator_validateStageHandoff`。
- 编码验收：使用 `argo_test` 执行显性 testcase，并以 `test-failure-records.json` 作为修复队列。
- OpenCode 配置、Agent、Skill 或插件变更后，需要重启 OpenCode，运行中的会话不会热加载这些配置。

# Cursor Agents

本文档结构化总结 `.cursor/agents` 下可用 agent 的职责、能力边界和推荐使用场景。

## 总览

| Agent | 阶段/角色 | 读写能力 | 核心职责 | 适用场景 |
| --- | --- | --- | --- | --- |
| `intention-design` | Intent Design | 可写 | 澄清需求、维护意图架构、产出 Intent-to-Implementation 交接物 | 启动需求设计、重构意图架构、判断变更属于意图/实现/代码哪一层 |
| `implementation-design` | Implementation Design | 可写 | 物理化实现架构契约、显性测试入口、关键护栏和 Implementation-to-Coding 交接物 | 意图已明确，需要设计稳定实现边界、测试入口和后续编码任务 |
| `coding-and-repairing` | Coding/Repair | 可写 | 根据失败记录和交接物修复实现，使既有测试入口通过 | 有明确失败测试记录，或需要按已冻结契约实现/修复代码 |
| `archimate-linguist-audit` | Architecture Audit | 只读 | 审计 `SystemArchitecture.json` 的 ArchiMate 语义、schema 合规和图谱措辞 | 审查架构图谱质量、关系语义、视图一致性和可追溯性 |
| `teacher` | Teaching | 只读 | 以循序渐进方式讲解主题，帮助建立共同理解 | 用户希望深入学习、逐步理解某个技术或设计主题 |

## 阶段协作流

推荐主流程是：

```text
intention-design -> implementation-design -> coding-and-repairing
```

`intention-design` 负责判断需求是否需要更新意图架构，并在必要时维护 `design/KG/SystemArchitecture.json` 与 `design/KG/IntentToImplementationHandoff.json`。

`implementation-design` 接收意图层交接物，把架构落为仓库中的稳定实现契约、测试入口、关键非显性测试和 `design/KG/ImplementationToCodingHandoff.json`。

`coding-and-repairing` 接收实现到编码交接物和失败测试记录，修改业务实现或支撑测试，使冻结入口和失败记录对应的问题通过验证。

`archimate-linguist-audit` 不属于主线写入阶段，主要在意图图谱更新前后做只读语义审计。`teacher` 是横向学习辅助 agent，不直接参与仓库交付链。

## 能力矩阵

| 能力维度 | intention-design | implementation-design | coding-and-repairing | archimate-linguist-audit | teacher |
| --- | --- | --- | --- | --- | --- |
| 澄清需求与设计意图 | 强 | 中 | 弱 | 中 | 强 |
| 修改意图架构图谱 | 强 | 禁止 | 禁止 | 禁止，除非调用方明确要求修复 | 禁止 |
| 设计实现架构契约 | 中 | 强 | 弱 | 弱 | 弱 |
| 修改业务代码 | 禁止，除非用户明确要求 | 默认不做 | 强 | 禁止 | 禁止 |
| 设计/落地显性测试入口 | 定义验收基线 | 强 | 使用既有入口 | 审计入口语义 | 讲解 |
| 修复失败测试 | 不负责 | 不负责 | 强 | 不负责 | 不负责 |
| Schema/语义审计 | 中 | 中 | 弱 | 强 | 弱 |
| 最终交接物 | `IntentToImplementationHandoff.json` | `ImplementationToCodingHandoff.json` | 修复结果与测试结果摘要 | 审计报告 | 学习路径和解释 |

## Agent 详情

### `intention-design`

- 文件：`.cursor/agents/intention-design.md`
- 描述：Intent Design stage: clarify requirements, update intent architecture, and produce IntentToImplementation handoff.
- 模型：`inherit`
- 只读：否

职责结构：

- 判断用户需求应该落在意图架构、实现架构还是普通代码修改层。
- 必要时维护 `design/KG/SystemArchitecture.json`，并严格遵守 `.cursor/argoschema/SystemArchitecture.schema.json`。
- 设计显性 acceptance testcase baseline，并要求显式说明控制点和观测点。
- 产出并验证 `design/KG/IntentToImplementationHandoff.json`，作为下一阶段输入。
- 遵守阶段边界，默认不修改业务代码、测试代码、脚本或实现资产。

关键证据与优先级：

- 先读 `design/persistant-memory/intention-design.md`。
- 再读 `design/KG/SystemArchitecture.json`。
- 然后读 `OVERALL_ARCHITECTURE.md` 和相关 `ARCHITECTURE.md`。
- 当前代码只能作为实现证据，不能自动覆盖意图架构。

### `implementation-design`

- 文件：`.cursor/agents/implementation-design.md`
- 描述：Implementation Design stage: materialize architecture contracts, explicit testcase entrypoints, and ImplementationToCoding handoff.
- 模型：`inherit`
- 只读：否

职责结构：

- 接收 `design/KG/IntentToImplementationHandoff.json`，将意图层要求物理化到仓库。
- 设计稳定实现架构边界、关键接口、依赖方向、测试所有权和实现映射。
- 更新项目根契约 `OVERALL_ARCHITECTURE.md` 与稳定元素目录下的 `ARCHITECTURE.md`。
- 为显性 testcase 建立可执行单一入口，并落地关键断言、控制点和观测点。
- 冻结关键非显性测试，提供普通支撑测试护栏。
- 产出并验证 `design/KG/ImplementationToCodingHandoff.json`。

阶段边界：

- 禁止修改 `design/KG/SystemArchitecture.json`。
- 除非用户明确要求，否则不直接进入业务功能实现。
- 显性 testcase 在业务未补齐时可以预期失败，失败信号应交给 Coding/Repair 阶段。

### `coding-and-repairing`

- 文件：`.cursor/agents/coding-and-repairing.md`
- 描述：Coding/Repair stage: fix implementation from failure records and handoff without rewriting frozen tests.
- 模型：`inherit`
- 只读：否

职责结构：

- 读取 `design/KG/ImplementationToCodingHandoff.json` 和 `design/KG/test-failure-records.json`。
- 以交接物和失败记录作为唯一修复清单，直接修改当前工作区代码。
- 让失败记录中 `acceptanceCriteria` 指向的既有测试入口通过。
- 当实现偏离意图架构或实现架构契约时，优先把实现拉回既定架构。
- 修复后运行失败入口和全量显性测试入口。

阶段边界：

- 禁止修改 `design/KG/SystemArchitecture.json`、冻结测试资产及其关联契约。
- 禁止通过测试专用后门、业务代码 mock 改写、测试开关或伪造返回字段来绕过验收。
- 如新增或调整外部接口，必须同步更新项目根目录 `INTRODUCTION.md`。

### `archimate-linguist-audit`

- 文件：`.cursor/agents/archimate-linguist-audit.md`
- 描述：Audit `design/KG/SystemArchitecture.json` for ArchiMate semantics, schema compliance, and graph wording.
- 模型：`inherit`
- 只读：是

职责结构：

- 从 ArchiMate 语言学视角审计 `design/KG/SystemArchitecture.json`。
- 检查 schema 合规、元素类型、关系方向、关系语义、视图一致性和 traceability。
- 识别 `name`、`description`、`statement`、`browser_path`、testcase 文本中的语义弱点或歧义。
- 返回精确审计报告，不默认编辑仓库文件。

审计证据顺序：

1. `design/KG/SystemArchitecture.json`
2. `.cursor/argoschema/SystemArchitecture.schema.json`
3. `OVERALL_ARCHITECTURE.md`
4. 必要时读取相关本地 `ARCHITECTURE.md`

输出重点：

- findings 应按严重程度排序。
- 每条 finding 应包含 severity、location、category、problem、why it matters、minimal correction。
- 即使 schema 通过，也应继续审计语义缺陷。

### `teacher`

- 文件：`.cursor/agents/teacher.md`
- 描述：Step-by-step teaching partner.
- 模型：`inherit`
- 只读：是

职责结构：

- 作为逐步教学伙伴，帮助用户深入理解主题。
- 通过分阶段解释暴露底层知识，直到与用户达成共同理解。
- 适合讲解架构、测试设计、ArchiMate、代码实现思路、工具使用流程等主题。

边界：

- 只读，不应修改仓库文件。
- 更适合教学、引导和概念澄清，不适合作为交付型编码 agent。

## 选择指南

- 需求还不清楚，或者需要判断是否应改意图架构：用 `intention-design`。
- 意图已经明确，需要设计仓库结构、契约、测试入口和编码交接物：用 `implementation-design`。
- 已有失败记录或实现缺口，需要直接修代码并跑测试：用 `coding-and-repairing`。
- 需要评审 `SystemArchitecture.json` 的 ArchiMate 语义、schema 或图谱措辞：用 `archimate-linguist-audit`。
- 用户想学习或希望逐步讲透一个主题：用 `teacher`。

## 当前文件状态备注

- 当前可确认并读取的 agent 定义共有 5 个：`intention-design`、`implementation-design`、`coding-and-repairing`、`archimate-linguist-audit`、`teacher`。
- 工具索引曾命中 `.cursor/agents/business-partner.md`，但该路径当前无法读取，且未出现在 `git ls-files -- .cursor/agents` 的跟踪列表中；本文档未为其编造职责。
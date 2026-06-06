# Repository Mapping

本文件说明参考 skill 中的概念，如何映射到 Argo 当前 ontology 和 workflow，避免引入平行机制。

## Fact Sources

先按 Argo 当前 workflow 的事实顺序读取：

1. `design/KG/SystemArchitecture.json`
2. `OVERALL_ARCHITECTURE.md`
3. 受影响稳定目录下的 `ARCHITECTURE.md`
4. 只有在上面三层不足以回答问题时，才继续读取相关代码、测试、脚本、配置

若以下交接物存在且与当前问题直接相关，可按需读取：

- `design/KG/IntentToImplementationHandoff.json`
- `design/KG/ImplementationToCodingHandoff.json`

## Mapping Rules

不要引入 `CONTEXT.md`、ADR 文件或任何平行的主事实源。参考 skill 中提到的上下文、约束、决策记录，在本仓库中统一映射到：

- `design/KG/SystemArchitecture.json`
- `OVERALL_ARCHITECTURE.md`
- 局部 `ARCHITECTURE.md`
- 现有 handoff JSON

## Argo-Specific Constraints

- 保持在当前仓库的 truth sources 内工作
- 优先推动契约澄清、稳定模块边界和依赖方向修正，而不是扩张功能
- 除非用户明确要求进入实现，否则不要修改代码、测试、脚本或设计资产
- 如果某个候选会冲击现有已接受的架构契约，要明确指出这是“需要重开契约讨论”，不要把它包装成普通重构
- 如果最终判断只是 Implementation Design 或 Coding/Repair 问题，要明确说明“不需要改 intent”
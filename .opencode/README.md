# Argo HARNESS for OpenCode

这个目录对应的是 Argo 的 OpenCode 版本说明。它把同一套 HARNESS 工程方法映射成 OpenCode 可直接消费的 agent、command、tool、validator 和全局指令。

如果你希望在 OpenCode 中也保持和 Copilot 版一致的阶段边界、测试入口和回归闭环，这个版本就是入口。

## 你会得到什么

OpenCode 版的主要资产位于 `.opencode/`：

- `opencode.json`：OpenCode 配置入口
- `GLOBAL_INSTRUCTIONS.md`：全局指令
- `agents/`：Init、IntentionDesign、ImplementationDesign、CodingAndReparing、Test
- `commands/`：如 `argo_init`、`argo_test`
- `tools/`：Argo 工具与 validator 工具
- `validator/` 与 `argoschema/`：结构校验与阶段交接校验资产

## 快速安装

### 1. 准备 OpenCode 配置

先检查 `.opencode/opencode.json` 中的这些内容：

- `model`
- `provider`
- `mcp`
- `instructions`

当前仓库默认示例里，`DeepSeek_custom_provider.options.apiKey` 仍是占位值 `XXX`。你需要把它替换成真实可用的 API Key。

### 2. 确认工作区最小输入

目标工作区至少应具备：

```text
design/KG/SystemArchitecture.json
OVERALL_ARCHITECTURE.md
src/
tests/
```

### 3. 确认 OpenCode 能读到 `.opencode/`

这个版本的运行前提，不是安装一个 VS Code 扩展，而是让 OpenCode 直接消费当前仓库中的 `.opencode/` 资产。因此要确保你的 OpenCode 运行环境把当前仓库根目录作为工作区打开，并能加载 `.opencode/opencode.json`。

## 快速上手

### 1. 先做初始化

如果目标工作区还没有准备好 Argo 所需资产，先使用：

- `Init` agent
- 或 `argo_init` command

它会把 schema、validator 和模板等基础资产投影到目标工作区。

### 2. 按阶段推进，而不是直接自由提示

推荐顺序如下：

1. 用 `IntentionDesign` agent 澄清意图边界。
2. 用 `ImplementationDesign` agent 落盘实现架构契约与测试入口。
3. 用 `Test` agent 或 `argo_test` command 刷新失败记录。
4. 用 `CodingAndReparing` agent 基于失败记录修复实现。
5. 重复 `Test -> Coding/Repair`，直到显性 testcase 通过。

### 3. 第一轮上手只需要记住这一条闭环

```text
先澄清 intent
再落盘 implementation contracts 和 tests
再执行 test
最后基于 failure records 进入 coding/repair
```

## 版本理念

OpenCode 版与 Copilot 版共享同一套 HARNESS 原则：

- 人类通过 ArchiMate 意图模型掌握方向盘。
- 目标通过分层测试用例持续向实现层传导。
- 架构最终沉淀进代码仓目录结构、契约文件、测试入口和 failure records。
- 先 Intent，后 Implementation，最后 Coding
- 测试先是契约，其次才是脚本
- failure records 是 Coding/Repair 的直接输入
- agent 要在受约束的工程系统里工作，而不是在自由提示里碰运气

因此，OpenCode 版的重点也不是“多几个 agent 名称”，而是让阶段交接、测试入口和验证脚本在 OpenCode 环境里继续成立。

## 常用入口

在 OpenCode 版本里，最常用的是这些入口：

- `Init`
- `IntentionDesign`
- `ImplementationDesign`
- `CodingAndReparing`
- `Test`
- `argo_init`
- `argo_test`

## 常用验证资产

OpenCode 版本保留了两类核心验证：

- `validateSystemArchitecture`
- `validateStageHandoff`

对应实现位于：

- `.opencode/tools/validator.ts`
- `.opencode/validator/script/validateSystemArchitecture.js`
- `.opencode/validator/script/validateStageHandoff.js`

没有 schema 校验和 handoff 校验的“阶段完成”，在 Argo 里不算真正完成。

## 适合谁

OpenCode 版更适合这些场景：

- 你希望把 Argo 工作流接到 OpenCode 代理体系里
- 你已经接受 `.opencode/` 目录作为主要运行入口
- 你希望在不同 agent 平台之间复用同一套 HARNESS 工程方法

如果把顺序打乱，OPENCODE 里的 Argo 也会失去它最重要的价值：不是“多一个 agent”，而是“把架构边界、测试边界和阶段交接变成显性、可验证、可复用的工程流程”。
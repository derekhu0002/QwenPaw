# QwenPaw Implementation Architecture Temp View

## Scope

This temporary view summarizes the current implementation architecture from `design/persistant-memory/implementation-design.md` and the implementation contracts it points to. It focuses on the security/audit delivery slice that repeatedly appears in the implementation memory: local runtime evidence, Security Center cloud boundary, operator visibility, explicit acceptance entrypoints, and the implementation-to-coding handoff.

## 实现架构图

```mermaid
flowchart LR
    subgraph LocalProduct["本地 QwenPaw 产品边界"]
        CLI["Local Operator CLI\nsrc/qwenpaw/cli"]
        Runtime["Backend Runtime\nsrc/qwenpaw"]
        AppGlue["App / Transport Glue\nsrc/qwenpaw/app"]
        Security["Local Security Audit Foundation\nsrc/qwenpaw/security"]
        ToolGuard["High-Risk Tool Guard\nsrc/qwenpaw/security/tool_guard"]
        LocalEvidence["本地证据与审计链\nSecurityContext / confirmation / ledger / heartbeat"]
    end

    subgraph SecurityCenter["Security Center 独立部署边界\ndeploy"]
        Api["Security Center Backend API\ndeploy/api"]
        Store["Cloud Shadow State / Lease Registry\nAPI durable store"]
        Web["Operator Web\ndeploy/web"]
        Stream["Realtime Alert Stream\nSSE or WebSocket"]
    end

    subgraph Verification["验证与治理边界"]
        ExplicitTests["显式安全验收入口\ntests/integration/security"]
        ContractTests["契约与回归测试\ntests/contract/security"]
        ArchGuards["架构守卫\ntests/architecture"]
        Handoff["ImplementationToCodingHandoff\ndesign/KG"]
        Argo["Argo / validator commands\nnpm run validate:* / npm run test:argo"]
    end

    CLI -->|调用稳定运行时能力| Runtime
    AppGlue -->|提供请求、通道、会话元数据| Security
    Runtime -->|包含安全子边界| Security
    Security --> ToolGuard
    ToolGuard -->|高风险动作前强制确认| LocalEvidence
    Security -->|生成审计链、锁定、租约、恢复投影| LocalEvidence
    Security -->|仅通过 HTTP 上行摘要、心跳、恢复证明、拒绝事件| Api
    Api --> Store
    Api -->|查询异常、租约、恢复、nonce、hash 曲线| Web
    Api -->|推送红色告警与状态升级| Stream
    Stream --> Web

    ExplicitTests -->|真实 app subprocess + harness 观察| Runtime
    ExplicitTests -->|验证审计链、篡改、租约、正常重连、prompt injection| Security
    ExplicitTests -->|观察 backend/web 投影| Api
    ExplicitTests -->|观察 operator 展示| Web
    ContractTests -->|守住租约、客户端身份、恢复语义| Api
    ArchGuards -->|守住边界与入口 traceability| Handoff
    Handoff -->|记录冻结入口、目标与状态| Argo
    Argo -->|刷新 failure records 并验证闭环| Handoff
```

## 关键架构元素分布图

```mermaid
flowchart TB
    subgraph Product["产品运行区"]
        A1["src/qwenpaw\nBackend Runtime Root"]
        A2["src/qwenpaw/app\nHTTP / session / runtime glue"]
        A3["src/qwenpaw/cli\nOperator CLI"]
        A4["console\nOperator Console"]
        A5["website\nDocs Website"]
    end

    subgraph SecurityRuntime["本地安全实现区"]
        B1["src/qwenpaw/security\nSecurity Audit Foundation"]
        B2["tool_guard\nHigh-risk policy and enforcement"]
        B3["audit_foundation.py\nledger / heartbeat / recovery / projection"]
        B4["rules_integrity.py\nbuiltin rule integrity"]
        B5["secret_store.py\nlocal secret utilities"]
    end

    subgraph CloudBoundary["Security Center 部署区"]
        C1["deploy/api\nHTTP API boundary"]
        C2["deploy/api/store.py\nshadow state, lease, recovery store"]
        C3["deploy/web\noperator web views"]
        C4["SSE / WebSocket\nred alerts and state updates"]
    end

    subgraph VerificationZone["验证资产区"]
        D1["tests/integration/security/test_audit_foundation.py\nsec-e2e-024/025/027/028/021"]
        D2["tests/integration/security/harness.py\nbusiness-readable harness"]
        D3["tests/unit/security/tool_guard/test_rules_integrity.py\nsec-e2e-029"]
        D4["tests/contract/security/test_lease_recovery_semantics_contract.py\nlease/reconnect guards"]
        D5["tests/architecture/*.test.js\narchitecture guards"]
    end

    subgraph DesignGovernance["设计与交接区"]
        E1["design/KG/SystemArchitecture.json\nintent graph"]
        E2["design/KG/ImplementationToCodingHandoff.json\nimplementation-to-coding handoff"]
        E3["design/KG/test-failure-records.json\nArgo failure records"]
        E4["OVERALL_ARCHITECTURE.md\nstable implementation boundaries"]
        E5["*/ARCHITECTURE.md\nper-element contracts"]
    end

    A1 --> B1
    A2 --> B1
    B1 --> B2
    B1 --> B3
    B2 --> B4
    B1 --> C1
    C1 --> C2
    C1 --> C3
    C1 --> C4
    C4 --> C3
    D1 --> A1
    D1 --> B1
    D1 --> C1
    D1 --> C3
    D3 --> B4
    D4 --> B3
    D4 --> C2
    D5 --> E1
    D5 --> E2
    E2 --> E3
    E4 --> E5
```

## 关键架构元素

| 分布区域 | 核心元素 | 实现锚点 | 架构职责 |
| --- | --- | --- | --- |
| 产品运行区 | Backend Runtime | `src/qwenpaw` | 承载后端编排、运行时 glue、CLI/API 能力，并包含本地安全子边界。 |
| 产品运行区 | App / Transport Glue | `src/qwenpaw/app` | 提供请求、通道、会话等运行时元数据，但不拥有安全验收语义。 |
| 本地安全实现区 | Local Security Audit Foundation | `src/qwenpaw/security` | 统一拥有可信上下文、确认凭证、审计链、篡改锁定、租约心跳、恢复投影与高风险工具保护语义。 |
| 本地安全实现区 | High-Risk Tool Guard | `src/qwenpaw/security/tool_guard` | 在工具调用边界执行高风险确认与拒绝，确保执行前先持久化证据。 |
| 本地安全实现区 | Builtin Rule Integrity | `rules_integrity.py` / `scripts/update_tool_rule_manifest.py` | 使用共享 LF-normalized hash 规则，避免 Windows CRLF 签名误报，同时保留语义篡改检测。 |
| Security Center 部署区 | Backend API | `deploy/api` | 作为边缘运行时唯一 HTTP 云侧入口，接收 uplink、维护租约、处理恢复、发布 operator query。 |
| Security Center 部署区 | Operator Web | `deploy/web` | 展示异常、UNTRUSTED、恢复状态、hash-break 曲线、nonce Voucher 与实时红色告警。 |
| 验证资产区 | Explicit Security Entrypoints | `tests/integration/security` | 以真实 app subprocess 与业务可读 harness 验证 sec-e2e-024/025/027/028/021。 |
| 验证资产区 | Rule Integrity Entrypoint | `tests/unit/security/tool_guard/test_rules_integrity.py` | 验证 sec-e2e-029 的 LF/CRLF 不变量与语义篡改分支。 |
| 设计与交接区 | Implementation Handoff | `design/KG/ImplementationToCodingHandoff.json` | 记录显式入口、状态、验证命令、冻结文件和 Coding/Repair 目标。 |

## 当前实现主线

- `implementation-design.md` 记录的实现主线已经从安全验收缺口逐步收敛到 6 个显式入口全部通过：`sec-e2e-024`、`sec-e2e-025`、`sec-e2e-027`、`sec-e2e-028`、`sec-e2e-021`、`sec-e2e-029`。
- 安全语义集中在 `src/qwenpaw/security`；`src/qwenpaw/app` 可以提供 transport/session 证据，但不能重新定义审计、租约、恢复、锁定或高风险工具边界。
- Security Center 是独立部署边界，边缘运行时只能经由 `deploy/api` 的 HTTP API 上行，不能共享存储、导入云侧代码或绕过后端 API 直接写 Web。
- 显式验收入口保持冻结，由 `tests/integration/security/harness.py` 屏蔽运行时细节，测试主体保留 GIVEN/WHEN/THEN 风格的业务可读性。
- `design/KG/ImplementationToCodingHandoff.json` 与 `design/KG/test-failure-records.json` 是实现设计到修复阶段的交接状态面；当前交接记录显示 sec-e2e-029 已闭环，failure records 为空。

## 架构约束摘要

- 本地安全边界必须保存一个 canonical runtime client id，贯穿 startup heartbeat、recovery preflight、lockdown projection、restored-access projection 和 Security Center timeline。
- 租约过期后的恢复必须经过缺口验证；正常离线且在租约过期前重连的路径必须保持 `CLEAR`，不能误判为 `GAP_VALIDATION_REQUIRED`。
- 历史审计记录篡改必须验证完整 ledger，而不是只检查 checkpoint 或最新 tail record。
- `Security_Rejection_Nonce` 必须成为持久拒绝事件和 operator Voucher，并通过 SSE/WebSocket 在 500ms 内触发红色告警。
- 内置规则完整性校验必须共享 LF-normalized digest helper，使 CRLF-only checkout 不被视为篡改，语义内容修改仍被判定为 tampered。

# 审计日志本体模型

本文档给出面向 QwenPaw 企业级日志审计目标的本体模型草案。模型以“可追责行为”为中心，而不是以日志字段为中心，用于支撑事后追责、实时告警和合规证明。

## 设计目标

- 能回答“谁在什么上下文中，对什么资源做了什么，系统为什么允许或拒绝，结果如何，证据是否可信”。
- 将用户、Agent、工具、资源、策略、证据统一建模，避免审计日志退化为不可关联的扁平字段。
- 支撑当前已有的高风险工具审计、哈希链、Security Center 投影，并为文件访问、配置变更、合规导出扩展预留语义基础。

## 顶层本体

```mermaid
flowchart LR
    Subject["Subject<br/>主体：谁发起或参与行为"]
    Context["Context<br/>上下文：行为发生在哪条链路"]
    Object["Object<br/>客体：行为作用于什么资源"]
    ActionEvent["ActionEvent<br/>行为事件：做了什么"]
    Decision["Decision<br/>决策：为什么允许/拒绝/审批/告警"]
    Evidence["Evidence<br/>证据：如何证明且防篡改"]

    Subject -->|PERFORMS / ACTS_ON_BEHALF_OF| ActionEvent
    ActionEvent -->|IN_CONTEXT_OF| Context
    ActionEvent -->|TARGETS / USES| Object
    ActionEvent -->|DECIDED_BY| Decision
    ActionEvent -->|MATERIALIZED_AS| Evidence
```

## 核心实体

```mermaid
classDiagram
    class Subject {
      <<abstract>>
      id
      name
      type
    }

    class User {
      employee_id
      role
      department
    }

    class Agent {
      agent_id
      workspace_id
      profile
    }

    class SubAgent {
      parent_agent_id
      delegation_scope
    }

    class SystemService {
      service_name
      runtime_client_id
    }

    class ChannelBot {
      channel_type
      bot_id
    }

    class ExternalActor {
      provider
      external_id
    }

    class Context {
      <<abstract>>
      id
    }

    class Workspace {
      workspace_id
      owner
    }

    class Channel {
      channel_type
      channel_id
    }

    class Session {
      session_id
      root_session_id
    }

    class Request {
      request_id
      prompt_hash
      prompt_summary
    }

    class Trace {
      trace_id
      parent_event_id
    }

    class Runtime {
      runtime_client_id
      trust_state
    }

    Subject <|-- User
    Subject <|-- Agent
    Agent <|-- SubAgent
    Subject <|-- SystemService
    Subject <|-- ChannelBot
    Subject <|-- ExternalActor

    Context <|-- Workspace
    Context <|-- Channel
    Context <|-- Session
    Context <|-- Request
    Context <|-- Trace
    Context <|-- Runtime
```

## 客体与资源

```mermaid
classDiagram
    class Object {
      <<abstract>>
      object_id
      object_type
      sensitivity_level
    }

    class Tool {
      tool_name
      tool_provider
      execution_level
    }

    class FileResource {
      path_hash
      path_label
      file_type
    }

    class DataResource {
      data_domain
      data_label
    }

    class ConfigResource {
      config_scope
      config_key
    }

    class Skill {
      skill_name
      content_hash
      source
    }

    class MCPServer {
      server_name
      trust_level
    }

    class ModelProvider {
      provider_name
      model_name
      deployment_mode
    }

    class ExternalEndpoint {
      url_hash
      domain
      protocol
    }

    class Secret {
      secret_type
      secret_label
    }

    Object <|-- Tool
    Object <|-- FileResource
    Object <|-- DataResource
    Object <|-- ConfigResource
    Object <|-- Skill
    Object <|-- MCPServer
    Object <|-- ModelProvider
    Object <|-- ExternalEndpoint
    Object <|-- Secret
```

## 行为事件模型

行为应建模为事件节点，而不是简单边。原因是审计事件必须承载时间、上下文、策略决策、风险等级、结果、哈希和投影状态。

```mermaid
classDiagram
    class ActionEvent {
      <<abstract>>
      event_id
      event_type
      timestamp
      action
      risk_level
      result_status
      result_summary
    }

    class ToolAccessEvent {
      tool_name
      tool_call_id
      input_summary
    }

    class FileAccessEvent {
      operation
      path_hash
      path_label
    }

    class DataAccessEvent {
      data_domain
      query_summary
    }

    class ConfigChangeEvent {
      config_scope
      config_key
      before_hash
      after_hash
    }

    class ApprovalEvent {
      approval_id
      approver_id
      approval_decision
    }

    class SecurityRejectionEvent {
      rejection_reason
      security_rejection_nonce
    }

    class AuditIntegrityEvent {
      anomaly_category
      trust_state
      recovery_required
    }

    class AlertEvent {
      alert_type
      severity
      alert_latency_ms
    }

    class ExportEvent {
      export_id
      export_scope
      export_hash
    }

    ActionEvent <|-- ToolAccessEvent
    ActionEvent <|-- FileAccessEvent
    ActionEvent <|-- DataAccessEvent
    ActionEvent <|-- ConfigChangeEvent
    ActionEvent <|-- ApprovalEvent
    ActionEvent <|-- SecurityRejectionEvent
    ActionEvent <|-- AuditIntegrityEvent
    ActionEvent <|-- AlertEvent
    ActionEvent <|-- ExportEvent
```

## 决策与证据模型

```mermaid
classDiagram
    class Policy {
      policy_id
      name
      version
    }

    class PolicyRule {
      rule_id
      category
      severity
    }

    class Guard {
      guardian_name
      guardian_version
    }

    class RiskFinding {
      finding_id
      category
      severity
      matched_pattern_hash
      remediation
    }

    class PolicyDecision {
      decision_id
      decision
      policy_reason
    }

    class ApprovalDecision {
      approval_id
      approver_id
      decision
      confirmation_digest
    }

    class AuditRecord {
      record_id
      event_id
      payload_hash
      current_hash
      prior_hash
    }

    class Checkpoint {
      checkpoint_id
      checkpoint_hash
      anchored_event_id
    }

    class NonceVoucher {
      nonce
      binding_hash
      voucher
    }

    class CloudProjection {
      projection_id
      cloud_shadow_hash
      projection_status
    }

    class ExportArtifact {
      export_id
      export_hash
      generated_at
    }

    Policy "1" --> "*" PolicyRule : CONTAINS
    Guard --> RiskFinding : PRODUCES
    RiskFinding --> PolicyRule : MATCHES
    PolicyRule --> PolicyDecision : JUSTIFIES
    ApprovalDecision --> PolicyDecision : CONFIRMS_OR_OVERRIDES
    AuditRecord --> Checkpoint : ANCHORED_BY
    AuditRecord --> AuditRecord : HASH_LINKS_TO
    AuditRecord --> CloudProjection : PROJECTED_TO
    AuditRecord --> ExportArtifact : INCLUDED_IN
    PolicyDecision --> NonceVoucher : ISSUES_ON_REJECTION
```

## 统一审计关系图

```mermaid
flowchart TD
    User["User"]
    Channel["Channel"]
    Workspace["Workspace"]
    Session["Session"]
    Request["Request"]
    Agent["Agent"]
    SubAgent["SubAgent"]
    ActionEvent["ActionEvent"]
    Tool["Tool"]
    Resource["Resource"]
    Guard["Guard"]
    RiskFinding["RiskFinding"]
    PolicyRule["PolicyRule"]
    PolicyDecision["PolicyDecision"]
    ApprovalDecision["ApprovalDecision"]
    AuditRecord["AuditRecord"]
    Checkpoint["Checkpoint"]
    SecurityCenter["SecurityCenter"]
    Alert["Alert"]
    ExportArtifact["ExportArtifact"]

    User -->|AUTHENTICATED_IN| Channel
    User -->|INITIATES| Request
    Request -->|DELIVERED_BY| Channel
    Request -->|PART_OF| Session
    Session -->|BELONGS_TO| Workspace
    User -->|REQUESTS| Agent
    Agent -->|ACTS_ON_BEHALF_OF| User
    Agent -->|DELEGATES_TO| SubAgent
    Agent -->|PERFORMS| ActionEvent
    SubAgent -->|PERFORMS| ActionEvent
    ActionEvent -->|USES| Tool
    ActionEvent -->|TARGETS| Resource
    Tool -->|OPERATES_ON| Resource
    ActionEvent -->|EVALUATED_BY| Guard
    Guard -->|PRODUCES| RiskFinding
    RiskFinding -->|MATCHES| PolicyRule
    PolicyRule -->|JUSTIFIES| PolicyDecision
    PolicyDecision -->|DECIDES| ActionEvent
    ApprovalDecision -->|CONFIRMS| ActionEvent
    ActionEvent -->|MATERIALIZED_AS| AuditRecord
    AuditRecord -->|ANCHORED_BY| Checkpoint
    AuditRecord -->|PROJECTED_TO| SecurityCenter
    SecurityCenter -->|EMITS| Alert
    AuditRecord -->|INCLUDED_IN| ExportArtifact
```

## 高风险工具访问示例

```mermaid
sequenceDiagram
    participant U as User(employee_a)
    participant C as Channel(feishu)
    participant A as Agent(agent_b)
    participant G as Guard(high_risk_tool_guard)
    participant P as PolicyRule(rule_payroll_export)
    participant T as Tool(payroll_export_tool)
    participant L as AuditRecord(hash_chain)
    participant S as SecurityCenter

    U->>C: Send request
    C->>A: Deliver request with user/session/channel context
    A->>G: Request tool access
    G->>P: Evaluate risk and policy
    P-->>G: REQUIRE_APPROVAL
    G-->>A: Hold execution
    U->>A: Confirm high-risk operation
    A->>L: Write USER_CONFIRMATION before tool effect
    L->>S: Project trusted anchor
    A->>T: Execute approved tool
    T-->>A: Return result summary
    A->>L: Link result evidence to audit chain
```

## 最小落地子集

第一阶段建议优先落地以下本体元素：

- `Subject`：`User`、`Agent`、`SystemService`
- `Context`：`Workspace`、`Channel`、`Session`、`Trace`
- `Object`：`Tool`、`FileResource`、`ConfigResource`、`ExternalEndpoint`
- `ActionEvent`：`ToolAccessEvent`、`FileAccessEvent`、`ConfigChangeEvent`、`SecurityRejectionEvent`、`ApprovalEvent`、`AuditIntegrityEvent`
- `Decision`：`PolicyDecision`、`RiskFinding`、`ApprovalDecision`
- `Evidence`：`AuditRecord`、`Checkpoint`、`NonceVoucher`、`CloudProjection`、`Alert`

## 建模原则

- `ActionEvent` 是中心节点。不要把 `Agent -> Tool` 直接当作完整审计事实，因为边无法承载决策、结果和证据完整性。
- 默认不保存原文。优先保存摘要、哈希、资源标识、风险标签和策略依据，避免审计日志本身成为敏感数据池。
- 人类责任与系统行为必须分离。`User` 是请求和确认主体，`Agent` 是执行主体，`SystemService` 是后台安全行为主体。
- 所有高风险动作必须能链接到 `PolicyDecision` 和 `AuditRecord`，否则无法支撑追责和合规证明。
- 完整性证据应至少包含 `prior_hash`、`current_hash`、`payload_hash` 和 `Checkpoint`，并允许投影到 Security Center 形成外部可观测点。

# Audit Event

本文档只保留当前代码里已经实际落盘的审计事件，按“事件列表 + 触发/上报时机/核心字段”做精简说明。

当前范围分两层：

- 边缘侧审计事件：写入 `working_dir/inbox_traces/*.json`
- 云侧投影/告警记录：写入 `deploy/api` 的 Security Center store

## 1、事件列表

| 事件 | 层级 | 作用 |
| --- | --- | --- |
| `USER_CONFIRMATION` | 边缘侧 | 记录高风险工具的人类确认链 |
| `SECURITY_REJECTION` | 边缘侧 | 记录高风险工具守卫拒绝，携带 `Security_Rejection_Nonce` |
| `AUDIT_INTEGRITY_LOCKDOWN` | 边缘侧 | 记录审计连续性失信与 `UNTRUSTED` 锁定 |
| 云侧 `SECURITY_REJECTION` 投影 | 云侧 | 接收边缘拒绝上报，形成 Voucher 与实时告警 |
| 云侧 `AUDIT_LOCKDOWN` 投影 | 云侧 | 接收边缘锁定上报，形成分叉时间线与恢复态 |
| 云侧 `alert` | 云侧 | 面向 Web/SSE 的实时告警记录 |

## 2、每个事件的触发、上报时机、字段（名称、含义、作用）

### 2.1 `USER_CONFIRMATION`

#### 触发

- 高风险工具进入审批流时写入。
- 由审批服务和审计基础设施共同生成本地确认记录。

#### 上报时机

- 先写边缘侧本地审计文件。
- 当前不会单独投影为云侧独立确认事件。

#### 核心字段

| 字段组 | 名称 | 含义/作用 |
| --- | --- | --- |
| 标识 | `run_id` `event_type` `status` | 唯一标识确认事件及其审批阶段 |
| 时间 | `created_at` `confirmed_at` `released_at` `tool_effect_at` | 证明“先确认、后放行、再生效”的时间顺序 |
| 完整性 | `prior_hash` `current_hash` `payload_hash` `hash_chain_valid` `continuity_anchor` | 维持本地审计链连续性 |
| 主体 | `user_id` `request_user_id` `session_id` `channel` | 标识是谁、在哪个会话和入口触发确认 |
| 业务 | `tool_name` `high_risk_tool_name` `user_confirmation_phrase` `prompt_text` | 说明确认针对什么工具、基于什么请求 |
| 证据链 | `agent_id` `delegated_agent_name` `third_party_plugin_name` `chain` | 形成 user -> agent -> plugin -> tool 证据链 |
| 扩展 | `confirmation_context` `audit_scope` `extra` | 保留场景标签和补充上下文 |

### 2.2 `SECURITY_REJECTION`

#### 触发

- 高风险工具守卫在工具边界判定请求不可信时写入。
- 典型场景是 prompt injection 或缺失可信确认链。

#### 上报时机

- 先写边缘侧本地拒绝记录。
- 随后异步上报到云侧 rejection uplink。
- 上报成功后会回填 Voucher、SSE、Web 可见性等投影信息。

#### 核心字段

| 字段组 | 名称 | 含义/作用 |
| --- | --- | --- |
| 标识 | `run_id` `event_type` `status` `decision` | 唯一标识本次拒绝与守卫决策 |
| 时间 | `created_at` `verified_at` `edge_timestamp_ns` | 记录拒绝发生与云侧计算实时延迟所需时间基线 |
| 主体 | `user_id` `request_user_id` `session_id` `channel` `agent_id` | 标识谁在什么上下文触发了拒绝 |
| 业务 | `tool_call_id` `tool_name` `high_risk_tool_name` `prompt_text` | 标识被拒绝的工具与原始请求 |
| 守卫 | `guard_decision` `guard_category` `rejection_reason` `guardians_used` `guard_rule_id` | 说明是哪类安全守卫拒绝了请求 |
| Nonce | `Security_Rejection_Nonce` `security_rejection_nonce` `security_rejection_nonce_binding_hash` | 证明拒绝来自守卫而不是代码异常，且 Nonce 与当前 trace 绑定 |
| 完整性 | `prior_hash` `current_hash` `payload_hash` | 将拒绝事件纳入本地审计链 |
| 云侧投影 | `security_center_backend_api` `sse_stream` `operator_alert_stream` `nonce_voucher` `alert_latency_ms` `cloud_mirror_status` `uplink_status` | 表示云侧已接收、可查询并可实时告警 |
| 前端可见性 | `operator_web_projection` `security_center_operator_web` `operator_dashboard_status` `web_rejection_state` `red_alert_state` `operator_popup_state` | 表示 Web 已展示拒绝与红色告警 |

### 2.3 `AUDIT_INTEGRITY_LOCKDOWN`

#### 触发

- 检测到 checkpoint 丢失、哈希链断裂或审计连续性失信时写入。
- 系统随即进入 `UNTRUSTED` 锁定态并阻止继续执行敏感工具。

#### 上报时机

- 先写边缘侧本地锁定记录。
- 随后请求云侧恢复握手。
- 再上报到云侧 lockdown uplink，并补齐 timeline / fork point / Web 投影信息。

#### 核心字段

| 字段组 | 名称 | 含义/作用 |
| --- | --- | --- |
| 标识 | `run_id` `event_type` `status` `decision` | 标识本次完整性锁定事件 |
| 时间 | `created_at` `verified_at` `edge_timestamp_ns` | 记录锁定发生时间与实时延迟基线 |
| 主体 | `user_id` `request_user_id` `session_id` `channel` `agent_id` | 标识谁在什么上下文触发锁定 |
| 业务 | `tool_name` `high_risk_tool_name` `prompt_text` | 标识被阻断的工具和请求 |
| 完整性异常 | `lock_mode` `trust_state` `anomaly_category` `checkpoint_missing` `checkpoint_loss_detected` `tamper_detected` `integrity_alert` | 说明为什么进入 `UNTRUSTED` |
| 哈希与分叉 | `prior_hash` `current_hash` `payload_hash` `cloud_anchor_hash` `hash_divergence_curve` `fork_point_event_id` `fork_sequence_number` | 说明本地与云侧从哪里开始发生分叉 |
| 恢复流程 | `resume_handshake_status` `recovery_required` `trusted_hash_alignment` `recovery_projection` | 表示必须先恢复信任再继续高风险操作 |
| 云侧/前端 | `security_center_backend_api` `cloud_mirror_status` `alert_latency_ms` `operator_web_projection` `hash_break_curve_chart` | 表示云侧 timeline 和 Web 曲线图已可见 |

### 2.4 云侧 `SECURITY_REJECTION` 投影

#### 触发

- 边缘侧 `SECURITY_REJECTION` 上报到 Security Center 后写入。

#### 上报时机

- `deploy/api` 收到 rejection uplink 后立即入库，并同步生成一条实时 `alert`。

#### 核心字段

| 字段组 | 名称 | 含义/作用 |
| --- | --- | --- |
| 关联 | `client_id` `trace_id` `user_id` | 建立云侧记录与边缘事件的对应关系 |
| 业务 | `tool_name` `prompt_text` | 保留拒绝上下文 |
| Nonce | `nonce` `binding_hash` `voucher` | 用于运营核验拒绝凭证及其绑定关系 |
| 时间与状态 | `edge_timestamp_ns` `received_at_ns` `severity` `status` | 支撑实时延迟计算和云侧状态展示 |

### 2.5 云侧 `AUDIT_LOCKDOWN` 投影

#### 触发

- 边缘侧 `AUDIT_INTEGRITY_LOCKDOWN` 上报到 Security Center 后写入。

#### 上报时机

- `deploy/api` 收到 lockdown uplink 后立即入库，并同步生成一条实时 `alert`。

#### 核心字段

| 字段组 | 名称 | 含义/作用 |
| --- | --- | --- |
| 关联 | `client_id` `trace_id` `user_id` | 建立云侧记录与边缘锁定事件的对应关系 |
| 业务 | `tool_name` `trust_state` `recovery_required` `handshake_status` | 说明当前为何锁定、是否需要恢复 |
| 哈希 | `local_hash` `cloud_shadow_hash` `prior_hash` | 表示本地与云侧当前链头状态 |
| 时间线 | `timeline` | 为 Web 的 hash-break curve 和 fork point 展示提供数据 |
| 时间 | `edge_timestamp_ns` `received_at_ns` | 支撑云侧感知延迟计算 |

### 2.6 云侧实时 `alert`

#### 触发

- 云侧 rejection 或 lockdown 投影入库时同步生成。

#### 上报时机

- 写入云侧 store 后立刻广播到订阅者队列，供 Web 端 SSE/实时告警使用。

#### 核心字段

| 字段组 | 名称 | 含义/作用 |
| --- | --- | --- |
| 类型 | `type` `severity` `message` | 标识告警类别和人类可读摘要 |
| 关联 | `client_id` `trace_id` | 定位是哪一个边缘节点、哪一条事件触发告警 |
| 时间 | `edge_timestamp_ns` `received_at_ns` `alert_latency_ms` | 支撑 `<500ms` 实时感知校验 |
| 特殊字段 | `nonce` `fork_point_event_id` | 分别服务于拒绝凭证展示和锁定分叉点展示 |

## 3、当前不纳入审计事件范围的内容

- `src/qwenpaw/app/inbox_trace_store.py` 的通用运行 trace
- 普通 `logger.info/warning/error` 输出
- `deploy/api/overview()` 这类聚合视图返回值
- Web 从 API 拉取后的展示态本身

这些内容对排障或展示有用，但不是当前已经规范化的审计事件类型。

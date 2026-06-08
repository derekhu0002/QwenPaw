# 凭据中心改造报告（Agent 独立 + 全局共享）

## 1. 背景与目标

本次改造围绕以下目标展开：

- 为每个 Agent 提供独立凭据管理能力（按 Agent ID 隔离）。
- 同时支持全局共享凭据，供多个 Agent 引用。
- 在 Console UI 提供凭据的增删改查（CRUD）能力。
- 支持多种凭据类型：`API Key`、`Token`、`AK/SK`、`Cookie`、`Custom KV`。
- 支持在模型（Provider）、MCP、Dify 配置中引用凭据，并在运行时注入到请求。
- 分阶段推进安全能力：先完成功能，再补齐加密与审计。

---

## 2. 改造范围与分期

### Phase 1：功能闭环（已完成）

- 凭据数据模型与存储。
- 全局/Agent 作用域 CRUD API。
- 统一凭据解析器（Credential Resolver）。
- 模型、MCP、Dify 调用链接入凭据引用。
- Console 凭据管理页面与相关配置页面引用入口。
- 兼容旧配置并提供迁移接口。

### Phase 2 Batch 1：基础安全增强（已完成）

- 凭据落盘加密（`secret_store`）。
- 查看明文行为审计日志。

### Phase 2 Batch 2：高级安全能力（未实施）

- 更细粒度权限、审批、脱敏策略、密钥轮换等后续能力。

---

## 3. 总体设计

### 3.1 数据域模型

核心模型位于 `src/qwenpaw/config/config.py`：

- `CredentialType`：凭据类型枚举。
- `CredentialScope`：作用域枚举（`agent` / `global`）。
- `CredentialRef`：引用对象（`credential_id` + `field_map`）。
- `CredentialEntry`：凭据实体（含元数据与数据体）。

并在以下配置对象中引入 `credential_ref`：

- Provider 配置（模型提供商）。
- MCP 客户端配置。
- Dify 远程工作流配置。

### 3.2 存储与解析

- 存储层：`src/qwenpaw/security/credential_store.py`
  - 管理全局凭据与 Agent 凭据。
  - 支持按可见域（`visible`）融合查询（Agent + Global）。
  - Phase 2 中接入 `secret_store` 做凭据数据加密落盘。
- 解析层：`src/qwenpaw/security/credential_resolver.py`
  - 将 `CredentialRef` 解析为实际键值。
  - 按 `field_map` 注入 Provider/MCP/Dify 运行参数。

### 3.3 运行时注入链路（主调用链已接入，部分路径按上下文条件生效）

- Provider 链路：
  - `src/qwenpaw/providers/provider_manager.py`
  - `src/qwenpaw/agents/model_factory.py`
  - 在主调用链（`get_provider_for_agent`）中会基于 Agent 上下文解析凭据后再创建模型实例。
  - 说明：并非所有 Provider 读取路径都注入，部分通用读取路径不做运行时解析。
- MCP 链路：
  - `src/qwenpaw/app/mcp/manager.py`
  - 构建 MCP client 时可解析并注入 headers/env。
  - `src/qwenpaw/app/workspace/service_factories.py` 传入 workspace 上下文。
  - 说明：MCP 注入依赖运行时 workspace 上下文，缺失上下文时会跳过解析注入。
- Dify 链路：
  - `src/qwenpaw/app/routers/dify.py`
  - 在 invoke 主路径中，调用前基于 `credential_ref` 生成运行时 headers。
  - 说明：配置读取/更新接口不属于运行时注入环节。

---

## 4. 后端改动摘要

### 4.1 新增/核心模块

- `src/qwenpaw/security/credential_store.py`
  - 凭据存储、查询、作用域解析、加密落盘。
- `src/qwenpaw/security/credential_resolver.py`
  - 凭据引用解析与注入。
- `src/qwenpaw/security/credential_audit.py`
  - 明文查看行为审计日志写入/读取。
- `src/qwenpaw/app/routers/credentials.py`
  - 凭据 CRUD、明文查看、审计日志、Provider/MCP 迁移接口。
- `src/qwenpaw/app/routers/dify.py`
  - Dify 配置与调用接口，支持凭据引用。
- `src/qwenpaw/integrations/dify/client.py`
  - Dify 工作流调用客户端。

### 4.2 路由装配与可访问性

- 在 `src/qwenpaw/app/routers/__init__.py` 与 `src/qwenpaw/app/routers/agent_scoped.py` 挂载了：
  - 全局路由：`/api/credentials`、`/api/dify`
  - Agent 路由：`/api/agents/{agentId}/credentials`、`/api/agents/{agentId}/dify`

### 4.3 安全相关实现

- `credential_store` 中对敏感 `data` 字段加密落盘（`secret_store`）。
- `credentials` 明文查看接口触发审计落盘（`view_plaintext` 事件）。

---

## 5. 前端改动摘要

### 5.1 新增页面与 API

- 页面：`console/src/pages/Settings/Credentials/index.tsx`
  - 凭据列表、创建、编辑、删除、明文查看、审计日志查看。
- API：`console/src/api/modules/credentials.ts`
  - 对应后端凭据中心接口。
- 类型：`console/src/api/types/credentials.ts`
  - 凭据与审计类型定义。

### 5.2 配置页面接入引用

- Provider：`console/src/pages/Settings/Models/components/modals/ProviderConfigModal.tsx`
  - 新增 `credential_ref_id` 输入。
- MCP：`console/src/pages/Agent/MCP/index.tsx`
  - 新增 `credentialRefId` 输入。
- Dify：`console/src/pages/Agent/Dify/index.tsx`
  - 支持 `credential_ref` 配置。

### 5.3 导航与路由

- `console/src/layouts/MainLayout/index.tsx`：增加 `/credentials`、`/dify` 路由。
- `console/src/layouts/Sidebar.tsx`：增加菜单项。
- `console/src/layouts/constants.ts`：增加路径映射。
- `console/src/locales/en.json`、`console/src/locales/zh.json`：新增文案键值。

### 5.4 最近修复（按 Agent 身份独立管理）

针对“前端看起来未按 Agent 身份独立”的问题，补充了以下改造：

- `console/src/api/modules/credentials.ts`
  - 所有凭据 API 增加可选 `agentId` 参数。
  - 显式携带 `X-Agent-Id` 请求头，确保服务端按指定 Agent 解析。
- `console/src/pages/Settings/Credentials/index.tsx`
  - 新增“目标 Agent”下拉选择。
  - 列表/CRUD/明文查看/审计查询均绑定所选 Agent。
- 同时修复一次前端构建阻塞：
  - `ProviderConfigModal` 的 `credential_ref` 类型补齐 `null` 兼容。

---

## 6. 关键问题与修复记录

1. `pytest` 未安装导致测试无法执行  
   - 处理：安装 `pytest`，恢复测试能力。

2. 审计日志测试 `FileNotFoundError`  
   - 原因：审计文件目录不存在。  
   - 修复：`credential_audit` 写入前确保父目录创建。

3. 后端启动循环依赖（`CredentialResolver` 与 Provider）  
   - 原因：运行时直接导入触发环依赖。  
   - 修复：改为 `TYPE_CHECKING` 类型导入，移除运行时环。

4. 前端构建失败（`credential_ref` 类型不兼容）  
   - 原因：`null` 与 `undefined` 类型不一致。  
   - 修复：前端类型定义扩展为 `| null`。

5. 页面无 Credentials 入口  
   - 原因：使用了旧的 `console/dist` 静态产物。  
   - 修复：重新构建前端静态包并验证新路由存在。

---

## 7. 测试与联调结果

### 7.1 自动化测试

已通过的重点测试：

- `tests/unit/security/test_credential_store_and_resolver.py`
- `tests/unit/security/test_credential_audit.py`
- `tests/integration/test_mcp.py`
- `tests/integration/test_workspace_running_config.py`

结果：静态核对上述 4 个测试文件共计 `17` 个用例；文档口径中的 `17 passed` 指向该测试集合。  
说明：该数字与用例数量一致，但是否在某次实际执行中全部通过，仍以本地/CI 运行日志为准。

### 7.2 联调脚本

新增脚本：`scripts/integration_smoke_credentials.py`

覆盖内容：

- 凭据 CRUD（agent/global）与返回掩码校验。
- plaintext 接口可用性与审计日志命中。
- MCP 迁移链路与 `credential_ref` 生效校验。
- Dify 凭据引用配置与 invoke 异常链路（受控 502）校验。
- `finally` 自动清理（恢复配置、删除临时资源）。

文档已补充至：`scripts/README.md`。

---

## 8. 当前状态结论

- 凭据中心的核心能力已经形成端到端闭环（以主调用链为主）：  
  **建模 -> 存储 -> 引用 -> 注入 -> 迁移 -> UI 管理 -> 加密 -> 审计 -> 联调验证**。
- 当前支持“Agent 独立 + 全局共享引用”的设计目标。
- 已补充“按目标 Agent 显式操作”的前端交互，避免身份歧义。
- 关于注入能力的口径：当前为“主调用链已接入，部分路径按上下文条件生效”，非“所有分支无条件全链路注入”。

---

## 9. 后续建议（可选）

1. 在 Credentials 页面增加筛选器：`visible / agent / global`。  
2. 在审计页增加按 `agent_id`、`credential_id`、时间区间过滤。  
3. 在 API 层补充更细的权限控制（按角色限制明文查看）。  
4. 引入凭据轮换策略与过期提醒。  
5. 为关键改造点补充更多端到端回归用例（含 UI 自动化）。

---

## 10. 相关文件索引（核心）

- 后端
  - `src/qwenpaw/config/config.py`
  - `src/qwenpaw/security/credential_store.py`
  - `src/qwenpaw/security/credential_resolver.py`
  - `src/qwenpaw/security/credential_audit.py`
  - `src/qwenpaw/app/routers/credentials.py`
  - `src/qwenpaw/app/routers/dify.py`
  - `src/qwenpaw/providers/provider.py`
  - `src/qwenpaw/providers/provider_manager.py`
  - `src/qwenpaw/agents/model_factory.py`
  - `src/qwenpaw/app/mcp/manager.py`
  - `src/qwenpaw/app/workspace/service_factories.py`

- 前端
  - `console/src/pages/Settings/Credentials/index.tsx`
  - `console/src/api/modules/credentials.ts`
  - `console/src/api/types/credentials.ts`
  - `console/src/pages/Agent/Dify/index.tsx`
  - `console/src/pages/Settings/Models/components/modals/ProviderConfigModal.tsx`
  - `console/src/pages/Agent/MCP/index.tsx`
  - `console/src/layouts/MainLayout/index.tsx`
  - `console/src/layouts/Sidebar.tsx`
  - `console/src/layouts/constants.ts`

- 测试与脚本
  - `tests/unit/security/test_credential_store_and_resolver.py`
  - `tests/unit/security/test_credential_audit.py`
  - `scripts/integration_smoke_credentials.py`
  - `scripts/README.md`

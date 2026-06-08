# QwenPaw 当前代码变更总结（相对当前分支源码基线）

## 1. 变更范围总览

- 统计口径：当前工作区相对当前分支基线（未提交改动）。
- 已跟踪文件变更：`30` 个文件，约 `+344 / -30`（以 `git diff --stat` 为准）。
- 新增未跟踪文件：凭据中心后端/前端代码与测试，以及两份中文说明文档。

## 2. 主要功能性改动

### 2.1 Agent 独立凭据中心（核心新增）

#### 后端新增

- 新增凭据存储层：`src/qwenpaw/security/credential_store.py`
  - 支持 `global` / `agent` 作用域隔离存储。
  - 凭据字段加密落盘（基于 `secret_store`），读取时解密，列表接口返回掩码值。
  - 提供 CRUD、可见域合并查询（global + agent）。
- 新增凭据解析层：`src/qwenpaw/security/credential_resolver.py`
  - 通过 `CredentialRef` + `field_map` 解析并注入运行时参数。
  - 支持 Provider 注入、MCP header/env 注入。
- 新增凭据路由：`src/qwenpaw/app/routers/credentials.py`
  - 提供 `/credentials` CRUD、可见性查询、引用校验。
  - 提供 Provider/MCP 迁移入口（将历史明文配置迁移为 `credential_ref`）。

#### 配置模型扩展

- `src/qwenpaw/config/config.py`
- `src/qwenpaw/config/__init__.py`

新增/导出凭据相关模型（如 `CredentialEntry`、`CredentialRef`、`CredentialScope`、`CredentialType` 等），并把凭据引用纳入配置体系。

#### 路由挂载与作用域接入

- `src/qwenpaw/app/routers/__init__.py`
- `src/qwenpaw/app/routers/agent_scoped.py`

挂载凭据路由，支持在 Agent 作用域下获取/使用凭据。

### 2.2 Provider / MCP / 工具调用链注入能力

- `src/qwenpaw/agents/model_factory.py`
- `src/qwenpaw/providers/provider.py`
- `src/qwenpaw/app/routers/providers.py`
- `src/qwenpaw/app/mcp/manager.py`
- `src/qwenpaw/app/routers/mcp.py`
- `src/qwenpaw/app/workspace/workspace.py`

将 `credential_ref` 贯穿到模型提供方、MCP 客户端和相关运行路径，支持按需注入 API Key、Authorization、header/env 映射字段等。

## 3. Console 前端改动

### 3.1 新增凭据中心页面与 API

- 新增 API 模块：`console/src/api/modules/credentials.ts`
- 新增类型定义：`console/src/api/types/credentials.ts`
- 新增页面：`console/src/pages/Settings/Credentials/index.tsx`

实现凭据列表、创建、编辑、删除、作用域切换（visible/agent/global）及 JSON 数据编辑。

### 3.2 入口与类型联动

- `console/src/api/index.ts`
- `console/src/api/types/index.ts`
- `console/src/layouts/MainLayout/index.tsx`
- `console/src/layouts/Sidebar.tsx`
- `console/src/layouts/constants.ts`

完成导航入口、API 聚合导出、页面路由接入。

### 3.3 配置页与多语言补充

- `console/src/pages/Settings/Models/components/modals/ProviderConfigModal.tsx`
- `console/src/api/types/provider.ts`
- `console/src/api/types/mcp.ts`
- `console/src/locales/en.json`
- `console/src/locales/ja.json`
- `console/src/locales/pt-BR.json`
- `console/src/locales/ru.json`
- `console/src/locales/zh.json`

在 Provider/MCP 配置中增加凭据引用入口与类型适配，并补齐文案。

## 4. 稳定性与测试驱动修复（显式用例相关）

### 4.1 测试与兼容性修复

- `tests/conftest.py`：第三方模块 mock 策略调整，避免误覆盖真实安装包。
- `src/qwenpaw/constant.py`：上传大小限制默认值修正（避免配置缺失时绕过限制）。
- `src/qwenpaw/app/routers/agents.py`：Agent ID 自动生成策略调整为短 ID 唯一化重试（不再拼接机器信息）。
- `src/qwenpaw/security/skill_scanner/scan_policy.py`：字符兼容修复（Windows 编码相关）。

### 4.2 Security Center 恢复链路修复

- `deploy/api/store.py`
- `src/qwenpaw/security/audit_foundation.py`

围绕租约过期后的恢复握手、gap proof 验证、runtime preflight 与 canonical client 映射做了多轮修复，目标是通过安全相关显式测试并稳定联调链路。

### 4.3 前端资产显式锚点

- `deploy/web/index.html`

补充测试稳定锚点注释，减少语言/文案变体导致的显式测试脆弱性。

## 5. 测试与设计辅助文件

- `design/KG/test-failure-records.json`：测试失败记录更新。
- 新增：`tests/unit/security/test_credential_store.py`（凭据存储/解析单测）。
- 新增文档：
  - `CREDENTIAL_CENTER_EXEC_SUMMARY_zh.md`
  - `CREDENTIAL_CENTER_REPORT_zh.md`

## 6. 当前状态说明

- 凭据中心（后端 + Console）已具备可用的 CRUD + 注入基础能力。
- 主流程可启动并运行（`qwenpaw app` 可直接使用）。
- 安全恢复链路存在一条集成用例的间歇性不稳定现象（租约恢复场景），相关代码已做针对性修复并在部分回归中通过，建议后续继续做稳定化收敛。

## 7. 变更文件清单（已跟踪）

- `console/src/api/index.ts`
- `console/src/api/types/index.ts`
- `console/src/api/types/mcp.ts`
- `console/src/api/types/provider.ts`
- `console/src/layouts/MainLayout/index.tsx`
- `console/src/layouts/Sidebar.tsx`
- `console/src/layouts/constants.ts`
- `console/src/locales/en.json`
- `console/src/locales/ja.json`
- `console/src/locales/pt-BR.json`
- `console/src/locales/ru.json`
- `console/src/locales/zh.json`
- `console/src/pages/Settings/Models/components/modals/ProviderConfigModal.tsx`
- `deploy/api/store.py`
- `deploy/web/index.html`
- `src/qwenpaw/agents/model_factory.py`
- `src/qwenpaw/app/mcp/manager.py`
- `src/qwenpaw/app/routers/__init__.py`
- `src/qwenpaw/app/routers/agent_scoped.py`
- `src/qwenpaw/app/routers/agents.py`
- `src/qwenpaw/app/routers/mcp.py`
- `src/qwenpaw/app/routers/providers.py`
- `src/qwenpaw/app/workspace/workspace.py`
- `src/qwenpaw/config/__init__.py`
- `src/qwenpaw/config/config.py`
- `src/qwenpaw/constant.py`
- `src/qwenpaw/providers/provider.py`
- `src/qwenpaw/security/audit_foundation.py`
- `src/qwenpaw/security/skill_scanner/scan_policy.py`
- `tests/conftest.py`


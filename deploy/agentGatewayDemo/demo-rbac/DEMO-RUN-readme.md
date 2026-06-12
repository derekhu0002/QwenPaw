# agentGateway RBAC 演示 — 运行指南

## 目录要求

agentGatewayDemo下只需两样即可完整演示（可整包复制到其他 Windows 机器）：

```
agentGatewayDemo/
├── agentgateway.exe
└── demo-rbac/
```

### 系统依赖（机器上预装，不在目录内）

- **Python 3.10+**（含 pip）— MCP 后端与演示脚本
- **Node.js 18+**（含 npm）— MCP Inspector（双屏演示需要）

---

## 从头演示 — 完整步骤

以下命令均在 **DeployRoot** 下执行。

### 0. 进入部署目录

```powershell
cd <DeployRoot>
# 示例: cd D:\coding\QwenPaw\deploy\agentGatewayDemo

在powershell中运行以下指令，显示True代表路径正确。
  Test-Path .\agentgateway.exe
  Test-Path .\demo-rbac\scripts\start-all.ps1
如果本目录下没有agentgateway.exe，有agentgateway.zip，则将agentgateway.zip解压，可进入后续步骤。
```

### 1. 启动全部后台服务（MCP + Gateway）

```powershell
.\demo-rbac\scripts\start-all.ps1
```

成功后会看到 3 个后台进程（无弹窗）：

| 服务 | 端口 |
|------|------|
| HR MCP | 9001 |
| Forum MCP | 9002 |
| AgentGateway MCP | 3000 |
| Admin Console | 15000 |

日志目录：`demo-rbac\logs\`

### 2. 启动双屏 Inspector（后台 + 自动开浏览器）

```powershell
.\demo-rbac\scripts\open-dual-inspector.ps1
```

会自动：

- 后台启动两个 Inspector（`:6274` 员工屏、`:6275` 管理员屏）
- 打开 2 个浏览器标签 + `inspector-helper.html` 助手页

### 3. Inspector 三档权限演示（核心环节）

助手页中有 Token 与权限矩阵。

| 步骤 | 操作 | 预期 List Tools |
|------|------|-----------------|
| **① 无 Token** | 两屏 **都不填** Authorization → Connect | 仅 `forum_list_posts` |
| | Call `forum_list_posts` | 成功 |
| |                                                             |                                          |
| **② 普通员工 Token** | 从助手页复制 **普通员工 Token** → Authorization → Reconnect | `forum_list_posts` + `forum_create_post` |
| | Call `forum_create_post` | 成功发帖 |
| |                                                             |                                          |
| **③ 管理员 Token** | 复制 **管理员 Token** → 另一屏 Reconnect | 5 个工具 |
| | Call `hr_get_employee` `{}` | 成功返回 4 条员工 PII |

**Inspector 连接设置（两屏相同）：**

- Transport：**Streamable HTTP**
- URL：`http://localhost:3000/mcp`
- Custom Header：`Authorization: Bearer <token>`（无 Token 时不加）

### 4. 自动化脚本验证

```powershell
.\demo-rbac\scripts\run-demo.ps1
```

自动跑：游客 → 普通员工（含越权攻击）→ 管理员。

### 5.鉴权拒绝取证

```powershell
.\demo-rbac\scripts\audit-auth-deny.ps1 -RunAttack
.\demo-rbac\scripts\show-auth-deny.ps1
```

### 6.（可选）实时 Debug Trace

```powershell
.\demo-rbac\scripts\start-trace.ps1
```

### 7. 演示结束 — 关闭全部

```powershell
.\demo-rbac\scripts\stop-all.ps1
```

停止 5 个后台进程：HR MCP、Forum MCP、AgentGateway、两个 Inspector。

---

## 常用管理命令

```powershell
# 已在运行时重启全部服务
.\demo-rbac\scripts\start-all.ps1 -Restart

# 只重新启动 Inspector（Gateway 保持运行）
.\demo-rbac\scripts\open-dual-inspector.ps1
```

## 其他入口

| 用途 | 地址 |
|------|------|
| Admin Console | http://localhost:15000/ui |
| Metrics | http://localhost:15020/metrics |
| Token 助手页 | `demo-rbac\inspector-helper.html` |

## 权限矩阵

| 工具 | 无 Token | 普通员工 Token | 管理员 Token |
|------|----------|----------------|--------------|
| forum_list_posts | 允许 | 允许 | 允许 |
| forum_create_post | 拒绝 | 允许 | 允许 |
| forum_delete_post | 拒绝 | 拒绝 | 允许 |
| hr_get_employee | 拒绝 | 拒绝 | 允许 |
| hr_update_employee | 拒绝 | 拒绝 | 允许 |

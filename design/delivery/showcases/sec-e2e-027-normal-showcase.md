# sec-e2e-027 正常用户 SHOWCASE：在线使用时不被安全审计打扰

## 场景一句话

一个完全不知道 QwenPaw 安全审计能力的普通用户，像平时一样打开 QwenPaw 继续处理工作；设备保持在线并持续发送心跳，Security Center 在后台确认租约有效，用户不会看到额外的安全术语、恢复流程或人工干预。

## 演示视角

- 演示对象是普通业务用户，不是安全管理员。
- 用户不知道“租约”“审计链”“Security Center”“gap proof”这些概念。
- 用户只关心：QwenPaw 能不能继续对话、能不能继续使用模型、工作会不会被莫名打断。

## 前置准备

- 开始演示前，先将环境恢复到正常状态。
  - 在仓库根目录执行：

    ```powershell
    .\.venv\Scripts\Activate.ps1
    powershell -ExecutionPolicy Bypass -File .\scripts\reset-showcase-demo-state.ps1
    ```

  - 最小环境变量与其他安全审计 showcase 保持一致：

    ```powershell
    $env:QWENPAW_WORKING_DIR = "D:\QwenPawDemo\working2"
    $env:QWENPAW_SECRET_DIR = "D:\QwenPawDemo\working2.secret"
    $env:QWENPAW_BACKUP_DIR = "D:\QwenPawDemo\working2.backups"
    $env:QWENPAW_SECURITY_CENTER_DATA_DIR = "D:\QwenPawDemo\security-center-data"
    $env:QWENPAW_SECURITY_CENTER_API_URL = "http://127.0.0.1:8091"
    $env:QWENPAW_SECURITY_CENTER_WEB_URL = "http://127.0.0.1:8092"
    $env:QWENPAW_AUTH_ENABLED = "false"
    $env:NO_PROXY = "*"
    $env:PYTHONPATH = "D:\Projects\QwenPaw\src"
    $env:PYTHONIOENCODING = "utf-8"
    $env:SECURITY_CENTER_API_BASE = "http://127.0.0.1:8091"
    ```

- QwenPaw Console 已正常启动。
- Security Center backend API 已启动，默认地址为 `http://127.0.0.1:8091`。
- Security Center operator web 已启动，默认地址为 `http://127.0.0.1:8092`。
- 演示时不要先解释安全审计特性；把用户当作第一次使用该能力的人。

## 演示输入

用户在 QwenPaw 对话框中输入一条普通工作请求：

> 帮我总结今天的项目进展，并列出下一步待办。

随后等待一个短时间间隔，再继续输入：

> 继续基于刚才的内容，帮我把下一步待办整理成三条优先级建议。

## 演示步骤

### 1. 用户打开 QwenPaw 并发起普通工作请求

用户不知道系统正在做安全审计，只是像平时一样发送工作问题。

预期结果：

- QwenPaw 正常响应。
- 用户不会看到“租约”“恢复”“UNTRUSTED”之类的安全状态文案。
- 模型访问保持可用。

### 2. 用户短暂停留后继续对话

用户停顿一小段时间，例如查看返回内容、切换窗口或修改输入，然后继续发起第二条请求。

预期结果：

- QwenPaw 继续正常响应。
- 对话上下文没有因为后台心跳或安全检查而丢失。
- 用户仍然只感知到“这是一个能持续工作的 AI 助理”。

### 3. 管理员视角静默确认租约有效

这一步只给演示人员或观察员看，不主动告诉普通用户。打开 Security Center operator web 或 backend API：

- `GET /security-center/v1/operator/overview`
- `GET /security-center/v1/operator/timelines/{client_id}`

预期结果：

- 对应客户端保持 `ALIGNED` 或等价正常状态。
- 可以看到 `last_heartbeat_at`、`lease_ttl_seconds`、`lease_expires_at` 等租约字段。
- `recovery_required` 为 `false`。
- 没有出现恢复闸门、异常告警或模型访问拒绝。

## 控制点与观察点

- 控制点：普通用户在设备在线且租约未过期时连续发起两次普通模型请求。
- 用户观察点：QwenPaw 持续可用，响应不中断，不向用户暴露安全审计内部概念。
- 后台观察点：Security Center 投影显示客户端租约有效、信任状态正常、无需恢复。

## 观测点

- 安全审计能力在正常使用时是低打扰的。
- 用户不需要理解租约机制，也不需要做额外操作。
- 后台租约字段存在且可解释，但不会把普通用户拖进安全运维流程。

## 验收标准

- 用户两次普通请求都能得到正常模型响应。
- 用户界面没有出现不必要的安全术语或恢复提示。
- Security Center 中对应客户端保持正常信任状态。
- Security Center 能看到租约时间字段，说明正常路径也在持续维护 active-defense 基线。

## 失败判定

- 普通在线使用过程中模型访问被误拦截。
- 用户必须理解或处理安全审计概念才能继续工作。
- Security Center 看不到租约字段，无法解释为什么当前客户端仍可信。
- 客户端在租约未过期时被错误标记为 `UNTRUSTED`。

## 讲解口径

“这个场景先不讲攻击，也不讲审计术语。用户只是正常打开 QwenPaw 工作，系统应该像普通 AI 助理一样流畅响应。安全能力在后台维护设备在线租约和可信状态，但不会打扰用户。只有当设备真的长期失联或连续性无法证明时，用户才会看到恢复提示。正常情况下，它应该是安静的、可解释的、但不抢戏的。”
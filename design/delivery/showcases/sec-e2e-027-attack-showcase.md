# sec-e2e-027 异常攻击 SHOWCASE：设备离线超租约后阻断恢复使用

## 场景一句话

一个普通用户并不知道 QwenPaw 有安全审计和租约防御能力；他的设备长时间离线或疑似被拿走后再次上线，系统不会直接恢复模型访问，而是先把设备标记为不可信，并要求完成缺失审计区间的连续性校验。

## 演示视角

- 演示主角仍然是普通用户，而不是攻击者或安全管理员。
- 用户不知道后台有租约 TTL、云侧镜像、hash gap、recovery gate。
- 用户只看到：设备回来后，QwenPaw 暂时不允许继续使用模型，并提示需要恢复信任。
- 管理员只作为旁观者查看 Security Center，解释系统为什么拒绝恢复。

## 前置准备

- 开始演示前，先将环境恢复到正常状态。
  - 在仓库根目录执行：

    ```powershell
    .\.venv\Scripts\Activate.ps1
    . .\scripts\reset-showcase-demo-state.ps1
    ```

  - 演示环境变量已内置到 reset 脚本。脚本默认使用 `D:\QwenPawDemo\working2`、`D:\QwenPawDemo\working2.secret`、`D:\QwenPawDemo\working2.backups`、`D:\QwenPawDemo\security-center-data`、`http://127.0.0.1:8091`、`http://127.0.0.1:8092` 等 showcase 默认值。
  - 在仓库根目录执行 `. .\scripts\reset-showcase-demo-state.ps1` 即可一键停止旧进程、重建演示目录、清掉残留状态、设置当前 PowerShell 终端环境变量，并写入当前 Windows User 环境供新终端继承。脚本仍会生成 `D:\QwenPawDemo\showcase-demo-env.ps1`，仅用于刷新已经打开的其他终端；如果不希望写入 User 环境，可额外加 `-SkipUserEnvironmentPersist`。

- QwenPaw Console 已正常启动。
- Security Center backend API 已启动，默认地址为 `http://127.0.0.1:8091`。
- Security Center operator web 已启动，默认地址为 `http://127.0.0.1:8092`。
- QwenPaw runtime 启动后会自动向 Security Center 注册首个 lease heartbeat，并在运行期间周期发送；演示中不要通过用户 prompt 触发或补发租约心跳。
- 演示人员准备好解释“设备离线太久”这个普通用户能理解的业务事实，不提前讲 hash 或审计链。

## 演示输入

第一次在 QwenPaw 对话框中输入，用于建立正常使用基线：

> 帮我检查今天的项目事项，并记住我稍后会回来继续处理。

模拟设备离线并超过租约窗口后，再输入：

> 我回来了，继续刚才的项目事项总结。

完成缺失区间校验后，再输入：

> 现在继续生成下一步行动建议。

## 演示步骤

### 1. QwenPaw 启动后后台自动注册租约

用户不知道后台会生成心跳和审计基线；在用户发起第一条工作请求前，QwenPaw runtime 已经通过后台 Heartbeat Emitter 向 Security Center 注册首个租约心跳。随后用户只是正常发起工作请求。

预期结果：

- Security Center 后台已经接收该 runtime 客户端的首个租约心跳。
- QwenPaw 正常响应。
- 用户第一次正常使用只是在这个后台租约基础上建立业务上下文和后续审计基线。
- 管理员视角可以看到客户端处于正常状态，但普通用户不需要知道这些细节。

### 2. 模拟设备长时间离线或疑似被带走

演示人员让后台 heartbeat 停止或让客户端错过周期租约心跳，等待超过当前演示环境的租约窗口。当前 DEMO 使用压缩后的租约窗口，便于现场演示；产品语义是“超过租约时间后必须重新证明连续性”。不要通过用户 prompt 触发或补发租约心跳，本场景观察的是后台心跳停止后的 Security Center 主动降级。

预期结果：

- 普通用户视角：这只是“我离开了一段时间，设备现在回来了”。
- Security Center 视角：该客户端的 `lease_expires_at` 已经过期。
- 系统不需要等用户主动承认风险，云侧会在读取投影时把客户端降级为 `UNTRUSTED`。

### 3. 用户回来后尝试继续使用模型

用户输入：

> 我回来了，继续刚才的项目事项总结。

预期结果：

- QwenPaw 不直接恢复模型访问。
- 用户看到的是业务可理解的提示，例如设备需要恢复信任、当前暂时不能继续敏感使用。
- 这不是模型故障，也不是网络错误，而是系统主动保护用户工作区。

### 4. 管理员观察 Security Center 的拒绝与恢复状态

打开 Security Center operator web，或查询 backend API：

- `GET /security-center/v1/operator/overview`
- `GET /security-center/v1/operator/timelines/{client_id}`

预期结果：

- 客户端信任状态为 `UNTRUSTED` 或等价状态。
- `recovery_required = true`。
- 可以看到 `last_heartbeat_at`、`lease_ttl_seconds`、`lease_expires_at`。
- 可以看到恢复闸门仍打开，模型访问尚未恢复。

### 5. 系统完成缺失区间连续性校验

演示人员触发恢复流程，让客户端提交缺失区间的审计连续性证明。普通用户不需要理解这个过程，只需要知道“系统正在确认这台设备离线期间没有丢失关键证据”。

预期结果：

- 如果只提交匹配的 hash 或自报状态，Security Center 不会直接放行。
- 只有完整缺失区间证明被云侧校验通过后，恢复闸门才关闭。
- Security Center 状态从恢复必需转回正常。

### 6. 用户再次继续工作

用户输入：

> 现在继续生成下一步行动建议。

预期结果：

- QwenPaw 恢复正常模型访问。
- 用户可以继续工作。
- 用户不需要学习审计链细节，只需要感知到系统先保护、再恢复。

## 控制点与观察点

- 控制点一：QwenPaw runtime 启动后自动注册首个租约心跳，随后设备错过后台周期租约心跳并超过租约窗口。
- 观察点一：Security Center 将客户端降级为 `UNTRUSTED`，并投影 `recovery_required = true`。
- 控制点二：用户在恢复前尝试继续模型访问。
- 观察点二：QwenPaw 拒绝恢复访问，用户看到需要恢复信任的业务反馈。
- 控制点三：客户端提交完整缺失区间连续性证明。
- 观察点三：Security Center 验证通过后关闭恢复闸门，QwenPaw 才恢复模型访问。

## 观测点

- 攻击或异常不需要表现成复杂技术行为；对普通用户来说，它只是“设备离线太久后又回来了”。
- 系统不是等攻击者再次操作才被动发现问题，而是在租约过期后主动把客户端降级。
- 租约心跳是 runtime 后台行为，不是用户通过对话触发的隐藏命令。
- 恢复不是用户点一下“相信我”就放行，而是必须完成云侧缺失区间校验。
- 用户体验上，安全能力表现为清晰的暂时阻断和恢复，而不是晦涩的审计术语。

## 验收标准

- QwenPaw runtime 启动后，Security Center 能在没有用户 warmup prompt 的情况下看到首个租约心跳。
- 租约过期后，Security Center 能主动把客户端标记为 `UNTRUSTED`。
- 恢复前，用户继续使用模型的请求被拒绝。
- Security Center 能展示租约时间字段和恢复必需状态。
- 缺少完整 gap proof 的恢复尝试不能把状态恢复为正常。
- 完整缺失区间证明通过后，模型访问才恢复。

## 失败判定

- 设备离线超过租约后仍被当成正常客户端。
- 首个租约心跳必须依赖用户输入特定 lease warmup 提示词才能出现。
- 用户回来后无需任何连续性校验就能继续使用模型。
- 只凭自报 hash 或单个状态值就关闭恢复闸门。
- Security Center 看不到租约过期原因或恢复状态。
- 普通用户看到的是技术错误堆栈，而不是可理解的恢复提示。

## 讲解口径

“这个场景要从普通用户感受出发：他并不知道系统背后有租约和审计链，也不需要输入任何隐藏的心跳指令。QwenPaw 启动后已经在后台注册租约；当设备离线太久后回来，系统没有立刻允许继续使用。系统这样做不是为了增加麻烦，而是因为离线期间设备可能被拿走、克隆或篡改。QwenPaw 会先把设备标记为不可信，等缺失期间的连续性被云侧验证通过后，才恢复正常模型访问。用户看到的是一个保护动作，管理员看到的是可解释的租约过期和恢复证据。”
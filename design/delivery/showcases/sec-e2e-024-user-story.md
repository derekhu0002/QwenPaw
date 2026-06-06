# sec-e2e-024 用户演示用例

## 场景一句话

用户在 QwenPaw 对话中要求 agent 删除一个测试文件，系统在执行删除前弹出审批窗口，用户点击“批准”后才继续执行。

## 前置准备

- 开始演示前，先将环境恢复到正常状态。
	- 演示环境变量已内置到 reset 脚本。脚本默认使用 `D:\QwenPawDemo\working2`、`D:\QwenPawDemo\working2.secret`、`D:\QwenPawDemo\working2.backups`、`D:\QwenPawDemo\security-center-data`、`http://127.0.0.1:8091`、`http://127.0.0.1:8092` 等 showcase 默认值。
	- 在仓库根目录执行：
		```powershell
		.\.venv\Scripts\Activate.ps1
		. .\scripts\reset-showcase-demo-state.ps1
		```
		第二行是 dot-source 形式的一键准备命令：它会停止默认演示端口上的旧进程、重建干净的演示目录、清掉残留状态、设置当前 PowerShell 终端环境变量，并写入当前 Windows User 环境供新终端继承。脚本仍会生成 `D:\QwenPawDemo\showcase-demo-env.ps1`，仅用于刷新已经打开的其他终端；如果不希望写入 User 环境，可额外加 `-SkipUserEnvironmentPersist`。
	- 环境变量说明：
		- `QWENPAW_WORKING_DIR` 指向一个干净的演示目录。
		- `QWENPAW_SECRET_DIR` 指向配套的 secret 目录。
		- `QWENPAW_BACKUP_DIR` 指向配套的 backup 目录。
		- `QWENPAW_SECURITY_CENTER_DATA_DIR` 指向 deploy/api 使用的独立 Security Center 数据目录；如果不显式设置，deploy/api 可能回落到仓库内默认 store 路径，上一轮演示的云侧残留状态会污染本轮结果。
		- 如果是从仓库源码直接运行，而不是使用安装包，建议确保 `PYTHONPATH` 包含仓库下的 `src` 目录；在 Windows 上建议额外设置 `PYTHONIOENCODING=utf-8`，减少日志与子进程编码问题。
		- 若演示机器存在系统代理，建议设置 `NO_PROXY=*`，避免本机 `127.0.0.1` 的 API / SSE 请求被代理劫持。
		- 如果不打算演示登录流程，建议显式设置 `QWENPAW_AUTH_ENABLED=false`。否则需要先完成 Console 注册或登录，因为开启认证后页面行为会依赖是否已有注册用户。
- QwenPaw 已正常启动。
- 控制台页面可正常打开。
	- Security Center backend API 已启动并可访问。最小启动方式与本次通过用例一致：在仓库根目录执行 `python -m deploy.api.app`，默认监听 `http://127.0.0.1:8091`；若需改端口，可设置 `SECURITY_CENTER_API_HOST` 与 `SECURITY_CENTER_API_PORT`。
	- Security Center operator web 已启动并可访问。最小启动方式与本次通过用例一致：在仓库根目录执行 `python -m deploy.web.server`，默认监听 `http://127.0.0.1:8092`；若 API 不在默认地址，需要同时设置 `SECURITY_CENTER_API_BASE` 指向 deploy/api。
	- 当前环境可以观察到本地审计工作目录。这里指 edge runtime 的 `QWENPAW_WORKING_DIR`；本次通过用例里，关键文件是 `<QWENPAW_WORKING_DIR>/audit_chain_checkpoint.json` 和 `<QWENPAW_WORKING_DIR>/inbox_traces/*.json`。不需要单独预制目录，但必须先完成一次正常高风险动作，让这两个位置已经产生基线审计文件。
- 已启用高风险工具保护(推荐shell 删除文件之类的现有 builtin tool)。

## 演示输入

在 QwenPaw 对话框中输入：

> 请删除测试文件 D:\Projects\QwenPaw\temp\test-file.txt

## 演示步骤

### 1. 用户发起删除请求

用户在对话中要求 agent 删除测试文件。

预期结果：

- QwenPaw 接收请求并开始处理。
- 文件不会被立即删除。

### 2. 系统弹出审批

系统到达高风险工具边界后进入等待审批状态。

预期结果：

- 界面出现“安全审批”卡片或弹窗。
- 可以看到“批准”按钮。
- 在点击“批准”前，删除操作不会执行。

### 3. 用户点击批准

由演示用户点击“批准”。

预期结果：

- 审批界面关闭，或变为已批准状态。
- 删除流程继续执行。

### 4. 验证删除结果

检查测试文件是否已被删除。

预期结果：

- 文件 `D:\Projects\QwenPaw\temp\test-file.txt` 已不存在。
- Inbox 的“审批”页签中存在对应审批记录，或演示后可以查询到 trace 记录 (`D:\QwenPawDemo\working\inbox_traces`下)。

## 观测点

- 删除请求先触发审批，而不是直接执行。
- 用户点击“批准”后删除才发生。
- 删除完成后能看到审批记录或证据记录。

## 验收标准

- 未批准前，测试文件仍然存在。
- 点击“批准”后，测试文件被删除。
- 系统保留了审批相关证据。

## 失败判定

- 没有弹出审批窗口就直接删除了文件。
- 点击“批准”前文件已经不存在。
- 点击“批准”后文件仍未删除。
- 演示结束后找不到审批记录或证据记录。

## 讲解口径

“这里演示的是一个最小高风险操作场景。用户在 QwenPaw 中要求 agent 删除一个测试文件。系统不会直接执行删除，而是先弹出安全审批窗口。只有当用户点击‘批准’后，删除动作才会真正发生。执行完成后，还可以看到对应的审批记录和证据链。”

# QwenPaw 一眼说明

## 这是什么

QwenPaw 是一个仓库内集成的个人 AI 助手平台，当前稳定形态由五个部分构成：Python 后端运行时、本地运维 CLI、运维控制台前端、对外文档网站，以及一组用于验证架构与阶段交接的校验资产。

从当前意图架构和实现架构看，这个项目不是单一聊天界面，而是一套围绕 AI 助手运行、操作、配置、文档发布和架构治理组织起来的完整产品仓库。

## 核心能力概览

- 后端运行时：承载 API 路由、Agent 执行、Channel 编排、配置、安全和共享工具能力。
- 本地运维 CLI：通过 `qwenpaw` 入口提供本地操作面，当前已明确存在版本查询、Agent 列表和任务命令帮助面。
- 运维控制台：提供浏览器和桌面壳共用的操作界面，用于运行管理、聊天、设置、渠道和编码模式相关流程。
- 文档网站：提供对外说明、安装引导、特性传达和发布向内容。
- 架构校验资产：提供系统架构、阶段交接和显式测试用例执行的仓库原生验证能力。

## 适合的使用方式

QwenPaw 当前更适合以下采用路径：

1. 把它作为一个带 Python 运行时的 AI 助手平台仓库来接入和二次开发。
2. 把 `qwenpaw` CLI 作为本地操作入口，用于查看版本、发现命令和执行受控任务。
3. 把 `console/` 视为运维操作 UI，把 `website/` 视为对外文档和采用入口。
4. 把 `.github/validator` 和根目录架构合同视为治理和交付约束，而不是业务功能的一部分。

## 不适合的场景

- 需要仓库已经证明的公开 SaaS 地址、托管 API 域名或云端多租户交付模型的场景。目前架构合同没有提供这些事实。
- 需要已经冻结的控制台前端显式验收基线的场景。当前显式基线集中在 CLI 和后端运行时。
- 需要完整公共 API 文档、完整参数默认值矩阵或稳定错误码目录的场景。当前仓库架构只证明了少量稳定入口与观察点。

## 模块与边界

### 1. 后端运行时

- 稳定路径：`src/qwenpaw`
- 责任：拥有 API 路由、Agent 运行时、Channel、配置、安全、Provider 和共享工具。
- 已证明边界：控制台和网站可以依赖后端契约，但后端不依赖前端实现细节。
- 当前显式验收基线：
  - `PUT /api/settings/language` 后紧接 `GET /api/settings/language`，读取结果必须返回刚写入的语言值。
  - Git 辅助执行必须委托给共享命令运行器。

### 2. 本地运维 CLI

- 稳定路径：`src/qwenpaw/cli`
- 责任：拥有通过 `qwenpaw` 暴露的 click 命令面，并通过延迟加载控制启动成本。
- 已证明命令面：
  - `qwenpaw --version`
  - `qwenpaw agents list`
  - `qwenpaw task --help`
- 边界：CLI 负责操作入口，不重新拥有后端编排状态。

### 3. 运维控制台

- 稳定路径：`console`
- 责任：拥有运维控制台前端和 Tauri 桌面包装资产。
- 已证明能力范围：运行管理、聊天、设置、渠道和编码模式 UI 流程。
- 边界：控制台依赖后端 API；后端不能反向依赖控制台实现。

### 4. 文档网站

- 稳定路径：`website`
- 责任：拥有安装引导、功能说明和对外发布内容。
- 边界：网站负责说明与采用，不拥有运行时行为。

### 5. 架构校验资产

- 稳定路径：`.github/validator`
- 责任：提供系统架构、阶段交接和显式测试执行的验证脚本。
- 边界：用于治理，不属于业务运行时。

## 外部接口与集成点

以下条目仅包含当前架构来源明确证明的入口。凡是仓库没有证明的默认值、错误码、部署地址或示例，都会直接标记为“未提供仓库证据”。

### 接口 1：`qwenpaw` 根 CLI

- 名称：`qwenpaw`
- 用途：本地操作入口，用于查看版本、发现子命令和进入受控任务面。
- 调用路径：Python 包暴露的 `qwenpaw` 命令入口；稳定实现位于 `src/qwenpaw/cli/main.py`。
- 已证明输入与约束：
  - `--version` 必须可用。
  - `task --help` 必须展示稳定 flag 面，覆盖 instruction、model、guard、skills、output、iteration、timeout、agent selection。
  - 其他参数默认值：未提供仓库证据。
- 可观察结果：
  - `--version` 成功退出并输出当前包版本。
  - `task --help` 成功退出并展示稳定 flag 面。
- 前置条件与依赖：依赖 Python 运行时和 `src/qwenpaw` 运行时能力。
- 最小使用示例：

```bash
qwenpaw --version
qwenpaw task --help
```

- 证据来源：`design/KG/SystemArchitecture.json`、`OVERALL_ARCHITECTURE.md`、`src/qwenpaw/ARCHITECTURE.md`、`src/qwenpaw/cli/ARCHITECTURE.md`
- 已知限制：仓库架构没有给出完整命令手册、参数默认值表或安装步骤细节。

### 接口 2：`qwenpaw agents list`

- 名称：`qwenpaw agents list`
- 用途：通过 CLI 暴露 Agent 列表能力。
- 调用路径：`qwenpaw` 根命令下的 `agents list` 子命令；稳定文件为 `src/qwenpaw/cli/agents_cmd.py`。
- 已证明输入与约束：当前只证明该子命令保持接到共享 agent helper；其余参数和默认值未提供仓库证据。
- 可观察结果：命令成功退出，并打印共享 helper 返回的 agent 记录序列化结果。
- 前置条件与依赖：依赖 CLI 命令面和共享 agent 工具辅助能力。
- 最小使用示例：

```bash
qwenpaw agents list
```

- 证据来源：`design/KG/SystemArchitecture.json`、`OVERALL_ARCHITECTURE.md`、`src/qwenpaw/cli/ARCHITECTURE.md`
- 已知限制：仓库架构没有提供输出格式规范、分页行为或过滤参数说明。

### 接口 3：语言设置 HTTP 入口

- 名称：`/api/settings/language`
- 用途：写入并读取语言设置。
- 调用路径：后端 FastAPI 路由挂载的 `PUT /api/settings/language` 与 `GET /api/settings/language`。
- 已证明输入与约束：
  - 先发送一个有效语言值到 `PUT /api/settings/language`。
  - 随后对同一设置存储执行 `GET /api/settings/language`。
  - 语言值的完整枚举、默认值和鉴权要求：未提供仓库证据。
- 可观察结果：`GET` 返回与前一次 `PUT` 持久化相同的语言值。
- 前置条件与依赖：依赖后端运行时和可用的设置存储。
- 最小使用示例：仓库架构未提供可直接复用的 HTTP 请求示例。
- 证据来源：`design/KG/SystemArchitecture.json`、`src/qwenpaw/ARCHITECTURE.md`
- 已知限制：仓库架构没有提供公开基地址、认证方式、错误响应格式或完整设置模型。

### 接口 4：运维控制台前端

- 名称：Operator Console
- 用途：提供运行管理、聊天、设置、渠道和编码模式的操作 UI。
- 访问路径：仓库稳定实现位于 `console/`，包含 `src/` 浏览器前端和 `src-tauri/` 桌面壳资产。
- 已证明输入与约束：控制台消费后端 API 和共享运行时契约；具体页面路由、启动命令、环境变量默认值未提供仓库证据。
- 可观察结果：构成一个浏览器/桌面双形态的运维前端。
- 前置条件与依赖：依赖后端 API 契约；桌面形态额外依赖 Tauri 打包资产。
- 最小使用示例：仓库架构未提供控制台运行或发布示例。
- 证据来源：`design/KG/SystemArchitecture.json`、`OVERALL_ARCHITECTURE.md`、`console/ARCHITECTURE.md`
- 已知限制：当前意图图没有为控制台定义显式验收用例，也没有证明部署入口地址。

### 接口 5：对外文档网站

- 名称：Documentation Website
- 用途：承载安装引导、功能说明和发布向产品内容。
- 访问路径：仓库稳定实现位于 `website/`。
- 已证明输入与约束：网站拥有独立依赖图与构建系统；具体公开 URL、页面结构和搜索入口默认行为未提供仓库证据。
- 可观察结果：形成一个独立的对外文档与采用网站。
- 前置条件与依赖：依赖网站自身构建资产；不拥有业务运行时。
- 最小使用示例：仓库架构未提供网站运行或部署示例。
- 证据来源：`design/KG/SystemArchitecture.json`、`OVERALL_ARCHITECTURE.md`、`website/ARCHITECTURE.md`
- 已知限制：仓库架构没有给出对外域名、信息架构明细或内容发布流程。

### 接口 6：架构验证命令面

- 名称：Architecture Validation Assets
- 用途：校验系统架构、阶段交接和显式测试执行链路。
- 调用路径：根目录 npm 验证命令经由 `.github/validator/script/*.js` 调用验证脚本。
- 已证明输入与约束：验证范围覆盖系统架构、handoff 和显式测试执行；各命令具体参数默认值未提供仓库证据。
- 可观察结果：为仓库治理提供结构与交接有效性校验结果。
- 前置条件与依赖：依赖根目录验证命令和 `.github/validator` 中的脚本资产。
- 最小使用示例：仓库架构未提供完整命令示例，但已证明这些能力通过根目录 npm 验证命令暴露。
- 证据来源：`design/KG/SystemArchitecture.json`、`OVERALL_ARCHITECTURE.md`、`.github/validator/ARCHITECTURE.md`
- 已知限制：仓库架构没有在允许来源中提供完整命令清单或样例输出。

## 采用前需要知道的前提

- 这是一个多边界仓库，不应只按单一应用来理解。后端、CLI、控制台、网站和架构验证是并列稳定元素。
- Python 运行时是当前稳定后端核心；CLI 与后端共享同一运行时根。
- 控制台和网站是两个独立前端边界，职责不同，不应混为一个 UI 工程。
- 显式验收基线当前集中在 CLI 与后端运行时；前端更多依赖实现层测试和未来扩展。

## 约束与已知缺口

- 当前架构文档证明的是“稳定边界与少量稳定入口”，不是完整公开 API 手册。
- 仓库当前没有在允许来源中证明统一部署拓扑，因此不能把它描述成已固定的在线服务形态。
- 当前没有在允许来源中证明完整安装流程、环境变量表、认证模型或错误码字典。
- 当前没有在意图图中为控制台和网站定义显式测试基线，因此这两个边界更适合作为已存在实现面，而不是已冻结验收合同。

## 证据边界说明

本文件只基于以下架构来源整理，不引入代码、测试、脚本或其他文档中的额外事实：

- `design/KG/SystemArchitecture.json`
- `OVERALL_ARCHITECTURE.md`
- `src/qwenpaw/ARCHITECTURE.md`
- `src/qwenpaw/cli/ARCHITECTURE.md`
- `console/ARCHITECTURE.md`
- `website/ARCHITECTURE.md`
- `tests/ARCHITECTURE.md`
- `.github/validator/ARCHITECTURE.md`
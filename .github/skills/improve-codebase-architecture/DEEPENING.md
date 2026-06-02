# Deepening

本文件定义在候选被怀疑为 shallow module 或 seam 放错位置时，如何进一步判断和提出 deepening 方向。

## Dependency Categories

对候选涉及的依赖做最小分类，帮助后续决定 deepening 策略和测试方法。

### 1. In-process

纯计算或进程内状态。

- 通常可以直接深挖为更深的 module
- 测试优先直接跨 interface 断言行为

### 2. Local-substitutable

依赖有本地替身。

- 可以通过本地替身支撑 interface 级测试
- 不要为了测试替身而把内部 seam 暴露成外部 interface

### 3. Remote but owned

跨网络但你方可控。

- 通常意味着要在 seam 上定义 port 或稳定接口
- 生产和测试可分别配 production/test adapters
- 推荐把逻辑集中在深模块里，而不是散落在调用侧

### 4. True external

第三方外部依赖。

- 优先隔离为 adapter
- 不要让外部不稳定性直接渗透进核心 module interface

## Deepening Checks

当你准备建议“加深某个模块”时，至少回答这些问题：

- 问题到底出在 interface 太宽、implementation 太碎、seam 放错位置，还是 adapter 只是多余间接层
- 删除当前模块后，复杂度是消失还是回流到多个调用点
- 候选模块的测试应该停留在哪个 interface 上，而不是穿透到哪里
- 这个 seam 是真实可变需求，还是只有一个 adapter 的假 seam

## Testing Strategy

- 如果 deepening 成立，旧的 shallow 单元测试可能会失去价值，需要说明哪些测试应该删除或降级。
- 新测试应尽量上移到 deepened module 的 interface 层。
- 测试讨论必须明确 control point 和 observation point。
- 如果测试必须跟着内部实现重写，说明它很可能测穿了 interface。
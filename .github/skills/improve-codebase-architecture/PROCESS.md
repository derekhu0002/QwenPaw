# Process

本文件定义这个 SKILL 的执行步骤、输出形状，以及与现有 `grill-me` 流程的衔接方式。

## 1. Explore

先探索目标切片，找出这些信号：

- shallow module
- 职责泄漏
- 跨文件来回跳转过多
- seam 不清或放错位置
- 测试面不稳定
- 依赖方向可疑

然后对可疑候选应用 [LANGUAGE.md](LANGUAGE.md) 中的判别原则，并结合 [DEEPENING.md](DEEPENING.md) 中的依赖分类判断是否值得继续深挖。

## 2. Present Candidates

候选先以内联聊天形式给用户，不要先落盘。未被选中的候选保持临时状态，不写进仓库。

对每个候选都要明确说明：

- 涉及的具体仓库路径
- 当前的架构摩擦点
- 它为什么是 shallow，或者它的 seam 为什么放错了位置
- 建议加深的 module、需要重构的 seam，或应删除的 pass-through 层
- 对 locality、leverage、testability 的预期收益
- 依赖分类和对应的测试策略
- 它更像是 Intent 变更、Implementation Architecture 变更，还是仅需代码变更
- 建议强度：`Strong`、`Worth exploring`、`Speculative`

## 3. Output Rules

- 先给候选，不要一上来就给唯一答案
- 每个候选都要带推荐答案和理由
- 明确区分“仓库已证实事实”和“当前推断”
- 如果讨论到测试，必须写清 control point 和 observation point；缺一项就视为设计未完成
- 如果某个候选建议“加深模块”，要同步说明哪些旧测试会失去价值、哪些测试应该上移到 interface 层
- 如果某个候选建议保留现状，也要说明为什么 deletion test 没有通过，或者为什么当前 seam 已经足够真实

## 4. Hand Back To Grill-Me

用户选定某个候选后，不在这个 SKILL 里直接扩写实现方案。

改为把选中方向交给现有的 `grill-me` 风格对话，继续按设计树逐支路确认：

- 是否真的需要改 intent
- 是否其实只是 implementation architecture 调整
- 是否只需要 code change
- 测试边界、control point、observation point 是否闭合
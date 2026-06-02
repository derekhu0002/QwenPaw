# Language

本文件定义这个 SKILL 的统一术语和判别原则。

这些术语用于帮助识别 shallow module、无效 seam 和真正值得 deepening 的候选，但不能覆盖 Argo 既有本体语义。涉及 intent、implementation architecture、handoff、explicit testcase 时，仍以仓库现有术语为准。

## Terms

**Module**
一个带接口和实现的代码或契约单元，可以是函数、类、目录级切片或稳定架构元素。

**Interface**
调用方或下游阶段必须知道的使用面、约束、错误模式、顺序要求和配置前提，不只是类型签名。

**Implementation**
隐藏在接口后的代码或资产。

**Depth**
接口背后真正封装了多少复杂度。Deep module 让调用方只学较小接口就获得较多行为；Shallow module 的接口复杂度接近实现复杂度。

**Seam**
可以调整行为而不需要原地改调用方的位置。优先使用 seam，不要泛化成 boundary。

**Adapter**
在某个 seam 上满足接口的具体实现。

**Locality**
改动、知识和 bug 面是否集中在少数位置。

**Leverage**
调用方因为模块足够深而减少了多少复杂度暴露。

## Principles

- **Deletion test**：想象删掉这个 module。如果复杂度直接消失，它大概率只是 pass-through；如果复杂度会回流到多个调用方，它可能真的在“赚它自己的存在价值”。
- **The interface is the test surface**：测试应该优先跨 interface 断言可观察行为，而不是测试穿透到实现内部。
- **One adapter means a hypothetical seam, two adapters means a real seam**：只有一个 adapter 时，先警惕是否只是额外间接层；当生产与测试或两种运行环境都需要不同 adapter 时，seam 才更像真实需求。
- **Depth is a property of the interface**：不要因为实现代码多就误判为 deep module，关键是接口有没有替调用方隐藏复杂度。

## Usage Rules

- 分析时尽量使用这里的术语，而不是随意切换成 component、service、API、boundary 等词。
- 如果术语使用与 Argo 现有本体冲突，优先保留 Argo 本体语义，并把这里的术语当作辅助分析语言。
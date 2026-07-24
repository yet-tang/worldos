# RFC-0004：Tick 生命周期与确定性

- 状态：Draft

## 1. 标准 Tick Phase

```text
1. clock
2. environment
3. perception
4. cognition
5. intent_collection
6. validation
7. resolution
8. consequence
9. knowledge_memory
10. projection
11. narration_index
```

同一 phase 内使用稳定排序键；并发只允许用于无共享写冲突的计算。

## 2. 决策确定性边界

LLM 本身不保证位级确定。WorldOS 的复现保证分为两层：

- Historical Replay：已物化事件回放必须完全一致。
- Simulation Rerun：相同模型、参数、prompt、工具结果和 decision record 时尽量一致，但不作为核心不变量。

因此每次 Agent 决策都必须记录：观察输入摘要、模型标识、prompt/version、工具结果引用、原始输出 hash、规范化 Intent。

## 3. RNG

每次随机解析使用派生 seed：

```text
world_seed + timeline_id + tick + phase + intent_id
```

随机结果写入 Event，回放不调用 RNG。

# RFC-0006：Agent 决策协议

- 状态：Draft

## 1. Agent 输入

Agent 只能看到为其构建的 Observation Packet，而不是完整 World State：

- 当前时间与可感知环境
- 自身 Component
- 可见 Entity 的有限属性
- Working Memory
- 检索到的 Episodic / Semantic Memory
- 当前 Goals 与 Commitments
- 上一行动反馈

## 2. Agent 输出

输出必须是结构化 Decision：

```json
{
  "decision_id": "dec_...",
  "goal_ref": "goal_survive",
  "plan_ref": "plan_find_food",
  "intent_type": "move",
  "arguments": {"destination_id": "loc_kitchen"},
  "expected_outcome": "reach_food_source",
  "fallback": "ask_innkeeper",
  "confidence": 0.61
}
```

## 3. 禁止项

Agent 不得：

- 声明行动已经成功；
- 读取未被观察到的事实；
- 创建资源或物品；
- 修改其他 Entity；
- 直接写入 Memory、Knowledge 或 Relationship。

## 4. 低成本决策

并非每个 Tick 都调用 LLM。调度器按活动度、事件相关性、计划阻塞和预算选择：规则策略、缓存计划、轻量模型或高级模型。

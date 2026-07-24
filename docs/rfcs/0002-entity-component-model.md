# RFC-0002：Entity / Component 模型

- 状态：Draft

## 1. 决策

WorldOS 使用数据导向的 Entity / Component 模型，但不要求所有对象都是“会思考的 Agent”。

- Entity：稳定身份和生命周期边界。
- Component：某类状态数据。
- System：读取指定 Component，验证 Intent，产生 Event。
- Agent Capability：仅是 Entity 可选的一组 Component 与运行能力。

因此，“一封信”可以是 Entity，但不必调用 LLM。它可以拥有 Position、Ownership、ReadableContent、EvidenceTrail 等 Component。

## 2. 最小 Entity

```json
{
  "entity_id": "ent_01...",
  "kind": "human",
  "created_by_event": "evt_01...",
  "destroyed_by_event": null
}
```

`kind` 是方便检索的非权威标签，具体能力由 Component 决定。

## 3. Component 设计约束

- Component 必须可序列化。
- Component 不封装外部连接。
- Component 更新只能由事件 reducer 完成。
- 每种 Component 有独立 schema version。
- 引用其他 Entity 时只保存 entity_id。

## 4. 初期 Component 集

- Identity
- Position
- Container / Inventory
- Ownership
- Health
- Needs
- Traits
- Goals
- Plan
- Relationships
- Perception
- Knowledge
- Memory
- Agency

## 5. 为什么不是 Everything is Agent

把所有 Entity 都当成推理 Agent 会造成模型成本、调度复杂度和语义混乱。正确的统一层是 Entity；Agent 是具有 Agency + Cognition 能力的 Entity 子集。

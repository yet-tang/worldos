# RFC-0005：Knowledge、Belief 与 Memory

- 状态：Draft

## 1. 四层分离

- Fact：世界中已发生的客观事件或可推导事实。
- Observation：某 Entity 通过感知获得的有限信号。
- Belief：角色对命题的主观判断，包含置信度、来源和更新时间。
- Memory：角色保存的经历或概括，不保证真实。

## 2. Belief Record

```json
{
  "proposition": "merchant_carries_letter",
  "confidence": 0.72,
  "stance": "believes",
  "source_refs": ["obs_...", "entity_old_man"],
  "acquired_tick": 17,
  "last_revised_tick": 21
}
```

## 3. 信息传播

Talk 不应直接复制知识集合。它产生 `statement.uttered`；听者产生 Observation；再根据对说话者信任、已有信念和证据形成或修订 Belief。

## 4. Memory 分层

- Working：短期任务上下文。
- Episodic：带时间地点的经历。
- Semantic：从经历压缩出的稳定认识。
- Identity：价值观、自我叙事、承诺。

Memory consolidation 必须产生可追踪事件，不能静默改写人格。

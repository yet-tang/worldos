# RFC-0003：Event Store、回放与时间线

- 状态：Accepted

## 1. Event Envelope

每个事件至少包含：

```json
{
  "event_id": "evt_...",
  "timeline_id": "tl_main",
  "sequence": 12,
  "tick": 4,
  "phase": "resolution",
  "event_type": "health.changed",
  "schema_version": 1,
  "actor_id": "ent_attacker",
  "subject_ids": ["ent_target"],
  "caused_by": ["evt_attack_intent_accepted"],
  "correlation_id": "cmd_...",
  "payload": {},
  "metadata": {}
}
```

## 2. 顺序

同一时间线使用严格递增 `sequence` 作为总序。`tick` 只表示模拟时间，不能替代提交顺序。

## 3. 原子 Event Batch

一个 Intent 可能解析为多个事件，例如攻击：

```text
attack.started
attack.resolved
health.changed
death.occurred
```

它们必须作为一个 batch 原子追加，避免只提交一半结果。

## 4. 分支

分支引用父时间线及其可见截止 sequence：

```text
Timeline B = Timeline A[1..120] + B[121..]
```

父时间线后续事件不会自动进入已经创建的分支。

## 5. Snapshot

Snapshot 包含 timeline、through_sequence、projection_version、canonical_state 和 checksum。Snapshot 不是事实，可随时失效和重建。

## 6. 模式升级

事件不可就地改写。旧事件通过 upcaster 转换为当前 reducer 可读结构。无法安全升级时，应创建新 projection version，而不是修改历史。

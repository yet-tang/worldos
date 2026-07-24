# RFC-0001：WorldOS 核心宪法

- 状态：Accepted
- 版本：1.0
- 目标版本：WorldOS v1

## 1. 问题

v0.2 已证明多角色目标与规则结算能够产生涌现冲突，但其世界状态仍由 Engine 直接修改。这会导致：历史无法完整回放、分支难以实现、调试缺少因果链、模型升级后结果难以复现、Narrator 可能依赖不可追溯状态。

## 2. 核心定义

WorldOS 是一个确定性的离散事件模拟内核。它管理世界事实、Entity、Component、时间线、Intent、Event、Projection 和 Snapshot。LLM 是决策插件，不是事实源。

## 3. 不变量

### 3.1 Event Store 是唯一事实源

任何可观察世界变化都必须来源于已提交事件。禁止业务代码绕过 Event Store 直接持久化权威状态。

### 3.2 State 是 Projection

当前世界状态由事件序列经过 Reducer 得到。Snapshot 只是优化，可丢弃并重建。

### 3.3 Intent 与 Event 分离

Agent、Director、玩家或系统模块提交 Intent。规则系统验证 Intent 并生成一个或多个 Event。Intent 表示“希望发生什么”，Event 表示“已经发生什么”。

### 3.4 Reducer 无副作用

Reducer 不调用 LLM、不读取当前时间、不使用隐式随机数、不访问网络、不写外部存储。输入相同 State 与 Event，输出必须相同。

### 3.5 随机性显式化

随机数由 Resolution 阶段使用受控 RNG 产生，并写入事件 payload 或 resolution metadata。回放时不得重新掷骰。

### 3.6 认知与事实隔离

客观事件不会自动成为所有角色的知识。角色知道什么，由 Observation、Communication、Inference、Memory 等独立事件决定。

### 3.7 叙事器只读

Narrator 不得创建、修改或撤销世界事实。其输出不是世界事件，除非用户明确将叙事内容作为外部行为重新提交给世界。

### 3.8 时间线不可变

已提交事件不可原地编辑。纠错通过补偿事件或从旧位置创建新分支完成。

## 4. 权威写入路径

```text
Source
  → Intent
  → Validation
  → Resolution
  → Event Batch
  → Atomic Append
  → Reducers / Projections
  → State / Index / Narration
```

## 5. 模块边界

- Core：事件、时间线、回放、快照、模式版本。
- Rules：Intent 验证和事件解析。
- ECS：Entity 与 Component projection。
- Agent Runtime：观察、规划、Intent 生成。
- Knowledge：事实可见性、信念、谣言和记忆。
- Scheduler：Tick 和 phase 调度。
- Narration：只读历史表达。
- Inspector：因果链、决策依据、分支比较。

## 6. 暂不解决

本 RFC 不规定具体战斗公式、经济模型、LLM 供应商、UI 技术栈或小说文风。

## 7. 验收条件

- 删除当前 State 后可以仅靠 Event Store 重建。
- 相同事件序列得到相同 canonical hash。
- 能从任意事件位置创建分支，且父时间线不受影响。
- 世界变化不存在未对应事件的写入路径。

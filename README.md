# WorldOS v1 Architecture Baseline

WorldOS 是一个事件驱动、可回放、可分叉的 AI 世界模拟内核。世界先运行，叙事器只读取历史；小说、剧本、漫画和游戏剧情是同一条世界历史的不同投影。

本仓库是从 WorldOS v0.2 原型迁移到规范驱动架构的第一条基线，包含：

- RFC-0001：核心宪法与边界
- RFC-0002：Entity / Component 模型
- RFC-0003：Event Store、回放与时间线分叉
- RFC-0004：Tick 生命周期和确定性
- RFC-0005：Knowledge / Memory / Belief 分层
- RFC-0006：Agent 决策协议
- RFC-0007：Narrator 与 Director 权限边界
- 一个可运行的最小事件溯源内核
- 回放、校验和分叉测试

## 当前里程碑

这不是完整模拟器，而是 `v1.0 Architecture Kernel`：先证明所有世界变化都能通过事件重建，且同一历史可稳定回放和分叉。

## 快速运行

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
pytest -q
worldos-core demo
```

示例会：

1. 创建世界与两个 Entity；
2. 追加移动、伤害事件；
3. 回放得到主时间线状态；
4. 在伤害发生前创建分支；
5. 在分支中追加另一组事件；
6. 输出两个世界线的不同状态与摘要哈希。

## 架构原则

1. Event Store 是事实源；State 是可重建缓存。
2. Agent 只提交 Intent，不直接修改 State。
3. Reducer 必须纯函数化、可重放、无外部副作用。
4. 随机结果必须先物化为事件数据，再由 Reducer 应用。
5. Knowledge、Belief、Memory 与客观世界事实彼此独立。
6. Narrator 只读；Director 只能提交受规则约束的世界 Intent。
7. 每个事件具有因果、来源、时间线和模式版本。

## 目录

```text
docs/rfcs/           设计规范
src/worldos_core/    最小事件内核
tests/               架构验收测试
examples/            示例
```

## 下一实现阶段

- Command / Intent 验证管线
- ECS Component Registry
- Snapshot 与增量回放
- Knowledge Projection
- Scheduler 与 Tick Phase
- Inspector 决策追踪
- 将“暴雪客栈”迁移为第一个 world package

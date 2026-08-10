# WorldOS v1

WorldOS 是一个事件驱动、可回放、可分叉的 AI 世界模拟内核。世界先运行，叙事器只读取历史；小说、剧本、漫画和游戏剧情是同一条世界历史的不同投影。

## 当前能力

- SQLite / 内存事件存储、确定性回放与 Timeline 分叉
- Snapshot、迁移、事务恢复和持久化 World Runner
- Entity / Component 世界投影
- Intent 验证与确定性 Resolution
- Observation、Belief 与角色知识隔离
- Working、Episodic、Semantic、Identity Memory
- Needs、Goal Tree 与确定性 Planner
- Scheduler / Tick Engine
- 可插拔 World Module 与生存经济模块
- Replay-backed Inspector / Debug API
- Narrator 只读上下文 API
- 本地只读 Web Inspector
- 开发环境 Token Debug Read API
- CLI 示例与端到端测试

世界运行链路：

```text
Tick Started
→ World Modules: Before Actions
→ Needs / Goal Selection
→ Plan Materialization
→ Intent Validation / Resolution
→ World Effects
→ World Modules: After Actions
→ Observation / Belief
→ Memory
→ Tick Completed
→ Inspector / Web Inspector
→ Narrator
```

Narrator 和 Web Inspector 永远位于 Event Store 的只读下游。

## 安装

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev]'
```

Windows PowerShell：

```powershell
py -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -e '.[dev]'
```

## 运行测试

```bash
python -m pytest -q
```

GitHub Actions 会在 Python 3.11、3.12 和 3.13 上执行测试与 CLI smoke test。

## CLI

### 完整架构演示

```bash
worldos-core demo
```

运行主世界线，创建分支，并输出两个 Timeline 的状态哈希。

### 运行确定性世界 Tick

```bash
worldos-core simulate --ticks 1 --seed worldos-demo
```

输出事件数量、世界状态和 canonical hash。同一历史与同一 seed 应产生完全一致的结果。

### 检查角色运行状态

```bash
worldos-core inspect traveler --ticks 1
```

输出角色的物理状态、观察、信念、记忆、目标和计划步骤。

### 获取 Narrator 上下文

全知视角：

```bash
worldos-core narrate --ticks 1
```

角色视角：

```bash
worldos-core narrate --actor witness --ticks 1
```

角色视角不会返回世界哈希，也不会暴露该角色未观察到的事件。

### 持久化世界

```bash
worldos-core world-init --db world.db
worldos-core run --db world.db --ticks 100
worldos-core pause --db world.db
worldos-core step --db world.db --ticks 1
worldos-core resume --db world.db
worldos-core status --db world.db
worldos-core branch --db world.db alternate --through-sequence 100
```

### Web Inspector

```bash
worldos-inspector --db world.db
```

默认打开 `http://127.0.0.1:8765`，提供世界地图、角色状态、目标与计划、信念与记忆、关系、事件时间线、分支对比和 Narrator 上下文。该服务默认只绑定本机；对外暴露时应放在带认证的反向代理后面。

### 开发环境 Token Debug API

为远程自动验证配置一个至少 24 字符的随机 Token：

```bash
export WORLDOS_DEBUG_TOKEN="$(openssl rand -hex 32)"
worldos-inspector --db world.db
```

推荐使用标准 Bearer 认证：

```bash
curl -H "Authorization: Bearer $WORLDOS_DEBUG_TOKEN" \
  http://127.0.0.1:8765/api/debug/health
```

最常用的一次性世界探针：

```bash
curl -H "Authorization: Bearer $WORLDOS_DEBUG_TOKEN" \
  "http://127.0.0.1:8765/api/debug/worlds/<world_id>/probe?limit=50"
```

它会返回运行版本、当前回合、事件数量、World Hash、人物状态、Active Goals、社会关系、人情债、最近事件和结构诊断。Debug API 只有读取能力，不提供推进、删除或修改世界的接口。

无法设置自定义 Header 的只读工具可在 GET 请求使用 `?token=<url-encoded-token>`。部署版 Nginx 会对 `/api/debug` 关闭自身 access log，避免把 query token 写进该代理日志；能使用 Header 时仍应优先使用 Bearer Token。

完整规范见 `docs/rfcs/0030-token-debug-read-api.md`。

## Python 示例

```python
from worldos_core.cli import build_demo_store
from worldos_core.inspector import WorldInspector
from worldos_core.narrator import NarratorReadAPI

store = build_demo_store(ticks=1, world_seed="my-world")
inspector = WorldInspector(store)

snapshot = inspector.snapshot("main")
traveler = inspector.actor("traveler", "main")
narrative = NarratorReadAPI(inspector).context(
    "main",
    perspective_actor_id="traveler",
)

print(snapshot.world_hash)
print(traveler.memories)
print(narrative.events)
```

## 核心原则

1. Event Store 是事实源；State 是可重建缓存。
2. Agent 只提交 Intent，不直接修改 State。
3. Reducer 必须纯函数化、可重放、无外部副作用。
4. 随机结果必须先物化为事件数据，再由 Reducer 应用。
5. Knowledge、Belief、Memory 与客观世界事实彼此独立。
6. Narrator 只读；Director 只能提交受规则约束的 Intent。
7. 每个事件具有因果、来源、时间线和模式版本。
8. CLI、Inspector、Web Inspector、Token Debug API 和 Narrator 都不能绕过事件管线修改世界。

## RFC

`docs/rfcs/` 保存 WorldOS 的规范，包括核心宪法、事件存储、Tick、Intent、Knowledge、Memory、Planner、World Modules、Inspector、Narrator、Runner、Web Inspector、Token Debug API 与 CLI 验收边界。

## 目录

```text
docs/rfcs/           设计规范
src/worldos_core/    世界模拟内核
tests/               单元与端到端验收测试
.github/workflows/   持续集成
```

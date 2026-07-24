# RFC-0007：Narrator 与 Director 权限边界

- 状态：Draft

## Narrator

Narrator 是只读 projection consumer。允许压缩、选视角、调整叙述顺序和语言风格，但不得添加会改变因果理解的虚构事实。

叙事输出应可附带 provenance：每个段落引用支持它的 event_id。

## Director

Director 不是作者。它只能提交世界层 Intent，例如天气变化、公共资源冲击或新 Entity 到达；这些 Intent 仍需规则验证、预算约束和冷却时间。

Director 不得指定某角色必须爱上、背叛、死亡或获胜，也不得读取角色私有思想后定向操纵世界，除非该世界模板明确把这种能力定义为可观察、可对抗的世界实体。

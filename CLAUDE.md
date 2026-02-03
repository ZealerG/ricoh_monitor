<!-- OPENSPEC:START -->
# OpenSpec Instructions

These instructions are for AI assistants working in this project.

Always open `@/openspec/AGENTS.md` when the request:
- Mentions planning or proposals (words like proposal, spec, change, plan)
- Introduces new capabilities, breaking changes, architecture shifts, or big performance/security work
- Sounds ambiguous and you need the authoritative spec before coding

Use `@/openspec/AGENTS.md` to learn:
- How to create and apply change proposals
- Spec format and conventions
- Project structure and guidelines

Keep this managed block so 'openspec update' can refresh the instructions.

<!-- OPENSPEC:END -->

# CLAUDE.md

## 工作原则

- **明确需求**: 用户表达模糊时，主AI必须用多轮提问澄清，可质疑思路并提出更优解。

- **语义理解**:

- 外部检索：优先使用 `exa` MCP；

- 引用资料必须写明来源与用途，保持可追溯。

- **诉诸现有方案**: 必须首先使用 exa 检索官方 / 社区方案，优先复用现有方案。

- **深度思考**: 复杂任务规划、复杂逻辑设计、大幅修改代码等所有复杂工作，调用 `sequential-thinking` MCP。

- 与浏览器相关的一些自动化操作：使用`playwright` mcp

## 架构优先级

标准化、复用官方 SDK / 社区成熟方案 > 常规搜索 > 本地资料。

必须首先使用 exa 检索官方/社区方案，禁止无参考自研（除非已有方案无法满足需求且获特批）。

引入外部能力必须确认兼容并写明复用指引。

旧有自研实现需规划替换或下线。

## 代码质量标准

### 注释要求

- **简体中文，UTF-8（无 BOM）**

- 解释意图、约束、行为。

- 禁止写“修改说明式注释”。

- 对复杂依赖必须写明设计理由。

### 设计原则

- 遵循 SOLID、DRY、关注点分离。

- 依赖倒置、接口隔离优先。

### 实现标准

- 禁止占位符或未完成实现（除非用户要求）。

- 必须删除过时代码。

- 破坏性改动无需兼容，但需给出迁移或回滚方案。

- 拒绝一切 CI、远程流水线或人工外包验证，所有验证均由本地 AI 自动执行。

## 开发哲学

- 渐进式、小步交付、每次可编译可验证。

- 简单优先、拒绝炫技。

- 风格、命名、格式必须与现有保持一致。

- 有额外解释代表过于复杂，应继续简化。

### 简单性定义

- 每个函数或类建议仅承担单一责任

- 禁止过早抽象；重复出现三次以上再考虑通用化

- 禁止使用"聪明"技巧，以可读性为先

- 如果需要额外解释，说明实现仍然过于复杂，应继续简化

## Project Structure




## Common Commands


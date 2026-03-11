# .agents/
> L2 | 父级: /CLAUDE.md

## 定位

Agent 声明式扩展层 — 通过 markdown 文件定义 skills 和 subagents，Kernel boot 时自动发现加载，零代码变更。

## 成员清单

### skills/
Agent 技能定义文件，遵循 Anthropic Agent Skills 开放规范。Kernel 启动时扫描 `SKILL.md` / `skill.md`。

### subagents/
`technician.md`: 量化技术分析子代理，工具白名单 [market_ohlcv, compute]，拉行情算指标输出结构化技术评估
`researcher.md`: 信息研究子代理，工具白名单 [web_search, web_fetch]，多角度搜索新闻事件输出研究报告

[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md

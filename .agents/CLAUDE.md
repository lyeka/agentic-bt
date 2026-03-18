# .agents/
> L2 | 父级: /CLAUDE.md

## 定位

Agent 声明式扩展层 — 通过 markdown 文件定义 skills 和 subagents，Kernel boot 时自动发现加载，零代码变更。

## 成员清单

### skills/
Agent 技能定义文件，遵循 Anthropic Agent Skills 开放规范。Kernel 启动时扫描 `SKILL.md` / `skill.md`。

`scan.md`: 多标的扫描筛选，按标准排序产出候选名单
`compare.md`: 多标的并排对比，统一指标矩阵 + 推荐边界
`review.md`: 持仓/决策回顾复盘
`research/SKILL.md`: 单标的深度研究笔记，技术面指标 + 论点 + 风险
`openbb/SKILL.md`: OpenBB 金融数据网关，覆盖基本面/宏观/量化/技术/多资产/筛选，通过 bash 执行 SDK 调用
`self-evolve.md`: AthenaClaw 自我进化规则 — 架构认知/设计哲学/工作空间感知/可观测性，修改自身代码时作为 context 注入 ask_coder

### subagents/
`technician.md`: 量化技术分析子代理，工具白名单 [market_ohlcv, compute]，拉行情算指标输出结构化技术评估
`researcher.md`: 信息研究子代理，工具白名单 [web_search, web_fetch]，多角度搜索新闻事件输出研究报告
`coder.md`: 通用代码专家子代理，工具白名单 [read, write, edit, bash]，理解/诊断/修改代码，80轮/500K tokens/30分钟

[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md

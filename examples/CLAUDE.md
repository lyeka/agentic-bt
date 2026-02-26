# examples/
> L2 | 父级: /CLAUDE.md

## 成员清单
`__init__.py`: 包入口
`strategies.py`: 策略注册表 + 5 个 Mock Agent 类 + 7 个 LLM Prompt + STRATEGIES dict + get_strategy/list_strategies

## 策略矩阵

| 策略 | Mock | 框架能力 | regime |
|------|------|---------|--------|
| rsi | RsiMockAgent | 市价单/单指标 | mean_reverting |
| bracket_atr | BracketAtrMockAgent | Bracket/多指标/动态止损 | trending |
| bollinger_limit | BollingerLimitMockAgent | 限价单/order管理/valid_bars | volatile |
| adaptive_memory | AdaptiveMemoryMockAgent | memory_note/recall/自适应仓位 | mean_reverting |
| multi_asset | MultiAssetMockAgent | 多资产/风控/轮动 | bull_bear |
| free_play | LLM-only | 全工具链自由探索 | random |
| reflective | LLM-only | 记忆系统深度/自我反思 | random |

[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md

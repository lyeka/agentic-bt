# athenaclaw/

## 定位

AthenaClaw 主产品包。

## 结构

- `kernel/`：Kernel、Session、Permission、prompt 组装
- `runtime/`：AgentConfig、KernelBundle、trace wiring、session store
- `llm/`：消息模型、provider、context 压缩
- `tools/`：filesystem、compute、market（含 market_snapshot）、trade（trade_account/trade_execute）、portfolio、watchlist、shell、web
- `automation/`：任务定义、执行、worker
- `trading/`：交易域 canonical 类型、TradeOrchestrator（execute_limit/execute_cancel 单步执行）、RiskGuard seam、audit store、账户快照映射
- `skills/`：skills 发现与展开
- `subagents/`：子代理定义、运行和系统集成
- `interfaces/`：CLI、Telegram、Discord、TUI、IM
- `integrations/`：market/web provider
- `observability/`：trace

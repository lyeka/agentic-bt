# tests/
> L2 | 父级: /CLAUDE.md

## 成员清单
`conftest.py`: 共享 fixtures + 项目根目录 path 注入（使 examples/ 可导入）
`features/engine.feature`: Engine 市场模拟行为规格（含 recent_bars scenario）
`features/indicators.feature`: 技术指标计算行为规格
`features/memory.feature`: 记忆系统行为规格
`features/tools.feature`: 工具桥接层行为规格（含 market_history scenarios）
`features/agent.feature`: Agent ReAct 决策行为规格
`features/runner.feature`: 回测编排行为规格
`features/eval.feature`: 评估计算行为规格
`features/context.feature`: 上下文工程行为规格（11 scenarios）
`features/data.feature`: 数据生成行为规格（7 scenarios，regime 多行情模式）
`features/tracer.feature`: 可观测性追踪行为规格（7 scenarios）
`features/compute.feature`: 沙箱计算工具行为规格（19 scenarios：基础计算/数据访问/安全边界/错误处理/序列化/标准Python能力）
`test_engine.py`: engine.feature step definitions（含 recent_bars steps）
`test_indicators.py`: indicators.feature step definitions
`test_memory.py`: memory.feature step definitions
`test_tools.py`: tools.feature step definitions（含 market_history steps）
`test_agent.py`: agent.feature step definitions（mock LLM，context: Context 类型）
`test_runner.py`: runner.feature step definitions（mock Agent，context: Context 类型）
`test_eval.py`: eval.feature step definitions
`test_context.py`: context.feature step definitions（fixture: cctx）
`test_data.py`: data.feature step definitions（fixture: dctx）
`test_tracer.py`: tracer.feature step definitions（fixture: trcx）
`test_compute.py`: compute.feature step definitions（fixture: cptx）
`test_e2e_strategies.py`: E2E 策略自动化测试（参数化 5 mock + 2 LLM-only 验证）
`features/kernel.feature`: Kernel 核心协调器行为规格（13 scenarios：对话/历史/ReAct/管道/最大轮次/boot soul+workspace指南/soul刷新/workspace指南/memory不进prompt/日期注入/auto-compact/overflow-compact/session-summary）
`features/memory_compress.feature`: Memory 自动压缩行为规格（3 scenarios：超限触发/未超限/markdown格式）
`test_kernel.py`: kernel.feature step definitions（fixture: kctx，Mock LLM）
`test_memory_compress.py`: memory_compress.feature step definitions（fixture: mcctx，mock LLM 压缩）
`features/kernel_tools.feature`: Kernel 工具与工作区行为规格（11 scenarios：market OHLCV 数据返回+日期透传/compute/read/write/edit/权限/Session 持久化/自举；recall 已移除）
`test_kernel_tools.py`: kernel_tools.feature step definitions（fixture: ktctx，直接调用 handler，SpyAdapter 记录 fetch 参数）
`features/sandbox_thread.feature`: 沙箱线程安全行为规格（3 scenarios：主线程执行/子线程执行/子线程超时）
`test_sandbox_thread.py`: sandbox_thread.feature step definitions（fixture: sbtx，threading.Thread 子线程验证）
`features/tushare_adapter.feature`: TushareAdapter 行为规格（5 scenarios：列名标准化/日期类型/排序/日期范围透传/默认范围）
`test_tushare_adapter.py`: tushare_adapter.feature step definitions（fixture: tsctx，mock tushare API）
`features/yfinance_adapter.feature`: YFinanceAdapter 行为规格（5 scenarios：列名标准化/日期类型/排序/日期范围透传/默认范围）
`test_yfinance_adapter.py`: yfinance_adapter.feature step definitions（fixture: yfctx，mock yfinance download）
`features/finnhub_adapter.feature`: FinnhubAdapter 行为规格（5 scenarios：列名标准化/日期类型/排序/UNIX时间戳透传/默认范围）
`test_finnhub_adapter.py`: finnhub_adapter.feature step definitions（fixture: fhctx，mock finnhub client）
`features/market_routing.feature`: CompositeMarketAdapter 路由行为规格（5 scenarios：匹配路由/fallback/first-match-wins/无fallback异常/仅fallback）
`test_market_routing.py`: market_routing.feature step definitions（fixture: mrctx，FakeAdapter 纯路由逻辑）
`features/agent_tools.feature`: Agent 工具系统行为规格（20 scenarios：read 分页截断行号/edit 模糊匹配唯一性diff/write 字节数/bash 超时截断/路径安全）
`test_agent_tools.py`: agent_tools.feature step definitions（fixture: atx，MockKernel + 双信任区域）
`features/skills.feature`: Skill Engine 行为规格（6 scenarios：发现/注入/显式展开/disable-model-invocation/模型自主 skill_invoke）
`test_skills.py`: skills.feature step definitions（fixture: sctx，Mock LLM + skill 临时目录）
`features/im_driver.feature`: IM 通用驱动行为规格（9 scenarios：鉴权/进度状态/确认交互/会话持久化/默认隐藏过程消息/new命令/reset别名/context统计/compact压缩）
`test_im_driver.py`: im_driver.feature step definitions（fixture: imctx，FakeBackend + FakeKernel + bundle_factory）
`test_telegram_adapter.py`: Telegram 适配器 helper 单测（allowlist/bool/render_mode 解析 + markdown->HTML 渲染）
`features/web_tools.feature`: Web 工具行为规格（9 scenarios：web_search 结构化结果/域名过滤/上限/失败；web_fetch 内容/截断/无效URL/网络错误；条件注册）
`test_web_tools.py`: web_tools.feature step definitions（fixture: wctx，MockSearchAdapter + patch _fetch_url）
`features/context_ops.feature`: 上下文管理行为规格（7 scenarios：token估算/统计/短历史不压缩/压缩返回摘要/保留原样/结构化摘要）
`test_context_ops.py`: context_ops.feature step definitions（fixture: coctx，mock LLM client）
`features/tui.feature`: TUI 终端界面行为规格（9 scenarios：消息收发/空输入/确认对话框/工具进度/历史恢复/流式输出/新建会话/耗时元数据/异常错误提示）
`test_tui.py`: tui.feature step definitions（fixture: tuictx，FakeKernel + MemorySessionStore + Textual app.run_test）

[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md

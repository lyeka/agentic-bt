# agent/
> L2 | 父级: /CLAUDE.md

## 定位

持久投资助手 — Kernel-centric 架构，import core/ 公共基础，不依赖 agenticbt。

## 成员清单
`__init__.py`: 包入口
`kernel.py`: Kernel 核心协调器（ReAct loop + wire/emit 声明式管道 + DataStore + Permission 权限 + boot 自举 + Skill Engine 集成 + /skill 显式展开 + skill_invoke 工具 + _assemble_system_prompt 注入 skills 摘要 + auto-compact 自动上下文压缩 + overflow 溢出重试）；Session 会话容器（持久化 save/load + summary 对话摘要）；DataStore 数据注册表；Permission 枚举；MemoryCompressor Protocol；MEMORY_MAX_CHARS = 100_000；WORKSPACE_GUIDE 元认知框架
`context_ops.py`: 上下文管理纯函数层（estimate_tokens token 估算 + ContextInfo/context_info 统计 + CompactResult/compact_history 对话压缩 + _llm_compress LLM 摘要生成含 fallback）
`skills.py`: Agent Skills 引擎（目录发现 + SKILL.md/frontmatter 解析 + 校验诊断 + 重名冲突处理 + `<available_skills>` XML 注入文本生成 + `/skill:name` 命令展开 + skill_invoke 载荷构建）
`runtime.py`: 入口无关的 Kernel 组装层（AgentConfig + KernelBundle + 统一 tools/permissions/wires/trace/session 路径约定 + MARKET_CN/MARKET_US 显式声明数据源 + _make_adapter 工厂 + Composite 异源组装）
`session_store.py`: SessionStore 抽象 + JsonSessionStore（兼容旧格式 + 原子写）

### tools/
`__init__.py`: 工具包入口
`_path.py`: 路径安全基础设施（resolve_path/is_trusted/check_trust/check_write_permission），双信任区域（workspace+cwd）
`_truncate.py`: 截断基础设施（truncate_head/truncate_tail），双限制（行数+字节），read 用 head，bash 用 tail
`read.py`: read 工具 — 文件读取（行号+分页+截断+二进制检测+目录列表）
`write.py`: write 工具 — 文件写入（自动创建目录+权限检查+字节数反馈）
`edit.py`: edit 工具 — 精确文本替换（模糊匹配+唯一性检查+diff 输出）
`market.py`: MarketAdapter Protocol + market_ohlcv 工具注册（返回原始 OHLCV records + start/end 时间范围透传），adapter pattern 解耦数据源
`compute.py`: 沙箱 Python 计算，自动从 DataStore 注入 OHLCV
`bash.py`: shell 命令执行；subprocess + 超时 + 进程树清理（os.killpg）+ tail 截断；USER_CONFIRM 权限
`web.py`: SearchAdapter Protocol + web_search/web_fetch 工具注册；Jina Reader 优先 + stdlib fallback；fetch 始终注册，search 按 adapter 条件注册

### adapters/
`__init__.py`: 适配器层入口
`cli.py`: CLI REPL 入口（dotenv + runtime 统一组装 + state_dir Session 持久化 + 旧会话迁移 + /new /compact /context /help 命令路由）
`telegram.py`: Telegram Bot 入口（polling + allowlist + InboundMessage 映射 + IMDriver 驱动 + markdown->HTML 基础渲染 + 过程消息开关）

### adapters/tui/
`__init__.py`: TUI 终端界面包入口
`app.py`: InvestmentApp(App) — Textual TUI 主界面（布局/ChatInput/UserSubmitted 消息/worker 线程 kernel.turn/进度事件渲染/confirm 桥接/sidebar 工作区状态）
`screens.py`: ConfirmScreen(ModalScreen) — 文件写入确认对话框（y/n 快捷键 + 按钮）
`commands.py`: AppCommandProvider(Provider) — 命令面板（重置会话/切换侧边栏/查看状态/退出）
`app.tcss`: TUI CSS 样式（布局/消息气泡/侧边栏/输入区）

### adapters/im/
`__init__.py`: IM 通用驱动层入口
`backend.py`: IMBackend 协议 + InboundMessage/OutboundRef（平台抽象）
`driver.py`: IMDriver（鉴权/命令路由 /new /reset /compact /context /status /help/并发锁/进度状态更新/confirm 桥接/session 落盘）
`confirm_bridge.py`: async confirm -> sync bool 桥接（给 Kernel.on_confirm）
`progress.py`: 进度缓冲与渲染（状态消息行聚合）

### adapters/market/
`__init__.py`: 市场数据适配器入口
`csv.py`: CsvAdapter — 基于 DataFrame dict 的测试用 MarketAdapter
`tushare.py`: TushareAdapter — A 股日线 OHLCV，tushare Pro API
`yfinance.py`: YFinanceAdapter — 美股日线 OHLCV，Yahoo Finance（零 API Key）
`finnhub.py`: FinnhubAdapter — 美股日线 OHLCV，Finnhub REST API（后备源，需免费 Key）
`composite.py`: CompositeMarketAdapter — 多数据源聚合路由器（matcher + fallback），对外满足 MarketAdapter Protocol；is_ashare 便利函数

### adapters/web/
`__init__.py`: web 搜索适配器包入口
`tavily.py`: TavilyAdapter — Tavily Search API（agent-native，返回 {title, url, snippet, score}）

### bootstrap/
`__init__.py`: 自举包入口
`seed.py`: SEED_PROMPT — 首次启动种子 system prompt，给定初始人格与语言风格（口语化/有观点/短句），通过自然对话延迟结晶 soul.md/memory.md

[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md

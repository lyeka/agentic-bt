# agent/
> L2 | 父级: /CLAUDE.md

## 定位

持久投资助手 — Kernel-centric 架构，import core/ 公共基础，不依赖 agenticbt。

## 成员清单
`__init__.py`: 包入口
`kernel.py`: Kernel 核心协调器（ReAct loop + wire/emit 声明式管道 + DataStore + Permission 权限 + boot 自举）；Session 会话容器（持久化 save/load）；DataStore 数据注册表；Permission 枚举

### tools/
`__init__.py`: 工具包入口
`_path.py`: 路径安全基础设施（resolve_path/is_trusted/check_trust/check_write_permission），双信任区域（workspace+cwd）
`_truncate.py`: 截断基础设施（truncate_head/truncate_tail），双限制（行数+字节），read 用 head，bash 用 tail
`read.py`: read 工具 — 文件读取（行号+分页+截断+二进制检测+目录列表）
`write.py`: write 工具 — 文件写入（自动创建目录+权限检查+字节数反馈）
`edit.py`: edit 工具 — 精确文本替换（模糊匹配+唯一性检查+diff 输出）
`market.py`: MarketAdapter Protocol + market.ohlcv 工具注册，adapter pattern 解耦数据源
`compute.py`: 沙箱 Python 计算，自动从 DataStore 注入 OHLCV
`recall.py`: 全文搜索 workspace .md 文件，返回匹配段落
`bash.py`: shell 命令执行；subprocess + 超时 + 进程树清理（os.killpg）+ tail 截断；USER_CONFIRM 权限

### adapters/
`__init__.py`: 适配器层入口
`cli.py`: CLI REPL 完整入口（dotenv + boot + 7 工具注册 + 权限 + Session 持久化）

### adapters/market/
`__init__.py`: 市场数据适配器入口
`csv.py`: CsvAdapter — 基于 DataFrame dict 的测试用 MarketAdapter
`tushare.py`: TushareAdapter — A 股日线 OHLCV，tushare Pro API

### bootstrap/
`__init__.py`: 自举包入口
`seed.py`: SEED_PROMPT — 首次启动种子 system prompt，引导 Agent 创建工作区

[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md

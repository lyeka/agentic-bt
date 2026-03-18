# AthenaClaw

个人投资研究 Agent。

AthenaClaw 不是一堆散装工具，而是一个已经预连通的 agent 系统：`market_ohlcv` 拉到的 OHLCV 会自动进入 `compute`，`soul.md` 变更会刷新 system prompt，`memory.md` 超限会自动压缩。它长期运行在自己的 workspace 里，持续积累人格、记忆、研究笔记和自动化任务。

## 安装

```bash
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"
```

## 快速开始

```bash
cp .env.example .env
```

至少配置：

- `ATHENACLAW_API_KEY`
- `ATHENACLAW_MODEL`
- `TUSHARE_TOKEN` 或使用默认 `yfinance`

启动 CLI：

```bash
python -m athenaclaw
```

也可以直接用 console script：

```bash
athenaclaw
athenaclaw-telegram
athenaclaw-discord
athenaclaw-worker
athenaclaw-harness start     # 监督模式（推荐生产部署）
```

## 服务管理 (Harness)

```bash
athenaclaw-harness start              # 监督模式启动（崩溃自动重启 + 更新后循环）
athenaclaw-harness status             # 查看版本 + 可用更新 + 运行中的服务
athenaclaw-harness update             # 更新到最新版本（幂等 + 自动回滚）
athenaclaw-harness update v1.2.0      # 更新到指定版本
athenaclaw-harness version            # 显示版本号
```

详见 [docs/harness.md](docs/harness.md)。

## 自我进化

AthenaClaw 通过 Coder SubAgent + self-evolve Skill 实现自我代码修改：

- **Coder SubAgent** (`.agents/subagents/coder.md`) — 通用代码专家（理解/诊断/修改）
- **self-evolve Skill** (`.agents/skills/self-evolve.md`) — AthenaClaw 特定规则

Agent 在独立分支上修改代码 → 提 PR → review → merge → `athenaclaw-harness update` 部署。

详见 [docs/self-evolution.md](docs/self-evolution.md)。

## 运行模型

AthenaClaw 使用一组应用级环境变量：

- `ATHENACLAW_MODEL`
- `ATHENACLAW_BASE_URL`
- `ATHENACLAW_API_KEY`
- `ATHENACLAW_WORKSPACE`
- `ATHENACLAW_STATE_DIR`
- `ATHENACLAW_ENABLE_BASH`

第三方服务保持原始 provider 变量名：

- `TUSHARE_TOKEN`
- `FINNHUB_API_KEY`
- `TAVILY_API_KEY`
- `TELEGRAM_BOT_TOKEN`
- `DISCORD_BOT_TOKEN`

## 架构

```text
athenaclaw/
  kernel/          # ReAct loop、权限、system prompt、自举
  runtime/         # 配置、bundle、wiring、session store
  llm/             # 消息模型、provider 适配、context 压缩
  tools/           # filesystem / compute / market / shell / web
  automation/      # task plan/apply/context/control 与 worker
  skills/          # skill 发现、展开、注入
  subagents/       # 子代理定义、加载、执行、工具桥接
  interfaces/      # CLI / Telegram / Discord / TUI / IM
  integrations/    # market / web provider 集成
  observability/   # trace 写入
  harness.py       # 服务管理（update/status/start）
```

设计原则：

- Kernel-centric：所有行为经由同一个 Kernel 协调
- Tool semantics stable：工具名和工具参数语义保持稳定
- Agent-first persistence：`soul.md`、`memory.md`、`notebook/` 是第一公民
- Interfaces vs integrations 分离：入口与外部依赖不混放

## 常用入口

CLI：

```bash
python -m athenaclaw
python -m athenaclaw.interfaces.cli --simple
```

Telegram：

```bash
python -m athenaclaw.interfaces.telegram
```

Discord：

```bash
python -m athenaclaw.interfaces.discord
```

Automation worker：

```bash
python -m athenaclaw.automation.worker
```

## 测试

```bash
.venv/bin/pytest -q
```

当前主线测试覆盖 Kernel、tools、skills、subagents、automation、market adapters、IM adapters 和 TUI。

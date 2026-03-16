# AthenaClaw Architecture

AthenaClaw 是一个长期运行的个人投资研究 Agent。

## 核心原则

- Kernel-centric：所有对话、工具调用、子代理委派和权限判断都经由 `Kernel`
- Agent-first persistence：`soul.md`、`memory.md`、`notebook/`、automation tasks 都是第一公民
- Stable tool semantics：`market_ohlcv`、`compute`、`read`、`write`、`edit`、`bash`、`web_*` 的语义稳定
- Interfaces vs integrations：用户入口和外部 provider 解耦

## 目录边界

```text
src/athenaclaw/
  kernel/         # ReAct loop、权限、prompt、自举
  runtime/        # config、bundle、trace wiring、session store
  llm/            # provider 抽象、消息模型、context 压缩
  tools/          # filesystem / compute / market / shell / web
  automation/     # task 模型、store、executor、worker
  skills/         # skill 发现、展开、注入
  subagents/      # 子代理定义、运行、工具桥接
  interfaces/     # CLI / Telegram / Discord / TUI / IM
  integrations/   # market/web provider 适配
  observability/  # JSONL trace
```

## 运行时数据流

```text
User / IM / TUI
      |
      v
  interfaces/*
      |
      v
    Kernel
      |
      +--> tools/*
      +--> skills/*
      +--> subagents/*
      +--> automation/*
      |
      v
 workspace + state
```

## 关键机制

- `market_ohlcv` 拉取的标准化 OHLCV 会写入 `Kernel.data`
- `compute` 从 `Kernel.data` 选择匹配的 OHLCV 执行沙箱代码
- `soul.md` 写入会触发 system prompt 重组
- `memory.md` 写入会触发超限压缩
- `runtime.build_kernel_bundle()` 负责把 tools、permissions、trace、session store、automation wiring 统一装配起来

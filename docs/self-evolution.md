# Self-Evolution — Agent 自我修改

AthenaClaw 通过 **Coder SubAgent** + **self-evolve Skill** 实现自我代码修改。

## 架构

```
用户: "添加 RSI 工具"
  ↓
Main Agent → 加载 self-evolve skill → ask_coder(task, context)
  ↓
Coder SubAgent:
  1. 读 CLAUDE.md (自我认知)
  2. 创建分支 → 修改代码
  3. git commit → push → gh pr create
  ↓
返回 PR 链接给用户
```

## 两层分离

| 层 | 文件 | 职责 |
|----|------|------|
| Coder SubAgent | `.agents/subagents/coder.md` | 通用编码专家，可操作任何代码库 |
| self-evolve Skill | `.agents/skills/self-evolve.md` | AthenaClaw 特定规则，通过 context 参数注入 |

## Coder SubAgent 三重角色

- **理解者**: 解释架构、追踪代码路径、回答实现问题
- **诊断者**: 调查错误、读 trace/日志、找 root cause
- **修改者**: 创建分支、写代码、提 PR

## PR 工作流

1. Agent（Coder SubAgent）在独立分支上修改代码
2. 通过 `gh pr create` 提交 PR
3. Maintainer review + merge
4. 通过 `athenaclaw-harness update` 部署新版本

Agent **不直接推送到 master**，**不直接打 tag**。所有变更经过 review。

## self-evolve Skill 内容

- 自我认知协议（读 CLAUDE.md L1/L2/L3）
- 设计哲学（好品味、实用主义、简洁）
- 架构原则（Kernel-centric、Event-driven）
- 编码规范（L3 头部、中文注释、tool 注册模式）
- 工作空间感知（portfolio.json、watchlist.json、trace 等）
- 可观测性感知（trace 事件、wire/emit 机制）

## 更新部署

详见 [harness.md](harness.md)。

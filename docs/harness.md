# Harness — 服务管理

AthenaClaw 的进程生命周期管理工具。所有用户（普通用户、开发者、运维）通过 `athenaclaw-harness` 管理 Agent 服务。

## 快速开始

```bash
# 启动（监督模式，崩溃自动重启）
athenaclaw-harness start

# 纯文本模式
athenaclaw-harness start --simple
```

## 命令

### status — 查看当前状态

```bash
athenaclaw-harness status
```

输出示例:
```
AthenaClaw 0.1.0 (tag: v0.1.0, commit: 7661f54)
Up to date

Running services:
  cli          PID 12345
  worker       PID 12347
```

### update — 更新版本

```bash
# 更新到最新
athenaclaw-harness update

# 更新到指定版本
athenaclaw-harness update v1.2.0
```

更新流程：
1. `git fetch` 获取远端最新
2. `git pull --ff-only` 或 `git checkout <version>`
3. `pip install -e .` 重新安装
4. 健康检查（`import athenaclaw`）
5. 失败自动回滚到更新前版本

### version — 显示版本号

```bash
athenaclaw-harness version
```

### start — 监督模式启动

```bash
athenaclaw-harness start [agent_args...]
```

- 在 while-loop 中启动 agent 进程
- Agent 正常退出（exit 0）→ harness 停止
- Agent 请求更新（exit 42）→ harness 自动 update + 重启
- Agent 异常退出 → harness 停止

## 对话中更新

用户可以在对话中让 Agent 自行检查和执行更新：

- "请检查是否有更新" → Agent 调用 `athenaclaw-harness status`
- "更新到最新版本" → Agent 调用 `athenaclaw-harness update`，然后触发重启

## 部署方式

| 环境 | 启动命令 |
|------|----------|
| 本地开发 | `athenaclaw-harness start` |
| macOS 服务 | launchd plist → `athenaclaw-harness start` |
| Linux 服务 | systemd unit → `athenaclaw-harness start` |
| Docker | `CMD ["athenaclaw-harness", "start"]` |

## 版本管理

- 版本号定义在 `pyproject.toml` 的 `version` 字段
- Git tag 格式: `v{version}` (如 `v0.1.0`)
- Agent 通过 PR 提议版本变更，maintainer review 后 merge
- CI 自动化或 maintainer 手动打 tag

## 环境变量

| 变量 | 用途 | 默认值 |
|------|------|--------|
| `ATHENACLAW_INSTALL_DIR` | 安装目录 | 自动检测 (git root) |

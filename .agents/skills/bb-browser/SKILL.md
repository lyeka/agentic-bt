---
name: bb-browser
description: 浏览器自动化与信息获取工具。通过用户真实 Chrome 浏览器 + 登录态，获取公域/私域信息、操作网页、执行表单填写。支持 36 个平台 103 条 site 命令实时获取结构化数据。使用场景：(1) 需要从网站获取信息 (2) 需要操作网页（填表、点击、截图）(3) 用户说"打开网页"、"搜推特"、"查股票"、"爬数据"等浏览器相关请求
allowed-tools: Bash(bb-browser:*)
---

# bb-browser — 互联网即 API

用户真实 Chrome 浏览器 + 已登录的账号 = 无需 API key，无需反爬，直接获取公域和私域信息。

## 两种使用模式

### 模式 A: Site 适配器（数据获取，首选）

一行命令从 36 个平台获取结构化 JSON 数据：

```bash
bb-browser site <platform/command> [args] [--json] [--jq '<expr>']
```

**动态发现 adapter（必做）**：不要猜命令，用 CLI 自省：

```bash
bb-browser site list                    # 所有可用 adapter（按平台分组）
bb-browser site search <keyword>        # 按关键词搜索 adapter
bb-browser site info <name>             # 查看参数、示例、域名
bb-browser site recommend               # 基于浏览历史推荐
bb-browser site update                  # 拉取最新社区 adapter
```

**使用示例**：

```bash
bb-browser site twitter/search "AI agent"
bb-browser site xueqiu/hot-stock 5 --jq '.items[] | {name, changePercent}'
bb-browser site github/issues owner/repo
bb-browser site zhihu/hot
```

**登录态处理**：如果返回 401/403，提示用户在浏览器中登录该网站，然后重试。

### 模式 B: 浏览器自动化（页面操作）

直接控制浏览器进行交互操作：

```bash
bb-browser open <url>        # 打开页面（新 tab）
bb-browser snapshot -i       # 获取可交互元素（返回 @ref）
bb-browser click @5          # 点击
bb-browser fill @3 "text"    # 填写输入框
bb-browser close             # 完成后关闭 tab
```

**核心工作流**：

```
open → snapshot -i → 用 @ref 操作 → 页面变化后重新 snapshot -i → close
```

**关键规则**：
- 操作前必须先 `snapshot -i` 获取 @ref
- 页面导航/动态加载后 @ref 失效，必须重新 snapshot
- 操作完成后必须 `close` 关闭自己打开的 tab
- 详细 ref 生命周期见 [references/snapshot-refs.md](references/snapshot-refs.md)

## 信息提取策略

| 目标 | 方法 | 原因 |
|------|------|------|
| 结构化平台数据 | `site <adapter>` | 一行命令，JSON 输出 |
| 网页正文/长文本 | `eval "document.querySelector('...').innerText"` | 直接提取，避免冗长 snapshot |
| 表单交互/按钮操作 | `snapshot -i` → `click/fill @ref` | ref 精准定位可交互元素 |
| 页面截图 | `screenshot [path.png]` | 视觉快照 |

## 命令发现

bb-browser 持续更新。不要依赖静态文档，用 CLI 自省获取最新能力：

```bash
bb-browser --help             # 完整命令列表（含所有选项）
bb-browser site list          # 所有 site adapter（36 平台 103+ 命令）
bb-browser site info <name>   # adapter 参数、示例、域名
bb-browser site search <kw>   # 按关键词搜索 adapter
```

**首次使用或不确定命令时，务必先 `--help` 或 `site list` 发现可用能力。**

## 常用选项

```bash
--json          JSON 格式输出
--jq '<expr>'   对 JSON 输出应用 jq 过滤（隐含 --json）
--tab <tabId>   指定操作的标签页
-i              snapshot 只显示可交互元素（推荐）
```

## 参考文档

| 文档 | 说明 | 何时阅读 |
|------|------|----------|
| [references/snapshot-refs.md](references/snapshot-refs.md) | Ref 生命周期、最佳实践、调试技巧 | 使用浏览器自动化模式（模式 B）遇到 ref 问题时 |

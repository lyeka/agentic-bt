# Skills 系统设计文档

> 本文档是 AthenaClaw Skill 系统的完整规格。代码变更时同步更新。

---

## 一、定位：Skill 在认知架构中的位置

在仿生设计中，Skill 对应人类投资者"学过的分析方法"——**知识**，而非能力。

```
Tool  = 能力（what you can do）  → 器官：market_ohlcv, compute, bash
Skill = 知识（how to use tools） → 方法论：research, openbb, clawhub
MCP   = 能力扩展（new organs）   → 新器官的接入协议
```

Skill 的载体永远是 **prompt（Markdown）**，不是可执行代码。安装 Skill = 学会一个新方法，不是安装一段代码。

Skill 与 Kernel 的关系类比 Unix 用户态程序与内核：Kernel 提供能力（tools = syscalls），Skill 编排能力完成任务（methods = programs）。

---

## 二、文件格式

### 目录结构

```text
skills/
  my-skill/
    SKILL.md          # 必需：skill 定义文件
    references/       # 可选：补充文档
      setup.md
      api-reference.md
  quick-skill.md      # 简易 skill：单文件
```

- skills 根目录下直接 `.md` 文件被识别为 skill
- 子目录下仅识别 `SKILL.md`（也兼容 `skill.md`）

### Frontmatter 规格

```yaml
---
# ── 必填 ──────────────────────────────────────────────────
name: compare                     # 仅小写字母/数字/连字符，1-64 字符
description: "Compare two symbols side by side."  # 1-1024 字符

# ── 可见性 ────────────────────────────────────────────────
disable-model-invocation: false   # true → 不出现在 <available_skills>，仅 /skill:name 可调

# ── requires 合约 ────────────────────────────────────────
requires:
  tools: [market_ohlcv, compute]  # 硬依赖：boot 时验证 tools 已注册
  bins: [clawhub]                 # 硬依赖：boot 时验证 PATH 可执行文件
  python: [openbb]                # 软依赖：仅 warning，不阻塞

# ── 元信息（文档性质）───────────────────────────────────
license: MIT
compatibility: "Python 3.8+"
allowed-tools: [bash]             # 文档性质，不执行约束
metadata:
  category: research
  version: "1.0"
---
```

### Name 规则

- 仅小写字母、数字、连字符（`a-z0-9-`）
- 不以 `-` 开头或结尾，不含 `--`
- 最大 64 字符
- `SKILL.md` 文件的 name 必须与父目录名一致

---

## 三、requires 合约

Skill 通过 `requires` 声明对运行环境的依赖。Kernel 在 boot 时验证合约，不满足则标记为 `degraded`。

| 字段 | 含义 | 检查方式 | 失败影响 |
|------|------|---------|---------|
| `requires.tools` | 需要的内核工具 | `set(required) ⊆ set(registered_tools)` | **硬降级** — 不出现在 prompt |
| `requires.bins` | 需要的 PATH 可执行文件 | `shutil.which(bin)` | **硬降级** — 不出现在 prompt |
| `requires.python` | 需要的 Python 包 | `importlib.import_module` | 软警告 — 仍然可用 |

降级 skill：
- **不出现**在 `<available_skills>` system prompt 中
- `skill_invoke` 调用时返回清晰错误（含 `missing_tools`/`missing_bins`）
- 仍可通过显式 `/skill:name` 命令调用（power user 覆盖）
- `skills.degraded` 事件通知 interface 层展示降级原因

兼容旧版 `required-tools` 字段，等价于 `requires.tools`。

---

## 四、发现机制

### 默认搜索路径

加载优先级（先到先得，重名后者忽略）：

1. `SKILL_PATHS` 环境变量（`os.pathsep` 分隔）
2. 从 `cwd` 向上到 git root 的项目路径：
   - `.agents/skills/`
   - `.pi/skills/`
   - `skills/`（ClawHub 默认安装目录）
3. 用户路径：
   - `~/.agents/skills/`
   - `~/.pi/agent/skills/`
   - `~/.agent/skills/`
   - `~/.claude/skills/`
   - `~/.codex/skills/`
   - `~/.cursor/skills/`

### 发现算法

1. 根目录直接 `.md` 文件 → skill 候选
2. 子目录递归 → 仅识别 `SKILL.md` / `skill.md`
3. 跳过：`node_modules`, `__pycache__`, `.venv`, `venv`, `dist`, `build`
4. 路径去重：`resolve()` 后 `seen` set

### 诊断输出

解析失败不阻塞系统，产出结构化诊断（code + message + path + name）：

| Code | 含义 |
|------|------|
| `read_failed` | 文件读取失败 |
| `frontmatter_unterminated` | frontmatter 缺少 `---` 结束 |
| `frontmatter_parse_failed` | YAML 解析失败 |
| `missing_description` | description 缺失 |
| `invalid_name_*` | name 不符合规范 |
| `name_collision` | 多个 skill 同名 |
| `missing_required_deps` | requires 合约不满足 |
| `reference_missing` | 引用文件不存在 |

---

## 五、调用流程

### 双轨调用

**显式调用**（强制展开）：

```
用户输入: /skill:compare 比亚迪 vs 宁德时代
→ parse_explicit_skill_command() → ParsedCommand(name, args)
→ expand_explicit_skill_command() → build_skill_payload()
→ <skill name="compare" location="...">body</skill> + args
→ 替换用户消息，进入 LLM
```

**模型自主调用**：

```
System prompt 包含 <available_skills> XML
→ LLM 判断任务匹配 skill
→ 调用 skill_invoke(name, args) 工具
→ invoke_skill() → 返回 body + expanded
→ LLM 按 skill 指令继续使用 tools
```

### 热重载

安装新 skill 后，Agent 调用 `reload_skills` 工具使其生效：

```
Agent 用 bash: clawhub install my-skill --workdir .agents/skills
Agent 调用 reload_skills 工具（内核工具）
→ Kernel._load_skills() 重新扫描目录
→ Kernel._validate_skills() 验证 requires
→ Kernel._assemble_system_prompt() 更新 prompt
→ 下一次 LLM 调用自动使用新 prompt
```

---

## 六、Boot 流程

```
Kernel.boot(workspace, cwd, skill_roots)
  ├─ _load_skills()               ← Parse：发现 + 解析 frontmatter
  ├─ _register_skill_invoke_tool() ← 注册 skill_invoke + reload_skills 工具
  ├─ _validate_skills()           ← Validate：requires 合约 + 引用验证
  │   ├─ requires.tools 检查
  │   ├─ requires.bins 检查（shutil.which）
  │   ├─ 引用文件存在性检查
  │   └─ 降级 skill → emit "skills.degraded" 事件
  ├─ _load_subagents()
  └─ _assemble_system_prompt()    ← 只注入 status="ready" 的 skills
```

---

## 七、ClawHub 集成

AthenaClaw 通过 **clawhub 元 Skill** 集成 ClawHub 生态。Agent 用 bash 调用 `clawhub` CLI 完成搜索/安装/更新，无内核侵入。

### 前置条件

```bash
npm i -g clawhub
```

### 典型流程

```
用户: "帮我从 ClawHub 找一个技术分析的 skill 安装一下"

Agent:
1. skill_invoke("clawhub") → 获取 clawhub skill 知识
2. bash: clawhub search "technical analysis"
3. 展示搜索结果
4. bash: clawhub install ta-master --workdir .agents/skills
5. 调用 reload_skills 工具 → 新 skill 生效
6. 回复用户
```

### clawhub skill 降级

如果 `clawhub` CLI 未安装，clawhub skill 被标记为 degraded（`requires.bins: [clawhub]`）。Agent 无法使用该 skill，interface 层提示用户安装：

```
⚠ 以下 skill 因缺少依赖被暂时禁用：
  - clawhub: 缺少可执行文件 clawhub（npm i -g clawhub）
```

### 与 OpenClaw 生态共享

ClawHub 是 OpenClaw 的公开 skill 注册表（https://clawhub.ai），AthenaClaw 通过 clawhub CLI 与其共享 skill 生态。安装的 skill 遵循相同的 SKILL.md + YAML frontmatter 规范。

---

## 八、安全模型

### Skill 是 prompt，不是代码

Skill body 直接注入 LLM context，不经过任何代码执行。真正的安全边界在工具层：

| 层 | 机制 | 作用 |
|----|------|------|
| Tool Permission | `ToolAccessPolicy` | bash/write 等工具的独立权限控制 |
| File Permission | `Permission` 系统 | soul.md 等敏感文件需要 ELEVATED 权限 |
| Skill requires | `requires` 合约 | 缺少工具的 skill 自动降级 |

### 第三方 skill 信任

- 第三方 skill 视为**不可信输入**，使用前请审查内容
- ClawHub 有社区举报 + 自动隐藏 + 版本管理机制
- 建议只安装 star 数高、来源可信的 skill

---

## 九、关键文件路径

| 文件 | 职责 |
|------|------|
| `src/athenaclaw/skills/discovery.py` | Skill 发现/解析/验证/展开/调用 |
| `src/athenaclaw/skills/__init__.py` | 公共接口导出 |
| `src/athenaclaw/kernel/service.py` | Kernel 集成（boot/validate/reload/prompt） |
| `.agents/skills/` | 项目级 skill 存储 |
| `.agents/skills/clawhub/SKILL.md` | ClawHub 元 Skill |
| `tests/bdd/features/skills.feature` | 原始 BDD 规格（6 scenarios） |
| `tests/bdd/features/skill-reliability.feature` | 可靠性 BDD（8 scenarios） |
| `tests/bdd/features/skill-lifecycle.feature` | 生命周期 BDD（3 scenarios） |

---
name: self-evolve
description: "AthenaClaw self-evolution rules: architecture awareness, design philosophy, workspace structure, observability. Load this as context when ask_coder modifies AthenaClaw code."
---

<skill>
You are modifying AthenaClaw's code. AthenaClaw is you — every code change reshapes yourself.

## Self-Awareness Protocol (mandatory before any code change)

### Phase 1: Read the Constitution
```bash
cat $ATHENACLAW_SOURCE_DIR/CLAUDE.md
```
Understand: global structure, module boundaries, development rules.

### Phase 2: Read the Module Map
```bash
cat $ATHENACLAW_SOURCE_DIR/src/athenaclaw/CLAUDE.md
```
Understand: each sub-module's responsibility and relationships.

### Phase 3: Read Target Module
Find the module you will modify. Read its CLAUDE.md (L2) and the target file's L3 header comments.
```
[INPUT]: what this file depends on
[OUTPUT]: what this file exports
[POS]: this file's role in its module
[PROTOCOL]: update this header on change, then check CLAUDE.md
```

### Phase 4: Read Runtime Data (when debugging or understanding behavior)
```bash
# Workspace data
cat $ATHENACLAW_WORKSPACE/portfolio.json    # current holdings snapshot
cat $ATHENACLAW_WORKSPACE/watchlist.json     # watchlist snapshot
cat $ATHENACLAW_WORKSPACE/soul.md            # agent personality
cat $ATHENACLAW_WORKSPACE/memory.md          # long-term memory

# Traces
tail -100 $ATHENACLAW_STATE_DIR/traces/cli/cli.jsonl
# Events: turn.*, llm.*, tool.*, tool:*, subagent.*, memory.compressed, context.*
# Format: {"ts": "ISO", "event": "xxx", "data": {...}}

# Debugging
grep "error" $ATHENACLAW_STATE_DIR/traces/cli/cli.jsonl
grep "tool.call" $ATHENACLAW_STATE_DIR/traces/cli/cli.jsonl
```

## Design Philosophy

**Good Taste**: Eliminate special cases rather than adding if/else. Three or more branches? Stop and redesign. Let boundaries naturally merge into the common path.

**Pragmatism**: Code solves real problems, not hypothetical ones. Always write the simplest working implementation first. Extend only when needed.

**Simplicity**: Each function does one thing. Nesting > 3 levels = design error. Any function > 20 lines deserves scrutiny.

## Architecture Principles

- **Kernel-centric**: All capabilities register through and coordinate via `Kernel`
- **Event-driven**: `wire/emit` provides zero-intrusion observability hooks
- **Interfaces vs Integrations**: User entry points (CLI/TUI/Telegram/Discord) decoupled from providers (market data, search, LLM)
- **Stable tool semantics**: `market_ohlcv`, `compute`, `read`, `write`, `edit`, `bash`, `web_*` have stable contracts

## Coding Standards

- **L3 headers**: Every file must have `[INPUT] [OUTPUT] [POS] [PROTOCOL]` at the top
- **Comments**: Chinese + ASCII block-style, like a polished open-source library
- **Tool registration pattern**: `xxx.register(kernel, ...)` → `kernel.tool(name, desc, params, handler)`
- **New modules**: Create CLAUDE.md (L2) + update parent's CLAUDE.md
- **File size**: ≤ 800 lines per file, ≤ 8 files per directory level

## Environment Variables (paths are configurable — never hardcode)

| Variable | Purpose | Default |
|----------|---------|---------|
| `ATHENACLAW_SOURCE_DIR` | Source code directory | — |
| `ATHENACLAW_WORKSPACE` | Workspace dir | `~/.athenaclaw/workspace` |
| `ATHENACLAW_STATE_DIR` | Runtime state dir | `~/.athenaclaw/state` |

## Workspace Structure

```
$WORKSPACE/
  soul.md         — agent personality (write triggers system prompt rebuild)
  memory.md       — long-term memory (write triggers compression when oversized)
  portfolio.json  — holdings snapshot (portfolio tool reads/writes)
  watchlist.json  — watchlist snapshot (watchlist tool reads/writes)
  notebook/       — research notes (free read/write zone)
  automation/tasks/ — automation task definitions

$STATE_DIR/
  sessions/{adapter}/{conv}.json  — conversation history
  traces/{adapter}/{conv}.jsonl   — event traces
  automation/                     — task runtime state + worker lock
```

## Wire/Emit Mechanism

```
kernel.wire("pattern", handler)  — mount observer (fnmatch patterns)
kernel.emit("event", data)       — fire event

Key wires:
  write soul.md    → triggers system prompt reassembly
  write memory.md  → triggers compression if oversized
  tool:*           → trace recording
```

## Code Smell Detection

When modifying code, actively check for:
- **Rigidity**: Small change cascades through many files?
- **Redundancy**: Same logic repeated?
- **Fragility**: Change in one place breaks unrelated parts?
- **Opacity**: Intent unclear, structure confusing?

Found a smell → fix it, note in the PR description.

## Modification Workflow

1. Self-awareness (Phase 1-4, mandatory)
2. Branch: `cd $ATHENACLAW_SOURCE_DIR && git pull && git checkout -b <branch>`
3. Implement: modify code + sync L2/L3 documentation
4. Test (optional — CI pipeline will gate): `.venv/bin/pytest tests/ -v`
5. Submit: `git add → commit → push -u → gh pr create`

## Update & Restart

```bash
athenaclaw-harness status           # check version + available updates
athenaclaw-harness update           # update to latest
athenaclaw-harness update v1.2.0    # update to specific version
```
</skill>

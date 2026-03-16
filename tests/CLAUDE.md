# tests/
> L2 | 父级: /CLAUDE.md

## 结构

- `conftest.py`: 全局 fixtures 和仓库级导入设置
- `bdd/`: 行为规格测试；`features/` 放 `.feature` 文件，同名 `test_*.py` 放 step definitions
- `unit/`: 纯函数或轻量 helper 测试，不依赖完整运行时装配
- `integration/`: 跨模块装配测试，验证 runtime/kernel/automation 级联行为

## 维护规则

- 新的行为规格优先放入 `bdd/`
- 新的纯逻辑回归优先放入 `unit/`
- 只有覆盖真实装配边界时才放入 `integration/`
- 目录说明保持高层，不在这里维护逐文件清单

[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md

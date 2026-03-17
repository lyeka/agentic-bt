# skills/
> L2 | 父级: src/athenaclaw/CLAUDE.md

Skill 发现/解析/验证/注入/展开/调用引擎。

## 成员清单

__init__.py: 公共接口导出（Skill, load_skills, validate_references, build_available_skills_prompt, invoke_skill 等）
discovery.py: 核心引擎（~530行）— Skill dataclass + requires 合约解析 + 发现 + frontmatter 解析 + validate_references + 显式展开 + 模型自主调用
invoke.py: 薄包装，re-export invoke_skill
prompting.py: 薄包装，re-export build_available_skills_prompt / build_skill_payload / expand_explicit_skill_command / parse_explicit_skill_command

[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md

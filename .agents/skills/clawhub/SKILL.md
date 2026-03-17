---
name: clawhub
description: 从 ClawHub 搜索、安装、更新 Agent Skills。当需要安装新技能、查找可用技能、更新已安装技能时使用。
requires:
  bins: [clawhub]
---

# ClawHub — Skill 包管理器

从 https://clawhub.ai 搜索和安装 Agent Skills。

## 前置条件

```bash
npm i -g clawhub
```

## 搜索 skill

```bash
clawhub search "关键词"
clawhub search "technical analysis" --limit 10
```

## 安装 skill

```bash
# 安装到项目 .agents/skills 目录（推荐）
clawhub install <skill-slug> --workdir .agents/skills

# 指定版本
clawhub install <skill-slug> --version 1.2.3 --workdir .agents/skills

# 强制覆盖已存在的同名 skill
clawhub install <skill-slug> --force --workdir .agents/skills
```

## 更新 skill

```bash
clawhub update <skill-slug> --workdir .agents/skills
clawhub update --all --workdir .agents/skills
```

## 列出已安装

```bash
clawhub list
```

## 发布 skill

```bash
clawhub login
clawhub publish ./my-skill --slug my-skill --name "My Skill" --version 1.0.0 --changelog "Initial release"
```

## 关键事项

- 安装完成后，**必须调用 `reload_skills` 工具**使新 skill 生效
- 推荐使用 `--workdir .agents/skills` 安装到项目目录
- 默认 Registry: https://clawhub.com（可通过 CLAWHUB_REGISTRY 环境变量覆盖）
- 浏览所有可用 skill: https://clawhub.ai

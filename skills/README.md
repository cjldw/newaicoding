# 平台官方 Skills(镜像预装挂点说明)

镜像预装 Skills 的**实际源目录是 `docker/devbox/skills/`**(目录式 `<name>/SKILL.md`,YAML front-matter 含 name/description),由 `docker/devbox/Dockerfile` 构建(context=仓库根)时 COPY 到镜像 `/home/node/.claude/skills/`。

- 本目录(仓库根 `skills/`)为历史占位,**构建不引用**;新预装 Skill 请放入 `docker/devbox/skills/<name>/SKILL.md`。
- R17 落地后官方/项目级 Skills 主要经数据库 + 任务创建时注入容器,镜像预装位仅保留平台基础三件(code-review/refactoring/writing-tests)。

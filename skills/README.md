# 平台官方 Skills(镜像预装位)

本目录为 `platform/devbox:v1` 镜像的 Skills 预装挂点(D15/R17:构建时 COPY 到镜像 `/home/vscode/.claude/skills/`)。

- R17 落地后官方/项目级 Skills 主要经数据库 + 任务创建时注入容器,本目录保留空占位与构建契约。
- 需要镜像内置的平台级 Skill,把 Markdown 文件(YAML frontmatter)放进本目录即可。

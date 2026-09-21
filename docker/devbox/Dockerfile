# 旗程任务容器镜像(按 ARCH D10:基于 devcontainer universal + Claude CLI)
# R17:预装常用 MCP server 与平台官方 Skills(注入时项目级覆盖同名)
FROM mcr.microsoft.com/devcontainer/universal:linux

USER root

# Claude CLI
RUN npm install -g @anthropic-ai/claude-code

# 预装高频 Python 包
RUN pip3 install --break-system-packages \
    fastapi uvicorn sqlalchemy pytest requests httpx

# 预装高频 npm 包
RUN npm install -g vite create-react-app

# 预装常用 MCP server(按 D15/R17)
RUN npm install -g \
    @modelcontextprotocol/server-filesystem \
    @modelcontextprotocol/server-git \
    @modelcontextprotocol/server-github \
    @modelcontextprotocol/server-sqlite \
    @modelcontextprotocol/server-brave-search

# 预装平台官方 Skills(按 R17;任务创建时项目级 Skills 覆盖同名)
COPY skills/ /home/codespace/.claude/skills/

USER codespace
WORKDIR /workspace
CMD ["/bin/bash"]

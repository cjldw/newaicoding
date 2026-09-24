# Runner 镜像(R16:分布式容器执行的薄代理)
# 构建:docker build -t platform/runner:v1 -f docker/runner/Dockerfile runner/
# R31.F3(BUG-049):基础镜像参数化——docker.io 不可达的环境(如国内网络)可
# --build-arg BASE_IMAGE=python:3.10 用本地已有基础镜像构建,平台侧自动回退见
# local_runner_service._ensure_image
ARG BASE_IMAGE=python:3.12-slim
FROM ${BASE_IMAGE}

RUN pip3 install --no-cache-dir fastapi uvicorn websockets docker

COPY main.py container_manager.py terminal_manager.py file_watcher.py /app/

WORKDIR /app
CMD ["python3", "main.py"]

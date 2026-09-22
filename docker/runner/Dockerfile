# Runner 镜像(R16:分布式容器执行的薄代理)
# 构建:docker build -t platform/runner:v1 -f docker/runner/Dockerfile runner/
FROM python:3.12-slim

RUN pip3 install --no-cache-dir fastapi uvicorn websockets docker

COPY main.py container_manager.py terminal_manager.py file_watcher.py /app/

WORKDIR /app
CMD ["python3", "main.py"]

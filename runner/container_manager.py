"""Runner 容器管理 - R8(Docker SDK 封装;docker 客户端可注入便于测试)

职责:
- 分配随机宿主机端口(20000-29999,冲突自动重试;D20 无本地代理层)
- docker run:端口直接映射 + env 注入 + 资源限制
- 容器内执行 git clone / checkout / force push(通过 docker exec)
- 监听 Docker events(start/die/oom)
"""

import logging
import random
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)

PORT_RANGE_START = 20000
PORT_RANGE_END = 29999
MAX_RESTARTS = 3  # 崩溃自动 restart ≤ 3 次


def allocate_ports(needed: list[int], rng: Optional[random.Random] = None,
                   taken: Optional[set[int]] = None) -> dict[int, int]:
    """
    为容器内端口分配随机宿主机端口(范围 20000-29999,不冲突)。
    返回 {容器端口: 宿主机端口}。
    """
    rng = rng or random.Random()
    taken = taken if taken is not None else set()
    mapping: dict[int, int] = {}
    for container_port in needed:
        for _ in range(100):  # 冲突自动重试
            candidate = rng.randint(PORT_RANGE_START, PORT_RANGE_END)
            if candidate not in taken and candidate not in mapping.values():
                mapping[container_port] = candidate
                taken.add(candidate)
                break
        else:
            raise RuntimeError(f"无法为容器端口 {container_port} 分配宿主机端口(范围耗尽)")
    return mapping


class ContainerManager:
    """Docker 容器管理(docker_client 工厂可注入;测试传 fake)"""

    def __init__(self, client_factory: Optional[Callable[[], Any]] = None) -> None:
        # 惰性导入 docker SDK:平台开发机无需安装
        self._client_factory = client_factory or self._default_client_factory
        self._restart_counts: dict[str, int] = {}

    @staticmethod
    def _default_client_factory() -> Any:
        import docker  # Runner 机器安装:pip install docker

        return docker.from_env()

    @property
    def client(self) -> Any:
        if not hasattr(self, "_client"):
            self._client = self._client_factory()
        return self._client

    # -----------------------------------------------------------------
    # 启动
    # -----------------------------------------------------------------
    def start_container(
        self,
        task_id: str,
        image: str,
        env: dict,
        ports: list[int],
        repos: list[dict],
        cpu_limit: str = "2c",
        mem_limit: str = "4g",
        disk_limit: str = "10g",
    ) -> dict:
        """
        拉起容器:
        1. 分配随机宿主机端口
        2. docker run(-p 直接映射宿主机;env 注入;资源限制)
        3. 容器内逐 repo 执行 git clone + checkout(+ 建工作分支)
        返回 {"container_id": docker_id, "ports": {"5173": 20001, ...}}
        """
        port_map = allocate_ports(ports)
        port_args: list[str] = []
        for cport, hport in port_map.items():
            port_args += ["-p", f"{hport}:{cport}"]

        # docker run(用 SDK;labels 标记平台容器便于清理与事件过滤)
        run_kwargs: dict[str, Any] = {
            "image": image,
            "detach": True,
            "environment": env,
            "labels": {"qicheng.task_id": task_id, "qicheng.managed": "true"},
            "nano_cpus": _cpu_limit_to_nano_cpus(cpu_limit),
            "mem_limit": mem_limit,
        }
        if port_args:
            run_kwargs["ports"] = {f"{c}/tcp": h for c, h in port_map.items()}

        container = self.client.containers.run(**run_kwargs)
        logger.info("容器已启动 container=%s task=%s ports=%s", container.short_id, task_id, port_map)

        # git clone + checkout(逐 repo;失败抛出由调用方标记 failed 并清理)
        try:
            for repo in repos:
                self._clone_repo(container, repo)
        except Exception:
            logger.exception("容器内 git 操作失败 container=%s", container.short_id)
            self.stop_container(container.short_id, force_push=False)
            raise

        self._restart_counts.pop(container.short_id, None)
        return {
            "container_id": container.short_id,
            "ports": {str(c): h for c, h in port_map.items()},
        }

    def _clone_repo(self, container: Any, repo: dict) -> None:
        """容器内:git clone {url} {path} + checkout branch(+ 建工作分支)"""
        url = repo["url"]
        path = repo["path"]
        branch = repo.get("branch")

        _exec(container, f"git clone {url} {path}")
        if branch:
            # 先尝试 checkout 远端分支;不存在则从当前 HEAD 建新分支(需求分支语义)
            code = _exec(container, f"git checkout {branch}", cwd=path, check=False)
            if code != 0:
                _exec(container, f"git checkout -b {branch}", cwd=path)

    # -----------------------------------------------------------------
    # 停止(销毁前强制 push)
    # -----------------------------------------------------------------
    def stop_container(self, container_id: str, force_push: bool = True, repos: Optional[list[dict]] = None) -> bool:
        """
        停止并销毁容器:
        1. force_push=True 时逐 repo 执行 git push(--force-with-lease 语义由任务层保证,
           此处 push 所有本地分支)
        2. docker stop + rm
        返回 push 是否全部成功(False 时调用方按分片保留容器 30 分钟重试)。
        """
        container = self.client.containers.get(container_id)
        push_ok = True

        if force_push and repos:
            for repo in repos:
                path = repo["path"]
                code = _exec(container, "git push --all origin", cwd=path, check=False)
                if code != 0:
                    logger.warning("强制 push 失败 container=%s path=%s", container_id, path)
                    push_ok = False

        if push_ok or not force_push:
            container.stop(timeout=10)
            container.remove(force=True)
            self._restart_counts.pop(container_id, None)
            logger.info("容器已销毁 container=%s", container_id)
        else:
            # push 失败:保留容器 30 分钟,由平台重试(分片异常场景)
            logger.warning("push 失败,保留容器 30 分钟 container=%s", container_id)
        return push_ok

    # -----------------------------------------------------------------
    # 事件监听与崩溃重启
    # -----------------------------------------------------------------
    def handle_event(self, event: str, container_id: str, exit_code: Optional[int] = None) -> Optional[str]:
        """
        处理 Docker 事件(start/die/oom):
        die → 自动 restart ≤3 次,超过返回 "restart_failed"(平台标 failed);
        其余返回 None 或事件语义字符串。
        """
        if event == "die":
            count = self._restart_counts.get(container_id, 0)
            if count < MAX_RESTARTS:
                self._restart_counts[container_id] = count + 1
                try:
                    self.client.containers.get(container_id).start()
                    logger.info("容器自动重启(%d/3)container=%s", count + 1, container_id)
                    return "restarted"
                except Exception:
                    logger.exception("自动重启失败 container=%s", container_id)
                    return "restart_failed"
            return "restart_failed"
        if event == "oom":
            return "restart_failed"
        return None

    def iter_events(self) -> Any:
        """阻塞迭代 Docker events(只关注容器 start/die/oom)"""
        for event in self.client.events(decode=True):
            if event.get("Type") == "container" and event.get("Action") in ("start", "die", "oom"):
                yield event


def _cpu_limit_to_nano_cpus(cpu_limit: str) -> int:
    """'2c' → 2 * 1e9 nano CPUs"""
    try:
        cores = float(cpu_limit.rstrip("c"))
        return int(cores * 1e9)
    except ValueError:
        return int(2e9)


def _exec(container: Any, cmd: str, cwd: str = "", check: bool = True) -> int:
    """容器内执行 shell 命令(docker exec 语义);返回退出码"""
    full = f"bash -lc 'cd {cwd} 2>/dev/null; {cmd}'" if cwd else f"bash -lc '{cmd}'"
    exit_code, output = container.exec_run(full)
    if check and exit_code != 0:
        raise RuntimeError(f"容器内命令失败({exit_code}): {cmd}\n{output.decode(errors='ignore')[:500]}")
    if check:
        logger.debug("容器内命令完成: %s", cmd)
    return exit_code if not check else 0

"""Runner 文件 watcher - R11(容器内 inotifywait 流;best-effort)

容器 /workspace 未挂载宿主机(纯计算资源),watcher 通过长驻
`inotifywait -m -r` exec 流读取事件;镜像需含 inotify-tools
(docker/devbox/Dockerfile 预装)。不可用时静默降级(前端有手动刷新)。
"""

import logging
import threading
from typing import Any, Callable

logger = logging.getLogger(__name__)

_INOTIFY_CMD = (
    "command -v inotifywait >/dev/null && "
    "inotifywait -m -r -q -e modify,create,delete,moved_to,close_write "
    "--format '%e %w%f' /workspace 2>/dev/null || "
    "echo 'INOTIFY_UNAVAILABLE'"
)


class FileWatcher:
    """每容器一个 watcher 线程;事件回调 on_event(task_id, kind, path)"""

    def __init__(self) -> None:
        self._threads: dict[str, threading.Thread] = {}
        self._stops: dict[str, threading.Event] = {}

    def start(self, container_id: str, task_id: str, manager: Any,
              on_event: Callable[[str, str, str], None]) -> bool:
        """启动 watcher;已在跑返回 False"""
        if container_id in self._threads and self._threads[container_id].is_alive():
            return False
        stop = threading.Event()
        self._stops[container_id] = stop
        thread = threading.Thread(
            target=self._loop, args=(container_id, task_id, manager, on_event, stop),
            daemon=True,
        )
        self._threads[container_id] = thread
        thread.start()
        return True

    def stop(self, container_id: str) -> None:
        stop = self._stops.get(container_id)
        if stop is not None:
            stop.set()
        self._threads.pop(container_id, None)

    def _loop(self, container_id: str, task_id: str, manager: Any,
              on_event: Callable, stop: threading.Event) -> None:
        try:
            container = manager.client.containers.get(container_id)
            cmd = ["bash", "-lc", _INOTIFY_CMD]
            code, stream = container.exec_run(cmd, stream=True, demux=False)
            unavailable_announced = False
            for chunk in stream:
                if stop.is_set():
                    break
                for raw in chunk.decode(errors="ignore").splitlines():
                    line = raw.strip()
                    if not line:
                        continue
                    if line == "INOTIFY_UNAVAILABLE":
                        if not unavailable_announced:
                            logger.warning("容器无 inotifywait,watcher 降级 container=%s", container_id)
                            unavailable_announced = True
                        return
                    parts = line.split(None, 1)
                    if len(parts) != 2:
                        continue
                    events, path = parts
                    if "DELETE" in events:
                        on_event(task_id, "file_deleted", path)
                    else:
                        on_event(task_id, "file_changed", path)
        except Exception:
            if not stop.is_set():
                logger.exception("文件 watcher 异常 container=%s", container_id)
        finally:
            logger.info("文件 watcher 退出 container=%s", container_id)

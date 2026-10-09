"""
R8.F7(BUG-081):sync 上报带宿主机端口映射
====================================================
现场:WS 断连丢 container_started 回报后,平台靠 sync 收养占位行——
收养需要端口回填预览映射,故 local_container_states 从 running_probes 带上端口。
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import main as runner_main


class _FakeContainer:
    def __init__(self, short_id, labels):
        self.short_id = short_id
        self.status = "running"
        self.labels = labels


class _FakeContainers:
    """docker client.containers 替身;containers 列表由测试注入"""

    items: list = []

    @classmethod
    def list(cls, filters=None):
        return cls.items


class _FakeClient:
    containers = _FakeContainers()


class _FakeManager:
    client = _FakeClient()


def _install(monkeypatch, items: list) -> None:
    _FakeContainers.items = items
    monkeypatch.setattr(runner_main, "manager", _FakeManager())


def test_local_container_states_includes_ports(monkeypatch):
    short_id = "abc123def456"
    runner_main.running_probes[short_id] = {"ports": {5173: 23413, 8000: 20701}}
    try:
        _install(monkeypatch, [_FakeContainer(short_id, {
            "qicheng.managed": "true", "qicheng.task_id": "task-t1",
        })])
        states = runner_main.local_container_states()
    finally:
        runner_main.running_probes.pop(short_id, None)

    assert len(states) == 1
    st = states[0]
    assert st["task_id"] == "task-t1"
    # R8.F7:端口随上报(键转字符串,与 handle_container_started 的 ports.get("5173") 口径一致)
    assert st["ports"] == {"5173": 23413, "8000": 20701}


def test_local_container_states_ports_default_empty(monkeypatch):
    """probes 未登记的容器(如平台重启后 runner 未重跑 start)端口缺省空 dict,不炸"""
    _install(monkeypatch, [_FakeContainer("def456abc789", {"qicheng.managed": "true"})])
    states = runner_main.local_container_states()
    assert states[0]["ports"] == {}
    assert states[0]["task_id"] == ""

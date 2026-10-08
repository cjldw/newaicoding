"""
BUG-078 Red 测试:docker client 必须显式长读超时(>= runner 侧流式看门狗)
====================================================================
根因(2026-10-08 复验 BUG-077 时实证):
  ContainerManager._default_client_factory 用 docker.from_env() 裸构造,
  APIClient timeout=60s(docker-py 默认)被 exec 流 socket 继承
  (_get_raw_response_socket 不重设超时)。claude 生成期静默段 >60s →
  socket.timeout("timed out",py3.10 str 即此)从执行线程抛出,
  exec_tool 通用 except 原样回报 error="timed out"。
  后果:① R8.F6 的 120s 看门狗(stream_timeout + pkill)永远轮不到执行;
       ② 容器内 claude 成为孤儿继续烧 token(实证:失败的流式请求,
          容器内会话转录仍在持续增长)。
修复:from_env(timeout=DOCKER_API_TIMEOUT),取值须 > STREAM_TIMEOUT(120s)
  与平台非流式超时(600s),看门狗语义才成立。
"""
import sys
import types
import unittest.mock as mock

import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import container_manager as cm


class TestDockerClientTimeout:
    def test_default_factory_passes_long_timeout(self):
        """默认工厂必须给 from_env 显式传 timeout,且 > 120s 流式看门狗"""
        # 打桩 docker 模块(宿主机可能未装 SDK;工厂本就惰性导入)
        fake_docker = types.ModuleType("docker")
        captured = {}

        def fake_from_env(**kwargs):
            captured.update(kwargs)
            return object()

        fake_docker.from_env = fake_from_env
        with mock.patch.dict(sys.modules, {"docker": fake_docker}):
            cm.ContainerManager._default_client_factory()

        assert "timeout" in captured, (
            "BUG-078:from_env() 未显式传 timeout → 读超时继承 60s 默认,"
            "LLM 静默段 >60s 即 socket.timeout('timed out')炸掉执行线程"
        )
        assert captured["timeout"] > 120, (
            "BUG-078:timeout 必须大于 runner 流式看门狗 STREAM_TIMEOUT(120s),"
            "否则看门狗(stream_timeout+pkill)永远轮不到执行"
        )
        assert captured["timeout"] > 600, (
            "BUG-078:非流式 claude -p 全程无输出(json 模式),读超时还须盖过"
            "平台侧 600s 执行超时,避免中途 socket 断流"
        )

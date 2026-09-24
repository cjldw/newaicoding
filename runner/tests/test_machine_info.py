"""R16.F4 / BUG-045:collect_machine_info 字段扩充与跨平台容错(本机实跑断言)。

- 根因回归:原实现 os.sysconf(SC_PAGE_SIZE/SC_PHYS_PAGES) 仅 Unix 存在,
  Windows 必 AttributeError → mem_total_gb 恒 0;修复后本机(Windows)须实取 >0
- 扩充字段:os_version / hostname / ip / disk_total_gb / disk_free_gb / cpu_model
- 容错约定:任何字段失败整键缺席,绝不上报 None 值,也不抛错阻塞注册
"""
import re
import sys

import main


def test_core_fields_unchanged():
    """既有键语义不变(后端透传/前端既有消费兼容);取不到的值保持既有占位口径"""
    info = main.collect_machine_info()
    assert info["os"] in ("windows", "linux", "darwin")
    assert info["arch"]
    assert info["cpu_count"] >= 1
    assert "docker_version" in info  # 取不到时为空串,键仍在
    assert "self_container_id" in info  # 裸跑为空串,键仍在


def test_mem_total_fixed():
    """BUG-045 根因回归:双平台内存总量都必须实取(不得再回退 0)"""
    info = main.collect_machine_info()
    assert info["mem_total_gb"] > 0


def test_new_fields_present():
    """扩充字段:本机环境应可实取;ip 允许取不到(离线/受限网络),取到则须为 IPv4 形态"""
    info = main.collect_machine_info()
    assert info.get("os_version")  # platform.platform() 非空
    assert info.get("hostname")  # socket.gethostname() 非空
    assert info["disk_total_gb"] > 0
    assert info["disk_free_gb"] >= 0
    ip = info.get("ip")
    if ip is not None:
        assert re.match(r"^\d{1,3}(\.\d{1,3}){3}$", ip)


def test_no_none_values_and_no_raise():
    """容错约定:失败字段整键缺席(不允许 None 值混进上报载荷)"""
    info = main.collect_machine_info()
    assert all(v is not None for v in info.values())

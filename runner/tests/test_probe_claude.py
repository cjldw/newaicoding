"""
R5(probe_claude)— Runner 侧指令单测 — QA TDD Red phase
=========================================================
依据 docs/20260926_skills市场安装/DEVPLAN/R5.md:
- Runner 新指令 probe_claude(照 claude_inject 先例 runner/main.py:429):
  container_manager 新方法在单次调用内完成
  start_container(repos=[], task_id 哨兵)→ exec_capture 探测 → stop_container(用后即毁)
  返回 {skills:[name...], mcps:[{name,transport...}]}
- main.handle_message 接线:单条指令 → 单条 result 回报(ok=True + data)

不依赖真实 Docker/平台:handle_message 用 FakeWS 直驱(test_runner_shutdown.py 先例),
container_manager 用 fake docker client(test_container_manager.py 先例)。
真机全链路(临时容器起→探→毁 + 镜像实际资产核对)依赖在线 Runner 与 devbox 镜像,
不在本轮(Runner 依赖,已注明)。

实现纬度说明(收口审查后已定口径):
- 单侧探测命令失败 = PRD R1「部分结果+警告」:该侧按空并在 failed_sides/warnings
  标记(平台侧据此不清该侧旧库),不上抛;exec 通道抛异常(硬失败)才向上传播
  且容器仍被销毁(销毁兜底)。命令不掩盖 exit code(无 `|| true`)。

R4 扩展(docs/20260927_devbox默认skills与mcp/DEVPLAN/R4.md,QA TDD Red phase):
- 路径校准:探测三段(skills find / .claude.json 读取 / plugins/cache 遍历)路径
  基准 /root → /home/node,探测命令零 /root。存量用例(此前钉 /root 旧契约)已同步
  改钉 /home/node,避免 Green 阶段新旧断言双红打架(R3 同款处理)
- 响应契约新增 plugin_skills/plugin_commands 独立字段(2026-09-27 契约微调,覆盖分片
  「skills=平台∪plugin」表述:skills 保持平台 skills 目录名存量语义,plugin 条目走独立
  字段,平台侧落库按字段来源打 detail.source 标记);plugin 探测按实测钉死布局
  cache/<marketplace>/<plugin>/<hash>/skills/<分类>/<skill>/SKILL.md 遍历(条目名取
  SKILL.md 父目录名,分类层不混入;deprecated/ 无 SKILL.md 由 find -name 天然不采);
  commands 同根 -path "*/commands/*.md";plugins 目录缺失 → 空列表、不报错、不进
  failed_sides;平台与 plugin 同名条目两字段各保一条,落库并列两行(backend 侧钉)
"""
import asyncio
import json

import pytest

import main as runner_main
from container_manager import ContainerManager


# ---------------------------------------------------------------------------
# fakes
# ---------------------------------------------------------------------------
class FakeWS:
    def __init__(self):
        self.sent = []

    async def send(self, data):
        self.sent.append(json.loads(data))


class FakeProbeManager:
    """接线测试用:记录 probe_claude 调用(含 kwargs)与预置结果/异常"""

    def __init__(self, result=None, exc=None):
        self.calls = 0
        self.last_kwargs: dict | None = None
        self.result = result or {
            "skills": ["skill-a"],
            "mcps": [{"name": "fetch", "transport": "stdio"}],
        }
        self.exc = exc

    def probe_claude(self, *args, **kwargs):
        self.calls += 1
        self.last_kwargs = kwargs
        if self.exc is not None:
            raise self.exc
        return self.result


class FakeExecResult:
    def __init__(self, code=0, output=b""):
        self.exit_code = code
        self.output = output

    def __iter__(self):
        # 兼容 docker SDK namedtuple 用法:exit_code, output = exec_run(...)
        return iter((self.exit_code, self.output))


class ProbeFakeContainer:
    """fake 容器:exec_run 按 cmd 子串路由预置输出;记录 stop/remove"""

    def __init__(self, routes=None, exec_exc=None):
        self.short_id = "probe123abc"
        self.exec_cmds: list[str] = []
        self.stopped = False
        self.removed = False
        self._routes = routes or []  # [(匹配子串列表, code, output_bytes)]
        self._exec_exc = exec_exc

    def exec_run(self, cmd_args):
        cmd = cmd_args[-1] if isinstance(cmd_args, (list, tuple)) else str(cmd_args)
        self.exec_cmds.append(cmd)
        if self._exec_exc is not None:
            raise self._exec_exc
        for subs, code, out in self._routes:
            if all(s in cmd for s in subs):
                return FakeExecResult(code, out)
        return FakeExecResult(0, b"")

    def stop(self, timeout=10):
        self.stopped = True

    def remove(self, force=False):
        self.removed = True


class ProbeFakeContainersAPI:
    def __init__(self, container: ProbeFakeContainer, run_exc=None):
        self.container = container
        self.run_kwargs = None
        self._run_exc = run_exc

    def run(self, **kwargs):
        self.run_kwargs = kwargs
        if self._run_exc is not None:
            raise self._run_exc
        return self.container

    def get(self, container_id):
        return self.container


class ProbeFakeDockerClient:
    """标准形态 fake client:containers API 挂 .containers(与真实 docker SDK 同形)"""

    def __init__(self, api: ProbeFakeContainersAPI):
        self.containers = api


def _make_manager(container=None, run_exc=None) -> tuple[ContainerManager, ProbeFakeContainersAPI]:
    container = container or ProbeFakeContainer()
    api = ProbeFakeContainersAPI(container, run_exc=run_exc)
    client = ProbeFakeDockerClient(api)
    return ContainerManager(client_factory=lambda: client), api


def _call_probe(manager: ContainerManager):
    """probe_claude 调用(R1:不传 image 直调,钉生产默认镜像应为 v2;
    方法缺失显式 fail,防 AttributeError 被 pytest.raises(Exception) 误吞成假通过)"""
    if not hasattr(manager, "probe_claude"):
        pytest.fail("container_manager.probe_claude 方法未创建(R5 契约)")
    return manager.probe_claude()


async def _dispatch_probe(ws: FakeWS, req_id: str):
    """下发 probe 指令(type 直发)"""
    await runner_main.handle_message(ws, {"type": "probe_claude", "req_id": req_id})


# ---------------------------------------------------------------------------
# 1. main.handle_message 接线:单条指令 → 单条 result(ok=True + data)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_handle_message_probe_claude_single_result():
    """probe 指令 → manager.probe_claude 恰一次 → 回一条 result(ok=True, data 原样)"""
    ws = FakeWS()
    fake = FakeProbeManager()
    orig = runner_main.manager
    runner_main.manager = fake
    try:
        await _dispatch_probe(ws, "r-p1")
    finally:
        runner_main.manager = orig

    assert fake.calls == 1, f"probe_claude 应被调用一次,实际 {fake.calls}"
    # R1:接线默认镜像应为 v2(指令不带 image 时由 main 提供默认;
    # 钉住生产常量 runner/main.py 的 v2 默认)
    assert (fake.last_kwargs or {}).get("image") == "platform/devbox:v2", (
        f"probe_claude 应收到默认镜像 v2,实际 kwargs: {fake.last_kwargs}"
    )
    results = [p for p in ws.sent if p.get("type") == "result" and p.get("req_id") == "r-p1"]
    assert len(results) == 1, f"应回一条 result,实际: {ws.sent}"
    assert results[0]["ok"] is True
    assert results[0]["data"] == {"skills": ["skill-a"], "mcps": [{"name": "fetch", "transport": "stdio"}]}


@pytest.mark.asyncio
async def test_handle_message_probe_failure_replies_ok_false():
    """probe 抛异常(容器启动失败等)→ 回一条 result(ok=False, error 非空);平台侧据此 502"""
    ws = FakeWS()
    fake = FakeProbeManager(exc=RuntimeError("container start failed"))
    orig = runner_main.manager
    runner_main.manager = fake
    try:
        await _dispatch_probe(ws, "r-p2")
    finally:
        runner_main.manager = orig

    assert fake.calls == 1
    results = [p for p in ws.sent if p.get("type") == "result" and p.get("req_id") == "r-p2"]
    assert len(results) == 1, f"应回一条 result,实际: {ws.sent}"
    assert results[0]["ok"] is False
    assert results[0]["error"]


# ---------------------------------------------------------------------------
# 2. container_manager.probe_claude:start(repos=[])→exec 探测→stop 单次调用内完成
# ---------------------------------------------------------------------------
def test_probe_happy_path_start_exec_stop():
    """时序:空仓库临时容器(repos=[],task_id 哨兵,无 qicheng.managed)→ 探测
    (skills 只取一级目录 + 读 /home/node/.claude.json;R4 路径校准)→ 容器销毁
    (用后即毁);返回契约含 skills/plugin_skills/plugin_commands(R4 新增)/
    mcps/failed_sides/warnings"""
    find_out = b"skill-a\nskill-b\n"
    claude_json = json.dumps({
        "mcpServers": {"fetch": {"type": "stdio", "command": "uvx mcp-server-fetch"}},
    }).encode()
    container = ProbeFakeContainer(routes=[
        (["find /home/node/.claude/skills"], 0, find_out),
        (["cat /home/node/.claude.json"], 0, claude_json),
    ])
    manager, api = _make_manager(container)

    result = _call_probe(manager)

    # start 契约:临时容器,不挂仓库,task_id 为哨兵值;一次性容器不打 qicheng.managed
    # (die 自动重启/对账清扫均按该标签过滤,探测容器不得参与)
    assert api.run_kwargs is not None, "未启动容器"
    labels = (api.run_kwargs.get("labels") or {})
    task_id = labels.get("qicheng.task_id", "")
    assert task_id, "task_id 哨兵缺失(labels)"
    assert labels.get("qicheng.managed") != "true", "一次性探测容器不得带 qicheng.managed 标签"
    # R1:probe 默认镜像应为 v2(_call_probe 不传 image 直调,钉生产默认;
    # 钉住生产常量 runner/container_manager.py 的 v2 默认)
    assert api.run_kwargs.get("image") == "platform/devbox:v2", (
        f"probe 默认镜像应为 v2,实际: {api.run_kwargs.get('image')}"
    )
    # 探测命令:skills 只取一级目录(find -type d,R4 路径基准 /home/node)+
    # 读 /home/node/.claude.json;命令不得掩盖 exit code(无 `|| true`——
    # 单侧失败须可检测,PRD R1 部分结果语义)
    skills_cmds = [c for c in container.exec_cmds if "/home/node/.claude/skills" in c]
    assert skills_cmds and all("-type d" in c for c in skills_cmds), container.exec_cmds
    assert all("|| true" not in c for c in container.exec_cmds), container.exec_cmds
    assert any("/home/node/.claude.json" in c for c in container.exec_cmds), container.exec_cmds
    # 空仓库:不做 git clone
    assert not any("git clone" in c for c in container.exec_cmds), container.exec_cmds
    # 用后即毁:容器已 stop + remove
    assert container.stopped and container.removed, "临时容器未销毁(用后即毁)"
    # 返回契约(R4:plugin_skills/plugin_commands 新增键一并纳入)
    assert {"skills", "plugin_skills", "plugin_commands", "mcps", "failed_sides", "warnings"} <= set(result.keys()), result
    assert result["skills"] == ["skill-a", "skill-b"]
    assert result["failed_sides"] == [] and result["warnings"] == []
    assert len(result["mcps"]) == 1
    m = result["mcps"][0]
    assert m.get("name") == "fetch"
    # 传输字段:归一化 transport 或探测原文 type 均认(PRD:名称+传输类型)
    assert m.get("transport", m.get("type")) == "stdio"


def test_probe_side_failure_reported_not_masked():
    """单侧探测命令失败(skills find 非零)→ 不上抛,该侧按空并在
    failed_sides/warnings 标记(PRD R1 部分结果语义;平台侧据此不清该侧旧库);
    另一侧(mcps)正常探测;容器仍销毁"""
    claude_json = json.dumps({
        "mcpServers": {"fetch": {"type": "stdio", "command": "uvx mcp-server-fetch"}},
    }).encode()
    container = ProbeFakeContainer(routes=[
        (["find /home/node/.claude/skills"], 1, b""),  # skills 目录缺失/命令失败
        (["cat /home/node/.claude.json"], 0, claude_json),
    ])
    manager, _ = _make_manager(container)

    result = _call_probe(manager)

    assert result["skills"] == []
    assert result["failed_sides"] == ["skills"]
    assert result["warnings"] and "skills" in result["warnings"][0]
    assert [m["name"] for m in result["mcps"]] == ["fetch"]
    assert container.stopped and container.removed, "失败路径临时容器未销毁"


def test_probe_mcps_side_failure_reported():
    """claude.json 不可读(cat 非零)→ mcps 侧按空 + failed_sides 标记,不上抛"""
    container = ProbeFakeContainer(routes=[
        (["find /home/node/.claude/skills"], 0, b"skill-a\n"),
        (["cat /home/node/.claude.json"], 1, b""),
    ])
    manager, _ = _make_manager(container)

    result = _call_probe(manager)

    assert result["skills"] == ["skill-a"]
    assert result["mcps"] == []
    assert result["failed_sides"] == ["mcps"]
    assert result["warnings"]


def test_probe_mcp_servers_non_dict_treated_as_empty():
    """mcpServers 真值非 dict(list)→ 按空处理不炸(契约「非法按空」),不标记侧失败"""
    claude_json = json.dumps({"mcpServers": ["not-a-dict"]}).encode()
    container = ProbeFakeContainer(routes=[
        (["find /home/node/.claude/skills"], 0, b"skill-a\n"),
        (["cat /home/node/.claude.json"], 0, claude_json),
    ])
    manager, _ = _make_manager(container)

    result = _call_probe(manager)

    assert result["skills"] == ["skill-a"]
    assert result["mcps"] == []
    assert result["failed_sides"] == []


def test_probe_start_failure_propagates():
    """容器启动失败 → 异常向上传播(接线层转 ok=False → 平台 502 可重试)"""
    manager, api = _make_manager(run_exc=RuntimeError("docker run failed"))
    with pytest.raises(Exception):
        _call_probe(manager)


def test_probe_exec_exception_still_destroys_container():
    """exec 通道硬失败(异常)→ 异常向上传播,且容器仍被销毁(销毁兜底,不留临时容器)"""
    container = ProbeFakeContainer(exec_exc=RuntimeError("exec channel broken"))
    manager, api = _make_manager(container)

    with pytest.raises(Exception):
        _call_probe(manager)

    assert container.stopped and container.removed, "exec 失败后临时容器未销毁(销毁兜底)"


# ---------------------------------------------------------------------------
# 3. R4:probe 覆盖 plugin + 路径校准 /home_node(QA TDD Red phase)
# ---------------------------------------------------------------------------
# 实测钉死的 plugin 布局(R4.md「plugin 探测」行):
#   cache/<marketplace>/<plugin>/<hash>/skills/<分类>/<skill>/SKILL.md(rd-flow 37 个
#   skill 分类嵌套;deprecated/ 无 SKILL.md → find -name SKILL.md 天然不采)
# fake 按 find 命令子串路由输出(沿用本文件既有手法),输出行 = find 应吐的原始路径。
# 路由键约定(Green 实现按 R4 规格落命令即天然命中):
#   - plugin skills:命令含 /home/node/.claude/plugins/cache 且含 SKILL.md(-name 形态)
#   - plugin commands:命令含 /home/node/.claude/plugins/cache 且含 */commands/*.md
PLUGIN_SKILL_MD_OUT = (
    "/home/node/.claude/plugins/cache/marketplaces/rd-flow/a1b2c3d4e5f6/skills/develop/rd-arch/SKILL.md\n"
    "/home/node/.claude/plugins/cache/marketplaces/rd-flow/a1b2c3d4e5f6/skills/review/rd-review/SKILL.md\n"
    "/home/node/.claude/plugins/cache/other-mkt/other-plugin/ff8899aa/skills/tutorials/nested-tut/SKILL.md\n"
).encode()
PLUGIN_CMD_MD_OUT = (
    "/home/node/.claude/plugins/cache/marketplaces/rd-flow/a1b2c3d4e5f6/commands/flow-status.md\n"
    "/home/node/.claude/plugins/cache/marketplaces/rd-flow/a1b2c3d4e5f6/commands/flow-run.md\n"
).encode()


def _r4_routes(
    platform_skills: bytes = b"",
    plugin_skills: bytes = PLUGIN_SKILL_MD_OUT,
    plugin_cmds: bytes = PLUGIN_CMD_MD_OUT,
    claude_json: bytes | None = None,
    plugins_fail: bool = False,
    dual_path: bool = False,
) -> list:
    """R4 探测 fake 路由表。

    dual_path=True:平台段(skills find / .claude.json cat)同时接受 /home/node 与
    /root 两种命令形态——非路径专项用例借此隔离「路径未校准」与「plugin 段未实现」
    两种 Red 根因(路径本身由专项用例钉)。
    plugins_fail=True:任何 plugins/cache 遍历命令一律 exit 1(目录缺失/不可达)。
    """
    if claude_json is None:
        claude_json = json.dumps({"mcpServers": {}}).encode()
    bases = ["/home/node", "/root"] if dual_path else ["/home/node"]
    routes: list = []
    for base in bases:
        routes.append(([f"find {base}/.claude/skills"], 0, platform_skills))
    for base in bases:
        routes.append(([f"cat {base}/.claude.json"], 0, claude_json))
    if plugins_fail:
        routes.insert(0, (["/home/node/.claude/plugins/cache"], 1, b""))
    else:
        routes.append((["/home/node/.claude/plugins/cache", "SKILL.md"], 0, plugin_skills))
        routes.append((["/home/node/.claude/plugins/cache", "*/commands/*.md"], 0, plugin_cmds))
    return routes


def test_probe_paths_calibrated_to_home_node():
    """R4 判据1:探测三段命令路径基准全部 /home/node——skills find、
    .claude.json 读取、plugins/cache 遍历;探测命令零 /root;三段探测命令
    均存在(plugins 段不因缺省省略);数据从 /home/node 实际采到"""
    container = ProbeFakeContainer(routes=_r4_routes(
        platform_skills=b"platform-a\n",
        claude_json=json.dumps({"mcpServers": {"fetch": {"type": "stdio"}}}).encode(),
    ))
    manager, _ = _make_manager(container)

    result = _call_probe(manager)

    # 三段探测命令逐一钉住(缺任一段 = 探测面残缺)
    assert any("find /home/node/.claude/skills" in c and "-type d" in c for c in container.exec_cmds), (
        f"skills 探测应基于 /home/node(find -type d),实际命令: {container.exec_cmds}"
    )
    assert any("cat /home/node/.claude.json" in c for c in container.exec_cmds), (
        f".claude.json 应读 /home/node 基准,实际命令: {container.exec_cmds}"
    )
    assert any("/home/node/.claude/plugins/cache" in c for c in container.exec_cmds), (
        f"plugin 探测应遍历 /home/node/.claude/plugins/cache,实际命令: {container.exec_cmds}"
    )
    # 正向:.claude 相关命令全部基于 /home/node;负向:探测命令零 /root
    # (探测命令为纯 find/cat,无 base64 载荷,全量扫描无假阳性)
    path_cmds = [c for c in container.exec_cmds if ".claude" in c]
    assert path_cmds, f"应产生 .claude 探测命令,实际: {container.exec_cmds}"
    assert all("/home/node" in c for c in path_cmds), f".claude 命令应全部基于 /home/node: {path_cmds}"
    assert not any("/root" in c for c in container.exec_cmds), (
        f"探测命令不得出现 /root(R4 路径校准): {container.exec_cmds}"
    )
    # 数据也从 /home/node 采到(路径未校准前 skills/mcps 必为空)
    assert result["skills"] == ["platform-a"], f"skills 应自 /home/node 采到,实际: {result['skills']}"
    assert [m["name"] for m in result["mcps"]] == ["fetch"], (
        f"mcps 应自 /home/node/.claude.json 采到,实际: {result['mcps']}"
    )


def test_probe_response_contract_includes_plugin_fields():
    """R4 接口契约(2026-09-27 契约微调,同步改钉:原 commands 键 → plugin_commands,
    并新增 plugin_skills;QA 备注预案「runner 响应另行扩展 plugin_skills 字段」落地形态):
    响应含 skills/plugin_skills/plugin_commands/mcps/failed_sides/warnings 六键;
    skills 恰为平台 skills 目录名(存量语义,不合入 plugin 条目);
    plugin_skills 恰为 SKILL.md 父目录名列表;plugin_commands 恰为
    plugin commands 名列表(commands/*.md 文件名词干)"""
    container = ProbeFakeContainer(routes=_r4_routes(platform_skills=b"platform-a\n"))
    manager, _ = _make_manager(container)

    result = _call_probe(manager)

    assert {"skills", "plugin_skills", "plugin_commands", "mcps", "failed_sides", "warnings"} <= set(result.keys()), (
        f"响应契约缺键(R4 新增 plugin_skills/plugin_commands),实际键: {sorted(result.keys())}"
    )
    assert result["skills"] == ["platform-a"], (
        f"skills 应保持平台 skills 存量语义(不含 plugin 条目),实际: {result.get('skills')}"
    )
    assert sorted(result["plugin_skills"]) == ["nested-tut", "rd-arch", "rd-review"], (
        f"plugin_skills 应为 SKILL.md 父目录名列表,实际: {result.get('plugin_skills')}"
    )
    assert sorted(result["plugin_commands"]) == ["flow-run", "flow-status"], (
        f"plugin_commands 应为 plugin commands 名列表(文件名词干),实际: {result.get('plugin_commands')}"
    )
    assert result["failed_sides"] == [] and result["warnings"] == [], result


def test_probe_plugin_layout_traversal_names():
    """R4 判据2:plugin 布局遍历——SKILL.md 条目名取父目录名(分类层
    develop/review/tutorials 不得误作条目名);commands 同根 -path 采集;
    plugin 条目入 plugin_skills 独立字段(2026-09-27 契约微调:skills 保持平台
    存量语义,合并并列由落库两行承载,backend 侧钉);find 命令形态钉死
    (-name SKILL.md → deprecated/ 无 SKILL.md 天然不采)"""
    container = ProbeFakeContainer(routes=_r4_routes(platform_skills=b"platform-a\nplatform-b\n"))
    manager, _ = _make_manager(container)

    result = _call_probe(manager)

    # 命令形态:skills 用 -name SKILL.md(deprecated/ 无 SKILL.md 天然不采),
    # commands 用 -path "*/commands/*.md"
    skill_finds = [c for c in container.exec_cmds if "plugins/cache" in c and "SKILL.md" in c]
    assert skill_finds and all("-name" in c for c in skill_finds), (
        f"plugin skills 应以 find -name SKILL.md 遍历,实际命令: {container.exec_cmds}"
    )
    assert any("*/commands/*.md" in c for c in container.exec_cmds), (
        f"plugin commands 应以 -path '*/commands/*.md' 遍历,实际命令: {container.exec_cmds}"
    )
    # 条目名 = SKILL.md 父目录名:分类层不是条目(入 plugin_skills 独立字段)
    for expected in ("rd-arch", "rd-review", "nested-tut"):
        assert expected in result["plugin_skills"], (
            f"plugin skill {expected} 应按 SKILL.md 父目录名采入 plugin_skills,实际: {result['plugin_skills']}"
        )
    assert not {"develop", "review", "tutorials"} & set(result["plugin_skills"]), (
        f"分类目录名不得混入 plugin_skills 条目: {result['plugin_skills']}"
    )
    # skills 保持平台语义;plugin 条目在独立字段(平台 ∪ plugin 由落库并列承载)
    assert sorted(result["skills"]) == ["platform-a", "platform-b"], (
        f"skills 应恰为平台 skills 目录名,实际: {result['skills']}"
    )
    assert sorted(result["plugin_skills"]) == [
        "nested-tut", "rd-arch", "rd-review",
    ], f"plugin_skills 应恰为 plugin 条目,实际: {result['plugin_skills']}"


def test_probe_plugins_dir_missing_degrades_to_empty():
    """R4 判据7:plugins 目录缺失(find 非零)→ plugin skills/commands 按空,
    不报错(不上抛)、不进 failed_sides;平台 skills 与 mcps 两段照常返回;
    临时容器照常用后即毁(dual_path 隔离路径根因,只验 plugin 降级)"""
    container = ProbeFakeContainer(routes=_r4_routes(
        platform_skills=b"platform-a\n",
        plugins_fail=True,
        claude_json=json.dumps({"mcpServers": {"fetch": {"type": "stdio"}}}).encode(),
        dual_path=True,
    ))
    manager, _ = _make_manager(container)

    result = _call_probe(manager)  # 目录缺失不上抛

    assert result["skills"] == ["platform-a"], f"平台 skills 段应照常返回: {result['skills']}"
    assert [m["name"] for m in result["mcps"]] == ["fetch"], f"mcps 段应照常返回: {result['mcps']}"
    assert result.get("plugin_skills") == [] and result.get("plugin_commands") == [], (
        f"plugins 目录缺失 → plugin_skills/plugin_commands 按空列表,"
        f"实际: {result.get('plugin_skills')!r} / {result.get('plugin_commands')!r}"
    )
    assert result["failed_sides"] == [], (
        f"plugins 目录缺失不得计入 failed_sides,实际: {result['failed_sides']}"
    )
    assert container.stopped and container.removed, "降级路径临时容器未销毁(用后即毁)"


def test_probe_same_name_platform_and_plugin_coexist():
    """R4 判据6(runner 侧,2026-09-27 契约微调同步改钉):平台 skill 目录与 plugin
    SKILL.md 条目同名 → skills(平台)与 plugin_skills(独立字段)各保一条同名同值
    不丢失不混字段;落库两行并列(先清后插不去重 + detail.source 来源标记)由平台侧
    保证,见 backend/tests 对应用例;dual_path 隔离路径根因"""
    container = ProbeFakeContainer(routes=_r4_routes(
        platform_skills=b"dup-skill\nplatform-a\n",
        plugin_skills=(
            b"/home/node/.claude/plugins/cache/marketplaces/rd-flow/a1b2c3d4e5f6"
            b"/skills/dev/dup-skill/SKILL.md\n"
        ),
        plugin_cmds=b"",
        dual_path=True,
    ))
    manager, _ = _make_manager(container)

    result = _call_probe(manager)

    assert result["skills"].count("dup-skill") == 1, (
        f"平台侧同名条目应保留一条(skills 平台存量语义),实际: {result['skills']}"
    )
    assert result["plugin_skills"].count("dup-skill") == 1, (
        f"plugin 侧同名条目应保留一条(plugin_skills 独立字段),实际: {result['plugin_skills']}"
    )
    assert result["skills"] == ["dup-skill", "platform-a"], (
        f"除平台条目外不应多出/丢失条目,实际: {result['skills']}"
    )
    assert result["plugin_skills"] == ["dup-skill"], (
        f"除 plugin 条目外不应多出/丢失条目,实际: {result['plugin_skills']}"
    )

"""
R3(claude_inject 合并语义改造 + 路径基准 /home/node)— QA TDD Red phase
==========================================================================
依据 docs/20260927_devbox默认skills与mcp/DEVPLAN/R3.md「完成判据」1–6:

- 判据 1 合并语义:预置 ∪ 项目级,同名项目级覆盖,文件其余键原样保留
- 判据 2 项目级为空不触碰配置文件(现状 :627 分支保留,回归护栏)
- 判据 3 文件不存在 / 非法 JSON / mcpServers 非 dict → 按 {} 兜底合并写入
- 判据 4 注入链路径基准 /home/node(claude_inject 链路;probe 相关 /root 归 R4,本文件不触)
- 判据 5 skills 注入语义不变:写 /home/node/.claude/skills/<safe>.md、非法名跳过、同名后写覆盖
- 判据 6 响应 mcp 语义 = 合并后文件内 mcpServers 总条数(非项目级条数)

fake 手法沿用本目录先例(test_container_manager.py / test_probe_claude.py /
test_r32_claude_stream.py):fake docker client,exec_run 按 cmd 子串路由。
本文件的替身是「内存文件系统」形态的 v2 devbox 容器:镜像原生预置配置位于
/home/node/.claude.json(R2),/root/.claude.json 不存在——这正是现状代码
(整段替换 + /root 路径)必失败的 Red 前提。

路径断言域:路径类断言只认 fake 的结构化路径集合(written_paths /
catted_paths 提取的目标路径),不扫原始命令文本——命令内嵌 skill 内容的
base64 载荷,标准字母表含 "/",载荷碰巧编出 "/root" 这类无 "." 子串时,
原始文本扫描会对「零 /root」断言造成与注入路径无关的假失败(约 0.06%/10KB);
含 "." 的子串(.claude.json 等)不可能出现在 base64 载荷中,不受此限。

现状(Red 基线):runner/container_manager.py:597-636
  - :622 skills 写 /root/.claude/skills/、:629 读 /root/.claude.json、
    :631 mcpServers 整段替换、:632 写回 /root/.claude.json
"""
import base64
import json
import re

from container_manager import ContainerManager

HOME_CONFIG = "/home/node/.claude.json"
HOME_SKILLS = "/home/node/.claude/skills"

# R2 预置(形态参考 devbox 镜像 mcp 配置;判据 6 用 6 条)
PRESET_2 = {
    "mysql_dev": {"type": "stdio", "command": "uvx", "args": ["mcp-server-mysql", "--preset"]},
    "github": {"type": "stdio", "command": "npx", "args": ["-y", "@modelcontextprotocol/server-github"]},
}


# ---------------------------------------------------------------------------
# fakes:内存文件系统容器(exec_run 按 cat / base64 落盘 路由)
# ---------------------------------------------------------------------------
class FakeExecResult:
    def __init__(self, code=0, output=b""):
        self.exit_code = code
        self.output = output

    def __iter__(self):
        # 兼容 docker SDK namedtuple 用法:exit_code, output = exec_run(...)
        return iter((self.exit_code, self.output))


class FakeNodeContainer:
    """v2 devbox 容器替身:dict 内存 FS;只识别注入链两条命令形态——
    cat <path> 2>/dev/null(缺失→exit 1)与 write_file 的 mkdir+base64 落盘。
    记录全部 exec 命令供路径断言(判据 4)。"""

    # 路径断言域说明:路径类断言只认本类提供的结构化路径集合
    # (written_paths / catted_paths 提取的目标路径),不扫原始命令文本——
    # 命令内嵌 skill 内容的 base64 载荷,标准字母表含 "/",载荷碰巧编出
    # "/root" 这类无 "." 子串时,原始文本扫描会对「零 /root」断言造成
    # 与注入路径无关的假失败;含 "." 的子串(.claude.json 等)不可能出现
    # 在 base64 载荷中,不受此限。

    def __init__(self, files=None):
        # 统一存 bytes(str 便捷入参在此编码),保证逐字节断言类型一致
        self.fs: dict[str, bytes] = {
            k: (v.encode() if isinstance(v, str) else v) for k, v in dict(files or {}).items()
        }
        self.exec_cmds: list[str] = []

    def exec_run(self, cmd_args):
        cmd = cmd_args[-1] if isinstance(cmd_args, (list, tuple)) else str(cmd_args)
        self.exec_cmds.append(cmd)
        if cmd.startswith("cat "):
            path = cmd.split()[1]
            if path in self.fs:
                return FakeExecResult(0, self.fs[path])
            return FakeExecResult(1, b"")  # cat 2>/dev/null 对缺失文件 exit 1
        m = re.search(r"echo (\S+) \| base64 -d > (\S+)", cmd)
        if m:
            self.fs[m.group(2)] = base64.b64decode(m.group(1))
            return FakeExecResult(0, b"")
        return FakeExecResult(0, b"")

    # ---- 断言辅助 ----
    def written_paths(self) -> list[str]:
        """base64 落盘命令的目标路径列表(按执行序)"""
        out = []
        for c in self.exec_cmds:
            m = re.search(r"base64 -d > (\S+)", c)
            if m:
                out.append(m.group(1))
        return out

    def catted_paths(self) -> list[str]:
        """cat 读取的目标路径列表(按执行序)"""
        return [c.split()[1] for c in self.exec_cmds if c.startswith("cat ")]

    def file_bytes(self, path: str) -> bytes:
        return self.fs[path]


class FakeContainersAPI:
    def __init__(self, container: FakeNodeContainer):
        self.container = container

    def get(self, container_id):
        return self.container


class FakeDockerClient:
    def __init__(self, container: FakeNodeContainer):
        self.containers = FakeContainersAPI(container)


def _manager(files=None) -> tuple[ContainerManager, FakeNodeContainer]:
    container = FakeNodeContainer(files)
    return ContainerManager(client_factory=lambda: FakeDockerClient(container)), container


# ---------------------------------------------------------------------------
# 判据 1:合并语义(预置 ∪ 项目级,同名项目级覆盖,其余键保留)
# ---------------------------------------------------------------------------
def test_merge_preset_and_project_servers():
    """预置 mysql_dev+github,项目级注入同名 mysql_dev(改写)+figma
    → 文件含 3 条且 mysql_dev 为项目级值;文件其余键(theme)原样保留"""
    mgr, c = _manager({HOME_CONFIG: json.dumps({"theme": "dark", "mcpServers": PRESET_2})})
    project = {
        "mysql_dev": {"type": "stdio", "command": "uvx", "args": ["mcp-server-mysql", "--project"]},
        "figma": {"type": "http", "url": "http://figma-mcp"},
    }

    out = mgr.claude_inject("c1", mcp_config={"mcpServers": project})

    written = json.loads(c.file_bytes(HOME_CONFIG))
    assert set(written["mcpServers"].keys()) == {"mysql_dev", "github", "figma"}, (
        f"合并后应为预置∪项目级 3 条,实际: {written['mcpServers'].keys()}"
    )
    assert written["mcpServers"]["mysql_dev"] == project["mysql_dev"], "同名 server 应以项目级配置生效"
    assert written["mcpServers"]["github"] == PRESET_2["github"], "预置项不得丢失"
    assert written["theme"] == "dark", "文件其余键应原样保留(整文件读-合-写)"
    assert out["mcp"] == 3, f"响应 mcp 应为合并后总条数 3,实际 {out}"


# ---------------------------------------------------------------------------
# 判据 2:项目级为空不触碰配置文件(现状 :627 分支保留,回归护栏)
# ---------------------------------------------------------------------------
def test_empty_project_mcp_leaves_config_untouched():
    """mcp_config.mcpServers 为空 dict(仅带 skills)→ 配置文件逐字节一致,
    且整条注入链零次 .claude.json 读写"""
    original = json.dumps({"theme": "dark", "mcpServers": PRESET_2})
    mgr, c = _manager({HOME_CONFIG: original})

    out = mgr.claude_inject("c1", skills=[{"name": "s1", "content": "S"}], mcp_config={"mcpServers": {}})

    assert c.file_bytes(HOME_CONFIG) == original.encode(), "项目级为空不得改写配置文件(逐字节)"
    assert not c.written_paths() or all(".claude.json" not in p for p in c.written_paths()), (
        f"不得有 .claude.json 写命令,实际写入: {c.written_paths()}"
    )
    assert not any(".claude.json" in cmd for cmd in c.exec_cmds), (
        f"项目级为空不得读写 .claude.json,实际命令: {c.exec_cmds}"
    )
    assert out["mcp"] == 0


def test_missing_mcp_config_key_leaves_config_untouched():
    """mcp_config 缺省(None,上游仅注入 skills)→ 同样不触碰配置文件"""
    original = json.dumps({"theme": "dark", "mcpServers": PRESET_2})
    mgr, c = _manager({HOME_CONFIG: original})

    out = mgr.claude_inject("c1", skills=[{"name": "s1", "content": "S"}], mcp_config=None)

    assert c.file_bytes(HOME_CONFIG) == original.encode()
    assert not any(".claude.json" in cmd for cmd in c.exec_cmds)
    assert out["mcp"] == 0


# ---------------------------------------------------------------------------
# 判据 3:文件不存在 / 非法 JSON / mcpServers 非 dict → 按 {} 兜底合并写入
# ---------------------------------------------------------------------------
def test_missing_config_file_fallback_creates():
    """v1 存量容器并行期兼容:无 /home/node/.claude.json → 按空对象兜底新建,
    项目级条目全量写入;响应 mcp=项目级条数(=合并后总条数)"""
    mgr, c = _manager({})  # 空 FS:预置/存量均不存在
    project = {"gitlab": {"url": "http://mcp"}, "fetch": {"command": "uvx mcp-server-fetch"}}

    out = mgr.claude_inject("c1", mcp_config={"mcpServers": project})

    written = json.loads(c.file_bytes(HOME_CONFIG))
    assert written["mcpServers"] == project, "兜底新建应写入项目级全量条目"
    assert out["mcp"] == 2, f"响应 mcp 应为 2,实际 {out}"


def test_invalid_json_config_fallback():
    """容器内配置文件为非法 JSON → 按空对象兜底,合并结果(合法 JSON)写回"""
    mgr, c = _manager({HOME_CONFIG: b"{{{ not-json"})  # 非法 JSON(exit 0 可读)
    project = {"fetch": {"command": "uvx mcp-server-fetch"}}

    out = mgr.claude_inject("c1", mcp_config={"mcpServers": project})

    written = json.loads(c.file_bytes(HOME_CONFIG))  # 写回后必须为合法 JSON
    assert written["mcpServers"] == project
    assert out["mcp"] == 1


def test_mcp_servers_non_dict_treated_as_empty_then_merge():
    """存量文件 mcpServers 段为非 dict(list)→ 按 {} 处理再合并;
    文件其余键(keep)保留"""
    mgr, c = _manager({HOME_CONFIG: json.dumps({"mcpServers": ["bad"], "keep": 1})})
    project = {"a": {"url": "u"}}

    out = mgr.claude_inject("c1", mcp_config={"mcpServers": project})

    written = json.loads(c.file_bytes(HOME_CONFIG))
    assert written["mcpServers"] == project, "非 dict mcpServers 应按 {} 处理后合并"
    assert written["keep"] == 1
    assert out["mcp"] == 1


# ---------------------------------------------------------------------------
# 判据 4:注入链路径基准 /home/node(probe 相关 /root 归 R4,本文件不调用 probe)
# ---------------------------------------------------------------------------
def test_inject_chain_paths_under_home_node():
    """skills 写入 + 配置读写的全部路径均基于 /home/node,注入链零 /root。
    「零 /root」断言域 = 结构化路径集合(cat 读 + base64 落盘的目标路径),
    不扫原始命令文本:base64 载荷字母表含 "/",可能碰巧编出 "/root" 子串
    (见文件头「路径断言域」说明)"""
    mgr, c = _manager({HOME_CONFIG: json.dumps({"mcpServers": PRESET_2})})

    mgr.claude_inject(
        "c1",
        skills=[{"name": "x", "content": "X"}],
        mcp_config={"mcpServers": {"figma": {"url": "u"}}},
    )

    # 正向守护(不受 base64 载荷干扰:含 "." 的子串进不了载荷):
    # 任何提及 .claude 的命令必须基于 /home/node(覆盖 cat/base64 之外的命令形态)
    path_cmds = [cmd for cmd in c.exec_cmds if ".claude" in cmd]
    assert path_cmds, f"注入链应产生 .claude 相关命令,实际: {c.exec_cmds}"
    assert all("/home/node" in cmd for cmd in path_cmds), (
        f".claude 相关命令应全部基于 /home/node,实际: {path_cmds}"
    )
    # 负向守护(结构化路径集合,含非 .claude 命名形态的读写路径)
    touched = c.catted_paths() + c.written_paths()
    assert touched, f"注入链应产生路径读写,实际命令: {c.exec_cmds}"
    assert all(p.startswith("/home/node") for p in touched), (
        f"注入链读写路径应全部在 /home/node 下,实际: {touched}"
    )
    assert not any(p.startswith("/root") for p in touched), (
        f"注入链读写路径不得出现 /root,实际: {touched}"
    )
    # 守护强度钉死两类路径,防断言域收窄成空集形同虚设:
    # skills 写入路径 + .claude.json 读写路径
    skill_writes = [p for p in c.written_paths() if p.startswith(HOME_SKILLS + "/")]
    assert skill_writes == [f"{HOME_SKILLS}/x.md"], (
        f"skill 应写入 {HOME_SKILLS}/x.md,实际 skills 写入: {skill_writes}"
    )
    # 读取与写回都钉在 /home/node/.claude.json
    assert c.catted_paths() == [HOME_CONFIG], f"应读 {HOME_CONFIG},实际 cat: {c.catted_paths()}"
    config_writes = [p for p in c.written_paths() if p.endswith(".claude.json")]
    assert config_writes == [HOME_CONFIG], f"应写回 {HOME_CONFIG},实际写: {config_writes}"


# ---------------------------------------------------------------------------
# 判据 5:skills 注入语义不变(路径改为 /home/node,其余现状保留)
# ---------------------------------------------------------------------------
def test_skills_written_under_home_node_and_illegal_names_skipped():
    """合法名写 /home/node/.claude/skills/<safe>.md;
    非法名(空名/全特殊字符)与空 content 跳过且不报错"""
    mgr, c = _manager({})
    skills = [
        {"name": "x", "content": "# X"},
        {"name": "", "content": "skip"},          # 空名 → 跳过
        {"name": "###", "content": "skip"},       # 全特殊字符(过滤后为空)→ 跳过
        {"name": "empty", "content": ""},         # 空 content → 跳过
    ]

    out = mgr.claude_inject("c1", skills=skills)

    assert c.file_bytes(f"{HOME_SKILLS}/x.md") == b"# X"
    assert f"{HOME_SKILLS}/x.md" in c.written_paths(), (
        f"skill 应写入 {HOME_SKILLS}/,实际写入: {c.written_paths()}"
    )
    assert not any(p.startswith("/root") for p in c.written_paths()), c.written_paths()
    assert out["skills"] == 1, f"仅 1 个合法 skill,响应 skills 应为 1,实际 {out}"


def test_skills_same_name_later_write_wins():
    """同名 skill 后写覆盖(现状语义保留;项目级后写即覆盖预置)"""
    mgr, c = _manager({})
    mgr.claude_inject("c1", skills=[{"name": "dup", "content": "first"}])
    mgr.claude_inject("c1", skills=[{"name": "dup", "content": "second"}])

    assert c.file_bytes(f"{HOME_SKILLS}/dup.md") == b"second", "同名后写应覆盖前写"


# ---------------------------------------------------------------------------
# 判据 6:响应 mcp 语义 = 合并后文件内 mcpServers 总条数
# ---------------------------------------------------------------------------
def test_response_mcp_is_merged_total_not_project_count():
    """预置 6 + 项目级 2(其中 1 条同名覆盖)→ 响应 mcp=7(非项目级条数 2);
    skills 计数语义不变"""
    preset = {f"s{i}": {"url": f"http://p{i}"} for i in range(1, 7)}  # s1..s6
    project = {"s6": {"url": "http://project-6"}, "s7": {"url": "http://p7"}}  # 1 同名 + 1 新增
    mgr, c = _manager({HOME_CONFIG: json.dumps({"mcpServers": preset})})

    out = mgr.claude_inject(
        "c1",
        skills=[{"name": "a", "content": "A"}, {"name": "b", "content": "B"}],
        mcp_config={"mcpServers": project},
    )

    merged = json.loads(c.file_bytes(HOME_CONFIG))["mcpServers"]
    assert len(merged) == 7, f"合并后文件应 7 条,实际 {len(merged)}: {sorted(merged)}"
    assert out == {"skills": 2, "mcp": 7}, f"响应 mcp 应为合并后总条数 7,实际 {out}"

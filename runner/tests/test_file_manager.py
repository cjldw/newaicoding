"""
R11 Runner 侧文件管理测试(fake docker exec)
==========================
- list_dir 解析(find printf)
- read/write 文件(base64 往返)
- git_changes numstat+name-status 配对(含 R 重命名)
- _parse_unified_diff 逐文件切分
"""
import base64

from container_manager import ContainerManager, _parse_unified_diff


class FakeExecResult:
    def __init__(self, code=0, output=b""):
        self.exit_code = code
        self.output = output

    def __iter__(self):
        return iter((self.exit_code, self.output))


class ScriptedContainer:
    """按命令子串返回脚本化输出的容器替身"""

    def __init__(self):
        self.short_id = "fake123"
        self.responses: list[tuple[str, int, bytes]] = []  # (子串, code, output)
        self.calls: list[str] = []

    def exec_run(self, cmd_args):
        cmd = cmd_args[-1] if isinstance(cmd_args, list) else str(cmd_args)
        self.calls.append(cmd)
        for pattern, code, output in self.responses:
            if pattern in cmd:
                return FakeExecResult(code, output)
        return FakeExecResult(0, b"")

    def stop(self, timeout=10):
        pass

    def remove(self, force=False):
        pass


class ScriptedClient:
    def __init__(self, container: ScriptedContainer):
        self.container = container

    @property
    def containers(self):
        outer = self

        class API:
            def get(self, _id):
                return outer.container

            def run(self, **kwargs):
                return outer.container

        return API()


def make_mgr(container: ScriptedContainer) -> ContainerManager:
    return ContainerManager(client_factory=lambda: ScriptedClient(container))


# ---------------------------------------------------------------------------
class TestListDir:
    def test_list_dir_parse(self):
        c = ScriptedContainer()
        c.responses.append((
            "find",
            0,
            "d\t4096\t1758412800.0\tsrc\n"
            "f\t1234\t1758412801.5\tmain.py\n".encode(),
        ))
        mgr = make_mgr(c)
        items = mgr.list_dir("fake123", "/workspace/main")
        assert items[0] == {"path": "src", "type": "tree", "size": 4096, "mtime": 1758412800.0}
        assert items[1] == {"path": "main.py", "type": "file", "size": 1234, "mtime": 1758412801.5}


class TestReadWrite:
    def test_read_file_base64(self):
        content = "print('héllo 世界')\n"
        c = ScriptedContainer()
        c.responses.append(("base64 -w0", 0, base64.b64encode(content.encode())))
        mgr = make_mgr(c)
        assert mgr.read_file("fake123", "/workspace/main/a.py") == content

    def test_write_file_roundtrip(self):
        c = ScriptedContainer()
        mgr = make_mgr(c)
        mgr.write_file("fake123", "/workspace/main/new.py", "x = 1")
        cmd = c.calls[-1]
        assert "mkdir -p" in cmd and "base64 -d" in cmd
        # 回解 base64 内容
        b64 = cmd.split("echo ")[1].split(" |")[0]
        assert base64.b64decode(b64).decode() == "x = 1"

    def test_read_file_not_found(self):
        c = ScriptedContainer()
        c.responses.append(("base64 -w0", 1, b""))
        mgr = make_mgr(c)
        try:
            mgr.read_file("fake123", "/nope")
            assert False, "should raise"
        except RuntimeError:
            pass


class TestGitChanges:
    def test_git_changes_parse_with_rename(self):
        c = ScriptedContainer()
        c.responses.append((
            "git diff --numstat",
            0,
            b"12\t3\tsrc/main.py\n"
            b"40\t0\tsrc/new.py\n"
            b"2\t1\tsrc/old.py => src/renamed.py\n",
        ))
        c.responses.append((
            "git diff --name-status",
            0,
            b"M\tsrc/main.py\n"
            b"A\tsrc/new.py\n"
            b"R100\tsrc/old.py\tsrc/renamed.py\n",
        ))
        mgr = make_mgr(c)
        files = mgr.git_changes("fake123", "/workspace/main", "master")
        assert files[0] == {"path": "src/main.py", "status": "M", "additions": 12, "deletions": 3}
        assert files[1] == {"path": "src/new.py", "status": "A", "additions": 40, "deletions": 0}
        assert files[2]["status"] == "R"
        assert files[2]["path"] == "src/renamed.py"
        assert files[2]["old_path"] == "src/old.py"

    def test_git_changes_git_failure_returns_empty(self):
        c = ScriptedContainer()
        c.responses.append(("git diff --numstat", 128, b""))
        c.responses.append(("git diff --name-status", 128, b""))
        mgr = make_mgr(c)
        assert mgr.git_changes("fake123", "/nope", "master") == []


class TestUnifiedDiffParser:
    def test_parse_multi_file(self):
        text = (
            "diff --git a/a.py b/a.py\n"
            "--- a/a.py\n"
            "+++ b/a.py\n"
            "@@ -1 +1 @@\n"
            "-old\n"
            "+new\n"
            "diff --git a/b.py b/b.py\n"
            "new file mode\n"
            "--- /dev/null\n"
            "+++ b/b.py\n"
            "+created\n"
        )
        files = _parse_unified_diff(text)
        assert files[0]["path"] == "a.py"
        assert files[0]["status"] == "modified"
        assert "+new" in files[0]["diff"]
        assert files[1]["path"] == "b.py"
        assert files[1]["status"] == "added"
        assert "+created" in files[1]["diff"]


class TestFileWatcherParse:
    def test_watcher_inotify_command_present(self):
        """watcher 命令含 inotifywait 与降级标记"""
        from file_watcher import _INOTIFY_CMD

        assert "inotifywait" in _INOTIFY_CMD
        assert "INOTIFY_UNAVAILABLE" in _INOTIFY_CMD

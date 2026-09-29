"""
R39 QA-Red 测试:runner 侧 git_commit / git_push 方法规格
=====================================================
覆盖:
- git_commit:身份注入(-c user.name/-c user.email)走 base64 通道(防引号/分号注入)、
  add -A 全仓库、message base64 解码通道、porcelain 空检、无变更返回 {"commit": "none"}
- git_push:push 前 remote 注入 oauth2 token,push 后恢复原 remote;
  push 失败也必须恢复 remote
"""
import base64

import pytest

from container_manager import ContainerManager


class FakeExec:
    """记录 exec_capture 调用序列,按命令关键字返回预设 (code, bytes)"""

    def __init__(self, responses=None, porcelain_empty=False, push_fail=False):
        self.calls = []
        self.responses = responses or {}
        self.porcelain_empty = porcelain_empty
        self.push_fail = push_fail

    def __call__(self, container_id, cmd, workdir=None):
        self.calls.append({"container_id": container_id, "cmd": cmd, "workdir": workdir})
        # porcelain 空检 → 返回空输出 + 0
        if "status --porcelain" in cmd:
            return (0, b"" if self.porcelain_empty else b"M file.py\n")
        if "rev-parse" in cmd:
            return (0, b"abc1234\n")
        if "remote get-url origin" in cmd:
            return (0, b"https://gitlab.example.com/g/repo.git")
        if "remote set-url origin" in cmd:
            return (0, b"")
        if "git push" in cmd:
            if self.push_fail:
                return (1, b"remote: Non-fast-forward reject\n")
            return (0, b"")
        if "git commit" in cmd or "git add" in cmd:
            return (0, b"[main abc1234] commit\n")
        return (0, b"")


def _make_manager():
    m = ContainerManager()
    return m


def _b64(s: str) -> str:
    """辅助:字符串 → base64 编码(测试用)"""
    return base64.b64encode(s.encode()).decode()


class TestGitCommit:
    def test_identity_injection_uses_base64_channel(self):
        """commit 命令必须含 -c user.name=... -c user.email=... 且走 base64 解码通道"""
        m = _make_manager()
        fake = FakeExec()
        m.exec_capture = fake  # type: ignore[method-assign]
        name_b64 = _b64("Alice")
        email_b64 = _b64("alice@example.com")
        m.git_commit("c1", "/workspace/main", _b64("hello"), name_b64, email_b64)
        cmds = " ".join(c["cmd"] for c in fake.calls)
        # 身份走 base64 通道:命令含 printf %s ... | base64 -d 模式
        assert "base64 -d" in cmds
        # -c user.name 和 -c user.email 必须存在(值由 base64 解码注入)
        assert "-c user.name=" in cmds
        assert "-c user.email=" in cmds
        # 原始身份不应直接出现在命令中(已被 base64 编码)
        assert "Alice" not in cmds
        assert "alice@example.com" not in cmds

    def test_add_all_not_specific_path(self):
        """commit 必须 add -A(整仓库),不是单路径"""
        m = _make_manager()
        fake = FakeExec()
        m.exec_capture = fake
        m.git_commit("c1", "/workspace/main", _b64("msg"), _b64("n"), _b64("e@x.com"))
        cmds = " ".join(c["cmd"] for c in fake.calls)
        assert "add -A" in cmds
        # 不能出现 add <具体文件>
        for c in fake.calls:
            if "git add" in c["cmd"]:
                assert c["cmd"].strip().endswith("-A")

    def test_message_base64_decode_channel(self):
        """message 走 base64 通道(防单引号注入),命令含 base64 -d 解码"""
        m = _make_manager()
        fake = FakeExec()
        m.exec_capture = fake
        payload = _b64("feat: quote'test\"")
        m.git_commit("c1", "/workspace/main", payload, _b64("n"), _b64("e@x.com"))
        cmds = " ".join(c["cmd"] for c in fake.calls)
        assert "base64 -d" in cmds
        # 原始 message 不应直接出现在命令中(防注入)
        assert "quote" not in cmds

    def test_porcelain_empty_check_before_commit(self):
        """commit 前必须 git status --porcelain 空检;空 → 返回 {"commit": "none"}"""
        m = _make_manager()
        fake = FakeExec(porcelain_empty=True)
        m.exec_capture = fake
        result = m.git_commit("c1", "/workspace/main", _b64("m"), _b64("n"), _b64("e@x.com"))
        # 空变更 → 返回 {"commit": "none"}(无变更标记)
        assert result == {"commit": "none"}
        # 且未执行 git commit / git add / rev-parse
        commit_calls = [c for c in fake.calls if "git commit" in c["cmd"]]
        add_calls = [c for c in fake.calls if "git add" in c["cmd"]]
        assert commit_calls == []
        assert add_calls == []

    def test_porcelain_nonempty_triggers_commit(self):
        """porcelain 非空 → 执行 add -A + commit + rev-parse"""
        m = _make_manager()
        fake = FakeExec(porcelain_empty=False)
        m.exec_capture = fake
        m.git_commit("c1", "/workspace/main", _b64("m"), _b64("n"), _b64("e@x.com"))
        add_calls = [c for c in fake.calls if "git add" in c["cmd"]]
        # commit 命令含 "commit" 且含 "-c user.name"(身份注入)
        commit_calls = [c for c in fake.calls if "commit" in c["cmd"] and "-c user.name" in c["cmd"]]
        revparse_calls = [c for c in fake.calls if "rev-parse" in c["cmd"]]
        assert add_calls, f"未执行 git add,实际:{fake.calls}"
        assert commit_calls, f"未执行 git commit,实际:{fake.calls}"
        assert revparse_calls, f"未执行 rev-parse,实际:{fake.calls}"

    def test_identity_with_quotes_and_semicolons_is_safe(self):
        """身份含引号/分号/反引号也安全(base64 通道防注入)"""
        m = _make_manager()
        fake = FakeExec(porcelain_empty=False)
        m.exec_capture = fake

        # 身份含危险字符:引号、分号、反引号、$()
        dangerous_name = 'Test"; rm -rf /; `echo pwned`; $(whoami)'
        dangerous_email = "test;@example.com"
        name_b64 = _b64(dangerous_name)
        email_b64 = _b64(dangerous_email)

        result = m.git_commit("c1", "/workspace/main", _b64("test message"), name_b64, email_b64)

        # 验证 commit 命令包含 base64 解码(而非直插原始字符串)
        commit_calls = [c for c in fake.calls if "commit" in c["cmd"]]
        assert commit_calls, "未执行 git commit"
        commit_cmd = commit_calls[0]["cmd"]
        assert "printf %s" in commit_cmd
        assert "base64 -d" in commit_cmd
        # 验证危险字符未直接出现在命令中(已被 base64 编码)
        assert dangerous_name not in commit_cmd
        assert dangerous_email not in commit_cmd
        # 验证结果正常返回(短 hash)
        assert result == {"commit": "abc1234"}


class TestGitPush:
    def test_remote_token_injection_before_push(self):
        """push 前 remote 注入 oauth2:{token}@"""
        m = _make_manager()
        fake = FakeExec()
        m.exec_capture = fake
        m.git_push("c1", "/workspace/main", "feat/x", "secret-token")
        # 找到 set-url 调用,必须含 oauth2:secret-token@
        set_url_calls = [c for c in fake.calls if "remote set-url origin" in c["cmd"]
                         and "oauth2:secret-token@" in c["cmd"]]
        assert set_url_calls, f"未注入 token,实际调用:{fake.calls}"

    def test_remote_restored_after_push(self):
        """push 后必须恢复原 remote(不残留 token)"""
        m = _make_manager()
        fake = FakeExec()
        m.exec_capture = fake
        m.git_push("c1", "/workspace/main", "feat/x", "secret-token")
        set_url_calls = [c for c in fake.calls if "remote set-url origin" in c["cmd"]]
        # 至少两次 set-url:一次注入、一次恢复
        assert len(set_url_calls) >= 2
        # 最后一次 set-url 必须是原 URL(无 token)
        last = set_url_calls[-1]["cmd"]
        assert "oauth2" not in last
        assert "https://gitlab.example.com/g/repo.git" in last

    def test_remote_restored_even_on_push_failure(self):
        """push 失败也必须恢复 remote(不能留 token 痕迹)"""
        m = _make_manager()
        fake = FakeExec(push_fail=True)
        m.exec_capture = fake
        with pytest.raises(Exception):
            m.git_push("c1", "/workspace/main", "feat/x", "secret-token")
        set_url_calls = [c for c in fake.calls if "remote set-url origin" in c["cmd"]]
        last = set_url_calls[-1]["cmd"]
        assert "oauth2" not in last

    def test_push_uses_specified_branch(self):
        """push 命令必须用传入的 branch"""
        m = _make_manager()
        fake = FakeExec()
        m.exec_capture = fake
        m.git_push("c1", "/workspace/main", "feat/xyz", "t")
        push_calls = [c for c in fake.calls if "git push" in c["cmd"]]
        assert push_calls
        assert "feat/xyz" in push_calls[0]["cmd"]

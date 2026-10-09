"""
BUG-086(R8.F9)Red→Green:http remote 凭据注入
================================================
现场:自建 GitLab remote 为 http://47.111.69.64/...,commit_push 凭据注入
replace("https://",...) 对 http 串替换不了任何东西 → 裸推 → git 交互要
用户名(无 tty)→ fatal: could not read Username → PRD 永远推不上去。

修复契约:http/https 通吃,在 :// 后注入 oauth2:token@;push 后恢复原 remote。
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from container_manager import ContainerManager


class _CaptureMgr(ContainerManager):
    """记录 exec_capture 全部命令;get-url 返回 http remote,其余成功"""

    def __init__(self):
        super().__init__(client_factory=lambda: object())
        self.cmds: list[str] = []

    def exec_capture(self, container_id, cmd, workdir=None):
        self.cmds.append(cmd)
        if "git remote get-url origin" in cmd:
            return 0, b"http://47.111.69.64/group/repo.git"
        return 0, b""


def test_commit_push_injects_token_into_http_remote():
    """http remote 也要注入 oauth2 凭据;push 后恢复原 remote"""
    mgr = _CaptureMgr()
    mgr.commit_push(
        container_id="c1", repo_path="/workspace/main", add_path=".",
        message="msg", branch="feat/x", token="tok-123",
    )

    set_urls = [c for c in mgr.cmds if "git remote set-url origin" in c]
    assert set_urls, "应发生 remote set-url(注入与恢复)"
    assert any("http://oauth2:tok-123@47.111.69.64/group/repo.git" in c for c in set_urls), (
        "BUG-086:http remote 未注入凭据(原 replace('https://',...) 对 http 串无效)"
    )
    assert set_urls[-1] == "git remote set-url origin http://47.111.69.64/group/repo.git", (
        "push 后应恢复原始 remote(不留 token 痕迹)"
    )


def test_git_push_injects_token_into_http_remote():
    """R39 git_push 同款修复:http remote 注入 oauth2 凭据"""
    mgr = _CaptureMgr()
    mgr.git_push(
        container_id="c1", repo_path="/workspace/main",
        branch="feat/x", token="tok-123",
    )

    set_urls = [c for c in mgr.cmds if "git remote set-url origin" in c]
    assert any("http://oauth2:tok-123@47.111.69.64/group/repo.git" in c for c in set_urls), (
        "BUG-086:git_push 对 http remote 同样未注入凭据"
    )

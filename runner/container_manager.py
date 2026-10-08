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
PROBE_TASK_SENTINEL = "__probe_claude__"  # R5:探测容器 task_id 哨兵(labels 可识别清理)

# R34.F3:容器内权限确认桥接(claude --permission-prompt-tool 的 MCP stdio server)
PERMGATE_DIR = "/tmp/permgate"
PERMGATE_TOOL_REF = "mcp__permgate__approval"

# R3:容器内 claude CLI 资产路径基准(D4,claude_inject 读-合-写)
CLAUDE_JSON_PATH = "/home/node/.claude.json"
CLAUDE_SKILLS_DIR = "/home/node/.claude/skills"

# 桥接脚本(write_file 注入容器;纯标准库):CLI 作为 MCP client 握手后,每个需确认
# 的工具调用发 tools/call → 桥接把请求 JSON 行追加 req.log,轮询 ans-{n}.json 等平台
# 应答(实证:CLI 无限阻塞等 MCP 应答,5min 超时兜底必须在本层,到点回 deny)。
PERMGATE_BRIDGE_SCRIPT = r'''#!/usr/bin/env python3
"""R34.F3 权限确认桥接(fake MCP stdio server,容器内运行)。
协议:initialize → notifications/initialized → tools/list → tools/call(approval)。
tools/call 到达即把请求行追加 req.log,等待 ans-{seq}.json(平台经 Runner 写入);
PERMGATE_TIMEOUT 秒无应答自动 deny(CLI 不设应答超时,兜底在本层)。"""
import json
import os
import sys
import time

DIR = os.path.dirname(os.path.abspath(__file__))
REQ_LOG = os.path.join(DIR, "req.log")
TIMEOUT = float(os.environ.get("PERMGATE_TIMEOUT", "300"))


def reply(obj):
    sys.stdout.write(json.dumps(obj, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def wait_answer(seq):
    ans_path = os.path.join(DIR, "ans-%d.json" % seq)
    deadline = time.time() + TIMEOUT
    while time.time() < deadline:
        try:
            with open(ans_path, "r", encoding="utf-8") as f:
                decision = json.load(f)
            if isinstance(decision, dict) and decision.get("behavior") in ("allow", "deny"):
                return decision
        except (OSError, ValueError):
            pass  # 未生成/写入中(半行)→ 继续轮询
        time.sleep(0.1)
    return {"behavior": "deny", "message": "confirm timeout (%ds), auto denied" % int(TIMEOUT),
            "interrupt": False}


def main():
    seq = 0
    while True:
        raw = sys.stdin.readline()
        if not raw:
            break  # CLI 退出/被杀 → stdin EOF,桥接随之退出
        raw = raw.strip()
        if not raw:
            continue
        try:
            msg = json.loads(raw)
        except ValueError:
            continue
        method = msg.get("method", "")
        mid = msg.get("id")
        if method == "initialize":
            reply({"jsonrpc": "2.0", "id": mid, "result": {
                "protocolVersion": "2024-11-05", "capabilities": {},
                "serverInfo": {"name": "permgate", "version": "1.0.0"}}})
        elif method == "tools/list":
            reply({"jsonrpc": "2.0", "id": mid, "result": {"tools": [{
                "name": "approval",
                "description": "Human approval gate for tool use",
                "inputSchema": {"type": "object", "properties": {
                    "tool_name": {"type": "string"},
                    "input": {"type": "object"},
                    "tool_use_id": {"type": "string"}},
                    "required": ["tool_name"]}}]}})
        elif method == "tools/call":
            args = ((msg.get("params") or {}).get("arguments") or {})
            seq += 1
            with open(REQ_LOG, "a", encoding="utf-8") as f:
                f.write(json.dumps({"n": seq, "tool_name": args.get("tool_name", ""),
                                    "input": args.get("input") or {},
                                    "tool_use_id": args.get("tool_use_id", "")},
                                   ensure_ascii=False) + "\n")
            decision = wait_answer(seq)
            # 应答格式(实证):decision JSON 内嵌为 content[0].text 字符串
            reply({"jsonrpc": "2.0", "id": mid, "result": {"content": [
                {"type": "text", "text": json.dumps(decision, ensure_ascii=False)}]}})
        elif mid is not None:
            reply({"jsonrpc": "2.0", "id": mid,
                   "error": {"code": -32601, "message": "unknown method: %s" % method}})


main()
'''

PERMGATE_MCP_CONFIG = {
    "mcpServers": {
        "permgate": {"command": "python3", "args": [f"{PERMGATE_DIR}/bridge.py"]},
    }
}


def _merge_permgate_into_config(config: dict | None) -> dict:
    """
    R5.F3(BUG-072 路径②):把 permgate server 幂等合并进 ~/.claude.json 的 mcpServers。
    纯函数,便于单测:
    - config=None / 非法 → 返回全新 {mcpServers: {permgate: ...}}
    - 已有 permgate 键 → 更新(幂等)
    - 已有其他 mcpServers 键 → 保留不覆盖
    - 顶层非 dict 字段(如 mcpServers 非 dict) → 按缺失处理
    """
    cfg = dict(config) if isinstance(config, dict) else {}
    servers = cfg.get("mcpServers")
    if not isinstance(servers, dict):
        servers = {}
    else:
        servers = dict(servers)  # 浅拷贝,不修改入参
    servers["permgate"] = {
        "command": "python3",
        "args": [f"{PERMGATE_DIR}/bridge.py"],
    }
    cfg["mcpServers"] = servers
    return cfg


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

        # BUG-078:必须显式长读超时——from_env() 默认 APIClient timeout=60s 会被
        # exec 流 socket 继承,claude 生成静默段 >60s → socket.timeout("timed out")
        # 从执行线程炸出(通用 except 原样回报),R8.F6 的 120s 看门狗(stream_timeout
        # +pkill)永远轮不到,容器内 claude 成孤儿继续跑。取值须 > 120s(流式看门狗)
        # 且 > 600s(平台非流式超时;json 模式全程无输出,整段生成都是一次静默读)
        return docker.from_env(timeout=3600)

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
        managed: bool = True,
    ) -> dict:
        """
        拉起容器:
        1. 分配随机宿主机端口
        2. docker run(-p 直接映射宿主机;env 注入;资源限制)
        3. 容器内逐 repo 执行 git clone + checkout(+ 建工作分支)
        返回 {"container_id": docker_id, "ports": {"5173": 20001, ...}}

        managed=False(R5 一次性探测容器):不打 qicheng.managed 标签——die 自动重启
        与对账清扫均按该标签过滤,一次性容器不得参与(消除竞态与重启计数泄漏)。
        """
        port_map = allocate_ports(ports)
        port_args: list[str] = []
        for cport, hport in port_map.items():
            port_args += ["-p", f"{hport}:{cport}"]

        # docker run(用 SDK;labels 标记平台容器便于清理与事件过滤)
        labels: dict[str, str] = {"qicheng.task_id": task_id}
        if managed:
            labels["qicheng.managed"] = "true"
        run_kwargs: dict[str, Any] = {
            "image": image,
            "detach": True,
            "environment": env,
            "labels": labels,
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
                self._clone_repo(container, repo, env)
        except Exception:
            logger.exception("容器内 git 操作失败 container=%s", container.short_id)
            self.stop_container(container.short_id, force_push=False)
            raise

        self._restart_counts.pop(container.short_id, None)
        return {
            "container_id": container.short_id,
            "ports": {str(c): h for c, h in port_map.items()},
        }

    def _clone_repo(self, container: Any, repo: dict, env: Optional[dict] = None) -> None:
        """容器内:git clone {url} {path} + checkout branch(+ 建工作分支)

        BUG-029:私有仓库 clone 需认证——平台 env 已注入 GITLAB_TOKEN(D10)。
        普通 clone 失败时用 oauth2:{token}@ URL 重试,成功后立即把 remote 洗回干净
        URL(凭据不落盘、不进 .git/config)。
        """
        url = repo["url"]
        path = repo["path"]
        branch = repo.get("branch")

        code = _exec(container, f"git clone {url} {path}", check=False)
        if code != 0:
            token = (env or {}).get("GITLAB_TOKEN", "")
            if not token:
                # 无 token:按原逻辑抛出(clone 的真实报错)
                _exec(container, f"git clone {url} {path}")
            cred_url = _embed_token(url, token)
            _exec(container, f"git clone {cred_url} {path}")
            # 凭据不留在 .git/config(后续 push 由任务层单独处理)
            _exec(container, f"git -C {path} remote set-url origin {url}", check=False)
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

    def exec_capture(self, container_id: str, cmd: str, workdir: str = None) -> tuple[int, bytes]:
        """
        容器内执行命令并采集输出(R11 文件操作):
        返回 (exit_code, output bytes);不抛异常,由调用方判码。
        """
        container = self.client.containers.get(container_id)
        cmd_args = ["bash", "-lc", cmd]
        if workdir:
            cmd_args = ["bash", "-lc", f"cd {workdir} 2>/dev/null || exit 9; {cmd}"]
        code, output = container.exec_run(cmd_args)
        return code, output if isinstance(output, bytes) else str(output).encode()

    def read_file(self, container_id: str, path: str) -> str:
        """读文件(base64 传输,规避二进制/转义问题);>2MB 或失败抛错"""
        raw = self.read_file_bytes(container_id, path)
        if len(raw) > 2 * 1024 * 1024:
            raise RuntimeError("文件超过 2MB")
        return raw.decode("utf-8", errors="replace")

    def read_file_bytes(self, container_id: str, path: str) -> bytes:
        """读文件原始字节(base64 通道;附件下载用)"""
        code, out = self.exec_capture(container_id, f"base64 -w0 {path}")
        if code != 0:
            raise RuntimeError(f"读取失败({code}): {path}")
        import base64

        return base64.b64decode(out)

    def write_file(self, container_id: str, path: str, content: str) -> None:
        """写文件(base64 解码落盘;自动建父目录)"""
        import base64

        b64 = base64.b64encode(content.encode("utf-8")).decode("ascii")
        code, out = self.exec_capture(
            container_id,
            f"mkdir -p $(dirname {path}) && echo {b64} | base64 -d > {path}",
        )
        if code != 0:
            raise RuntimeError(f"写入失败({code}): {path} {out.decode(errors='ignore')[:200]}")

    def list_dir(self, container_id: str, path: str) -> list[dict]:
        """列目录(find 单层;y=time 返回值转 ISO 由平台格式化)"""
        code, out = self.exec_capture(
            container_id,
            f"find {path} -maxdepth 1 -mindepth 1 -printf '%y\\t%s\\t%T@\\t%P\\n' 2>/dev/null | sort",
        )
        items = []
        for line in out.decode(errors="ignore").splitlines():
            parts = line.split("\t", 3)
            if len(parts) != 4:
                continue
            ftype, size, mtime, rel = parts
            items.append({
                "path": rel,
                "type": "dir" if ftype == "d" else "file",
                "size": int(float(size)),
                "mtime": float(mtime),
            })
        return items

    def file_op(self, container_id: str, operation: str, path: str, new_path: str = None,
                base_branch: str = "master") -> None:
        """文件操作:create(touch)/delete(rm -rf)/rename(mv)/revert(git checkout base -- path)"""
        if operation == "create":
            code, out = self.exec_capture(container_id, f"mkdir -p $(dirname {path}) && touch {path}")
        elif operation == "delete":
            code, out = self.exec_capture(container_id, f"rm -rf {path}")
        elif operation == "rename":
            code, out = self.exec_capture(container_id, f"mkdir -p $(dirname {new_path}) && mv {path} {new_path}")
        elif operation == "revert":
            code, out = self.exec_capture(
                container_id, f"git checkout {base_branch} -- {path}", workdir=str(path).split("/src")[0] or None
            )
        else:
            raise RuntimeError(f"未知操作: {operation}")
        if code != 0:
            raise RuntimeError(f"操作失败({code}): {operation} {path} {out.decode(errors='ignore')[:200]}")

    def git_diff(self, container_id: str, repo_path: str, base_branch: str) -> list[dict]:
        """逐文件 unified diff(git diff -U3 base;含未 commit)"""
        code, out = self.exec_capture(
            container_id,
            f"git diff -U3 --no-color {base_branch} -- . || git diff -U3 --no-color HEAD -- .",
            workdir=repo_path,
        )
        text = out.decode(errors="ignore")
        if code != 0 and not text.strip():
            return []
        return _parse_unified_diff(text)

    def git_changes(self, container_id: str, repo_path: str, base_branch: str) -> list[dict]:
        """
        Q27 变更清单:git diff --numstat --name-status {base}
        numstat 与 name-status 同序逐行配对;R 行附 old_path。
        """
        code_num, out_num = self.exec_capture(
            container_id, f"git diff --numstat {base_branch} -- .", workdir=repo_path)
        code_name, out_name = self.exec_capture(
            container_id, f"git diff --name-status {base_branch} -- .", workdir=repo_path)
        if code_num != 0 or code_name != 0:
            return []

        num_lines = [ln.split("\t") for ln in out_num.decode(errors="ignore").splitlines() if ln.strip()]
        name_lines = [ln.split("\t") for ln in out_name.decode(errors="ignore").splitlines() if ln.strip()]

        files: list[dict] = []
        for i, nums in enumerate(num_lines):
            if len(nums) < 3:
                continue
            additions, deletions, path = nums[0], nums[1], nums[2]
            status = name_lines[i][0][:1] if i < len(name_lines) else "M"
            entry = {
                "path": path.split(" => ")[-1] if " => " in path else path,
                "status": status,
                "additions": 0 if additions == "-" else int(additions),
                "deletions": 0 if deletions == "-" else int(deletions),
            }
            # R 重命名:name-status 行为 R100\told\tnew(tab 分隔两个路径)
            if status == "R" and i < len(name_lines) and len(name_lines[i]) >= 3:
                entry["old_path"] = name_lines[i][1]
            files.append(entry)
        return files

    def git_commit(self, container_id: str, repo_path: str, message_b64: str,
                   author_name_b64: str, author_email_b64: str) -> dict:
        """
        R39:容器内 git commit(整仓库 add -A + commit;身份 base64 传输防注入)。
        流程:
        1. git status --porcelain 空检 → 空则返回 {"commit": "none"}(无变更标记)
        2. git add -A
        3. git -c user.name="$(printf %s {name_b64} | base64 -d)"
              -c user.email="$(printf %s {email_b64} | base64 -d)"
              commit -m "$(printf %s {message_b64} | base64 -d)"
        4. 返回 {"commit": 短 hash}
        身份/message 均走 base64 通道(同 write_file L343 先例),规避引号/特殊字符注入。
        """
        # 空变更预检
        code, out = self.exec_capture(
            container_id, "git status --porcelain", workdir=repo_path)
        if code != 0:
            raise RuntimeError(
                f"git status 失败({code}): {out.decode(errors='ignore')[:300]}")
        if not out.decode(errors="ignore").strip():
            return {"commit": "none"}

        # add -A(整仓库)
        code, out = self.exec_capture(
            container_id, "git add -A", workdir=repo_path)
        if code != 0:
            raise RuntimeError(
                f"git add 失败({code}): {out.decode(errors='ignore')[:300]}")

        # commit(message/身份均 base64 解码;双引号包裹防 shell 注入)
        # printf %s 避免 echo 的 -n/-e 解释;base64 -d 解码
        commit_cmd = (
            f'git -c user.name="$(printf %s {author_name_b64} | base64 -d)" '
            f'-c user.email="$(printf %s {author_email_b64} | base64 -d)" '
            f'commit -m "$(printf %s {message_b64} | base64 -d)"'
        )
        code, out = self.exec_capture(
            container_id, commit_cmd, workdir=repo_path)
        if code != 0:
            raise RuntimeError(
                f"git commit 失败({code}): {out.decode(errors='ignore')[:300]}")

        # 取短 hash
        code, out = self.exec_capture(
            container_id, "git rev-parse --short HEAD", workdir=repo_path)
        if code != 0:
            raise RuntimeError(
                f"git rev-parse 失败({code}): {out.decode(errors='ignore')[:300]}")
        short_hash = out.decode(errors="ignore").strip()
        return {"commit": short_hash}

    def git_push(self, container_id: str, repo_path: str, branch: str, token: str) -> dict:
        """
        R39:容器内 git push(临时注入 oauth2 remote → push → 恢复原 remote)。
        失败抛 RuntimeError(含上游输出截断 ≤300 字符)。
        同 commit_push L463-476 先例,但分离 push 逻辑,不绑定 commit。
        """
        # 取原 remote URL
        code, out = self.exec_capture(
            container_id, "git remote get-url origin", workdir=repo_path)
        origin = out.decode(errors="ignore").strip()
        auth_url = ""
        if code == 0 and origin.startswith("http"):
            auth_url = origin.replace("https://", f"https://oauth2:{token}@", 1)
            self.exec_capture(
                container_id, f"git remote set-url origin {auth_url}",
                workdir=repo_path)

        try:
            code, out = self.exec_capture(
                container_id, f"git push origin {branch}", workdir=repo_path)
            if code != 0:
                raise RuntimeError(
                    f"git push 失败({code}): {out.decode(errors='ignore')[:300]}")
        finally:
            # 恢复原 remote(token 不留痕迹)
            if auth_url:
                self.exec_capture(
                    container_id, f"git remote set-url origin {origin}",
                    workdir=repo_path)

        logger.info("git push 完成 repo=%s branch=%s", repo_path, branch)
        return {"branch": branch}

    def commit_push(self, container_id: str, repo_path: str, add_path: str,
                    message: str, branch: str, token: str) -> None:
        """
        R3 评审通过:容器内 git add/commit/push(评审人个人 token 注入 remote URL;
        push 后恢复原始 remote,不留 token 痕迹)。失败抛错。
        """
        code, out = self.exec_capture(container_id, "git remote get-url origin", workdir=repo_path)
        origin = out.decode(errors="ignore").strip()
        if code == 0 and origin.startswith("http"):
            auth_url = origin.replace("https://", f"https://oauth2:{token}@", 1)
            self.exec_capture(container_id, f"git remote set-url origin {auth_url}", workdir=repo_path)

        code, out = self.exec_capture(
            container_id, f"git add {add_path} && git commit -m '{message}' || echo 'nothing to commit'",
            workdir=repo_path,
        )
        code, out = self.exec_capture(container_id, f"git push origin {branch}", workdir=repo_path)

        if auth_url:
            self.exec_capture(container_id, f"git remote set-url origin {origin}", workdir=repo_path)

        if code != 0:
            raise RuntimeError(f"PRD push 失败({code}): {out.decode(errors='ignore')[:300]}")
        logger.info("PRD 已 commit+push repo=%s branch=%s", repo_path, branch)

    def claude_prompt_stream(
        self,
        container_id: str,
        prompt: str,
        workdir: str = "/workspace/main",
        session_id: str | None = None,
        resume: bool = False,
        model: str | None = None,
        permission_bridge: bool = False,
        on_line: Callable[[str], None] | None = None,
    ) -> dict:
        """
        R32.F3:流式 AI 对话 —— 容器内 claude -p --output-format stream-json --verbose
        逐行读取 stdout,每行(一个 stream-json 事件)经 on_line 回调实时上泵;
        进程结束后从 type=result 事件提取 result/tokens(与 claude_prompt 同口径)。

        实现:docker low-level exec(socket=True,非 tty)按行读;BUG-050 同款
        recv/read 探测(SocketIO vs NpipeSocket)。on_line 为 None 时退化为一次性收集。
        R34.F2:model 非空时拼 --model(消息级模型切换;CLI flag 覆盖容器创建时
        固化的 ANTHROPIC_MODEL env——env 改不到运行中容器,只能走 flag)。
        R34.F3:permission_bridge=True 时加 --permission-prompt-tool(mcp__permgate__approval,
        经注入容器的 MCP stdio 桥接承接权限确认;不用 --strict-mcp-config,保留
        claude_inject 注入的项目级 MCP 配置)。False 维持原命令(无确认通道,静默拒绝)。
        """
        import json as _json
        import shlex as _shlex

        session_flag = ""
        if session_id is not None:
            if resume:
                session_flag = f" --resume {_shlex.quote(session_id)}"
            else:
                session_flag = f" --session-id {_shlex.quote(session_id)}"
        model_flag = f" --model {_shlex.quote(model)}" if model else ""
        # R5.F3(BUG-072 路径①):任务 AI 对话本身即授权环境,放行 MCP 工具面免人工审批。
        # 留痕:mysql_query 类工具具备写库能力(mcp-server-mysql 不限只读),任务容器环境
        # 由用户自配凭据,接受。Bash/Edit/Write 等危险内置工具**不**放行,保持审批语义。
        allowed_tools = (
            "mcp__mysql_dev__* mcp__mysql_beta__* mcp__filesystem__* "
            "mcp__brave-search__* mcp__figma__* mcp__github__* "
            "ListMcpResourcesTool ReadMcpResourceTool ReadMcpResourceDirTool"
        )
        allowed_tools_flag = f" --allowedTools '{allowed_tools}'"

        # R5.F3 二修(BUG-072 第 41 轮):--permission-prompt-tool + permgate 桥在 CLI
        # 2.1.280 实测整体失效——两种注入形态都报 "MCP tool mcp__permgate__approval
        # (passed via --permission-prompt-tool) not found"(permgate 不进可用工具列表:
        # --mcp-config 与合并进 ~/.claude.json 两形态容器内均复现)。坏 flag 使每次 MCP
        # 工具调用 tool_use_error → 秒级空结算占位(用户 14:44 复现)。stream 链路摘除
        # 该 flag:MCP 走上方 --allowedTools 放行;Bash/Edit/Write 需审批工具维持静默
        # 拒绝;桥接恢复归 CLI 升级/换实现(BUG-072/R34.F3 留档)。permission_bridge
        # 形参保留(调用方兼容),本函数不再输出任何权限 flag。
        perm_flag = ""

        # BUG-069(F4):去末尾 2>/dev/null,stderr 走 docker demux 分离(帧 stream=2)
        # cd 的 2>/dev/null 保留(目录切换失败静默合理)
        # R5.F5(BUG-076):prompt 走临时文件 + stdin 重定向,不占 argv(避 ARG_MAX)
        # BUG-077:不得写 `claude -p -`——CLI 2.1.280 把「-」当字面 prompt 与 stdin 拼接,
        # 所有消息变成 "-\n<原文>",斜杠命令/技能(/rd-prd 等)永远无法触发(实证:差分 + 尸检)
        import uuid as _uuid
        prompt_file = f"/tmp/prompt_{_uuid.uuid4().hex}.txt"
        self.write_file(container_id, prompt_file, prompt)
        cmd = (
            f"cd {workdir} 2>/dev/null; "
            # BUG-058:--include-partial-messages 输出 stream_event/text_delta 增量(逐字流式)
            f"claude -p --output-format stream-json --verbose "
            f"--include-partial-messages{session_flag}{model_flag}{allowed_tools_flag}{perm_flag} "
            f"< {_shlex.quote(prompt_file)}; "
            f"_rc=$?; rm -f {_shlex.quote(prompt_file)}; exit $_rc"
        )
        api = self.client.api
        exec_id = api.exec_create(container_id, ["bash", "-lc", cmd], tty=False, stdin=False)
        sock = api.exec_start(exec_id, tty=False, socket=True, demux=False)

        buf = b""       # 原始 socket 字节缓冲(含 docker 帧)
        line_buf = b""  # 已剥帧的行缓冲
        result_text = ""
        tokens_in = 0
        tokens_out = 0
        lines: list[str] = []
        # BUG-069(F1):累积 textDelta 文本 —— CLI 不发 result 事件时,用累积文本兜底
        accumulated_text_parts: list[str] = []
        # BUG-069(F4):stderr 捕获 —— 截断 ≤2000 字符,供日志/排障
        stderr_tail = ""
        _STDERR_TAIL_MAX = 2000
        # R5.F3 三修(BUG-072):--resume 不存在的会话时,CLI 输出单行 error-result
        # (is_error=true,errors=["No conversation found..."],result 字段空)——
        # 非零行、非正常空回复,原「零行降级」判定失效(BUG-067②)。置位供降级
        resume_error_seen = False

        def _drain_line_buf() -> None:
            """把行缓冲按 \\n 切行处理(上泵/提 result);非 local 的 result_* 经闭包写回"""
            nonlocal line_buf, result_text, tokens_in, tokens_out, resume_error_seen, stderr_tail
            while b"\n" in line_buf:
                raw, line_buf = line_buf.split(b"\n", 1)
                line = raw.decode(errors="ignore").strip()
                if not line:
                    continue
                lines.append(line)
                try:
                    evt = _json.loads(line)
                except _json.JSONDecodeError:
                    evt = None
                if evt and evt.get("type") == "result":
                    result_text = evt.get("result", "") or result_text
                    usage = evt.get("usage") or {}
                    tokens_in = evt.get("total_tokens_in") or usage.get("input_tokens", 0) or tokens_in
                    tokens_out = evt.get("total_tokens_out") or usage.get("output_tokens", 0) or tokens_out
                    # R5.F3 三修(BUG-072):error-result 视同 resume 失败(见上方注释),
                    # CLI 的 errors[] 折入 stderr_tail 供排障
                    if evt.get("is_error") and not result_text:
                        resume_error_seen = True
                        errs = evt.get("errors") or []
                        if errs and len(stderr_tail) < _STDERR_TAIL_MAX:
                            stderr_tail += "cli: " + "; ".join(str(e) for e in errs)
                    continue  # result 事件不上泵(终态由 result 回报承载)
                # BUG-069(F1):累积 textDelta 文本 —— 长消息/中途出错场景 CLI 不发 result 事件时兜底
                if evt and evt.get("type") == "stream_event":
                    inner = evt.get("event") or {}
                    if inner.get("type") == "content_block_delta":
                        delta = inner.get("delta") or {}
                        if delta.get("type") == "text_delta" and delta.get("text"):
                            accumulated_text_parts.append(delta["text"])
                if on_line is not None:
                    on_line(line)

        try:
            while True:
                chunk = sock.recv(4096) if hasattr(sock, "recv") else sock.read(4096)
                if not chunk:
                    break
                buf += chunk
                # BUG-056:docker exec 非 tty(tty=False)stdout 是多路复用帧流 ——
                # 8 字节帧头 = stream 类型 1B + 填充 3B(恒 \x00\x00\x00)+ 载荷长度 4B 大端。
                # demux=False 裸读必须先剥帧,否则帧头混入行流(实证:\x01\x00..前缀污染对话内容)
                while True:
                    if len(buf) < 8:
                        break  # 不足一个帧头,等下一个 chunk(EOF 残字节由循环外冲入行缓冲)
                    if buf[0] in (0, 1, 2) and buf[1:4] == b"\x00\x00\x00":
                        frame_len = int.from_bytes(buf[4:8], "big")
                        if len(buf) < 8 + frame_len:
                            break  # 帧体未收齐
                        if buf[0] == 1:  # stdout → 入行缓冲(剥帧后按行处理)
                            line_buf += buf[8:8 + frame_len]
                        elif buf[0] == 2:  # BUG-069(F4):stderr → 累积到 stderr_tail(截断 ≤2000 字符)
                            stderr_piece = buf[8:8 + frame_len].decode(errors="ignore")
                            if len(stderr_tail) < _STDERR_TAIL_MAX:
                                stderr_tail += stderr_piece
                                if len(stderr_tail) > _STDERR_TAIL_MAX:
                                    stderr_tail = stderr_tail[:_STDERR_TAIL_MAX]
                        buf = buf[8 + frame_len:]
                    else:
                        # 防御:非帧协议流(理论不发生)按裸流处理,保持旧兜底
                        line_buf += buf
                        buf = b""
                        break
                _drain_line_buf()
            # EOF:冲入残余(末尾不足 8 字节的半帧头/无尾 \n 的最后一行)
            line_buf += buf
            buf = b""
            _drain_line_buf()
        finally:
            try:
                sock.close()
            except Exception:
                pass

        # BUG-069(F1):finalize 优先级:显式 result 事件 > 累积文本 > lines[-1] 兜底
        # 长消息/中途出错场景 CLI 不发 result 事件,累积文本是完整内容;lines[-1] 是
        # 最后一个 content_block_delta(解析出空/残缺),仅作末道兜底
        accumulated_text = "".join(accumulated_text_parts)
        if not result_text and accumulated_text:
            result_text = accumulated_text
        if not result_text and lines:
            # 流式输出缺失/被 CLI 版本降级:兜底取最后一行纯文本(与 claude_prompt 非 JSON 兜底同思路)
            try:
                last = _json.loads(lines[-1])
                result_text = last.get("result", "") if isinstance(last, dict) else ""
            except _json.JSONDecodeError:
                result_text = lines[-1]
        # BUG-060(R32.F8):lines 计数供调用方识别「resume 会话不存在」的静默失败
        # (CLI 报错走 stderr 被吞,stdout 零行;正常空回复也会有 assistant 行)
        # BUG-069(F1/F4):返回体新增 accumulated_text(供后端兜底)+ stderr_tail(供日志排障)
        # R5.F3 三修(BUG-072):resume_error=error-result 且无有效内容(降级判定用)
        return {"result": result_text, "tokens_in": int(tokens_in or 0),
                "tokens_out": int(tokens_out or 0), "lines": len(lines),
                "accumulated_text": accumulated_text, "stderr_tail": stderr_tail,
                "resume_error": bool(resume_error_seen and not result_text and not accumulated_text)}

    def _read_container_json(self, container_id: str, path: str) -> tuple[bool, Optional[dict]]:
        """读容器内 JSON 文件,统一 exit code gating(claude_inject R32.F1 / probe_claude R5 共用)。
        返回 (可读, 解析结果):
        - 命令失败(path 不存在/cat 失败,exit != 0)→ (False, None):调用方按「读取失败」处理
        - 可读但非法 JSON / 顶层非 dict → (True, None):调用方按「空配置」处理(R5 契约:非法按空)
        """
        import json as _json

        code, out = self.exec_capture(container_id, f"cat {path} 2>/dev/null")
        if code != 0:
            return False, None
        try:
            data = _json.loads(out.decode(errors="ignore") or "{}")
        except _json.JSONDecodeError:
            return True, None
        return True, (data if isinstance(data, dict) else None)

    def claude_inject(
        self,
        container_id: str,
        skills: list[dict] | None = None,
        mcp_config: dict | None = None,
    ) -> dict:
        """
        R32.F1 / R3 合并语义改造:把平台 Skills/MCP 写入容器 claude CLI 配置:
        - skills:[{name, content}] → /home/node/.claude/skills/{name}.md(逐个 write_file,自动建目录)
        - mcp_config:{mcpServers:{...}} → 与容器既有 /home/node/.claude.json 按 server 名合并:
          项目级覆盖同名,镜像预置项保留,文件其余键原样保留(整文件读-合-写;R3,路径基准 D4 /home/node)
        返回 {"skills": n, "mcp": m},mcp=合并后文件内 mcpServers 总条数(R3 语义变更);
        幂等(重跑合并结果稳定)。
        """
        import json as _json

        skills = skills or []
        project_servers = (mcp_config or {}).get("mcpServers") or {}
        if not isinstance(project_servers, dict):
            project_servers = {}  # 上游畸形 args 防护(与既有 mcpServers 非 dict 按 {} 对称)
        logger.info(
            "claude_inject 入口 container=%s skills=%d project_mcp=%d",
            container_id, len(skills), len(project_servers),
        )

        try:
            written = 0
            for s in skills:
                name = (s.get("name") or "").strip()
                content = s.get("content") or ""
                if not name or not content:
                    continue
                # 防路径穿越:skill 名只允许文件名安全字符
                safe = "".join(c for c in name if c.isalnum() or c in "-_")
                if not safe:
                    continue
                self.write_file(container_id, f"{CLAUDE_SKILLS_DIR}/{safe}.md", content)
                written += 1

            mcp_count = 0
            if project_servers:
                # 读既有配置(共享 _read_container_json:读取失败/非法 JSON/顶层非 dict 一律按
                # 空对象——既有兜底行为不变),按 server 名合并 mcpServers 段后回写(R3 合并语义)
                readable, existing_cfg = self._read_container_json(container_id, CLAUDE_JSON_PATH)
                if not readable:
                    # cat 失败可能为临时执行通道故障,已按空配置兜底;若容器内存在预置
                    # mcpServers 会被本次写入覆盖(兜底语义不变,仅告警留痕)
                    logger.warning(
                        "claude_inject cat 既有配置失败 container=%s(可能为临时执行通道故障),"
                        "已按空配置兜底;若容器内存在预置 mcpServers 会被本次写入覆盖",
                        container_id,
                    )
                existing: dict = existing_cfg or {}
                preset_servers = existing.get("mcpServers")
                if not isinstance(preset_servers, dict):
                    preset_servers = {}  # 契约「非 dict 按 {}」
                overwritten = sorted(k for k in project_servers if k in preset_servers)
                existing["mcpServers"] = {**preset_servers, **project_servers}
                self.write_file(
                    container_id,
                    CLAUDE_JSON_PATH,
                    _json.dumps(existing, ensure_ascii=False, indent=2),
                )
                mcp_count = len(existing["mcpServers"])
                # 单条结果日志(含 skills 落盘数,替代原尾部遗留日志,消除 mcp= 双语义)
                logger.info(
                    "claude_inject 合并完成 container=%s skills=%d mcp_total=%d overwritten=%s",
                    container_id, written, mcp_count, overwritten,
                )
        except Exception:
            logger.exception("claude_inject 失败 container=%s(上游 failed_sides 降级,不阻塞就绪)", container_id)
            raise

        return {"skills": written, "mcp": mcp_count}

    def probe_claude(self, image: str = "platform/devbox:v2") -> dict:
        """
        R5 系统级采集(R4 扩展):拉起临时容器探测镜像内置的 Claude 资产,单次调用内完成:
        start_container(repos=[],task_id 哨兵,managed=False)→ exec 探测 → stop_container(用后即毁)。
        探测面(R4 路径校准:/root → /home/node,与镜像内安装用户 node 一致):
        - skills:只取 /home/node/.claude/skills/ 一级**目录**(PRD「skill 目录名」)
        - plugin skills/commands:遍历 /home/node/.claude/plugins/cache(布局已实测钉死:
          cache/<marketplace>/<plugin>/<hash>/skills/<分类>/<skill>/SKILL.md,条目名取
          SKILL.md 父目录名,分类层不混入;commands 同根 -path "*/commands/*.md" 取
          文件名词干)。目录缺失/不可达(find 非零)→ 两段按空,info 级留痕,不报错、
          不计入 failed_sides(R4 契约)
        - mcps:/home/node/.claude.json 的 mcpServers 段

        部分结果语义(PRD R1):探测命令不掩盖 exit code(无 `|| true`)——单侧命令失败
        → 该侧按空并在 failed_sides/warnings 标记(平台侧据此不清该侧旧库);
        mcpServers 真值非 dict 一律按空(契约「非法按空」)。
        容器启动失败/exec 通道硬异常向上抛(平台侧转 502 可重试),容器销毁 finally 兜底。
        返回 {"skills": [平台 skill 目录名...], "plugin_skills": [plugin skill 名...],
              "plugin_commands": [plugin command 名...],
              "mcps": [{name, transport, ...原始配置}],
              "failed_sides": ["skills"...], "warnings": [...]}
        (R4 契约微调 2026-09-27:skills 保持「平台 skills 目录名」存量语义,plugin 条目
        走 plugin_skills/plugin_commands 独立字段,平台侧落库按字段来源打 detail.source 标记)
        """
        import time as _time

        t0 = _time.monotonic()
        started: dict | None = None
        try:
            started = self.start_container(
                task_id=PROBE_TASK_SENTINEL,  # 哨兵:探测容器不挂任务,task_id 仍可识别清理
                image=image,
                env={},
                ports=[],
                repos=[],  # 空仓库:不 git clone
                managed=False,  # 一次性容器:不打 qicheng.managed(die 自动重启/清扫不接管)
            )
            cid = started["container_id"]
            logger.info("probe_claude 临时容器已起 container=%s image=%s", cid, image)

            failed_sides: list[str] = []
            warnings: list[str] = []

            # 探测 1:skills 只取一级目录名(find -type d;exit code 不掩盖——
            # 目录缺失/命令失败 → 该侧失败,保留原数据由平台侧处理;R4 路径基准 /home/node)
            code, out = self.exec_capture(
                cid,
                "find /home/node/.claude/skills -mindepth 1 -maxdepth 1 -type d -printf '%f\\n' 2>/dev/null",
            )
            if code == 0:
                skills = [ln.strip() for ln in out.decode(errors="ignore").splitlines() if ln.strip()]
            else:
                skills = []
                failed_sides.append("skills")
                warnings.append(f"skills 探测失败(exit {code}),该侧保留原有数据")
                logger.warning("probe_claude skills 探测失败 code=%s", code)

            # 探测 1.5(R4):plugin skills/commands——best-effort 段,两条独立 find
            # (QA fake 路由按 SKILL.md / */commands/*.md 区分,勿合并成单条):
            # skills 条目名 = SKILL.md 父目录名(deprecated/ 无 SKILL.md 由 -name 天然不采,
            # 分类层不混入);commands 取文件名词干。目录缺失/不可达(find 非零)→ 按空 +
            # info 留痕,不报错、不进 failed_sides(R4 契约「插件目录缺失不计入」)
            plugin_skills: list[str] = []
            plugin_commands: list[str] = []
            code, out = self.exec_capture(
                cid,
                "find /home/node/.claude/plugins/cache -name SKILL.md 2>/dev/null",
            )
            if code == 0:
                for ln in out.decode(errors="ignore").splitlines():
                    parts = ln.strip().rstrip("/").split("/")
                    if len(parts) >= 2 and parts[-1] == "SKILL.md" and parts[-2]:
                        plugin_skills.append(parts[-2])
            else:
                logger.info(
                    "probe_claude plugins/cache 目录缺失或不可达(code=%s),plugin skills 按空", code
                )
            code, out = self.exec_capture(
                cid,
                'find /home/node/.claude/plugins/cache -path "*/commands/*.md" 2>/dev/null',
            )
            if code == 0:
                for ln in out.decode(errors="ignore").splitlines():
                    fname = ln.strip().rstrip("/").rsplit("/", 1)[-1]
                    if fname.endswith(".md") and len(fname) > 3:
                        plugin_commands.append(fname[:-3])
            else:
                logger.info(
                    "probe_claude plugins/cache 目录缺失或不可达(code=%s),plugin commands 按空", code
                )

            # 探测 2:claude.json 的 mcpServers 段(_read_container_json 统一 exit code gating:
            # 读取失败=该侧失败;非法 JSON/顶层非 dict 按空;mcpServers 非 dict 一律按空)
            mcps: list[dict] = []
            readable, cfg = self._read_container_json(cid, "/home/node/.claude.json")
            if readable:
                servers = cfg.get("mcpServers") if cfg else None
                if not isinstance(servers, dict):
                    servers = {}  # 契约「非法按空」:mcpServers 为 list/str 等真值非 dict 时不炸
                for name, mcfg in servers.items():
                    if not isinstance(mcfg, dict):
                        mcfg = {}
                    entry = {"name": name}
                    entry.update(mcfg)  # 原始配置保留(detail 存探测原文)
                    entry["transport"] = mcfg.get("transport") or mcfg.get("type") or ""
                    mcps.append(entry)
            else:
                failed_sides.append("mcps")
                warnings.append("mcps 探测失败(/home/node/.claude.json 不可读),该侧保留原有数据")
                logger.warning("probe_claude mcp 探测失败:/home/node/.claude.json 不可读")

            logger.info(
                "probe_claude 完成 image=%s skills=%d plugin_skills=%d plugin_commands=%d "
                "mcps=%d failed_sides=%s 耗时=%.1fs",
                image, len(skills), len(plugin_skills), len(plugin_commands),
                len(mcps), failed_sides or "无", _time.monotonic() - t0,
            )
            return {
                "skills": skills,
                "plugin_skills": plugin_skills,
                "plugin_commands": plugin_commands,
                "mcps": mcps,
                "failed_sides": failed_sides,
                "warnings": warnings,
            }
        finally:
            # 用后即毁(成功/exec 异常两条路径都销毁;启动失败无容器可销毁)
            if started is not None:
                try:
                    self.stop_container(started["container_id"], force_push=False)
                except Exception:
                    logger.exception(
                        "probe_claude 容器销毁失败 container=%s(需人工清理)",
                        started.get("container_id"),
                    )

    def claude_prompt(
        self,
        container_id: str,
        prompt: str,
        workdir: str = "/workspace/main",
        session_id: str | None = None,
        resume: bool = False,
        model: str | None = None,
    ) -> dict:
        """
        R4 AI 执行(CLI 兜底):容器内 claude -p <prompt> --output-format json
        返回 {"result", "tokens_in", "tokens_out"};输出非 JSON 时按纯文本兜底。

        R9.F1 会话参数:
        - session_id + resume=False → --session-id <sid>(首次建会话)
        - session_id + resume=True  → --resume <sid>(续接已有会话)
        - 都不传 → 维持原 cmd(兼容旧行为)
        R34.F2 模型参数:model 非空 → --model(消息级切换,覆盖 ANTHROPIC_MODEL env)。
        """
        import json as _json
        import shlex as _shlex

        # R9.F1:会话参数拼接(规避 CLI 版本差异:首次 --session-id,后续 --resume)
        session_flag = ""
        if session_id is not None:
            if resume:
                session_flag = f" --resume {_shlex.quote(session_id)}"
            else:
                session_flag = f" --session-id {_shlex.quote(session_id)}"
        model_flag = f" --model {_shlex.quote(model)}" if model else ""

        # R5.F5(BUG-076):prompt 走临时文件 + stdin 重定向,不占 argv(避 ARG_MAX)
        # BUG-077:同流式路径,`claude -p -` 的「-」会被 CLI 当字面 prompt(斜杠命令全灭),去掉
        import uuid as _uuid
        prompt_file = f"/tmp/prompt_{_uuid.uuid4().hex}.txt"
        self.write_file(container_id, prompt_file, prompt)
        cmd = (
            f"cd {workdir} 2>/dev/null; "
            f"claude -p --output-format json{session_flag}{model_flag} < {_shlex.quote(prompt_file)} 2>/dev/null; "
            f"_rc=$?; rm -f {_shlex.quote(prompt_file)}; exit $_rc"
        )
        code, out = self.exec_capture(container_id, cmd)
        text = out.decode(errors="ignore").strip()
        if code != 0 and not text:
            raise RuntimeError(f"claude CLI 执行失败({code})")
        try:
            data = _json.loads(text)
            return {
                "result": data.get("result", text),
                "tokens_in": data.get("total_tokens_in") or data.get("usage", {}).get("input_tokens", 0) or 0,
                "tokens_out": data.get("total_tokens_out") or data.get("usage", {}).get("output_tokens", 0) or 0,
            }
        except _json.JSONDecodeError:
            return {"result": text, "tokens_in": 0, "tokens_out": 0}

    def cancel_claude(self, container_id: str) -> bool:
        """
        R34.F1:对话真取消 —— 杀容器内 claude CLI 进程(对话取消)。
        pkill -f 命中执行中的 `claude -p ...`;exec socket 随进程死亡 EOF,
        读线程(claude_prompt/claude_prompt_stream)退出,终态由调用方按
        cancelled 结算。模式用 [c]laude 方括号技巧:pkill 自身与其 bash -lc
        父进程命令行含 "[c]laude" 字面量,正则 [c]laude 只匹配 "claude",
        避免杀到自己所在 exec 会话。`|| true` 幂等:进程已自然结束(无匹配)
        也算成功。容器已销毁时向上抛(调用方记日志兜底)。
        """
        code, out = self.exec_capture(container_id, 'pkill -f "[c]laude" || true')
        logger.info("容器内 claude 已取消 container=%s exit=%s", container_id, code)
        return code == 0

    # -----------------------------------------------------------------
    # R34.F3:权限确认桥接(--permission-prompt-tool 的 MCP stdio 桥)
    # -----------------------------------------------------------------
    def setup_permission_bridge(self, container_id: str) -> bool:
        """
        注入权限确认桥接(每次 claude_prompt_stream 执行前调用):
        - 写 bridge.py 到 PERMGATE_DIR(桥接脚本,承接 tools/call 协议)
        - 把 permgate server 配置**幂等合并**进 /home/node/.claude.json 的 mcpServers
          (R5.F3 改造:不再写独立 mcp.json + --mcp-config;2.1.280 下 --mcp-config 的
          server 不进 tools 列表,合并到 claude.json 才能被 CLI 识别)
        - 清空上次请求/应答残留
        失败(容器异常等)返回 False —— 调用方降级不加权限参数(维持静默拒绝现状,
        验收③:无确认能力时不回归)。
        """
        import json as _json

        try:
            self.write_file(container_id, f"{PERMGATE_DIR}/bridge.py", PERMGATE_BRIDGE_SCRIPT)
            # 幂等合并 permgate 进 ~/.claude.json(R5.F3)
            readable, existing_cfg = self._read_container_json(
                container_id, CLAUDE_JSON_PATH)
            merged = _merge_permgate_into_config(existing_cfg if readable else None)
            self.write_file(container_id, CLAUDE_JSON_PATH,
                            _json.dumps(merged, ensure_ascii=False))
            self.exec_capture(container_id,
                              f"rm -f {PERMGATE_DIR}/req.log {PERMGATE_DIR}/ans-*.json 2>/dev/null")
            logger.info("权限确认桥接已注入 container=%s dir=%s(merged into %s)",
                        container_id, PERMGATE_DIR, CLAUDE_JSON_PATH)
            return True
        except Exception:
            logger.exception("权限桥接初始化失败 container=%s(本次执行降级为无确认通道)", container_id)
            return False

    def read_new_confirm_requests(self, container_id: str, cursor: int) -> tuple[int, list[dict]]:
        """
        读桥接请求日志(req.log)cursor 行之后的新权限请求(轮询通道:容器内桥接与
        Runner 之间无直连,经 docker exec cat 中转)。
        返回 (新 cursor, 请求列表 [{n, tool_name, input, tool_use_id}]);无日志/读失败
        返回 (cursor, []) 由调用方继续轮询。
        """
        import json as _json

        code, out = self.exec_capture(container_id, f"cat {PERMGATE_DIR}/req.log 2>/dev/null")
        if code != 0:
            return cursor, []
        lines = out.decode(errors="ignore").splitlines()
        requests: list[dict] = []
        for line in lines[cursor:]:
            line = line.strip()
            if not line:
                continue
            try:
                obj = _json.loads(line)
            except _json.JSONDecodeError:
                continue
            if isinstance(obj, dict) and obj.get("n") is not None:
                requests.append(obj)
        return len(lines), requests

    def write_confirm_answer(self, container_id: str, seq: int, decision: dict) -> None:
        """
        写确认应答文件(ans-{seq}.json,桥接轮询读取后回 MCP 应答放行/拒绝 CLI)。
        decision 形如 {"behavior": "allow", "updatedInput": {...}} /
        {"behavior": "deny", "message": "...", "interrupt": false}(实证格式)。
        """
        import base64 as _base64
        import json as _json

        payload = _json.dumps(decision, ensure_ascii=False).encode("utf-8")
        b64 = _base64.b64encode(payload).decode("ascii")
        code, out = self.exec_capture(
            container_id, f"echo {b64} | base64 -d > {PERMGATE_DIR}/ans-{int(seq)}.json")
        if code != 0:
            raise RuntimeError(
                f"确认应答写入失败({code}): ans-{int(seq)}.json "
                f"{out.decode(errors='ignore')[:200]}")

    def cleanup_permission_bridge(self, container_id: str) -> None:
        """清理桥接目录(执行收尾调用;孤儿桥接进程按自身 5min 超时自灭,尽力而为)"""
        self.exec_capture(container_id, f"rm -rf {PERMGATE_DIR} 2>/dev/null")

    def merge_branch(self, container_id: str, repo_path: str,
                     source_branch: str, target_branch: str) -> None:
        """
        R7 发布 merge:checkout target → merge source。
        冲突(非快进失败)抛错 → 平台标 failed 提示人工(R7:AI 解决能力由任务对话承载)。
        """
        code, out = self.exec_capture(
            container_id,
            f"git checkout {target_branch} && git merge {source_branch} "
            f"|| (git merge --abort; exit 1)",
            workdir=repo_path,
        )
        if code != 0:
            raise RuntimeError(
                f"merge 冲突或失败({code}): {out.decode(errors='ignore')[:300]}"
            )

    def run_deploy(self, container_id: str, script: str,
                   health_port: int, health_path: str = "/",
                   health_timeout: int = 10) -> dict:
        """
        R7 部署执行:后台启动部署脚本 → 健康检查轮询(10s)。
        返回 {"ok": True, "log": ...};健康检查失败抛错。
        """
        # 后台启动(nohup),避免阻塞
        code, out = self.exec_capture(
            container_id, f"nohup bash -lc '{script}' > /tmp/deploy.out 2>&1 &", workdir="/workspace/main",
        )
        # 健康检查轮询
        import time as _time

        deadline = _time.time() + health_timeout
        while _time.time() < deadline:
            hcode, _ = self.exec_capture(
                container_id,
                f"curl -s -o /dev/null -w '%{{http_code}}' http://localhost:{health_port}{health_path}",
            )
            if hcode == 0:
                return {"ok": True}
            _time.sleep(1)
        raise RuntimeError(f"健康检查失败:localhost:{health_port} 在 {health_timeout}s 内未就绪")

    def iter_events(self) -> Any:
        """阻塞迭代 Docker events(只关注容器 start/die/oom)"""
        for event in self.client.events(decode=True):
            if event.get("Type") == "container" and event.get("Action") in ("start", "die", "oom"):
                yield event


def _parse_unified_diff(text: str) -> list[dict]:
    """unified diff 文本 → 逐文件 [{path, status, diff}](R11 Diff 视图)"""
    files: list[dict] = []
    current: dict | None = None
    lines = text.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i]
        if line.startswith("--- a/") or line.startswith("--- /dev/"):
            # 新文件块开始(+++ 在下一行)
            old = line[6:] if line.startswith("--- a/") else ""
            new_line = lines[i + 1] if i + 1 < len(lines) else ""
            new = new_line[6:] if new_line.startswith("+++ b/") else ("/dev/null" if new_line.startswith("+++ /dev/") else "")
            path = new if new not in ("", "/dev/null") else old
            status = "deleted" if new == "/dev/null" else ("added" if old == "" else "modified")
            current = {"path": path, "status": status, "diff": ""}
            files.append(current)
            i += 2
            continue
        if current is not None:
            current["diff"] += line + "\n"
        i += 1
    return files


def _cpu_limit_to_nano_cpus(cpu_limit: str) -> int:
    """'2c' → 2 * 1e9 nano CPUs"""
    try:
        cores = float(cpu_limit.rstrip("c"))
        return int(cores * 1e9)
    except ValueError:
        return int(2e9)


def _embed_token(url: str, token: str) -> str:
    """http(s) URL 嵌入 oauth2 凭据(clone 认证重试用;clone 后立即洗回原 URL)"""
    for scheme in ("https://", "http://"):
        if url.startswith(scheme):
            return f"{scheme}oauth2:{token}@{url[len(scheme):]}"
    return url


def _exec(container: Any, cmd: str, cwd: str = "", check: bool = True) -> int:
    """容器内执行 shell 命令(docker exec 语义);返回退出码"""
    full = f"bash -lc 'cd {cwd} 2>/dev/null; {cmd}'" if cwd else f"bash -lc '{cmd}'"
    exit_code, output = container.exec_run(full)
    if check and exit_code != 0:
        raise RuntimeError(f"容器内命令失败({exit_code}): {cmd}\n{output.decode(errors='ignore')[:500]}")
    if check:
        logger.debug("容器内命令完成: %s", cmd)
    return exit_code if not check else 0

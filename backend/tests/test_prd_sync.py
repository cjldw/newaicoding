"""
R2 PRD 回传机制(容器 → 平台副本)— TDD Red 测试
================================================
完成判据 8 条中 6 条自动化覆盖(判据 7「非流式不接入」与判据 8「独立 session」留代码审查):
1. 结算回传成功:容器在线 + read_file 返回内容 → prd_content 更新
2. 容器离线跳过:无 running 容器 → prd_content 不变,无异常
3. 回读失败静默:read_file 抛异常 → 主流程不受影响,日志含 [prd-sync] failed
4. 空内容跳过:read_file 返回空串 → prd_content 不被覆盖(旧值保留)
5. 超长截断:read_file 返回 >16MB → 库中 ≤16MB + warning 日志
6. 悬空 req_id 跳过:task.req_id 指向不存在 requirement → 跳过 + 日志,无异常

mock 策略:
- 容器/runner:参照 test_files_api.py FakeWS 模式,直接 monkeypatch file_service.task_read_file
  (回传函数消费它的返回值),runner_registry 注册 + 清理
- 集成验证(send_message_stream → 副本落库):test_task_chat_stream.py 等已有先例,
  但 send_message_stream 涉及 Claude CLI 子进程 mock 复杂度高,降级为「同步函数被正确调用」
  的 monkeypatch 断言(asyncio.create_task 被触发 + sync_prd_from_container 被调用)
"""
import asyncio
import logging
import uuid

import pytest

from app.models.container import Container
from app.models.project import Project
from app.models.requirement import Requirement
from app.models.task import Task
from app.services import file_service, requirement_service
from app.services.runner_service import runner_registry


# ---------------------------------------------------------------------------
# fixture:构造 task + requirement + running container 最小集合
# ---------------------------------------------------------------------------
async def _seed_task_with_container(db_session, registered_user, task_id="task-prd-sync"):
    """构造 project + requirement + task + running container 最小依赖图"""
    project = Project(
        name="prd-sync-p", slug=f"ps-{uuid.uuid4().hex[:6]}",
        owner_id=registered_user["user_id"],
    )
    db_session.add(project)
    await db_session.flush()

    req = Requirement(
        req_id=f"req-{uuid.uuid4().hex[:8]}",
        project_id=project.project_id,
        title="PRD sync test",
        description="desc",
        req_branch="req-test",
        prd_file_path="docs/PRD.md",
        created_by=registered_user["user_id"],
    )
    db_session.add(req)
    await db_session.flush()

    task = Task(
        task_id=task_id,
        req_id=req.req_id,
        project_id=project.project_id,
        type="requirement",
        title="polish task",
        description="打磨 PRD",
        base_branch="master",
        work_branch="req-test",
        created_by=registered_user["user_id"],
    )
    db_session.add(task)
    await db_session.flush()

    container = Container(
        container_id=f"docker-{uuid.uuid4().hex[:10]}",
        task_id=task_id,
        runner_id=f"runner-{uuid.uuid4().hex[:6]}",
        project_id=project.project_id,
        status="running",
        exposed_ports=[],
    )
    db_session.add(container)
    await db_session.flush()

    runner_registry.register(container.runner_id, "worker", None, "10.0.0.99")
    return project, req, task, container


# ---------------------------------------------------------------------------
# test 1: 结算回传成功 — read_file 返回 PRD 文本 → prd_content 更新
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_sync_prd_success(client, db_session, registered_user, monkeypatch):
    """完成判据 1:容器在线 + read_file 返回非空 → prd_content 更新为容器内容"""
    _, req, task, container = await _seed_task_with_container(db_session, registered_user)

    mock_content = "# PRD Title\n\n## Background\nSome content here."

    async def fake_task_read_file(db, task_id, path):
        return {"path": path, "content": mock_content, "encoding": "utf-8"}

    monkeypatch.setattr(file_service, "task_read_file", fake_task_read_file)

    # 调用同步函数(Red:函数尚不存在)
    await requirement_service.sync_prd_from_container(db_session, task.task_id)

    # 回读验证:requirement.prd_content 已更新
    await db_session.refresh(req)
    assert req.prd_content == mock_content, (
        f"期望 prd_content='{mock_content}',实际 '{req.prd_content}'"
    )

    runner_registry.unregister(container.runner_id)


# ---------------------------------------------------------------------------
# test 2: 容器离线跳过 — 无 running 容器 → prd_content 不变,无异常
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_sync_prd_container_offline(client, db_session, registered_user, monkeypatch):
    """完成判据 2:无 running 容器 → 跳过更新,prd_content 保持旧值/NULL,无异常外抛"""
    _, req, task, container = await _seed_task_with_container(db_session, registered_user)
    # 预置旧值
    req.prd_content = "old content"
    await db_session.flush()

    # 将容器状态改为非 running(模拟离线)
    container.status = "stopped"
    await db_session.flush()

    read_called = False

    async def fake_task_read_file(db, task_id, path):
        nonlocal read_called
        read_called = True
        return {"path": path, "content": "should not reach", "encoding": "utf-8"}

    monkeypatch.setattr(file_service, "task_read_file", fake_task_read_file)

    # 不应抛异常
    await requirement_service.sync_prd_from_container(db_session, task.task_id)

    # 断言:read_file 未被调用,prd_content 保持旧值
    assert read_called is False, "容器离线时不应调用 read_file"
    await db_session.refresh(req)
    assert req.prd_content == "old content", f"旧值应保留,实际 '{req.prd_content}'"

    runner_registry.unregister(container.runner_id)


# ---------------------------------------------------------------------------
# test 3: 回读失败静默 — read_file 抛异常 → 主流程不受影响,日志含 [prd-sync] failed
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_sync_prd_read_failure_silent(client, db_session, registered_user, monkeypatch, caplog):
    """完成判据 3:read_file 抛异常 → 静默跳过,日志含 [prd-sync] failed,无外抛"""
    _, req, task, container = await _seed_task_with_container(db_session, registered_user)
    req.prd_content = "before error"
    await db_session.flush()

    async def fake_task_read_file(db, task_id, path):
        raise TimeoutError("Runner 响应超时")

    monkeypatch.setattr(file_service, "task_read_file", fake_task_read_file)

    # 捕获日志
    with caplog.at_level(logging.WARNING, logger="app.services.requirement_service"):
        # 不应抛异常
        await requirement_service.sync_prd_from_container(db_session, task.task_id)

    # 断言:日志含 [prd-sync] failed,prd_content 保持旧值
    log_messages = [r.message for r in caplog.records]
    assert any("[prd-sync] failed" in msg for msg in log_messages), (
        f"期望日志含 '[prd-sync] failed',实际日志: {log_messages}"
    )
    await db_session.refresh(req)
    assert req.prd_content == "before error", "回读失败时旧值应保留"

    runner_registry.unregister(container.runner_id)


# ---------------------------------------------------------------------------
# test 4: 空内容跳过 — read_file 返回空串 → prd_content 不被覆盖
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_sync_prd_empty_content_skipped(client, db_session, registered_user, monkeypatch):
    """完成判据 4:read_file 返回空串 → prd_content 不被覆盖(旧值保留)

    路径后置改造后:固定路径读空会进容器内发现器自愈,此处连 task_file_list 一并 mock
    (返回空列表)保证密闭——发现器全候选落空 → 路径与内容均不被改写。
    """
    _, req, task, container = await _seed_task_with_container(db_session, registered_user)
    req.prd_content = "existing content"
    await db_session.flush()

    async def fake_task_file_list(db, task_id, path):
        return []  # docs 无子目录,发现器仅剩根候选

    async def fake_task_read_file(db, task_id, path):
        return {"path": path, "content": "", "encoding": "utf-8"}

    monkeypatch.setattr(file_service, "task_file_list", fake_task_file_list)
    monkeypatch.setattr(file_service, "task_read_file", fake_task_read_file)

    await requirement_service.sync_prd_from_container(db_session, task.task_id)

    # 断言:空内容不覆盖旧值;prd_file_path 亦不被发现器改写
    await db_session.refresh(req)
    assert req.prd_content == "existing content", (
        f"空内容应跳过,旧值应保留;实际 '{req.prd_content}'"
    )
    assert req.prd_file_path == "docs/PRD.md", "发现器未命中时不应回写 prd_file_path"

    runner_registry.unregister(container.runner_id)


# ---------------------------------------------------------------------------
# test 5: 超长截断 — read_file 返回超过截断阈值 → 库中 ≤阈值 + warning 日志
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_sync_prd_oversized_truncated(client, db_session, registered_user, monkeypatch, caplog):
    """完成判据 5:read_file 返回超限内容 → 截断至阈值内 + warning 日志

    截断阈值 monkeypatch 为 64KB(生产规格仍为 16MB):真实发送 16MB 单包 UPDATE 会
    超过测试库 max_allowed_packet 触发 2013 断连——那是传输层环境限制,不是截断逻辑
    本身;截断行为(超限→截到阈值内→warning)用小阈值注入验证等价。生产上即便出现
    超限包失败,也会被 sync_prd_from_container 的 try/except 静默容错(PRD:回传失败
    不阻断主流程,下一时机自然重试)。
    """
    _, req, task, container = await _seed_task_with_container(db_session, registered_user)

    # 构造 1MB 内容 + 64KB 截断阈值(超出阈值 16 倍)
    oversized_content = "x" * (1024 * 1024)
    test_max = 64 * 1024
    monkeypatch.setattr(requirement_service, "_PRD_CONTENT_MAX_BYTES", test_max)

    async def fake_task_read_file(db, task_id, path):
        return {"path": path, "content": oversized_content, "encoding": "utf-8"}

    monkeypatch.setattr(file_service, "task_read_file", fake_task_read_file)

    with caplog.at_level(logging.WARNING, logger="app.services.requirement_service"):
        await requirement_service.sync_prd_from_container(db_session, task.task_id)

    # 断言:库中内容 ≤阈值 + 日志含 truncated/warning
    await db_session.refresh(req)
    assert req.prd_content is not None, "prd_content 应被写入"
    assert len(req.prd_content.encode("utf-8")) <= test_max, (
        f"期望截断至 ≤{test_max} 字节,实际 {len(req.prd_content.encode('utf-8'))} 字节"
    )

    log_messages = [r.message for r in caplog.records]
    assert any("truncat" in msg.lower() or "oversiz" in msg.lower() for msg in log_messages), (
        f"期望日志含 truncated/oversized 警告,实际: {log_messages}"
    )

    runner_registry.unregister(container.runner_id)


# ---------------------------------------------------------------------------
# test 6: 悬空 req_id 跳过 — task.req_id 指向不存在 requirement → 跳过 + 日志
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_sync_prd_dangling_req_id_skipped(client, db_session, registered_user, monkeypatch, caplog):
    """完成判据 6:task.req_id 指向不存在 requirement → 跳过 + 日志,无异常"""
    # 构造 task,但 req_id 指向不存在的 requirement
    project = Project(
        name="dangling-p", slug=f"dg-{uuid.uuid4().hex[:6]}",
        owner_id=registered_user["user_id"],
    )
    db_session.add(project)
    await db_session.flush()

    task = Task(
        task_id="task-dangling",
        req_id="req-nonexistent-000000",  # 不存在
        project_id=project.project_id,
        type="requirement",
        title="dangling task",
        description="desc",
        base_branch="master",
        work_branch="req-test",
        created_by=registered_user["user_id"],
    )
    db_session.add(task)
    await db_session.flush()

    container = Container(
        container_id=f"docker-{uuid.uuid4().hex[:10]}",
        task_id="task-dangling",
        runner_id=f"runner-{uuid.uuid4().hex[:6]}",
        project_id=project.project_id,
        status="running",
        exposed_ports=[],
    )
    db_session.add(container)
    await db_session.flush()
    runner_registry.register(container.runner_id, "worker", None, "10.0.0.100")

    read_called = False

    async def fake_task_read_file(db, task_id, path):
        nonlocal read_called
        read_called = True
        return {"path": path, "content": "should not reach", "encoding": "utf-8"}

    monkeypatch.setattr(file_service, "task_read_file", fake_task_read_file)

    with caplog.at_level(logging.WARNING, logger="app.services.requirement_service"):
        # 不应抛异常
        await requirement_service.sync_prd_from_container(db_session, task.task_id)

    # 断言:read_file 未被调用,日志含 requirement not found
    assert read_called is False, "悬空 req_id 时不应调用 read_file"
    log_messages = [r.message for r in caplog.records]
    assert any("requirement not found" in msg.lower() or "not found" in msg.lower() for msg in log_messages), (
        f"期望日志含 'requirement not found',实际: {log_messages}"
    )

    runner_registry.unregister(container.runner_id)


# ---------------------------------------------------------------------------
# test 7(降级):集成验证 — send_message_stream 结算区接线 + 后台包装两层正确
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_send_message_stream_triggers_sync(client, db_session, registered_user, monkeypatch):
    """集成验证(降级):send_message_stream 结算后触发 PRD 回传。

    完整 SSE 集成需 mock claude_service.run_prompt_stream 全链(文件引用解析/模型解析/
    claude 会话/runner 流通道),成本远超本判据意图,降级为两段等价验证:
    1) 静态:send_message_stream 函数源码含 fire-and-forget 接线(asyncio.create_task +
       _sync_prd_background(task.task_id)),且带 type=="requirement" 守卫;
    2) 动态:_sync_prd_background(实现内局部 import 的目标)确实把 task_id 接到
       sync_prd_from_container(monkeypatch spy)——两层接线闭环。

    此决策记入测试文档:.scratch/R2/qa-red-tests.md
    """
    import inspect

    from app.services import task_service

    # 1) 静态断言:结算区接线存在(插入点回归保护)
    src = inspect.getsource(task_service.send_message_stream)
    assert "_sync_prd_background" in src, "send_message_stream 应接线 _sync_prd_background"
    assert "asyncio.create_task" in src, "回传应为 fire-and-forget(create_task,不阻塞收尾)"
    assert 'task.type == "requirement"' in src, "接线应带 requirement 类型守卫"

    # 2) 动态断言:后台包装 → 同步函数接线
    _, req, task, container = await _seed_task_with_container(db_session, registered_user)

    called = {}

    async def spy_sync_prd(db, task_id):
        called["task_id"] = task_id

    monkeypatch.setattr(requirement_service, "sync_prd_from_container", spy_sync_prd)

    await asyncio.wait_for(
        requirement_service._sync_prd_background(task.task_id), timeout=5.0
    )
    assert called.get("task_id") == task.task_id, (
        f"_sync_prd_background 应把 task_id='{task.task_id}' 接到 sync_prd_from_container,"
        f"实际 {called}"
    )

    runner_registry.unregister(container.runner_id)


# ---------------------------------------------------------------------------
# 路径后置自愈(实际路径发现 + prd_file_path 回写)+ GitLab 兜底 + 终态钩子
# ---------------------------------------------------------------------------
async def _seed_discoverable_docs(
    fake_file_list, fake_task_read_file, monkeypatch, short_id: str, discovered_dir: str,
    discovered_content: str,
):
    """发现器测试公共 mock:docs 目录清单 + 逐路径 read(命中 discovered_dir 才有内容)"""
    monkeypatch.setattr(file_service, "task_file_list", fake_file_list)

    async def _read(db, task_id, path):
        if path.endswith(f"{discovered_dir}/PRD.md"):
            return {"path": path, "content": discovered_content, "encoding": "utf-8"}
        return {"path": path, "content": "", "encoding": "utf-8"}

    monkeypatch.setattr(file_service, "task_read_file", _read)


@pytest.mark.asyncio
async def test_sync_prd_empty_path_discovers_and_heals(client, db_session, registered_user, monkeypatch):
    """路径后置自愈①:prd_file_path 为空(打磨启动新常态)→ 发现器命中实际路径 → 回写 + 回传"""
    _, req, task, container = await _seed_task_with_container(
        db_session, registered_user, task_id="task-heal01"
    )
    req.prd_file_path = ""
    req.prd_content = None
    await db_session.flush()

    short_id = task.task_id[:8]  # "task-hea"
    discovered_dir = f"20261008_某需求_{short_id}"
    discovered_content = "# discovered PRD"

    async def fake_file_list(db, task_id, path):
        assert path == "/workspace/main/docs"
        return [{"path": discovered_dir, "type": "dir", "size": 0, "mtime": 0.0}]

    await _seed_discoverable_docs(
        fake_file_list, None, monkeypatch, short_id, discovered_dir, discovered_content
    )

    await requirement_service.sync_prd_from_container(db_session, task.task_id)

    await db_session.refresh(req)
    assert req.prd_file_path == f"docs/{discovered_dir}/PRD.md", (
        f"实际路径应回写为关联键,实际 '{req.prd_file_path}'"
    )
    assert req.prd_content == discovered_content, "回传副本应为发现路径的内容"

    runner_registry.unregister(container.runner_id)


@pytest.mark.asyncio
async def test_sync_prd_stale_path_healed_overwrite(client, db_session, registered_user, monkeypatch):
    """路径后置自愈②:存量预生成路径读空(实际写到别处)→ 发现器命中 → 覆盖回写"""
    _, req, task, container = await _seed_task_with_container(
        db_session, registered_user, task_id="task-stale1"
    )
    req.prd_file_path = "docs/stale_expected/PRD.md"  # 存量预生成,实际未写这里
    await db_session.flush()

    short_id = task.task_id[:8]
    discovered_dir = f"docs_real_{short_id}"
    discovered_content = "# real PRD"

    async def fake_file_list(db, task_id, path):
        return [{"path": discovered_dir, "type": "dir", "size": 0, "mtime": 0.0}]

    await _seed_discoverable_docs(
        fake_file_list, None, monkeypatch, short_id, discovered_dir, discovered_content
    )

    await requirement_service.sync_prd_from_container(db_session, task.task_id)

    await db_session.refresh(req)
    assert req.prd_file_path == f"docs/{discovered_dir}/PRD.md", "失效路径应被实际路径覆盖"
    assert req.prd_content == discovered_content

    runner_registry.unregister(container.runner_id)


@pytest.mark.asyncio
async def test_discover_prefers_task_short_id_dir(client, db_session, registered_user, monkeypatch):
    """路径后置自愈③:多个候选目录时,目录名含任务短 id(task_id[:8])的优先命中"""
    _, req, task, container = await _seed_task_with_container(
        db_session, registered_user, task_id="task-pref1"
    )
    req.prd_file_path = ""
    await db_session.flush()

    short_id = task.task_id[:8]
    preferred_dir = f"20261008_x_{short_id}"
    plain_dir = "20261001_other_task"

    async def fake_file_list(db, task_id, path):
        # 故意让非优先目录排前,验证候选择优与列表顺序无关
        return [
            {"path": plain_dir, "type": "dir", "size": 0, "mtime": 1.0},
            {"path": preferred_dir, "type": "dir", "size": 0, "mtime": 2.0},
        ]

    read_paths: list[str] = []

    async def fake_read(db, task_id, path):
        read_paths.append(path)
        return {"path": path, "content": f"# content of {path}", "encoding": "utf-8"}

    monkeypatch.setattr(file_service, "task_file_list", fake_file_list)
    monkeypatch.setattr(file_service, "task_read_file", fake_read)

    await requirement_service.sync_prd_from_container(db_session, task.task_id)

    assert read_paths, "发现器应至少读一个候选"
    assert short_id in read_paths[0], (
        f"首个回读候选应为含任务短 id 的目录,实际 read 顺序: {read_paths}"
    )
    await db_session.refresh(req)
    assert req.prd_file_path == f"docs/{preferred_dir}/PRD.md"

    runner_registry.unregister(container.runner_id)


@pytest.mark.asyncio
async def test_prd_view_gitlab_fallback_heals(client, db_session, registered_user, monkeypatch):
    """读侧第③层 GitLab 兜底:容器已销毁 → 直取 404 → tree 发现命中 → 回写路径 + ('gitlab')"""
    import base64

    from app.core.response import BizError
    from app.services import gitlab_service

    _, req, task, container = await _seed_task_with_container(
        db_session, registered_user, task_id="task-gl01"
    )
    # 容器已销毁(第②层不可用)+ 副本为空 + 存量路径已失效
    container.status = "destroyed"
    req.prd_content = None
    req.prd_file_path = "docs/stale/PRD.md"
    req.polish_task_id = task.task_id
    await db_session.flush()

    short_id = task.task_id[:8]
    discovered_rel = f"docs/20261008_gl_{short_id}/PRD.md"
    gitlab_content = "# PRD from gitlab"

    async def fake_gitlab_ctx(db, project):
        return ("https://gitlab.example", "bot-token", type("R", (), {"gitlab_repo_id": 1})())

    async def fake_bot_get_file(bot_token, gitlab_url, repo_id, ref, path):
        if path == discovered_rel:
            return {
                "content": base64.b64encode(gitlab_content.encode("utf-8")).decode("ascii"),
                "size": len(gitlab_content),
            }
        raise BizError(404, "文件不存在", status_code=404)  # 直取/根候选/其余候选 404

    async def fake_bot_get_tree(bot_token, gitlab_url, repo_id, ref, path, recursive=False):
        assert path == "docs"
        return [{"path": f"docs/20261008_gl_{short_id}", "type": "tree"}]

    monkeypatch.setattr(file_service, "_gitlab_ctx", fake_gitlab_ctx)
    monkeypatch.setattr(gitlab_service, "bot_get_file", fake_bot_get_file)
    monkeypatch.setattr(gitlab_service, "bot_get_tree", fake_bot_get_tree)

    content, source = await requirement_service.get_prd_content_with_fallback(db_session, req)

    assert source == "gitlab", f"应命中 GitLab 兜底层,实际 source={source}"
    assert content == gitlab_content
    await db_session.refresh(req)
    assert req.prd_file_path == discovered_rel, "GitLab 兜底命中也应回写实际路径"
    assert req.prd_content == gitlab_content, "GitLab 命中应回填平台副本(下次直走 db 层)"

    runner_registry.unregister(container.runner_id)


@pytest.mark.asyncio
async def test_finish_task_syncs_prd_for_requirement_only(client, db_session, registered_user, monkeypatch):
    """终态钩子:finish_task 收尾时 type=requirement 触发 PRD 回传(含路径自愈);其他类型不触发"""
    from sqlalchemy import select as sa_select

    from app.models.user import User
    from app.services import task_service

    _, req, task, container = await _seed_task_with_container(
        db_session, registered_user, task_id="task-fin01"
    )
    # dev 任务(同项目;req_id 列不可空,占位——守卫是 type != "requirement")
    dev_task = Task(
        task_id="task-fin-dev", req_id=req.req_id, project_id=task.project_id,
        type="dev", title="dev task", description="d",
        base_branch="master", work_branch="dev-x", created_by=registered_user["user_id"],
    )
    db_session.add(dev_task)
    await db_session.flush()
    dev_container = Container(
        container_id=f"docker-{uuid.uuid4().hex[:10]}", task_id=dev_task.task_id,
        runner_id=f"runner-{uuid.uuid4().hex[:6]}", project_id=task.project_id,
        status="running", exposed_ports=[],
    )
    db_session.add(dev_container)
    await db_session.flush()

    operator = (await db_session.execute(
        sa_select(User).where(User.user_id == registered_user["user_id"])
    )).scalar_one()

    # R37.F8(BUG-082)新契约:done 收尾要求 Runner 在线 + 提交凭据可用,否则显式
    # 报错。本用例关注 PRD 回传钩子,补齐桩:Runner 假在线 + bot token + request_stop
    # 假收容(绕开 ws=None 连接的 AttributeError 原注销方案)
    monkeypatch.setattr(runner_registry, "get", lambda rid: object())

    async def fake_bot_config(db):
        return ("http://gitlab.example.com", "bot-token-prdsync", None)

    monkeypatch.setattr(
        "app.services.platform_settings_service.get_gitlab_bot_config", fake_bot_config
    )

    async def fake_request_stop(db, c):
        c.status = "destroyed"
        from datetime import datetime, timezone as _tz

        c.destroyed_at = datetime.now(_tz.utc).replace(tzinfo=None)
        await db.flush()

    from app.services import container_service as _container_service
    from app.services import runner_service as _runner_service

    monkeypatch.setattr(_container_service, "request_stop", fake_request_stop)

    async def fake_request_runner(*a, **kw):
        return {"ok": True}

    monkeypatch.setattr(_runner_service, "request_runner", fake_request_runner)

    called: list[str] = []

    async def spy_sync(db, tid):
        called.append(tid)

    monkeypatch.setattr(requirement_service, "sync_prd_from_container", spy_sync)

    await task_service.finish_task(db_session, task, operator, status="done")
    await task_service.finish_task(db_session, dev_task, operator, status="done")

    assert called == [task.task_id], (
        f"仅 requirement 任务应触发回传,实际 {called}"
    )
    await db_session.refresh(task)
    assert task.status == "done"


@pytest.mark.asyncio
async def test_start_polish_no_longer_pregenerates_path():
    """路径后置回归:start_polish 不再预生成 prd_file_path(回写是唯一写入来源)"""
    import inspect

    src = inspect.getsource(requirement_service.start_polish)
    assert "build_prd_path" not in src, (
        "start_polish 不应再调用 build_prd_path 预生成路径"
    )
    assert "req.prd_file_path" not in src, (
        "start_polish 不应有 req.prd_file_path 赋值(由打磨完成后实际路径回写)"
    )

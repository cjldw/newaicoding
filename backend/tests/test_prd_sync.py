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
    """完成判据 4:read_file 返回空串 → prd_content 不被覆盖(旧值保留)"""
    _, req, task, container = await _seed_task_with_container(db_session, registered_user)
    req.prd_content = "existing content"
    await db_session.flush()

    async def fake_task_read_file(db, task_id, path):
        return {"path": path, "content": "", "encoding": "utf-8"}

    monkeypatch.setattr(file_service, "task_read_file", fake_task_read_file)

    await requirement_service.sync_prd_from_container(db_session, task.task_id)

    # 断言:空内容不覆盖旧值
    await db_session.refresh(req)
    assert req.prd_content == "existing content", (
        f"空内容应跳过,旧值应保留;实际 '{req.prd_content}'"
    )

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

"""
R11 文件服务测试(平台侧)
==========================
- 项目模式文件树/内容(GitLab mock)
- 任务模式读/写文件(请求-响应 fake)
- 变更清单按仓库分组 + total(Q27)
- request_runner / resolve_request 关联机制
"""
import asyncio
import uuid

import httpx
import pytest

from app.models.project import Project, ProjectRepo
from app.services import file_service, runner_service
from app.services.runner_service import runner_registry


async def _setup_project_with_repo(db_session, registered_user):
    from tests.test_projects_api import _seed_gitlab_settings

    await _seed_gitlab_settings(db_session)
    project = Project(name="fp", slug=f"fp-{uuid.uuid4().hex[:6]}", owner_id=registered_user["user_id"])
    db_session.add(project)
    await db_session.flush()
    repo = ProjectRepo(
        project_id=project.project_id, role="main",
        gitlab_repo_url="https://gitlab.example.com/g/main.git",
        gitlab_repo_id=321, gitlab_bind_type="manual", created_by=registered_user["user_id"],
    )
    db_session.add(repo)
    await db_session.flush()
    return project, repo


@pytest.mark.asyncio
async def test_project_mode_file_tree(client, auth_headers, db_session, registered_user):
    """项目模式文件树(GitLab mock tree 接口)"""
    project, repo = await _setup_project_with_repo(db_session, registered_user)

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET" and "/repository/tree" in str(request.url):
            return httpx.Response(200, json=[
                {"path": "src", "type": "tree"},
                {"path": "src/main.py", "type": "blob", "size": 1234},
            ])
        return httpx.Response(404)

    with httpx.MockTransport(handler):
        items = await file_service.project_file_tree(db_session, project, "master", "")
    assert items[0]["type"] == "tree"
    assert items[1]["path"] == "src/main.py"
    assert items[1]["size"] == 1234


@pytest.mark.asyncio
async def test_request_runner_roundtrip():
    """request_runner ↔ resolve_request 关联机制"""
    from app.services.runner_service import RunnerConnection

    sent: list[dict] = []

    class FakeWS:
        async def send_json(self, payload):
            sent.append(payload)

    conn = RunnerConnection(runner_id="rr", websocket=FakeWS(), host="h")
    loop = asyncio.get_running_loop()

    async def responder():
        await asyncio.sleep(0.01)
        req_id = sent[0]["req_id"]
        assert runner_service.resolve_request(req_id, True, data={"items": [1, 2]})

    task = loop.create_task(responder())
    result = await runner_service.request_runner(conn, {"type": "file_list", "path": "/w"}, timeout=2)
    await task
    assert result["ok"] is True and result["data"]["items"] == [1, 2]

    # 失败结算
    async def fail_responder():
        await asyncio.sleep(0.01)
        runner_service.resolve_request(sent[-1]["req_id"], False, error="boom")

    task = loop.create_task(fail_responder())
    result = await runner_service.request_runner(conn, {"type": "read_file"}, timeout=2)
    await task
    assert result["ok"] is False and result["error"] == "boom"


@pytest.mark.asyncio
async def test_task_mode_read_write_file(client, auth_headers, db_session, registered_user, monkeypatch):
    """任务模式读写(经 Runner 请求-响应 fake)"""
    project = Project(name="ft", slug=f"ft-{uuid.uuid4().hex[:6]}", owner_id=registered_user["user_id"])
    db_session.add(project)
    await db_session.flush()
    from app.models.container import Container

    container = Container(
        container_id=f"docker-{uuid.uuid4().hex[:10]}",
        task_id="task-fw", runner_id="runner-fw", project_id=project.project_id,
        status="running", exposed_ports=[],
    )
    db_session.add(container)
    await db_session.flush()
    runner_registry.register("runner-fw", "worker", None, "10.0.0.5")

    async def fake_request(db, container, message, timeout=15.0):
        if message["type"] == "read_file":
            return {"content": "print('hello')"}  # 契约:直接返回 data(已解包)
        if message["type"] == "write_file":
            writes.append(message)
            return {}
        raise AssertionError(f"unexpected {message['type']}")

    writes: list = []
    monkeypatch.setattr(file_service, "_request_container", fake_request)

    content = await file_service.task_read_file(db_session, "task-fw", "/workspace/main/src/main.py")
    assert content["content"] == "print('hello')"

    await file_service.task_write_file(db_session, "task-fw", "/workspace/main/src/main.py", "x = 1")
    assert writes[0]["content"] == "x = 1"
    runner_registry.unregister("runner-fw")


@pytest.mark.asyncio
async def test_task_mode_changes_grouped_by_repo(client, auth_headers, db_session, registered_user, monkeypatch):
    """Q27:变更清单按仓库分组 + total 正确(含未 commit 差异口径)"""
    project = Project(name="fg", slug=f"fg-{uuid.uuid4().hex[:6]}", owner_id=registered_user["user_id"])
    db_session.add(project)
    await db_session.flush()
    for role, repo_id in (("main", 1), ("test", 2)):
        db_session.add(ProjectRepo(
            project_id=project.project_id, role=role,
            gitlab_repo_url=f"https://gitlab.example.com/g/{role}.git",
            gitlab_repo_id=repo_id, gitlab_bind_type="manual",
            created_by=registered_user["user_id"],
        ))
    await db_session.flush()
    from app.models.container import Container

    container = Container(
        container_id=f"docker-{uuid.uuid4().hex[:10]}",
        task_id="task-cg", runner_id="runner-cg", project_id=project.project_id,
        status="running", exposed_ports=[],
    )
    db_session.add(container)
    await db_session.flush()
    runner_registry.register("runner-cg", "worker", None, "10.0.0.6")

    async def fake_request(db, container, message, timeout=15.0):
        if message["type"] != "git_changes":
            raise AssertionError("unexpected")
        if message["repo_path"] == "/workspace/main":
            return {"files": [
                {"path": "src/main.py", "status": "M", "additions": 12, "deletions": 3},
                {"path": "src/new.py", "status": "A", "additions": 40, "deletions": 0},
            ]}
        return {"files": [
            {"path": "tests/t.py", "status": "D", "additions": 0, "deletions": 5},
        ]}

    monkeypatch.setattr(file_service, "_request_container", fake_request)

    data = await file_service.task_git_changes(db_session, "task-cg")
    assert data["total"] == 3
    roles = {g["repo_role"]: g for g in data["repos"]}
    assert len(roles["main"]["files"]) == 2
    assert roles["test"]["files"][0]["status"] == "D"
    runner_registry.unregister("runner-cg")


@pytest.mark.asyncio
async def test_project_mode_file_content_endpoint(client, auth_headers, db_session, registered_user):
    """项目模式文件内容端点(经 GitLab mock;base64 → utf-8)"""
    project, repo = await _setup_project_with_repo(db_session, registered_user)
    import base64

    def handler(request: httpx.Request) -> httpx.Response:
        if "/repository/files/" in str(request.url):
            return httpx.Response(200, json={
                "file_name": "main.py", "size": 14,
                "content": base64.b64encode(b"print('hello')").decode(),
                "encoding": "base64",
            })
        return httpx.Response(404)

    with httpx.MockTransport(handler):
        resp = await client.get(
            f"/api/projects/{project.project_id}/files/content",
            headers=auth_headers,
            params={"branch": "master", "path": "src/main.py"},
        )
    data = resp.json()
    assert data["code"] == 0
    assert data["data"]["content"] == "print('hello')"
    assert data["data"]["encoding"] == "utf-8"

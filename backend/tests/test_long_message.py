"""
R5.F5(BUG-076) Red 测试:长消息发送失败(后端侧)
================================================
覆盖 R5.F5 测试验证逻辑中后端可自动化的 3 条:

① ORM 列类型断言:TaskMessage.content 应为 MEDIUMTEXT(16MB),当前为 TEXT(64KB)
② 超长回复落库不截断:写入 100KB 内容,读回长度一致(当前 TEXT 静默截断)
③ SendMessageRequest.content 加 max_length 校验:超长请求返回 422(当前无限制)

根因引用:
- P1:task.py:96 `content = Column(Text, ...)` → 应改 MEDIUMTEXT
- P2:api/tasks.py:597 `content: str = Field(min_length=1)` → 应加 max_length=200000
"""
import uuid

import pytest
from sqlalchemy import inspect, text
from sqlalchemy.dialects.mysql import MEDIUMTEXT

from app.models.task import TaskMessage


# ---------------------------------------------------------------------------
# ① ORM 列类型断言:TaskMessage.content 应为 MEDIUMTEXT
# ---------------------------------------------------------------------------
def test_task_message_content_column_is_mediumtext():
    """
    Red 断言:TaskMessage.content 列类型应为 MEDIUMTEXT(16MB 上限)。
    当前实现为 Text(MySQL TEXT, 64KB 上限)→ 断言失败。
    """
    # 通过 SQLAlchemy inspection 获取列类型
    mapper = inspect(TaskMessage)
    content_col = mapper.columns["content"]
    col_type = content_col.type

    # 断言类型是 MEDIUMTEXT(不是 Text)
    assert isinstance(col_type, MEDIUMTEXT), (
        f"BUG-076 P1:TaskMessage.content 应为 MEDIUMTEXT(16MB),实际为 {type(col_type).__name__}"
        f"(TEXT 只有 64KB,长 AI 回复会被静默截断)"
    )


# ---------------------------------------------------------------------------
# ② 超长回复落库不截断:写入 100KB,读回长度一致
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_long_content_write_read_roundtrip(db_session):
    """
    Red 断言:写入 100KB 内容到 TaskMessage.content,读回长度应一致。
    当前 TEXT 列在 sql_mode=IGNORE_SPACE(非严格)下静默截断到 64KB → 读回变短。
    """
    # 构造 100KB 中文内容(每字符 3 字节 UTF-8;每轮 54 字节 × 2000 = 108KB)
    long_content = "这是一段超长 AI 回复内容,用于验证 MEDIUMTEXT 列能否完整存储。" * 2000
    content_bytes = len(long_content.encode("utf-8"))
    assert content_bytes > 100 * 1024, f"测试内容应 >100KB,实际 {content_bytes} 字节"

    # 先验证列类型(若为 TEXT,直接标记 Red;若已改 MEDIUMTEXT,继续测 roundtrip)
    mapper = inspect(TaskMessage)
    col_type = mapper.columns["content"].type
    if not isinstance(col_type, MEDIUMTEXT):
        pytest.fail(
            f"BUG-076 P1:content 列仍为 {type(col_type).__name__}(TEXT),无法存储 >64KB;"
            f"需改为 MEDIUMTEXT 后再测 roundtrip"
        )

    # 写入一条 TaskMessage(需要 task_id;此处用假 UUID,不依赖外键约束)
    msg_id = str(uuid.uuid4())
    task_id = str(uuid.uuid4())
    msg = TaskMessage(
        message_id=msg_id,
        task_id=task_id,
        role="assistant",
        content=long_content,
        tokens_in=100,
        tokens_out=200,
    )
    db_session.add(msg)
    await db_session.flush()

    # 读回
    result = await db_session.execute(
        TaskMessage.__table__.select().where(TaskMessage.message_id == msg_id)
    )
    row = result.first()
    assert row is not None, "应能读回刚写入的消息"

    read_content = row.content
    read_len = len(read_content.encode("utf-8"))

    # 断言:读回长度 == 写入长度(不截断)
    assert read_len == content_bytes, (
        f"BUG-076 P1:长内容落库被截断!写入 {content_bytes} 字节,读回 {read_len} 字节"
        f"(差异 {content_bytes - read_len} 字节)"
    )
    assert read_content == long_content, "读回内容应与写入完全一致"


# ---------------------------------------------------------------------------
# ③ SendMessageRequest.content 加 max_length 校验:超长请求返回 422
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_send_message_rejects_oversized_content(client, registered_user):
    """
    Red 断言:SendMessageRequest.content 超过 max_length(默认 200000 字符)
    应返回 422 校验错误(非 500 / 401 / 404)。当前无 max_length → 断言失败。

    注:需先登录获取 token,否则 endpoint 返回 401 掩盖 Pydantic 校验。
    """
    # 登录获取 token
    login_resp = await client.post("/api/auth/login", json={
        "phone": registered_user["phone"],
        "password": registered_user["password"],
    })
    token = login_resp.json()["data"]["access_token"]
    client.headers["Authorization"] = f"Bearer {token}"

    # 构造 >200000 字符的内容
    oversized_content = "x" * 200001

    # POST 到一个不存在的 task_id(预期:先过 Pydantic 校验,再查 task)
    # 若 Pydantic 校验通过(无 max_length),会进入业务逻辑报 task 不存在(404/其他)
    # 若有 max_length,会直接 422 + 校验错
    fake_task_id = str(uuid.uuid4())
    resp = await client.post(
        f"/api/tasks/{fake_task_id}/messages",
        json={"content": oversized_content},
    )

    # 断言:返回 422(校验错)且错误信息包含 max_length 相关提示
    assert resp.status_code == 422, (
        f"BUG-076 P2:超长 content 应返回 422 校验错,实际返回 {resp.status_code}。"
        f"SendMessageRequest.content 缺少 max_length 校验(应 ≤200000 字符)"
    )

    # 进一步校验:错误信息应提及 max_length / 长度限制
    error_body = resp.json()
    error_str = str(error_body).lower()
    assert "max_length" in error_str or "长度" in error_str or "length" in error_str or "too long" in error_str, (
        f"BUG-076 P2:422 错误信息应提示 max_length / 长度限制,实际:{error_body}"
    )


# ---------------------------------------------------------------------------
# 补充:Pydantic 模型直接校验(更轻量,不依赖 endpoint 路由)
# ---------------------------------------------------------------------------
def test_send_message_request_model_max_length():
    """
    Red 断言(补充):SendMessageRequest Pydantic 模型本身应配 max_length。
    直接实例化 >200000 字符的 content,应抛 ValidationError。
    当前无 max_length → 不会抛错 → 断言失败。
    """
    from pydantic import ValidationError
    from app.api.tasks import SendMessageRequest

    oversized_content = "y" * 200001

    # 尝试实例化
    with pytest.raises(ValidationError) as exc_info:
        SendMessageRequest(content=oversized_content)

    # 校验错误应涉及 max_length
    error_str = str(exc_info.value).lower()
    assert "max_length" in error_str or "length" in error_str or "too long" in error_str, (
        f"BUG-076 P2:ValidationError 应提示 max_length,实际:{exc_info.value}"
    )

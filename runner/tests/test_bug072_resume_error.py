"""R5.F3 三修(BUG-072):--resume 不存在的会话时 CLI 输出单行 error-result
(is_error=true,errors=["No conversation found..."],result 字段空)——非零行,
原「零行降级」判定失效。本用例锁定:返回体 resume_error=True 置位 + errors 折入
stderr_tail,供 main.py R32.F8 降级条件(lines==0 or resume_error)与后端会话自清。
"""
import json

from test_r34_confirm_bridge import FakeContainer, FakeExecApi, _manager


def test_resume_error_result_sets_resume_error_flag():
    err_line = json.dumps({
        "type": "result", "subtype": "error_during_execution",
        "duration_ms": 0, "is_error": True, "num_turns": 0,
        "session_id": "54528b7c-14a1-478c-86cb-b019195ada1c",
        "errors": ["No conversation found with session ID: 54528b7c-14a1-478c-86cb-b019195ada1c"],
    }) + "\n"
    api = FakeExecApi(err_line.encode())
    mgr = _manager(FakeContainer(api))

    data = mgr.claude_prompt_stream("c1", "hi", session_id="54528b7c", resume=True)

    assert data["lines"] == 1          # 非零行——原零行降级判定漏掉的形态
    assert data["result"] == ""        # result 字段空
    assert data["resume_error"] is True
    assert "No conversation found" in data["stderr_tail"]


def test_normal_result_not_marked_resume_error():
    ok_line = json.dumps({
        "type": "result", "subtype": "success", "is_error": False,
        "result": "pong", "usage": {"input_tokens": 1, "output_tokens": 1},
    }) + "\n"
    api = FakeExecApi(ok_line.encode())
    mgr = _manager(FakeContainer(api))

    data = mgr.claude_prompt_stream("c1", "hi", session_id="s1", resume=True)

    assert data["result"] == "pong"
    assert data["resume_error"] is False

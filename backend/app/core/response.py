"""统一响应格式与全局异常处理"""

from typing import Any, Optional

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
import logging

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 业务异常
# ---------------------------------------------------------------------------

class BizError(Exception):
    """业务异常，携带错误码和提示信息"""

    def __init__(self, code: int, message: str, status_code: int = 200, data: Any = None):
        self.code = code
        self.message = message
        self.status_code = status_code
        self.data = data
        super().__init__(message)


# ---------------------------------------------------------------------------
# 错误码常量 (R1 定义)
# ---------------------------------------------------------------------------

class ErrCode:
    """业务错误码"""
    PHONE_EXISTS = 1001          # 手机号已注册
    WEAK_PASSWORD = 1003         # 密码强度不足
    WRONG_CREDENTIALS = 1005     # 手机号或密码错误
    ACCOUNT_LOCKED = 1006        # 账号已锁定(密码错误次数过多)
    ACCOUNT_DISABLED = 1007      # 账号已禁用
    INVALID_REFRESH = 1008       # refresh token 无效
    GITLAB_TOKEN_INVALID = 1012  # GitLab token 无效
    GITLAB_SCOPE_INSUFFICIENT = 1013  # GitLab token scope 不足

    # R2 项目管理
    BOT_TOKEN_NOT_CONFIGURED = 2001   # 平台 GitLab bot token 未配置
    REPO_URL_INVALID = 2002           # GitLab repo URL 无效或 bot 无权限
    PROJECT_LIMIT_EXCEEDED = 2003     # 单用户项目数超限(>50)
    REPO_ALREADY_BOUND = 2004         # 同一 repo 已绑定到该项目
    REPO_LIMIT_EXCEEDED = 2005        # 单项目绑定 repo 数超限(>10)
    MAIN_REPO_UNBINDABLE = 2006       # main repo 不可解绑
    PLATFORM_SETTING_INVALID = 2007   # 非法配置值(域名格式非法/数值越界/未知配置键)

    # R12 项目成员
    INVITE_USER_NOT_FOUND = 12001  # 用户不存在(手机号未注册)
    ALREADY_MEMBER = 12002         # 用户已是项目成员
    MEMBER_LIMIT_EXCEEDED = 12003  # 单项目成员数超限(>50)
    LAST_OWNER_UNREMOVABLE = 12004 # 不可移除/降级最后一个 owner
    TRANSFER_NON_MEMBER = 12005    # owner 转让给非成员

    # R13 模型接入
    LLM_CONNECT_FAILED = 13001     # base_url 不通/超时/401/404(连通性测试失败)
    CONFIG_NAME_DUPLICATE = 13002  # 同项目下配置名重复
    CONFIG_DEFAULT_EXISTS = 13003  # 同项目已有 default 配置
    CONFIG_DEFAULT_UNDELETABLE = 13004  # 不可删除 default 配置

    # R17 MCP / Skills
    MCP_JSON_INVALID = 17001       # MCP 配置 JSON 格式错误(message 携带行号)
    SKILL_ALREADY_INSTALLED = 17002  # 已安装过该 Skill
    SKILL_FORMAT_INVALID = 17003   # Skill .md 格式错误(缺 frontmatter name/description)

    # R8 容器
    USER_CONTAINER_LIMIT = 8001     # 单用户同时运行容器超限(≤5)
    PLATFORM_CONTAINER_LIMIT = 8002 # 平台总容器数超限
    NO_RUNNER_AVAILABLE = 8003      # 无可用 Runner(离线/角色不匹配)

    # R9 终端
    TERMINAL_UNAVAILABLE = 9001    # 终端不可用(Runner 离线/容器非 running)
    TERMINAL_NOT_FOUND = 9002      # 会话不存在或无权访问

    # R7 发布
    DEPLOY_PORT_CONFLICT = 7001     # deploy_port 全平台唯一,冲突拒绝
    DEPLOY_LIMIT_EXCEEDED = 7002    # 单项目同时部署数超限(>5)
    DEPLOY_HOST_INVALID = 7003      # deploy_host 非法/冲突

    # R4 任务
    TASK_REQ_STATUS_INVALID = 4001   # 需求状态不合法(如 dev 要求 approved)
    TASK_NO_GITLAB_TOKEN = 4002      # 用户未绑定 GitLab token
    TASK_CONCURRENT_LIMIT = 4003     # 单项目并发 running 任务超限(>3)
    TASK_FILE_TOO_LARGE = 4004       # 单文件超限(>50MB)
    TASK_UPLOAD_COUNT_LIMIT = 4005   # 单次上传文件数超限(>10)
    TASK_UPLOAD_TOTAL_LIMIT = 4006   # 单任务累计上传超限(>200MB)

    # R3 需求
    POLISH_ALREADY_RUNNING = 3001  # 已有打磨任务进行中
    NOT_IN_POLISHING = 3002        # 需求状态不是 polishing

    # R20 知识库空间
    KB_IMPORT_READONLY = 20002     # repo_import 只读(写操作一律 403,含超管)

    # R15 网关
    DEPLOY_HOST_CONFLICT = 15001   # deploy_host 全平台唯一,冲突拒绝

    # R16 Runner
    RUNNER_HAS_CONTAINERS = 16001  # Runner 上有运行中容器,不可删除

    # 权限
    NOT_SUPERADMIN = 19002            # 非平台超级管理员
    NO_PROJECT_PERMISSION = 1901      # 无项目操作权限(非 owner)


# ---------------------------------------------------------------------------
# 统一响应构造
# ---------------------------------------------------------------------------

def success(data: Any = None, message: str = "ok") -> dict:
    """成功响应"""
    return {"code": 0, "data": data, "message": message}


def error(code: int, message: str, data: Any = None) -> dict:
    """错误响应"""
    return {"code": code, "data": data, "message": message}


# ---------------------------------------------------------------------------
# 全局异常处理注册
# ---------------------------------------------------------------------------

def register_exception_handlers(app: FastAPI):
    """注册全局异常处理器"""

    @app.exception_handler(BizError)
    async def biz_error_handler(request: Request, exc: BizError):
        return JSONResponse(
            status_code=exc.status_code,
            content=error(exc.code, exc.message, exc.data),
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(request: Request, exc: RequestValidationError):
        # 提取第一个校验错误信息
        errors = exc.errors()
        msg = errors[0]["msg"] if errors else "请求参数校验失败"
        # 去掉 "Value error, " 前缀（pydantic v2 自定义校验器抛出的）
        if msg.startswith("Value error, "):
            msg = msg[len("Value error, "):]
        return JSONResponse(
            status_code=422,
            content=error(422, msg),
        )

    @app.exception_handler(Exception)
    async def unhandled_error_handler(request: Request, exc: Exception):
        logger.exception("Unhandled exception: %s", exc)
        return JSONResponse(
            status_code=500,
            content=error(500, "服务器内部错误"),
        )

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
    REPO_URL_INVALID = 2002           # 仓库地址格式无效(R27 语义收窄:仅 parse_repo_path 解析失败)
    PROJECT_LIMIT_EXCEEDED = 2003     # 单用户项目数超限(>50)
    REPO_ALREADY_BOUND = 2004         # 同一 repo 已绑定到该项目
    REPO_LIMIT_EXCEEDED = 2005        # 单项目绑定 repo 数超限(>10)
    MAIN_REPO_UNBINDABLE = 2006       # main repo 不可解绑
    PLATFORM_SETTING_INVALID = 2007   # 非法配置值(域名格式非法/数值越界/未知配置键)
    PLATFORM_LLM_CONNECT_FAILED = 2008  # 平台默认 LLM 保存连通性测试失败(R23;区别于项目级 13001)

    # R27 项目绑定错误细分(manual 绑定/add_repo 同口径;2002 保留=URL 格式非法)
    REPO_NOT_FOUND = 2011           # GitLab 查仓库 404(仓库不存在)
    REPO_FORBIDDEN = 2012           # GitLab 查仓库 401/403(平台 bot 无访问权限,归并防枚举)
    REPO_PERM_LOW = 2013            # bot 权限 < Maintainer(40,含 group 继承后仍不足/permissions 全 null)
    GITLAB_UNREACHABLE = 2014       # GitLab 连接失败(httpx 网络异常/其他非 200 状态码)

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

    # R31 本机 Runner 快速创建(16xx 段顺延)
    RUNNER_LOCAL_ENV = 16002            # 本机环境校验失败(message 细分 sub)
    RUNNER_LOCAL_LIMIT = 16003          # 本机 runner 上限(3)
    RUNNER_LOCAL_STOP_FAILED = 16004    # 删除代停容器失败
    RUNNER_NAME_EXISTS = 16005          # 名称冲突(本端点显式校验)
    RUNNER_NOT_LOCAL = 16006            # 非本机 runner 调 start/stop,或 disabled 启动
    RUNNER_NO_PROCESS_HANDLE = 16007    # 停止时既无 WS 连接也无句柄

    # R26 Runner 终端(6xxx 段)
    RUNNER_NOT_ONLINE = 6001          # Runner 不在线
    RUNNER_SESSION_EXISTS = 6002      # 该 Runner 已有终端会话,请先关闭
    RUNNER_TOO_OLD = 6003             # Runner 容器标识缺失(旧版镜像未上报 或 非容器化部署),无法打开终端

    # R28 头像上传(按契约使用 4001/4002;与 R4 任务 4001/4002 数字段重合,
    # 两者业务语境不同、不会同时出现在同一接口,前端按 message 展示)
    AVATAR_FORMAT_UNSUPPORTED = 4001  # 文件格式不支持(仅 JPG/PNG/WebP)
    AVATAR_TOO_LARGE = 4002           # 文件大小超过 2MB

    # 权限
    NOT_SUPERADMIN = 19002            # 非平台超级管理员
    NO_PROJECT_PERMISSION = 1901      # 无项目操作权限(非 owner)


# ---------------------------------------------------------------------------
# R27 绑定错误文案(「枚举与字典映射」表文案列,一字不差交付)
# message 不含 bot token/内部 path,不区分 401/403 细节;gitlab_url 插值仅 2011
# ---------------------------------------------------------------------------
MSG_REPO_URL_INVALID = "仓库地址格式无效,请粘贴形如 http://{host}/{group}/{repo}.git 的地址"
MSG_REPO_NOT_FOUND = ("仓库不存在,请检查 group/repo 名称是否正确"
                      "(仅支持平台 GitLab:{gitlab_url})")
MSG_REPO_FORBIDDEN = "平台 bot 无权访问该仓库,请联系管理员将平台 bot 加入仓库所在 group"
MSG_REPO_PERM_LOW = "平台 bot 权限不足(需 Maintainer 及以上),请联系管理员调整"
MSG_GITLAB_UNREACHABLE = "GitLab 服务连接失败,请稍后重试"


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

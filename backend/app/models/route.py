"""网关路由模型 - R10/R15 共享(routes 表)

type=preview:任务预览路由(R10)
type=deploy:部署路由(R7/R15)
网关本体(HTTP Host 转发服务器)归 R15,消费 route_service。
"""

import uuid
from datetime import datetime

from sqlalchemy import BigInteger, Boolean, Column, DateTime, Enum, Index, Integer, String, UniqueConstraint, func
from sqlalchemy.dialects.mysql import CHAR

from app.database import Base


class Route(Base):
    """网关路由表(Host 精确匹配 → upstream 直连;D20 无本地代理层)"""
    __tablename__ = "routes"
    __table_args__ = (
        Index("ix_routes_type_status", "type", "status"),
    )

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    route_id = Column(CHAR(36), default=lambda: str(uuid.uuid4()), unique=True, nullable=False, comment="对外UUID")
    host = Column(String(255), unique=True, nullable=False, comment="匹配 Host(如 {slug}--{taskId}--{port}.preview.xxx)")
    upstream = Column(String(255), nullable=False, comment="上游地址 http://{runner_host}:{mapped_port}")
    type = Column(
        Enum("preview", "deploy", name="route_type_enum"),
        nullable=False,
        default="preview",
        server_default="preview",
        comment="路由类型",
    )
    task_id = Column(CHAR(36), nullable=True, index=True, comment="任务 id(preview/deploy 均关联任务)")
    project_id = Column(CHAR(36), nullable=False, index=True, comment="项目 id(鉴权:项目成员)")
    port = Column(Integer, nullable=False, comment="容器内端口")
    status = Column(
        Enum("active", "inactive", name="route_status_enum"),
        nullable=False,
        default="inactive",
        server_default="inactive",
        comment="状态(active 才转发)",
    )
    auth_required = Column(Boolean, nullable=False, default=True, server_default="1", comment="是否需要鉴权(预览=成员;部署=公开则 False)")
    created_at = Column(DateTime, default=func.now(), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, default=func.now(), server_default=func.now(), onupdate=func.now(), nullable=False)

    def __repr__(self) -> str:
        return f"<Route(host={self.host}, type={self.type}, status={self.status})>"

"""Runner 模型 - R16(runners 表)"""

import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Column,
    DateTime,
    Enum,
    Integer,
    JSON,
    String,
    func,
)
from sqlalchemy.dialects.mysql import CHAR

from app.database import Base


class Runner(Base):
    """Runner 注册表(运维经超管创建,Runner 进程用 token 注册上线)"""
    __tablename__ = "runners"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    runner_id = Column(CHAR(36), default=lambda: str(uuid.uuid4()), unique=True, nullable=False, comment="对外UUID")
    name = Column(String(64), unique=True, nullable=False, comment="Runner 名(运维起)")
    role = Column(
        Enum("worker", "deploy", name="runner_role_enum"),
        nullable=False,
        default="worker",
        server_default="worker",
        index=True,
        comment="角色(worker 跑任务/deploy 跑部署容器)",
    )
    token_hash = Column(String(255), nullable=False, comment="Runner token 的 bcrypt hash(不存明文)")
    status = Column(
        Enum("online", "offline", "disabled", name="runner_status_enum"),
        nullable=False,
        default="offline",
        server_default="offline",
        index=True,
        comment="状态",
    )
    last_heartbeat_at = Column(DateTime, nullable=True, comment="最后心跳时间")
    machine_info = Column(JSON, nullable=True, comment="{os, arch, cpu_count, mem_total_gb, docker_version}")
    current_containers = Column(Integer, nullable=False, default=0, server_default="0", comment="当前运行容器数(调度用)")
    max_containers = Column(Integer, nullable=False, default=10, server_default="10", comment="最多容器数")
    public_ip = Column(String(64), nullable=True, comment="deploy Runner 必填(部署 URL 指向)")
    created_by = Column(CHAR(36), nullable=False, comment="创建 token 的超管 user_id")
    created_at = Column(DateTime, default=func.now(), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime,
        default=func.now(),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    def __repr__(self) -> str:
        return f"<Runner(id={self.id}, name={self.name}, role={self.role}, status={self.status})>"

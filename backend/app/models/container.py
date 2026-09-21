"""容器模型 - R8 任务级容器(containers 表)"""

from datetime import datetime

from sqlalchemy import (
    JSON,
    DateTime,
    Enum,
    String,
    func,
)
from sqlalchemy import (
    BigInteger,
    Column,
)
from sqlalchemy.dialects.mysql import CHAR

from app.database import Base


class Container(Base):
    """任务容器记录(平台侧台账;实际容器跑在 Runner 上)

    - task_id:部署中容器可空(R7 deployed 后保留运行)
    - runner_host_port_*:Runner 把容器端口直接映射到宿主机随机端口(D20,无本地代理层)
    """
    __tablename__ = "containers"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    container_id = Column(String(64), unique=True, nullable=False, comment="Runner 上的 docker id")
    task_id = Column(CHAR(36), nullable=True, index=True, comment="任务 id(部署中容器可空)")
    runner_id = Column(CHAR(36), nullable=False, index=True, comment="运行该容器的 Runner id")
    project_id = Column(CHAR(36), nullable=False, index=True, comment="项目 id")
    status = Column(
        Enum("creating", "running", "stopped", "failed", "destroyed", name="container_status_enum"),
        nullable=False,
        default="creating",
        server_default="creating",
        index=True,
        comment="状态",
    )
    image = Column(String(255), nullable=False, default="platform/devbox:v1", server_default="platform/devbox:v1", comment="镜像")
    cpu_limit = Column(String(16), nullable=False, default="2c", server_default="2c", comment="CPU 限制")
    mem_limit = Column(String(16), nullable=False, default="4g", server_default="4g", comment="内存限制")
    disk_limit = Column(String(16), nullable=False, default="10g", server_default="10g", comment="磁盘限制")
    exposed_ports = Column(JSON, nullable=False, comment="容器内端口列表 [5173, 8000]")
    runner_host_port_5173 = Column(BigInteger, nullable=True, comment="Runner 上映射到 5173 的宿主机端口")
    runner_host_port_8000 = Column(BigInteger, nullable=True, comment="Runner 上映射到 8000 的宿主机端口")
    created_at = Column(DateTime, default=func.now(), server_default=func.now(), nullable=False, comment="创建时间")
    destroyed_at = Column(DateTime, nullable=True, comment="销毁时间")

    def __repr__(self) -> str:
        return f"<Container(id={self.id}, container_id={self.container_id}, status={self.status})>"

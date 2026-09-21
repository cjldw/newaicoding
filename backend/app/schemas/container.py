"""容器 Pydantic 模型 - R8(内部台账模型;容器管理不暴露用户接口)"""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class ContainerStatusData(BaseModel):
    """容器状态摘要(内部/管理用)"""
    container_id: str
    task_id: Optional[str] = None
    runner_id: str
    project_id: str
    status: str
    image: str
    runner_host_port_5173: Optional[int] = None
    runner_host_port_8000: Optional[int] = None
    created_at: datetime
    destroyed_at: Optional[datetime] = None

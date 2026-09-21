"""模型配置模型 - R13 模型接入(model_configs 表)"""

import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    Column,
    DateTime,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.mysql import CHAR

from app.database import Base


class ModelConfig(Base):
    """项目级模型配置(OpenAI 兼容 url+key+model,主/备多组)

    约束:
    - (project_id, name) 唯一:同项目配置名唯一(组合唯一约束硬保证)
    - 同项目最多一个 is_default:MySQL 无部分唯一索引,由服务层保证(13003 拒绝第二个 default)
    """
    __tablename__ = "model_configs"
    __table_args__ = (
        UniqueConstraint("project_id", "name", name="uq_model_config_name"),
    )

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    config_id = Column(CHAR(36), default=lambda: str(uuid.uuid4()), unique=True, nullable=False, comment="对外UUID")
    project_id = Column(CHAR(36), nullable=False, index=True, comment="项目 id(projects.project_id)")
    name = Column(String(64), nullable=False, comment="配置名")
    base_url = Column(String(255), nullable=False, comment="OpenAI 兼容 endpoint(http/https)")
    api_key_encrypted = Column(Text, nullable=False, comment="AES-GCM 加密的 api_key")
    model = Column(String(64), nullable=False, comment="模型名(claude-sonnet-5/gpt-5/deepseek-chat 等)")
    is_default = Column(Boolean, nullable=False, default=False, server_default="0", comment="是否默认(同项目最多一个,服务层保证)")
    enabled = Column(Boolean, nullable=False, default=True, server_default="1", comment="是否启用")
    created_by = Column(CHAR(36), nullable=False, comment="创建者 user_id")
    created_at = Column(DateTime, default=func.now(), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, default=func.now(), server_default=func.now(), onupdate=func.now(), nullable=False)

    def __repr__(self) -> str:
        return f"<ModelConfig(id={self.id}, config_id={self.config_id}, name={self.name}, is_default={self.is_default})>"

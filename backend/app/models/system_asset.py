"""系统级 Claude 资产模型 - R5(容器探测采集 claude_system_assets 表)

超管触发采集:Runner 拉临时容器探测镜像内置 skills/MCP(ls /root/.claude/skills/
+ cat /root/.claude.json),结果覆盖式入库(先清后插);失败不清旧库。
字段规格与迁移 SQL 见 docs/20260926_skills市场安装/DEPLOY.md。
"""

from sqlalchemy import (
    BigInteger,
    Column,
    DateTime,
    Enum,
    Index,
    JSON,
    String,
)

from app.database import Base


class ClaudeSystemAsset(Base):
    """claude_system_assets:镜像内置资产快照(每次采集整体覆盖,无更新语义)"""

    __tablename__ = "claude_system_assets"
    __table_args__ = (
        Index("idx_kind", "kind"),
    )

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    name = Column(String(128), nullable=False, comment="skill目录名/mcp名")
    kind = Column(
        Enum("skill", "mcp", name="claude_system_asset_kind_enum"),
        nullable=False,
        comment="类别",
    )
    detail = Column(JSON, nullable=True, comment="探测原文")
    collected_at = Column(DateTime, nullable=False, comment="采集时间")
    image_tag = Column(String(128), nullable=True, comment="镜像标识")

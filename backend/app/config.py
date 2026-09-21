"""旗程后端配置模块 - 基于 pydantic-settings"""

from pathlib import Path
from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """应用配置，从 .env 文件和环境变量加载"""

    model_config = SettingsConfigDict(
        env_file=str(Path(__file__).resolve().parent.parent / ".env"),
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # 数据库
    DATABASE_URL: str = "mysql+asyncmy://user:password@localhost:3306/aicoding?charset=utf8mb4"

    # Redis（R1 仅占位）
    REDIS_URL: str = "redis://localhost:6379/0"

    # 安全密钥
    JWT_SECRET_KEY: str = "change-me-jwt-secret"
    PLATFORM_SECRET_KEY: str = "change-me-platform-secret-32bytes"  # AES-256-GCM 密钥（hex 64 字符 = 32 字节）

    # JWT 过期时间
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = 120  # 2 小时
    JWT_REFRESH_TOKEN_EXPIRE_DAYS: int = 7  # 7 天

    # 密码锁策略
    LOGIN_MAX_WRONG_ATTEMPTS: int = 5
    LOGIN_LOCK_MINUTES: int = 10

    # Runner 接入共享密钥(R8 最小版;R16 升级为 per-runner 注册 token)
    RUNNER_TOKEN: str = "change-me-runner-token"
    # Runner 宿主机端口映射范围(D20)
    RUNNER_PORT_RANGE_START: int = 20000
    RUNNER_PORT_RANGE_END: int = 29999

    # 环境
    ENVIRONMENT: str = "development"

    @property
    def platform_secret_bytes(self) -> bytes:
        """将 PLATFORM_SECRET_KEY 转为 32 字节（AES-256 要求）"""
        key = self.PLATFORM_SECRET_KEY
        # 如果是 hex 字符串（64 字符），解码为 32 字节
        if len(key) == 64:
            try:
                return bytes.fromhex(key)
            except ValueError:
                pass
        # 否则用 SHA-256 哈希到 32 字节
        import hashlib
        return hashlib.sha256(key.encode()).digest()


# 全局单例
settings = Settings()

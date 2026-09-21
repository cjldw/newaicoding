"""AES-256-GCM 加解密模块 - 用于 GitLab token 加密存储"""

import base64
import os

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.config import settings


def _get_key() -> bytes:
    """获取 32 字节 AES-256 密钥"""
    return settings.platform_secret_bytes


def encrypt_token(plaintext: str) -> str:
    """
    AES-256-GCM 加密，返回 base64 编码字符串。
    格式: base64(nonce_12bytes + ciphertext + tag_16bytes)
    """
    key = _get_key()
    aesgcm = AESGCM(key)
    nonce = os.urandom(12)  # 96-bit nonce
    ciphertext = aesgcm.encrypt(nonce, plaintext.encode("utf-8"), None)
    # nonce + ciphertext(含 tag) 拼接后 base64
    return base64.b64encode(nonce + ciphertext).decode("ascii")


def decrypt_token(encrypted: str) -> str:
    """
    AES-256-GCM 解密，输入 base64 编码字符串，返回明文。
    """
    key = _get_key()
    aesgcm = AESGCM(key)
    raw = base64.b64decode(encrypted)
    nonce = raw[:12]
    ciphertext = raw[12:]
    plaintext = aesgcm.decrypt(nonce, ciphertext, None)
    return plaintext.decode("utf-8")

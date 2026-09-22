"""知识库导入服务 - R20(repo_import 后台拉取:GitLab tree + raw → 事务内整体替换)

- bot token 经 GitLab API:tree recursive 过滤 paths 前缀下 .md → 逐文件 raw
- 限制:单库 ≤500 页(超出跳过提示);单文件 >1MB 跳过提示;全部为空 → failed
- 整体替换:先删旧 docs 再插新(同事务);失败保留旧快照
- 并发互斥:同库 importing 中重复触发 20007(服务层检查 + 内存锁双保险)
- 通知:R18 未落地,当前 logger 记录(钩子点 _notify_import_done)
"""

import asyncio
import logging
import time
from typing import Optional

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.response import BizError
from app.models.knowledge_base import KnowledgeBase, KnowledgeDoc
from app.services import gitlab_service

logger = logging.getLogger(__name__)

IMPORT_TIMEOUT_SECONDS = 300  # 导入超时 5 分钟
_MAX_PATH_INVALID = re_compile = None  # placeholder 防误用(实际用 kb_service._slug 工具)

# 内存互斥锁(进程内;单实例部署口径)
_importing_locks: set[str] = set()


def is_importing(kb_id: str) -> bool:
    return kb_id in _importing_locks


def _parse_path(path: str) -> tuple[str, str]:
    """repo 文件路径 → (doc path, title):去 .md 后缀;title 取最后一段"""
    p = path[:-3] if path.endswith(".md") else path
    title = p.rsplit("/", 1)[-1]
    return p, title


def _sanitize(path: str) -> str:
    from app.services.kb_service import _PATH_INVALID_RE

    return _PATH_INVALID_RE.sub("-", path)


async def run_import(db: AsyncSession, kb: KnowledgeBase, bot_token: str, gitlab_url: str) -> dict:
    """
    执行导入/同步(同步阻塞版;后台任务包装见 spawn_import):
    - 拉 tree(recursive)过滤 paths 前缀下 .md
    - 逐文件 raw 拉内容(>1MB 跳过;页面总数 >500 截断)
    - 事务内整体替换(以仓库为准:删除/新增/覆盖)
    返回导入结果摘要 {pages, skipped_oversize, skipped_paths, hint}。
    """
    import httpx

    config = kb.source_config or {}
    repo_id = config.get("repo_id")
    branch = config.get("branch", "master")
    prefixes = tuple(f"{p.strip('/')}/" for p in config.get("paths", []))
    prefix_exact = tuple(p.strip('/') for p in config.get("paths", []))

    from app.core.encryption import decrypt_token  # noqa: F401 — bot token 已由调用方解密传入
    from sqlalchemy import text as _text

    headers = {"Authorization": f"Bearer {bot_token}"}
    base = f"{gitlab_url.rstrip('/')}/api/v4/projects/{repo_id}/repository"

    client = httpx.AsyncClient(timeout=30.0, verify=False)
    skipped_oversize = 0
    skipped_paths: list[str] = []
    files: list[tuple[str, str]] = []  # (repo 路径, tree path)

    try:
        # 分页拉全量 tree
        page = 1
        entries: list[dict] = []
        while True:
            resp = await client.get(
                f"{base}/tree",
                params={"ref": branch, "recursive": "true", "per_page": 100, "page": page},
                headers=headers,
            )
            if resp.status_code != 200:
                raise RuntimeError(f"仓库目录拉取失败({resp.status_code}),请检查仓库/分支/权限")
            batch = resp.json()
            entries.extend(batch)
            if len(batch) < 100:
                break
            page += 1

        for entry in entries:
            if entry.get("type") != "blob" or not entry.get("path", "").endswith(".md"):
                continue
            path = entry["path"]
            if not (path.startswith(prefixes) or path in prefix_exact):
                continue
            files.append((path, path))

        if not files:
            raise RuntimeError("导入目录下没有可导入的 .md 文件")

        # 逐文件拉内容(限制:1MB 跳过;500 页截断)
        docs: list[dict] = []
        for repo_path, _tp in files:
            if len(docs) >= 500:
                skipped_paths.append(f"{repo_path}(页面数超限)")
                continue
            raw_resp = await client.get(
                f"{base}/files/{__import__('urllib.parse', fromlist=['quote']).quote(repo_path, safe='')}/raw",
                params={"ref": branch},
                headers=headers,
            )
            if raw_resp.status_code != 200:
                skipped_paths.append(repo_path)
                continue
            content_bytes = raw_resp.content
            if len(content_bytes) > 1024 * 1024:
                skipped_oversize += 1
                continue
            docs.append({"repo_path": repo_path, "content": content_bytes.decode("utf-8", errors="replace")})

        if not docs:
            raise RuntimeError("导入目录下没有可导入的 .md 文件")

        # 事务内整体替换(以仓库为准;path 冲突由 UNIQUE 兜底,此处先生成唯一 path)
        await db.execute(delete(KnowledgeDoc).where(KnowledgeDoc.kb_id == kb.kb_id))
        existing_paths: set[str] = set()
        operator_id = kb.created_by
        for d in docs:
            doc_path, title = _parse_path(d["repo_path"])
            doc_path = _sanitize_path(doc_path)
            candidate = doc_path
            j = 1
            while candidate in existing_paths:
                candidate = f"{doc_path}-{j}"
                j += 1
            existing_paths.add(candidate)
            db.add(KnowledgeDoc(
                kb_id=kb.kb_id,
                title=title,
                path=candidate,
                content=d["content"],
                source_file_path=d["repo_path"],
                created_by=operator_id,
                updated_by=operator_id,
            ))
        await db.flush()

        kb.import_status = "done"
        kb.import_error = ";".join(
            ([f"{len([s for s in skipped_paths])} 个路径跳过"] if skipped_paths else [])
            + ([f"{skipped_oversize} 个文件超过 1MB 跳过"] if skipped_oversize else [])
        ) or None
        kb.last_synced_at = __import__("datetime").datetime.now()
        await db.flush()

        result = {
            "pages": len(docs),
            "skipped_oversize": skipped_oversize,
            "skipped_paths": skipped_paths,
        }
        logger.info("知识库导入完成 kb=%s pages=%d", kb.kb_id, len(docs))
        return result
    finally:
        await client.aclose()


def _sanitize_path(path: str) -> str:
    import re

    return re.sub(r"[^0-9A-Za-z一-鿿/_-]+", "-", path)


# ---------------------------------------------------------------------------
# 后台任务包装(spawn;完成后通知钩子)
# ---------------------------------------------------------------------------
def _notify_import_done(kb_id: str, ok: bool, summary: str) -> None:
    # TODO(R18): 站内信 + toast 通知(接收人=触发人 + 项目 owner)
    if ok:
        logger.info("知识库导入完成通知 kb=%s %s", kb_id, summary)
    else:
        logger.warning("知识库导入失败通知 kb=%s %s", kb_id, summary)


async def _import_task(kb_id: str, bot_token: str, gitlab_url: str) -> None:
    from app.database import async_session_factory

    started = time.time()
    try:
        while True:
            async with async_session_factory() as db:
                kb = (await db.execute(
                    select(KnowledgeBase).where(KnowledgeBase.kb_id == kb_id)
                )).scalars().first()
                if kb is None:
                    return
                try:
                    result = await asyncio.wait_for(
                        run_import(db, kb, bot_token, gitlab_url),
                        timeout=IMPORT_TIMEOUT_SECONDS,
                    )
                    await db.commit()
                    _notify_import_done(kb_id, True, f"共 {result['pages']} 个页面")
                except Exception as e:
                    await db.rollback()
                    # 失败保留旧快照:仅更新状态与错误信息
                    async with async_session_factory() as db2:
                        kb2 = (await db2.execute(
                            select(KnowledgeBase).where(KnowledgeBase.kb_id == kb_id)
                        )).scalars().first()
                        if kb2 is not None:
                            kb2.import_status = "failed"
                            kb2.import_error = str(e)[:255]
                            await db2.commit()
                    _notify_import_done(kb_id, False, str(e))
                return
    except Exception:
        logger.exception("导入任务异常 kb=%s", kb_id)
    finally:
        _importing_locks.discard(kb_id)
        _ = started


def spawn_import(kb_id: str, bot_token: str, gitlab_url: str) -> None:
    """入队后台导入(asyncio 任务;并发互斥由调用方 20007 前置检查 + 此处锁双保险)"""
    if kb_id in _importing_locks:
        raise BizError(20007, "导入进行中,请稍候")
    _importing_locks.add(kb_id)
    try:
        loop = asyncio.get_running_loop()
        loop.create_task(_import_task(kb_id, bot_token, gitlab_url))
    except RuntimeError:
        _importing_locks.discard(kb_id)
        raise

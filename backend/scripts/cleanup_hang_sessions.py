"""
一次性数据清理脚本:清空任务 977/978 的 claude_session_id

背景:R32.F8 平台侧置空代码在 container_service.py:242(已提交),但对 977/978
未生效——容器启动时置空发生在 handle_container_started,之后终端自动进 claude
又把会话建回(详见 hang-analysis.md 第 1 项机理分析)。

执行前后 SELECT 留痕,确认 rows affected。
"""
import asyncio
import os
import sys

# 添加 backend 到 path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession

# 从 .env 读取 DATABASE_URL
env_path = os.path.join(os.path.dirname(__file__), "..", ".env")
with open(env_path, encoding="utf-8") as f:
    for line in f:
        if line.startswith("DATABASE_URL="):
            DATABASE_URL = line.split("=", 1)[1].strip()
            break


async def main():
    engine = create_async_engine(DATABASE_URL, echo=False)
    async with engine.begin() as conn:
        # 执行前 SELECT 留痕
        print("=" * 60)
        print("执行前:SELECT id, task_id, claude_session_id FROM tasks WHERE id IN (977, 978)")
        result = await conn.execute(
            text("SELECT id, task_id, claude_session_id FROM tasks WHERE id IN (977, 978)")
        )
        rows_before = result.fetchall()
        for row in rows_before:
            print(f"  id={row[0]}, task_id={row[1]}, claude_session_id={row[2]}")

        # UPDATE 清空
        print("\n执行:UPDATE tasks SET claude_session_id=NULL WHERE id IN (977, 978)")
        await conn.execute(
            text("UPDATE tasks SET claude_session_id=NULL WHERE id IN (977, 978)")
        )

        # 执行后 SELECT 留痕
        print("\n执行后:SELECT id, task_id, claude_session_id FROM tasks WHERE id IN (977, 978)")
        result = await conn.execute(
            text("SELECT id, task_id, claude_session_id FROM tasks WHERE id IN (977, 978)")
        )
        rows_after = result.fetchall()
        for row in rows_after:
            print(f"  id={row[0]}, task_id={row[1]}, claude_session_id={row[2]}")

        print("=" * 60)
        print(f"清理完成:rows_before={len(rows_before)}, rows_after={len(rows_after)}")

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())

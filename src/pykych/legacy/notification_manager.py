"""
通知管理模块 — 通知的 CRUD 操作。
管理员和站长可管理通知，重要通知可显示在首页。
"""

from typing import Optional
from .mysql_manager import get_sys_pool, row_to_dict


async def list_notifications(include_inactive: bool = False) -> list[dict]:
    """获取所有通知（按创建时间倒序）。"""
    pool = await get_sys_pool()
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            if include_inactive:
                await cur.execute(
                    "SELECT id, title, content, is_important, is_active, "
                    "created_at, updated_at "
                    "FROM notifications ORDER BY created_at DESC"
                )
            else:
                await cur.execute(
                    "SELECT id, title, content, is_important, is_active, "
                    "created_at, updated_at "
                    "FROM notifications WHERE is_active = 1 "
                    "ORDER BY created_at DESC"
                )
            rows = await cur.fetchall()
            return [row_to_dict(r, cur) for r in rows]


async def get_important_notifications() -> list[dict]:
    """获取首页显示的活跃重要通知（最多 5 条）。"""
    pool = await get_sys_pool()
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                "SELECT id, title, content, created_at "
                "FROM notifications "
                "WHERE is_important = 1 AND is_active = 1 "
                "ORDER BY created_at DESC LIMIT 5"
            )
            rows = await cur.fetchall()
            return [row_to_dict(r, cur) for r in rows]


async def get_notification(notif_id: int) -> Optional[dict]:
    """获取单条通知。"""
    pool = await get_sys_pool()
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                "SELECT id, title, content, is_important, is_active, "
                "created_at, updated_at "
                "FROM notifications WHERE id = %s",
                (notif_id,),
            )
            row = await cur.fetchone()
            return row_to_dict(row, cur) if row else None


async def create_notification(
    title: str, content: str, is_important: bool = False
) -> dict:
    """创建新通知。"""
    pool = await get_sys_pool()
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                "INSERT INTO notifications (title, content, is_important) "
                "VALUES (%s, %s, %s)",
                (title, content, 1 if is_important else 0),
            )
            notif_id = cur.lastrowid
            return await get_notification(notif_id)


async def update_notification(
    notif_id: int,
    title: str,
    content: str,
    is_important: bool = False,
    is_active: bool = True,
) -> Optional[dict]:
    """更新通知。"""
    pool = await get_sys_pool()
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                "UPDATE notifications SET title = %s, content = %s, "
                "is_important = %s, is_active = %s "
                "WHERE id = %s",
                (title, content, 1 if is_important else 0, 1 if is_active else 0, notif_id),
            )
            if cur.rowcount == 0:
                return None
            return await get_notification(notif_id)


async def delete_notification(notif_id: int) -> bool:
    """删除通知。"""
    pool = await get_sys_pool()
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                "DELETE FROM notifications WHERE id = %s", (notif_id,)
            )
            return cur.rowcount > 0


async def toggle_notification_importance(notif_id: int) -> Optional[dict]:
    """切换通知的「重要」状态。"""
    pool = await get_sys_pool()
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                "UPDATE notifications SET is_important = NOT is_important "
                "WHERE id = %s",
                (notif_id,),
            )
            if cur.rowcount == 0:
                return None
            return await get_notification(notif_id)


async def toggle_notification_active(notif_id: int) -> Optional[dict]:
    """切换通知的启用/停用状态。"""
    pool = await get_sys_pool()
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                "UPDATE notifications SET is_active = NOT is_active "
                "WHERE id = %s",
                (notif_id,),
            )
            if cur.rowcount == 0:
                return None
            return await get_notification(notif_id)

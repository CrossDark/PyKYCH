"""
评论区数据管理层 — 评论的增删查。
"""

from typing import Optional
from .mysql_manager import get_sys_pool, row_to_dict


async def get_comments(article_type: str, article_slug: str) -> list[dict]:
    """获取指定文章的所有评论（按时间正序）。"""
    pool = await get_sys_pool()
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                "SELECT id, article_type, article_slug, author_name, content, created_at "
                "FROM comments "
                "WHERE article_type = %s AND article_slug = %s "
                "ORDER BY created_at ASC",
                (article_type, article_slug),
            )
            rows = await cur.fetchall()
            return [row_to_dict(r, cur) for r in rows]


async def add_comment(
    article_type: str,
    article_slug: str,
    author_name: str,
    content: str,
) -> dict:
    """添加一条评论，返回新评论的完整信息。"""
    pool = await get_sys_pool()
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                "INSERT INTO comments (article_type, article_slug, author_name, content) "
                "VALUES (%s, %s, %s, %s)",
                (article_type, article_slug, author_name, content),
            )
            comment_id = cur.lastrowid
            await cur.execute(
                "SELECT id, article_type, article_slug, author_name, content, created_at "
                "FROM comments WHERE id = %s",
                (comment_id,),
            )
            row = await cur.fetchone()
            return row_to_dict(row, cur)


async def get_comment_count(article_type: str, article_slug: str) -> int:
    """获取指定文章的评论数。"""
    pool = await get_sys_pool()
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                "SELECT COUNT(*) FROM comments "
                "WHERE article_type = %s AND article_slug = %s",
                (article_type, article_slug),
            )
            row = await cur.fetchone()
            return row[0] if row else 0


async def delete_comment(comment_id: int) -> bool:
    """删除一条评论。返回是否成功删除。"""
    pool = await get_sys_pool()
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                "DELETE FROM comments WHERE id = %s",
                (comment_id,),
            )
            return cur.rowcount > 0

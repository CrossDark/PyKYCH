"""
行评论数据管理层 — 为文章每一行提供短评论功能。
每条行评论不超过 20 字，同一用户可在同一行添加多条。
"""

from typing import Optional
from .mysql_manager import get_sys_pool, row_to_dict


async def get_line_comments(
    article_type: str, article_slug: str
) -> list[dict]:
    """获取指定文章的所有行评论（按行号、时间正序）。"""
    pool = await get_sys_pool()
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                "SELECT id, article_type, article_slug, line_number, "
                "author_name, content, created_at "
                "FROM line_comments "
                "WHERE article_type = %s AND article_slug = %s "
                "ORDER BY line_number ASC, created_at ASC",
                (article_type, article_slug),
            )
            rows = await cur.fetchall()
            return [row_to_dict(r, cur) for r in rows]


async def get_line_comments_by_line(
    article_type: str, article_slug: str, line_number: int
) -> list[dict]:
    """获取指定文章某一行的所有行评论。"""
    pool = await get_sys_pool()
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                "SELECT id, article_type, article_slug, line_number, "
                "author_name, content, created_at "
                "FROM line_comments "
                "WHERE article_type = %s AND article_slug = %s "
                "AND line_number = %s "
                "ORDER BY created_at ASC",
                (article_type, article_slug, line_number),
            )
            rows = await cur.fetchall()
            return [row_to_dict(r, cur) for r in rows]


async def get_line_comment_counts(
    article_type: str, article_slug: str
) -> dict[int, int]:
    """获取文章每行的评论数量，返回 {line_number: count}。"""
    pool = await get_sys_pool()
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                "SELECT line_number, COUNT(*) as cnt "
                "FROM line_comments "
                "WHERE article_type = %s AND article_slug = %s "
                "GROUP BY line_number",
                (article_type, article_slug),
            )
            rows = await cur.fetchall()
            return {r[0]: r[1] for r in rows}


async def add_line_comment(
    article_type: str,
    article_slug: str,
    line_number: int,
    author_name: str,
    content: str,
) -> dict:
    """添加一条行评论（自动截断至 20 字）。"""
    content = content.strip()[:20]
    if not content:
        raise ValueError("评论内容不能为空")

    pool = await get_sys_pool()
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                "INSERT INTO line_comments "
                "(article_type, article_slug, line_number, author_name, content) "
                "VALUES (%s, %s, %s, %s, %s)",
                (article_type, article_slug, line_number, author_name, content),
            )
            comment_id = cur.lastrowid
            await cur.execute(
                "SELECT id, article_type, article_slug, line_number, "
                "author_name, content, created_at "
                "FROM line_comments WHERE id = %s",
                (comment_id,),
            )
            row = await cur.fetchone()
            return row_to_dict(row, cur)


async def delete_line_comment(comment_id: int) -> bool:
    """删除一条行评论。"""
    pool = await get_sys_pool()
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                "DELETE FROM line_comments WHERE id = %s",
                (comment_id,),
            )
            return cur.rowcount > 0

"""
评分数据管理层 — 为文章提供 [-1, 1] 区间的浮点评分。
用户以上可评分，每人每篇文章仅一条评分（可修改）。
"""

from typing import Optional
from .mysql_manager import get_sys_pool, row_to_dict


async def get_article_rating(article_type: str, article_slug: str) -> dict:
    """获取文章的评分汇总: average_score, total_voters。"""
    pool = await get_sys_pool()
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                "SELECT COUNT(*) as total_voters, AVG(score) as average_score "
                "FROM ratings "
                "WHERE article_type = %s AND article_slug = %s",
                (article_type, article_slug),
            )
            row = await cur.fetchone()
            total = row[0] if row else 0
            avg = float(row[1]) if row and row[1] is not None else 0.0
            return {
                "average_score": round(avg, 2),
                "total_voters": total,
            }


async def get_user_rating(
    article_type: str, article_slug: str, author_name: str
) -> Optional[dict]:
    """获取某用户对某文章的已有评分。"""
    pool = await get_sys_pool()
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                "SELECT id, article_type, article_slug, author_name, score, created_at "
                "FROM ratings "
                "WHERE article_type = %s AND article_slug = %s AND author_name = %s",
                (article_type, article_slug, author_name),
            )
            row = await cur.fetchone()
            return row_to_dict(row, cur) if row else None


async def set_rating(
    article_type: str,
    article_slug: str,
    author_name: str,
    score: float,
) -> dict:
    """设置或更新评分。score 会被钳制在 [-1, 1] 之间。"""
    score = max(-1.0, min(1.0, float(score)))
    score = round(score, 2)

    pool = await get_sys_pool()
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                "INSERT INTO ratings (article_type, article_slug, author_name, score) "
                "VALUES (%s, %s, %s, %s) "
                "ON DUPLICATE KEY UPDATE score = VALUES(score)",
                (article_type, article_slug, author_name, score),
            )

    # 返回更新后的汇总
    return await get_article_rating(article_type, article_slug)

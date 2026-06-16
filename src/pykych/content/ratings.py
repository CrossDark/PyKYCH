"""
评分系统模块 — 为文章提供 [-1, 1] 浮点评分。

特性:
    - 评分范围 [-1.00, 1.00]，精度 0.01
    - 每用户每文章仅一条评分（可修改）
    - 自动计算平均值和总人数
    - 评分值自动钳制在有效范围内

表: ratings (article_type, article_slug, author_name, score)

用法:
    from pykych.content.ratings import get_article_rating, set_rating
"""

from ..core.db import get_sys_pool, row_to_dict


async def get_article_rating(
    article_type: str, article_slug: str
) -> dict:
    """
    获取文章的评分汇总。

    参数:
        article_type: 文章类型标识
        article_slug: 文章 slug

    返回:
        {"average_score": float, "total_voters": int}
    """
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
) -> dict | None:
    """
    获取某用户对某文章的已有评分。

    参数:
        article_type: 文章类型标识
        article_slug: 文章 slug
        author_name:  用户名

    返回:
        评分记录字典或 None
    """
    pool = await get_sys_pool()
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                "SELECT id, article_type, article_slug, author_name, "
                "score, created_at "
                "FROM ratings "
                "WHERE article_type = %s AND article_slug = %s "
                "AND author_name = %s",
                (article_type, article_slug, author_name),
            )
            row = await cur.fetchone()
            if row:
                result = row_to_dict(row, cur)
                # MySQL DECIMAL 可能返回 Decimal 类型，转为 float
                if "score" in result and result["score"] is not None:
                    result["score"] = float(result["score"])
                return result
            return None


async def set_rating(
    article_type: str,
    article_slug: str,
    author_name: str,
    score: float,
) -> dict:
    """
    设置或更新用户评分。

    评分值会被自动钳制在 [-1.00, 1.00] 范围内。

    参数:
        article_type: 文章类型标识
        article_slug: 文章 slug
        author_name:  用户名
        score:        评分值（-1.00 到 1.00）

    返回:
        更新后的评分汇总 {"average_score": ..., "total_voters": ...}
    """
    # 钳制并四舍五入
    score = max(-1.0, min(1.0, float(score)))
    score = round(score, 2)

    pool = await get_sys_pool()
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                "INSERT INTO ratings "
                "(article_type, article_slug, author_name, score) "
                "VALUES (%s, %s, %s, %s) "
                "ON DUPLICATE KEY UPDATE score = VALUES(score)",
                (article_type, article_slug, author_name, score),
            )

    return await get_article_rating(article_type, article_slug)


async def delete_rating(
    article_type: str, article_slug: str, author_name: str
) -> bool:
    """
    删除用户对文章的评分。

    参数:
        article_type: 文章类型标识
        article_slug: 文章 slug
        author_name:  用户名

    返回:
        True 表示删除成功
    """
    pool = await get_sys_pool()
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                "DELETE FROM ratings "
                "WHERE article_type = %s AND article_slug = %s "
                "AND author_name = %s",
                (article_type, article_slug, author_name),
            )
            return cur.rowcount > 0


async def get_all_ratings(
    article_type: str, article_slug: str
) -> list[dict]:
    """
    获取文章的所有用户评分详情（按时间倒序）。

    参数:
        article_type: 文章类型标识
        article_slug: 文章 slug

    返回:
        评分详情列表
    """
    pool = await get_sys_pool()
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                "SELECT author_name, score, created_at "
                "FROM ratings "
                "WHERE article_type = %s AND article_slug = %s "
                "ORDER BY created_at DESC",
                (article_type, article_slug),
            )
            rows = await cur.fetchall()
            results = []
            for row in rows:
                item = row_to_dict(row, cur)
                if "score" in item and item["score"] is not None:
                    item["score"] = float(item["score"])
                results.append(item)
            return results

"""
评论管理模块 — 文章评论与行评论的 CRUD。

支持两种评论方式:
    1. 全文评论 (comments 表):   对整篇文章的评论，无字数限制
    2. 行评论 (line_comments 表): 对文章特定行的短评，限 20 字

用法:
    from pykych.content.comments import get_comments, add_comment
    from pykych.content.comments import get_line_comments, add_line_comment
"""

from ..core.db import get_sys_pool, row_to_dict


# ═══════════════════════════════════════════════════════════════
# 全文评论
# ═══════════════════════════════════════════════════════════════


async def get_comments(article_type: str, article_slug: str) -> list[dict]:
    """
    获取指定文章的所有评论（按时间正序）。

    参数:
        article_type: 文章类型标识 ('md', 'wikidot', 'html', 'bbcode')
        article_slug: 文章 slug

    返回:
        评论字典列表 [{id, article_type, article_slug, author_name, content, created_at}, ...]
    """
    pool = await get_sys_pool()
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                "SELECT id, article_type, article_slug, author_name, "
                "content, created_at "
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
    """
    添加一条全文评论。

    参数:
        article_type: 文章类型标识
        article_slug: 文章 slug
        author_name:  评论者名称（登录用户使用昵称）
        content:      评论内容

    返回:
        新创建的评论字典
    """
    pool = await get_sys_pool()
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                "INSERT INTO comments "
                "(article_type, article_slug, author_name, content) "
                "VALUES (%s, %s, %s, %s)",
                (article_type, article_slug, author_name, content),
            )
            comment_id = cur.lastrowid
            await cur.execute(
                "SELECT id, article_type, article_slug, author_name, "
                "content, created_at "
                "FROM comments WHERE id = %s",
                (comment_id,),
            )
            row = await cur.fetchone()
            return row_to_dict(row, cur)


async def get_comment_count(article_type: str, article_slug: str) -> int:
    """
    获取指定文章的评论总数。

    参数:
        article_type: 文章类型标识
        article_slug: 文章 slug

    返回:
        评论数量
    """
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
    """
    删除一条评论。

    参数:
        comment_id: 评论 ID

    返回:
        True 表示删除成功，False 表示评论不存在
    """
    pool = await get_sys_pool()
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                "DELETE FROM comments WHERE id = %s",
                (comment_id,),
            )
            return cur.rowcount > 0


# ═══════════════════════════════════════════════════════════════
# 行评论（逐行短评，限 20 字）
# ═══════════════════════════════════════════════════════════════


async def get_line_comments(
    article_type: str, article_slug: str
) -> list[dict]:
    """
    获取指定文章的所有行评论（按行号、时间正序）。

    参数:
        article_type: 文章类型标识
        article_slug: 文章 slug

    返回:
        行评论列表 [{id, line_number, author_name, content, created_at}, ...]
    """
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
    """
    获取指定文章某一行的所有行评论。

    参数:
        article_type: 文章类型标识
        article_slug: 文章 slug
        line_number:  行号

    返回:
        该行的评论列表
    """
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
    """
    获取文章每行的评论数量。

    参数:
        article_type: 文章类型标识
        article_slug: 文章 slug

    返回:
        {line_number: count} 字典
    """
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
    """
    添加一条行评论（自动截断至 20 字）。

    参数:
        article_type: 文章类型标识
        article_slug: 文章 slug
        line_number:  行号
        author_name:  评论者名称
        content:      评论内容（超过 20 字会自动截断）

    返回:
        新创建的行评论字典

    异常:
        ValueError: 内容为空时抛出
    """
    content = content.strip()[:20]
    if not content:
        raise ValueError("行评论内容不能为空")

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
    """
    删除一条行评论。

    参数:
        comment_id: 行评论 ID

    返回:
        True 表示删除成功
    """
    pool = await get_sys_pool()
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                "DELETE FROM line_comments WHERE id = %s",
                (comment_id,),
            )
            return cur.rowcount > 0


# ═══════════════════════════════════════════════════════════════
# 统计
# ═══════════════════════════════════════════════════════════════


async def count_all_comments() -> int:
    """
    获取全站评论总数（全文评论 + 行评论）。

    返回:
        评论总数
    """
    pool = await get_sys_pool()
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                "SELECT (SELECT COUNT(*) FROM comments) + "
                "(SELECT COUNT(*) FROM line_comments) AS total"
            )
            row = await cur.fetchone()
            return row[0] if row else 0

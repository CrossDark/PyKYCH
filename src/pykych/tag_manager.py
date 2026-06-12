"""
标签管理模块 — 标签 CRUD、文章-标签关联查询。
"""

from typing import Optional

from .mysql_manager import _get_pool, row_to_dict


# ── 标签 CRUD ────────────────────────────────────────────────


async def get_or_create_tag(name: str) -> int:
    """获取标签 ID，不存在则创建。返回 tag_id。"""
    name = name.strip().lower()
    pool = await _get_pool()
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute("SELECT id FROM tags WHERE name = %s", (name,))
            row = await cur.fetchone()
            if row:
                return row[0]
            await cur.execute("INSERT INTO tags (name) VALUES (%s)", (name,))
            return cur.lastrowid


async def get_all_tags() -> list[dict]:
    """获取所有标签（按名称排序）。"""
    pool = await _get_pool()
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                "SELECT id, name, created_at FROM tags ORDER BY name"
            )
            rows = await cur.fetchall()
            return [row_to_dict(r, cur) for r in rows]


async def get_tag_by_name(name: str) -> Optional[dict]:
    """根据名称获取标签。"""
    pool = await _get_pool()
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                "SELECT id, name, created_at FROM tags WHERE name = %s", (name,)
            )
            row = await cur.fetchone()
            return row_to_dict(row, cur) if row else None


# ── 文章-标签关联 ────────────────────────────────────────────


async def add_tag_to_article(article_type: str, slug: str, tag_name: str) -> None:
    """为文章添加标签。"""
    tag_id = await get_or_create_tag(tag_name)
    pool = await _get_pool()
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            try:
                await cur.execute(
                    "INSERT INTO article_tags (article_type, article_slug, tag_id) "
                    "VALUES (%s, %s, %s)",
                    (article_type, slug, tag_id),
                )
            except Exception:
                pass  # 忽略重复


async def remove_tag_from_article(article_type: str, slug: str, tag_name: str) -> None:
    """从文章移除标签。"""
    pool = await _get_pool()
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                "DELETE at FROM article_tags at "
                "JOIN tags t ON at.tag_id = t.id "
                "WHERE at.article_type = %s AND at.article_slug = %s AND t.name = %s",
                (article_type, slug, tag_name.strip().lower()),
            )


async def get_tags_for_article(article_type: str, slug: str) -> list[dict]:
    """获取文章的所有标签。"""
    pool = await _get_pool()
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                "SELECT t.id, t.name, t.created_at "
                "FROM tags t "
                "JOIN article_tags at ON t.id = at.tag_id "
                "WHERE at.article_type = %s AND at.article_slug = %s "
                "ORDER BY t.name",
                (article_type, slug),
            )
            rows = await cur.fetchall()
            return [row_to_dict(r, cur) for r in rows]


async def set_article_tags(article_type: str, slug: str, tag_names: list[str]) -> None:
    """设置文章标签（先清空再添加）。"""
    pool = await _get_pool()
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            # 清空现有标签
            await cur.execute(
                "DELETE FROM article_tags WHERE article_type = %s AND article_slug = %s",
                (article_type, slug),
            )
        # 添加新标签
        for name in tag_names:
            name = name.strip()
            if name:
                await add_tag_to_article(article_type, slug, name)


async def get_articles_by_tag(
    tag_name: str, page: int = 1, per_page: int = 10
) -> dict:
    """获取含有指定标签的所有文章（合并 md 和 wikidot）。"""
    tag = await get_tag_by_name(tag_name.strip().lower())
    if not tag:
        return {"articles": [], "total": 0, "page": page, "per_page": per_page, "total_pages": 0, "tag": None}

    pool = await _get_pool()
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            # 统计总数
            await cur.execute(
                "SELECT COUNT(*) FROM article_tags WHERE tag_id = %s", (tag["id"],)
            )
            total = (await cur.fetchone())[0]

            offset = (page - 1) * per_page

            # 合并查询：md / wikidot / html 三种文章类型
            await cur.execute(
                "SELECT at.article_type, at.article_slug, "
                "COALESCE(a.title, p.title, h.title) AS title, "
                "COALESCE(a.created_at, p.created_at, h.created_at) AS created_at, "
                "COALESCE(a.updated_at, p.updated_at, h.updated_at) AS updated_at "
                "FROM article_tags at "
                "LEFT JOIN articles a ON at.article_type = 'md' AND at.article_slug = a.slug "
                "LEFT JOIN pages p ON at.article_type = 'wikidot' AND at.article_slug = p.slug "
                "LEFT JOIN html_pages h ON at.article_type = 'html' AND at.article_slug = h.slug "
                "WHERE at.tag_id = %s "
                "ORDER BY created_at DESC "
                "LIMIT %s OFFSET %s",
                (tag["id"], per_page, offset),
            )
            rows = await cur.fetchall()
            articles = [row_to_dict(r, cur) for r in rows]

    return {
        "articles": articles,
        "total": total,
        "page": page,
        "per_page": per_page,
        "total_pages": max(1, (total + per_page - 1) // per_page),
        "tag": tag,
    }


async def auto_tag_article(article_type: str, slug: str) -> None:
    """自动为文章添加默认标签（md 文章添加 'md'，wikidot 添加 'wikidot'）。"""
    type_tag_map = {"md": "md", "wikidot": "wikidot", "html": "html"}
    default_tag = type_tag_map.get(article_type)
    if default_tag:
        await add_tag_to_article(article_type, slug, default_tag)

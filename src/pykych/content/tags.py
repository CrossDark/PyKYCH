"""
标签管理模块 — 标签 CRUD、文章-标签关联。

标签是文章的轻量分类系统，每个文章可以有多个标签。
默认标签（如 'md', 'wikidot'）由系统自动添加。

用法:
    from pykych.content.tags import get_all_tags, set_article_tags
"""

from ..core.db import _get_pool, row_to_dict


# ── 标签 CRUD ────────────────────────────────────────────────


async def get_or_create_tag(name: str) -> int:
    """
    获取标签 ID，不存在则自动创建。

    标签名会自动转为小写并去除首尾空白。

    参数:
        name: 标签名称

    返回:
        标签的数据库 ID
    """
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
    """
    获取所有标签（按名称排序）。

    返回:
        标签字典列表 [{id, name, created_at}, ...]
    """
    pool = await _get_pool()
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                "SELECT id, name, created_at FROM tags ORDER BY name"
            )
            rows = await cur.fetchall()
            return [row_to_dict(r, cur) for r in rows]


async def get_tag_by_name(name: str) -> dict | None:
    """
    根据名称查找标签。

    参数:
        name: 标签名称

    返回:
        标签字典或 None
    """
    pool = await _get_pool()
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                "SELECT id, name, created_at FROM tags WHERE name = %s",
                (name,),
            )
            row = await cur.fetchone()
            return row_to_dict(row, cur) if row else None


async def get_all_tags_with_counts() -> list[dict]:
    """
    获取所有标签及其关联文章数量。

    返回:
        [{id, name, created_at, count}, ...]
    """
    pool = await _get_pool()
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                "SELECT t.id, t.name, t.created_at, "
                "COUNT(at.tag_id) as cnt "
                "FROM tags t "
                "LEFT JOIN article_tags at ON t.id = at.tag_id "
                "GROUP BY t.id, t.name, t.created_at "
                "ORDER BY t.name"
            )
            rows = await cur.fetchall()
            return [row_to_dict(r, cur) for r in rows]


async def create_tag(name: str) -> dict:
    """
    创建新标签。

    参数:
        name: 标签名称

    返回:
        新创建的标签字典
    """
    tag_id = await get_or_create_tag(name)
    return await get_tag_by_name(name)


async def rename_tag(tag_id: int, new_name: str) -> bool:
    """
    重命名标签。

    参数:
        tag_id:   标签 ID
        new_name: 新名称

    返回:
        True 表示成功
    """
    new_name = new_name.strip().lower()
    if not new_name:
        return False
    pool = await _get_pool()
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                "UPDATE tags SET name = %s WHERE id = %s",
                (new_name, tag_id),
            )
            return cur.rowcount > 0


async def delete_tag(tag_id: int) -> bool:
    """
    删除标签（级联删除关联）。

    参数:
        tag_id: 标签 ID

    返回:
        True 表示成功
    """
    pool = await _get_pool()
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute("DELETE FROM tags WHERE id = %s", (tag_id,))
            return cur.rowcount > 0


# ── 文章-标签关联 ────────────────────────────────────────────


async def auto_tag_article(article_type: str, slug: str) -> None:
    """
    为文章自动添加默认类型标签。

    由系统在创建文章时自动调用。

    参数:
        article_type: 文章类型标识（同时也是默认标签名）
        slug:         文章 slug
    """
    await add_tag_to_article(article_type, slug, article_type)


async def add_tag_to_article(
    article_type: str, slug: str, tag_name: str
) -> None:
    """
    为文章添加标签（忽略重复）。

    参数:
        article_type: 文章类型标识
        slug:         文章 slug
        tag_name:     标签名称
    """
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


async def remove_tag_from_article(
    article_type: str, slug: str, tag_name: str
) -> None:
    """
    从文章移除标签。

    参数:
        article_type: 文章类型标识
        slug:         文章 slug
        tag_name:     要移除的标签名称
    """
    pool = await _get_pool()
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                "DELETE at FROM article_tags at "
                "JOIN tags t ON at.tag_id = t.id "
                "WHERE at.article_type = %s AND at.article_slug = %s "
                "AND t.name = %s",
                (article_type, slug, tag_name.strip().lower()),
            )


async def get_tags_for_article(
    article_type: str, slug: str
) -> list[dict]:
    """
    获取文章的所有标签。

    参数:
        article_type: 文章类型标识
        slug:         文章 slug

    返回:
        标签字典列表
    """
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


async def set_article_tags(
    article_type: str, slug: str, tag_names: list[str]
) -> None:
    """
    设置文章的全部标签（替换现有标签）。

    先删除所有旧标签，再逐一添加新标签。

    参数:
        article_type: 文章类型标识
        slug:         文章 slug
        tag_names:    标签名称列表
    """
    pool = await _get_pool()
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            # 删除旧标签
            await cur.execute(
                "DELETE FROM article_tags "
                "WHERE article_type = %s AND article_slug = %s",
                (article_type, slug),
            )
    # 添加新标签
    for name in tag_names:
        name = name.strip().lower()
        if name:
            await add_tag_to_article(article_type, slug, name)


async def get_articles_by_tag(
    tag_name: str, page: int = 1, per_page: int = 10
) -> dict:
    """
    获取带有指定标签的所有文章（支持分页）。

    参数:
        tag_name: 标签名称
        page:     页码
        per_page: 每页条数

    返回:
        {tag, articles, total, page, per_page, total_pages}
    """
    tag = await get_tag_by_name(tag_name)
    if not tag:
        return {
            "tag": None, "articles": [],
            "total": 0, "page": 1,
            "per_page": per_page, "total_pages": 0,
        }

    pool = await _get_pool()
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            offset = (page - 1) * per_page

            # 使用 UNION ALL 跨表查询
            await cur.execute(
                "SELECT at.article_type, at.article_slug "
                "FROM article_tags at "
                "WHERE at.tag_id = %s "
                "ORDER BY at.id DESC LIMIT %s OFFSET %s",
                (tag["id"], per_page, offset),
            )
            rows = await cur.fetchall()

            await cur.execute(
                "SELECT COUNT(*) FROM article_tags WHERE tag_id = %s",
                (tag["id"],),
            )
            total = (await cur.fetchone())[0]

        articles = []
        for row in rows:
            atype, slug = row
            # 从对应表获取标题
            table_map = {
                "md": "articles",
                "wikidot": "pages",
                "html": "html_pages",
                "bbcode": "bbcode_pages",
            }
            table = table_map.get(atype)
            if table:
                async with conn.cursor() as cur2:
                    await cur2.execute(
                        f"SELECT title, created_at FROM {table} WHERE slug = %s",
                        (slug,),
                    )
                    info = await cur2.fetchone()
                    if info:
                        articles.append({
                            "type": atype,
                            "slug": slug,
                            "title": info[0],
                            "created_at": str(info[1])[:10] if info[1] else "",
                            "url_prefix": {
                                "md": "/md/",
                                "wikidot": "/wikidot/",
                                "html": "/html/local/",
                                "bbcode": "/bbcode/",
                            }.get(atype, "/"),
                        })

    return {
        "tag": tag,
        "articles": articles,
        "total": total,
        "page": page,
        "per_page": per_page,
        "total_pages": max(1, (total + per_page - 1) // per_page),
    }

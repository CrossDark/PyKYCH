"""
标签管理模块 — 标签 CRUD、文章-标签关联。

标签是文章的轻量分类系统，每个文章可以有多个标签。
默认标签（如 'md', 'wikidot'）由系统自动添加。

用法:
    from pykych.content.tags import get_all_tags, set_article_tags
"""

from ..core.db import _get_pool, row_to_dict

# ── 文章类型 → 表名 映射 ──────────────────────────────────────
_TYPE_TABLE_MAP = {
    "md": "articles",
    "wikidot": "pages",
    "html": "html_pages",
    "bbcode": "bbcode_pages",
}

# ── 文章类型 → URL 前缀 映射 ─────────────────────────────────
_TYPE_URL_MAP = {
    "md": "/md",
    "wikidot": "/wikidot",
    "html": "/html/local",
    "bbcode": "/bbcode",
}


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
    if not name:
        raise ValueError("标签名称不能为空")
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
    name = name.strip().lower()
    if not name:
        return None
    pool = await _get_pool()
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                "SELECT id, name, created_at FROM tags WHERE name = %s",
                (name,),
            )
            row = await cur.fetchone()
            return row_to_dict(row, cur) if row else None


async def get_tag_by_id(tag_id: int) -> dict | None:
    """根据 ID 获取标签。"""
    pool = await _get_pool()
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                "SELECT id, name, created_at FROM tags WHERE id = %s",
                (tag_id,),
            )
            row = await cur.fetchone()
            return row_to_dict(row, cur) if row else None


async def get_all_tags_with_counts() -> list[dict]:
    """
    获取所有标签及其关联的"真实存在"文章数量。

    通过子查询验证 article_tags 关联的文章确实存在于对应的文章表中，
    避免统计已删除但关联未清理的孤立记录。

    返回:
        [{id, name, created_at, count}, ...]
    """
    pool = await _get_pool()
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                """
                SELECT t.id, t.name, t.created_at,
                       SUM(
                           CASE
                               WHEN at.article_type = 'md' AND EXISTS(SELECT 1 FROM articles a WHERE a.slug = at.article_slug) THEN 1
                               WHEN at.article_type = 'wikidot' AND EXISTS(SELECT 1 FROM pages p WHERE p.slug = at.article_slug) THEN 1
                               WHEN at.article_type = 'html' AND EXISTS(SELECT 1 FROM html_pages h WHERE h.slug = at.article_slug) THEN 1
                               WHEN at.article_type = 'bbcode' AND EXISTS(SELECT 1 FROM bbcode_pages b WHERE b.slug = at.article_slug) THEN 1
                               ELSE 0
                           END
                       ) as cnt
                FROM tags t
                LEFT JOIN article_tags at ON t.id = at.tag_id
                GROUP BY t.id, t.name, t.created_at
                ORDER BY t.name
                """
            )
            rows = await cur.fetchall()
            result = []
            for r in rows:
                d = row_to_dict(r, cur)
                d["count"] = d.pop("cnt", 0)
                result.append(d)
            return result


async def create_tag(name: str) -> dict | None:
    """
    创建新标签（如已存在则返回已有标签）。

    参数:
        name: 标签名称

    返回:
        标签字典或 None
    """
    name = name.strip().lower()
    if not name:
        return None
    tag_id = await get_or_create_tag(name)
    return await get_tag_by_id(tag_id)


async def rename_tag(tag_id: int, new_name: str) -> bool:
    """
    重命名标签。会检查新名是否已被占用。

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
            # 检查新名称是否已被其他标签占用
            await cur.execute(
                "SELECT id FROM tags WHERE name = %s AND id != %s",
                (new_name, tag_id),
            )
            if await cur.fetchone():
                return False
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
    if article_type in _TYPE_TABLE_MAP:
        await add_tag_to_article(article_type, slug, article_type)


async def add_tag_to_article(
    article_type: str, slug: str, tag_name: str
) -> bool:
    """
    为文章添加标签（忽略重复）。

    参数:
        article_type: 文章类型标识
        slug:         文章 slug
        tag_name:     标签名称

    返回:
        True 表示添加成功，False 表示重复忽略
    """
    tag_name = tag_name.strip().lower()
    if not tag_name:
        return False
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
                return True
            except Exception:
                return False  # 忽略重复


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
    tag_name = tag_name.strip().lower()
    if not tag_name:
        return
    pool = await _get_pool()
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                "DELETE at FROM article_tags at "
                "JOIN tags t ON at.tag_id = t.id "
                "WHERE at.article_type = %s AND at.article_slug = %s "
                "AND t.name = %s",
                (article_type, slug, tag_name),
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
        标签字典列表 [{id, name, created_at}, ...]
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

    所有操作在单次数据库连接中完成，确保原子性。

    参数:
        article_type: 文章类型标识
        slug:         文章 slug
        tag_names:    标签名称列表
    """
    # 预处理：去重、去空白、小写
    cleaned = []
    seen = set()
    for name in tag_names:
        n = name.strip().lower()
        if n and n not in seen:
            cleaned.append(n)
            seen.add(n)

    pool = await _get_pool()
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            # 1. 删除旧标签关联
            await cur.execute(
                "DELETE FROM article_tags "
                "WHERE article_type = %s AND article_slug = %s",
                (article_type, slug),
            )
            # 2. 逐个添加新标签（使用同一连接）
            for tag_name in cleaned:
                # 获取或创建标签
                await cur.execute(
                    "SELECT id FROM tags WHERE name = %s", (tag_name,)
                )
                row = await cur.fetchone()
                if row:
                    tag_id = row[0]
                else:
                    await cur.execute(
                        "INSERT INTO tags (name) VALUES (%s)", (tag_name,)
                    )
                    tag_id = cur.lastrowid
                # 建立关联
                try:
                    await cur.execute(
                        "INSERT INTO article_tags "
                        "(article_type, article_slug, tag_id) "
                        "VALUES (%s, %s, %s)",
                        (article_type, slug, tag_id),
                    )
                except Exception:
                    pass  # 重复则忽略


async def get_articles_by_tag(
    tag_name: str, page: int = 1, per_page: int = 10
) -> dict:
    """
    获取带有指定标签的所有文章（支持分页，单次 JOIN 查询）。

    参数:
        tag_name: 标签名称
        page:     页码（从 1 开始）
        per_page: 每页条数

    返回:
        {tag, articles, total, page, per_page, total_pages}
        articles 中每项: {article_type, article_slug, title, created_at, updated_at}
    """
    tag_name = tag_name.strip().lower()
    tag = await get_tag_by_name(tag_name)
    if not tag:
        return {
            "tag": None, "articles": [],
            "total": 0, "page": page,
            "per_page": per_page, "total_pages": 0,
        }

    pool = await _get_pool()
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            # 统计真实存在的文章数（排除已删除但关联残留的记录）
            await cur.execute(
                """
                SELECT COUNT(*) FROM article_tags at
                WHERE at.tag_id = %s
                  AND (
                    (at.article_type = 'md' AND EXISTS(SELECT 1 FROM articles a WHERE a.slug = at.article_slug))
                    OR (at.article_type = 'wikidot' AND EXISTS(SELECT 1 FROM pages p WHERE p.slug = at.article_slug))
                    OR (at.article_type = 'html' AND EXISTS(SELECT 1 FROM html_pages h WHERE h.slug = at.article_slug))
                    OR (at.article_type = 'bbcode' AND EXISTS(SELECT 1 FROM bbcode_pages b WHERE b.slug = at.article_slug))
                  )
                """,
                (tag["id"],),
            )
            total = (await cur.fetchone())[0]

            if total == 0:
                return {
                    "tag": tag, "articles": [],
                    "total": 0, "page": page,
                    "per_page": per_page, "total_pages": 0,
                }

            offset = (page - 1) * per_page

            # 使用 LEFT JOIN 一次性跨四表查询，避免 N+1 问题
            await cur.execute(
                "SELECT "
                "  at.article_type, "
                "  at.article_slug, "
                "  COALESCE(a.title, p.title, h.title, b.title) AS title, "
                "  COALESCE(a.created_at, p.created_at, h.created_at, b.created_at) AS created_at, "
                "  COALESCE(a.updated_at, p.updated_at, h.updated_at, b.updated_at) AS updated_at "
                "FROM article_tags at "
                "LEFT JOIN articles a "
                "  ON at.article_type = 'md' AND at.article_slug = a.slug "
                "LEFT JOIN pages p "
                "  ON at.article_type = 'wikidot' AND at.article_slug = p.slug "
                "LEFT JOIN html_pages h "
                "  ON at.article_type = 'html' AND at.article_slug = h.slug "
                "LEFT JOIN bbcode_pages b "
                "  ON at.article_type = 'bbcode' AND at.article_slug = b.slug "
                "WHERE at.tag_id = %s "
                "ORDER BY at.id DESC "
                "LIMIT %s OFFSET %s",
                (tag["id"], per_page, offset),
            )
            rows = await cur.fetchall()

        articles = []
        for row in rows:
            article_type, article_slug, title, created_at, updated_at = row
            # 跳过已删除但关联仍然存在的文章（title 为 NULL）
            if title is None:
                continue
            articles.append({
                "article_type": article_type,
                "article_slug": article_slug,
                "title": title,
                "created_at": str(created_at) if created_at else "",
                "updated_at": str(updated_at) if updated_at else "",
            })

    return {
        "tag": tag,
        "articles": articles,
        "total": total,
        "page": page,
        "per_page": per_page,
        "total_pages": max(1, (total + per_page - 1) // per_page),
    }


async def cleanup_orphan_tags() -> int:
    """
    清理没有任何文章关联的孤立标签。

    返回:
        删除的标签数量
    """
    pool = await _get_pool()
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                "DELETE FROM tags WHERE id NOT IN "
                "(SELECT DISTINCT tag_id FROM article_tags)"
            )
            return cur.rowcount


async def cleanup_orphan_article_tags() -> int:
    """
    清理 article_tags 中指向已删除文章的孤立关联记录。

    返回:
        清理的 article_tags 记录数量
    """
    pool = await _get_pool()
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                """
                DELETE FROM article_tags
                WHERE (article_type = 'md' AND NOT EXISTS(
                    SELECT 1 FROM articles a WHERE a.slug = article_slug
                ))
                OR (article_type = 'wikidot' AND NOT EXISTS(
                    SELECT 1 FROM pages p WHERE p.slug = article_slug
                ))
                OR (article_type = 'html' AND NOT EXISTS(
                    SELECT 1 FROM html_pages h WHERE h.slug = article_slug
                ))
                OR (article_type = 'bbcode' AND NOT EXISTS(
                    SELECT 1 FROM bbcode_pages b WHERE b.slug = article_slug
                ))
                """
            )
            return cur.rowcount

"""
站点设置数据层 — 子站点链接 & 主页推荐文章管理。
"""

from typing import Optional
from .mysql_manager import get_sys_pool, row_to_dict


# ═══════════════════════════════════════════════════════════
#  子站点链接
# ═══════════════════════════════════════════════════════════

async def list_subsite_links() -> list[dict]:
    """获取所有子站点链接（按 sort_order 排序）。"""
    pool = await get_sys_pool()
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                "SELECT id, name, url, description, sort_order, created_at "
                "FROM subsite_links ORDER BY sort_order ASC, id ASC"
            )
            rows = await cur.fetchall()
            return [row_to_dict(r, cur) for r in rows]


async def get_subsite_link(link_id: int) -> Optional[dict]:
    """获取单条子站点链接。"""
    pool = await get_sys_pool()
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                "SELECT id, name, url, description, sort_order, created_at "
                "FROM subsite_links WHERE id = %s",
                (link_id,),
            )
            row = await cur.fetchone()
            return row_to_dict(row, cur) if row else None


async def create_subsite_link(
    name: str, url: str, description: str = "", sort_order: int = 0
) -> dict:
    """创建子站点链接。"""
    pool = await get_sys_pool()
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                "INSERT INTO subsite_links (name, url, description, sort_order) "
                "VALUES (%s, %s, %s, %s)",
                (name, url, description, sort_order),
            )
            link_id = cur.lastrowid
            await cur.execute(
                "SELECT id, name, url, description, sort_order, created_at "
                "FROM subsite_links WHERE id = %s",
                (link_id,),
            )
            return row_to_dict(await cur.fetchone(), cur)


async def update_subsite_link(
    link_id: int,
    name: str,
    url: str,
    description: str = "",
    sort_order: int = 0,
) -> bool:
    """更新子站点链接。返回是否成功。"""
    pool = await get_sys_pool()
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                "UPDATE subsite_links SET name=%s, url=%s, description=%s, sort_order=%s "
                "WHERE id=%s",
                (name, url, description, sort_order, link_id),
            )
            return cur.rowcount > 0


async def delete_subsite_link(link_id: int) -> bool:
    """删除子站点链接。"""
    pool = await get_sys_pool()
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute("DELETE FROM subsite_links WHERE id = %s", (link_id,))
            return cur.rowcount > 0


# ═══════════════════════════════════════════════════════════
#  主页推荐文章
# ═══════════════════════════════════════════════════════════

async def list_featured_articles() -> list[dict]:
    """获取所有推荐文章（按 sort_order 排序），补全文章标题。"""
    pool = await get_sys_pool()
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                "SELECT id, article_type, article_slug, sort_order, created_at "
                "FROM featured_articles ORDER BY sort_order ASC, id ASC"
            )
            rows = await cur.fetchall()
            # 立即转换所有行（在 cur.description 被覆盖前）
            items = [row_to_dict(r, cur) for r in rows]

        # 使用新连接补全标题（避免游标描述被覆盖）
        for item in items:
            title = await _get_article_title_by_pool(pool, item["article_type"], item["article_slug"])
            item["title"] = title or item["article_slug"]
            item["url"] = _article_url(item["article_type"], item["article_slug"])
        return items


async def add_featured_article(article_type: str, article_slug: str) -> Optional[dict]:
    """添加推荐文章。返回新记录或 None（已存在/文章不存在）。"""
    pool = await get_sys_pool()
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            # 验证文章存在
            title = await _get_article_title_on_conn(conn, article_type, article_slug)
            if title is None:
                return None

            # 获取当前最大 sort_order
            await cur.execute(
                "SELECT COALESCE(MAX(sort_order), 0) FROM featured_articles"
            )
            max_order = (await cur.fetchone())[0]

            try:
                await cur.execute(
                    "INSERT INTO featured_articles (article_type, article_slug, sort_order) "
                    "VALUES (%s, %s, %s)",
                    (article_type, article_slug, max_order + 1),
                )
                item_id = cur.lastrowid
                await cur.execute(
                    "SELECT id, article_type, article_slug, sort_order, created_at "
                    "FROM featured_articles WHERE id = %s",
                    (item_id,),
                )
                item = row_to_dict(await cur.fetchone(), cur)
                item["title"] = title
                item["url"] = _article_url(article_type, article_slug)
                return item
            except Exception:
                return None  # 已存在


async def remove_featured_article(featured_id: int) -> bool:
    """移除推荐文章。"""
    pool = await get_sys_pool()
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                "DELETE FROM featured_articles WHERE id = %s", (featured_id,)
            )
            return cur.rowcount > 0


async def move_featured_article(featured_id: int, direction: str) -> bool:
    """上移/下移推荐文章排序。"""
    pool = await get_sys_pool()
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                "SELECT id, sort_order FROM featured_articles WHERE id = %s",
                (featured_id,),
            )
            row = await cur.fetchone()
            if not row:
                return False

            current_order = row[1]
            if direction == "up":
                await cur.execute(
                    "SELECT id, sort_order FROM featured_articles "
                    "WHERE sort_order < %s ORDER BY sort_order DESC LIMIT 1",
                    (current_order,),
                )
            else:
                await cur.execute(
                    "SELECT id, sort_order FROM featured_articles "
                    "WHERE sort_order > %s ORDER BY sort_order ASC LIMIT 1",
                    (current_order,),
                )
            other = await cur.fetchone()
            if not other:
                return False

            # 交换 sort_order
            await cur.execute(
                "UPDATE featured_articles SET sort_order = %s WHERE id = %s",
                (other[1], featured_id),
            )
            await cur.execute(
                "UPDATE featured_articles SET sort_order = %s WHERE id = %s",
                (current_order, other[0]),
            )
            return True


# ═══════════════════════════════════════════════════════════
#  工具函数
# ═══════════════════════════════════════════════════════════

TABLE_MAP = {
    "md": "articles",
    "wikidot": "pages",
    "html": "html_pages",
    "bbcode": "bbcode_pages",
}

URL_MAP = {
    "md": "/md/{slug}",
    "wikidot": "/wikidot/{slug}",
    "html": "/html/local/{slug}",
    "bbcode": "/bbcode/{slug}",
}


async def _get_article_title_on_conn(conn, article_type: str, article_slug: str) -> Optional[str]:
    """查询文章标题（使用已有连接，新建游标）。"""
    table = TABLE_MAP.get(article_type)
    if not table:
        return None
    try:
        async with conn.cursor() as cur:
            await cur.execute(
                f"SELECT title FROM {table} WHERE slug = %s LIMIT 1",
                (article_slug,),
            )
            row = await cur.fetchone()
            return row[0] if row else None
    except Exception:
        return None


async def _get_article_title_by_pool(pool, article_type: str, article_slug: str) -> Optional[str]:
    """查询文章标题（使用连接池）。"""
    table = TABLE_MAP.get(article_type)
    if not table:
        return None
    try:
        async with pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    f"SELECT title FROM {table} WHERE slug = %s LIMIT 1",
                    (article_slug,),
                )
                row = await cur.fetchone()
                return row[0] if row else None
    except Exception:
        return None


def _article_url(article_type: str, slug: str) -> str:
    """生成文章访问 URL。"""
    pattern = URL_MAP.get(article_type, "/{slug}")
    return pattern.format(slug=slug)

"""
MySQL 数据库模块 — 管理 BBCode 文章的存储与查询。
配置来自 settings/db.yaml，通过 mysql_manager 获取连接池。
"""

from typing import Optional

from .mysql_manager import get_md_pool, row_to_dict
from . import tag_manager


async def list_pages(page: int = 1, per_page: int = 10) -> dict:
    """分页获取 BBCode 页面列表（按创建时间倒序）。"""
    pool = await get_md_pool()
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            offset = (page - 1) * per_page
            await cur.execute(
                "SELECT id, slug, title, author_id, created_at, updated_at "
                "FROM bbcode_pages ORDER BY created_at DESC LIMIT %s OFFSET %s",
                (per_page, offset),
            )
            rows = await cur.fetchall()
            pages = [row_to_dict(r, cur) for r in rows]

            await cur.execute("SELECT COUNT(*) FROM bbcode_pages")
            total = (await cur.fetchone())[0]

    return {
        "pages": pages,
        "total": total,
        "page": page,
        "per_page": per_page,
        "total_pages": max(1, (total + per_page - 1) // per_page),
    }


async def get_page_by_slug(slug: str) -> Optional[dict]:
    """根据 slug 获取 BBCode 页面。"""
    pool = await get_md_pool()
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                "SELECT * FROM bbcode_pages WHERE slug = %s", (slug,)
            )
            row = await cur.fetchone()
            return row_to_dict(row, cur) if row else None


async def get_pages_by_author(
    author_id: int, page: int = 1, per_page: int = 10
) -> dict:
    """获取指定作者的 BBCode 页面列表。"""
    pool = await get_md_pool()
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            offset = (page - 1) * per_page
            await cur.execute(
                "SELECT id, slug, title, author_id, created_at, updated_at "
                "FROM bbcode_pages WHERE author_id = %s "
                "ORDER BY created_at DESC LIMIT %s OFFSET %s",
                (author_id, per_page, offset),
            )
            rows = await cur.fetchall()
            pages = [row_to_dict(r, cur) for r in rows]

            await cur.execute(
                "SELECT COUNT(*) FROM bbcode_pages WHERE author_id = %s",
                (author_id,),
            )
            total = (await cur.fetchone())[0]

    return {
        "pages": pages,
        "total": total,
        "page": page,
        "per_page": per_page,
        "total_pages": max(1, (total + per_page - 1) // per_page),
    }


async def create_page(
    slug: str, title: str, content: str, author_id: int = None
) -> dict:
    """创建新的 BBCode 页面。"""
    pool = await get_md_pool()
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                "INSERT INTO bbcode_pages (slug, title, content, author_id) "
                "VALUES (%s, %s, %s, %s)",
                (slug, title, content, author_id),
            )
            # 自动添加 bbcode 标签
            await tag_manager.auto_tag_article("bbcode", slug)
            return await get_page_by_slug(slug)


async def update_page(
    slug: str, title: str, content: str
) -> Optional[dict]:
    """更新已有 BBCode 页面。"""
    pool = await get_md_pool()
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                "UPDATE bbcode_pages SET title = %s, content = %s "
                "WHERE slug = %s",
                (title, content, slug),
            )
            if cur.rowcount == 0:
                return None
            return await get_page_by_slug(slug)


async def delete_page(slug: str) -> bool:
    """删除 BBCode 页面。"""
    pool = await get_md_pool()
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                "DELETE FROM bbcode_pages WHERE slug = %s", (slug,)
            )
            return cur.rowcount > 0


# ── 种子数据 ──────────────────────────────────────────────

SEED_PAGES = [
    {
        "slug": "bbcode-demo",
        "title": "BBCode 语法演示",
        "content": """[center][size=large][b]BBCode 语法演示页面[/b][/size][/center]

[hr]

[anchor]intro[/anchor]
[color=#3b82f6][b]什么是 BBCode？[/b][/color]

BBCode（Bulletin Board Code）是一种轻量级标记语言，广泛用于论坛和社区中。它使用 [b]方括号[/b] 包裹标签来格式化文本。

[hr]

[b]一、文本格式化[/b]

这是 [b]粗体[/b] 文字，这是 [i]斜体[/i] 文字，这是 [u]下划线[/u] 文字。

还有 [s]删除线[/s]、上标 [sup]上标[/sup]、下标 [sub]下标[/sub]。

[hr]

[b]二、链接与图片[/b]

这是一个 [url=https://github.com]GitHub[/url] 链接。

也可以直接放 URL：[url]https://www.python.org/[/url]

联系方式：[email]example@example.com[/email]

插入图片：[img]https://www.python.org/static/img/python-logo.png[/img]

[hr]

[b]三、引用与代码[/b]

[quote=某位作者]
这是一段引用文字，通常用于回复或引用他人的内容。
[/quote]

Python 代码示例：

[code=python]
def hello():
    print("Hello, BBCode!")

hello()
[/code]

[hr]

[b]四、列表[/b]

无序列表：

[list]
[*]第一项
[*]第二项
[*]第三项
[/list]

有序列表：

[list=1]
[*]第一步：安装 Python
[*]第二步：创建虚拟环境
[*]第三步：安装依赖
[/list]

[hr]

[b]五、表格[/b]

[table]
[tr]
[th]名称[/th]
[th]版本[/th]
[th]描述[/th]
[/tr]
[tr]
[td]Python[/td]
[td]3.12[/td]
[td]编程语言[/td]
[/tr]
[tr]
[td]LiHiL[/td]
[td]latest[/td]
[td]Web 框架[/td]
[/tr]
[tr]
[td]aiomysql[/td]
[td]0.2.0[/td]
[td]异步 MySQL 驱动[/td]
[/tr]
[/table]

[hr]

[b]六、特殊效果[/b]

[color=red]红色文字[/color] [color=#3b82f6]蓝色文字[/color] [color=green]绿色文字[/color]

[size=small]小号文字[/size] [size=large]大号文字[/size]

[bg=yellow]黄色背景高亮[/bg]

[font=Courier New]等宽字体文字[/font]

[center]居中对齐的文字[/center]

[right]右对齐的文字[/right]

[hr]

[b]七、折叠内容[/b]

[spoiler=点击查看隐藏内容]
这里是隐藏的内容，点击标题即可展开查看。

支持 [b]粗体[/b] 和 [i]斜体[/i] 等格式。
[/spoiler]

[spoiler]
这是没有标题的折叠内容，默认显示 "Spoiler"。
[/spoiler]

[hr]

[center][size=small]—— 跨越晨昏 · BBCode 模块 ——[/size][/center]
""",
    },
]


async def seed_db() -> int:
    """写入种子数据（如不存在），返回已存在的数量。"""
    existing = 0
    for item in SEED_PAGES:
        existing_page = await get_page_by_slug(item["slug"])
        if existing_page:
            existing += 1
        else:
            await create_page(item["slug"], item["title"], item["content"])
    return existing

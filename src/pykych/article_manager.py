"""
统一文章管理器 — 为所有文章类型 (md/wikidot/html/bbcode) 提供统一的 CRUD 接口。
替代分散的 db.py, wikidot_db.py, html_db.py, bbcode_db.py。
"""

from typing import Optional
from datetime import datetime, timezone

from .mysql_manager import _get_pool, row_to_dict
from . import tag_manager

# ── 文章类型配置 ─────────────────────────────────────────────

ARTICLE_TYPES = {
    "md": {
        "label": "Markdown",
        "table": "articles",
        "list_cols": "id, slug, title, author_id, created_at, updated_at",
        "default_tag": "md",
        "url_prefix": "/md",
        "form_title_new": "新建 Markdown 文章",
        "form_title_edit": "编辑 Markdown 文章",
    },
    "wikidot": {
        "label": "Wikidot",
        "table": "pages",
        "list_cols": "id, slug, title, author_id, created_at, updated_at",
        "default_tag": "wikidot",
        "url_prefix": "/wikidot",
        "form_title_new": "新建 Wikidot 页面",
        "form_title_edit": "编辑 Wikidot 页面",
    },
    "html": {
        "label": "HTML",
        "table": "html_pages",
        "list_cols": "id, slug, title, author_id, created_at, updated_at",
        "default_tag": "html",
        "url_prefix": "/html/local",
        "form_title_new": "新建 HTML 页面",
        "form_title_edit": "编辑 HTML 页面",
    },
    "bbcode": {
        "label": "BBCode",
        "table": "bbcode_pages",
        "list_cols": "id, slug, title, author_id, created_at, updated_at",
        "default_tag": "bbcode",
        "url_prefix": "/bbcode",
        "form_title_new": "新建 BBCode 文章",
        "form_title_edit": "编辑 BBCode 文章",
    },
}


def get_article_config(article_type: str) -> dict:
    """获取文章类型配置。"""
    cfg = ARTICLE_TYPES.get(article_type)
    if cfg is None:
        raise ValueError(f"未知文章类型: {article_type}")
    return cfg


# ── 通用列表查询 ────────────────────────────────────────────


async def list_articles(
    article_type: str, page: int = 1, per_page: int = 10, author_id: int = None
) -> dict:
    """分页获取文章列表（按创建时间倒序）。可选按作者过滤。"""
    cfg = get_article_config(article_type)
    table = cfg["table"]
    list_cols = cfg["list_cols"]

    pool = await _get_pool()
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            offset = (page - 1) * per_page

            if author_id is not None:
                await cur.execute(
                    f"SELECT {list_cols} FROM {table} "
                    "WHERE author_id = %s ORDER BY created_at DESC LIMIT %s OFFSET %s",
                    (author_id, per_page, offset),
                )
                rows = await cur.fetchall()
                articles = [row_to_dict(r, cur) for r in rows]

                await cur.execute(
                    f"SELECT COUNT(*) FROM {table} WHERE author_id = %s", (author_id,)
                )
                total = (await cur.fetchone())[0]
            else:
                await cur.execute(
                    f"SELECT {list_cols} FROM {table} "
                    "ORDER BY created_at DESC LIMIT %s OFFSET %s",
                    (per_page, offset),
                )
                rows = await cur.fetchall()
                articles = [row_to_dict(r, cur) for r in rows]

                await cur.execute(f"SELECT COUNT(*) FROM {table}")
                total = (await cur.fetchone())[0]

    # 统一返回键名
    key = "pages" if article_type == "wikidot" else "articles"
    return {
        key: articles,
        "articles": articles,
        "total": total,
        "page": page,
        "per_page": per_page,
        "total_pages": max(1, (total + per_page - 1) // per_page),
    }


# ── 通用单条查询 ────────────────────────────────────────────


async def get_article(article_type: str, slug: str) -> Optional[dict]:
    """根据 slug 获取单篇文章。"""
    cfg = get_article_config(article_type)
    table = cfg["table"]

    pool = await _get_pool()
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute(f"SELECT * FROM {table} WHERE slug = %s", (slug,))
            row = await cur.fetchone()
            return row_to_dict(row, cur) if row else None


# ── 通用 CRUD ───────────────────────────────────────────────


async def create_article(
    article_type: str, slug: str, title: str, content: str, author_id: int = None
) -> dict:
    """创建新文章，自动添加默认类型标签。"""
    cfg = get_article_config(article_type)
    table = cfg["table"]
    default_tag = cfg["default_tag"]

    pool = await _get_pool()
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                f"INSERT INTO {table} (slug, title, content, author_id) "
                "VALUES (%s, %s, %s, %s)",
                (slug, title, content, author_id),
            )
            # 自动添加默认类型标签
            await tag_manager.auto_tag_article(article_type, slug)
            return await get_article(article_type, slug)


async def update_article(
    article_type: str, slug: str, title: str, content: str
) -> Optional[dict]:
    """更新已有文章。"""
    cfg = get_article_config(article_type)
    table = cfg["table"]

    pool = await _get_pool()
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                f"UPDATE {table} SET title = %s, content = %s WHERE slug = %s",
                (title, content, slug),
            )
            if cur.rowcount == 0:
                return None
            return await get_article(article_type, slug)


async def delete_article(article_type: str, slug: str) -> bool:
    """删除文章。"""
    cfg = get_article_config(article_type)
    table = cfg["table"]

    pool = await _get_pool()
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute(f"DELETE FROM {table} WHERE slug = %s", (slug,))
            return cur.rowcount > 0


# ── 种子数据 ─────────────────────────────────────────────────


async def seed_db(article_type: str) -> None:
    """为指定类型插入种子数据（如不存在）。"""
    cfg = get_article_config(article_type)
    table = cfg["table"]
    default_tag = cfg["default_tag"]

    seeds = {
        "md": [
            ("hello-world", "你好，世界！", "# 你好，世界！\n\n这是我的第一篇 Markdown 文章。\n\n## 关于本站\n\n欢迎来到「跨越晨昏」，这是我的个人网站。"),
        ],
        "wikidot": [
            ("syntax-test", "Wikidot 语法测试", "[[div]]\n= 这是 Wikidot 语法测试\n[[/div]]\n\n+ 标题 1\n++ 标题 2\n\n[[div class=\"wiki-collapsible\"]]\n[[collapsible show=\"展开\" hide=\"收起\"]]\n## 折叠内容\n这是折叠的内容。\n[[/collapsible]]\n[[/div]]\n\n> 这是引用块\n>> 嵌套引用\n\n* 无序列表\n* 无序列表 2\n\n# 有序列表\n# 有序列表 2\n\n[[code type=\"python\"]]\ndef hello():\n    print(\"Hello Wikidot!\")\n[[/code]]\n\n[[size 120%]]大号文字[[/size]]\n[[size 80%]]小号文字[[/size]]\n\n[[color red]]红色文字[[/color]]\n\n@@这是等宽字体@@\n\n##blue|蓝色标题##\n\n[[=]]\n居中文字\n[[/=]]\n\n[[<]]\n左对齐\n[[/<]]\n\n[[>]]\n右对齐\n[[/>]]\n\n普通^^上标^^\n普通,,下标,,\n\n----\n\n[[a myanchor]]\n这里是锚点\n[[/a]]\n\n[[image https://via.placeholder.com/150]]\n\n||~ 表头1 ||~ 表头2 ||\n|| 数据1 || 数据2 ||\n\n[[note]]\n这是一个备注。\n[[/note]]\n\n[[warning]]\n这是一个警告。\n[[/warning]]\n\n使用\\*\\*转义\\*\\*语法\n"),
        ],
        "html": [
            ("hello-html", "你好 HTML", "<h1>你好 HTML</h1>\n<p>这是一篇本地 HTML 文章。</p>\n<ul>\n  <li>项目 1</li>\n  <li>项目 2</li>\n</ul>"),
        ],
        "bbcode": [
            ("bbcode-demo", "BBCode 示例", "[b]粗体文字[/b]\n\n[i]斜体文字[/i]\n\n[u]下划线文字[/u]\n\n[s]删除线文字[/s]\n\n[color=red]红色文字[/color]\n\n[size=150]大号文字[/size]\n\n[center]居中文字[/center]\n\n[quote]这是一个引用[/quote]\n\n[code]\nprint('Hello BBCode!')\n[/code]\n\n[list]\n[*] 项目 1\n[*] 项目 2\n[/list]\n\n[table]\n[tr][th]列1[/th][th]列2[/th][/tr]\n[tr][td]A[/td][td]B[/td][/tr]\n[/table]\n\n[url=https://example.com]链接文字[/url]\n[img]https://via.placeholder.com/100[/img]\n\n[spoiler=点击展开]隐藏内容[/spoiler]\n\n[hr]\n\n换行测试：\n第一行[br]第二行\n"),
        ],
    }

    items = seeds.get(article_type, [])
    pool = await _get_pool()
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            for slug, title, content in items:
                await cur.execute(
                    f"SELECT id FROM {table} WHERE slug = %s", (slug,)
                )
                if await cur.fetchone():
                    continue
                await cur.execute(
                    f"INSERT INTO {table} (slug, title, content) VALUES (%s, %s, %s)",
                    (slug, title, content),
                )
                await tag_manager.auto_tag_article(article_type, slug)


# ── 向后兼容：保留旧模块接口 ──────────────────────────────────
# 以下函数为向后兼容而保留，新代码请直接使用统一接口。


async def list_md(page=1, per_page=10, author_id=None):
    return await list_articles("md", page, per_page, author_id)

async def get_md(slug):
    return await get_article("md", slug)

async def create_md(slug, title, content, author_id=None):
    return await create_article("md", slug, title, content, author_id)

async def update_md(slug, title, content):
    return await update_article("md", slug, title, content)

async def delete_md(slug):
    return await delete_article("md", slug)

async def seed_md():
    return await seed_db("md")


async def list_wikidot(page=1, per_page=10, author_id=None):
    return await list_articles("wikidot", page, per_page, author_id)

async def get_wikidot(slug):
    return await get_article("wikidot", slug)

async def create_wikidot(slug, title, content, author_id=None):
    return await create_article("wikidot", slug, title, content, author_id)

async def update_wikidot(slug, title, content):
    return await update_article("wikidot", slug, title, content)

async def delete_wikidot(slug):
    return await delete_article("wikidot", slug)

async def seed_wikidot():
    return await seed_db("wikidot")


async def list_html(page=1, per_page=10, author_id=None):
    return await list_articles("html", page, per_page, author_id)

async def get_html(slug):
    return await get_article("html", slug)

async def create_html(slug, title, content, author_id=None):
    return await create_article("html", slug, title, content, author_id)

async def update_html(slug, title, content):
    return await update_article("html", slug, title, content)

async def delete_html(slug):
    return await delete_article("html", slug)

async def seed_html():
    return await seed_db("html")


async def list_bbcode(page=1, per_page=10, author_id=None):
    return await list_articles("bbcode", page, per_page, author_id)

async def get_bbcode(slug):
    return await get_article("bbcode", slug)

async def create_bbcode(slug, title, content, author_id=None):
    return await create_article("bbcode", slug, title, content, author_id)

async def update_bbcode(slug, title, content):
    return await update_article("bbcode", slug, title, content)

async def delete_bbcode(slug):
    return await delete_article("bbcode", slug)

async def seed_bbcode():
    return await seed_db("bbcode")

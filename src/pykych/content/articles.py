"""
统一文章管理器 — 为所有文章类型提供统一 CRUD 接口。

支持的文章类型:
    - md:      Markdown 文章 (表: articles)
    - wikidot: Wikidot 页面  (表: pages)
    - html:    HTML 页面     (表: html_pages)
    - bbcode:  BBCode 文章   (表: bbcode_pages)

用法:
    from pykych.content.articles import list_articles, get_article, create_article
"""

from typing import Optional

from ..core.db import _get_pool, row_to_dict
from .tags import auto_tag_article

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
    "typst": {
        "label": "Typst",
        "table": "typst_pages",
        "list_cols": "id, slug, title, author_id, created_at, updated_at",
        "default_tag": "typst",
        "url_prefix": "/typst",
        "form_title_new": "新建 Typst 文章",
        "form_title_edit": "编辑 Typst 文章",
    },
}


def get_article_config(article_type: str) -> dict:
    """
    获取文章类型配置。

    参数:
        article_type: 文章类型标识 ('md', 'wikidot', 'html', 'bbcode')

    返回:
        包含表名、列名、标签等信息的配置字典

    异常:
        ValueError: 未知的文章类型
    """
    cfg = ARTICLE_TYPES.get(article_type)
    if cfg is None:
        raise ValueError(
            f"未知文章类型: {article_type}，"
            f"有效值: {', '.join(ARTICLE_TYPES.keys())}"
        )
    return cfg


# ── 通用列表查询 ────────────────────────────────────────────


async def list_articles(
    article_type: str,
    page: int = 1,
    per_page: int = 10,
    author_id: int = None,
) -> dict:
    """
    分页获取文章列表（按创建时间倒序）。

    参数:
        article_type: 文章类型标识
        page:         页码（从 1 开始）
        per_page:     每页条数
        author_id:    作者 ID（可选，用于过滤）

    返回:
        {
            "articles": [...],   # 文章列表
            "total": int,        # 总数
            "page": int,         # 当前页码
            "per_page": int,     # 每页条数
            "total_pages": int,  # 总页数
        }
    """
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
                    "WHERE author_id = %s "
                    "ORDER BY created_at DESC LIMIT %s OFFSET %s",
                    (author_id, per_page, offset),
                )
                rows = await cur.fetchall()
                articles = [row_to_dict(r, cur) for r in rows]

                await cur.execute(
                    f"SELECT COUNT(*) FROM {table} WHERE author_id = %s",
                    (author_id,),
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

    # 返回统一键名，同时保留 "pages" 兼容旧模板
    return {
        "articles": articles,
        "pages": articles,       # 向后兼容（wikidot/html/bbcode 模板使用）
        "total": total,
        "page": page,
        "per_page": per_page,
        "total_pages": max(1, (total + per_page - 1) // per_page),
    }


# ── 通用单条查询 ────────────────────────────────────────────


async def get_article(article_type: str, slug: str) -> Optional[dict]:
    """
    根据 slug 获取单篇文章。

    参数:
        article_type: 文章类型标识
        slug:         文章唯一标识符

    返回:
        文章字典（含所有字段）或 None
    """
    cfg = get_article_config(article_type)
    table = cfg["table"]

    pool = await _get_pool()
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                f"SELECT * FROM {table} WHERE slug = %s", (slug,)
            )
            row = await cur.fetchone()
            return row_to_dict(row, cur) if row else None


# ── 通用 CRUD ───────────────────────────────────────────────


async def create_article(
    article_type: str,
    slug: str,
    title: str,
    content: str,
    author_id: int = None,
) -> dict:
    """
    创建新文章，自动添加默认类型标签。

    参数:
        article_type: 文章类型标识
        slug:         文章唯一标识符
        title:        文章标题
        content:      文章内容
        author_id:    作者用户 ID

    返回:
        新创建的文章字典
    """
    cfg = get_article_config(article_type)
    table = cfg["table"]

    pool = await _get_pool()
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                f"INSERT INTO {table} (slug, title, content, author_id) "
                "VALUES (%s, %s, %s, %s)",
                (slug, title, content, author_id),
            )
            await auto_tag_article(article_type, slug)
            return await get_article(article_type, slug)


async def update_article(
    article_type: str,
    slug: str,
    title: str,
    content: str,
) -> Optional[dict]:
    """
    更新已有文章。

    参数:
        article_type: 文章类型标识
        slug:         文章唯一标识符
        title:        新标题
        content:      新内容

    返回:
        更新后的文章字典，或 None（如果文章不存在）
    """
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
    """
    删除文章及其所有关联数据（标签关联、评论、评分、行评论）。

    参数:
        article_type: 文章类型标识
        slug:         文章唯一标识符

    返回:
        True 表示删除成功，False 表示文章不存在
    """
    cfg = get_article_config(article_type)
    table = cfg["table"]

    pool = await _get_pool()
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            # 删除评论
            await cur.execute(
                "DELETE FROM comments WHERE article_type = %s AND article_slug = %s",
                (article_type, slug),
            )
            # 删除评分
            await cur.execute(
                "DELETE FROM ratings WHERE article_type = %s AND article_slug = %s",
                (article_type, slug),
            )
            # 删除行评论
            await cur.execute(
                "DELETE FROM line_comments WHERE article_type = %s AND article_slug = %s",
                (article_type, slug),
            )
            # 删除标签关联
            await cur.execute(
                "DELETE FROM article_tags WHERE article_type = %s AND article_slug = %s",
                (article_type, slug),
            )
            # 删除文章本体
            await cur.execute(
                f"DELETE FROM {table} WHERE slug = %s", (slug,)
            )
            return cur.rowcount > 0


# ── 种子数据 ─────────────────────────────────────────────────


async def seed_db(article_type: str) -> None:
    """
    为指定文章类型插入种子数据（仅当表为空时）。

    种子数据提供新站点的初始内容示例。

    参数:
        article_type: 文章类型标识
    """
    cfg = get_article_config(article_type)
    table = cfg["table"]

    seeds = {
        "md": [
            ("hello-world", "你好，世界！",
             "# 你好，世界！\n\n这是我的第一篇 Markdown 文章。\n\n"
             "## 关于本站\n\n欢迎来到「跨越晨昏」，这是我的个人网站。"),
        ],
        "wikidot": [
            ("syntax-test", "Wikidot 语法测试",
             "[[div]]\n= 这是 Wikidot 语法测试\n[[/div]]\n\n"
             "+ 标题 1\n++ 标题 2\n\n"
             "[[code type=\"python\"]]\ndef hello():\n"
             "    print(\"Hello Wikidot!\")\n[[/code]]\n\n"
             "[[size 120%]]大号文字[[/size]]\n"
             "[[color red]]红色文字[[/color]]\n\n"
             "* 无序列表\n* 无序列表 2\n\n"
             "# 有序列表\n# 有序列表 2"),
        ],
        "html": [
            ("hello-html", "你好 HTML",
             "<h1>你好 HTML</h1>\n<p>这是一篇本地 HTML 文章。</p>\n"
             "<ul>\n  <li>项目 1</li>\n  <li>项目 2</li>\n</ul>"),
        ],
        "bbcode": [
            ("bbcode-demo", "BBCode 示例",
             "[b]粗体文字[/b]\n\n[i]斜体文字[/i]\n\n"
             "[u]下划线文字[/u]\n\n[s]删除线文字[/s]\n\n"
             "[color=red]红色文字[/color]\n\n"
             "[size=150]大号文字[/size]\n\n"
             "[center]居中文字[/center]\n\n"
             "[quote]这是一个引用[/quote]\n\n"
             "[code]\nprint('Hello BBCode!')\n[/code]\n\n"
             "[list]\n[*] 项目 1\n[*] 项目 2\n[/list]\n\n"
             "[url=https://example.com]链接文字[/url]\n"
             "[img]https://via.placeholder.com/100[/img]\n\n"
             "[spoiler=点击展开]隐藏内容[/spoiler]\n\n[hr]"),
        ],
        "typst": [
            ("typst-demo", "Typst 示例",
             '#import "@preview/tufted:0.1.1"\n\n'
             "= Typst 示例文档\n\n"
             "欢迎使用 Typst！这是一个现代化的排版系统。\n\n"
             "== 特点\n\n"
             "- *快速编译*：增量编译，即时预览\n"
             "- *编程式*：使用函数和变量自动化排版\n"
             "- *美观*：内置优雅的默认样式\n\n"
             "== 代码示例\n\n"
             "```typst\n"
             "#let add(x, y) = x + y\n"
             "#add(3, 4)  // 输出 7\n"
             "```\n\n"
             "== 数学公式\n\n"
             "$ integral_0^oo e^(-x^2) dif x = sqrt(pi)/2 $\n\n"
             "== 表格\n\n"
             "#table(\n"
             "  columns: 3,\n"
             "  [ID], [名称], [数量],\n"
             "  [1], [苹果], [10],\n"
             "  [2], [香蕉], [5],\n"
             ")\n"),
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
                    continue  # 已存在，跳过
                await cur.execute(
                    f"INSERT INTO {table} (slug, title, content) "
                    "VALUES (%s, %s, %s)",
                    (slug, title, content),
                )
                await auto_tag_article(article_type, slug)

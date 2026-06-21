"""
搜索路由 — /search/ 下的所有端点。
支持跨全部文章类型（Markdown、Wikidot、HTML、BBCode、Typst）的内容搜索。
"""

import re
from typing import Any

from lihil import Route
from starlette.responses import HTMLResponse
from pathlib import Path
from ..core.db import _get_pool

# ── 模板（使用统一模板引擎） ──────────────────────────────
from ..core.templates import render_template as render


# ── 路由 ────────────────────────────────────────────────────

search_route = Route("/search")

# 文章类型到路由前缀的映射
TYPE_ROUTE_MAP: dict[str, str] = {
    "md": "/md/",
    "wikidot": "/wikidot/",
    "html": "/html/local/",
    "bbcode": "/bbcode/",
    "typst": "/typst/",
}

TYPE_LABEL_MAP: dict[str, str] = {
    "md": "Markdown",
    "wikidot": "Wikidot",
    "html": "HTML",
    "bbcode": "BBCode",
    "typst": "Typst",
}


@search_route.get
async def search(q: str = "", page: int = 1) -> HTMLResponse:
    """搜索页面 — 根据关键词搜索所有类型的文章。

    使用 MySQL FULLTEXT 索引进行高效全文搜索（MATCH ... AGAINST IN BOOLEAN MODE）。

    参数:
        q:    搜索关键词
        page: 分页页码（从 1 开始）

    返回:
        搜索结果页面，包含匹配文章列表、分页信息和搜索摘要
    """
    per_page = 10
    results = []
    total = 0
    total_pages = 0

    if q.strip():
        pool = await _get_pool()
        keyword = q.strip()

        async with pool.acquire() as conn:
            async with conn.cursor() as cur:
                # 构建 FULLTEXT 搜索查询（MATCH ... AGAINST IN BOOLEAN MODE）
                # 使用布尔模式支持精确匹配，* 通配符实现前缀搜索
                ft_keyword = f"{keyword}*"

                # 先查总数（使用 FULLTEXT MATCH）
                await cur.execute(
                    """
                    SELECT COUNT(*) FROM (
                        SELECT slug FROM articles
                        WHERE MATCH(title, content) AGAINST(%s IN BOOLEAN MODE)
                        UNION ALL
                        SELECT slug FROM pages
                        WHERE MATCH(title, content) AGAINST(%s IN BOOLEAN MODE)
                        UNION ALL
                        SELECT slug FROM html_pages
                        WHERE MATCH(title, content) AGAINST(%s IN BOOLEAN MODE)
                        UNION ALL
                        SELECT slug FROM bbcode_pages
                        WHERE MATCH(title, content) AGAINST(%s IN BOOLEAN MODE)
                        UNION ALL
                        SELECT slug FROM typst_pages
                        WHERE MATCH(title, content) AGAINST(%s IN BOOLEAN MODE)
                    ) AS all_results
                    """,
                    (ft_keyword, ft_keyword, ft_keyword, ft_keyword, ft_keyword),
                )
                total = (await cur.fetchone())[0]
                total_pages = max(1, (total + per_page - 1) // per_page)

                # SQL 层面分页
                offset = (page - 1) * per_page
                await cur.execute(
                    """
                    SELECT slug, title, content, created_at, 'md' AS article_type
                    FROM articles
                    WHERE MATCH(title, content) AGAINST(%s IN BOOLEAN MODE)
                    UNION ALL
                    SELECT slug, title, content, created_at, 'wikidot' AS article_type
                    FROM pages
                    WHERE MATCH(title, content) AGAINST(%s IN BOOLEAN MODE)
                    UNION ALL
                    SELECT slug, title, content, created_at, 'html' AS article_type
                    FROM html_pages
                    WHERE MATCH(title, content) AGAINST(%s IN BOOLEAN MODE)
                    UNION ALL
                    SELECT slug, title, content, created_at, 'bbcode' AS article_type
                    FROM bbcode_pages
                    WHERE MATCH(title, content) AGAINST(%s IN BOOLEAN MODE)
                    UNION ALL
                    SELECT slug, title, content, created_at, 'typst' AS article_type
                    FROM typst_pages
                    WHERE MATCH(title, content) AGAINST(%s IN BOOLEAN MODE)
                    ORDER BY created_at DESC
                    LIMIT %s OFFSET %s
                    """,
                    (ft_keyword, ft_keyword, ft_keyword, ft_keyword, ft_keyword,
                     per_page, offset),
                )
                page_rows = await cur.fetchall()

        # 生成摘要：从 content 中截取包含关键词的片段
        results = []
        for row in page_rows:
            slug, title, content, created_at, article_type = row
            snippet = _generate_snippet(content, q.strip(), max_length=200)
            results.append({
                "slug": slug,
                "title": title,
                "snippet": snippet,
                "created_at": str(created_at)[:10] if created_at else "",
                "article_type": article_type,
                "type_label": TYPE_LABEL_MAP.get(article_type, article_type),
                "url": f"{TYPE_ROUTE_MAP.get(article_type, '/')}{slug}",
            })

    return render(
        "search.html",
        title="搜索 - 跨越晨昏",
        q=q,
        results=results,
        page=page,
        total_pages=total_pages,
        total=total,
    )


def _generate_snippet(content: str, keyword: str, max_length: int = 200) -> str:
    """从文章内容中截取包含关键词的摘要片段。"""
    if not content:
        return ""

    # 去除 HTML 标签
    clean = re.sub(r"<[^>]+>", "", content)
    clean = re.sub(r"\s+", " ", clean).strip()

    keyword_lower = keyword.lower()
    idx = clean.lower().find(keyword_lower)

    if idx == -1:
        # 关键词不在纯文本中（可能在 HTML 标签内），取开头
        snippet = clean[:max_length]
    else:
        # 以关键词为中心截取
        half = max_length // 2
        start = max(0, idx - half)
        end = min(len(clean), idx + len(keyword) + half)
        snippet = clean[start:end]
        if start > 0:
            snippet = "…" + snippet
        if end < len(clean):
            snippet = snippet + "…"

    return snippet

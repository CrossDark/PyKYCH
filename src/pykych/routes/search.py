"""
搜索路由 — /search/ 下的所有端点。
支持跨全部文章类型（Markdown、Wikidot、HTML、BBCode）的内容搜索。
"""

from lihil import Route
from starlette.responses import HTMLResponse
from pathlib import Path
from jinja2 import Environment, FileSystemLoader

from ..mysql_manager import _get_pool

# ── 模板 ────────────────────────────────────────────────────
TEMPLATE_DIR = Path(__file__).parent.parent / "templates"
jinja_env = Environment(
    loader=FileSystemLoader(str(TEMPLATE_DIR)),
    autoescape=True,
)


def render(template_name: str, status_code: int = 200, **context) -> HTMLResponse:
    template = jinja_env.get_template(template_name)
    return HTMLResponse(template.render(**context), status_code=status_code)


# ── 路由 ────────────────────────────────────────────────────

search_route = Route("/search")

# 文章类型到路由前缀的映射
TYPE_ROUTE_MAP = {
    "md": "/md/",
    "wikidot": "/wikidot/",
    "html": "/html/local/",
    "bbcode": "/bbcode/",
}

TYPE_LABEL_MAP = {
    "md": "Markdown",
    "wikidot": "Wikidot",
    "html": "HTML",
    "bbcode": "BBCode",
}


@search_route.get
async def search(q: str = "", page: int = 1):
    """搜索页面 — 根据关键词搜索所有类型的文章。"""
    per_page = 10
    results = []
    total = 0
    total_pages = 0

    if q.strip():
        pool = await _get_pool()
        keyword = f"%{q.strip()}%"

        async with pool.acquire() as conn:
            async with conn.cursor() as cur:
                # 跨四张表搜索，使用 UNION ALL
                await cur.execute(
                    """
                    SELECT slug, title, content, created_at, 'md' AS article_type
                    FROM articles
                    WHERE title LIKE %s OR content LIKE %s
                    UNION ALL
                    SELECT slug, title, content, created_at, 'wikidot' AS article_type
                    FROM pages
                    WHERE title LIKE %s OR content LIKE %s
                    UNION ALL
                    SELECT slug, title, content, created_at, 'html' AS article_type
                    FROM html_pages
                    WHERE title LIKE %s OR content LIKE %s
                    UNION ALL
                    SELECT slug, title, content, created_at, 'bbcode' AS article_type
                    FROM bbcode_pages
                    WHERE title LIKE %s OR content LIKE %s
                    ORDER BY created_at DESC
                    """,
                    (keyword, keyword, keyword, keyword, keyword, keyword, keyword, keyword),
                )
                all_rows = await cur.fetchall()

        total = len(all_rows)
        total_pages = max(1, (total + per_page - 1) // per_page)

        # 分页截取
        start = (page - 1) * per_page
        end = start + per_page
        page_rows = all_rows[start:end]

        # 生成摘要：从 content 中截取包含关键词的片段
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
    import re
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

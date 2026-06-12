"""
HTML 文章路由 — /html/ 下的所有端点。
"""

from lihil import Route
from starlette.responses import HTMLResponse
from pathlib import Path
from jinja2 import Environment, FileSystemLoader

from .. import html_db as db
from .. import tag_manager
from .. import comment_manager

# ── 模板引擎 ────────────────────────────────────────────────
TEMPLATE_DIR = Path(__file__).parent.parent / "templates"
jinja_env = Environment(
    loader=FileSystemLoader(str(TEMPLATE_DIR)),
    autoescape=True,
)


def render(template_name: str, status_code: int = 200, **context) -> HTMLResponse:
    template = jinja_env.get_template(template_name)
    return HTMLResponse(template.render(**context), status_code=status_code)


# ── 路由 ────────────────────────────────────────────────────

html_route = Route("/html")


@html_route.get
async def html_page_list(page: int = 1):
    """HTML 页面列表页。"""
    result = await db.list_html_pages(page=page, per_page=10)
    for p in result["pages"]:
        p["tags"] = await tag_manager.get_tags_for_article("html", p["slug"])
    return render(
        "html_list.html",
        title="HTML 页面 - PyKYCH",
        pages=result["pages"],
        page=result["page"],
        total_pages=result["total_pages"],
        total=result["total"],
    )


@html_route.sub("/local/{slug}").get
async def html_page_detail(slug: str):
    """HTML 页面详情页。"""
    page = await db.get_html_page_by_slug(slug)
    if not page:
        return render(
            "html_detail.html",
            title="页面未找到 - PyKYCH",
            status_code=404,
            page=None,
            html_content="<p>抱歉，您查找的 HTML 页面不存在。</p>",
        )

    page["tags"] = await tag_manager.get_tags_for_article("html", slug)
    # 加载评论
    comments = await comment_manager.get_comments("html", slug)
    return render(
        "html_detail.html",
        title=f"{page['title']} - PyKYCH",
        page=page,
        html_content=page["content"],
        comments=comments,
    )

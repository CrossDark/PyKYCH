"""
BBCode 文章路由 — /bbcode/ 下的所有端点。
"""

from lihil import Route
from starlette.responses import HTMLResponse
from pathlib import Path
from jinja2 import Environment, FileSystemLoader

from .. import bbcode_db as db
from ..bbcode_parser import parse_bbcode
from .. import tag_manager

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

bbcode_route = Route("/bbcode")


@bbcode_route.get
async def page_list(page: int = 1):
    """BBCode 页面列表。"""
    result = await db.list_pages(page=page, per_page=10)
    for p in result["pages"]:
        p["tags"] = await tag_manager.get_tags_for_article("bbcode", p["slug"])
    return render(
        "bbcode_list.html",
        title="BBCode 文章 - 跨越晨昏",
        pages=result["pages"],
        page=result["page"],
        total_pages=result["total_pages"],
        total=result["total"],
    )


@bbcode_route.sub("/{slug}").get
async def page_detail(slug: str):
    """BBCode 页面详情。"""
    page = await db.get_page_by_slug(slug)
    if not page:
        return render(
            "bbcode_detail.html",
            title="页面未找到 - 跨越晨昏",
            status_code=404,
            page=None,
            html_content="<p>抱歉，您查找的 BBCode 页面不存在。</p>",
        )

    page["tags"] = await tag_manager.get_tags_for_article("bbcode", slug)
    html_body = parse_bbcode(page["content"])
    return render(
        "bbcode_detail.html",
        title=f"{page['title']} - 跨越晨昏",
        page=page,
        html_content=html_body,
    )

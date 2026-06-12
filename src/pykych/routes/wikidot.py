"""
Wikidot 页面路由 — /wikidot/ 下的所有端点。
"""

from lihil import Route
from starlette.responses import HTMLResponse
from pathlib import Path
from jinja2 import Environment, FileSystemLoader

from .. import wikidot_db as db
from ..wikidot_parser import parse_wikidot
from .. import tag_manager

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

wikidot_route = Route("/wikidot")


@wikidot_route.get
async def page_list(page: int = 1):
    """Wikidot 页面列表。"""
    result = await db.list_pages(page=page, per_page=10)
    # 为每个页面加载标签
    for p in result["pages"]:
        p["tags"] = await tag_manager.get_tags_for_article("wikidot", p["slug"])
    return render(
        "wikidot_list.html",
        title="Wiki 页面 - 跨越晨昏",
        pages=result["pages"],
        page=result["page"],
        total_pages=result["total_pages"],
        total=result["total"],
    )


@wikidot_route.sub("/{slug}").get
async def page_detail(slug: str):
    """Wikidot 页面详情。"""
    page = await db.get_page_by_slug(slug)
    if not page:
        return render(
            "wikidot_detail.html",
            title="页面未找到 - 跨越晨昏",
            status_code=404,
            page=None,
            html_content="<p>抱歉，该 Wiki 页面不存在。</p>",
        )

    # 加载标签
    page["tags"] = await tag_manager.get_tags_for_article("wikidot", slug)
    html_body = parse_wikidot(page["content"])
    return render(
        "wikidot_detail.html",
        title=f"{page['title']} - 跨越晨昏 Wiki",
        page=page,
        html_content=html_body,
    )

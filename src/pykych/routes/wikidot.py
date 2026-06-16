"""
Wikidot 页面路由 — /wikidot/ 下的所有端点。
"""

from lihil import Route
from starlette.responses import HTMLResponse
from pathlib import Path
from jinja2 import Environment, FileSystemLoader

from lihil import Request

from ..content import articles as db
from ..content.parsers.wikidot import parse_wikidot
from ..content import tags as tag_manager
from ..content import comments as comment_manager
from ..content import comments as line_comment_manager
from ..content import ratings as rating_manager
from ..auth.session import get_current_user

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
    result = await db.list_articles('wikidot', page=page, per_page=10)
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
async def page_detail(request: Request, slug: str):
    """Wikidot 页面详情。"""
    page = await db.get_article('wikidot', slug)
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
    # 加载评论
    comments = await comment_manager.get_comments("wikidot", slug)
    # 加载行评论
    line_comments = await line_comment_manager.get_line_comments("wikidot", slug)
    line_comment_counts = await line_comment_manager.get_line_comment_counts("wikidot", slug)
    # 加载评分
    rating = await rating_manager.get_article_rating("wikidot", slug)
    # 获取当前用户
    current_user = await get_current_user(request)
    html_body = parse_wikidot(page["content"])
    return render(
        "wikidot_detail.html",
        title=f"{page['title']} - 跨越晨昏 Wiki",
        page=page,
        html_content=html_body,
        comments=comments,
        line_comments=line_comments,
        line_comment_counts=line_comment_counts,
        rating=rating,
        current_user=current_user,
    )

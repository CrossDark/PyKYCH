"""
HTML 文章路由 — /html/ 下的所有端点。
"""

from lihil import Route
from starlette.responses import HTMLResponse
from pathlib import Path
from jinja2 import Environment, FileSystemLoader

from lihil import Request

from ..content import articles as db
from ..content import tags as tag_manager
from ..content import comments as comment_manager
from ..content import comments as line_comment_manager
from ..content import ratings as rating_manager
from ..auth.session import get_current_user

# ── 模板引擎 ────────────────────────────────────────────────
TEMPLATE_DIR = Path(__file__).parent.parent / "templates"
jinja_env = Environment(
    loader=FileSystemLoader(str(TEMPLATE_DIR)),
    autoescape=True,
)

# 注入站点设置访问函数
from ..core.settings import get_setting, get_site_title, get_site_subtitle
jinja_env.globals["site_logo"] = lambda: get_setting("site.logo_path", "/static/img/logo.png")
jinja_env.globals["site_favicon"] = lambda: get_setting("site.favicon_path", "/static/img/favicon.ico")
jinja_env.globals["site_title_func"] = lambda: get_site_title()
jinja_env.globals["site_subtitle_func"] = lambda: get_site_subtitle()


def render(template_name: str, status_code: int = 200, **context) -> HTMLResponse:
    template = jinja_env.get_template(template_name)
    return HTMLResponse(template.render(**context), status_code=status_code)


# ── 路由 ────────────────────────────────────────────────────

html_route = Route("/html")


@html_route.get
async def html_page_list(page: int = 1):
    """HTML 页面列表页。"""
    result = await db.list_articles('html', page=page, per_page=10)
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
async def html_page_detail(request: Request, slug: str):
    """HTML 页面详情页。"""
    page = await db.get_article('html', slug)
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
    # 加载行评论
    line_comments = await line_comment_manager.get_line_comments("html", slug)
    line_comment_counts = await line_comment_manager.get_line_comment_counts("html", slug)
    # 加载评分
    rating = await rating_manager.get_article_rating("html", slug)
    # 获取当前用户
    current_user = await get_current_user(request)
    return render(
        "html_detail.html",
        title=f"{page['title']} - PyKYCH",
        page=page,
        html_content=page["content"],
        comments=comments,
        line_comments=line_comments,
        line_comment_counts=line_comment_counts,
        rating=rating,
        current_user=current_user,
    )




"""
Typst 文章路由 — /typst/ 下的所有端点。

支持:
    - /typst/               文章列表
    - /typst/{slug}         文章详情（编译为 HTML）
    - /typst/{slug}/pdf     下载 PDF 版本
"""

from lihil import Route
from starlette.responses import HTMLResponse, Response
from pathlib import Path
from jinja2 import Environment, FileSystemLoader

from lihil import Request

from ..content import articles as db
from ..content.parsers.typst_parser import (
    compile_typst_to_html,
    compile_typst_to_pdf,
    check_typst_available,
)
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

from ..core.settings import get_setting, get_site_title, get_site_subtitle
jinja_env.globals["site_logo"] = lambda: get_setting("site.logo_path", "/static/img/logo.png")
jinja_env.globals["site_favicon"] = lambda: get_setting("site.favicon_path", "/static/img/favicon.ico")
jinja_env.globals["site_title_func"] = lambda: get_site_title()
jinja_env.globals["site_subtitle_func"] = lambda: get_site_subtitle()


def render(template_name: str, status_code: int = 200, **context) -> HTMLResponse:
    template = jinja_env.get_template(template_name)
    return HTMLResponse(template.render(**context), status_code=status_code)


# ── 路由 ────────────────────────────────────────────────────

typst_route = Route("/typst")


@typst_route.get
async def typst_article_list(page: int = 1):
    """Typst 文章列表页。"""
    result = await db.list_articles('typst', page=page, per_page=10)
    for article in result["articles"]:
        article["tags"] = await tag_manager.get_tags_for_article("typst", article["slug"])
    return render(
        "typst_list.html",
        title="Typst 文章 - PyKYCH",
        articles=result["articles"],
        pages=result["pages"],
        page=result["page"],
        total_pages=result["total_pages"],
        total=result["total"],
        typst_available=check_typst_available(),
    )


@typst_route.sub("/{slug}").get
async def typst_article_detail(request: Request, slug: str):
    """Typst 文章详情页 — 编译 Typst 源码为 HTML 后展示。"""
    article = await db.get_article('typst', slug)
    if not article:
        return render(
            "typst_detail.html",
            title="文章未找到 - PyKYCH",
            status_code=404,
            article=None,
            html_content="<p>抱歉，您查找的 Typst 文章不存在。</p>",
        )

    # 编译 Typst → HTML
    html_body, compile_error = await compile_typst_to_html(
        article["content"], slug=slug
    )

    # 加载标签
    article["tags"] = await tag_manager.get_tags_for_article("typst", slug)
    # 加载评论
    comments = await comment_manager.get_comments("typst", slug)
    # 加载行评论
    line_comments = await line_comment_manager.get_line_comments("typst", slug)
    line_comment_counts = await line_comment_manager.get_line_comment_counts("typst", slug)
    # 加载评分
    rating = await rating_manager.get_article_rating("typst", slug)
    # 获取当前用户
    current_user = await get_current_user(request)

    return render(
        "typst_detail.html",
        title=f"{article['title']} - PyKYCH",
        article=article,
        html_content=html_body,
        comments=comments,
        line_comments=line_comments,
        line_comment_counts=line_comment_counts,
        rating=rating,
        current_user=current_user,
        typst_available=check_typst_available(),
        compile_error=compile_error,
    )


@typst_route.sub("/{slug}/pdf").get
async def typst_article_pdf(request: Request, slug: str):
    """下载 Typst 文章的 PDF 版本。"""
    article = await db.get_article('typst', slug)
    if not article:
        return HTMLResponse("<p>文章不存在</p>", status_code=404)

    pdf_bytes, error = await compile_typst_to_pdf(
        article["content"], slug=slug
    )

    if error:
        return HTMLResponse(
            f"<h2>PDF 生成失败</h2><pre>{error}</pre>",
            status_code=500,
        )

    # 生成安全的文件名
    safe_title = slug.replace("/", "-").replace("\\", "-")
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="{safe_title}.pdf"',
        },
    )

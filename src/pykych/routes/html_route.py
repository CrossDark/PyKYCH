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
from .. import line_comment_manager
from .. import rating_manager
from .. import external_html

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

    # 获取活跃的外部站点列表
    ext_sites = await external_html.list_external_sites()
    ext_sites = [s for s in ext_sites if s.get("is_active")]

    return render(
        "html_list.html",
        title="HTML 页面 - PyKYCH",
        pages=result["pages"],
        page=result["page"],
        total_pages=result["total_pages"],
        total=result["total"],
        external_sites=ext_sites,
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
    # 加载行评论
    line_comments = await line_comment_manager.get_line_comments("html", slug)
    line_comment_counts = await line_comment_manager.get_line_comment_counts("html", slug)
    # 加载评分
    rating = await rating_manager.get_article_rating("html", slug)
    return render(
        "html_detail.html",
        title=f"{page['title']} - PyKYCH",
        page=page,
        html_content=page["content"],
        comments=comments,
        line_comments=line_comments,
        line_comment_counts=line_comment_counts,
        rating=rating,
    )


# ===== 外部 HTML 站点路由 =====


@html_route.sub("/{site_name}").get
async def external_site_page(site_name: str):
    """外部站点首页 — 显示缓存的外部 HTML 站点首页。"""
    # 排除 local 路径
    if site_name == "local":
        # 不应该到达这里，但防御性处理
        return render(
            "html_detail.html",
            title="页面未找到 - PyKYCH",
            status_code=404,
            page=None,
            html_content="<p>抱歉，您查找的页面不存在。</p>",
        )

    page = await external_html.get_cached_page(site_name, "")
    if not page:
        # 检查站点是否存在
        site = await external_html.get_external_site_by_name(site_name)
        if site:
            return render(
                "external_html.html",
                title=f"{site_name} - PyKYCH",
                site_name=site_name,
                page_title=site.get("description", site_name),
                html_content="<p>该站点尚未缓存内容，请联系管理员刷新。</p>",
                fetched_at=None,
            )
        return render(
            "html_detail.html",
            title="页面未找到 - PyKYCH",
            status_code=404,
            page=None,
            html_content=f"<p>未找到外部站点「{site_name}」。</p>",
        )

    return render(
        "external_html.html",
        title=f"{page.get('page_title') or page['title'] or site_name} - PyKYCH",
        site_name=site_name,
        page_title=page["title"],
        html_content=page["content"],
        fetched_at=page.get("fetched_at"),
    )


@html_route.sub("/{site_name}/{sub_path}").get
async def external_site_subpage(site_name: str, sub_path: str, request=None):
    """外部站点子页面 — 显示缓存的外部 HTML 子页面。"""
    if site_name == "local":
        return render(
            "html_detail.html",
            title="页面未找到 - PyKYCH",
            status_code=404,
            page=None,
            html_content="<p>抱歉，您查找的页面不存在。</p>",
        )

    # sub_path 可能包含多级路径（通过 URL 手动解析）
    path = sub_path.rstrip("/")

    page = await external_html.get_cached_page(site_name, path)
    if not page:
        return render(
            "external_html.html",
            title=f"{path} - {site_name} - PyKYCH",
            site_name=site_name,
            page_title=f"{site_name}/{path}",
            html_content=f"<p>页面「{path}」未缓存，请联系管理员刷新。</p>",
            fetched_at=None,
        )

    return render(
        "external_html.html",
        title=f"{page['title'] or path} - {site_name} - PyKYCH",
        site_name=site_name,
        page_title=page["title"],
        html_content=page["content"],
        fetched_at=page.get("fetched_at"),
    )

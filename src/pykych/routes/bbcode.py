"""
BBCode 文章路由 — /bbcode/ 下的所有端点。
"""

from lihil import Route
from starlette.responses import HTMLResponse

from lihil import Request

from ..content import articles as db
from ..content.parsers.bbcode import parse_bbcode
from ..content import tags as tag_manager
from ..content import comments as comment_manager
from ..content import comments as line_comment_manager
from ..content import ratings as rating_manager
from ..auth.session import get_current_user
from ..auth import user as auth_user

# ── 模板（使用统一模板引擎） ──────────────────────────────
from ..core.templates import render_template as render


# ── 路由 ────────────────────────────────────────────────────

bbcode_route = Route("/bbcode")


@bbcode_route.get
async def page_list(page: int = 1):
    """BBCode 页面列表。"""
    result = await db.list_articles('bbcode', page=page, per_page=10)
    # 批量加载所有文章的标签（一次查询，避免 N+1 问题）
    article_keys = [("bbcode", p["slug"]) for p in result["pages"]]
    tags_map = await tag_manager.get_tags_for_articles_batch(article_keys)
    for p in result["pages"]:
        p["tags"] = tags_map.get(("bbcode", p["slug"]), [])
    return render(
        "bbcode_list.html",
        title="BBCode 文章 - 跨越晨昏",
        pages=result["pages"],
        page=result["page"],
        total_pages=result["total_pages"],
        total=result["total"],
    )


@bbcode_route.sub("/{slug}").get
async def page_detail(request: Request, slug: str):
    """BBCode 页面详情。"""
    page = await db.get_article('bbcode', slug)
    if not page:
        return render(
            "bbcode_detail.html",
            title="页面未找到 - 跨越晨昏",
            status_code=404,
            page=None,
            html_content="<p>抱歉，您查找的 BBCode 页面不存在。</p>",
        )

    page["tags"] = await tag_manager.get_tags_for_article("bbcode", slug)
    # 加载评论
    comments = await comment_manager.get_comments("bbcode", slug)
    # 加载行评论
    line_comments = await line_comment_manager.get_line_comments("bbcode", slug)
    line_comment_counts = await line_comment_manager.get_line_comment_counts("bbcode", slug)
    # 加载评分
    rating = await rating_manager.get_article_rating("bbcode", slug)
    # 获取当前用户
    current_user = await get_current_user(request)
    # 检查当前用户是否有编辑权限（管理员/站长可编辑所有，普通用户只能编辑自己的）
    can_edit = (
        current_user is not None
        and (
            auth_user.is_admin(current_user)
            or page.get("author_id") == current_user.get("id")
        )
    )
    html_body = parse_bbcode(page["content"])
    return render(
        "bbcode_detail.html",
        title=f"{page['title']} - 跨越晨昏",
        page=page,
        html_content=html_body,
        comments=comments,
        line_comments=line_comments,
        line_comment_counts=line_comment_counts,
        rating=rating,
        current_user=current_user,
        can_edit=can_edit,
    )

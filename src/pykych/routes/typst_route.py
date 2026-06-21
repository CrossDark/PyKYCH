"""
Typst 文章路由 — /typst/ 下的所有端点。

支持:
    - /typst/               文章列表
    - /typst/{slug}         文章详情（编译为 HTML）
    - /typst/{slug}/pdf     下载 PDF 版本
"""

import asyncio
import logging
from lihil import Route
from starlette.responses import HTMLResponse, Response

from lihil import Request

from ..content import articles as db
from ..content.parsers.typst_parser import (
    compile_typst_to_html,
    compile_typst_to_pdf,
    check_typst_available,
    get_cached_typst_html,
    get_cached_typst_pdf,
)
from ..content import tags as tag_manager
from ..content import comments as comment_manager
from ..content import comments as line_comment_manager
from ..content import ratings as rating_manager
from ..auth.session import get_current_user
from ..auth import user as auth_user

# ── 模板（使用统一模板引擎） ──────────────────────────────
from ..core.templates import render_template as render

logger = logging.getLogger(__name__)


def _create_background_task(coro, name: str = "unknown"):
    """
    安全创建后台异步任务，附带异常日志。

    与裸 asyncio.create_task() 不同，此函数会：
    1. 保存 Task 引用防止被 GC 回收
    2. 为任务添加异常回调，确保异常被记录到日志
    """
    task = asyncio.create_task(coro)
    def _log_exception(t: asyncio.Task):
        try:
            t.result()
        except Exception:
            logger.exception(f"后台任务 [{name}] 异常")
    task.add_done_callback(_log_exception)
    return task


# ── 路由 ────────────────────────────────────────────────────

typst_route = Route("/typst")


@typst_route.get
async def typst_article_list(page: int = 1):
    """Typst 文章列表页。"""
    result = await db.list_articles('typst', page=page, per_page=10)
    # 批量加载所有文章的标签（一次查询，避免 N+1 问题）
    article_keys = [("typst", a["slug"]) for a in result["articles"]]
    tags_map = await tag_manager.get_tags_for_articles_batch(article_keys)
    for article in result["articles"]:
        article["tags"] = tags_map.get(("typst", article["slug"]), [])
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
    """Typst 文章详情页 — 优先使用缓存 HTML，缓存未命中时实时编译。"""
    article = await db.get_article('typst', slug)
    if not article:
        return render(
            "typst_detail.html",
            title="文章未找到 - PyKYCH",
            status_code=404,
            article=None,
            html_content="<p>抱歉，您查找的 Typst 文章不存在。</p>",
        )

    # 优先使用缓存
    compile_error = None
    html_body = await get_cached_typst_html(slug)

    if html_body is None:
        # 缓存未命中 → 实时编译并回填缓存
        html_body, compile_error = await compile_typst_to_html(
            article["content"], slug=slug
        )
        # 编译成功后异步回填缓存（不阻塞响应）
        if compile_error is None:
            _create_background_task(_fill_cache_after_miss(slug), name=f"typst-cache-{slug}")

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
    # 检查当前用户是否有编辑权限（管理员/站长可编辑所有，普通用户只能编辑自己的）
    can_edit = (
        current_user is not None
        and (
            auth_user.is_admin(current_user)
            or article.get("author_id") == current_user.get("id")
        )
    )

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
        can_edit=can_edit,
        typst_available=check_typst_available(),
        compile_error=compile_error,
    )


@typst_route.sub("/{slug}/pdf").get
async def typst_article_pdf(request: Request, slug: str):
    """下载 Typst 文章的 PDF 版本 — 优先使用缓存。"""
    article = await db.get_article('typst', slug)
    if not article:
        return HTMLResponse("<p>文章不存在</p>", status_code=404)

    # 优先使用缓存
    pdf_bytes = await get_cached_typst_pdf(slug)

    if pdf_bytes is None:
        # 缓存未命中 → 实时编译
        pdf_bytes, error = await compile_typst_to_pdf(
            article["content"], slug=slug
        )

        if error:
            return HTMLResponse(
                f"<h2>PDF 生成失败</h2><pre>{error}</pre>",
                status_code=500,
            )

        # 编译成功后异步回填缓存
        _create_background_task(_fill_cache_after_miss(slug), name=f"typst-cache-pdf-{slug}")

    # 生成安全的文件名
    safe_title = slug.replace("/", "-").replace("\\", "-")
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="{safe_title}.pdf"',
        },
    )


# ── 缓存辅助 ─────────────────────────────────────────────────

async def _fill_cache_after_miss(slug: str):
    """
    缓存未命中后异步回填缓存（不阻塞用户响应）。

    当用户访问文章时缓存未命中，实时编译完成后，
    在后台异步将结果写入缓存表，加速后续访问。
    """
    from ..content.parsers.typst_parser import build_and_cache_typst
    try:
        await build_and_cache_typst(slug)
    except Exception:
        pass  # 缓存回填失败不影响用户

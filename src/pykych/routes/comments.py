"""
评论区路由 — 处理评论提交。
"""

from lihil import Route, Request
from starlette.responses import RedirectResponse

from .. import comment_manager


def redirect(url: str) -> RedirectResponse:
    return RedirectResponse(url, status_code=303)


comments_route = Route("/comments")


@comments_route.sub("/add").post
async def add_comment(request: Request):
    """处理评论提交，完成后重定向回文章页面。"""
    form = await request.form()

    article_type = form.get("article_type", "").strip()
    article_slug = form.get("article_slug", "").strip()
    author_name = form.get("author_name", "").strip()
    content = form.get("content", "").strip()
    redirect_url = form.get("redirect_url", "/")

    # 校验
    if not article_type or not article_slug or not content:
        return redirect(redirect_url)

    if not author_name:
        author_name = "匿名"

    await comment_manager.add_comment(
        article_type=article_type,
        article_slug=article_slug,
        author_name=author_name,
        content=content,
    )

    return redirect(redirect_url)

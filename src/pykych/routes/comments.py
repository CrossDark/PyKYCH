"""
评论区路由 — 处理评论提交（仅登录用户可评论）。
"""

from lihil import Route, Request
from starlette.responses import RedirectResponse
from urllib.parse import quote

from ..content import comments as comment_manager
from ..auth.session import get_current_user


def redirect(url: str) -> RedirectResponse:
    return RedirectResponse(url, status_code=303)


comments_route = Route("/comments")


def _safe_redirect_url(url: str, fallback: str = "/") -> str:
    """校验重定向 URL 安全性：必须以 / 开头且不含 // 或 @，防止开放重定向。"""
    url = url.strip()
    if not url:
        return fallback
    if url.startswith("/") and "//" not in url and "@" not in url:
        return url
    return fallback


@comments_route.sub("/add").post
async def add_comment(request: Request):
    """处理评论提交，仅登录用户可评论，使用用户信息作为作者。"""
    form = await request.form()

    article_type = form.get("article_type", "").strip()
    article_slug = form.get("article_slug", "").strip()
    content = form.get("content", "").strip()
    redirect_url = _safe_redirect_url(form.get("redirect_url", "/"))

    # 校验
    if not article_type or not article_slug or not content:
        return redirect(redirect_url)

    # 登录检查：未登录用户跳转到登录页
    user = await get_current_user(request)
    if user is None:
        login_url = f"/auth/login?next={quote(redirect_url)}"
        return redirect(login_url)

    # 使用用户昵称（fallback 到用户名）作为评论作者
    author_name = user.get("nickname") or user["username"]

    await comment_manager.add_comment(
        article_type=article_type,
        article_slug=article_slug,
        author_name=author_name,
        content=content,
    )

    return redirect(redirect_url)

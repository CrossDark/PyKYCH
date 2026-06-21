"""
API 路由模块 — 所有 /api/* 端点。

包含:
    - /api/me                    当前用户信息
    - /api/line-comments/*       行评论 CRUD
    - /api/ratings/*             评分 CRUD

从 main.py 提取以减小主入口文件体积，提高模块化程度。
"""

from typing import Any

from lihil import Route, Request
from starlette.responses import JSONResponse

from ..auth.session import get_current_user
from ..auth import profile as user_profile
from ..content import comments as line_comment_manager
from ..content import ratings as rating_manager


# ═══════════════════════════════════════════════════════════
#  当前用户 API
# ═══════════════════════════════════════════════════════════

user_api = Route("/api")


@user_api.sub("/me").get
async def api_me(request: Request) -> dict[str, Any]:
    """获取当前登录用户信息（用于前端导航栏头像）。

    返回:
        - user: 当前用户信息字典（含 username, nickname, role, avatar）
        - user 为 null 表示未登录
    """
    user = await get_current_user(request)
    if user is None:
        return {"user": None}
    profile = await user_profile.get_user_profile(user["username"])
    return {
        "user": {
            "username": user["username"],
            "nickname": user.get("nickname", user["username"]),
            "role": user.get("role", "user"),
            "avatar": profile.get("avatar", user_profile.DEFAULT_AVATAR) if profile else user_profile.DEFAULT_AVATAR,
        }
    }


# ═══════════════════════════════════════════════════════════
#  行评论 API
# ═══════════════════════════════════════════════════════════

line_comments_api = Route("/api/line-comments")


@line_comments_api.sub("/{article_type}/{article_slug}").get
async def api_get_line_comments(article_type: str, article_slug: str) -> dict[str, Any]:
    """获取文章的所有行评论（按行分组）。

    参数:
        article_type: 文章类型 (md/wikidot/html/bbcode/typst)
        article_slug: 文章唯一标识符

    返回:
        comments: 所有评论列表
        counts: 每行的评论数量统计
    """
    comments = await line_comment_manager.get_line_comments(article_type, article_slug)
    counts = await line_comment_manager.get_line_comment_counts(article_type, article_slug)
    return {"comments": comments, "counts": counts}


@line_comments_api.sub("/{article_type}/{article_slug}").post
async def api_add_line_comment(
    request: Request, article_type: str, article_slug: str
) -> dict[str, Any] | JSONResponse:
    """添加一条行评论（需要登录）。

    请求体 (JSON):
        - line_number: int  — 行号
        - content: str      — 评论内容（最多 20 字符）

    返回:
        201: 新创建的评论
        400: 参数错误
        401: 未登录
    """
    user = await get_current_user(request)
    if user is None:
        return JSONResponse({"error": "请先登录"}, status_code=401)

    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "请求格式错误"}, status_code=400)

    line_number = body.get("line_number")
    content = body.get("content", "").strip()

    if line_number is None or not content:
        return JSONResponse({"error": "缺少参数"}, status_code=400)

    try:
        comment = await line_comment_manager.add_line_comment(
            article_type=article_type,
            article_slug=article_slug,
            line_number=line_number,
            author_name=user["username"],
            content=content,
        )
        return {"comment": comment}
    except ValueError as e:
        return JSONResponse({"error": str(e)}, status_code=400)


@line_comments_api.sub("/{article_type}/{article_slug}/{line_number}").get
async def api_get_line_comments_by_line(
    article_type: str, article_slug: str, line_number: int
) -> dict[str, Any]:
    """获取某一行所有评论。

    参数:
        article_type: 文章类型
        article_slug: 文章标识符
        line_number: 行号

    返回:
        comments: 该行的所有评论列表
    """
    comments = await line_comment_manager.get_line_comments_by_line(
        article_type, article_slug, line_number
    )
    return {"comments": comments}


# ═══════════════════════════════════════════════════════════
#  评分 API
# ═══════════════════════════════════════════════════════════

ratings_api = Route("/api/ratings")


@ratings_api.sub("/{article_type}/{article_slug}").get
async def api_get_rating(
    request: Request, article_type: str, article_slug: str
) -> dict[str, Any]:
    """获取文章评分汇总及当前用户评分。

    参数:
        article_type: 文章类型
        article_slug: 文章标识符

    返回:
        average_score: 平均评分 (0-5)
        total_voters: 评分人数
        user_score: 当前用户的评分（未登录或未评分时为 null）
    """
    summary = await rating_manager.get_article_rating(article_type, article_slug)
    user = await get_current_user(request)
    user_score = None
    if user:
        ur = await rating_manager.get_user_rating(article_type, article_slug, user["username"])
        user_score = ur["score"] if ur else None
    return {
        "average_score": summary["average_score"],
        "total_voters": summary["total_voters"],
        "user_score": user_score,
    }


@ratings_api.sub("/{article_type}/{article_slug}/details").get
async def api_get_rating_details(
    request: Request, article_type: str, article_slug: str
) -> dict[str, Any]:
    """获取文章的所有用户评分详情。

    返回:
        ratings: 所有用户的评分记录列表
    """
    details = await rating_manager.get_all_ratings(article_type, article_slug)
    return {"ratings": details}


@ratings_api.sub("/{article_type}/{article_slug}").post
async def api_set_rating(
    request: Request, article_type: str, article_slug: str
) -> dict[str, Any] | JSONResponse:
    """提交或更新评分（需要登录）。

    请求体 (JSON):
        - score: float  — 评分值 (0-5)

    返回:
        200: 更新后的评分汇总及用户评分
        400: 参数错误
        401: 未登录
    """
    user = await get_current_user(request)
    if user is None:
        return JSONResponse({"error": "请先登录"}, status_code=401)

    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "请求格式错误"}, status_code=400)

    score = body.get("score")
    if score is None:
        return JSONResponse({"error": "缺少评分"}, status_code=400)

    try:
        result = await rating_manager.set_rating(
            article_type=article_type,
            article_slug=article_slug,
            author_name=user["username"],
            score=float(score),
        )
        ur = await rating_manager.get_user_rating(article_type, article_slug, user["username"])
        return {
            "average_score": result["average_score"],
            "total_voters": result["total_voters"],
            "user_score": ur["score"] if ur else None,
        }
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=400)


@ratings_api.sub("/{article_type}/{article_slug}").delete
async def api_delete_rating(
    request: Request, article_type: str, article_slug: str
) -> dict[str, Any] | JSONResponse:
    """撤销评分（需要登录）。

    返回:
        200: 撤销后的评分汇总
        404: 用户尚未对该文章评分
        401: 未登录
    """
    user = await get_current_user(request)
    if user is None:
        return JSONResponse({"error": "请先登录"}, status_code=401)

    deleted = await rating_manager.delete_rating(
        article_type=article_type,
        article_slug=article_slug,
        author_name=user["username"],
    )
    if not deleted:
        return JSONResponse({"error": "你尚未评分"}, status_code=404)

    # 返回更新后的汇总
    summary = await rating_manager.get_article_rating(article_type, article_slug)
    return {
        "average_score": summary["average_score"],
        "total_voters": summary["total_voters"],
        "user_score": None,
    }

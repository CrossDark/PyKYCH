"""
会话管理模块 — 用户登录状态维持、CSRF 保护、会话固定攻击防护。

安全性设计:
    - 会话固定攻击防护：登录时重新生成会话 ID
    - CSRF Token：使用 itsdangerous 签名的随机令牌
    - 会话过期：服务端可配置超时（默认 24 小时）
    - 安全 Cookie：HttpOnly + SameSite=Lax + Secure（生产环境）

用法:
    from .session import login_user, logout_user, get_current_user
    from .session import generate_csrf_token, verify_csrf_token
"""

import os
import time
from typing import Optional

from .user import get_user_by_username
from . import rate_limit


# ── 会话配置 ────────────────────────────────────────────────

# 会话最大空闲时间（秒），24 小时
SESSION_MAX_AGE = 24 * 60 * 60


# ── 会话辅助函数 ────────────────────────────────────────────


async def get_current_user(request) -> Optional[dict]:
    """
    从请求会话中获取当前登录用户。

    同时验证会话是否过期（last_activity），过期则自动登出。

    参数:
        request: Starlette/Lihil Request 对象

    返回:
        用户字典（含 id, username, nickname, role 等）或 None
    """
    session = request.session if hasattr(request, "session") else {}
    username = session.get("user")
    if not username:
        return None

    # 检查会话是否过期
    last_activity = session.get("last_activity", 0)
    if time.time() - last_activity > SESSION_MAX_AGE:
        # 会话过期，清除
        session.pop("user", None)
        session.pop("last_activity", None)
        session.pop("csrf_token", None)
        return None

    # 更新活动时间
    session["last_activity"] = time.time()

    return await get_user_by_username(username)


async def login_user(request, username: str) -> None:
    """
    用户登录：设置会话并生成 CSRF Token。

    安全性措施:
        1. 重新生成会话 ID（防会话固定攻击）
        2. 生成 CSRF Token
        3. 记录登录时间（用于会话过期检查）
        4. 清除失败计数（速率限制重置）

    参数:
        request: Starlette/Lihil Request 对象
        username: 成功登录的用户名
    """
    if not hasattr(request, "session"):
        return

    session = request.session

    # 防会话固定：清除旧会话数据
    session.clear()

    # 设置新的会话数据
    session["user"] = username
    session["login_time"] = time.time()
    session["last_activity"] = time.time()

    # 生成并存储 CSRF Token
    csrf_token = _generate_token()
    session["csrf_token"] = csrf_token

    # 重置该用户/IP 的登录失败计数
    client_ip = _get_client_ip(request)
    rate_limit.reset_login_rate_limit(username, client_ip)


def logout_user(request) -> None:
    """
    用户登出：完全清除会话数据。

    安全性措施:
        清除所有会话键，不留残留数据。

    参数:
        request: Starlette/Lihil Request 对象
    """
    if hasattr(request, "session"):
        request.session.clear()


# ── CSRF 保护 ───────────────────────────────────────────────


def generate_csrf_token(request) -> str:
    """
    生成并存储 CSRF Token。

    CSRF Token 在登录时自动生成，此函数用于获取当前有效的 Token。
    如果会话中不存在 Token，会自动创建。

    参数:
        request: Starlette/Lihil Request 对象

    返回:
        CSRF Token 字符串（64 字符十六进制）
    """
    if not hasattr(request, "session"):
        # 无会话支持时，返回一次性 Token（功能降级）
        return _generate_token()

    token = request.session.get("csrf_token")
    if not token:
        token = _generate_token()
        request.session["csrf_token"] = token
    return token


def verify_csrf_token(request, token: str) -> bool:
    """
    验证 CSRF Token。

    使用恒定时间比较防止时序攻击。
    验证成功后 Token 保持不变（非一次性）。

    参数:
        request: Starlette/Lihil Request 对象
        token:  客户端提交的 CSRF Token

    返回:
        True 表示验证通过，False 表示无效
    """
    if not token:
        return False
    if not hasattr(request, "session"):
        return False

    expected = request.session.get("csrf_token", "")
    if not expected:
        return False

    # 恒定时间比较
    import hmac
    return hmac.compare_digest(expected, token)


# ── 登录/权限装饰器 ─────────────────────────────────────────


async def require_login(request):
    """
    要求登录的检查函数。

    返回 (user, error_response)。
    如果未登录，error_response 是重定向到登录页的响应；
    如果已登录，error_response 为 None。

    用法:
        user, err = await require_login(request)
        if err:
            return err
        # user 可用

    参数:
        request: Starlette/Lihil Request 对象

    返回:
        (user_dict | None, error_RedirectResponse | None)
    """
    from urllib.parse import quote

    user = await get_current_user(request)
    if user is None:
        from starlette.responses import RedirectResponse
        target = quote(request.url.path, safe="")
        return None, RedirectResponse(
            f"/auth/login?next={target}", status_code=303
        )
    return user, None


async def require_admin(request):
    """
    要求管理员权限的检查函数。

    先检查登录状态，再检查是否为 admin 或 owner 角色。

    用法:
        user, err = await require_admin(request)
        if err:
            return err

    参数:
        request: Starlette/Lihil Request 对象

    返回:
        (user_dict | None, error_RedirectResponse | None)
    """
    from starlette.responses import RedirectResponse

    user, err = await require_login(request)
    if err:
        return None, err

    role = user.get("role", "user")
    if role not in ("admin", "owner"):
        return None, RedirectResponse("/", status_code=303)

    return user, None


async def require_owner(request):
    """
    要求站长权限的检查函数。

    先检查登录状态，再检查是否为 owner 角色。

    用法:
        user, err = await require_owner(request)
        if err:
            return err

    参数:
        request: Starlette/Lihil Request 对象

    返回:
        (user_dict | None, error_RedirectResponse | None)
    """
    from starlette.responses import RedirectResponse

    user, err = await require_login(request)
    if err:
        return None, err

    if user.get("role") != "owner":
        return None, RedirectResponse("/", status_code=303)

    return user, None


# ── 内部辅助 ────────────────────────────────────────────────


def _generate_token() -> str:
    """生成 64 字符十六进制随机令牌。"""
    return os.urandom(32).hex()


def _get_client_ip(request) -> str:
    """
    获取客户端 IP 地址（考虑代理）。

    优先级: X-Forwarded-For > X-Real-IP > request.client.host
    """
    forwarded = request.headers.get("X-Forwarded-For", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    real_ip = request.headers.get("X-Real-IP", "")
    if real_ip:
        return real_ip.strip()
    if hasattr(request, "client") and request.client:
        return request.client.host
    return "127.0.0.1"

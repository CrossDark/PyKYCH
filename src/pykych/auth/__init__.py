"""
认证模块 (auth) — 用户认证、会话管理、密码安全、通行密钥。

本模块将登录相关功能全部移至后端，增强安全性：
- PBKDF2-HMAC-SHA256 密码哈希（60 万次迭代）
- 会话管理与 CSRF 保护
- 登录速率限制（防暴力破解）
- 密码强度校验
- 会话固定攻击防护（登录后重新生成会话 ID）
- 数学验证码（防机器人）
- WebAuthn/Passkey 通行密钥支持

模块结构:
    __init__.py     — 公开接口导出
    password.py     — 密码哈希与验证、密码强度校验
    session.py      — 会话管理（创建、验证、销毁、CSRF）
    user.py         — 用户 CRUD（增删改查、角色管理）
    rate_limit.py   — 登录速率限制（内存 + 可选 Redis）
    webauthn.py     — 通行密钥注册与认证
"""

from .password import hash_password, verify_password, validate_password_strength
from .session import (
    get_current_user,
    login_user,
    logout_user,
    generate_csrf_token,
    verify_csrf_token,
    require_login,
    require_admin,
    require_owner,
)
from .user import (
    get_user_by_username,
    get_user_with_password,
    list_users,
    create_user,
    update_user_password,
    update_user_info,
    update_user_role,
    delete_user,
    is_owner,
    is_admin,
    can_manage_users,
)
from .rate_limit import (
    check_login_rate_limit,
    reset_login_rate_limit,
)

__all__ = [
    # 密码
    "hash_password",
    "verify_password",
    "validate_password_strength",
    # 会话
    "get_current_user",
    "login_user",
    "logout_user",
    "generate_csrf_token",
    "verify_csrf_token",
    "require_login",
    "require_admin",
    "require_owner",
    # 用户
    "get_user_by_username",
    "get_user_with_password",
    "list_users",
    "create_user",
    "update_user_password",
    "update_user_info",
    "update_user_role",
    "delete_user",
    # 速率限制
    "check_login_rate_limit",
    "reset_login_rate_limit",
]

"""
用户资料管理模块 — 用户个人资料、头像、密码修改。
"""

import os
import hashlib
from pathlib import Path
from typing import Optional

from .mysql_manager import get_sys_pool, row_to_dict
from .auth import hash_password, verify_password

# ── 头像目录 ─────────────────────────────────────────────────

AVATAR_DIR = Path(__file__).parent / "static" / "avatars"
DEFAULT_AVATAR = "/static/img/default-avatar.png"


def _ensure_avatar_dir() -> None:
    """确保头像目录存在（惰性创建）。"""
    try:
        AVATAR_DIR.mkdir(parents=True, exist_ok=True)
    except (OSError, PermissionError):
        pass


# ── 用户资料 CRUD ────────────────────────────────────────────


async def get_user_profile(username: str) -> Optional[dict]:
    """获取用户完整资料（含头像、简介等）。"""
    pool = await get_sys_pool()
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                "SELECT id, username, nickname, role, avatar, bio, email, "
                "website, created_at "
                "FROM users WHERE username = %s",
                (username,),
            )
            row = await cur.fetchone()
            if not row:
                return None
            profile = row_to_dict(row, cur)
            if not profile.get("avatar"):
                profile["avatar"] = DEFAULT_AVATAR
            return profile


async def update_profile(
    username: str,
    nickname: str = None,
    bio: str = None,
    email: str = None,
    website: str = None,
) -> bool:
    """更新用户个人资料。"""
    pool = await get_sys_pool()
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            updates = []
            params = []

            if nickname is not None:
                updates.append("nickname = %s")
                params.append(nickname)
            if bio is not None:
                updates.append("bio = %s")
                params.append(bio)
            if email is not None:
                updates.append("email = %s")
                params.append(email)
            if website is not None:
                updates.append("website = %s")
                params.append(website)

            if not updates:
                return False

            params.append(username)
            await cur.execute(
                f"UPDATE users SET {', '.join(updates)} WHERE username = %s",
                params,
            )
            return cur.rowcount > 0


async def change_password(
    username: str, old_password: str, new_password: str
) -> tuple[bool, str]:
    """
    修改密码。需要验证旧密码。
    返回 (成功, 消息)
    """
    if len(new_password) < 6:
        return False, "新密码至少需要 6 个字符。"

    pool = await get_sys_pool()
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                "SELECT password_hash FROM users WHERE username = %s",
                (username,),
            )
            row = await cur.fetchone()
            if not row:
                return False, "用户不存在。"

            current_hash = row[0]
            if not verify_password(old_password, current_hash):
                return False, "旧密码不正确。"

            new_hash = hash_password(new_password)
            await cur.execute(
                "UPDATE users SET password_hash = %s WHERE username = %s",
                (new_hash, username),
            )
            return True, "密码修改成功。"


async def save_avatar(username: str, file_data: bytes, filename: str) -> Optional[str]:
    """
    保存用户头像。返回头像 URL 路径。
    """
    # 生成唯一文件名
    ext = os.path.splitext(filename)[1].lower()
    if ext not in (".png", ".jpg", ".jpeg", ".gif", ".webp"):
        ext = ".png"

    avatar_name = f"{username}_{hashlib.md5(file_data).hexdigest()[:12]}{ext}"
    _ensure_avatar_dir()
    avatar_path = AVATAR_DIR / avatar_name

    try:
        with open(avatar_path, "wb") as f:
            f.write(file_data)
    except (OSError, PermissionError):
        return None

    avatar_url = f"/static/avatars/{avatar_name}"

    # 更新数据库中的头像路径
    pool = await get_sys_pool()
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                "UPDATE users SET avatar = %s WHERE username = %s",
                (avatar_url, username),
            )

    return avatar_url


# ── 确保 users 表有资料字段 ──────────────────────────────────


async def ensure_profile_columns() -> None:
    """确保 users 表包含头像、简介等字段（迁移用）。"""
    pool = await get_sys_pool()
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            # 检查并添加列
            migrations = [
                ("avatar", "VARCHAR(500) DEFAULT NULL"),
                ("bio", "TEXT DEFAULT NULL"),
                ("email", "VARCHAR(255) DEFAULT NULL"),
                ("website", "VARCHAR(500) DEFAULT NULL"),
            ]
            for col_name, col_def in migrations:
                try:
                    await cur.execute(
                        f"ALTER TABLE users ADD COLUMN {col_name} {col_def}"
                    )
                except Exception:
                    pass  # 列已存在

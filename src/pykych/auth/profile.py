"""
用户资料管理模块 — 用户个人资料、头像、密码修改。
"""

import os
import hashlib
import logging
from pathlib import Path
from typing import Optional

from ..core.db import get_sys_pool, row_to_dict
from .password import hash_password, verify_password, validate_password_strength

logger = logging.getLogger(__name__)

# ── 头像目录 ─────────────────────────────────────────────────

AVATAR_DIR = Path(__file__).parent.parent.parent.parent / "data" / "avatars"
DEFAULT_AVATAR = "/static/img/default-avatar.png"


def _ensure_avatar_dir() -> None:
    """确保头像目录存在（惰性创建）。"""
    try:
        AVATAR_DIR.mkdir(parents=True, exist_ok=True)
    except (OSError, PermissionError) as e:
        logger.warning(f"无法创建头像目录 {AVATAR_DIR}: {e}")


# ── 图片格式检测（基于文件头魔数） ──────────────────────────

# 魔数签名: (前缀字节, 扩展名)
_MAGIC_SIGNATURES: list[tuple[bytes, str]] = [
    (b"\x89PNG\r\n\x1a\n", ".png"),
    (b"\xff\xd8\xff", ".jpg"),       # JPEG 通用
    (b"GIF87a", ".gif"),
    (b"GIF89a", ".gif"),
    (b"RIFF", ".webp"),              # WebP (需要额外检查 WEBPVP8)
    (b"<svg", ".svg"),               # SVG (文本)
    (b"\x00\x00\x01\x00", ".ico"),   # ICO
    (b"<?xml", ".svg"),              # SVG (XML)
    (b"BM", ".bmp"),                 # BMP
]


def _detect_image_ext(data: bytes, filename: str = "") -> str:
    """
    通过文件头魔数检测图片真实格式。
    检测失败时回退到文件扩展名，再失败返回 ".png"。
    """
    # 1. WebP 特殊处理：RIFF + WEBPVP8
    if data[:4] == b"RIFF" and len(data) >= 12 and data[8:16] == b"WEBPVP8 ":
        return ".webp"
    if data[:4] == b"RIFF" and len(data) >= 12 and data[8:15] == b"WEBPVP8":
        return ".webp"

    # 2. SVG 文本检测
    text_head = data[:256].lstrip()  # 跳过 BOM/空白
    if text_head[:4] == b"<svg" or text_head[:5] == b"<?xml":
        return ".svg"

    # 3. 通用魔数匹配
    for magic, ext in _MAGIC_SIGNATURES:
        if data[:len(magic)] == magic:
            return ext

    # 4. 回退到文件扩展名
    if filename:
        ext = os.path.splitext(filename)[1].lower()
        if ext in {".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg", ".ico", ".bmp", ".jfif"}:
            # 统一 .jpeg/.jfif → .jpg
            if ext in (".jpeg", ".jfif"):
                return ".jpg"
            return ext

    # 5. 最终回退
    return ".png"


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
    # 使用统一的密码强度校验
    strength_error = validate_password_strength(new_password)
    if strength_error:
        return False, strength_error

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
    保存用户头像。返回头像 URL 路径，失败返回 None。
    会自动清理该用户的旧头像文件。
    通过文件头魔数检测真实格式，不依赖文件扩展名。
    """
    if not file_data:
        logger.warning(f"用户 {username} 上传了空头像文件")
        return None

    # 通过文件头魔数检测真实图片格式
    ext = _detect_image_ext(file_data, filename)

    avatar_name = f"{username}_{hashlib.md5(file_data).hexdigest()[:12]}{ext}"
    _ensure_avatar_dir()
    avatar_path = AVATAR_DIR / avatar_name

    # 先查出旧头像路径，用于后续清理
    old_avatar_url: Optional[str] = None
    pool = await get_sys_pool()
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                "SELECT avatar FROM users WHERE username = %s",
                (username,),
            )
            row = await cur.fetchone()
            if row and row[0]:
                old_avatar_url = row[0]

    # 写入新头像文件
    try:
        with open(avatar_path, "wb") as f:
            f.write(file_data)
    except (OSError, PermissionError) as e:
        logger.error(f"无法写入头像文件 {avatar_path}: {e}")
        return None

    avatar_url = f"/static/avatars/{avatar_name}"

    # 更新数据库中的头像路径
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                "UPDATE users SET avatar = %s WHERE username = %s",
                (avatar_url, username),
            )

    # 清理旧头像文件（避免磁盘堆积）
    if old_avatar_url and old_avatar_url.startswith("/static/avatars/"):
        old_filename = old_avatar_url[len("/static/avatars/"):]
        # 不删除刚写入的新文件
        if old_filename != avatar_name:
            old_path = AVATAR_DIR / old_filename
            if old_path.exists() and old_path.is_file():
                try:
                    old_path.unlink()
                    logger.info(f"已删除旧头像: {old_filename}")
                except (OSError, PermissionError) as e:
                    logger.warning(f"无法删除旧头像 {old_filename}: {e}")

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

"""
用户认证模块 — 密码哈希、会话管理、用户 CRUD。
使用 hashlib.pbkdf2_hmac（标准库，无外部依赖）。
"""

import hashlib
import os
from typing import Optional

from .mysql_manager import get_md_pool, row_to_dict

# ── 密码哈希 (PBKDF2-HMAC-SHA256) ────────────────────────────

_SALT_LEN = 32
_ITERATIONS = 600_000
_KEY_LEN = 32


def hash_password(password: str) -> str:
    """返回 '$pbkdf2$iterations$salt_hex$hash_hex' 格式的字符串。"""
    salt = os.urandom(_SALT_LEN)
    key = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, _ITERATIONS, _KEY_LEN)
    return f"$pbkdf2${_ITERATIONS}${salt.hex()}${key.hex()}"


def verify_password(plain: str, hashed: str) -> bool:
    """验证明文密码与哈希值是否匹配。"""
    try:
        _, algo, iterations, salt_hex, key_hex = hashed.split("$")
        if algo != "pbkdf2":
            return False
        salt = bytes.fromhex(salt_hex)
        expected = bytes.fromhex(key_hex)
        actual = hashlib.pbkdf2_hmac(
            "sha256", plain.encode(), salt, int(iterations), len(expected)
        )
        return actual == expected
    except (ValueError, AttributeError):
        return False


# ── 用户 CRUD ────────────────────────────────────────────────


async def get_user_by_username(username: str) -> Optional[dict]:
    pool = await get_md_pool()
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                "SELECT id, username, nickname, is_admin, created_at "
                "FROM users WHERE username = %s", (username,),
            )
            row = await cur.fetchone()
            return row_to_dict(row, cur) if row else None


async def get_user_with_password(username: str) -> Optional[dict]:
    pool = await get_md_pool()
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                "SELECT * FROM users WHERE username = %s", (username,),
            )
            row = await cur.fetchone()
            return row_to_dict(row, cur) if row else None


async def list_users() -> list[dict]:
    pool = await get_md_pool()
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                "SELECT id, username, nickname, is_admin, created_at "
                "FROM users ORDER BY created_at DESC"
            )
            rows = await cur.fetchall()
            return [row_to_dict(r, cur) for r in rows]


async def create_user(
    username: str, password: str, nickname: str = "", is_admin: bool = False
) -> dict:
    pool = await get_md_pool()
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            pwd_hash = hash_password(password)
            await cur.execute(
                "INSERT INTO users (username, password_hash, nickname, is_admin) "
                "VALUES (%s, %s, %s, %s)",
                (username, pwd_hash, nickname or username, is_admin),
            )
            return await get_user_by_username(username)


async def update_user_password(username: str, new_password: str) -> bool:
    pool = await get_md_pool()
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            pwd_hash = hash_password(new_password)
            await cur.execute(
                "UPDATE users SET password_hash = %s WHERE username = %s",
                (pwd_hash, username),
            )
            return cur.rowcount > 0


async def update_user_info(
    username: str, nickname: str = "", is_admin: bool = False
) -> bool:
    pool = await get_md_pool()
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                "UPDATE users SET nickname = %s, is_admin = %s WHERE username = %s",
                (nickname, username, is_admin),
            )
            return cur.rowcount > 0


async def delete_user(username: str) -> bool:
    pool = await get_md_pool()
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                "DELETE FROM users WHERE username = %s", (username,),
            )
            return cur.rowcount > 0


# ── 会话工具 ─────────────────────────────────────────────────

async def get_current_user(request) -> Optional[dict]:
    session = request.session if hasattr(request, "session") else {}
    username = session.get("user")
    if not username:
        return None
    return await get_user_by_username(username)


def login_user(request, username: str) -> None:
    if hasattr(request, "session"):
        request.session["user"] = username


def logout_user(request) -> None:
    if hasattr(request, "session"):
        request.session.pop("user", None)

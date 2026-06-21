"""
用户数据访问层 — 用户 CRUD 操作、角色管理。

所有用户管理操作通过此模块进行，确保:
    - 统一的权限控制入口
    - 密码哈希处理隔离
    - 角色枚举校验

表结构 (users):
    id            INT AUTO_INCREMENT PRIMARY KEY
    username      VARCHAR(64) UNIQUE NOT NULL
    password_hash VARCHAR(255) NOT NULL
    nickname      VARCHAR(128) NOT NULL DEFAULT ''
    role          ENUM('user', 'admin', 'owner') NOT NULL DEFAULT 'user'
    created_at    DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP

用法:
    from .user import get_user_by_username, create_user, list_users
"""

from typing import Optional

from ..core.db import get_sys_pool, row_to_dict
from .password import hash_password, validate_password_strength


# ── 角色常量 ────────────────────────────────────────────────

VALID_ROLES = ("user", "admin", "owner")


# ── 用户查询 ────────────────────────────────────────────────


async def get_user_by_username(username: str) -> Optional[dict]:
    """
    根据用户名获取用户基本信息（不含密码哈希）。

    返回字段: id, username, nickname, role, avatar, created_at

    参数:
        username: 用户名

    返回:
        用户字典或 None
    """
    pool = await get_sys_pool()
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            # 优先查询含 avatar 的完整字段；若 avatar 列不存在则回退
            try:
                await cur.execute(
                    "SELECT id, username, nickname, role, "
                    "COALESCE(avatar, '') AS avatar, created_at "
                    "FROM users WHERE username = %s",
                    (username,),
                )
            except Exception:
                await cur.execute(
                    "SELECT id, username, nickname, role, created_at "
                    "FROM users WHERE username = %s",
                    (username,),
                )
            row = await cur.fetchone()
            return row_to_dict(row, cur) if row else None


async def get_user_with_password(username: str) -> Optional[dict]:
    """
    根据用户名获取用户完整信息（含密码哈希）。

    仅用于登录验证等需要密码哈希的场景。
    返回字段: id, username, password_hash, nickname, role, created_at

    参数:
        username: 用户名

    返回:
        用户字典或 None
    """
    pool = await get_sys_pool()
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                "SELECT * FROM users WHERE username = %s",
                (username,),
            )
            row = await cur.fetchone()
            return row_to_dict(row, cur) if row else None


async def list_users() -> list[dict]:
    """
    获取所有用户列表（按创建时间倒序，不含密码哈希）。

    返回字段: id, username, nickname, role, created_at

    返回:
        用户字典列表
    """
    pool = await get_sys_pool()
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                "SELECT id, username, nickname, role, created_at "
                "FROM users ORDER BY created_at DESC"
            )
            rows = await cur.fetchall()
            return [row_to_dict(r, cur) for r in rows]


# ── 用户创建 ────────────────────────────────────────────────


async def create_user(
    username: str,
    password: str,
    nickname: str = "",
    role: str = "user",
) -> dict:
    """
    创建新用户。

    执行密码强度校验后生成 PBKDF2 哈希存储。

    参数:
        username: 用户名（唯一，3-64 字符）
        password: 明文密码（至少 8 字符，含大小写字母+数字）
        nickname: 昵称（默认同用户名）
        role:     角色（'user', 'admin', 'owner'）

    返回:
        新创建的用户字典（不含密码哈希）

    异常:
        ValueError: 密码强度不足或角色无效
    """
    # 校验密码强度
    error = validate_password_strength(password)
    if error:
        raise ValueError(error)

    # 校验角色
    if role not in VALID_ROLES:
        raise ValueError(f"无效的角色: {role}，有效值: {', '.join(VALID_ROLES)}")

    # 校验用户名长度
    if not username or len(username) < 3 or len(username) > 64:
        raise ValueError("用户名长度需要在 3-64 个字符之间")

    pool = await get_sys_pool()
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            pwd_hash = hash_password(password)
            await cur.execute(
                "INSERT INTO users (username, password_hash, nickname, role) "
                "VALUES (%s, %s, %s, %s)",
                (username, pwd_hash, nickname or username, role),
            )
            return await get_user_by_username(username)


# ── 用户更新 ────────────────────────────────────────────────


async def update_user_password(username: str, new_password: str) -> bool:
    """
    更新用户密码。

    执行密码强度校验后生成新哈希。

    参数:
        username:     用户名
        new_password: 新密码（需满足强度要求）

    返回:
        True 表示更新成功，False 表示用户不存在

    异常:
        ValueError: 密码强度不足
    """
    error = validate_password_strength(new_password)
    if error:
        raise ValueError(error)

    pool = await get_sys_pool()
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            pwd_hash = hash_password(new_password)
            await cur.execute(
                "UPDATE users SET password_hash = %s WHERE username = %s",
                (pwd_hash, username),
            )
            return cur.rowcount > 0


async def update_user_info(
    username: str, nickname: str = "", role: str = "user"
) -> bool:
    """
    更新用户信息（昵称、角色）。

    参数:
        username: 用户名
        nickname: 新昵称
        role:     新角色

    返回:
        True 表示更新成功，False 表示用户不存在
    """
    if role not in VALID_ROLES:
        raise ValueError(f"无效的角色: {role}")

    pool = await get_sys_pool()
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                "UPDATE users SET nickname = %s, role = %s WHERE username = %s",
                (nickname, role, username),
            )
            return cur.rowcount > 0


async def update_user_role(username: str, role: str) -> bool:
    """
    更新用户角色（仅站长可用）。

    参数:
        username: 用户名
        role:     新角色 ('user', 'admin', 'owner')

    返回:
        True 表示更新成功，False 表示用户不存在或角色无效
    """
    if role not in VALID_ROLES:
        return False

    pool = await get_sys_pool()
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                "UPDATE users SET role = %s WHERE username = %s",
                (role, username),
            )
            return cur.rowcount > 0


# ── 用户删除 ────────────────────────────────────────────────


async def delete_user(username: str) -> bool:
    """
    删除用户及其所有关联数据。

    级联清理顺序：
        1. 评论 (comments)
        2. 评分 (ratings) 
        3. 行评论 (line_comments)
        4. 标签关联 (article_tags)
        5. 通行密钥 (webauthn_credentials)
        6. 上传文件 (static_files)
        7. 推荐文章 (featured_articles)
        8. 文章 (articles / pages / html_pages / bbcode_pages / typst_pages)
        9. 用户本体 (users)

    参数:
        username: 要删除的用户名

    返回:
        True 表示删除成功，False 表示用户不存在
    """
    pool = await get_sys_pool()
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            # 开启事务，确保所有删除操作原子执行
            await conn.begin()
            try:
                # 1. 删除用户评论
                await cur.execute(
                    "DELETE FROM comments WHERE author_name = %s",
                    (username,),
                )
                # 2. 删除用户评分
                await cur.execute(
                    "DELETE FROM ratings WHERE author_name = %s",
                    (username,),
                )
                # 3. 删除用户行评论
                await cur.execute(
                    "DELETE FROM line_comments WHERE author_name = %s",
                    (username,),
                )
                # 4. 删除用户在所有文章类型中的标签关联
                await cur.execute(
                    "DELETE FROM article_tags WHERE (article_type, article_slug) IN ("
                    "SELECT 'md', slug FROM articles WHERE author_id = "
                    "(SELECT id FROM users WHERE username = %s) "
                    "UNION "
                    "SELECT 'wikidot', slug FROM pages WHERE author_id = "
                    "(SELECT id FROM users WHERE username = %s) "
                    "UNION "
                    "SELECT 'html', slug FROM html_pages WHERE author_id = "
                    "(SELECT id FROM users WHERE username = %s) "
                    "UNION "
                    "SELECT 'bbcode', slug FROM bbcode_pages WHERE author_id = "
                    "(SELECT id FROM users WHERE username = %s) "
                    "UNION "
                    "SELECT 'typst', slug FROM typst_pages WHERE author_id = "
                    "(SELECT id FROM users WHERE username = %s)"
                    ")",
                    (username, username, username, username, username),
                )
                # 5. 删除通行密钥
                await cur.execute(
                    "DELETE FROM webauthn_credentials WHERE username = %s",
                    (username,),
                )
                # 6. 删除上传文件物理记录
                await cur.execute(
                    "DELETE FROM static_files WHERE uploaded_by = "
                    "(SELECT id FROM users WHERE username = %s)",
                    (username,),
                )
                # 7. 删除推荐文章（指向用户文章的推荐记录）
                await cur.execute(
                    "DELETE FROM featured_articles WHERE article_slug IN "
                    "(SELECT slug FROM articles WHERE author_id = "
                    "(SELECT id FROM users WHERE username = %s))",
                    (username,),
                )
                # 8. 删除用户文章
                for table in ("articles", "pages", "html_pages", "bbcode_pages", "typst_pages"):
                    try:
                        await cur.execute(
                            f"DELETE FROM {table} WHERE author_id = "
                            "(SELECT id FROM users WHERE username = %s)",
                            (username,),
                        )
                    except Exception:
                        pass  # 表可能不存在
                # 9. 删除用户
                await cur.execute(
                    "DELETE FROM users WHERE username = %s",
                    (username,),
                )
                await conn.commit()
                return cur.rowcount > 0
            except Exception:
                await conn.rollback()
                raise


# ── 角色检查辅助 ────────────────────────────────────────────


def is_owner(user: dict | None) -> bool:
    """检查用户是否为站长。"""
    return user is not None and user.get("role") == "owner"


def is_admin(user: dict | None) -> bool:
    """检查用户是否为管理员及以上（admin 或 owner）。"""
    return user is not None and user.get("role") in ("admin", "owner")


def can_manage_users(user: dict | None) -> bool:
    """检查用户是否可以管理其他用户（仅站长）。"""
    return is_owner(user)

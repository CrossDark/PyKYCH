"""
MySQL 连接管理器 — 读取 settings/db.yaml，管理连接池。

用法:
    from .mysql_manager import get_md_pool, get_wk_pool, get_sys_pool
"""

import yaml
from pathlib import Path
from typing import Any

import aiomysql

# ── 加载配置 ────────────────────────────────────────────────

CONFIG_PATH = Path(__file__).parent.parent.parent / "settings" / "db.yaml"

with open(CONFIG_PATH, "r", encoding="utf-8") as f:
    _config: dict[str, Any] = yaml.safe_load(f)

_mysql = _config["mysql"]


# ── 全局连接池 (惰性创建) ───────────────────────────────────

_md_pool: aiomysql.Pool | None = None
_wk_pool: aiomysql.Pool | None = None
_sys_pool: aiomysql.Pool | None = None


async def _create_pool(database: str) -> aiomysql.Pool:
    """创建 MySQL 连接池。"""
    pool_cfg = _mysql.get("pool", {})
    return await aiomysql.create_pool(
        host=_mysql["host"],
        port=_mysql.get("port", 3306),
        user=_mysql["user"],
        password=_mysql["password"],
        db=database,
        charset=_mysql.get("charset", "utf8mb4"),
        minsize=pool_cfg.get("minsize", 2),
        maxsize=pool_cfg.get("maxsize", 10),
        pool_recycle=pool_cfg.get("pool_recycle", 3600),
        autocommit=True,
    )


async def get_md_pool() -> aiomysql.Pool:
    """获取 Markdown 数据库连接池。"""
    global _md_pool
    if _md_pool is None:
        _md_pool = await _create_pool(_mysql["markdown_db"])
    return _md_pool


async def get_wk_pool() -> aiomysql.Pool:
    """获取 Wikidot 数据库连接池。"""
    global _wk_pool
    if _wk_pool is None:
        _wk_pool = await _create_pool(_mysql["wikidot_db"])
    return _wk_pool


async def get_sys_pool() -> aiomysql.Pool:
    """获取系统管理数据库连接池（用户、配置等）。"""
    global _sys_pool
    if _sys_pool is None:
        _sys_pool = await _create_pool(_mysql["system_db"])
    return _sys_pool


async def close_pools() -> None:
    """关闭所有连接池（应用关闭时调用）。"""
    global _md_pool, _wk_pool, _sys_pool
    for pool in (_md_pool, _wk_pool, _sys_pool):
        if pool:
            pool.close()
            await pool.wait_closed()
    _md_pool = _wk_pool = _sys_pool = None


# ── 表初始化 ────────────────────────────────────────────────

MD_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS articles (
    id          INT AUTO_INCREMENT PRIMARY KEY,
    slug        VARCHAR(255) UNIQUE NOT NULL,
    title       VARCHAR(255) NOT NULL,
    content     LONGTEXT NOT NULL,
    created_at  DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at  DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,

    INDEX idx_slug (slug),
    INDEX idx_created (created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
"""

WK_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS pages (
    id          INT AUTO_INCREMENT PRIMARY KEY,
    slug        VARCHAR(255) UNIQUE NOT NULL,
    title       VARCHAR(255) NOT NULL,
    content     LONGTEXT NOT NULL,
    created_at  DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at  DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,

    INDEX idx_slug (slug),
    INDEX idx_created (created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
"""

USERS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS users (
    id            INT AUTO_INCREMENT PRIMARY KEY,
    username      VARCHAR(64)  UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    nickname      VARCHAR(128) NOT NULL DEFAULT '',
    role          ENUM('user', 'admin', 'owner') NOT NULL DEFAULT 'user',
    created_at    DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,

    INDEX idx_username (username)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
"""


async def _safe_add_column(cur, table: str, column: str, definition: str) -> None:
    """安全地添加列（如果不存在则添加，忽略错误）。"""
    try:
        await cur.execute(
            f"ALTER TABLE {table} ADD COLUMN {column} {definition}"
        )
    except Exception:
        pass  # 列已存在则跳过


async def _migrate_user_roles(cur) -> None:
    """将旧的 is_admin 字段迁移为 role 枚举。"""
    try:
        # 检查 role 列是否存在
        await cur.execute(
            "SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS "
            "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'users' "
            "AND COLUMN_NAME = 'role'"
        )
        has_role = await cur.fetchone() is not None

        if not has_role:
            # 添加 role 列
            await cur.execute(
                "ALTER TABLE users ADD COLUMN role ENUM('user','admin','owner') "
                "NOT NULL DEFAULT 'user'"
            )

        # 检查 is_admin 列是否存在
        await cur.execute(
            "SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS "
            "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'users' "
            "AND COLUMN_NAME = 'is_admin'"
        )
        if await cur.fetchone():
            # 迁移：is_admin=1 -> role='admin'
            await cur.execute(
                "UPDATE users SET role = 'admin' WHERE is_admin = 1 AND role = 'user'"
            )
            # 删除旧列
            await cur.execute("ALTER TABLE users DROP COLUMN is_admin")
    except Exception:
        pass  # 列不存在或已迁移


async def init_tables() -> None:
    """在应用启动时确保表结构存在，并执行必要的迁移。"""
    md_pool = await get_md_pool()
    async with md_pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute(MD_TABLE_SQL)
            # 迁移：添加 author_id 列（如果不存在）
            await _safe_add_column(cur, "articles", "author_id", "INT DEFAULT NULL")

    wk_pool = await get_wk_pool()
    async with wk_pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute(WK_TABLE_SQL)
            # 迁移：添加 author_id 列（如果不存在）
            await _safe_add_column(cur, "pages", "author_id", "INT DEFAULT NULL")

    sys_pool = await get_sys_pool()
    async with sys_pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute(USERS_TABLE_SQL)
            # 迁移：从 is_admin 升级到 role
            await _migrate_user_roles(cur)


async def seed_admin(username: str, password: str, nickname: str = "") -> None:
    """创建默认站长（如不存在），或将已有管理员升级为站长。"""
    from .auth import hash_password
    pool = await get_sys_pool()
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute("SELECT COUNT(*) FROM users WHERE username = %s", (username,))
            if (await cur.fetchone())[0] == 0:
                pwd_hash = hash_password(password)
                await cur.execute(
                    "INSERT INTO users (username, password_hash, nickname, role) "
                    "VALUES (%s, %s, %s, 'owner')",
                    (username, pwd_hash, nickname or username),
                )
            else:
                # 确保已有管理员升级为站长
                await cur.execute(
                    "UPDATE users SET role = 'owner' WHERE username = %s AND role = 'admin'",
                    (username,),
                )


# ── 工具函数 ────────────────────────────────────────────────

def row_to_dict(row: tuple, cursor: aiomysql.Cursor) -> dict:
    """将查询结果行转为字典，datetime 对象转为 ISO 字符串。"""
    from datetime import datetime, date
    cols = [desc[0] for desc in cursor.description]
    result = {}
    for col, val in zip(cols, row):
        if isinstance(val, (datetime, date)):
            result[col] = val.isoformat()
        else:
            result[col] = val
    return result

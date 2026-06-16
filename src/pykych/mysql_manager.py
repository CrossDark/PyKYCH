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

_pool: aiomysql.Pool | None = None


async def _create_pool() -> aiomysql.Pool:
    """创建 MySQL 连接池（统一使用 pykych 数据库）。如果数据库不存在则尝试自动创建。"""
    pool_cfg = _mysql.get("pool", {})
    db_name = _mysql["database"]

    async def _connect(db: str) -> aiomysql.Pool:
        return await aiomysql.create_pool(
            host=_mysql["host"],
            port=_mysql.get("port", 3306),
            user=_mysql["user"],
            password=_mysql["password"],
            db=db,
            charset=_mysql.get("charset", "utf8mb4"),
            minsize=pool_cfg.get("minsize", 2),
            maxsize=pool_cfg.get("maxsize", 10),
            pool_recycle=pool_cfg.get("pool_recycle", 3600),
            autocommit=True,
        )

    # 尝试直接连接目标数据库
    try:
        return await _connect(db_name)
    except Exception as e:
        err_msg = str(e)
        # 如果数据库不存在 (错误码 1049)，尝试创建
        if "1049" not in err_msg and "Unknown database" not in err_msg:
            raise

    # 数据库不存在，尝试创建
    try:
        temp_conn = await aiomysql.connect(
            host=_mysql["host"],
            port=_mysql.get("port", 3306),
            user=_mysql["user"],
            password=_mysql["password"],
            charset=_mysql.get("charset", "utf8mb4"),
            autocommit=True,
        )
        try:
            async with temp_conn.cursor() as cur:
                await cur.execute(
                    f"CREATE DATABASE IF NOT EXISTS `{db_name}` "
                    "CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
                )
        finally:
            temp_conn.close()
    except Exception as e:
        raise RuntimeError(
            f"数据库 '{db_name}' 不存在且无法自动创建（权限不足）。\n"
            f"请在 MySQL 中手动执行: CREATE DATABASE IF NOT EXISTS `{db_name}` "
            "CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;\n"
            f"原始错误: {e}"
        ) from e

    # 创建成功后连接目标数据库
    return await _connect(db_name)


async def _get_pool() -> aiomysql.Pool:
    """获取统一数据库连接池（惰性创建）。"""
    global _pool
    if _pool is None:
        _pool = await _create_pool()
    return _pool


async def get_md_pool() -> aiomysql.Pool:
    """获取 Markdown 文章连接池（指向统一 pykych 数据库）。"""
    return await _get_pool()


async def get_wk_pool() -> aiomysql.Pool:
    """获取 Wikidot 页面连接池（指向统一 pykych 数据库）。"""
    return await _get_pool()


async def get_sys_pool() -> aiomysql.Pool:
    """获取系统管理连接池（指向统一 pykych 数据库）。"""
    return await _get_pool()


async def close_pools() -> None:
    """关闭连接池（应用关闭时调用）。"""
    global _pool
    if _pool:
        _pool.close()
        await _pool.wait_closed()
    _pool = None


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

TAGS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS tags (
    id          INT AUTO_INCREMENT PRIMARY KEY,
    name        VARCHAR(64) UNIQUE NOT NULL,
    created_at  DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,

    INDEX idx_tag_name (name)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
"""

ARTICLE_TAGS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS article_tags (
    id           INT AUTO_INCREMENT PRIMARY KEY,
    article_type ENUM('md', 'wikidot', 'html', 'bbcode') NOT NULL,
    article_slug VARCHAR(255) NOT NULL,
    tag_id       INT NOT NULL,

    UNIQUE KEY uq_article_tag (article_type, article_slug, tag_id),
    INDEX idx_article (article_type, article_slug),
    INDEX idx_tag (tag_id),
    FOREIGN KEY (tag_id) REFERENCES tags(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
"""

HTML_PAGES_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS html_pages (
    id          INT AUTO_INCREMENT PRIMARY KEY,
    slug        VARCHAR(255) UNIQUE NOT NULL,
    title       VARCHAR(255) NOT NULL,
    content     LONGTEXT NOT NULL,
    author_id   INT DEFAULT NULL,
    created_at  DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at  DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,

    INDEX idx_slug (slug),
    INDEX idx_created (created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
"""

BBCODE_PAGES_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS bbcode_pages (
    id          INT AUTO_INCREMENT PRIMARY KEY,
    slug        VARCHAR(255) UNIQUE NOT NULL,
    title       VARCHAR(255) NOT NULL,
    content     LONGTEXT NOT NULL,
    author_id   INT DEFAULT NULL,
    created_at  DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at  DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,

    INDEX idx_slug (slug),
    INDEX idx_created (created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
"""

COMMENTS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS comments (
    id           INT AUTO_INCREMENT PRIMARY KEY,
    article_type ENUM('md','wikidot','html','bbcode') NOT NULL,
    article_slug VARCHAR(255) NOT NULL,
    author_name  VARCHAR(128) NOT NULL DEFAULT '匿名',
    content      TEXT NOT NULL,
    created_at   DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,

    INDEX idx_article (article_type, article_slug),
    INDEX idx_created (created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
"""

SUBSITE_LINKS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS subsite_links (
    id          INT AUTO_INCREMENT PRIMARY KEY,
    name        VARCHAR(255) NOT NULL,
    url         VARCHAR(1024) NOT NULL,
    description VARCHAR(512) DEFAULT '',
    sort_order  INT NOT NULL DEFAULT 0,
    created_at  DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,

    INDEX idx_sort (sort_order)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
"""

FEATURED_ARTICLES_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS featured_articles (
    id           INT AUTO_INCREMENT PRIMARY KEY,
    article_type ENUM('md','wikidot','html','bbcode') NOT NULL,
    article_slug VARCHAR(255) NOT NULL,
    sort_order   INT NOT NULL DEFAULT 0,
    created_at   DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,

    UNIQUE KEY uq_featured (article_type, article_slug),
    INDEX idx_sort (sort_order)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
"""

NOTIFICATIONS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS notifications (
    id           INT AUTO_INCREMENT PRIMARY KEY,
    title        VARCHAR(255) NOT NULL,
    content      TEXT NOT NULL,
    is_important TINYINT(1) NOT NULL DEFAULT 0,
    is_active    TINYINT(1) NOT NULL DEFAULT 1,
    created_at   DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at   DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,

    INDEX idx_important (is_important),
    INDEX idx_active (is_active),
    INDEX idx_created (created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
"""

EXTERNAL_SITES_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS external_sites (
    id           INT AUTO_INCREMENT PRIMARY KEY,
    name         VARCHAR(64) UNIQUE NOT NULL,
    source_url   VARCHAR(1024) NOT NULL,
    description  VARCHAR(512) DEFAULT '',
    auto_tags    VARCHAR(512) DEFAULT '',
    is_active    TINYINT(1) NOT NULL DEFAULT 1,
    created_at   DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at   DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,

    INDEX idx_name (name),
    INDEX idx_active (is_active)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
"""

EXTERNAL_PAGES_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS external_pages (
    id           INT AUTO_INCREMENT PRIMARY KEY,
    site_id      INT NOT NULL,
    path         VARCHAR(512) NOT NULL,
    title        VARCHAR(255) NOT NULL DEFAULT '',
    content      LONGTEXT NOT NULL,
    fetched_at   DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,

    UNIQUE KEY uq_site_path (site_id, path),
    INDEX idx_site (site_id),
    INDEX idx_path (path(255)),
    FOREIGN KEY (site_id) REFERENCES external_sites(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
"""

STATIC_FILES_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS static_files (
    id            INT AUTO_INCREMENT PRIMARY KEY,
    filename      VARCHAR(255) UNIQUE NOT NULL,
    original_name VARCHAR(255) NOT NULL,
    file_path     VARCHAR(512) NOT NULL,
    file_size     BIGINT NOT NULL DEFAULT 0,
    mime_type     VARCHAR(128) DEFAULT 'application/octet-stream',
    uploaded_by   INT DEFAULT NULL,
    created_at    DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,

    INDEX idx_filename (filename),
    INDEX idx_created (created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
"""

LINE_COMMENTS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS line_comments (
    id            INT AUTO_INCREMENT PRIMARY KEY,
    article_type  ENUM('md','wikidot','html','bbcode') NOT NULL,
    article_slug  VARCHAR(255) NOT NULL,
    line_number   INT NOT NULL,
    author_name   VARCHAR(128) NOT NULL DEFAULT '匿名',
    content       VARCHAR(20) NOT NULL,
    created_at    DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,

    INDEX idx_article_line (article_type, article_slug, line_number),
    INDEX idx_created (created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
"""

RATINGS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS ratings (
    id            INT AUTO_INCREMENT PRIMARY KEY,
    article_type  ENUM('md','wikidot','html','bbcode') NOT NULL,
    article_slug  VARCHAR(255) NOT NULL,
    author_name   VARCHAR(128) NOT NULL,
    score         DECIMAL(4,2) NOT NULL,
    created_at    DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at    DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,

    UNIQUE KEY uq_user_article (article_type, article_slug, author_name),
    INDEX idx_article (article_type, article_slug)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
"""

WEBAUTHN_CREDENTIALS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS webauthn_credentials (
    id            INT AUTO_INCREMENT PRIMARY KEY,
    username      VARCHAR(128) NOT NULL,
    credential_id VARCHAR(512) NOT NULL UNIQUE,
    public_key    TEXT NOT NULL,
    sign_count    INT DEFAULT 0,
    transports    VARCHAR(255) DEFAULT '',
    created_at    DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,

    INDEX idx_username (username),
    FOREIGN KEY (username) REFERENCES users(username) ON DELETE CASCADE
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


async def _migrate_tags() -> None:
    """为已有文章（无标签的）添加默认标签。"""
    from . import tag_manager
    pool = await _get_pool()
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            # 迁移 article_tags ENUM 以支持新类型
            try:
                await cur.execute(
                    "ALTER TABLE article_tags MODIFY article_type "
                    "ENUM('md','wikidot','html','bbcode') NOT NULL"
                )
            except Exception:
                pass

            # Markdown 文章
            await cur.execute(
                "SELECT a.slug FROM articles a "
                "WHERE NOT EXISTS ("
                "  SELECT 1 FROM article_tags at WHERE at.article_type = 'md' AND at.article_slug = a.slug"
                ")"
            )
            rows = await cur.fetchall()
            for row in rows:
                await tag_manager.auto_tag_article("md", row[0])

            # Wikidot 页面
            await cur.execute(
                "SELECT p.slug FROM pages p "
                "WHERE NOT EXISTS ("
                "  SELECT 1 FROM article_tags at WHERE at.article_type = 'wikidot' AND at.article_slug = p.slug"
                ")"
            )
            rows = await cur.fetchall()
            for row in rows:
                await tag_manager.auto_tag_article("wikidot", row[0])

            # HTML 页面
            await cur.execute(
                "SELECT hp.slug FROM html_pages hp "
                "WHERE NOT EXISTS ("
                "  SELECT 1 FROM article_tags at WHERE at.article_type = 'html' AND at.article_slug = hp.slug"
                ")"
            )
            rows = await cur.fetchall()
            for row in rows:
                await tag_manager.auto_tag_article("html", row[0])

            # BBCode 页面
            await cur.execute(
                "SELECT bp.slug FROM bbcode_pages bp "
                "WHERE NOT EXISTS ("
                "  SELECT 1 FROM article_tags at WHERE at.article_type = 'bbcode' AND at.article_slug = bp.slug"
                ")"
            )
            rows = await cur.fetchall()
            for row in rows:
                await tag_manager.auto_tag_article("bbcode", row[0])


async def init_tables() -> None:
    """在应用启动时确保表结构存在，并执行必要的迁移。"""
    pool = await _get_pool()
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            # Markdown 文章表
            await cur.execute(MD_TABLE_SQL)
            await _safe_add_column(cur, "articles", "author_id", "INT DEFAULT NULL")

            # Wikidot 页面表
            await cur.execute(WK_TABLE_SQL)
            await _safe_add_column(cur, "pages", "author_id", "INT DEFAULT NULL")

            # 用户表
            await cur.execute(USERS_TABLE_SQL)
            await _migrate_user_roles(cur)

            # 标签表
            await cur.execute(TAGS_TABLE_SQL)
            await cur.execute(ARTICLE_TAGS_TABLE_SQL)

            # HTML 页面表
            await cur.execute(HTML_PAGES_TABLE_SQL)

            # BBCode 页面表
            await cur.execute(BBCODE_PAGES_TABLE_SQL)

            # 评论表
            await cur.execute(COMMENTS_TABLE_SQL)

            # 子站点链接表
            await cur.execute(SUBSITE_LINKS_TABLE_SQL)

            # 主页推荐文章表
            await cur.execute(FEATURED_ARTICLES_TABLE_SQL)

            # 通知表
            await cur.execute(NOTIFICATIONS_TABLE_SQL)

            # 外部站点表
            await cur.execute(EXTERNAL_SITES_TABLE_SQL)
            await cur.execute(EXTERNAL_PAGES_TABLE_SQL)

            # 静态文件表
            await cur.execute(STATIC_FILES_TABLE_SQL)

            # 行评论表
            await cur.execute(LINE_COMMENTS_TABLE_SQL)

            # 评分表
            await cur.execute(RATINGS_TABLE_SQL)

            # 通行密钥表 (WebAuthn)
            await cur.execute(WEBAUTHN_CREDENTIALS_TABLE_SQL)

    # 迁移：为已有文章添加默认标签
    await _migrate_tags()


async def seed_admin(username: str, password: str, nickname: str = "") -> None:
    """创建默认站长（如不存在），或将已有管理员升级为站长。"""
    from .auth import hash_password
    pool = await _get_pool()
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

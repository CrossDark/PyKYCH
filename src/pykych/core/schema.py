"""
数据库表结构定义与初始化迁移。

在应用启动时自动建表和迁移，确保数据库结构与应用代码一致。
所有表使用 InnoDB 引擎 + utf8mb4 字符集，支持 Emoji 等 4 字节 Unicode。
"""

import os
import aiomysql

from .db import _get_pool


# ═══════════════════════════════════════════════════════════════
# 建表 SQL
# ═══════════════════════════════════════════════════════════════

MD_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS articles (
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

WK_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS pages (
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
    article_type ENUM('md','wikidot','html','bbcode','typst') NOT NULL,
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
    article_type ENUM('md','wikidot','html','bbcode','typst') NOT NULL,
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
    article_type ENUM('md','wikidot','html','bbcode','typst') NOT NULL,
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
    article_type  ENUM('md','wikidot','html','bbcode','typst') NOT NULL,
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
    article_type  ENUM('md','wikidot','html','bbcode','typst') NOT NULL,
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

TYPST_PAGES_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS typst_pages (
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

TYPST_FILES_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS typst_files (
    id          INT AUTO_INCREMENT PRIMARY KEY,
    page_id     INT NOT NULL,
    filename    VARCHAR(255) NOT NULL,
    content     LONGTEXT NOT NULL,
    created_at  DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_page_file (page_id, filename),
    INDEX idx_page (page_id),
    FOREIGN KEY (page_id) REFERENCES typst_pages(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
"""

TYPST_CACHE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS typst_cache (
    id           INT AUTO_INCREMENT PRIMARY KEY,
    page_id      INT NOT NULL UNIQUE,
    html_content LONGTEXT NOT NULL,
    pdf_content  LONGBLOB NOT NULL,
    compiled_at  DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (page_id) REFERENCES typst_pages(id) ON DELETE CASCADE,
    INDEX idx_page (page_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
"""

# ── 视图（OPT-025：文章表统一视图） ──────────────────────────

VW_ALL_ARTICLES_SQL = """
CREATE OR REPLACE VIEW VW_ALL_ARTICLES AS
SELECT 'md' AS article_type, id, slug, title, content, author_id, created_at, updated_at
FROM articles
UNION ALL
SELECT 'wikidot', id, slug, title, content, author_id, created_at, updated_at
FROM pages
UNION ALL
SELECT 'html', id, slug, title, content, author_id, created_at, updated_at
FROM html_pages
UNION ALL
SELECT 'bbcode', id, slug, title, content, author_id, created_at, updated_at
FROM bbcode_pages
UNION ALL
SELECT 'typst', id, slug, title, content, author_id, created_at, updated_at
FROM typst_pages;
"""

# ── 所有建表语句的列表（按依赖顺序） ────────────────────────

ALL_TABLE_SQLS = [
    MD_TABLE_SQL,
    WK_TABLE_SQL,
    USERS_TABLE_SQL,
    TAGS_TABLE_SQL,
    ARTICLE_TAGS_TABLE_SQL,
    HTML_PAGES_TABLE_SQL,
    BBCODE_PAGES_TABLE_SQL,
    TYPST_PAGES_TABLE_SQL,
    TYPST_FILES_TABLE_SQL,
    TYPST_CACHE_TABLE_SQL,
    COMMENTS_TABLE_SQL,
    SUBSITE_LINKS_TABLE_SQL,
    FEATURED_ARTICLES_TABLE_SQL,
    NOTIFICATIONS_TABLE_SQL,
    STATIC_FILES_TABLE_SQL,
    LINE_COMMENTS_TABLE_SQL,
    RATINGS_TABLE_SQL,
    WEBAUTHN_CREDENTIALS_TABLE_SQL,
]


# ── 迁移辅助 ────────────────────────────────────────────────


async def _safe_add_column(cur, table: str, column: str, definition: str) -> None:
    """
    安全地添加列（如果不存在则添加，忽略重复错误）。

    参数:
        cur:        数据库游标
        table:      表名
        column:     列名
        definition: 列定义（如 'INT DEFAULT NULL'）
    """
    try:
        await cur.execute(
            f"ALTER TABLE {table} ADD COLUMN {column} {definition}"
        )
    except Exception:
        pass  # 列已存在则跳过


async def _migrate_user_roles(cur) -> None:
    """
    将旧的 is_admin 字段迁移为 role 枚举。

    迁移规则:
        - is_admin=1 且 role='user' → role='admin'
        - 迁移成功后删除 is_admin 列
    """
    try:
        await cur.execute(
            "SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS "
            "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'users' "
            "AND COLUMN_NAME = 'role'"
        )
        has_role = await cur.fetchone() is not None

        if not has_role:
            await cur.execute(
                "ALTER TABLE users ADD COLUMN role ENUM('user','admin','owner') "
                "NOT NULL DEFAULT 'user'"
            )

        await cur.execute(
            "SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS "
            "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'users' "
            "AND COLUMN_NAME = 'is_admin'"
        )
        if await cur.fetchone():
            await cur.execute(
                "UPDATE users SET role = 'admin' WHERE is_admin = 1 AND role = 'user'"
            )
            await cur.execute("ALTER TABLE users DROP COLUMN is_admin")
    except Exception:
        pass


async def _migrate_tags() -> None:
    """
    为已有文章（无标签关联的）添加默认类型标签。

    遍历所有文章表，为没有标签关联的文章自动添加默认标签。
    同时确保 article_tags 表的 ENUM 支持所有文章类型。
    """
    from ..content.tags import auto_tag_article

    pool = await _get_pool()
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            # 确保 ENUM 支持所有文章类型（包括 typst）
            try:
                await cur.execute(
                    "ALTER TABLE article_tags MODIFY article_type "
                    "ENUM('md','wikidot','html','bbcode','typst') NOT NULL"
                )
            except Exception:
                pass

            # 为各文章类型添加默认标签
            type_table_map = {
                "md": "articles",
                "wikidot": "pages",
                "html": "html_pages",
                "bbcode": "bbcode_pages",
                "typst": "typst_pages",
            }

            for atype, table in type_table_map.items():
                await cur.execute(
                    f"SELECT {table}.slug FROM {table} "
                    "WHERE NOT EXISTS ("
                    "  SELECT 1 FROM article_tags at "
                    f" WHERE at.article_type = %s AND at.article_slug = {table}.slug"
                    ")",
                    (atype,),
                )
                rows = await cur.fetchall()
                for row in rows:
                    await auto_tag_article(atype, row[0])


async def _migrate_enums_for_typst() -> None:
    """
    将已有 ENUM 列扩展为包含 'typst' 类型。

    对 comments, line_comments, ratings, featured_articles 表的
    article_type 列进行 ALTER，确保新值 'typst' 可用。
    """
    pool = await _get_pool()
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            enum_migrations = {
                "comments": "ENUM('md','wikidot','html','bbcode','typst')",
                "line_comments": "ENUM('md','wikidot','html','bbcode','typst')",
                "ratings": "ENUM('md','wikidot','html','bbcode','typst')",
                "featured_articles": "ENUM('md','wikidot','html','bbcode','typst')",
            }
            for table, enum_def in enum_migrations.items():
                try:
                    await cur.execute(
                        f"ALTER TABLE {table} MODIFY article_type {enum_def} NOT NULL"
                    )
                except Exception:
                    pass  # 列可能已是新定义，或表尚不存在


async def _migrate_typst_cache_dependencies() -> None:
    """
    为 typst_cache 表添加 dependencies 列（跨文章引用依赖追踪）。

    dependencies 存储 JSON 数组格式的引用 slug 列表，
    用于在缓存查找时验证被引用文章是否已更新。
    """
    pool = await _get_pool()
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            await _safe_add_column(
                cur, "typst_cache", "dependencies",
                "TEXT DEFAULT NULL"
            )


async def _migrate_missing_indexes() -> None:
    """
    为缺少索引的列添加索引（OPT-026）。

    添加:
        - ratings.author_name 索引（加速 delete_user 时的清理）
        - static_files.uploaded_by 索引（加速用户文件查询）
    """
    pool = await _get_pool()
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            try:
                await cur.execute(
                    "ALTER TABLE ratings ADD INDEX idx_author_name (author_name)"
                )
            except Exception:
                pass  # 索引已存在
            try:
                await cur.execute(
                    "ALTER TABLE static_files ADD INDEX idx_uploaded_by (uploaded_by)"
                )
            except Exception:
                pass  # 索引已存在


async def _migrate_fulltext_indexes() -> None:
    """
    为文章表添加 FULLTEXT 索引以优化搜索（OPT-007）。

    为 5 张文章表的 title 和 content 列添加 MySQL FULLTEXT 索引，
    使搜索从 LIKE '%keyword%' 全表扫描升级为全文索引查询。

    注意：FULLTEXT 索引在 LONGTEXT 列上创建可能非常耗时（大表可能需要数分钟）。
    此迁移设置了 30 秒总超时，超时后跳过剩余索引，不影响应用启动。
    生产环境建议在低峰期手动执行 ALTER TABLE。
    """
    import asyncio
    pool = await _get_pool()
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            tables = ["articles", "pages", "html_pages", "bbcode_pages", "typst_pages"]
            for table in tables:
                try:
                    # 30 秒超时保护：大表上创建 FULLTEXT 索引可能很慢
                    await asyncio.wait_for(
                        cur.execute(
                            f"ALTER TABLE {table} ADD FULLTEXT INDEX ft_title_content (title, content)"
                        ),
                        timeout=30.0,
                    )
                except asyncio.TimeoutError:
                    import logging
                    logging.getLogger(__name__).warning(
                        f"⚠️  FULLTEXT 索引创建超时 (表: {table})，已跳过。"
                        f"请在低峰期手动执行: ALTER TABLE {table} ADD FULLTEXT INDEX ft_title_content (title, content);"
                    )
                except Exception:
                    pass  # 索引已存在或表不支持


async def _create_all_articles_view() -> None:
    """
    创建或替换统一文章视图 VW_ALL_ARTICLES（OPT-025）。

    将 5 张文章表合并为一个视图，方便跨类型查询（搜索、统计、推荐）。
    """
    pool = await _get_pool()
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            try:
                await cur.execute(VW_ALL_ARTICLES_SQL)
            except Exception:
                pass  # 视图创建失败不影响主流程


# ── 初始化入口 ──────────────────────────────────────────────


async def init_tables() -> None:
    """
    初始化所有数据库表结构。

    在应用启动时调用，执行以下操作:
        1. 创建所有表（如不存在）
        2. 添加缺失的列
        3. 迁移旧数据（is_admin → role）
        4. 为已有文章添加默认标签
    """
    pool = await _get_pool()
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            # 依次执行所有建表语句
            for sql in ALL_TABLE_SQLS:
                await cur.execute(sql)

            # 确保 author_id 列存在
            await _safe_add_column(cur, "articles", "author_id", "INT DEFAULT NULL")
            await _safe_add_column(cur, "pages", "author_id", "INT DEFAULT NULL")

            # 迁移用户角色
            await _migrate_user_roles(cur)

    # 迁移标签
    await _migrate_tags()
    # 迁移 ENUM 以支持 typst
    await _migrate_enums_for_typst()
    # 迁移 typst_cache 表（跨文章依赖列）
    await _migrate_typst_cache_dependencies()
    # 补充缺失索引（OPT-026）
    await _migrate_missing_indexes()
    # 全文索引（OPT-007）— 可通过环境变量跳过（大表可能很慢）
    if not os.environ.get("PYKYCH_SKIP_FULLTEXT", "").lower() in ("true", "1", "yes"):
        await _migrate_fulltext_indexes()
    # 创建统一文章视图（OPT-025）
    await _create_all_articles_view()


async def seed_admin(username: str, password: str, nickname: str = "") -> None:
    """
    创建默认站长账号（如不存在），或升级已有管理员。

    参数:
        username: 站长用户名
        password: 站长密码（明文，会自动哈希存储）
        nickname: 站长昵称（默认同用户名）
    """
    from ..auth.password import hash_password

    pool = await _get_pool()
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                "SELECT COUNT(*) FROM users WHERE username = %s", (username,)
            )
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
                    "UPDATE users SET role = 'owner' "
                    "WHERE username = %s AND role = 'admin'",
                    (username,),
                )

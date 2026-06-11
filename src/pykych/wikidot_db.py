"""
Wikidot 独立数据库模块 — 与 Markdown 文章数据库分离。
"""

import aiosqlite
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

DB_PATH = Path(__file__).parent.parent / "data" / "wikidot.db"


async def get_db() -> aiosqlite.Connection:
    """获取 Wikidot 数据库连接。"""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = await aiosqlite.connect(str(DB_PATH))
    conn.row_factory = aiosqlite.Row
    await conn.execute("PRAGMA journal_mode=WAL")
    await conn.execute("PRAGMA foreign_keys=ON")
    return conn


async def init_db() -> None:
    """初始化 Wikidot 数据库表结构。"""
    conn = await get_db()
    try:
        await conn.executescript("""
            CREATE TABLE IF NOT EXISTS pages (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                slug        TEXT    UNIQUE NOT NULL,
                title       TEXT    NOT NULL,
                content     TEXT    NOT NULL,
                created_at  TEXT    NOT NULL,
                updated_at  TEXT    NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_wikidot_slug
                ON pages(slug);

            CREATE INDEX IF NOT EXISTS idx_wikidot_created
                ON pages(created_at DESC);
        """)
        await conn.commit()
    finally:
        await conn.close()


# ── CRUD ────────────────────────────────────────────────────


async def list_pages(page: int = 1, per_page: int = 10) -> dict:
    """分页获取 Wikidot 页面列表。"""
    conn = await get_db()
    try:
        offset = (page - 1) * per_page
        rows = await conn.execute_fetchall(
            "SELECT id, slug, title, created_at, updated_at "
            "FROM pages ORDER BY created_at DESC LIMIT ? OFFSET ?",
            (per_page, offset),
        )
        row = await conn.execute_fetchall("SELECT COUNT(*) FROM pages")
        total = row[0][0] if row else 0
        return {
            "pages": [dict(r) for r in rows],
            "total": total,
            "page": page,
            "per_page": per_page,
            "total_pages": max(1, (total + per_page - 1) // per_page),
        }
    finally:
        await conn.close()


async def get_page_by_slug(slug: str) -> Optional[dict]:
    """根据 slug 获取 Wikidot 页面。"""
    conn = await get_db()
    try:
        row = await conn.execute_fetchall(
            "SELECT * FROM pages WHERE slug = ?", (slug,)
        )
        return dict(row[0]) if row else None
    finally:
        await conn.close()


async def create_page(slug: str, title: str, content: str) -> dict:
    """创建新页面。"""
    conn = await get_db()
    try:
        now = datetime.now(timezone.utc).isoformat()
        await conn.execute(
            "INSERT INTO pages (slug, title, content, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (slug, title, content, now, now),
        )
        await conn.commit()
        return await get_page_by_slug(slug)
    finally:
        await conn.close()


async def update_page(slug: str, title: str, content: str) -> Optional[dict]:
    """更新已有页面。"""
    conn = await get_db()
    try:
        now = datetime.now(timezone.utc).isoformat()
        cursor = await conn.execute(
            "UPDATE pages SET title = ?, content = ?, updated_at = ? "
            "WHERE slug = ?",
            (title, content, now, slug),
        )
        await conn.commit()
        if cursor.rowcount == 0:
            return None
        return await get_page_by_slug(slug)
    finally:
        await conn.close()


async def delete_page(slug: str) -> bool:
    """删除页面，返回是否成功。"""
    conn = await get_db()
    try:
        cursor = await conn.execute(
            "DELETE FROM pages WHERE slug = ?", (slug,)
        )
        await conn.commit()
        return cursor.rowcount > 0
    finally:
        await conn.close()


# ── 种子数据 ──────────────────────────────────────────────

SEED_PAGES = [
    {
        "slug": "start",
        "title": "欢迎来到 PyKYCH Wiki",
        "content": r"""+ 欢迎来到 PyKYCH Wiki

这里是使用 **Wikidot 语法** 构建的维基页面。

[[div class="content-body"]]

++ 什么是 Wikidot 语法？

Wikidot 是一种轻量级的维基标记语言，广泛用于 Wikidot 平台上的协作编辑。
它比 HTML 更简洁，但比 Markdown 功能更强大。

+++ 基本语法

* **粗体文本** 使用 {{**双星号**}}
* //斜体// 使用 {{//双斜线//}}
* __下划线__ 使用 {{__双下划线__}}
* --删除线-- 使用 {{--双破折号--}}

+++ 代码块

[[code]]
def hello_world():
    print("Hello, Wikidot!")
    return True
[[/code]]

+++ 列表

* 无序列表项 1
* 无序列表项 2
 * 嵌套项 2.1
 * 嵌套项 2.2

# 有序列表项 1
# 有序列表项 2

[[/div]]
""",
    },
    {
        "slug": "syntax-guide",
        "title": "Wikidot 语法指南",
        "content": r"""+ Wikidot 语法快速参考

本文档涵盖了 PyKYCH 支持的 Wikidot 语法。

[[div class="content-body"]]

++ 标题

+ 一级标题（页面标题）
++ 二级标题
+++ 三级标题
++++ 四级标题

++ 文本格式

* **粗体** — {{**text**}}
* //斜体// — {{//text//}}
* __下划线__ — {{__text__}}
* --删除线-- — {{--text--}}
* {{等宽字体}} — {{{{text}}}}

++ 链接

* [[[/start | 首页]]] — 创建到其他页面的链接
* [[[https://lihil.cc | LiHiL 官网]]] — 外部链接

++ 代码块

[[code]]
import asyncio

async def main():
    print("异步编程示例")
    await asyncio.sleep(1)

asyncio.run(main())
[[/code]]

++ 引用块

> 这是一段引用文字。
> 引用可以跨越多行。
> 第二行。

++ 表格

[[table]]
| 特性 | 状态 | 优先级 |
| **路由系统** | 已实现 | 高 |
| **语法解析器** | 已实现 | 高 |
| **数据库存储** | 已实现 | 高 |
[[/table]]

++ 提示框

!!! note
    这是一个信息提示框。

!!! warning
    这是一个警告提示框。

[[/div]]
""",
    },
    {
        "slug": "about-wiki",
        "title": "关于这个 Wiki",
        "content": r"""+ 关于 PyKYCH Wiki

[[div class="content-body"]]

++ 技术栈

| 组件 | 技术选型 |
| **框架** | [[[https://lihil.cc | LiHiL]]] |
| **数据库** | SQLite (独立于 Markdown) |
| **语法** | 自定义 Wikidot 解析器 |
| **模板** | Jinja2 |

++ 设计理念

> 将 Wikidot 内容与 Markdown 文章 **完全分离**——
> 不同的数据库、不同的路由、不同的解析器。

这让两种内容格式独立演进、互不干扰。

++ 支持的 Wikidot 块元素

* [[div]] 容器块
* [[code]] 代码块
* [[table]] 表格
* 引用块 (>)
* 提示框 (!!! note / !!! warning / !!! danger)

+++ 未来计划

# 支持更多 Wikidot 模块（如 [[module ListPages]]）
# 添加页面历史版本
# 实现页面间的 [[include]] 引用

[[/div]]
""",
    },
]


async def seed_db() -> int:
    """向数据库插入种子数据（如已存在则跳过）。"""
    conn = await get_db()
    try:
        count = 0
        for p in SEED_PAGES:
            now = datetime.now(timezone.utc).isoformat()
            cursor = await conn.execute(
                "INSERT OR IGNORE INTO pages (slug, title, content, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (p["slug"], p["title"], p["content"], now, now),
            )
            count += cursor.rowcount
        await conn.commit()
        return count
    finally:
        await conn.close()

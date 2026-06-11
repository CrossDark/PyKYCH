"""
MySQL 数据库模块 — 管理 Wikidot 页面的存储与查询。
配置来自 settings/db.yaml，通过 mysql_manager 获取连接池。
"""

from datetime import datetime, timezone
from typing import Optional

from .mysql_manager import get_wk_pool, row_to_dict


async def list_pages(page: int = 1, per_page: int = 10) -> dict:
    """分页获取 Wikidot 页面列表。"""
    pool = await get_wk_pool()
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            offset = (page - 1) * per_page
            await cur.execute(
                "SELECT id, slug, title, created_at, updated_at "
                "FROM pages ORDER BY created_at DESC LIMIT %s OFFSET %s",
                (per_page, offset),
            )
            rows = await cur.fetchall()
            pages = [row_to_dict(r, cur) for r in rows]

            await cur.execute("SELECT COUNT(*) FROM pages")
            total = (await cur.fetchone())[0]

    return {
        "pages": pages,
        "total": total,
        "page": page,
        "per_page": per_page,
        "total_pages": max(1, (total + per_page - 1) // per_page),
    }


async def get_page_by_slug(slug: str) -> Optional[dict]:
    """根据 slug 获取 Wikidot 页面。"""
    pool = await get_wk_pool()
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute("SELECT * FROM pages WHERE slug = %s", (slug,))
            row = await cur.fetchone()
            return row_to_dict(row, cur) if row else None


async def create_page(slug: str, title: str, content: str) -> dict:
    """创建新页面。"""
    pool = await get_wk_pool()
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                "INSERT INTO pages (slug, title, content) VALUES (%s, %s, %s)",
                (slug, title, content),
            )
            return await get_page_by_slug(slug)


async def update_page(slug: str, title: str, content: str) -> Optional[dict]:
    """更新已有页面。"""
    pool = await get_wk_pool()
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                "UPDATE pages SET title = %s, content = %s WHERE slug = %s",
                (title, content, slug),
            )
            if cur.rowcount == 0:
                return None
            return await get_page_by_slug(slug)


async def delete_page(slug: str) -> bool:
    """删除页面，返回是否成功。"""
    pool = await get_wk_pool()
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute("DELETE FROM pages WHERE slug = %s", (slug,))
            return cur.rowcount > 0


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
| **数据库** | MySQL (独立于 Markdown) |
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
    pool = await get_wk_pool()
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            count = 0
            for p in SEED_PAGES:
                await cur.execute(
                    "SELECT COUNT(*) FROM pages WHERE slug = %s", (p["slug"],)
                )
                if (await cur.fetchone())[0] == 0:
                    await cur.execute(
                        "INSERT INTO pages (slug, title, content) VALUES (%s, %s, %s)",
                        (p["slug"], p["title"], p["content"]),
                    )
                    count += 1
            return count

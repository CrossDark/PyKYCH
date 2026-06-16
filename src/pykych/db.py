"""
MySQL 数据库模块 — 管理 Markdown 文章的存储与查询。
配置来自 data/settings/db.yaml，通过 mysql_manager 获取连接池。
"""

from datetime import datetime, timezone
from typing import Optional

from .mysql_manager import get_md_pool, row_to_dict
from . import tag_manager


async def list_articles(page: int = 1, per_page: int = 10) -> dict:
    """分页获取文章列表（按创建时间倒序）。"""
    pool = await get_md_pool()
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            offset = (page - 1) * per_page
            await cur.execute(
                "SELECT id, slug, title, author_id, created_at, updated_at "
                "FROM articles ORDER BY created_at DESC LIMIT %s OFFSET %s",
                (per_page, offset),
            )
            rows = await cur.fetchall()
            articles = [row_to_dict(r, cur) for r in rows]

            await cur.execute("SELECT COUNT(*) FROM articles")
            total = (await cur.fetchone())[0]

    return {
        "articles": articles,
        "total": total,
        "page": page,
        "per_page": per_page,
        "total_pages": max(1, (total + per_page - 1) // per_page),
    }


async def get_article_by_slug(slug: str) -> Optional[dict]:
    """根据 slug 获取单篇文章。"""
    pool = await get_md_pool()
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute("SELECT * FROM articles WHERE slug = %s", (slug,))
            row = await cur.fetchone()
            return row_to_dict(row, cur) if row else None


async def get_articles_by_author(author_id: int, page: int = 1, per_page: int = 10) -> dict:
    """获取指定作者的文章列表。"""
    pool = await get_md_pool()
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            offset = (page - 1) * per_page
            await cur.execute(
                "SELECT id, slug, title, author_id, created_at, updated_at "
                "FROM articles WHERE author_id = %s ORDER BY created_at DESC LIMIT %s OFFSET %s",
                (author_id, per_page, offset),
            )
            rows = await cur.fetchall()
            articles = [row_to_dict(r, cur) for r in rows]

            await cur.execute("SELECT COUNT(*) FROM articles WHERE author_id = %s", (author_id,))
            total = (await cur.fetchone())[0]

    return {
        "articles": articles,
        "total": total,
        "page": page,
        "per_page": per_page,
        "total_pages": max(1, (total + per_page - 1) // per_page),
    }


async def create_article(slug: str, title: str, content: str, author_id: int = None) -> dict:
    """创建一篇新文章。"""
    pool = await get_md_pool()
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                "INSERT INTO articles (slug, title, content, author_id) VALUES (%s, %s, %s, %s)",
                (slug, title, content, author_id),
            )
            # 自动添加 md 标签
            await tag_manager.auto_tag_article("md", slug)
            return await get_article_by_slug(slug)


async def update_article(slug: str, title: str, content: str) -> Optional[dict]:
    """更新已有文章。"""
    pool = await get_md_pool()
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                "UPDATE articles SET title = %s, content = %s WHERE slug = %s",
                (title, content, slug),
            )
            if cur.rowcount == 0:
                return None
            return await get_article_by_slug(slug)


async def delete_article(slug: str) -> bool:
    """删除文章，返回是否成功。"""
    pool = await get_md_pool()
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute("DELETE FROM articles WHERE slug = %s", (slug,))
            return cur.rowcount > 0


# ── 种子数据 ──────────────────────────────────────────────

SEED_ARTICLES = [
    {
        "slug": "lihil-intro",
        "title": "使用 LiHiL 构建高性能 Web 应用",
        "content": """# 使用 LiHiL 构建高性能 Web 应用

*发布于 2026-06-10*

---

## 什么是 LiHiL？

LiHiL 是一个高性能的 Python ASGI Web 框架，相比其他框架快 **50%-100%**。
它提供了依赖注入、插件系统、WebSocket 支持等企业级功能。

## 快速开始

安装非常简单：

```bash
pip install "lihil[standard]"
```

创建一个最简单的应用：

```python
from lihil import Lihil

app = Lihil()

@app.sub("/").get
async def home():
    return {"message": "Hello, LiHiL!"}
```

然后使用 uvicorn 运行：

```bash
uvicorn main:app --reload
```

## 核心特性

| 特性 | 说明 |
|------|------|
| **路由系统** | 基于 Route 和 subroutes 的灵活路由 |
| **依赖注入** | 基于类型提示的自动注入 |
| **参数验证** | 自动解析和验证请求参数 |
| **插件系统** | 强大的中间件和插件架构 |
| **OpenAPI** | 自动生成 API 文档 |

## 与 FastAPI 的关键区别

> ⚠️ LiHiL **不是** FastAPI！不要混用语法。

```python
# ❌ FastAPI 写法 — 在 LiHiL 中无效
@app.get("/users")

# ✅ LiHiL 写法
@app.sub("/users").get
```

LiHiL 正在快速发展中，值得关注和尝试！
""",
    },
    {
        "slug": "python-async-guide",
        "title": "Python 异步编程入门指南",
        "content": """# Python 异步编程入门指南

*发布于 2026-06-05*

---

## 为什么需要异步编程？

在 Web 开发中，大量时间消耗在 I/O 操作上（数据库查询、API 调用、文件读写）。
同步代码会在等待 I/O 时阻塞整个线程，**而异步编程可以在等待时处理其他任务**。

## asyncio 基础

Python 的 `asyncio` 库提供了事件循环、协程和 Future 等核心概念：

```python
import asyncio

async def fetch_data():
    await asyncio.sleep(1)
    return "data"

async def main():
    result = await fetch_data()
    print(result)

asyncio.run(main())
```

### 关键概念

1. **协程 (Coroutine)**: 用 `async def` 定义的函数
2. **事件循环 (Event Loop)**: 调度和执行异步任务
3. **await**: 挂起当前协程，等待结果返回

## 在 LiHiL 中使用异步

LiHiL 天然支持异步处理，所有端点函数都可以是 `async` 的：

```python
@app.sub("/data").get
async def get_data():
    data = await fetch_from_db()
    return {"data": data}
```

## 常见的异步陷阱

- ❌ 在协程中调用同步阻塞函数会阻塞整个事件循环
- ❌ 忘记 `await` 导致协程没有执行
- ✅ 耗时同步操作使用 `asyncio.to_thread()` 放到线程池

异步编程让 Web 应用能够高效处理大量并发请求，是现代 Web 框架的标配。
""",
    },
    {
        "slug": "why-python-web",
        "title": "为什么选择 Python 做 Web 开发",
        "content": """# 为什么选择 Python 做 Web 开发

*发布于 2026-05-28*

---

## Python 的优势

Python 以其简洁优雅的语法和丰富的生态系统，成为 Web 开发的热门选择：

### 🚀 开发效率高

更少的代码量意味着更快的开发速度和更低的维护成本。

```python
# 用最少的代码完成最多的事
@app.sub("/users/{user_id}").get
async def get_user(user_id: str):
    return {"id": user_id, "name": "张三"}
```

### 📦 生态丰富

| 框架 | 特点 |
|------|------|
| Django | 全栈框架，"电池已包含" |
| FastAPI | 高性能，自动 API 文档 |
| **LiHiL** | **2 倍速，企业级功能** |
| Flask | 微型框架，灵活轻量 |

### 🤖 AI/ML 集成

Python 是 AI 和数据科学的事实标准语言，Web 应用可以无缝对接：

- 大语言模型 (LLM)
- 机器学习模型
- 数据分析管道

### 👥 社区活跃

庞大的开发者社区意味着：
- 丰富的第三方库
- 海量的学习资源
- 快速的问题解答

## LiHiL 的愿景

> LiHiL 的愿景是「让 Python 成为 Web 开发的主流语言」。

通过提供高性能和高生产力的开发体验，LiHiL 正在为这一目标努力。

Python 已经从脚本语言成长为全栈开发的有力竞争者。现在是时候用 Python 构建你的下一个 Web 项目了！
""",
    },
]


async def seed_db() -> int:
    """向数据库插入种子数据（如已存在则跳过）。"""
    pool = await get_md_pool()
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            count = 0
            for a in SEED_ARTICLES:
                await cur.execute(
                    "SELECT COUNT(*) FROM articles WHERE slug = %s", (a["slug"],)
                )
                if (await cur.fetchone())[0] == 0:
                    await cur.execute(
                        "INSERT INTO articles (slug, title, content) VALUES (%s, %s, %s)",
                        (a["slug"], a["title"], a["content"]),
                    )
                    # 自动添加 md 标签
                    await tag_manager.auto_tag_article("md", a["slug"])
                    count += 1
            return count

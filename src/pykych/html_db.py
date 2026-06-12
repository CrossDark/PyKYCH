"""
MySQL 数据库模块 — 管理 HTML 文章的存储与查询。
配置来自 settings/db.yaml，通过 mysql_manager 获取连接池。
"""

from datetime import datetime, timezone
from typing import Optional

from .mysql_manager import get_md_pool, row_to_dict
from . import tag_manager


async def list_html_pages(page: int = 1, per_page: int = 10) -> dict:
    """分页获取 HTML 页面列表（按创建时间倒序）。"""
    pool = await get_md_pool()
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            offset = (page - 1) * per_page
            await cur.execute(
                "SELECT id, slug, title, author_id, created_at, updated_at "
                "FROM html_pages ORDER BY created_at DESC LIMIT %s OFFSET %s",
                (per_page, offset),
            )
            rows = await cur.fetchall()
            pages = [row_to_dict(r, cur) for r in rows]

            await cur.execute("SELECT COUNT(*) FROM html_pages")
            total = (await cur.fetchone())[0]

    return {
        "pages": pages,
        "total": total,
        "page": page,
        "per_page": per_page,
        "total_pages": max(1, (total + per_page - 1) // per_page),
    }


async def get_html_page_by_slug(slug: str) -> Optional[dict]:
    """根据 slug 获取单个 HTML 页面。"""
    pool = await get_md_pool()
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute("SELECT * FROM html_pages WHERE slug = %s", (slug,))
            row = await cur.fetchone()
            return row_to_dict(row, cur) if row else None


async def get_html_pages_by_author(author_id: int, page: int = 1, per_page: int = 10) -> dict:
    """获取指定作者的 HTML 页面列表。"""
    pool = await get_md_pool()
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            offset = (page - 1) * per_page
            await cur.execute(
                "SELECT id, slug, title, author_id, created_at, updated_at "
                "FROM html_pages WHERE author_id = %s ORDER BY created_at DESC LIMIT %s OFFSET %s",
                (author_id, per_page, offset),
            )
            rows = await cur.fetchall()
            pages = [row_to_dict(r, cur) for r in rows]

            await cur.execute("SELECT COUNT(*) FROM html_pages WHERE author_id = %s", (author_id,))
            total = (await cur.fetchone())[0]

    return {
        "pages": pages,
        "total": total,
        "page": page,
        "per_page": per_page,
        "total_pages": max(1, (total + per_page - 1) // per_page),
    }


async def create_html_page(slug: str, title: str, content: str, author_id: int = None) -> dict:
    """创建一篇新的 HTML 页面。"""
    pool = await get_md_pool()
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                "INSERT INTO html_pages (slug, title, content, author_id) VALUES (%s, %s, %s, %s)",
                (slug, title, content, author_id),
            )
            # 自动添加 html 标签
            await tag_manager.auto_tag_article("html", slug)
            return await get_html_page_by_slug(slug)


async def update_html_page(slug: str, title: str, content: str) -> Optional[dict]:
    """更新已有 HTML 页面。"""
    pool = await get_md_pool()
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                "UPDATE html_pages SET title = %s, content = %s WHERE slug = %s",
                (title, content, slug),
            )
            if cur.rowcount == 0:
                return None
            return await get_html_page_by_slug(slug)


async def delete_html_page(slug: str) -> bool:
    """删除 HTML 页面，返回是否成功。"""
    pool = await get_md_pool()
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute("DELETE FROM html_pages WHERE slug = %s", (slug,))
            return cur.rowcount > 0


# ── 种子数据 ──────────────────────────────────────────────

SEED_HTML_PAGES = [
    {
        "slug": "hello-html",
        "title": "Hello HTML — 欢迎来到 HTML 模块",
        "content": """<h2>欢迎来到 HTML 模块</h2>

<p>这是一个 <strong>纯 HTML</strong> 文章示例。HTML 模块允许你直接编写 HTML 内容，无需任何标记语言转换。</p>

<h3>HTML 模块的特点</h3>
<ul>
    <li><strong>原生 HTML</strong>：直接使用 HTML 标签，无需转换</li>
    <li><strong>完全控制</strong>：可以嵌入任意 CSS/JS（内联）</li>
    <li><strong>数据库存储</strong>：与 Markdown 和 Wikidot 相同的持久化方式</li>
    <li><strong>标签支持</strong>：自动添加 <code>html</code> 标签</li>
</ul>

<h3>示例: 自定义样式表格</h3>
<table style="width:100%;border-collapse:collapse;margin:1rem 0;">
    <thead>
        <tr style="background:#f5f4f0;">
            <th style="padding:0.6rem 0.9rem;text-align:left;border:1px solid #e8e5df;">特性</th>
            <th style="padding:0.6rem 0.9rem;text-align:left;border:1px solid #e8e5df;">Markdown</th>
            <th style="padding:0.6rem 0.9rem;text-align:left;border:1px solid #e8e5df;">HTML</th>
        </tr>
    </thead>
    <tbody>
        <tr>
            <td style="padding:0.6rem 0.9rem;border:1px solid #e8e5df;">学习成本</td>
            <td style="padding:0.6rem 0.9rem;border:1px solid #e8e5df;">低</td>
            <td style="padding:0.6rem 0.9rem;border:1px solid #e8e5df;">中</td>
        </tr>
        <tr>
            <td style="padding:0.6rem 0.9rem;border:1px solid #e8e5df;">灵活度</td>
            <td style="padding:0.6rem 0.9rem;border:1px solid #e8e5df;">中</td>
            <td style="padding:0.6rem 0.9rem;border:1px solid #e8e5df;">高</td>
        </tr>
        <tr>
            <td style="padding:0.6rem 0.9rem;border:1px solid #e8e5df;">可读性</td>
            <td style="padding:0.6rem 0.9rem;border:1px solid #e8e5df;">高</td>
            <td style="padding:0.6rem 0.9rem;border:1px solid #e8e5df;">低</td>
        </tr>
    </tbody>
</table>

<h3>代码块示例</h3>
<pre style="background:#1e293b;color:#e2e8f0;padding:1rem;border-radius:8px;overflow-x:auto;">
&lt;div class="custom-box"&gt;
    &lt;h2&gt;自定义 HTML 区块&lt;/h2&gt;
    &lt;p&gt;你可以在这里写任何 HTML 内容&lt;/p&gt;
&lt;/div&gt;
</pre>

<blockquote style="border-left:4px solid #3b82f6;padding:0.5rem 1rem;margin:1rem 0;background:#f5f4f0;border-radius:0 8px 8px 0;">
    <p>💡 <strong>提示</strong>：HTML 模块适合需要高度自定义布局和样式的页面。对于一般文章，建议使用 Markdown。</p>
</blockquote>

<p style="text-align:center;color:#6b6b6b;margin-top:2rem;">— HTML 模块, Powered by PyKYCH —</p>""",
    },
]


async def seed_db() -> int:
    """向数据库插入种子数据（如已存在则跳过）。"""
    pool = await get_md_pool()
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            count = 0
            for p in SEED_HTML_PAGES:
                await cur.execute(
                    "SELECT COUNT(*) FROM html_pages WHERE slug = %s", (p["slug"],)
                )
                if (await cur.fetchone())[0] == 0:
                    await cur.execute(
                        "INSERT INTO html_pages (slug, title, content) VALUES (%s, %s, %s)",
                        (p["slug"], p["title"], p["content"]),
                    )
                    await tag_manager.auto_tag_article("html", p["slug"])
                    count += 1
            return count

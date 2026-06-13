"""
外部 HTML 站点管理模块 — 从外部静态网站抓取 HTML 并缓存。
"""

import re
from typing import Optional
from urllib.parse import urljoin, urlparse

import aiohttp

from .mysql_manager import get_sys_pool, row_to_dict
from . import tag_manager


# ── 外部站点 CRUD ──────────────────────────────────────────


async def list_external_sites() -> list[dict]:
    """获取所有外部站点。"""
    pool = await get_sys_pool()
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                "SELECT id, name, source_url, description, auto_tags, "
                "is_active, created_at, updated_at "
                "FROM external_sites ORDER BY name"
            )
            rows = await cur.fetchall()
            sites = [row_to_dict(r, cur) for r in rows]
            # 统计每个站点的缓存页面数
            for site in sites:
                await cur.execute(
                    "SELECT COUNT(*) FROM external_pages WHERE site_id = %s",
                    (site["id"],),
                )
                site["page_count"] = (await cur.fetchone())[0]
            return sites


async def get_external_site(site_id: int) -> Optional[dict]:
    """获取单个外部站点。"""
    pool = await get_sys_pool()
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                "SELECT id, name, source_url, description, auto_tags, "
                "is_active, created_at, updated_at "
                "FROM external_sites WHERE id = %s",
                (site_id,),
            )
            row = await cur.fetchone()
            return row_to_dict(row, cur) if row else None


async def get_external_site_by_name(name: str) -> Optional[dict]:
    """根据名称获取外部站点。"""
    pool = await get_sys_pool()
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                "SELECT id, name, source_url, description, auto_tags, "
                "is_active, created_at, updated_at "
                "FROM external_sites WHERE name = %s",
                (name,),
            )
            row = await cur.fetchone()
            return row_to_dict(row, cur) if row else None


async def create_external_site(
    name: str, source_url: str, description: str = "", auto_tags: str = ""
) -> dict:
    """创建外部站点。"""
    name = name.strip().lower()
    source_url = source_url.strip().rstrip("/")
    pool = await get_sys_pool()
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                "INSERT INTO external_sites (name, source_url, description, auto_tags) "
                "VALUES (%s, %s, %s, %s)",
                (name, source_url, description, auto_tags),
            )
            return await get_external_site(cur.lastrowid)


async def update_external_site(
    site_id: int,
    source_url: str = "",
    description: str = "",
    auto_tags: str = "",
    is_active: bool = True,
) -> Optional[dict]:
    """更新外部站点配置。"""
    pool = await get_sys_pool()
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            updates = []
            params = []
            if source_url:
                updates.append("source_url = %s")
                params.append(source_url.strip().rstrip("/"))
            if description is not None:
                updates.append("description = %s")
                params.append(description)
            if auto_tags is not None:
                updates.append("auto_tags = %s")
                params.append(auto_tags)
            updates.append("is_active = %s")
            params.append(1 if is_active else 0)
            params.append(site_id)
            await cur.execute(
                f"UPDATE external_sites SET {', '.join(updates)} WHERE id = %s",
                params,
            )
            if cur.rowcount == 0:
                return None
            return await get_external_site(site_id)


async def delete_external_site(site_id: int) -> bool:
    """删除外部站点及其所有缓存页面。"""
    pool = await get_sys_pool()
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                "DELETE FROM external_sites WHERE id = %s", (site_id,)
            )
            return cur.rowcount > 0


# ── 页面缓存 CRUD ──────────────────────────────────────────


async def get_cached_page(site_name: str, path: str) -> Optional[dict]:
    """获取缓存的页面内容。path 为空字符串时表示首页。"""
    pool = await get_sys_pool()
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                "SELECT ep.title, ep.content, ep.fetched_at, "
                "es.name AS site_name, es.source_url, es.auto_tags "
                "FROM external_pages ep "
                "JOIN external_sites es ON ep.site_id = es.id "
                "WHERE es.name = %s AND es.is_active = 1 AND ep.path = %s",
                (site_name, path),
            )
            row = await cur.fetchone()
            return row_to_dict(row, cur) if row else None


async def list_cached_pages(site_id: int) -> list[dict]:
    """获取站点的所有缓存页面。"""
    pool = await get_sys_pool()
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                "SELECT id, path, title, fetched_at "
                "FROM external_pages WHERE site_id = %s "
                "ORDER BY path",
                (site_id,),
            )
            rows = await cur.fetchall()
            return [row_to_dict(r, cur) for r in rows]


async def save_page(site_id: int, path: str, title: str, content: str) -> None:
    """保存或更新页面缓存。"""
    pool = await get_sys_pool()
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                "INSERT INTO external_pages (site_id, path, title, content, fetched_at) "
                "VALUES (%s, %s, %s, %s, NOW()) "
                "ON DUPLICATE KEY UPDATE title = VALUES(title), "
                "content = VALUES(content), fetched_at = NOW()",
                (site_id, path, title, content),
            )


async def clear_site_cache(site_id: int) -> None:
    """清除站点的所有缓存页面。"""
    pool = await get_sys_pool()
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                "DELETE FROM external_pages WHERE site_id = %s", (site_id,)
            )


# ── HTML 抓取 ──────────────────────────────────────────────


def _extract_body(html: str) -> str:
    """从 HTML 中提取 <body> 内容（去除 body 标签本身）。"""
    # 尝试提取 <body>...</body>
    match = re.search(r"<body[^>]*>(.*?)</body>", html, re.DOTALL | re.IGNORECASE)
    if match:
        return match.group(1).strip()
    # 没有 body 标签，返回全部
    return html.strip()


def _extract_title(html: str) -> str:
    """从 HTML 中提取 <title> 内容。"""
    match = re.search(r"<title[^>]*>(.*?)</title>", html, re.DOTALL | re.IGNORECASE)
    if match:
        return match.group(1).strip()
    return ""


def _rewrite_links(content: str, source_url: str) -> str:
    """将相对路径的资源链接重写为绝对路径。"""
    if not source_url:
        return content

    def _replace_attr(match: re.Match) -> str:
        attr = match.group(1)
        url = match.group(2)
        prefix = match.group(0)[: match.start(2) - match.start(0)]
        suffix = match.group(0)[match.end(2) - match.start(0) :]

        # 跳过已经是绝对 URL、data URI、锚点、mailto 等的
        if url.startswith(("http://", "https://", "data:", "#", "mailto:", "javascript:")):
            return match.group(0)

        # 将相对 URL 转为绝对 URL
        absolute = urljoin(source_url, url)
        return prefix + absolute + suffix

    # 重写 src 和 href 属性
    content = re.sub(
        r'(src|href)\s*=\s*["\']([^"\']+)["\']',
        _replace_attr,
        content,
        flags=re.IGNORECASE,
    )
    return content


async def fetch_page(url: str) -> Optional[tuple[str, str]]:
    """抓取指定 URL 的 HTML 页面。返回 (title, body_content) 或 None。"""
    try:
        timeout = aiohttp.ClientTimeout(total=30)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(url, headers={
                "User-Agent": "PyKYCH-ExternalFetcher/1.0"
            }) as resp:
                if resp.status != 200:
                    return None
                html = await resp.text(encoding="utf-8", errors="replace")
                title = _extract_title(html)
                body = _extract_body(html)
                return (title, body)
    except Exception:
        return None


async def fetch_and_cache_site(site_id: int) -> dict:
    """抓取外部站点首页并缓存。返回结果摘要。"""
    site = await get_external_site(site_id)
    if not site or not site["is_active"]:
        return {"status": "error", "message": "站点不存在或已停用"}

    source_url = site["source_url"]
    result = await fetch_page(source_url)
    if result is None:
        return {"status": "error", "message": f"无法访问 {source_url}"}

    title, body = result
    body = _rewrite_links(body, source_url)

    # 保存首页（path=""）
    await save_page(site_id, "", title, body)

    # 自动标签
    auto_tags = site.get("auto_tags", "")
    if auto_tags:
        tag_names = [t.strip() for t in auto_tags.split(",") if t.strip()]
        for tag_name in tag_names:
            await tag_manager.add_tag_to_article("html", f"ext:{site['name']}", tag_name)

    return {
        "status": "ok",
        "message": f"成功缓存 {source_url}",
        "title": title,
        "pages": 1,
    }


async def fetch_specific_page(site_id: int, path: str) -> dict:
    """抓取外部站点的特定路径页面并缓存。"""
    site = await get_external_site(site_id)
    if not site or not site["is_active"]:
        return {"status": "error", "message": "站点不存在或已停用"}

    url = f"{site['source_url']}/{path.lstrip('/')}"
    result = await fetch_page(url)
    if result is None:
        return {"status": "error", "message": f"无法访问 {url}"}

    title, body = result
    body = _rewrite_links(body, site["source_url"])
    await save_page(site_id, path, title, body)
    return {"status": "ok", "message": f"成功缓存 {url}", "title": title}

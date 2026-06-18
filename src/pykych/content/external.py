"""
外部 HTML 站点管理模块 — 从外部静态网站抓取 HTML 并缓存。
"""

import re
from typing import Optional
from urllib.parse import urljoin, urlparse

import aiohttp

from ..core.db import get_sys_pool, row_to_dict
from . import tags as tag_manager


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
    """从 HTML 中智能提取正文内容（去除导航、页脚等附属部分）。
    
    使用 html.parser 处理嵌套标签，优先级：
    1. <main> 或 <article> 标签内容
    2. 带有 content/main/article 类名的容器
    3. <body> 内容（去除 nav/footer/header/sidebar）
    4. 原始 HTML
    """
    from html.parser import HTMLParser

    class BodyExtractor(HTMLParser):
        def __init__(self):
            super().__init__()
            self.result = ""
            self.target_tag = None
            self.target_class = None
            self.depth = 0
            self.collecting = False
            self.buffer = []
            self.body_content = ""

        def handle_starttag(self, tag, attrs):
            attrs_dict = dict(attrs)
            classes = (attrs_dict.get("class", "")).lower().split()

            # Strategy 1: <main> or <article>
            if tag in ("main", "article") and not self.target_tag:
                self.target_tag = tag
                self.depth = 1
                self.collecting = True
                self.buffer = []
                return

            # Strategy 2: div with content class
            if not self.target_tag:
                for cls in ("content", "main-content", "article-content", "post-content", "entry-content"):
                    if cls in classes:
                        self.target_tag = tag
                        self.target_class = cls
                        self.depth = 1
                        self.collecting = True
                        self.buffer = []
                        return

            if self.collecting and tag == self.target_tag:
                self.depth += 1

            # Strategy 3: track body
            if tag == "body":
                self._body_pos = self.getpos()
                self._body_start = True

        def handle_endtag(self, tag):
            if self.collecting and tag == self.target_tag:
                self.depth -= 1
                if self.depth == 0:
                    self.collecting = False
                    self.result = "".join(self.buffer)
                    return

        def handle_data(self, data):
            if self.collecting:
                self.buffer.append(data)

        def handle_startendtag(self, tag, attrs):
            if self.collecting:
                self.buffer.append(self.get_starttag_text() or "")

    # Try strategies 1 & 2
    extractor = BodyExtractor()
    try:
        extractor.feed(html)
    except Exception:
        pass
    if extractor.result and len(extractor.result.strip()) > 50:
        return extractor.result.strip()

    # 策略 3：提取 <body> 并去除导航/页脚等
    match = re.search(r"<body[^>]*>(.*?)</body>", html, re.DOTALL | re.IGNORECASE)
    if match:
        body = match.group(1)
        # 去除常见非内容标签（这些标签通常不嵌套自身，正则可行）
        for tag in ("nav", "header", "footer", "aside", "script", "style"):
            body = re.sub(
                rf"<{tag}[\s>].*?</{tag}>", "", body, flags=re.DOTALL | re.IGNORECASE
            )
            body = re.sub(
                rf"<{tag}\s*/>", "", body, flags=re.IGNORECASE
            )
        # 去除常见非内容类名（深度跟踪方式处理嵌套 div）
        CONTENT_SKIP_CLASSES = {"sidebar", "navigation", "navbar", "footer", "header", "menu", "widget"}
        # 简化：使用非贪婪匹配（大多数情况有效；嵌套 div 已在策略 1/2 中处理）
        for cls in CONTENT_SKIP_CLASSES:
            body = re.sub(
                rf'<[^>]*class\s*=\s*["\'][^"\']*\b{cls}\b[^"\']*["\'][^>]*>.*?</[^>]+>',
                "", body, flags=re.DOTALL | re.IGNORECASE
            )
        result = body.strip()
        if len(result) > 50:
            return result

    return html.strip()


def _extract_title(html: str) -> str:
    """从 HTML 中提取 <title> 内容。"""
    match = re.search(r"<title[^>]*>(.*?)</title>", html, re.DOTALL | re.IGNORECASE)
    if match:
        return match.group(1).strip()
    return ""


def _rewrite_links(content: str, source_url: str, site_name: str = "") -> str:
    """将相对路径的资源链接重写为绝对路径。
    同时将内部页面链接重写为本站导入页面的路由。
    """
    if not source_url:
        return content

    from urllib.parse import urlparse
    parsed_source = urlparse(source_url)
    source_domain = f"{parsed_source.scheme}://{parsed_source.netloc}"

    def _replace_attr(match: re.Match) -> str:
        attr = match.group(1)
        url = match.group(2)
        prefix = match.group(0)[: match.start(2) - match.start(0)]
        suffix = match.group(0)[match.end(2) - match.start(0) :]

        # 跳过 data URI、锚点、mailto、javascript 等
        if url.startswith(("data:", "#", "mailto:", "javascript:")):
            return match.group(0)

        # 已经是绝对 URL 的情况
        if url.startswith(("http://", "https://")):
            # 如果是同站链接且 site_name 已知，转为本站路由
            if site_name and url.startswith(source_domain) and attr in ("href",):
                parsed = urlparse(url)
                path = parsed.path.strip("/")
                if path:
                    return f'{attr}="/html/{site_name}/{path}"'
                else:
                    return f'{attr}="/html/{site_name}"'
            return match.group(0)

        # 对于 href 相对路径，转向本站导入页面
        if attr == "href" and site_name:
            clean_url = url.split("?")[0].split("#")[0]
            path = clean_url.strip("/")
            if path:
                return f'{attr}="/html/{site_name}/{path}"'
            else:
                return f'{attr}="/html/{site_name}"'

        # 资源文件（图片等）使用绝对 URL
        absolute = urljoin(source_url, url)
        return prefix + absolute + suffix

    def _replace_srcset(match: re.Match) -> str:
        """处理 srcset 属性（可能包含逗号分隔的多个 URL）。"""
        attr = match.group(1)
        value = match.group(2)
        # 分割 srcset 值（逗号分隔，每项可能是 "URL descriptor" 格式）
        parts = []
        for part in value.split(","):
            part = part.strip()
            if not part:
                continue
            # 分割 URL 和描述符
            tokens = part.split(None, 1)
            url = tokens[0]
            descriptor = tokens[1] if len(tokens) > 1 else ""
            # 跳过 data URI 等
            if url.startswith(("data:", "#", "mailto:", "javascript:")):
                parts.append(part)
            elif url.startswith(("http://", "https://")):
                parts.append(part)
            else:
                absolute = urljoin(source_url, url)
                if descriptor:
                    parts.append(f"{absolute} {descriptor}")
                else:
                    parts.append(absolute)
        sep = ", "
        return f'{attr}="{sep.join(parts)}"'

    # 先处理 srcset（需要特殊逻辑处理多 URL）
    content = re.sub(
        r'(srcset)\s*=\s*["\']([^"\']+)["\']',
        _replace_srcset,
        content,
        flags=re.IGNORECASE,
    )
    # 再处理 src 和 href
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
    """抓取外部站点首页并缓存。返回结果摘要。
    
    优先通过插件系统处理，若无插件则使用内置实现。
    """
    # 优先使用插件实现
    from ..plugins_sys.manager import run_hook, Hooks
    results = await run_hook(Hooks.EXTERNAL_SITE_FETCH, site_id)
    if results:
        return results[0]
    
    # 内置回退实现
    site = await get_external_site(site_id)
    if not site or not site["is_active"]:
        return {"status": "error", "message": "站点不存在或已停用"}

    source_url = site["source_url"]
    result = await fetch_page(source_url)
    if result is None:
        return {"status": "error", "message": f"无法访问 {source_url}"}

    title, body = result
    body = _rewrite_links(body, source_url, site["name"])

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
    """抓取外部站点的特定路径页面并缓存。
    
    优先通过插件系统处理，若无插件则使用内置实现。
    """
    # 优先使用插件实现
    from ..plugins_sys.manager import run_hook, Hooks
    results = await run_hook(Hooks.EXTERNAL_PAGE_FETCH, site_id, path)
    if results:
        return results[0]
    
    # 内置回退实现
    site = await get_external_site(site_id)
    if not site or not site["is_active"]:
        return {"status": "error", "message": "站点不存在或已停用"}

    url = f"{site['source_url']}/{path.lstrip('/')}"
    result = await fetch_page(url)
    if result is None:
        return {"status": "error", "message": f"无法访问 {url}"}

    title, body = result
    body = _rewrite_links(body, site["source_url"], site["name"])
    await save_page(site_id, path, title, body)
    return {"status": "ok", "message": f"成功缓存 {url}", "title": title}


# ── 全面导入（爬虫） ──────────────────────────────────────

# 非 HTML 资源的文件扩展名（爬虫应跳过这些链接）
_SKIP_EXTENSIONS = {
    ".css", ".js", ".json", ".xml", ".rss", ".atom",
    ".png", ".jpg", ".jpeg", ".gif", ".svg", ".ico", ".webp", ".bmp",
    ".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx",
    ".zip", ".tar", ".gz", ".bz2", ".7z", ".rar",
    ".mp3", ".mp4", ".avi", ".mov", ".wmv", ".flv", ".webm",
    ".woff", ".woff2", ".ttf", ".eot", ".otf",
    ".map", ".txt", ".csv", ".tsv",
}


def _is_html_link(url: str) -> bool:
    """判断链接是否指向 HTML 页面（而非资源文件）。"""
    # 去掉查询参数和锚点
    path = url.split("?")[0].split("#")[0]
    # 如果路径以已知非 HTML 扩展名结尾，跳过
    lower = path.lower()
    for ext in _SKIP_EXTENSIONS:
        if lower.endswith(ext):
            return False
    # 如果没有扩展名或扩展名看起来像 HTML 相关，视为 HTML
    last_segment = path.rstrip("/").rsplit("/", 1)[-1] if path.rstrip("/") else ""
    if "." not in last_segment:
        return True
    ext = "." + last_segment.rsplit(".", 1)[-1].lower()
    return ext not in _SKIP_EXTENSIONS


def _extract_internal_links(html: str, source_domain: str) -> list[str]:
    """从 HTML 正文中提取所有内部 href 链接（指向同域名下的 HTML 页面）。
    
    Args:
        html: 页面 HTML 内容
        source_domain: 源站点域名（含 scheme，如 https://example.com）
    
    Returns:
        去重后的路径列表（相对路径格式，不含域名）
    """
    parsed_domain = urlparse(source_domain)
    domain_netloc = parsed_domain.netloc

    links: set[str] = set()

    # 匹配 href 属性
    href_pattern = re.compile(
        r"""href\s*=\s*["']([^"']+)["']""",
        re.IGNORECASE,
    )

    for match in href_pattern.finditer(html):
        url = match.group(1).strip()

        # 跳过特殊协议
        if url.startswith(("data:", "mailto:", "javascript:", "tel:", "ftp:", "#")):
            continue
        # 跳过纯锚点
        if not url or url.startswith("#"):
            continue

        # 处理绝对 URL
        if url.startswith(("http://", "https://")):
            parsed = urlparse(url)
            if parsed.netloc != domain_netloc:
                continue  # 外部链接，跳过
            # 同域链接，提取路径
            path = parsed.path.strip("/")
            if not _is_html_link(path):
                continue
            if path:
                links.add(path)
            else:
                links.add("")  # 首页
        else:
            # 相对 URL
            clean = url.split("?")[0].split("#")[0].strip("/")
            if not _is_html_link(clean):
                continue
            links.add(clean if clean else "")

    return list(links)


async def crawl_and_cache_site(site_id: int, max_pages: int = 500) -> dict:
    """全面导入：爬取外部站点的所有内部 HTML 页面并缓存，同时重构内部链接。
    
    优先通过插件系统处理，若无插件则使用内置实现。
    """
    # 优先使用插件实现
    from ..plugins_sys.manager import run_hook, Hooks
    results = await run_hook(Hooks.EXTERNAL_SITE_CRAWL, site_id, max_pages)
    if results:
        return results[0]
    
    # 内置回退实现
    site = await get_external_site(site_id)
    if not site or not site["is_active"]:
        return {"status": "error", "message": "站点不存在或已停用"}

    source_url = site["source_url"]
    site_name = site["name"]
    parsed_source = urlparse(source_url)
    source_domain = f"{parsed_source.scheme}://{parsed_source.netloc}"

    # 清除旧缓存，准备全新导入
    await clear_site_cache(site_id)

    # BFS 爬取队列：(path, url)
    # path 是本站缓存路径，url 是源站完整 URL
    visited_urls: set[str] = set()
    visited_paths: set[str] = set()
    to_visit: list[tuple[str, str]] = [("", source_url)]  # 首页
    cached_count = 0
    errors: list[str] = []

    while to_visit and cached_count < max_pages:
        path, url = to_visit.pop(0)

        # 去重检查
        normalized_url = url.rstrip("/")
        if normalized_url in visited_urls:
            continue
        visited_urls.add(normalized_url)
        if path in visited_paths:
            # 同一路径已被其他 URL 覆盖，跳过
            continue
        visited_paths.add(path)

        # 抓取页面
        result = await fetch_page(url)
        if result is None:
            errors.append(f"无法访问: {url}")
            continue

        title, body = result

        # 在重写链接之前提取内部链接（使用原始 body）
        internal_links = _extract_internal_links(body, source_domain)

        # 重写链接为本站路由
        body = _rewrite_links(body, source_url, site_name)

        # 保存页面
        await save_page(site_id, path, title, body)
        cached_count += 1

        # 将新发现的内部链接加入待爬取队列
        for link_path in internal_links:
            # 构建完整 URL
            if link_path == "":
                link_url = source_url
            elif link_path.startswith("http"):
                link_url = link_path
            else:
                link_url = urljoin(source_url, "/" + link_path)

            normalized = link_url.rstrip("/")
            if normalized not in visited_urls and normalized not in {u.rstrip("/") for _, u in to_visit}:
                to_visit.append((link_path, link_url))

    # 自动标签
    auto_tags = site.get("auto_tags", "")
    if auto_tags:
        tag_names = [t.strip() for t in auto_tags.split(",") if t.strip()]
        for tag_name in tag_names:
            await tag_manager.add_tag_to_article("html", f"ext:{site_name}", tag_name)

    return {
        "status": "ok",
        "message": f"成功导入 {cached_count} 个页面" + (f"，{len(errors)} 个失败" if errors else ""),
        "pages": cached_count,
        "errors": errors,
    }

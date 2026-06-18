"""
插件：外部站点导入 (External Site Import)
─────────────────────────────────────────
处理外部站点的首页抓取和全面爬取导入。

钩子:
    - external_site_fetch: 抓取外部站点首页并缓存
    - external_site_crawl: 全面爬取外部站点所有 HTML 页面并缓存
"""

from urllib.parse import urljoin, urlparse

from pykych.plugins_sys import register_hook, Hooks
from pykych.content import external as ext
from pykych.content import tags as tag_manager


# ── 非 HTML 资源的文件扩展名（爬虫应跳过这些链接） ──────────

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
    path = url.split("?")[0].split("#")[0]
    lower = path.lower()
    for ext_skip in _SKIP_EXTENSIONS:
        if lower.endswith(ext_skip):
            return False
    last_segment = path.rstrip("/").rsplit("/", 1)[-1] if path.rstrip("/") else ""
    if "." not in last_segment:
        return True
    file_ext = "." + last_segment.rsplit(".", 1)[-1].lower()
    return file_ext not in _SKIP_EXTENSIONS


def _extract_internal_links(html: str, source_domain: str) -> list[str]:
    """从 HTML 正文中提取所有内部 href 链接（指向同域名下的 HTML 页面）。"""
    import re
    parsed_domain = urlparse(source_domain)
    domain_netloc = parsed_domain.netloc

    links: set[str] = set()
    href_pattern = re.compile(r"""href\s*=\s*["']([^"']+)["']""", re.IGNORECASE)

    for match in href_pattern.finditer(html):
        url = match.group(1).strip()

        if url.startswith(("data:", "mailto:", "javascript:", "tel:", "ftp:", "#")):
            continue
        if not url or url.startswith("#"):
            continue

        if url.startswith(("http://", "https://")):
            parsed = urlparse(url)
            if parsed.netloc != domain_netloc:
                continue
            path = parsed.path.strip("/")
            if not _is_html_link(path):
                continue
            links.add(path if path else "")
        else:
            clean = url.split("?")[0].split("#")[0].strip("/")
            if not _is_html_link(clean):
                continue
            links.add(clean if clean else "")

    return list(links)


# ── 钩子回调 ─────────────────────────────────────────────────


async def _fetch_and_cache_site(site_id: int) -> dict:
    """抓取外部站点首页并缓存。"""
    site = await ext.get_external_site(site_id)
    if not site or not site["is_active"]:
        return {"status": "error", "message": "站点不存在或已停用"}

    source_url = site["source_url"]
    result = await ext.fetch_page(source_url)
    if result is None:
        return {"status": "error", "message": f"无法访问 {source_url}"}

    title, body = result
    body = ext._rewrite_links(body, source_url, site["name"])

    await ext.save_page(site_id, "", title, body)

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


async def _crawl_and_cache_site(site_id: int, max_pages: int = 500) -> dict:
    """全面导入：爬取外部站点的所有内部 HTML 页面并缓存，同时重构内部链接。"""
    site = await ext.get_external_site(site_id)
    if not site or not site["is_active"]:
        return {"status": "error", "message": "站点不存在或已停用"}

    source_url = site["source_url"]
    site_name = site["name"]
    parsed_source = urlparse(source_url)
    source_domain = f"{parsed_source.scheme}://{parsed_source.netloc}"

    await ext.clear_site_cache(site_id)

    visited_urls: set[str] = set()
    visited_paths: set[str] = set()
    to_visit: list[tuple[str, str]] = [("", source_url)]
    cached_count = 0
    errors: list[str] = []

    while to_visit and cached_count < max_pages:
        path, url = to_visit.pop(0)

        normalized_url = url.rstrip("/")
        if normalized_url in visited_urls:
            continue
        visited_urls.add(normalized_url)
        if path in visited_paths:
            continue
        visited_paths.add(path)

        result = await ext.fetch_page(url)
        if result is None:
            errors.append(f"无法访问: {url}")
            continue

        title, body = result
        internal_links = _extract_internal_links(body, source_domain)
        body = ext._rewrite_links(body, source_url, site_name)

        await ext.save_page(site_id, path, title, body)
        cached_count += 1

        for link_path in internal_links:
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


# ── 注册钩子 ─────────────────────────────────────────────────


def setup():
    """插件加载时由插件系统调用。"""
    register_hook(Hooks.EXTERNAL_SITE_FETCH, _fetch_and_cache_site)
    register_hook(Hooks.EXTERNAL_SITE_CRAWL, _crawl_and_cache_site)

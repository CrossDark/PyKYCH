"""
插件：外部页面导入 (External Page Import)
─────────────────────────────────────────
处理外部站点的单个页面抓取导入。

钩子:
    - external_page_fetch: 抓取外部站点的特定路径页面并缓存
"""

from pykych.plugins_sys import register_hook, Hooks
from pykych.content import external as ext


# ── 钩子回调 ─────────────────────────────────────────────────


async def _fetch_specific_page(site_id: int, path: str) -> dict:
    """抓取外部站点的特定路径页面并缓存。"""
    site = await ext.get_external_site(site_id)
    if not site or not site["is_active"]:
        return {"status": "error", "message": "站点不存在或已停用"}

    url = f"{site['source_url']}/{path.lstrip('/')}"
    result = await ext.fetch_page(url)
    if result is None:
        return {"status": "error", "message": f"无法访问 {url}"}

    title, body = result
    body = ext._rewrite_links(body, site["source_url"], site["name"])
    await ext.save_page(site_id, path, title, body)
    return {"status": "ok", "message": f"成功缓存 {url}", "title": title}


# ── 注册钩子 ─────────────────────────────────────────────────


def setup():
    """插件加载时由插件系统调用。"""
    register_hook(Hooks.EXTERNAL_PAGE_FETCH, _fetch_specific_page)

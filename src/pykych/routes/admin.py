"""
管理后台模块 — 统一文章管理、用户管理、站点设置。
路由前缀: /admin （全部需要登录）
重构版：使用统一 article_manager，消除重复代码，WordPress 风格界面。
"""

from lihil import Route, Request
from lihil import HTML
from starlette.responses import HTMLResponse, RedirectResponse
from pathlib import Path
from jinja2 import Environment, FileSystemLoader
from urllib.parse import quote

from ..content import articles as article_manager
from ..content import tags as tag_manager
from ..content import files as file_manager
from ..content import external as external_html
from ..content import notifications as notification_manager
from ..auth import user as auth_user
from ..auth import session as auth_session
from ..auth import profile as user_profile
from ..core import settings as settings_manager
from ..core import site_settings
from ..themes_sys import manager as theme_manager
from ..plugins_sys.manager import run_hook, Hooks

# ── 模板 ──
TEMPLATE_DIR = Path(__file__).parent.parent / "templates"
jinja_env = Environment(loader=FileSystemLoader(str(TEMPLATE_DIR)), autoescape=True)

# 注入站点设置访问函数
from ..core.settings import get_setting, get_site_title, get_site_subtitle
jinja_env.globals["site_logo"] = lambda: get_setting("site.logo_path", "/static/img/logo.png")
jinja_env.globals["site_favicon"] = lambda: get_setting("site.favicon_path", "/static/img/favicon.ico")
jinja_env.globals["site_title_func"] = lambda: get_site_title()
jinja_env.globals["site_subtitle_func"] = lambda: get_site_subtitle()

def render(template_name: str, status_code: int = 200, **context) -> HTMLResponse:
    template = jinja_env.get_template(template_name)
    return HTMLResponse(template.render(**context), status_code=status_code)

def redirect(url: str) -> RedirectResponse:
    return RedirectResponse(url, status_code=303)

# ── 登录保护 ──

async def _check(request: Request):
    """所有管理路由复用此检查。返回 (user, error_response)。"""
    user = await auth_session.get_current_user(request)
    if user is None:
        target = quote(request.url.path, safe="")
        return None, redirect(f"/auth/login?next={target}")
    # 补充用户头像（从 profile 表获取）
    try:
        profile = await user_profile.get_user_profile(user["username"])
        if profile:
            user["avatar"] = profile.get("avatar")
    except Exception:
        pass  # profile 表可能尚未初始化
    return user, None


async def _require_owner(request: Request):
    """要求站长权限。返回 (user, error_response)。"""
    user, err = await _check(request)
    if err:
        return None, err
    if not auth_user.is_owner(user):
        return None, render("admin_dashboard.html", title="权限不足 - PyKYCH",
            current_user=user, md_articles=[], wk_pages=[],
            md_total=0, wk_total=0, users=[],
            permission_error="仅站长可执行此操作。")
    return user, None


def _can_edit(article: dict | None, user: dict) -> bool:
    """检查用户是否有权限编辑文章：管理员/站长可编辑所有，普通用户只能编辑自己的。"""
    if article is None:
        return False
    if auth_user.is_admin(user):
        return True
    return article.get("author_id") == user.get("id")

# ── 路由 ──

admin_route = Route("/admin")

# ===== 仪表盘 =====

# ── 文章类型列表（用于统一构建 CRUD 路由） ──
_ARTICLE_TYPES = ["md", "wikidot", "html", "bbcode"]


@admin_route.get
async def dashboard(request: Request):
    user, err = await _check(request)
    if err: return err

    # 管理员/站长看到所有文章，普通用户只看到自己的
    is_admin = auth_user.is_admin(user)
    uid = user.get("id") if not is_admin else None

    articles_by_type = {}
    for atype in _ARTICLE_TYPES:
        result = await article_manager.list_articles(atype, page=1, per_page=100, author_id=uid)
        articles_by_type[atype] = result

    users = await auth_user.list_users() if auth_user.is_owner(user) else []
    subsite_links = await site_settings.list_subsite_links() if auth_user.is_owner(user) else []
    featured_articles = await site_settings.list_featured_articles() if auth_user.is_owner(user) else []
    tags = await tag_manager.get_all_tags_with_counts() if auth_user.is_admin(user) else []
    notifications = await notification_manager.list_notifications(include_inactive=True) if auth_user.is_admin(user) else []
    ext_sites = await external_html.list_external_sites() if auth_user.is_admin(user) else []
    site_settings_data = settings_manager.load_settings() if auth_user.is_owner(user) else {}

    return render("admin_dashboard.html", title="管理后台 - PyKYCH",
        current_user=user,
        md_articles=articles_by_type["md"]["articles"],
        wk_pages=articles_by_type["wikidot"]["articles"],
        html_pages=articles_by_type["html"]["articles"],
        bb_pages=articles_by_type["bbcode"]["articles"],
        md_total=articles_by_type["md"]["total"],
        wk_total=articles_by_type["wikidot"]["total"],
        html_total=articles_by_type["html"]["total"],
        bb_total=articles_by_type["bbcode"]["total"],
        users=users,
        subsite_links=subsite_links, featured_articles=featured_articles,
        tags=tags, notifications=notifications, ext_sites=ext_sites,
        site_settings=site_settings_data,
        permission_error=None)

# ═══════════════════════════════════════════════════════════════
#  统一文章 CRUD（替代原来 4×4 共 16 个重复函数）
# ═══════════════════════════════════════════════════════════════

# 文章类型显示名映射
_TYPE_LABELS = {
    "md": "Markdown 文章",
    "wikidot": "Wikidot 页面",
    "html": "HTML 页面",
    "bbcode": "BBCode 文章",
}

# ── 通用：新建表单 (GET) ──

async def _article_new_form(article_type: str, request: Request):
    user, err = await _check(request)
    if err: return err
    cfg = article_manager.get_article_config(article_type)
    return render("admin_form.html",
        title=f"{cfg['form_title_new']} - PyKYCH",
        form_title=cfg["form_title_new"],
        action=f"/admin/{article_type}/new",
        article_type=article_type, article=None, error=None)


# ── 通用：创建文章 (POST) ──

async def _article_create(article_type: str, request: Request):
    user, err = await _check(request)
    if err: return err
    cfg = article_manager.get_article_config(article_type)

    form = await request.form()
    title = form.get("title", "").strip()
    slug = form.get("article_slug", "").strip()
    content = form.get("content", "")
    tags_str = form.get("tags", "").strip()

    error = _validate(title, slug, content)
    if error:
        return render("admin_form.html",
            title=f"新建 {cfg['label']} - PyKYCH",
            form_title=cfg["form_title_new"],
            action=f"/admin/{article_type}/new",
            article_type=article_type,
            article={"title": title, "slug": slug, "content": content},
            error=error)

    try:
        await article_manager.create_article(article_type, slug, title, content, author_id=user.get("id"))
        # 处理用户提交的标签（修复 TODO 23：新建时也保存手动标签）
        tag_names = [t.strip() for t in tags_str.split(",") if t.strip()] if tags_str else []
        if cfg["default_tag"] not in tag_names:
            tag_names.append(cfg["default_tag"])
        await tag_manager.set_article_tags(article_type, slug, tag_names)
        return redirect("/admin")
    except Exception as e:
        return render("admin_form.html",
            title=f"新建 {cfg['label']} - PyKYCH",
            form_title=cfg["form_title_new"],
            action=f"/admin/{article_type}/new",
            article_type=article_type,
            article={"title": title, "slug": slug, "content": content},
            error=f"创建失败: {e}")


# ── 通用：编辑表单 (GET) ──

async def _article_edit_form(article_type: str, slug: str, request: Request):
    user, err = await _check(request)
    if err: return err
    cfg = article_manager.get_article_config(article_type)

    article = await article_manager.get_article(article_type, slug)
    if not article:
        # 不存在时进入新建模式
        return render("admin_form.html",
            title=f"{cfg['form_title_new']} - PyKYCH",
            form_title=cfg["form_title_new"],
            action=f"/admin/{article_type}/{slug}/edit",
            article_type=article_type, article={"slug": slug}, error=None)
    if not _can_edit(article, user):
        return render("admin_form.html", title="权限不足", form_title="错误",
            action="", article_type=article_type, article=None,
            error="您没有权限编辑此文章。")

    # 加载标签
    article["tags"] = await tag_manager.get_tags_for_article(article_type, slug)
    article["_tag_str"] = ", ".join(t["name"] for t in article["tags"])
    return render("admin_form.html",
        title=f"编辑: {article['title']} - PyKYCH",
        form_title=cfg["form_title_edit"],
        action=f"/admin/{article_type}/{slug}/edit",
        article_type=article_type, article=article, error=None)


# ── 通用：更新文章 (POST) ──

async def _article_update(article_type: str, slug: str, request: Request):
    user, err = await _check(request)
    if err: return err
    cfg = article_manager.get_article_config(article_type)

    form = await request.form()
    title = form.get("title", "").strip()
    content = form.get("content", "")
    tags_str = form.get("tags", "").strip()

    article = await article_manager.get_article(article_type, slug)

    if article is None:
        # 文章不存在 → 自动创建 (upsert)
        error = _validate(title, slug, content)
        if error:
            return render("admin_form.html",
                title=f"新建 {cfg['label']} - PyKYCH",
                form_title=cfg["form_title_new"],
                action=f"/admin/{article_type}/{slug}/edit",
                article_type=article_type,
                article={"title": title, "slug": slug, "content": content},
                error=error)
        try:
            await article_manager.create_article(article_type, slug, title, content, author_id=user.get("id"))
            tag_names = [t.strip() for t in tags_str.split(",") if t.strip()] if tags_str else []
            if cfg["default_tag"] not in tag_names:
                tag_names.append(cfg["default_tag"])
            await tag_manager.set_article_tags(article_type, slug, tag_names)
            return redirect("/admin")
        except Exception as e:
            return render("admin_form.html",
                title=f"新建 {cfg['label']} - PyKYCH",
                form_title=cfg["form_title_new"],
                action=f"/admin/{article_type}/{slug}/edit",
                article_type=article_type,
                article={"title": title, "slug": slug, "content": content},
                error=f"创建失败: {e}")

    if not _can_edit(article, user):
        return render("admin_form.html", title="权限不足", form_title="错误",
            action="", article_type=article_type, article=None,
            error="您没有权限编辑此文章。")

    error = _validate(title, slug, content, is_edit=True)
    if error:
        return render("admin_form.html",
            title=f"编辑: {title or slug} - PyKYCH",
            form_title=cfg["form_title_edit"],
            action=f"/admin/{article_type}/{slug}/edit",
            article_type=article_type,
            article={"title": title, "slug": slug, "content": content},
            error=error)

    # 更新文章内容（标题/内容未变化时 rowcount 可能为 0，但文章已在上方确认存在）
    await article_manager.update_article(article_type, slug, title, content)

    # 更新标签
    tag_names = [t.strip() for t in tags_str.split(",") if t.strip()] if tags_str else []
    if cfg["default_tag"] not in tag_names:
        tag_names.append(cfg["default_tag"])
    await tag_manager.set_article_tags(article_type, slug, tag_names)
    return redirect("/admin")


# ── 通用：删除文章 (POST) ──

async def _article_delete(article_type: str, slug: str, request: Request):
    user, err = await _check(request)
    if err: return err
    article = await article_manager.get_article(article_type, slug)
    if article is None:
        return redirect("/admin")
    if not _can_edit(article, user):
        return redirect("/admin")
    await article_manager.delete_article(article_type, slug)
    return redirect("/admin")


# ── 为每种文章类型显式注册路由（不能使用 lambda，LiHiL 需要类型标注） ──

# Markdown
@admin_route.sub("/md/new").get
async def md_create_form(request: Request):
    return await _article_new_form("md", request)

@admin_route.sub("/md/new").post
async def md_create(request: Request):
    return await _article_create("md", request)

@admin_route.sub("/md/{slug}/edit").get
async def md_edit_form(slug: str, request: Request):
    return await _article_edit_form("md", slug, request)

@admin_route.sub("/md/{slug}/edit").post
async def md_update(slug: str, request: Request):
    return await _article_update("md", slug, request)

@admin_route.sub("/md/{slug}/delete").post
async def md_delete(slug: str, request: Request):
    return await _article_delete("md", slug, request)

# Wikidot
@admin_route.sub("/wikidot/new").get
async def wikidot_create_form(request: Request):
    return await _article_new_form("wikidot", request)

@admin_route.sub("/wikidot/new").post
async def wikidot_create(request: Request):
    return await _article_create("wikidot", request)

@admin_route.sub("/wikidot/{slug}/edit").get
async def wikidot_edit_form(slug: str, request: Request):
    return await _article_edit_form("wikidot", slug, request)

@admin_route.sub("/wikidot/{slug}/edit").post
async def wikidot_update(slug: str, request: Request):
    return await _article_update("wikidot", slug, request)

@admin_route.sub("/wikidot/{slug}/delete").post
async def wikidot_delete(slug: str, request: Request):
    return await _article_delete("wikidot", slug, request)

# HTML
@admin_route.sub("/html/new").get
async def html_create_form(request: Request):
    return await _article_new_form("html", request)

@admin_route.sub("/html/new").post
async def html_create(request: Request):
    return await _article_create("html", request)

@admin_route.sub("/html/{slug}/edit").get
async def html_edit_form(slug: str, request: Request):
    return await _article_edit_form("html", slug, request)

@admin_route.sub("/html/{slug}/edit").post
async def html_update(slug: str, request: Request):
    return await _article_update("html", slug, request)

@admin_route.sub("/html/{slug}/delete").post
async def html_delete(slug: str, request: Request):
    return await _article_delete("html", slug, request)

# BBCode
@admin_route.sub("/bbcode/new").get
async def bbcode_create_form(request: Request):
    return await _article_new_form("bbcode", request)

@admin_route.sub("/bbcode/new").post
async def bbcode_create(request: Request):
    return await _article_create("bbcode", request)

@admin_route.sub("/bbcode/{slug}/edit").get
async def bbcode_edit_form(slug: str, request: Request):
    return await _article_edit_form("bbcode", slug, request)

@admin_route.sub("/bbcode/{slug}/edit").post
async def bbcode_update(slug: str, request: Request):
    return await _article_update("bbcode", slug, request)

@admin_route.sub("/bbcode/{slug}/delete").post
async def bbcode_delete(slug: str, request: Request):
    return await _article_delete("bbcode", slug, request)

# ===== 标签管理（管理员/站长） =====

@admin_route.sub("/tags").get
async def manage_tags(request: Request):
    """标签管理页面 — 管理员和站长可以管理所有标签。"""
    user, err = await _check(request)
    if err: return err
    if not auth_user.is_admin(user):
        return render("admin_dashboard.html", title="权限不足 - PyKYCH",
            current_user=user, md_articles=[], wk_pages=[],
            html_pages=[], bb_pages=[], md_total=0, wk_total=0,
            html_total=0, bb_total=0, users=[],
            subsite_links=[], featured_articles=[],
            permission_error="仅管理员和站长可管理标签。")
    tags = await tag_manager.get_all_tags_with_counts()
    return render("admin_tags.html", title="标签管理 - PyKYCH",
        current_user=user, tags=tags, error=None)

@admin_route.sub("/tags/create").post
async def create_tag_route(request: Request):
    """创建新标签。"""
    user, err = await _check(request)
    if err: return err
    if not auth_user.is_admin(user):
        return redirect("/admin")
    form = await request.form()
    name = form.get("name", "").strip()
    if name:
        await tag_manager.create_tag(name)
    return redirect("/admin/tags")

@admin_route.sub("/tags/{tag_id}/rename").post
async def rename_tag_route(tag_id: int, request: Request):
    """重命名标签。"""
    user, err = await _check(request)
    if err: return err
    if not auth_user.is_admin(user):
        return redirect("/admin")
    form = await request.form()
    new_name = form.get("new_name", "").strip()
    if new_name:
        await tag_manager.rename_tag(tag_id, new_name)
    return redirect("/admin/tags")

@admin_route.sub("/tags/{tag_id}/delete").post
async def delete_tag_route(tag_id: int, request: Request):
    """删除标签。"""
    user, err = await _check(request)
    if err: return err
    if not auth_user.is_admin(user):
        return redirect("/admin")
    await tag_manager.delete_tag(tag_id)
    return redirect("/admin/tags")

# ===== 通知管理（管理员/站长） =====

@admin_route.sub("/notifications").get
async def manage_notifications(request: Request):
    """通知管理页面。"""
    user, err = await _check(request)
    if err: return err
    if not auth_user.is_admin(user):
        return render("admin_dashboard.html", title="权限不足 - PyKYCH",
            current_user=user, md_articles=[], wk_pages=[],
            html_pages=[], bb_pages=[], md_total=0, wk_total=0,
            html_total=0, bb_total=0, users=[],
            subsite_links=[], featured_articles=[],
            permission_error="仅管理员和站长可管理通知。")
    notifications = await notification_manager.list_notifications(include_inactive=True)
    return render("admin_notifications.html", title="通知管理 - PyKYCH",
        current_user=user, notifications=notifications, error=None)

@admin_route.sub("/notifications/create").post
async def create_notification(request: Request):
    """创建新通知。"""
    user, err = await _check(request)
    if err: return err
    if not auth_user.is_admin(user):
        return redirect("/admin")
    form = await request.form()
    title = form.get("title", "").strip()
    content = form.get("content", "").strip()
    is_important = form.get("is_important") == "1"
    if title and content:
        await notification_manager.create_notification(title, content, is_important)
    return redirect("/admin/notifications")

@admin_route.sub("/notifications/{notif_id}/edit").post
async def edit_notification(notif_id: int, request: Request):
    """编辑通知。"""
    user, err = await _check(request)
    if err: return err
    if not auth_user.is_admin(user):
        return redirect("/admin")
    form = await request.form()
    title = form.get("title", "").strip()
    content = form.get("content", "").strip()
    is_important = form.get("is_important") == "1"
    is_active = form.get("is_active") == "1"
    if title and content:
        await notification_manager.update_notification(
            notif_id, title, content, is_important, is_active
        )
    return redirect("/admin/notifications")

@admin_route.sub("/notifications/{notif_id}/toggle-important").post
async def toggle_notification_importance(notif_id: int, request: Request):
    """切换通知的重要状态。"""
    user, err = await _check(request)
    if err: return err
    if not auth_user.is_admin(user):
        return redirect("/admin")
    await notification_manager.toggle_notification_importance(notif_id)
    return redirect("/admin/notifications")

@admin_route.sub("/notifications/{notif_id}/toggle-active").post
async def toggle_notification_active(notif_id: int, request: Request):
    """切换通知的启用/停用状态。"""
    user, err = await _check(request)
    if err: return err
    if not auth_user.is_admin(user):
        return redirect("/admin")
    await notification_manager.toggle_notification_active(notif_id)
    return redirect("/admin/notifications")

@admin_route.sub("/notifications/{notif_id}/delete").post
async def delete_notification_route(notif_id: int, request: Request):
    """删除通知。"""
    user, err = await _check(request)
    if err: return err
    if not auth_user.is_admin(user):
        return redirect("/admin")
    await notification_manager.delete_notification(notif_id)
    return redirect("/admin/notifications")

# ===== 外部站点管理（管理员/站长） =====

@admin_route.sub("/external").get
async def manage_external_sites(request: Request):
    """外部站点管理页面。"""
    user, err = await _check(request)
    if err: return err
    if not auth_user.is_admin(user):
        return render("admin_dashboard.html", title="权限不足 - PyKYCH",
            current_user=user, md_articles=[], wk_pages=[],
            html_pages=[], bb_pages=[], md_total=0, wk_total=0,
            html_total=0, bb_total=0, users=[],
            subsite_links=[], featured_articles=[],
            permission_error="仅管理员和站长可管理外部站点。")
    sites = await external_html.list_external_sites()
    return render("admin_external.html", title="外部站点管理 - PyKYCH",
        current_user=user, sites=sites, error=None)

@admin_route.sub("/external/add").post
async def add_external_site(request: Request):
    """添加外部站点。"""
    user, err = await _check(request)
    if err: return err
    if not auth_user.is_admin(user):
        return redirect("/admin")
    form = await request.form()
    name = form.get("name", "").strip()
    source_url = form.get("source_url", "").strip()
    description = form.get("description", "").strip()
    auto_tags = form.get("auto_tags", "").strip()
    if name and source_url:
        try:
            await external_html.create_external_site(name, source_url, description, auto_tags)
        except Exception:
            pass
    return redirect("/admin/external")

@admin_route.sub("/external/{site_id}/edit").post
async def edit_external_site(site_id: int, request: Request):
    """编辑外部站点配置。"""
    user, err = await _check(request)
    if err: return err
    if not auth_user.is_admin(user):
        return redirect("/admin")
    form = await request.form()
    source_url = form.get("source_url", "").strip()
    description = form.get("description", "").strip()
    auto_tags = form.get("auto_tags", "").strip()
    is_active = form.get("is_active") == "1"
    await external_html.update_external_site(
        site_id, source_url=source_url, description=description,
        auto_tags=auto_tags, is_active=is_active
    )
    return redirect("/admin/external")

@admin_route.sub("/external/{site_id}/fetch").post
async def fetch_external_site(site_id: int, request: Request):
    """手动刷新外部站点首页缓存。"""
    user, err = await _check(request)
    if err: return err
    if not auth_user.is_admin(user):
        return redirect("/admin")
    # 优先使用插件实现，回退到内置实现
    results = await run_hook(Hooks.EXTERNAL_SITE_FETCH, site_id)
    if results:
        result = results[0]
    else:
        result = await external_html.fetch_and_cache_site(site_id)
    return redirect("/admin/external")

@admin_route.sub("/external/{site_id}/crawl").post
async def crawl_external_site(site_id: int, request: Request):
    """全面导入：爬取外部站点所有 HTML 页面并缓存。"""
    user, err = await _check(request)
    if err: return err
    if not auth_user.is_admin(user):
        return redirect("/admin")
    form = await request.form()
    max_pages_str = form.get("max_pages", "500").strip()
    try:
        max_pages = int(max_pages_str)
    except ValueError:
        max_pages = 500
    # 优先使用插件实现，回退到内置实现
    results = await run_hook(Hooks.EXTERNAL_SITE_CRAWL, site_id, max_pages)
    if results:
        result = results[0]
    else:
        result = await external_html.crawl_and_cache_site(site_id, max_pages=max_pages)
    sites = await external_html.list_external_sites()
    return render("admin_external.html", title="外部站点管理 - PyKYCH",
        current_user=user, sites=sites,
        success=result.get("message", ""),
        crawl_result=result,
        error=None)


@admin_route.sub("/external/{site_id}/fetch-page").post
async def fetch_single_page(site_id: int, request: Request):
    """导入单个外部页面。"""
    user, err = await _check(request)
    if err: return err
    if not auth_user.is_admin(user):
        return redirect("/admin")
    form = await request.form()
    page_path = form.get("page_path", "").strip().strip("/")
    if not page_path:
        sites = await external_html.list_external_sites()
        return render("admin_external.html", title="外部站点管理 - PyKYCH",
            current_user=user, sites=sites,
            error="请输入页面路径。")
    # 优先使用插件实现，回退到内置实现
    results = await run_hook(Hooks.EXTERNAL_PAGE_FETCH, site_id, page_path)
    if results:
        result = results[0]
    else:
        result = await external_html.fetch_specific_page(site_id, page_path)
    sites = await external_html.list_external_sites()
    if result["status"] == "ok":
        return render("admin_external.html", title="外部站点管理 - PyKYCH",
            current_user=user, sites=sites,
            success=result.get("message", ""))
    else:
        return render("admin_external.html", title="外部站点管理 - PyKYCH",
            current_user=user, sites=sites,
            error=result.get("message", "导入失败"))

@admin_route.sub("/external/{site_id}/toggle").post
async def toggle_external_site(site_id: int, request: Request):
    """切换外部站点启用/停用状态。"""
    user, err = await _check(request)
    if err: return err
    if not auth_user.is_admin(user):
        return redirect("/admin")
    site = await external_html.get_external_site(site_id)
    if site:
        await external_html.update_external_site(
            site_id, is_active=not site.get("is_active", True)
        )
    return redirect("/admin/external")

@admin_route.sub("/external/{site_id}/clear-cache").post
async def clear_external_cache(site_id: int, request: Request):
    """清除外部站点缓存。"""
    user, err = await _check(request)
    if err: return err
    if not auth_user.is_admin(user):
        return redirect("/admin")
    await external_html.clear_site_cache(site_id)
    return redirect("/admin/external")

@admin_route.sub("/external/{site_id}/delete").post
async def delete_external_site(site_id: int, request: Request):
    """删除外部站点。"""
    user, err = await _check(request)
    if err: return err
    if not auth_user.is_admin(user):
        return redirect("/admin")
    await external_html.delete_external_site(site_id)
    return redirect("/admin/external")

# ===== 静态文件管理（管理员/站长） =====

@admin_route.sub("/files").get
async def manage_files(request: Request, page: int = 1):
    """静态文件管理页面。"""
    user, err = await _check(request)
    if err: return err
    if not auth_user.is_admin(user):
        return render("admin_dashboard.html", title="权限不足 - PyKYCH",
            current_user=user, md_articles=[], wk_pages=[],
            html_pages=[], bb_pages=[], md_total=0, wk_total=0,
            html_total=0, bb_total=0, users=[],
            subsite_links=[], featured_articles=[],
            tags=[], notifications=[], ext_sites=[],
            permission_error="仅管理员和站长可管理文件。")
    result = await file_manager.list_files(page=page, per_page=20)
    return render("admin_files.html", title="文件管理 - PyKYCH",
        current_user=user, files=result["files"],
        page=result["page"], total_pages=result["total_pages"],
        total=result["total"], error=None)

@admin_route.sub("/files/upload").post
async def upload_file(request: Request):
    """上传文件。"""
    user, err = await _check(request)
    if err: return err
    if not auth_user.is_admin(user):
        return redirect("/admin")

    form = await request.form()
    uploaded = form.get("file")

    if uploaded is None or not hasattr(uploaded, "filename"):
        result = await file_manager.list_files()
        return render("admin_files.html", title="文件管理 - PyKYCH",
            current_user=user, files=result["files"],
            page=1, total_pages=result["total_pages"],
            total=result["total"], error="请选择要上传的文件。")

    original_name = uploaded.filename or "unknown"
    content = await uploaded.read()

    if len(content) > file_manager.MAX_FILE_SIZE:
        result = await file_manager.list_files()
        return render("admin_files.html", title="文件管理 - PyKYCH",
            current_user=user, files=result["files"],
            page=1, total_pages=result["total_pages"],
            total=result["total"],
            error=f"文件过大（最大 {file_manager.MAX_FILE_SIZE // 1024 // 1024}MB）。")

    file_manager._ensure_upload_dir()
    store_name = file_manager._generate_filename(original_name)
    file_path = file_manager.UPLOAD_DIR / store_name

    with open(file_path, "wb") as f:
        f.write(content)

    mime_type = getattr(uploaded, "content_type", "application/octet-stream") or "application/octet-stream"

    await file_manager.save_file_record(
        store_name, original_name, len(content), mime_type,
        uploaded_by=user.get("id"),
    )

    return redirect("/admin/files")

@admin_route.sub("/files/{file_id}/delete").post
async def delete_file_route(file_id: int, request: Request):
    """删除文件。"""
    user, err = await _check(request)
    if err: return err
    if not auth_user.is_admin(user):
        return redirect("/admin")
    await file_manager.delete_file(file_id)
    return redirect("/admin/files")

# ===== 用户管理（仅站长） =====

@admin_route.sub("/users").get
async def manage_users(request: Request):
    """用户管理页面 — 仅站长可访问。"""
    user, err = await _require_owner(request)
    if err: return err
    users = await auth_user.list_users()
    return render("admin_users.html", title="用户管理 - PyKYCH",
        current_user=user, users=users, error=None)


@admin_route.sub("/users/add").post
async def add_user(request: Request):
    """站长添加新用户。"""
    user, err = await _require_owner(request)
    if err: return err
    form = await request.form()
    username = form.get("username", "").strip()
    password = form.get("password", "")
    nickname = form.get("nickname", "").strip()
    role = form.get("role", "user").strip()

    if not username or not password:
        return redirect("/admin/users")
    if role not in ("user", "admin", "owner"):
        role = "user"

    try:
        existing = await auth_user.get_user_by_username(username)
        if existing:
            return redirect("/admin/users")
        await auth_user.create_user(username, password, nickname, role=role)
    except Exception:
        pass
    return redirect("/admin/users")

@admin_route.sub("/users/{username}/delete").post
async def delete_user(username: str, request: Request):
    """站长删除用户（不允许删除自己）。"""
    owner_user, err = await _require_owner(request)
    if err: return err
    if username == owner_user["username"]:
        return redirect("/admin/users")
    await auth_user.delete_user(username)
    return redirect("/admin/users")

@admin_route.sub("/users/{username}/reset-password").post
async def reset_password(username: str, request: Request):
    """站长重置用户密码。"""
    owner_user, err = await _require_owner(request)
    if err: return err
    form = await request.form()
    new_password = form.get("new_password", "")
    if new_password:
        await auth_user.update_user_password(username, new_password)
    return redirect("/admin/users")

@admin_route.sub("/users/{username}/role").post
async def change_role(username: str, request: Request):
    """站长修改用户角色。"""
    owner_user, err = await _require_owner(request)
    if err: return err
    if username == owner_user["username"]:
        return redirect("/admin/users")  # 不允许修改自己的角色
    form = await request.form()
    new_role = form.get("role", "user").strip()
    if new_role in ("user", "admin", "owner"):
        await auth_user.update_user_role(username, new_role)
    return redirect("/admin/users")

# ===== 子站点链接管理（仅站长） =====

@admin_route.sub("/subsite/add").post
async def add_subsite(request: Request):
    """站长添加子站点链接。"""
    user, err = await _require_owner(request)
    if err: return err
    form = await request.form()
    name = form.get("name", "").strip()
    url = form.get("url", "").strip()
    description = form.get("description", "").strip()
    sort_order = form.get("sort_order", "0").strip()
    if name and url:
        try:
            order = int(sort_order) if sort_order else 0
        except ValueError:
            order = 0
        await site_settings.create_subsite_link(name, url, description, order)
    return redirect("/admin")


@admin_route.sub("/subsite/{link_id}/edit").post
async def edit_subsite(link_id: int, request: Request):
    """站长编辑子站点链接。"""
    user, err = await _require_owner(request)
    if err: return err
    form = await request.form()
    name = form.get("name", "").strip()
    url = form.get("url", "").strip()
    description = form.get("description", "").strip()
    sort_order = form.get("sort_order", "0").strip()
    if name and url:
        try:
            order = int(sort_order) if sort_order else 0
        except ValueError:
            order = 0
        await site_settings.update_subsite_link(link_id, name, url, description, order)
    return redirect("/admin")


@admin_route.sub("/subsite/{link_id}/delete").post
async def delete_subsite(link_id: int, request: Request):
    """站长删除子站点链接。"""
    user, err = await _require_owner(request)
    if err: return err
    await site_settings.delete_subsite_link(link_id)
    return redirect("/admin")


# ===== 主页推荐文章管理（仅站长） =====

@admin_route.sub("/featured/add").post
async def add_featured(request: Request):
    """站长添加推荐文章。"""
    user, err = await _require_owner(request)
    if err: return err
    form = await request.form()
    article_type = form.get("article_type", "").strip()
    article_slug = form.get("article_slug", "").strip()
    if article_type and article_slug:
        await site_settings.add_featured_article(article_type, article_slug)
    return redirect("/admin")


@admin_route.sub("/featured/{featured_id}/remove").post
async def remove_featured(featured_id: int, request: Request):
    """站长移除推荐文章。"""
    user, err = await _require_owner(request)
    if err: return err
    await site_settings.remove_featured_article(featured_id)
    return redirect("/admin")


@admin_route.sub("/featured/{featured_id}/move/{direction}").post
async def move_featured(featured_id: int, direction: str, request: Request):
    """站长上移/下移推荐文章。"""
    user, err = await _require_owner(request)
    if err: return err
    if direction in ("up", "down"):
        await site_settings.move_featured_article(featured_id, direction)
    return redirect("/admin")

# ===== 站点设置管理（仅站长） =====

@admin_route.sub("/settings").get
async def manage_site_settings(request: Request):
    """站点设置管理页面。"""
    user, err = await _check(request)
    if err: return err
    if not auth_user.is_owner(user):
        return redirect("/admin")
    site_cfg = settings_manager.load_settings()
    themes = theme_manager.list_themes()
    return render("admin_settings.html", title="站点设置 - PyKYCH",
        current_user=user, settings=site_cfg, themes=themes, error=None)


@admin_route.sub("/settings/update").post
async def update_site_settings(request: Request):
    """更新站点设置（含 Logo/Favicon 上传）。"""
    user, err = await _check(request)
    if err: return err
    if not auth_user.is_owner(user):
        return redirect("/admin")

    form = await request.form()

    # ── Logo 上传 ──
    logo_file = form.get("logo_file")
    if logo_file is not None and hasattr(logo_file, "filename") and logo_file.filename:
        content = await logo_file.read()
        if content and len(content) <= 2 * 1024 * 1024:
            logo_url = await _save_site_asset("logo", content, logo_file.filename)
            if logo_url:
                settings_manager.set_setting("site.logo_path", logo_url)

    # ── Favicon 上传 ──
    favicon_file = form.get("favicon_file")
    if favicon_file is not None and hasattr(favicon_file, "filename") and favicon_file.filename:
        content = await favicon_file.read()
        if content and len(content) <= 512 * 1024:  # 512KB for favicon
            favicon_url = await _save_site_asset("favicon", content, favicon_file.filename)
            if favicon_url:
                settings_manager.set_setting("site.favicon_path", favicon_url)

    # ── 如果没上传新文件，保留旧路径 ──
    if not (logo_file is not None and hasattr(logo_file, "filename") and logo_file.filename):
        settings_manager.set_setting("site.logo_path", form.get("site_logo_path", "").strip())
    if not (favicon_file is not None and hasattr(favicon_file, "filename") and favicon_file.filename):
        settings_manager.set_setting("site.favicon_path", form.get("favicon_path", "").strip())

    # 站点信息
    settings_manager.set_setting("site.title", form.get("site_title", "").strip())
    settings_manager.set_setting("site.subtitle", form.get("site_subtitle", "").strip())
    settings_manager.set_setting("site.description", form.get("site_description", "").strip())
    settings_manager.set_setting("site.icp_number", form.get("site_icp", "").strip())

    # 外观
    settings_manager.set_setting("appearance.theme", form.get("theme", "auto").strip())
    settings_manager.set_setting("appearance.style_theme", form.get("style_theme", "default").strip())
    settings_manager.set_setting("appearance.primary_color", form.get("primary_color", "#3b82f6").strip())

    # 应用样式主题
    new_style = form.get("style_theme", "default").strip()
    if new_style and theme_manager.list_themes():
        theme_manager.set_active_theme(new_style)

    # 功能
    settings_manager.set_setting("features.enable_comments", form.get("enable_comments") == "1")
    settings_manager.set_setting("features.enable_search", form.get("enable_search") == "1")
    settings_manager.set_setting("features.enable_dark_mode", form.get("enable_dark_mode") == "1")
    settings_manager.set_setting("features.posts_per_page", int(form.get("posts_per_page", "10")))

    # 社交
    settings_manager.set_setting("social.github", form.get("github", "").strip())
    settings_manager.set_setting("social.twitter", form.get("twitter", "").strip())
    settings_manager.set_setting("social.email", form.get("email", "").strip())

    return redirect("/admin/settings")


async def _save_site_asset(name: str, data: bytes, filename: str) -> str | None:
    """保存站点资源文件（logo、favicon）到 static/img/ 目录。返回 URL。"""
    import os, hashlib
    from pathlib import Path

    STATIC_IMG = Path(__file__).parent.parent / "static" / "img"
    STATIC_IMG.mkdir(parents=True, exist_ok=True)

    ext = os.path.splitext(filename)[1].lower()
    # 允许的扩展名
    ALLOWED = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg", ".ico", ".bmp"}
    if ext not in ALLOWED:
        ext = ".png"  # 回退

    unique = hashlib.md5(data).hexdigest()[:12]
    safe_name = f"{name}_{unique}{ext}"
    save_path = STATIC_IMG / safe_name

    try:
        with open(save_path, "wb") as f:
            f.write(data)
        return f"/static/img/{safe_name}"
    except (OSError, PermissionError) as e:
        from .. import logger
        logger.error(f"保存站点资源失败 {save_path}: {e}")
        return None


# ===== 主题管理路由 =====

@admin_route.sub("/themes/upload").post
async def upload_theme(request: Request):
    """上传主题 ZIP 包。"""
    user, err = await _check(request)
    if err: return err
    if not auth_user.is_owner(user):
        return redirect("/admin")

    form = await request.form()
    theme_file = form.get("theme_zip")

    if not theme_file or not hasattr(theme_file, "filename") or not theme_file.filename:
        site_cfg = settings_manager.load_settings()
        themes = theme_manager.list_themes()
        return render("admin_settings.html", title="站点设置 - PyKYCH",
            current_user=user, settings=site_cfg, themes=themes,
            error="请选择要上传的主题 ZIP 文件。")

    fname = theme_file.filename.lower()
    if not fname.endswith(".zip"):
        site_cfg = settings_manager.load_settings()
        themes = theme_manager.list_themes()
        return render("admin_settings.html", title="站点设置 - PyKYCH",
            current_user=user, settings=site_cfg, themes=themes,
            error="仅支持 .zip 格式的主题包。")

    content = await theme_file.read()
    if len(content) > 10 * 1024 * 1024:  # 最大 10MB
        site_cfg = settings_manager.load_settings()
        themes = theme_manager.list_themes()
        return render("admin_settings.html", title="站点设置 - PyKYCH",
            current_user=user, settings=site_cfg, themes=themes,
            error="主题包过大，最大支持 10MB。")

    import zipfile, io, tempfile, shutil

    try:
        with zipfile.ZipFile(io.BytesIO(content)) as zf:
            # 查找主题根目录（可能嵌套了一层）
            theme_root = _find_theme_root(zf)
            if theme_root is None:
                site_cfg = settings_manager.load_settings()
                themes = theme_manager.list_themes()
                return render("admin_settings.html", title="站点设置 - PyKYCH",
                    current_user=user, settings=site_cfg, themes=themes,
                    error="ZIP 包中未找到 theme.yaml，请确保包含有效的主题配置文件。")

            # 验证必需文件
            has_yaml = any(n == f"{theme_root}theme.yaml" or n.startswith(f"{theme_root}theme.yaml") for n in zf.namelist())
            has_css = any(n == f"{theme_root}static/theme.css" or n.startswith(f"{theme_root}static/theme.css") for n in zf.namelist())
            if not has_yaml:
                site_cfg = settings_manager.load_settings()
                themes = theme_manager.list_themes()
                return render("admin_settings.html", title="站点设置 - PyKYCH",
                    current_user=user, settings=site_cfg, themes=themes,
                    error="主题包缺少 theme.yaml 配置文件。")
            if not has_css:
                site_cfg = settings_manager.load_settings()
                themes = theme_manager.list_themes()
                return render("admin_settings.html", title="站点设置 - PyKYCH",
                    current_user=user, settings=site_cfg, themes=themes,
                    error="主题包缺少 static/theme.css 样式文件。")

            # 提取主题到临时目录
            with tempfile.TemporaryDirectory() as tmpdir:
                zf.extractall(tmpdir)
                extracted_root = Path(tmpdir) / theme_root.rstrip("/") if theme_root else Path(tmpdir)

                # 读取主题名
                yaml_path = extracted_root / "theme.yaml"
                if not yaml_path.exists():
                    yaml_path = Path(tmpdir) / "theme.yaml"

                import yaml
                with open(yaml_path, "r", encoding="utf-8") as f:
                    config = yaml.safe_load(f) or {}

                # 主题目录名：使用配置中的 name 或主题根目录名
                theme_dirname = (config.get("name") or theme_root.rstrip("/")).strip().lower().replace(" ", "_")
                # 安全检查：只允许字母数字下划线
                import re
                theme_dirname = re.sub(r"[^a-z0-9_]", "", theme_dirname)
                if not theme_dirname:
                    theme_dirname = "uploaded_theme"

                target = theme_manager.THEMES_DIR / theme_dirname
                if target.exists():
                    shutil.rmtree(target)  # 覆盖已存在的同名主题

                shutil.copytree(str(extracted_root), str(target))

            # 重新加载主题列表
            try:
                theme_manager.list_themes()
            except Exception:
                pass

            site_cfg = settings_manager.load_settings()
            themes = theme_manager.list_themes()
            return render("admin_settings.html", title="站点设置 - PyKYCH",
                current_user=user, settings=site_cfg, themes=themes,
                success=f"主题「{config.get('name', theme_dirname)}」已成功安装。")

    except zipfile.BadZipFile:
        site_cfg = settings_manager.load_settings()
        themes = theme_manager.list_themes()
        return render("admin_settings.html", title="站点设置 - PyKYCH",
            current_user=user, settings=site_cfg, themes=themes,
            error="ZIP 文件损坏，请重新上传。")
    except Exception as e:
        site_cfg = settings_manager.load_settings()
        themes = theme_manager.list_themes()
        return render("admin_settings.html", title="站点设置 - PyKYCH",
            current_user=user, settings=site_cfg, themes=themes,
            error=f"安装主题失败: {e}")


def _find_theme_root(zf: "zipfile.ZipFile") -> str | None:
    """在 ZIP 中查找主题根目录（包含 theme.yaml 的目录或根）。"""
    # 先检查根目录是否有 theme.yaml
    if "theme.yaml" in [n.rstrip("/") for n in zf.namelist()]:
        return ""

    # 查找嵌套的主题目录（去除顶层包装）
    dirs = set()
    for name in zf.namelist():
        parts = name.split("/")
        if len(parts) >= 2 and parts[0]:
            dirs.add(parts[0])

    for d in dirs:
        yaml_path = f"{d}/theme.yaml"
        if yaml_path in zf.namelist():
            return f"{d}/"

    return None


@admin_route.sub("/themes/refresh").post
async def refresh_themes(request: Request):
    """手动刷新主题列表（检测手动添加的主题目录）。"""
    user, err = await _check(request)
    if err: return err
    if not auth_user.is_owner(user):
        return redirect("/admin")

    # 确保默认主题存在
    theme_manager.ensure_default_theme()
    themes = theme_manager.list_themes()
    site_cfg = settings_manager.load_settings()
    return render("admin_settings.html", title="站点设置 - PyKYCH",
        current_user=user, settings=site_cfg, themes=themes,
        success=f"已检测到 {len(themes)} 个主题。")


@admin_route.sub("/themes/{theme_name}/delete").post
async def delete_theme_route(theme_name: str, request: Request):
    """删除指定主题。"""
    user, err = await _check(request)
    if err: return err
    if not auth_user.is_owner(user):
        return redirect("/admin")

    success = theme_manager.delete_theme(theme_name)
    site_cfg = settings_manager.load_settings()
    themes = theme_manager.list_themes()

    # 如果删除了当前激活的主题，回退到 default
    if theme_name == settings_manager.get_setting("appearance.style_theme", "default"):
        settings_manager.set_setting("appearance.style_theme", "default")
        theme_manager.set_active_theme("default")
        site_cfg = settings_manager.load_settings()

    if success:
        return render("admin_settings.html", title="站点设置 - PyKYCH",
            current_user=user, settings=site_cfg, themes=themes,
            success=f"主题「{theme_name}」已删除。")
    else:
        return render("admin_settings.html", title="站点设置 - PyKYCH",
            current_user=user, settings=site_cfg, themes=themes,
            error="无法删除该主题（可能是默认主题或当前激活的主题）。")


# ===== 用户资料路由 =====

@admin_route.sub("/profile").get
async def user_profile_page(request: Request):
    """当前用户的个人资料页面。"""
    user, err = await _check(request)
    if err: return err

    profile = await user_profile.get_user_profile(user["username"])
    return render("admin_profile.html", title="个人资料 - PyKYCH",
        current_user=user, profile=profile, error=None)


@admin_route.sub("/profile/update").post
async def update_profile_route(request: Request):
    """更新个人资料。"""
    user, err = await _check(request)
    if err: return err

    form = await request.form()
    await user_profile.update_profile(
        username=user["username"],
        nickname=form.get("nickname", "").strip() or None,
        bio=form.get("bio", "").strip() or None,
        email=form.get("email", "").strip() or None,
        website=form.get("website", "").strip() or None,
    )
    return redirect("/admin/profile")


@admin_route.sub("/profile/password").post
async def change_password_route(request: Request):
    """修改密码。"""
    user, err = await _check(request)
    if err: return err

    form = await request.form()
    old_pw = form.get("old_password", "")
    new_pw = form.get("new_password", "")
    success, message = await user_profile.change_password(
        user["username"], old_pw, new_pw
    )

    profile = await user_profile.get_user_profile(user["username"])
    return render("admin_profile.html", title="个人资料 - PyKYCH",
        current_user=user, profile=profile,
        error=None if success else message,
        success=message if success else None)


@admin_route.sub("/profile/avatar").post
async def upload_avatar_route(request: Request):
    """上传头像。"""
    user, err = await _check(request)
    if err: return err

    form = await request.form()
    uploaded = form.get("avatar")

    # 检查是否有文件上传（UploadFile 对象 vs 普通字符串）
    if uploaded is None:
        profile = await user_profile.get_user_profile(user["username"])
        return render("admin_profile.html", title="个人资料 - PyKYCH",
            current_user=user, profile=profile, error="请选择要上传的头像文件。")

    if not hasattr(uploaded, "filename"):
        profile = await user_profile.get_user_profile(user["username"])
        return render("admin_profile.html", title="个人资料 - PyKYCH",
            current_user=user, profile=profile, error="文件上传失败，请重试。")

    # 检查是否选择了文件（空文件名表示未选择）
    if not uploaded.filename:
        profile = await user_profile.get_user_profile(user["username"])
        return render("admin_profile.html", title="个人资料 - PyKYCH",
            current_user=user, profile=profile, error="请选择要上传的头像文件。")

    content = await uploaded.read()

    if len(content) == 0:
        profile = await user_profile.get_user_profile(user["username"])
        return render("admin_profile.html", title="个人资料 - PyKYCH",
            current_user=user, profile=profile, error="头像文件不能为空。")

    if len(content) > 2 * 1024 * 1024:  # 2MB 限制
        profile = await user_profile.get_user_profile(user["username"])
        return render("admin_profile.html", title="个人资料 - PyKYCH",
            current_user=user, profile=profile, error="头像文件不能超过 2MB。")

    result = await user_profile.save_avatar(
        user["username"], content, uploaded.filename or "avatar.png"
    )

    if result is None:
        profile = await user_profile.get_user_profile(user["username"])
        return render("admin_profile.html", title="个人资料 - PyKYCH",
            current_user=user, profile=profile,
            error="头像保存失败，请检查服务器磁盘空间和权限后重试。")

    return redirect("/admin/profile")


# ── 校验 ──

def _validate(title: str, slug: str, content: str, is_edit: bool = False) -> str | None:
    if not title: return "标题不能为空。"
    if not slug: return "Slug 不能为空。"
    if not slug.replace("-","").replace("_","").isalnum(): return "Slug 只能包含字母、数字、下划线和连字符。"
    if not content.strip(): return "内容不能为空。"
    return None

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

from .. import article_manager
from .. import auth as auth_mod
from .. import tag_manager
from .. import site_settings
from .. import notification_manager
from .. import external_html
from .. import file_manager
from .. import settings_manager
from .. import user_profile

# ── 模板 ──
TEMPLATE_DIR = Path(__file__).parent.parent / "templates"
jinja_env = Environment(loader=FileSystemLoader(str(TEMPLATE_DIR)), autoescape=True)

def render(template_name: str, status_code: int = 200, **context) -> HTMLResponse:
    template = jinja_env.get_template(template_name)
    return HTMLResponse(template.render(**context), status_code=status_code)

def redirect(url: str) -> RedirectResponse:
    return RedirectResponse(url, status_code=303)

# ── 登录保护 ──

async def _check(request: Request):
    """所有管理路由复用此检查。返回 (user, error_response)。"""
    user = await auth_mod.get_current_user(request)
    if user is None:
        target = quote(request.url.path, safe="")
        return None, redirect(f"/auth/login?next={target}")
    return user, None


async def _require_owner(request: Request):
    """要求站长权限。返回 (user, error_response)。"""
    user, err = await _check(request)
    if err:
        return None, err
    if not auth_mod.is_owner(user):
        return None, render("admin_dashboard.html", title="权限不足 - PyKYCH",
            current_user=user, md_articles=[], wk_pages=[],
            md_total=0, wk_total=0, users=[],
            permission_error="仅站长可执行此操作。")
    return user, None


def _can_edit(article: dict | None, user: dict) -> bool:
    """检查用户是否有权限编辑文章：管理员/站长可编辑所有，普通用户只能编辑自己的。"""
    if article is None:
        return False
    if auth_mod.is_admin(user):
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
    is_admin = auth_mod.is_admin(user)
    uid = user.get("id") if not is_admin else None

    articles_by_type = {}
    for atype in _ARTICLE_TYPES:
        result = await article_manager.list_articles(atype, page=1, per_page=100, author_id=uid)
        articles_by_type[atype] = result

    users = await auth_mod.list_users() if auth_mod.is_owner(user) else []
    subsite_links = await site_settings.list_subsite_links() if auth_mod.is_owner(user) else []
    featured_articles = await site_settings.list_featured_articles() if auth_mod.is_owner(user) else []
    tags = await tag_manager.get_all_tags_with_counts() if auth_mod.is_admin(user) else []
    notifications = await notification_manager.list_notifications(include_inactive=True) if auth_mod.is_admin(user) else []
    ext_sites = await external_html.list_external_sites() if auth_mod.is_admin(user) else []
    site_settings_data = settings_manager.load_settings() if auth_mod.is_owner(user) else {}

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

    result = await article_manager.update_article(article_type, slug, title, content)
    if result is None:
        return render("admin_form.html", title="编辑失败",
            form_title=cfg["form_title_edit"],
            action=f"/admin/{article_type}/{slug}/edit",
            article_type=article_type,
            article={"title": title, "slug": slug, "content": content},
            error=f"文章 '{slug}' 不存在。")

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
    if not auth_mod.is_admin(user):
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
    if not auth_mod.is_admin(user):
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
    if not auth_mod.is_admin(user):
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
    if not auth_mod.is_admin(user):
        return redirect("/admin")
    await tag_manager.delete_tag(tag_id)
    return redirect("/admin/tags")

# ===== 通知管理（管理员/站长） =====

@admin_route.sub("/notifications").get
async def manage_notifications(request: Request):
    """通知管理页面。"""
    user, err = await _check(request)
    if err: return err
    if not auth_mod.is_admin(user):
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
    if not auth_mod.is_admin(user):
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
    if not auth_mod.is_admin(user):
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
    if not auth_mod.is_admin(user):
        return redirect("/admin")
    await notification_manager.toggle_notification_importance(notif_id)
    return redirect("/admin/notifications")

@admin_route.sub("/notifications/{notif_id}/toggle-active").post
async def toggle_notification_active(notif_id: int, request: Request):
    """切换通知的启用/停用状态。"""
    user, err = await _check(request)
    if err: return err
    if not auth_mod.is_admin(user):
        return redirect("/admin")
    await notification_manager.toggle_notification_active(notif_id)
    return redirect("/admin/notifications")

@admin_route.sub("/notifications/{notif_id}/delete").post
async def delete_notification_route(notif_id: int, request: Request):
    """删除通知。"""
    user, err = await _check(request)
    if err: return err
    if not auth_mod.is_admin(user):
        return redirect("/admin")
    await notification_manager.delete_notification(notif_id)
    return redirect("/admin/notifications")

# ===== 外部站点管理（管理员/站长） =====

@admin_route.sub("/external").get
async def manage_external_sites(request: Request):
    """外部站点管理页面。"""
    user, err = await _check(request)
    if err: return err
    if not auth_mod.is_admin(user):
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
    if not auth_mod.is_admin(user):
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
    if not auth_mod.is_admin(user):
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
    """手动刷新外部站点缓存。"""
    user, err = await _check(request)
    if err: return err
    if not auth_mod.is_admin(user):
        return redirect("/admin")
    result = await external_html.fetch_and_cache_site(site_id)
    return redirect("/admin/external")

@admin_route.sub("/external/{site_id}/clear-cache").post
async def clear_external_cache(site_id: int, request: Request):
    """清除外部站点缓存。"""
    user, err = await _check(request)
    if err: return err
    if not auth_mod.is_admin(user):
        return redirect("/admin")
    await external_html.clear_site_cache(site_id)
    return redirect("/admin/external")

@admin_route.sub("/external/{site_id}/delete").post
async def delete_external_site(site_id: int, request: Request):
    """删除外部站点。"""
    user, err = await _check(request)
    if err: return err
    if not auth_mod.is_admin(user):
        return redirect("/admin")
    await external_html.delete_external_site(site_id)
    return redirect("/admin/external")

# ===== 静态文件管理（管理员/站长） =====

@admin_route.sub("/files").get
async def manage_files(request: Request, page: int = 1):
    """静态文件管理页面。"""
    user, err = await _check(request)
    if err: return err
    if not auth_mod.is_admin(user):
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
    if not auth_mod.is_admin(user):
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
    if not auth_mod.is_admin(user):
        return redirect("/admin")
    await file_manager.delete_file(file_id)
    return redirect("/admin/files")

# ===== 用户管理（仅站长） =====

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
        return redirect("/admin")
    if role not in ("user", "admin", "owner"):
        role = "user"

    try:
        existing = await auth_mod.get_user_by_username(username)
        if existing:
            return redirect("/admin")
        await auth_mod.create_user(username, password, nickname, role=role)
    except Exception:
        pass
    return redirect("/admin")

@admin_route.sub("/users/{username}/delete").post
async def delete_user(username: str, request: Request):
    """站长删除用户（不允许删除自己）。"""
    owner_user, err = await _require_owner(request)
    if err: return err
    if username == owner_user["username"]:
        return redirect("/admin")
    await auth_mod.delete_user(username)
    return redirect("/admin")

@admin_route.sub("/users/{username}/reset-password").post
async def reset_password(username: str, request: Request):
    """站长重置用户密码。"""
    owner_user, err = await _require_owner(request)
    if err: return err
    form = await request.form()
    new_password = form.get("new_password", "")
    if new_password:
        await auth_mod.update_user_password(username, new_password)
    return redirect("/admin")

@admin_route.sub("/users/{username}/role").post
async def change_role(username: str, request: Request):
    """站长修改用户角色。"""
    owner_user, err = await _require_owner(request)
    if err: return err
    if username == owner_user["username"]:
        return redirect("/admin")  # 不允许修改自己的角色
    form = await request.form()
    new_role = form.get("role", "user").strip()
    if new_role in ("user", "admin", "owner"):
        await auth_mod.update_user_role(username, new_role)
    return redirect("/admin")

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
    if not auth_mod.is_owner(user):
        return redirect("/admin")
    site_cfg = settings_manager.load_settings()
    return render("admin_settings.html", title="站点设置 - PyKYCH",
        current_user=user, settings=site_cfg, error=None)


@admin_route.sub("/settings/update").post
async def update_site_settings(request: Request):
    """更新站点设置。"""
    user, err = await _check(request)
    if err: return err
    if not auth_mod.is_owner(user):
        return redirect("/admin")

    form = await request.form()
    # 站点信息
    settings_manager.set_setting("site.title", form.get("site_title", "").strip())
    settings_manager.set_setting("site.subtitle", form.get("site_subtitle", "").strip())
    settings_manager.set_setting("site.description", form.get("site_description", "").strip())
    settings_manager.set_setting("site.logo_path", form.get("site_logo_path", "").strip())
    settings_manager.set_setting("site.icp_number", form.get("site_icp", "").strip())

    # 外观
    settings_manager.set_setting("appearance.theme", form.get("theme", "auto").strip())
    settings_manager.set_setting("appearance.primary_color", form.get("primary_color", "#3b82f6").strip())

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

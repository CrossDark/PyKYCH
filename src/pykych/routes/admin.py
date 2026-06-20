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
import asyncio
import logging
from contextvars import ContextVar

from ..content import articles as article_manager
from ..content import tags as tag_manager
from ..content import files as file_manager
from ..content import notifications as notification_manager
from ..auth import user as auth_user
from ..auth import session as auth_session
from ..auth import profile as user_profile
from ..core import settings as settings_manager
from ..core import site_settings
from ..themes_sys import manager as theme_manager
from ..plugins_sys.manager import get_all_plugins_info, install_plugin_from_zip
from ..plugins_sys.manager import (
    get_plugin_info, get_plugin_files, read_plugin_file,
    write_plugin_file, delete_plugin,
)

logger = logging.getLogger(__name__)

# ── 后台任务辅助 ──

def _create_background_task(coro, name: str = "unknown"):
    """
    安全创建后台异步任务，附带异常日志。

    与裸 asyncio.create_task() 不同，此函数会：
    1. 保存 Task 引用防止被 GC 回收
    2. 为任务添加异常回调，确保异常被记录到日志
    """
    task = asyncio.create_task(coro)
    def _log_exception(t: asyncio.Task):
        try:
            t.result()
        except Exception:
            logger.exception(f"后台任务 [{name}] 异常")
    task.add_done_callback(_log_exception)
    return task

# ── 模板 ──
TEMPLATE_DIR = Path(__file__).parent.parent / "templates"
jinja_env = Environment(loader=FileSystemLoader(str(TEMPLATE_DIR)), autoescape=True)

# 注入站点设置访问函数
from ..core.settings import get_setting, get_site_title, get_site_subtitle
jinja_env.globals["site_logo"] = lambda: get_setting("site.logo_path", "/static/img/logo.png")
jinja_env.globals["site_favicon"] = lambda: get_setting("site.favicon_path", "/static/img/favicon.ico")
jinja_env.globals["site_title_func"] = lambda: get_site_title()
jinja_env.globals["site_subtitle_func"] = lambda: get_site_subtitle()

# ── CSRF Token 上下文（async-safe，无需修改每个 render 调用） ──
_current_csrf: ContextVar[str] = ContextVar("csrf_token", default="")

def render(template_name: str, status_code: int = 200, **context) -> HTMLResponse:
    csrf = _current_csrf.get()
    if csrf:
        context.setdefault("csrf_token", csrf)
    template = jinja_env.get_template(template_name)
    return HTMLResponse(template.render(**context), status_code=status_code)

def redirect(url: str) -> RedirectResponse:
    return RedirectResponse(url, status_code=303)

# ── CSRF 验证 ──

def _verify_csrf(request: Request, form) -> bool:
    """
    验证 POST 请求的 CSRF Token。
    
    所有管理后台状态变更操作必须调用此函数。
    使用 session.py 中的恒定时间比较防止时序攻击。
    """
    csrf_token = form.get("csrf_token", "") if hasattr(form, "get") else ""
    return auth_session.verify_csrf_token(request, csrf_token)


def _csrf_error(request: Request, user: dict, error_msg: str = "CSRF 验证失败，请刷新页面后重试。") -> HTMLResponse:
    """返回 CSRF 验证失败的错误页面。"""
    return render("admin_dashboard.html", title="验证失败 - PyKYCH",
        current_user=user,
        md_total=0, wk_total=0, html_total=0, bb_total=0, typst_total=0,
        total_articles=0, users_count=0, tags_count=0,
        comments_count=0, files_count=0, notif_count=0,
        recent_articles=[], users=[],
        subsite_links=[], featured_articles=[],
        permission_error=error_msg)

# ── 登录保护 ──

async def _check(request: Request):
    """所有管理路由复用此检查。返回 (user, error_response)。POST 请求自动验证 CSRF。"""
    user = await auth_session.get_current_user(request)
    if user is None:
        target = quote(request.url.path, safe="")
        return None, redirect(f"/auth/login?next={target}")
    # 确保 avatar 有默认值（兼容 avatar 列不存在的情况）
    if not user.get("avatar"):
        user["avatar"] = user_profile.DEFAULT_AVATAR
    # 设置当前请求的 CSRF Token（供 render 自动注入）
    _current_csrf.set(auth_session.generate_csrf_token(request))
    # POST 请求自动验证 CSRF Token
    if request.method == "POST":
        form = await request.form()
        if not _verify_csrf(request, form):
            logger.warning(f"CSRF 验证失败: user={user.get('username')}, path={request.url.path}")
            return user, _csrf_error(request, user)
    return user, None


async def _require_owner(request: Request):
    """要求站长权限。返回 (user, error_response)。POST 请求自动验证 CSRF。"""
    user, err = await _check(request)
    if err:
        return None, err
    if not auth_user.is_owner(user):
        return None, render("admin_dashboard.html", title="权限不足 - PyKYCH",
            current_user=user,
            md_total=0, wk_total=0, html_total=0, bb_total=0, typst_total=0,
            total_articles=0, users_count=0, tags_count=0,
            comments_count=0, files_count=0, notif_count=0,
            recent_articles=[], users=[],
            subsite_links=[], featured_articles=[],
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
_ARTICLE_TYPES = ["md", "wikidot", "html", "bbcode", "typst"]


@admin_route.get
async def dashboard(request: Request):
    user, err = await _check(request)
    if err: return err

    # 管理员/站长看到所有文章，普通用户只看到自己的
    is_admin = auth_user.is_admin(user)
    uid = user.get("id") if not is_admin else None

    # 仅统计总数（不加载 content 字段）
    articles_by_type = {}
    total_articles_count = 0
    for atype in _ARTICLE_TYPES:
        result = await article_manager.list_articles(atype, page=1, per_page=1, author_id=uid)
        articles_by_type[atype] = result
        total_articles_count += result["total"]

    # 最近文章（跨类型）
    recent = await article_manager.list_recent_articles(limit=10, author_id=uid)

    # 站长专属数据
    users = []
    users_count = 0
    tags = []
    tags_count = 0
    comments_count = 0
    files_count = 0
    notif_count = 0
    subsite_links = []
    featured_articles = []
    site_settings_data = {}

    if auth_user.is_owner(user):
        users = await auth_user.list_users()
        users_count = len(users)
        subsite_links = await site_settings.list_subsite_links()
        featured_articles = await site_settings.list_featured_articles()
        site_settings_data = settings_manager.load_settings()
        tags_data = await tag_manager.get_all_tags_with_counts()
        tags = tags_data
        tags_count = len(tags_data)
        notifications = await notification_manager.list_notifications(include_inactive=True)
        notif_count = len(notifications) if notifications else 0
        files_result = await file_manager.list_files(page=1, per_page=1)
        files_count = files_result["total"] if files_result else 0
        # 评论总数
        try:
            from ..content import comments as comments_mgr
            comments_count = await comments_mgr.count_all_comments()
        except Exception:
            comments_count = 0
    elif auth_user.is_admin(user):
        tags_data = await tag_manager.get_all_tags_with_counts()
        tags = tags_data
        tags_count = len(tags_data)
        notifications = await notification_manager.list_notifications(include_inactive=True)
        notif_count = len(notifications) if notifications else 0

    return render("admin_dashboard.html", title="仪表盘 - PyKYCH",
        current_user=user,
        md_total=articles_by_type["md"]["total"],
        wk_total=articles_by_type["wikidot"]["total"],
        html_total=articles_by_type["html"]["total"],
        bb_total=articles_by_type["bbcode"]["total"],
        typst_total=articles_by_type["typst"]["total"],
        total_articles=total_articles_count,
        recent_articles=recent,
        users=users, users_count=users_count,
        tags=tags, tags_count=tags_count,
        comments_count=comments_count,
        files_count=files_count,
        notif_count=notif_count,
        subsite_links=subsite_links, featured_articles=featured_articles,
        site_settings=site_settings_data,
        permission_error=None)


# ===== 文章管理页面 =====

@admin_route.sub("/articles").get
async def articles_list(request: Request):
    """文章管理页面 — 列出所有类型文章。"""
    user, err = await _check(request)
    if err: return err

    is_admin = auth_user.is_admin(user)
    uid = user.get("id") if not is_admin else None

    articles_by_type = {}
    for atype in _ARTICLE_TYPES:
        result = await article_manager.list_articles(atype, page=1, per_page=20, author_id=uid)
        articles_by_type[atype] = result

    return render("admin_articles.html", title="文章管理 - PyKYCH",
        current_user=user,
        md_articles=articles_by_type["md"]["articles"],
        wk_pages=articles_by_type["wikidot"]["articles"],
        html_pages=articles_by_type["html"]["articles"],
        bb_pages=articles_by_type["bbcode"]["articles"],
        typst_articles=articles_by_type["typst"]["articles"],
        md_total=articles_by_type["md"]["total"],
        wk_total=articles_by_type["wikidot"]["total"],
        html_total=articles_by_type["html"]["total"],
        bb_total=articles_by_type["bbcode"]["total"],
        typst_total=articles_by_type["typst"]["total"],
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
    "typst": "Typst 文章",
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
        # Typst 文章：后台异步编译并缓存 HTML/PDF
        if article_type == "typst":
            from ..content.parsers.typst_parser import build_and_cache_typst
            _create_background_task(build_and_cache_typst(slug), name=f"typst-build-new-{slug}")
        return redirect("/admin/articles")
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
            # Typst 文章：后台异步编译并缓存 HTML/PDF
            if article_type == "typst":
                from ..content.parsers.typst_parser import build_and_cache_typst
                _create_background_task(build_and_cache_typst(slug), name=f"typst-build-edit-new-{slug}")
            return redirect("/admin/articles")
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
    # Typst 文章：后台异步编译并缓存 HTML/PDF
    if article_type == "typst":
        from ..content.parsers.typst_parser import build_and_cache_typst
        _create_background_task(build_and_cache_typst(slug), name=f"typst-build-edit-{slug}")
    return redirect("/admin/articles")


# ── 通用：删除文章 (POST) ──

async def _article_delete(article_type: str, slug: str, request: Request):
    user, err = await _check(request)
    if err: return err
    article = await article_manager.get_article(article_type, slug)
    if article is None:
        return redirect("/admin/articles")
    if not _can_edit(article, user):
        return redirect("/admin/articles")
    await article_manager.delete_article(article_type, slug)
    return redirect("/admin/articles")


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

# Typst
@admin_route.sub("/typst/new").get
async def typst_create_form(request: Request):
    return await _article_new_form("typst", request)

@admin_route.sub("/typst/new").post
async def typst_create(request: Request):
    return await _article_create("typst", request)

@admin_route.sub("/typst/{slug}/edit").get
async def typst_edit_form(slug: str, request: Request):
    return await _article_edit_form("typst", slug, request)

@admin_route.sub("/typst/{slug}/edit").post
async def typst_update(slug: str, request: Request):
    return await _article_update("typst", slug, request)

@admin_route.sub("/typst/{slug}/delete").post
async def typst_delete(slug: str, request: Request):
    return await _article_delete("typst", slug, request)

# ===== 标签管理（管理员/站长） =====

@admin_route.sub("/tags").get
async def manage_tags(request: Request):
    """标签管理页面 — 管理员和站长可以管理所有标签。"""
    user, err = await _check(request)
    if err: return err
    if not auth_user.is_admin(user):
        return render("admin_dashboard.html", title="权限不足 - PyKYCH",
            current_user=user,
            md_total=0, wk_total=0, html_total=0, bb_total=0, typst_total=0,
            total_articles=0, users_count=0, tags_count=0,
            comments_count=0, files_count=0, notif_count=0,
            recent_articles=[], users=[],
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
            current_user=user,
            md_total=0, wk_total=0,
            html_total=0, bb_total=0, typst_total=0,
            total_articles=0, users_count=0, tags_count=0,
            comments_count=0, files_count=0, notif_count=0,
            recent_articles=[], users=[],
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

# ===== 插件管理（管理员/站长） =====

@admin_route.sub("/plugins").get
async def manage_plugins(request: Request):
    """插件管理页面。"""
    user, err = await _check(request)
    if err: return err
    if not auth_user.is_admin(user):
        return render("admin_dashboard.html", title="权限不足 - PyKYCH",
            current_user=user,
            md_total=0, wk_total=0,
            html_total=0, bb_total=0, typst_total=0,
            total_articles=0, users_count=0, tags_count=0,
            comments_count=0, files_count=0, notif_count=0,
            recent_articles=[], users=[],
            subsite_links=[], featured_articles=[],
            permission_error="仅管理员和站长可管理插件。")
    plugins = get_all_plugins_info()
    return render("admin_plugins.html", title="插件管理 - PyKYCH",
        current_user=user, plugins=plugins)


@admin_route.sub("/plugins/upload").post
async def upload_plugin(request: Request):
    """上传并安装插件（zip 压缩包）。"""
    user, err = await _check(request)
    if err: return err
    if not auth_user.is_admin(user):
        return redirect("/admin")

    form = await request.form()
    uploaded = form.get("plugin_zip")

    if uploaded is None or not hasattr(uploaded, "filename"):
        plugins = get_all_plugins_info()
        return render("admin_plugins.html", title="插件管理 - PyKYCH",
            current_user=user, plugins=plugins,
            error="请选择要上传的插件 zip 文件。")

    # 检查文件扩展名
    if not uploaded.filename.lower().endswith(".zip"):
        plugins = get_all_plugins_info()
        return render("admin_plugins.html", title="插件管理 - PyKYCH",
            current_user=user, plugins=plugins,
            error="仅支持 .zip 格式的插件压缩包。")

    # 读取文件内容
    zip_data = await uploaded.read()
    if not zip_data:
        plugins = get_all_plugins_info()
        return render("admin_plugins.html", title="插件管理 - PyKYCH",
            current_user=user, plugins=plugins,
            error="上传的文件为空。")

    # 安装插件
    success, message = install_plugin_from_zip(zip_data)

    plugins = get_all_plugins_info()
    if success:
        return render("admin_plugins.html", title="插件管理 - PyKYCH",
            current_user=user, plugins=plugins,
            success=message)
    else:
        return render("admin_plugins.html", title="插件管理 - PyKYCH",
            current_user=user, plugins=plugins,
            error=message)


@admin_route.sub("/plugins/{plugin_name}").get
async def plugin_detail(plugin_name: str, request: Request):
    """插件详情页（含文件列表）。"""
    user, err = await _check(request)
    if err: return err
    if not auth_user.is_admin(user):
        return redirect("/admin")

    info = get_plugin_info(plugin_name)
    files = get_plugin_files(plugin_name)
    if not files and not info.get("loaded", False):
        # 插件不存在且未加载
        plugins = get_all_plugins_info()
        return render("admin_plugins.html", title="插件管理 - PyKYCH",
            current_user=user, plugins=plugins,
            error=f"插件 '{plugin_name}' 不存在。")

    return render("admin_plugin_detail.html", title=f"插件 {plugin_name} - PyKYCH",
        current_user=user, plugin=info, files=files)


@admin_route.sub("/plugins/{plugin_name}/edit/{file_path:path}").get
async def plugin_file_editor(plugin_name: str, file_path: str, request: Request):
    """插件文件编辑器页面。"""
    user, err = await _check(request)
    if err: return err
    if not auth_user.is_admin(user):
        return redirect("/admin")

    success, content = read_plugin_file(plugin_name, file_path)
    if not success:
        info = get_plugin_info(plugin_name)
        files = get_plugin_files(plugin_name)
        return render("admin_plugin_detail.html", title=f"插件 {plugin_name} - PyKYCH",
            current_user=user, plugin=info, files=files,
            error=content)

    info = get_plugin_info(plugin_name)
    return render("admin_plugin_editor.html", title=f"编辑 {file_path} - PyKYCH",
        current_user=user, plugin=info,
        file_path=file_path, file_content=content)


@admin_route.sub("/plugins/{plugin_name}/edit/{file_path:path}").post
async def plugin_file_save(plugin_name: str, file_path: str, request: Request):
    """保存插件文件。"""
    user, err = await _check(request)
    if err: return err
    if not auth_user.is_admin(user):
        return redirect("/admin")

    form = await request.form()
    new_content = form.get("content", "")

    success, message = write_plugin_file(plugin_name, file_path, new_content)

    info = get_plugin_info(plugin_name)
    if success:
        return render("admin_plugin_editor.html", title=f"编辑 {file_path} - PyKYCH",
            current_user=user, plugin=info,
            file_path=file_path, file_content=new_content,
            success=message)
    else:
        return render("admin_plugin_editor.html", title=f"编辑 {file_path} - PyKYCH",
            current_user=user, plugin=info,
            file_path=file_path, file_content=new_content,
            error=message)


@admin_route.sub("/plugins/{plugin_name}/delete").post
async def plugin_delete(plugin_name: str, request: Request):
    """删除插件。"""
    user, err = await _check(request)
    if err: return err
    if not auth_user.is_admin(user):
        return redirect("/admin")

    success, message = delete_plugin(plugin_name)
    plugins = get_all_plugins_info()
    if success:
        return render("admin_plugins.html", title="插件管理 - PyKYCH",
            current_user=user, plugins=plugins,
            success=message)
    else:
        return render("admin_plugins.html", title="插件管理 - PyKYCH",
            current_user=user, plugins=plugins,
            error=message)


# ===== 静态文件管理（管理员/站长） =====

@admin_route.sub("/files").get
async def manage_files(request: Request, page: int = 1):
    """静态文件管理页面。"""
    user, err = await _check(request)
    if err: return err
    if not auth_user.is_admin(user):
        return render("admin_dashboard.html", title="权限不足 - PyKYCH",
            current_user=user,
            md_total=0, wk_total=0,
            html_total=0, bb_total=0, typst_total=0,
            total_articles=0, users_count=0, tags_count=0,
            comments_count=0, files_count=0, notif_count=0,
            recent_articles=[], users=[],
            subsite_links=[], featured_articles=[],
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

    try:
        with open(file_path, "wb") as f:
            f.write(content)
    except (OSError, PermissionError) as e:
        logger.error(f"文件写入失败 {file_path}: {e}")
        result = await file_manager.list_files()
        return render("admin_files.html", title="文件管理 - PyKYCH",
            current_user=user, files=result["files"],
            page=1, total_pages=result["total_pages"],
            total=result["total"],
            error=f"文件保存失败：磁盘空间不足或权限不足。")

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

def _flash_get(request: Request, key: str) -> str:
    """读取一次性闪存消息（读取后自动清除）。"""
    session = request.session if hasattr(request, "session") else {}
    value = session.pop(key, "")
    return value if isinstance(value, str) else ""


def _flash_set(request: Request, key: str, value: str) -> None:
    """写入一次性闪存消息。"""
    if hasattr(request, "session"):
        request.session[key] = value


@admin_route.sub("/users").get
async def manage_users(request: Request):
    """用户管理页面 — 仅站长可访问。"""
    user, err = await _require_owner(request)
    if err: return err
    users = await auth_user.list_users()
    error = _flash_get(request, "_admin_error")
    success = _flash_get(request, "_admin_success")
    # 读取上次提交的表单值（出错时保留）
    form_username = _flash_get(request, "_form_username")
    form_nickname = _flash_get(request, "_form_nickname")
    form_role = _flash_get(request, "_form_role")
    return render("admin_users.html", title="用户管理 - PyKYCH",
        current_user=user, users=users, error=error, success=success,
        form_username=form_username, form_nickname=form_nickname,
        form_role=form_role)


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
        _flash_set(request, "_form_username", username)
        _flash_set(request, "_form_nickname", nickname)
        _flash_set(request, "_form_role", role if role in ("user", "admin", "owner") else "user")
        _flash_set(request, "_admin_error", "用户名和密码不能为空。")
        return redirect("/admin/users")
    if role not in ("user", "admin", "owner"):
        role = "user"

    try:
        existing = await auth_user.get_user_by_username(username)
        if existing:
            _flash_set(request, "_form_username", username)
            _flash_set(request, "_form_nickname", nickname)
            _flash_set(request, "_form_role", role)
            _flash_set(request, "_admin_error", f"用户名 «{username}» 已存在，请换一个。")
            return redirect("/admin/users")
        await auth_user.create_user(username, password, nickname, role=role)
        _flash_set(request, "_admin_success", f"用户 «{username}» 创建成功！")
    except ValueError as e:
        _flash_set(request, "_form_username", username)
        _flash_set(request, "_form_nickname", nickname)
        _flash_set(request, "_form_role", role if role in ("user", "admin", "owner") else "user")
        _flash_set(request, "_admin_error", str(e))
    except Exception as e:
        _flash_set(request, "_form_username", username)
        _flash_set(request, "_form_nickname", nickname)
        _flash_set(request, "_form_role", role if role in ("user", "admin", "owner") else "user")
        _flash_set(request, "_admin_error", f"创建用户失败: {e}")
    return redirect("/admin/users")

@admin_route.sub("/users/{username}/delete").post
async def delete_user(username: str, request: Request):
    """站长删除用户（不允许删除自己）。"""
    owner_user, err = await _require_owner(request)
    if err: return err
    if username == owner_user["username"]:
        _flash_set(request, "_admin_error", "不允许删除自己的账户。")
        return redirect("/admin/users")
    await auth_user.delete_user(username)
    _flash_set(request, "_admin_success", f"用户 «{username}» 已删除。")
    return redirect("/admin/users")

@admin_route.sub("/users/{username}/reset-password").post
async def reset_password(username: str, request: Request):
    """站长重置用户密码。"""
    owner_user, err = await _require_owner(request)
    if err: return err
    form = await request.form()
    new_password = form.get("new_password", "")
    if not new_password:
        _flash_set(request, "_admin_error", "新密码不能为空。")
    else:
        try:
            ok = await auth_user.update_user_password(username, new_password)
            if ok:
                _flash_set(request, "_admin_success", f"用户 «{username}» 的密码已重置。")
            else:
                _flash_set(request, "_admin_error", f"用户 «{username}» 不存在。")
        except ValueError as e:
            _flash_set(request, "_admin_error", f"密码重置失败: {e}")
        except Exception as e:
            _flash_set(request, "_admin_error", f"密码重置失败: {e}")
    return redirect("/admin/users")

@admin_route.sub("/users/{username}/role").post
async def change_role(username: str, request: Request):
    """站长修改用户角色。"""
    owner_user, err = await _require_owner(request)
    if err: return err
    if username == owner_user["username"]:
        _flash_set(request, "_admin_error", "不允许修改自己的角色。")
        return redirect("/admin/users")
    form = await request.form()
    new_role = form.get("role", "user").strip()
    if new_role in ("user", "admin", "owner"):
        await auth_user.update_user_role(username, new_role)
        _flash_set(request, "_admin_success", f"用户 «{username}» 的角色已更新为 {new_role}。")
    else:
        _flash_set(request, "_admin_error", f"无效的角色: {new_role}")
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
    try:
        posts_per_page = int(form.get("posts_per_page", "10"))
    except (ValueError, TypeError):
        posts_per_page = 10
    settings_manager.set_setting("features.posts_per_page", posts_per_page)

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
        import logging
        logger = logging.getLogger(__name__)
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

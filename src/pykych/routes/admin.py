"""
文章管理模块 — 创建、编辑、删除 Markdown 和 Wikidot 文章 + 用户管理。
路由前缀: /admin （全部需要登录）
"""

from lihil import Route, Request
from lihil import HTML
from starlette.responses import HTMLResponse, RedirectResponse
from pathlib import Path
from jinja2 import Environment, FileSystemLoader
from urllib.parse import quote

from .. import db
from .. import wikidot_db
from .. import auth as auth_mod

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

# ── 路由 ──

admin_route = Route("/admin")

# ===== 仪表盘 =====

@admin_route.get
async def dashboard(request: Request):
    user, err = await _check(request)
    if err: return err
    md_r = await db.list_articles(page=1, per_page=100)
    wk_r = await wikidot_db.list_pages(page=1, per_page=100)
    users = await auth_mod.list_users()
    return render("admin_dashboard.html", title="文章管理 - PyKYCH",
        current_user=user, md_articles=md_r["articles"], wk_pages=wk_r["pages"],
        md_total=md_r["total"], wk_total=wk_r["total"], users=users)

# ===== Markdown CRUD =====

@admin_route.sub("/md/new").get
async def md_create_form(request: Request):
    user, err = await _check(request)
    if err: return err
    return render("admin_form.html", title="新建 Markdown 文章 - PyKYCH",
        form_title="新建 Markdown 文章", action="/admin/md/new",
        article_type="md", article=None, error=None)

@admin_route.sub("/md/new").post
async def md_create(request: Request):
    user, err = await _check(request)
    if err: return err
    form = await request.form()
    title = form.get("title", "").strip()
    slug = form.get("slug", "").strip()
    content = form.get("content", "")
    error = _validate(title, slug, content)
    if error:
        return render("admin_form.html", title="新建 MD - PyKYCH",
            form_title="新建 Markdown 文章", action="/admin/md/new",
            article_type="md", article={"title":title,"slug":slug,"content":content}, error=error)
    try:
        await db.create_article(slug, title, content)
        return redirect("/admin")
    except Exception as e:
        return render("admin_form.html", title="新建 MD - PyKYCH",
            form_title="新建 Markdown 文章", action="/admin/md/new",
            article_type="md", article={"title":title,"slug":slug,"content":content}, error=f"创建失败: {e}")

@admin_route.sub("/md/{slug}/edit").get
async def md_edit_form(slug: str, request: Request):
    user, err = await _check(request)
    if err: return err
    article = await db.get_article_by_slug(slug)
    if not article:
        return render("admin_form.html", title="文章未找到", form_title="错误",
            action="", article_type="md", article=None, error=f"文章 '{slug}' 不存在。")
    return render("admin_form.html", title=f"编辑: {article['title']} - PyKYCH",
        form_title="编辑 Markdown 文章", action=f"/admin/md/{slug}/edit",
        article_type="md", article=article, error=None)

@admin_route.sub("/md/{slug}/edit").post
async def md_update(slug: str, request: Request):
    user, err = await _check(request)
    if err: return err
    form = await request.form()
    title = form.get("title", "").strip()
    content = form.get("content", "")
    error = _validate(title, slug, content, is_edit=True)
    if error:
        return render("admin_form.html", title=f"编辑: {title or slug} - PyKYCH",
            form_title="编辑 Markdown 文章", action=f"/admin/md/{slug}/edit",
            article_type="md", article={"title":title,"slug":slug,"content":content}, error=error)
    result = await db.update_article(slug, title, content)
    if result is None:
        return render("admin_form.html", title="编辑失败", form_title="编辑 Markdown 文章",
            action=f"/admin/md/{slug}/edit", article_type="md",
            article={"title":title,"slug":slug,"content":content}, error=f"文章 '{slug}' 不存在。")
    return redirect("/admin")

@admin_route.sub("/md/{slug}/delete").post
async def md_delete(slug: str, request: Request):
    user, err = await _check(request)
    if err: return err
    await db.delete_article(slug)
    return redirect("/admin")

# ===== Wikidot CRUD =====

@admin_route.sub("/wikidot/new").get
async def wk_create_form(request: Request):
    user, err = await _check(request)
    if err: return err
    return render("admin_form.html", title="新建 Wikidot 页面 - PyKYCH",
        form_title="新建 Wikidot 页面", action="/admin/wikidot/new",
        article_type="wikidot", article=None, error=None)

@admin_route.sub("/wikidot/new").post
async def wk_create(request: Request):
    user, err = await _check(request)
    if err: return err
    form = await request.form()
    title = form.get("title", "").strip()
    slug = form.get("slug", "").strip()
    content = form.get("content", "")
    error = _validate(title, slug, content)
    if error:
        return render("admin_form.html", title="新建 Wiki - PyKYCH",
            form_title="新建 Wikidot 页面", action="/admin/wikidot/new",
            article_type="wikidot", article={"title":title,"slug":slug,"content":content}, error=error)
    try:
        await wikidot_db.create_page(slug, title, content)
        return redirect("/admin")
    except Exception as e:
        return render("admin_form.html", title="新建 Wiki - PyKYCH",
            form_title="新建 Wikidot 页面", action="/admin/wikidot/new",
            article_type="wikidot", article={"title":title,"slug":slug,"content":content}, error=f"创建失败: {e}")

@admin_route.sub("/wikidot/{slug}/edit").get
async def wk_edit_form(slug: str, request: Request):
    user, err = await _check(request)
    if err: return err
    page = await wikidot_db.get_page_by_slug(slug)
    if not page:
        return render("admin_form.html", title="页面未找到", form_title="错误",
            action="", article_type="wikidot", article=None, error=f"页面 '{slug}' 不存在。")
    return render("admin_form.html", title=f"编辑: {page['title']} - PyKYCH",
        form_title="编辑 Wikidot 页面", action=f"/admin/wikidot/{slug}/edit",
        article_type="wikidot", article=page, error=None)

@admin_route.sub("/wikidot/{slug}/edit").post
async def wk_update(slug: str, request: Request):
    user, err = await _check(request)
    if err: return err
    form = await request.form()
    title = form.get("title", "").strip()
    content = form.get("content", "")
    error = _validate(title, slug, content, is_edit=True)
    if error:
        return render("admin_form.html", title=f"编辑: {title or slug} - PyKYCH",
            form_title="编辑 Wikidot 页面", action=f"/admin/wikidot/{slug}/edit",
            article_type="wikidot", article={"title":title,"slug":slug,"content":content}, error=error)
    result = await wikidot_db.update_page(slug, title, content)
    if result is None:
        return render("admin_form.html", title="编辑失败", form_title="编辑 Wikidot 页面",
            action=f"/admin/wikidot/{slug}/edit", article_type="wikidot",
            article={"title":title,"slug":slug,"content":content}, error=f"页面 '{slug}' 不存在。")
    return redirect("/admin")

@admin_route.sub("/wikidot/{slug}/delete").post
async def wk_delete(slug: str, request: Request):
    user, err = await _check(request)
    if err: return err
    await wikidot_db.delete_page(slug)
    return redirect("/admin")

# ===== 用户管理 =====

@admin_route.sub("/users/add").post
async def add_user(request: Request):
    """管理员添加新用户。"""
    user, err = await _check(request)
    if err: return err
    form = await request.form()
    username = form.get("username", "").strip()
    password = form.get("password", "")
    nickname = form.get("nickname", "").strip()

    if not username or not password:
        return redirect("/admin")

    try:
        existing = await auth_mod.get_user_by_username(username)
        if existing:
            return redirect("/admin")
        await auth_mod.create_user(username, password, nickname)
    except Exception:
        pass
    return redirect("/admin")

@admin_route.sub("/users/{username}/delete").post
async def delete_user(username: str, request: Request):
    """管理员删除用户（不允许删除自己）。"""
    admin_user, err = await _check(request)
    if err: return err
    if username == admin_user["username"]:
        return redirect("/admin")
    await auth_mod.delete_user(username)
    return redirect("/admin")

@admin_route.sub("/users/{username}/reset-password").post
async def reset_password(username: str, request: Request):
    """管理员重置用户密码。"""
    admin_user, err = await _check(request)
    if err: return err
    form = await request.form()
    new_password = form.get("new_password", "")
    if new_password:
        await auth_mod.update_user_password(username, new_password)
    return redirect("/admin")

# ── 校验 ──

def _validate(title: str, slug: str, content: str, is_edit: bool = False) -> str | None:
    if not title: return "标题不能为空。"
    if not slug: return "Slug 不能为空。"
    if not slug.replace("-","").replace("_","").isalnum(): return "Slug 只能包含字母、数字、下划线和连字符。"
    if not content.strip(): return "内容不能为空。"
    return None

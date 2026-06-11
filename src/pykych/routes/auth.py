"""
认证路由 — 登录 / 登出。
"""

from lihil import Route, Request
from starlette.responses import HTMLResponse, RedirectResponse
from pathlib import Path
from jinja2 import Environment, FileSystemLoader

from .. import auth as auth_mod

TEMPLATE_DIR = Path(__file__).parent.parent / "templates"
jinja_env = Environment(
    loader=FileSystemLoader(str(TEMPLATE_DIR)),
    autoescape=True,
)


def render(template_name: str, status_code: int = 200, **context) -> HTMLResponse:
    template = jinja_env.get_template(template_name)
    return HTMLResponse(template.render(**context), status_code=status_code)


def redirect(url: str) -> RedirectResponse:
    return RedirectResponse(url, status_code=303)


# ── 路由 ────────────────────────────────────────────────────

auth_route = Route("/auth")


@auth_route.sub("/login").get
async def login_form(request: Request):
    """登录页面。"""
    return render("login.html", title="登录 - PyKYCH", error=None)


@auth_route.sub("/login").post
async def login_action(request: Request):
    """处理登录请求。"""
    form = await request.form()
    username = form.get("username", "").strip()
    password = form.get("password", "")

    if not username or not password:
        return render("login.html", title="登录 - PyKYCH", error="用户名和密码不能为空。")

    user = await auth_mod.get_user_with_password(username)
    if not user or not auth_mod.verify_password(password, user["password_hash"]):
        return render("login.html", title="登录 - PyKYCH", error="用户名或密码错误。")

    auth_mod.login_user(request, username)

    next_url = request.query_params.get("next", "/admin")
    return redirect(next_url)


@auth_route.sub("/logout").get
async def logout(request: Request):
    """登出。"""
    auth_mod.logout_user(request)
    return redirect("/")

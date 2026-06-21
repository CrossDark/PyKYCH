"""
统一模板引擎 — 集中管理 Jinja2 模板环境和渲染函数。

所有路由模块通过导入此模块来复用同一个 jinja_env 实例，
避免在每个文件中重复创建 Environment、重复注入 globals。

用法:
    from pykych.core.templates import jinja_env, render_template

    # 直接使用 jinja_env 获取模板
    template = jinja_env.get_template("home.html")

    # 或使用便捷 render 函数
    return render_template("home.html", title="首页")
"""

from pathlib import Path
from jinja2 import Environment, FileSystemLoader
from starlette.responses import HTMLResponse

from .settings import get_setting, get_site_title, get_site_subtitle

# ── 模板目录 ────────────────────────────────────────────────
TEMPLATE_DIR = Path(__file__).parent.parent / "templates"

# ── 全局单例 jinja_env ─────────────────────────────────────
jinja_env = Environment(
    loader=FileSystemLoader(str(TEMPLATE_DIR)),
    autoescape=True,
)

# 注入站点设置访问函数，供所有模板使用
jinja_env.globals["site_logo"] = lambda: get_setting(
    "site.logo_path", "/static/img/logo.png"
)
jinja_env.globals["site_favicon"] = lambda: get_setting(
    "site.favicon_path", "/static/img/favicon.ico"
)
jinja_env.globals["site_title_func"] = lambda: get_site_title()
jinja_env.globals["site_subtitle_func"] = lambda: get_site_subtitle()


# ── 便捷渲染函数 ────────────────────────────────────────────

def render_template(
    template_name: str, status_code: int = 200, **context
) -> HTMLResponse:
    """渲染 Jinja2 模板并返回 HTML 响应。"""
    template = jinja_env.get_template(template_name)
    html = template.render(**context)
    return HTMLResponse(html, status_code=status_code)

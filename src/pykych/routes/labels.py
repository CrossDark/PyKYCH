"""
标签路由 — /labels/ 下的所有端点。
"""

from lihil import Route
from starlette.responses import HTMLResponse
from pathlib import Path
from jinja2 import Environment, FileSystemLoader

from ..content import tags as tm

# ── 模板 ────────────────────────────────────────────────────
TEMPLATE_DIR = Path(__file__).parent.parent / "templates"
jinja_env = Environment(
    loader=FileSystemLoader(str(TEMPLATE_DIR)),
    autoescape=True,
)

# 注入站点设置访问函数
from ..core.settings import get_setting, get_site_title, get_site_subtitle
jinja_env.globals["site_logo"] = lambda: get_setting("site.logo_path", "/static/img/logo.png")
jinja_env.globals["site_favicon"] = lambda: get_setting("site.favicon_path", "/static/img/favicon.ico")
jinja_env.globals["site_title_func"] = lambda: get_site_title()
jinja_env.globals["site_subtitle_func"] = lambda: get_site_subtitle()


def render(template_name: str, status_code: int = 200, **context) -> HTMLResponse:
    template = jinja_env.get_template(template_name)
    return HTMLResponse(template.render(**context), status_code=status_code)


# ── 路由 ────────────────────────────────────────────────────

labels_route = Route("/labels")


@labels_route.get
async def label_list():
    """标签列表页 — 展示所有标签及其文章数量（包含0篇的标签）。"""
    tags = await tm.get_all_tags_with_counts()

    return render(
        "labels.html",
        title="标签 - 跨越晨昏",
        tags=tags,
    )


@labels_route.sub("/{tag_name}").get
async def label_detail(tag_name: str, page: int = 1):
    """标签详情页 — 展示含有该标签的所有文章。"""
    result = await tm.get_articles_by_tag(tag_name, page=page, per_page=10)

    if result["tag"] is None:
        return render(
            "label_detail.html",
            title=f"标签不存在 - 跨越晨昏",
            status_code=404,
            tag=None,
            articles=[],
            page=1,
            total_pages=0,
            total=0,
        )

    return render(
        "label_detail.html",
        title=f"#{result['tag']['name']} - 跨越晨昏",
        tag=result["tag"],
        articles=result["articles"],
        page=result["page"],
        total_pages=result["total_pages"],
        total=result["total"],
    )

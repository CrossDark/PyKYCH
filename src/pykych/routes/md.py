"""
Markdown 文章路由 — /md/ 下的所有端点。
"""

from lihil import Route
from starlette.responses import HTMLResponse
from markdown import Markdown
from pathlib import Path
from jinja2 import Environment, FileSystemLoader

from lihil import Request

from ..content import articles as db
from ..content import tags as tag_manager
from ..content import comments as comment_manager
from ..content import comments as line_comment_manager
from ..content import ratings as rating_manager
from ..auth.session import get_current_user

# ── 模板引擎 ────────────────────────────────────────────────
TEMPLATE_DIR = Path(__file__).parent.parent / "templates"
jinja_env = Environment(
    loader=FileSystemLoader(str(TEMPLATE_DIR)),
    autoescape=True,
)


def render(template_name: str, status_code: int = 200, **context) -> HTMLResponse:
    template = jinja_env.get_template(template_name)
    return HTMLResponse(template.render(**context), status_code=status_code)


# ── Markdown 渲染器 ─────────────────────────────────────────
md_parser = Markdown(
    extensions=[
        "extra",          # 表格、围栏代码块、脚注等
        "fenced_code",    # ``` 围栏代码块
        "toc",            # [TOC] 生成目录
        "admonition",     # !!! note / !!! warning 提示框
        "sane_lists",     # 更合理的列表解析
    ],
    extension_configs={
        "fenced_code": {
            "lang_prefix": "language-",
        },
    },
    output_format="html5",
)


def render_markdown(md_text: str) -> str:
    """将 Markdown 文本渲染为 HTML。"""
    return md_parser.reset().convert(md_text)


# ── 路由 ────────────────────────────────────────────────────

md_route = Route("/md")


@md_route.get
async def md_article_list(page: int = 1):
    """Markdown 文章列表页。"""
    result = await db.list_articles('md', page=page, per_page=10)
    # 为每篇文章加载标签
    for article in result["articles"]:
        article["tags"] = await tag_manager.get_tags_for_article("md", article["slug"])
    return render(
        "md_list.html",
        title="Markdown 文章 - PyKYCH",
        articles=result["articles"],
        page=result["page"],
        total_pages=result["total_pages"],
        total=result["total"],
    )


@md_route.sub("/{slug}").get
async def md_article_detail(request: Request, slug: str):
    """Markdown 文章详情页。"""
    article = await db.get_article('md', slug)
    if not article:
        return render(
            "md_detail.html",
            title="文章未找到 - PyKYCH",
            status_code=404,
            article=None,
            html_content="<p>抱歉，您查找的文章不存在。</p>",
        )

    # 加载标签
    article["tags"] = await tag_manager.get_tags_for_article("md", slug)
    # 加载评论
    comments = await comment_manager.get_comments("md", slug)
    # 加载行评论
    line_comments = await line_comment_manager.get_line_comments("md", slug)
    line_comment_counts = await line_comment_manager.get_line_comment_counts("md", slug)
    # 加载评分
    rating = await rating_manager.get_article_rating("md", slug)
    # 获取当前用户
    current_user = await get_current_user(request)
    html_body = render_markdown(article["content"])
    return render(
        "md_detail.html",
        title=f"{article['title']} - PyKYCH",
        article=article,
        html_content=html_body,
        comments=comments,
        line_comments=line_comments,
        line_comment_counts=line_comment_counts,
        rating=rating,
        current_user=current_user,
    )

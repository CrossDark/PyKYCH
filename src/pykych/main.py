from lihil import Lihil, Route
from starlette.responses import HTMLResponse
from starlette.middleware.sessions import SessionMiddleware
from pathlib import Path
from contextlib import asynccontextmanager
from jinja2 import Environment, FileSystemLoader

from .routes import labels

from .mysql_manager import init_tables, close_pools, seed_admin

from . import article_manager
from . import site_settings
from . import notification_manager
from . import settings_manager
from . import user_profile
from . import plugin_manager
from . import theme_manager
from .routes import md
from .routes import wikidot
from .routes import admin
from .routes import auth
from .routes import labels
from .routes import html_route
from .routes import bbcode
from .routes import comments
from .routes import search

# ── 应用生命周期 ──────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app):
    """启动时建表并写入种子数据，关闭时释放连接池。"""
    await init_tables()
    # 使用统一文章管理器初始化种子数据
    for atype in ["md", "wikidot", "html", "bbcode"]:
        await article_manager.seed_db(atype)
    # 确保用户资料字段存在
    try:
        await user_profile.ensure_profile_columns()
    except Exception:
        pass  # 生产环境可能无 ALTER 权限
    
    # 加载所有插件
    try:
        plugin_manager.load_all_plugins()
        await plugin_manager.run_hook(plugin_manager.Hooks.ON_STARTUP)
    except Exception:
        pass

    # 创建默认管理员（如不存在）
    await seed_admin("admin", "admin123", "管理员")

    yield
    await plugin_manager.run_hook(plugin_manager.Hooks.ON_SHUTDOWN)
    await close_pools()

# ── 模板引擎 ──
TEMPLATE_DIR = Path(__file__).parent / "templates"

jinja_env = Environment(
    loader=FileSystemLoader(str(TEMPLATE_DIR)),
    autoescape=True,
)

# 创建 Lihil 应用
app = Lihil(lifespan=lifespan)

# Session 中间件（用于登录状态保持）
from starlette.middleware.sessions import SessionMiddleware
from functools import partial

app.add_middleware(
    partial(SessionMiddleware, secret_key="pykych-secret-change-in-production")
)


# 模板渲染辅助函数
def render_template(template_name: str, **context) -> HTMLResponse:
    """渲染 Jinja2 模板并返回 HTML 响应"""
    template = jinja_env.get_template(template_name)
    html = template.render(**context)
    return HTMLResponse(html)


# ===== 根路由：首页 =====
home_route = Route("/")

@home_route.get
async def home():
    """首页"""
    subsite_links = await site_settings.list_subsite_links()
    featured = await site_settings.list_featured_articles()
    important_notifications = await notification_manager.get_important_notifications()
    site_title = settings_manager.get_site_title()
    site_subtitle = settings_manager.get_site_subtitle()
    return render_template(
        "home.html",
        title=site_title,
        subtitle=site_subtitle,
        subsite_links=subsite_links,
        featured_articles=featured,
        important_notifications=important_notifications,
    )

# 将 home_route 包含进应用
app.include(home_route)

# ===== 关于页面 =====
@app.sub("/about").get
async def about():
    """关于页面"""
    return render_template(
        "page.html",
        title="关于我 - 跨越晨昏",
        content_heading="关于我",
        content_body="""<p>你好！我是跨越晨昏的作者，一名热爱编程和写作的开发者。</p>
        <p>这个网站使用 <strong>LiHiL</strong> 框架构建 —— 一个高性能、高产出的 Python ASGI Web 框架。</p>
        <p>我创建这个网站的目的是：</p>
        <ul>
            <li>记录学习心得和技术笔记</li>
            <li>分享 Python 和 Web 开发经验</li>
            <li>探索 LiHiL 框架的各种可能性</li>
        </ul>
        <p>如果你有任何建议或想交流技术，欢迎通过 GitHub 联系我。</p>""",
    )


# ===== 文章详情页 =====
@app.sub("/article/{slug}").get
async def article(slug: str):
    """文章详情页"""
    # 模拟文章数据
    articles_data = {
        "lihil-intro": {
            "title": "使用 LiHiL 构建高性能 Web 应用",
            "date": "2026-06-10",
            "body": """<h2>什么是 LiHiL？</h2>
            <p>LiHiL 是一个高性能的 Python ASGI Web 框架，相比其他框架快 50%-100%。它提供了依赖注入、插件系统、WebSocket 支持等企业级功能。</p>
            <h2>快速开始</h2>
            <p>安装非常简单：</p>
            <pre><code>pip install "lihil[standard]"</code></pre>
            <p>创建一个最简单的应用：</p>
            <pre><code>from lihil import Lihil

app = Lihil()

@app.sub("/").get
async def home():
    return {"message": "Hello, LiHiL!"}</code></pre>
            <p>然后使用 uvicorn 运行：</p>
            <pre><code>uvicorn main:app --reload</code></pre>
            <h2>核心特性</h2>
            <ul>
                <li><strong>路由系统</strong>：基于 Route 和 subroutes 的灵活路由</li>
                <li><strong>依赖注入</strong>：基于类型提示的自动注入</li>
                <li><strong>参数验证</strong>：自动解析和验证请求参数</li>
                <li><strong>插件系统</strong>：强大的中间件和插件架构</li>
                <li><strong>OpenAPI</strong>：自动生成 API 文档</li>
            </ul>
            <p>LiHiL 正在快速发展中，值得关注和尝试！</p>""",
            "back_link": "/",
            "back_text": "← 返回首页",
        },
        "python-async-guide": {
            "title": "Python 异步编程入门指南",
            "date": "2026-06-05",
            "body": """<h2>为什么需要异步编程？</h2>
            <p>在 Web 开发中，大量时间消耗在 I/O 操作上（数据库查询、API 调用、文件读写）。同步代码会在等待 I/O 时阻塞整个线程，而异步编程可以在等待时处理其他任务。</p>
            <h2>asyncio 基础</h2>
            <p>Python 的 asyncio 库提供了事件循环、协程和 Future 等核心概念：</p>
            <pre><code>import asyncio

async def fetch_data():
    await asyncio.sleep(1)
    return "data"

async def main():
    result = await fetch_data()
    print(result)

asyncio.run(main())</code></pre>
            <h2>在 LiHiL 中使用异步</h2>
            <p>LiHiL 天然支持异步处理，所有端点函数都可以是 async 的：</p>
            <pre><code>@app.sub("/data").get
async def get_data():
    data = await fetch_from_db()
    return {"data": data}</code></pre>
            <p>异步编程让 Web 应用能够高效处理大量并发请求，是现代 Web 框架的标配。</p>""",
            "back_link": "/",
            "back_text": "← 返回首页",
        },
        "why-python-web": {
            "title": "为什么选择 Python 做 Web 开发",
            "date": "2026-05-28",
            "body": """<h2>Python 的优势</h2>
            <p>Python 以其简洁优雅的语法和丰富的生态系统，成为 Web 开发的热门选择：</p>
            <ul>
                <li><strong>开发效率高</strong>：简洁的语法意味着更少的代码、更快的开发速度</li>
                <li><strong>生态丰富</strong>：拥有 Django、FastAPI、LiHiL 等优秀框架</li>
                <li><strong>AI/ML 集成</strong>：无缝对接 AI 模型和数据科学工具</li>
                <li><strong>社区活跃</strong>：庞大的开发者社区和丰富的学习资源</li>
            </ul>
            <h2>LiHiL 的愿景</h2>
            <p>LiHiL 的愿景是「让 Python 成为 Web 开发的主流语言」。通过提供高性能和高生产力的开发体验，LiHiL 正在为这一目标努力。</p>
            <p>Python 已经从脚本语言成长为全栈开发的有力竞争者。现在是时候用 Python 构建你的下一个 Web 项目了！</p>""",
            "back_link": "/",
            "back_text": "← 返回首页",
        },
    }

    article_data = articles_data.get(slug)
    if not article_data:
        return render_template(
            "page.html",
            title="文章未找到 - 跨越晨昏",
            content_heading="404 - 文章未找到",
            content_body="""<p>抱歉，您查找的文章不存在。</p>
            <p><a href="/" class="back-link">← 返回首页</a></p>""",
        )

    return render_template(
        "page.html",
        title=f"{article_data['title']} - 跨越晨昏",
        content_heading=article_data["title"],
        content_date=article_data["date"],
        content_body=article_data["body"],
        back_link=article_data["back_link"],
        back_text=article_data["back_text"],
    )


# ===== 健康检查 =====
@app.sub("/health").get
async def health():
    """健康检查接口"""
    return {"status": "healthy", "framework": "LiHiL", "app": "跨越晨昏"}


# ===== Markdown 文章路由 =====
app.include(md.md_route)

# ===== Wikidot 页面路由 =====
app.include(wikidot.wikidot_route)

# ===== HTML 页面路由 =====
app.include(html_route.html_route)

# ===== BBCode 页面路由 =====
app.include(bbcode.bbcode_route)
app.include(comments.comments_route)

# ===== 标签路由 =====
app.include(labels.labels_route)

# ===== 管理后台路由 =====
app.include(admin.admin_route)

# ===== 认证路由 (登录/登出) =====
app.include(auth.auth_route)

# ===== 搜索路由 =====
app.include(search.search_route)

# ===== 静态文件服务（上传目录） =====
from starlette.responses import FileResponse
from .file_manager import UPLOAD_DIR

uploads_route = Route("/static/uploads")

@uploads_route.sub("/{filename}").get
async def serve_upload(filename: str):
    """提供上传文件的访问。"""
    file_path = UPLOAD_DIR / filename
    if not file_path.exists() or not file_path.is_file():
        return HTMLResponse("<p>文件不存在</p>", status_code=404)
    return FileResponse(str(file_path))

app.include(uploads_route)

# ===== 头像静态文件服务 =====
from .user_profile import AVATAR_DIR

# 兼容旧头像路径
from pathlib import Path as _Path
_OLD_AVATAR_DIR = _Path(__file__).parent / "static" / "avatars"

avatar_route = Route("/static/avatars")

@avatar_route.sub("/{filename}").get
async def serve_avatar(filename: str):
    """提供头像文件的访问。"""
    file_path = AVATAR_DIR / filename
    if not file_path.exists() or not file_path.is_file():
        # 兼容旧头像路径
        old_path = _OLD_AVATAR_DIR / filename
        if old_path.exists() and old_path.is_file():
            return FileResponse(str(old_path))
        return HTMLResponse("<p>头像不存在</p>", status_code=404)
    return FileResponse(str(file_path))

app.include(avatar_route)

# ===== 主题 CSS 路由 =====
@app.sub("/theme.css").get
async def theme_css():
    """提供当前主题的自定义 CSS。"""
    from starlette.responses import Response
    css = theme_manager.get_theme_css()
    return Response(css, media_type="text/css")

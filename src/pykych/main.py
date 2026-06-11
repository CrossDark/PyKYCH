from lihil import Lihil, Route
from starlette.responses import HTMLResponse
from pathlib import Path
from jinja2 import Environment, FileSystemLoader

# 模板引擎配置
TEMPLATE_DIR = Path(__file__).parent / "templates"

jinja_env = Environment(
    loader=FileSystemLoader(str(TEMPLATE_DIR)),
    autoescape=True,
)

# 创建 Lihil 应用
app = Lihil()


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
    return render_template(
        "home.html",
        title="PyKYCH - 首页",
        subtitle="欢迎来到我的个人网站",
        articles=[
            {
                "title": "使用 LiHiL 构建高性能 Web 应用",
                "date": "2026-06-10",
                "summary": "LiHiL 是一个 2 倍速的 Python ASGI Web 框架，本文将介绍如何使用它快速构建高性能 Web 应用。",
                "slug": "lihil-intro",
            },
            {
                "title": "Python 异步编程入门指南",
                "date": "2026-06-05",
                "summary": "异步编程是现代 Web 开发的核心技能。本文从基础概念讲起，带你逐步掌握 Python asyncio。",
                "slug": "python-async-guide",
            },
            {
                "title": "为什么选择 Python 做 Web 开发",
                "date": "2026-05-28",
                "summary": "Python 拥有丰富的生态系统和简洁的语法，是 Web 开发的绝佳选择。本文分享我的实践经验。",
                "slug": "why-python-web",
            },
        ],
    )

# 将 home_route 包含进应用
app.include(home_route)

# ===== 关于页面 =====
@app.sub("/about").get
async def about():
    """关于页面"""
    return render_template(
        "page.html",
        title="关于我 - PyKYCH",
        content_heading="关于我",
        content_body="""<p>你好！我是 PyKYCH 的作者，一名热爱编程和写作的开发者。</p>
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
            title="文章未找到 - PyKYCH",
            content_heading="404 - 文章未找到",
            content_body="""<p>抱歉，您查找的文章不存在。</p>
            <p><a href="/" class="back-link">← 返回首页</a></p>""",
        )

    return render_template(
        "page.html",
        title=f"{article_data['title']} - PyKYCH",
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
    return {"status": "healthy", "framework": "LiHiL", "app": "PyKYCH"}

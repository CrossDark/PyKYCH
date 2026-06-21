"""
PyKYCH 主应用入口 — 「跨越晨昏」个人网站后端。

模块结构 (v2.0 重构):
    core/           核心基础设施（数据库、设置）
    auth/           认证系统（密码、会话、速率限制、通行密钥）
    content/        内容管理（文章、标签、评论、评分、文件）
    routes/         HTTP 路由层
    plugins_sys/    插件系统
    themes_sys/     主题系统

安全性改进 (v2.0):
    - 登录速率限制（防暴力破解）
    - CSRF 保护
    - 会话固定攻击防护
    - CAPTCHA 绕过漏洞修复
    - 密码强度校验
    - 恒定时间比较（防时序攻击）
"""

import os
import sys
import asyncio
import logging
from lihil import Lihil, Route, Request

# ── 日志配置 ────────────────────────────────────────────────
# 支持结构化日志输出（JSON 格式），方便日志收集系统（如 ELK、Loki）解析
_log_format = os.environ.get("PYKYCH_LOG_FORMAT", "text")
if _log_format == "json":
    # JSON 格式：适合生产环境的日志收集系统
    logging.basicConfig(
        level=getattr(logging, os.environ.get("PYKYCH_LOG_LEVEL", "INFO").upper(), logging.INFO),
        format='{"time":"%(asctime)s","level":"%(levelname)s","module":"%(name)s","message":"%(message)s"}',
        datefmt="%Y-%m-%dT%H:%M:%S",
        stream=sys.stderr,
    )
else:
    # 文本格式：适合开发环境阅读
    logging.basicConfig(
        level=getattr(logging, os.environ.get("PYKYCH_LOG_LEVEL", "INFO").upper(), logging.INFO),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        stream=sys.stderr,
    )
from starlette.responses import HTMLResponse, JSONResponse
from starlette.middleware.sessions import SessionMiddleware
from functools import partial
from pathlib import Path
from contextlib import asynccontextmanager
from .core.schema import init_tables, seed_admin
from .core.db import close_pools
from .core.settings import get_site_title, get_site_subtitle, get_setting
from .core.templates import jinja_env, render_template

from .content.articles import seed_db
from .content.tags import auto_tag_article

from .auth import profile as user_profile

from .plugins_sys.manager import load_all_plugins, run_hook, Hooks
from .themes_sys.manager import set_active_theme

from .core import site_settings
from .content import notifications as notification_manager

from .routes import (
    md, wikidot, admin, auth, labels,
    html_route, bbcode, comments, search,
    typst_route, api,
)

logger = logging.getLogger(__name__)

# ── 应用生命周期 ──────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app):
    """启动时建表并写入种子数据，关闭时释放连接池。"""
    await init_tables()
    # 使用统一文章管理器初始化种子数据
    for atype in ["md", "wikidot", "html", "bbcode", "typst"]:
        await seed_db(atype)
    # 清理可能的孤立标签关联（修复旧版本遗留数据）
    try:
        from .content.tags import cleanup_orphan_article_tags, cleanup_orphan_tags
        await cleanup_orphan_article_tags()
        await cleanup_orphan_tags()
    except Exception:
        pass
    # 确保用户资料字段存在
    try:
        await user_profile.ensure_profile_columns()
    except Exception:
        pass  # 生产环境可能无 ALTER 权限

    # 加载所有插件
    try:
        load_all_plugins()
        await run_hook(Hooks.ON_STARTUP)
    except Exception:
        pass

    # 创建默认管理员（如不存在）
    # ⚠️ 安全警告：生产环境请在首次登录后立即修改默认密码！
    await seed_admin("admin", "admin123", "管理员")
    logger.warning(
        "⚠️  默认管理员账户为 admin/admin123。"
        "如果这是首次启动，请立即登录并修改密码！"
    )

    # 确保头像目录存在并记录路径
    try:
        user_profile._ensure_avatar_dir()
        logger.info(f"头像目录: {user_profile.AVATAR_DIR} (URL前缀: {user_profile.AVATAR_URL_PREFIX})")
    except Exception:
        pass

    # 加载样式主题
    try:
        style_theme = get_setting("appearance.style_theme", "default")
        if style_theme and style_theme != "default":
            set_active_theme(style_theme)
    except Exception:
        pass

    yield
    await run_hook(Hooks.ON_SHUTDOWN)
    await close_pools()

# 创建 Lihil 应用
app = Lihil(lifespan=lifespan)

# Session 中间件（用于登录状态保持）
# 密钥优先使用环境变量，fallback 到默认值（生产环境务必设置环境变量！）
_SECRET_KEY = os.environ.get(
    "PYKYCH_SECRET_KEY",
    "pykych-secret-change-in-production"
)

# 安全警告：默认密钥
if _SECRET_KEY == "pykych-secret-change-in-production":
    logger.warning(
        "⚠️  安全警告: 使用了默认的 Session 密钥！\n"
        "   请设置 PYKYCH_SECRET_KEY 环境变量以保护会话安全。\n"
        "   攻击者可以使用此默认密钥伪造 Session Cookie。"
    )

# 生产环境下启用 Secure Cookie（HTTPS only）
# 可通过 PYKYCH_SECURE_COOKIE 环境变量显式控制:
#   - "true" / "1": 强制启用（仅 HTTPS 传输 Cookie）
#   - "false" / "0": 强制禁用（开发环境）
#   - 未设置: 自动检测（非 localhost/127.0.0.1 时启用）
_secure_cookie_env = os.environ.get("PYKYCH_SECURE_COOKIE", "").lower()
if _secure_cookie_env in ("true", "1"):
    _https_only = True
elif _secure_cookie_env in ("false", "0"):
    _https_only = False
else:
    # 自动检测：非本地地址默认启用 Secure Cookie
    _host = os.environ.get("PYKYCH_HOST", os.environ.get("HOST", "127.0.0.1"))
    _https_only = _host not in ("127.0.0.1", "localhost", "0.0.0.0")

app.add_middleware(
    partial(SessionMiddleware, secret_key=_SECRET_KEY, https_only=_https_only)
)
if _https_only:
    logger.info("🔒 Session Cookie Secure 标志已启用（仅 HTTPS 传输）")



home_route = Route("/")

@home_route.get
async def home():
    """首页 — 并行加载不依赖的查询以提升响应速度。"""
    subsite_links, featured, important_notifications = await asyncio.gather(
        site_settings.list_subsite_links(),
        site_settings.list_featured_articles(),
        notification_manager.get_important_notifications(),
    )
    site_title = get_site_title()
    site_subtitle = get_site_subtitle()
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


# ===== 健康检查 =====
@app.sub("/health").get
async def health():
    """健康检查接口（含数据库连接验证）。"""
    db_ok = False
    try:
        from .core.db import _get_pool
        pool = await _get_pool()
        async with pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute("SELECT 1")
                db_ok = True
    except Exception:
        pass

    status_code = 200 if db_ok else 503
    return JSONResponse({
        "status": "healthy" if db_ok else "degraded",
        "framework": "LiHiL",
        "app": "跨越晨昏",
        "database": "connected" if db_ok else "disconnected",
    }, status_code=status_code)


# ===== Markdown 文章路由 =====
app.include(md.md_route)

# ===== Wikidot 页面路由 =====
app.include(wikidot.wikidot_route)

# ===== HTML 页面路由 =====
app.include(html_route.html_route)

# ===== BBCode 页面路由 =====
app.include(bbcode.bbcode_route)
app.include(comments.comments_route)

# ===== Typst 页面路由 =====
app.include(typst_route.typst_route)

# ===== 标签路由 =====
app.include(labels.labels_route)

# ===== 管理后台路由 =====
app.include(admin.admin_route)

# ===== 认证路由 (登录/登出) =====
app.include(auth.auth_route)

# ===== API 路由（当前用户、行评论、评分） =====
app.include(api.user_api)
app.include(api.line_comments_api)
app.include(api.ratings_api)

# ===== 搜索路由 =====
app.include(search.search_route)

# ===== 静态文件服务（上传目录） =====
from starlette.responses import FileResponse
from .content.files import UPLOAD_DIR

# 静态资源缓存配置（默认缓存 1 小时，可通过环境变量调整）
_STATIC_CACHE_SECONDS = int(os.environ.get("PYKYCH_STATIC_CACHE_SECONDS", "3600"))
_STATIC_CACHE_HEADER = f"public, max-age={_STATIC_CACHE_SECONDS}"


def _cached_file_response(file_path: str) -> FileResponse:
    """返回带缓存头的 FileResponse。"""
    return FileResponse(
        file_path,
        headers={"Cache-Control": _STATIC_CACHE_HEADER},
    )

uploads_route = Route("/static/uploads")

def _is_safe_filename(filename: str) -> bool:
    """检查文件名是否安全（防止路径遍历攻击）。"""
    if not filename:
        return False
    # 拒绝包含路径分隔符或 .. 的文件名
    if "/" in filename or "\\" in filename or ".." in filename:
        return False
    return True

def _safe_resolve(base_dir: Path, filename: str) -> Path | None:
    """安全解析文件路径，确保结果在 base_dir 内。"""
    if not _is_safe_filename(filename):
        return None
    resolved = (base_dir / filename).resolve()
    base_resolved = base_dir.resolve()
    if not str(resolved).startswith(str(base_resolved) + os.sep) and resolved != base_resolved:
        return None
    return resolved

@uploads_route.sub("/{filename}").get
async def serve_upload(filename: str):
    """提供上传文件的访问。"""
    file_path = _safe_resolve(UPLOAD_DIR, filename)
    if file_path is None or not file_path.exists() or not file_path.is_file():
        return HTMLResponse("<p>文件不存在</p>", status_code=404)
    return _cached_file_response(str(file_path))

app.include(uploads_route)

# ===== 站点图片静态文件服务（Logo、Favicon） =====
STATIC_IMG_DIR = Path(__file__).parent / "static" / "img"

static_img_route = Route("/static/img")

@static_img_route.sub("/{filename}").get
async def serve_static_img(filename: str):
    """提供站点图片（Logo、Favicon 等）的访问。"""
    file_path = _safe_resolve(STATIC_IMG_DIR, filename)
    if file_path is None or not file_path.exists() or not file_path.is_file():
        return HTMLResponse("<p>图片不存在</p>", status_code=404)
    return _cached_file_response(str(file_path))

app.include(static_img_route)

# ===== 头像静态文件服务 =====
from .auth.profile import AVATAR_DIR, AVATAR_URL_PREFIX, OLD_AVATAR_URL_PREFIX

# 兼容旧头像路径
from pathlib import Path as _Path
_OLD_AVATAR_DIR = _Path(__file__).parent / "static" / "avatars"

# ── 新头像路由（/avatars/）─ 避免被生产环境反向代理的 /static/ 规则拦截 ──
avatar_route = Route(AVATAR_URL_PREFIX)

@avatar_route.sub("/{filename}").get
@avatar_route.sub("/{filename}").head
async def serve_avatar(filename: str):
    """提供头像文件的访问（新路由）。"""
    file_path = _safe_resolve(AVATAR_DIR, filename)
    if file_path is not None and file_path.exists() and file_path.is_file():
        return _cached_file_response(str(file_path))
    # 兼容旧头像路径
    old_path = _safe_resolve(_OLD_AVATAR_DIR, filename)
    if old_path is not None and old_path.exists() and old_path.is_file():
        return _cached_file_response(str(old_path))
    logger.warning(f"头像文件未找到: {filename} (AVATAR_DIR={AVATAR_DIR})")
    return HTMLResponse("<p>头像不存在</p>", status_code=404)

app.include(avatar_route)

# ── 旧头像路由（/static/avatars/）─ 向后兼容已上传的头像 ──
old_avatar_route = Route(OLD_AVATAR_URL_PREFIX)

@old_avatar_route.sub("/{filename}").get
@old_avatar_route.sub("/{filename}").head
async def serve_old_avatar(filename: str):
    """提供头像文件的访问（旧路由，向后兼容）。"""
    file_path = _safe_resolve(AVATAR_DIR, filename)
    if file_path is not None and file_path.exists() and file_path.is_file():
        return _cached_file_response(str(file_path))
    # 兼容旧头像路径
    old_path = _safe_resolve(_OLD_AVATAR_DIR, filename)
    if old_path is not None and old_path.exists() and old_path.is_file():
        return _cached_file_response(str(old_path))
    logger.warning(f"头像文件未找到(旧路由): {filename} (AVATAR_DIR={AVATAR_DIR})")
    return HTMLResponse("<p>头像不存在</p>", status_code=404)

app.include(old_avatar_route)

# ===== 主题 CSS 路由 =====
@app.sub("/theme.css").get
async def theme_css():
    """提供当前主题的自定义 CSS。"""
    from starlette.responses import Response
    from .themes_sys.manager import get_theme_css
    css = get_theme_css()
    return Response(css, media_type="text/css")


# ===== 开发/生产启动入口 =====
if __name__ == "__main__":
    import uvicorn
    import os

    host = os.environ.get("PYKYCH_HOST", os.environ.get("HOST", "0.0.0.0"))
    port = int(os.environ.get("PYKYCH_PORT", os.environ.get("PORT", "8000")))
    reload = os.environ.get("PYKYCH_RELOAD", "").lower() in ("true", "1", "yes")

    uvicorn.run(
        "src.pykych.main:app",
        host=host,
        port=port,
        reload=reload,
        log_level="info",
    )

"""
Typst 解析器 — 将 Typst 标记语言编译为 HTML / PDF。

此模块通过调用系统安装的 `typst` CLI 完成编译。
编译在临时目录中进行，以支持 Typst 的文件导入机制。

Typst 项目结构（参考 tufted）:
    content/               ← 文章内容目录
      blog/
        2024-10-04-xxx/
          index.typ         ← 文章主文件
          imgs/             ← 文章图片
      index.typ             ← 索引/目录页
    config.typ              ← 共享配置（模板、样式）

对于 PyKYCH，每篇 Typst 文章存储方式:
    - typst_pages.content:  文章主体 .typ 源码
    - typst_files:          文章的辅助文件（导入的模块、图片引用等）

用法:
    from pykych.content.parsers.typst_parser import (
        compile_typst_to_html,
        compile_typst_to_pdf,
        check_typst_available,
    )
"""

import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Optional


# ═══════════════════════════════════════════════════════════════
#  Typst CLI 检测
# ═══════════════════════════════════════════════════════════════

_typst_available: bool | None = None

# typst 可执行文件的常见安装路径（按优先级排序）
_TYPST_COMMON_PATHS = [
    # 通过环境变量指定
    lambda: os.environ.get("TYPST_PATH", ""),
    # 通过 PATH 查找
    lambda: shutil.which("typst") or "",
    # 常见固定路径
    lambda: _find_typst_in_common_dirs(),
]


def _find_typst_in_common_dirs() -> str:
    """在常见安装目录中查找 typst 可执行文件。"""
    candidates = [
        # macOS Homebrew (Apple Silicon / Intel)
        "/opt/homebrew/bin/typst",
        "/usr/local/bin/typst",
        # Linux 系统级安装
        "/usr/bin/typst",
        # Snap 安装 (Ubuntu)
        "/snap/bin/typst",
        # cargo 安装
        os.path.expanduser("~/.cargo/bin/typst"),
    ]
    for path in candidates:
        if os.path.isfile(path) and os.access(path, os.X_OK):
            return path
    return ""


def _resolve_typst_path() -> str:
    """
    按优先级查找 typst 可执行文件路径。
    返回找到的路径，或空字符串。
    """
    for getter in _TYPST_COMMON_PATHS:
        path = getter()
        if path and os.path.isfile(path) and os.access(path, os.X_OK):
            return path
    return ""


# 缓存解析后的 typst 路径
_typst_path: str | None = None


def get_typst_path() -> str:
    """
    获取 typst 可执行文件的路径。
    按以下优先级查找:
        1. 环境变量 TYPST_PATH
        2. PATH 中的 typst
        3. 常见安装目录
    结果会被缓存。
    """
    global _typst_path
    if _typst_path is None:
        _typst_path = _resolve_typst_path()
    return _typst_path


def check_typst_available() -> bool:
    """
    检测系统中是否安装了 typst CLI。

    返回:
        True 如果 typst 可用，False 否则。

    副作用:
        缓存检测结果，避免重复调用。
    """
    global _typst_available
    if _typst_available is not None:
        return _typst_available
    _typst_available = bool(get_typst_path())
    return _typst_available


def clear_typst_cache() -> None:
    """清除 typst 检测缓存（安装 typst 后调用）。"""
    global _typst_available, _typst_path
    _typst_available = None
    _typst_path = None


# ═══════════════════════════════════════════════════════════════
#  路径解析 — 处理 Typst 的 import 引用
# ═══════════════════════════════════════════════════════════════

# Typst import 语法:
#   #import "file.typ"          — 相对路径导入
#   #import "dir/file.typ"      — 子目录导入
#   #import "../config.typ"     — 父目录导入
#   #include "file.typ"         — 直接包含
#   image("imgs/photo.png")     — 图片引用
#   #import "@preview/pkg:ver"  — 包导入（需要网络，由 typst 自行处理）

_IMPORT_RE = re.compile(
    r'#(?:import|include)\s*"([^"]+\.typ)"'
)

_IMAGE_RE = re.compile(
    r'image\s*\(\s*"([^"]+\.(?:png|jpg|jpeg|gif|svg|webp))"'
)


def extract_local_imports(source: str) -> list[str]:
    """
    从 Typst 源码中提取所有本地文件引用路径。

    返回:
        去重后的相对路径列表（如 'config.typ', 'lib/utils.typ'）
    """
    imports = set()
    for m in _IMPORT_RE.finditer(source):
        path = m.group(1)
        # 跳过包导入（以 @ 开头）
        if not path.startswith("@"):
            imports.add(path)
    return sorted(imports)


def extract_image_refs(source: str) -> list[str]:
    """
    从 Typst 源码中提取所有图片引用路径。

    返回:
        去重后的图片路径列表
    """
    refs = set()
    for m in _IMAGE_RE.finditer(source):
        refs.add(m.group(1))
    return sorted(refs)


# ═══════════════════════════════════════════════════════════════
#  编译核心
# ═══════════════════════════════════════════════════════════════

# Typst 编译超时（秒）
_COMPILE_TIMEOUT = 60

# 默认共享配置文件路径（存放在 data/typst/ 下）
_SHARED_CONFIG_DIR = Path(__file__).parent.parent.parent.parent.parent / "data" / "typst"
_SHARED_CONFIG_FILE = _SHARED_CONFIG_DIR / "config.typ"


def _get_shared_config() -> Optional[str]:
    """
    读取共享 Typst 配置文件。

    返回:
        config.typ 的内容，或 None（文件不存在时）
    """
    if _SHARED_CONFIG_FILE.exists():
        return _SHARED_CONFIG_FILE.read_text(encoding="utf-8")
    return None


async def _get_aux_files(slug: str) -> list[dict]:
    """
    从数据库获取文章关联的辅助 Typst 文件。

    参数:
        slug: 文章 slug

    返回:
        文件列表 [{"filename": ..., "content": ...}, ...]
    """
    from ...core.db import _get_pool, row_to_dict

    try:
        pool = await _get_pool()
        async with pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    "SELECT tf.filename, tf.content "
                    "FROM typst_files tf "
                    "JOIN typst_pages tp ON tf.page_id = tp.id "
                    "WHERE tp.slug = %s",
                    (slug,),
                )
                rows = await cur.fetchall()
                return [row_to_dict(r, cur) for r in rows]
    except Exception:
        return []


def _write_workspace(
    workspace_dir: Path,
    main_source: str,
    aux_files: list[dict] | None = None,
    shared_config: str | None = None,
) -> Path:
    """
    在临时目录中构建 Typst 工作区。

    结构:
        workspace/
          index.typ          ← 主文件（文章内容）
          config.typ          ← 共享配置（可选）
          <aux files...>      ← 辅助文件（按原文件名）

    返回:
        index.typ 的路径
    """
    # 写入主文件
    main_path = workspace_dir / "index.typ"
    main_path.write_text(main_source, encoding="utf-8")

    # 写入共享配置
    if shared_config:
        config_path = workspace_dir / "config.typ"
        config_path.write_text(shared_config, encoding="utf-8")

    # 写入辅助文件（保持相对路径结构）
    if aux_files:
        for f in aux_files:
            fname = f.get("filename", "")
            content = f.get("content", "")
            if not fname:
                continue
            # 安全检查：防止路径遍历攻击
            safe_name = os.path.normpath(fname)
            if safe_name.startswith("..") or os.path.isabs(safe_name):
                continue
            file_path = workspace_dir / safe_name
            file_path.parent.mkdir(parents=True, exist_ok=True)
            file_path.write_text(content, encoding="utf-8")

    return main_path


async def compile_typst_to_html(
    source: str,
    slug: str = "",
    aux_files: list[dict] | None = None,
) -> tuple[str, Optional[str]]:
    """
    将 Typst 源码编译为 HTML。

    参数:
        source:    Typst 源码
        slug:      文章 slug（用于查找辅助文件）
        aux_files: 辅助文件列表（可选；如不提供，自动从数据库查询）

    返回:
        (html_content, error_message)
        - 成功时: error_message 为 None
        - 失败时: html_content 为包含错误信息的 HTML

    原理:
        1. 检测 typst CLI 是否可用
        2. 创建临时工作区
        3. 写入主文件和所有辅助文件
        4. 运行 `typst compile --features html --format html`
        5. 读取输出的 HTML
        6. 清理临时目录
    """
    if not check_typst_available():
        return (
            f'<div class="typst-error">'
            f'<h2>⚠️ Typst 未安装</h2>'
            f'<p>请安装 Typst CLI 以渲染 Typst 文章。</p>'
            f'<p>安装方法：<code>brew install typst</code> (macOS) '
            f'或访问 <a href="https://typst.app">typst.app</a></p>'
            f'</div>',
            "Typst CLI 未安装",
        )

    # 读取辅助文件
    if aux_files is None and slug:
        aux_files = await _get_aux_files(slug)
    if aux_files is None:
        aux_files = []

    shared_config = _get_shared_config()

    # 创建临时工作区
    tmp_dir = tempfile.mkdtemp(prefix="pykych_typst_")
    workspace = Path(tmp_dir)

    try:
        _write_workspace(workspace, source, aux_files, shared_config)

        # 输出 HTML 文件
        output_path = workspace / "output.html"

        # 运行 typst compile
        cmd = [
            get_typst_path(), "compile",
            "--root", str(workspace),
            "--features", "html",
            "--format", "html",
            str(workspace / "index.typ"),
            str(output_path),
        ]

        # 构造安全的子进程环境变量（避免 HOME/XDG 权限问题）
        subprocess_env = {
            **os.environ,
            "HOME": str(workspace),
            "XDG_CACHE_HOME": str(workspace / ".cache"),
            "XDG_RUNTIME_DIR": str(workspace / ".runtime"),
        }

        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=_COMPILE_TIMEOUT,
            env=subprocess_env,
        )

        if proc.returncode != 0:
            stderr = proc.stderr.strip() or "未知编译错误"
            # 将错误信息格式化为可读 HTML
            error_html = (
                f'<div class="typst-error">'
                f'<h2>⚠️ Typst 编译错误</h2>'
                f'<pre>{_escape_html(stderr)}</pre>'
                f'</div>'
            )
            return error_html, stderr

        # 读取编译输出
        html_content = output_path.read_text(encoding="utf-8")

        # 后处理：移除完整 HTML 文档结构，只保留 body 内容
        html_content = _extract_body(html_content)

        return html_content, None

    except subprocess.TimeoutExpired:
        return (
            f'<div class="typst-error">'
            f'<h2>⚠️ Typst 编译超时</h2>'
            f'<p>编译超过 {_COMPILE_TIMEOUT} 秒，已自动中止。</p>'
            f'</div>',
            f"编译超时（>{_COMPILE_TIMEOUT}s）",
        )
    except FileNotFoundError:
        return (
            f'<div class="typst-error">'
            f'<h2>⚠️ Typst 未安装</h2>'
            f'<p>请安装 Typst CLI。</p>'
            f'</div>',
            "Typst CLI 未安装",
        )
    except Exception as e:
        return (
            f'<div class="typst-error">'
            f'<h2>⚠️ 编译异常</h2>'
            f'<pre>{_escape_html(str(e))}</pre>'
            f'</div>',
            str(e),
        )
    finally:
        # 清理临时目录
        try:
            shutil.rmtree(tmp_dir)
        except Exception:
            pass


async def compile_typst_to_pdf(
    source: str,
    slug: str = "",
    aux_files: list[dict] | None = None,
) -> tuple[Optional[bytes], Optional[str]]:
    """
    将 Typst 源码编译为 PDF。

    参数:
        source:    Typst 源码
        slug:      文章 slug（用于查找辅助文件）
        aux_files: 辅助文件列表

    返回:
        (pdf_bytes, error_message)
        - 成功时: error_message 为 None
        - 失败时: pdf_bytes 为 None
    """
    if not check_typst_available():
        return None, "Typst CLI 未安装"

    if aux_files is None and slug:
        aux_files = await _get_aux_files(slug)
    if aux_files is None:
        aux_files = []

    shared_config = _get_shared_config()

    tmp_dir = tempfile.mkdtemp(prefix="pykych_typst_")
    workspace = Path(tmp_dir)

    try:
        _write_workspace(workspace, source, aux_files, shared_config)

        output_path = workspace / "output.pdf"

        cmd = [
            get_typst_path(), "compile",
            "--root", str(workspace),
            str(workspace / "index.typ"),
            str(output_path),
        ]

        # 构造安全的子进程环境变量（避免 HOME/XDG 权限问题）
        subprocess_env = {
            **os.environ,
            "HOME": str(workspace),
            "XDG_CACHE_HOME": str(workspace / ".cache"),
            "XDG_RUNTIME_DIR": str(workspace / ".runtime"),
        }

        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=_COMPILE_TIMEOUT,
            env=subprocess_env,
        )

        if proc.returncode != 0:
            return None, proc.stderr.strip() or "PDF 编译失败"

        pdf_bytes = output_path.read_bytes()
        return pdf_bytes, None

    except subprocess.TimeoutExpired:
        return None, f"编译超时（>{_COMPILE_TIMEOUT}s）"
    except Exception as e:
        return None, str(e)
    finally:
        try:
            shutil.rmtree(tmp_dir)
        except Exception:
            pass


# ═══════════════════════════════════════════════════════════════
#  辅助函数
# ═══════════════════════════════════════════════════════════════

_BODY_RE = re.compile(
    r"<body[^>]*>(.*?)</body>",
    re.DOTALL | re.IGNORECASE,
)


def _extract_body(html: str) -> str:
    """
    从完整 HTML 文档中提取 <body> 内容。

    如果找不到 <body> 标签，则返回原始内容。
    """
    m = _BODY_RE.search(html)
    if m:
        return m.group(1).strip()
    # 没有 body 标签时，尝试移除 <html>/<head> 包装
    html = re.sub(r"<!DOCTYPE[^>]*>", "", html, flags=re.IGNORECASE)
    html = re.sub(r"<html[^>]*>", "", html, flags=re.IGNORECASE)
    html = re.sub(r"</html>", "", html, flags=re.IGNORECASE)
    html = re.sub(r"<head>.*?</head>", "", html, flags=re.DOTALL | re.IGNORECASE)
    return html.strip()


def _escape_html(text: str) -> str:
    """转义 HTML 特殊字符。"""
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


# ═══════════════════════════════════════════════════════════════
#  辅助文件管理（供路由层使用）
# ═══════════════════════════════════════════════════════════════

async def get_aux_files(slug: str) -> list[dict]:
    """获取文章的所有辅助文件。"""
    return await _get_aux_files(slug)


async def save_aux_file(slug: str, filename: str, content: str) -> bool:
    """
    为文章保存一个辅助文件（upsert 行为）。

    参数:
        slug:     文章 slug
        filename: 辅助文件名（相对路径，如 'lib/utils.typ'）
        content:  文件内容

    返回:
        True 成功
    """
    from ...core.db import _get_pool

    pool = await _get_pool()
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            # 获取 page_id
            await cur.execute(
                "SELECT id FROM typst_pages WHERE slug = %s", (slug,)
            )
            row = await cur.fetchone()
            if not row:
                raise ValueError(f"Typst 文章不存在: {slug}")
            page_id = row[0]

            # Upsert
            await cur.execute(
                "INSERT INTO typst_files (page_id, filename, content) "
                "VALUES (%s, %s, %s) "
                "ON DUPLICATE KEY UPDATE content = VALUES(content)",
                (page_id, filename, content),
            )
            return True


async def delete_aux_file(slug: str, filename: str) -> bool:
    """删除文章的辅助文件。"""
    from ...core.db import _get_pool

    pool = await _get_pool()
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                "DELETE tf FROM typst_files tf "
                "JOIN typst_pages tp ON tf.page_id = tp.id "
                "WHERE tp.slug = %s AND tf.filename = %s",
                (slug, filename),
            )
            return cur.rowcount > 0

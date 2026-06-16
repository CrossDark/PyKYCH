"""
静态文件管理模块 — 上传、列表、删除文件。

支持的文件类型:
    - 图片: JPEG, PNG, GIF, WebP, SVG
    - 文档: PDF, TXT, Markdown
    - 代码: HTML, CSS, JS, JSON, XML
    - 多媒体: MP3, WAV, MP4
    - 压缩包: ZIP, GZ

安全性:
    - 最大文件大小: 50MB
    - 文件名使用 UUID 防止冲突
    - MIME 类型白名单验证

存储:
    文件存储在 src/pykych/static/uploads/，元信息存储在 static_files 表。

用法:
    from pykych.content.files import list_files, save_file_record, delete_file
"""

import os
import uuid
from pathlib import Path

from ..core.db import get_sys_pool, row_to_dict

# ── 上传目录 ────────────────────────────────────────────────

UPLOAD_DIR = Path(__file__).parent.parent / "static" / "uploads"

# 允许的图片 MIME 类型
ALLOWED_IMAGE_TYPES = {
    "image/jpeg", "image/png", "image/gif",
    "image/webp", "image/svg+xml",
}

# 允许的所有文件 MIME 类型
ALLOWED_FILE_TYPES = ALLOWED_IMAGE_TYPES | {
    "application/pdf", "application/zip", "application/gzip",
    "text/plain", "text/markdown", "text/html",
    "text/css", "text/javascript",
    "application/json", "application/xml",
    "audio/mpeg", "audio/wav", "video/mp4",
}

# 最大文件大小（50MB）
MAX_FILE_SIZE = 50 * 1024 * 1024


def _ensure_upload_dir() -> None:
    """确保上传目录存在。"""
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


def _generate_filename(original_name: str) -> str:
    """
    生成唯一的存储文件名（UUID + 原扩展名）。

    参数:
        original_name: 原始文件名

    返回:
        唯一文件名，如 'a1b2c3d4...png'
    """
    ext = Path(original_name).suffix.lower()
    return f"{uuid.uuid4().hex}{ext}"


# ── CRUD ────────────────────────────────────────────────────


async def list_files(page: int = 1, per_page: int = 20) -> dict:
    """
    分页获取文件列表。

    参数:
        page:     页码
        per_page: 每页条数

    返回:
        {files: [...], total: int, page: int, total_pages: int}
    """
    pool = await get_sys_pool()
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            offset = (page - 1) * per_page
            await cur.execute(
                "SELECT id, filename, original_name, file_size, "
                "mime_type, uploaded_by, created_at "
                "FROM static_files "
                "ORDER BY created_at DESC LIMIT %s OFFSET %s",
                (per_page, offset),
            )
            rows = await cur.fetchall()
            files = [row_to_dict(r, cur) for r in rows]

            await cur.execute("SELECT COUNT(*) FROM static_files")
            total = (await cur.fetchone())[0]

    return {
        "files": files,
        "total": total,
        "page": page,
        "per_page": per_page,
        "total_pages": max(1, (total + per_page - 1) // per_page),
    }


async def get_file(file_id: int) -> dict | None:
    """
    获取单个文件信息。

    参数:
        file_id: 文件 ID

    返回:
        文件信息字典或 None
    """
    pool = await get_sys_pool()
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                "SELECT id, filename, original_name, file_size, "
                "mime_type, uploaded_by, created_at "
                "FROM static_files WHERE id = %s",
                (file_id,),
            )
            row = await cur.fetchone()
            return row_to_dict(row, cur) if row else None


async def save_file_record(
    filename: str,
    original_name: str,
    file_size: int,
    mime_type: str,
    uploaded_by: int = None,
) -> dict:
    """
    保存文件记录到数据库。

    参数:
        filename:      存储的文件名（UUID 格式）
        original_name: 原始文件名
        file_size:     文件大小（字节）
        mime_type:     文件的 MIME 类型
        uploaded_by:   上传者用户 ID

    返回:
        新创建的文件记录
    """
    pool = await get_sys_pool()
    file_path = str(UPLOAD_DIR / filename)
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                "INSERT INTO static_files "
                "(filename, original_name, file_path, file_size, "
                "mime_type, uploaded_by) "
                "VALUES (%s, %s, %s, %s, %s, %s)",
                (filename, original_name, file_path, file_size,
                 mime_type, uploaded_by),
            )
            return await get_file(cur.lastrowid)


async def delete_file(file_id: int) -> bool:
    """
    删除文件（数据库记录 + 物理文件）。

    参数:
        file_id: 文件 ID

    返回:
        True 表示删除成功
    """
    file_info = await get_file(file_id)
    if not file_info:
        return False

    # 删除物理文件
    file_path = UPLOAD_DIR / file_info["filename"]
    try:
        if file_path.exists():
            os.remove(file_path)
    except OSError:
        pass

    # 删除数据库记录
    pool = await get_sys_pool()
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                "DELETE FROM static_files WHERE id = %s",
                (file_id,),
            )
            return cur.rowcount > 0

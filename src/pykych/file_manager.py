"""
静态文件管理模块 — 上传、列表、删除图片和附件。
文件存储在 src/pykych/static/uploads/ 目录，元信息存储在数据库。
"""

import os
import uuid
from pathlib import Path
from datetime import datetime
from typing import Optional

from .mysql_manager import get_sys_pool, row_to_dict

# ── 上传目录 ────────────────────────────────────────────────
UPLOAD_DIR = Path(__file__).parent / "static" / "uploads"

# 允许的 MIME 类型
ALLOWED_IMAGE_TYPES = {
    "image/jpeg", "image/png", "image/gif", "image/webp", "image/svg+xml",
}
ALLOWED_FILE_TYPES = ALLOWED_IMAGE_TYPES | {
    "application/pdf", "application/zip", "application/gzip",
    "text/plain", "text/markdown", "text/html", "text/css", "text/javascript",
    "application/json", "application/xml",
    "audio/mpeg", "audio/wav", "video/mp4",
}

MAX_FILE_SIZE = 50 * 1024 * 1024  # 50MB


def _ensure_upload_dir() -> None:
    """确保上传目录存在。"""
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


def _generate_filename(original_name: str) -> str:
    """生成唯一的存储文件名。"""
    ext = Path(original_name).suffix.lower()
    return f"{uuid.uuid4().hex}{ext}"


# ── CRUD ────────────────────────────────────────────────────

async def list_files(page: int = 1, per_page: int = 20) -> dict:
    """分页获取文件列表。"""
    pool = await get_sys_pool()
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            offset = (page - 1) * per_page
            await cur.execute(
                "SELECT id, filename, original_name, file_size, mime_type, "
                "uploaded_by, created_at "
                "FROM static_files ORDER BY created_at DESC LIMIT %s OFFSET %s",
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


async def get_file(file_id: int) -> Optional[dict]:
    """获取单个文件信息。"""
    pool = await get_sys_pool()
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                "SELECT id, filename, original_name, file_size, mime_type, "
                "uploaded_by, created_at "
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
    """保存文件记录到数据库。"""
    pool = await get_sys_pool()
    _file_path = str(UPLOAD_DIR / filename)
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                "INSERT INTO static_files "
                "(filename, original_name, file_path, file_size, mime_type, uploaded_by) "
                "VALUES (%s, %s, %s, %s, %s, %s)",
                (filename, original_name, _file_path, file_size, mime_type, uploaded_by),
            )
            file_id = cur.lastrowid
            return await get_file(file_id)


async def delete_file(file_id: int) -> bool:
    """删除文件（磁盘 + 数据库）。"""
    f = await get_file(file_id)
    if not f:
        return False

    # 删除磁盘文件
    file_path = Path(f["file_path"])
    if file_path.exists():
        try:
            file_path.unlink()
        except OSError:
            pass

    # 删除数据库记录
    pool = await get_sys_pool()
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                "DELETE FROM static_files WHERE id = %s", (file_id,)
            )
            return cur.rowcount > 0


def format_file_size(size: int) -> str:
    """格式化文件大小。"""
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024:
            return f"{size:.1f} {unit}" if unit != "B" else f"{size} B"
        size /= 1024
    return f"{size:.1f} TB"


def is_image(mime_type: str) -> bool:
    """判断是否为图片类型。"""
    return mime_type in ALLOWED_IMAGE_TYPES or mime_type.startswith("image/")

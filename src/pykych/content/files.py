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


# ── 文件头魔数 MIME 类型检测 ──────────────────────────────────

# 常见文件类型的魔数签名（前几个字节 → MIME 类型）
_MAGIC_SIGNATURES: list[tuple[bytes, str]] = [
    (b"\x89PNG\r\n\x1a\n", "image/png"),
    (b"\xff\xd8\xff", "image/jpeg"),
    (b"GIF87a", "image/gif"),
    (b"GIF89a", "image/gif"),
    (b"RIFF", "image/webp"),      # RIFF....WEBP
    (b"<svg", "image/svg+xml"),
    (b"<?xml", "image/svg+xml"),  # SVG 可能是 XML 声明开头
    (b"%PDF", "application/pdf"),
    (b"PK\x03\x04", "application/zip"),
    (b"\x1f\x8b", "application/gzip"),
    (b"ID3", "audio/mpeg"),
    (b"\xff\xfb", "audio/mpeg"),
    (b"RIFF", "audio/wav"),       # RIFF....WAVE
    (b"\x00\x00\x00", "video/mp4"),  # ftyp box, weak match
    (b"#!", "text/plain"),        # shebang scripts
]


def detect_mime_type(data: bytes, filename: str = "") -> str:
    """
    通过文件头魔数检测真实 MIME 类型（不信任客户端提供的 Content-Type）。

    先检查魔数签名，再回退到扩展名推断，最后返回通用二进制类型。

    参数:
        data:     文件内容（至少前 16 字节）
        filename: 原始文件名（用于回退扩展名检测）

    返回:
        检测到的 MIME 类型字符串
    """
    # 1. 检查魔数签名
    for magic, mime in _MAGIC_SIGNATURES:
        if data[:len(magic)] == magic:
            # WebP 特殊处理：RIFF 头后第 8-15 字节应为 WEBP
            if magic == b"RIFF" and len(data) >= 12:
                if data[8:12] == b"WEBP":
                    return "image/webp"
                elif data[8:12] == b"WAVE":
                    return "audio/wav"
                continue  # 不是 WEBP/WAVE，继续检查其他签名
            return mime

    # 2. 回退：通过扩展名推断
    ext = Path(filename).suffix.lower() if filename else ""
    ext_map = {
        ".txt": "text/plain",
        ".md": "text/markdown",
        ".html": "text/html",
        ".htm": "text/html",
        ".css": "text/css",
        ".js": "text/javascript",
        ".json": "application/json",
        ".xml": "application/xml",
        ".mp3": "audio/mpeg",
        ".wav": "audio/wav",
        ".mp4": "video/mp4",
        ".zip": "application/zip",
        ".gz": "application/gzip",
        ".pdf": "application/pdf",
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".gif": "image/gif",
        ".webp": "image/webp",
        ".svg": "image/svg+xml",
        ".ico": "image/x-icon",
        ".bmp": "image/bmp",
    }
    if ext in ext_map:
        return ext_map[ext]

    # 3. 检查文本内容（无空字节则为文本）
    if b"\x00" not in data[:1024]:
        try:
            data[:1024].decode("utf-8")
            return "text/plain"
        except UnicodeDecodeError:
            pass

    return "application/octet-stream"


def validate_file_type(data: bytes, filename: str, client_mime: str = "") -> tuple[bool, str]:
    """
    验证文件类型是否在允许列表中。

    使用文件头魔数检测真实 MIME 类型，与白名单比对。

    参数:
        data:        文件内容
        filename:    原始文件名
        client_mime: 客户端声明的 MIME 类型（仅供参考，记录日志用）

    返回:
        (是否允许, 检测到的 MIME 类型)
    """
    detected = detect_mime_type(data, filename)

    # 放宽 SVG 检测：内容以 <svg 或 <?xml 开头也接受
    if detected == "text/plain" and filename.lower().endswith(".svg"):
        text = data[:512].decode("utf-8", errors="ignore").strip().lower()
        if text.startswith("<svg") or text.startswith("<?xml"):
            detected = "image/svg+xml"

    if detected not in ALLOWED_FILE_TYPES:
        return False, detected

    if client_mime and client_mime != detected:
        import logging
        logging.getLogger(__name__).warning(
            f"文件 MIME 类型不匹配: 客户端声明={client_mime}, 服务端检测={detected}"
        )

    return True, detected


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
                "SELECT id, filename, original_name, file_path, file_size, "
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
    file_path = Path(file_info.get("file_path", ""))
    if not file_path.is_absolute():
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

"""
统一设置管理器 — YAML 配置文件读写。

设置存储在 data/settings/settings.yml（文件系统），支持:
    - 默认设置自动创建
    - 点号路径访问（如 'site.title'）
    - 线程安全的文件读写

配置分类:
    site:       站点基本信息（标题、副标题、描述、Logo、备案号等）
    appearance: 外观设置（主题、主色调、字体）
    features:   功能开关（评论、搜索、暗黑模式、标签侧栏等）
    social:     社交链接（GitHub、Twitter、邮箱）

用法:
    from pykych.core.settings import get_setting, set_setting
    title = get_setting("site.title", "默认标题")
"""

import os
import yaml
import threading
from pathlib import Path
from typing import Any

# ── 配置文件路径 ────────────────────────────────────────────

# 数据根目录，支持环境变量覆盖（方便不同部署环境配置）
_DATA_ROOT = Path(
    os.environ.get("PYKYCH_DATA_DIR", Path(__file__).parent.parent.parent.parent / "data")
)
SETTINGS_DIR = _DATA_ROOT / "settings"
SETTINGS_FILE = SETTINGS_DIR / "settings.yml"

# 文件写锁（防止并发写入）+ 读缓存
_write_lock = threading.Lock()

# 内存缓存（避免每次 get_setting 都读取文件）
_cache: dict[str, Any] | None = None
_cache_mtime: float = 0.0  # 缓存时的文件修改时间


# ── 默认设置 ────────────────────────────────────────────────

DEFAULT_SETTINGS = {
    "site": {
        "title": "跨越晨昏",
        "subtitle": "欢迎来到我的个人网站",
        "description": "个人网站，分享技术、生活与思考。",
        "logo_path": "/static/img/logo.png",
        "favicon_path": "/static/img/favicon.ico",
        "icp_number": "京ICP备2026033372号",
        "language": "zh-CN",
        "timezone": "Asia/Shanghai",
    },
    "appearance": {
        "theme": "auto",         # light, dark, auto
        "style_theme": "default", # 站点风格主题目录名
        "primary_color": "#3b82f6",
        "font_family": "system-ui, -apple-system, sans-serif",
    },
    "features": {
        "enable_comments": True,
        "enable_search": True,
        "enable_dark_mode": True,
        "enable_tags_sidebar": True,
        "posts_per_page": 10,
    },
    "social": {
        "github": "",
        "twitter": "",
        "email": "",
    },
}


# ── 文件操作 ────────────────────────────────────────────────


def _ensure_settings_file() -> None:
    """
    确保设置文件存在。

    如果文件不存在，使用默认设置创建。
    目录不存在时自动创建。
    """
    try:
        SETTINGS_DIR.mkdir(parents=True, exist_ok=True)
    except (OSError, PermissionError):
        pass

    if not SETTINGS_FILE.exists():
        try:
            with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
                yaml.dump(
                    DEFAULT_SETTINGS, f,
                    allow_unicode=True,
                    default_flow_style=False,
                )
        except (OSError, PermissionError):
            pass  # 生产环境可能只读


def load_settings() -> dict[str, Any]:
    """
    加载所有设置（带内存缓存）。

    返回:
        包含所有设置的字典，键为分类名。
        如果文件不存在或无法读取，返回空字典。

    缓存策略:
        基于文件修改时间（mtime）自动失效，避免每次请求都读取磁盘。
    """
    global _cache, _cache_mtime

    _ensure_settings_file()
    try:
        current_mtime = SETTINGS_FILE.stat().st_mtime
        # 缓存命中（文件未修改）
        if _cache is not None and current_mtime == _cache_mtime:
            return _cache

        with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
            _cache = yaml.safe_load(f) or {}
            _cache_mtime = current_mtime
            return _cache
    except (OSError, yaml.YAMLError):
        return _cache if _cache is not None else {}


def save_settings(settings: dict[str, Any]) -> None:
    """
    保存所有设置（覆盖写入），并更新内存缓存。

    参数:
        settings: 要保存的完整设置字典

    注意:
        使用写锁确保线程安全。
        写入成功后自动更新缓存，避免下次读取时重新解析文件。
    """
    global _cache, _cache_mtime

    _ensure_settings_file()
    with _write_lock:
        try:
            with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
                yaml.dump(
                    settings, f,
                    allow_unicode=True,
                    default_flow_style=False,
                )
            # 更新缓存（写入后立即生效，避免下次读取时重新解析）
            _cache = settings
            _cache_mtime = SETTINGS_FILE.stat().st_mtime
        except (OSError, PermissionError) as e:
            import sys
            print(
                f"⚠️ 无法保存设置到 {SETTINGS_FILE}: {e}",
                file=sys.stderr,
            )


# ── 设置项访问 ──────────────────────────────────────────────


def get_setting(path: str, default: Any = None) -> Any:
    """
    获取单个设置项（使用点号分隔的路径）。

    参数:
        path:    设置路径，如 "site.title" 或 "features.enable_comments"
        default: 路径不存在时的默认值

    返回:
        设置值，或默认值（如果路径不存在）

    示例:
        >>> get_setting("site.title", "默认标题")
        "跨越晨昏"
        >>> get_setting("nonexistent.key", 42)
        42
    """
    settings = load_settings()
    keys = path.split(".")
    value = settings
    for key in keys:
        if isinstance(value, dict):
            value = value.get(key)
        else:
            return default
        if value is None:
            return default
    return value


def set_setting(path: str, value: Any) -> None:
    """
    设置单个设置项（使用点号分隔的路径）。

    整个「读取-修改-写入」操作在写锁保护下原子完成，
    防止并发请求导致的修改丢失（读-改-写竞态条件）。

    参数:
        path:  设置路径，如 "site.title"
        value: 要设置的值

    示例:
        >>> set_setting("site.title", "新标题")
    """
    with _write_lock:
        settings = load_settings()
        keys = path.split(".")
        target = settings
        for key in keys[:-1]:
            if key not in target or not isinstance(target[key], dict):
                target[key] = {}
            target = target[key]
        target[keys[-1]] = value
        save_settings(settings)


# ── 便捷访问函数 ────────────────────────────────────────────


def get_site_title() -> str:
    """获取站点标题。"""
    return get_setting("site.title", "跨越晨昏")


def get_site_subtitle() -> str:
    """获取站点副标题。"""
    return get_setting("site.subtitle", "欢迎来到我的个人网站")


def get_site_description() -> str:
    """获取站点描述。"""
    return get_setting("site.description", "")


def get_primary_color() -> str:
    """获取主色调。"""
    return get_setting("appearance.primary_color", "#3b82f6")


def is_comments_enabled() -> bool:
    """检查评论功能是否启用。"""
    return get_setting("features.enable_comments", True)


def is_search_enabled() -> bool:
    """检查搜索功能是否启用。"""
    return get_setting("features.enable_search", True)

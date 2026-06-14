"""
统一设置管理器 — 管理网站全局设置。
设置存储在 settings/settings.yml（文件系统），支持后台管理。
"""

import yaml
from pathlib import Path
from typing import Any, Optional

# ── 配置文件路径 ────────────────────────────────────────────

SETTINGS_DIR = Path(__file__).parent.parent.parent / "settings"
SETTINGS_FILE = SETTINGS_DIR / "settings.yml"

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
        "theme": "auto",  # light, dark, auto
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


# ── 读写设置 ────────────────────────────────────────────────


def _ensure_settings_file() -> None:
    """确保设置文件存在，不存在则创建默认设置。"""
    try:
        SETTINGS_DIR.mkdir(parents=True, exist_ok=True)
    except (OSError, PermissionError):
        pass
    if not SETTINGS_FILE.exists():
        try:
            with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
                yaml.dump(DEFAULT_SETTINGS, f, allow_unicode=True, default_flow_style=False)
        except (OSError, PermissionError):
            pass  # 生产环境可能只读


def load_settings() -> dict[str, Any]:
    """加载所有设置。"""
    _ensure_settings_file()
    with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def save_settings(settings: dict[str, Any]) -> None:
    """保存所有设置。"""
    _ensure_settings_file()
    try:
        with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
            yaml.dump(settings, f, allow_unicode=True, default_flow_style=False)
    except (OSError, PermissionError):
        pass  # 生产环境可能只读


def get_setting(path: str, default: Any = None) -> Any:
    """
    获取单个设置项，用点号分隔路径。
    例如: get_setting("site.title", "默认标题")
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
    设置单个设置项，用点号分隔路径。
    例如: set_setting("site.title", "新标题")
    """
    settings = load_settings()
    keys = path.split(".")
    target = settings
    for key in keys[:-1]:
        if key not in target:
            target[key] = {}
        target = target[key]
    target[keys[-1]] = value
    save_settings(settings)


# ── 便捷访问器 ──────────────────────────────────────────────


def get_site_title() -> str:
    return get_setting("site.title", "跨越晨昏")


def get_site_subtitle() -> str:
    return get_setting("site.subtitle", "欢迎来到我的个人网站")


def get_site_description() -> str:
    return get_setting("site.description", "")


def get_logo_path() -> str:
    return get_setting("site.logo_path", "/static/img/logo.png")


def get_icp_number() -> str:
    return get_setting("site.icp_number", "")


def get_theme() -> str:
    return get_setting("appearance.theme", "auto")


def get_posts_per_page() -> int:
    return get_setting("features.posts_per_page", 10)


# ── 初始化 ──────────────────────────────────────────────────

_ensure_settings_file()

"""
主题系统 — 支持自定义主题，覆盖模板和静态资源。
主题放在 data/themes/ 目录下，每个主题是一个包含 theme.yaml 和 templates/ 的目录。
"""

import yaml
import shutil
from pathlib import Path
from typing import Optional, Any

# ── 主题目录 ─────────────────────────────────────────────────

THEMES_DIR = Path(__file__).parent.parent.parent / "data" / "themes"


def _ensure_themes_dir() -> None:
    """确保主题目录存在（惰性创建）。"""
    try:
        THEMES_DIR.mkdir(parents=True, exist_ok=True)
    except (OSError, PermissionError):
        pass

# 默认主题名
DEFAULT_THEME = "default"

# 当前激活的主题
_active_theme: str = DEFAULT_THEME


# ── 主题配置 ─────────────────────────────────────────────────


def get_active_theme() -> str:
    """获取当前激活的主题名。"""
    return _active_theme


def set_active_theme(theme_name: str) -> bool:
    """设置激活的主题。"""
    global _active_theme
    theme_path = THEMES_DIR / theme_name
    if theme_path.exists() and (theme_path / "theme.yaml").exists():
        _active_theme = theme_name
        return True
    return False


def list_themes() -> list[dict]:
    """列出所有可用主题。"""
    _ensure_themes_dir()
    themes = []
    if not THEMES_DIR.exists():
        return themes

    for item in THEMES_DIR.iterdir():
        if item.is_dir():
            config_file = item / "theme.yaml"
            if config_file.exists():
                with open(config_file, "r", encoding="utf-8") as f:
                    config = yaml.safe_load(f) or {}
                config["name"] = item.name
                config["active"] = (item.name == _active_theme)
                themes.append(config)
    return themes


def get_theme_config(theme_name: str = None) -> Optional[dict]:
    """获取主题配置。"""
    name = theme_name or _active_theme
    config_file = THEMES_DIR / name / "theme.yaml"
    if config_file.exists():
        with open(config_file, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    return None


# ── 模板覆盖 ─────────────────────────────────────────────────


def get_theme_template_path(template_name: str) -> Optional[Path]:
    """
    获取主题覆盖的模板路径。
    如果主题有自定义模板，返回该模板路径；否则返回 None。
    """
    theme_template = THEMES_DIR / _active_theme / "templates" / template_name
    if theme_template.exists():
        return theme_template
    return None


def get_all_template_overrides() -> dict[str, Path]:
    """获取当前主题的所有模板覆盖。"""
    overrides = {}
    templates_dir = THEMES_DIR / _active_theme / "templates"
    if templates_dir.exists():
        for f in templates_dir.rglob("*.html"):
            rel_path = f.relative_to(templates_dir)
            overrides[str(rel_path)] = f
    return overrides


# ── 静态资源 ─────────────────────────────────────────────────


def get_theme_static_dir() -> Optional[Path]:
    """获取当前主题的静态资源目录。"""
    static_dir = THEMES_DIR / _active_theme / "static"
    if static_dir.exists():
        return static_dir
    return None


def get_theme_css() -> str:
    """获取主题的自定义 CSS 内容。"""
    css_file = THEMES_DIR / _active_theme / "static" / "theme.css"
    if css_file.exists():
        return css_file.read_text(encoding="utf-8")
    return ""


# ── 主题创建 ─────────────────────────────────────────────────


def create_theme(theme_name: str, config: dict = None) -> bool:
    """
    创建新主题。
    
    Args:
        theme_name: 主题名称
        config: 主题配置字典，包含 name, version, author, description 等
    """
    _ensure_themes_dir()
    try:
        theme_path = THEMES_DIR / theme_name
        if theme_path.exists():
            return False

        # 创建目录结构
        (theme_path / "templates").mkdir(parents=True)
        (theme_path / "static").mkdir(parents=True)

        # 创建默认配置
        default_config = {
            "name": theme_name,
            "version": "1.0.0",
            "author": "",
            "description": "",
            "colors": {
                "light": {
                    "bg": "#ffffff",
                    "bg_card": "#f8f9fa",
                    "text": "#1a1a2e",
                    "accent": "#3b82f6",
                },
                "dark": {
                    "bg": "#000000",
                    "bg_card": "#111111",
                    "text": "#e5e5e5",
                    "accent": "#60a5fa",
                },
            },
        }
        if config:
            default_config.update(config)

        config_file = theme_path / "theme.yaml"
        with open(config_file, "w", encoding="utf-8") as f:
            yaml.dump(default_config, f, allow_unicode=True, default_flow_style=False)

        # 创建默认 CSS
        css_file = theme_path / "static" / "theme.css"
        css_file.write_text(f"""/* {theme_name} 主题自定义样式 */
/* 在此处添加主题特定的 CSS 覆盖 */

:root {{
    /* 浅色模式变量由 theme.yaml 定义 */
}}

[data-theme="dark"] {{
    /* 深色模式变量由 theme.yaml 定义 */
}}
""")

        return True
    except (OSError, PermissionError):
        return False


def delete_theme(theme_name: str) -> bool:
    """删除主题（不允许删除默认主题和当前激活主题）。"""
    if theme_name == DEFAULT_THEME:
        return False
    if theme_name == _active_theme:
        return False
    theme_path = THEMES_DIR / theme_name
    if theme_path.exists():
        shutil.rmtree(theme_path)
        return True
    return False


# ── 初始化默认主题 ──────────────────────────────────────────


def ensure_default_theme() -> None:
    """公开接口：确保默认主题存在。"""
    _init_default_theme()


def _init_default_theme() -> None:
    """确保默认主题存在。"""
    _ensure_themes_dir()
    default_path = THEMES_DIR / DEFAULT_THEME
    if not default_path.exists():
        create_theme(DEFAULT_THEME, {
            "name": "default",
            "version": "1.0.0",
            "author": "PyKYCH",
            "description": "默认主题 — 简洁的双栏设计，支持亮色/暗色模式。",
        })


# 初始化（惰性，不在导入时强写磁盘）
_init_default_theme()

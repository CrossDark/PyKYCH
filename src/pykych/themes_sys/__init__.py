"""
主题系统 (themes_sys) — 自定义主题支持。

主题放在 data/themes/ 目录下，每个主题包含:
    - theme.yaml:  主题配置（名称、作者、描述、颜色等）
    - templates/:  模板覆盖（可选，覆盖默认模板）
    - static/:     静态资源（CSS、JS、图片等）

支持的功能:
    - 模板覆盖：主题可提供自定义 HTML 模板
    - 静态资源覆盖：主题可提供自定义 CSS/JS
    - 多主题切换：运行时切换激活主题
    - 主题配置读取

用法:
    from pykych.themes_sys import get_active_theme, list_themes, set_active_theme
"""

from .manager import (
    get_active_theme,
    set_active_theme,
    list_themes,
    get_theme_config,
    get_theme_template_path,
    get_all_template_overrides,
    DEFAULT_THEME,
)

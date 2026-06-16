"""
核心基础设施模块 (core) — 数据库连接、表结构、应用设置。

提供 PyKYCH 最底层的基础设施：
    - db.py:           MySQL 连接池管理与工具函数
    - schema.py:       表结构定义、初始化、迁移
    - settings.py:     YAML 配置文件读写（站点全局设置）
    - site_settings.py: 站点数据层（子站链接、主页推荐）

用法:
    from pykych.core import db, schema, settings
"""

from .db import (
    _get_pool,
    get_md_pool,
    get_wk_pool,
    get_sys_pool,
    close_pools,
    row_to_dict,
)
from .schema import init_tables, seed_admin
from .settings import (
    load_settings,
    save_settings,
    get_setting,
    set_setting,
    get_site_title,
    get_site_subtitle,
)

__all__ = [
    # 数据库
    "_get_pool",
    "get_md_pool",
    "get_wk_pool",
    "get_sys_pool",
    "close_pools",
    "row_to_dict",
    # 表结构
    "init_tables",
    "seed_admin",
    # 设置
    "load_settings",
    "save_settings",
    "get_setting",
    "set_setting",
    "get_site_title",
    "get_site_subtitle",
]

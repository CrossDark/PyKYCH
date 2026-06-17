"""
插件系统 (plugins_sys) — 钩子驱动的可扩展架构。

支持通过钩子（hooks）扩展网站功能，插件放在 data/plugins/ 目录下。
每个插件是一个 Python 包，通过注册钩子回调来注入功能。

预定义钩子:
    - before_page_render / after_page_render: 页面渲染
    - before_article_save / after_article_save: 文章保存
    - before_article_delete: 文章删除
    - nav_items / admin_nav_items: 导航注入
    - head_injection / foot_injection: 头部/底部注入
    - on_startup / on_shutdown: 应用生命周期

用法:
    from pykych.plugins_sys import Hooks, register_hook, run_hook
"""

from .manager import (
    Hooks,
    register_hook,
    unregister_hook,
    run_hook,
    run_hook_chain,
    load_all_plugins,
    get_plugin_info,
    get_all_plugins_info,
    install_plugin_from_zip,
    delete_plugin,
    get_plugin_files,
    read_plugin_file,
    write_plugin_file,
    _loaded_plugins,
)

"""
插件系统 — 支持通过钩子（hooks）扩展网站功能。
插件放在 data/plugins/ 目录下，每个插件是一个 Python 包。
"""

import importlib
import pkgutil
from pathlib import Path
from typing import Any, Callable

# ── 插件目录 ─────────────────────────────────────────────────

PLUGINS_DIR = Path(__file__).parent.parent.parent.parent / "data" / "plugins"


def _ensure_plugins_dir() -> None:
    """确保插件目录存在（惰性创建，避免导入时崩溃）。"""
    try:
        PLUGINS_DIR.mkdir(parents=True, exist_ok=True)
        plugins_init = PLUGINS_DIR / "__init__.py"
        if not plugins_init.exists():
            plugins_init.touch()
    except (OSError, PermissionError):
        pass  # 生产环境可能只读


# ── 钩子系统 ─────────────────────────────────────────────────

# 全局钩子注册表：{hook_name: [callback, ...]}
_hooks: dict[str, list[Callable]] = {}

# 已加载的插件
_loaded_plugins: dict[str, Any] = {}


def register_hook(hook_name: str, callback: Callable) -> None:
    """注册一个钩子回调。"""
    if hook_name not in _hooks:
        _hooks[hook_name] = []
    _hooks[hook_name].append(callback)


def unregister_hook(hook_name: str, callback: Callable) -> None:
    """取消注册一个钩子回调。"""
    if hook_name in _hooks:
        _hooks[hook_name] = [cb for cb in _hooks[hook_name] if cb is not callback]


async def run_hook(hook_name: str, *args, **kwargs) -> list[Any]:
    """
    运行指定钩子的所有回调。
    回调可以是同步或异步函数。
    返回所有回调的结果列表。
    """
    results = []
    for callback in _hooks.get(hook_name, []):
        import asyncio
        if asyncio.iscoroutinefunction(callback):
            result = await callback(*args, **kwargs)
        else:
            result = callback(*args, **kwargs)
        if result is not None:
            results.append(result)
    return results


async def run_hook_chain(hook_name: str, initial_value: Any, *args, **kwargs) -> Any:
    """
    链式运行钩子：每个回调接收上一个回调的返回值作为第一个参数。
    适用于模板内容修改、数据处理管道等。
    """
    import asyncio
    value = initial_value
    for callback in _hooks.get(hook_name, []):
        if asyncio.iscoroutinefunction(callback):
            value = await callback(value, *args, **kwargs)
        else:
            value = callback(value, *args, **kwargs)
    return value


# ── 预定义钩子名称 ──────────────────────────────────────────

class Hooks:
    """常用钩子名称常量。"""
    # 页面渲染
    BEFORE_PAGE_RENDER = "before_page_render"      # (template_name, context) -> context
    AFTER_PAGE_RENDER = "after_page_render"        # (template_name, html) -> html
    
    # 文章生命周期
    BEFORE_ARTICLE_SAVE = "before_article_save"    # (article_type, article_data) -> article_data
    AFTER_ARTICLE_SAVE = "after_article_save"      # (article_type, article)
    BEFORE_ARTICLE_DELETE = "before_article_delete" # (article_type, slug)
    
    # 导航
    NAV_ITEMS = "nav_items"                        # (items: list) -> items
    ADMIN_NAV_ITEMS = "admin_nav_items"            # (items: list) -> items
    
    # 头部/底部
    HEAD_INJECTION = "head_injection"              # () -> html_string
    FOOTER_INJECTION = "footer_injection"          # () -> html_string
    
    # 搜索
    SEARCH_FILTER = "search_filter"                # (results: list, query: str) -> results
    
    # 站点启动
    ON_STARTUP = "on_startup"                      # () -> None
    ON_SHUTDOWN = "on_shutdown"                    # () -> None


# ── 插件加载器 ──────────────────────────────────────────────


def discover_plugins() -> list[str]:
    """发现 plugins/ 目录下的所有插件包。"""
    _ensure_plugins_dir()
    if not PLUGINS_DIR.exists():
        return []
    
    plugins = []
    for item in PLUGINS_DIR.iterdir():
        if item.is_dir() and (item / "__init__.py").exists():
            plugins.append(item.name)
        elif item.suffix == ".py" and item.name != "__init__.py":
            plugins.append(item.stem)
    return plugins


def load_plugin(plugin_name: str) -> Any | None:
    """
    加载指定插件。
    插件可以是 plugins/ 下的包或单文件模块。
    """
    if plugin_name in _loaded_plugins:
        return _loaded_plugins[plugin_name]
    
    try:
        module = importlib.import_module(f"plugins.{plugin_name}")
        _loaded_plugins[plugin_name] = module
        
        # 如果插件有 setup 函数，调用它
        if hasattr(module, "setup"):
            setup_func = getattr(module, "setup")
            if callable(setup_func):
                setup_func()
        
        return module
    except ImportError as e:
        print(f"[Plugin] 无法加载插件 '{plugin_name}': {e}")
        return None


def load_all_plugins() -> dict[str, Any]:
    """加载所有发现的插件。"""
    for name in discover_plugins():
        load_plugin(name)
    return _loaded_plugins


def unload_plugin(plugin_name: str) -> bool:
    """卸载插件并调用其 teardown 函数。"""
    if plugin_name not in _loaded_plugins:
        return False
    
    module = _loaded_plugins[plugin_name]
    if hasattr(module, "teardown"):
        teardown_func = getattr(module, "teardown")
        if callable(teardown_func):
            teardown_func()
    
    del _loaded_plugins[plugin_name]
    return True


# ── 示例插件（若无插件目录则创建默认） ──────────────────────


def _create_example_plugin() -> None:
    """创建示例插件以演示插件系统。"""
    _ensure_plugins_dir()
    try:
        example_dir = PLUGINS_DIR / "hello_world"
        example_dir.mkdir(parents=True, exist_ok=True)

        init_file = example_dir / "__init__.py"
        if not init_file.exists():
            init_file.write_text('''"""
示例插件：Hello World
演示 PyKYCH 插件系统的基本用法。
"""

def setup():
    """插件加载时调用。"""
    from src.pykych.plugin_manager import register_hook, Hooks
    
    async def inject_hello(context: dict) -> dict:
        """在页面渲染前注入问候语。"""
        context["plugin_greeting"] = "👋 Hello from HelloWorld Plugin!"
        return context
    
    register_hook(Hooks.BEFORE_PAGE_RENDER, inject_hello)
    print("[HelloWorld Plugin] 已加载！")


def teardown():
    """插件卸载时调用。"""
    print("[HelloWorld Plugin] 已卸载！")
''')
    except (OSError, PermissionError):
        pass

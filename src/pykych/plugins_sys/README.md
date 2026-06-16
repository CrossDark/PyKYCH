# Plugins 插件系统

基于钩子（Hooks）的可扩展架构，允许第三方插件注入功能。

## 插件位置

插件放在 `data/plugins/` 目录下，每个插件是一个 Python 包。

## 预定义钩子

| 钩子名称 | 参数 | 说明 |
|----------|------|------|
| `ON_STARTUP` | — | 应用启动时 |
| `ON_SHUTDOWN` | — | 应用关闭时 |
| `BEFORE_PAGE_RENDER` | (template_name, context) → context | 页面渲染前 |
| `AFTER_PAGE_RENDER` | (template_name, html) → html | 页面渲染后 |
| `BEFORE_ARTICLE_SAVE` | (article_type, article_data) → article_data | 文章保存前 |
| `AFTER_ARTICLE_SAVE` | (article_type, article) | 文章保存后 |
| `BEFORE_ARTICLE_DELETE` | (article_type, slug) | 文章删除前 |
| `NAV_ITEMS` | (items: list) → items | 导航菜单注入 |
| `ADMIN_NAV_ITEMS` | (items: list) → items | 管理后台导航注入 |
| `HEAD_INJECTION` | () → html_string | 页面 <head> 注入 |
| `FOOT_INJECTION` | () → html_string | 页面底部注入 |

## 插件开发示例

```python
# data/plugins/my_plugin/__init__.py
from pykych.plugins_sys import register_hook, Hooks

def inject_analytics():
    return '<script>console.log("analytics loaded")</script>'

register_hook(Hooks.FOOT_INJECTION, inject_analytics)


def modify_nav(items):
    items.append({"name": "我的链接", "url": "/custom"})
    return items

register_hook(Hooks.NAV_ITEMS, modify_nav)
```

## 使用

```python
from pykych.plugins_sys import register_hook, run_hook, Hooks

# 注册钩子
register_hook(Hooks.HEAD_INJECTION, my_callback)

# 运行钩子（链式，每个回调接收上一个返回值）
result = await run_hook(Hooks.BEFORE_PAGE_RENDER, "template.html", context)
```

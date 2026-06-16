# Themes 主题系统

支持自定义主题，覆盖模板和静态资源。

## 主题位置

主题放在 `data/themes/` 目录下，每个主题是一个包含以下内容的子目录：

```
themes/
├── default/          # 默认主题
│   ├── theme.yaml    # 主题配置
│   └── static/
│       └── theme.css # 主题样式
├── ocean/            # 海洋主题
│   ├── theme.yaml
│   └── static/
│       └── theme.css
└── ...
```

## 主题配置 (theme.yaml)

```yaml
name: "海洋主题"
description: "清新的海洋蓝色调主题"
author: "PyKYCH"
version: "1.0"
colors:
  primary: "#0ea5e9"
  background: "#f0f9ff"
  text: "#1e293b"
```

## 内置主题

| 主题 | 目录 | 说明 |
|------|------|------|
| default | `default/` | 默认主题（蓝白配色） |
| abyss | `abyss/` | 深渊主题（暗黑） |
| forest | `forest/` | 森林主题（绿色） |
| lavender | `lavender/` | 薰衣草主题（紫色） |
| mono | `mono/` | 单色主题（黑白） |
| ocean | `ocean/` | 海洋主题（蓝色） |
| sunset | `sunset/` | 日落主题（橙红） |

## 使用

```python
from pykych.themes_sys import list_themes, set_active_theme, get_active_theme

# 列出所有主题
themes = list_themes()
for t in themes:
    print(f"{t['name']}: {t.get('description')}")

# 切换主题
set_active_theme("ocean")

# 获取当前主题
current = get_active_theme()
```

## 模板覆盖

主题可以提供自定义模板，覆盖默认模板：

```
themes/ocean/templates/
├── home.html     # 覆盖首页
├── base.html     # 覆盖基础布局
└── ...
```

如果主题目录下有对应的模板文件，系统会自动使用主题版本。

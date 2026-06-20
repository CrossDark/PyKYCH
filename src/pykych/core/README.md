# Core 核心基础设施

提供 PyKYCH 最底层的基础设施，包括数据库连接管理、表结构定义和站点设置。

## 模块结构

| 文件 | 说明 |
|------|------|
| `__init__.py` | 公开接口导出 |
| `db.py` | MySQL 连接池管理与工具函数（惰性创建、自动建库、连接池复用） |
| `schema.py` | 数据库表结构定义（17 张表）、初始化、数据迁移 |
| `settings.py` | YAML 配置文件读写（站点标题、外观、功能开关、社交链接） |
| `site_settings.py` | 站点数据层（子站点链接管理、主页推荐文章） |

## 数据库设计

所有表使用 InnoDB 引擎 + utf8mb4 字符集，支持 Emoji。

### 核心表
- `articles` — Markdown 文章
- `pages` — Wikidot 页面
- `html_pages` — HTML 页面
- `bbcode_pages` — BBCode 文章

### 系统表
- `users` — 用户（含角色枚举：user/admin/owner）
- `tags` / `article_tags` — 标签与文章关联
- `comments` / `line_comments` — 全文评论 / 行评论
- `ratings` — 评分系统
- `notifications` — 站内通知
- `subsite_links` / `featured_articles` — 首页展示
- `static_files` — 上传文件管理
- `webauthn_credentials` — 通行密钥

## 使用示例

```python
from pykych.core.db import get_sys_pool, row_to_dict, close_pools
from pykych.core.schema import init_tables, seed_admin
from pykych.core.settings import get_setting, set_setting

# 获取设置
title = get_setting("site.title", "默认标题")

# 设置值
set_setting("features.enable_comments", True)
```

## 配置

数据库配置位于 `data/settings/db.yaml`，站点设置位于 `data/settings/settings.yml`。
两者均在应用首次启动时自动创建（如果不存在）。

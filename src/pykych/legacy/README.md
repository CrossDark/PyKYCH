# Legacy 旧模块

此目录包含 v1.0 版本的旧模块，已被新模块完全替代，保留仅作参考。

## 旧模块 → 新模块对照表

| 旧模块 | 新模块 | 说明 |
|--------|--------|------|
| `mysql_manager.py` | `core/db.py` + `core/schema.py` | 数据库连接与表结构 |
| `settings_manager.py` | `core/settings.py` | YAML 设置管理 |
| `_auth_legacy.py` | `auth/password.py` + `auth/user.py` + `auth/session.py` | 认证系统 |
| `webauthn_manager.py` | `auth/webauthn.py` | 通行密钥 |
| `article_manager.py` | `content/articles.py` | 统一文章 CRUD |
| `tag_manager.py` | `content/tags.py` | 标签管理 |
| `comment_manager.py` | `content/comments.py` | 全文评论 |
| `line_comment_manager.py` | `content/comments.py` | 行评论 |
| `rating_manager.py` | `content/ratings.py` | 评分系统 |
| `file_manager.py` | `content/files.py` | 文件上传 |
| `external_html.py` | `content/external.py` | 外部站点 |
| `bbcode_parser.py` | `content/parsers/bbcode.py` | BBCode 解析 |
| `wikidot_parser.py` | `content/parsers/wikidot.py` | Wikidot 解析 |
| `db.py` | `content/articles.py` | MD 文章 (已统一) |
| `wikidot_db.py` | `content/articles.py` | Wikidot (已统一) |
| `html_db.py` | `content/articles.py` | HTML (已统一) |
| `bbcode_db.py` | `content/articles.py` | BBCode (已统一) |
| `plugin_manager.py` | `plugins_sys/manager.py` | 插件系统 |
| `theme_manager.py` | `themes_sys/manager.py` | 主题系统 |
| `user_profile.py` | `auth/profile.py` | 用户资料 |
| `site_settings.py` | `core/site_settings.py` | 站点设置 |
| `notification_manager.py` | `content/notifications.py` | 通知管理 |

## 注意

这些文件 **不再被任何活跃代码引用**，仅保留作为历史参考。
如需修改功能，请编辑对应的新模块文件。

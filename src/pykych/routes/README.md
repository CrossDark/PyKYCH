# Routes 路由层

HTTP 请求处理与页面渲染，将 URL 映射到业务逻辑。

## 路由结构

| 文件 | 路由前缀 | 说明 |
|------|----------|------|
| `home` (在 main.py) | `/` | 首页、关于页面 |
| `auth.py` | `/auth` | 登录、登出、CAPTCHA、WebAuthn |
| `admin.py` | `/admin` | 管理后台（仪表盘、文章 CRUD、用户/标签/通知/文件管理） |
| `md.py` | `/md` | Markdown 文章列表与详情 |
| `wikidot.py` | `/wikidot` | Wikidot 页面列表与详情 |
| `html_route.py` | `/html` | HTML 页面（本地 + 外部站点） |
| `bbcode.py` | `/bbcode` | BBCode 文章列表与详情 |
| `comments.py` | `/comments` | 评论提交（仅登录用户） |
| `labels.py` | `/labels` | 标签列表与详情（按标签筛选文章） |
| `search.py` | `/search` | 全站搜索（跨四种文章类型） |
| `__init__.py` | — | 包初始化 |

## 权限模型

| 角色 | 权限 |
|------|------|
| `user` (普通用户) | 浏览文章、评论、评分 |
| `admin` (管理员) | 以上 + 管理文章、标签、通知、文件、外部站点 |
| `owner` (站长) | 以上 + 用户管理、站点设置、主题切换 |

## 安全增强 (v2.0)

- ✅ 登录速率限制（防暴力破解）
- ✅ CSRF Token 保护
- ✅ 会话固定攻击防护（登录时重建会话）
- ✅ CAPTCHA 绕过漏洞修复
- ✅ 密码强度校验（前端 + 后端双重验证）
- ✅ 恒定时间比较（防时序攻击）

## 使用示例

```python
# 在路由中使用登录检查
from pykych.auth.session import require_login, require_admin

user, err = await require_login(request)
if err:
    return err  # 重定向到登录页

user, err = await require_admin(request)
if err:
    return err  # 权限不足
```

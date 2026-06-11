# PyKYCH

个人网站 Python 版 —— 基于 LiHiL 异步 Web 框架构建的轻量级内容管理系统。

## 项目简介

PyKYCH 是一个使用 Python 编写的个人网站系统，支持 **Markdown 文章** 和 **Wikidot 风格 Wiki 页面** 的发布与管理。系统内置用户认证与后台管理面板，适合个人博客、技术笔记、知识库等场景。

### 功能特性

- **Markdown 文章系统** — 支持 GFM 表格、围栏代码块、目录、提示框等扩展语法，文章 CRUD 完整闭环
- **Wikidot Wiki 系统** — 自研 Wikidot 标记语言解析器，支持标题、粗斜体、代码块、表格、引用、列表等语法
- **用户认证** — 基于 Session 的登录/登出，PBKDF2-SHA256 密码哈希，管理员权限控制
- **后台管理** — 可视化管理面板，支持文章/页面的创建、编辑、删除及用户管理
- **MySQL 持久化** — 三库分离架构（文章库 / Wiki 库 / 系统库），aiomysql 异步连接池

## 项目架构

```
PyKYCH/
├── settings/
│   └── db.yaml                  # 数据库连接配置,已被git忽略,请根据实例进行创建
├── src/
│   └── pykych/
│       ├── __init__.py
│       ├── main.py              # 应用入口：Lihil 实例化、生命周期、模板引擎、路由挂载
│       ├── auth.py              # 认证模块：密码哈希 (PBKDF2-SHA256)、用户 CRUD、会话管理
│       ├── db.py                # 数据层：Markdown 文章的分页查询与 CRUD
│       ├── wikidot_db.py        # 数据层：Wikidot 页面的分页查询与 CRUD
│       ├── wikidot_parser.py    # 解析器：Wikidot 标记语言 → HTML 转换
│       ├── mysql_manager.py     # 基础设施：读取 db.yaml、管理 aiomysql 连接池
│       ├── routes/
│       │   ├── __init__.py
│       │   ├── auth.py          # 路由：/auth/login, /auth/logout
│       │   ├── admin.py         # 路由：/admin (仪表盘、文章/Wiki/用户 CRUD)
│       │   ├── md.py            # 路由：/md (Markdown 文章列表与详情)
│       │   └── wikidot.py       # 路由：/wikidot (Wiki 页面列表与详情)
│       ├── templates/           # Jinja2 模板（base / home / login / admin 等）
│       └── static/              # 静态资源（CSS / JS）
├── pyproject.toml               # 项目元信息与依赖
├── db.yaml.example              # 数据库配置示例
├── LICENSE                      # MIT 许可证
└── README.md
```

### 架构分层

```
┌─────────────────────────────────────────────────────────┐
│                      浏览器 / 客户端                      │
└──────────────────────────┬──────────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────┐
│                    路由层 (routes/)                      │
│   auth.py: 登录/登出           admin.py: 后台管理          │
│   md.py: Markdown 文章展示     wikidot.py: Wiki 页面展示   │
└──────────────────────────┬──────────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────┐
│                    业务逻辑层                             │
│   auth.py (认证)  │  wikidot_parser.py (Wiki 解析)       │
└──────────────────────────┬──────────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────┐
│                     数据访问层                            │
│   db.py (文章 CRUD)  │  wikidot_db.py (Wiki CRUD)        │
│   auth.py (用户 CRUD)                                    │
└──────────────────────────┬──────────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────┐
│                   基础设施层                              │
│   mysql_manager.py: aiomysql 连接池管理                   │
│   settings/db.yaml: 数据库配置                            │
└──────────────────────────┬──────────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────┐
│                      MySQL 数据库                        │
│   pykych_md (文章)  │  pykych_wiki (Wiki)  │  pykych_sys (系统)  │
└─────────────────────────────────────────────────────────┘
```

### 技术栈

| 组件 | 技术 | 说明 |
|------|------|------|
| Web 框架 | [LiHiL](https://pypi.org/project/lihil/) | 高性能异步 ASGI 框架 |
| 模板引擎 | Jinja2 | 服务端 HTML 渲染 |
| 数据库 | MySQL + aiomysql | 异步连接池，三库分离 |
| Markdown | Python-Markdown | 扩展语法支持 (extra, fenced_code, toc 等) |
| Wikidot | 自研解析器 | Wikidot 标记语言 → HTML |
| 密码哈希 | hashlib PBKDF2-SHA256 | 标准库实现，60 万次迭代 |
| 配置 | PyYAML | YAML 配置文件解析 |

## 快速开始

### 环境要求

- Python >= 3.10
- MySQL 8.0+

### 1. 克隆项目

```bash
git clone <repo-url>
cd PyKYCH
```

### 2. 创建虚拟环境

```bash
python -m venv .venv
source .venv/bin/activate  # Linux/macOS
# .venv\Scripts\activate   # Windows
```

### 3. 安装依赖

```bash
pip install -e .
```

### 4. 配置数据库

复制配置示例并填写你的 MySQL 连接信息：

```bash
cp db.yaml.example settings/db.yaml
```

编辑 `settings/db.yaml`：

```yaml
mysql:
  host: localhost
  port: 3306
  user: root
  password: your_password
  markdown_db: pykych_md
  wikidot_db: pykych_wiki
  system_db: pykych_sys
```

### 5. 创建数据库

```sql
CREATE DATABASE IF NOT EXISTS pykych_md CHARACTER SET utf8mb4;
CREATE DATABASE IF NOT EXISTS pykych_wiki CHARACTER SET utf8mb4;
CREATE DATABASE IF NOT EXISTS pykych_sys CHARACTER SET utf8mb4;
```

### 6. 启动服务

```bash
uvicorn src.pykych.main:app --host 0.0.0.0 --port 8000 --reload
```

访问 http://localhost:8000 即可看到首页。

### 7. 登录后台

默认管理员账号：

- 用户名: `admin`
- 密码: `admin123`

登录后访问 http://localhost:8000/admin 进入管理面板。

## 许可证

MIT License © 2026 跨越晨昏

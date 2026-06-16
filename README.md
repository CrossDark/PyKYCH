# 跨越晨昏

基于 [LiHiL](https://pypi.org/project/lihil/) 异步 Web 框架构建的个人网站系统，支持多种内容类型。

## 项目简介

跨越晨昏 是一个使用 Python 编写的个人网站系统，支持 **Markdown / Wikidot / BBCode / HTML** 四种内容类型的发布与管理。系统内置用户认证、评论、标签、搜索、通知、文件管理、插件系统、主题系统及 WordPress 风格后台管理面板。

### 功能特性

**内容类型**
- 📝 **Markdown 文章** — GFM 表格、围栏代码块、目录、提示框等扩展语法
- 📚 **Wikidot Wiki** — 自研解析器，支持折叠块、代码高亮、上下标、锚点等
- 💬 **BBCode 文章** — 自研解析器，兼容论坛风格标记
- 🌐 **HTML 页面** — 原生 HTML 编写，支持从外部静态站抓取缓存（智能正文提取 + 内部链接重写）；支持全面导入和单页面导入

**交互功能**
- 🔍 **全文搜索** — 跨四种文章类型的全文内容检索
- 💬 **评论区** — 所有文章底部统一的评论系统
- 📝 **行评论** — 针对文章每一行的短评系统（≤20字），单条评论直接展开在正文左侧，多条显示数量徽标
- ⭐ **评分系统** — [-1, 1] 区间浮点评分，实时汇总展示；已评分文章支持撤销评分
- 🏷️ **标签系统** — 文章标签管理，侧栏导航，标签聚合页
- 🔔 **通知系统** — 后台发布重要通知，首页醒目展示
- 🌙 **黑暗模式** — 纯白/纯黑双主题，跟随系统偏好，无闪烁切换

**管理后台 (WordPress 风格)**
- 📋 **文章管理** — 四种文章类型统一 CRUD，标签页切换
- 🏷️ **标签管理** — 可视化标签增删改，行内重命名
- 🏠 **主页管理** — 子站点链接、推荐文章、通知、外部站点管理
- 📁 **文件管理** — 图片/附件上传，链接复制
- 👥 **用户管理** — 三级角色（站长/管理员/用户），权限分级
- ⚙️ **站点设置** — 网站标题、副标题、ICP 备案号等全局配置
- 👤 **用户资料** — 头像上传、个人简介、密码修改

**扩展系统**
- 🔌 **插件系统** — 钩子（Hooks）机制，支持 ON_STARTUP / ON_SHUTDOWN 等生命周期
- 🎨 **主题系统** — 模板覆盖 + 自定义 CSS，支持多主题切换

**安全特性 (v2.0 后端化)**
- 🔐 **PBKDF2-SHA256** 密码哈希 (60 万次迭代，NFC Unicode 规范化)
- 🛡️ **速率限制** — 每用户名+IP 组合 5 次/分钟，连续 10 次失败锁定 15 分钟
- 🔑 **CSRF 保护** — 登录/表单操作使用签名 Token 防跨站请求伪造
- 🔄 **会话固定防护** — 登录时重建会话 ID
- ⏱️ **恒定时间比较** — `hmac.compare_digest` 防时序侧信道攻击
- 🔢 **数学验证码** — 防机器人暴力破解（已修复绕过漏洞）
- 🔏 **WebAuthn** 通行密钥 (Passkey) 无密码登录
- 🔒 **Session 密钥** — 通过 `PYKYCH_SECRET_KEY` 环境变量配置
- MySQL + aiomysql 异步连接池，单库统一架构
- Jinja2 模板引擎，响应式设计
- YAML 文件系统设置管理 (`data/settings.yml`)

## 项目架构 (v2.0 重构)

```
PyKYCH/
├── data/                        # 运行时数据目录
│   ├── settings/
│   │   ├── db.yaml              # 数据库配置 (gitignored)
│   │   └── settings.yml         # 站点全局设置
│   ├── avatars/                 # 用户头像
│   ├── plugins/                 # 插件包
│   └── themes/                  # 主题包
├── src/pykych/
│   ├── main.py                  # 应用入口 & 生命周期
│   ├── static/                  # CSS / JS / 上传文件
│   ├── templates/               # Jinja2 模板
│   │
│   ├── core/                    # 🔧 核心基础设施
│   │   ├── db.py                #   MySQL 异步连接池管理
│   │   ├── schema.py            #   17张表结构定义 & 初始化迁移
│   │   ├── settings.py          #   YAML 文件系统设置管理
│   │   └── site_settings.py     #   子站点链接 & 推荐文章
│   │
│   ├── auth/                    # 🔒 认证系统 (安全增强)
│   │   ├── password.py          #   PBKDF2-SHA256 密码哈希 + 强度校验
│   │   ├── session.py           #   会话管理 + CSRF 保护 + 权限检查
│   │   ├── user.py              #   用户 CRUD + 角色管理
│   │   ├── profile.py           #   用户资料 & 头像管理
│   │   ├── rate_limit.py        #   登录速率限制 (防暴力破解)
│   │   └── webauthn.py          #   通行密钥 (WebAuthn) + CBOR 解码
│   │
│   ├── content/                 # 📝 内容管理
│   │   ├── articles.py          #   统一文章 CRUD (MD/Wikidot/HTML/BBCode)
│   │   ├── tags.py              #   标签管理 & 文章关联
│   │   ├── comments.py          #   全文评论 + 行评论
│   │   ├── ratings.py           #   评分系统 ([-1, 1] 区间)
│   │   ├── files.py             #   静态文件上传管理
│   │   ├── external.py          #   外部站点抓取缓存
│   │   ├── notifications.py     #   站内通知管理
│   │   └── parsers/
│   │       ├── bbcode.py        #     BBCode → HTML 解析器
│   │       └── wikidot.py       #     Wikidot → HTML 解析器
│   │
│   ├── routes/                  # 🌐 HTTP 路由层
│   │   ├── auth.py              #   /auth (登录/登出/CAPTCHA/通行密钥)
│   │   ├── admin.py             #   /admin (管理后台)
│   │   ├── md.py                #   /md (Markdown)
│   │   ├── wikidot.py           #   /wikidot
│   │   ├── html_route.py        #   /html
│   │   ├── bbcode.py            #   /bbcode
│   │   ├── labels.py            #   /labels
│   │   ├── comments.py          #   评论提交
│   │   └── search.py            #   /search
│   │
│   ├── plugins_sys/             # 🔌 插件系统
│   │   └── manager.py           #   钩子 (Hooks) 机制
│   │
│   ├── themes_sys/              # 🎨 主题系统
│   │   └── manager.py           #   模板覆盖 + 自定义 CSS
│   │
│   └── legacy/                  # 📦 旧模块 (仅供参考，不再使用)
├── pyproject.toml
├── LICENSE (MIT)
└── README.md
```

### 数据库表

| 表名 | 用途 |
|------|------|
| `articles` | Markdown 文章 |
| `pages` | Wikidot 页面 |
| `html_pages` | 本地 HTML 页面 |
| `bbcode_pages` | BBCode 文章 |
| `users` | 用户账号（含头像、简介等扩展字段） |
| `tags` | 标签 |
| `article_tags` | 文章-标签关联 |
| `comments` | 评论 |
| `line_comments` | 行评论（每行短评，≤20字） |
| `ratings` | 文章评分（[-1, 1] 浮点，支持撤销） |
| `webauthn_credentials` | 通行密钥（WebAuthn 公钥存储） |
| `subsite_links` | 子站点链接 |
| `featured_articles` | 主页推荐文章 |
| `notifications` | 通知 |
| `external_sites` | 外部站点配置 |
| `external_pages` | 外部站点缓存 |
| `static_files` | 上传文件记录 |

### 技术栈

| 组件 | 技术 | 说明 |
|------|------|------|
| Web 框架 | [LiHiL](https://pypi.org/project/lihil/) | 高性能异步 ASGI 框架 |
| 模板引擎 | Jinja2 | 服务端 HTML 渲染 |
| 数据库 | MySQL + aiomysql | 异步连接池，单库统一 |
| 密码哈希 | hashlib PBKDF2-SHA256 | 标准库实现，NFC 规范化 |
| 通行密钥 | WebAuthn + cryptography | 自研 CBOR 解码器，ECDSA 签名验证 |
| HTTP 客户端 | aiohttp | 外部站点 HTML 抓取 |
| 配置 | PyYAML | YAML 配置解析 |

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
cp db.yaml.example data/settings/db.yaml
```

编辑 `data/settings/db.yaml`：

```yaml
mysql:
  host: localhost
  port: 3306
  user: root
  password: your_password
  database: pykych
```

### 5. 创建数据库

```sql
CREATE DATABASE IF NOT EXISTS pykych CHARACTER SET utf8mb4;
```

### 6. 站点设置（可选）

运行时数据目录 `data/` 会在首次启动时自动创建，包含：

```
data/
├── settings.yml    # 站点全局设置（自动生成默认值）
├── avatars/        # 用户头像存储
├── plugins/        # 插件包目录
└── themes/         # 主题包目录
    └── default/    # 默认主题
```

你也可以手动编辑 `data/settings.yml` 来配置网站标题、副标题、ICP 备案号等。

### 7. 配置安全密钥 (生产环境必须)

```bash
export PYKYCH_SECRET_KEY="your-random-secret-key-at-least-32-chars"
```

### 8. 启动服务

```bash
uvicorn src.pykych.main:app --host 0.0.0.0 --port 8000 --reload
```

或使用 LiHiL CLI：

```bash
lihil run
```

访问 http://localhost:8000 即可看到首页。

### 9. 登录后台

默认管理员账号（首次启动自动创建）：

- 用户名: `admin`
- 密码: `admin123`

登录后访问 http://localhost:8000/admin 进入管理面板。

## 插件系统

PyKYCH 支持通过钩子（Hooks）扩展网站功能。插件放在 `data/plugins/` 目录下，每个插件是一个 Python 包。

### 可用钩子

| 钩子 | 触发时机 | 说明 |
|------|---------|------|
| `ON_STARTUP` | 应用启动后 | 初始化插件资源 |
| `ON_SHUTDOWN` | 应用关闭前 | 清理插件资源 |

### 创建插件

在 `data/plugins/` 下创建 Python 包：

```
data/plugins/
└── my_plugin/
    ├── __init__.py
    └── plugin.py
```

`plugin.py` 示例：

```python
from src.pykych.plugin_manager import register_hook, Hooks

async def on_startup():
    print("MyPlugin: 网站已启动！")

def register():
    register_hook(Hooks.ON_STARTUP, on_startup)
```

## 主题系统

主题放在 `data/themes/` 目录下，每个主题包含 `theme.yaml` 配置、可选的 `templates/` 模板覆盖和 `static/theme.css` 自定义样式。

### 主题结构

```
data/themes/
└── my_theme/
    ├── theme.yaml          # 主题元信息
    ├── static/
    │   └── theme.css       # 自定义 CSS
    └── templates/          # 模板覆盖（可选）
        └── home.html
```

`theme.yaml` 示例：

```yaml
name: My Theme
version: "1.0"
author: Your Name
description: 自定义主题
```

当前激活的主题通过 `data/settings.yml` 中的 `appearance.theme` 配置。

## 许可证

MIT License © 2026 跨越晨昏

## Docker 部署

保持现有部署方式不变，额外提供 Docker 容器化部署方案。

### 前置要求

- [Docker](https://docs.docker.com/get-docker/) >= 20.10
- [Docker Compose](https://docs.docker.com/compose/install/) >= 2.0

### 1. 克隆项目

```bash
git clone <repo-url>
cd PyKYCH
```

### 2. 配置环境变量（可选）

```bash
cp .env.example .env
```

编辑 `.env` 修改 MySQL 密码：

```env
MYSQL_ROOT_PASSWORD=your_root_password
MYSQL_PASSWORD=your_app_password
```

### 3. 启动服务

```bash
docker compose up -d
```

首次启动会自动：
- 拉取并构建应用镜像
- 启动 MySQL 8.0 容器（端口映射到 `3307` 避免冲突）
- 等待 MySQL 健康检查通过后启动应用
- 自动创建数据库和表
- 创建默认管理员账号

### 4. 访问

- 网站首页: http://localhost:8000
- 管理后台: http://localhost:8000/admin
- 默认账号: `admin` / `admin123`

### 5. 常用命令

```bash
# 查看日志
docker compose logs -f app

# 停止服务
docker compose down

# 停止并删除数据卷（⚠️ 会清除数据库和上传文件）
docker compose down -v

# 重新构建镜像
docker compose build --no-cache

# 更新后重启
docker compose up -d --build
```

### 6. 自定义配置

**使用外部数据库：** 修改 `.env` 或 `docker-compose.yml` 中的数据库连接变量，并移除 `mysql` 服务。

**挂载自定义 db.yaml：** 在 `docker-compose.yml` 中取消注释 `data/settings/db.yaml` 的挂载配置，然后创建 `data/settings/db.yaml` 文件。挂载后环境变量配置将被忽略。

**持久化数据：** 应用数据（头像、插件、主题、站点设置）通过 `app_data` 卷持久化。MySQL 数据通过 `mysql_data` 卷持久化。即使容器被删除，数据也不会丢失。

## 生产部署 (Ubuntu 24.04 + Nginx)

### 1. 服务器环境准备

```bash
# 更新系统
sudo apt update && sudo apt upgrade -y

# 安装 Python 3.12（Ubuntu 24.04 自带）及必要工具
sudo apt install -y python3 python3-pip python3-venv git nginx
```

> **注意：** 如果使用远程 MySQL（即数据库不在本机），则无需安装 MySQL Server，只需确保服务器能连通远程数据库端口（默认 3306）。

### 2. 创建项目目录与用户

```bash
# 创建专用用户（出于安全考虑）
sudo useradd -m -s /bin/bash pykych
sudo usermod -aG www-data pykych

# 部署项目
sudo mkdir -p /opt/pykych
sudo chown -R pykych:pykych /opt/pykych
sudo -u pykych git clone <repo-url> /opt/pykych
```

### 3. 创建 Python 虚拟环境

```bash
sudo -u pykych python3 -m venv /opt/pykych/.venv
sudo -u pykych /opt/pykych/.venv/bin/pip install -e /opt/pykych
sudo -u pykych /opt/pykych/.venv/bin/pip install uvicorn
```

### 4. 配置 MySQL 数据库

> **如果数据库已存在（例如本地开发已在用同一远程数据库），可跳过此步骤，直接进入步骤 5。**

仅当 MySQL 在本机且首次部署时执行：

```sql
sudo mysql -u root

CREATE DATABASE IF NOT EXISTS pykych CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

-- 创建专用数据库用户
CREATE USER 'pykych'@'localhost' IDENTIFIED BY 'your_secure_password';
GRANT ALL PRIVILEGES ON pykych.* TO 'pykych'@'localhost';
FLUSH PRIVILEGES;
EXIT;
```

### 5. 配置 data/settings/db.yaml

```bash
# 如果沿用本地开发时的远程数据库，直接将本地的 data/settings/db.yaml 复制到服务器即可
# scp data/settings/db.yaml user@your-server:/opt/pykych/data/settings/db.yaml

# 如果数据库在服务器本机，则从示例创建
sudo -u pykych cp /opt/pykych/db.yaml.example /opt/pykych/data/settings/db.yaml
sudo -u pykych nano /opt/pykych/data/settings/db.yaml
```

示例配置：

```yaml
# 场景 A：远程数据库（本地开发已在用的同一数据库）
mysql:
  host: your-db-host.com     # 如 kych.net
  port: 3306
  user: pykych
  password: your_secure_password
  database: pykych
  charset: utf8mb4
  pool:
    minsize: 2
    maxsize: 20
    pool_recycle: 3600

# 场景 B：本地数据库
# mysql:
#   host: localhost
#   port: 3306
#   user: pykych
#   password: your_secure_password
#   ...
```

> **提示：** 使用远程数据库时，确保服务器防火墙允许出站到数据库端口 3306。可在服务器上测试连通性：`nc -zv your-db-host.com 3306`

### 6. 创建 systemd 服务

创建服务文件 `/etc/systemd/system/pykych.service`：

```bash
sudo nano /etc/systemd/system/pykych.service
```

```ini
[Unit]
Description=PyKYCH Personal Website
After=network.target
# 如果 MySQL 在本机，取消下一行注释：
# After=network.target mysql.service
# Wants=mysql.service

[Service]
Type=simple
User=pykych
Group=pykych
WorkingDirectory=/opt/pykych
Environment="PATH=/opt/pykych/.venv/bin"

# ── --host 参数说明 ──────────────────────────────────
# 127.0.0.1 → 仅本地访问（配合 Nginx 反代，最安全，推荐）
# 0.0.0.0   → 监听所有网卡（直连外部 / 同机容器访问 / 无 Nginx 时使用）
# 内网 IP   → 仅允许指定网段访问（如 10.0.0.5）
ExecStart=/opt/pykych/.venv/bin/uvicorn src.pykych.main:app \
    --host 127.0.0.1 \
    --port 8000 \
    --workers 4 \
    --log-level info
Restart=always
RestartSec=3

# 安全加固
NoNewPrivileges=yes
ProtectSystem=strict
ProtectHome=yes
ReadWritePaths=/opt/pykych/data /opt/pykych/src/pykych/static
PrivateTmp=yes

[Install]
WantedBy=multi-user.target
```

启动服务：

```bash
sudo systemctl daemon-reload
sudo systemctl enable pykych
sudo systemctl start pykych
sudo systemctl status pykych   # 确认运行正常
```

### 7. 配置 Nginx 反向代理

创建站点配置 `/etc/nginx/sites-available/pykych`：

```bash
sudo nano /etc/nginx/sites-available/pykych
```

```nginx
# HTTP → HTTPS 重定向
server {
    listen 80;
    server_name your-domain.com;

    # 静态资源由 Nginx 直接提供服务
    location /static/ {
        alias /opt/pykych/src/pykych/static/;
        expires 30d;
        add_header Cache-Control "public, immutable";
    }

    # 运行时数据（头像、主题 CSS 等）
    location /data/ {
        alias /opt/pykych/data/;
        expires 7d;
    }

    # 反向代理到 uvicorn
    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        # WebSocket 支持（如后续需要）
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";

        # 超时设置
        proxy_read_timeout 60s;
        proxy_send_timeout 60s;
    }
}
```

启用站点：

```bash
sudo ln -s /etc/nginx/sites-available/pykych /etc/nginx/sites-enabled/
sudo rm -f /etc/nginx/sites-enabled/default   # 删除默认站点

# 测试配置并重载
sudo nginx -t
sudo systemctl reload nginx
```

### 8. 配置 HTTPS（Certbot）

```bash
# 安装 certbot
sudo apt install -y certbot python3-certbot-nginx

# 自动获取证书并配置 HTTPS
sudo certbot --nginx -d your-domain.com

# 设置自动续期
sudo systemctl enable certbot.timer
```

完成后 Nginx 配置将自动更新为同时支持 HTTP 重定向和 HTTPS。

### 9. 生产环境安全检查清单

- [ ] 修改 `main.py` 中的 `SessionMiddleware` 密钥为随机字符串
- [ ] 修改默认管理员密码 (admin / admin123)
- [ ] 配置防火墙：`sudo ufw allow 22/tcp && sudo ufw allow 80/tcp && sudo ufw allow 443/tcp && sudo ufw enable`
- [ ] 若 MySQL 在本机，限制仅本地监听：编辑 `/etc/mysql/mysql.conf.d/mysqld.cnf`，设置 `bind-address = 127.0.0.1`
- [ ] 检查日志：`journalctl -u pykych -f`、`tail -f /var/log/nginx/access.log`

### 10. 更新部署

当本地开发完成后，按照以下步骤将最新代码部署到服务器。

#### 快速更新（日常小改动）

```bash
sudo -u pykych git -C /opt/pykych pull && sudo systemctl restart pykych
```

#### 完整更新流程

```bash
# 1. 拉取最新代码
sudo -u pykych git -C /opt/pykych pull

# 2. 更新依赖（每次建议执行，确保新增依赖也被安装）
sudo -u pykych /opt/pykych/.venv/bin/pip install -e /opt/pykych

# 3. 重启服务
sudo systemctl restart pykych

# 4. 验证服务状态
sudo systemctl status pykych
journalctl -u pykych -n 30 --no-pager
```

#### 不同场景的额外操作

| 场景 | 需要额外执行的操作 |
|------|-------------------|
| 数据库结构有变更 | 手动执行 SQL 迁移语句 |
| `data/settings/db.yaml` 有变动 | 参考 `db.yaml.example` 手动更新服务器上的配置 |
| `data/` 目录有新增内容 | 确保服务器上 `data/` 目录可写（插件、主题、头像等） |
| 仅修改了模板/静态资源 | 只需 `git pull`，无需重启服务（静态资源由 Nginx 直接代理） |
| 首次部署到新服务器 | 从第 1 步开始完整部署 |

### 11. 日常维护命令

```bash
# 查看服务状态
sudo systemctl status pykych
journalctl -u pykych -n 50 --no-pager

# 查看 Nginx 日志
sudo tail -f /var/log/nginx/access.log
sudo tail -f /var/log/nginx/error.log
```

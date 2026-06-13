# 跨越晨昏

基于 [LiHiL](https://pypi.org/project/lihil/) 异步 Web 框架构建的个人网站系统，支持多种内容类型。

## 项目简介

跨越晨昏 是一个使用 Python 编写的个人网站系统，支持 **Markdown / Wikidot / BBCode / HTML** 四种内容类型的发布与管理。系统内置用户认证、评论、标签、搜索、通知、文件管理及后台管理面板。

### 功能特性

**内容类型**
- 📝 **Markdown 文章** — GFM 表格、围栏代码块、目录、提示框等扩展语法
- 📚 **Wikidot Wiki** — 自研解析器，支持折叠块、代码高亮、上下标、锚点等
- 💬 **BBCode 文章** — 自研解析器，兼容论坛风格标记
- 🌐 **HTML 页面** — 原生 HTML 编写，支持从外部静态站抓取缓存

**交互功能**
- 🔍 **全文搜索** — 跨四种文章类型的全文内容检索
- 💬 **评论区** — 所有文章底部统一的评论系统
- 🏷️ **标签系统** — 文章标签管理，侧栏导航，标签聚合页
- 🔔 **通知系统** — 后台发布重要通知，首页醒目展示
- 🌙 **黑暗模式** — 纯白/纯黑双主题，跟随系统偏好

**管理后台**
- 📋 **文章管理** — 四种文章类型统一 CRUD
- 🏷️ **标签管理** — 可视化标签增删改，行内重命名
- 🏠 **主页管理** — 子站点链接、推荐文章、通知、外部站点管理
- 📁 **文件管理** — 图片/附件上传，链接复制
- 👥 **用户管理** — 三级角色（站长/管理员/用户），权限分级

**技术特性**
- PBKDF2-SHA256 密码哈希，Session 会话管理
- MySQL + aiomysql 异步连接池，单库统一架构
- Jinja2 模板引擎，响应式设计

## 项目架构

```
PyKYCH/
├── settings/
│   └── db.yaml                  # 数据库配置 (gitignored)
├── src/
│   └── pykych/
│       ├── main.py              # 应用入口
│       ├── auth.py              # 认证模块
│       ├── db.py                # Markdown 数据层
│       ├── wikidot_db.py        # Wikidot 数据层
│       ├── wikidot_parser.py    # Wikidot → HTML 解析器
│       ├── html_db.py           # HTML 数据层
│       ├── bbcode_db.py         # BBCode 数据层
│       ├── bbcode_parser.py     # BBCode → HTML 解析器
│       ├── tag_manager.py       # 标签管理
│       ├── comment_manager.py   # 评论管理
│       ├── site_settings.py     # 站点设置
│       ├── notification_manager.py  # 通知管理
│       ├── external_html.py     # 外部站点抓取缓存
│       ├── file_manager.py      # 静态文件管理
│       ├── mysql_manager.py     # 连接池 & 表初始化
│       ├── routes/
│       │   ├── auth.py          # /auth
│       │   ├── admin.py         # /admin
│       │   ├── md.py            # /md
│       │   ├── wikidot.py       # /wikidot
│       │   ├── html_route.py    # /html
│       │   ├── bbcode.py        # /bbcode
│       │   ├── labels.py        # /labels
│       │   ├── comments.py      # 评论提交
│       │   └── search.py        # /search
│       ├── templates/           # Jinja2 模板
│       └── static/              # CSS / JS / 上传文件
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
| `users` | 用户账号 |
| `tags` | 标签 |
| `article_tags` | 文章-标签关联 |
| `comments` | 评论 |
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
| 密码哈希 | hashlib PBKDF2-SHA256 | 标准库实现 |
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
cp db.yaml.example settings/db.yaml
```

编辑 `settings/db.yaml`：

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

### 5. 配置 settings/db.yaml

```bash
# 如果沿用本地开发时的远程数据库，直接将本地的 settings/db.yaml 复制到服务器即可
# scp settings/db.yaml user@your-server:/opt/pykych/settings/db.yaml

# 如果数据库在服务器本机，则从示例创建
sudo -u pykych cp /opt/pykych/db.yaml.example /opt/pykych/settings/db.yaml
sudo -u pykych nano /opt/pykych/settings/db.yaml
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
ReadWritePaths=/opt/pykych
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
| `settings/db.yaml` 有变动 | 参考 `db.yaml.example` 手动更新服务器上的配置 |
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

# 跨越晨昏

个人网站 Python 版 —— 基于 LiHiL 异步 Web 框架构建的轻量级内容管理系统。

## 项目简介

跨越晨昏 是一个使用 Python 编写的个人网站系统，支持 **Markdown 文章** 和 **Wikidot 风格 Wiki 页面** 的发布与管理。系统内置用户认证与后台管理面板，适合个人博客、技术笔记、知识库等场景。

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

CREATE DATABASE IF NOT EXISTS pykych_md CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE DATABASE IF NOT EXISTS pykych_wiki CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE DATABASE IF NOT EXISTS pykych_sys CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

-- 创建专用数据库用户
CREATE USER 'pykych'@'localhost' IDENTIFIED BY 'your_secure_password';
GRANT ALL PRIVILEGES ON pykych_md.* TO 'pykych'@'localhost';
GRANT ALL PRIVILEGES ON pykych_wiki.* TO 'pykych'@'localhost';
GRANT ALL PRIVILEGES ON pykych_sys.* TO 'pykych'@'localhost';
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
  markdown_db: pykych_md
  wikidot_db: pykych_wiki
  system_db: pykych_sys
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

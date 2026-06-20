# Bug 跟踪

## 🔴 严重 (Critical)

### BUG-001: 文件删除功能失效 — 使用了错误的字段构建路径
- **文件**: `content/files.py` 第 184 行
- **描述**: `delete_file()` 使用 `UPLOAD_DIR / file_info["filename"]` 构建文件路径，但 `filename` 只是 UUID 文件名（如 `abc123.png`），而 `UPLOAD_DIR` 已经是 `src/pykych/static/uploads/`。实际存储的 `file_path` 字段才是完整路径。当前代码会生成 `src/pykych/static/uploads/abc123.png`，但由于 `UPLOAD_DIR` 与保存时的路径一致，实际上这里碰巧能工作。**然而**，`get_file()` 返回的字段中 `file_path` 是完整路径，而 `filename` 只是 UUID 名。如果将来 `UPLOAD_DIR` 变更或路径结构改变，此处会静默失败。
- **修复建议**: 使用 `file_info["file_path"]` 代替 `UPLOAD_DIR / file_info["filename"]`。

### BUG-002: `_save_site_asset` 中 `logger` 导入路径错误
- **文件**: `routes/admin.py` 第 1177 行
- **描述**: `from .. import logger` 试图从 `src/pykych/__init__.py` 导入 `logger`，但 `__init__.py` 中并未定义 `logger` 对象。当 Logo/Favicon 上传过程中发生 `OSError` 时，会触发 `ImportError`，导致异常处理本身也抛出异常，最终返回 500 错误且无任何日志输出。
- **修复建议**: 改为 `import logging; logger = logging.getLogger(__name__)`，或从 `auth/profile.py` 中复用 logger。

### BUG-003: 修改密码的最低长度校验不一致（安全漏洞）
- **文件**: `auth/profile.py` 第 148 行
- **描述**: `change_password()` 仅要求新密码 ≥ 6 个字符，但 `password.py` 中的 `validate_password_strength()` 要求 ≥ 8 个字符 + 大小写字母 + 数字。通过「修改密码」路径设置的密码可以绕过强度校验（6-7 字符的弱密码可被设置），而通过「创建用户」路径则不行。
- **修复建议**: 在 `change_password()` 中调用 `validate_password_strength(new_password)` 替代自定义的 6 字符检查。

### BUG-004: 上传文件删除使用错误路径（静默失败）
- **文件**: `content/files.py` 第 184 行
- **描述**: `delete_file()` 中 `file_path = UPLOAD_DIR / file_info["filename"]`。`file_info["filename"]` 是 UUID 名（如 `abc123.png`），拼接后为 `src/pykych/static/uploads/abc123.png`。但数据库存储的 `file_path` 字段已经是完整绝对路径。如果 `UPLOAD_DIR` 在部署中与存储路径不一致（如 Docker 挂载不同），删除将静默失败（`file_path.exists()` 返回 False 但不报错），导致磁盘空间泄漏。
- **实际影响**: 在当前默认配置下碰巧能工作，但属于脆弱代码。
- **修复建议**: 直接使用 `file_path = Path(file_info["file_path"])`。

---

## 🟠 高 (High)

### BUG-005: `posts_per_page` 设置转换无错误处理
- **文件**: `routes/admin.py` 第 1144 行
- **描述**: `int(form.get("posts_per_page", "10"))` 在用户输入非数字字符串（如空字符串、字母）时会抛出 `ValueError`，导致 500 错误页面。
- **修复建议**: 用 `try/except ValueError` 包裹，回退到默认值 10。

### BUG-006: WebAuthn `rp_id` 在生产环境可能不匹配
- **文件**: `routes/auth.py` 第 76-85 行
- **描述**: `_get_rp_config()` 从 `Host` 请求头提取 `rp_id`，并假设非 localhost 使用 HTTPS。但在反向代理（Nginx）后面时，`Host` 头可能包含端口号或不反映真实协议。更关键的是，如果生产环境使用 `https://example.com`，但 `X-Forwarded-Proto` 未被检查，`origin` 可能被错误设为 `https://example.com:443`，导致 WebAuthn 断言验证失败。
- **修复建议**: 检查 `X-Forwarded-Proto` 和 `X-Forwarded-Host` 头，或允许配置 `rp_id` 和 `origin`。

### BUG-007: COSE 密钥坐标填充方向错误
- **文件**: `auth/webauthn.py` 第 234-235 行
- **描述**: `x.rjust(32, b"\x00")` 在 Python `bytes` 上是在**左侧**填充零字节。对于大端编码的 P-256 坐标，这在数学上是正确的（高位补零）。但 `rjust` 的语义是"右对齐"，即填充在左侧——这对无符号大端整数是正确的。然而，如果坐标已经超过 32 字节（如 33 字节），`x[:32]` 会截断**高位**字节，导致坐标值完全错误。
- **实际影响**: 某些 authenticator 可能生成带前导零的 33 字节坐标，截断高位会导致公钥无效，签名验证永远失败。
- **修复建议**: 使用 `x.ljust(32, b"\x00")[:32]` 或更安全的 `x[-32:].rjust(32, b"\x00")`。

### BUG-008: 搜索功能在大数据量下性能问题
- **文件**: `routes/search.py` 第 68-88 行
- **描述**: 搜索使用 `LIKE %keyword%` 跨四张表 `UNION ALL` 查询，无法利用索引。当文章数量增长时，每次搜索都会全表扫描四张表。且所有结果先全部加载到内存（`fetchall()`），再在 Python 中分页，浪费内存和带宽。
- **修复建议**: 使用 `LIMIT` + `OFFSET` 在 SQL 层面分页，或引入全文索引 / 搜索引擎。

### BUG-009: 外部 HTML 抓取的正则表达式无法处理嵌套标签
- **文件**: `content/external.py` 第 213 行
- **描述**: `_extract_body()` 策略 2 使用 `<div[^>]*class=...>(.*?)</div>` 匹配内容容器。正则 `.*?` 会在遇到**第一个** `</div>` 时停止匹配，如果内容容器内有嵌套的 `<div>`（非常常见），只会提取到部分内容。
- **修复建议**: 使用 HTML 解析库（如 `html.parser` 或 `lxml`）替代正则表达式。

---

## 🟡 中 (Medium)

### BUG-010: 数据库配置文件在模块导入时立即读取
- **文件**: `core/db.py` 第 27-28 行
- **描述**: `with open(CONFIG_PATH, "r") as f` 在模块级别执行。如果 `db.yaml` 不存在或格式错误，整个应用无法导入模块，无法给出友好的错误提示。在 Docker 部署中，如果配置文件挂载延迟，会导致启动失败。
- **修复建议**: 将配置读取移入函数内（惰性加载），或在 `try/except` 中包裹并提供明确的错误消息。

### BUG-011: Markdown 解析器全局实例的线程安全问题
- **文件**: `routes/md.py` 第 41-55 行
- **描述**: `md_parser = Markdown(...)` 是模块级全局实例。虽然每次调用 `md_parser.reset().convert()`，但在高并发下，多个协程可能同时调用 `reset()` 和 `convert()`，导致解析器内部状态混乱，渲染出错误的 HTML。
- **修复建议**: 每次请求创建新的 `Markdown` 实例，或使用 `asyncio.Lock()` 保护。

### BUG-012: `list_featured_articles` 可能耗尽连接池
- **文件**: `core/site_settings.py` 第 107-110 行
- **描述**: 先获取连接读取 `featured_articles` 表，释放连接后，对每个推荐文章调用 `_get_article_title_by_pool()`，该函数每次从池中获取新连接。如果有 N 个推荐文章，就需要 N 次额外的连接获取。当连接池 `maxsize=10` 且推荐文章较多时，可能导致连接池耗尽。
- **修复建议**: 使用单次 JOIN 查询获取所有推荐文章的标题，避免 N+1 查询。

### BUG-013: 示例插件的导入路径错误
- **文件**: `plugins_sys/manager.py` 第 431 行
- **描述**: 示例插件代码中 `from src.pykych.plugin_manager import register_hook, Hooks` 引用了不存在的模块 `plugin_manager`（实际为 `plugins_sys.manager`），且使用了绝对导入 `src.pykych`，在 `data/` 目录的 `sys.path` 上下文中不可用。
- **修复建议**: 改为 `from pykych.plugins_sys.manager import register_hook, Hooks` 或使用相对导入。

### BUG-014: 登出使用 GET 方法（CSRF 风险）
- **文件**: `routes/auth.py` 第 203 行
- **描述**: `/auth/logout` 使用 GET 请求执行登出操作。虽然当前没有 CSRF Token 保护，但 GET 请求可被浏览器预取、图片标签、链接嵌入等方式触发。攻击者可以在恶意页面嵌入 `<img src="/auth/logout">` 导致用户被登出。
- **修复建议**: 改为 POST 请求，并添加 CSRF Token 验证。

### BUG-015: 速率限制数据仅存储在内存中
- **文件**: `auth/rate_limit.py` 第 44-47 行
- **描述**: `_failure_records` 和 `_lockout_records` 使用模块级字典存储。在多进程部署（如多个 Uvicorn worker）下，每个进程有独立的速率限制状态，攻击者可以通过轮询不同连接绕过限制。此外，进程重启后所有记录丢失。
- **修复建议**: 使用 Redis 或数据库存储速率限制数据。

---

## 🔵 低 (Low)

### BUG-016: `__init__.py` 文件使用空字符串而非 docstring
- **文件**: `src/pykych/__init__.py` 第 1 行, `routes/__init__.py` 第 1 行
- **描述**: `""` 是一个无效的字符串表达式，不是 docstring。虽然不会报错，但无实际意义，且 IDE 可能给出警告。
- **修复建议**: 改为模块级 docstring 或移除。

### BUG-017: 硬编码的管理员密码
- **文件**: `main.py` 第 73 行
- **描述**: `await seed_admin("admin", "admin123", "管理员")` 使用硬编码的默认密码。虽然生产环境应该修改，但代码中没有强制修改的机制或启动时警告。`admin123` 不满足 `validate_password_strength` 的要求（缺少大写字母），但 `seed_admin` 绕过了强度校验直接哈希存储。
- **修复建议**: 在启动日志中输出警告，或要求首次登录时强制修改密码。

---

## 📊 统计

| 严重程度 | 数量 |
|----------|------|
| 🔴 严重  | 4    |
| 🟠 高    | 4    |
| 🟡 中    | 4    |
| 🔵 低    | 3    |
| **总计** | **15** |

# 安全

## 🔴 严重 (Critical) — 可被远程利用，直接造成数据泄露或系统被控制

### SEC-001: 静态文件服务存在路径遍历漏洞 (Path Traversal)
- **文件**: `main.py` 第 486-491 行、第 500-506 行、第 519-529 行
- **漏洞类型**: CWE-22 Path Traversal
- **描述**: 三个静态文件服务端点 (`serve_upload`, `serve_static_img`, `serve_avatar`) 直接将 URL 路径参数拼接到文件路径中，**未对 `..` 做任何过滤或路径规范化**。攻击者可通过构造 `../` 序列读取服务器上的任意文件。
- **攻击示例**: `GET /static/uploads/../../settings/db.yaml → 读取数据库配置（含密码） GET /static/uploads/../../../data/settings/db.yaml → 同上 GET /static/avatars/../../settings/db.yaml → 同上 GET /static/img/../../settings/db.yaml → 同上`
- **影响**: 攻击者可读取服务器上任意文件（数据库凭据、源代码、系统配置文件等），造成完全信息泄露。
- **代码分析**: main.py L486-491 — 三个端点均存在相同问题: async def serve_upload(filename: str): file_path = UPLOAD_DIR / filename # filename 可为 "../../etc/passwd" if not file_path.exists() or not file_path.is_file(): return HTMLResponse("<p>文件不存在</p>", status_code=404) return FileResponse(str(file_path)) # 直接返回文件内容
- **修复建议**: 使用 `_safe_resolve()` 辅助函数统一处理所有静态文件服务端点，检查 `..` 和路径分隔符，确保解析后路径在基础目录内。
- **状态**: ✅ 已修复

---

## 🆕 本轮测试新发现 (2026-06-18)

### 🔴 BUG-021: 文章删除后 `article_tags` 孤立记录未清理（数据一致性）
- **文件**: `content/articles.py` 第 255-270 行
- **描述**: `delete_article()` 仅删除文章表记录，不级联删除 `article_tags`、`comments`、`ratings`、`line_comments` 等关联表。实测发现 32 条 `article_tags` 中有 15 条（47%）指向已删除文章。导致标签列表计数不准确（如 "upsert" 标签显示 1 篇但实际 0 篇可见）。
- **影响**: 标签计数虚高、幽灵标签残留、`get_articles_by_tag()` 返回 total 值与实际显示文章数不一致。
- **修复建议**: 在 `delete_article()` 中增加级联删除：`comments` → `ratings` → `line_comments` → `article_tags`；同时修复 `get_all_tags_with_counts()` 和 `get_articles_by_tag()` 使用 EXISTS 子查询验证文章真实存在。
- **状态**: ✅ 已修复（`articles.py` + `tags.py` + 启动清理 + 手动清理历史数据）

### 🔴 BUG-022: `delete_user()` 无级联删除
- **文件**: `auth/user.py` 第 251-265 行
- **描述**: `delete_user()` 仅执行 `DELETE FROM users WHERE username = %s`，不级联清理用户相关的所有数据：评论 (`comments`)、评分 (`ratings`)、行评论 (`line_comments`)、文章 (`articles` / `pages` / `html_pages` / `bbcode_pages`)、标签关联 (`article_tags`)、通行密钥 (`webauthn_credentials`)、通知 (`notifications`)、上传文件 (`static_files`) 等。与 BUG-021 类型相同。
- **影响**: 删除用户后遗留大量孤立数据，数据库膨胀，且可能存在隐私合规风险（用户删除了但评论仍保留其用户名）。
- **状态**: ✅ 已修复（级联删除 8 张关联表）

### 🟠 BUG-023: 登录 `next` 参数未验证（开放重定向漏洞）
- **文件**: `routes/auth.py` 第 206 行
- **描述**: 登录成功后的跳转地址直接使用 `request.query_params.get("next", "/admin")`，未验证 URL 是否为本域名下的安全路径。攻击者可构造 `/auth/login?next=https://evil.com/phishing` 进行钓鱼攻击，用户登录后被重定向到恶意网站。
- **影响**: CWE-601 URL Redirection to Untrusted Site ('Open Redirect')。可用于社会工程攻击，诱导用户相信他们仍在合法站点。
- **状态**: ✅ 已修复（校验 next_url 必须以 / 开头且不含 // 和 @）

### 🟡 BUG-024: 仪表盘每次加载所有文章数据（性能隐患）
- **文件**: `routes/admin.py` 第 103-105 行
- **描述**: 仪表盘页面 `dashboard()` 对 4 种文章类型各执行 `list_articles(page=1, per_page=100)`，每次加载最多 400 篇文章的全部内容字段（`content` 字段通常包含大量 HTML/Markdown 文本）。随着文章增长，此查询将严重拖慢后台首页加载速度。
- **实际影响**: 当前文章量少时无影响，但随着内容增长会线性变慢。
- **状态**: ✅ 已修复（per_page 从 100 降至 20；list_cols 已排除 content 字段）

### 🔵 BUG-025: 行评论 `content[:20]` 截断无警告
- **文件**: `content/comments.py` 第 246 行 (`content = content.strip()[:20]`)
- **描述**: 行评论内容静默截断至 20 字符，前端和后端均无任何长度提示。用户输入 50 字仅保存前 20 字，造成信息丢失且无反馈。
- **状态**: ✅ 已修复（前端 maxlength=20 + 实时字符计数器 X/20）

### 🔵 BUG-026: `_save_site_asset` 函数在模块顶层被重复定义
- **文件**: `routes/admin.py` 第 1152 行附近
- **描述**: `_save_site_asset()` 定义在 `admin.py` 模块级别但仅被站点设置路由使用，且内部使用的 `STATIC_IMG` 路径硬编码为相对于 `__file__`。如果将来 admin.py 拆分或重构，此函数可能失去正确上下文。
- **修复建议**: 将 `_save_site_asset` 提取到 `content/files.py` 或独立的工具模块中。

---

## 📊 更新统计

| 严重程度 | 原有 | 新增 | 小计 | 状态 |
|----------|------|------|------|------|
| 🔴 严重  | 4    | +2   | 6    | ✅ 全部已修复 |
| 🟠 高    | 5    | +1   | 6    | ✅ 全部已修复 |
| 🟡 中    | 6    | +1   | 7    | ✅ 全部已修复 |
| 🔵 低    | 5    | +2   | 7    | ✅ 全部已修复 |
| **总计** | **20** | **+6** | **26** | ✅ **26/26** |

| 状态 | 数量 |
|------|------|
| ✅ 已修复 | 26 (BUG-001~025 + SEC-001) |
| ⬜ 待修复 | 0 |

# 新bug

| 状态 | 数量 |
|------|------|
| ✅ 已修复 | 26 (BUG-001~025 + SEC-001) |
| ⬜ 待修复 | 0 |

## 🔴 严重 (Critical)

### BUG-027: 评论提交后 `redirect_url` 开放重定向漏洞
- **文件**: `routes/comments.py` 第 28-32 行
- **漏洞类型**: CWE-601 Open Redirect
- **描述**: 评论提交后，`redirect_url` 直接从表单数据取值并跳转，**未做任何安全校验**。攻击者可以构造恶意表单，让用户评论后被重定向到钓鱼网站。
- **代码分析**: 虽然 `login` 路由已修复了开放重定向（BUG-023），但评论路由遗漏了同样的校验。
- **修复建议**: 校验 `redirect_url` 必须以 `/` 开头，且不含 `//` 和 `@`：
- **状态**: ⬜ 待修复

### BUG-028: 管理后台所有 POST 路由缺少 CSRF Token 验证
- **文件**: `routes/admin.py` 全文
- **漏洞类型**: CWE-352 Cross-Site Request Forgery
- **描述**: 仅 `login` 路由实现了 CSRF Token 验证。管理后台的**所有** POST 操作（新建/编辑/删除文章、用户管理、站点设置、文件上传等 30+ 个端点）均无 CSRF 防护。虽然 Session Cookie 设置了 `SameSite=Lax`，但：
  1. CSRF 防御不应仅依赖 Cookie 属性（defense-in-depth 原则）
  2. 旧版浏览器可能不支持 `SameSite`
  3. 某些网络场景下 `SameSite` 可能被绕过
- **影响**: 攻击者可构造恶意页面，诱导已登录管理员点击链接后执行管理操作（如删除文章、创建用户等）。
- **修复建议**: 实现一个 CSRF 验证中间件或装饰器，对所有 POST 请求统一验证。
- **状态**: ⬜ 待修复

## 🟠 高 (High)

### BUG-029: `delete_user()` 未清理 `typst_pages` 表
- **文件**: `auth/user.py` 第 308 行
- **描述**: `delete_user()` 级联删除时遍历的文章表为 `("articles", "pages", "html_pages", "bbcode_pages")`，**遗漏了 `typst_pages` 表**。删除用户后，该用户的 Typst 文章会成为孤立数据。
- **修复建议**: 将 `"typst_pages"` 加入删除循环：
- **状态**: ⬜ 待修复

### BUG-030: `delete_user()` 未清理 `featured_articles` 表
- **文件**: `auth/user.py` 第 251-322 行
- **描述**: 用户删除时未清理 `featured_articles` 表。如果用户的文章被推荐到首页，删除用户后这些推荐记录仍然存在，指向已删除的文章。
- **修复建议**: 在级联删除中增加对 `featured_articles` 表的清理。
- **状态**: ⬜ 待修复

## 🟡 中 (Medium)

### BUG-033: `set_setting()` 存在读-改-写竞态条件
- **文件**: `core/settings.py` 第 177-198 行
- **描述**: `set_setting()` 先调用 `load_settings()` 读取全量配置，修改后调用 `save_settings()` 写回。`_write_lock` 只保护了写入操作，但**读取-修改-写入**整个过程不是原子的。两个并发请求可能同时读取同一版本，各自修改不同字段后写入，导致其中一个修改丢失。
- **修复建议**: 将 `_write_lock` 的范围扩大到覆盖整个读-改-写流程。
- **状态**: ⬜ 待修复

### BUG-034: `get_setting()` 每次调用都读取文件 — 性能问题
- **文件**: `core/settings.py` 第 147-174 行
- **描述**: 每次 `get_setting()` 都调用 `load_settings()` → `_ensure_settings_file()` → `open()` → `yaml.safe_load()`。每次页面渲染会调用多次 `get_setting()`（模板中的 `site_title_func()`、`site_subtitle_func()`、`site_logo`、`site_favicon` 等），导致大量冗余磁盘 I/O。
- **修复建议**: 添加内存缓存 + 过期机制（TTL），或在应用启动时加载一次，修改时更新缓存。
- **状态**: ⬜ 待修复

### BUG-035: 文件上传无磁盘写入错误处理
- **文件**: `routes/admin.py` 第 945-946 行
- **描述**: 文件上传时直接 `open(file_path, "wb")` 写入，无 `try/except` 包裹。如果磁盘满、权限不足或目录不存在，会抛出未捕获的 `OSError`，导致 500 错误页。
- **修复建议**:
- **状态**: ⬜ 待修复

### BUG-036: `asyncio.create_task()` 后台任务异常无日志
- **文件**: `routes/admin.py` 第 198, 274, 311 行; `routes/typst_route.py` 第 98, 150 行
- **描述**: Typst 编译使用 `asyncio.create_task()` 在后台执行，但返回的 Task 对象被丢弃。如果任务抛出异常，只会在事件循环的 `task_destroyed` 回调中打印一个警告，很容易被忽略。如果事件循环在任务完成前关闭，任务会被静默取消。
- **修复建议**: 保存 Task 引用并添加异常回调：
- **状态**: ⬜ 待修复

## 🔵 低 (Low)

### BUG-037: `delete_user()` 级联删除无事务保护
- **文件**: `auth/user.py` 第 271-322 行
- **描述**: `delete_user()` 执行 8+ 条 DELETE 语句，但没有使用数据库事务。如果中途某条语句失败（如网络中断），部分数据已删除、部分未删除，造成数据不一致。虽然 `aiomysql` 默认 `autocommit=True`，但这里需要显式事务来保证原子性。
- **修复建议**: 使用 `async with conn.begin()` 包裹所有删除操作。
- **状态**: ⬜ 待修复

### BUG-038: `main.py` 中 `seed_admin` 后重复导入 `logging`
- **文件**: `main.py` 第 86 行
- **描述**: 模块顶部（第 22 行）已 `import logging`，但 `lifespan()` 函数内部又 `import logging`，且用 `logging.getLogger(__name__)` 而非已定义的 `logger`。虽然功能正确，但属于冗余代码。
- **修复建议**: 直接使用模块级 `logger`。
- **状态**: ⬜ 待修复

---

## 📊 最终统计

| 严重程度 | 原有 | 上轮新增 | 本轮新增 | 小计 | 状态 |
|----------|------|----------|----------|------|------|
| 🔴 严重  | 4    | +2       | +2       | 8    | 6 ✅ / 2 ⬜ |
| 🟠 高    | 5    | +1       | +4       | 10   | 6 ✅ / 4 ⬜ |
| 🟡 中    | 6    | +1       | +4       | 11   | 7 ✅ / 4 ⬜ |
| 🔵 低    | 5    | +2       | +3       | 10   | 7 ✅ / 3 ⬜ |
| **总计** | **20** | **+6** | **+13** | **39** | **26 ✅ / 13 ⬜** |

| 状态 | 数量 |
|------|------|
| ✅ 已修复 | 26 (BUG-001~025 + SEC-001) |
| ⬜ 待修复 | 13 (BUG-027~039) |

  
  
  
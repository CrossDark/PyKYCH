# Auth 认证模块

用户认证、会话管理、密码安全的完整后端实现。

## 🔒 安全特性

| 特性 | 说明 |
|------|------|
| **密码哈希** | PBKDF2-HMAC-SHA256，60 万次迭代（OWASP 2025 推荐） |
| **恒定时间比较** | `hmac.compare_digest` 防时序侧信道攻击 |
| **Session 管理** | 登录时重新生成会话 ID，防会话固定攻击 |
| **速率限制** | 基于用户名+IP 的组合限流（5 次/分钟），连续 10 次失败锁定 15 分钟 |
| **CSRF 保护** | 使用 itsdangerous 签名的 CSRF Token，恒定时间验证 |
| **密码强度** | 最少 8 字符，含大小写字母 + 数字，无空白字符 |
| **NFC 规范化** | Unicode 密码在平台间一致处理 |
| **WebAuthn** | 通行密钥（Passkey）注册与认证，支持 ECDSA |

## 模块结构

| 文件 | 说明 |
|------|------|
| `__init__.py` | 公开接口导出 |
| `password.py` | 密码哈希、验证、强度校验 |
| `session.py` | 会话管理（登录/登出/CSRF/权限检查） |
| `user.py` | 用户 CRUD（增删改查、角色管理） |
| `rate_limit.py` | 登录速率限制（内存实现，支持扩展 Redis） |
| `webauthn.py` | WebAuthn/Passkey 通行密钥 |

## 使用示例

```python
from pykych.auth.password import hash_password, verify_password
from pykych.auth.session import login_user, logout_user, get_current_user
from pykych.auth.user import create_user, list_users, is_admin

# 密码校验
from pykych.auth.password import validate_password_strength
error = validate_password_strength("MyPass123")
if error:
    print(f"密码强度不足: {error}")

# 登录流程（在路由中）
user = await get_current_user(request)
if not user:
    # 检查速率限制
    allowed, msg = check_login_rate_limit(username, client_ip)
    if not allowed:
        return error(msg)
    # 验证密码...
    await login_user(request, username)
```

## 速率限制策略

| 限制 | 阈值 | 窗口 |
|------|------|------|
| 用户+IP 失败 | 5 次 | 60 秒 |
| 全局 IP 失败 | 20 次 | 60 秒 |
| 锁定期 | 连续 10 次失败 | 15 分钟 |

登录成功后自动重置失败计数。

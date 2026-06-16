"""
登录速率限制模块 — 防止暴力破解攻击。

策略:
    - 基于用户名 + IP 地址的组合进行限制
    - 默认：每用户名+IP 组合 5 次/分钟（失败尝试）
    - 默认：每 IP 地址 20 次/分钟（全局限制）
    - 使用内存存储（生产环境建议接入 Redis）
    - 锁定期：连续失败 10 次后锁定 15 分钟

用法:
    from .rate_limit import check_login_rate_limit, reset_login_rate_limit

    # 登录尝试前检查
    allowed, msg = check_login_rate_limit(username, client_ip)
    if not allowed:
        return error(msg)

    # 登录成功后重置
    reset_login_rate_limit(username, client_ip)
"""

import time
import threading
from collections import defaultdict


# ── 配置 ────────────────────────────────────────────────────

# 每用户名+IP 组合最大失败次数（每分钟）
_MAX_FAILURES_PER_USER_IP = 5
# 每 IP 地址最大失败次数（每分钟）
_MAX_FAILURES_PER_IP = 20
# 速率限制窗口（秒）
_WINDOW_SECONDS = 60
# 锁定期：连续失败多少次后触发锁定
_LOCKOUT_THRESHOLD = 10
# 锁定时长（秒）
_LOCKOUT_DURATION = 15 * 60  # 15 分钟


# ── 内存存储 ────────────────────────────────────────────────

# 存储结构: {key: [(timestamp, count), ...]}
_failure_records: dict[str, list[tuple[float, int]]] = defaultdict(list)
# 锁定期记录: {key: lockout_end_timestamp}
_lockout_records: dict[str, float] = {}

# 线程安全锁
_lock = threading.Lock()


def _clean_old_records(key: str) -> None:
    """清除超过时间窗口的旧记录。"""
    now = time.time()
    cutoff = now - _WINDOW_SECONDS
    _failure_records[key] = [
        (ts, cnt) for ts, cnt in _failure_records[key] if ts > cutoff
    ]


def check_login_rate_limit(username: str, client_ip: str) -> tuple[bool, str]:
    """
    检查是否允许登录尝试。

    参数:
        username:  尝试登录的用户名
        client_ip: 客户端 IP 地址

    返回:
        (allowed, message) — allowed 为 True 表示允许尝试，
        message 在拒绝时包含原因说明
    """
    now = time.time()
    user_key = f"user:{username}:{client_ip}"
    ip_key = f"ip:{client_ip}"
    lockout_key = f"lockout:{username}:{client_ip}"

    with _lock:
        # 1. 检查是否处于锁定期
        lockout_end = _lockout_records.get(lockout_key, 0)
        if now < lockout_end:
            remaining = int(lockout_end - now)
            minutes = remaining // 60
            seconds = remaining % 60
            return False, (
                f"由于多次登录失败，该账号已暂时锁定。"
                f"请在 {minutes} 分 {seconds} 秒后重试。"
            )

        # 2. 检查全局 IP 限制
        _clean_old_records(ip_key)
        ip_failures = sum(cnt for _, cnt in _failure_records[ip_key])
        if ip_failures >= _MAX_FAILURES_PER_IP:
            return False, (
                f"来自该 IP 的登录尝试过于频繁，请稍后重试。"
            )

        # 3. 检查用户+IP 限制
        _clean_old_records(user_key)
        user_failures = sum(cnt for _, cnt in _failure_records[user_key])
        if user_failures >= _MAX_FAILURES_PER_USER_IP:
            return False, (
                f"该账号登录尝试过于频繁，请稍后重试。"
            )

        # 允许尝试
        return True, ""


def record_login_failure(username: str, client_ip: str) -> None:
    """
    记录一次登录失败。

    此函数应在密码验证失败后调用。

    参数:
        username:  登录失败的用户名
        client_ip: 客户端 IP 地址
    """
    now = time.time()
    user_key = f"user:{username}:{client_ip}"
    ip_key = f"ip:{client_ip}"
    lockout_key = f"lockout:{username}:{client_ip}"

    with _lock:
        _clean_old_records(user_key)
        _clean_old_records(ip_key)

        # 记录用户+IP 失败
        _failure_records[user_key].append((now, 1))
        # 记录 IP 失败
        _failure_records[ip_key].append((now, 1))

        # 检查是否触发锁定
        user_failures = sum(cnt for _, cnt in _failure_records[user_key])
        if user_failures >= _LOCKOUT_THRESHOLD:
            _lockout_records[lockout_key] = now + _LOCKOUT_DURATION


def reset_login_rate_limit(username: str, client_ip: str) -> None:
    """
    重置登录失败计数（登录成功后调用）。

    参数:
        username:  成功登录的用户名
        client_ip: 客户端 IP 地址
    """
    user_key = f"user:{username}:{client_ip}"
    lockout_key = f"lockout:{username}:{client_ip}"

    with _lock:
        _failure_records.pop(user_key, None)
        _lockout_records.pop(lockout_key, None)

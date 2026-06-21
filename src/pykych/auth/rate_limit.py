"""
登录速率限制模块 — 防止暴力破解攻击。

策略:
    - 基于用户名 + IP 地址的组合进行限制
    - 默认：每用户名+IP 组合 5 次/分钟（失败尝试）
    - 默认：每 IP 地址 20 次/分钟（全局限制）
    - 可插拔后端：MemoryRateLimitBackend / RedisRateLimitBackend
    - 锁定期：连续失败 10 次后锁定 15 分钟

用法:
    from .rate_limit import check_login_rate_limit, reset_login_rate_limit

    # 登录尝试前检查
    allowed, msg = check_login_rate_limit(username, client_ip)
    if not allowed:
        return error(msg)

    # 登录成功后重置
    reset_login_rate_limit(username, client_ip)

后端切换:
    通过环境变量 PYKYCH_RATE_LIMIT_BACKEND 切换:
        - 'memory'（默认）: 内存存储，适合单进程部署
        - 'redis': Redis 存储，适合多进程/分布式部署
"""

import os
import time
import threading
import abc
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


# ═══════════════════════════════════════════════════════════════
#  速率限制后端抽象
# ═══════════════════════════════════════════════════════════════

class RateLimitBackend(abc.ABC):
    """
    速率限制后端抽象基类。

    子类必须实现以下方法:
        - check_allowed(username, client_ip) -> tuple[bool, str]
        - record_failure(username, client_ip) -> None
        - reset(username, client_ip) -> None
    """

    @abc.abstractmethod
    def check_allowed(self, username: str, client_ip: str) -> tuple[bool, str]:
        """
        检查是否允许登录尝试。

        返回:
            (allowed, message) — allowed 为 True 表示允许尝试
        """
        ...

    @abc.abstractmethod
    def record_failure(self, username: str, client_ip: str) -> None:
        """记录一次登录失败。"""
        ...

    @abc.abstractmethod
    def reset(self, username: str, client_ip: str) -> None:
        """重置登录失败计数（登录成功后调用）。"""
        ...


# ═══════════════════════════════════════════════════════════════
#  内存后端实现（默认）
# ═══════════════════════════════════════════════════════════════

class MemoryRateLimitBackend(RateLimitBackend):
    """
    内存存储速率限制后端。

    使用进程内字典存储，适合单进程部署。
    多进程部署时各进程独立计数，需要使用 RedisRateLimitBackend。
    """

    def __init__(self):
        # 存储结构: {key: [(timestamp, count), ...]}
        self._failure_records: dict[str, list[tuple[float, int]]] = defaultdict(list)
        # 锁定期记录: {key: lockout_end_timestamp}
        self._lockout_records: dict[str, float] = {}
        # 线程安全锁
        self._lock = threading.Lock()

    def _clean_old_records(self, key: str) -> None:
        """清除超过时间窗口的旧记录。"""
        now = time.time()
        cutoff = now - _WINDOW_SECONDS
        self._failure_records[key] = [
            (ts, cnt) for ts, cnt in self._failure_records[key] if ts > cutoff
        ]

    def check_allowed(self, username: str, client_ip: str) -> tuple[bool, str]:
        now = time.time()
        user_key = f"user:{username}:{client_ip}"
        ip_key = f"ip:{client_ip}"
        lockout_key = f"lockout:{username}:{client_ip}"

        with self._lock:
            # 1. 检查是否处于锁定期
            lockout_end = self._lockout_records.get(lockout_key, 0)
            if now < lockout_end:
                remaining = int(lockout_end - now)
                minutes = remaining // 60
                seconds = remaining % 60
                return False, (
                    f"由于多次登录失败，该账号已暂时锁定。"
                    f"请在 {minutes} 分 {seconds} 秒后重试。"
                )

            # 2. 检查全局 IP 限制
            self._clean_old_records(ip_key)
            ip_failures = sum(cnt for _, cnt in self._failure_records[ip_key])
            if ip_failures >= _MAX_FAILURES_PER_IP:
                return False, (
                    f"来自该 IP 的登录尝试过于频繁，请稍后重试。"
                )

            # 3. 检查用户+IP 限制
            self._clean_old_records(user_key)
            user_failures = sum(cnt for _, cnt in self._failure_records[user_key])
            if user_failures >= _MAX_FAILURES_PER_USER_IP:
                return False, (
                    f"该账号登录尝试过于频繁，请稍后重试。"
                )

            # 允许尝试
            return True, ""

    def record_failure(self, username: str, client_ip: str) -> None:
        now = time.time()
        user_key = f"user:{username}:{client_ip}"
        ip_key = f"ip:{client_ip}"
        lockout_key = f"lockout:{username}:{client_ip}"

        with self._lock:
            self._clean_old_records(user_key)
            self._clean_old_records(ip_key)

            # 记录用户+IP 失败
            self._failure_records[user_key].append((now, 1))
            # 记录 IP 失败
            self._failure_records[ip_key].append((now, 1))

            # 检查是否触发锁定
            user_failures = sum(cnt for _, cnt in self._failure_records[user_key])
            if user_failures >= _LOCKOUT_THRESHOLD:
                self._lockout_records[lockout_key] = now + _LOCKOUT_DURATION

    def reset(self, username: str, client_ip: str) -> None:
        user_key = f"user:{username}:{client_ip}"
        lockout_key = f"lockout:{username}:{client_ip}"

        with self._lock:
            self._failure_records.pop(user_key, None)
            self._lockout_records.pop(lockout_key, None)


# ═══════════════════════════════════════════════════════════════
#  Redis 后端（预留）
# ═══════════════════════════════════════════════════════════════

class RedisRateLimitBackend(RateLimitBackend):
    """
    Redis 存储速率限制后端。

    适合多进程/分布式部署，确保跨进程一致的速率限制。

    使用方式:
        需要安装 redis-py: pip install redis
        设置环境变量:
            PYKYCH_RATE_LIMIT_BACKEND=redis
            REDIS_URL=redis://localhost:6379/0

    注意: 此为预留接口，需要安装 redis 依赖后方可使用。
    """

    def __init__(self, redis_url: str | None = None):
        self._redis_url = redis_url or os.environ.get("REDIS_URL", "redis://localhost:6379/0")
        self._redis = None

    def _get_redis(self):
        """惰性连接 Redis。"""
        if self._redis is None:
            try:
                import redis
                self._redis = redis.from_url(self._redis_url)
            except ImportError:
                raise ImportError(
                    "使用 RedisRateLimitBackend 需要安装 redis 包: pip install redis"
                ) from None
        return self._redis

    def check_allowed(self, username: str, client_ip: str) -> tuple[bool, str]:
        raise NotImplementedError(
            "RedisRateLimitBackend 尚未完全实现。"
            "请使用 MemoryRateLimitBackend 或安装 redis 后自行实现。"
        )

    def record_failure(self, username: str, client_ip: str) -> None:
        raise NotImplementedError(
            "RedisRateLimitBackend 尚未完全实现。"
        )

    def reset(self, username: str, client_ip: str) -> None:
        raise NotImplementedError(
            "RedisRateLimitBackend 尚未完全实现。"
        )


# ═══════════════════════════════════════════════════════════════
#  后端工厂
# ═══════════════════════════════════════════════════════════════

_backend: RateLimitBackend | None = None


def _get_backend() -> RateLimitBackend:
    """
    获取当前速率限制后端实例（惰性初始化，单例）。

    通过环境变量 PYKYCH_RATE_LIMIT_BACKEND 切换后端:
        - 'memory'（默认）
        - 'redis'
    """
    global _backend
    if _backend is None:
        backend_name = os.environ.get("PYKYCH_RATE_LIMIT_BACKEND", "memory").lower()
        if backend_name == "redis":
            _backend = RedisRateLimitBackend()
        else:
            _backend = MemoryRateLimitBackend()
    return _backend


# ═══════════════════════════════════════════════════════════════
#  公开 API（委托给当前后端）
# ═══════════════════════════════════════════════════════════════


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
    return _get_backend().check_allowed(username, client_ip)


def record_login_failure(username: str, client_ip: str) -> None:
    """
    记录一次登录失败。

    此函数应在密码验证失败后调用。

    参数:
        username:  登录失败的用户名
        client_ip: 客户端 IP 地址
    """
    _get_backend().record_failure(username, client_ip)


def reset_login_rate_limit(username: str, client_ip: str) -> None:
    """
    重置登录失败计数（登录成功后调用）。

    参数:
        username:  成功登录的用户名
        client_ip: 客户端 IP 地址
    """
    _get_backend().reset(username, client_ip)

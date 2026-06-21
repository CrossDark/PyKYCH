"""
速率限制模块测试 — 内存后端功能验证。

测试覆盖:
    - 正常允许登录
    - 用户+IP 限制触发
    - 全局 IP 限制触发
    - 锁定期机制
    - 重置功能
"""

import unittest
import sys
import os
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from pykych.auth.rate_limit import MemoryRateLimitBackend


class TestMemoryRateLimitBackend(unittest.TestCase):
    """内存速率限制后端测试。"""

    def setUp(self):
        self.backend = MemoryRateLimitBackend()

    def test_initial_allowed(self):
        """初始状态允许登录尝试。"""
        allowed, msg = self.backend.check_allowed("testuser", "127.0.0.1")
        self.assertTrue(allowed)
        self.assertEqual(msg, "")

    def test_record_failure(self):
        """记录失败不应立即阻止（未达阈值）。"""
        self.backend.record_failure("user1", "10.0.0.1")
        allowed, msg = self.backend.check_allowed("user1", "10.0.0.1")
        self.assertTrue(allowed)

    def test_user_ip_limit(self):
        """超过用户+IP 限制后应拒绝。"""
        for _ in range(5):
            self.backend.record_failure("user2", "10.0.0.2")
        allowed, msg = self.backend.check_allowed("user2", "10.0.0.2")
        self.assertFalse(allowed)

    def test_global_ip_limit(self):
        """超过全局 IP 限制后应拒绝。"""
        for i in range(20):
            self.backend.record_failure(f"user_{i}", "10.0.0.3")
        allowed, msg = self.backend.check_allowed("another_user", "10.0.0.3")
        self.assertFalse(allowed)

    def test_lockout_triggered(self):
        """连续失败超过锁定期阈值后触发锁定。"""
        for _ in range(10):
            self.backend.record_failure("lockuser", "10.0.0.4")
        allowed, msg = self.backend.check_allowed("lockuser", "10.0.0.4")
        self.assertFalse(allowed)
        self.assertIn("锁定", msg)

    def test_reset_clears_failures(self):
        """登录成功后重置应清除失败计数。"""
        for _ in range(4):
            self.backend.record_failure("resetuser", "10.0.0.5")
        self.backend.reset("resetuser", "10.0.0.5")
        allowed, msg = self.backend.check_allowed("resetuser", "10.0.0.5")
        self.assertTrue(allowed)

    def test_reset_clears_lockout(self):
        """重置应清除锁定状态。"""
        for _ in range(10):
            self.backend.record_failure("lockreset", "10.0.0.6")
        # 确认已锁定
        allowed, _ = self.backend.check_allowed("lockreset", "10.0.0.6")
        self.assertFalse(allowed)
        # 重置
        self.backend.reset("lockreset", "10.0.0.6")
        allowed, msg = self.backend.check_allowed("lockreset", "10.0.0.6")
        self.assertTrue(allowed)

    def test_different_users_independent(self):
        """不同用户的限制互相独立。"""
        for _ in range(5):
            self.backend.record_failure("userA", "10.0.0.7")
        # userA 应被限制
        allowed_a, _ = self.backend.check_allowed("userA", "10.0.0.7")
        self.assertFalse(allowed_a)
        # userB 应不受影响
        allowed_b, _ = self.backend.check_allowed("userB", "10.0.0.7")
        self.assertTrue(allowed_b)


if __name__ == "__main__":
    unittest.main()

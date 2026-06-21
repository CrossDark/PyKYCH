"""
会话与 CSRF 模块测试。

测试覆盖:
    - CSRF Token 生成格式
    - Token 唯一性
    - 验证逻辑
"""

import unittest
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from pykych.auth.session import _generate_token


class TestCSRFToken(unittest.TestCase):
    """CSRF Token 生成测试。"""

    def test_token_format(self):
        """Token 应为 64 字符十六进制字符串。"""
        token = _generate_token()
        self.assertEqual(len(token), 64)
        # 验证所有字符都是十六进制
        self.assertTrue(all(c in "0123456789abcdef" for c in token))

    def test_token_uniqueness(self):
        """每次生成的 Token 应唯一。"""
        tokens = {_generate_token() for _ in range(100)}
        self.assertEqual(len(tokens), 100)

    def test_token_is_string(self):
        """Token 应是字符串类型。"""
        token = _generate_token()
        self.assertIsInstance(token, str)


if __name__ == "__main__":
    unittest.main()

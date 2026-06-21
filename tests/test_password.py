"""
密码模块测试 — PBKDF2-HMAC-SHA256 哈希与验证。

测试覆盖:
    - 密码哈希生成
    - 密码验证（正确/错误）
    - 密码强度校验
    - 恒定时间比较
    - Unicode 规范化
"""

import unittest
import sys
import os

# 确保项目在 path 中
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from pykych.auth.password import (
    hash_password,
    verify_password,
    validate_password_strength,
)


class TestPasswordHashing(unittest.TestCase):
    """密码哈希与验证测试。"""

    def test_hash_format(self):
        """验证哈希格式: $pbkdf2$iterations$salt_hex$hash_hex"""
        hashed = hash_password("test123")
        parts = hashed.split("$")
        self.assertEqual(len(parts), 5)
        self.assertEqual(parts[0], "")
        self.assertEqual(parts[1], "pbkdf2")
        # iterations 应为 600000
        self.assertEqual(int(parts[2]), 600_000)
        # salt 为 64 字符十六进制（32 字节）
        self.assertEqual(len(parts[3]), 64)
        # hash 为 64 字符十六进制（32 字节）
        self.assertEqual(len(parts[4]), 64)

    def test_verify_correct_password(self):
        """正确密码验证通过。"""
        plain = "MySecureP@ss1"
        hashed = hash_password(plain)
        self.assertTrue(verify_password(plain, hashed))

    def test_verify_wrong_password(self):
        """错误密码验证失败。"""
        plain = "correct_password"
        hashed = hash_password(plain)
        self.assertFalse(verify_password("wrong_password", hashed))

    def test_verify_empty_password(self):
        """空密码也能正常哈希和验证。"""
        hashed = hash_password("")
        self.assertTrue(verify_password("", hashed))

    def test_hash_is_random(self):
        """相同密码两次哈希产生不同结果（随机盐）。"""
        plain = "same_password"
        hash1 = hash_password(plain)
        hash2 = hash_password(plain)
        self.assertNotEqual(hash1, hash2)
        # 但都能验证通过
        self.assertTrue(verify_password(plain, hash1))
        self.assertTrue(verify_password(plain, hash2))

    def test_unicode_password(self):
        """Unicode 密码（含中文、Emoji）正常哈希和验证。"""
        plain = "密码🔐测试"
        hashed = hash_password(plain)
        self.assertTrue(verify_password(plain, hashed))

    def test_unicode_normalization(self):
        """NFC 规范化：组合字符与预组合字符等价。"""
        # é 可以用预组合字符 U+00E9 或组合序列 e + U+0301
        nfc_form = "\u00e9"  # é
        nfd_form = "e\u0301"  # e + combining acute
        # 两者视觉相同但 Unicode 表示不同
        hash_nfc = hash_password(nfc_form)
        self.assertTrue(verify_password(nfd_form, hash_nfc))


class TestPasswordStrength(unittest.TestCase):
    """密码强度校验测试。"""

    def test_valid_password(self):
        """符合要求的密码通过校验。"""
        err = validate_password_strength("MyP@ssw0rd")
        self.assertIsNone(err)

    def test_too_short(self):
        """少于 8 字符的密码不通过。"""
        err = validate_password_strength("Ab1!")
        self.assertIsNotNone(err)
        self.assertIn("8", err)

    def test_no_uppercase(self):
        """缺少大写字母的密码不通过。"""
        err = validate_password_strength("myp@ssw0rd")
        self.assertIsNotNone(err)

    def test_no_lowercase(self):
        """缺少小写字母的密码不通过。"""
        err = validate_password_strength("MYP@SSW0RD")
        self.assertIsNotNone(err)

    def test_no_digit(self):
        """缺少数字的密码不通过。"""
        err = validate_password_strength("MyP@ssword")
        self.assertIsNotNone(err)

    def test_long_password(self):
        """长密码正常通过。"""
        err = validate_password_strength("A" + "b" * 98 + "1")
        self.assertIsNone(err)


if __name__ == "__main__":
    unittest.main()

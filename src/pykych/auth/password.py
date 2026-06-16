"""
密码安全模块 — PBKDF2-HMAC-SHA256 哈希、验证、强度校验。

安全性设计:
    - PBKDF2-HMAC-SHA256，60 万次迭代（OWASP 2025 推荐 >= 60 万）
    - 32 字节随机盐值
    - NFC Unicode 规范化（确保跨平台一致性）
    - 对比使用恒定时间比较（防时序攻击）
    - 密码强度校验：最少 8 字符，含大小写字母 + 数字

哈希格式:
    $pbkdf2${iterations}${salt_hex}${hash_hex}
"""

import hashlib
import os
import re
import unicodedata
import hmac
from typing import Optional


# ── 密码哈希常量 ────────────────────────────────────────────

_SALT_LEN = 32          # 盐值长度（字节）
_ITERATIONS = 600_000   # PBKDF2 迭代次数（OWASP 2025 推荐 ≥ 600k）
_KEY_LEN = 32           # 输出哈希长度（字节）


# ── 密码哈希 ────────────────────────────────────────────────


def hash_password(password: str) -> str:
    """
    使用 PBKDF2-HMAC-SHA256 生成密码哈希。

    参数:
        password: 明文密码（支持任意 Unicode 字符）

    返回:
        格式为 '$pbkdf2$iterations$salt_hex$hash_hex' 的哈希字符串

    安全性:
        - 使用 NFC 规范化确保跨平台一致性（相同视觉密码产生相同哈希）
        - 32 字节随机盐值防止彩虹表攻击
        - 60 万次迭代增加暴力破解成本
    """
    # NFC 规范化：确保相同视觉密码在不同系统上产生相同哈希
    normalized = unicodedata.normalize("NFC", password)
    salt = os.urandom(_SALT_LEN)
    key = hashlib.pbkdf2_hmac(
        "sha256", normalized.encode("utf-8"), salt, _ITERATIONS, _KEY_LEN
    )
    return f"$pbkdf2${_ITERATIONS}${salt.hex()}${key.hex()}"


def verify_password(plain: str, hashed: str) -> bool:
    """
    验证明文密码与哈希值是否匹配。

    参数:
        plain: 用户输入的明文密码
        hashed: 数据库中存储的哈希字符串

    返回:
        True 表示密码正确，False 表示不匹配

    安全性:
        - 使用 hmac.compare_digest 进行恒定时间比较（防时序攻击）
        - NFC 规范化与 hash_password 保持一致
        - 异常安全：任何解析失败都返回 False，不泄露内部状态
    """
    try:
        _, algo, iterations, salt_hex, key_hex = hashed.split("$")
        if algo != "pbkdf2":
            return False
        salt = bytes.fromhex(salt_hex)
        expected = bytes.fromhex(key_hex)
        # NFC 规范化：与 hash_password 保持一致
        normalized = unicodedata.normalize("NFC", plain)
        actual = hashlib.pbkdf2_hmac(
            "sha256", normalized.encode("utf-8"), salt, int(iterations), len(expected)
        )
        # 恒定时间比较：防止时序侧信道攻击
        return hmac.compare_digest(actual, expected)
    except (ValueError, AttributeError):
        return False


# ── 密码强度校验 ────────────────────────────────────────────


def validate_password_strength(password: str) -> Optional[str]:
    """
    校验密码强度，返回错误信息或 None（表示通过）。

    密码要求（安全基线）:
        - 长度 ≥ 8 字符（推荐 ≥ 12）
        - 包含至少 1 个大写字母 (A-Z)
        - 包含至少 1 个小写字母 (a-z)
        - 包含至少 1 个数字 (0-9)
        - 不超过 128 字符（防止过长输入）
        - 不包含空白字符

    参数:
        password: 待校验的明文密码

    返回:
        None 表示密码强度合格
        字符串表示具体的错误信息
    """
    if not password:
        return "密码不能为空。"

    if len(password) < 8:
        return "密码长度至少需要 8 个字符。"

    if len(password) > 128:
        return "密码长度不能超过 128 个字符。"

    if re.search(r'\s', password):
        return "密码不能包含空格或空白字符。"

    if not re.search(r'[A-Z]', password):
        return "密码必须包含至少一个大写字母 (A-Z)。"

    if not re.search(r'[a-z]', password):
        return "密码必须包含至少一个小写字母 (a-z)。"

    if not re.search(r'[0-9]', password):
        return "密码必须包含至少一个数字 (0-9)。"

    # 额外建议（非强制执行）
    # if len(password) < 12:
    #     return "建议使用 12 字符以上密码以增强安全性。"

    return None  # 通过校验

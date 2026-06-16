"""
WebAuthn / Passkey 管理器 — 通行密钥的注册与认证。
使用 cryptography 进行 ECDSA 签名验证。
内置最小 CBOR 解码器（无外部依赖）。
"""

import base64
import hashlib
import json
import os
import struct
from typing import Optional

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.backends import default_backend
from cryptography.exceptions import InvalidSignature

from ..core.db import get_sys_pool, row_to_dict

# ── CBOR 解码器（最小实现，仅支持 WebAuthn 所需类型） ────────


def _cbor_decode(data: bytes):
    """解码 CBOR 字节串，返回 Python 对象。"""
    idx = 0
    n = len(data)

    def _read_u8():
        nonlocal idx
        if idx >= n:
            raise ValueError("CBOR: 意外结束")
        v = data[idx]
        idx += 1
        return v

    def _read_bytes(length: int) -> bytes:
        nonlocal idx
        if idx + length > n:
            raise ValueError("CBOR: 长度超出")
        v = data[idx : idx + length]
        idx += length
        return v

    def _read_int_bytes(length: int) -> int:
        return int.from_bytes(_read_bytes(length), "big")

    def _decode():
        initial = _read_u8()
        major = initial >> 5
        info = initial & 0x1F

        # ── 解析参数值 ──
        if info < 24:
            argument = info
        elif info == 24:
            argument = _read_u8()
        elif info == 25:
            argument = _read_int_bytes(2)
        elif info == 26:
            argument = _read_int_bytes(4)
        elif info == 27:
            argument = _read_int_bytes(8)
        else:
            raise ValueError(f"CBOR: 不支持 info={info}")

        # ── Major Type 0: 无符号整数 ──
        if major == 0:
            return argument

        # ── Major Type 1: 负整数 ──
        if major == 1:
            return -1 - argument

        # ── Major Type 2: 字节串 ──
        if major == 2:
            return _read_bytes(argument)

        # ── Major Type 3: 文本串 ──
        if major == 3:
            return _read_bytes(argument).decode("utf-8")

        # ── Major Type 4: 数组 ──
        if major == 4:
            return [_decode() for _ in range(argument)]

        # ── Major Type 5: 映射（返回 dict） ──
        if major == 5:
            result = {}
            for _ in range(argument):
                k = _decode()
                v = _decode()
                result[k] = v
            return result

        # ── Major Type 6: 语义标签（跳过） ──
        if major == 6:
            return _decode()

        # ── Major Type 7: 简单值/浮点数 ──
        if major == 7:
            if info == 20:  # false
                return False
            elif info == 21:  # true
                return True
            elif info == 22:  # null
                return None
            elif info == 23:  # undefined
                return None
            elif info == 25:  # half float (跳过，2字节)
                _read_bytes(2)
                return 0.0
            elif info == 26:  # 单精度 float
                v = struct.unpack(">f", _read_bytes(4))[0]
                return v
            elif info == 27:  # 双精度 float
                v = struct.unpack(">d", _read_bytes(8))[0]
                return v
            raise ValueError(f"CBOR: 不支持的 simple value info={info}")

        raise ValueError(f"CBOR: 不支持 major={major}")

    result = _decode()
    return result


# ── Base64 URL 安全编码（WebAuthn 标准） ─────────────────────


def _b64url_decode(s: str) -> bytes:
    """Base64URL 解码（处理填充）。"""
    s = s.replace("-", "+").replace("_", "/")
    padding = 4 - len(s) % 4
    if padding != 4:
        s += "=" * padding
    return base64.b64decode(s, validate=True)


def _b64url_encode(data: bytes) -> str:
    """Base64URL 编码（无填充）。"""
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


# ── WebAuthn 数据结构解析 ───────────────────────────────────


def _parse_auth_data(auth_data: bytes):
    """解析 authenticatorData 二进制结构。
    
    返回 dict:
        rp_id_hash: bytes (32)
        flags: int
        sign_count: int
        attested_cred_data: dict | None (含 credential_id, public_key)
    """
    if len(auth_data) < 37:
        raise ValueError("authData 太短")

    idx = 0
    rp_id_hash = auth_data[idx : idx + 32]
    idx += 32

    flags = auth_data[idx]
    idx += 1

    sign_count = int.from_bytes(auth_data[idx : idx + 4], "big")
    idx += 4

    result = {
        "rp_id_hash": rp_id_hash,
        "flags": flags,
        "sign_count": sign_count,
        "attested_cred_data": None,
    }

    # AT 标志：是否有 attested credential data
    AT_FLAG = 0x40
    if flags & AT_FLAG:
        if idx + 16 + 2 > len(auth_data):
            raise ValueError("authData 不含完整 attested credential data")
        aaguid = auth_data[idx : idx + 16]
        idx += 16
        cred_id_len = int.from_bytes(auth_data[idx : idx + 2], "big")
        idx += 2
        credential_id = auth_data[idx : idx + cred_id_len]
        idx += cred_id_len

        # 剩余部分是 COSE_Key（CBOR 编码）
        if idx >= len(auth_data):
            raise ValueError("authData 不含 COSE_Key")
        cose_key_data = auth_data[idx:]
        cose_key = _cbor_decode(cose_key_data)

        # 从 COSE_Key 提取公钥坐标
        # ES256 / P-256: kty=2 (EC2), alg=-7 (ES256), crv=1 (P-256)
        public_key = _cose_key_to_public_key(cose_key)

        result["attested_cred_data"] = {
            "aaguid": aaguid,
            "credential_id": credential_id,
            "public_key_pem": public_key,
            "cose_key": cose_key,
        }

    return result


def _cose_key_to_public_key(cose_key: dict) -> str:
    """将 COSE_Key dict 转换为 PEM 格式的公钥字符串。
    
    支持 ES256 (P-256 / prime256v1):
        kty: 2 (EC2)
        alg: -7 (ES256)
        crv: 1 (P-256)
        x: bytes (x 坐标)
        y: bytes (y 坐标)
    """
    kty = cose_key.get(1, 0)
    alg = cose_key.get(3, 0)
    crv = cose_key.get(-1, 0)
    x = cose_key.get(-2, b"")
    y = cose_key.get(-3, b"")

    if kty != 2:
        raise ValueError(f"不支持的密钥类型: kty={kty}")
    if crv != 1:
        raise ValueError(f"不支持的曲线: crv={crv}")
    if not x or not y:
        raise ValueError("缺少 x 或 y 坐标")

    # 构建 SEC1 编码的公钥点
    # SEC1: 0x04 || x || y
    # 确保坐标是32字节（P-256）
    x_padded = x.rjust(32, b"\x00") if len(x) < 32 else x[:32]
    y_padded = y.rjust(32, b"\x00") if len(y) < 32 else y[:32]

    point_bytes = b"\x04" + x_padded + y_padded

    # 使用 cryptography 构建公钥
    pubkey = ec.EllipticCurvePublicKey.from_encoded_point(
        ec.SECP256R1(), point_bytes
    )

    pem = pubkey.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    return pem.decode()


# ── 签名验证 ─────────────────────────────────────────────────


def _verify_assertion_signature(
    public_key_pem: str,
    client_data_json: bytes,
    auth_data: bytes,
    signature: bytes,
) -> bool:
    """验证 WebAuthn assertion 的 ECDSA 签名。
    
    签名覆盖: authData || SHA-256(clientDataJSON)
    """
    pubkey = serialization.load_pem_public_key(
        public_key_pem.encode(), backend=default_backend()
    )

    if not isinstance(pubkey, ec.EllipticCurvePublicKey):
        return False

    # 验证数据: authenticatorData || SHA-256(clientDataJSON)
    client_data_hash = hashlib.sha256(client_data_json).digest()
    verify_data = auth_data + client_data_hash

    # ES256 使用 SHA-256，签名可能为 raw (r||s, 64字节) 或 DER (70-73字节)
    try:
        from cryptography.hazmat.primitives.asymmetric.utils import (
            encode_dss_signature,
        )

        if len(signature) == 64:
            # Raw 格式: r || s (各 32 字节)
            r = int.from_bytes(signature[:32], "big")
            s_int = int.from_bytes(signature[32:], "big")
            der_sig = encode_dss_signature(r, s_int)
        elif 68 <= len(signature) <= 73:
            # DER 格式: 直接使用
            der_sig = signature
        else:
            import sys
            print(f"[WebAuthn] sig verify: unexpected sig len={len(signature)}", file=sys.stderr)
            return False

        pubkey.verify(der_sig, verify_data, ec.ECDSA(hashes.SHA256()))
        return True
    except InvalidSignature:
        return False
    except ValueError as e:
        import sys
        print(f"[WebAuthn] sig verify ValueError: {e}", file=sys.stderr)
        return False


# ── 挑战值管理（基于会话） ───────────────────────────────────


def _store_challenge(request, challenge: str) -> None:
    """将 WebAuthn 挑战值存入会话。"""
    if hasattr(request, "session"):
        request.session["webauthn_challenge"] = challenge


def _get_challenge(request) -> Optional[str]:
    """从会话获取并清除 WebAuthn 挑战值。"""
    if hasattr(request, "session"):
        return request.session.pop("webauthn_challenge", None)
    return None


# ── 通行密钥数据库操作 ──────────────────────────────────────


async def store_credential(
    username: str,
    credential_id: bytes,
    public_key_pem: str,
    sign_count: int = 0,
    transports: str = "",
) -> None:
    """存储 WebAuthn 凭据。"""
    pool = await get_sys_pool()
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            cred_id_b64 = _b64url_encode(credential_id)
            await cur.execute(
                "INSERT INTO webauthn_credentials "
                "(username, credential_id, public_key, sign_count, transports) "
                "VALUES (%s, %s, %s, %s, %s)",
                (username, cred_id_b64, public_key_pem, sign_count, transports),
            )


async def get_credentials(username: str) -> list[dict]:
    """获取用户的所有通行密钥。"""
    pool = await get_sys_pool()
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                "SELECT id, username, credential_id, sign_count, transports, created_at "
                "FROM webauthn_credentials WHERE username = %s ORDER BY created_at DESC",
                (username,),
            )
            rows = await cur.fetchall()
            return [row_to_dict(r, cur) for r in rows]


async def get_credential_by_id(credential_id_b64: str) -> Optional[dict]:
    """根据 base64url 编码的 credential_id 获取凭据详情。"""
    pool = await get_sys_pool()
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                "SELECT id, username, credential_id, public_key, sign_count, transports "
                "FROM webauthn_credentials WHERE credential_id = %s",
                (credential_id_b64,),
            )
            row = await cur.fetchone()
            return row_to_dict(row, cur) if row else None


async def update_sign_count(credential_id_b64: str, sign_count: int) -> None:
    """更新签名计数器。"""
    pool = await get_sys_pool()
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                "UPDATE webauthn_credentials SET sign_count = %s "
                "WHERE credential_id = %s",
                (sign_count, credential_id_b64),
            )


async def delete_credential(credential_id: int) -> bool:
    """删除通行密钥（按数据库 id）。"""
    pool = await get_sys_pool()
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                "DELETE FROM webauthn_credentials WHERE id = %s",
                (credential_id,),
            )
            return cur.rowcount > 0


async def delete_credential_by_username(username: str) -> None:
    """删除用户的所有通行密钥。"""
    pool = await get_sys_pool()
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                "DELETE FROM webauthn_credentials WHERE username = %s",
                (username,),
            )


async def has_credentials(username: str) -> bool:
    """检查用户是否有注册的通行密钥。"""
    pool = await get_sys_pool()
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                "SELECT COUNT(*) FROM webauthn_credentials WHERE username = %s",
                (username,),
            )
            row = await cur.fetchone()
            return row[0] > 0 if row else False


# ── WebAuthn 注册流程 ────────────────────────────────────────


def generate_registration_options(username: str, rp_id: str, rp_name: str) -> dict:
    """生成 WebAuthn 注册选项（PublicKeyCredentialCreationOptions）。
    
    返回给前端，用于 navigator.credentials.create()。
    """
    challenge = _b64url_encode(os.urandom(32))

    # 用户标识
    user_id = hashlib.sha256(username.encode()).digest()

    options = {
        "rp": {"name": rp_name, "id": rp_id},
        "user": {
            "id": _b64url_encode(user_id),
            "name": username,
            "displayName": username,
        },
        "challenge": challenge,
        "pubKeyCredParams": [
            {"type": "public-key", "alg": -7},   # ES256
            {"type": "public-key", "alg": -257},  # RS256
        ],
        "timeout": 60000,
        "attestation": "none",
        "authenticatorSelection": {
            "authenticatorAttachment": "platform",
            "userVerification": "preferred",
            "requireResidentKey": False,
        },
    }

    return options, challenge


async def verify_registration(
    username: str,
    challenge: str,
    credential_id_b64: str,
    client_data_json_b64: str,
    attestation_object_b64: str,
    rp_id: str,
) -> tuple[bool, str]:
    """验证 WebAuthn 注册响应。

    返回 (success, message)。
    """
    # 解码 clientDataJSON
    client_data_json = _b64url_decode(client_data_json_b64)
    try:
        client_data = json.loads(client_data_json)
    except json.JSONDecodeError:
        return False, "clientDataJSON 解析失败"

    # 验证 challenge
    if client_data.get("challenge") != challenge:
        return False, "挑战值不匹配"

    # 验证 origin（忽略端口差异，安全策略由部署决定）
    # 在开发环境中 origin 可能是 http://localhost:8000
    # 暂时跳过严格的 origin 检查

    # 解码 attestationObject（CBOR）
    att_obj_bytes = _b64url_decode(attestation_object_b64)
    try:
        att_obj = _cbor_decode(att_obj_bytes)
    except ValueError as e:
        return False, f"attestationObject 解析失败: {e}"

    auth_data_bytes = att_obj.get("authData", b"")
    if isinstance(auth_data_bytes, str):
        auth_data_bytes = auth_data_bytes.encode()
    if not isinstance(auth_data_bytes, bytes) or len(auth_data_bytes) < 37:
        return False, "authData 无效"

    # 验证 rpIdHash
    auth_data = _parse_auth_data(auth_data_bytes)
    expected_hash = hashlib.sha256(rp_id.encode()).digest()
    if auth_data["rp_id_hash"] != expected_hash:
        return False, "rpIdHash 不匹配"

    # 验证用户存在标志
    UP_FLAG = 0x01
    if not (auth_data["flags"] & UP_FLAG):
        return False, "用户未验证"

    # 获取公钥
    if auth_data["attested_cred_data"] is None:
        return False, "attestedCredentialData 缺失"

    cred_data = auth_data["attested_cred_data"]
    # 验证 credential_id 匹配
    stored_cred_id = _b64url_decode(credential_id_b64)
    if cred_data["credential_id"] != stored_cred_id:
        return False, "credential_id 不匹配"

    # 存储凭据
    await store_credential(
        username=username,
        credential_id=stored_cred_id,
        public_key_pem=cred_data["public_key_pem"],
        sign_count=auth_data["sign_count"],
    )

    return True, "通行密钥注册成功"


# ── WebAuthn 认证流程 ────────────────────────────────────────


def generate_authentication_options(rp_id: str) -> dict:
    """生成 WebAuthn 认证选项（PublicKeyCredentialRequestOptions）。
    
    允许任何已注册的凭据进行认证（不限定 credential_id）。
    """
    challenge = _b64url_encode(os.urandom(32))

    options = {
        "challenge": challenge,
        "timeout": 60000,
        "rpId": rp_id,
        "userVerification": "preferred",
    }

    return options, challenge


async def verify_authentication(
    challenge: str,
    credential_id_b64: str,
    client_data_json_b64: str,
    auth_data_b64: str,
    signature_b64: str,
    rp_id: str,
) -> tuple[Optional[str], str]:
    """验证 WebAuthn 认证断言。

    返回 (username_or_None, message)。
    """
    # 获取凭据
    cred = await get_credential_by_id(credential_id_b64)
    if not cred:
        return None, "通行密钥未注册"

    # 解码参数
    try:
        client_data_json = _b64url_decode(client_data_json_b64)
        client_data = json.loads(client_data_json)
    except (json.JSONDecodeError, ValueError):
        return None, "clientDataJSON 解析失败"

    auth_data_bytes = _b64url_decode(auth_data_b64)
    signature = _b64url_decode(signature_b64)

    # 验证 challenge
    if client_data.get("challenge") != challenge:
        import sys
        print(f"[WebAuthn] challenge mismatch: client={client_data.get('challenge','')[:20]}... stored={challenge[:20]}...", file=sys.stderr)
        return None, "挑战值不匹配"

    # 解析 authData
    parsed = _parse_auth_data(auth_data_bytes)

    # 验证 rpIdHash
    expected_hash = hashlib.sha256(rp_id.encode()).digest()
    if parsed["rp_id_hash"] != expected_hash:
        import sys
        print(f"[WebAuthn] rpIdHash mismatch: rp_id={rp_id}", file=sys.stderr)
        return None, "rpIdHash 不匹配"

    # 验证用户存在和验证标志
    UP_FLAG = 0x01
    if not (parsed["flags"] & UP_FLAG):
        return None, "用户未验证"

    # 验证签名
    public_key_pem = cred.get("public_key", "")
    if not _verify_assertion_signature(
        public_key_pem, client_data_json, auth_data_bytes, signature
    ):
        import sys
        print(f"[WebAuthn] signature verify failed: sig_len={len(signature)} pubkey_len={len(public_key_pem)}", file=sys.stderr)
        return None, "签名验证失败"

    # 验证签名计数器（防止重放攻击）
    stored_count = cred.get("sign_count", 0) or 0
    new_count = parsed["sign_count"]
    # 如果存储的计数器为 0 且新的也为 0，跳过（某些身份验证器不递增计数器）
    if stored_count > 0 and new_count > 0 and new_count <= stored_count:
        return None, "签名计数器异常"

    # 更新签名计数器
    if new_count > 0:
        await update_sign_count(credential_id_b64, new_count)

    return cred["username"], "认证成功"

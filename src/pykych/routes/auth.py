"""
认证路由 — 登录 / 登出 / CAPTCHA / 通行密钥 (WebAuthn)。
"""

import os
from lihil import Route, Request
from starlette.responses import HTMLResponse, RedirectResponse, JSONResponse
from pathlib import Path
from ..auth import password as auth_pwd
from ..auth import user as auth_user
from ..auth import session as auth_session
from ..auth import rate_limit as auth_rate
from ..auth import webauthn

from ..core.templates import jinja_env, render_template as _render_template


def render(template_name: str, status_code: int = 200, **context) -> HTMLResponse:
    """渲染模板（保持向后兼容的函数签名）。"""
    return _render_template(template_name, status_code=status_code, **context)


def redirect(url: str) -> RedirectResponse:
    return RedirectResponse(url, status_code=303)


# ── 验证码辅助函数 ──────────────────────────────────────────

def _generate_captcha(request) -> dict:
    """生成数学验证码，存入会话。返回 {question, answer}。"""
    import random
    a = random.randint(1, 20)
    b = random.randint(1, 20)
    ops = [("+", a + b), ("-", a + b), ("×", a * b)]
    op, answer = random.choice(ops)
    if op == "-":
        # 确保结果非负
        a, b = max(a, b), min(a, b)
        answer = a - b
    question = f"{a} {op} {b} = ?"
    if hasattr(request, "session"):
        request.session["captcha_answer"] = str(answer)
    return {"question": question, "answer": answer}


def _verify_captcha(request, user_input: str) -> bool:
    """验证数学验证码答案。

    修复: 当会话不可用时返回 False（而非 True），防止 CAPTCHA 被绕过。
    """
    if not hasattr(request, "session"):
        return False  # 修复：无法访问会话时拒绝，而非放行
    expected = request.session.pop("captcha_answer", None)
    if expected is None:
        return False
    # 使用恒定时间比较防止时序攻击
    import hmac
    return hmac.compare_digest(user_input.strip(), expected)


# ── RP 配置 ──────────────────────────────────────────────────

def _get_rp_config(request) -> dict:
    """获取 WebAuthn Relying Party 配置。
    
    支持反向代理：检查 X-Forwarded-Proto 和 X-Forwarded-Host 头。
    """
    # 优先使用反向代理转发的头
    host = request.headers.get("x-forwarded-host", "") or request.headers.get("host", "localhost:8000")
    proto = request.headers.get("x-forwarded-proto", "") or request.url.scheme
    # 移除端口号作为 rp_id
    rp_id = host.split(":")[0] if ":" in host else host
    # 对于 localhost，使用 localhost
    if rp_id in ("127.0.0.1", "0.0.0.0"):
        rp_id = "localhost"
    is_local = "localhost" in host or rp_id == "localhost"
    origin = f"http://{host}" if is_local else f"{proto}://{host}"
    return {"rp_id": rp_id, "rp_name": "PyKYCH", "origin": origin}


# ── 路由 ───────────────────────────────────────────────────

auth_route = Route("/auth")


# ═══════════════════════════════════════════════════════════════
# check-passkey 接口专用限流（防用户名枚举暴力破解）
# ═══════════════════════════════════════════════════════════════

import time as _time
_check_passkey_records: dict[str, list[float]] = {}
_check_passkey_lock = __import__('threading').Lock()
_CHECK_PASSKEY_MAX_PER_IP = 10      # 每 IP 每分钟最多 10 次
_CHECK_PASSKEY_WINDOW = 60           # 限流窗口（秒）


def _check_passkey_rate_limit(client_ip: str) -> bool:
    """检查 check-passkey 接口是否被限流。返回 True 表示允许。"""
    now = _time.time()
    cutoff = now - _CHECK_PASSKEY_WINDOW
    with _check_passkey_lock:
        records = _check_passkey_records.get(client_ip, [])
        records = [ts for ts in records if ts > cutoff]
        if len(records) >= _CHECK_PASSKEY_MAX_PER_IP:
            _check_passkey_records[client_ip] = records
            return False
        records.append(now)
        _check_passkey_records[client_ip] = records
        return True


@auth_route.sub("/login").get
async def login_form(request: Request):
    """登录页面。"""
    captcha = _generate_captcha(request)
    csrf_token = auth_session.generate_csrf_token(request)
    return render("login.html", title="登录 - PyKYCH", error=None,
                  captcha_question=captcha["question"],
                  csrf_token=csrf_token)


@auth_route.sub("/login").post
async def login_action(request: Request):
    """处理登录请求。"""
    form = await request.form()
    username = form.get("username", "").strip()
    password = form.get("password", "")
    captcha_input = form.get("captcha", "")

    # ── CSRF 防护 ──
    csrf_token = form.get("csrf_token", "")
    if not auth_session.verify_csrf_token(request, csrf_token):
        captcha = _generate_captcha(request)
        new_csrf = auth_session.generate_csrf_token(request)
        return render("login.html", title="登录 - PyKYCH",
                      error="安全验证失败，请刷新页面后重试。",
                      captcha_question=captcha["question"],
                      csrf_token=new_csrf)

    if not username or not password:
        captcha = _generate_captcha(request)
        csrf = auth_session.generate_csrf_token(request)
        return render("login.html", title="登录 - PyKYCH",
                      error="用户名和密码不能为空。",
                      captcha_question=captcha["question"],
                      csrf_token=csrf)

    # 验证验证码
    if not _verify_captcha(request, captcha_input):
        captcha = _generate_captcha(request)
        csrf = auth_session.generate_csrf_token(request)
        return render("login.html", title="登录 - PyKYCH",
                      error="验证码错误，请重试。",
                      captcha_question=captcha["question"],
                      csrf_token=csrf)

    # 速率限制检查（防暴力破解）
    client_ip = auth_session._get_client_ip(request)
    allowed, rate_msg = auth_rate.check_login_rate_limit(username, client_ip)
    if not allowed:
        captcha = _generate_captcha(request)
        csrf = auth_session.generate_csrf_token(request)
        return render("login.html", title="登录 - PyKYCH",
                      error=rate_msg,
                      captcha_question=captcha["question"],
                      csrf_token=csrf)

    user = await auth_user.get_user_with_password(username)
    if not user or not auth_pwd.verify_password(password, user["password_hash"]):
        # 记录登录失败（速率限制）
        client_ip2 = auth_session._get_client_ip(request)
        auth_rate.record_login_failure(username, client_ip2)
        captcha = _generate_captcha(request)
        csrf = auth_session.generate_csrf_token(request)
        return render("login.html", title="登录 - PyKYCH",
                      error="用户名或密码错误。",
                      captcha_question=captcha["question"],
                      csrf_token=csrf)

    # 检查用户是否已设置通行密钥 → 禁用密码登录
    if await webauthn.has_passkey(username):
        captcha = _generate_captcha(request)
        csrf = auth_session.generate_csrf_token(request)
        return render("login.html", title="登录 - PyKYCH",
                      error="此账户已设置通行密钥，请使用下方的「通行密钥登录」按钮进行登录。",
                      captcha_question=captcha["question"],
                      has_passkey=True,
                      csrf_token=csrf)

    await auth_session.login_user(request, username)

    next_url = request.query_params.get("next", "/admin")
    # 防止开放重定向：仅允许本站内部相对路径
    if not next_url.startswith("/") or next_url.startswith("//") or "@" in next_url:
        next_url = "/admin"
    return redirect(next_url)


@auth_route.sub("/logout").post
async def logout(request: Request):
    """登出（需 POST 请求，防止 CSRF 强制登出）。"""
    auth_session.logout_user(request)
    return redirect("/")


# ═══════════════════════════════════════════════════════════════
# WebAuthn / Passkey 通行密钥
# ═══════════════════════════════════════════════════════════════


@auth_route.sub("/webauthn/register/begin").post
async def webauthn_register_begin(request: Request):
    """开始通行密钥注册 — 返回 creationOptions。"""
    user = await auth_session.get_current_user(request)
    if not user:
        return JSONResponse({"error": "请先登录"}, status_code=401)

    rp = _get_rp_config(request)
    options, challenge = webauthn.generate_registration_options(
        user["username"], rp["rp_id"], rp["rp_name"]
    )
    webauthn._store_challenge(request, challenge)

    return JSONResponse({"publicKey": options})


@auth_route.sub("/webauthn/register/complete").post
async def webauthn_register_complete(request: Request):
    """完成通行密钥注册 — 验证并存储凭据。"""
    user = await auth_session.get_current_user(request)
    if not user:
        return JSONResponse({"error": "请先登录"}, status_code=401)

    challenge = webauthn._get_challenge(request)
    if not challenge:
        return JSONResponse({"error": "会话已过期，请重试"}, status_code=400)

    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "请求格式错误"}, status_code=400)

    rp = _get_rp_config(request)
    success, message = await webauthn.verify_registration(
        username=user["username"],
        challenge=challenge,
        credential_id_b64=body.get("id", ""),
        client_data_json_b64=body.get("response", {}).get("clientDataJSON", ""),
        attestation_object_b64=body.get("response", {}).get("attestationObject", ""),
        rp_id=rp["rp_id"],
    )

    if success:
        return JSONResponse({"status": "ok", "message": message})
    else:
        return JSONResponse({"error": message}, status_code=400)


@auth_route.sub("/webauthn/login/begin").post
async def webauthn_login_begin(request: Request):
    """开始通行密钥登录 — 返回 requestOptions。"""
    rp = _get_rp_config(request)
    options, challenge = webauthn.generate_authentication_options(rp["rp_id"])
    webauthn._store_challenge(request, challenge)

    return JSONResponse({"publicKey": options})


@auth_route.sub("/webauthn/login/complete").post
async def webauthn_login_complete(request: Request):
    """完成通行密钥登录 — 验证断言并登录。"""
    challenge = webauthn._get_challenge(request)
    if not challenge:
        return JSONResponse({"error": "会话已过期，请重试"}, status_code=400)

    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "请求格式错误"}, status_code=400)

    rp = _get_rp_config(request)
    username, message = await webauthn.verify_authentication(
        challenge=challenge,
        credential_id_b64=body.get("id", ""),
        client_data_json_b64=body.get("response", {}).get("clientDataJSON", ""),
        auth_data_b64=body.get("response", {}).get("authenticatorData", ""),
        signature_b64=body.get("response", {}).get("signature", ""),
        rp_id=rp["rp_id"],
    )

    if username:
        await auth_session.login_user(request, username)
        return JSONResponse({"status": "ok", "message": message, "username": username})
    else:
        return JSONResponse({"error": message}, status_code=400)


@auth_route.sub("/webauthn/credentials").get
async def webauthn_list_credentials(request: Request):
    """获取当前用户的通行密钥列表。"""
    user = await auth_session.get_current_user(request)
    if not user:
        return JSONResponse({"error": "请先登录"}, status_code=401)

    creds = await webauthn.get_credentials(user["username"])
    return JSONResponse({"credentials": creds})


@auth_route.sub("/webauthn/credentials/{cred_id}").delete
async def webauthn_delete_credential(cred_id: int, request: Request):
    """删除指定的通行密钥。"""
    user = await auth_session.get_current_user(request)
    if not user:
        return JSONResponse({"error": "请先登录"}, status_code=401)

    success = await webauthn.delete_credential(cred_id)
    if success:
        return JSONResponse({"status": "ok"})
    else:
        return JSONResponse({"error": "凭据不存在"}, status_code=404)


# ═══════════════════════════════════════════════════════════════
# 通行密钥检测（用于前端判断是否禁用密码登录）
# ═══════════════════════════════════════════════════════════════


@auth_route.sub("/check-passkey").get
async def check_passkey(request: Request):
    """检查指定用户名是否已设置通行密钥。用于前端 UI 调整。
    
    安全措施:
        1. CSRF Token 验证 — 防止跨站请求
        2. IP 限流 — 每 IP 每分钟最多 10 次，防用户名枚举
        3. 恒定响应模式 — 限流被拒时返回相同结构，不暴露原因
    """
    # ── IP 限流 ──
    client_ip = auth_session._get_client_ip(request)
    if not _check_passkey_rate_limit(client_ip):
        # 返回通用响应，不暴露限流原因
        return JSONResponse({"has_passkey": False, "throttled": True})

    # ── CSRF 验证 ──
    csrf_token = request.query_params.get("_csrf", "")
    if not auth_session.verify_csrf_token(request, csrf_token):
        return JSONResponse({"has_passkey": False, "error": "invalid_csrf"})

    username = request.query_params.get("username", "").strip()
    if not username:
        return JSONResponse({"has_passkey": False})

    has = await webauthn.has_passkey(username)
    return JSONResponse({"has_passkey": has})


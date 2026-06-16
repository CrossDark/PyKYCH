"""
认证路由 — 登录 / 登出 / CAPTCHA / 通行密钥 (WebAuthn)。
"""

import os
from lihil import Route, Request
from starlette.responses import HTMLResponse, RedirectResponse, JSONResponse
from pathlib import Path
from jinja2 import Environment, FileSystemLoader

from ..auth import password as auth_pwd
from ..auth import user as auth_user
from ..auth import session as auth_session
from ..auth import rate_limit as auth_rate
from ..auth import webauthn

TEMPLATE_DIR = Path(__file__).parent.parent / "templates"
jinja_env = Environment(
    loader=FileSystemLoader(str(TEMPLATE_DIR)),
    autoescape=True,
)


def render(template_name: str, status_code: int = 200, **context) -> HTMLResponse:
    template = jinja_env.get_template(template_name)
    return HTMLResponse(template.render(**context), status_code=status_code)


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
    """获取 WebAuthn Relying Party 配置。"""
    host = request.headers.get("host", "localhost:8000")
    # 移除端口号作为 rp_id
    rp_id = host.split(":")[0] if ":" in host else host
    # 对于 localhost，使用 localhost
    if rp_id in ("127.0.0.1", "0.0.0.0"):
        rp_id = "localhost"
    origin = f"http://{host}" if "localhost" in host or rp_id == "localhost" else f"https://{host}"
    return {"rp_id": rp_id, "rp_name": "PyKYCH", "origin": origin}


# ── 路由 ───────────────────────────────────────────────────

auth_route = Route("/auth")


@auth_route.sub("/login").get
async def login_form(request: Request):
    """登录页面。"""
    captcha = _generate_captcha(request)
    return render("login.html", title="登录 - PyKYCH", error=None,
                  captcha_question=captcha["question"])


@auth_route.sub("/login").post
async def login_action(request: Request):
    """处理登录请求。"""
    form = await request.form()
    username = form.get("username", "").strip()
    password = form.get("password", "")
    captcha_input = form.get("captcha", "")

    if not username or not password:
        captcha = _generate_captcha(request)
        return render("login.html", title="登录 - PyKYCH",
                      error="用户名和密码不能为空。",
                      captcha_question=captcha["question"])

    # 验证验证码
    if not _verify_captcha(request, captcha_input):
        captcha = _generate_captcha(request)
        return render("login.html", title="登录 - PyKYCH",
                      error="验证码错误，请重试。",
                      captcha_question=captcha["question"])

    # 速率限制检查（防暴力破解）
    client_ip = auth_session._get_client_ip(request)
    allowed, rate_msg = auth_rate.check_login_rate_limit(username, client_ip)
    if not allowed:
        captcha = _generate_captcha(request)
        return render("login.html", title="登录 - PyKYCH",
                      error=rate_msg,
                      captcha_question=captcha["question"])

    user = await auth_user.get_user_with_password(username)
    if not user or not auth_pwd.verify_password(password, user["password_hash"]):
        # 记录登录失败（速率限制）
        client_ip2 = auth_session._get_client_ip(request)
        auth_rate.record_login_failure(username, client_ip2)
        captcha = _generate_captcha(request)
        return render("login.html", title="登录 - PyKYCH",
                      error="用户名或密码错误。",
                      captcha_question=captcha["question"])

    await auth_session.login_user(request, username)

    next_url = request.query_params.get("next", "/admin")
    return redirect(next_url)


@auth_route.sub("/logout").get
async def logout(request: Request):
    """登出。"""
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
    user = await auth_mod.get_current_user(request)
    if not user:
        return JSONResponse({"error": "请先登录"}, status_code=401)

    creds = await webauthn.get_credentials(user["username"])
    return JSONResponse({"credentials": creds})


@auth_route.sub("/webauthn/credentials/{cred_id}").delete
async def webauthn_delete_credential(cred_id: int, request: Request):
    """删除指定的通行密钥。"""
    user = await auth_mod.get_current_user(request)
    if not user:
        return JSONResponse({"error": "请先登录"}, status_code=401)

    success = await webauthn.delete_credential(cred_id)
    if success:
        return JSONResponse({"status": "ok"})
    else:
        return JSONResponse({"error": "凭据不存在"}, status_code=404)


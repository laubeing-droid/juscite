# -*- coding: utf-8 -*-
"""#43 订阅型推理引擎产品面（RE-43，2026-10-30 施工）。

唯一依据=juscite/docs/RE规格库/RE-43-订阅型推理引擎.md。机制等量吸收律台
lawdesk 0.4.2 lib/chatgpt.js（MIT，行为级对拍零复制），参照 Hermes 桌面版
（MIT）pill/协议合同由后续 UI 消费单对拍收口。**Claude 订阅族整族划出**
（2026-10-30 用户裁决：走本机 CLI 终端登录态非 OAuth 交接）；本面只做
OpenAI 订阅族 SIWC（Sign in with ChatGPT，OpenAI 预览协议——服务端行为
本地不可实证=规格 UNKNOWN-1，接入实测为准；授权/API 域名可注入 seam=规格
§2.1#13，全链可对本地模拟服务测试）。

行为面（规格 §2.1 穷举=对拍验收单）：
  - 登录：PKCE S256+state/nonce 随机+10 分钟窗一次性（#1）；scope 钉定含
    套餐用量位（#2）；动态客户端注册——首登 client_id 占位、回调以授权服务
    器回填值为准（#3）；回调校验链 fail-closed：state 对账→授权码换令牌→
    id_token 全链校验（RS256/ES256 签名经 JWKS 按 kid 取钥缓存 1h、iss/aud
    （-5s 容差）/exp/iat/nonce/sub 逐项硬校验，任一不过=拒；同 client_id
    换账号拒（#4）。
  - 存储：index（账号/绑定/待登录窗）与令牌凭证分离——**令牌只进
    credential_vault DPAPI 密文**（F12 公开面唯一权威，规格 §2.4#4 强于律台
    0o600 明文文件；index 零令牌字节）；hostId 每机一枚 urn:uuid 随授权参数
    ext_agent_host_id 上送（#5）。
  - 刷新：剩余寿命<120s 才刷；同账号串行（refresh token 每次轮换并发刷=
    作废风险）；earliest_refresh_at 节流（失败后 60s 内不重锤）；刷新成功=
    access/refresh/id_token/scopes/expires 整组替换（#6）。
  - 终态失效分流：终态码集→清凭证+标记需重登；invalid_client→具名指引重
    登；其余→保留凭证报错；**网络故障不清凭证**（#7）。
  - 退出撤销：向授权服务器 revoke refresh_token（3 试，5xx/传输错续试、
    4xx 即止）+删本地凭证+保留账号↔client_id 映射（#8）。
  - 请求期韧性：订阅请求 401=强制刷新重试一次；503=退避重试两次
    （1.5s/3s，测试可注入短档）（#9）。
  - 用量与错误语义：服务端错误码→具名码映射；套餐用量上限 wire 码→
    subscription_usage_limit；请求 ID 透传（#10）。
  - 模型列表：登录后拉 /models（visibility 过滤），账号缓存；默认模型=
    列表首项（#11）。
  - 双执行路：v1 主路=Responses API 直连（非流式整读，SSE 流式后续增强）；
    Codex 交接路=可选增强——configArgs+env 注入，**令牌走环境变量不经命令
    行**；Windows 下 codex 为 npm .cmd 包装时先落 shim 解析（桥增强三式·式
    三机制等量，tools/bridge/cli_shim.mjs:69-133 同构 Python 侧实现）（#12）。
  - 降级路（规格 §2.3 写死，用户点名差异化）：订阅可用三查（有已登录账号/
    无 needsLogin/scope 含套餐用量位）任一不满足→**不中断对话**自动切到
    该对话已配置的 API Key provider（OpenAI 兼容 /chat/completions 或
    Anthropic /v1/messages），回执带具名回落原因码；订阅恢复后不自动切回
    （来源选择权在用户）。回落动作回执 backend/来源字段——消费面落对话账
    可审计，不静默。

安全红线（规格 §2.4）：令牌不写日志不进 URL 不进错误码；错误只 typed
SubscriptionError（str 只有 siwc_* 码，密钥材料永不进入）；API Key 同走
vault（调用方持 vault 引用，本面不收明文键）。
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import secrets
import shutil
import threading
import time
import uuid
from pathlib import Path
from urllib.parse import urlencode

from bridge_errors import NotConnected
from opencode_http import Client, TransportError

ENGINE_ID = "siwc/1"
# 引擎来源标识（规格 §3.1：provider 族扩展，对齐 api:<providerId> 约定）。
BACKEND_SUBSCRIPTION = "chatgpt-sub:"
BACKEND_API_KEY = "api-key:"

# legal_entry 冻结方法组（组外方法绝不落到本面）。
SUBSCRIPTION_METHODS = frozenset({
    "subscription.status",
    "subscription.login_begin",
    "subscription.login_callback",
    "subscription.refresh",
    "subscription.logout",
    "subscription.models",
    "subscription.chat",
    "subscription.codex_handover",
})

# scope 钉定（SIWC 协议 wire 值；chatgpt.tokens.use.direct=套餐用量开关）。
SCOPES = ("openid profile email offline_access "
          "resource.invoke chatgpt.tokens.use.direct")
PLAN_USAGE_SCOPE = "chatgpt.tokens.use.direct"
DYNAMIC_CLIENT_PLACEHOLDER = "juscite-siwc-dynamic-client"
HOST_ID_PARAM = "ext_agent_host_id"

LOGIN_WINDOW_SECONDS = 600.0
MIN_VALID_SECONDS = 120.0          # 剩余寿命<120s 才刷（规格 §2.1#6）
HANDOVER_MIN_VALID_SECONDS = 900.0  # 交接路长轮余量 15 分钟
EARLIEST_REFRESH_SECONDS = 60.0    # 节流：失败后 60s 内不重锤
EXP_TOLERANCE_SECONDS = 5.0
JWKS_CACHE_SECONDS = 3600.0
REVOKE_MAX_ATTEMPTS = 3
BACKOFF_SCHEDULE = (1.5, 3.0)      # 503 退避两试（规格 §2.1#9）
USAGE_LIMIT_WIRE_CODE = "subscription_sharing_usage_limit_exceeded"
# 终态失效码集（清凭证+标记需重登；规格 §2.1#7）。
TERMINAL_REFRESH_CODES = frozenset({
    "invalid_grant", "invalid_refresh_token", "token_expired",
    "refresh_token_expired", "refresh_token_invalidated",
    "refresh_token_reused",
})
HANDOVER_ENV_KEY = "JUSCITE_SIWC_TOKEN"

VAULT_SERVICE = "juscite.siwc"
INDEX_SCHEMA = "siwc-index/1"
TOKENS_SCHEMA = "siwc-tokens/1"

_INDEX_FIELDS = frozenset({"schema", "hostId", "accounts",
                           "clientBindings", "pending"})
_ACCOUNT_FIELDS = frozenset({"clientId", "email", "scopes", "needsLogin",
                             "defaultModel", "models", "modelsFetchedAt"})
_PENDING_FIELDS = frozenset({"nonce", "verifier", "redirectPort",
                             "createdAt"})


class SubscriptionError(RuntimeError):
    """Typed engine failure; str() is an siwc_* code only（零密钥材料）。"""


# ── 注入 seam（规格 §2.1#13：授权/API 域名可注入→全链可对本地模拟服务）──

def _auth_base(config: dict) -> str:
    return str(config.get("siwc_auth_base")
               or os.environ.get("JUSCITE_SIWC_AUTH_BASE")
               or "https://auth.openai.com").rstrip("/")


def _api_base(config: dict) -> str:
    return str(config.get("siwc_api_base")
               or os.environ.get("JUSCITE_SIWC_API_BASE")
               or "https://chatgpt.com/backend-api/codex").rstrip("/")


def _backoff(config: dict) -> tuple:
    injected = config.get("siwc_backoff_schedule")
    return tuple(injected) if injected else BACKOFF_SCHEDULE


_now = time.time  # 可注入时钟（测试）


# ---------------------------------------------------------------------- #
# index 存储（零令牌字节；令牌只进 vault）
# ---------------------------------------------------------------------- #

def _index_path(config: dict) -> Path:
    root = (config.get("subscription_state_root")
            or config.get("vault_state_root")
            or config.get("harness_state_root"))
    if not root:
        raise SubscriptionError("siwc_state_root_not_configured")
    return Path(root) / "siwc" / "index.json"


def _load_index(config: dict) -> dict:
    path = _index_path(config)
    if not path.exists():
        return {"schema": INDEX_SCHEMA, "hostId": None, "accounts": {},
                "clientBindings": {}, "pending": {}}
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        raise SubscriptionError("siwc_index_unreadable") from None
    if not isinstance(data, dict) or data.get("schema") != INDEX_SCHEMA \
            or set(data) != _INDEX_FIELDS:
        raise SubscriptionError("siwc_index_invalid")
    return data


def _save_index(config: dict, index: dict) -> None:
    path = _index_path(config)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(index, ensure_ascii=False, sort_keys=True),
                   encoding="utf-8")
    os.replace(tmp, path)


def _host_id(config: dict, index: dict) -> str:
    """每机一枚 urn:uuid（规格 §2.1#5 hostId）。"""
    if not index.get("hostId"):
        index["hostId"] = "urn:uuid:" + str(uuid.uuid4())
        _save_index(config, index)
    return index["hostId"]


def _vault_root(config: dict):
    root = config.get("vault_state_root") or _index_path(config).parent.parent
    return root


def _load_tokens(config: dict, sub: str) -> dict:
    from credential_vault import vault_get, VaultError
    try:
        out = vault_get(_vault_root(config), VAULT_SERVICE, sub,
                        reveal=True)
    except VaultError as exc:
        raise SubscriptionError("siwc_tokens_missing:" + str(exc)) from None
    try:
        record = json.loads(base64.b64decode(out["secret_b64"]))
    except (ValueError, KeyError, TypeError):
        raise SubscriptionError("siwc_tokens_corrupt") from None
    if not isinstance(record, dict) or record.get("schema") != TOKENS_SCHEMA \
            or not isinstance(record.get("access_token"), str):
        raise SubscriptionError("siwc_tokens_corrupt")
    return record


def _save_tokens(config: dict, sub: str, record: dict) -> None:
    from credential_vault import vault_put
    payload = json.dumps(record, ensure_ascii=False,
                         sort_keys=True).encode("utf-8")
    vault_put(_vault_root(config), VAULT_SERVICE, sub, payload)


def _delete_tokens(config: dict, sub: str) -> None:
    from credential_vault import vault_delete, VaultError
    try:
        vault_delete(_vault_root(config), VAULT_SERVICE, sub)
    except VaultError:
        pass  # 幂等清理：登记已不存在=目标态已达成


# ---------------------------------------------------------------------- #
# HTTP 面（复用 opencode_http.Client：https/环回校验+typed 码+零重定向）
# ---------------------------------------------------------------------- #

def _client(config: dict, base: str, token: str | None = None) -> Client:
    headers = {}
    if token:
        # 令牌只进 Authorization 头——不进 URL 不进日志（规格 §2.4#1）。
        headers["Authorization"] = "Bearer " + token
    return Client(base, headers=headers,
                  timeout=float(config.get("siwc_timeout", 30)))


def _post_json(config: dict, base: str, path: str, body: dict,
               token: str | None = None):
    """POST JSON，返回 (status, parsed|None)。

    与 opencode_http.Client 的分工：Client 对 4xx/5xx 只回 typed 码并按纪
    律丢弃响应体；订阅面的用量上限/终态失效/4xx 即止分类**需要错误体里的
    wire 错误码**（规格 §2.1#7/#10）——此处复用 Client 的 base 校验与
    opener（环回/https 纪律不旁路），对 HTTPError 补一次结构化读体：只进
    解析不进日志不进错误码（密钥材料永不外泄）。
    """
    from urllib.error import HTTPError
    from urllib.request import Request
    client = _client(config, base, token)
    data = json.dumps(body, ensure_ascii=False).encode("utf-8")
    req = Request(client.url + path, data=data, method="POST", headers={
        "Accept": "application/json", "Content-Type": "application/json",
        **client.headers})
    try:
        with client.opener.open(req, timeout=client.timeout) as response:
            raw = response.read()
            status = response.status
    except HTTPError as exc:
        raw = exc.read()
        status = exc.code
    except TransportError:
        raise  # redirect_refused 等协议级
    except (OSError, TimeoutError):
        raise SubscriptionError("siwc_transport_unreachable") from None
    parsed = None
    if raw:
        try:
            parsed = json.loads(raw)
        except ValueError:
            parsed = None
    return status, parsed if isinstance(parsed, dict) else None


def _error_code(response: dict) -> str | None:
    for key in ("error", "code"):
        value = response.get(key)
        if isinstance(value, str) and value:
            return value
    err = response.get("error")
    if isinstance(err, dict) and isinstance(err.get("type"), str):
        return err["type"]
    detail = response.get("detail")
    if isinstance(detail, str) and detail:
        return detail
    return None


# ---------------------------------------------------------------------- #
# id_token 全链校验（规格 §2.1#4；六负例=对拍验收）
# ---------------------------------------------------------------------- #

_JWKS_CACHE: dict = {}
_JWKS_LOCK = threading.Lock()


def _b64url_decode(segment: str) -> bytes:
    padding = "=" * (-len(segment) % 4)
    return base64.urlsafe_b64decode(segment + padding)


def _fetch_jwks(config: dict) -> list:
    base = _auth_base(config)
    with _JWKS_LOCK:
        cached = _JWKS_CACHE.get(base)
        if cached and _now() - cached[0] < JWKS_CACHE_SECONDS:
            return cached[1]
        try:
            out = _client(config, base).request(
                "GET", "/.well-known/jwks.json")
        except TransportError as exc:
            raise SubscriptionError(
                "siwc_jwks_unreachable:" + exc.code) from None
        keys = out.get("keys") if isinstance(out, dict) else None
        if not isinstance(keys, list) or not keys:
            raise SubscriptionError("siwc_jwks_unavailable")
        _JWKS_CACHE[base] = (_now(), keys)
        return keys


def _verify_jwt_signature(signing_input: bytes, signature: bytes,
                          jwk: dict) -> None:
    from cryptography.exceptions import InvalidSignature

    def jwk_int(segment: str) -> int:
        # JWK 整数成分=base64url 无符号大端（RFC 7518），不是十六进制。
        return int.from_bytes(_b64url_decode(segment), "big")

    alg = jwk.get("alg") or jwk.get("kty")
    try:
        if alg in ("RS256", "RSA"):
            from cryptography.hazmat.primitives.asymmetric import (
                padding, rsa)
            public = rsa.RSAPublicNumbers(
                jwk_int(jwk["e"]), jwk_int(jwk["n"])).public_key()
            public.verify(signature, signing_input,
                          padding.PKCS1v15(), _sha256_alg())
        elif alg in ("ES256", "EC"):
            from cryptography.hazmat.primitives.asymmetric import ec
            from cryptography.hazmat.primitives.asymmetric.utils import (
                encode_dss_signature)
            public = ec.EllipticCurvePublicNumbers(
                jwk_int(jwk["x"]), jwk_int(jwk["y"]),
                ec.SECP256R1()).public_key()
            r = int.from_bytes(signature[:32], "big")
            s = int.from_bytes(signature[32:], "big")
            public.verify(encode_dss_signature(r, s), signing_input,
                          ec.ECDSA(_sha256_alg()))
        else:
            raise SubscriptionError("siwc_id_token_alg_rejected")
    except SubscriptionError:
        raise
    except (InvalidSignature, ValueError, TypeError, KeyError) as exc:
        raise SubscriptionError("siwc_id_token_signature_invalid") from exc


def _sha256_alg():
    from cryptography.hazmat.primitives import hashes
    return hashes.SHA256()


def _validate_id_token(config: dict, id_token: str, *, audience: str,
                       nonce: str) -> dict:
    """六项硬校验（签名/iss/aud/exp(-5s)/iat/nonce/sub）+kid 取钥。"""
    parts = id_token.split(".")
    if len(parts) != 3:
        raise SubscriptionError("siwc_id_token_malformed")
    try:
        header = json.loads(_b64url_decode(parts[0]))
        claims = json.loads(_b64url_decode(parts[1]))
    except (ValueError, TypeError):
        raise SubscriptionError("siwc_id_token_malformed") from None
    if header.get("alg") not in ("RS256", "ES256"):
        raise SubscriptionError("siwc_id_token_alg_rejected")
    kid = header.get("kid")
    jwk = next((k for k in _fetch_jwks(config)
                if isinstance(k, dict) and k.get("kid") == kid), None)
    if jwk is None:
        raise SubscriptionError("siwc_id_token_kid_unknown")
    signing_input = (parts[0] + "." + parts[1]).encode("ascii")
    _verify_jwt_signature(signing_input, _b64url_decode(parts[2]), jwk)
    now = _now()
    issuer = _auth_base(config)
    if claims.get("iss") != issuer:
        raise SubscriptionError("siwc_id_token_iss_mismatch")
    if claims.get("aud") != audience:
        raise SubscriptionError("siwc_id_token_aud_mismatch")
    exp = claims.get("exp")
    if not isinstance(exp, (int, float)) \
            or now > exp + EXP_TOLERANCE_SECONDS:
        raise SubscriptionError("siwc_id_token_expired")
    iat = claims.get("iat")
    if not isinstance(iat, (int, float)) or iat > now + EXP_TOLERANCE_SECONDS:
        raise SubscriptionError("siwc_id_token_iat_invalid")
    if claims.get("nonce") != nonce:
        raise SubscriptionError("siwc_id_token_nonce_mismatch")
    if not isinstance(claims.get("sub"), str) or not claims["sub"]:
        raise SubscriptionError("siwc_id_token_sub_missing")
    return claims


# ---------------------------------------------------------------------- #
# 刷新（串行+终态分流+网络错不清凭证；规格 §2.1#6/#7）
# ---------------------------------------------------------------------- #

_REFRESH_LOCKS: dict = {}


def _refresh_lock(sub: str) -> threading.Lock:
    lock = _REFRESH_LOCKS.get(sub)
    if lock is None:
        lock = threading.Lock()
        _REFRESH_LOCKS[sub] = lock
    return lock


def _issue_tokens(config: dict, sub: str, response: dict) -> dict:
    """整组替换（access/refresh/id_token/scopes/expires；规格 §2.1#6）。"""
    expires_in = response.get("expires_in")
    if not isinstance(expires_in, (int, float)) or expires_in <= 0:
        raise SubscriptionError("siwc_token_exchange_incomplete")
    record = {
        "schema": TOKENS_SCHEMA,
        "access_token": response.get("access_token"),
        "refresh_token": response.get("refresh_token"),
        "id_token": response.get("id_token"),
        "scopes": str(response.get("scope") or SCOPES).split(),
        "expires_at": _now() + float(expires_in),
        "earliest_refresh_at": _now(),
    }
    if not record["access_token"] or not record["refresh_token"]:
        raise SubscriptionError("siwc_token_exchange_incomplete")
    _save_tokens(config, sub, record)
    return record


def _refresh_tokens(config: dict, sub: str, *, force: bool = False) -> dict:
    """取有效令牌（必要时串行刷新）；force=请求期 401 强刷重试径。"""
    record = _load_tokens(config, sub)
    index = _load_index(config)
    account = index["accounts"].get(sub)
    if account is None:
        raise SubscriptionError("siwc_account_unknown")
    with _refresh_lock(sub):
        record = _load_tokens(config, sub)
        remaining = record["expires_at"] - _now()
        throttled = record["expires_at"] > _now() + EARLIEST_REFRESH_SECONDS \
            and record.get("earliest_refresh_at", 0) > _now()
        if not force and remaining >= MIN_VALID_SECONDS:
            return record  # 寿命足额：不刷（节流：未到期先用着）
        if throttled:
            if remaining > 0:
                return record
            raise SubscriptionError("siwc_refresh_throttled")
        body = {"grant_type": "refresh_token",
                "refresh_token": record["refresh_token"],
                "client_id": account["clientId"]}
        try:
            status, response = _post_json(config, _auth_base(config),
                                          "/oauth/token", body)
        except SubscriptionError as exc:
            # 网络故障不清凭证（规格 §2.1#7）；节流防重锤。
            record["earliest_refresh_at"] = _now() + EARLIEST_REFRESH_SECONDS
            _save_tokens(config, sub, record)
            raise SubscriptionError(
                "siwc_refresh_unreachable:" + str(exc)) from None
        if status != 200:
            code = _error_code(response or {})
            if status >= 500:
                record["earliest_refresh_at"] = (
                    _now() + EARLIEST_REFRESH_SECONDS)
                _save_tokens(config, sub, record)
                raise SubscriptionError(
                    "siwc_refresh_unreachable:http_%d" % status)
            if code in TERMINAL_REFRESH_CODES:
                _delete_tokens(config, sub)
                account["needsLogin"] = True
                _save_index(config, index)
                raise SubscriptionError(
                    "siwc_terminal_invalidated:" + code)
            if code == "invalid_client":
                raise SubscriptionError("siwc_relogin_required")
            raise SubscriptionError("siwc_refresh_rejected:" + str(code))
        response = response or {}
        record = _issue_tokens(config, sub, response)
        account["needsLogin"] = False
        _save_index(config, index)
        return record


def _active_account(index: dict) -> tuple | None:
    """订阅可用三查前置：取活跃账号（唯一 needsLogin=False 的账号）。"""
    for sub, account in index["accounts"].items():
        if not account.get("needsLogin"):
            return sub, account
    return None


def _availability(index: dict) -> tuple:
    """订阅可用三查（规格 §2.3）：有已登录账号/无 needsLogin/scope 含套餐
    用量位。返回 (sub, account) 或 (None, 回落原因码)。"""
    if not index["accounts"]:
        return None, "siwc_not_logged_in"
    active = _active_account(index)
    if active is None:
        return None, "siwc_needs_relogin"
    sub, account = active
    if PLAN_USAGE_SCOPE not in (account.get("scopes") or []):
        return None, "siwc_plan_usage_absent"
    return sub, None


# ---------------------------------------------------------------------- #
# 方法面
# ---------------------------------------------------------------------- #

def _require(args: dict, fields: frozenset, optional: frozenset = frozenset(),
             code: str = "subscription_args_invalid") -> None:
    if not isinstance(args, dict) \
            or not fields <= set(args) <= fields | optional:
        raise SubscriptionError(code)


def subscription_status(args: dict, config: dict) -> dict:
    _require(args, frozenset())
    index = _load_index(config)
    accounts = []
    for sub, account in index["accounts"].items():
        accounts.append({
            "sub": sub,
            "email": account.get("email"),
            "needsLogin": bool(account.get("needsLogin")),
            "planUsage": PLAN_USAGE_SCOPE in (account.get("scopes") or []),
            "defaultModel": account.get("defaultModel"),
            "models": account.get("models") or [],
        })
    active, reason = _availability(index)
    return {"engine": ENGINE_ID, "hostId": index.get("hostId"),
            "accounts": accounts, "activeSub": active,
            "available": active is not None,
            "unavailableReason": reason,
            "note": "Claude 订阅族已划出（2026-10-30 用户裁决）；本面只做"
                    "OpenAI 订阅族 SIWC"}


def subscription_login_begin(args: dict, config: dict) -> dict:
    _require(args, frozenset(), {"redirect_port"})
    from airplane_mode import enforce_bridge_egress
    enforce_bridge_egress(config, "model_round_remote", provider_id="siwc")
    port = args.get("redirect_port")
    if not isinstance(port, int) or not 1024 <= port <= 65535:
        raise SubscriptionError("siwc_redirect_port_invalid")
    index = _load_index(config)
    host_id = _host_id(config, index)
    verifier = base64.urlsafe_b64encode(
        secrets.token_bytes(48)).decode("ascii").rstrip("=")
    challenge = base64.urlsafe_b64encode(
        hashlib.sha256(verifier.encode("ascii")).digest()
    ).decode("ascii").rstrip("=")
    state = base64.urlsafe_b64encode(
        secrets.token_bytes(24)).decode("ascii").rstrip("=")
    nonce = base64.urlsafe_b64encode(
        secrets.token_bytes(16)).decode("ascii").rstrip("=")
    redirect_uri = "http://127.0.0.1:{}/auth/callback".format(port)
    url = _auth_base(config) + "/authorize?" + urlencode({
        "response_type": "code",
        "client_id": DYNAMIC_CLIENT_PLACEHOLDER,
        "redirect_uri": redirect_uri,
        "scope": SCOPES,
        "state": state,
        "nonce": nonce,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
        HOST_ID_PARAM: host_id,
    })
    # 10 分钟窗一次性：state 入账即占用，回调核销后不复用（规格 §2.1#1）。
    index["pending"][state] = {"nonce": nonce, "verifier": verifier,
                               "redirectPort": port,
                               "createdAt": _now()}
    _save_index(config, index)
    return {"authorizationUrl": url, "state": state,
            "expiresIn": int(LOGIN_WINDOW_SECONDS), "engine": ENGINE_ID,
            "redirectUri": redirect_uri}


def subscription_login_callback(args: dict, config: dict) -> dict:
    _require(args, frozenset({"code", "state"}))
    from airplane_mode import enforce_bridge_egress
    enforce_bridge_egress(config, "model_round_remote", provider_id="siwc")
    index = _load_index(config)
    pending = index["pending"].pop(args.get("state"), None)
    if pending is None or set(pending) != _PENDING_FIELDS:
        _save_index(config, index)  # 一次性：占用即核销
        raise SubscriptionError("siwc_state_mismatch")
    _save_index(config, index)
    if _now() - pending["createdAt"] > LOGIN_WINDOW_SECONDS:
        raise SubscriptionError("siwc_login_window_expired")
    body = {"grant_type": "authorization_code",
            "code": args.get("code"),
            "redirect_uri": "http://127.0.0.1:{}/auth/callback".format(
                pending["redirectPort"]),
            "client_id": DYNAMIC_CLIENT_PLACEHOLDER,
            "code_verifier": pending["verifier"]}
    try:
        status, response = _post_json(config, _auth_base(config),
                                      "/oauth/token", body)
    except SubscriptionError as exc:
        raise SubscriptionError("siwc_exchange_unreachable:" + str(exc)) \
            from None
    response = response or {}
    if status != 200:
        code = _error_code(response)
        if status >= 500:
            raise SubscriptionError("siwc_exchange_unreachable:http_%d"
                                    % status)
        raise SubscriptionError("siwc_exchange_rejected:" + str(code))
    # 动态客户端注册（规格 §2.1#3）：以授权服务器回填 client_id 为准。
    client_id = response.get("client_id") or DYNAMIC_CLIENT_PLACEHOLDER
    claims = _validate_id_token(config, response.get("id_token") or "",
                                audience=client_id,
                                nonce=pending["nonce"])
    sub = claims["sub"]
    bound = index["clientBindings"].get(client_id)
    if bound is not None and bound != sub:
        # 同 client_id 换账号拒（规格 §2.1#4）。
        raise SubscriptionError("siwc_client_account_switch_rejected")
    record = _issue_tokens(config, sub, response)
    index["clientBindings"][client_id] = sub
    index["accounts"][sub] = {
        "clientId": client_id,
        "email": claims.get("email"),
        "scopes": record["scopes"],
        "needsLogin": False,
        "defaultModel": None,
        "models": [],
        "modelsFetchedAt": None,
    }
    _save_index(config, index)
    out = {"account": {"sub": sub, "email": claims.get("email"),
                       "planUsage": PLAN_USAGE_SCOPE in record["scopes"]},
           "engine": ENGINE_ID}
    try:
        models = subscription_models({"sub": sub}, config)
        out["models"] = models["models"]
        out["defaultModel"] = models["defaultModel"]
    except SubscriptionError as exc:
        out["models"] = []
        out["defaultModel"] = None
        out["note"] = "登录成功但模型列表暂不可用：" + str(exc)
    return out


def subscription_refresh(args: dict, config: dict) -> dict:
    _require(args, frozenset(), {"sub"})
    index = _load_index(config)
    sub = args.get("sub") or _active_sub(index)
    record = _refresh_tokens(config, sub)
    return {"sub": sub, "expiresAt": record["expires_at"],
            "scopes": record["scopes"], "engine": ENGINE_ID}


def subscription_logout(args: dict, config: dict) -> dict:
    _require(args, {"sub"})
    from airplane_mode import enforce_bridge_egress
    enforce_bridge_egress(config, "model_round_remote", provider_id="siwc")
    index = _load_index(config)
    sub = args["sub"]
    account = index["accounts"].get(sub)
    if account is None:
        raise SubscriptionError("siwc_account_unknown")
    record = _load_tokens(config, sub)
    attempts = 0
    revoked = False
    while attempts < REVOKE_MAX_ATTEMPTS and not revoked:
        attempts += 1
        try:
            status, response = _post_json(
                config, _auth_base(config), "/oauth/revoke",
                {"token": record["refresh_token"],
                 "client_id": account["clientId"],
                 "token_type_hint": "refresh_token"})
        except SubscriptionError:
            continue  # 传输级失败续试（≤3 试；规格 §2.1#8）
        if status == 200:
            revoked = True
        elif status >= 500:
            continue  # 5xx 续试
        else:
            break  # 4xx 即止
    _delete_tokens(config, sub)
    account["needsLogin"] = True  # 清凭证+保留账号↔client_id 映射（#8）
    _save_index(config, index)
    return {"sub": sub, "revoked": revoked, "attempts": attempts,
            "engine": ENGINE_ID}


def _active_sub(index: dict) -> str:
    active = _active_account(index)
    if active is None:
        raise SubscriptionError("siwc_needs_relogin")
    return active[0]


def subscription_models(args: dict, config: dict) -> dict:
    _require(args, frozenset(), {"sub", "refresh"})
    from airplane_mode import enforce_bridge_egress
    enforce_bridge_egress(config, "model_round_remote", provider_id="siwc")
    index = _load_index(config)
    sub = args.get("sub") or _active_sub(index)
    account = index["accounts"].get(sub)
    if account is None:
        raise SubscriptionError("siwc_account_unknown")
    cached = account.get("models") or []
    fresh = account.get("modelsFetchedAt") and (
        _now() - account["modelsFetchedAt"] < 300.0)
    if cached and fresh and not args.get("refresh"):
        return {"sub": sub, "models": cached,
                "defaultModel": account.get("defaultModel"),
                "cached": True}
    record = _refresh_tokens(config, sub)
    try:
        out = _client(config, _api_base(config),
                      record["access_token"]).request("GET", "/models")
    except TransportError as exc:
        raise SubscriptionError("siwc_models_unreachable:" + exc.code) \
            from None
    rows = out.get("data") if isinstance(out, dict) else None
    if not isinstance(rows, list):
        raise SubscriptionError("siwc_models_invalid")
    models = sorted(
        str(row.get("slug") or row.get("id"))
        for row in rows
        if isinstance(row, dict) and row.get("visible", True) is not False
        and (row.get("slug") or row.get("id")))
    account["models"] = models
    account["defaultModel"] = models[0] if models else None  # 默认=首项（#11）
    account["modelsFetchedAt"] = _now()
    _save_index(config, index)
    return {"sub": sub, "models": models,
            "defaultModel": account["defaultModel"], "cached": False}


# ---------------------------------------------------------------------- #
# 对话轮（订阅主路 Responses 直连+韧性+用量映射+回落 API Key；规格 §2.1#9/
# #10、§2.3 写死降级路）
# ---------------------------------------------------------------------- #

def _subscription_turn(config: dict, sub: str, args: dict) -> dict:
    """订阅一轮：401 强刷重试一次/503 退避两试/用量上限具名（不静默）。"""
    body = {"model": args.get("model"), "input": args.get("input"),
            "stream": False, "store": False}
    if args.get("reasoning"):
        body["reasoning"] = {"effort": args["reasoning"]}
    schedule = _backoff(config)
    attempts_limit = 1 + len(schedule)
    force_refresh = False
    status = None
    parsed = None
    for attempt in range(attempts_limit + 1):
        record = _refresh_tokens(config, sub, force=force_refresh)
        try:
            status, parsed = _post_json(config, _api_base(config),
                                        "/responses", body,
                                        token=record["access_token"])
        except SubscriptionError as exc:
            raise SubscriptionError("siwc_turn_failed:" + str(exc)) \
                from None
        if status == 200:
            break
        if status == 401 and not force_refresh:
            force_refresh = True  # 401=强制刷新重试一次（规格 §2.1#9）
            continue
        if status == 503 and attempt < attempts_limit:
            time.sleep(schedule[attempt])  # 503 退避重试两试（#9）
            continue
        code = _error_code(parsed or {})
        if code == USAGE_LIMIT_WIRE_CODE:
            raise SubscriptionError("subscription_usage_limit")
        if code:
            raise SubscriptionError("siwc_turn_rejected:" + code)
        raise SubscriptionError("siwc_turn_failed:http_%d" % status)
    if not isinstance(parsed, dict):
        raise SubscriptionError("siwc_turn_protocol_invalid")
    error_code = _error_code(parsed.get("error") or {}
                             if isinstance(parsed.get("error"), dict)
                             else parsed)
    if error_code == USAGE_LIMIT_WIRE_CODE:
        raise SubscriptionError("subscription_usage_limit")
    if error_code:
        raise SubscriptionError("siwc_turn_rejected:" + error_code)
    text = None
    for item in parsed.get("output") or []:
        if isinstance(item, dict) and item.get("type") == "message":
            for part in item.get("content") or []:
                if isinstance(part, dict) and part.get("text"):
                    text = part["text"]
    return {"text": text,
            "requestId": parsed.get("request_id")
            or parsed.get("id")}


def _fallback_turn(config: dict, fallback: dict, args: dict) -> dict:
    """回落路（规格 §2.3 写死）：API Key provider 轮——键只从 vault 取。"""
    kind = fallback.get("kind")
    if kind not in ("openai-compat", "anthropic"):
        raise SubscriptionError("siwc_fallback_kind_invalid")
    base = str(fallback.get("api_base") or "").rstrip("/")
    if not base:
        raise SubscriptionError("siwc_fallback_base_required")
    key_ref = fallback.get("key_vault")
    if not isinstance(key_ref, dict) \
            or set(key_ref) != {"service", "account"}:
        raise SubscriptionError("siwc_fallback_key_ref_invalid")
    from credential_vault import vault_get, VaultError
    try:
        revealed = vault_get(_vault_root(config), key_ref["service"],
                             key_ref["account"], reveal=True)
    except VaultError as exc:
        raise SubscriptionError("siwc_fallback_key_missing:" + str(exc)) \
            from None
    api_key = base64.b64decode(revealed["secret_b64"]).decode("utf-8")
    model = fallback.get("model") or args.get("model")
    if kind == "openai-compat":
        path = "/chat/completions"
        body = {"model": model, "messages": [{"role": "user",
                                              "content": args.get("input")}]}
    else:
        path = "/v1/messages"
        body = {"model": model, "max_tokens": 1024,
                "messages": [{"role": "user", "content": args.get("input")}]}
    try:
        status, parsed = _post_json(config, base, path, body, token=api_key)
    except SubscriptionError as exc:
        raise SubscriptionError("siwc_fallback_failed:" + str(exc)) from None
    if status != 200:
        raise SubscriptionError("siwc_fallback_failed:http_%d" % status)
    parsed = parsed or {}
    if not isinstance(parsed, dict):
        raise SubscriptionError("siwc_fallback_protocol_invalid")
    text = parsed.get("output_text")
    if text is None:
        choices = parsed.get("choices") or []
        text = choices[0].get("message", {}).get("content") if choices \
            else parsed.get("content", {}).get("text")
    return {"text": text, "requestId": parsed.get("id")}


def subscription_chat(args: dict, config: dict) -> dict:
    _require(args, frozenset({"input"}), {"model", "reasoning", "sub",
                                          "fallback", "conversation"})
    from airplane_mode import enforce_bridge_egress
    enforce_bridge_egress(config, "model_round_remote", provider_id="siwc")
    index = _load_index(config)
    sub = args.get("sub")
    if sub:
        if sub not in index["accounts"]:
            raise SubscriptionError("siwc_account_unknown")
    else:
        available, reason = _availability(index)
        sub = available
        if sub is None:
            if not isinstance(args.get("fallback"), dict):
                raise SubscriptionError(reason)  # 未配回落＝具名拒不伪答
            return _chat_out(
                *_fallback_turn(config, args["fallback"], args),
                backend=BACKEND_API_KEY + str(
                    args["fallback"].get("name") or "fallback"),
                fallback_reason=reason)
    try:
        turn = _subscription_turn(config, sub, args)
        return _chat_out(turn["text"], turn["requestId"],
                         backend=BACKEND_SUBSCRIPTION + sub,
                         fallback_reason=None)
    except SubscriptionError as exc:
        # 订阅路不可用→不中断对话：自动回落（规格 §2.3 写死）；回落回执带
        # 具名原因码（未登录/需重登/未开套餐/用量上限/终态失效类），消费面
        # 落对话账可审计。订阅恢复后不自动切回（来源选择权在用户）。
        reason = str(exc)
        if reason == "subscription_usage_limit" \
                or reason.startswith("siwc_terminal_invalidated") \
                or reason in ("siwc_needs_relogin",
                              "siwc_relogin_required") \
                or reason.startswith("siwc_turn_failed:") \
                or reason.startswith("siwc_turn_rejected:") \
                or reason.startswith("siwc_refresh_"):
            if isinstance(args.get("fallback"), dict):
                fallback = _fallback_turn(config, args["fallback"], args)
                return _chat_out(
                    fallback["text"], fallback["requestId"],
                    backend=BACKEND_API_KEY + str(
                        args["fallback"].get("name") or "fallback"),
                    fallback_reason=reason)
        raise  # 其余（DTO/回落自身失败）原样具名，绝不伪答


def _chat_out(text, request_id, *, backend, fallback_reason) -> dict:
    return {"backend": backend, "fallbackUsed": fallback_reason is not None,
            "fallbackReason": fallback_reason, "replyText": text,
            "requestId": request_id, "engine": ENGINE_ID,
            "note": "回落动作回执带 backend/来源字段——消费面落对话账可审计"
                    "（不静默）；订阅恢复后不自动切回"}


# ---------------------------------------------------------------------- #
# Codex 交接路（可选增强；规格 §2.1#12 前半+桥增强三式·式三 shim）
# ---------------------------------------------------------------------- #

_WIN_EXE_ORDER = (".exe", ".cmd", ".bat", ".com")
_SHIM_TARGET_RE = '"%~dp0[\\\\/]([^"]+)"'


def _resolve_cli(command: str, explicit: str | None) -> dict:
    """CLI 解析（机制等量=tools/bridge/cli_shim.mjs:69-133 的 Python 侧形
    态）：显式优先→PATH 扩展序探测→.cmd/.bat shim 解析（剔 node.exe 与二
    级包装、优先 js 入口）→argv 数组形态（exe 直跑/node 直跑，零 shell）。
    """
    path = explicit
    if path:
        if not Path(path).is_file():
            raise SubscriptionError("siwc_cli_path_missing")
    else:
        for ext in _WIN_EXE_ORDER:
            found = shutil.which(command + ext) if os.name == "nt" \
                else shutil.which(command)
            if found:
                path = found
                break
        if not path:
            raise SubscriptionError("siwc_cli_not_found")
    suffix = Path(path).suffix.lower()
    if suffix in (".cmd", ".bat"):
        text = Path(path).read_text(encoding="utf-8", errors="replace")
        targets = []
        import re
        for match in re.finditer(_SHIM_TARGET_RE, text):
            targets.append(match.group(1))
        real = [t for t in targets
                if not t.lower().endswith("node.exe")
                and Path(t).suffix.lower() not in (".cmd", ".bat", ".ps1")]
        entry = next((t for t in real
                      if Path(t).suffix.lower() in (".js", ".mjs", ".cjs")),
                     real[0] if real else None)
        if not entry:
            raise SubscriptionError("siwc_cli_shim_unparseable")
        target = (Path(path).parent / entry).resolve()
        if not target.is_file():
            raise SubscriptionError("siwc_cli_shim_target_missing")
        if target.suffix.lower() == ".exe":
            return {"argv": [str(target)], "origin": "shim-exe",
                    "wrapper": path}
        node = shutil.which("node")
        if not node:
            raise SubscriptionError("siwc_node_not_found")
        return {"argv": [node, str(target)], "origin": "shim-node",
                "wrapper": path}
    if suffix in (".js", ".mjs", ".cjs"):
        node = shutil.which("node")
        if not node:
            raise SubscriptionError("siwc_node_not_found")
        return {"argv": [node, path], "origin": "node-script",
                "wrapper": None}
    return {"argv": [path], "origin": "direct", "wrapper": None}


def subscription_codex_handover(args: dict, config: dict) -> dict:
    _require(args, frozenset(), {"sub", "codex_command",
                                 "codex_path"})
    from airplane_mode import enforce_bridge_egress
    enforce_bridge_egress(config, "model_round_remote", provider_id="siwc")
    index = _load_index(config)
    sub = args.get("sub") or _active_sub(index)
    record = _refresh_tokens(config, sub)  # 交接取长轮余量（15 分钟）
    if record["expires_at"] - _now() < HANDOVER_MIN_VALID_SECONDS:
        raise SubscriptionError("siwc_handover_token_short_lived")
    resolved = _resolve_cli("codex", args.get("codex_path"))
    return {
        "sub": sub,
        "command": resolved["argv"],
        "providerConfig": {
            "configArgs": {
                "base_url": _api_base(config),
                "env_key": HANDOVER_ENV_KEY,
                "wire_api": "responses",
            },
            "note": "provider 配置以 configArgs 注入；wire_api=responses",
        },
        "env": {HANDOVER_ENV_KEY: record["access_token"]},
        "origin": resolved["origin"],
        "engine": ENGINE_ID,
        "note": "令牌只走环境变量（"
                + HANDOVER_ENV_KEY + "）不经命令行；Windows .cmd 包装经"
                "shim 解析直跑（桥增强三式·式三机制等量）",
    }


# ---------------------------------------------------------------------- #
# legal_entry 冻结方法组分发
# ---------------------------------------------------------------------- #

def subscription_call(method: str, args: dict, config: dict) -> dict:
    """未列方法绝不落到这里。"""
    handler = {
        "subscription.status": subscription_status,
        "subscription.login_begin": subscription_login_begin,
        "subscription.login_callback": subscription_login_callback,
        "subscription.refresh": subscription_refresh,
        "subscription.logout": subscription_logout,
        "subscription.models": subscription_models,
        "subscription.chat": subscription_chat,
        "subscription.codex_handover": subscription_codex_handover,
    }.get(method)
    if handler is None:
        raise SubscriptionError("subscription_method_unknown:" + method)
    return handler(args, config)

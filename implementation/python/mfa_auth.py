# -*- coding: utf-8 -*-
"""F06 MFA 两步验证产品面（工单 W5-U08）。

06 V7-06 assertion：MFA注册登录恢复与失效真实可用；密钥和恢复码不明文日志。
owner=product（UI_HOST_OR_NEW_PRODUCT：新增产品合同/持久化，不冒已有业务
入口，不创第二 Agent loop）。preserved（16 决策保留表 F06 行）：自托管认证
先做密码级——本面即「密码级基底 + MFA 增强层」：auth.register/auth.login
为密码级最小身份面；TOTP/恢复码是其上的增强层，不重建、不替代既有身份与
案件权限权威（F04 harness 面已 VERIFIED，本面零改动零复制）。

设计（最小必要面）：
  - 密码级基底：auth.register 落 PBKDF2-HMAC-SHA256 盐化校验值（16B 盐，
    210k 轮）到 ``<mfa_state_root>/accounts/<user>.json``；明文密码只在
    调用方进程内存，本面任何路径不写明文、不打日志、错误码零材料。
  - MFA 增强层凭据归产品凭据设施（F12 保险库先例 W3-U09）：TOTP 密钥
    （20B）＝保险库登记位 ``lvyin.mfa/<user>.totp-v1`` DPAPI 密文 blob；
    恢复码只在 enroll 回执出现一次，持久化面只有逐码盐化 sha256
    （``lvyin.mfa/<user>.recovery-v1``，仍经保险库加密）——存储面结构性
    不存在 TOTP 密钥与恢复码明文。
  - TOTP＝RFC 6238（HMAC-SHA1/6 位/30s/±1 窗口）；时间一律显式 ``now``
    纪元秒入参（确定性合成时钟注入：过期/失效窗口可复现）；防重放＝
    last-used 计数器单调（同窗复用＝mfa_totp_replay 具名拒）。
  - 登录两步：auth.login 密码过→未注册 MFA＝直接发会话（密码级基底语义，
    preserved「先做密码级」）；已注册＝mfa_required 挑战（绝不发会话），
    mfa.verify/mfa.recover 补第二因子→才发会话。
  - 恢复：mfa.recover 逐码盐化哈希核对，命中即从存面摘除（一次性消费，
    复用＝具名拒）；回执带剩余计数。
  - 失效：mfa.disable（密码＋任一有效第二因子）拆除保险库登记位＋账户
    MFA 位；拆后 TOTP/恢复码一律 mfa_not_enrolled 具名拒，登录回落密码级。
  - 会话：随机 token 只在回执出现，存面只有 token 的 sha256；auth.session
    只读回读（过期＝mfa_session_expired 具名拒）。

错误全部 typed（MfaAuthError 的 str 只有 mfa_*/vault_* 码）；材料与凭据
内容永不进入错误码。本面零日志零 print；产品应用数据目录零触碰（状态根
一律调用方显式配置）。
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import re
import secrets
import struct
import tempfile
from pathlib import Path

MFA_SCHEMA = "lvyin-f06-mfa/1"
SESSION_SCHEMA = "lvyin-f06-session/1"

# legal_entry 冻结方法组（组外方法绝不落到本面）。
MFA_AUTH_METHODS = frozenset({
    "auth.register", "auth.login", "auth.session",
    "mfa.enroll", "mfa.verify", "mfa.recover", "mfa.status", "mfa.disable",
})

# MFA 增强层凭据在产品凭据设施（F12 保险库）的登记位前缀。
MFA_VAULT_SERVICE = "lvyin.mfa"
_TOTP_ACCOUNT_SUFFIX = ".totp-v1"
_RECOVERY_ACCOUNT_SUFFIX = ".recovery-v1"

# 密码级基底参数（PBKDF2-HMAC-SHA256）。
PBKDF2_ALGO = "pbkdf2-hmac-sha256"
PBKDF2_ITERATIONS = 210_000
_PASSWORD_SALT_BYTES = 16
_PASSWORD_MAX_BYTES = 1024

# TOTP 参数（RFC 6238，认证器 App 兼容形）。
TOTP_STEP = 30
TOTP_DIGITS = 6
TOTP_WINDOW = 1          # 接受 ±1 窗口（时钟漂移惯例）
_TOTP_FAR_SCAN = 10      # 「过期窗口」具名判定的扫描半径（±10 窗）
_TOTP_SECRET_BYTES = 20

# 恢复码：10 hex 字符 × 8 枚。
RECOVERY_CODE_COUNT = 8
_RECOVERY_CODE_BYTES = 5
_RECOVERY_SALT_BYTES = 16

# 会话 TTL（秒）。
SESSION_TTL_SECONDS = 3600

_USER_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")


class MfaAuthError(RuntimeError):
    """Typed MFA/auth failure; str() is an mfa_*/vault_* code only."""


# ---------------------------------------------------------------------- #
# TOTP 核心（RFC 6238；时间显式注入，零内隐时钟）
# ---------------------------------------------------------------------- #

def totp_at(secret: bytes, now_epoch: int, step: int = TOTP_STEP,
            digits: int = TOTP_DIGITS) -> str:
    """RFC 6238 HOTP 型截断：确定性（同 secret 同 now 同码）。"""
    counter = int(now_epoch) // int(step)
    msg = struct.pack(">Q", counter)
    digest = hmac.new(secret, msg, hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    code = (int.from_bytes(digest[offset:offset + 4], "big")
            & 0x7FFFFFFF) % (10 ** int(digits))
    return str(code).zfill(int(digits))


def secret_to_base32(secret: bytes) -> str:
    return base64.b32encode(secret).decode("ascii").rstrip("=")


def provisioning_uri(user_id: str, secret: bytes) -> str:
    return ("otpauth://totp/JusBench:%s?secret=%s&issuer=JusBench"
            "&algorithm=SHA1&digits=%d&period=%d"
            % (user_id, secret_to_base32(secret), TOTP_DIGITS, TOTP_STEP))


# ---------------------------------------------------------------------- #
# 存取小面（账户/会话/保险库登记位）
# ---------------------------------------------------------------------- #

def _state_roots(config: dict) -> tuple[str, str]:
    cfg = config or {}
    mfa_root = cfg.get("mfa_state_root")
    vault_root = cfg.get("vault_state_root")
    if not mfa_root:
        raise MfaAuthError("mfa_state_root_not_configured")
    if not vault_root:
        raise MfaAuthError("vault_state_root_not_configured")
    return str(mfa_root), str(vault_root)


def _check_user(user_id) -> str:
    if not isinstance(user_id, str) or not _USER_RE.match(user_id) \
            or ".." in user_id:
        raise MfaAuthError("mfa_user_id_invalid")
    return user_id


def _check_password(password) -> None:
    if not isinstance(password, str) or not password:
        raise MfaAuthError("mfa_password_required")
    if len(password.encode("utf-8")) > _PASSWORD_MAX_BYTES:
        raise MfaAuthError("mfa_password_oversized")


def _check_now(now) -> int:
    if isinstance(now, bool) or not isinstance(now, int) or now < 0:
        raise MfaAuthError("mfa_now_required")
    return now


def _account_path(mfa_root: str, user_id: str) -> Path:
    return Path(mfa_root) / "accounts" / (user_id + ".json")


def _atomic_write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(dir=str(path.parent),
                                    prefix=path.stem + "-", suffix=".tmp")
    os.close(fd)
    with open(tmp_name, "w", encoding="utf-8", newline="\n") as handle:
        json.dump(payload, handle, ensure_ascii=False, sort_keys=True,
                  indent=1)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(tmp_name, path)


def _load_account(mfa_root: str, user_id: str) -> dict | None:
    path = _account_path(mfa_root, user_id)
    if not path.is_file():
        return None
    try:
        account = json.loads(path.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        raise MfaAuthError("mfa_account_store_invalid") from None
    if account.get("schema") != MFA_SCHEMA:
        raise MfaAuthError("mfa_account_store_invalid")
    return account


def _password_verifier(password: str, salt: bytes,
                       iterations: int) -> bytes:
    return hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt,
                               iterations)


def _vault_put(vault_root: str, account: str, secret: bytes) -> None:
    from credential_vault import vault_put, VaultError
    try:
        vault_put(vault_root, MFA_VAULT_SERVICE, account, secret, "dpapi")
    except VaultError as exc:
        raise MfaAuthError(str(exc)) from None


def _vault_get(vault_root: str, account: str) -> bytes | None:
    """取第二因子密料；登记位缺失＝None（未注册语义由调用方定）。"""
    from credential_vault import vault_get, VaultError
    try:
        out = vault_get(vault_root, MFA_VAULT_SERVICE, account, "dpapi",
                        reveal=True)
    except VaultError as exc:
        if str(exc).startswith("vault_entry_missing"):
            return None
        raise MfaAuthError(str(exc)) from None
    return base64.b64decode(out["secret_b64"])


def _vault_delete(vault_root: str, account: str) -> None:
    from credential_vault import vault_delete, VaultError
    try:
        vault_delete(vault_root, MFA_VAULT_SERVICE, account, "dpapi")
    except VaultError as exc:
        if not str(exc).startswith("vault_entry_missing"):
            raise MfaAuthError(str(exc)) from None


# ---------------------------------------------------------------------- #
# 恢复码存面（保险库内 JSON：逐码盐化哈希；结构性零明文）
# ---------------------------------------------------------------------- #

def _recovery_hash(code: str, salt: bytes) -> bytes:
    return hashlib.sha256(salt + code.encode("utf-8")).digest()


def _put_recovery_hashes(vault_root: str, user_id: str,
                         codes: list[str]) -> int:
    entries = []
    for code in codes:
        salt = os.urandom(_RECOVERY_SALT_BYTES)
        entries.append({"salt_hex": salt.hex(),
                        "verifier_hex": _recovery_hash(code, salt).hex()})
    payload = json.dumps({"schema": MFA_SCHEMA, "entries": entries},
                         sort_keys=True, separators=(",", ":"))
    _vault_put(vault_root, user_id + _RECOVERY_ACCOUNT_SUFFIX,
               payload.encode("utf-8"))
    return len(entries)


def _load_recovery_hashes(vault_root: str, user_id: str) -> list[dict]:
    blob = _vault_get(vault_root, user_id + _RECOVERY_ACCOUNT_SUFFIX)
    if blob is None:
        return []
    try:
        payload = json.loads(blob.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        raise MfaAuthError("mfa_recovery_store_invalid") from None
    if payload.get("schema") != MFA_SCHEMA:
        raise MfaAuthError("mfa_recovery_store_invalid")
    return list(payload.get("entries") or [])


def _consume_recovery_code(vault_root: str, user_id: str,
                           code: str) -> tuple[bool, int]:
    """命中即摘除（一次性消费）；返回 (命中?, 剩余数)。"""
    entries = _load_recovery_hashes(vault_root, user_id)
    for index, entry in enumerate(entries):
        salt = bytes.fromhex(entry["salt_hex"])
        if hmac.compare_digest(bytes.fromhex(entry["verifier_hex"]),
                               _recovery_hash(code, salt)):
            entries.pop(index)
            _put_recovery_entries(vault_root, user_id, entries)
            return True, len(entries)
    return False, len(entries)


def _put_recovery_entries(vault_root: str, user_id: str,
                          entries: list[dict]) -> None:
    payload = json.dumps({"schema": MFA_SCHEMA, "entries": entries},
                         sort_keys=True, separators=(",", ":"))
    _vault_put(vault_root, user_id + _RECOVERY_ACCOUNT_SUFFIX,
               payload.encode("utf-8"))


# ---------------------------------------------------------------------- #
# 会话
# ---------------------------------------------------------------------- #

def _session_path(mfa_root: str, token: str) -> Path:
    token_sha = hashlib.sha256(token.encode("utf-8")).hexdigest()
    return Path(mfa_root) / "sessions" / (token_sha + ".json")


def _issue_session(mfa_root: str, user_id: str, factor: str,
                   now: int) -> dict:
    token = secrets.token_urlsafe(32)
    _atomic_write_json(_session_path(mfa_root, token), {
        "schema": SESSION_SCHEMA, "user_id": user_id, "factor": factor,
        "created_at": now, "expires_at": now + SESSION_TTL_SECONDS,
    })
    return {"session_token": token, "factor": factor,
            "expires_at": now + SESSION_TTL_SECONDS}


# ---------------------------------------------------------------------- #
# 方法面
# ---------------------------------------------------------------------- #

def auth_register(args: dict, mfa_root: str, vault_root: str) -> dict:
    user_id = _check_user(args.get("user_id"))
    _check_password(args.get("password"))
    now = _check_now(args.get("now"))
    if _load_account(mfa_root, user_id) is not None:
        raise MfaAuthError("mfa_user_exists")
    salt = os.urandom(_PASSWORD_SALT_BYTES)
    _atomic_write_json(_account_path(mfa_root, user_id), {
        "schema": MFA_SCHEMA, "user_id": user_id,
        "algo": PBKDF2_ALGO, "iterations": PBKDF2_ITERATIONS,
        "salt_hex": salt.hex(),
        "verifier_hex": _password_verifier(args["password"], salt,
                                           PBKDF2_ITERATIONS).hex(),
        "created_at": now, "mfa": "none",
    })
    return {"registered": True, "user_id": user_id, "mfa": "none",
            "note": "密码级基底（preserved：自托管认证先做密码级）；"
                    "存面只有 PBKDF2 盐化校验值，零明文密码"}


def _verify_password(account: dict, password) -> None:
    _check_password(password)
    salt = bytes.fromhex(account["salt_hex"])
    verifier = _password_verifier(password, salt, int(account["iterations"]))
    if not hmac.compare_digest(verifier,
                               bytes.fromhex(account["verifier_hex"])):
        raise MfaAuthError("mfa_password_mismatch")


def auth_login(args: dict, mfa_root: str, vault_root: str) -> dict:
    user_id = _check_user(args.get("user_id"))
    now = _check_now(args.get("now"))
    account = _load_account(mfa_root, user_id)
    if account is None:
        raise MfaAuthError("mfa_user_unknown")
    _verify_password(account, args.get("password"))
    if account.get("mfa") == "totp":
        # 两步登录第一步过：绝不发会话，只发挑战。
        return {"status": "mfa_required", "user_id": user_id,
                "second_factors": ["totp", "recovery"],
                "note": "MFA 增强层在位：第二因子补齐才发会话"}
    session = _issue_session(mfa_root, user_id, "password", now)
    return {"status": "ok", "user_id": user_id, **session}


def auth_session(args: dict, mfa_root: str, vault_root: str) -> dict:
    token = args.get("session_token")
    if not isinstance(token, str) or not token:
        raise MfaAuthError("mfa_session_token_required")
    now = _check_now(args.get("now"))
    path = _session_path(mfa_root, token)
    if not path.is_file():
        raise MfaAuthError("mfa_session_unknown")
    try:
        session = json.loads(path.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        raise MfaAuthError("mfa_session_store_invalid") from None
    if session.get("schema") != SESSION_SCHEMA:
        raise MfaAuthError("mfa_session_store_invalid")
    if now >= int(session["expires_at"]):
        raise MfaAuthError("mfa_session_expired")
    return {"user_id": session["user_id"], "factor": session["factor"],
            "expires_at": session["expires_at"]}


def mfa_enroll(args: dict, mfa_root: str, vault_root: str) -> dict:
    user_id = _check_user(args.get("user_id"))
    now = _check_now(args.get("now"))
    account = _load_account(mfa_root, user_id)
    if account is None:
        raise MfaAuthError("mfa_user_unknown")
    _verify_password(account, args.get("password"))
    if account.get("mfa") == "totp":
        raise MfaAuthError("mfa_already_enrolled")
    secret = os.urandom(_TOTP_SECRET_BYTES)
    _vault_put(vault_root, user_id + _TOTP_ACCOUNT_SUFFIX, secret)
    codes = [secrets.token_hex(_RECOVERY_CODE_BYTES)
             for _ in range(RECOVERY_CODE_COUNT)]
    _put_recovery_hashes(vault_root, user_id, codes)
    account["mfa"] = "totp"
    account["mfa_enrolled_at"] = now
    account["totp_last_counter"] = -1
    _atomic_write_json(_account_path(mfa_root, user_id), account)
    return {"enrolled": True, "user_id": user_id,
            "algorithm": "SHA1", "digits": TOTP_DIGITS, "step": TOTP_STEP,
            "secret_base32": secret_to_base32(secret),
            "otpauth_uri": provisioning_uri(user_id, secret),
            "recovery_codes": codes,
            "recovery_count": RECOVERY_CODE_COUNT,
            "disclosure": "secret_base32/recovery_codes 只在本回执出现一次；"
                          "持久化面只有保险库密文与逐码盐化哈希"}


def _load_totp_secret(vault_root: str, user_id: str) -> bytes:
    secret = _vault_get(vault_root, user_id + _TOTP_ACCOUNT_SUFFIX)
    if secret is None or len(secret) != _TOTP_SECRET_BYTES:
        raise MfaAuthError("mfa_totp_key_unavailable")
    return secret


def _verify_totp(account: dict, vault_root: str, user_id: str,
                 code, now: int, *, update_replay: bool) -> int:
    """核 TOTP；接受 ±TOTP_WINDOW 窗；重放/过期/错码分具名。
    返回接受窗计数器（update_replay=True 时同账更新防重放位）。"""
    if not isinstance(code, str):
        raise MfaAuthError("mfa_totp_invalid")
    text = code.strip()
    if not text.isdigit() or len(text) != TOTP_DIGITS:
        raise MfaAuthError("mfa_totp_invalid")
    secret = _load_totp_secret(vault_root, user_id)
    counter = now // TOTP_STEP
    last_used = int(account.get("totp_last_counter") or -1)
    near = [counter + delta
            for delta in range(-TOTP_WINDOW, TOTP_WINDOW + 1)]
    accepted = next((c for c in near
                     if hmac.compare_digest(
                         totp_at(secret, c * TOTP_STEP), text)), None)
    if accepted is not None:
        if accepted <= last_used:
            raise MfaAuthError("mfa_totp_replay")
        if update_replay:
            account["totp_last_counter"] = accepted
        return accepted
    far = [counter + delta
           for delta in range(-_TOTP_FAR_SCAN, _TOTP_FAR_SCAN + 1)
           if counter + delta not in near]
    if any(totp_at(secret, c * TOTP_STEP) == text for c in far):
        raise MfaAuthError("mfa_totp_window_exceeded")
    raise MfaAuthError("mfa_totp_invalid")


def mfa_verify(args: dict, mfa_root: str, vault_root: str) -> dict:
    user_id = _check_user(args.get("user_id"))
    now = _check_now(args.get("now"))
    account = _load_account(mfa_root, user_id)
    if account is None:
        raise MfaAuthError("mfa_user_unknown")
    if account.get("mfa") != "totp":
        raise MfaAuthError("mfa_not_enrolled")
    _verify_totp(account, vault_root, user_id, args.get("code"), now,
                 update_replay=True)
    _atomic_write_json(_account_path(mfa_root, user_id), account)
    session = _issue_session(mfa_root, user_id, "totp", now)
    return {"status": "ok", "user_id": user_id, **session}


def mfa_recover(args: dict, mfa_root: str, vault_root: str) -> dict:
    user_id = _check_user(args.get("user_id"))
    now = _check_now(args.get("now"))
    account = _load_account(mfa_root, user_id)
    if account is None:
        raise MfaAuthError("mfa_user_unknown")
    if account.get("mfa") != "totp":
        raise MfaAuthError("mfa_not_enrolled")
    code = args.get("recovery_code")
    if not isinstance(code, str) or not code.strip():
        raise MfaAuthError("mfa_recovery_code_required")
    consumed, remaining = _consume_recovery_code(
        vault_root, user_id, code.strip().lower())
    if not consumed:
        raise MfaAuthError("mfa_recovery_code_invalid")
    session = _issue_session(mfa_root, user_id, "recovery", now)
    return {"status": "ok", "recovered": True, "user_id": user_id,
            "remaining_recovery_codes": remaining, **session}


def mfa_status(args: dict, mfa_root: str, vault_root: str) -> dict:
    user_id = _check_user(args.get("user_id"))
    account = _load_account(mfa_root, user_id)
    if account is None:
        raise MfaAuthError("mfa_user_unknown")
    enrolled = account.get("mfa") == "totp"
    out = {"user_id": user_id, "mfa_enrolled": enrolled,
           "enrolled_at": account.get("mfa_enrolled_at")}
    if enrolled:
        out["recovery_codes_remaining"] = len(
            _load_recovery_hashes(vault_root, user_id))
        masked = _vault_get(vault_root, user_id + _TOTP_ACCOUNT_SUFFIX)
        # masked 形（零明文）：密钥存在性由 sha256 掩码面呈现。
        out["totp_key_sha256_prefix"] = hashlib.sha256(
            masked or b"").hexdigest()[:12]
    return out


def mfa_disable(args: dict, mfa_root: str, vault_root: str) -> dict:
    user_id = _check_user(args.get("user_id"))
    now = _check_now(args.get("now"))
    account = _load_account(mfa_root, user_id)
    if account is None:
        raise MfaAuthError("mfa_user_unknown")
    if account.get("mfa") != "totp":
        raise MfaAuthError("mfa_not_enrolled")
    _verify_password(account, args.get("password"))
    factor_type = args.get("factor_type")
    if factor_type == "totp":
        _verify_totp(account, vault_root, user_id, args.get("factor"),
                     now, update_replay=True)
    elif factor_type == "recovery":
        code = args.get("factor")
        if not isinstance(code, str) or not code.strip():
            raise MfaAuthError("mfa_recovery_code_required")
        consumed, _ = _consume_recovery_code(
            vault_root, user_id, code.strip().lower())
        if not consumed:
            raise MfaAuthError("mfa_recovery_code_invalid")
    else:
        raise MfaAuthError("mfa_factor_type_invalid")
    _vault_delete(vault_root, user_id + _TOTP_ACCOUNT_SUFFIX)
    _vault_delete(vault_root, user_id + _RECOVERY_ACCOUNT_SUFFIX)
    account["mfa"] = "none"
    account["totp_last_counter"] = -1
    account["mfa_disabled_at"] = now
    _atomic_write_json(_account_path(mfa_root, user_id), account)
    return {"disabled": True, "user_id": user_id,
            "mfa": "none",
            "note": "失效＝保险库登记位拆除＋账户 MFA 位回落；"
                    "登录回到密码级基底（preserved 不变）"}


def mfa_auth_call(method: str, args: dict, config: dict) -> dict:
    """legal_entry 冻结方法组分发。未配置状态根＝fail-closed typed 拒。"""
    mfa_root, vault_root = _state_roots(config)
    if method == "auth.register":
        return auth_register(args, mfa_root, vault_root)
    if method == "auth.login":
        return auth_login(args, mfa_root, vault_root)
    if method == "auth.session":
        return auth_session(args, mfa_root, vault_root)
    if method == "mfa.enroll":
        return mfa_enroll(args, mfa_root, vault_root)
    if method == "mfa.verify":
        return mfa_verify(args, mfa_root, vault_root)
    if method == "mfa.recover":
        return mfa_recover(args, mfa_root, vault_root)
    if method == "mfa.status":
        return mfa_status(args, mfa_root, vault_root)
    if method == "mfa.disable":
        return mfa_disable(args, mfa_root, vault_root)
    raise MfaAuthError("mfa_method_not_connected:" + method)

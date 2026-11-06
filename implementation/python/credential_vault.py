# -*- coding: utf-8 -*-
"""F12 凭据保险库产品面（工单 W3-U09）。

06 F12 assertion：真实BYOK经DPAPI/keyring读写；配置和日志不露key；缺解密
不明文降级。owner=product（UI_HOST_OR_NEW_PRODUCT：新增产品义务，不冒已有
业务入口，不创第二 Agent loop）。

设计（最小必要面）：
  - 唯一持久化形态 = `<vault_state_root>/credentials/<service>/<account>.json`
    内的 DPAPI 密文 blob（CryptProtectData，当前用户作用域）。明文 secret
    只在调用方进程内存中存在，本模块任何路径都不写明文文件、不打日志。
  - keyring 后端：`vault_backend="keyring"` 且本机装了 keyring 包时走
    keyring；未安装＝具名拒 vault_keyring_backend_unavailable——绝不静默
    换成明文文件（缺设施≠降级）。
  - 缺解密不明文降级：blob 损坏/换用户/DPAPI 失败＝typed
    vault_decrypt_failed，结构性不存在「解不开就读配置里的明文键」回退
    路径（get 只有一条解密通道）。
  - vault.get 默认不回传 secret（只回 sha256＋掩码形）；显式 reveal=true
    才回 secret_b64——回执面最小暴露。
  - 审计/其他产品面的密钥一律经本设施存取（F07 密钥归产品凭据设施）。

金额/解析纪律不适用本面；错误全部 typed（VaultError 的 str 只有 vault_*
码），材料内容永不进入错误码。
"""

from __future__ import annotations

import base64
import ctypes
import hashlib
import json
import os
import re
import secrets
import sys
import tempfile
from pathlib import Path

VAULT_SCHEMA = "lvyin-credential-vault/1"

# legal_entry 冻结方法组（组外方法绝不落到本面）。
VAULT_METHODS = frozenset({
    "vault.status",
    "vault.put",
    "vault.get",
    "vault.delete",
    "vault.list",
})

# F07 审计 HMAC 密钥的凭据登记位（密钥归产品凭据设施＝审计面无独立钥文件）。
AUDIT_KEY_SERVICE = "lvyin.audit"
AUDIT_KEY_ACCOUNT = "hmac-sha256-v1"
AUDIT_KEY_BYTES = 32

_SECRET_MAX_BYTES = 4096
# 服务名/账户名是路径段。允许点与连字符（lvyin.audit / hmac-sha256-v1），
# 拒绝分隔符、盘符、ADS（name:stream）和 `..`。
_REF_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
# get 回执掩码形：sk-xxxx…xxxx（只露前 3 后 4）。
_MASK_HEAD, _MASK_TAIL = 3, 4

_BACKENDS = ("dpapi", "keyring")


class VaultError(RuntimeError):
    """Typed vault failure; str() is a vault_* code only."""


# ---------------------------------------------------------------------- #
# DPAPI（ctypes，crypt32；纯标准库，零新增依赖）
# ---------------------------------------------------------------------- #

class _DATA_BLOB(ctypes.Structure):
    _fields_ = [("cbData", ctypes.c_uint),
                ("pbData", ctypes.POINTER(ctypes.c_char))]


def _blob(data: bytes) -> tuple[_DATA_BLOB, ctypes.create_string_buffer]:
    # 缓冲区 buf 必须在 Crypt*Data 调用期间存活，故随 blob 一起返回。
    buf = ctypes.create_string_buffer(data, len(data))
    blob = _DATA_BLOB(len(data),
                      ctypes.cast(buf, ctypes.POINTER(ctypes.c_char)))
    return blob, buf


def dpapi_available() -> bool:
    return sys.platform == "win32"


def dpapi_protect(data: bytes) -> bytes:
    """CryptProtectData（当前用户作用域）→ 密文 bytes。"""
    if not dpapi_available():
        raise VaultError("vault_dpapi_unavailable_platform")
    crypt32 = ctypes.windll.crypt32  # noqa: attribute exists on win32
    in_blob, in_buf = _blob(data)
    out_blob = _DATA_BLOB(0, None)
    if not crypt32.CryptProtectData(
            ctypes.byref(in_blob), None, None, None, None, 0,
            ctypes.byref(out_blob)):
        raise VaultError("vault_dpapi_protect_failed")
    try:
        return ctypes.string_at(out_blob.pbData, out_blob.cbData)
    finally:
        ctypes.windll.kernel32.LocalFree(out_blob.pbData)


def dpapi_unprotect(blob: bytes) -> bytes:
    """CryptUnprotectData → 明文 bytes；失败＝typed 拒（绝不明文降级）。"""
    if not dpapi_available():
        raise VaultError("vault_dpapi_unavailable_platform")
    crypt32 = ctypes.windll.crypt32
    in_blob, in_buf = _blob(blob)
    out_blob = _DATA_BLOB(0, None)
    if not crypt32.CryptUnprotectData(
            ctypes.byref(in_blob), None, None, None, None, 0,
            ctypes.byref(out_blob)):
        # 换用户/损坏/策略拒绝都落到这里：唯一出口＝typed 拒。
        raise VaultError("vault_decrypt_failed")
    try:
        return ctypes.string_at(out_blob.pbData, out_blob.cbData)
    finally:
        ctypes.windll.kernel32.LocalFree(out_blob.pbData)


# ---------------------------------------------------------------------- #
# 存取面
# ---------------------------------------------------------------------- #

def _check_ref(value: object) -> str:
    if not isinstance(value, str) or not _REF_RE.match(value) or ".." in value:
        raise VaultError("vault_ref_invalid")
    return value


def _entry_path(state_root: str | Path, service: str, account: str) -> Path:
    root = Path(str(state_root))
    service = _check_ref(service)
    account = _check_ref(account)
    return root / "credentials" / service / (account + ".json")


def _name(entry: dict) -> str:
    return f"{entry['service']}/{entry['account']}"


def _write_entry(path: Path, entry: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(dir=str(path.parent),
                                    prefix=path.stem + "-", suffix=".tmp")
    os.close(fd)
    with open(tmp_name, "w", encoding="utf-8", newline="\n") as handle:
        json.dump(entry, handle, ensure_ascii=False, sort_keys=True, indent=1)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(tmp_name, path)


def vault_put(state_root: str | Path, service: str, account: str,
              secret: bytes, backend: str = "dpapi") -> dict:
    """真实加密写入：secret 只进密文 blob；回执零 secret 零 blob。"""
    if not isinstance(secret, (bytes, bytearray)) or not secret:
        raise VaultError("vault_secret_required")
    if len(secret) > _SECRET_MAX_BYTES:
        raise VaultError("vault_secret_oversized")
    if backend not in _BACKENDS:
        raise VaultError("vault_backend_unknown:" + str(backend))
    # 路径先于加密：非法引用不得先把 secret 送进 DPAPI/keyring。
    path = _entry_path(state_root, service, account)
    if backend == "dpapi":
        blob = dpapi_protect(bytes(secret))
        stored = "dpapi-current-user"
    else:
        try:
            import keyring  # noqa: 供 keyring 后端；未装＝具名拒
        except ImportError:
            raise VaultError("vault_keyring_backend_unavailable") from None
        keyring.set_password(service, account,
                             base64.b64encode(bytes(secret)).decode("ascii"))
        _write_entry(path, {
            "schema": VAULT_SCHEMA, "service": service, "account": account,
            "backend": "keyring",
            "sha256": hashlib.sha256(secret).hexdigest(),
            "stored_at": _now(),
        })
        return {"service": service, "account": account,
                "backend": "keyring",
                "sha256": hashlib.sha256(secret).hexdigest(),
                "note": "secret 存 keyring；登记文件零 secret 零 blob"}
    entry = {
        "schema": VAULT_SCHEMA, "service": service, "account": account,
        "backend": "dpapi", "scope": stored,
        "blob_b64": base64.b64encode(blob).decode("ascii"),
        "sha256": hashlib.sha256(secret).hexdigest(),
        "stored_at": _now(),
    }
    _write_entry(path, entry)
    return {"service": service, "account": account, "backend": "dpapi",
            "sha256": entry["sha256"],
            "note": "secret 只存 DPAPI 密文 blob；回执与登记文件零明文"}


def vault_get(state_root: str | Path, service: str, account: str,
              backend: str = "dpapi", reveal: bool = False) -> dict:
    """真实解密读取。reveal=false 回执只带 sha256＋掩码形（零 secret）。"""
    path = _entry_path(state_root, service, account)
    if backend not in _BACKENDS:
        raise VaultError("vault_backend_unknown:" + str(backend))
    if not path.is_file():
        raise VaultError("vault_entry_missing:" + _name2(service, account))
    try:
        entry = json.loads(path.read_text(encoding="utf-8"))
    except (ValueError, OSError, UnicodeDecodeError):
        raise VaultError("vault_schema_unknown") from None
    if not isinstance(entry, dict) or entry.get("schema") != VAULT_SCHEMA:
        raise VaultError("vault_schema_unknown")
    if entry.get("backend") == "keyring":
        try:
            import keyring
        except ImportError:
            raise VaultError("vault_keyring_backend_unavailable") from None
        payload = keyring.get_password(service, account)
        if payload is None:
            raise VaultError("vault_decrypt_failed")
        secret = base64.b64decode(payload)
    else:
        try:
            blob = base64.b64decode(entry.get("blob_b64") or "")
        except (ValueError, TypeError):
            raise VaultError("vault_decrypt_failed") from None
        secret = dpapi_unprotect(blob)  # 失败＝vault_decrypt_failed，无回退
    digest = hashlib.sha256(secret).hexdigest()
    if entry.get("sha256") not in (None, digest):
        raise VaultError("vault_digest_mismatch")
    out = {"service": service, "account": account,
           "backend": entry.get("backend"),
           "sha256": digest,
           "masked": _mask(secret),
           "revealed": False}
    if reveal is True:
        out["secret_b64"] = base64.b64encode(secret).decode("ascii")
        out["revealed"] = True
    return out


def vault_delete(state_root: str | Path, service: str, account: str,
                 backend: str = "dpapi") -> dict:
    path = _entry_path(state_root, service, account)
    if not path.is_file():
        raise VaultError("vault_entry_missing:" + _name2(service, account))
    path.unlink()
    return {"service": service, "account": account, "deleted": True}


def vault_list(state_root: str | Path) -> dict:
    root = Path(str(state_root)) / "credentials"
    entries = []
    if root.is_dir():
        for path in sorted(root.glob("*/*.json")):
            try:
                entry = json.loads(path.read_text(encoding="utf-8"))
            except (ValueError, OSError):
                raise VaultError("vault_schema_unknown") from None
            entries.append({
                "service": entry.get("service"),
                "account": entry.get("account"),
                "backend": entry.get("backend"),
                "sha256": entry.get("sha256"),
                "stored_at": entry.get("stored_at"),
            })
    return {"entries": entries, "count": len(entries),
            "note": "清单只含元数据，零 secret 零 blob"}


def vault_status(state_root: str | Path, backend: str = "dpapi") -> dict:
    return {
        "schema": VAULT_SCHEMA,
        "backend_selected": backend,
        "backends": {"dpapi": dpapi_available(), "keyring": _keyring_ok()},
        "state_root_configured": bool(state_root),
        "note": "BYOK 凭据设施（F12）：密文 blob 经 DPAPI（当前用户作用域）"
                "或 keyring；明文只存在调用方进程内存；缺解密＝typed 拒不明文降级",
    }


def new_byok_test_key() -> str:
    """DeepSeek 形合成测试键（sk-+32hex）：运行时生成，不入 git、不入证据。"""
    return "sk-" + secrets.token_hex(16)


def _mask(secret: bytes) -> str:
    text = secret.decode("utf-8", "replace")
    if len(text) <= _MASK_HEAD + _MASK_TAIL:
        return "*" * len(text)
    return text[:_MASK_HEAD] + "…" + text[-_MASK_TAIL:]


def _keyring_ok() -> bool:
    try:
        import keyring  # noqa: F401
        return True
    except ImportError:
        return False


def _name2(service: str, account: str) -> str:
    return f"{service}/{account}"


def _now() -> str:
    import datetime
    return datetime.datetime.now(
        datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ---------------------------------------------------------------------- #
# legal_entry 冻结方法组分发（vault.*）
# ---------------------------------------------------------------------- #

def vault_call(method: str, args: dict, config: dict) -> dict:
    """legal_entry 冻结方法组分发。未配置状态根＝fail-closed NOT_CONNECTED
    语义（VaultError→桥面 NotConnected）。未列方法绝不落到这里。"""
    state_root = config.get("vault_state_root")
    if method == "vault.status":
        return vault_status(state_root,
                            str(args.get("backend") or "dpapi"))
    if not state_root:
        raise VaultError("vault_state_root_not_configured")
    backend = str(args.get("backend") or "dpapi")
    if method == "vault.put":
        secret_b64 = args.get("secret_b64")
        if not isinstance(secret_b64, str) or not secret_b64:
            raise VaultError("vault_secret_required")
        try:
            secret = base64.b64decode(secret_b64)
        except (ValueError, TypeError):
            raise VaultError("vault_secret_invalid") from None
        return vault_put(state_root, str(args.get("service") or ""),
                         str(args.get("account") or ""), secret, backend)
    if method == "vault.get":
        return vault_get(state_root, str(args.get("service") or ""),
                         str(args.get("account") or ""), backend,
                         reveal=args.get("reveal") is True)
    if method == "vault.delete":
        return vault_delete(state_root, str(args.get("service") or ""),
                            str(args.get("account") or ""), backend)
    if method == "vault.list":
        return vault_list(state_root)
    raise VaultError("vault_method_not_connected:" + method)

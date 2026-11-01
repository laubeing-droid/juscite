# -*- coding: utf-8 -*-
"""F10 案件库 at-rest 密钥产品面（工单 W4-U32）。

06 F10 assertion：加密持久状态和 CAS 可恢复；无密钥不可读且不明文降级。
owner=product 密钥供给半边（加密本体在 harness EncryptedCASStore 与
anonymizer atrest 面，各走其仓分支）。

设计（最小必要面，不造第二凭据体系）：
  - 唯一持久化形态 = 既有 F12 凭据保险库登记位
    ``lvyin.f10/atrest-aes-256-gcm-v1`` 的 DPAPI 密文 blob。本模块零持久化、
    零日志；明文 32B 密钥只在调用方进程内存存在，交给存储面后即弃。
  - provision = get-or-create（幂等）：已有登记位原样返回元数据（不轮换、
    不重写）；缺才 ``os.urandom(32)`` 生成并入保险库。
  - 回执最小暴露：默认零密钥字节，只回 sha256＋掩码形；``reveal=True``
    才回 ``key_b64``（内部供给通道，供 material.parse_* / 存储面取钥）。
  - 零明文降级：加密态（config f10_atrest=on）下取不到钥＝typed
    ``f10_atrest_key_not_provisioned`` 拒——结构性不存在「无钥就明文落盘」
    回退路径（resolve 唯一出口是保险库解密）。

错误全部 typed（AtrestKeyError 的 str 只有 f10_*/vault_* 码），案件内容
永不进入错误码。
"""

from __future__ import annotations

import base64
import hashlib
import os

ATREST_SCHEMA = "lvyin-f10-atrest/1"

# legal_entry 冻结方法组（组外方法绝不落到本面）。
ATREST_METHODS = frozenset({
    "atrest.status",
    "atrest.provision",
})

# F10 at-rest 主密钥的凭据登记位（密钥归产品凭据设施＝存储面无独立钥文件）。
ATREST_KEY_SERVICE = "lvyin.f10"
ATREST_KEY_ACCOUNT = "atrest-aes-256-gcm-v1"
ATREST_KEY_BYTES = 32

# 掩码形（与 F12 同风格）：只露前 4 后 4 hex。
_MASK_HEAD, _MASK_TAIL = 4, 4


class AtrestKeyError(RuntimeError):
    """Typed at-rest key failure; str() is an f10_*/vault_* code only."""


def _state_root(config: dict):
    state_root = (config or {}).get("vault_state_root")
    if not state_root:
        raise AtrestKeyError("vault_state_root_not_configured")
    return state_root


def _load(config: dict, reveal: bool = False) -> dict | None:
    """读登记位；未配置＝None（typed 拒由调用方按语义给出）。"""
    from credential_vault import vault_get, VaultError

    try:
        out = vault_get(_state_root(config), ATREST_KEY_SERVICE,
                        ATREST_KEY_ACCOUNT, "dpapi", reveal=reveal)
    except VaultError as exc:
        if str(exc).startswith("vault_entry_missing"):
            return None
        raise AtrestKeyError(str(exc)) from None
    return out


def _masked(key: bytes) -> str:
    text = key.hex()
    return text[:_MASK_HEAD] + "…" + text[-_MASK_TAIL:]


def atrest_key_status(config: dict) -> dict:
    """回执零密钥字节：provisioned/sha256/masked/length＋设施说明。"""
    entry = _load(config)
    if entry is None:
        return {"schema": ATREST_SCHEMA, "provisioned": False,
                "service": ATREST_KEY_SERVICE, "account": ATREST_KEY_ACCOUNT,
                "key_bytes": ATREST_KEY_BYTES,
                "note": "密钥唯一持久化=F12 保险库 DPAPI blob；"
                        "未配置时加密态 typed 拒不明文降级"}
    return {"schema": ATREST_SCHEMA, "provisioned": True,
            "service": ATREST_KEY_SERVICE, "account": ATREST_KEY_ACCOUNT,
            "key_sha256": entry["sha256"], "masked": entry["masked"],
            "backend": entry.get("backend"), "key_bytes": ATREST_KEY_BYTES}


def atrest_key_provision(config: dict) -> dict:
    """get-or-create（幂等）：已有登记位不轮换不重写；缺才生成入保险库。"""
    from credential_vault import vault_put, VaultError

    entry = _load(config)
    if entry is not None:
        out = atrest_key_status(config)
        out["created"] = False
        return out
    key = os.urandom(ATREST_KEY_BYTES)
    try:
        vault_put(_state_root(config), ATREST_KEY_SERVICE,
                  ATREST_KEY_ACCOUNT, key, "dpapi")
    except VaultError as exc:
        raise AtrestKeyError(str(exc)) from None
    out = atrest_key_status(config)
    out["created"] = True
    return out


def resolve_atrest_key(config: dict) -> bytes:
    """加密态取钥唯一通道：保险库解密。取不到＝typed 拒（零明文降级）。"""
    entry = _load(config, reveal=True)
    if entry is None:
        raise AtrestKeyError("f10_atrest_key_not_provisioned")
    key = base64.b64decode(entry["secret_b64"])
    if len(key) != ATREST_KEY_BYTES:
        raise AtrestKeyError("f10_atrest_key_invalid")
    if hashlib.sha256(key).hexdigest() != entry["sha256"]:
        raise AtrestKeyError("f10_atrest_key_invalid")
    return key


def atrest_enabled(config: dict) -> bool:
    """加密态开关（显式 opt-in；v1 缺省关＝权限闸+假名 preserved）。"""
    return bool((config or {}).get("f10_atrest"))


def atrest_key_call(method: str, args: dict, config: dict) -> dict:
    """legal_entry 冻结方法组分发。回执零密钥字节（reveal 仅内部 resolve）。"""
    if method == "atrest.status":
        return atrest_key_status(config)
    if method == "atrest.provision":
        return atrest_key_provision(config)
    raise AtrestKeyError("f10_atrest_method_not_connected:" + method)

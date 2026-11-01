# -*- coding: utf-8 -*-
"""F79 离线 Ed25519 许可＋设备指纹＋防时钟回拨（工单 W5-U01）。

06 F79（V7-79；owner=distribution，desktop/selfhost 双实例；acceptance：
「离线许可验签和时钟回拨反例受控；私钥不入发行物」；legacy link F78）。
裁决 #13-19（00-总协调 §6.1）：签发私钥/商业服务端统一合成先行——真实
设施 v2 商业化时补，具名回收点＝tools/license_issuer_synth.py 头注与本
文件本注。LawX 为闭源竞品（authority/01:236「借交互与方法，不复制素材」），
本面按其方法（离线许可验签＋指纹绑定＋单调时钟水印）自研，零代码复制。

设计（最小必要面，零新增依赖——Ed25519 走既有 cryptography，缺席具名拒
不静默降级，F11 f11_crypto_unavailable 同式）：
  - 离线许可令牌＝{schema, algorithm:"ed25519", payload_b64, signature_b64}
    ；签名覆盖 payload 原始字节（签发时 canonical JSON）；payload 闭集
    字段：license_id/subject/device_fp_hash/not_before/not_after/features。
    验签公钥只从部署面 config.license_trusted_pubkeys（b64 列表）取——
    令牌自带公钥绝不是信任锚（自签自验结构性不存在）。
  - 设备指纹＝确定性派生：win32 取 HKLM MachineGuid（只读注册表）＋
    platform.system/machine，sha256 截断；回执只带 hash 与来源名，原始
    MachineGuid 永不出面。
  - 防时钟回拨＝单调水印：每次受时操作（verify_offline / F78 check）先把
    now 与水印比（now < 水印-容差＝typed license_clock_rollback_detected），
    过闸才前进水印并原子写。水印经 HMAC-SHA256 封印，密钥 get-or-create
    存既有 F12 保险库（lvyin.f79/clock-watermark-hmac-v1——legacy link
    F12 复用，不造第二凭据体系）；封印不符＝license_clock_state_untrusted
    fail-closed（删水印可抹回拨证据，故绝不自动重置）。
  - 本面是授权域唯一时钟权威：F78 每日校验/宽限计时一律经 now_checked()
    取时（不复制第二时钟）。
  - 私钥不入发行物：本文件零私钥加载/签名路径（只 PublicKey.verify）；
    签发私钥只存在于 tools/license_issuer_synth.py（施工/测试设施，非发
    行物）；recon 以 git tracked 全文件字节扫描钉死。

错误全部 typed（LicenseError 的 str 只有 license_* 码）；材料/密钥内容
永不进入错误码与回执。
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import platform
import time
from pathlib import Path

FACE_SCHEMA = "lvyin-license-verify/1"
PAYLOAD_SCHEMA = "lvyin-license-payload/1"
TOKEN_SCHEMA = "lvyin-license-token/1"
CLOCK_SCHEMA = "lvyin-license-clock/1"
ALGORITHM = "ed25519"

# legal_entry 冻结方法组（组外方法绝不落到本面）。
LICENSE_VERIFY_METHODS = frozenset({
    "license.verify_offline",
    "license.device_fingerprint",
    "license.clock_status",
})

# F12 保险库登记位（时钟水印 HMAC 密钥；legacy link F12＝不造第二凭据体系）。
CLOCK_KEY_SERVICE = "lvyin.f79"
CLOCK_KEY_ACCOUNT = "clock-watermark-hmac-v1"
CLOCK_KEY_BYTES = 32

# 回拨容差（秒）：吸收同机 NTP 毫秒级回跳；负测回拨以天计，远超容差。
CLOCK_TOLERANCE_SECONDS = 5.0

_WATERMARK_FILENAME = "clock-watermark.json"
_FP_HASH_LEN = 32
_ISO_FMT = "%Y-%m-%dT%H:%M:%SZ"


class LicenseError(RuntimeError):
    """Typed license failure; str() is a license_* code only."""


# ---------------------------------------------------------------------- #
# 设备指纹（确定性派生；原始标识符永不出面）
# ---------------------------------------------------------------------- #

def _machine_guid() -> tuple[str, str] | None:
    """win32 只读注册表 MachineGuid；不可得＝None（来源面如实降列）。"""
    if platform.system() != "Windows":
        return None
    try:
        import winreg  # noqa: 仅 win32
    except ImportError:
        return None
    try:
        with winreg.OpenKey(
                winreg.HKEY_LOCAL_MACHINE,
                r"SOFTWARE\Microsoft\Cryptography", 0,
                winreg.KEY_READ | winreg.KEY_WOW64_64KEY) as key:
            value, _ = winreg.QueryValueEx(key, "MachineGuid")
    except OSError:
        return None
    return ("winreg.machineguid", str(value))


def device_fingerprint() -> dict:
    """确定性设备指纹：多来源规范文本 sha256 截断。回执零原始标识符。"""
    sources: list[str] = []
    parts: list[str] = []
    guid = _machine_guid()
    if guid is not None:
        sources.append(guid[0])
        parts.append(guid[1])
    sys_name = platform.system()
    sys_machine = platform.machine()
    sources.extend(["platform.system", "platform.machine"])
    parts.extend([sys_name, sys_machine])
    if not parts:
        raise LicenseError("license_fingerprint_no_source")
    canonical = "\n".join(parts).encode("utf-8")
    digest = hashlib.sha256(canonical).hexdigest()
    return {"schema": FACE_SCHEMA,
            "fingerprint_hash": digest[:_FP_HASH_LEN],
            "sources": sources,
            "note": "指纹=多来源 sha256 截断；原始 MachineGuid 永不出面"}


# ---------------------------------------------------------------------- #
# 时钟权威（单调水印；F78 共用）
# ---------------------------------------------------------------------- #

def _canonical(payload) -> bytes:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":")).encode("utf-8")


def _iso(epoch: float) -> str:
    return time.strftime(_ISO_FMT, time.gmtime(epoch))


def _clock_key(config: dict) -> bytes:
    """水印 HMAC 密钥唯一来源＝F12 保险库（get-or-create 幂等不轮换）。"""
    from credential_vault import vault_get, vault_put, VaultError

    vault_root = (config or {}).get("vault_state_root")
    if not vault_root:
        raise LicenseError("vault_state_root_not_configured")
    try:
        entry = vault_get(vault_root, CLOCK_KEY_SERVICE, CLOCK_KEY_ACCOUNT,
                          "dpapi", reveal=True)
    except VaultError as exc:
        if not str(exc).startswith("vault_entry_missing"):
            raise LicenseError("license_clock_key_vault_failed:" +
                               str(exc)) from None
        key = os.urandom(CLOCK_KEY_BYTES)
        try:
            vault_put(vault_root, CLOCK_KEY_SERVICE, CLOCK_KEY_ACCOUNT,
                      key, "dpapi")
        except VaultError as exc2:
            raise LicenseError("license_clock_key_vault_failed:" +
                               str(exc2)) from None
        return key
    key = base64.b64decode(entry["secret_b64"])
    if len(key) != CLOCK_KEY_BYTES:
        raise LicenseError("license_clock_key_invalid")
    return key


def _seal(key: bytes, watermark_epoch: float) -> dict:
    body = {"schema": CLOCK_SCHEMA, "watermark_epoch": watermark_epoch}
    return {**body,
            "sealed_at_iso": _iso(watermark_epoch),
            "mac": hmac.new(key, _canonical(body),
                            hashlib.sha256).hexdigest()}


def _load_watermark(path: Path, key: bytes) -> float | None:
    if not path.is_file():
        return None
    try:
        sealed = json.loads(path.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        raise LicenseError("license_clock_state_untrusted") from None
    if (not isinstance(sealed, dict)
            or sealed.get("schema") != CLOCK_SCHEMA
            or not isinstance(sealed.get("watermark_epoch"), (int, float))):
        raise LicenseError("license_clock_state_untrusted")
    body = {"schema": sealed["schema"],
            "watermark_epoch": sealed["watermark_epoch"]}
    expect = hmac.new(key, _canonical(body), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expect, str(sealed.get("mac") or "")):
        raise LicenseError("license_clock_state_untrusted")
    return float(sealed["watermark_epoch"])


def _write_watermark(path: Path, key: bytes, watermark_epoch: float) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(_seal(key, watermark_epoch), ensure_ascii=False,
                              indent=1), encoding="utf-8")
    os.replace(tmp, path)


def clock_inspect(config: dict) -> dict:
    """只读检视（不前进不拒）：水印事实＋now 关系。回拨作为事实在案。"""
    state_root = (config or {}).get("license_state_root")
    if not state_root:
        raise LicenseError("license_state_root_not_configured")
    path = Path(str(state_root)) / _WATERMARK_FILENAME
    now = time.time()
    if not path.is_file():
        return {"schema": CLOCK_SCHEMA, "watermark_epoch": None,
                "watermark_iso": None, "now_epoch": now, "now_iso": _iso(now),
                "rollback_detected": False, "behind_seconds": 0.0,
                "note": "水印未建立（尚无受时操作）"}
    key = _clock_key(config)
    watermark = _load_watermark(path, key)
    behind = (watermark - CLOCK_TOLERANCE_SECONDS) - now
    return {"schema": CLOCK_SCHEMA, "watermark_epoch": watermark,
            "watermark_iso": _iso(watermark), "now_epoch": now,
            "now_iso": _iso(now),
            "rollback_detected": behind > 0.0,
            "behind_seconds": round(max(behind, 0.0), 3),
            "tolerance_seconds": CLOCK_TOLERANCE_SECONDS}


def now_checked(config: dict) -> float:
    """授权域唯一时钟入口：回拨拒绝→过闸→前进水印→返回 now。

    F78 每日校验/宽限计时一律经此取时（单一权威，不复制第二时钟）。
    水印封印损坏＝license_clock_state_untrusted（fail-closed，绝不自动
    重置——重置＝允许删证据）。"""
    state_root = (config or {}).get("license_state_root")
    if not state_root:
        raise LicenseError("license_state_root_not_configured")
    path = Path(str(state_root)) / _WATERMARK_FILENAME
    key = _clock_key(config)
    watermark = _load_watermark(path, key)
    now = time.time()
    if watermark is not None and now < watermark - CLOCK_TOLERANCE_SECONDS:
        raise LicenseError("license_clock_rollback_detected")
    advance = now if watermark is None else max(now, watermark)
    _write_watermark(path, key, advance)
    return now


# ---------------------------------------------------------------------- #
# 离线许可验签（Ed25519；私钥结构性不在本面）
# ---------------------------------------------------------------------- #

def _verify_engine():
    try:
        from cryptography.exceptions import InvalidSignature
        from cryptography.hazmat.primitives.asymmetric.ed25519 import (
            Ed25519PublicKey)
        return InvalidSignature, Ed25519PublicKey
    except ImportError:
        raise LicenseError("license_crypto_unavailable") from None


def _trusted_pubkeys(config: dict) -> list[bytes]:
    keys = (config or {}).get("license_trusted_pubkeys")
    if not isinstance(keys, list) or not keys:
        raise LicenseError("license_trusted_keys_not_configured")
    out = []
    for item in keys:
        if not isinstance(item, str):
            raise LicenseError("license_trusted_key_invalid")
        try:
            raw = base64.b64decode(item)
        except (ValueError, TypeError):
            raise LicenseError("license_trusted_key_invalid") from None
        if len(raw) != 32:
            raise LicenseError("license_trusted_key_invalid")
        out.append(raw)
    return out


def verify_offline_token(token, config: dict, now: float) -> dict:
    """离线令牌验签：信任锚→签名→指纹→时间窗（now 必须来自 now_checked）。"""
    InvalidSignature, Ed25519PublicKey = _verify_engine()
    trusted = _trusted_pubkeys(config)
    if not isinstance(token, dict) or token.get("schema") != TOKEN_SCHEMA:
        raise LicenseError("license_token_malformed")
    if token.get("algorithm") != ALGORITHM:
        raise LicenseError("license_algorithm_unknown:" + str(
            token.get("algorithm")))
    try:
        payload_bytes = base64.b64decode(token.get("payload_b64") or "")
        signature = base64.b64decode(token.get("signature_b64") or "")
    except (ValueError, TypeError):
        raise LicenseError("license_token_malformed") from None
    issuer_raw = None
    for raw in trusted:
        pub = Ed25519PublicKey.from_public_bytes(raw)
        try:
            pub.verify(signature, payload_bytes)
        except InvalidSignature:
            continue
        issuer_raw = raw
        break
    if issuer_raw is None:
        raise LicenseError("license_signature_invalid")
    try:
        payload = json.loads(payload_bytes.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        raise LicenseError("license_payload_malformed") from None
    if (not isinstance(payload, dict)
            or payload.get("schema") != PAYLOAD_SCHEMA):
        raise LicenseError("license_payload_schema_unknown")
    for field in ("license_id", "subject", "device_fp_hash",
                  "not_before", "not_after"):
        if not isinstance(payload.get(field), str):
            raise LicenseError("license_payload_field_missing:" + field)
    fp = device_fingerprint()["fingerprint_hash"]
    if payload["device_fp_hash"] != fp:
        raise LicenseError("license_device_mismatch")
    try:
        not_before = float(payload["not_before"])
        not_after = float(payload["not_after"])
    except (ValueError, TypeError):
        raise LicenseError("license_payload_malformed") from None
    if now < not_before:
        raise LicenseError("license_not_yet_valid")
    if now > not_after:
        raise LicenseError("license_expired")
    return {
        "valid": True,
        "license_id": payload["license_id"],
        "subject": payload["subject"],
        "features": list(payload.get("features") or []),
        "device_fp_hash": payload["device_fp_hash"],
        "not_before": not_before, "not_after": not_after,
        "not_before_iso": _iso(not_before),
        "not_after_iso": _iso(not_after),
        "algorithm": ALGORITHM,
        "issuer_fingerprint": hashlib.sha256(issuer_raw).hexdigest()[:16],
    }


# ---------------------------------------------------------------------- #
# legal_entry 冻结方法组分发（license.verify_offline / device_fingerprint /
# clock_status——F78 的 activate/check/status 三方法在 license_manager）。
# ---------------------------------------------------------------------- #

def license_verify_call(method: str, args: dict, config: dict) -> dict:
    if method == "license.device_fingerprint":
        return device_fingerprint()
    if method == "license.clock_status":
        return clock_inspect(config)
    if method == "license.verify_offline":
        now = now_checked(config)
        return verify_offline_token((args or {}).get("token"), config, now)
    raise LicenseError("license_method_not_connected:" + method)

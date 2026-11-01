# -*- coding: utf-8 -*-
"""F33 托管模型积分通道（设备签名短 TTL 凭证，子 Key 不落端）合成先行
产品面（工单 W5-U03）。

06 V7-33 行（v2；owner=product；B5）acceptance＝托管短TTL凭证过期失效；
设备/额度绑定；子key不落端。17 卡 preserved＝L12 商业化留槽；来源非选型
要求原档位保持；不创第二 Agent loop。python_entry=UI_HOST_OR_NEW_PRODUCT：
不要求新增法律 Python 服务，不冒已有业务入口——本面**不接入
legal_entry**（零第二业务入口），真实网关 v2 商业化时补（00-总协调
裁决#13-19 统一合成先行）。

设计（最小必要面；源设计=竞品 LawX /ai/session：设备签名换 ≤60s TTL 短期
凭证、"子 Key 始终只在服务端"，竞品情报 2026-10-11 lawx-structure.md §4）：

  - gateway（服务端语义·合成签发/验证服务，进程内）：唯一持有上游子key
    （sub_key，内存态；v2 真实网关接管后落服务端设施）；设备登记一次性
    回执 device_key；凭证 token＝HMAC-SHA256(sub_key, canonical 载荷)，
    载荷钉 {schema, device_id, nonce, authorized_fen, issued_at, exp,
    ttl_s}，任一字段篡改＝hosted_credential_invalid（token 是唯一完整
    性凭据，禁只验字段）。
  - device（端侧语义）：设备密钥唯一持久化通道＝credential_vault（F12
    公开面，DPAPI 密文；复用其公开面，不第二权威）；请求签名＝
    HMAC-SHA256(device_key, canonical{device_id, nonce, requested_fen,
    sig_v})；端侧请求/回执/持久化零子key——本面零日志零打印零文件读写。
  - TTL 过期失效：verify 处 now > exp（clock 可注入，默认 time.time）
    → hosted_credential_expired，且不扣额度。
  - 设备绑定：verify 处凭据 device_id ≠ 到账 device_id →
    hosted_device_mismatch；请求签名覆盖 device_id，异钥异名→
    hosted_signature_invalid。
  - 额度绑定（整型分）：签发处 remaining < requested →
    hosted_quota_exceeded；verify 扣减按整型分精确记账；浮点/bool 额度
    → hosted_quota_not_integer（bool 是 int 子类显式拒，turn_budget
    同式）；nonce 一次性（重放 → hosted_credential_replayed，额度不
    双扣）。
  - 零网络 I/O 零模型调用：合成先行（真实网关 v2 补，裁决#13-19）；
    不创第二 Agent loop（推理永远在上游，本面只做凭证与计量）。

错误全部 typed（HostedError 的 str 只有 hosted_* 码；密钥材料内容永不
进错误码）；F12 面的 VaultError 原样穿透（不包第二错误体系）。
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import time

from credential_vault import vault_get, vault_put

HOSTED_SCHEMA = "juscite-f33-hosted-inference/1"

# 源设计 ≤60s 短 TTL（lawx-structure.md §4：换 ≤60s TTL 短期凭证）。
DEFAULT_TTL_SECONDS = 60

# F12 凭据保险库登记位：service 固定，account=device-<device_id>。
HOSTED_VAULT_SERVICE = "lvyin.hosted"

_DEVICE_KEY_BYTES = 32
_SIG_V = 1
# 凭证载荷钉定键序（token 覆盖全集；缺一/多一都算 invalid）。
_CREDENTIAL_KEYS = ("schema", "device_id", "nonce", "authorized_fen",
                    "issued_at", "exp", "ttl_s")


class HostedError(RuntimeError):
    """Typed hosted failure; str() is a hosted_* code only."""


def _canonical(payload: dict) -> bytes:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":")).encode("utf-8")


def _device_account(device_id: str) -> str:
    return "device-" + device_id


def _require_device_id(device_id) -> None:
    if not isinstance(device_id, str) or not device_id.strip() \
            or any(sep in device_id for sep in ("/", "\\", "..")):
        raise HostedError("hosted_device_id_invalid")


def _require_fen(value, *, allow_zero: bool = False) -> None:
    # bool 是 int 子类——显式拒；浮点额度结构性不入账（turn_budget 同式）。
    if isinstance(value, bool) or not isinstance(value, int):
        raise HostedError("hosted_quota_not_integer")
    if (value < 0) if allow_zero else (value <= 0):
        raise HostedError("hosted_quota_invalid_amount")


# ---------------------------------------------------------------------- #
# 端侧（device）：vault 取钥＋请求签名
# ---------------------------------------------------------------------- #

def new_nonce() -> str:
    return secrets.token_hex(16)


def device_signature(device_key: bytes, device_id: str, nonce: str,
                     requested_fen: int) -> str:
    """端侧请求签名：HMAC-SHA256(device_key, canonical 四元组)。"""
    _require_device_id(device_id)
    if not isinstance(device_key, (bytes, bytearray)) or not device_key:
        raise HostedError("hosted_device_key_invalid")
    if not isinstance(nonce, str) or not nonce:
        raise HostedError("hosted_nonce_required")
    _require_fen(requested_fen)
    msg = _canonical({"device_id": device_id, "nonce": nonce,
                      "requested_fen": requested_fen, "sig_v": _SIG_V})
    return hmac.new(bytes(device_key), msg, hashlib.sha256).hexdigest()


def store_device_key(state_root, device_id: str, device_key: bytes) -> dict:
    """设备密钥入 F12 凭据保险库（DPAPI 密文；复用其公开面不第二权威）。
    回执零密钥材料（vault_put 既有合同）。"""
    _require_device_id(device_id)
    if not isinstance(device_key, (bytes, bytearray)) or not device_key:
        raise HostedError("hosted_device_key_invalid")
    return vault_put(state_root, HOSTED_VAULT_SERVICE,
                     _device_account(device_id), bytes(device_key))


def load_device_key(state_root, device_id: str) -> bytes:
    """F12 vault.get 显式 reveal 通道取设备密钥——唯一取钥通道，无旁路。
    登记不存在＝VaultError（vault_entry_missing）原样穿透。"""
    _require_device_id(device_id)
    out = vault_get(state_root, HOSTED_VAULT_SERVICE,
                    _device_account(device_id), reveal=True)
    return base64.b64decode(out["secret_b64"])


def request_session(gateway, state_root, device_id: str, requested_fen: int,
                    nonce: str | None = None) -> dict:
    """端侧完整通道：vault 取钥→签名→向 gateway 签发。回执零子key。
    （合成先行：gateway 为进程内对象；真实网关 v2 换传输面，本函数
    语义不变。）"""
    _require_fen(requested_fen)
    key = load_device_key(state_root, device_id)
    nonce = nonce if isinstance(nonce, str) and nonce else new_nonce()
    return gateway.issue_session(
        device_id,
        device_signature(key, device_id, nonce, requested_fen),
        nonce, requested_fen)


# ---------------------------------------------------------------------- #
# 服务端（gateway）：合成签发/验证服务
# ---------------------------------------------------------------------- #

class HostedGateway:
    """合成签发/验证服务（进程内；服务端语义）。唯一持有 sub_key——
    它不进任何回执、不落任何持久化（v2 真实网关接管后落服务端设施）。"""

    def __init__(self, sub_key: bytes, starting_quota_fen: int,
                 clock=time.time, ttl_seconds: int = DEFAULT_TTL_SECONDS):
        if not isinstance(sub_key, (bytes, bytearray)) \
                or len(sub_key) < 16:
            raise HostedError("hosted_sub_key_invalid")
        _require_fen(starting_quota_fen, allow_zero=True)
        if not callable(clock):
            raise HostedError("hosted_clock_invalid")
        if isinstance(ttl_seconds, bool) or not isinstance(ttl_seconds, int) \
                or ttl_seconds <= 0:
            raise HostedError("hosted_ttl_invalid")
        self._sub_key = bytes(sub_key)
        self._remaining_fen = starting_quota_fen
        self.clock = clock  # 公开可注入（TTL 负测拨钟用）；默认 time.time
        self._ttl_seconds = ttl_seconds
        self._devices: dict[str, bytes] = {}
        self._used_nonces: set[str] = set()

    @property
    def remaining_quota_fen(self) -> int:
        return self._remaining_fen

    def provision_device(self, device_id: str) -> dict:
        """登记设备并一次性发放 device_key（对称签名钥；端侧唯一持久化
        通道＝store_device_key→F12 保险库）。重复登记＝typed 拒。"""
        _require_device_id(device_id)
        if device_id in self._devices:
            raise HostedError("hosted_device_already_registered")
        device_key = secrets.token_bytes(_DEVICE_KEY_BYTES)
        self._devices[device_id] = device_key
        return {"schema": HOSTED_SCHEMA, "device_id": device_id,
                "device_key_b64": base64.b64encode(device_key).decode("ascii"),
                "note": "device_key 一次性回执；端侧唯一持久化通道＝"
                        "credential_vault（F12 面）；本回执零子key"}

    def issue_session(self, device_id: str, signature_hex: str, nonce: str,
                      requested_fen: int) -> dict:
        """验设备签名→验额度（整型分）→铸短 TTL 凭证（token 覆盖全部
        绑定字段）。回执零子key。"""
        _require_device_id(device_id)
        if not isinstance(nonce, str) or not nonce:
            raise HostedError("hosted_nonce_required")
        _require_fen(requested_fen)
        device_key = self._devices.get(device_id)
        if device_key is None:
            raise HostedError("hosted_device_not_registered")
        expected = device_signature(device_key, device_id, nonce,
                                    requested_fen)
        if not isinstance(signature_hex, str) \
                or not hmac.compare_digest(expected, signature_hex):
            raise HostedError("hosted_signature_invalid")
        if requested_fen > self._remaining_fen:
            raise HostedError("hosted_quota_exceeded")
        issued_at = self.clock()
        payload = {"schema": HOSTED_SCHEMA, "device_id": device_id,
                   "nonce": nonce, "authorized_fen": requested_fen,
                   "issued_at": issued_at,
                   "exp": issued_at + self._ttl_seconds,
                   "ttl_s": self._ttl_seconds}
        token = hmac.new(self._sub_key, _canonical(payload),
                         hashlib.sha256).hexdigest()
        credential = dict(payload, token=token)
        return {"schema": HOSTED_SCHEMA, "credential": credential,
                "remaining_quota_fen": self._remaining_fen,
                "note": "短 TTL 凭证已签发（绑定设备/额度/过期）；回执零子key"}

    def verify_session(self, credential, device_id: str) -> dict:
        """验凭证：token 完整性→设备绑定→TTL→重放→额度扣减（整型分）。
        失败路径一律 typed 拒且零扣减。"""
        _require_device_id(device_id)
        if not isinstance(credential, dict) \
                or any(key not in credential for key in _CREDENTIAL_KEYS):
            raise HostedError("hosted_credential_invalid")
        payload = {key: credential[key] for key in _CREDENTIAL_KEYS}
        if payload["schema"] != HOSTED_SCHEMA:
            raise HostedError("hosted_credential_invalid")
        token = credential.get("token")
        expected = hmac.new(self._sub_key, _canonical(payload),
                            hashlib.sha256).hexdigest()
        if not isinstance(token, str) \
                or not hmac.compare_digest(expected, token):
            raise HostedError("hosted_credential_invalid")
        if payload["device_id"] != device_id:
            raise HostedError("hosted_device_mismatch")
        if self.clock() > payload["exp"]:
            raise HostedError("hosted_credential_expired")
        authorized = payload["authorized_fen"]
        _require_fen(authorized)
        if payload["nonce"] in self._used_nonces:
            raise HostedError("hosted_credential_replayed")
        if authorized > self._remaining_fen:
            raise HostedError("hosted_quota_exceeded")
        self._used_nonces.add(payload["nonce"])
        self._remaining_fen -= authorized
        return {"schema": HOSTED_SCHEMA, "accepted": True,
                "device_id": device_id, "charged_fen": authorized,
                "remaining_quota_fen": self._remaining_fen,
                "synthetic": True,
                "note": "合成回执：真实模型推理 v2 商业化时接"
                        "（裁决#13-19）；本面不创第二 Agent loop"}


# 引用面（recon AST 断言用）：本模块公开面的全部 hosted_* 错误码。
HOSTED_ERROR_CODES = (
    "hosted_device_id_invalid", "hosted_quota_not_integer",
    "hosted_quota_invalid_amount", "hosted_device_key_invalid",
    "hosted_nonce_required", "hosted_sub_key_invalid", "hosted_clock_invalid",
    "hosted_ttl_invalid", "hosted_device_already_registered",
    "hosted_device_not_registered", "hosted_signature_invalid",
    "hosted_quota_exceeded", "hosted_credential_invalid",
    "hosted_device_mismatch", "hosted_credential_expired",
    "hosted_credential_replayed",
)

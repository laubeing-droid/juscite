# -*- coding: utf-8 -*-
"""F07 产品审计 HMAC 完整性面（工单 W3-U09）。

06 F07 assertion：保留源F07产品审计HMAC完整性要求，密钥归产品凭据设施；
不恢复Harness已拆部署签章总闸；篡改/截断/重放检测，摘要不含原件/身份/秘
密。owner=product+harness——harness 侧为既有静态复用（W25 audit_chain
SHA256 链＋audit.read/verify/export 公开方法，本单零改动、绝不恢复
SPLIT-LOCAL-3 stage B 已拆除的 activation/deployment/sealed-signature 总
闸）；**产品侧按 F07 扩 HMAC 链**：

  - 链形态＝HMAC-SHA256(key, canonical{stream_id, seq, previous_hash,
    event})，genesis previous=64 零；append-only JSONL（每流一文件），
    追加原子（append+flush+fsync），绝不改写历史行。
  - 密钥归产品凭据设施：唯一取钥通道＝credential_vault（DPAPI 密文；
    F12 面），登记位 lvyin.audit/hmac-sha256-v1。设施未配置/未登记＝
    typed audit_hmac_key_not_provisioned——审计面结构性没有独立钥文件、
    没有派生回退。
  - 篡改：任一行 event/previous/digest 改动→verify 处 audit_hmac_chain_
    broken:<seq>；截断（尾部行被删）→对 pinned head verify 处 audit_head_
    mismatch（无锚前缀自查通过与 harness 链同一边界——防全权重写攻击者
    不在本链主张内，如实陈述）；重放（旧行原样再插回存储）→verify 处
    audit_hmac_replay_refused:<seq>；append 前全链复验，绝不续写破损链。
  - 摘要不含原件/身份/秘密：事件闭集＝扁平 str/int/bool/None 元数据，
    单值≤512 字符、整事件 canonical ≤4096 字节（长文/二进制/嵌套结构
    typed 拒）——原件只以 digest/ref 进入事件；本面零日志零打印。
  - export 镜像＝verify 后写 JSON 镜像；已存在镜像必须为其前缀扩展
    （audit_export_tampered），同 harness export_mirror 纪律。

审计面是证据账，不是业务闸：append/verify 不挂在任何业务方法路径上
（不签章放行/拦截任何业务命令——部署签章总闸已拆，不恢复）。
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import tempfile
from pathlib import Path

from credential_vault import (AUDIT_KEY_ACCOUNT, AUDIT_KEY_SERVICE,
                              VaultError, vault_get)

AUDIT_SCHEMA = "lvyin-audit-hmac/1"

# legal_entry 冻结方法组（组外方法绝不落到本面）。
AUDIT_HMAC_METHODS = frozenset({
    "audit.append",
    "audit.verify",
    "audit.read",
    "audit.export",
})

ZERO_HASH = "0" * 64
_EVENT_VALUE_MAX = 512
_EVENT_CANONICAL_MAX = 4096
_EVENT_VALUE_TYPES = (str, int, bool, type(None))
_STREAM_MAX = 128

_DIR_NAME = "audit-hmac"
_EXPORT_DIR_NAME = "audit-hmac-export"


class AuditHmacError(RuntimeError):
    """Typed audit failure; str() is an audit_* code only."""


# ---------------------------------------------------------------------- #
# 密钥（唯一来源＝产品凭据设施 F12）
# ---------------------------------------------------------------------- #

def _audit_key(vault_state_root) -> bytes:
    if not vault_state_root:
        raise AuditHmacError("audit_hmac_key_not_provisioned")
    try:
        receipt = vault_get(vault_state_root, AUDIT_KEY_SERVICE,
                            AUDIT_KEY_ACCOUNT, reveal=True)
    except VaultError as exc:
        if str(exc).startswith("vault_entry_missing"):
            raise AuditHmacError(
                "audit_hmac_key_not_provisioned") from None
        raise AuditHmacError("audit_hmac_key_unavailable:"
                             + str(exc)) from None
    try:
        key = base64.b64decode(receipt["secret_b64"])
    except (KeyError, ValueError, TypeError):
        raise AuditHmacError("audit_hmac_key_unavailable") from None
    if len(key) != 32:
        raise AuditHmacError("audit_hmac_key_unavailable")
    return key


def provision_audit_key(vault_state_root, key: bytes | None = None) -> dict:
    """审计 HMAC 密钥登记（经凭据设施；测试/装机面用——审计面自身只读）。"""
    from credential_vault import vault_put
    if key is None:
        key = os.urandom(32)
    if not isinstance(key, (bytes, bytearray)) or len(key) != 32:
        raise AuditHmacError("audit_hmac_key_invalid")
    return vault_put(vault_state_root, AUDIT_KEY_SERVICE,
                     AUDIT_KEY_ACCOUNT, bytes(key))


# ---------------------------------------------------------------------- #
# 链核心
# ---------------------------------------------------------------------- #

def encoded(value) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"), allow_nan=False).encode("utf-8")


def entry_digest(key: bytes, stream_id: str, seq: int, previous: str,
                 event: dict) -> str:
    return hmac.new(key, encoded({
        "stream_id": stream_id, "seq": seq,
        "previous_hash": previous, "event": event,
    }), hashlib.sha256).hexdigest()


def _check_event(event) -> None:
    """事件闭集＝扁平元数据（原件/身份/秘密结构性进不了链）。"""
    if not isinstance(event, dict) or not event:
        raise AuditHmacError("audit_event_required")
    for key, value in event.items():
        if not isinstance(key, str) or not key:
            raise AuditHmacError("audit_event_payload_refused")
        if not isinstance(value, _EVENT_VALUE_TYPES) \
                or isinstance(value, float) or isinstance(value, bytes):
            raise AuditHmacError("audit_event_payload_refused")
        if isinstance(value, str) and len(value) > _EVENT_VALUE_MAX:
            raise AuditHmacError("audit_event_payload_refused")
    if len(encoded(event)) > _EVENT_CANONICAL_MAX:
        raise AuditHmacError("audit_event_payload_refused")


def _check_stream(stream_id) -> None:
    if not isinstance(stream_id, str) or not stream_id.strip() \
            or len(stream_id) > _STREAM_MAX \
            or any(sep in stream_id for sep in ("/", "\\", "..", ":")):
        raise AuditHmacError("audit_stream_invalid")


def _stream_path(audit_state_root, stream_id: str) -> Path:
    return Path(str(audit_state_root)) / _DIR_NAME / (stream_id + ".jsonl")


def _read_lines(path: Path) -> list[dict]:
    if not path.is_file():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            raise AuditHmacError("audit_chain_corrupt:blank_line")
        try:
            rows.append(json.loads(line))
        except ValueError:
            raise AuditHmacError("audit_chain_corrupt:unparsable_line") from None
    return rows


# ---------------------------------------------------------------------- #
# 四方法
# ---------------------------------------------------------------------- #

def audit_append(vault_state_root, audit_state_root,
                 stream_id: str, event: dict) -> dict:
    key = _audit_key(vault_state_root)
    _check_stream(stream_id)
    _check_event(event)
    path = _stream_path(audit_state_root, stream_id)
    rows = _read_lines(path)
    # 绝不在破损链上续写：追加前全链复验（账量小，O(N) 诚实代价）。
    verify_rows(key, stream_id, rows)
    if rows:
        head = rows[-1]
        seq, previous = head["seq"] + 1, head["digest"]
    else:
        seq, previous = 1, ZERO_HASH
    digest = entry_digest(key, stream_id, seq, previous, event)
    line = json.dumps({"seq": seq, "previous": previous,
                       "digest": digest, "event": event},
                      ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"))
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8", newline="\n") as handle:
        handle.write(line + "\n")
        handle.flush()
        os.fsync(handle.fileno())
    return {"schema": AUDIT_SCHEMA, "streamId": stream_id, "seq": seq,
            "previousHash": previous, "digest": digest,
            "note": "HMAC-SHA256 链追加；密钥经产品凭据设施（F12）"}


def verify_rows(key: bytes, stream_id: str, rows: list[dict],
                expected_head: str | None = None) -> str:
    previous = ZERO_HASH
    seen: set[int] = set()
    for expected_seq, row in enumerate(rows, start=1):
        seq = row.get("seq")
        if seq in seen:
            # 旧行被原样再插回（重放攻击形态）＝独立具名，不等同缺口。
            raise AuditHmacError(f"audit_hmac_replay_refused:{seq}")
        seen.add(seq)
        if seq != expected_seq:
            raise AuditHmacError(f"audit_hmac_sequence_gap:{expected_seq}")
        actual = entry_digest(key, stream_id, row["seq"], previous,
                              row["event"])
        if row.get("previous") != previous or row.get("digest") != actual:
            raise AuditHmacError(f"audit_hmac_chain_broken:{expected_seq}")
        previous = actual
    if expected_head is not None and previous != expected_head:
        raise AuditHmacError("audit_head_mismatch")
    return previous


def audit_verify(vault_state_root, audit_state_root,
                 stream_id: str, expected_head: str | None = None) -> dict:
    key = _audit_key(vault_state_root)
    _check_stream(stream_id)
    rows = _read_lines(_stream_path(audit_state_root, stream_id))
    head = verify_rows(key, stream_id, rows, expected_head)
    return {"schema": AUDIT_SCHEMA, "streamId": stream_id,
            "ok": True, "entries": len(rows), "head": head,
            "expectedHeadMatch": expected_head is None or head == expected_head,
            "boundary": "链检测=相对保留头的修改；防全权重写不在本链主张内"}


def audit_read(vault_state_root, audit_state_root, stream_id: str) -> dict:
    key = _audit_key(vault_state_root)
    _check_stream(stream_id)
    rows = _read_lines(_stream_path(audit_state_root, stream_id))
    head = verify_rows(key, stream_id, rows)
    return {"schema": AUDIT_SCHEMA, "streamId": stream_id, "head": head,
            "entries": [{"seq": row["seq"], "digest": row["digest"],
                         "event": row["event"]} for row in rows],
            "note": "事件＝扁平元数据（原件只以 digest/ref 在场）"}


def audit_export(vault_state_root, audit_state_root, stream_id: str) -> dict:
    """verify 后写 JSON 镜像；已存在镜像必须是新镜像的前缀（追加型）。"""
    read = audit_read(vault_state_root, audit_state_root, stream_id)
    target = (Path(str(audit_state_root)) / _EXPORT_DIR_NAME
              / (stream_id + ".json"))
    data = json.dumps(read, ensure_ascii=False, sort_keys=True,
                      indent=1).encode("utf-8")
    if target.exists():
        if not data.startswith(target.read_bytes()):
            raise AuditHmacError("audit_export_tampered")
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(dir=str(target.parent),
                                    prefix=stream_id + "-", suffix=".tmp")
    os.close(fd)
    with open(tmp_name, "wb") as handle:
        handle.write(data)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(tmp_name, target)
    return {"schema": AUDIT_SCHEMA, "streamId": stream_id,
            "exportPath": str(target), "head": read["head"],
            "entries": read["entries"] if "entries" in read else [],
            "entryCount": len(read["entries"]),
            "note": "镜像可核非第二真源；前缀不连续＝audit_export_tampered"}


# ---------------------------------------------------------------------- #
# legal_entry 冻结方法组分发（audit.*）
# ---------------------------------------------------------------------- #

def audit_hmac_call(method: str, args: dict, config: dict) -> dict:
    """legal_entry 冻结方法组分发。vault_state_root 未配置＝typed 拒（密
    钥归产品凭据设施，无独立钥文件）；audit_state_root 未配置＝typed 拒。
    未列方法绝不落到这里。"""
    if not isinstance(args, dict):
        raise AuditHmacError("audit_hmac_params_invalid")
    vault_root = config.get("vault_state_root")
    audit_root = config.get("audit_state_root")
    if method == "audit.append":
        if not audit_root:
            raise AuditHmacError("audit_state_root_not_configured")
        return audit_append(vault_root, audit_root,
                            args.get("stream_id"), args.get("event"))
    if method == "audit.verify":
        if not audit_root:
            raise AuditHmacError("audit_state_root_not_configured")
        return audit_verify(vault_root, audit_root,
                            args.get("stream_id"), args.get("expected_head"))
    if method == "audit.read":
        if not audit_root:
            raise AuditHmacError("audit_state_root_not_configured")
        return audit_read(vault_root, audit_root, args.get("stream_id"))
    if method == "audit.export":
        if not audit_root:
            raise AuditHmacError("audit_state_root_not_configured")
        return audit_export(vault_root, audit_root, args.get("stream_id"))
    raise AuditHmacError("audit_hmac_method_not_connected:" + method)

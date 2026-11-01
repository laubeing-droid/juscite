# -*- coding: utf-8 -*-
"""F123 导出签名清单·签发器（tamper-evident export，工单 W4-U54）。

06 F123（v1.5；owner=harness+product）：实际导出清单/文件 hash 验签可核；
篡改单文件被检出，私钥不出包。preserved：与「每条主张绑具名证据」宪法
同频——导出物是一束主张，其完整性事实入 harness 账可回读。

分工（合同 docs/f123-signed-export-contract.md，harness 仓 w4-u54 分支）：
  - 本面＝签发器：逐文件 sha256＋清单本身 HMAC-SHA256 签名＋经 harness
    export_record_create 把清单钉进账（签发不落账＝导出未完成——账本收
    到才返回签发回执）。
  - export_manifest_checker＝**独立验证器**（验证器与签发器不同代码路径
    ——calc_checker 独立算路先例；本模块绝不被其 import，wiring AST 钉
    死）。
  - harness＝只记账守门（export_records＋export_verifications 两账六方
    法），永不签发、永不验签。

密钥纪律（不出包三重钉）：
  - 密钥＝os.urandom(32)B，只存 `<signed_export_state_root>/f123-export/
    signing.secret`（state，非产物；F41 signing.secret 同名同法先例）。
  - 清单/账本/回执只携 keyFingerprint＝sha256(key) 前 16 hex（指纹非密
    钥）。
  - export.secret_exposure_scan＝全产物目录逐文件扫密钥 hex/原始字节
    （F41 batch_secret_exposure 同法；exposed=True 为 fail-closed 面，
    调用方断言零暴露）；发行物字节扫描（W3-U33 F77 工件字节扫描同法）
    在 recon 仓级另测。

清单规范（lvyin-signed-export/1）：
  manifest = {schema, exportId, matterId, createdAt, algorithm,
              keyFingerprint, files: [{path, sha256, bytes}], fileSetDigest}
  canonical 字节＝json.dumps(ensure_ascii=False, sort_keys=True,
  separators=(",",":")).encode("utf-8")（harness runtime.protocol.
  canonical_json 同形——账本侧独立重算摘要过账）。
  fileSetDigest＝sha256 over 排序 "sha256␠␠path" 行（LF 连接，无尾换
  行）。manifest.json＝manifest＋"signature"（对 canonical(无签名字段)
  的 HMAC-SHA256 hex）。

同输入确定性：文件字节/逐文件 sha256/文件集摘要确定性；清单含真实时钟
createdAt（manifest 字节不主张跨跑相同——账本钉定实际签发摘要）。
错误码只携工程标识（f123_*），材料内容永不进错误码。
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import json
import os
import re
import secrets as _secrets
from pathlib import Path

EXPORT_SCHEMA = "lvyin-signed-export/1"
EXPORT_ALGORITHM = "HMAC-SHA256"

# legal_entry 冻结方法组（组外方法绝不落到本面）。
EXPORT_MANIFEST_METHODS = frozenset({
    "export.package",
    "export.package_read",
    "export.package_list",
    "export.secret_exposure_scan",
})

_STATE_DIR = "f123-export"
_SECRET_NAME = "signing.secret"
_EXPORTS_DIR = "exports"
_MANIFEST_NAME = "manifest.json"
_KEY_BYTES = 32
_FINGERPRINT_HEX = 16
_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_PATH_MAX = 512
_FILES_MAX = 4096
_PURPOSE_MAX = 512
_SOURCE_REFS_MAX = 64

_PACKAGE_ARGS_FIELDS = frozenset({
    "exportId", "matterId", "purpose", "files", "sourceRefs"})
_PACKAGE_FILE_FIELDS = frozenset({"path", "dataB64"})


class SignedExportError(RuntimeError):
    """具名错误（f123_* 码），绝不携材料内容。"""


def _canonical(payload) -> bytes:
    """清单 canonical 字节（与 harness 账本重算同形）。"""
    return json.dumps(payload, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":")).encode("utf-8")


def _utcnow() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def file_set_digest(files: list) -> str:
    """文件集摘要＝sha256 over 排序 "sha256␠␠path" 行。"""
    lines = sorted(f"{entry['sha256']}  {entry['path']}" for entry in files)
    return hashlib.sha256("\n".join(lines).encode("utf-8")).hexdigest()


def fingerprint_of(key: bytes) -> str:
    return hashlib.sha256(key).hexdigest()[:_FINGERPRINT_HEX]


def _state_root(config: dict) -> Path:
    root = config.get("signed_export_state_root")
    if not root:
        raise SignedExportError("f123_state_root_not_configured")
    return Path(str(root)) / _STATE_DIR


def _load_or_create_key(state_dir: Path) -> bytes:
    """密钥唯一存所＝state 的 signing.secret（首次用 os.urandom 生成）。
    密钥永不进日志/回执/错误码。"""
    path = state_dir / _SECRET_NAME
    if path.is_file():
        key = path.read_bytes()
        if len(key) != _KEY_BYTES:
            raise SignedExportError("f123_signing_key_corrupt")
        return key
    key = _secrets.token_bytes(_KEY_BYTES)
    state_dir.mkdir(parents=True, exist_ok=True)
    # O_BINARY 必须显式：Windows os.open 缺省文本模式会把密钥字节里的
    # 0x0A 翻译成 0x0D 0x0A（密钥被改写，读回 corrupt——实测复现）。
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(
        os, "O_BINARY", 0) | getattr(os, "O_NOINHERIT", 0)
    fd = os.open(str(path), flags, 0o600)
    try:
        view = memoryview(key)
        while view:
            written = os.write(fd, view)
            view = view[written:]
    finally:
        os.close(fd)
    return key


def _validate_relative_path(path: str) -> str:
    if not isinstance(path, str) or not path or len(path) > _PATH_MAX:
        raise SignedExportError("f123_file_path_invalid")
    if path.startswith("/") or "\\" in path:
        raise SignedExportError("f123_file_path_invalid")
    parts = path.split("/")
    if any(part in ("", ".", "..") for part in parts):
        raise SignedExportError("f123_file_path_invalid")
    if re.match(r"^[A-Za-z]:", path):
        raise SignedExportError("f123_file_path_invalid")
    return path


def _entry_error(exc: Exception) -> SignedExportError:
    """桥错误原样透传为 f123_* 具名码（账面 typed 码不二次包裹）。"""
    return SignedExportError(str(exc))


def export_call(method: str, args: dict, config: dict,
                harness_call=None) -> dict:
    """F123 签发面唯一入口（legal_entry 冻结方法组分派）。

    harness_call 注入点：缺省＝legal_entry.call（desktop 桥子进程全链）；
    selfhost recon 注入封闭注册直连。"""
    if harness_call is None:
        from legal_entry import call as _entry_call

        def harness_call(h_method, h_args):
            return _entry_call(h_method, h_args, config)

    if not isinstance(args, dict):
        raise SignedExportError("f123_args_invalid")
    if method == "export.package":
        return _package(args, config, harness_call)
    if method == "export.package_read":
        return _package_read(args, config, harness_call)
    if method == "export.package_list":
        return _package_list(args, config, harness_call)
    if method == "export.secret_exposure_scan":
        return _secret_exposure_scan(config)
    raise SignedExportError("f123_method_unknown:" + method)


def _require_text(value, code: str) -> str:
    if not isinstance(value, str) or not value:
        raise SignedExportError(code)
    return value


def _package(args: dict, config: dict, harness_call) -> dict:
    """导出签发：写文件→逐文件 sha256→清单 canonical→HMAC 签名→harness
    账本登记（登记不到＝签发失败，typed 码上浮）→回执。"""
    extra = set(args) - _PACKAGE_ARGS_FIELDS
    if extra:
        raise SignedExportError("f123_args_fields_not_closed")
    export_id = _require_text(args.get("exportId"), "f123_export_id_invalid")
    if not _ID_RE.match(export_id):
        raise SignedExportError("f123_export_id_invalid")
    matter_id = _require_text(args.get("matterId"), "f123_matter_invalid")
    purpose = _require_text(args.get("purpose"), "f123_purpose_invalid")
    if len(purpose) > _PURPOSE_MAX:
        raise SignedExportError("f123_purpose_invalid")
    source_refs = args.get("sourceRefs", [])
    if not isinstance(source_refs, list) \
            or len(source_refs) > _SOURCE_REFS_MAX:
        raise SignedExportError("f123_source_refs_invalid")
    entries = args.get("files")
    if not isinstance(entries, list) or not (1 <= len(entries) <= _FILES_MAX):
        raise SignedExportError("f123_files_invalid")
    state_dir = _state_root(config)
    key = _load_or_create_key(state_dir)
    fingerprint = fingerprint_of(key)
    export_dir = state_dir / _EXPORTS_DIR / export_id
    files_dir = export_dir / "files"

    decoded: dict[str, bytes] = {}
    for entry in entries:
        if not isinstance(entry, dict) \
                or set(entry) != _PACKAGE_FILE_FIELDS:
            raise SignedExportError("f123_file_fields_not_closed")
        path = _validate_relative_path(entry.get("path"))
        if path in decoded:
            raise SignedExportError("f123_file_path_duplicate")
        try:
            data = base64.b64decode(entry.get("dataB64", ""), validate=True)
        except (binascii.Error, ValueError):
            raise SignedExportError("f123_file_data_invalid") from None
        decoded[path] = data

    # 幂等：同 export_id 已有清单——文件集一致＝不重写（走账本重放）；
    # 不一致＝具名拒（导出 id 绑定唯一文件集）。
    manifest_path = export_dir / _MANIFEST_NAME
    if manifest_path.is_file():
        try:
            existing = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            raise SignedExportError("f123_manifest_corrupt") from None
        existing_digests = {f["path"]: f["sha256"]
                            for f in existing.get("files", [])}
        incoming = {p: hashlib.sha256(b).hexdigest()
                    for p, b in decoded.items()}
        if existing_digests != incoming:
            raise SignedExportError("f123_export_id_conflict")

    file_entries = []
    for path, data in decoded.items():
        file_entries.append({"path": path,
                             "sha256": hashlib.sha256(data).hexdigest(),
                             "bytes": len(data)})

    # 幂等：同 export_id 已有清单且文件集一致＝沿用既有清单（同 manifest
    # 字节→账本 command 同封→重放同回执，不重写不重签）；不一致＝具名拒
    # （导出 id 绑定唯一文件集）。
    manifest_path = export_dir / _MANIFEST_NAME
    document = None
    if manifest_path.is_file():
        try:
            stored = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            raise SignedExportError("f123_manifest_corrupt") from None
        stored_digests = {f["path"]: f["sha256"]
                          for f in stored.get("files", [])}
        incoming = {p: hashlib.sha256(b).hexdigest()
                    for p, b in decoded.items()}
        if stored_digests != incoming:
            raise SignedExportError("f123_export_id_conflict")
        if str(stored.get("matterId")) != matter_id:
            raise SignedExportError("f123_matter_mismatch")
        document = stored
        manifest = {k: v for k, v in stored.items() if k != "signature"}
    else:
        manifest = {
            "schema": EXPORT_SCHEMA,
            "exportId": export_id,
            "matterId": matter_id,
            "createdAt": _utcnow(),
            "algorithm": EXPORT_ALGORITHM,
            "keyFingerprint": fingerprint,
            "files": file_entries,
            "fileSetDigest": file_set_digest(file_entries),
        }

    canonical_bytes = _canonical(manifest)
    manifest_sha256 = hashlib.sha256(canonical_bytes).hexdigest()
    if document is None:
        signature = hmac.new(key, canonical_bytes,
                             hashlib.sha256).hexdigest()
        document = dict(manifest)
        document["signature"] = {"algorithm": EXPORT_ALGORITHM,
                                 "keyFingerprint": fingerprint,
                                 "value": signature}

    # 先落文件（写齐才落清单），再落清单，再过账本（登记不到＝签发未
    # 完成，typed 码上浮）。
    if not manifest_path.is_file():
        for path, data in decoded.items():
            target = files_dir / Path(*path.split("/"))
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
        export_dir.mkdir(parents=True, exist_ok=True)
        manifest_path.write_text(
            json.dumps(document, ensure_ascii=False, indent=1,
                       sort_keys=True), encoding="utf-8")

    try:
        ledger = harness_call("harness.export_record_create", {
            "actor_id": "lvyin-product", "export_id": export_id,
            "purpose": purpose, "manifest": manifest,
            "manifest_sha256": manifest_sha256,
            "source_refs": source_refs,
            "scope": {"kind": "matter", "matterId": matter_id},
            "key": {"requestId": f"f123-export-{export_id}",
                    "targetId": None, "expectedRevision": None,
                    "inputRefs": []},
        })
    except SignedExportError:
        raise
    except Exception as exc:
        raise _entry_error(exc) from None
    record = ledger.get("result", ledger) if isinstance(ledger, dict) \
        else ledger
    if not isinstance(record, dict) or "recordRef" not in record:
        raise SignedExportError("f123_ledger_receipt_invalid")
    return {"exportId": export_id,
            "matterId": matter_id,
            "dir": str(export_dir),
            "manifestSha256": manifest_sha256,
            "fileSetDigest": manifest["fileSetDigest"],
            "fileCount": len(file_entries),
            "totalBytes": sum(f["bytes"] for f in file_entries),
            "algorithm": EXPORT_ALGORITHM,
            "keyFingerprint": fingerprint,
            "recordRef": record["recordRef"],
            "ledger": record}


def _package_read(args: dict, config: dict, harness_call) -> dict:
    """导出回读＝清单文件＋账本签发行两侧并读（本面只读，不验签——验签
    分义给独立验证器 export.verify）。"""
    export_id = _require_text(args.get("exportId"), "f123_export_id_invalid")
    if not _ID_RE.match(export_id):
        raise SignedExportError("f123_export_id_invalid")
    state_dir = _state_root(config)
    manifest_path = state_dir / _EXPORTS_DIR / export_id / _MANIFEST_NAME
    if not manifest_path.is_file():
        raise SignedExportError("f123_export_not_found")
    try:
        document = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        raise SignedExportError("f123_manifest_corrupt") from None
    signature = document.pop("signature", None)
    manifest_sha256 = hashlib.sha256(_canonical(document)).hexdigest()
    try:
        ledger = harness_call("harness.export_record_read", {
            "scope": {"kind": "matter",
                      "matterId": str(document.get("matterId"))},
            "export_id": export_id})
    except SignedExportError:
        raise
    except Exception as exc:
        raise _entry_error(exc) from None
    record = ledger.get("result", ledger) if isinstance(ledger, dict) \
        else ledger
    return {"exportId": export_id, "manifest": document,
            "signature": signature, "manifestSha256": manifest_sha256,
            "ledger": record}


def _package_list(args: dict, config: dict, harness_call) -> dict:
    """导出面清单＝账本投影（ledger 是唯一权威——盘上目录只是产物）。
    需 matterId 定 scope。"""
    matter_id = _require_text(args.get("matterId"), "f123_matter_invalid")
    try:
        ledger = harness_call("harness.export_record_list", {
            "scope": {"kind": "matter", "matterId": matter_id}})
    except SignedExportError:
        raise
    except Exception as exc:
        raise _entry_error(exc) from None
    return ledger.get("result", ledger) if isinstance(ledger, dict) \
        else ledger


def _secret_exposure_scan(config: dict) -> dict:
    """密钥不进产物断言（F41 batch_secret_exposure 同法）：扫描 f123-
    export 状态树全部产物文件（signing.secret 本体除外），密钥十六进制/
    原始字节任一出现＝exposed（调用方断言零暴露；正控样本由 recon 在另
    立临时状态根注入后同法扫描证明非空转）。"""
    state_dir = _state_root(config)
    key = _load_or_create_key(state_dir)
    needles = (key.hex().encode("ascii"), key)
    scanned = 0
    for path in sorted(state_dir.rglob("*")):
        if not path.is_file() or path.name == _SECRET_NAME:
            continue
        data = path.read_bytes()
        scanned += 1
        if any(needle in data for needle in needles):
            return {"exposed": True,
                    "exposedFile": path.name,
                    "scannedFiles": scanned}
    return {"exposed": False, "exposedFile": None,
            "scannedFiles": scanned}

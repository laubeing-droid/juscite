# -*- coding: utf-8 -*-
"""F123 导出签名清单·独立验证器（工单 W4-U54）。

06 F123（v1.5；owner=harness+product）：实际导出清单/文件 hash 验签可核；
篡改单文件被检出，私钥不出包。

**独立验证路径（硬纪律）**：本模块与签发器 signed_export 是不同代码路径
（calc_checker 独立算路先例）——
  - 零 import signed_export（wiring AST 钉死）；canonical 序列化/密钥装
    载/清单解析全部本模块自带实现；
  - 逐文件 hash **遍历实际目录**独立重算（绝不信任清单文件列表——增删
    文件在目录遍历侧显形）；
  - 文件集摘要、清单 canonical 摘要、HMAC 全部本模块独立重算。

三形态篡改＋清单自身两形，全部检出且定位到具体文件（findings 形态闭集
＝harness export_verification_record 合同同闭集）：
  file_hash_mismatch        改单文件字节（该文件 hash 不符）
  file_missing              删文件（清单有、盘上无）
  file_not_in_manifest      增/换外来文件（盘上有、清单无）
  manifest_signature_invalid 清单本身被改（签名不验）
  file_set_digest_mismatch  清单内部文件集摘要与逐文件行不一致

verdict 闭集 PASS/TAMPERED：PASS 当且仅当零 findings 且签名验过——结论
与事实互斥绑定（harness 回执账同合同）。密钥只读本机 state 的
signing.secret（与签发器同一物理文件、不同代码路径）；本面零打印零日
志，密钥/材料内容永不进错误码与回执。
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
from pathlib import Path

# legal_entry 冻结方法组（组外方法绝不落到本面）。
EXPORT_CHECKER_METHODS = frozenset({
    "export.verify",
})

EXPORT_SCHEMA = "lvyin-signed-export/1"
EXPORT_ALGORITHM = "HMAC-SHA256"

_STATE_DIR = "f123-export"
_SECRET_NAME = "signing.secret"
_EXPORTS_DIR = "exports"
_MANIFEST_NAME = "manifest.json"
_KEY_BYTES = 32

# findings 形态闭集（harness export_verification_record 同合同）。
FINDING_FORMS = frozenset({
    "file_hash_mismatch",
    "file_missing",
    "file_not_in_manifest",
    "manifest_signature_invalid",
    "file_set_digest_mismatch",
})
VERDICTS = frozenset({"PASS", "TAMPERED"})


class ExportManifestCheckError(RuntimeError):
    """具名错误（f123chk_* 码），绝不携材料内容/密钥。"""


def checker_call(method: str, args: dict, config: dict) -> dict:
    """F123 验证器唯一入口（legal_entry 冻结方法组分派）。"""
    if method != "export.verify":
        raise ExportManifestCheckError("f123chk_method_unknown:" + method)
    if not isinstance(args, dict):
        raise ExportManifestCheckError("f123chk_args_invalid")
    export_id = args.get("exportId")
    if not isinstance(export_id, str) or not export_id:
        raise ExportManifestCheckError("f123chk_export_id_invalid")
    root = config.get("signed_export_state_root")
    if not root:
        raise ExportManifestCheckError("f123chk_state_root_not_configured")
    state_dir = Path(str(root)) / _STATE_DIR
    export_dir = state_dir / _EXPORTS_DIR / export_id
    if not export_dir.is_dir():
        raise ExportManifestCheckError("f123chk_export_not_found")
    return verify_export(export_dir)


def _canonical(payload) -> bytes:
    """清单 canonical 字节（本模块自带实现——与签发器不同代码路径）。"""
    return json.dumps(payload, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":")).encode("utf-8")


def _load_key(state_dir: Path) -> bytes:
    """密钥装载（本模块自带实现；同一物理文件、不同代码路径）。"""
    path = state_dir / _SECRET_NAME
    if not path.is_file():
        raise ExportManifestCheckError("f123chk_key_absent")
    key = path.read_bytes()
    if len(key) != _KEY_BYTES:
        raise ExportManifestCheckError("f123chk_key_corrupt")
    return key


def _walk_actual_files(files_dir: Path) -> dict:
    """遍历实际目录（不信任清单文件列表——增删在遍历侧显形）。"""
    actual = {}
    if not files_dir.is_dir():
        return actual
    for current, _dirs, names in os.walk(files_dir):
        for name in names:
            path = Path(current) / name
            rel = path.relative_to(files_dir).as_posix()
            actual[rel] = hashlib.sha256(path.read_bytes()).hexdigest()
    return actual


def verify_export(export_dir: Path) -> dict:
    """清单 hash 验签＋目录全量对账。findings 逐条定位到具体文件；
    verdict=PASS 当且仅当零 findings 且签名验过。"""
    export_id = export_dir.name
    manifest_path = export_dir / _MANIFEST_NAME
    if not manifest_path.is_file():
        raise ExportManifestCheckError("f123chk_manifest_absent")
    raw = manifest_path.read_bytes()
    try:
        document = json.loads(raw.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        raise ExportManifestCheckError("f123chk_manifest_corrupt") from None
    if not isinstance(document, dict) \
            or document.get("schema") != EXPORT_SCHEMA:
        raise ExportManifestCheckError("f123chk_manifest_schema_unknown")
    signature = document.get("signature")
    manifest = {k: v for k, v in document.items() if k != "signature"}
    findings: list[dict] = []

    # ① 清单本身：HMAC-SHA256 对 canonical(无签名字段) 验签。
    key = _load_key(export_dir.parent.parent)
    signature_value = None
    if isinstance(signature, dict) \
            and signature.get("algorithm") == EXPORT_ALGORITHM:
        signature_value = signature.get("value")
    if not isinstance(signature_value, str) or not signature_value:
        findings.append({"form": "manifest_signature_invalid",
                         "path": _MANIFEST_NAME})
    else:
        expected = hmac.new(key, _canonical(manifest),
                            hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected, signature_value):
            findings.append({"form": "manifest_signature_invalid",
                             "path": _MANIFEST_NAME})

    # ② 清单内部：文件集摘要 vs 逐文件行（清单被改且签名同谋过不了——
    # 但摘要规则自洽性独立于签名成立）。
    files = manifest.get("files")
    manifest_paths: dict[str, str] = {}
    if isinstance(files, list) and files:
        for entry in files:
            if isinstance(entry, dict) \
                    and isinstance(entry.get("path"), str) \
                    and isinstance(entry.get("sha256"), str):
                manifest_paths[entry["path"]] = entry["sha256"]
        lines = sorted(f"{entry['sha256']}  {entry['path']}"
                       for entry in files
                       if isinstance(entry, dict)
                       and isinstance(entry.get("path"), str)
                       and isinstance(entry.get("sha256"), str))
        recomputed_set = hashlib.sha256(
            "\n".join(lines).encode("utf-8")).hexdigest()
        if recomputed_set != manifest.get("fileSetDigest"):
            findings.append({"form": "file_set_digest_mismatch",
                             "path": _MANIFEST_NAME})
    else:
        findings.append({"form": "file_set_digest_mismatch",
                         "path": _MANIFEST_NAME})

    # ③ 目录全量对账（三形态篡改逐一定位）。
    actual = _walk_actual_files(export_dir / "files")
    for rel in sorted(actual):
        if rel not in manifest_paths:
            findings.append({"form": "file_not_in_manifest", "path": rel})
        elif actual[rel] != manifest_paths[rel]:
            findings.append({"form": "file_hash_mismatch", "path": rel})
    for rel in sorted(set(manifest_paths) - set(actual)):
        findings.append({"form": "file_missing", "path": rel})

    findings.sort(key=lambda f: (f["form"], f["path"]))
    verdict = "PASS" if not findings else "TAMPERED"
    return {"exportId": export_id,
            "verdict": verdict,
            "signatureValid": not any(
                f["form"] == "manifest_signature_invalid"
                for f in findings),
            "manifestSha256": hashlib.sha256(
                _canonical(manifest)).hexdigest(),
            "fileSetDigest": manifest.get("fileSetDigest"),
            "checkedFileCount": len(actual),
            "manifestFileCount": len(manifest_paths),
            "findings": findings}

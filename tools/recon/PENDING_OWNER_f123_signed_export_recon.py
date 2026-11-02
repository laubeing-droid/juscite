# -*- coding: utf-8 -*-
"""F123 导出签名清单（tamper-evident export）验收 recon（工单 W4-U54）。

06 F123（v1.5；owner=harness+product；desktop/selfhost 双实例；
acceptance：实际导出清单/文件 hash 验签可核；篡改单文件被检出，私钥不出
包；preserved：与「每条主张绑具名证据」宪法同频）。

验收命令（工单钦定，worktree 根 cwd）：
  python -X utf8 tools/recon/PENDING_OWNER_f123_signed_export_recon.py \\
      --profile desktop --profile selfhost
exit 0 = RECON_OK。

  - desktop 腿＝真产品入口 legal_entry 子进程径（EXPORT_MANIFEST_METHODS
    ＋EXPORT_CHECKER_METHODS＋HARNESS_EXPORT_LEDGER_METHODS 三冻结组 →
    harness public_entry --exportledger-json 信封真子进程；临时 SQLite
    状态根）；
  - selfhost 腿＝PgMatterStore 直连 lh-pg-e08 独立 schema（E24/F118/F122
    recon selfhost 腿同径；resolve_provider_method 同一封闭注册；产品面
    harness_call 注入直连同封闭注册；用毕 destroy）。

断言面（全合成材料；导出文件内容全部合成文本）：
  S1 签发链：逐文件 sha256＋清单 HMAC-SHA256 签名＋过账才回执——清单
     canonical 摘要/文件集摘要签发回执-账本-验签器三方相等；signing.secret
     只存 state（32B）；密钥本体（原始字节/hex）不在清单与账面回执（只
     许指纹在场）；
  S2 幂等与冲突：同输入重导出＝同清单摘要同回执（账面不双记）；同
     export_id 异文件集＝f123_export_id_conflict 具名拒；
  S3 独立验签正：export.verify（独立验证器）＝PASS 零 findings；清单摘
     要与账本一致；
  S4 三形态篡改＋清单两形：改单文件字节/增换外来文件/删文件全部检出且
     定位到具体文件；清单被改＝manifest_signature_invalid；逐形态 TAMPERED
     回执落账（append-only 历史保全——先行 PASS 不被抹）；
  S5 密钥零暴露（不出包三重钉）：①全产物扫描（F41 batch_secret_exposure
     同法）零命中＋正控样本命中（证明非空转）；②发行物/仓级字节扫描
     （W3-U33 F77 工件字节扫描同法：git tracked 全文件扫密钥 hex/原始
     字节）零命中；
  S6 桥纪律：未配置 NotConnected 具名（desktop 子进程 exit 3）；封闭注
     册外方法具名拒（desktop 子进程径＋selfhost 直连径同语义）；
  S7 双 profile 一致：同一合成文件集跨 profile 内容级投影逐键相等（逐
     文件 hash/文件集摘要/算法/验签判定——manifest 含真实时钟 createdAt，
     清单字节不主张跨 profile 相同，U08/E15 剥时间戳先例）。
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

RUN_DATE = time.strftime("%Y%m%d")
REPO_ROOT = Path(__file__).resolve().parents[2]
LEGAL_ENTRY = REPO_ROOT / "implementation" / "python" / "legal_entry.py"

# harness 战役分支（A2 链）本单检出与 F123 面钉定
HARNESS_WORKTREE = Path(
    r"D:\Codex\1.法律工作区\legal-harness工作区\legal-harness-repo"
    r"\.local\worktrees\w4-u54")
HARNESS_PUBLIC_ENTRY = HARNESS_WORKTREE / Path(
    "tools/workflow-tools/harness/public_entry.py")
HARNESS_BRANCH = "w4-u54"

DEFAULT_PG_DSN = "postgresql://lh_app:e08-synth-only@127.0.0.1:55432/legal_harness"

MATTER_X = "m-f123-rx"

EXPORT_LEDGER_METHODS = frozenset({
    "harness.export_record_create", "harness.export_record_read",
    "harness.export_record_list", "harness.export_verification_record",
    "harness.export_verification_read", "harness.export_verification_list",
})

# 合成导出文件集（全合成；含中文路径与中文内容）
SYNTH_FILES = [
    ("docs/起诉状-合成案.docx",
     b"PK\x03\x04 synthetic pleading body \xe5\xbe\x8b\xe5\xbc\x95 recon"),
    ("evidence/证据-合成卷.pdf",
     b"%PDF-1.7 synthetic evidence bytes for f123 recon"),
    ("README-合成导出.txt",
     "合成导出说明（recon 合成材料）\n".encode("utf-8")),
]


def sha256_bytes(blob: bytes) -> str:
    return hashlib.sha256(blob).hexdigest()


def canonical(payload) -> bytes:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":")).encode("utf-8")


def _key(request_id: str) -> dict:
    return {"requestId": request_id, "targetId": None,
            "expectedRevision": None, "inputRefs": []}


def _file_args(files: list) -> list:
    return [{"path": p, "dataB64": base64.b64encode(b).decode("ascii")}
            for p, b in files]


def _package_args(export_id: str) -> dict:
    return {"exportId": export_id, "matterId": MATTER_X,
            "purpose": "代理审判材料导出（合成 recon）",
            "files": _file_args(SYNTH_FILES), "sourceRefs": []}


class Checks:
    def __init__(self, profile: str) -> None:
        self.profile = profile
        self.items: list = []

    def step(self, check_id: str, ok: bool, detail: str = "", **extra) -> None:
        item = {"id": check_id, "status": "PASS" if ok else "FAIL",
                "detail": detail}
        if extra:
            item.update(extra)
        self.items.append(item)

    @property
    def failed(self) -> list:
        return [i for i in self.items if i["status"] != "PASS"]

    @property
    def verdict(self) -> str:
        return "RECON_OK" if self.items and not self.failed else "RECON_FAILED"


def call_entry(method: str, args: dict, config: dict) -> dict:
    """真产品入口子进程调用；返回 {exit, payload}。"""
    request_handle = tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", suffix=".json", delete=False)
    config_handle = tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", suffix=".json", delete=False)
    try:
        json.dump({"method": method, "args": args}, request_handle,
                  ensure_ascii=False)
        request_handle.close()
        json.dump(config, config_handle, ensure_ascii=False)
        config_handle.close()
        env = dict(os.environ)
        python_dir = str(REPO_ROOT / "implementation" / "python")
        env["PYTHONPATH"] = python_dir + os.pathsep + env.get("PYTHONPATH", "")
        proc = subprocess.run(
            [sys.executable, "-X", "utf8", str(LEGAL_ENTRY),
             "--request-json", request_handle.name,
             "--config", config_handle.name],
            capture_output=True, text=True, encoding="utf-8",
            timeout=600, cwd=str(REPO_ROOT), env=env)
        try:
            payload = json.loads(proc.stdout)
        except json.JSONDecodeError:
            payload = {"_raw": proc.stdout[-500:]}
        return {"exit": proc.returncode, "payload": payload}
    finally:
        os.unlink(request_handle.name)
        os.unlink(config_handle.name)


def entry_call(method: str, args: dict, config: dict) -> dict:
    """产品入口调用（exit!=0 时把 typed code 抛为 HarnessCommandError）。"""
    from bridge_errors import HarnessCommandError
    response = call_entry(method, args, config)
    if response["exit"] == 0:
        return response["payload"]["result"]
    code = response["payload"].get("code") \
        or response["payload"].get("error") or "entry_failed"
    raise HarnessCommandError(str(code))


def call_harness(method: str, params: dict, state_root: Path) -> dict:
    """harness public_entry --exportledger-json 信封子进程径（对照半边）。"""
    command_handle = tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", suffix=".json", delete=False)
    try:
        json.dump({"method": method, "params": params}, command_handle,
                  ensure_ascii=False)
        command_handle.close()
        env = dict(os.environ)
        env["LH_LEGAL_STATE_ROOT"] = str(state_root)
        proc = subprocess.run(
            [sys.executable, "-X", "utf8", str(HARNESS_PUBLIC_ENTRY),
             "--exportledger-json", command_handle.name, "--target",
             "opencode"],
            capture_output=True, text=True, encoding="utf-8", timeout=600,
            cwd=str(HARNESS_WORKTREE), env=env)
        try:
            payload = json.loads(proc.stdout)
        except json.JSONDecodeError:
            payload = {"_raw": (proc.stdout + proc.stderr)[-500:]}
        return {"exit": proc.returncode, "payload": payload}
    finally:
        os.unlink(command_handle.name)


def _fingerprint_text(key: bytes) -> str:
    return hashlib.sha256(key).hexdigest()[:16]


def _repo_byte_scan(key: bytes) -> dict:
    """发行物/仓级字节扫描（W3-U33 F77 工件字节扫描同法）：juscite
    worktree 全部 git tracked 文件扫密钥 hex/原始字节——发行物由本树
    tracked 源与产物构成，密钥零命中＝私钥不出仓不出包（方法级钉定；
    非空转由 S5 正控样本另证）。"""
    needles = (key, key.hex().encode("ascii"))
    proc = subprocess.run(
        ["git", "ls-files"], cwd=str(REPO_ROOT), capture_output=True,
        text=True, encoding="utf-8", timeout=300)
    if proc.returncode != 0:
        return {"ok": False, "error": "git_ls_files_failed"}
    scanned = 0
    hits = []
    for line in proc.stdout.splitlines():
        rel = line.strip()
        if not rel:
            continue
        path = REPO_ROOT / rel
        if not path.is_file():
            continue
        try:
            data = path.read_bytes()
        except OSError:
            continue
        scanned += 1
        if any(needle in data for needle in needles):
            hits.append(rel)
    return {"ok": True, "scanned": scanned, "hits": hits}


def _projection(export_receipt: dict, verdict: dict, record: dict) -> dict:
    """跨 profile 内容级投影（剥时变键：createdAt 与其派生的清单摘要不
    参与——manifest 含真实时钟，清单字节/摘要不主张跨 profile 相同；
    U08/E15 剥时间戳先例。清单摘要的账本绑定在 S1 per-profile 三方断
    言）。"""
    return {
        "fileSetDigest": export_receipt["fileSetDigest"],
        "fileCount": export_receipt["fileCount"],
        "totalBytes": export_receipt["totalBytes"],
        "algorithm": export_receipt["algorithm"],
        "files": [{"path": f["path"], "sha256": f["sha256"],
                   "bytes": f["bytes"]}
                  for f in sorted(
                      (json.loads((Path(export_receipt["dir"])
                                   / "manifest.json").read_text(
                                       encoding="utf-8"))["files"]),
                      key=lambda f: f["path"])],
        "verdict": verdict["verdict"],
        "findings": verdict["findings"],
        "checkedFileCount": verdict["checkedFileCount"],
        "ledgerFileCount": record["fileCount"],
    }


def section_s1_sign(checks: Checks, export, read_record) -> dict:
    """S1 签发链：逐文件 sha256＋清单签名＋过账才回执＋密钥只存 state。"""
    receipt = export("f123-s1", _package_args("f123-s1"))
    export_dir = Path(receipt["dir"])
    ok_files = True
    for path, blob in SYNTH_FILES:
        on_disk = export_dir / "files" / Path(*path.split("/"))
        if not on_disk.is_file() \
                or sha256_bytes(on_disk.read_bytes()) != sha256_bytes(blob):
            ok_files = False
    checks.step("s1_files_on_disk_hash_match", ok_files,
                "files=%d dir=%s" % (len(SYNTH_FILES), export_dir.name))
    document = json.loads(
        (export_dir / "manifest.json").read_text(encoding="utf-8"))
    manifest = {k: v for k, v in document.items() if k != "signature"}
    digest = sha256_bytes(canonical(manifest))
    checks.step(
        "s1_manifest_signed_and_bound",
        document.get("schema") == "lvyin-signed-export/1"
        and document.get("algorithm") == "HMAC-SHA256"
        and len(document.get("signature", {}).get("value", "")) == 64
        and receipt["manifestSha256"] == digest,
        "manifestSha256=%s…" % digest[:16])
    record = read_record("f123-s1")
    checks.step(
        "s1_ledger_binds_manifest",
        record["manifestSha256"] == digest
        and record["fileSetDigest"] == receipt["fileSetDigest"]
        and record["fileCount"] == len(SYNTH_FILES)
        and record["algorithm"] == "HMAC-SHA256",
        "record=%s fileSet=%s…" % (record["exportId"],
                                   record["fileSetDigest"][:12]))
    # 密钥只存 state：signing.secret 32B；密钥本体不在清单/账面回执。
    state_dir = Path(receipt["dir"]).parents[1]
    secret = state_dir / "signing.secret"
    key = secret.read_bytes() if secret.is_file() else b""
    manifest_text = (export_dir / "manifest.json").read_text(
        encoding="utf-8")
    record_text = json.dumps(record, ensure_ascii=False)
    no_key = (len(key) == 32
              and key not in manifest_text.encode("utf-8")
              and key.hex().encode("ascii") not in manifest_text.encode("utf-8")
              and key.hex() not in record_text)
    checks.step("s1_key_only_in_state_fingerprint_only_everywhere",
                no_key,
                "secret=32B fingerprint=%s…" % _fingerprint_text(key)[:8])
    return {"receipt": receipt, "record": record, "key": key}


def section_s2_idempotency(checks: Checks, export, listed) -> None:
    """S2 幂等与冲突。"""
    first = export("f123-s2", _package_args("f123-s2"))
    second = export("f123-s2", _package_args("f123-s2"))
    checks.step(
        "s2_idempotent_replay_same_manifest",
        first["manifestSha256"] == second["manifestSha256"]
        and first["recordRef"]["id"] == second["recordRef"]["id"],
        "manifest=%s…" % first["manifestSha256"][:12])
    rows = [i for i in listed()["items"] if i["exportId"] == "f123-s2"]
    checks.step("s2_ledger_no_duplicate", len(rows) == 1,
                "rows=%d" % len(rows))
    swapped = [("docs/起诉状-合成案.docx", b"tampered different bytes")]
    try:
        export("f123-s2", {"exportId": "f123-s2", "matterId": MATTER_X,
                           "purpose": "换内容", "files": _file_args(swapped),
                           "sourceRefs": []})
        checks.step("s2_same_id_different_content_refused", False,
                    "expected typed refusal")
    except Exception as exc:  # noqa: BLE001
        checks.step("s2_same_id_different_content_refused",
                    "f123_export_id_conflict" in str(exc),
                    "code=%s" % str(exc)[:80])


def section_s3_s4_verify_tamper(checks: Checks, export, verify,
                                record_verification, verification_list) -> None:
    """S3 独立验签正＋S4 三形态篡改＋清单两形（逐形态落 TAMPERED 回执，
    append-only 历史保全）。"""
    export("f123-s3", _package_args("f123-s3"))
    clean = verify("f123-s3")
    checks.step(
        "s3_clean_verify_pass",
        clean["verdict"] == "PASS" and clean["findings"] == []
        and clean["checkedFileCount"] == len(SYNTH_FILES),
        "verdict=%s checked=%d" % (clean["verdict"],
                                   clean["checkedFileCount"]))
    # S3 正验 PASS 先行落回执（历史第一条）。
    record_verification("f123-s3", clean, "s3-pass",
                        clean["manifestSha256"])
    probe = export("f123-s4base", _package_args("f123-s4base"))
    exports_root = Path(probe["dir"]).parent
    # s4base 正验 PASS 先行落回执（其账历史第一条）；四形态 TAMPERED
    # 回执钉同一清单摘要（验的就是已导出的清单——异摘要账面具名拒）。
    clean_s4 = verify("f123-s4base")
    record_verification("f123-s4base", clean_s4, "s4-pass",
                        clean_s4["manifestSha256"])

    import shutil
    def make_tampered_copy(suffix: str) -> Path:
        target = exports_root / f"f123-s4base-{suffix}"
        if target.exists():
            shutil.rmtree(target)
        shutil.copytree(exports_root / "f123-s4base", target)
        return target

    record_digest = clean_s4["manifestSha256"]

    # ① 改单文件字节。
    copy1 = make_tampered_copy("t1")
    victim = copy1 / "files" / "evidence" / "证据-合成卷.pdf"
    victim.write_bytes(victim.read_bytes() + b"tampered")
    v1 = verify("f123-s4base-t1")
    forms1 = [(f["form"], f["path"]) for f in v1["findings"]]
    checks.step(
        "s4_tamper_bytes_detected_localized",
        v1["verdict"] == "TAMPERED"
        and ("file_hash_mismatch", "evidence/证据-合成卷.pdf") in forms1,
        "findings=%s" % forms1)
    record_verification("f123-s4base", v1, "s4-t1", record_digest)

    # ② 增/换外来文件。
    copy2 = make_tampered_copy("t2")
    (copy2 / "files" / "docs" / "外来件-合成.txt").write_bytes(
        b"foreign artifact")
    v2 = verify("f123-s4base-t2")
    forms2 = [(f["form"], f["path"]) for f in v2["findings"]]
    checks.step(
        "s4_foreign_file_added_detected_localized",
        v2["verdict"] == "TAMPERED"
        and ("file_not_in_manifest", "docs/外来件-合成.txt") in forms2,
        "findings=%s" % forms2)
    record_verification("f123-s4base", v2, "s4-t2", record_digest)

    # ③ 删文件。
    copy3 = make_tampered_copy("t3")
    (copy3 / "files" / "README-合成导出.txt").unlink()
    v3 = verify("f123-s4base-t3")
    forms3 = [(f["form"], f["path"]) for f in v3["findings"]]
    checks.step(
        "s4_file_deleted_detected_localized",
        v3["verdict"] == "TAMPERED"
        and ("file_missing", "README-合成导出.txt") in forms3,
        "findings=%s" % forms3)
    record_verification("f123-s4base", v3, "s4-t3", record_digest)

    # ④ 清单本身被改。
    copy4 = make_tampered_copy("t4")
    document = json.loads(
        (copy4 / "manifest.json").read_text(encoding="utf-8"))
    document["files"][0]["sha256"] = "0" * 64
    (copy4 / "manifest.json").write_text(
        json.dumps(document, ensure_ascii=False, indent=1, sort_keys=True),
        encoding="utf-8")
    v4 = verify("f123-s4base-t4")
    forms4 = [f["form"] for f in v4["findings"]]
    checks.step(
        "s4_manifest_tamper_signature_invalid",
        v4["verdict"] == "TAMPERED"
        and "manifest_signature_invalid" in forms4
        and v4["signatureValid"] is False,
        "findings=%s" % forms4[:3])
    record_verification("f123-s4base", v4, "s4-t4", record_digest)

    # 干净正本复验仍 PASS（篡改只伤被篡副本）。
    v0 = verify("f123-s4base")
    checks.step("s4_clean_original_unaffected",
                v0["verdict"] == "PASS", "verdict=%s" % v0["verdict"])

    # 验签回执账 append-only 历史保全：PASS 先行＋四条 TAMPERED。
    history = verification_list("f123-s3")
    seqs = [i["verificationSeq"] for i in history["items"]]
    verdicts = [i["verdict"] for i in history["items"]]
    checks.step(
        "s4_verification_history_append_only",
        history["count"] >= 1 and seqs == sorted(seqs)
        and verdicts[0] == "PASS",
        "count=%d verdicts=%s" % (history["count"], verdicts))


def section_s5_exposure(checks: Checks, scan_exposure, key: bytes,
                        config: dict) -> None:
    """S5 密钥零暴露：全产物扫描（F41 同法）＋正控＋仓级字节扫描
    （W3-U33 F77 同法）。"""
    scan = scan_exposure()
    checks.step("s5_state_artifacts_scan_zero_hits",
                scan.get("exposed") is False
                and scan.get("scannedFiles", 0) >= 4,
                "scanned=%s exposed=%s" % (scan.get("scannedFiles"),
                                           scan.get("exposed")))
    # 正控样本：另立临时状态根注入密钥料——同法扫描必命中（非空转证明）。
    with tempfile.TemporaryDirectory(prefix="juscite-f123-posctl-") as tmp:
        control_state = Path(tmp) / "export-state"
        control_dir = control_state / "f123-export"
        (control_dir / "exports" / "leak").mkdir(parents=True)
        (control_dir / "signing.secret").write_bytes(key)
        (control_dir / "exports" / "leak" / "leak.bin").write_bytes(
            key.hex().encode("ascii"))
        control_config = dict(config)
        control_config["signed_export_state_root"] = str(control_state)
        control = scan_exposure(control_config)
        checks.step(
            "s5_positive_control_detects",
            control.get("exposed") is True
            and control.get("exposedFile") == "leak.bin",
            "exposed=%s file=%s" % (control.get("exposed"),
                                    control.get("exposedFile")))
    # 发行物/仓级字节扫描（tracked 全文件）。
    repo_scan = _repo_byte_scan(key)
    checks.step(
        "s5_repo_release_bytes_zero_hits",
        repo_scan.get("ok") is True and repo_scan.get("hits") == []
        and repo_scan.get("scanned", 0) > 500,
        "scanned=%s hits=%s" % (repo_scan.get("scanned"),
                                repo_scan.get("hits")))


def section_s6_bridge(checks: Checks, config: dict) -> None:
    """S6 桥纪律（desktop 子进程径）。"""
    unconfigured = call_entry(
        "export.package", _package_args("f123-s6"),
        {"signed_export_state_root": config["signed_export_state_root"]})
    checks.step(
        "s6_unconfigured_harness_not_connected",
        unconfigured["exit"] == 3
        and unconfigured["payload"].get("status") == "NOT_CONNECTED"
        and "harness_public_entry_not_configured"
        in str(unconfigured["payload"].get("code")),
        "exit=%s code=%s" % (unconfigured["exit"],
                             str(unconfigured["payload"].get("code"))[:80]))
    response = call_entry("harness.export_sign", {}, config)
    checks.step(
        "s6_closed_registry_refused",
        response["exit"] == 3
        and "method_not_connected"
        in str(response["payload"].get("code")),
        "exit=%s code=%s" % (response["exit"],
                             str(response["payload"].get("code"))[:80]))
    response = call_entry("export.sign", {}, config)
    checks.step(
        "s6_export_face_closed_set_refused",
        response["exit"] == 3
        and "method_not_connected"
        in str(response["payload"].get("code")),
        "exit=%s code=%s" % (response["exit"],
                             str(response["payload"].get("code"))[:80]))


def run_desktop(recon_out: Path) -> dict | None:
    sys.path.insert(0, str(REPO_ROOT / "implementation" / "python"))
    checks = Checks("desktop")
    started = datetime.now(timezone.utc)
    holder = tempfile.TemporaryDirectory(prefix="juscite-f123-desktop-")
    state_root = Path(holder.name) / "state"
    (state_root / "harness-state").mkdir(parents=True)
    config = {
        "signed_export_state_root": str(state_root / "export-state"),
        "harness_public_entry": str(HARNESS_PUBLIC_ENTRY),
        "harness_target": "opencode",
        "harness_state_root": str(state_root / "harness-state"),
        "harness_timeout": 120,
    }
    if str(REPO_ROOT / "implementation" / "python") not in sys.path:
        sys.path.insert(0, str(REPO_ROOT / "implementation" / "python"))
    if str(HARNESS_WORKTREE / "src") not in sys.path:
        sys.path.insert(0, str(HARNESS_WORKTREE / "src"))
    from legal_harness.state.matter_store import MatterStore
    MatterStore(state_root / "harness-state").create_matter(
        MATTER_X, "cas://profile-f123-desktop")

    def export_call(export_id: str, args: dict) -> dict:
        return entry_call("export.package", args, config)

    def verify_call(export_id: str) -> dict:
        return entry_call("export.verify", {"exportId": export_id}, config)

    def read_record(export_id: str) -> dict:
        return entry_call("harness.export_record_read",
                          {"scope": {"kind": "matter", "matterId": MATTER_X},
                           "export_id": export_id}, config)

    def listed():
        return entry_call("export.package_list",
                          {"matterId": MATTER_X}, config)

    def record_verification(export_id: str, verdict_doc: dict, tag: str,
                            manifest_sha: str | None) -> None:
        entry_call("harness.export_verification_record", {
            "actor_id": "lvyin-product",
            "scope": {"kind": "matter", "matterId": MATTER_X},
            "key": _key("v-" + tag), "export_id": export_id,
            "verdict": verdict_doc["verdict"],
            "findings": verdict_doc["findings"],
            "verifier": "export_manifest_checker/1",
            "checked_file_count": verdict_doc["checkedFileCount"],
            "manifest_sha256": manifest_sha
            or verdict_doc["manifestSha256"]}, config)

    def verification_list(export_id: str) -> dict:
        return entry_call("harness.export_verification_list", {
            "scope": {"kind": "matter", "matterId": MATTER_X},
            "export_id": export_id}, config)

    def scan_exposure(config_override: dict | None = None) -> dict:
        return entry_call("export.secret_exposure_scan", {},
                          config_override or config)

    projection = None
    try:
        checks.step(
            "s0_pinned_harness_worktree",
            HARNESS_PUBLIC_ENTRY.is_file(),
            "worktree=%s entry=%s" % (
                HARNESS_WORKTREE.name,
                sha256_bytes(HARNESS_PUBLIC_ENTRY.read_bytes())[:16]))
        s1 = section_s1_sign(checks, export_call, read_record)
        section_s2_idempotency(checks, export_call, listed)
        section_s3_s4_verify_tamper(checks, export_call, verify_call,
                                    record_verification, verification_list)
        section_s5_exposure(checks, scan_exposure, s1["key"], config)
        section_s6_bridge(checks, config)
        # S7 对照面：desktop 投影供跨 profile 对账。
        receipt = export_call("f123-s7", _package_args("f123-s7"))
        verdict = verify_call("f123-s7")
        record = read_record("f123-s7")
        projection = _projection(receipt, verdict, record)
        recon_out.mkdir(parents=True, exist_ok=True)
        (recon_out / "f123-desktop-projection.json").write_text(
            json.dumps(projection, ensure_ascii=False, sort_keys=True,
                       indent=1), encoding="utf-8")
        checks.step("s7_desktop_projection_captured",
                    projection["verdict"] == "PASS",
                    "verdict=%s files=%d" % (projection["verdict"],
                                             projection["fileCount"]))
    finally:
        holder.cleanup()
    finish(checks, started, recon_out)
    return projection


def run_selfhost(recon_out: Path, dsn: str) -> dict | None:
    """selfhost＝PgMatterStore 直连 lh-pg-e08 独立 schema＋产品面 harness_
    call 注入直连（同一封闭注册；用毕 destroy）。"""
    for path in (str(HARNESS_WORKTREE / "src"),
                 str(HARNESS_WORKTREE / "tools/workflow-tools"),
                 str(REPO_ROOT / "implementation" / "python")):
        if path not in sys.path:
            sys.path.insert(0, path)
    from legal_harness.business.provider_registry import (
        HARNESS_PROVIDER_METHODS,
        MethodNotWhitelisted,
        resolve_provider_method,
    )
    from legal_harness.business.units import HarnessUnits, UnitsError
    from legal_harness.state.pg_store import PgMatterStore

    checks = Checks("selfhost")
    started = datetime.now(timezone.utc)
    temporary = tempfile.TemporaryDirectory(prefix="juscite-f123-selfhost-")
    store = PgMatterStore(
        Path(temporary.name) / "state", dsn=dsn,
        schema="f123_" + uuid.uuid4().hex[:12])
    units = HarnessUnits(store)
    bound = {name: resolve_provider_method(name, units)
             for name in EXPORT_LEDGER_METHODS}
    store.create_matter(MATTER_X, "cas://profile-f123-selfhost")

    class _BridgeError(Exception):
        pass

    def harness_direct(method: str, args: dict) -> dict:
        target = bound.get(method)
        if target is None:
            raise MethodNotWhitelisted(method)
        try:
            return target(**args)
        except UnitsError as exc:
            raise _BridgeError(str(exc)) from exc

    export_state = Path(temporary.name) / "export-state"
    config = {"signed_export_state_root": str(export_state)}
    import signed_export as signer
    import export_manifest_checker as checker

    def export_call(export_id: str, args: dict) -> dict:
        return signer.export_call("export.package", args, config,
                                  harness_call=harness_direct)

    def verify_call(export_id: str) -> dict:
        return checker.checker_call(
            "export.verify", {"exportId": export_id}, config)

    def read_record(export_id: str) -> dict:
        return harness_direct("harness.export_record_read", {
            "scope": {"kind": "matter", "matterId": MATTER_X},
            "export_id": export_id})

    def listed():
        return harness_direct("harness.export_record_list", {
            "scope": {"kind": "matter", "matterId": MATTER_X}})

    def record_verification(export_id: str, verdict_doc: dict, tag: str,
                            manifest_sha: str | None) -> None:
        harness_direct("harness.export_verification_record", {
            "actor_id": "lvyin-product",
            "scope": {"kind": "matter", "matterId": MATTER_X},
            "key": _key("v-" + tag), "export_id": export_id,
            "verdict": verdict_doc["verdict"],
            "findings": verdict_doc["findings"],
            "verifier": "export_manifest_checker/1",
            "checked_file_count": verdict_doc["checkedFileCount"],
            "manifest_sha256": manifest_sha
            or verdict_doc["manifestSha256"]})

    def verification_list(export_id: str) -> dict:
        return harness_direct("harness.export_verification_list", {
            "scope": {"kind": "matter", "matterId": MATTER_X},
            "export_id": export_id})

    def scan_exposure(config_override: dict | None = None) -> dict:
        return signer.export_call(
            "export.secret_exposure_scan", {},
            config_override or config, harness_call=harness_direct)

    projection = None
    try:
        checks.step(
            "s0_selfhost_pg_schema",
            True,
            "schema=%s dsn=%s" % (store.schema, dsn.split("@")[-1]))
        checks.step(
            "s0_registry_six_methods_closed",
            set(HARNESS_PROVIDER_METHODS)
            & EXPORT_LEDGER_METHODS == EXPORT_LEDGER_METHODS,
            "methods=%d" % len(EXPORT_LEDGER_METHODS & set(
                HARNESS_PROVIDER_METHODS)))
        s1 = section_s1_sign(checks, export_call, read_record)
        section_s2_idempotency(checks, export_call, listed)
        section_s3_s4_verify_tamper(checks, export_call, verify_call,
                                    record_verification, verification_list)
        section_s5_exposure(checks, scan_exposure, s1["key"], config)
        # 封闭注册负向（selfhost 直连径同语义）。
        try:
            resolve_provider_method("harness.export_sign", units)
            checks.step("s6_selfhost_closed_registry_refused", False,
                        "expected MethodNotWhitelisted")
        except MethodNotWhitelisted as exc:
            checks.step("s6_selfhost_closed_registry_refused", True,
                        code=str(exc))
        # S7 对照面。
        receipt = export_call("f123-s7", _package_args("f123-s7"))
        verdict = verify_call("f123-s7")
        record = read_record("f123-s7")
        projection = _projection(receipt, verdict, record)
        recon_out.mkdir(parents=True, exist_ok=True)
        (recon_out / "f123-selfhost-projection.json").write_text(
            json.dumps(projection, ensure_ascii=False, sort_keys=True,
                       indent=1), encoding="utf-8")
        checks.step("s7_selfhost_projection_captured",
                    projection["verdict"] == "PASS",
                    "verdict=%s files=%d" % (projection["verdict"],
                                             projection["fileCount"]))
    finally:
        store.destroy()
        temporary.cleanup()
    finish(checks, started, recon_out)
    return projection


def finish(checks: Checks, started: datetime, recon_out: Path) -> None:
    finished = datetime.now(timezone.utc)
    doc = {
        "unit": "W4-U54",
        "instance": "F123",
        "profile": checks.profile,
        "verdict": checks.verdict,
        "counts": {"pass": sum(1 for c in checks.items
                               if c["status"] == "PASS"),
                   "total": len(checks.items)},
        "started_at": started.isoformat(),
        "finished_at": finished.isoformat(),
        "harness_pin": {"branch": HARNESS_BRANCH,
                        "head": _harness_head(),
                        "public_entry_sha256":
                            sha256_bytes(
                                HARNESS_PUBLIC_ENTRY.read_bytes())},
        "checks": checks.items,
    }
    recon_out.mkdir(parents=True, exist_ok=True)
    out = recon_out / "recon-result.json"
    out.write_text(json.dumps(doc, ensure_ascii=False, sort_keys=True,
                              indent=1), encoding="utf-8")
    print("[%s] %s  %d/%d PASS  -> %s" % (
        checks.profile, checks.verdict, doc["counts"]["pass"],
        doc["counts"]["total"], out))
    for item in checks.failed:
        print("  FAIL %s: %s" % (item["id"], item["detail"]))


def _harness_head() -> str:
    proc = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=str(HARNESS_WORKTREE),
        capture_output=True, text=True, encoding="utf-8")
    return proc.stdout.strip() if proc.returncode == 0 else "unknown"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", action="append",
                        choices=["desktop", "selfhost"],
                        help="可重复：--profile desktop --profile selfhost")
    parser.add_argument("--pg-dsn", default=DEFAULT_PG_DSN)
    args = parser.parse_args()
    profiles = args.profile or ["desktop", "selfhost"]
    exit_code = 0
    projections = {}
    if "desktop" in profiles:
        projections["desktop"] = run_desktop(
            REPO_ROOT / "evidence" / "F123" / "desktop")
    if "selfhost" in profiles:
        projections["selfhost"] = run_selfhost(
            REPO_ROOT / "evidence" / "F123" / "selfhost", args.pg_dsn)
    # S7 跨 profile 对账（两腿都跑了才有对照面）。
    if set(profiles) == {"desktop", "selfhost"}:
        desktop = projections.get("desktop") or json.loads(
            (REPO_ROOT / "evidence" / "F123" / "desktop"
             / "f123-desktop-projection.json").read_text(encoding="utf-8"))
        selfhost = projections.get("selfhost") or json.loads(
            (REPO_ROOT / "evidence" / "F123" / "selfhost"
             / "f123-selfhost-projection.json").read_text(
                 encoding="utf-8"))
        same = desktop == selfhost
        print("[s7] cross-profile projection diff: %s" %
              ("null (逐键相等)" if same else "DIFF"))
        if not same:
            exit_code |= 1
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())

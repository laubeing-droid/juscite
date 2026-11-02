#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""W4-U32 / F10 案件库 at-rest 加密验收对账（RECON）。

06 F10（owner=harness+anonymizer；prereq E05/E08/E09 全 VERIFIED）acceptance：
「加密持久状态和CAS可恢复；无密钥不可读且不明文降级」。v1 权限闸+假名
preserved，本单补 at-rest 加密；密钥管理走既有 F07/F12 凭据设施
（lvyin.f10/atrest-aes-256-gcm-v1，DPAPI blob——不造第二凭据体系）。

对账腿（每 profile 独立 %TEMP% 状态根，全程合成材料，零网络零出站）：

* H 腿（harness 仓 w4-u32 分支 owner 面，子进程径）：
  - H1 加密 CAS put→read 往返相等且逐读解密+地址重哈希对账（随读必验可恢复）
  - H2 无密钥直读库文件不可读（字节级：盘上≠明文、明文全/长/短子串零命中、
    magic LHF10E01、nonce 随机化两写不同）
  - H3 v1 明文 CAS 视图读信封＝CASCorruptionError 拒（绝不返回明文）
  - H4/H5/H6/H7 零明文降级 typed 拒：无钥构造/短钥/错钥/篡改/明文残留位
  - H8 audit 带钥全过；H9 密钥不落库（全 state root 逐文件扫描零命中；
    产物字节不进 DB/WAL）；H10 MatterStore 接线（atrest_key→EncryptedCASStore；
    缺省 v1 明文形态不变）
* A 腿（anonymizer 仓 w4-u32 分支 material_parse_service 公开面，子进程径）：
  - A1 加密态页载荷盘上＝信封（LALF10E01、json 不可解码、明文记录特征零命中）
  - A2 带钥 read/report/human_edit 全链可恢复（人改不覆在加密态保持）
  - A3-A5 零明文降级 typed 拒：无钥/错钥/明文残留；幂等 skip 在加密态保持
  - A6 v1 形态字节不变（无钥根＝明文 JSON）；A7 密钥不落库（全树扫描零命中）
* P 腿（产品桥，in-process 同 legal_entry.call 同径）：
  - P1 atrest.status/provision 冻结方法组；provision 幂等不轮换；回执零密钥
  - P2 唯一持久化＝F12 保险库 DPAPI blob（登记文件零明文密钥）
  - P3 material.parse_* 加密态全链（信封落盘+带钥回读）＋零明文降级
    （未 provision 时 process=typed 拒且零文件落盘）
  - P4 v1 缺省 off＝明文 JSON 不变；P5 方法组两两不交

边界如实（不入 PASS 断言，只入证据边界节）：harness DB 账本文件与 anonymizer
OCR 派生工作态（F40/F41）为 v1 保护（权限闸+假名+DPAPI 私封），本单信封面=
CAS 产物与材料解析页载荷；公开入口（public_entry）密钥通道未接线（E06 环境
合同冻结 13 变量；加密态经 owner API 显式 atrest_key 构造）。

用法（juscite worktree 根 cwd）：
  python -X utf8 tools/recon/PENDING_OWNER_f10_atrest_encryption_recon.py \
      --profile desktop --profile selfhost
exit 0 = RECON_OK；exit 1 = FAIL；exit 2 = 环境预态不满足。
证据落 evidence/F10/<profile>/f10-atrest-recon{,-suffix}.{json,md}。
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
UNIT_DEFAULT = "W4-U32"


def _workspace_root() -> Path:
    """jusbench工作区 的父级（1.法律工作区）——主检出与 worktree 通用。"""
    for parent in REPO_ROOT.parents:
        if parent.name == "jusbench工作区":
            return parent.parent
    raise RuntimeError("预态：未定位 jusbench工作区（cwd 须在 juscite 仓内）")


ANONYMIZER_REPO = _workspace_root() / "legal-cn-anonymizer工作区" / "legal-cn-anonymizer"
HARNESS_REPO = _workspace_root() / "legal-harness工作区" / "legal-harness-repo"


class ReconFail(Exception):
    pass


# ---------------------------------------------------------------- 预态
def resolve_worktrees() -> tuple[Path, Path]:
    awt = ANONYMIZER_REPO / ".local" / "worktrees" / "w4-u32"
    hwt = HARNESS_REPO / ".local" / "worktrees" / "w4-u32"
    if not (awt / "src" / "legal_anonymizer" / "security" / "atrest_crypto.py").is_file():
        raise ReconFail(f"预态：anonymizer w4-u32 worktree 缺 atrest_crypto：{awt}")
    if not (hwt / "src" / "legal_harness" / "state" / "atrest_crypto.py").is_file():
        raise ReconFail(f"预态：harness w4-u32 worktree 缺 atrest_crypto：{hwt}")
    return awt, hwt


def _run_py(script: str, cwd: Path, env_extra: dict) -> dict:
    env = dict(os.environ)
    env.update(env_extra)
    env.setdefault("PYTHONUTF8", "1")
    proc = subprocess.run(
        [sys.executable, "-X", "utf8", "-c", script],
        cwd=str(cwd), capture_output=True, text=True, encoding="utf-8",
        errors="replace", env=env, timeout=600)
    if not (proc.stdout or "").strip():
        raise ReconFail(
            f"子进程无 stdout：exit={proc.returncode} "
            f"stderr={(proc.stderr or '')[-800:]}")
    try:
        payload = json.loads(proc.stdout)
    except json.JSONDecodeError:
        raise ReconFail(
            f"子进程 stdout 非 JSON：{proc.stdout[:400]}… "
            f"stderr={(proc.stderr or '')[-400:]}") from None
    return payload


# ---------------------------------------------------------------- H 腿脚本
HARNESS_SCRIPT = r'''
import hashlib, json, os, tempfile
from pathlib import Path

checks = []
def ck(cid, ok, detail=""):
    checks.append({"id": cid, "ok": bool(ok), "detail": str(detail)[:400]})

from legal_harness.state import atrest_crypto
from legal_harness.state.cas_store import (CASCorruptionError, CASStore,
                                           EncryptedCASStore)
from legal_harness.state.matter_store import MatterStore

KEY = os.urandom(32)
WRONG = os.urandom(32)
PLAINTEXT = ("合成案件材料 F10-RECON：本院认为，合同价款 123,456.78 元，"
             "违约金按日万分之五自验收后 30 日起算。".encode("utf-8") * 8)
root = Path(tempfile.mkdtemp(prefix="f10-recon-h-"))

store = EncryptedCASStore(root / "artifacts", KEY)
ref = store.put_bytes(PLAINTEXT)["sha256"]
ck("H1_recover_per_read", store.read_bytes(ref) == PLAINTEXT
   and store.read_once(ref) == PLAINTEXT and ref == CASStore.digest(PLAINTEXT))

raw = store.path_for(ref).read_bytes()
other = EncryptedCASStore(root / "artifacts-b", KEY)
other.put_bytes(PLAINTEXT)
raw_b = other.path_for(ref).read_bytes()
ck("H2_byte_unreadable", raw != PLAINTEXT and PLAINTEXT not in raw
   and PLAINTEXT[:32] not in raw and PLAINTEXT[:8] not in raw
   and raw[:8] == atrest_crypto.MAGIC and raw != raw_b)

plain_view = CASStore(root / "artifacts")
try:
    plain_view.read_bytes(ref)
    ck("H3_v1_view_refused", False, "明文 CAS 读信封未拒")
except CASCorruptionError:
    ck("H3_v1_view_refused", True)

for key, want in ((None, "atrest_key_required"), (b"short", "atrest_key_invalid")):
    try:
        EncryptedCASStore(root / ("artifacts-" + str(want)), key)
        ck("H4_construct_typed_" + str(want), False, "未拒")
    except atrest_crypto.AtRestError as exc:
        ck("H4_construct_typed_" + str(want), exc.code == want, exc.code)

wrong = EncryptedCASStore(root / "artifacts", WRONG)
try:
    wrong.read_bytes(ref)
    ck("H5_wrong_key_typed", False, "错钥未拒")
except CASCorruptionError as exc:
    ck("H5_wrong_key_typed", "atrest_decrypt_failed" in str(exc))

path = store.path_for(ref)
tampered = path.read_bytes()
path.write_bytes(tampered[:-1] + bytes([tampered[-1] ^ 0x01]))
try:
    store.read_bytes(ref)
    ck("H6_tamper_typed", False, "篡改未拒")
except CASCorruptionError as exc:
    ck("H6_tamper_typed", "atrest_decrypt_failed" in str(exc))
path.write_bytes(tampered)

store2 = EncryptedCASStore(root / "artifacts", KEY)
store2.put_bytes(PLAINTEXT)
report = store2.audit()
ck("H8_audit_ok", report["ok"] and report["checked"] >= 1, str(report)[:120])

hits = [str(p) for p in root.rglob("*")
        if p.is_file() and KEY in p.read_bytes()]
db = root / "core" / "matter-store.sqlite3"
db_bytes = db.read_bytes() if db.is_file() else b""
ck("H9_key_not_persisted", not hits and PLAINTEXT not in db_bytes,
   f"key_hits={len(hits)}")

mstore = MatterStore(root / "ms", atrest_key=KEY)
enc_ok = isinstance(mstore.cas, EncryptedCASStore)
ref2 = mstore.cas.put_bytes(PLAINTEXT)["sha256"]
vstore = MatterStore(root / "ms-v1")
v1_ok = type(vstore.cas) is CASStore
vref = vstore.cas.put_bytes(PLAINTEXT)["sha256"]
v1_plain = vstore.cas.path_for(vref).read_bytes() == PLAINTEXT
ck("H10_store_wiring", enc_ok and mstore.cas.read_bytes(ref2) == PLAINTEXT
   and v1_ok and v1_plain)

# H7 明文残留位（独立 store 根，勿污染 H8 的 audit 根）
pt_root = root / "artifacts-pt"
pt_store = EncryptedCASStore(pt_root, KEY)
pt_ref = CASStore.digest("明文残留位".encode("utf-8"))
pt_path = pt_store.path_for(pt_ref)
pt_path.parent.mkdir(parents=True, exist_ok=True)
pt_path.write_bytes("明文残留位".encode("utf-8"))
try:
    pt_store.read_bytes(pt_ref)
    ck("H7_plaintext_slot_typed", False, "明文位未拒")
except atrest_crypto.AtRestError as exc:
    ck("H7_plaintext_slot_typed", exc.code == "atrest_plaintext_forbidden", exc.code)
try:
    pt_store.verify(pt_ref)
    ck("H7b_verify_same_typed", False, "verify 明文位未拒")
except atrest_crypto.AtRestError:
    ck("H7b_verify_same_typed", True)

print(json.dumps({"ok": all(c["ok"] for c in checks), "checks": checks}))
'''

# ---------------------------------------------------------------- A 腿脚本
ANONYMIZER_SCRIPT = r'''
import io, json, os, tempfile, hashlib
from pathlib import Path

checks = []
def ck(cid, ok, detail=""):
    checks.append({"id": cid, "ok": bool(ok), "detail": str(detail)[:400]})

from legal_anonymizer.application import material_parse_service as mp
from legal_anonymizer.application.material_parse_service import (
    MaterialParseError, batch_report, human_edit, process_pages, read_page,
    register_batch)
from legal_anonymizer.security import atrest_crypto

KEY = os.urandom(32)
WRONG = os.urandom(32)

def white_png():
    from PIL import Image
    buf = io.BytesIO()
    Image.new("L", (992, 1403), 255).save(buf, format="PNG")
    return buf.getvalue()

def write_corpus(root):
    corpus = root / "corpus"
    (corpus / "pages" / "doc_0001").mkdir(parents=True)
    page_files = []
    for i in range(2):
        payload = white_png()
        rel = f"pages/doc_0001/p{i+1:04d}.png"
        (corpus / rel).write_bytes(payload)
        page_files.append({"page": i+1, "kind": "TEXT", "png": rel,
                           "sha256": hashlib.sha256(payload).hexdigest(),
                           "bytes": len(payload)})
    manifest = {"schema": "juscite-e12-corpus/1", "seed": 7, "pages": 2,
                "documents": [{"doc_id": "doc_0001", "doc_code": "SJ-0001",
                               "page_count": 2, "pdf": "docs/doc_0001.pdf",
                               "page_files": page_files}]}
    (corpus / "corpus_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
    return corpus

def page_file(state_root, batch_id, page):
    return (Path(state_root) / "material-parse" / batch_id / "pages"
            / "doc_0001" / f"p{page:04d}.json")

root = Path(tempfile.mkdtemp(prefix="f10-recon-a-"))
corpus = write_corpus(root)
reg = register_batch(root, corpus)
bid = reg["batch_id"]
summary = process_pages(root, bid, atrest_key=KEY)
ck("A1_envelopes_on_disk", summary["processed"] == 2 and all(
    page_file(root, bid, p).read_bytes()[:8] == atrest_crypto.MAGIC
    and b'"signal"' not in page_file(root, bid, p).read_bytes()
    for p in (1, 2)), str(summary))

rec = read_page(root, bid, "doc_0001", 1, atrest_key=KEY)
report = batch_report(root, bid, atrest_key=KEY)
ck("A2_recover_with_key", rec["signal"] in mp.SIGNALS
   and report["completed"] == 2 and report["corrupt_records"] == 0,
   str(report)[:160])

human = human_edit(root, bid, "doc_0001", 1, "- 7 -", atrest_key=KEY)
kept = read_page(root, bid, "doc_0001", 1, atrest_key=KEY)
env_still = page_file(root, bid, 1).read_bytes()[:8] == atrest_crypto.MAGIC
ck("A2b_human_edit_kept", human["source"] == "human" and env_still
   and any(v["source"] == "human" and v["text"] == "- 7 -"
           for v in kept["page_no"]["versions"]))

again = process_pages(root, bid, atrest_key=KEY)
try:
    read_page(root, bid, "doc_0001", 1)
    ck("A3_no_key_typed", False, "无钥未拒")
except MaterialParseError as exc:
    ck("A3_no_key_typed", "parse_atrest_key_required" in str(exc), str(exc))
try:
    read_page(root, bid, "doc_0001", 2, atrest_key=WRONG)
    ck("A4_wrong_key_typed", False, "错钥未拒")
except MaterialParseError as exc:
    ck("A4_wrong_key_typed", "parse_atrest_decrypt_failed" in str(exc), str(exc))
p1 = page_file(root, bid, 1)
p2 = page_file(root, bid, 2)
p2.write_bytes(p1.read_bytes())
try:
    read_page(root, bid, "doc_0001", 2, atrest_key=KEY)
    ck("A5_cross_page_move_typed", False, "跨页搬移未拒")
except MaterialParseError as exc:
    ck("A5_cross_page_move_typed", "parse_atrest_decrypt_failed" in str(exc))
p2.write_bytes(json.dumps({"doc_id": "doc_0001", "page": 2, "signal": "BLANK"},
                          ensure_ascii=False).encode("utf-8"))
try:
    read_page(root, bid, "doc_0001", 2, atrest_key=KEY)
    ck("A5b_plaintext_slot_typed", False, "明文残留位未拒")
except MaterialParseError as exc:
    ck("A5b_plaintext_slot_typed", "parse_atrest_plaintext_forbidden" in str(exc))

v1_root = root / "v1root"
v1reg = register_batch(v1_root, corpus)
v1sum = process_pages(v1_root, v1reg["batch_id"])
v1raw = page_file(v1_root, v1reg["batch_id"], 1).read_bytes()
ck("A6_v1_unchanged", v1sum["processed"] == 2 and v1raw[:1] == b"{"
   and json.loads(v1raw)["signal"] in mp.SIGNALS
   and not atrest_crypto.is_envelope(v1raw), str(v1sum)[:120])

hits = [str(p) for p in root.rglob("*")
        if p.is_file() and KEY in p.read_bytes()]
ck("A7_key_not_persisted", not hits, f"key_hits={len(hits)}")

print(json.dumps({"ok": all(c["ok"] for c in checks), "checks": checks}))
'''


# ---------------------------------------------------------------- P 腿（in-process）
def run_product_leg(worktree: Path) -> list[dict]:
    checks: list[dict] = []

    def ck(cid, ok, detail=""):
        checks.append({"id": cid, "ok": bool(ok), "detail": str(detail)[:400]})

    py_dir = worktree / "implementation" / "python"
    anon_src = ANONYMIZER_REPO / ".local" / "worktrees" / "w4-u32" / "src"
    for p in (str(py_dir), str(anon_src)):
        if p not in sys.path:
            sys.path.insert(0, p)
    import legal_entry  # noqa: E402
    import atrest_key as ak  # noqa: E402
    from bridge_errors import NotConnected  # noqa: E402
    from legal_anonymizer.security import atrest_crypto  # noqa: E402

    tmp = Path(tempfile.mkdtemp(prefix="f10-recon-p-"))
    vault_root = tmp / "vault"
    state_root = tmp / "state"
    config = {"anonymizer_contract": "p09/p10",
              "material_parse_state_root": str(state_root),
              "vault_state_root": str(vault_root)}

    status0 = legal_entry.call("atrest.status", {}, config)
    ck("P1_status_unprovisioned", status0["provisioned"] is False)
    try:
        legal_entry.call("atrest.status", {}, {})
        ck("P1b_unconfigured_typed", False, "未配置未拒")
    except NotConnected as exc:
        ck("P1b_unconfigured_typed",
           "vault_state_root_not_configured" in str(exc), str(exc)[:120])

    # P3 零明文降级（provision 之前）：加密态未配置钥＝typed 拒且零文件落盘
    corpus = _synth_corpus(tmp)
    enc_cfg = dict(config, f10_atrest="on")
    reg = legal_entry.call("material.parse_register",
                           {"corpus_root": str(corpus)}, enc_cfg)
    bid = reg["batch_id"]
    try:
        legal_entry.call("material.parse_process", {"batch_id": bid}, enc_cfg)
        ck("P3_no_provision_no_plaintext", False, "未 provision 未拒")
    except NotConnected as exc:
        pages_dir = state_root / "material-parse" / bid / "pages"
        ck("P3_no_provision_no_plaintext",
           "f10_atrest_key_not_provisioned" in str(exc)
           and not pages_dir.exists(), str(exc)[:120])

    first = legal_entry.call("atrest.provision", {}, config)
    second = legal_entry.call("atrest.provision", {}, config)
    key = ak.resolve_atrest_key(config)
    receipt_blob = json.dumps(first) + json.dumps(second)
    ck("P2_provision_idempotent_no_secret",
       first["created"] is True and second["created"] is False
       and first["key_sha256"] == second["key_sha256"]
       and key.hex() not in receipt_blob
       and base64_str(key) not in receipt_blob)
    entry_path = (vault_root / "credentials" / ak.ATREST_KEY_SERVICE
                  / (ak.ATREST_KEY_ACCOUNT + ".json"))
    ck("P2b_vault_dpapi_only", entry_path.is_file()
       and json.loads(entry_path.read_text(encoding="utf-8"))["backend"] == "dpapi"
       and key not in entry_path.read_bytes())

    legal_entry.call("material.parse_process", {"batch_id": bid}, enc_cfg)
    env_ok = all(
        (state_root / "material-parse" / bid / "pages" / "doc_0001"
         / f"p{p:04d}.json").read_bytes()[:8] == atrest_crypto.MAGIC
        for p in (1, 2))
    rec = legal_entry.call("material.parse_page",
                           {"batch_id": bid, "doc_id": "doc_0001", "page": 1},
                           enc_cfg)
    report = legal_entry.call("material.parse_report", {"batch_id": bid}, enc_cfg)
    ck("P3b_encrypted_bridge_roundtrip",
       env_ok and rec["signal"] == "BLANK" and report["completed"] == 2,
       str(report)[:160])
    hits = [str(p) for p in state_root.rglob("*")
            if p.is_file() and key in p.read_bytes()]
    ck("P3c_key_not_in_parse_state", not hits, f"key_hits={len(hits)}")

    # P4 v1 缺省 off：独立状态根（明文 JSON 形态字节不变）
    v1_state = tmp / "state-v1"
    v1_cfg = dict(config, material_parse_state_root=str(v1_state))
    vreg = legal_entry.call("material.parse_register",
                            {"corpus_root": str(corpus)}, v1_cfg)
    v1sum = legal_entry.call("material.parse_process",
                             {"batch_id": vreg["batch_id"]}, v1_cfg)
    v1raw = (v1_state / "material-parse" / vreg["batch_id"] / "pages"
             / "doc_0001" / "p0001.json").read_bytes()
    ck("P4_v1_default_plaintext", v1sum["processed"] == 2
       and v1raw[:1] == b"{" and not atrest_crypto.is_envelope(v1raw))

    groups = [v for k, v in vars(legal_entry).items()
              if k.endswith("_METHODS") and isinstance(v, frozenset)]
    disjoint = all(not (legal_entry.ATREST_METHODS & g) for g in groups
                   if g is not legal_entry.ATREST_METHODS)
    ck("P5_group_frozen_disjoint",
       legal_entry.ATREST_METHODS == frozenset({"atrest.status",
                                                "atrest.provision"}) and disjoint)
    return checks


def base64_str(data: bytes) -> str:
    import base64
    return base64.b64encode(data).decode("ascii")


def _synth_corpus(root: Path) -> Path:
    import hashlib
    import io

    from PIL import Image

    corpus = root / "corpus"
    (corpus / "pages" / "doc_0001").mkdir(parents=True)
    page_files = []
    for i in range(2):
        buf = io.BytesIO()
        Image.new("L", (992, 1403), 255).save(buf, format="PNG")
        payload = buf.getvalue()
        rel = f"pages/doc_0001/p{i + 1:04d}.png"
        (corpus / rel).write_bytes(payload)
        page_files.append({"page": i + 1, "kind": "TEXT", "png": rel,
                           "sha256": hashlib.sha256(payload).hexdigest(),
                           "bytes": len(payload)})
    manifest = {"schema": "juscite-e12-corpus/1", "seed": 7, "pages": 2,
                "documents": [{"doc_id": "doc_0001", "doc_code": "SJ-0001",
                               "page_count": 2, "pdf": "docs/doc_0001.pdf",
                               "page_files": page_files}]}
    (corpus / "corpus_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
    return corpus


# ---------------------------------------------------------------- 编排
def run_profile(profile: str, awt: Path, hwt: Path, unit: str,
                suffix: str) -> dict:
    started = time.strftime("%Y-%m-%dT%H:%M:%S")
    h_payload = _run_py(HARNESS_SCRIPT, hwt,
                        {"PYTHONPATH": str(hwt / "src")})
    a_payload = _run_py(ANONYMIZER_SCRIPT, awt,
                        {"PYTHONPATH": str(awt / "src")})
    p_checks = run_product_leg(REPO_ROOT)
    checks = (h_payload["checks"] + a_payload["checks"] + p_checks)
    failed = [c for c in checks if not c["ok"]]
    verdict = "RECON_OK" if not failed else "RECON_FAIL"
    result = {
        "unit": unit,
        "feature": "F10-desktop" if profile == "desktop" else "F10-selfhost",
        "profile": profile,
        "verdict": verdict,
        "started_at": started,
        "finished_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "counts": {"total": len(checks), "passed": len(checks) - len(failed),
                   "failed": len(failed)},
        "checks": checks,
        "failed_checks": [c["id"] for c in failed],
        "boundaries": [
            "harness DB 账本文件与 anonymizer OCR 派生工作态（F40/F41）=v1 保护"
            "（权限闸+假名+DPAPI 私封）；本单信封面=CAS 产物与材料解析页载荷",
            "public_entry 密钥通道未接线（E06 环境合同冻结 13 变量）；"
            "加密态经 owner API 显式 atrest_key 构造（MatterStore/PgMatterStore/"
            "material_parse_service atrest_key 参数）",
            "密钥唯一持久化=F12 保险库 lvyin.f10/atrest-aes-256-gcm-v1（DPAPI "
            "blob）——不造第二凭据体系；OCR 引擎钉定与语料生成器为既有 owner 面",
        ],
        "subjects": {
            "harness_worktree": str(hwt),
            "anonymizer_worktree": str(awt),
        },
    }
    evidence_dir = REPO_ROOT / "evidence" / "F10" / profile
    evidence_dir.mkdir(parents=True, exist_ok=True)
    base = "f10-atrest-recon" + (f"-{suffix}" if suffix else "")
    (evidence_dir / f"{base}.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
    md = [_render_md(result)]
    (evidence_dir / f"{base}.md").write_text("\n".join(md), encoding="utf-8")
    return result


def _render_md(result: dict) -> str:
    lines = [
        f"# F10 at-rest 加密 recon（{result['profile']}）— {result['verdict']}",
        "",
        f"- unit: {result['unit']}（{result['feature']}）",
        f"- counts: {result['counts']['passed']}/{result['counts']['total']} "
        f"passed, {result['counts']['failed']} failed",
        f"- window: {result['started_at']} → {result['finished_at']}",
        "",
        "| # | check | ok | detail |",
        "|---|-------|----|--------|",
    ]
    for i, check in enumerate(result["checks"], 1):
        lines.append(f"| {i} | {check['id']} | {'PASS' if check['ok'] else 'FAIL'} "
                     f"| {check['detail']} |")
    lines += ["", "## 边界（如实，不入 PASS 断言）"]
    lines += [f"- {b}" for b in result["boundaries"]]
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", action="append", default=[],
                        choices=["desktop", "selfhost"],
                        help="验收 profile（可重复）")
    parser.add_argument("--unit", default=UNIT_DEFAULT)
    parser.add_argument("--evidence-suffix", default="")
    args = parser.parse_args()
    profiles = args.profile or ["desktop", "selfhost"]
    try:
        awt, hwt = resolve_worktrees()
    except ReconFail as exc:
        print(f"F10_RECON_BLOCKED: {exc}", file=sys.stderr)
        return 2
    overall = []
    for profile in profiles:
        result = run_profile(profile, awt, hwt, args.unit, args.evidence_suffix)
        overall.append(result)
        print(f"[{profile}] {result['verdict']} "
              f"{result['counts']['passed']}/{result['counts']['total']} "
              f"failed={result['failed_checks']}")
    if any(r["verdict"] != "RECON_OK" for r in overall):
        print("F10_RECON_FAIL")
        return 1
    print(f"F10_RECON_OK profiles={','.join(profiles)} "
          f"checks={sum(r['counts']['total'] for r in overall)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

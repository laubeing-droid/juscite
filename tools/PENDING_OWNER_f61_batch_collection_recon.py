#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""F61 义务验收 recon（W3-U13）：微信 ID 批次采集负测先行。

F61（06 行）：微信生态采集（按 ID 分批收口）；验收向量＝按已授权 ID 批次
采集与出处保存；敏感材料过闸；不走 Cookie 逆向。05:234：微信以用户授权
导出或合规工具按 ID 分批，不偷 Cookie/全聊天。裁决#6：微信批次＝合成
先行（幂等回流/不改期限负测），授权后补联测；裁决#8-12 负测先行纪律：
禁编 URL/失败不造假——未授权 ID＝UNKNOWN 值 None 非 0。

落点＝产品材料面 wechat_collection.py＋legal_entry 冻结方法组
collection.*（P09,P10 消费径）：授权账（显式登记才可采）→批次采集
（text 件经 material.deidentify＝P10 既有 pipeline；pdf 附件件经
attachment.gate＝F38/F44 既有闸全链，真人审签名＋真钉定解释器 OCR）→
出处保存（导出件/采集产物双 sha256 绑定＋闸裁决引用）。敏感过闸消费
anonymizer attachment_gate/review 既有公开面（W2a-U15 分支），本单零
anonymizer 仓改动。

夹具全合成：e12_corpus_gen --attachments（seed 20261015 钉定，att_0001
正常 PII 页→授权附件件；att_0003 低置信页→具名拒不假成功）＋导出包
（合成聊天文本导出，PII 面供材料化工作）。

用法（juscite worktree w3-u13 仓根 cwd）：
  python -X utf8 tools/PENDING_OWNER_f61_batch_collection_recon.py \
      --profile desktop --profile selfhost
  [--attachments <dir>] [--exports <dir>] [--state-root-prefix <dir>]
  [--anonymizer-src <path>] [--interpreter <path>] [--skip-regen-check]
  [--keep-temp]

退出码：0＝RECON_OK（双 profile 硬门全过）；2＝RECON_FAIL；3＝环境缺失。
证据：docs/construction/evidence/F61/<profile>/（JSON＋MD）。
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
CORPUS_SEED = 20261015
DEFAULT_INTERPRETER = Path(os.environ.get(
    "JUSCITE_F40_BASELINE_INTERPRETER",
    r"C:\Users\being\AppData\Local\pdf2md-venv\Scripts\python.exe"))

PHONE = "13700005555"
ID_CARD = "110101199003078670"
CASE_NO = "(2026)合0101民初1234号"

# 合成导出包（固定内容＝确定性锚定；"微信聊天记录导出"为用户授权导出
# 形态的合成替身——裁决#6 真实通道授权后补联测，不编造其形状）。
SYNTH_CHAT_001 = "\n".join([
    "【聊天记录导出（合成样本）】",
    "导出对象：wxid_demo_001（授权导出）",
    f"2026-10-10 09:12 客户张三：我这个案子 {CASE_NO} 什么时候开庭？",
    f"2026-10-10 09:15 客户张三：我的电话 {PHONE}，身份证 {ID_CARD}，"
    "住址合成市合成区合成路1号",
    "2026-10-10 09:20 律师助理：已登记，等待法院传票送达。",
    "",
])
SYNTH_CHAT_002 = "\n".join([
    "【聊天记录导出（合成样本）】",
    "导出对象：wxid_demo_002（授权导出）",
    "2026-10-11 10:00 客户李四：材料已按清单补齐，谢谢。",
    "",
])
SYNTH_CHAT_GHOST = "【聊天记录导出（合成样本）】\n导出对象：wxid_ghost_999\n"

AUTHORIZED_IDS = ["wxid_demo_001", "wxid_demo_002",
                  "wxid_demo_101", "wxid_demo_102"]
UNAUTHORIZED_ID = "wxid_ghost_999"

# 导入闭集＋旁路关键字（负测先行纪律：结构性事实断言）
EXPECTED_IMPORTS = {"__future__", "hashlib", "json", "os", "datetime",
                    "pathlib"}
BANNED_IDENT_SUBSTRINGS = ("cookie", "session", "webdriver", "selenium",
                           "credential")
BANNED_LITERAL_SUBSTRINGS = ("http://", "https://")


def eprint(*a) -> None:
    print(*a, file=sys.stderr, flush=True)


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


class Checks:
    def __init__(self) -> None:
        self.rows: list[dict] = []
        self.failed = 0

    def check(self, cid: str, ok: bool, detail: str) -> bool:
        self.rows.append({"id": cid, "ok": bool(ok), "detail": detail[:600]})
        if not ok:
            self.failed += 1
            eprint(f"  [FAIL] {cid}: {detail[:300]}")
        else:
            eprint(f"  [ ok ] {cid}: {detail[:180]}")
        return bool(ok)

    @property
    def passed(self) -> int:
        return len(self.rows) - self.failed


def resolve_anonymizer_src(explicit: str | None) -> str | None:
    """anonymizer w2a-u15 源定位（attachment_gate_service 公开面所在分支）：
    显式参 > 环境变量 > 同波 worktree 相对推断（两布局通用向上扫描）。"""
    if explicit:
        return str(Path(explicit).resolve())
    env = os.environ.get("JUSCITE_ANONYMIZER_SRC")
    if env and (Path(env) / "legal_anonymizer" / "application"
                / "attachment_gate_service.py").is_file():
        return str(Path(env).resolve())
    root = next((_p for _p in REPO.resolve().parents
                 if (_p / "legal-cn-anonymizer工作区").is_dir()), None)
    if root is None and (REPO.parent / "legal-cn-anonymizer工作区").is_dir():
        root = REPO.parent
    if root is not None:
        guess = (root / "legal-cn-anonymizer工作区" / "legal-cn-anonymizer"
                 / ".local" / "worktrees" / "w2a-u15" / "src")
        if (guess / "legal_anonymizer" / "application"
                / "attachment_gate_service.py").is_file():
            return str(guess)
    return None


def load_bridge(anonymizer_src: str | None):
    sys.path.insert(0, str(REPO / "implementation" / "python"))
    if anonymizer_src:
        sys.path.insert(0, anonymizer_src)
    import legal_anonymizer
    from legal_entry import call as bridge_call
    return bridge_call, str(legal_anonymizer.__file__)


def ensure_attachments(target: Path) -> bool:
    """附件夹具＝生成器 --attachments 产物；缺失则同 seed 重建。"""
    if (target / "corpus_manifest.json").is_file():
        return True
    eprint(f"[GEN] 附件夹具缺失，按 seed={CORPUS_SEED} 重建 → {target}")
    proc = subprocess.run(
        [sys.executable, "-X", "utf8", str(REPO / "tools" / "e12_corpus_gen.py"),
         "--attachments", str(target), "--seed", str(CORPUS_SEED)],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        timeout=600)
    if proc.returncode != 0:
        eprint((proc.stdout or "")[-600:], (proc.stderr or "")[-600:])
        return False
    return (target / "corpus_manifest.json").is_file()


def ensure_exports(target: Path, attachments: Path) -> dict:
    """合成导出包（确定性重建）：文本导出件＋附件导出件（att_0001/0003
    只读字节复制改名，映射关系随锚定入证据）。"""
    target.mkdir(parents=True, exist_ok=True)
    manifest = json.loads((attachments / "corpus_manifest.json")
                          .read_text(encoding="utf-8"))
    docs = {d["doc_id"]: d for d in manifest["documents"]}
    files: dict[str, Path] = {}
    files["wx_chat_001.txt"] = _write_text(
        target / "wx_chat_001.txt", SYNTH_CHAT_001)
    files["wx_chat_002.txt"] = _write_text(
        target / "wx_chat_002.txt", SYNTH_CHAT_002)
    files["wx_ghost.txt"] = _write_text(
        target / "wx_ghost.txt", SYNTH_CHAT_GHOST)
    copies: dict[str, tuple[str, str]] = {}
    for eid, att in (("wxid_demo_101", "att_0001"),
                     ("wxid_demo_102", "att_0003")):
        src = attachments / docs[att]["pdf"]
        dst = target / f"{eid}.pdf"
        if not dst.is_file() or sha256_file(dst) != sha256_file(src):
            shutil.copyfile(src, dst)
        files[dst.name] = dst
        copies[eid] = (att, sha256_file(src))
    anchor = hashlib.sha256("|".join(
        f"{name}:{sha256_file(p)}" for name, p in sorted(files.items()))
        .encode("utf-8")).hexdigest()
    return {"files": files, "anchor": anchor, "copies": copies}


def _write_text(path: Path, content: str) -> Path:
    # newline="\n"：禁平台换行翻译（CRLF 化会漂移文本 sha 锚——U53 事故同源）
    path.write_text(content, encoding="utf-8", newline="\n")
    return path


def fixture_attachments_digest(attachments: Path) -> str:
    return (attachments / "attachments_digest.txt").read_text("ascii").split()[0]


def module_ast_audit() -> tuple[bool, str]:
    """C01：wechat_collection.py 导入闭集零网络模块＋字符串常量零 URL
    模式＋标识符零采集旁路关键字（禁编 URL/不走 Cookie 逆向＝结构性）。"""
    source = (REPO / "implementation" / "python" / "wechat_collection.py") \
        .read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(a.name.split(".")[0] for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0:
            imported.add((node.module or "").split(".")[0])
    if imported != EXPECTED_IMPORTS:
        return False, f"导入闭集漂移: {sorted(imported)}"
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            low = node.value.lower()
            for banned in BANNED_LITERAL_SUBSTRINGS:
                if banned in low:
                    return False, f"字符串常量含 {banned}"
        names = []
        if isinstance(node, ast.Name):
            names.append(node.id)
        elif isinstance(node, ast.Attribute):
            names.append(node.attr)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            names.append(node.name)
        elif isinstance(node, ast.arg):
            names.append(node.arg)
        for name in names:
            for kw in BANNED_IDENT_SUBSTRINGS:
                if kw in name.lower():
                    return False, f"标识符 {name} 含旁路关键字 {kw}"
    return True, (f"导入闭集 {sorted(imported)}；常量零 URL；"
                  "标识符零旁路关键字")


def scan_tree_blob(root: Path) -> str:
    chunks = []
    for p in sorted(root.rglob("*.json")):
        chunks.append(p.read_text(encoding="utf-8", errors="replace"))
    return "\n".join(chunks)


def assert_no_url(blob: str) -> list[str]:
    low = blob.lower()
    return [b for b in BANNED_LITERAL_SUBSTRINGS if b in low]


def run_profile(profile: str, args, manifest: dict, attachments: Path,
                exports: dict, bridge, anonymizer_file: str,
                evidence_common: dict) -> tuple[Checks, dict]:
    ck = Checks()
    state_root = Path(args.state_root_prefix) / f"juscite-f61-state-{profile}"
    collection_root = state_root / "collection"
    cfg = {"anonymizer_contract": "p09/p10",
           "collection_state_root": str(collection_root),
           "review_gate_state_root": str(state_root),
           "attachment_gate_state_root": str(state_root),
           "ocr_ports_state_root": str(state_root / "ocr"),
           "ocr_baseline_interpreter": str(args.interpreter)}
    # matter 名跨 profile 恒定（profile 隔离靠独立状态根；matter 进批次
    # input digest，后缀化会破坏跨 profile 投影确定性对照）
    matter = "m-f61-recon"
    files = exports["files"]
    evidence: dict = {"profile": profile, "state_root": str(collection_root),
                      "anonymizer_src": anonymizer_file,
                      "exports_anchor": exports["anchor"],
                      "attachments": str(attachments)}

    # ---- C01 模块 AST 面（负测先行：结构性事实）--------------------------
    ok, detail = module_ast_audit()
    ck.check("c01_module_ast_no_network_no_url_no_cookie", ok, detail)

    # ---- C02 桥 fail-closed 三路------------------------------------------
    try:
        bridge("collection.authorize",
               {"external_ids": ["w"], "authorized_by": "x"},
               {"anonymizer_contract": "p09/p10"})
        ck.check("c02_fail_closed_state_root", False, "未抛 NOT_CONNECTED")
    except Exception as exc:  # noqa: BLE001
        ck.check("c02_fail_closed_state_root",
                 "collection_state_root_not_configured" in str(exc),
                 f"state root 缺→{exc}")
    try:
        bridge("collection.authorize", {"external_ids": ["w"],
                                        "authorized_by": "x"}, {})
        ck.check("c02_fail_closed_contract", False, "未抛 NOT_CONNECTED")
    except Exception as exc:  # noqa: BLE001
        ck.check("c02_fail_closed_contract",
                 "anonymizer_p09_p10_not_configured" in str(exc),
                 f"合同缺→{exc}")
    try:
        bridge("collection.explode", {}, cfg)
        ck.check("c02_fail_closed_unknown_method", False, "未抛 NOT_CONNECTED")
    except Exception as exc:  # noqa: BLE001
        ck.check("c02_fail_closed_unknown_method",
                 "method_not_connected:collection.explode" in str(exc),
                 f"未知方法→{exc}")

    # ---- C03 授权账（显式登记才可采；幂等重放）---------------------------
    auth1 = bridge("collection.authorize",
                   {"external_ids": list(AUTHORIZED_IDS),
                    "authorized_by": f"recon-synth-{profile}"}, cfg)
    auth2 = bridge("collection.authorize",
                   {"external_ids": list(reversed(AUTHORIZED_IDS)),
                    "authorized_by": f"recon-synth-{profile}"}, cfg)
    ck.check("c03_authorize_idempotent_replay",
             auth2["idempotent_replay"] is True
             and auth2["authorization"]["auth_id"]
             == auth1["authorization"]["auth_id"]
             and auth1["authorization"]["scope"] == "local_authorized_export"
             and auth1["authorized_ids_total"] == len(AUTHORIZED_IDS),
             f"auth_id={auth1['authorization']['auth_id']} "
             f"total={auth1['authorized_ids_total']}")
    try:
        bridge("collection.authorize",
               {"external_ids": ["w"], "authorized_by": "x",
                "scope": "web_crawl"}, cfg)
        ck.check("c03_scope_closed", False, "闭集外 scope 未拒")
    except Exception as exc:  # noqa: BLE001
        ck.check("c03_scope_closed", "f61_scope_unknown:web_crawl" in str(exc),
                 f"scope 闭集外→{exc}")

    # ---- C04 导出材料包锚-------------------------------------------------
    ck.check("c04_exports_anchor",
             len(exports["files"]) == 5 and len(exports["anchor"]) == 64
             and all(v[1] for v in exports["copies"].values()),
             f"锚={exports['anchor'][:16]}… 复制映射="
             + ",".join(f"{k}←{v[0]}" for k, v in exports["copies"].items()))
    ck.check("c04_attachments_digest_anchor",
             evidence_common["attachments_digest"]
             == fixture_attachments_digest(attachments),
             f"附件夹具 digest={evidence_common['attachments_digest'][:16]}…")

    # ---- OCR 材料化（F40 既有面；附件件过闸的闸内证据）--------------------
    eprint("-- OCR（att_0001 + att_0003 各 1 页，钉定解释器）")
    reg = bridge("ocr.baseline_register",
                 {"corpus_root": str(attachments),
                  "interpreter": str(args.interpreter)}, cfg)
    run_id = reg["run_id"]
    bridge("ocr.baseline_run",
           {"run_id": run_id,
            "pages": [{"doc_id": "att_0001", "page": 1},
                      {"doc_id": "att_0003", "page": 1}],
            "interpreter": str(args.interpreter)}, cfg)
    evidence["ocr_source"] = {"run_id": run_id, "pages": 2}

    # ---- 批次一 b-collect（正向三态）--------------------------------------
    eprint("-- 批次一 b-collect：text＋附件 prepare＋未授权")
    b1_items = [
        {"external_id": "wxid_demo_001", "kind": "text",
         "export_path": str(files["wx_chat_001.txt"])},
        {"external_id": "wxid_demo_101", "kind": "pdf_attachment",
         "export_path": str(files["wxid_demo_101.pdf"]),
         "ocr_doc_id": "att_0001"},
        {"external_id": UNAUTHORIZED_ID, "kind": "text",
         "export_path": str(files["wx_ghost.txt"])},
    ]
    b1 = bridge("collection.batch",
                {"batch_id": "b-collect", "matter_id": matter,
                 "items": b1_items, "ocr_run_id": run_id}, cfg)
    evidence["batch1"] = b1
    by_id = {i["external_id"]: i for i in b1["items"]}

    text_item = by_id["wxid_demo_001"]
    ck.check("c05_text_collected_provenance",
             text_item["status"] == "COLLECTED"
             and text_item["export"]["sha256"]
             == sha256_file(files["wx_chat_001.txt"])
             and len(text_item["collected"]["sha256"]) == 64
             and text_item["collected"]["sha256"]
             != text_item["export"]["sha256"]
             and text_item["review_required"] is True,
             "COLLECTED＋双 sha 出处绑定＋review_required 如实")
    independent = bridge("material.deidentify",
                         {"text": SYNTH_CHAT_001}, cfg)
    ck.check(
        "c05_sanitized_sha_independent_match",
        text_item["collected"]["sha256"]
        == hashlib.sha256(
            independent["sanitized_text"].encode("utf-8")).hexdigest(),
        "独立 deidentify 对照：sanitized sha 相等（材料化同源同确定）")

    att_item = by_id["wxid_demo_101"]
    ck.check("c06_attachment_gate_required",
             att_item["status"] == "GATE_REQUIRED"
             and att_item["reason"] == "review_required_no_human_decision"
             and att_item["collected"] is None
             and att_item["review_required"] is True
             and (att_item.get("detections_count") or 0) >= 3,
             f"prepare 未决＝值 None＋检出 {att_item.get('detections_count')}")

    unk_item = by_id[UNAUTHORIZED_ID]
    ck.check("c07_unknown_none_not_zero",
             unk_item["status"] == "UNKNOWN_NOT_AUTHORIZED"
             and unk_item["export"] is None
             and unk_item["collected"] is None
             and unk_item["gate"] is None
             and unk_item["reason"] == "external_id_not_authorized",
             "未授权＝UNKNOWN 三值 None（非 0 非空对象）")
    ck.check("c07_unknown_counts_semantics",
             b1["counts"]["unknown_not_authorized"] == 1
             and b1["counts"]["total"] == 3,
             "聚合只计条目数；UNKNOWN 不冒采集计数")

    counts_sum = (b1["counts"]["collected"]
                  + b1["counts"]["authorized_gate"]
                  + b1["counts"]["gate_required"]
                  + b1["counts"]["gate_refused"]
                  + b1["counts"]["source_mismatch"]
                  + b1["counts"]["unknown_not_authorized"])
    ck.check("c08_counts_reconcile",
             b1["counts"]["total"] == counts_sum
             and b1["counts"]["collected"] == 1
             and b1["counts"]["gate_required"] == 1,
             f"counts 全景对账 {json.dumps(b1['counts'])}")

    # ---- 批次二 b-gate（人审全链 AUTHORIZED_GATE）--------------------------
    eprint("-- 批次二 b-gate：prepare→签名人审→全链授权")
    prep = bridge("attachment.gate",
                  {"matter_id": matter, "attachment_id": "wxid_demo_101",
                   "source_pdf": str(files["wxid_demo_101.pdf"]),
                   "ocr": {"run_id": run_id, "doc_id": "att_0001"}}, cfg)
    from legal_anonymizer.application.attachment_gate_service import (
        canonical_decision_body,
    )
    from legal_anonymizer.security.receipt_identity import ReceiptIdentity
    identity = ReceiptIdentity(state_root / "identity").ensure()
    body = canonical_decision_body(
        matter, "wxid_demo_101", run_id,
        prep.get("detections_digest") or "0" * 64,
        prep.get("proposed_boxes") or [])
    decision = {"reviewer": f"S-1-5-21-recon-{profile}", "role": "MATTER_LEAD",
                "ocr_run_id": run_id,
                "detections_digest": prep["detections_digest"],
                "boxes": body["boxes"], "signature": identity.sign(body)}
    b2 = bridge("collection.batch",
                {"batch_id": "b-gate", "matter_id": matter,
                 "items": [{"external_id": "wxid_demo_101",
                            "kind": "pdf_attachment",
                            "export_path": str(files["wxid_demo_101.pdf"]),
                            "ocr_doc_id": "att_0001",
                            "human_decision": decision}],
                 "ocr_run_id": run_id}, cfg)
    evidence["batch2"] = b2
    g_item = b2["items"][0]
    ck.check("c09_full_gate_authorized",
             g_item["status"] == "AUTHORIZED_GATE"
             and g_item["collected"]["kind"] == "authorized_attachment"
             and g_item["collected"]["sha256"]
             == g_item["gate"]["bound_sha256"]
             and g_item["review_required"] is False,
             f"全链授权 bound={str(g_item['gate']['bound_sha256'])[:16]}…"
             "＝采集产物出处")
    ck.check("c18_export_provenance_consistency",
             g_item["export"]["sha256"]
             == exports["copies"]["wxid_demo_101"][1],
             "导出件出处==原件 att_0001 sha（只读字节复制）")

    # ---- 批次三 b-refused（低置信具名拒不假成功）---------------------------
    eprint("-- 批次三 b-refused：低置信页")
    b3 = bridge("collection.batch",
                {"batch_id": "b-refused", "matter_id": matter,
                 "items": [{"external_id": "wxid_demo_102",
                            "kind": "pdf_attachment",
                            "export_path": str(files["wxid_demo_102.pdf"]),
                            "ocr_doc_id": "att_0003"}],
                 "ocr_run_id": run_id}, cfg)
    evidence["batch3"] = b3
    r_item = b3["items"][0]
    # att_0003 在本钉定解释器下＝页面 OCR 失败（F38 同夹具同拒因实测钉定；
    # 17 卡语义同族：低置信/失败不中断为假成功——OCR 证据即拒具名不假绿）
    ck.check("c10_ocr_evidence_refused",
             r_item["status"] == "GATE_REFUSED"
             and r_item["reason"] == "ocr_page_failed"
             and r_item["collected"] is None,
             f"OCR 证据即拒（{r_item['reason']}）值 None 不假成功"
             "＝F38 同夹具同拒因")

    # ---- 幂等回流（裁决#6）＋回读------------------------------------------
    b1_replay = bridge("collection.batch",
                       {"batch_id": "b-collect", "matter_id": matter,
                        "items": b1_items, "ocr_run_id": run_id}, cfg)
    ck.check("c11_idempotent_replay_same_receipt", b1_replay == b1,
             "同批次同输入重放逐键相等（不双记）")
    conflict = json.loads(json.dumps(
        {"batch_id": "b-collect", "matter_id": matter,
         "items": b1_items, "ocr_run_id": run_id}))
    conflict["items"][0]["export_path"] = str(files["wx_chat_002.txt"])
    try:
        bridge("collection.batch", conflict, cfg)
        ck.check("c11_conflict_refused", False, "异输入未拒")
    except Exception as exc:  # noqa: BLE001
        ck.check("c11_conflict_refused", "f61_batch_conflict" in str(exc),
                 f"异输入→{exc}")
    read = bridge("collection.batch_read", {"batch_id": "b-collect"}, cfg)
    ck.check("c12_batch_read_projection", read == b1, "回读投影==回执")
    try:
        bridge("collection.batch_read", {"batch_id": "nope"}, cfg)
        ck.check("c12_batch_read_not_found", False, "缺失批次未拒")
    except Exception as exc:  # noqa: BLE001
        ck.check("c12_batch_read_not_found", "f61_batch_not_found" in str(exc),
                 f"缺失批次→{exc}")

    # ---- 负测：url/cookie 旁路字段具名拒------------------------------------
    url_refused = cookie_refused = top_refused = None
    try:
        bridge("collection.batch",
               {"batch_id": "b-neg-url", "matter_id": matter,
                "items": [{"external_id": "wxid_demo_001", "kind": "text",
                           "export_path": str(files["wx_chat_002.txt"]),
                           "url": "https://weixin.example.invalid/x"}]},
               cfg)
    except Exception as exc:  # noqa: BLE001
        url_refused = "f61_field_forbidden:url" in str(exc)
    try:
        bridge("collection.batch",
               {"batch_id": "b-neg-cookie", "matter_id": matter,
                "items": [{"external_id": "wxid_demo_001", "kind": "text",
                           "export_path": str(files["wx_chat_002.txt"]),
                           "cookie": "SESSIONID=1"}]}, cfg)
    except Exception as exc:  # noqa: BLE001
        cookie_refused = "f61_field_forbidden:cookie" in str(exc)
    try:
        bridge("collection.batch",
               {"batch_id": "b-neg-top", "matter_id": matter,
                "weixin_url": "https://weixin.example.invalid",
                "items": [{"external_id": "wxid_demo_001", "kind": "text",
                           "export_path": str(files["wx_chat_002.txt"])}]},
               cfg)
    except Exception as exc:  # noqa: BLE001
        top_refused = "f61_field_forbidden:weixin_url" in str(exc)
    ck.check("c13_url_cookie_bypass_refused",
             url_refused is True and cookie_refused is True
             and top_refused is True,
             "url/cookie item 级＋顶层旁路字段全具名拒（无隐式采集通道）")

    # ---- 产物面零 URL＋投影红线--------------------------------------------
    collection_blob = scan_tree_blob(collection_root)
    receipt_blob = json.dumps(
        {"b1": b1, "b2": b2, "b3": b3}, ensure_ascii=False)
    ck.check("c14_artifacts_zero_url",
             not assert_no_url(collection_blob + receipt_blob)
             and not assert_no_url(scan_tree_blob(Path(args.state_root_prefix)
                                                  / f"juscite-f61-state-{profile}")),
             "授权账/批次账/回执/全状态根零 URL 字面量")
    surfaces = [PHONE, ID_CARD, CASE_NO, "张三", "att_0001", "att_0003",
                "export_path", "source_pdf", "proposed_boxes"]
    leaked = [s for s in surfaces if s in collection_blob]
    ck.check("c15_projection_redline_no_surfaces", not leaked,
             f"F61 账面零 PII/零原件名/零路径键/零建议坐标"
             f"（{len(collection_blob)} 字节扫描）")

    # ---- 授权闸先于出处校验（顺序语义）------------------------------------
    b4 = bridge("collection.batch",
                {"batch_id": "b-order", "matter_id": matter,
                 "items": [
                     {"external_id": UNAUTHORIZED_ID, "kind": "text",
                      "export_path": str(files["wx_ghost.txt"]),
                      "export_sha256": "0" * 64},
                     {"external_id": "wxid_demo_002", "kind": "text",
                      "export_path": str(files["wx_chat_002.txt"]),
                      "export_sha256": "0" * 64}]}, cfg)
    o_items = {i["external_id"]: i for i in b4["items"]}
    ck.check("c16_authorization_gate_precedes_source_check",
             o_items[UNAUTHORIZED_ID]["status"] == "UNKNOWN_NOT_AUTHORIZED"
             and o_items[UNAUTHORIZED_ID]["collected"] is None
             and o_items["wxid_demo_002"]["status"] == "SOURCE_MISMATCH"
             and o_items["wxid_demo_002"]["reason"]
             == "f61_export_sha_mismatch"
             and o_items["wxid_demo_002"]["collected"] is None,
             "未授权＋坏声明→UNKNOWN（授权闸先行）；授权＋坏声明→"
             "SOURCE_MISMATCH 值 None")

    return ck, evidence


def render_md(evidence: dict, checks: Checks, cross_rows: list) -> str:
    b1 = evidence.get("batch1", {})
    b2 = evidence.get("batch2", {})
    b3 = evidence.get("batch3", {})
    lines = [
        f"# F61 微信 ID 批次采集 recon 证据（{evidence.get('profile', '')}，"
        "W3-U13）",
        "",
        f"- anonymizer 面：`{evidence.get('anonymizer_src')}`；"
        f"导出包锚：`{str(evidence.get('exports_anchor'))[:16]}…`（全合成）",
        f"- 源 OCR run：`{evidence.get('ocr_source', {}).get('run_id')}"
        f"（{evidence.get('ocr_source', {}).get('pages')} 页，"
        "F40 钉定解释器）",
        "## 批次结果（按已授权 ID 批次采集＋出处保存）",
        f"- 批次一 b-collect counts＝{json.dumps(b1.get('counts'))}",
        f"- 附件件 b-gate 全链＝**{str((b2.get('items') or [{}])[0].get('status'))}**，"
        f"bound＝`{(str((((b2.get('items') or [{}])[0].get('collected') or {}).get('sha256')) or '')[:16])}…`",
        f"- 低置信件＝**{str((b3.get('items') or [{}])[0].get('status'))}**"
        f"（{str((b3.get('items') or [{}])[0].get('reason'))}）",
        "## 负测先行纪律",
        "- 未授权 ID＝UNKNOWN_NOT_AUTHORIZED，出处/采集/闸三值 None 非 0；",
        "- url/cookie 旁路字段 item 级＋顶层全具名拒；模块 AST 导入闭集零网络；",
        "- 产物面（授权账/批次账/回执）零 URL 字面量；不走 Cookie 逆向＝结构性。",
        "## 检查清单",
    ]
    lines += [f"- [{'x' if r['ok'] else ' '}] {r['id']}: {r['detail']}"
              for r in checks.rows]
    lines += [f"- [{'x' if r['ok'] else ' '}] {r['id']}: {r['detail']}"
              for r in cross_rows]
    passed = checks.passed + sum(1 for r in cross_rows if r["ok"])
    total = len(checks.rows) + len(cross_rows)
    lines += ["", f"**{passed}/{total} checks passed.**", ""]
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--profile", action="append", default=None,
                    help="验收 profile（可多次；默认 desktop+selfhost）")
    ap.add_argument("--attachments", type=Path,
                    default=Path(tempfile.gettempdir())
                    / "juscite-f61-attachments")
    ap.add_argument("--exports", type=Path,
                    default=Path(tempfile.gettempdir()) / "juscite-f61-exports")
    ap.add_argument("--state-root-prefix", type=Path,
                    default=Path(tempfile.gettempdir()) / "juscite-f61-root")
    ap.add_argument("--anonymizer-src", type=str, default=None)
    ap.add_argument("--interpreter", type=Path, default=DEFAULT_INTERPRETER)
    ap.add_argument("--skip-regen-check", action="store_true")
    ap.add_argument("--keep-temp", action="store_true")
    args = ap.parse_args()
    if not args.profile:
        args.profile = ["desktop", "selfhost"]

    started = time.time()
    eprint(f"== W3-U13 F61 recon profiles={args.profile}"
           f" attachments={args.attachments}")

    # -- 环境面 -------------------------------------------------------------
    if not ensure_attachments(args.attachments):
        eprint("[ENV] 附件夹具不可得")
        return 3
    manifest = json.loads((args.attachments / "corpus_manifest.json")
                          .read_text(encoding="utf-8"))
    if manifest.get("schema") != "juscite-f38-f44-attachments/1":
        eprint(f"[ENV] 夹具 schema 异常: {manifest.get('schema')}")
        return 3
    try:
        bridge, anonymizer_file = load_bridge(
            resolve_anonymizer_src(args.anonymizer_src))
    except Exception as exc:  # noqa: BLE001
        eprint(f"[ENV] 桥/anonymizer 面不可用: {type(exc).__name__}: {exc}")
        return 3
    if not args.interpreter.is_file():
        eprint(f"[ENV] 钉定解释器缺失: {args.interpreter}")
        return 3

    exports = ensure_exports(args.exports, args.attachments)
    evidence_common: dict = {
        "attachments_digest": fixture_attachments_digest(args.attachments),
        "exports_anchor": exports["anchor"],
        "export_copies": {k: {"source_doc": v[0], "source_sha256": v[1]}
                          for k, v in exports["copies"].items()},
        "anonymizer_src": anonymizer_file,
        "attachments": str(args.attachments),
        "interpreter": str(args.interpreter),
    }
    if not args.skip_regen_check:
        regen_dir = Path(tempfile.mkdtemp(prefix="juscite-f61-regen-"))
        proc = subprocess.run(
            [sys.executable, "-X", "utf8", str(REPO / "tools"
                                               / "e12_corpus_gen.py"),
             "--attachments", str(regen_dir), "--seed", str(CORPUS_SEED)],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=600)
        if proc.returncode == 0:
            evidence_common["regen_attachments_digest"] = \
                fixture_attachments_digest(regen_dir)
        else:
            evidence_common["regen_attachments_digest"] = None
        shutil.rmtree(regen_dir, ignore_errors=True)
    anchor_before = fixture_attachments_digest(args.attachments)

    all_checks: list[Checks] = []
    all_evidence: dict = {"schema": "juscite-f61-batch-collection-recon/1",
                          "started_at": now_iso(), **evidence_common}
    ok = True
    for profile in args.profile:
        eprint(f"==== profile {profile} ====")
        ck, evidence = run_profile(profile, args, manifest, args.attachments,
                                   exports, bridge, anonymizer_file,
                                   evidence_common)
        all_checks.append(ck)
        all_evidence[profile] = evidence
        ok = ok and ck.failed == 0

    # -- C17 语料锚不变（只读消费）＋C19 跨 profile 投影一致性----------------
    anchor_after = fixture_attachments_digest(args.attachments)
    cross_rows: list[dict] = [{
        "id": "c17_corpus_anchor_unchanged",
        "ok": anchor_before == anchor_after,
        "detail": f"附件夹具 digest 跑前后一致 {anchor_before[:16]}…",
    }]
    ok = ok and anchor_before == anchor_after

    def _strip_volatile(receipt: dict) -> dict:
        # 时变键（时间戳/授权账 digest——含各 profile 授权时刻）＋profile
        # 标识键（matter_id 带后缀）不参与确定性对照；其余（items 投影/
        # counts/input_digest）必须逐键相等。
        return {k: v for k, v in receipt.items()
                if k not in ("recorded_at", "authorization_digest",
                             "matter_id")}

    c19_ok = len(args.profile) >= 2
    if c19_ok:
        base = _strip_volatile(all_evidence[args.profile[0]]["batch1"])
        for other in args.profile[1:]:
            if _strip_volatile(all_evidence[other]["batch1"]) != base:
                c19_ok = False
                break
    cross_rows.append({
        "id": "c19_cross_profile_projection_equal",
        "ok": c19_ok,
        "detail": "跨 profile 批次投影剥时变键逐键相等"
                  "（材料化/检出的确定性面）" if c19_ok else
                  "跨 profile 批次投影漂移（确定性破约）",
    })
    ok = ok and c19_ok
    all_evidence.setdefault("checks", {})["cross"] = cross_rows

    all_evidence["finished_at"] = now_iso()
    all_evidence["duration_s"] = round(time.time() - started, 1)
    for idx, ck in enumerate(all_checks):
        all_evidence.setdefault("checks", {})[
            str(args.profile[idx])] = ck.rows

    # -- 证据落盘 ------------------------------------------------------------
    ev_dir = REPO / "docs" / "construction" / "evidence"
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    for profile in args.profile:
        idx = args.profile.index(profile)
        out_dir = ev_dir / "F61" / profile
        out_dir.mkdir(parents=True, exist_ok=True)
        payload = {k: v for k, v in all_evidence.items()
                   if k not in args.profile or k == profile}
        payload["this_profile"] = all_evidence[profile]
        (out_dir / f"f61-batch-collection-recon-{stamp}.json").write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8")
        (out_dir / f"f61-batch-collection-recon-{stamp}.md").write_text(
            render_md(all_evidence[profile], all_checks[idx], cross_rows),
            encoding="utf-8")

    total = sum(len(c.rows) for c in all_checks) + len(cross_rows)
    passed = sum(c.passed for c in all_checks) \
        + sum(1 for r in cross_rows if r["ok"])
    failed = total - passed
    for r in cross_rows:
        if not r["ok"]:
            eprint(f"  [FAIL] {r['id']}: {r['detail'][:300]}")
    eprint(f"== {passed}/{total} checks passed ({time.time() - started:.0f}s)")
    if failed:
        eprint(f"RECON_FAIL: {failed} failed")
        return 2
    eprint("RECON_OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

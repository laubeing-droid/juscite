#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""F38/F44 义务验收 recon（W2a-U15）：附件文件闸与脱敏硬红线。

F38（06:39）：附件文件闸 OCR→人审→像素烧入→残留复扫，绑定最终附件字节；
未通过一律不能外发。F44（06:45）：黑框下文本层/隐藏文本/元数据/图片残留
反例全部复扫拒发。17 卡实现序：只读原件→现有pipeline/解析→分子分母与
资格→人工范围决定→最终字节复扫→合格引用交消费；低置信/失败不中断为
假成功。

夹具＝W2a-U01 生成器扩展（tools/e12_corpus_gen.py --attachments，全合成
红线）：att_0001/att_0002 含 PII 扫描页（电话/身份证/住址/案号/人名金标
携像素盒）＋att_0003 低置信降质页＋F44 五反例（黑框文本层/隐藏文本/
Info+XMP 元数据/图像裁切区/alt）。产品径＝implementation/python/
legal_entry.py 桥（attachment.*/ocr.*/review.* 方法组）→anonymizer
attachment_gate_service 公开面（同进程，P09/P10 纪律）。

用法（juscite worktree w2a-u15 仓根 cwd）：
  python -X utf8 tools/PENDING_OWNER_f38_f44_attachment_gate_recon.py \
      --profile desktop --profile selfhost
  [--attachments <dir>] [--state-root-prefix <dir>] [--anonymizer-src <path>]
  [--interpreter <path>] [--keep-temp]

退出码：0＝RECON_OK（双 profile 硬门全过）；2＝RECON_FAIL；3＝环境缺失。
证据：docs/construction/evidence/F38/<profile>/＋F44/<profile>/（JSON＋MD，
同一跑批双义务目录）。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
TEMP = Path(os.environ.get("TEMP", "."))
DEFAULT_ATTACHMENTS = TEMP / "juscite-f38f44-attachments"
DEFAULT_INTERPRETER = Path(os.environ.get(
    "JUSCITE_F40_BASELINE_INTERPRETER",
    r"C:\Users\being\AppData\Local\pdf2md-venv\Scripts\python.exe"))
CORPUS_SEED = 20261015


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
    """anonymizer w2a-u15 源定位：显式参 > 环境变量 > 同波 worktree 相对
    推断 > None（回退已安装面——若缺 attachment_gate_service 在环境检报缺）。"""
    if explicit:
        return str(Path(explicit).resolve())
    env = os.environ.get("JUSCITE_ANONYMIZER_SRC")
    if env:
        return str(Path(env).resolve())
    guess = (REPO.parents[4] / "legal-cn-anonymizer工作区"
             / "legal-cn-anonymizer" / ".local" / "worktrees" / "w2a-u15"
             / "src")
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
    """夹具＝生成器 --attachments 产物；缺失则同 seed 重建（确定性合成）。"""
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


def fixture_anchor(root: Path, manifest: dict) -> str:
    parts = [sha256_file(root / "corpus_manifest.json")]
    for doc in manifest["documents"]:
        parts.append(doc["doc_id"] + ":" + sha256_file(root / doc["pdf"]))
        parts.append(doc["doc_id"] + ":png:" + doc["page_files"][0]["sha256"])
    for ce in manifest["counterexamples"]:
        parts.append(ce["file"] + ":" + ce["sha256"])
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()


def all_surfaces(manifest: dict) -> list[str]:
    out = []
    for doc in manifest["documents"]:
        out.append(doc["case_no"])
        for g in doc["gold_pii"]:
            out.append(g["surface"])
    return [s for s in out if s]


def blob_leaks_surfaces(blob: str, surfaces: list[str]) -> list[str]:
    return [s for s in surfaces if s in blob]


def run_profile(profile: str, args, manifest: dict, attachments: Path,
                bridge, anonymizer_file: str, evidence_common: dict) -> tuple[Checks, dict]:
    ck = Checks()
    state_root = Path(args.state_root_prefix) / f"juscite-f38f44-state-{profile}"
    state_root.mkdir(parents=True, exist_ok=True)
    cfg = {"anonymizer_contract": "p09/p10",
           "review_gate_state_root": str(state_root),
           "attachment_gate_state_root": str(state_root),
           "ocr_ports_state_root": str(state_root / "ocr"),
           "ocr_baseline_interpreter": str(args.interpreter)}
    surfaces = all_surfaces(manifest)
    docs = {d["doc_id"]: d for d in manifest["documents"]}
    evidence: dict = {"profile": profile, "docs": sorted(docs),
                      "state_root": str(state_root),
                      "anonymizer_src": evidence_common["anonymizer_src"],
                      "attachments": evidence_common["attachments"]}

    # ---- C0 源附件 OCR 材料化（现有 F40 基础线面，钉定解释器）----------
    eprint(f"-- C0 源 OCR（{len(docs)} 附件页）")
    reg = bridge("ocr.baseline_register",
                 {"corpus_root": str(attachments),
                  "interpreter": str(args.interpreter)}, cfg)
    run_id = reg["run_id"]
    pages = [{"doc_id": d, "page": 1} for d in sorted(docs)]
    t0 = time.time()
    bridge("ocr.baseline_run",
           {"run_id": run_id, "pages": pages,
            "interpreter": str(args.interpreter)}, cfg)
    eprint(f"   OCR 完成 {len(pages)} 页 用时 {time.time() - t0:.0f}s")
    evidence["ocr_source"] = {"run_id": run_id, "pages": len(pages)}

    def ocr_lines(doc_id: str):
        page = bridge("ocr.baseline_page",
                      {"run_id": run_id, "doc_id": doc_id, "page": 1}, cfg)
        return page

    def gate_call(matter: str, doc_id: str, decision=None, gold=None,
                  source_pdf: Path | None = None):
        req = {"matter_id": matter, "attachment_id": doc_id,
               "source_pdf": str(source_pdf or attachments / "docs" / f"{doc_id}.pdf"),
               "ocr": {"run_id": run_id, "doc_id": doc_id}}
        if decision is not None:
            req["human_decision"] = decision
        if gold is not None:
            req["gold"] = gold
        return bridge("attachment.gate", req, cfg)

    def make_decision(matter: str, doc_id: str, digest: str, boxes: list):
        from legal_anonymizer.application.attachment_gate_service import (
            canonical_decision_body,
        )
        from legal_anonymizer.security.receipt_identity import ReceiptIdentity
        identity = ReceiptIdentity(state_root / "identity").ensure()
        body = canonical_decision_body(matter, doc_id, run_id, digest, boxes)
        return {"reviewer": f"S-1-5-21-recon-{profile}", "role": "MATTER_LEAD",
                "ocr_run_id": run_id, "detections_digest": digest,
                "boxes": body["boxes"], "signature": identity.sign(body)}

    def propose_and_decide(matter: str, doc_id: str, extra_boxes=None,
                           drop_first: int = 0):
        """prepare（无决定→机器建议）→ 人审签字（建议盒∪金标盒）→ 决定。"""
        prep = gate_call(matter, doc_id, decision=None)
        # OCR 证据即拒（低置信/空页）时无机器建议：以空检出摘要构造决定，
        # 闸门仍在 OCR 段具名拒（c2b 正是要验这个不假成功路径）
        digest = prep.get("detections_digest") or "0" * 64
        boxes = [dict(b) for b in prep.get("proposed_boxes") or []]
        for g in docs[doc_id]["gold_pii"]:
            cand = {"page": 1, "box": [int(round(v)) for v in g["box"]]}
            if cand["box"] not in [b["box"] for b in boxes]:
                boxes.append(cand)
        for b in (extra_boxes or []):
            boxes.append({"page": 1, "box": b})
        if drop_first:
            # 丢机器建议盒（检出线盒）→ 制造「人审范围不盖机器检出」反例
            boxes = boxes[drop_first:]
        return make_decision(matter, doc_id, digest, boxes), prep

    # ---- C1 烧入链全过（F38 ①）------------------------------------------
    eprint("-- C1 烧入链全过 att_0001")
    matter_a = f"m-f38-{profile}-a"
    decision_a, prep_a = propose_and_decide(matter_a, "att_0001")
    gold_a = [{"surface": g["surface"], "class_id": g["class_id"]}
              for g in docs["att_0001"]["gold_pii"]]
    verdict_a = gate_call(matter_a, "att_0001", decision=decision_a, gold=gold_a)
    evidence["verdict_att_0001"] = verdict_a
    ck.check("c1_chain_authorized",
             verdict_a.get("verdict") == "AUTHORIZED",
             f"verdict={verdict_a.get('verdict')} reasons={verdict_a.get('reasons')}")
    ck.check("c1_prepare_machine_proposal",
             prep_a["reasons"] == ["review_required_no_human_decision"]
             and prep_a["detections_count"] >= 3
             and len(prep_a["proposed_boxes"]) >= 3,
             f"prepare 建议检出 {prep_a['detections_count']} 类 "
             f"{prep_a['detections_kinds']}（盒 {len(prep_a['proposed_boxes'])}）")
    ck.check("c1_verdict_bound_to_final_bytes",
             verdict_a.get("bound_sha256") == verdict_a.get("burn", {}).get("out_sha256")
             and verdict_a.get("rescan", {}).get("structural", {}).get("status") == "clean"
             and verdict_a.get("rescan", {}).get("ocr", {}).get("status") == "clean",
             f"bound={str(verdict_a.get('bound_sha256'))[:16]} 结构面 clean＋OCR 面 clean")
    auth_a = bridge("attachment.authorize",
                    {"matter_id": matter_a, "attachment_id": "att_0001"}, cfg)
    evidence["authorize_att_0001"] = auth_a
    ck.check("c1_authorized_egress_after_rescan",
             auth_a["decision"] == "AUTHORIZED"
             and auth_a["egress_authorized"] is True
             and auth_a["current_sha256"] == auth_a["bound_sha256"],
             "复扫通过→授权外发（绑定字节）")
    cov = verdict_a.get("coverage") or {}
    ck.check("c1_coverage_stamp_rides_along",
             cov.get("gate") == "REVIEW_REQUIRED"
             and cov.get("gold_total") == len(gold_a)
             and cov.get("matched_total") >= 3,
             f"分子分母随裁决（金标 {cov.get('gold_total')} 检出 "
             f"{cov.get('matched_total')} gate={cov.get('gate')}）")

    eprint("-- C1b 人审范围超机器底线 att_0002（人名规则盲区→金标盒人审盖）")
    matter_b = f"m-f38-{profile}-b"
    decision_b, _prep_b = propose_and_decide(matter_b, "att_0002")
    gold_b = [{"surface": g["surface"], "class_id": g["class_id"]}
              for g in docs["att_0002"]["gold_pii"]]
    verdict_b = gate_call(matter_b, "att_0002", decision=decision_b, gold=gold_b)
    evidence["verdict_att_0002"] = verdict_b
    per_class = {c["class_id"]: c for c in
                 (verdict_b.get("coverage") or {}).get("per_class", [])}
    person = per_class.get("PERSON", {"gold_count": 0, "matched_count": 0})
    auth_b = bridge("attachment.authorize",
                    {"matter_id": matter_b, "attachment_id": "att_0002"}, cfg)
    ck.check("c1b_human_scope_exceeds_machine_floor",
             verdict_b.get("verdict") == "AUTHORIZED"
             and person["gold_count"] == 1 and person["matched_count"] == 0
             and auth_b["decision"] == "AUTHORIZED",
             f"人名金标 1 规则检出 0（诚实缺口）→人审金标盒烧入→授权"
             f"（人工范围决定≥机器底线）")

    # ---- C2 未通过一律不能外发（F38 ②）----------------------------------
    eprint("-- C2 未通过一律不能外发")
    no_verdict = bridge("attachment.authorize",
                        {"matter_id": f"m-f38-{profile}-none",
                         "attachment_id": "att_0002"}, cfg)
    evidence["authorize_no_verdict"] = no_verdict
    ck.check("c2_unburned_refused",
             no_verdict["decision"] == "REFUSED"
             and no_verdict["reason"] == "no_verdict",
             "未烧入（无裁决）→拒 no_verdict")

    eprint("-- C2b 低置信/失败不假成功 att_0003（LOWCONF 降质页）")
    matter_low = f"m-f38-{profile}-low"
    decision_low, prep_low = propose_and_decide(matter_low, "att_0003")
    verdict_low = gate_call(matter_low, "att_0003", decision=decision_low)
    evidence["verdict_att_0003_lowconf"] = verdict_low
    low_reasons = verdict_low.get("reasons") or []
    ck.check("c2b_low_confidence_refused_named",
             verdict_low.get("verdict") == "REFUSED"
             and low_reasons in ([ "ocr_low_confidence" ], ["ocr_page_failed"]),
             f"降质附件页具名拒（{low_reasons}；低置信/失败不中断为假成功）")

    eprint("-- C2c 复扫后字节被改→裁决失效")
    burned = state_root / "attachments" / matter_a / "att_0001" / "burned.pdf"
    data = bytearray(burned.read_bytes())
    data[len(data) // 2] ^= 0xFF
    burned.write_bytes(bytes(data))
    tampered = bridge("attachment.authorize",
                      {"matter_id": matter_a, "attachment_id": "att_0001"}, cfg)
    evidence["authorize_tampered"] = tampered
    ck.check("c2c_bytes_changed_voids_verdict",
             tampered["decision"] == "REFUSED"
             and tampered["reason"] == "bytes_changed_since_verdict"
             and tampered.get("current_sha256") != tampered.get("bound_sha256"),
             "复扫后字节被改→拒 bytes_changed_since_verdict（字节变即裁决失效）")

    eprint("-- C2d 人审范围不盖机器检出→拒")
    matter_miss = f"m-f38-{profile}-miss"
    decision_miss, _prep = propose_and_decide(matter_miss, "att_0002",
                                              drop_first=1)
    verdict_miss = gate_call(matter_miss, "att_0002", decision=decision_miss)
    evidence["verdict_decision_miss"] = verdict_miss
    ck.check("c2d_decision_not_covering_detections",
             verdict_miss.get("verdict") == "REFUSED"
             and verdict_miss.get("reasons") == ["decision_does_not_cover_detections"]
             and verdict_miss.get("uncovered_detection_count", 0) >= 1,
             f"缺盖检出 {verdict_miss.get('uncovered_detection_count')} 条→具名拒")

    # ---- C3 F44 四反例全部复扫拒发 --------------------------------------
    eprint("-- C3 F44 反例复扫")
    ce_results = {}
    for ce in manifest["counterexamples"]:
        rep = bridge("attachment.scan",
                     {"pdf_path": str(attachments / ce["file"])}, cfg)
        ce_results[ce["file"]] = rep
        name = ce["file"].split("/")[-1]
        expected = ce["f44_class"]
        ck.check(f"c3_{name}",
                 rep["status"] == "rejected"
                 and all(cls in rep["reasons"] for cls in expected),
                 f"{name} → {rep['reasons']}（期望含 {expected}）")
    evidence["counterexamples"] = {
        k: {"status": v["status"], "reasons": v["reasons"]}
        for k, v in ce_results.items()}
    classes_hit = {cls for rep in ce_results.values() for cls in rep["reasons"]}
    ck.check("c3_four_f44_classes_all_named",
             {"text_layer_present", "text_layer_pii",
              "hidden_text_render_mode", "metadata_pii", "xmp_pii",
              "image_clip_residual", "residual_string_pii"} <= classes_hit,
             f"四类（黑框/隐藏文本/元数据/图片残留·裁切区+alt）全具名："
             f"{sorted(classes_hit)}")

    # ---- C4 三类永不回填＋surface 零回传 --------------------------------
    eprint("-- C4 三类永不回填＋零 surface")
    nb_kinds = {tuple(verdict_a.get("never_backfill_kinds") or []),
                tuple(auth_a.get("never_backfill_kinds") or []),
                tuple(no_verdict.get("never_backfill_kinds") or [])}
    ck.check("c4_never_backfill_kinds_riding",
             nb_kinds == {("id_card", "phone", "personal_address")},
             "三类永不回填 kinds 随裁决/授权/拒发携带（E11 纪律沿用）")
    blobs = json.dumps([verdict_a, auth_a, no_verdict, verdict_low,
                        verdict_miss, prep_a,
                        list(ce_results.values())], ensure_ascii=False)
    leaks = blob_leaks_surfaces(blobs, surfaces)
    ck.check("c4_no_surface_echo_anywhere",
             not leaks,
             "全部响应零 surface 回传（金标值不出 anonymizer 面）"
             + (f" leaked={leaks[:3]}" if leaks else ""))

    # ---- C5 原件只读＋映射不出域 ----------------------------------------
    eprint("-- C5 原件只读/映射不出域")
    doc_shas = {d: sha256_file(attachments / docs[d]["pdf"])
                for d in docs}
    manifest_ok = all(
        doc_shas[d] == docs[d]["pdf_sha256"] for d in docs)
    ck.check("c5_source_readonly",
             manifest_ok,
             "全链跑完后源附件字节与清单钉定一致（原件只读）")
    ck.check("c5_no_path_or_mapping_in_responses",
             str(attachments) not in blobs
             and "originalPath" not in blobs and "Vault" not in blobs,
             "响应无原件路径/身份映射字段（红线投影面）")
    try:
        bridge("material.rehydrate", {"text": "合成"}, cfg)
        rehydrate_blocked = False
    except Exception as exc:  # noqa: BLE001
        rehydrate_blocked = "method_not_connected" in str(exc)
    ck.check("c5_no_standalone_rehydrate",
             rehydrate_blocked,
             "material.rehydrate 结构性不存在（映射不出 owner）")

    # ---- C6 NER 未 qualified 不自动合格 ---------------------------------
    eprint("-- C6 资格事实与人审分开")
    qual = bridge("review.qualification", {}, cfg)
    evidence["qualification"] = {
        "gate": qual["gate"]["status"], "reasons": qual["gate"]["reasons"]}
    bad_sig = dict(decision_a)
    bad_sig["signature"] = {"alg": "ed25519", "sig": "00" * 64, "key_id": "k"}
    matter_badsig = f"m-f38-{profile}-badsig"
    verdict_badsig = gate_call(matter_badsig, "att_0002",
                               decision=bad_sig)
    evidence["verdict_badsig"] = {
        "reasons": verdict_badsig.get("reasons")}
    ck.check("c6_review_required_semantics",
             qual["gate"]["status"] == "REVIEW_REQUIRED"
             and verdict_a["qualification"]["status"] == "REVIEW_REQUIRED"
             and verdict_a["qualification"]["manifest_qualified"] is False,
             "NER manifest 未 qualified：资格事实入裁决不被人审改写（⑥）")
    ck.check("c6_bad_signature_refused",
             verdict_badsig.get("reasons") == ["decision_signature_invalid"],
             "伪签名决定→具名拒（授权只经真人审签字）")

    # ---- C7 语料只读锚＋确定性 ------------------------------------------
    eprint("-- C7 只读锚/确定性")
    anchor_after = fixture_anchor(attachments, manifest)
    ck.check("c7_fixture_readonly_anchor",
             anchor_after == evidence_common["anchor_before"],
             "夹具锚前后一致（只读）")
    verdict_a2 = gate_call(matter_a, "att_0001", decision=decision_a,
                           gold=gold_a)
    ck.check("c7_gate_two_runs_same_burned_bytes",
             verdict_a2.get("verdict") == "AUTHORIZED"
             and verdict_a2.get("bound_sha256") == verdict_a.get("bound_sha256"),
             f"两跑烧入同字节 bound={str(verdict_a.get('bound_sha256'))[:16]}")
    evidence["determinism"] = {
        "run1_bound": verdict_a.get("bound_sha256"),
        "run2_bound": verdict_a2.get("bound_sha256")}
    ck.check("c7_fixture_regeneration_deterministic",
             evidence_common.get("regen_digest") == evidence_common["digest"],
             f"夹具重建同摘要 {str(evidence_common.get('regen_digest'))[:16]}")
    return ck, evidence


def render_md(ev: dict, ck: Checks) -> str:
    ces = ev.get("counterexamples", {})
    v1 = ev.get("verdict_att_0001", {})
    lines = [
        f"# F38/F44 附件文件闸与脱敏硬红线 recon 证据（{ev['profile']}，W2a-U15）",
        "",
        f"- anonymizer 面：`{ev.get('anonymizer_src')}`；夹具（全合成）："
        f"`{ev.get('attachments')}`",
        f"- 源 OCR run：`{ev.get('ocr_source', {}).get('run_id')}`"
        f"（{ev.get('ocr_source', {}).get('pages')} 页，F40 钉定解释器）",
        "## C1 烧入链全过（F38 ①）",
        f"- att_0001 裁决＝**{v1.get('verdict')}**；"
        f"bound_sha256=`{str(v1.get('bound_sha256'))[:16]}…`；"
        f"结构面={v1.get('rescan', {}).get('structural', {}).get('status')}"
        f"＋OCR 面={v1.get('rescan', {}).get('ocr', {}).get('status')}",
        f"- 机器建议检出 {ev.get('verdict_att_0001', {}).get('detections', {}).get('count')}"
        f" 条（prepare 面）→人审签字（建议盒∪金标盒）→烧入→复扫→授权。",
        "## C2 未通过一律不能外发（F38 ②）",
        f"- 未烧入={ev.get('authorize_no_verdict', {}).get('reason')}"
        f"；低置信={ev.get('verdict_att_0003_lowconf', {}).get('reasons')}"
        f"；字节被改={ev.get('authorize_tampered', {}).get('reason')}"
        f"；范围缺盖={ev.get('verdict_decision_miss', {}).get('reasons')}",
        "## C3 F44 四反例全部复扫拒发",
    ]
    lines += [f"- {k.split('/')[-1]} → {v['reasons']}"
              for k, v in ces.items()]
    lines += [
        "## C4/C5/C6 纪律面",
        f"- 三类永不回填 kinds 携带；零 surface 回传；原件只读；"
        f"无独立回填面；资格 REVIEW_REQUIRED（人审不清写）；伪签名拒。",
        "## 检查清单",
    ]
    lines += [f"- [{'x' if r['ok'] else ' '}] {r['id']}: {r['detail']}"
              for r in ck.rows]
    lines += ["", f"**{ck.passed}/{len(ck.rows)} checks passed.**", ""]
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--profile", action="append", required=True,
                    choices=["desktop", "selfhost"])
    ap.add_argument("--attachments", type=Path, default=DEFAULT_ATTACHMENTS)
    ap.add_argument("--state-root-prefix", type=Path, default=TEMP)
    ap.add_argument("--anonymizer-src", default=None)
    ap.add_argument("--interpreter", type=Path, default=DEFAULT_INTERPRETER)
    ap.add_argument("--skip-regen-check", action="store_true",
                    help="跳过夹具重建确定性检查（省时）")
    args = ap.parse_args()

    started = time.time()
    eprint(f"== W2a-U15 F38/F44 recon profiles={args.profile}"
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

    evidence_common: dict = {
        "anchor_before": fixture_anchor(args.attachments, manifest),
        "digest": (args.attachments / "attachments_digest.txt")
        .read_text(encoding="ascii").split()[0],
        "anonymizer_src": anonymizer_file,
        "attachments": str(args.attachments),
    }
    if not args.skip_regen_check:
        regen_dir = Path(tempfile.mkdtemp(prefix="juscite-f38f44-regen-"))
        proc = subprocess.run(
            [sys.executable, "-X", "utf8", str(REPO / "tools" / "e12_corpus_gen.py"),
             "--attachments", str(regen_dir), "--seed", str(CORPUS_SEED)],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=600)
        if proc.returncode == 0:
            evidence_common["regen_digest"] = (
                regen_dir / "attachments_digest.txt").read_text("ascii").split()[0]
        else:
            evidence_common["regen_digest"] = None
        subprocess.run(["cmd", "/c", "rmdir", "/s", "/q", str(regen_dir)],
                       capture_output=True)

    all_checks: list[Checks] = []
    all_evidence: dict = {"schema": "juscite-f38-f44-attachment-gate-recon/1",
                          "started_at": now_iso(), **evidence_common}
    ok = True
    for profile in args.profile:
        eprint(f"==== profile {profile} ====")
        ck, evidence = run_profile(profile, args, manifest,
                                   args.attachments, bridge, anonymizer_file,
                                   evidence_common)
        all_checks.append(ck)
        all_evidence[profile] = evidence
        ok = ok and ck.failed == 0

    all_evidence["finished_at"] = now_iso()
    all_evidence["duration_s"] = round(time.time() - started, 1)
    for ck in all_checks:
        all_evidence.setdefault("checks", {})[
            str(len(all_evidence["checks"]))] = ck.rows

    # -- 证据落盘 ------------------------------------------------------------
    ev_dir = REPO / "docs" / "construction" / "evidence"
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    for profile in args.profile:
        idx = args.profile.index(profile)
        for ob in ("F38", "F44"):
            out_dir = ev_dir / ob / profile
            out_dir.mkdir(parents=True, exist_ok=True)
            payload = {k: v for k, v in all_evidence.items()
                       if k not in args.profile or k == profile}
            payload["this_profile"] = all_evidence[profile]
            (out_dir / f"f38f44-attachment-gate-recon-{stamp}.json").write_text(
                json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8")
            (out_dir / f"f38f44-attachment-gate-recon-{stamp}.md").write_text(
                render_md(all_evidence[profile], all_checks[idx]),
                encoding="utf-8")

    total = sum(len(c.rows) for c in all_checks)
    passed = sum(c.passed for c in all_checks)
    failed = total - passed
    eprint(f"== {passed}/{total} checks passed ({time.time() - started:.0f}s)")
    if failed:
        eprint(f"RECON_FAIL: {failed} failed")
        return 2
    eprint("RECON_OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

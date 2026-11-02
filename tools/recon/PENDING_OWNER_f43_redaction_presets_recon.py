#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""F43 义务验收 recon（W4-U36）：脱敏策略预设三套（对外发送/内部分析/公开发布）。

06:F43（owner=anonymizer，B4；v1 先做内部分析单策略+假名映射，本单补三预
设）验收向量「三策略作用于不同出域 scope；共享假名不串案；策略变化重审」。
17 卡 target＝Anonymizer pipeline/cli 及原 owner 公开面（P09/P10）。落
W2a-U15/E11/F37 既有公开面扩展不建第二权威：闸链＝attachment_gate_service
（gate/authorize opt-in 参数），假名权威＝mapping.Vault（每案共享库）。

产品径＝implementation/python/legal_entry.py 桥（redaction.*＋attachment.*
方法组）→anonymizer 公开面（同进程，P09/P10 纪律）。夹具＝W2a-U01 生成器
--attachments 产物（全合成红线，seed 20261015，与 F38/F44 验收同源）。

用法（juscite worktree w4-u36 仓根 cwd）：
  python -X utf8 tools/recon/PENDING_OWNER_f43_redaction_presets_recon.py \
      --profile desktop --profile selfhost
  [--attachments <dir>] [--state-root-prefix <dir>] [--anonymizer-src <path>]
  [--interpreter <path>] [--keep-temp]

退出码：0＝RECON_OK（双 profile 硬门全过）；2＝RECON_FAIL；3＝环境缺失。
证据：evidence/F43/<profile>/f43-presets-recon.{json,md}。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
TEMP = Path(os.environ.get("TEMP", "."))
DEFAULT_ATTACHMENTS = TEMP / "juscite-f38f44-attachments"
DEFAULT_INTERPRETER = Path(os.environ.get(
    "JUSCITE_F40_BASELINE_INTERPRETER",
    r"C:\Users\being\AppData\Local\pdf2md-venv\Scripts\python.exe"))
CORPUS_SEED = 20261015
PRESETS = ("external_send", "internal_analysis", "public_release")


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


def canonical(obj) -> str:
    return json.dumps(obj, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"))


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
    """anonymizer w4-u36 源定位：显式参 > 环境变量 > 同波 worktree 相对
    推断 > None（回退已安装面——若缺 redaction_presets_service 在环境检报
    缺）。w4-u36 分支＝W4 链头（w4-u32）＋W2a-U15 附件闸面（45d8f12 merge）
    ＋本单 F43 面。"""
    if explicit:
        return str(Path(explicit).resolve())
    env = os.environ.get("JUSCITE_ANONYMIZER_SRC")
    if env and (Path(env) / "legal_anonymizer" / "application"
                / "redaction_presets_service.py").is_file():
        return str(Path(env).resolve())
    root = next((_p for _p in REPO.resolve().parents
                 if (_p / "legal-cn-anonymizer工作区").is_dir()), None)
    if root is not None:
        guess = (root / "legal-cn-anonymizer工作区" / "legal-cn-anonymizer"
                 / ".local" / "worktrees" / "w4-u36" / "src")
        if (guess / "legal_anonymizer" / "application"
                / "redaction_presets_service.py").is_file():
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


def write_evidence(profile: str, payload: dict, md: str) -> list[Path]:
    out_dir = REPO / "evidence" / "F43" / profile
    out_dir.mkdir(parents=True, exist_ok=True)
    jpath = out_dir / "f43-presets-recon.json"
    mpath = out_dir / "f43-presets-recon.md"
    jpath.write_text(json.dumps(payload, ensure_ascii=False, indent=1),
                     encoding="utf-8")
    mpath.write_text(md, encoding="utf-8")
    return [jpath, mpath]


def run_profile(profile: str, args, manifest: dict, attachments: Path,
                bridge, anonymizer_file: str) -> tuple[Checks, dict]:
    ck = Checks()
    state_root = Path(args.state_root_prefix) / f"juscite-f43-state-{profile}"
    state_root.mkdir(parents=True, exist_ok=True)
    cfg = {"anonymizer_contract": "p09/p10",
           "review_gate_state_root": str(state_root),
           "attachment_gate_state_root": str(state_root),
           "ocr_ports_state_root": str(state_root / "ocr"),
           "ocr_baseline_interpreter": str(args.interpreter)}
    docs = {d["doc_id"]: d for d in manifest["documents"]}
    evidence: dict = {"profile": profile, "docs": sorted(docs),
                      "state_root": str(state_root),
                      "anonymizer_src": anonymizer_file,
                      "attachments": str(attachments),
                      "interpreter": str(args.interpreter)}

    # ---- C0 源附件 OCR 材料化（现有 F40 基础线面，钉定解释器）----------
    eprint(f"-- C0 源 OCR（att_0001/att_0002）")
    reg = bridge("ocr.baseline_register",
                 {"corpus_root": str(attachments),
                  "interpreter": str(args.interpreter)}, cfg)
    run_id = reg["run_id"]
    bridge("ocr.baseline_run",
           {"run_id": run_id,
            "pages": [{"doc_id": "att_0001", "page": 1},
                      {"doc_id": "att_0002", "page": 1}],
            "interpreter": str(args.interpreter)}, cfg)
    evidence["ocr_source"] = {"run_id": run_id}

    def gate_call(matter: str, doc_id: str, decision=None, gold=None,
                  policy=None):
        req = {"matter_id": matter, "attachment_id": doc_id,
               "source_pdf": str(attachments / "docs" / f"{doc_id}.pdf"),
               "ocr": {"run_id": run_id, "doc_id": doc_id}}
        if decision is not None:
            req["human_decision"] = decision
        if gold is not None:
            req["gold"] = gold
        extra = {"policy": policy} if policy else {}
        return bridge("attachment.gate", {**req, **extra}, cfg)

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

    def propose_and_decide(matter: str, doc_id: str):
        """prepare（无决定→机器建议）→ 人审签字（建议盒∪金标盒）→ 决定。"""
        prep = gate_call(matter, doc_id, decision=None)
        digest = prep.get("detections_digest") or "0" * 64
        boxes = [dict(b) for b in prep.get("proposed_boxes") or []]
        for g in docs[doc_id]["gold_pii"]:
            cand = {"page": 1, "box": [int(round(v)) for v in g["box"]]}
            if cand["box"] not in [b["box"] for b in boxes]:
                boxes.append(cand)
        return make_decision(matter, doc_id, digest, boxes), prep

    # ---- C1 注册表：三预设一一绑定 scope＋指纹确定性 --------------------
    eprint("-- C1 注册表")
    reg_a = bridge("redaction.presets", {}, cfg)
    reg_b = bridge("redaction.presets", {}, cfg)
    ids = [p["preset"] for p in reg_a["presets"]]
    scopes = [p["egress_scope"] for p in reg_a["presets"]]
    evidence["registry"] = reg_a
    ck.check("c1_three_presets_one_to_one_scopes",
             ids == list(PRESETS) and len(set(scopes)) == 3
             and scopes == list(PRESETS),
             f"预设 {ids} ↔ scope {scopes} 一一绑定")
    ck.check("c1_external_send_strictest",
             reg_a["strictest"] == "external_send"
             and [p["preset"] for p in reg_a["presets"] if p["strictest"]]
             == ["external_send"],
             "对外发送=最严（唯一 strictest 位）")
    ck.check("c1_digest_deterministic_canonical",
             canonical(reg_a) == canonical(reg_b)
             and all(p["config_sha256"] == hashlib.sha256(canonical(
                 {k: v for k, v in p.items()
                  if k not in ("config_sha256", "override_active")})
                 .encode("utf-8")).hexdigest() for p in reg_a["presets"]),
             "两次读取同值＋指纹=canonical sha256 复算")
    ck.check("c1_no_override_by_default",
             all(p["override_active"] is False for p in reg_a["presets"]),
             "无覆写＝默认指纹（v1 缺省）")

    # ---- C2 external_send 全闸链＋授权三路 ------------------------------
    eprint("-- C2 external_send 全闸链 att_0001")
    m_ext = f"m-f43-{profile}-ext"
    decision_ext, prep_ext = propose_and_decide(m_ext, "att_0001")
    gold_ext = [{"surface": g["surface"], "class_id": g["class_id"]}
                for g in docs["att_0001"]["gold_pii"]]
    verdict_ext = gate_call(m_ext, "att_0001", decision=decision_ext,
                            gold=gold_ext, policy="external_send")
    evidence["verdict_external_send"] = verdict_ext
    binding = verdict_ext.get("policy_binding") or {}
    ck.check("c2_gate_authorized_with_binding",
             verdict_ext.get("verdict") == "AUTHORIZED"
             and binding.get("preset") == "external_send"
             and binding.get("egress_scope") == "external_send",
             f"verdict={verdict_ext.get('verdict')} 绑定 "
             f"{binding.get('preset')}/{binding.get('egress_scope')}")
    ck.check("c2_binding_digest_matches_registry",
             binding.get("config_sha256") == next(
                 p["config_sha256"] for p in reg_a["presets"]
                 if p["preset"] == "external_send")
             and verdict_ext.get("bound_sha256") == (verdict_ext.get("burn")
                                                     or {}).get("out_sha256"),
             "策略指纹=注册表当前值；裁决绑定烧入字节")
    auth_ok = bridge("attachment.authorize",
                     {"matter_id": m_ext, "attachment_id": "att_0001",
                      "egress_scope": "external_send"}, cfg)
    evidence["authorize_scope_match"] = auth_ok
    ck.check("c2_authorize_scope_match_authorized",
             auth_ok.get("decision") == "AUTHORIZED"
             and auth_ok.get("egress_authorized") is True
             and auth_ok.get("current_sha256") == auth_ok.get("bound_sha256")
             and (auth_ok.get("policy_binding") or {}).get("preset")
             == "external_send",
             "scope 相符＋字节绑定完整→授权外发（绑定回显）")
    auth_mis = bridge("attachment.authorize",
                      {"matter_id": m_ext, "attachment_id": "att_0001",
                       "egress_scope": "public_release"}, cfg)
    evidence["authorize_scope_mismatch"] = auth_mis
    ck.check("c2_authorize_scope_mismatch_refused",
             auth_mis.get("decision") == "REFUSED"
             and auth_mis.get("reason") == "policy_scope_mismatch",
             "他 scope 冒用本裁决→拒 policy_scope_mismatch")
    auth_v1 = bridge("attachment.authorize",
                     {"matter_id": m_ext, "attachment_id": "att_0001"}, cfg)
    evidence["authorize_v1_no_scope"] = auth_v1
    ck.check("c2_v1_authorize_without_scope_unchanged",
             auth_v1.get("decision") == "AUTHORIZED"
             and "policy_binding" not in auth_v1,
             "scope 缺省＝W2a-U15 v1 行为（无策略键，字节不变）")

    # ---- C3 策略变化→旧授权失效→重审闭环 --------------------------------
    eprint("-- C3 策略变化重审")
    odir = state_root / "redaction_presets"
    odir.mkdir(parents=True, exist_ok=True)
    (odir / "external_send.json").write_text(canonical({
        "preset": "external_send",
        "redact_floor_kinds": ["id_card", "person", "personal_address",
                               "phone", "wechat"],
        "note": "recon synthetic tightening"}), encoding="utf-8")
    reg_c = bridge("redaction.presets", {}, cfg)
    cur_ext = next(p for p in reg_c["presets"]
                   if p["preset"] == "external_send")
    ck.check("c3_override_changes_digest",
             cur_ext["config_sha256"] != binding.get("config_sha256")
             and cur_ext["override_active"] is True,
             "覆写变更→活动指纹迁移（override_active）")
    auth_stale = bridge("attachment.authorize",
                        {"matter_id": m_ext, "attachment_id": "att_0001",
                         "egress_scope": "external_send"}, cfg)
    evidence["authorize_policy_changed"] = auth_stale
    ck.check("c3_policy_change_voids_authorization",
             auth_stale.get("decision") == "REFUSED"
             and auth_stale.get("reason") == "policy_changed_since_verdict"
             and auth_stale.get("bound_config_sha256")
             == binding.get("config_sha256")
             and auth_stale.get("current_config_sha256")
             == cur_ext["config_sha256"],
             "策略变更→旧授权失效（旧指纹≠当前指纹），旧 verdict 不自动沿用")
    decision_re, _prep_re = propose_and_decide(m_ext, "att_0001")
    verdict_re = gate_call(m_ext, "att_0001", decision=decision_re,
                           gold=gold_ext, policy="external_send")
    evidence["verdict_regated"] = verdict_re
    binding_re = verdict_re.get("policy_binding") or {}
    auth_re = bridge("attachment.authorize",
                     {"matter_id": m_ext, "attachment_id": "att_0001",
                      "egress_scope": "external_send"}, cfg)
    evidence["authorize_after_regate"] = auth_re
    ck.check("c3_regate_under_current_policy_restores",
             verdict_re.get("verdict") == "AUTHORIZED"
             and binding_re.get("config_sha256") == cur_ext["config_sha256"]
             and auth_re.get("decision") == "AUTHORIZED",
             "按当前策略重走闸门（人审在新策略下重签）→授权恢复（重审闭环）")
    (odir / "external_send.json").unlink()

    # ---- C4 internal_analysis 全闸链＋跨预设 scope 隔离 ------------------
    eprint("-- C4 internal_analysis 全闸链 att_0002（人审超机器底线）")
    m_int = f"m-f43-{profile}-int"
    decision_int, prep_int = propose_and_decide(m_int, "att_0002")
    gold_int = [{"surface": g["surface"], "class_id": g["class_id"]}
                for g in docs["att_0002"]["gold_pii"]]
    verdict_int = gate_call(m_int, "att_0002", decision=decision_int,
                            gold=gold_int, policy="internal_analysis")
    evidence["verdict_internal_analysis"] = verdict_int
    per_class = {c["class_id"]: c for c in
                 (verdict_int.get("coverage") or {}).get("per_class", [])}
    person = per_class.get("PERSON", {"gold_count": -1, "matched_count": -1})
    auth_int = bridge("attachment.authorize",
                      {"matter_id": m_int, "attachment_id": "att_0002",
                       "egress_scope": "internal_analysis"}, cfg)
    ck.check("c4_internal_scope_authorized",
             verdict_int.get("verdict") == "AUTHORIZED"
             and (verdict_int.get("policy_binding") or {}).get("preset")
             == "internal_analysis"
             and auth_int.get("decision") == "AUTHORIZED",
             "内部分析 scope 绑定授权")
    auth_cross = bridge("attachment.authorize",
                        {"matter_id": m_int, "attachment_id": "att_0002",
                         "egress_scope": "external_send"}, cfg)
    evidence["authorize_internal_as_external"] = auth_cross
    ck.check("c4_cross_scope_reuse_refused",
             auth_cross.get("decision") == "REFUSED"
             and auth_cross.get("reason") == "policy_scope_mismatch",
             "内部分析裁决不伺候对外发送 scope（跨 scope 复用拒）")

    # ---- C5 v1 无策略裁决：不自动沿用 ------------------------------------
    eprint("-- C5 v1 无策略裁决")
    m_v1 = f"m-f43-{profile}-v1"
    decision_v1, _prep_v1 = propose_and_decide(m_v1, "att_0001")
    verdict_v1 = gate_call(m_v1, "att_0001", decision=decision_v1)
    evidence["verdict_v1_no_policy"] = {"verdict": verdict_v1.get("verdict"),
                                        "keys": sorted(verdict_v1)}
    ck.check("c5_v1_verdict_has_no_policy_binding",
             verdict_v1.get("verdict") == "AUTHORIZED"
             and "policy_binding" not in verdict_v1,
             "policy 缺省＝v1 裁决无策略绑定量（W2a-U15 字节不变）")
    auth_v1s = bridge("attachment.authorize",
                      {"matter_id": m_v1, "attachment_id": "att_0001",
                       "egress_scope": "external_send"}, cfg)
    evidence["authorize_v1_with_scope"] = auth_v1s
    ck.check("c5_v1_verdict_not_reused_under_scope",
             auth_v1s.get("decision") == "REFUSED"
             and auth_v1s.get("reason") == "policy_not_bound_in_verdict",
             "v1 旧裁决进 F43 授权面＝拒（不自动沿用，须按策略重走闸门）")

    # ---- C6 共享假名不串案（每案共享库，跨策略一致，分案隔离）------------
    eprint("-- C6 共享假名")
    text = f"委托人已确认（电话 13700005555）同意代理。"
    d_i = bridge("redaction.deidentify_matter",
                 {"matter_id": f"m-p-{profile}", "preset": "internal_analysis",
                  "text": text}, cfg)
    d_e = bridge("redaction.deidentify_matter",
                 {"matter_id": f"m-p-{profile}", "preset": "external_send",
                  "text": text}, cfg)
    d_u = bridge("redaction.deidentify_matter",
                 {"matter_id": f"m-p-{profile}", "preset": "public_release",
                  "text": text}, cfg)
    evidence["pseudonym_shared"] = {
        "internal": {"policy": d_i["policy"], "counts": d_i["counts"],
                     "map_sha256": d_i["map_sha256"]},
        "external": {"policy": d_e["policy"], "counts": d_e["counts"],
                     "map_sha256": d_e["map_sha256"]},
        "public": {"policy": d_u["policy"], "counts": d_u["counts"],
                   "map_sha256": d_u["map_sha256"]}}
    ck.check("c6_contact_redacted_all_presets",
             all("13700005555" not in d["sanitized_text"]
                 for d in (d_i, d_e, d_u)),
             "联系方式三预设全脱（规则层恒脱）")
    ck.check("c6_token_shared_across_strategies",
             d_i["map_sha256"] == d_e["map_sha256"] == d_u["map_sha256"]
             and d_i["counts"]["token_total"]
             == d_e["counts"]["token_total"] == d_u["counts"]["token_total"],
             "同案三预设同一共享库（指纹/计数一致＝同 token）")
    r1 = bridge("redaction.pseudonym_resolve",
                {"matter_id": f"m-p-{profile}", "preset": "internal_analysis",
                 "items": [{"surface": "13700005555", "category": "contact",
                            "kind": "cn-mobile"},
                           {"surface": "张三丰", "category": "person"}]}, cfg)
    r2 = bridge("redaction.pseudonym_resolve",
                {"matter_id": f"m-p-{profile}", "preset": "external_send",
                 "items": [{"surface": "13700005555", "category": "contact",
                            "kind": "cn-mobile"},
                           {"surface": "张三丰", "category": "person"}]}, cfg)
    r3 = bridge("redaction.pseudonym_resolve",
                {"matter_id": f"m-p-{profile}", "preset": "public_release",
                 "items": [{"surface": "13700005555", "category": "contact",
                            "kind": "cn-mobile"}]}, cfg)
    evidence["resolve_tokens"] = {"internal": r1["tokens"],
                                  "external": r2["tokens"],
                                  "public": r3["tokens"]}
    ck.check("c6_resolve_same_surface_same_token",
             r1["tokens"][:1] == r2["tokens"][:1] == r3["tokens"][:1]
             and r1["tokens"][1] == r2["tokens"][1],
             "同一 surface 跨三预设同 token（共享映射文件保证）")
    body_r1 = canonical(r1)
    ck.check("c6_resolve_zero_surface_echo",
             "13700005555" not in body_r1 and "张三丰" not in body_r1,
             "裸解析只回 token 串（按输入序对位），零 surface 回显")
    m2map = bridge(
        "redaction.pseudonym_resolve",
        {"matter_id": f"m-q-{profile}", "preset": "internal_analysis",
         "items": [{"surface": "李四明", "category": "person"}]}, cfg)
    # 他案库还原本案独有 token → 原文不动（跨案结构性不可达）
    phone_tok = r1["tokens"][0]
    cross = bridge("redaction.rehydrate_matter",
                   {"matter_id": f"m-q-{profile}",
                    "preset": "internal_analysis", "text": phone_tok}, cfg)
    ck.check("c6_cross_matter_rehydrate_unreachable",
             cross["text"] == phone_tok and cross["resolved_count"] == 0,
             "他案（m-q）库无本案条目→还原不动原文（不串案）")
    own = bridge("redaction.rehydrate_matter",
                 {"matter_id": f"m-p-{profile}",
                  "preset": "internal_analysis", "text": d_i["sanitized_text"]},
                 cfg)
    ck.check("c6_own_matter_rehydrate_restores",
             "13700005555" in own["text"] and own["resolved_count"] >= 1,
             "本案还原正常（映射不出 anonymizer，owner 本地可逆）")

    # ---- C7 桥 fail-closed ------------------------------------------------
    eprint("-- C7 桥 fail-closed")
    try:
        bridge("redaction.deidentify_matter",
               {"matter_id": "m", "preset": "bogus", "text": "x"}, cfg)
        bad_preset = "no-raise"
    except Exception as exc:  # noqa: BLE001 - 桥 typed 拒形态断言
        bad_preset = str(exc)
    try:
        bridge("redaction.rehydrate_matter",
               {"matter_id": "m-none", "preset": "external_send",
                "text": "x"}, cfg)
        no_map = "no-raise"
    except Exception as exc:  # noqa: BLE001
        no_map = str(exc)
    try:
        bridge("attachment.authorize",
               {"matter_id": m_ext, "attachment_id": "att_0001",
                "egress_scope": "bogus"}, cfg)
        bad_scope = "no-raise"
    except Exception as exc:  # noqa: BLE001
        bad_scope = str(exc)
    ck.check("c7_bridge_typed_refusals",
             isinstance(bad_preset, str) and "redaction_preset_invalid"
             in bad_preset and "redaction_preset_no_map" in no_map
             and "attachment_gate_egress_scope_invalid" in bad_scope,
             f"未知预设/无映射案/未知 scope 全 typed 具名拒（{bad_preset[:40]}…）")
    return ck, evidence


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--profile", action="append", default=[],
                    choices=["desktop", "selfhost"])
    ap.add_argument("--attachments", default=str(DEFAULT_ATTACHMENTS))
    ap.add_argument("--state-root-prefix",
                    default=str(TEMP / "juscite-f43-states"))
    ap.add_argument("--anonymizer-src", default=None)
    ap.add_argument("--interpreter", default=str(DEFAULT_INTERPRETER))
    ap.add_argument("--keep-temp", action="store_true")
    args = ap.parse_args()
    profiles = args.profile or ["desktop", "selfhost"]

    if not Path(args.interpreter).is_file():
        eprint(f"[ENV] 钉定解释器缺失：{args.interpreter}")
        return 3
    anonymizer_src = resolve_anonymizer_src(args.anonymizer_src)
    bridge, anonymizer_file = load_bridge(anonymizer_src)
    try:
        import legal_anonymizer.application.redaction_presets_service  # noqa: F401
    except ImportError as exc:
        eprint(f"[ENV] anonymizer F43 面不可导入：{exc}")
        return 3
    attachments = Path(args.attachments)
    if not ensure_attachments(attachments):
        eprint("[ENV] 附件夹具不可用（生成器失败）")
        return 3
    manifest = json.loads((attachments / "corpus_manifest.json")
                          .read_text(encoding="utf-8"))

    overall_ok = True
    all_evidence: dict = {"unit": "W4-U36", "obligation": "F43",
                          "started_at": now_iso(),
                          "anonymizer_src": anonymizer_file,
                          "attachments": str(attachments),
                          "profiles": {}}
    for profile in profiles:
        eprint(f"=== profile {profile} ===")
        t0 = time.time()
        ck, evidence = run_profile(profile, args, manifest, attachments,
                                   bridge, anonymizer_file)
        verdict = "RECON_OK" if ck.failed == 0 else "RECON_FAIL"
        overall_ok = overall_ok and ck.failed == 0
        payload = {"unit": "W4-U36", "obligation": "F43", "profile": profile,
                   "started_at": all_evidence["started_at"],
                   "finished_at": now_iso(),
                   "duration_s": round(time.time() - t0, 1),
                   "verdict": verdict,
                   "checks": {"total": len(ck.rows), "passed": ck.passed,
                              "failed": ck.failed},
                   "rows": ck.rows, "evidence": evidence}
        md = ["# F43 脱敏策略预设三套 recon（W4-U36）", "",
              f"- profile: `{profile}`", f"- verdict: **{verdict}**",
              f"- checks: {ck.passed}/{len(ck.rows)} passed", "",
              "| id | ok | detail |", "|---|---|---|"]
        md += [f"| {r['id']} | {'ok' if r['ok'] else 'FAIL'} | {r['detail']} |"
               for r in ck.rows]
        md += ["", f"anonymizer src: `{anonymizer_file}`",
               f"attachments: `{attachments}` (seed {CORPUS_SEED})"]
        paths = write_evidence(profile, payload, "\n".join(md) + "\n")
        eprint(f"[EVIDENCE] {verdict} {ck.passed}/{len(ck.rows)} → "
               + ", ".join(str(p) for p in paths))
        all_evidence["profiles"][profile] = {
            "verdict": verdict, "checks": payload["checks"]}
    all_evidence["finished_at"] = now_iso()
    all_evidence["overall"] = "RECON_OK" if overall_ok else "RECON_FAIL"
    return 0 if overall_ok else 2


if __name__ == "__main__":
    sys.exit(main())

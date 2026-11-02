#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""E11/F37 义务验收 recon（W2a-U09）：脱敏资格闸与人审覆盖。

E11（07:12，prereq E10/E12）：生产 NER 未 qualified 显 REVIEW_REQUIRED；
人审覆盖与自动性能分母分开；终字节复扫和假名只在 owner。
F37（06:38，P20）：人名/主体/敏感类分子分母真实报告；ner 未合格依赖面
REVIEW_REQUIRED，人审覆盖有决定；不自建第二隐私引擎；保 14 类规则/案件
词典稳定假名/三类永不回填；NER 资格与人审分开。

金标＝W2a-U02 解析产物（%TEMP%\\juscite-e12-corpus-5k-a，W2a-U01 生成器
seed 20261015 全合成语料；corpus_manifest 每卷 title/case_no 推导当事人
金标——E12 recon 同源金标）。材料文本＝真 OCR：anonymizer ocr_ports_service
基础线（F40 钉定解释器）跑每卷第 1 页（首页 TEXT 标题页，生成器约束）。
产品径＝implementation/python/legal_entry.py 桥（review.* 方法组）→
anonymizer review_gate_service 公开面（同进程，P09/P10 纪律）。

用法（juscite worktree w2a-u09 仓根 cwd）：
  python -X utf8 tools/PENDING_OWNER_e11_f37_review_gate_recon.py --profile desktop
  python -X utf8 tools/PENDING_OWNER_e11_f37_review_gate_recon.py --profile selfhost
  [--docs 40] [--corpus <dir>] [--state-root <dir>] [--anonymizer-src <path>]
  [--interpreter <path>] [--skip-ocr]

退出码：0＝RECON_OK（硬门全过）；2＝RECON_FAIL；3＝环境缺失。
证据：docs/construction/evidence/E11/<profile>/＋evidence/F37/<profile>/
（JSON＋MD，同一跑批双义务目录）。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import time
import unicodedata
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
TEMP = Path(os.environ.get("TEMP", "."))
DEFAULT_CORPUS = TEMP / "juscite-e12-corpus-5k-a"
DEFAULT_INTERPRETER = Path(os.environ.get(
    "JUSCITE_F40_BASELINE_INTERPRETER",
    r"C:\Users\being\AppData\Local\pdf2md-venv\Scripts\python.exe"))
CORPUS_SEED = 20261015
CORPUS_PAGES = 5000

# 硬门阈值：案号规则层命中率（干净字体 OCR；F40 单元格 99.41% 实测参考）
CASE_NUMBER_RATIO_MIN = 0.95


def eprint(*a) -> None:
    print(*a, file=sys.stderr, flush=True)


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def norm(s: str) -> str:
    return re.sub(r"\s+", "", unicodedata.normalize("NFKC", s or ""))


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
    """anonymizer w2a-u09 源定位：显式参 > 环境变量 > 同波 worktree 相对
    推断 > None（回退已安装面——若缺 review_gate_service 会在 C1 报环境缺）。"""
    if explicit:
        return str(Path(explicit).resolve())
    env = os.environ.get("JUSCITE_ANONYMIZER_SRC")
    if env:
        return str(Path(env).resolve())
    guess = (REPO.parents[4] / "legal-cn-anonymizer工作区"
             / "legal-cn-anonymizer" / ".local" / "worktrees" / "w2a-u09"
             / "src")
    if (guess / "legal_anonymizer" / "application"
            / "review_gate_service.py").is_file():
        return str(guess)
    return None


def load_bridge(anonymizer_src: str | None):
    sys.path.insert(0, str(REPO / "implementation" / "python"))
    if anonymizer_src:
        sys.path.insert(0, anonymizer_src)
    import legal_anonymizer
    from legal_entry import call as bridge_call
    return bridge_call, str(legal_anonymizer.__file__)


def ensure_corpus(corpus: Path) -> bool:
    """语料=W2a-U02 产物；缺失则按同生成器/seed/页数重建（确定性合成）。"""
    if (corpus / "corpus_manifest.json").is_file():
        return True
    eprint(f"[GEN] 语料缺失，按 seed={CORPUS_SEED} 重建 → {corpus}")
    proc = subprocess.run(
        [sys.executable, "-X", "utf8", str(REPO / "tools" / "e12_corpus_gen.py"),
         "--pages", str(CORPUS_PAGES), "--seed", str(CORPUS_SEED),
         "--out", str(corpus)],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        timeout=1800)
    if proc.returncode != 0:
        eprint((proc.stdout or "")[-600:], (proc.stderr or "")[-600:])
        return False
    return (corpus / "corpus_manifest.json").is_file()


def load_gold(corpus: Path, docs_limit: int) -> tuple[dict, list[dict], list[dict]]:
    """金标＝corpus_manifest 每卷：原告/被告（主体×2）＋案号（业务标识）。
    当事人从 title 确定性解析（生成器固定格式＋DOC_TYPES 冻结清单）。"""
    sys.path.insert(0, str(REPO / "tools"))
    from e12_corpus_gen import DOC_TYPES  # 冻结合成语料定义（同仓工具）

    manifest = json.loads((corpus / "corpus_manifest.json")
                          .read_text(encoding="utf-8"))
    gold: list[dict] = []
    docs = []
    for doc in manifest["documents"][:docs_limit]:
        title = doc["title"]
        body = title.split("：", 1)[1]
        body = body[: -len("纠纷案")] if body.endswith("纠纷案") else body
        plaintiff, rest = body.split("与", 1)
        defendant = rest
        for doc_type in DOC_TYPES:
            if rest.endswith(doc_type):
                defendant = rest[: -len(doc_type)]
                break
        docs.append({"doc_id": doc["doc_id"], "case_no": doc["case_no"],
                     "plaintiff": plaintiff, "defendant": defendant,
                     "first_page_kind": doc["page_files"][0]["kind"]})
        gold.append({"surface": plaintiff, "class_id": "LEGAL_PERSON"})
        gold.append({"surface": defendant, "class_id": "LEGAL_PERSON"})
        gold.append({"surface": doc["case_no"], "class_id": "case_number"})
    return manifest, gold, docs


def corpus_anchor(corpus: Path, docs: list[dict]) -> str:
    parts = [sha256_file(corpus / "corpus_manifest.json")]
    for d in docs[:8]:
        png = corpus / "pages" / d["doc_id"] / "p0001.png"
        parts.append(d["doc_id"] + ":" + sha256_file(png))
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--profile", choices=["desktop", "selfhost"],
                    default="desktop")
    ap.add_argument("--docs", type=int, default=40,
                    help="金标取前 N 卷（每卷第 1 页 OCR）")
    ap.add_argument("--corpus", type=Path, default=DEFAULT_CORPUS)
    ap.add_argument("--state-root", type=Path, default=None)
    ap.add_argument("--anonymizer-src", default=None)
    ap.add_argument("--interpreter", type=Path, default=DEFAULT_INTERPRETER)
    ap.add_argument("--skip-ocr", action="store_true",
                    help="跳过 OCR 跑批（要求该 profile 状态根已完成）")
    args = ap.parse_args()

    state_root = args.state_root or (
        TEMP / f"juscite-e11f37-state-{args.profile}")
    state_root.mkdir(parents=True, exist_ok=True)
    started = time.time()
    eprint(f"== W2a-U09 E11/F37 recon [{args.profile}] corpus={args.corpus}")

    # -- 环境面 -------------------------------------------------------------
    bridge = None
    anonymizer_file = None
    if not ensure_corpus(args.corpus):
        eprint("[ENV] 语料不可得")
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

    manifest, gold, docs = load_gold(args.corpus, args.docs)
    anchor_before = corpus_anchor(args.corpus, docs)
    cfg = {"anonymizer_contract": "p09/p10",
           "review_gate_state_root": str(state_root),
           "ocr_ports_state_root": str(state_root),
           "ocr_baseline_interpreter": str(args.interpreter)}
    ck = Checks()
    evidence: dict = {"schema": "juscite-e11-f37-review-gate-recon/1",
                      "profile": args.profile, "started_at": now_iso(),
                      "anonymizer_src": anonymizer_file,
                      "corpus": str(args.corpus),
                      "corpus_anchor_before": anchor_before,
                      "docs": len(docs), "checks": ck.rows}

    # -- C1 资格闸（E11）----------------------------------------------------
    eprint("-- C1 资格闸")
    qual = bridge("review.qualification", {}, cfg)
    evidence["qualification"] = qual
    ck.check("c1_gate_review_required",
             qual["gate"]["status"] == "REVIEW_REQUIRED",
             f"gate={qual['gate']['status']} reasons={qual['gate']['reasons']}")
    ck.check("c1_manifest_unqualified_named",
             qual["ner"]["manifest_qualified"] is False
             and "manifest_ner_not_qualified" in qual["gate"]["reasons"],
             "manifest ner.qualified=false 如实入闸")
    ck.check("c1_runtime_components_named",
             bool(qual["ner"]["components"])
             and all(c["ok"] in (True, False) and c["reason"]
                     for c in qual["ner"]["components"]),
             "runtime probe 每组件具名："
             + ",".join(f"{c['name']}={'ok' if c['ok'] else c['reason'][:24]}"
                        for c in qual["ner"]["components"]))
    ck.check("c1_qualification_human_separation",
             qual["separation"]["independent"] is True
             and "人审" in qual["gate"]["semantics"],
             "资格（机器事实）与人审（回执决定）分开表述")

    # -- C2 规则类闭集清单（F37）--------------------------------------------
    eprint("-- C2 规则类闭集清单")
    inventory = bridge("review.rule_classes", {}, cfg)["inventory"]
    evidence["rule_class_inventory"] = inventory
    ids = [c["class_id"] for c in inventory]
    ck.check("c2_inventory_closed_14_floor",
             len(ids) == len(set(ids)) and len(ids) >= 14,
             f"确定性规则层类闭集 {len(ids)} 类（14 类底线）")
    groups = {c["group"] for c in inventory}
    ck.check("c2_groups_cover_f37",
             {"person", "subject", "sensitive"} <= groups,
             f"分组={sorted(groups)}")
    nb = {c["class_id"] for c in inventory if c["never_backfill"]}
    ck.check("c2_never_backfill_flags",
             nb == {"id_card", "phone"},
             f"规则层 never_backfill={sorted(nb)}"
             "（owner 常量另含 personal_address）")

    # -- C3 分子分母真实报告（F37）------------------------------------------
    eprint(f"-- C3 OCR 材料化（{len(docs)} 卷首页）")
    reg = bridge("ocr.baseline_register",
                 {"corpus_root": str(args.corpus),
                  "interpreter": str(args.interpreter)}, cfg)
    run_id = reg["run_id"]
    pages = [{"doc_id": d["doc_id"], "page": 1} for d in docs]
    if not args.skip_ocr:
        t0 = time.time()
        bridge("ocr.baseline_run",
               {"run_id": run_id, "pages": pages,
                "interpreter": str(args.interpreter)}, cfg)
        eprint(f"   OCR 完成 {len(pages)} 页 用时 {time.time()-t0:.0f}s")
    texts, ocr_pages_ok = [], 0
    for d in docs:
        page = bridge("ocr.baseline_page",
                      {"run_id": run_id, "doc_id": d["doc_id"], "page": 1},
                      cfg)
        lines = page.get("lines") or []
        if page.get("error") is None and lines:
            ocr_pages_ok += 1
        texts.append("\n".join(str(l.get("text", "")) for l in lines))
    ck.check("c3_ocr_pages_materialized",
             ocr_pages_ok == len(docs),
             f"OCR 首页 {ocr_pages_ok}/{len(docs)} 卷可读（真材料文本）")
    evidence["ocr"] = {"run_id": run_id, "pages": len(pages),
                       "pages_with_lines": ocr_pages_ok}

    eprint("-- C3a 规则口径分子分母（无词典）")
    rules_cov = bridge("review.class_coverage",
                       {"texts": texts, "gold": gold, "stack": "rules"}, cfg)
    evidence["coverage_rules"] = rules_cov
    by_class = {c["class_id"]: c for c in rules_cov["per_class"]}
    case_row = by_class.get("case_number", {"gold_count": 0,
                                            "matched_count": 0})
    case_ratio = (case_row["matched_count"] / case_row["gold_count"]
                  if case_row["gold_count"] else None)
    ck.check("c3a_case_denominator_real",
             case_row["gold_count"] == len(docs),
             f"案号分母={case_row['gold_count']}（金标 {len(docs)} 卷逐一入分母）")
    ck.check("c3a_case_numerator_real",
             case_ratio is not None and case_ratio >= CASE_NUMBER_RATIO_MIN
             and case_row["matched_count"] <= case_row["gold_count"],
             f"案号分子={case_row['matched_count']}/{case_row['gold_count']}"
             f" ratio={case_ratio}")
    subject = by_class.get("LEGAL_PERSON", {"gold_count": 0,
                                            "matched_count": 0})
    ck.check("c3a_subject_rules_honest_zero",
             subject["gold_count"] == 2 * len(docs)
             and subject["matched_count"] == 0,
             f"主体分母={subject['gold_count']} 规则层分子=0（无公司名正则，"
             "诚实缺口＝NER/词典/人审面）")
    ck.check("c3a_person_unmeasured_null",
             rules_cov["groups"]["person"]["gold_count"] == 0
             and rules_cov["groups"]["person"]["ratio"] is None,
             "人名类金标 0（语料无法人当事人）→ ratio=None 非造 0")
    ck.check("c3a_gate_stamp_on_numbers",
             rules_cov["gate"]["status"] == "REVIEW_REQUIRED",
             "分子分母报告带资格闸戳（未 qualified 数字≠自动足够）")

    eprint("-- C3b 案件词典口径（主体确认源）")
    dictionary = {"blacklist": [
        item for d in docs for item in (
            {"value": d["plaintiff"], "type": "LEGAL_PERSON",
             "name": f"{d['doc_id']}-原告"},
            {"value": d["defendant"], "type": "LEGAL_PERSON",
             "name": f"{d['doc_id']}-被告"},
        )]}
    dict_cov = bridge("review.class_coverage",
                      {"texts": texts, "gold": gold, "stack": "rules",
                       "dictionary": dictionary}, cfg)
    evidence["coverage_dictionary"] = dict_cov
    d_subject = next((c for c in dict_cov["per_class"]
                      if c["class_id"] == "LEGAL_PERSON"), None)
    ck.check("c3b_dictionary_confirms_subject",
             d_subject is not None
             and d_subject["matched_count"] == 2 * len(docs)
             and d_subject.get("matched_by_source", {}).get("dictionary")
             == 2 * len(docs),
             f"词典确认后主体分子={d_subject['matched_count'] if d_subject else 0}"
             f"/{2 * len(docs)}（source=dictionary）")
    ck.check("c3b_gate_unchanged_by_dictionary",
             dict_cov["gate"]["status"] == "REVIEW_REQUIRED"
             and dict_cov["ner"]["manifest_qualified"] is False,
             "词典救分子不改资格事实（NER 资格与人审/词典分开）")

    # -- C4 人审覆盖分母（E11，与自动性能分母分开）---------------------------
    eprint("-- C4 人审覆盖分母")
    from legal_anonymizer.application.review_service import (
        issue_review_receipt,
    )
    from legal_anonymizer.application.sanitize_service import SanitizeService
    from legal_anonymizer.application.state import MatterState

    # 每跑独立 matter：幂等复跑时旧回执不污染「回执前」分母检查
    matter = f"m-e11f37-{args.profile}-{int(time.time())}"
    matter_dir = state_root / "matters" / matter
    inbox = matter_dir / "in"
    inbox.mkdir(parents=True, exist_ok=True)
    (inbox / "note.md").write_text(
        "合成合同：原告合某诚科技有限公司与被告北某建工集团有限公司，"
        "案号（2026）京01民初90001号，电话13700002222，"
        "身份证110101199003078670。（全合成测试材料）\n", encoding="utf-8")
    if not MatterState(state_root, matter).exists():
        MatterState(state_root, matter).init("cn-ai-safe-v1")
    out = matter_dir / "out"
    result = SanitizeService(state_root).sanitize(matter, inbox, out)
    evidence["matter_sanitize"] = {"matter": matter, "status": result.status,
                                   "review_reasons": result.review_reasons}
    ck.check("c4_sanitize_review_required",
             result.status == "REVIEW_REQUIRED",
             f"合成 matter（无词典）机器闸={result.status}"
             f" reasons={result.review_reasons}")

    hc0 = bridge("review.human_coverage",
                 {"matter_ids": [matter], "out_dirs": {matter: str(out)}},
                 cfg)
    evidence["human_coverage_before_receipt"] = hc0
    ck.check("c4_human_denominator_before_receipt",
             hc0["totals"]["review_required"] == 1
             and hc0["totals"]["receipt_covered"] == 0,
             f"人审覆盖分母=1 分子=0（{hc0['denominator_basis']}）")
    ck.check("c4_human_denominator_separate_statement",
             hc0["separated_from"].startswith("auto performance"),
             "人审覆盖分母与自动性能分母口径声明分开")

    issue_review_receipt(
        state_root, matter, out,
        {"matter_id": matter, "decisions": [{"scope": "all",
                                             "action": "confirm"}]},
        f"S-1-5-21-recon-{args.profile}", "MATTER_LEAD")
    hc1 = bridge("review.human_coverage",
                 {"matter_ids": [matter], "out_dirs": {matter: str(out)}},
                 cfg)
    evidence["human_coverage"] = hc1
    ck.check("c4_receipt_lifts_coverage_only",
             hc1["totals"]["review_required"] == 1
             and hc1["totals"]["receipt_covered"] == 1
             and hc1["matters"][0]["receipt"]["valid_signature"] is True,
             "有效回执→人审分子=1/1")

    # 自动性能分母不随人审改变（分开实证）：主体规则分子仍是 0
    sep_cov = bridge("review.class_coverage",
                     {"texts": ["合成合同：原告合某诚科技有限公司与被告"
                                "北某建工集团有限公司，案号（2026）京01民初"
                                "90001号。"], "stack": "rules",
                      "gold": [
                          {"surface": "合某诚科技有限公司",
                           "class_id": "LEGAL_PERSON"},
                          {"surface": "北某建工集团有限公司",
                           "class_id": "LEGAL_PERSON"}]}, cfg)
    sep_subject = next((c for c in sep_cov["per_class"]
                        if c["class_id"] == "LEGAL_PERSON"), None)
    ck.check("c4_auto_denominator_untouched_by_human_review",
             sep_subject is not None and sep_subject["matched_count"] == 0
             and sep_subject["gold_count"] == 2,
             "人审回执后自动性能口径主体分子仍=0/2（两分母互不代言）")

    # -- C5 三类永不回填（F37）----------------------------------------------
    eprint("-- C5 三类永不回填")
    from legal_anonymizer.application.rehydrate_service import RehydrateService

    nb_matter = f"m-f37nb-{args.profile}"
    nb_dir = state_root / "matters" / nb_matter
    nb_dir.mkdir(parents=True, exist_ok=True)
    if not MatterState(state_root, nb_matter).exists():
        MatterState(state_root, nb_matter).init("cn-ai-safe-v1")
    st = MatterState(state_root, nb_matter)
    private = st.read_private()
    private["identifier_aliases"] = [
        {"kind": "case_number", "surface": "（2026）京01民初90001号",
         "alias": "案号甲"},
        {"kind": "id_card", "surface": "110101199003078670",
         "alias": "证件甲"},
        {"kind": "phone", "surface": "13700002222", "alias": "电话甲"},
        {"kind": "personal_address", "surface": "北京市海淀区合成路1号",
         "alias": "住址甲"},
    ]
    private["entities"] = [
        {"entity_id": "ent-1", "entity_type": "LEGAL_PERSON",
         "canonical_surface": "合某诚科技有限公司", "aliases": [],
         "display_alias": "法人甲", "roles": []}]
    st.write_private(private)

    nb_report = bridge("review.never_backfill", {"matter_id": nb_matter}, cfg)
    evidence["never_backfill"] = nb_report
    ck.check("c5_report_three_kinds_no_surfaces",
             nb_report["never_backfill_kinds"] == [
                 "id_card", "phone", "personal_address"]
             and {h["kind"] for h in
                  nb_report["aliases_in_never_backfill_kinds"]}
             == {"id_card", "phone", "personal_address"}
             and all("surface" not in h for h in
                     nb_report["aliases_in_never_backfill_kinds"]),
             "三类命中清单只带 alias+kind，真实 surface 绝不出域")
    rehy = RehydrateService(state_root).rehydrate_text(
        nb_matter, "法人甲 案号甲 证件甲 电话甲 住址甲 的合成回复")
    leaked = [s for s, present in {
        "110101199003078670": "110101199003078670" in rehy.output_text,
        "13700002222": "13700002222" in rehy.output_text,
        "北京市海淀区合成路1号": "北京市海淀区合成路1号" in rehy.output_text,
    }.items() if present]
    ck.check("c5_never_backfill_enforced",
             not leaked
             and "合某诚科技有限公司" in rehy.output_text
             and "（2026）京01民初90001号" in rehy.output_text,
             "实体/案号假名照常回填；三类真实值零泄漏"
             + (f" leaked={leaked}" if leaked else ""))

    # -- C6 假名与终字节复扫只在 owner（E11）---------------------------------
    eprint("-- C6 owner-only")
    import legal_entry
    ck.check("c6_bridge_methods_frozen",
             legal_entry.REVIEW_GATE_METHODS == frozenset({
                 "review.qualification", "review.rule_classes",
                 "review.class_coverage", "review.human_coverage",
                 "review.never_backfill"}),
             "review.* 方法组冻结（五方法，无映射/回填导出面）")
    try:
        bridge("material.rehydrate", {"text": "法人甲"}, cfg)
        rehydrate_blocked = False
    except Exception as exc:  # noqa: BLE001
        rehydrate_blocked = "method_not_connected" in str(exc)
    ck.check("c6_no_standalone_rehydrate_face",
             rehydrate_blocked,
             "material.rehydrate 结构性不存在（映射不出 owner）")

    product_py = sorted((REPO / "implementation" / "python").glob("*.py"))
    forbidden = [r"1[3-9]\\d{9}", r"\\d{17}[0-9Xx]", r"（\\d{4}）"]
    second_engine_hits = [
        f.name for f in product_py
        if f.name != "legal_entry.py"
        and any(re.search(sig, f.read_text(encoding="utf-8", errors="ignore"))
                for sig in forbidden)]
    ck.check("c6_no_second_privacy_engine",
             not second_engine_hits,
             "产品 Python 面无 PII 检测正则（唯一引擎=anonymizer）"
             + (f" hits={second_engine_hits}" if second_engine_hits else ""))

    from legal_anonymizer.application import scan_bytes_service
    dirty = json.dumps({"content": "身份证110101199003078670"
                        "电话13700002222"}, ensure_ascii=False).encode()
    dirty_report = scan_bytes_service.scan_bytes({
        "requestId": "recon-e11f37-dirty", "releaseProfileId":
            "cn-release-v42", "profileVersion": "1",
        "scanProfile": "json-recursive-keys-and-strings/v1",
        "bodyBase64": __import__("base64").b64encode(dirty).decode(),
        "bodySha256": hashlib.sha256(dirty).hexdigest(),
        "byteLength": len(dirty)})
    clean = json.dumps({"content": "无关内容"}, ensure_ascii=False).encode()
    clean_report = scan_bytes_service.scan_bytes({
        "requestId": "recon-e11f37-clean", "releaseProfileId":
            "cn-release-v42", "profileVersion": "1",
        "scanProfile": "json-recursive-keys-and-strings/v1",
        "bodyBase64": __import__("base64").b64encode(clean).decode(),
        "bodySha256": hashlib.sha256(clean).hexdigest(),
        "byteLength": len(clean)})
    evidence["scan_bytes"] = {"dirty": dirty_report, "clean": clean_report}
    ck.check("c6_final_byte_rescan_in_owner",
             (dirty_report["status"] == "complete"
              and dirty_report["alertCount"] >= 1)
             or dirty_report["status"] == "model_missing",
             f"owner 终字节复扫：脏字节 alerts={dirty_report['alertCount']}"
             f" status={dirty_report['status']}（NER 缺失时 fail-closed）")
    ck.check("c6_clean_bytes_complete",
             clean_report["status"] in ("complete", "model_missing")
             and clean_report["alertCount"] == 0,
             f"净字节 status={clean_report['status']}")

    # -- 语料只读锚 ----------------------------------------------------------
    anchor_after = corpus_anchor(args.corpus, docs)
    ck.check("c7_corpus_readonly_anchor",
             anchor_after == anchor_before,
             "语料锚前后一致（只读）")
    evidence["corpus_anchor_after"] = anchor_after
    evidence["finished_at"] = now_iso()
    evidence["duration_s"] = round(time.time() - started, 1)

    # -- 证据落盘 ------------------------------------------------------------
    ev_dir = REPO / "docs" / "construction" / "evidence"
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    for ob in ("E11", "F37"):
        out_dir = ev_dir / ob / args.profile
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / f"e11f37-review-gate-recon-{stamp}.json").write_text(
            json.dumps(evidence, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8")
    summary_md = render_md(evidence, ck)
    for ob in ("E11", "F37"):
        (ev_dir / ob / args.profile
         / f"e11f37-review-gate-recon-{stamp}.md").write_text(
            summary_md, encoding="utf-8")
    eprint(f"== {ck.passed}/{len(ck.rows)} checks passed"
           f" ({time.time() - started:.0f}s)")
    if ck.failed:
        eprint(f"RECON_FAIL: {ck.failed} failed")
        return 2
    eprint("RECON_OK")
    return 0


def render_md(ev: dict, ck: Checks) -> str:
    rules = ev.get("coverage_rules", {})
    dict_cov = ev.get("coverage_dictionary", {})
    per = {c["class_id"]: c for c in rules.get("per_class", [])}
    d_per = {c["class_id"]: c for c in dict_cov.get("per_class", [])}
    qual = ev.get("qualification", {})
    lines = [
        "# E11/F37 脱敏资格闸与人审覆盖 recon 证据"
        f"（{ev['profile']}，W2a-U09）",
        "",
        f"- 时间：{ev['started_at']} → {ev['finished_at']}"
        f"（{ev.get('duration_s')}s）；anonymizer 面：`{ev['anonymizer_src']}`",
        f"- 语料（W2a-U02 解析产物，全合成）：`{ev['corpus']}`；"
        f"金标 {ev['docs']} 卷（主体×2＋案号）；语料锚只读。",
        "## C1 资格闸（E11）",
        f"- gate = **{qual.get('gate', {}).get('status')}**；"
        f"reasons = {qual.get('gate', {}).get('reasons')}",
        f"- manifest qualified = {qual.get('ner', {}).get('manifest_qualified')}"
        f"；runtime available = {qual.get('ner', {}).get('runtime_available')}"
        f"（组件逐项实测："
        + ", ".join(f"{c['name']}={'ok' if c['ok'] else c['reason']}"
                    for c in qual.get('ner', {}).get('components', [])) + "）",
        "- 资格（机器事实）与人审（回执决定）互不代言。",
        "## C3 分子分母真实报告（F37）",
        f"- 材料文本＝OCR 首页 {ev.get('ocr', {}).get('pages_with_lines')}"
        f"/{ev.get('ocr', {}).get('pages')} 卷真跑（F40 钉定解释器）。",
        f"- 案号（rules）：{per.get('case_number', {}).get('matched_count')}"
        f"/{per.get('case_number', {}).get('gold_count')}",
        f"- 主体（rules）：{per.get('LEGAL_PERSON', {}).get('matched_count')}"
        f"/{per.get('LEGAL_PERSON', {}).get('gold_count')}"
        "（规则层无公司名正则＝诚实缺口）",
        f"- 主体（词典确认后）：{d_per.get('LEGAL_PERSON', {}).get('matched_count')}"
        f"/{d_per.get('LEGAL_PERSON', {}).get('gold_count')}"
        f"（source={d_per.get('LEGAL_PERSON', {}).get('matched_by_source')}）",
        f"- 人名类金标 0 → ratio=None（未测不造 0）；"
        f"gate 戳={rules.get('gate', {}).get('status')}",
        "## C4 人审覆盖分母（E11，与自动性能分母分开）",
        f"- matter 机器闸：{ev.get('matter_sanitize', {}).get('status')}"
        f"（reasons={ev.get('matter_sanitize', {}).get('review_reasons')}）",
        f"- 回执前 totals="
        f"{ev.get('human_coverage_before_receipt', {}).get('totals')}"
        f" → 回执后 totals="
        f"{ev.get('human_coverage', {}).get('totals')}",
        "- 人审回执后自动性能口径主体分子仍 0/2（两分母互不代言）。",
        "## C5 三类永不回填（F37）",
        f"- kinds={ev.get('never_backfill', {}).get('never_backfill_kinds')}"
        "；回填实测：实体/案号恢复，三类真实值零泄漏。",
        "## C6 假名与终字节复扫只在 owner（E11）",
        f"- review.* 五方法冻结；material.rehydrate 不存在；"
        f"产品面无第二隐私引擎；owner 终字节复扫脏字节 alerts="
        f"{ev.get('scan_bytes', {}).get('dirty', {}).get('alertCount')}"
        f"（status={ev.get('scan_bytes', {}).get('dirty', {}).get('status')}）。",
        "## 检查清单",
    ]
    lines += [f"- [{'x' if r['ok'] else ' '}] {r['id']}: {r['detail']}"
              for r in ck.rows]
    lines += ["", f"**{ck.passed}/{len(ck.rows)} checks passed.**", ""]
    return "\n".join(lines)


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""F40 义务验收 recon（W2a-U03）：OCR 级联四端口 capability/未安装状态/
页块表格金标对照。

义务 06:F40（05:123）——PaddleOCR 基础线＋MinerU/Paddle-VL/PP-OCRv6/
MiniCPM-V 预留（「四端口」＝预留四个，级联登记=基础线+预留共 5 具名条目）；
本地基础 OCR 真实页块/表格输出；四端口能力与未安装状态明确（未安装如实
标注不装样子）。语料＝W2a-U01 全合成生成器产物（00-总协调 §6.1 裁决#1，
小集 30 页）；基础线引擎基准参考 D:\\文档处理（PaddleOCR GPU fail-closed、
模型缓存离线）。产品径＝implementation/python/legal_entry.py 桥
（ocr.* 方法组）→ anonymizer ocr_ports_service 公开面（同进程，
P09/P10 纪律）。

用法（juscite worktree w2a-u03 仓根 cwd）：
  python -X utf8 tools/recon/PENDING_OWNER_f40_ocr_ports_recon.py --profile desktop
  python -X utf8 tools/recon/PENDING_OWNER_f40_ocr_ports_recon.py --profile selfhost
  [--corpus <dir>] [--state <dir>] [--interpreter <path>]
  [--anonymizer-src <path>] [--skip-run]

退出码：0＝RECON_OK（硬门全过）；2＝RECON_FAIL；3＝环境缺失。
证据：docs/construction/evidence/F40/<profile>/ 下 JSON＋MD。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
import unicodedata
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
TEMP = Path(os.environ.get("TEMP", "."))
DEFAULT_INTERPRETER = Path(os.environ.get(
    "JUSCITE_F40_BASELINE_INTERPRETER",
    r"C:\Users\being\AppData\Local\pdf2md-venv\Scripts\python.exe"))
CORPUS_PAGES = 30
CORPUS_SEED = 20261015

EXPECTED_PORTS = ["paddleocr-baseline", "mineru", "paddle-vl", "pp-ocrv6",
                  "minicpm-v"]
EXPECTED_AUTHORITY_NAMES = {"paddleocr-baseline": "PaddleOCR 基础线",
                            "mineru": "MinerU", "paddle-vl": "Paddle-VL",
                            "pp-ocrv6": "PP-OCRv6", "minicpm-v": "MiniCPM-V"}
_READ_OK_FAMILY = {"read_ok", "rotation_page"}   # 语料侧可读页（recon 私用）


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


def corpus_identity_digest(corpus: Path) -> str:
    parts = [sha256_file(corpus / "corpus_manifest.json")]
    for p in sorted((corpus / "pages").rglob("*.png")):
        parts.append(p.relative_to(corpus).as_posix() + ":" + sha256_file(p))
    return hashlib.sha256("\n".join(parts).encode("utf-8")).hexdigest()


def resolve_anonymizer_src(explicit: str | None) -> str | None:
    """anonymizer w2a-u03 源定位：显式参 > 环境变量 > 同波 worktree 相对
    推断 > None（回退 .pth 主树——若缺 ocr_ports_service 会在 C01 报环境缺）。"""
    if explicit:
        return str(Path(explicit).resolve())
    env = os.environ.get("JUSCITE_ANONYMIZER_SRC")
    if env:
        return str(Path(env).resolve())
    # juscite worktree …/juscite/.local/worktrees/w2a-u03 → 同波 anonymizer
    # worktree …/legal-cn-anonymizer/.local/worktrees/w2a-u03/src
    guess = (REPO.parents[4] / "legal-cn-anonymizer工作区"
             / "legal-cn-anonymizer" / ".local" / "worktrees" / "w2a-u03"
             / "src")
    if (guess / "legal_anonymizer" / "application"
            / "ocr_ports_service.py").is_file():
        return str(guess)
    return None


def ensure_corpus(corpus: Path, pages: int, seed: int) -> bool:
    if (corpus / "corpus_manifest.json").is_file():
        return True
    corpus.parent.mkdir(parents=True, exist_ok=True)
    eprint(f"[GEN] 语料不存在，生成 {pages} 页 seed={seed} → {corpus}")
    proc = subprocess.run(
        [sys.executable, "-X", "utf8", str(REPO / "tools" / "e12_corpus_gen.py"),
         "--pages", str(pages), "--seed", str(seed), "--out", str(corpus)],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        timeout=600)
    if proc.returncode != 0:
        eprint(proc.stdout[-800:] or "", proc.stderr[-800:] or "")
        return False
    return (corpus / "corpus_manifest.json").is_file()


def load_bridge(anonymizer_src: str | None):
    sys.path.insert(0, str(REPO / "implementation" / "python"))
    if anonymizer_src:
        sys.path.insert(0, anonymizer_src)
    import legal_anonymizer
    from legal_entry import call as bridge_call
    return bridge_call, str(legal_anonymizer.__file__)


def load_gold(corpus: Path) -> dict:
    manifest = json.loads((corpus / "corpus_manifest.json")
                          .read_text(encoding="utf-8"))
    pages = []
    for doc in manifest["documents"]:
        for pf in doc["page_files"]:
            pages.append({"doc_id": doc["doc_id"], "page": pf["page"],
                          "kind": pf["kind"],
                          "expected_signal": pf["expected_signal"],
                          "page_no_gold": pf.get("page_no_gold"),
                          "png": pf["png"]})
    return {"manifest": manifest, "pages": pages, "tables": manifest["tables"]}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--profile", choices=["desktop", "selfhost"],
                    default="desktop")
    ap.add_argument("--corpus", type=Path,
                    default=TEMP / f"juscite-f40-corpus-{CORPUS_PAGES}")
    ap.add_argument("--state", type=Path, default=None)
    ap.add_argument("--interpreter", type=Path, default=DEFAULT_INTERPRETER)
    ap.add_argument("--anonymizer-src", default=None)
    ap.add_argument("--skip-run", action="store_true",
                    help="跳过跑批（要求状态已完成），只做对表")
    args = ap.parse_args()

    evidence_dir = REPO / "docs" / "construction" / "evidence" / "F40" / args.profile
    state = args.state or (TEMP / f"juscite-f40-state-{args.profile}")
    corpus = args.corpus.resolve()
    interpreter = args.interpreter.resolve()

    if not interpreter.is_file():
        eprint(f"[ENV-MISSING] 钉定解释器不存在：{interpreter}")
        return 3
    if not ensure_corpus(corpus, CORPUS_PAGES, CORPUS_SEED):
        eprint(f"[ENV-MISSING] 语料不可得：{corpus}")
        return 3
    anonymizer_src = resolve_anonymizer_src(args.anonymizer_src)
    bridge, anonymizer_file = load_bridge(anonymizer_src)
    if "w2a-u03" not in anonymizer_file:
        eprint(f"[ENV-MISSING] anonymizer 源不在 w2a-u03 树：{anonymizer_file}"
               "（用 --anonymizer-src 指定）")
        return 3
    config = {"anonymizer_contract": "p09/p10",
              "ocr_ports_state_root": str(state),
              "ocr_baseline_interpreter": str(interpreter)}

    gold = load_gold(corpus)
    checks: list[dict] = []
    metrics: dict[str, object] = {}
    started = now_iso()

    def record(name: str, ok: bool, detail) -> bool:
        checks.append({"name": name, "ok": bool(ok), "detail": str(detail)})
        print(f"[{'PASS' if ok else 'FAIL'}] {name}: {detail}", flush=True)
        return ok

    # ------------------------------------------------ C01 四端口具名 capability
    report = bridge("ocr.ports", {"interpreter": str(interpreter)},
                    {"anonymizer_contract": "p09/p10"})
    got_ids = [p["port_id"] for p in report["ports"]]
    named_ok = all(
        p["authority_name"] == EXPECTED_AUTHORITY_NAMES[p["port_id"]]
        and isinstance(p["declared_capability"], dict)
        and isinstance(p["declared_capability"].get("page_blocks"), bool)
        and isinstance(p["declared_capability"].get("tables"), bool)
        for p in report["ports"])
    record("C01_ports_named_capability",
           got_ids == EXPECTED_PORTS and named_ok
           and report["reserved_port_count"] == 4
           and report["cascade_entries"] == 5
           and [p["rank"] for p in report["ports"]] == [1, 2, 3, 4, 5],
           f"ports={got_ids} reserved=4/4 named={named_ok} "
           f"authority_line={report['authority_line'][:24]}…")

    # -------------------------------------------- C02 未安装如实（不装样子）
    ports_by_id = {p["port_id"]: p for p in report["ports"]}
    base = ports_by_id["paddleocr-baseline"]
    reserved_ok = True
    reserved_detail = []
    for pid in EXPECTED_PORTS[1:]:
        p = ports_by_id[pid]
        okc = (p["install_status"] == "NOT_INSTALLED"
               and p["installed"] is False
               and p["probe"]["rc"] == 0          # 探针真跑过且干净返回
               and p["probe"]["detail"])          # 有实测缺失证据
        reserved_ok = reserved_ok and okc
        reserved_detail.append(f"{pid}:{p['install_status']}"
                               f"({p['probe']['detail']})")
    record("C02_not_installed_honest",
           base["install_status"] == "INSTALLED"
           and base["installed"] is True
           and base["probe"]["rc"] == 0
           and base["probe"]["version"]
           and report["cascade_effective"] == ["paddleocr-baseline"]
           and reserved_ok,
           f"baseline=INSTALLED paddleocr {base['probe']['version']} "
           f"cascade={report['cascade_effective']} reserved=[{'; '.join(reserved_detail)}]")
    metrics["ports_report"] = report

    # ------------------------------------------------ C03 语料只读锚（跑前）
    digest_before = corpus_identity_digest(corpus)
    record("C03_corpus_anchor_before", True,
           f"sha256(identity)={digest_before[:16]}… pages={len(gold['pages'])} "
           f"tables={len(gold['tables'])}")

    # ------------------------------------------------ C04 基线真跑（页块分母）
    reg = bridge("ocr.baseline_register", {"corpus_root": str(corpus)},
                 config)
    run_id = reg["run_id"]
    pending_before = bridge("ocr.baseline_pending", {"run_id": run_id},
                            config)["pending"]
    if not args.skip_run and pending_before:
        t0 = time.time()
        run_out = bridge("ocr.baseline_run", {"run_id": run_id}, config)
        metrics["run_seconds"] = round(time.time() - t0, 1)
        print(f"[RUN] {run_out} ({metrics['run_seconds']}s)", flush=True)
    report_run = bridge("ocr.baseline_report", {"run_id": run_id}, config)
    sample_rec = bridge("ocr.baseline_page",
                        {"run_id": run_id, "doc_id": "doc_0001", "page": 1},
                        config)
    engine = sample_rec.get("engine") or {}
    engine_ok = (engine.get("engine") == "paddleocr"
                 and engine.get("device") == "gpu:0"
                 and engine.get("cuda_compiled") is True
                 and isinstance(engine.get("model_cache", {})
                                .get("files"), dict)
                 and engine["model_cache"]["files"])
    record("C04_baseline_real_run_engine_pinned",
           report_run["completed"] == report_run["registered_pages"]
           and report_run["error_pages"] == 0
           and report_run["corrupt_records"] == 0
           and report_run["pending"] == 0
           and engine_ok,
           f"completed={report_run['completed']}/"
           f"{report_run['registered_pages']} errors=0 "
           f"lines_total={report_run['lines_total']} "
           f"engine=paddleocr@{engine.get('paddleocr_version')} "
           f"paddle={engine.get('paddle_version')} device=gpu:0 "
           f"model_files={len(engine.get('model_cache', {}).get('files', {}))}")
    metrics["run_report"] = report_run

    # ------------------------------------------------ C05 页块真实（按页型）
    page_records = {}
    for g in gold["pages"]:
        rec = bridge("ocr.baseline_page",
                     {"run_id": run_id, "doc_id": g["doc_id"],
                      "page": g["page"]}, config)
        page_records[(g["doc_id"], g["page"])] = (g, rec)
    page_w, page_h = gold["manifest"].get("page_px", [992, 1403])
    from PIL import Image
    blocks_fail = []
    by_kind: dict[str, dict] = {}
    for key, (g, rec) in page_records.items():
        if rec.get("error"):
            blocks_fail.append(f"{key}:{rec['error']}")
            continue
        lines = rec.get("lines") or []
        # 页真实几何（旋转页宽高互换；PIL 实测，不猜）
        with Image.open(corpus / g["png"]) as _img:
            real_w, real_h = _img.size
        entry = by_kind.setdefault(g["expected_signal"],
                                   {"pages": 0, "lines_total": 0})
        entry["pages"] += 1
        entry["lines_total"] += len(lines)
        for line in lines:
            x0, y0, x1, y1 = line["bbox"]
            if not (-0.5 <= x0 < x1 <= real_w + 0.5
                    and -0.5 <= y0 < y1 <= real_h + 0.5
                    and 0.0 <= line["conf"] <= 1.0):
                blocks_fail.append(f"{key}:bbox/conf@{real_w}x{real_h}")
                break
        if g["expected_signal"] in _READ_OK_FAMILY and not lines:
            blocks_fail.append(f"{key}:readable_page_zero_lines")
    blanks = by_kind.get("blank", {})
    record("C05_page_blocks_real",
           not blocks_fail and bool(by_kind),
           f"failures={len(blocks_fail)}"
           + (f" e.g. {blocks_fail[:5]}" if blocks_fail else "")
           + f" by_signal={json.dumps(by_kind, ensure_ascii=False)}"
           + "（blank 页 0 行=诚实空输出，非装样子）")
    metrics["page_blocks_by_signal"] = by_kind

    # --------------------------------- C06 表格金标对照（结构硬门＋质量报告）
    table_fail = []
    rows_total = rows_exact = cells_total = cells_match = 0
    col_corr_total = col_corr_ok = 0
    mismatch_samples = []
    for tbl in gold["tables"]:
        asm = bridge("ocr.baseline_tables",
                     {"run_id": run_id, "doc_id": tbl["doc_id"]}, config)
        group = next((g for g in asm["groups"]
                      if g["pages"] == tbl["pages"]), None)
        if group is None:
            table_fail.append(f"{tbl['table_id']}:group_missing")
            continue
        gold_rows = tbl["reading_order_rows"]
        if group["columns"] != len(tbl["columns"]):
            table_fail.append(f"{tbl['table_id']}:cols={group['columns']}"
                              f"!={len(tbl['columns'])}")
        if len(group["rows"]) != len(gold_rows):
            table_fail.append(f"{tbl['table_id']}:rows={len(group['rows'])}"
                              f"!={len(gold_rows)}")
            continue
        order = [(r["page"], r["page_row_index"]) for r in group["rows"]]
        want = [(r["page"], r["page_row_index"]) for r in gold_rows]
        if order != want:
            table_fail.append(f"{tbl['table_id']}:reading_order_mismatch")
        for row, grow in zip(group["rows"], gold_rows):
            row_exact = True
            for gi, (cell, gcell) in enumerate(zip(row["cells"],
                                                   grow["cells"])):
                cells_total += 1
                want_text = None if norm(gcell["text"]) == "—" \
                    else norm(gcell["text"])
                got_text = norm(cell["text"]) if cell else None
                if got_text == want_text:
                    cells_match += 1
                    # 跨页行列对应（LegalTech 约束 3）：格心落金标列框
                    if cell and want_text:
                        col_corr_total += 1
                        gb = gcell["bbox_px"]
                        cx = (cell["bbox"][0] + cell["bbox"][2]) / 2
                        if gb[0] - 6 <= cx <= gb[2] + 6:
                            col_corr_ok += 1
                        else:
                            table_fail.append(
                                f"{tbl['table_id']}r{row['page_row_index']}"
                                f"c{gi}:column_drift")
                else:
                    row_exact = False
                    if len(mismatch_samples) < 12:
                        mismatch_samples.append(
                            f"{tbl['table_id']}p{row['page']}r"
                            f"{row['page_row_index']}c{gi}:"
                            f"{cell['text'] if cell else None!r}!={gcell['text']!r}")
            rows_total += 1
            rows_exact += 1 if row_exact else 0
    record("C06_table_gold_structure_hard_gate",
           not table_fail and rows_total > 0,
           f"tables={len(gold['tables'])} failures={len(table_fail)}"
           + (f" e.g. {table_fail[:5]}" if table_fail else "")
           + f" rows={rows_total} (阅读序=(页,页内行)全对表) "
           f"column_correspondence={col_corr_ok}/{col_corr_total}")
    metrics["table_cell_recognition"] = {
        "rows_total": rows_total, "rows_exact": rows_exact,
        "cells_total": cells_total, "cells_match": cells_match,
        "cell_match_rate": round(cells_match / cells_total, 6)
        if cells_total else None,
        "mismatch_samples": mismatch_samples,
        "note": "单元格文本识别质量＝基础线引擎实测（单字形期次漏检等），"
                "如实报告不设门；结构/序/列数/行列对应为硬门",
    }

    # ------------------------------------------- C07 表页页号 bbox 金标（硬门）
    pn_total = pn_present = pn_bbox_ok = pn_text_ok = 0
    for g in gold["pages"]:
        if g["kind"] not in ("TABLE_SPAN", "TABLE_CONT"):
            continue
        if not g["page_no_gold"]:
            continue
        pn_total += 1
        _, rec = page_records[(g["doc_id"], g["page"])]
        hits = [l for l in (rec.get("lines") or [])
                if re.fullmatch(r"-\d{1,4}-", norm(l["text"]))]
        if not hits:
            continue
        pn_present += 1
        best = max(hits, key=lambda l: l["conf"])
        gb = g["page_no_gold"]["bbox_px"]
        cx = (best["bbox"][0] + best["bbox"][2]) / 2
        cy = (best["bbox"][1] + best["bbox"][3]) / 2
        if gb[0] <= cx <= gb[2] and gb[1] <= cy <= gb[3]:
            pn_bbox_ok += 1
        m = re.search(r"\d+", norm(best["text"]))
        gm = re.search(r"\d+", g["page_no_gold"]["text"])
        if m and gm and m.group() == gm.group():
            pn_text_ok += 1
    record("C07_table_page_no_bbox_gold",
           pn_total > 0 and pn_present == pn_total
           and pn_bbox_ok == pn_total,
           f"table_pages={pn_total} extracted={pn_present} "
           f"bbox_in_gold={pn_bbox_ok}/{pn_total} text_ok={pn_text_ok}")

    # --------------------------------------- C08 语料只读锚（跑后）＋确定性抽样
    digest_after = corpus_identity_digest(corpus)
    readonly_ok = digest_after == digest_before
    det_sample, det_mismatch = [], []
    for kind_wanted in ("read_ok", "rotation_page", "low_confidence_or_fail"):
        for g in gold["pages"]:
            if g["expected_signal"] == kind_wanted:
                det_sample.append((g["doc_id"], g["page"]))
                break
    if det_sample:
        det_sample.append((gold["pages"][0]["doc_id"],
                           gold["pages"][0]["page"]))
    for doc_id, page in det_sample:
        rec = page_records.get((doc_id, page))
        if not rec:
            continue
        ppath = (state / "f40-baseline" / run_id / "pages" / doc_id
                 / f"p{page:04d}.json")
        ppath.unlink()
        bridge("ocr.baseline_run", {"run_id": run_id,
                                    "pages": [{"doc_id": doc_id,
                                               "page": page}]}, config)
        fresh = bridge("ocr.baseline_page",
                       {"run_id": run_id, "doc_id": doc_id, "page": page},
                       config)
        old_lines = rec[1].get("lines") or []
        new_lines = fresh.get("lines") or []
        same = len(old_lines) == len(new_lines)
        if same:
            for a, b in zip(old_lines, new_lines):
                if norm(a["text"]) != norm(b["text"]) or any(
                        abs(x - y) > 2.0 for x, y in zip(a["bbox"], b["bbox"])):
                    same = False
                    break
        if not same:
            det_mismatch.append(f"{doc_id}:p{page}")
    record("C08_originals_untouched_and_determinism",
           readonly_ok and not det_mismatch,
           f"anchor_before={digest_before[:16]}… after={digest_after[:16]}… "
           f"determinism_sample={len(det_sample)} mismatch={det_mismatch}")

    # ------------------------------------------------- C09 桥面 fail-closed
    from legal_entry import NotConnected
    fc_ok = True
    fc_detail = []
    for bad_config, want, method, payload in (
            ({}, "anonymizer_p09_p10_not_configured",
             "ocr.baseline_report", {"run_id": run_id}),
            ({"anonymizer_contract": "p09/p10"},
             "ocr_ports_state_root_not_configured",
             "ocr.baseline_report", {"run_id": run_id}),
            ({"anonymizer_contract": "p09/p10",
              "ocr_ports_state_root": str(state)},
             "ocr_baseline_interpreter_not_configured",
             "ocr.baseline_register", {"corpus_root": str(corpus)})):
        try:
            bridge(method, payload, bad_config)
            fc_ok = False
            fc_detail.append(f"{want}:NOT_RAISED")
        except NotConnected as exc:
            if want not in str(exc):
                fc_ok = False
                fc_detail.append(f"got:{exc}")
    try:
        bridge("ocr.explode", {}, config)
        fc_ok = False
        fc_detail.append("unknown_method:NOT_RAISED")
    except NotConnected as exc:
        if "method_not_connected:ocr.explode" not in str(exc):
            fc_ok = False
            fc_detail.append(f"got:{exc}")
    record("C09_bridge_fail_closed", fc_ok,
           "; ".join(fc_detail) if fc_detail else
           "contract/state/interpreter 三重 fail-closed＋未知方法拒")

    ok_all = all(c["ok"] for c in checks)
    verdict = "RECON_OK" if ok_all else "RECON_FAIL"
    evidence = {
        "verdict": verdict, "profile": args.profile,
        "started": started, "finished": now_iso(),
        "corpus": str(corpus), "pages": len(gold["pages"]),
        "state_root": str(state), "run_id": run_id,
        "interpreter": str(interpreter),
        "anonymizer_src": anonymizer_src,
        "anonymizer_resolved": anonymizer_file,
        "bridge_methods": ["ocr.ports", "ocr.baseline_register",
                           "ocr.baseline_run", "ocr.baseline_pending",
                           "ocr.baseline_report", "ocr.baseline_page",
                           "ocr.baseline_tables"],
        "checks": checks, "metrics": metrics,
        "scope_note": "本单 anonymizer＋桥面，无 PG 面；desktop/selfhost 双"
                      "实例共用同一宿主面分证记录（实例分化面挂部署轮，"
                      "F39 先例）",
    }
    evidence_dir.mkdir(parents=True, exist_ok=True)
    out_json = evidence_dir / "f40-ocr-ports-recon-result.json"
    out_json.write_text(json.dumps(evidence, ensure_ascii=False, indent=1),
                        encoding="utf-8")
    md = [f"# F40 OCR 级联四端口 recon（{args.profile}）",
          f"- verdict: **{verdict}**  profile={args.profile} "
          f"run_id={run_id}",
          f"- 语料: {corpus}（{len(gold['pages'])} 页全合成）"
          f" 引擎: paddleocr {base['probe']['version']} GPU",
          f"- anonymizer 源: {anonymizer_file}", ""]
    for c in checks:
        md.append(f"- {'✅' if c['ok'] else '❌'} **{c['name']}**: {c['detail']}")
    tcr = metrics.get("table_cell_recognition", {})
    md += ["", f"单元格识别质量（报告不设门）: {tcr.get('cells_match')}/"
           f"{tcr.get('cells_total')}"
           f"={tcr.get('cell_match_rate')}；失配样本 "
           f"{len(tcr.get('mismatch_samples', []))} 条见 JSON", ""]
    (evidence_dir / "f40-ocr-ports-recon-result.md").write_text(
        "\n".join(md), encoding="utf-8")
    print(f"\n{verdict}  checks={'/'.join('PASS' if c['ok'] else 'FAIL' for c in checks)}")
    print(f"evidence: {out_json}", flush=True)
    return 0 if ok_all else 2


if __name__ == "__main__":
    raise SystemExit(main())

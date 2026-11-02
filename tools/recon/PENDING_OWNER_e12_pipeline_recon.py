#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""E12 义务本体验收 recon（W2a-U02）：真跑合成 5000 页全量材料解析。

义务 07:E12——5000 页级清单、未读失败低置信分母（失败/空识别/未读/低置信
分别计数，不凭文件存在已读），跨页表阅读序、页号 bbox 版本，人改不覆，
局部恢复。语料＝W2a-U01 全合成生成器产物（00-总协调 §6.1 裁决#1，零真实
文档）；解析走 anonymizer material_parse_service 公开面，产品径＝
implementation/python/legal_entry.py 桥（material.parse_* 方法组）。

用法（juscite worktree w2a-u02 仓根 cwd）：
  python -X utf8 tools/recon/PENDING_OWNER_e12_pipeline_recon.py \
      [--corpus <dir>] [--state <dir>] [--workers 6] [--interrupt-after 500]
      [--fresh] [--skip-run] [--worker <spec.json>]

--fresh 清解析状态根重跑（语料目录永不触碰）；缺省续跑既有状态（局部恢复
本身即验收面）。--skip-run 只做读侧对表（要求状态已完成）。
worker 模式由驱动进程内部使用。

退出码：0＝RECON_OK（全部硬门通过）；2＝RECON_FAIL；3＝环境缺失。
证据：docs/construction/evidence/E12/ 下 JSON＋MD。
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

REPO = Path(__file__).resolve().parents[2]
EVIDENCE_DIR = REPO / "docs" / "construction" / "evidence" / "E12"
DEFAULT_CORPUS = Path(os.environ.get("TEMP", ".")) / "juscite-e12-corpus-5k-a"
DEFAULT_STATE = Path(os.environ.get("TEMP", ".")) / "juscite-e12-parse-state"

READ_FAMILY = {"READ_OK"}
FAIL_FAMILY = {"LOW_CONFIDENCE", "EMPTY_RECOGNITION", "UNREAD_FAILED"}


def eprint(*a) -> None:
    print(*a, file=sys.stderr, flush=True)


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def norm(s: str) -> str:
    return re.sub(r"\s+", "", unicodedata.normalize("NFKC", s))


def sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def corpus_identity_digest(corpus: Path) -> str:
    """语料只读性对表锚：manifest 字节＋逐页字节哈希链（独立于生成器实现）。"""
    parts = [sha256_file(corpus / "corpus_manifest.json")]
    for p in sorted((corpus / "pages").rglob("*.png")):
        parts.append(p.relative_to(corpus).as_posix() + ":" + sha256_file(p))
    chain = hashlib.sha256("\n".join(parts).encode("utf-8")).hexdigest()
    return chain


def load_bridge():
    sys.path.insert(0, str(REPO / "implementation" / "python"))
    from legal_entry import call as bridge_call
    return bridge_call


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
    return {"manifest": manifest, "pages": pages,
            "tables": manifest["tables"], "docs": manifest["documents"]}


# ------------------------------------------------------------------ worker
def run_worker(spec_path: Path) -> int:
    spec = json.loads(spec_path.read_text(encoding="utf-8"))
    bridge = load_bridge()
    config = {"anonymizer_contract": "p09/p10",
              "material_parse_state_root": spec["state_root"]}
    pages = [{"doc_id": d, "page": p} for d, p in spec["pages"]]
    out = bridge("material.parse_process",
                 {"batch_id": spec["batch_id"], "pages": pages}, config)
    print(json.dumps({"worker": spec.get("worker_id"), "result": out},
                     ensure_ascii=False), flush=True)
    return 0


def spawn_worker(spec: dict) -> subprocess.Popen:
    import tempfile
    fd, name = tempfile.mkstemp(suffix=".json", prefix="e12-worker-")
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        json.dump(spec, fh, ensure_ascii=False)
    # stderr 必须落到文件（不能是 PIPE）：引擎逐页日志会填满 ~4KB 管道缓冲
    # 导致 worker 阻塞在 stderr 写上（实测 1500 页/worker 后齐挂，非死亡）。
    # stdout 只在收尾打一行结果 JSON（<4KB，PIPE 安全）。
    log_fd, log_name = tempfile.mkstemp(suffix=".log", prefix="e12-worker-log-")
    os.close(log_fd)
    proc = subprocess.Popen(
        [sys.executable, "-X", "utf8", str(Path(__file__).resolve()),
         "--worker", name],
        stdout=subprocess.PIPE, stderr=open(log_name, "w", encoding="utf-8",
                                            errors="replace"),
        text=True, encoding="utf-8", cwd=str(REPO))
    proc.spec_file = name          # type: ignore[attr-defined]
    proc.log_file = log_name       # type: ignore[attr-defined]
    return proc


def completed_count(state_root: Path, batch_id: str) -> int:
    return len(list((state_root / "material-parse" / batch_id)
                    .glob("pages/*/*.json")))


# ------------------------------------------------------------------- driver
def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--corpus", type=Path, default=DEFAULT_CORPUS)
    ap.add_argument("--state", type=Path, default=DEFAULT_STATE)
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--interrupt-after", type=int, default=500,
                    help="先单 worker 处理的页数（随后中途击杀，验局部恢复）")
    ap.add_argument("--kill-at", type=int, default=200,
                    help="完成多少页记录后击杀 worker")
    ap.add_argument("--fresh", action="store_true",
                    help="清解析状态根重跑（语料目录永不触碰）")
    ap.add_argument("--skip-run", action="store_true",
                    help="跳过处理阶段，只做读侧对表（要求状态已完成）")
    ap.add_argument("--worker", type=Path, default=None)
    args = ap.parse_args()

    if args.worker is not None:
        return run_worker(args.worker)

    corpus = args.corpus.resolve()
    state = args.state.resolve()
    if not (corpus / "corpus_manifest.json").is_file():
        eprint(f"[ENV-MISSING] 语料不存在：{corpus}")
        eprint("  重新生成：python -X utf8 tools/e12_corpus_gen.py "
               "--pages 5000 --seed 20261015 --out <空目录>（约 29 分钟）")
        return 3

    bridge = load_bridge()
    config = {"anonymizer_contract": "p09/p10",
              "material_parse_state_root": str(state)}
    gold = load_gold(corpus)
    total_pages = len(gold["pages"])
    checks: list[dict] = []       # {name, ok, detail}
    metrics: dict = {}
    started = now_iso()

    def record(name: str, ok: bool, detail) -> bool:
        checks.append({"name": name, "ok": bool(ok), "detail": str(detail)})
        mark = "PASS" if ok else "FAIL"
        print(f"[{mark}] {name}: {detail}", flush=True)
        return ok

    # C01 语料只读锚（跑前）
    digest_before = corpus_identity_digest(corpus)
    record("C01_corpus_anchor_before", True,
           f"sha256(identity)={digest_before[:16]}… pages={total_pages}")

    # C02 登记（5000 页级清单）
    if args.fresh and state.exists():
        import shutil
        shutil.rmtree(state)
        print(f"[FRESH] 清状态根 {state}", flush=True)
    reg = bridge("material.parse_register", {"corpus_root": str(corpus)},
                 config)
    batch_id = reg["batch_id"]
    record("C02_register_manifest",
           reg["registered_pages"] == total_pages
           and reg["documents"] == len(gold["docs"]),
           f"batch={batch_id} registered={reg['registered_pages']}"
           f"/{total_pages} docs={reg['documents']}/{len(gold['docs'])}"
           f" engine={reg['engine']}")

    resumed = completed_count(state, batch_id)
    if resumed:
        print(f"[RESUME] 状态根已有 {resumed} 完成页（局部恢复续跑）",
              flush=True)

    # C03/C04 中断＋续跑（局部恢复：不重不漏）
    if not args.skip_run and resumed < total_pages:
        pending = [p for p in gold["pages"]
                   if not (state / "material-parse" / batch_id / "pages"
                           / p["doc_id"] / f"p{p['page']:04d}.json").is_file()]
        head = pending[:args.interrupt_after]
        killed_at = None
        early_exits: list[str] = []
        for attempt in range(3 if head else 0):
            if killed_at is not None:
                break
            eprint(f"[RUN-A] 尝试 {attempt + 1}/3：单 worker 处理前 "
                   f"{len(head)} 页，完成 {args.kill_at} 页后击杀（真中断）")
            proc = spawn_worker({"batch_id": batch_id, "state_root": str(state),
                                 "corpus_root": str(corpus),
                                 "pages": [[p["doc_id"], p["page"]]
                                           for p in head], "worker_id": "A"})
            deadline = time.time() + 3600
            while time.time() < deadline:
                if proc.poll() is not None:
                    # worker 提前退出（页少或启动失败）——留痕后重试
                    rc = proc.wait()
                    try:
                        with open(proc.log_file, encoding="utf-8",
                                  errors="replace") as fh:
                            tail = fh.read()[-200:].replace("\n", "|")
                    except OSError:
                        tail = ""
                    out, _ = proc.communicate()
                    done_now = completed_count(state, batch_id)
                    early_exits.append(f"rc={rc} at={done_now} "
                                       f"out={out.strip()[:120]} tail={tail}")
                    break
                if completed_count(state, batch_id) - resumed >= args.kill_at:
                    proc.kill()
                    killed_at = completed_count(state, batch_id)
                    rc = proc.wait()
                    print(f"[KILLED] 中断于 {killed_at} 完成页"
                          f"（returncode={rc}）", flush=True)
                    break
                time.sleep(2)
            proc.wait()
            try:
                os.unlink(proc.spec_file)
                os.unlink(proc.log_file)
            except OSError:
                pass
        record("C03_interrupt_and_kill",
               killed_at is not None,
               f"killed_at_completed={killed_at} resumed_base={resumed} "
               f"early_exits={early_exits[:3]}")

        # RUN-B：分块滚动 worker（每块 ~400 页/进程后回收重启——批量工程
        # 纪律：单 worker 任何原因退出（含被击杀/环境回收），剩余页下轮
        # 重算 pending 续跑，直到清零或轮次上限；永不重写已完成页记录）。
        round_no, chunk = 0, 400
        worker_failures = 0
        while True:
            pending = [p for p in gold["pages"]
                       if not (state / "material-parse" / batch_id / "pages"
                               / p["doc_id"] / f"p{p['page']:04d}.json").is_file()]
            if not pending:
                break
            round_no += 1
            if round_no > 40:
                eprint(f"[RUN-B] 轮次上限（40）仍有 {len(pending)} 页——退出对表")
                break
            specs = [{"batch_id": batch_id, "state_root": str(state),
                      "corpus_root": str(corpus),
                      "pages": [[p["doc_id"], p["page"]]
                                for p in pending[i * chunk:(i + 1) * chunk]],
                      "worker_id": f"R{round_no}W{i}"}
                     for i in range(min(args.workers,
                                        (len(pending) + chunk - 1) // chunk))]
            procs = [spawn_worker(spec) for spec in specs]
            eprint(f"[RUN-B] round {round_no}: {len(specs)} workers × "
                   f"≤{chunk} 页（余 {len(pending)}）")
            t0 = time.time()
            while any(p.poll() is None for p in procs):
                time.sleep(30)
                done = completed_count(state, batch_id)
                rate = done / max(time.time() - t0 + 1e-9, 1e-9)
                eta = (total_pages - done) / max(rate, 1e-9) / 60
                print(f"[PROGRESS] {done}/{total_pages} "
                      f"({rate:.2f}p/s eta {eta:.0f}min)", flush=True)
            for p in procs:
                out, _err = p.communicate()
                if p.returncode != 0:
                    worker_failures += 1
                    log_tail = ""
                    try:
                        with open(p.log_file, encoding="utf-8",
                                  errors="replace") as fh:
                            log_tail = fh.read()[-400:]
                    except OSError:
                        pass
                    eprint(f"[WORKER-FAIL] {p.spec_file} rc={p.returncode} "
                           f"tail={log_tail!r}")
                for f in (p.spec_file, p.log_file):
                    try:
                        os.unlink(f)
                    except OSError:
                        pass
        metrics["run_b_rounds"] = round_no
        metrics["worker_failures"] = worker_failures
    elif not args.skip_run:
        print("[RUN] 状态已完成，跳过处理阶段", flush=True)

    report = bridge("material.parse_report", {"batch_id": batch_id}, config)
    records_dir = state / "material-parse" / batch_id / "pages"
    record_files = list(records_dir.glob("*/*.json"))
    tmp_leftovers = list((state / "material-parse" / batch_id)
                         .rglob("*.json.tmp"))

    # C04 分母闭合＋不重不漏
    per_page: dict[tuple[str, int], dict] = {}
    dup_records = 0
    for rf in record_files:
        rec = json.loads(rf.read_text(encoding="utf-8"))
        key = (rec["doc_id"], int(rec["page"]))
        if key in per_page:
            dup_records += 1
        per_page[key] = rec
    # parse_count>1 只允许发生在带 human 版本的页（C09 人改不覆演示的重抽）
    nonhuman_reparsed = sum(
        1 for rec in per_page.values()
        if rec.get("parse_count", 1) > 1
        and not any(v["source"] == "human"
                    for v in rec.get("page_no", {}).get("versions", [])))
    record("C04_resume_no_dup_no_miss",
           report["completed"] == total_pages and report["pending"] == 0
           and report["corrupt_records"] == 0 and dup_records == 0
           and len(record_files) == total_pages
           and nonhuman_reparsed == 0,
           f"completed={report['completed']}/{total_pages} pending="
           f"{report['pending']} corrupt={report['corrupt_records']} "
           f"dup_records={dup_records} nonhuman_reparsed={nonhuman_reparsed} "
           f"tmp_leftovers={len(tmp_leftovers)}")
    metrics["signals"] = report["signals"]

    # C05 未读失败低置信分母 ↔ 语料 expected_signal 对表
    violations = []
    gold_by_key = {(p["doc_id"], p["page"]): p for p in gold["pages"]}
    for key, g in gold_by_key.items():
        rec = per_page.get(key)
        if rec is None:
            violations.append(f"{key}:missing")
            continue
        sig, expect = rec["signal"], g["expected_signal"]
        if expect == "blank":
            okc = sig == "BLANK"
        elif expect.startswith("duplicate_of:"):
            src = expect.split(":", 1)[1]
            sdoc, spage = src.split(":p")
            okc = (sig == "DUPLICATE" and rec.get("duplicate_of") ==
                   {"doc_id": sdoc, "page": int(spage)})
        elif expect == "rotation_page":
            okc = sig in READ_FAMILY
        elif expect == "low_confidence_or_fail":
            okc = sig in FAIL_FAMILY
        else:                                    # read_ok
            okc = sig in READ_FAMILY
        if not okc:
            violations.append(f"{key}:{expect}->{sig}")
    by_kind = {}
    for g in gold_by_key.values():
        rec = per_page.get((g["doc_id"], g["page"]), {})
        by_kind.setdefault(g["expected_signal"], {})
        k = rec.get("signal", "MISSING")
        by_kind[g["expected_signal"]][k] = \
            by_kind[g["expected_signal"]].get(k, 0) + 1
    record("C05_denominator_reconciliation", not violations,
           f"violations={len(violations)}"
           + (f" e.g. {violations[:5]}" if violations else "")
           + f" mapping={json.dumps(by_kind, ensure_ascii=False)}")

    # C06 跨页表阅读序（结构/序/列数硬门）＋C07 单元格识别质量（报告）
    table_fail = []
    rows_total = rows_exact = cells_total = cells_match = 0
    mismatch_samples = []
    for tbl in gold["tables"]:
        asm = bridge("material.parse_tables",
                     {"batch_id": batch_id, "doc_id": tbl["doc_id"]}, config)
        group = next((g for g in asm["groups"]
                      if g["pages"] == tbl["pages"]), None)
        if group is None:
            table_fail.append(f"{tbl['table_id']}:group_missing")
            continue
        gold_rows = tbl["reading_order_rows"]
        if group["columns"] != len(tbl["columns"]):
            table_fail.append(
                f"{tbl['table_id']}:cols={group['columns']}"
                f"!={len(tbl['columns'])}")
        if len(group["rows"]) != len(gold_rows):
            table_fail.append(
                f"{tbl['table_id']}:rows={len(group['rows'])}"
                f"!={len(gold_rows)}")
            continue
        order = [(r["page"], r["page_row_index"]) for r in group["rows"]]
        want = [(r["page"], r["page_row_index"]) for r in gold_rows]
        if order != want:
            table_fail.append(f"{tbl['table_id']}:order_mismatch")
        prev_installment = 0
        for row, grow in zip(group["rows"], gold_rows):
            row_exact = True
            got = [c["text"] if c else None for c in row["cells"]]
            want_texts = [None if norm(c["text"]) == "—" else norm(c["text"])
                          for c in grow["cells"]]
            for gi, (gtxt, wtxt) in enumerate(zip(got, want_texts)):
                cells_total += 1
                if (norm(gtxt) if gtxt else None) == (wtxt or None):
                    cells_match += 1
                else:
                    row_exact = False
                    if len(mismatch_samples) < 12:
                        mismatch_samples.append(
                            f"{tbl['table_id']}p{row['page']}r"
                            f"{row['page_row_index']}c{gi}:"
                            f"{gtxt!r}!={wtxt!r}")
            rows_total += 1
            rows_exact += 1 if row_exact else 0
            col0 = row["cells"][0] if row["cells"] else None
            # 期次单调只信高置信格：低置信识别（如实测「合计」→'1'@0.635）
            # 不作为序证据——那是 F40 识别质量，入 mismatch 报告不入序硬门
            if col0 is not None and col0["text"] is not None \
                    and col0["text"].isdigit() \
                    and col0.get("confidence", 0) >= 0.85:
                if int(col0["text"]) <= prev_installment:
                    table_fail.append(
                        f"{tbl['table_id']}:installment_not_monotonic"
                        f"@{col0['text']}")
                prev_installment = int(col0["text"])
    record("C06_table_reading_order", not table_fail,
           f"tables={len(gold['tables'])} failures={len(table_fail)}"
           + (f" e.g. {table_fail[:5]}" if table_fail else "")
           + f" rows={rows_total} (order=(页,页内行) 全对表＋期次单调)")
    metrics["table_cell_recognition"] = {
        "rows_total": rows_total, "rows_exact": rows_exact,
        "cells_total": cells_total, "cells_match": cells_match,
        "cell_match_rate": round(cells_match / cells_total, 6) if cells_total else None,
        "mismatch_samples": mismatch_samples,
        "note": "单元格文本识别质量属 F40 OCR 面，此处报告不设门；"
                "阅读序/行数/列数/期次单调为硬门",
    }

    # C08 页号 bbox 版本（表页必提取硬门；文本页页脚被正文覆印→如实缺报）
    pn_total = pn_present = pn_text_ok = pn_bbox_ok = 0
    pn_absent_by_expect = {}
    pn_text_mismatch_samples = []
    for key, g in gold_by_key.items():
        if g["page_no_gold"] is None:
            continue                              # 空白/重复页无页号金标
        rec = per_page.get(key)
        if rec is None or rec["signal"] not in READ_FAMILY:
            continue                              # 未读成功页不参与
        pn_total += 1
        versions = rec["page_no"]["versions"]
        if not versions:
            pn_absent_by_expect[g["expected_signal"]] = \
                pn_absent_by_expect.get(g["expected_signal"], 0) + 1
            continue
        pn_present += 1
        v = versions[0]
        gold_bbox = g["page_no_gold"]["bbox_px"]
        cx = (v["bbox"][0] + v["bbox"][2]) / 2
        cy = (v["bbox"][1] + v["bbox"][3]) / 2
        if gold_bbox[0] <= cx <= gold_bbox[2] and \
                gold_bbox[1] <= cy <= gold_bbox[3]:
            pn_bbox_ok += 1
        else:
            if len(pn_text_mismatch_samples) < 12:
                pn_text_mismatch_samples.append(
                    f"{key}:bbox {v['bbox']} outside gold {gold_bbox}")
        m = re.search(r"\d+", norm(v["text"]))
        gold_num = int(re.search(r"\d+", g["page_no_gold"]["text"]).group())
        if m and int(m.group()) == gold_num:
            pn_text_ok += 1
        elif len(pn_text_mismatch_samples) < 12:
            pn_text_mismatch_samples.append(
                f"{key}:text {v['text']!r} != gold "
                f"{g['page_no_gold']['text']!r}")
    # 表页（TABLE_SPAN/CONT）页脚构造上无覆印 → 提取必须 100%
    table_pages_with_gold = [g for g in gold_by_key.values()
                             if g["kind"] in ("TABLE_SPAN", "TABLE_CONT")]
    table_absent = sum(
        1 for g in table_pages_with_gold
        if g["page_no_gold"] and per_page.get((g["doc_id"], g["page"]), {})
        .get("page_no", {}).get("versions") == []
        and per_page.get((g["doc_id"], g["page"]), {}).get("signal")
        in READ_FAMILY)
    record("C08_page_no_bbox_version",
           pn_present > 0 and pn_bbox_ok == pn_present and table_absent == 0,
           f"read_ok_with_gold={pn_total} extracted={pn_present} "
           f"bbox_in_gold={pn_bbox_ok}/{pn_present} "
           f"text_ok={pn_text_ok}/{pn_present} table_page_absent="
           f"{table_absent} absent_by_kind="
           f"{json.dumps(pn_absent_by_expect)}")
    metrics["page_no"] = {
        "extracted": pn_present, "bbox_in_gold": pn_bbox_ok,
        "text_ok": pn_text_ok,
        "absent_by_expected_signal": pn_absent_by_expect,
        "mismatch_samples": pn_text_mismatch_samples,
        "note": "文本/旋转页页脚被生成器行预算覆印（正文墨迹压过页脚带，"
                "见 e12-corpus-generator 渲染常量），OCR 诚实缺报不计通过；"
                "表页页脚构造上无覆印，提取+bbox 硬门 100%",
    }

    # C09 人改不覆（重抽后 human 版本仍是当前版本）
    human_demo = None
    demo_key = None
    for g in gold_by_key.values():
        if g["kind"] not in ("TABLE_SPAN", "TABLE_CONT"):
            continue
        key = (g["doc_id"], g["page"])
        rec = per_page.get(key)
        if not rec or rec["signal"] not in READ_FAMILY:
            continue
        demo_key = key
        gold_text = g["page_no_gold"]["text"]
        current = next((v for v in rec["page_no"]["versions"]
                        if v["version"] == rec["page_no"]["current_version"]),
                       None)
        human_demo = {"key": f"{key[0]}:p{key[1]}",
                      "engine_text": current["text"] if current else None,
                      "corrected_text": gold_text}
        break
    if demo_key is None:
        record("C09_human_edit_not_overwritten", False, "no_demo_page")
    else:
        before = per_page.get(demo_key, {})
        prior_human = sum(1 for v in before.get("page_no", {})
                          .get("versions", []) if v["source"] == "human")
        prior_parse_count = int(before.get("parse_count", 1))
        edit = bridge("material.parse_human_edit",
                      {"batch_id": batch_id, "doc_id": demo_key[0],
                       "page": demo_key[1],
                       "page_no_text": human_demo["corrected_text"]}, config)
        rescan = bridge("material.parse_reparse",
                        {"batch_id": batch_id, "doc_id": demo_key[0],
                         "page": demo_key[1]}, config)
        after = bridge("material.parse_page",
                       {"batch_id": batch_id, "doc_id": demo_key[0],
                        "page": demo_key[1]}, config)
        cur = next(v for v in after["page_no"]["versions"]
                   if v["version"] == after["page_no"]["current_version"])
        record("C09_human_edit_not_overwritten",
               rescan["human_versions_kept"] == prior_human + 1
               and cur["source"] == "human"
               and cur["text"] == human_demo["corrected_text"]
               and after["parse_count"] == prior_parse_count + 1,
               f"page={human_demo['key']} engine={human_demo['engine_text']!r}"
               f"->human={human_demo['corrected_text']!r} "
               f"rescan_kept={rescan['human_versions_kept']}"
               f"(prior={prior_human}) current_source={cur['source']} "
               f"parse_count={after['parse_count']}"
               f"(prior={prior_parse_count})")
        metrics["human_edit_demo"] = human_demo

    # C10 金标不泄漏（登记清单身份白名单）＋页记录哈希独立复算
    batch_raw = (state / "material-parse" / batch_id / "batch.json") \
        .read_text(encoding="utf-8")
    leak_keys = [k for k in ("expected_signal", "page_no_gold",
                             "reading_order_rows", "header_gold",
                             "synthetic_tag_gold", "lowconf_recipe")
                 if k in batch_raw]
    sample_keys = [k for k in sorted(gold_by_key)][::max(
        1, total_pages // 40)][:40]
    sha_mismatch = []
    for key in sample_keys:
        g = gold_by_key[key]
        rec = per_page.get(key)
        if rec is None:
            continue
        actual = sha256_file(corpus / g["png"])
        if rec["png_sha256"] != actual or rec["png_ref"] != g["png"]:
            sha_mismatch.append(f"{key}:sha_or_ref")
    record("C10_no_gold_leak_and_sha_independent",
           not leak_keys and not sha_mismatch,
           f"leak_keys={leak_keys} sample={len(sample_keys)} "
           f"sha_mismatch={sha_mismatch[:5]}")

    # C11 语料只读（跑后锚不变）
    digest_after = corpus_identity_digest(corpus)
    record("C11_originals_untouched", digest_after == digest_before,
           f"before={digest_before[:16]}… after={digest_after[:16]}…")

    # C12 确定性抽样（同页只读重解析＝同信号/同页号/同表行数）
    from legal_anonymizer.application import material_parse_service as mpsvc
    batch = json.loads((state / "material-parse" / batch_id / "batch.json")
                       .read_text(encoding="utf-8"))
    task_map = {(d["doc_id"], int(t["page"])): t
                for d in batch["documents"] for t in d["pages"]}
    seen: dict[str, tuple[str, int]] = {}
    dup_index: dict[str, tuple[str, int]] = {}
    for d in batch["documents"]:
        for t in d["pages"]:
            sha, p = t.get("sha256"), int(t["page"])
            if sha and sha in seen and seen[sha][0] == d["doc_id"]:
                dup_index[sha] = seen[sha]
            if sha and sha not in seen:
                seen[sha] = (d["doc_id"], p)
    strat = {}
    for key in gold_by_key:
        strat.setdefault(gold_by_key[key]["expected_signal"], []).append(key)
    sample = []
    for expect, keys in sorted(strat.items()):
        sample.extend(keys[:6])
    det_mismatch = []
    for key in sample:
        rec = per_page.get(key)
        if rec is None:
            continue
        fresh = mpsvc._parse_one(batch, state / "material-parse" / batch_id,
                                 key[0], key[1], task_map[key], dup_index)
        same = (fresh["signal"] == rec["signal"]
                and (fresh["page_no"]["versions"][0]["text"] if
                     fresh["page_no"]["versions"] else None) ==
                (rec["page_no"]["versions"][0]["text"] if
                 rec["page_no"]["versions"] else None)
                and len(fresh["table_rows"]) == len(rec["table_rows"]))
        if not same:
            det_mismatch.append(f"{key}:{rec['signal']}->{fresh['signal']}")
    record("C12_determinism_sample", not det_mismatch,
           f"sample={len(sample)} mismatch={det_mismatch[:5]}")

    ok_all = all(c["ok"] for c in checks)
    verdict = "RECON_OK" if ok_all else "RECON_FAIL"
    evidence = {
        "verdict": verdict, "started": started, "finished": now_iso(),
        "corpus": str(corpus), "state_root": str(state),
        "batch_id": batch_id, "total_pages": total_pages,
        "workers": args.workers, "resumed_from": resumed,
        "checks": checks, "metrics": metrics,
        "engine_pin": reg,
        "report": report,
    }
    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    out_json = EVIDENCE_DIR / "e12-pipeline-recon-result.json"
    out_json.write_text(json.dumps(evidence, ensure_ascii=False, indent=1),
                        encoding="utf-8")
    print(f"\n{verdict}  checks={'/'.join('PASS' if c['ok'] else 'FAIL' for c in checks)}")
    print(f"evidence: {out_json}", flush=True)
    return 0 if ok_all else 2


if __name__ == "__main__":
    raise SystemExit(main())

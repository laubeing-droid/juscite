#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""F41 义务验收 recon（W2a-U16）：OCR 批量工程——串行限流/进度事件/取消/
单文档重抽/过期报告签名（双 profile 两实例）。

义务 06:F41（acceptance）「批量进度/限流/取消/重抽/过期版本真实；单件
失败可恢复无重写原件；过期报告签名及重抽版本不删」。细则 05:123
「GPU重任务与WordCOM限流，可暂停局部重跑，人改不覆」；08§2「重型OCR/GPU
与Word COM限流，施工不得影响用户现有任务」；08§3「扫描完成不等每页理解
正确；人审抽样另分母」。

产品径＝implementation/python/legal_entry.py 桥（ocr.batch_* 方法组）→
anonymizer ocr_batch_service 公开面（同进程，P09/P10 纪律）。引擎权威
=F40 ocr_ports_worker_baseline 钉定解释器子进程（GPU fail-closed·模型
sha256 钉定·绝不运行时下载，纪律沿用 F40）。

语料＝tools/e12_corpus_gen.py 全合成小集（60 页 3 卷，seed 20261017，
00-总协调 §6.1 裁决#1 零真实文档）；故障注入在派生副本语料上（主语料
只读锚跑前后不变）。本 recon 每次运行重建干净 %TEMP% 状态根（取消/续跑
生命周期需要未跑批状态）；显式 --state 已存在且非空=拒绝（不静默清用户
目录）。持久证据=docs/construction/evidence/F41/<profile>/ JSON＋MD。

用法（juscite worktree w2a-u16 仓根 cwd）：
  python -X utf8 tools/recon/PENDING_OWNER_f41_batch_recon.py --profile desktop --profile selfhost
  [--corpus <dir>] [--state <dir>] [--interpreter <path>] [--anonymizer-src <path>]

退出码：0＝全部 profile RECON_OK；2＝RECON_FAIL；3＝环境缺失。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
TEMP = Path(os.environ.get("TEMP", "."))
DEFAULT_INTERPRETER = Path(os.environ.get(
    "JUSCITE_F40_BASELINE_INTERPRETER",
    r"C:\Users\being\AppData\Local\pdf2md-venv\Scripts\python.exe"))
CORPUS_PAGES = 60
CORPUS_SEED = 20261017
MIN_DOCS = 3                 # 取消语义需要（已完成件＋pending 并存）
DOC_GAP_S = 0.5              # 显式限流窗（登记定格，事件时间戳可观测）
GAP_TOLERANCE = 0.05
FAULT_PAGE = 2               # 故障页=最小卷第 2 页（登记后改写字节）


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


def dir_digest(root: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    if root.is_dir():
        for p in sorted(root.rglob("*")):
            if p.is_file():
                out[p.relative_to(root).as_posix()] = sha256_file(p)
    return out


def corpus_identity_digest(corpus: Path) -> str:
    parts = [sha256_file(corpus / "corpus_manifest.json")]
    for p in sorted((corpus / "pages").rglob("*.png")):
        parts.append(p.relative_to(corpus).as_posix() + ":" + sha256_file(p))
    return hashlib.sha256("\n".join(parts).encode("utf-8")).hexdigest()


def resolve_anonymizer_src(explicit: str | None) -> Path | None:
    """anonymizer w2a-u16 源定位：显式参 > 环境变量 > 同波 worktree 相对
    推断 > None。必须有 ocr_batch_service（缺=环境缺，不回退主树装样子）。"""
    if explicit:
        return Path(explicit).resolve()
    env = os.environ.get("JUSCITE_ANONYMIZER_SRC")
    if env:
        return Path(env).resolve()
    # juscite worktree …/1.法律工作区/jusbench工作区/juscite/.local/…/w2a-u16
    # → anonymizer worktree …/1.法律工作区/legal-cn-anonymizer工作区/…
    root = REPO
    for _ in range(6):
        if root.name == "jusbench工作区":
            guess = (root.parent / "legal-cn-anonymizer工作区"
                     / "legal-cn-anonymizer" / ".local" / "worktrees"
                     / "w2a-u16" / "src")
            if (guess / "legal_anonymizer" / "application"
                    / "ocr_batch_service.py").is_file():
                return guess
            break
        root = root.parent
    return None


def ensure_corpus(corpus: Path) -> bool:
    if (corpus / "corpus_manifest.json").is_file():
        return True
    corpus.parent.mkdir(parents=True, exist_ok=True)
    eprint(f"[GEN] 语料不存在，生成 {CORPUS_PAGES} 页 seed={CORPUS_SEED} "
           f"→ {corpus}")
    proc = subprocess.run(
        [sys.executable, "-X", "utf8", str(REPO / "tools" / "e12_corpus_gen.py"),
         "--pages", str(CORPUS_PAGES), "--seed", str(CORPUS_SEED),
         "--out", str(corpus)],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        timeout=1200)
    if proc.returncode != 0:
        eprint((proc.stdout or "")[-800:], (proc.stderr or "")[-800:])
        return False
    return (corpus / "corpus_manifest.json").is_file()


def build_fault_corpus(main_corpus: Path, out: Path) -> Path | None:
    """派生故障语料（副本，每次重建保证原样起点；主语料零接触）：取首卷＋
    最小卷，页字节原样拷贝（清单登记 sha 不变）。"""
    try:
        if out.is_dir():
            shutil.rmtree(out)
        manifest = json.loads(
            (main_corpus / "corpus_manifest.json").read_text(encoding="utf-8"))
        docs = manifest["documents"]
        pick = [docs[0], min(docs, key=lambda d: d["page_count"])]
        if pick[0]["doc_id"] == pick[1]["doc_id"]:
            pick = [docs[0], docs[1]]
        (out / "pages").mkdir(parents=True)
        for doc in pick:
            for pf in doc["page_files"]:
                dst = out / pf["png"]
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(main_corpus / pf["png"], dst)
        sub = {k: v for k, v in manifest.items() if k != "documents"}
        sub["documents"] = pick
        sub["pages"] = sum(d["page_count"] for d in pick)
        (out / "corpus_manifest.json").write_text(
            json.dumps(sub, ensure_ascii=False), encoding="utf-8")
        return out
    except (OSError, KeyError, ValueError):
        return None


def load_bridge(anonymizer_src: Path):
    sys.path.insert(0, str(REPO / "implementation" / "python"))
    sys.path.insert(0, str(anonymizer_src))
    import legal_anonymizer
    from legal_entry import call as bridge_call
    return bridge_call, str(legal_anonymizer.__file__)


def run_profile(profile: str, args, corpus: Path, fault_corpus: Path,
                bridge) -> bool:
    """单 profile 全链真跑（C00-C11）。"""
    evidence_dir = REPO / "docs" / "construction" / "evidence" / "F41" / profile
    state = Path(args.state) if args.state \
        else (TEMP / f"juscite-f41-state-{profile}")
    if args.state is not None:
        # 显式状态根：非空=拒绝（不静默清用户目录）
        if state.exists() and any(state.iterdir()):
            eprint(f"[ENV-MISSING] 状态根非空（拒绝静默清理）：{state}")
            return False
    elif state.exists():
        # 默认 %TEMP% 状态根=recon 自有草稿（取消/续跑生命周期需干净起点）
        shutil.rmtree(state)
    state.mkdir(parents=True, exist_ok=True)
    config = {"anonymizer_contract": "p09/p10",
              "ocr_ports_state_root": str(state),
              "ocr_baseline_interpreter": str(args.interpreter)}

    checks: list[dict] = []
    metrics: dict[str, object] = {}
    started = now_iso()

    def record(name: str, ok: bool, detail) -> bool:
        checks.append({"name": name, "ok": bool(ok), "detail": str(detail)})
        print(f"[{'PASS' if ok else 'FAIL'}] {name}: {detail}", flush=True)
        return bool(ok)

    def finish(ok_all: bool) -> bool:
        verdict = "RECON_OK" if ok_all else "RECON_FAIL"
        evidence = {
            "verdict": verdict, "profile": profile,
            "started": started, "finished": now_iso(),
            "corpus": str(corpus), "pages": CORPUS_PAGES,
            "fault_corpus": str(fault_corpus),
            "interpreter": str(args.interpreter),
            "anonymizer_src": str(args.anonymizer_src),
            "bridge_methods": [
                "ocr.batch_register", "ocr.batch_run", "ocr.batch_cancel",
                "ocr.batch_status", "ocr.batch_events", "ocr.batch_pending",
                "ocr.batch_redraw", "ocr.batch_report",
                "ocr.batch_verify_reports", "ocr.batch_doc_version",
                "ocr.batch_secret_exposure"],
            "checks": checks, "metrics": metrics,
            "scope_note": "本单 anonymizer＋桥面（ocr.batch_* 十一方法）；"
                          "引擎权威=F40 worker（GPU fail-closed·模型 sha256 "
                          "钉定·绝不运行时下载）；桌面真机进度 UI 不前造"
                          "（进度面=公开面回读）；compose 宿主面挂 F02；"
                          "Word COM 限流面属 W2b 文书波不在本单",
        }
        evidence_dir.mkdir(parents=True, exist_ok=True)
        out_json = evidence_dir / "f41-ocr-batch-recon-result.json"
        out_json.write_text(json.dumps(evidence, ensure_ascii=False, indent=1),
                            encoding="utf-8")
        md = [f"# F41 OCR 批量工程 recon（{profile}）",
              f"- verdict: **{verdict}**  profile={profile} "
              f"batch={metrics.get('batch_id')}",
              f"- 语料: {corpus}（{CORPUS_PAGES} 页全合成，"
              f"{metrics.get('docs') or '?'} 卷 seed={CORPUS_SEED}）",
              f"- anonymizer 源: {args.anonymizer_src}", ""]
        for c in checks:
            md.append(f"- {'✅' if c['ok'] else '❌'} **{c['name']}**: "
                      f"{c['detail']}")
        md.append("")
        (evidence_dir / "f41-ocr-batch-recon-result.md").write_text(
            "\n".join(md), encoding="utf-8")
        print(f"\n[{profile}] {verdict}  checks="
              + "/".join("PASS" if c["ok"] else "FAIL" for c in checks))
        print(f"[{profile}] evidence: {out_json}", flush=True)
        return ok_all

    manifest = json.loads((corpus / "corpus_manifest.json")
                          .read_text(encoding="utf-8"))
    doc_ids = [d["doc_id"] for d in manifest["documents"]]
    doc_pages = {d["doc_id"]: d["page_count"] for d in manifest["documents"]}
    n_docs = len(doc_ids)
    metrics["docs"] = doc_pages
    if n_docs < MIN_DOCS:
        record("C00_corpus_multi_volume", False,
               f"docs={n_docs}<{MIN_DOCS}（取消语义需多卷；语料分卷随"
               f" seed 确定，seed={CORPUS_SEED} 应得 3 卷）")
        return finish(False)

    # -------------------------------------------- C01 登记与限流定格＋白名单
    digest_before = corpus_identity_digest(corpus)
    reg = bridge("ocr.batch_register",
                 {"corpus_root": str(corpus), "min_doc_gap_s": DOC_GAP_S},
                 config)
    batch_id = reg["batch_id"]
    metrics["batch_id"] = batch_id
    state_root_dir = state / "f41-batch" / batch_id
    batch_raw = (state_root_dir / "batch.json").read_text(encoding="utf-8")
    gold_leak = [k for k in ("expected_signal", "page_no_gold",
                             "reading_order_rows") if k in batch_raw]
    record("C01_register_limits_pinned",
           reg["limits"]["max_concurrency"] == 1
           and reg["limits"]["min_doc_gap_s"] == DOC_GAP_S
           and reg["counters"]["docs_pending"] == n_docs
           and not gold_leak
           and bool(reg["interpreter_sha256"]),
           f"batch={batch_id} limits={reg['limits']} "
           f"pending={reg['counters']['docs_pending']}/{n_docs} "
           f"金标零泄漏={not gold_leak} "
           f"interp_sha={reg['interpreter_sha256'][:12]}…")

    # --------------------------- C02 真跑（线程）＋中途取消＋进度事件流回读
    cancel_after = max(1, n_docs - 2)
    run_out: dict = {}

    def _runner():
        try:
            run_out["result"] = bridge("ocr.batch_run",
                                       {"batch_id": batch_id}, config)
        except Exception as exc:                    # noqa: BLE001 - 如实入证
            run_out["error"] = f"{type(exc).__name__}: {exc}"

    th = threading.Thread(target=_runner)
    th.start()
    observed: list[dict] = []
    deadline = time.time() + 3600
    while time.time() < deadline and th.is_alive():
        after = observed[-1]["seq"] if observed else 0
        ev = bridge("ocr.batch_events",
                    {"batch_id": batch_id, "after_seq": after}, config)
        observed.extend(ev["events"])
        done = sum(1 for e in observed if e["type"] == "doc_completed")
        if done >= cancel_after:
            try:
                metrics["cancel_echo"] = bridge(
                    "ocr.batch_cancel", {"batch_id": batch_id}, config)
            except Exception as exc:                # noqa: BLE001 - 如实入证
                # 跑批先于取消完成（观测窗极快时）——C03 会响亮失败
                metrics["cancel_echo_error"] = f"{type(exc).__name__}: {exc}"
            break
        time.sleep(0.5)
    th.join(timeout=3600)
    if "error" in run_out:
        record("C02_progress_events_monotonic_pollable", False,
               f"跑批线程异常：{run_out['error']}")
        return finish(False)
    first_run = run_out.get("result") or {}
    metrics["first_run"] = first_run

    events_all = bridge("ocr.batch_events", {"batch_id": batch_id},
                        config)["events"]
    seqs = [e["seq"] for e in events_all]
    done_seq = [e["counters"]["docs_done"] for e in events_all]
    pend_seq = [e["counters"]["docs_pending"] for e in events_all]
    # 轮询窗口内观测的 done 前缀计数单调不减（增量回读 after_seq）
    obs_done = []
    for e in observed:
        if e["type"] == "doc_completed":
            obs_done.append(e["counters"]["docs_done"])
    record("C02_progress_events_monotonic_pollable",
           seqs == list(range(1, len(seqs) + 1))
           and done_seq == sorted(done_seq)
           and pend_seq == sorted(pend_seq, reverse=True)
           and obs_done == sorted(obs_done)
           and len(observed) >= cancel_after,
           f"事件 seq 连续 1..{len(seqs)}；done 单调不降＋pending 单调不增；"
           f"轮询增量回读观测 {len(observed)} 条（cancel 阈值 "
           f"{cancel_after} 件完成时命中）；done 观测序={obs_done}")

    # ------------------------------------------------ C03 取消语义（硬门）
    status_mid = bridge("ocr.batch_status", {"batch_id": batch_id}, config)
    completed_mid = [d for d in status_mid["documents"]
                     if d["last_outcome"] in ("ok", "error_pages")]
    version_readable = True
    for d in completed_mid:
        rec = bridge("ocr.batch_doc_version",
                     {"batch_id": batch_id, "doc_id": d["doc_id"]}, config)
        if rec["doc"]["pages_ok"] + rec["doc"]["error_pages"] != d["pages"]:
            version_readable = False
    record("C03_cancel_preserves_done_and_pending",
           first_run.get("status") == "CANCELLED"
           and len(completed_mid) >= 1
           and first_run.get("pending_after") == status_mid["pending"]
           and len(status_mid["pending"]) >= 1
           and version_readable
           and "batch_cancel_requested" in {e["type"] for e in events_all}
           and "batch_cancelled" in {e["type"] for e in events_all},
           f"status={first_run.get('status')} 已完成件={len(completed_mid)}"
           f"（页数对账可回读={version_readable}） "
           f"pending={status_mid['pending']} 取消请求/确认事件在列")

    # --------------------------------------- C04 续跑（不重不漏）＋三方对账
    resume_out = bridge("ocr.batch_run", {"batch_id": batch_id}, config) \
        if status_mid["pending"] else {"status": status_mid["status"]}
    events_resume = bridge("ocr.batch_events", {"batch_id": batch_id},
                           config)["events"]
    status_final = bridge("ocr.batch_status", {"batch_id": batch_id}, config)
    per_doc_completions: dict[str, int] = {}
    for e in events_resume:
        if e["type"] == "doc_completed":
            per_doc_completions[e["doc_id"]] = \
                per_doc_completions.get(e["doc_id"], 0) + 1
    versions_ok = all(d["current_version"] == 1
                      for d in status_final["documents"])
    report_final = bridge("ocr.batch_report", {"batch_id": batch_id}, config)
    report_counts = report_final["latest"]["counters"]
    record("C04_resume_no_dup_no_leak_reconciled",
           resume_out.get("status") == "COMPLETED"
           and per_doc_completions == {d: 1 for d in doc_ids}
           and versions_ok
           and sum(1 for e in events_resume
                   if e["type"] == "batch_resumed") == 1
           and report_counts["docs_done"] == n_docs
           and report_counts["docs_pending"] == 0,
           f"续跑={resume_out.get('status')}；每件恰一次 doc_completed="
           f"{per_doc_completions == {d: 1 for d in doc_ids}}；"
           f"全部 current_version=1={versions_ok}；事件/盘上/报告三方对账 "
           f"{report_counts}")

    # ------------------------------------- C05 串行限流可实测观测（并发=1）
    wins: dict[str, dict] = {}
    for e in events_resume:
        if e["type"] == "doc_started":
            wins.setdefault(e["doc_id"], {})["start"] = e["ts_epoch"]
        elif e["type"] == "doc_completed":
            wins.setdefault(e["doc_id"], {})["end"] = e["ts_epoch"]
    ordered = sorted((w for w in wins.values()
                      if "start" in w and "end" in w),
                     key=lambda w: w["start"])
    overlaps = sum(1 for a, b in zip(ordered, ordered[1:])
                   if b["start"] < a["end"] - 1e-6)
    gaps = [round(b["start"] - a["end"], 3) for a, b in zip(ordered,
                                                            ordered[1:])]
    pids = [e.get("engine_pid") for e in events_resume
            if e["type"] == "doc_completed"]
    record("C05_serial_limit_observable",
           overlaps == 0 and len(ordered) >= 2
           and all(g >= DOC_GAP_S - GAP_TOLERANCE for g in gaps)
           and all(isinstance(p, int) for p in pids),
           f"观察窗重叠={overlaps}（并发≤1）；文档间隔={gaps}s 全≥"
           f"{DOC_GAP_S}-{GAP_TOLERANCE}（显式限流窗）；"
           f"engine_pids={pids}（逐件独立引擎进程）")

    # ------------------------- C06 单文档重抽：新版本＋旧版本/他件/原件不动
    redraw_doc = min(doc_ids, key=lambda d: doc_pages[d])
    docs_before = {d: dir_digest(state_root_dir / "docs" / d)
                   for d in doc_ids}
    reports_before = dir_digest(state_root_dir / "reports")
    redraw = bridge("ocr.batch_redraw",
                    {"batch_id": batch_id, "doc_id": redraw_doc}, config)
    others_untouched = all(
        dir_digest(state_root_dir / "docs" / d) == docs_before[d]
        for d in doc_ids if d != redraw_doc)
    v1_unchanged = all(
        dir_digest(state_root_dir / "docs" / redraw_doc).get(p) == h
        for p, h in docs_before[redraw_doc].items()
        if p.startswith("v0001/"))
    reports_after = dir_digest(state_root_dir / "reports")
    old_version = bridge("ocr.batch_doc_version",
                         {"batch_id": batch_id, "doc_id": redraw_doc,
                          "version": 1}, config)
    current_version = bridge("ocr.batch_doc_version",
                             {"batch_id": batch_id, "doc_id": redraw_doc},
                             config)
    record("C06_redraw_new_version_old_bytes_untouched",
           redraw.get("version") == 2 and redraw.get("previous_version") == 1
           and others_untouched and v1_unchanged
           and all(reports_after.get(p) == h
                   for p, h in reports_before.items())
           and len(reports_after) > len(reports_before)
           and not old_version["is_current"]
           and current_version["version"] == 2,
           f"重抽件={redraw_doc}（{doc_pages[redraw_doc]} 页）v1→v2；"
           f"他件字节不动={others_untouched}；v1 逐字节不变={v1_unchanged}；"
           f"旧报告不删＋新报告追加；current 指针=v2、v1 仍可回读")

    # ------------------------- C07 过期报告签名：验签过＋篡改负向＋密钥不漏
    verify = bridge("ocr.batch_verify_reports",
                    {"batch_id": batch_id}, config)
    rows = {r["report_seq"]: r for r in verify["reports"]}
    expired_seqs = [s for s, r in rows.items() if r["expired"]]
    expired_valid = all(rows[s]["valid"] for s in expired_seqs)
    r1_path = state_root_dir / "reports" / "report-0001.json"
    tamper_detected = False
    original_bytes = r1_path.read_bytes()
    try:
        forged = json.loads(original_bytes.decode("utf-8"))
        forged["content"]["counters"]["docs_done"] = 999
        r1_path.write_bytes(
            json.dumps(forged, ensure_ascii=False).encode("utf-8"))
        bad = bridge("ocr.batch_verify_reports",
                     {"batch_id": batch_id}, config)
        tamper_detected = (
            not bad["all_valid"]
            and not [r for r in bad["reports"]
                     if r["report_seq"] == 1][0]["valid"])
    finally:
        r1_path.write_bytes(original_bytes)
    restored_ok = bridge("ocr.batch_verify_reports",
                         {"batch_id": batch_id}, config)["all_valid"]
    exposure = bridge("ocr.batch_secret_exposure",
                      {"batch_id": batch_id}, config)
    record("C07_report_signature_tamper_negative",
           verify["all_valid"] and expired_valid
           and tamper_detected and restored_ok
           and not exposure["exposed"],
           f"全部 {len(rows)} 份报告验签过（seq={sorted(rows)}）；过期报告 "
           f"{expired_seqs} 验签仍过（不删）；篡改计数→拒="
           f"{tamper_detected}→字节恢复→过={restored_ok}；密钥扫描 "
           f"{exposure['scanned_files']} 产物文件零暴露")

    # ------------------------- C08 故障注入（派生副本语料）：单件失败可恢复
    fault_manifest = json.loads(
        (fault_corpus / "corpus_manifest.json").read_text(encoding="utf-8"))
    fault_doc_ids = [d["doc_id"] for d in fault_manifest["documents"]]
    target_doc = min(fault_doc_ids,
                     key=lambda d: next(x["page_count"]
                                        for x in fault_manifest["documents"]
                                        if x["doc_id"] == d))
    fault_page_rel = next(
        pf["png"] for d in fault_manifest["documents"]
        if d["doc_id"] == target_doc
        for pf in d["page_files"] if pf["page"] == FAULT_PAGE)
    page_original = (fault_corpus / fault_page_rel).read_bytes()
    fault_ok = False
    fault_detail = ""
    try:
        (fault_corpus / fault_page_rel).write_bytes(
            b"F41-SYNTHETIC-FAULT-INJECTION")
        freg = bridge("ocr.batch_register",
                      {"corpus_root": str(fault_corpus)}, config)
        frun = bridge("ocr.batch_run", {"batch_id": freg["batch_id"]}, config)
        fdoc = bridge("ocr.batch_doc_version",
                      {"batch_id": freg["batch_id"], "doc_id": target_doc},
                      config)
        others_clean = all(
            bridge("ocr.batch_doc_version",
                   {"batch_id": freg["batch_id"], "doc_id": d},
                   config)["doc"]["error_pages"] == 0
            for d in fault_doc_ids if d != target_doc)
        # 恢复：修回页字节 → 单件重抽出干净新版本（其余件零接触）
        (fault_corpus / fault_page_rel).write_bytes(page_original)
        frec = bridge("ocr.batch_redraw",
                      {"batch_id": freg["batch_id"], "doc_id": target_doc},
                      config)
        fv2 = bridge("ocr.batch_doc_version",
                     {"batch_id": freg["batch_id"], "doc_id": target_doc},
                     config)
        page_restored = ((fault_corpus / fault_page_rel).read_bytes()
                         == page_original)
        fault_ok = (frun["status"] == "COMPLETED"
                    and fdoc["doc"]["error_pages"] == 1
                    and fdoc["doc"]["error_codes"].get(
                        "page_bytes_mismatch") == 1
                    and others_clean
                    and frec["error_pages"] == 0
                    and fv2["doc"]["error_pages"] == 0
                    and fv2["version"] == 2
                    and page_restored)
        fault_detail = (
            f"故障件={target_doc}:p{FAULT_PAGE} 登记后改写→"
            f"page_bytes_mismatch 拒跑（原件只读红线）；批次="
            f"{frun['status']}（不阻断）他件零错={others_clean}；修页后"
            f"单件重抽 v1→v2 error_pages 1→0；副本页字节复原="
            f"{page_restored}")
        metrics["fault_recovery"] = {
            "fault_doc": target_doc, "fault_page": FAULT_PAGE,
            "run_status": frun["status"],
            "v1_error_codes": fdoc["doc"]["error_codes"],
            "v2_error_pages": fv2["doc"]["error_pages"]}
    except Exception as exc:                        # noqa: BLE001 - 如实入证
        fault_detail = f"故障注入段异常：{type(exc).__name__}"
        try:                                        # 副本页字节尽力复原
            (fault_corpus / fault_page_rel).write_bytes(page_original)
        except OSError:
            pass
    record("C08_fault_page_injection_recoverable", fault_ok, fault_detail)

    # ------------------------------- C09 引擎钉定纪律（GPU fail-closed 真跑）
    sample = bridge("ocr.batch_doc_version",
                    {"batch_id": batch_id, "doc_id": doc_ids[0]}, config)
    engine = sample["doc"].get("engine") or {}
    model_files = (engine.get("model_cache") or {}).get("files") or {}
    record("C09_engine_pinning_f40_discipline",
           engine.get("engine") == "paddleocr"
           and engine.get("device") == "gpu:0"
           and engine.get("cuda_compiled") is True
           and bool(model_files),
           f"engine=paddleocr@{engine.get('paddleocr_version')} "
           f"paddle={engine.get('paddle_version')} device=gpu:0 "
           f"cuda_compiled={engine.get('cuda_compiled')} "
           f"模型文件 sha256 钉定={len(model_files)} 个 "
           f"worker_pid={engine.get('engine_pid')}")

    # --------------------------------------------- C10 桥面 fail-closed
    from legal_entry import NotConnected
    fc_ok = True
    fc_detail = []
    for bad_config, want, method, payload in (
            ({}, "anonymizer_p09_p10_not_configured",
             "ocr.batch_status", {"batch_id": batch_id}),
            ({"anonymizer_contract": "p09/p10"},
             "ocr_ports_state_root_not_configured",
             "ocr.batch_status", {"batch_id": batch_id}),
            ({"anonymizer_contract": "p09/p10",
              "ocr_ports_state_root": str(state)},
             "ocr_baseline_interpreter_not_configured",
             "ocr.batch_register", {"corpus_root": str(corpus)})):
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
    record("C10_bridge_fail_closed", fc_ok,
           "; ".join(fc_detail) if fc_detail else
           "contract/state/interpreter 三重 fail-closed＋未知方法拒")

    # --------------------------------------- C11 语料只读锚（跑后不变）
    digest_after = corpus_identity_digest(corpus)
    record("C11_corpus_readonly_anchor",
           digest_after == digest_before,
           f"before={digest_before[:16]}… after={digest_after[:16]}… "
           f"{'不变' if digest_after == digest_before else '漂移！'}")
    metrics["events_total"] = len(events_resume)
    metrics["report_seqs"] = sorted(rows)
    return finish(all(c["ok"] for c in checks))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--profile", action="append",
                    choices=["desktop", "selfhost"], default=None)
    ap.add_argument("--corpus", type=Path,
                    default=TEMP / f"juscite-f41-corpus-{CORPUS_PAGES}")
    ap.add_argument("--state", type=Path, default=None,
                    help="显式状态根（须不存在或为空；默认按 profile 分 "
                         "%TEMP% 独立根，且每次运行重建）")
    ap.add_argument("--interpreter", type=Path, default=DEFAULT_INTERPRETER)
    ap.add_argument("--anonymizer-src", default=None)
    args = ap.parse_args()
    profiles = args.profile or ["desktop"]

    if not args.interpreter.is_file():
        eprint(f"[ENV-MISSING] 钉定解释器不存在：{args.interpreter}")
        return 3
    corpus = args.corpus.resolve()
    if not ensure_corpus(corpus):
        eprint(f"[ENV-MISSING] 语料不可得：{corpus}")
        return 3
    anonymizer_src = resolve_anonymizer_src(args.anonymizer_src)
    if anonymizer_src is None:
        eprint("[ENV-MISSING] anonymizer w2a-u16 源不可得"
               "（--anonymizer-src 指定）")
        return 3
    args.anonymizer_src = anonymizer_src
    if args.state is not None:
        args.state = args.state.resolve()
    bridge, resolved = load_bridge(anonymizer_src)
    if "w2a-u16" not in resolved:
        eprint(f"[ENV-MISSING] anonymizer 源不在 w2a-u16 树：{resolved}")
        return 3
    print(f"[ENV] anonymizer={resolved}")

    fault_corpus = TEMP / f"juscite-f41-faultcorpus-{CORPUS_PAGES}"
    built = build_fault_corpus(corpus, fault_corpus)
    if built is None:
        eprint("[ENV-MISSING] 派生故障语料构建失败")
        return 3
    print(f"[ENV] 故障语料（派生副本，主语料零接触）: {fault_corpus}")

    all_ok = True
    for profile in profiles:
        print(f"\n===== profile {profile} =====", flush=True)
        if args.state is not None and profile != profiles[0]:
            eprint("[ENV-MISSING] 显式 --state 只支持单 profile 运行")
            return 3
        all_ok = run_profile(profile, args, corpus, fault_corpus, bridge) \
            and all_ok
    print(f"\n{'RECON_OK' if all_ok else 'RECON_FAIL'}"
          f"（profiles={profiles}）")
    return 0 if all_ok else 2


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""F86 义务验收 recon（W2a-U07）：前后端阅读序同源——共享固定样例集双端序
一致性＋三类命中高亮（页段/表格/扫描OCR命中）。

义务 06:F86 断言：「前后端阅读序同源固定样例全一致；高亮页段/表格/扫描
OCR 命中」（引用命中属 E14 接线/W2b，不在本单）。python_entry_binding＝
原生 OpenCode UI/host（17 卡）：后端＝产品 Python 桥（legal_entry
material.parse_* / reading.*）；前端＝原生 UI 投影（patch 013
reading-order.ts 纯投影模块，桌面 seam window.lvyinReading 同一消费方）。

固定样例集＝W2a-U01 全合成语料生成器（seed 钉定，同 W2a-U02 语料源）＋
W2a-U02 解析产物（material.parse_* 真跑落盘）。

双端一致性＝后端规范阅读序文档（reading.document）与**前端投影模块真跑**
（从交付补丁 013 中原样抽出的 reading-order.ts，Bun 执行）对同一夹具各出
id 序列与三类命中，逐项相等；序哈希由 Python 对前端输出重算复核。

用法（juscite worktree w2a-u07 仓根 cwd）：
  python -X utf8 tools/PENDING_OWNER_f86_reading_order_recon.py --profile desktop
  python -X utf8 tools/PENDING_OWNER_f86_reading_order_recon.py --profile selfhost
  [--corpus <dir>] [--state <dir>] [--bun <path>] [--skip-parse]

退出码：0＝RECON_OK（硬门全过）；2＝RECON_FAIL；3＝环境缺失。
证据：docs/construction/evidence/F86/<profile>/ 下 JSON＋MD。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
TEMP = Path(os.environ.get("TEMP", "."))
BRIDGE = REPO / "implementation" / "python" / "legal_entry.py"
PATCH = REPO / "implementation" / "patches" / "013-f86-reading-surface.patch"
# worktree …/juscite/.local/worktrees/w2a-u07 → parents[3]＝jusbench工作区
OC28 = REPO.parents[3] / "oc28"
BUN = Path(os.environ.get("JUSCITE_BUN", str(Path.home() / ".bun" / "bun.exe")))

CORPUS_PAGES = 30          # 固定样例集（同 F40 语料参数：seed 20261015）
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


def corpus_identity_digest(corpus: Path) -> str:
    parts = [sha256_file(corpus / "corpus_manifest.json")]
    for p in sorted((corpus / "pages").rglob("*.png")):
        parts.append(p.relative_to(corpus).as_posix() + ":" + sha256_file(p))
    return hashlib.sha256("\n".join(parts).encode("utf-8")).hexdigest()


def ensure_corpus(corpus: Path) -> bool:
    if (corpus / "corpus_manifest.json").is_file():
        return True
    corpus.parent.mkdir(parents=True, exist_ok=True)
    eprint(f"[GEN] 固定样例语料不存在，生成 {CORPUS_PAGES} 页 "
           f"seed={CORPUS_SEED} → {corpus}")
    proc = subprocess.run(
        [sys.executable, "-X utf8", str(REPO / "tools" / "e12_corpus_gen.py"),
         "--pages", str(CORPUS_PAGES), "--seed", str(CORPUS_SEED),
         "--out", str(corpus)],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        timeout=900)
    if proc.returncode != 0:
        eprint((proc.stdout or "")[-800:], (proc.stderr or "")[-800:])
        return False
    return (corpus / "corpus_manifest.json").is_file()


def bridge_call(config: dict, method: str, args: dict,
                expect_exit: int = 0) -> tuple[int, dict]:
    """真桥 CLI 子进程径（与桌面 main 进程 reading-surface.ts 完全同形）：
    python -X utf8 legal_entry.py --request-json --config。"""
    with tempfile.NamedTemporaryFile(
            "w", encoding="utf-8", suffix=".json", delete=False) as req, \
         tempfile.NamedTemporaryFile(
            "w", encoding="utf-8", suffix=".json", delete=False) as cfg:
        json.dump({"method": method, "args": args}, req, ensure_ascii=False)
        json.dump(config, cfg, ensure_ascii=False)
        req_name, cfg_name = req.name, cfg.name
    try:
        proc = subprocess.run(
            [sys.executable, "-X", "utf8", str(BRIDGE),
             "--request-json", req_name, "--config", cfg_name],
            capture_output=True, text=True, encoding="utf-8",
            errors="replace", timeout=1800)
        payload = {}
        if proc.stdout.strip():
            try:
                payload = json.loads(proc.stdout)
            except json.JSONDecodeError:
                payload = {"raw": proc.stdout[-400:]}
        return proc.returncode, payload
    finally:
        os.unlink(req_name)
        os.unlink(cfg_name)


def extract_reading_order_ts() -> str:
    """从交付补丁 013 原样抽出 reading-order.ts（测交付物本体，不是副本）。"""
    text = PATCH.read_text(encoding="utf-8")
    m = re.search(
        r"\+\+\+ b/packages/app/src/legal-workbench/reading-order\.ts\n"
        r"@@ -0,0 \+1,(\d+) @@\n((?:\+.*\n)+)",
        text)
    if not m or not m.group(2):
        raise RuntimeError("reading-order.ts section not found in patch 013")
    lines = [line[1:] for line in m.group(2).splitlines()
             if line.startswith("+")]
    if len(lines) != int(m.group(1)):
        raise RuntimeError("reading-order.ts line count mismatch: "
                           f"{len(lines)} != {m.group(1)}")
    return "\n".join(lines) + "\n"


def run_frontend_projection(doc_payload: dict, selectors: dict) -> dict:
    """前端投影真跑：Bun 执行补丁抽出的 reading-order.ts（零依赖纯模块）。"""
    work = Path(tempfile.mkdtemp(prefix="juscite-f86-frontend-"))
    (work / "reading-order.ts").write_text(
        extract_reading_order_ts(), encoding="utf-8", newline="")
    (work / "doc.json").write_text(
        json.dumps(doc_payload, ensure_ascii=False), encoding="utf-8")
    (work / "selectors.json").write_text(
        json.dumps(selectors, ensure_ascii=False), encoding="utf-8")
    driver = r'''
import { readFileSync } from "node:fs"
import { projectOrder, resolveHits, itemById } from "./reading-order.ts"
const doc = JSON.parse(readFileSync(process.argv[2], "utf8"))
const selectors = JSON.parse(readFileSync(process.argv[3], "utf8"))
const out = { projectedIds: projectOrder(doc), duplicateCheck: null, hits: {}, errors: {} }
try { itemById(doc); out.duplicateCheck = "ok" } catch (e) { out.duplicateCheck = e.code ?? String(e) }
for (const [name, entry] of Object.entries(selectors)) {
  try { out.hits[name] = resolveHits(doc, entry.kind, entry.selector).map((i) => i.id).sort() }
  catch (e) { out.errors[name] = (e && e.code) ? e.code : String(e) }
}
console.log(JSON.stringify(out))
'''
    (work / "driver.ts").write_text(driver, encoding="utf-8", newline="")
    proc = subprocess.run(
        [str(BUN), "run", "driver.ts", "doc.json", "selectors.json"],
        cwd=work, capture_output=True, text=True, encoding="utf-8",
        errors="replace", timeout=120)
    if proc.returncode != 0:
        raise RuntimeError("bun driver failed: "
                           + (proc.stderr or proc.stdout)[-600:])
    return json.loads(proc.stdout.strip().splitlines()[-1])


def order_hash_ids(ids: list[str]) -> str:
    digest = hashlib.sha256()
    for item_id in ids:
        digest.update(item_id.encode("utf-8"))
        digest.update(b"\n")
    return digest.hexdigest()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--profile", choices=["desktop", "selfhost"],
                    default="desktop")
    ap.add_argument("--corpus", type=Path,
                    default=TEMP / f"juscite-f86-corpus-{CORPUS_PAGES}")
    ap.add_argument("--state", type=Path, default=None)
    ap.add_argument("--bun", type=Path, default=None)
    ap.add_argument("--skip-parse", action="store_true",
                    help="跳过解析（要求状态已落盘），只做对表")
    args = ap.parse_args()
    if args.bun:
        global BUN
        BUN = args.bun

    evidence_dir = (REPO / "docs" / "construction" / "evidence" / "F86"
                    / args.profile)
    state = args.state or (TEMP / f"juscite-f86-state-{args.profile}")
    corpus = args.corpus.resolve()

    if not BRIDGE.is_file():
        eprint(f"[ENV-MISSING] 桥入口缺失：{BRIDGE}")
        return 3
    if not PATCH.is_file():
        eprint(f"[ENV-MISSING] 补丁 013 缺失：{PATCH}")
        return 3
    if not BUN.is_file():
        eprint(f"[ENV-MISSING] Bun 不在：{BUN}（--bun 指定）")
        return 3
    if not ensure_corpus(corpus):
        eprint(f"[ENV-MISSING] 语料不可得：{corpus}")
        return 3

    config = {"anonymizer_contract": "p09/p10",
              "material_parse_state_root": str(state)}

    checks: list[dict] = []
    metrics: dict[str, object] = {}
    started = now_iso()

    def record(name: str, ok: bool, detail) -> bool:
        checks.append({"name": name, "ok": bool(ok), "detail": str(detail)})
        print(f"[{'PASS' if ok else 'FAIL'}] {name}: {detail}", flush=True)
        return ok

    # ------------------------------------------------ C01 固定样例集（语料锚）
    digest_before = corpus_identity_digest(corpus)
    manifest = json.loads((corpus / "corpus_manifest.json")
                          .read_text(encoding="utf-8"))
    kinds: dict[str, int] = {}
    for doc in manifest["documents"]:
        for pf in doc["page_files"]:
            kinds[pf["expected_signal"]] = kinds.get(pf["expected_signal"], 0) + 1
    record("C01_fixed_sample_corpus_anchor",
           manifest["pages"] == CORPUS_PAGES and manifest["seed"] == CORPUS_SEED
           and len(manifest["tables"]) >= 1,
           f"pages={manifest['pages']} seed={manifest['seed']} "
           f"docs={len(manifest['documents'])} tables={len(manifest['tables'])} "
           f"kinds={json.dumps(kinds, ensure_ascii=False)} "
           f"sha256(identity)={digest_before[:16]}…")

    # ------------------------------------- C02 解析产物（真桥 CLI 子进程径）
    rc, reg = bridge_call(config, "material.parse_register",
                          {"corpus_root": str(corpus)})
    reg = reg.get("result", {})
    if rc != 0 or not reg.get("batch_id"):
        eprint(f"[FAIL] 登记失败 rc={rc}：{reg}")
        return 2
    batch_id = reg["batch_id"]
    if not args.skip_parse:
        rc0, pend = bridge_call(config, "material.parse_pending",
                                {"batch_id": batch_id})
        if pend.get("result", {}).get("pending"):
            t0 = time.time()
            rc0, out = bridge_call(config, "material.parse_process",
                                   {"batch_id": batch_id})
            metrics["parse_seconds"] = round(time.time() - t0, 1)
            eprint(f"[PARSE] {out.get('result')} "
                   f"({metrics['parse_seconds']}s)")
    rc, report = bridge_call(config, "material.parse_report",
                             {"batch_id": batch_id})
    rep = report.get("result", {})
    record("C02_parse_products_via_bridge",
           rc == 0 and rep.get("completed") == rep.get("registered_pages")
           and rep.get("pending") == 0 and rep.get("corrupt_records") == 0,
           f"batch={batch_id} completed={rep.get('completed')}/"
           f"{rep.get('registered_pages')} signals="
           f"{json.dumps(rep.get('signals', {}), ensure_ascii=False)}")
    metrics["parse_report"] = rep

    # ---------------------------------- C03 后端规范文档（确定性＝两跑同哈希）
    rc, doc1 = bridge_call(config, "reading.document", {"batch_id": batch_id})
    rc2, doc2 = bridge_call(config, "reading.document", {"batch_id": batch_id})
    canon = doc1.get("result", {})
    canon2 = doc2.get("result", {})
    backend_ids = [i["id"] for i in canon.get("items", [])]
    identical = json.dumps(canon, sort_keys=True) == json.dumps(canon2,
                                                                sort_keys=True)
    record("C03_backend_canonical_document_deterministic",
           rc == 0 and rc2 == 0 and canon and identical
           and canon.get("schema") == "juscite-f86-reading-order/1"
           and canon.get("source_face") == "material.parse_*"
           and canon.get("order_hash") == order_hash_ids(backend_ids)
           and [i["order_index"] for i in canon["items"]]
           == list(range(len(backend_ids))),
           f"items={canon.get('counts')} order_hash="
           f"{str(canon.get('order_hash'))[:16]}… 两跑同字节={identical}")
    metrics["backend_counts"] = canon.get("counts")

    # ---------------------------------- C04 前端投影（补丁抽出模块 Bun 真跑）
    try:
        front = run_frontend_projection(canon, {})
    except Exception as exc:  # noqa: BLE001
        record("C04_frontend_projection_same_order", False,
               f"bun 投影失败：{exc}")
        front = None
    if front is not None:
        ts_hash = order_hash_ids(front["projectedIds"])
        record("C04_frontend_projection_same_order",
               front["projectedIds"] == backend_ids
               and ts_hash == canon["order_hash"]
               and front.get("duplicateCheck") == "ok",
               f"前端 id 序列==后端（{len(front['projectedIds'])} 项逐项相等）"
               f"；序哈希复核 {ts_hash[:16]}…=={canon['order_hash'][:16]}…")

    # ------------------------------------------- C05 三类命中高亮（双端一致）
    seg_pages = {i["page"] for i in canon["items"]
                 if i["kind"] == "page_segment"}
    blank_page = next((i["page"] for i in canon["items"]
                       if i["kind"] == "page_segment"
                       and i.get("signal") == "BLANK"), None)
    table_item = next((i for i in canon["items"]
                       if i["kind"] == "table_row"), None)
    ocr_item = next((i for i in canon["items"]
                     if i["kind"] == "ocr_hit"), None)
    doc_id = canon["docs"][0] if canon.get("docs") else "doc_0001"
    selectors: dict[str, dict] = {
        "seg_ok": {"kind": "page_segment",
                   "selector": {"doc_id": doc_id, "page": min(seg_pages)}},
        "table_group": {"kind": "table",
                        "selector": {"doc_id": doc_id,
                                     "group": table_item["group"]}},
        "table_row": {"kind": "table",
                      "selector": {"doc_id": doc_id,
                                   "group": table_item["group"],
                                   "row": table_item["row"]}},
        "ocr_ok": {"kind": "ocr",
                   "selector": {"doc_id": doc_id, "page": ocr_item["page"]}},
        "seg_missing": {"kind": "page_segment",
                        "selector": {"doc_id": doc_id, "page": 9999}},
        "kind_invalid": {"kind": "citation",
                         "selector": {"doc_id": doc_id}},
    }
    if blank_page is not None:
        selectors["ocr_blank_page_fail_loud"] = {
            "kind": "ocr", "selector": {"doc_id": doc_id, "page": blank_page}}
    front2 = None
    try:
        front2 = run_frontend_projection(canon, selectors)
    except Exception as exc:  # noqa: BLE001
        record("C05_three_hit_kinds_dual_end", False, f"bun 投影失败：{exc}")

    backend_hits: dict[str, object] = {}
    backend_errors: dict[str, str] = {}
    for name, entry in selectors.items():
        rc, payload = bridge_call(config, "reading.hits",
                                  {"batch_id": batch_id,
                                   "kind": entry["kind"],
                                   "selector": entry["selector"]})
        if rc == 0:
            backend_hits[name] = sorted(
                h["id"] for h in payload.get("result", {}).get("hits", []))
        else:
            backend_errors[name] = str(payload.get("code"))

    if front2 is not None:
        agree = all(front2["hits"].get(name) == backend_hits.get(name)
                    for name in backend_hits)
        fail_loud = (
            backend_errors.get("seg_missing")
            == "reading_order_failed:f86_selector_not_found:page_segment"
            and front2["errors"].get("seg_missing")
            == "f86_selector_not_found:page_segment"
            and backend_errors.get("kind_invalid")
            == "reading_order_failed:f86_kind_invalid"
            and front2["errors"].get("kind_invalid") == "f86_kind_invalid")
        if "ocr_blank_page_fail_loud" in selectors:
            fail_loud = fail_loud and (
                backend_errors.get("ocr_blank_page_fail_loud")
                == "reading_order_failed:f86_selector_not_found:ocr_hit"
                and front2["errors"].get("ocr_blank_page_fail_loud")
                == "f86_selector_not_found:ocr_hit")
        bbox_ok = all(
            cell is None or (cell.get("bbox") and len(cell["bbox"]) == 4)
            for h in canon["items"] if h["kind"] == "table_row"
            for cell in (h.get("cells") or []))
        ocr_bbox_ok = (ocr_item.get("bbox") and len(ocr_item["bbox"]) == 4
                       and ocr_item.get("text"))
        record("C05_three_hit_kinds_dual_end",
               agree and fail_loud and bbox_ok and ocr_bbox_ok,
               f"六选择子双端逐项一致={agree}（页段/表格组/表格行/扫描OCR "
               f"命中 {len(backend_hits.get('table_group', []))}+"
               f"{len(backend_hits.get('table_row', []))} 行）；"
               f"静默失败预防针（解析不到=双端响亮报错）={fail_loud}；"
               f"表格单元格 bbox 四元组齐={bbox_ok}；"
               f"扫描OCR命中带文本+bbox={bool(ocr_bbox_ok)}")
    metrics["backend_hits"] = backend_hits
    metrics["backend_hit_errors"] = backend_errors

    # ------------------------------- C06 同源硬扣（规范文档 == 解析产物序）
    rc, tables = bridge_call(config, "material.parse_tables",
                             {"batch_id": batch_id, "doc_id": doc_id})
    gold_rows = [(g["group_index"], r["page"], r["page_row_index"])
                 for g in tables.get("result", {}).get("groups", [])
                 for r in g["rows"]]
    doc_rows = [(i["group"], i["page"], i["row"]) for i in canon["items"]
                if i["kind"] == "table_row"]
    page_seq = [(i["doc_id"], i["page"]) for i in canon["items"]
                if i["kind"] == "page_segment"]
    registered_seq = sorted(
        (d["doc_id"], int(pf["page"]))
        for d in manifest["documents"] for pf in d["page_files"])
    ocr_gold = 0
    for doc in manifest["documents"]:
        for pf in doc["page_files"]:
            rc, page = bridge_call(
                config, "material.parse_page",
                {"batch_id": batch_id, "doc_id": doc["doc_id"],
                 "page": int(pf["page"])})
            rec = page.get("result", {})
            versions = (rec.get("page_no") or {}).get("versions") or []
            if versions:
                ocr_gold += 1
    record("C06_same_source_hard_ties",
           gold_rows == doc_rows and page_seq == registered_seq
           and ocr_gold == canon["counts"]["ocr_hits"],
           f"表格行序==material.parse_tables 组装序（{len(doc_rows)} 行逐项）"
           f"；页段序==登记页序（{len(page_seq)} 页）；"
           f"OCR 命中数==页号版本链页数（{ocr_gold}）")

    # --------------------------------------- C07 桥 fail-closed 负向（CLI）
    rc_bad, payload_bad = bridge_call(
        {"anonymizer_contract": "p09/p10"}, "reading.document",
        {"batch_id": batch_id})
    rc_unknown, payload_unknown = bridge_call(
        config, "reading.explode", {"batch_id": batch_id})
    rc_nobatch, payload_nobatch = bridge_call(
        config, "reading.document", {"batch_id": "mp-none"})
    record("C07_bridge_fail_closed",
           rc_bad == 3 and payload_bad.get("status") == "NOT_CONNECTED"
           and "f86_state_root_not_configured" in str(payload_bad.get("code"))
           and rc_unknown == 3
           and "method_not_connected:reading.explode"
           in str(payload_unknown.get("code"))
           and rc_nobatch == 3
           and "f86_parse_face:parse_batch_not_registered"
           in str(payload_nobatch.get("code")),
           f"缺状态根 exit{rc_bad}={payload_bad.get('code')}；"
           f"未知方法 exit{rc_unknown}={payload_unknown.get('code')}；"
           f"未登记批次 exit{rc_nobatch}={payload_nobatch.get('code')}")

    # ------------------------------------- C08 补丁 013 交付态（未应用完好）
    oc28_ok = OC28.is_dir()
    patch_ok = True
    detail = []
    if oc28_ok:
        targets = [
            "packages/app/src/legal-workbench/legal-workbench.tsx",
            "packages/desktop/src/main/index.ts",
            "packages/desktop/src/preload/index.ts",
        ]
        for rel in targets:
            proc = subprocess.run(
                [sys.executable, "-X", "utf8", str(REPO / "tools"
                   / "verify_patch.py"), str(PATCH), str(OC28 / rel)],
                capture_output=True, text=True, encoding="utf-8",
                errors="replace", timeout=60)
            prestate = ("RESULT: PASS" in proc.stdout
                        and "prestate" in proc.stdout
                        and "applied" not in proc.stdout)
            patch_ok = patch_ok and proc.returncode == 0 and prestate
            state_label = "prestate" if prestate else \
                (proc.stdout.strip().splitlines() or ["?"])[-1]
            detail.append(f"{rel.split('/')[-1]}:{state_label}")
        apply_check = subprocess.run(
            ["git", "apply", "--check", str(PATCH)],
            cwd=OC28, capture_output=True, text=True, encoding="utf-8",
            errors="replace", timeout=60)
        patch_ok = patch_ok and apply_check.returncode == 0
        apply_label = "CLEAN" if apply_check.returncode == 0 \
            else apply_check.stderr[-120:]
        detail.append(f"git-apply-check:{apply_label}")
    record("C08_patch013_delivered_not_applied", patch_ok and oc28_ok,
           "; ".join(detail) if detail else f"oc28 不在预期位置 {OC28}")

    # ------------------------------------------------ C09 语料只读锚（跑后）
    digest_after = corpus_identity_digest(corpus)
    record("C09_corpus_anchor_after",
           digest_after == digest_before,
           f"跑前后 sha256(identity) 相同＝{digest_after == digest_before} "
           f"({digest_after[:16]}…)")

    ok = all(c["ok"] for c in checks)
    verdict = "RECON_OK" if ok else "RECON_FAIL"
    result = {
        "obligation": "06:F86 前后端阅读序同源（固定样例一致＋高亮页段/表格/扫描OCR命中）",
        "unit": "W2a-U07",
        "profile": args.profile,
        "started_utc": started,
        "finished_utc": now_iso(),
        "verdict": verdict,
        "batch_id": batch_id,
        "corpus": {"pages": CORPUS_PAGES, "seed": CORPUS_SEED,
                   "root": str(corpus),
                   "identity_digest": digest_before,
                   "readonly_unchanged": digest_after == digest_before},
        "state_root": str(state),
        "patch": {"path": str(PATCH), "sha256": sha256_file(PATCH),
                  "applied_to_oc28": False},
        "checks": checks,
        "metrics": {k: v for k, v in metrics.items() if k != "run_seconds"},
    }
    evidence_dir.mkdir(parents=True, exist_ok=True)
    out_json = evidence_dir / "f86-reading-order-recon-result.json"
    out_json.write_text(json.dumps(result, ensure_ascii=False, indent=2),
                        encoding="utf-8")
    print(f"\n{verdict}  ({sum(c['ok'] for c in checks)}/{len(checks)} checks)"
          f"  证据 → {out_json}", flush=True)
    return 0 if ok else 2


if __name__ == "__main__":
    sys.exit(main())

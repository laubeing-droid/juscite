#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""F42 义务验收 recon（W4-U35）：印章/PS 疑似视觉检测——疑似项可回原图
区域定位＋检测局限声明＋只出『疑似』档永不输出真伪结论（双 profile）。

义务 06:F42（v1.5，acceptance）「疑似印章/视觉异常可回原图且标检测局限；
不签真伪鉴定」；来源纪律「证据质证有价值但依赖视觉模型，随级联入」
（F40 四端口级联）。检测跑在 F40 钉定解释器子进程纪律内（GPU fail-closed·
模型 sha256 钉定·绝不运行时下载，W2a-U03/W2a-U16 先例；08§2 重 GPU 串行
分块一次一个 worker）。低置信/失败不假成功（E11 语义）。不签真伪＝结构
断言（结论词闭集 {suspected, not_detected}＋禁形语素全产物扫描，真伪
判断形态零存在）。

产品径＝implementation/python/legal_entry.py 桥（stamp.* 方法组）→
anonymizer stamp_visual_service 公开面（同进程，P09/P10 纪律；anonymizer
w4-u21 分支，W4-U21 交付，本 recon 零 anonymizer 改动）。语料＝
tools/e12_corpus_gen.py --stamp-boxes 全合成金标盒两卷八页（seed 20261020
钉定，00-总协调 §6.1 裁决#1 零真实文档；金标盒仅验收侧直读）。故障注入
在派生副本语料上（主语料只读锚跑前后不变）。本 recon 每次运行重建干净
%TEMP% 状态根；显式 --state 已存在且非空=拒绝（不静默清用户目录）。
持久证据=docs/construction/evidence/F42/<profile>/ JSON＋MD。

用法（juscite worktree w4-u35 仓根 cwd）：
  python -X utf8 tools/recon/PENDING_OWNER_f42_seal_detection_recon.py --profile desktop --profile selfhost
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
import tempfile
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
TEMP = Path(os.environ.get("TEMP", "."))
DEFAULT_INTERPRETER = Path(os.environ.get(
    "JUSCITE_F40_BASELINE_INTERPRETER",
    r"C:\Users\being\AppData\Local\pdf2md-venv\Scripts\python.exe"))
CORPUS_SEED = 20261020
GOLD_NAME = "f42_stamp_digest.txt"
# 金标正例页（doc_id, page, gold_kind）——疑似预期＋金标盒中心定位。
GOLD_POSITIVE = [
    ("doc_f42_a", 1, "seal_red_strong"),
    ("doc_f42_a", 2, "seal_red_pale"),
    ("doc_f42_a", 3, "seal_red_overlap"),
    ("doc_f42_a", 4, "ps_red_paste"),
]
# 对照页（not_detected 预期）。
GOLD_NEGATIVE = [
    ("doc_f42_b", 1, "clean", "净页"),
    ("doc_f42_b", 3, "ps_nonred_paste", "漏报向例证（非红篡改在探针范围外"
                                        "＝检测局限具名边界实测成立）"),
    ("doc_f42_b", 4, "blank", "空白"),
]
# 局限误报向例证（suspected 预期）：红色文本页——局限声明具名方向
# 「红色文本可能误报为疑似区域」的实测发生。疑似档=初筛线索非结论，
# 误报由随页局限声明与人审承接；本页无金标盒（非印章/痕迹正例）。
LIMIT_FALSE_POSITIVE = ("doc_f42_b", 2, "red_text",
                        "误报向例证（红色文本——局限具名方向实测发生："
                        "大字号红色字符块过面积/长宽门后如实报疑似）")
FAULT_DOC, FAULT_PAGE = "doc_f42_b", 3   # 故障注入页（派生副本语料内）


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
    """anonymizer w4-u21 源定位：显式参 > 环境变量 > 同波 worktree 相对
    推断 > None。必须有 stamp_visual_service（缺=环境缺，不回退主树装
    样子）。"""
    if explicit:
        return Path(explicit).resolve()
    env = os.environ.get("JUSCITE_ANONYMIZER_SRC")
    if env:
        return Path(env).resolve()
    root = REPO
    for _ in range(6):
        if root.name == "jusbench工作区":
            guess = (root.parent / "legal-cn-anonymizer工作区"
                     / "legal-cn-anonymizer" / ".local" / "worktrees"
                     / "w4-u21" / "src")
            if (guess / "legal_anonymizer" / "application"
                    / "stamp_visual_service.py").is_file():
                return guess
            break
        root = root.parent
    return None


def build_stamp_corpus(out: Path, seed: int) -> bool:
    if (out / "corpus_manifest.json").is_file():
        return True
    out.parent.mkdir(parents=True, exist_ok=True)
    eprint(f"[GEN] 生成印章/PS 金标盒语料 seed={seed} → {out}")
    proc = subprocess.run(
        [sys.executable, "-X", "utf8",
         str(REPO / "tools" / "e12_corpus_gen.py"),
         "--stamp-boxes", str(out), "--seed", str(seed)],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        timeout=600)
    if proc.returncode != 0:
        eprint((proc.stdout or "")[-800:], (proc.stderr or "")[-800:])
        return False
    return (out / "corpus_manifest.json").is_file()


def build_fault_corpus(main_corpus: Path, out: Path) -> Path | None:
    """派生故障语料（副本，每次重建保证原样起点；主语料零接触）：只取
    doc_f42_b 两对照页（页字节原样拷贝，清单登记 sha 不变）。"""
    try:
        if out.is_dir():
            shutil.rmtree(out)
        manifest = json.loads(
            (main_corpus / "corpus_manifest.json").read_text(
                encoding="utf-8"))
        doc = next(d for d in manifest["documents"]
                   if d["doc_id"] == "doc_f42_b")
        (out / "pages").mkdir(parents=True)
        for pf in doc["page_files"]:
            dst = out / pf["png"]
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(main_corpus / pf["png"], dst)
        sub = {k: v for k, v in manifest.items() if k != "documents"}
        sub["documents"] = [doc]
        (out / "corpus_manifest.json").write_text(
            json.dumps(sub, ensure_ascii=False), encoding="utf-8")
        return out
    except (OSError, KeyError, ValueError, StopIteration):
        return None


def load_bridge(anonymizer_src: Path):
    sys.path.insert(0, str(REPO / "implementation" / "python"))
    sys.path.insert(0, str(anonymizer_src))
    import legal_anonymizer
    from legal_entry import call as bridge_call
    return bridge_call, str(legal_anonymizer.__file__)


def run_profile(profile: str, args, corpus: Path, fault_corpus: Path,
                bridge, corpus_det: dict) -> bool:
    """单 profile 全链真跑（C01-C11）。"""
    evidence_dir = REPO / "docs" / "construction" / "evidence" / "F42" / profile
    state = Path(args.state) if args.state \
        else (TEMP / f"juscite-f42-state-{profile}")
    if args.state is not None:
        if state.exists() and any(state.iterdir()):
            eprint(f"[ENV-MISSING] 状态根非空（拒绝静默清理）：{state}")
            return False
    elif state.exists():
        shutil.rmtree(state)   # 默认 %TEMP% 状态根=recon 自有草稿
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
            "unit": "W4-U35",
            "acceptance": "疑似印章/视觉异常可回原图且标检测局限；"
                          "不签真伪鉴定",
            "corpus": str(corpus), "corpus_seed": CORPUS_SEED,
            "corpus_determinism": corpus_det,
            "fault_corpus": str(fault_corpus),
            "interpreter": str(args.interpreter),
            "anonymizer_src": str(args.anonymizer_src),
            "bridge_methods": [
                "stamp.register", "stamp.run", "stamp.pending",
                "stamp.report", "stamp.page", "stamp.original",
                "stamp.limitation", "stamp.conclusion_scan"],
            "checks": checks, "metrics": metrics,
            "scope_note": "本单=juscite 桥面（stamp.* 八方法）＋验收 recon；"
                          "anonymizer stamp_visual 面=W4-U21 交付（本单零 "
                          "anonymizer 改动）；检测=F40 钉定解释器 worker 子"
                          "进程纪律（GPU fail-closed·模型 sha256 钉定·绝不"
                          "运行时下载）；桌面真机 UI 面/compose 宿主面不在"
                          "本单（挂 F02/后续）",
        }
        evidence_dir.mkdir(parents=True, exist_ok=True)
        out_json = evidence_dir / "f42-stamp-detection-recon-result.json"
        out_json.write_text(json.dumps(evidence, ensure_ascii=False,
                                       indent=1), encoding="utf-8")
        md = [f"# F42 印章/PS 疑似视觉检测 recon（{profile}）",
              f"- verdict: **{verdict}**  profile={profile} "
              f"run={metrics.get('run_id')}",
              f"- 语料: {corpus}（两卷八页全合成金标盒 seed={CORPUS_SEED}；"
              f"确定性 {corpus_det.get('same_bytes')}）",
              f"- anonymizer 源: {args.anonymizer_src}（W4-U21 交付）",
              f"- 不签真伪：结论词闭集 suspected/not_detected＋禁形语素"
              f"全产物扫描零命中", ""]
        for c in checks:
            md.append(f"- {'✅' if c['ok'] else '❌'} **{c['name']}**: "
                      f"{c['detail']}")
        md.append("")
        (evidence_dir / "f42-stamp-detection-recon-result.md").write_text(
            "\n".join(md), encoding="utf-8")
        print(f"\n[{profile}] {verdict}  checks="
              + "/".join("PASS" if c["ok"] else "FAIL" for c in checks))
        print(f"[{profile}] evidence: {out_json}", flush=True)
        return ok_all

    manifest = json.loads((corpus / "corpus_manifest.json")
                          .read_text(encoding="utf-8"))
    gold_by_page = {}
    for d in manifest["documents"]:
        for pf in d["page_files"]:
            gold_by_page[(d["doc_id"], int(pf["page"]))] = \
                pf.get("gold_boxes") or []

    # --------------------------------- C01 登记（解释器钉定＋金标白名单）
    digest_before = corpus_identity_digest(corpus)
    reg = bridge("stamp.register", {"corpus_root": str(corpus)}, config)
    run_id = reg["run_id"]
    metrics["run_id"] = run_id
    run_raw = (state / "f42-stamp" / run_id / "run.json").read_text(
        encoding="utf-8")
    gold_leak = [k for k in ("gold_boxes", '"cx"', '"kind"', "page_kind")
                 if k in run_raw]
    record("C01_register_pinned_whitelist",
           run_id.startswith("f42-")
           and reg["registered_pages"] == 8
           and reg["verdicts_closed_set"] == ["suspected", "not_detected"]
           and not gold_leak
           and json.loads(run_raw)["interpreter_pin"]["sha256"]
           == sha256_file(Path(args.interpreter)),
           f"run={run_id} pages={reg['registered_pages']}/8；结论词闭集="
           f"{reg['verdicts_closed_set']}；金标结构性不入账（gold_boxes/cx/"
           f"kind 零泄漏={not gold_leak}）；解释器 sha256 钉定入账"
           f"={sha256_file(Path(args.interpreter))[:12]}…")

    # --------------------------------------- C02 真跑（钉定解释器 worker）
    run_out = bridge("stamp.run", {"run_id": run_id}, config)
    report = bridge("stamp.report", {"run_id": run_id}, config)
    sample = bridge("stamp.page",
                    {"run_id": run_id, "doc_id": "doc_f42_a", "page": 1},
                    config)
    engine = sample.get("engine") or {}
    model_files = (engine.get("model_cache") or {}).get("files") or {}
    pids = set()
    all_pages = ([(d, p) for d, p, _k in GOLD_POSITIVE]
                 + [(d, p) for d, p, _k, _s in GOLD_NEGATIVE]
                 + [(LIMIT_FALSE_POSITIVE[0], LIMIT_FALSE_POSITIVE[1])])
    for key in all_pages:
        rec = bridge("stamp.page",
                     {"run_id": run_id, "doc_id": key[0], "page": key[1]},
                     config)
        if rec.get("engine"):
            pids.add(rec["engine"].get("worker_pid"))
    record("C02_real_run_engine_pinned_f40_discipline",
           run_out["failed"] == 0 and run_out["processed"] == 8
           and report["completed"] == 8 and report["error_pages"] == 0
           and engine.get("device") == "gpu:0"
           and engine.get("cuda_compiled") is True
           and len(model_files) >= 10
           and bool(engine.get("paddleocr_version"))
           and bool(engine.get("cv2_version"))
           and pids == {engine.get("worker_pid")}
           and engine.get("worker_pid") != os.getpid()
           and bool(engine.get("detect_params")),
           f"8/8 页完成 0 错误；engine={engine.get('engine')}@"
           f"{engine.get('paddleocr_version')} paddle="
           f"{engine.get('paddle_version')} device=gpu:0 cuda_compiled="
           f"{engine.get('cuda_compiled')}；模型缓存 sha256 钉定="
           f"{len(model_files)} 文件（绝不运行时下载）；8 页同一 worker_pid="
           f"{engine.get('worker_pid')}（串行分块一次一个进程，08§2）≠桥"
           f"pid={os.getpid()}；检测参数全集入账={bool(engine.get('detect_params'))}")

    # ------------------------- C03 疑似项可回原图区域定位（acceptance 硬门）
    loc_ok = True
    loc_detail = []
    orig_ok = True
    for doc_id, page, kind in GOLD_POSITIVE:
        rec = bridge("stamp.page",
                     {"run_id": run_id, "doc_id": doc_id, "page": page},
                     config)
        golds = [g for g in gold_by_page.get((doc_id, page), [])
                 if g["kind"] == kind]
        if rec.get("verdict") != "suspected" or not rec.get("regions"):
            loc_ok = False
            loc_detail.append(f"{doc_id}p{page}:verdict={rec.get('verdict')}")
            continue
        if len(rec["regions"]) != 1:
            loc_ok = False
            loc_detail.append(f"{doc_id}p{page}:regions={len(rec['regions'])}")
            continue
        bx = rec["regions"][0]["bbox"]
        for g in golds:
            if not (bx[0] <= g["cx"] <= bx[2] and bx[1] <= g["cy"] <= bx[3]):
                loc_ok = False
                loc_detail.append(
                    f"{doc_id}p{page}:bbox={bx}金标中心=({g['cx']},{g['cy']})")
        orig = bridge("stamp.original",
                      {"run_id": run_id, "doc_id": doc_id, "page": page},
                      config)
        if not (orig.get("sha_match") and orig.get("read_only")
                and orig.get("bytes_returned") is False
                and orig.get("region_bboxes") == [bx]
                and not ("payload" in orig or "png_bytes" in orig)):
            orig_ok = False
            loc_detail.append(f"{doc_id}p{page}:original 映射面不符")
        loc_detail.append(f"{doc_id}p{page}({kind}):bbox={bx}conf="
                          f"{rec['regions'][0]['conf']}")
    record("C03_suspected_regions_locate_gold_and_original_readonly",
           loc_ok and orig_ok,
           f"4/4 金标正例页（强红章/浅淡章/叠字章/红色 PS 贴块）verdict="
           f"suspected 且恰一疑似区域 bbox 覆盖金标盒中心；{'；'.join(loc_detail)}；"
           f"原图只读回读 4/4：sha_match＋read_only＋bytes_returned=false"
           f"（原件字节绝不复制绝不出域，只回映射与身份）={orig_ok}")

    # --------------------------------- C04 对照页＋局限例证（诚实面）
    neg_ok = True
    neg_detail = []
    for doc_id, page, kind, why in GOLD_NEGATIVE:
        rec = bridge("stamp.page",
                     {"run_id": run_id, "doc_id": doc_id, "page": page},
                     config)
        if rec.get("verdict") != "not_detected" or rec.get("regions"):
            neg_ok = False
            neg_detail.append(f"{doc_id}p{page}({kind}):verdict="
                              f"{rec.get('verdict')}")
        else:
            neg_detail.append(f"{doc_id}p{page}({kind})=not_detected")
    fp_doc, fp_page, fp_kind, fp_why = LIMIT_FALSE_POSITIVE
    fp_rec = bridge("stamp.page",
                    {"run_id": run_id, "doc_id": fp_doc, "page": fp_page},
                    config)
    fp_hit = (fp_rec.get("verdict") == "suspected"
              and bool(fp_rec.get("regions"))
              and bool(fp_rec.get("limitation", {}).get("boundary")))
    record("C04_negative_pages_honest_with_limitation_exemplars",
           neg_ok and fp_hit,
           f"3/3 对照页 not_detected 零疑似区域：{'；'.join(neg_detail)}"
           f"——非红贴块=漏报向例证（局限具名『仅覆盖红色主导印迹』边界实测"
           f"成立，如实不检出不补第二探针）；{fp_why}：verdict=suspected "
           f"regions={len(fp_rec.get('regions') or [])} 携局限声明="
           f"{fp_hit}——误报如实入『疑似』档不掩饰（疑似≠结论，由局限声明"
           f"与人审承接；检测局限声明不是免责装饰是行为实况）")

    # --------------------------------- C05 置信如实（低置信不假成功不夹取）
    strong = bridge("stamp.page",
                    {"run_id": run_id, "doc_id": "doc_f42_a", "page": 1},
                    config)["regions"][0]["conf"]
    pale = bridge("stamp.page",
                  {"run_id": run_id, "doc_id": "doc_f42_a", "page": 2},
                  config)["regions"][0]["conf"]
    record("C05_confidence_honest_no_clamping",
           0.0 < pale < strong <= 1.0,
           f"浅淡印迹 conf={pale} < 强红 conf={strong}（同几何仅色度差，"
           f"量值随实测落盘不夹取不虚高）；两值均∈(0,1] 且随页记录可回读"
           f"——低置信页仍如实出『疑似』并携真实置信，不弃检不虚标")

    # --------------------------------------------- C06 检测局限声明随记录
    lim = bridge("stamp.limitation", {}, config)["limitation"]
    pages_carry = True
    all_eight = ([(d, p) for d, p, _k in GOLD_POSITIVE]
                 + [(d, p) for d, p, _k, _s in GOLD_NEGATIVE]
                 + [(LIMIT_FALSE_POSITIVE[0], LIMIT_FALSE_POSITIVE[1])])
    for doc_id, page in all_eight:
        rec = bridge("stamp.page",
                     {"run_id": run_id, "doc_id": doc_id, "page": page},
                     config)
        rlim = rec.get("limitation") or {}
        if not (rlim.get("not_a") == "expert_opinion" and rlim.get("models")
                and len(rlim.get("boundary") or []) >= 3
                and rlim.get("scope")):
            pages_carry = False
    record("C06_limitation_statement_on_every_record",
           lim.get("not_a") == "expert_opinion" and bool(lim.get("models"))
           and len(lim.get("boundary") or []) >= 3 and bool(lim.get("scope"))
           and pages_carry,
           f"静态面：not_a=expert_opinion·模型清单={len(lim['models'])} 项"
           f"（视觉模型角色＋训练域边界具名）·边界条款={len(lim['boundary'])}"
           f" 条（非红漏检/红色误报/数字篡改痕迹无探针如实具名）·范围="
           f"初筛线索不构成结论；运行面：8/8 页记录均携局限声明＋引擎版本"
           f"钉定（detect/run 双钉定）")

    # ------------------------------- C07 不签真伪＝结构断言（acceptance 硬门）
    scan = bridge("stamp.conclusion_scan", {"run_id": run_id}, config)
    planted = False
    victim = state / "f42-stamp" / run_id / "pages" / "doc_f42_b" / "p0001.json"
    victim_bytes = victim.read_bytes()
    try:
        doc = json.loads(victim_bytes.decode("utf-8"))
        doc["鉴定结论"] = "synthetic-plant"
        victim.write_bytes(json.dumps(doc, ensure_ascii=False).encode("utf-8"))
        try:
            bridge("stamp.conclusion_scan", {"run_id": run_id}, config)
        except Exception as exc:                    # noqa: BLE001 - typed 拒
            planted = "stamp_conclusion_morphology_detected" in str(exc)
    finally:
        victim.write_bytes(victim_bytes)
    scan_restored = bridge("stamp.conclusion_scan",
                           {"run_id": run_id}, config)
    expected_verdicts = {"suspected": 5, "not_detected": 3}
    record("C07_no_authenticity_verdict_structural",
           scan["forbidden_hits"] == []
           and scan["verdict_values"] == expected_verdicts
           and scan["verdicts_closed_set"] == ["suspected", "not_detected"]
           and scan["records_scanned"] == 9
           and planted and scan_restored["forbidden_hits"] == [],
           f"全产物（run.json＋8 页）扫描 {scan['records_scanned']} 记录："
           f"verdict 全在闭集 {scan['verdict_values']}；键名与非材料值零"
           f"「鉴定/确证/真伪」语形（forbidden_hits=空）＝真伪字段结构性"
           f"零存在（不签真伪鉴定不是措辞约定是结构断言）；植入『鉴定结论』"
           f"键→typed 拒交={planted}→字节复原→复扫清白；输出只有『疑似』"
           f"档（not_detected=未检出非『确认无篡改』）")

    # ------------------------- C08 失败不假成功（E11 语义·派生副本语料）
    fault_manifest = json.loads((fault_corpus / "corpus_manifest.json")
                                .read_text(encoding="utf-8"))
    fault_pf = next(pf for d in fault_manifest["documents"]
                    if d["doc_id"] == FAULT_DOC
                    for pf in d["page_files"] if pf["page"] == FAULT_PAGE)
    freg = bridge("stamp.register", {"corpus_root": str(fault_corpus)},
                  config)
    fault_rel = Path(fault_corpus / fault_pf["png"])
    fault_bytes = fault_rel.read_bytes()
    fault_ok = False
    fault_detail = ""
    try:
        fault_rel.write_bytes(b"F42-SYNTHETIC-FAULT-INJECTION")
        bridge("stamp.run", {"run_id": freg["run_id"],
                             "pages": [{"doc_id": FAULT_DOC,
                                        "page": FAULT_PAGE}]}, config)
        frec = bridge("stamp.page",
                      {"run_id": freg["run_id"], "doc_id": FAULT_DOC,
                       "page": FAULT_PAGE}, config)
        frep = bridge("stamp.report", {"run_id": freg["run_id"]}, config)
        try:
            bridge("stamp.original",
                   {"run_id": freg["run_id"], "doc_id": FAULT_DOC,
                    "page": FAULT_PAGE}, config)
            orig_refused = False
        except Exception as exc:                # noqa: BLE001 - typed 拒
            orig_refused = "stamp_original_page_not_completed" in str(exc)
        fault_ok = (frec.get("error") == "page_bytes_mismatch"
                    and frec.get("verdict") is None
                    and frec.get("regions") is None
                    and frep["error_pages"] == 1
                    and frep["error_codes"].get("page_bytes_mismatch") == 1
                    and frep["completed"] == 0
                    and orig_refused)
        fault_detail = (f"派生副本登记后改写页字节→拒跑 page_bytes_mismatch"
                        f"（原件只读红线）；错误页 verdict=None·regions=None·"
                        f"报告入错误分母（error_pages=1·completed=0）＝失败"
                        f"绝不计完成；错误页原图回读 typed 拒={orig_refused}")
        metrics["fault"] = {"run_id": freg["run_id"],
                            "error": frec.get("error"),
                            "verdict": frec.get("verdict")}
    except Exception as exc:                        # noqa: BLE001 - 如实入证
        fault_detail = f"故障注入段异常：{type(exc).__name__}"
    record("C08_failure_never_fakes_success", fault_ok, fault_detail)

    # ------------------------------------------- C09 解释器钉定漂移拒跑
    # （解释器经 config 键传达——桥面无 args 覆盖通道，与 ocr.* 面同式）
    stub = state / "stub-interp.py"
    stub.write_bytes(b"# synthetic stub interpreter\n")
    drift_ok = True
    drift_detail = []
    stub_config = dict(config)
    stub_config["ocr_baseline_interpreter"] = str(stub)
    try:
        bridge("stamp.run", {"run_id": run_id}, stub_config)
        drift_ok = False
        drift_detail.append("changed:NOT_RAISED")
    except Exception as exc:                        # noqa: BLE001 - typed 拒
        if "stamp_interpreter_changed" not in str(exc):
            drift_ok = False
            drift_detail.append(f"changed:{exc}")
    miss_config = dict(config)
    miss_config["ocr_baseline_interpreter"] = str(state / "nope.exe")
    try:
        bridge("stamp.run", {"run_id": run_id}, miss_config)
        drift_ok = False
        drift_detail.append("missing:NOT_RAISED")
    except Exception as exc:                        # noqa: BLE001 - typed 拒
        if "stamp_interpreter_missing" not in str(exc):
            drift_ok = False
            drift_detail.append(f"missing:{exc}")
    record("C09_interpreter_drift_fail_closed", drift_ok,
           ("；".join(drift_detail)) if drift_detail else
           "钉定解释器漂移（stub sha≠登记 pin）=拒跑；解释器缺失=拒跑——"
           "绝不回退非钉定解释器静默续跑")

    # ------------------------------------------------- C10 桥面 fail-closed
    from legal_entry import NotConnected
    fc_ok = True
    fc_detail = []
    for bad_config, want, method, payload in (
            ({}, "anonymizer_p09_p10_not_configured",
             "stamp.report", {"run_id": run_id}),
            ({"anonymizer_contract": "p09/p10"},
             "stamp_state_root_not_configured",
             "stamp.report", {"run_id": run_id}),
            ({"anonymizer_contract": "p09/p10",
              "ocr_ports_state_root": str(state)},
             "stamp_interpreter_not_configured",
             "stamp.register", {"corpus_root": str(corpus)})):
        try:
            bridge(method, payload, bad_config)
            fc_ok = False
            fc_detail.append(f"{want}:NOT_RAISED")
        except NotConnected as exc:
            if want not in str(exc):
                fc_ok = False
                fc_detail.append(f"got:{exc}")
    try:
        bridge("stamp.explode", {}, config)
        fc_ok = False
        fc_detail.append("unknown_method:NOT_RAISED")
    except NotConnected as exc:
        if "method_not_connected:stamp.explode" not in str(exc):
            fc_ok = False
            fc_detail.append(f"got:{exc}")
    record("C10_bridge_fail_closed", fc_ok,
           "; ".join(fc_detail) if fc_detail else
           "contract/state/interpreter 三重 fail-closed＋未知方法拒")

    # --------------------------------------------- C11 语料只读锚（跑后不变）
    digest_after = corpus_identity_digest(corpus)
    record("C11_corpus_readonly_anchor",
           digest_after == digest_before,
           f"before={digest_before[:16]}… after={digest_after[:16]}… "
           f"{'不变' if digest_after == digest_before else '漂移！'}"
           f"（主语料零接触；故障注入全在派生副本）")
    metrics["report"] = {k: report[k] for k in
                         ("registered_pages", "completed", "error_pages",
                          "pending", "verdict_counts", "suspected_pages",
                          "regions_total")}
    return finish(all(c["ok"] for c in checks))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--profile", action="append",
                    choices=["desktop", "selfhost"], default=None)
    ap.add_argument("--corpus", type=Path,
                    default=TEMP / "juscite-f42-stamp-corpus")
    ap.add_argument("--state", type=Path, default=None,
                    help="显式状态根（须不存在或为空；默认按 profile 分 "
                         "%TEMP% 独立根，且每次运行重建）")
    ap.add_argument("--interpreter", type=Path, default=DEFAULT_INTERPRETER)
    ap.add_argument("--anonymizer-src", default=None)
    ap.add_argument("--seed", type=int, default=CORPUS_SEED)
    args = ap.parse_args()
    profiles = args.profile or ["desktop"]

    if not args.interpreter.is_file():
        eprint(f"[ENV-MISSING] 钉定解释器不存在：{args.interpreter}")
        return 3
    corpus = args.corpus.resolve()
    if not build_stamp_corpus(corpus, args.seed):
        eprint("[ENV-MISSING] 语料不可得（--stamp-boxes 生成失败）")
        return 3
    # 确定性锚：同 seed 二次生成逐字节同（独立 %TEMP% 目录，用毕即删）
    det_dir = TEMP / "juscite-f42-stamp-corpus-det"
    if det_dir.exists():
        shutil.rmtree(det_dir)
    det_same = False
    try:
        if build_stamp_corpus(det_dir, args.seed):
            det_same = (det_dir / GOLD_NAME).read_text(encoding="ascii") \
                == (corpus / GOLD_NAME).read_text(encoding="ascii")
    finally:
        shutil.rmtree(det_dir, ignore_errors=True)
    corpus_det = {"same_bytes": det_same,
                  "digest": (corpus / GOLD_NAME).read_text(encoding="ascii")
                  .strip()}
    if not det_same:
        eprint("[ENV-MISSING] 语料确定性锚失败（同 seed 两跑摘要不等）")
        return 3
    eprint(f"[GEN] 确定性锚：同 seed 两跑逐字节同 "
           f"{corpus_det['digest'][:16]}…")
    anonymizer_src = resolve_anonymizer_src(args.anonymizer_src)
    if anonymizer_src is None:
        eprint("[ENV-MISSING] anonymizer w4-u21 源不可得"
               "（--anonymizer-src 指定）")
        return 3
    args.anonymizer_src = anonymizer_src
    if args.state is not None:
        args.state = args.state.resolve()
    bridge, resolved = load_bridge(anonymizer_src)
    if "w4-u21" not in resolved:
        eprint(f"[ENV-MISSING] anonymizer 源不在 w4-u21 树：{resolved}")
        return 3
    print(f"[ENV] anonymizer={resolved}")

    fault_corpus = TEMP / "juscite-f42-faultcorpus"
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
        all_ok = run_profile(profile, args, corpus, fault_corpus, bridge,
                             corpus_det) and all_ok
    print(f"\n{'RECON_OK' if all_ok else 'RECON_FAIL'}"
          f"（profiles={profiles}）")
    return 0 if all_ok else 2


if __name__ == "__main__":
    raise SystemExit(main())

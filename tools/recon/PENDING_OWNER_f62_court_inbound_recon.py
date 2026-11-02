#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""F62 义务验收 recon（W3-U14）：法院来件 OCR 入库链真跑——合成法院来件
附件→F40/F41 既有 OCR 基线链真跑（GPU fail-closed、钉定解释器、绝不运行
时下载）→送达候选人审入库→重复短信幂等（双 profile 两实例）。

义务 06:F62（acceptance）「法院来件附件OCR及送达候选人审入库；重复短信
幂等」；17 卡「公开DTO/权限→既有command_tx和MatterStore/CAS→事务幂等/
版本/lease→canonical采用或候选→公开回读」——入库=harness.register_material
（F08 MatterStore/CAS 已 VERIFIED 面，本单零 harness 改动）；OCR=F41
ocr.batch_* 桥→F40 钉定解释器 worker（本单零引擎改动）。

语料＝tools/e12_corpus_gen.py --attachments 全合成夹具（W2a-U15 扩展，
att_0001/0002 含 PII 行＋att_0003 低置信降质页，00-总协调 §6.1 裁决#1 零
真实文档）；短信文本全合成引用夹具 doc_id。状态根每次运行重建 %TEMP%
（幂等生命周期需干净起点）；显式 --state 非空=拒绝。harness 根钉定
w2b-u53 交付链头 worktree（只读消费，树必须净）；anonymizer 源钉定
w2a-u18 同波 worktree（conftest 同式）。活产品服务零触碰（合成注册文件
替代 %APPDATA% 注册，F45 recon 先例）。持久证据
=docs/construction/evidence/F62/<profile>/ JSON＋MD。

用法（juscite worktree w3-u14 仓根 cwd）：
  python -X utf8 tools/recon/PENDING_OWNER_f62_court_inbound_recon.py --profile desktop --profile selfhost
  [--corpus <dir>] [--state <dir>] [--interpreter <path>] [--anonymizer-src <path>] [--harness-root <path>]

退出码：0＝全部 profile RECON_OK；2＝RECON_FAIL；3＝环境缺失。
"""
from __future__ import annotations

import argparse
import ast
import base64
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
ATT_SEED = 20261017
HARNESS_BRANCH = "w2b-u53"
MATTER = "m-f62-recon"

SMS_A_TEXT = ("【合成市第一人民法院】王合成：您有（2026）京01民初91001号案件"
              "文书送达，请及时登录律引查收并确认入库。【合成法院送达平台】")
SMS_B_TEXT = ("【合成市第一人民法院】王合成：您有（2026）京01民初91002号案件"
              "文书送达，请及时登录律引查收并确认入库。【合成法院送达平台】")
CASE_A = "（2026）京01民初91001号"

#: E10/确定性纪律（AST 静态面）：产品面导入闭集零网络零模型。
IMPORT_WHITELIST = {"__future__", "base64", "hashlib", "json", "os", "re",
                    "datetime", "pathlib", "bridge_errors", "legal_entry"}


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
    parts = []
    for p in sorted(corpus.rglob("*")):
        if p.is_file():
            parts.append(p.relative_to(corpus).as_posix() + ":"
                         + sha256_file(p))
    return hashlib.sha256("\n".join(parts).encode("utf-8")).hexdigest()


def resolve_anonymizer_src(explicit: str | None) -> Path | None:
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
                     / "w2a-u18" / "src")
            if (guess / "legal_anonymizer" / "application"
                    / "ocr_batch_service.py").is_file():
                return guess
            break
        root = root.parent
    return None


def resolve_harness_root(explicit: str | None) -> Path | None:
    if explicit:
        return Path(explicit).resolve()
    env = os.environ.get("JUSCITE_F62_HARNESS_ROOT")
    if env:
        return Path(env).resolve()
    root = REPO
    for _ in range(6):
        if root.name == "jusbench工作区":
            guess = (root.parent / "legal-harness工作区" / "legal-harness-repo"
                     / ".local" / "worktrees" / HARNESS_BRANCH)
            if (guess / "tools" / "workflow-tools" / "harness"
                    / "public_entry.py").is_file():
                return guess
            break
        root = root.parent
    return None


def ensure_fixture(corpus: Path) -> bool:
    if (corpus / "corpus_manifest.json").is_file():
        return True
    corpus.parent.mkdir(parents=True, exist_ok=True)
    eprint(f"[GEN] 附件夹具不存在，生成（seed={ATT_SEED}）→ {corpus}")
    proc = subprocess.run(
        [sys.executable, "-X", "utf8", str(REPO / "tools" / "e12_corpus_gen.py"),
         "--attachments", str(corpus), "--seed", str(ATT_SEED)],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        timeout=1200)
    if proc.returncode != 0:
        eprint((proc.stdout or "")[-800:], (proc.stderr or "")[-800:])
        return False
    return (corpus / "corpus_manifest.json").is_file()


def git(root: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(root), *args], capture_output=True, text=True,
        encoding="utf-8", errors="replace", timeout=60).stdout.strip()


def check_harness_root(root: Path) -> tuple[bool, str]:
    branch = git(root, "rev-parse", "--abbrev-ref", "HEAD")
    head = git(root, "rev-parse", "HEAD")
    dirty = git(root, "status", "--porcelain")
    ok = branch == HARNESS_BRANCH and dirty == ""
    return ok, f"branch={branch} head={head[:12]} dirty={dirty[:120]!r}"


def load_bridge(anonymizer_src: Path):
    sys.path.insert(0, str(REPO / "implementation" / "python"))
    sys.path.insert(0, str(anonymizer_src))
    import legal_anonymizer  # noqa: F401 - 解析面验证
    from legal_entry import call as bridge_call
    return bridge_call, str(Path(legal_anonymizer.__file__).parents[2])


def run_profile(profile: str, args, corpus: Path, harness_root: Path,
                bridge) -> bool:  # noqa: C901 - 单 profile 全链编排
    evidence_dir = REPO / "docs" / "construction" / "evidence" / "F62" / profile
    state = Path(args.state) if args.state \
        else (TEMP / f"juscite-f62-state-{profile}")
    if args.state is not None:
        if state.exists() and any(state.iterdir()):
            eprint(f"[ENV-MISSING] 状态根非空（拒绝静默清理）：{state}")
            return False
    elif state.exists():
        shutil.rmtree(state)          # recon 自有草稿：幂等生命周期需干净起点
    state.mkdir(parents=True, exist_ok=True)
    matter_state = state / "matter"
    matter_state.mkdir(parents=True, exist_ok=True)
    registration = state / "service-local.json"
    registration.write_text(json.dumps(
        {"url": "http://127.0.0.1:1", "password": "synthetic-recon"}),
        encoding="utf-8")
    config = {
        "court_inbound_state_root": str(state / "inbound"),
        "anonymizer_contract": "p09/p10",
        "ocr_ports_state_root": str(state / "ocr"),
        "ocr_baseline_interpreter": str(args.interpreter),
        "harness_public_entry": str(
            harness_root / "tools/workflow-tools/harness/public_entry.py"),
        "harness_target": "opencode",
        "harness_state_root": str(matter_state),
        "harness_service_registration": str(registration),
        "harness_timeout": 300,
    }

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
            "fixture": str(corpus), "seed": ATT_SEED,
            "interpreter": str(args.interpreter),
            "anonymizer_src": str(args.anonymizer_src),
            "harness_root": str(harness_root),
            "harness_head": metrics.get("harness_head"),
            "juscite_head": metrics.get("juscite_head"),
            "chain": ["合成法院短信→附件提取（夹具 sha 钉定）",
                      "F41 ocr.batch_* 桥→F40 worker 真跑（GPU fail-closed）",
                      "送达候选确定性提取（正则，禁模型猜测）",
                      "律师人审确认（append-only，翻案具名拒）",
                      "harness.register_material 入库（CommandKey 幂等）",
                      "重复短信三层面幂等（短信账/OCR 批/材料行）"],
            "checks": checks, "metrics": metrics,
            "scope_note": "本单＝F62 v1 验收链（acceptance 文本）：附件 OCR＋"
                          "送达候选人审入库＋重复短信幂等；06 卡「AI 阅读」步"
                          " v1 落为确定性结构化阅读（模型辅助阅读不在本验收命"
                          "令，模型轮次沿 §2.1 纪律）；E24 边界=送达事实不由上"
                          "传日补（候选≠事实，人审前不入正式账）、外部发送/程"
                          "序提醒零触；E17 取证账零触（法院来件非律师取证）；"
                          "期限计算属 E21/F107 面零触；原件字节不出 OCR 状态根"
                          "域（入库材料=OCR 文本衍生物＋溯源）；桌面 UI 面不前"
                          "造（公开面回读）；%APPDATA% 零触碰",
        }
        evidence_dir.mkdir(parents=True, exist_ok=True)
        out_json = evidence_dir / "f62-court-inbound-recon-result.json"
        out_json.write_text(json.dumps(evidence, ensure_ascii=False, indent=1),
                            encoding="utf-8")
        md = [f"# F62 法院来件 OCR 入库链 recon（{profile}）",
              f"- verdict: **{verdict}**  profile={profile}",
              f"- 夹具: {corpus}（seed={ATT_SEED} 全合成）",
              f"- harness: {harness_root} @{metrics.get('harness_head')}",
              f"- anonymizer: {args.anonymizer_src}", ""]
        for c in checks:
            md.append(f"- {'✅' if c['ok'] else '❌'} **{c['name']}**: "
                      f"{c['detail']}")
        md.append("")
        (evidence_dir / "f62-court-inbound-recon-result.md").write_text(
            "\n".join(md), encoding="utf-8")
        print(f"\n[{profile}] {verdict}  checks="
              + "/".join("PASS" if c["ok"] else "FAIL" for c in checks))
        print(f"[{profile}] evidence: {out_json}", flush=True)
        return ok_all

    manifest = json.loads((corpus / "corpus_manifest.json")
                          .read_text(encoding="utf-8"))
    docs = {d["doc_id"]: d for d in manifest["documents"]}
    metrics["harness_head"] = git(harness_root, "rev-parse", "HEAD")
    metrics["juscite_head"] = git(REPO, "rev-parse", "HEAD")

    # --------------------------------------- C00 harness/anonymizer 钉定卫生
    ok, detail = check_harness_root(harness_root)
    if not record("C00_harness_pinned_clean", ok,
                  f"harness 根（{HARNESS_BRANCH} 链头只读消费）：{detail}"):
        return finish(False)
    sys.path.insert(0, str(harness_root / "src"))
    sys.path.insert(0, str(harness_root / "tools" / "workflow-tools"))
    from legal_harness.state.matter_store import MatterStore
    store = MatterStore(matter_state)
    store.create_matter(MATTER, "cas://f62-recon-fixture")

    digest_before = corpus_identity_digest(corpus)

    # ------------------------- C01 短信登记：确定性解析＋附件钉定＋幂等三形态
    def bridge_call(method, payload):
        return bridge(method, payload, config)

    sms_a = {"sms_id": "sms-court-0001", "sender": "合成市第一人民法院",
             "sent_at": "2026-10-17T09:00:00+08:00", "text": SMS_A_TEXT,
             "corpus_root": str(corpus),
             "attachments": [{"doc_id": "att_0001",
                              "path": docs["att_0001"]["pdf"]}]}
    recv = bridge_call("court_inbound.sms_receive",
                       {"matter_id": MATTER, "sms": sms_a})
    c01_ok = (not recv["duplicate"]
              and recv["parsed"]["case_numbers"] == [CASE_A]
              and recv["parsed"]["court"] == "合成市第一人民法院"
              and recv["attachments"][0]["sha256"]
              == sha256_file(corpus / docs["att_0001"]["pdf"]))
    sms_records = list((state / "inbound" / "f62-inbound" / MATTER)
                       .glob("sms-*.json"))
    c01_ok = c01_ok and len(sms_records) == 1
    record("C01_sms_receive_parsed_pinned", c01_ok,
           f"sms_id={recv['sms_id']} 解析案号={recv['parsed']['case_numbers']}"
           f" 法院={recv['parsed']['court']} 附件钉定 sha256="
           f"{recv['attachments'][0]['sha256'][:16]}… 账内记录={len(sms_records)}")

    # 同 id 同内容→重放
    replay = bridge_call("court_inbound.sms_receive",
                         {"matter_id": MATTER, "sms": sms_a})
    # 同内容异 id（网关重发）→去重回既有账
    resent = bridge_call("court_inbound.sms_receive",
                         {"matter_id": MATTER,
                          "sms": dict(sms_a, sms_id="sms-court-0001-retry")})
    # 同 id 异内容→具名拒
    conflict_ok = False
    try:
        bridge_call("court_inbound.sms_receive",
                    {"matter_id": MATTER,
                     "sms": dict(sms_a, text=SMS_A_TEXT + "（篡改）")})
    except Exception as exc:                    # noqa: BLE001 - 断言 typed 码
        conflict_ok = "f62_sms_id_content_conflict" in str(exc)
    sms_records = list((state / "inbound" / "f62-inbound" / MATTER)
                       .glob("sms-*.json"))
    record("C02_duplicate_sms_idempotent_ledger_single",
           replay["duplicate"] is True and resent["duplicate"] is True
           and resent["sms_id"] == "sms-court-0001"
           and resent["deduped_from"] == "sms-court-0001-retry"
           and conflict_ok and len(sms_records) == 1,
           f"同 id 重放={replay['duplicate']}；同内容异 id 去重 "
           f"deduped_from={resent.get('deduped_from')}→既有账；同 id 异内容"
           f"具名拒={conflict_ok}；短信账恒 1 条={len(sms_records) == 1}")

    # --------------------- C03 入件真跑：F41 批→F40 worker（GPU fail-closed）
    run = bridge_call("court_inbound.inbound_run",
                      {"matter_id": MATTER, "sms_id": "sms-court-0001"})
    engine = run.get("engine") or {}
    model_files = (engine.get("model_cache") or {}).get("files") or {}
    values = [c["value"] for c in run["candidates"]]
    c03_ok = (run["batch_id"].startswith("f41-")
              and engine.get("engine") == "paddleocr"
              and engine.get("device") == "gpu:0"
              and engine.get("cuda_compiled") is True
              and bool(model_files)
              and CASE_A in values
              and any(c["doc_id"] == "att_0001" and c["page"] == 1
                      for c in run["candidates"]))
    record("C03_ocr_real_run_gpu_failclosed_candidates",
           c03_ok,
           f"batch={run['batch_id']}（F41 桥登记→F40 钉定解释器 worker 真跑）"
           f" engine=paddleocr@{engine.get('paddleocr_version')}"
           f" paddle={engine.get('paddle_version')} device="
           f"{engine.get('device')} cuda_compiled="
           f"{engine.get('cuda_compiled')} 模型钉定={len(model_files)} 文件；"
           f"送达候选值={values}（短信↔OCR 交叉印证={CASE_A in values}）；"
           f"pages={run['pages']}")
    metrics["batch_id"] = run["batch_id"]
    metrics["candidates"] = run["candidates"]
    if not c03_ok:
        return finish(False)

    # ------------------------------------- C04 跑批幂等（F41 登记口径沿用）
    rerun = bridge_call("court_inbound.inbound_run",
                        {"matter_id": MATTER, "sms_id": "sms-court-0001"})
    record("C04_inbound_run_idempotent",
           rerun["duplicate"] is True
           and rerun["candidates_sha256"] == run["candidates_sha256"]
           and rerun["batch_id"] == run["batch_id"],
           f"重跑 duplicate={rerun['duplicate']} 同批={rerun['batch_id']}"
           f" 候选指纹一致={rerun['candidates_sha256'][:16]}…"
           f"（F41 batch_id=清单 sha 派生幂等）")

    # ------------------------------------------------ C05 人审：守卫＋确认
    cid = run["candidates"][0]["candidate_id"]
    guard_ok = False
    try:
        bridge_call("court_inbound.candidate_review",
                    {"matter_id": MATTER, "sms_id": "sms-court-0001",
                     "reviewer": "律师甲（合成）",
                     "decisions": [{"candidate_id": "cand-nope",
                                    "decision": "confirmed"}]})
    except Exception as exc:                    # noqa: BLE001
        guard_ok = "f62_candidate_unknown" in str(exc)
    review = bridge_call("court_inbound.candidate_review",
                         {"matter_id": MATTER, "sms_id": "sms-court-0001",
                          "reviewer": "律师甲（合成）",
                          "decisions": [
                              {"candidate_id": c["candidate_id"],
                               "decision": "confirmed"}
                              for c in run["candidates"]]})
    flip_ok = False
    try:
        bridge_call("court_inbound.candidate_review",
                    {"matter_id": MATTER, "sms_id": "sms-court-0001",
                     "reviewer": "律师甲（合成）",
                     "decisions": [{"candidate_id": cid,
                                    "decision": "rejected"}]})
    except Exception as exc:                    # noqa: BLE001
        flip_ok = "f62_candidate_review_conflict" in str(exc)
    record("C05_human_review_guards_and_confirm",
           guard_ok and review["counts"]["confirmed"] == len(run["candidates"])
           and review["counts"]["unreviewed"] == 0 and flip_ok,
           f"未知候选具名拒={guard_ok}；逐候选确认 "
           f"{review['counts']['confirmed']}/{len(run['candidates'])} 未审余"
           f"={review['counts']['unreviewed']}；翻案具名拒="
           f"{flip_ok}（E24 纪律：送达认定不静默翻案）")

    # --------------------- C06 入库真跑：harness.register_material＋回读对账
    intake = bridge_call("court_inbound.intake",
                         {"matter_id": MATTER, "sms_id": "sms-court-0001",
                          "actor_id": "lawyer-a-synthetic"})
    listing = bridge_call("harness.list_materials",
                          {"scope": {"kind": "matter", "matterId": MATTER}})
    readback = bridge_call("harness.read_material",
                           {"scope": {"kind": "matter",
                                      "matterId": MATTER},
                            "material_id": intake["material_id"]})
    material_bytes = base64.b64decode(readback["bytesB64"])
    c06_ok = (not intake["replayed"]
              and intake["revision"] == 1
              and len(listing.get("materials") or []) == 1
              and readback["sha256"] == intake["material_sha256"]
              and hashlib.sha256(material_bytes).hexdigest()
              == intake["material_sha256"]
              and CASE_A in material_bytes.decode("utf-8"))
    record("C06_intake_register_readback_single_material",
           c06_ok,
           f"material={intake['material_id']} rev={intake['revision']}"
           f" sha={intake['material_sha256'][:16]}…（CAS 回读逐字节核对="
           f"{readback['sha256'] == intake['material_sha256']}）；"
           f"harness 材料行恰 1；入库文本含交叉印证案号；requestId="
           f"{intake['request_id'][:40]}…")
    metrics["intake_request_id"] = intake["request_id"]
    metrics["material_id"] = intake["material_id"]
    if not c06_ok:
        return finish(False)

    # --------------- C07 重复短信幂等收口：产品重放＋harness 同键重放＋单行
    replay_intake = bridge_call("court_inbound.intake",
                                {"matter_id": MATTER,
                                 "sms_id": "sms-court-0001",
                                 "actor_id": "lawyer-a-synthetic"})
    count_after_replay = len(bridge_call(
        "harness.list_materials",
        {"scope": {"kind": "matter", "matterId": MATTER}})
        .get("materials") or [])
    # harness 层幂等：产品侧入库账丢失（模拟重试）→同 requestId 重放原回执
    intake_record = (state / "inbound" / "f62-inbound" / MATTER
                     / "intake-sms-court-0001.json")
    saved = intake_record.read_bytes()
    intake_record.unlink()
    retry = bridge_call("court_inbound.intake",
                        {"matter_id": MATTER, "sms_id": "sms-court-0001",
                         "actor_id": "lawyer-a-synthetic"})
    count_after_retry = len(bridge_call(
        "harness.list_materials",
        {"scope": {"kind": "matter", "matterId": MATTER}})
        .get("materials") or [])
    harness_replay_same = (retry["request_id"] == intake["request_id"]
                           and retry["material_sha256"]
                           == intake["material_sha256"]
                           and retry["revision"] == 1)
    record("C07_duplicate_sms_full_chain_single_material",
           replay_intake["replayed"] is True
           and count_after_replay == 1
           and harness_replay_same and count_after_retry == 1,
           f"产品侧重放={replay_intake['replayed']}（材料行="
           f"{count_after_replay}）；入库账丢失后同键重试→harness 同 "
           f"CommandKey 重放原回执（rev 仍 1、sha 相等="
           f"{harness_replay_same}）材料行仍={count_after_retry}"
           f"＝重复短信全链恰一条材料")

    # ------------------------------- C08 未审不入库＋附件篡改拒跑（负向面）
    sms_b = {"sms_id": "sms-court-0002", "sender": "合成市第一人民法院",
             "sent_at": "2026-10-17T09:30:00+08:00", "text": SMS_B_TEXT,
             "corpus_root": str(corpus),
             "attachments": [{"doc_id": "att_0002",
                              "path": docs["att_0002"]["pdf"]}]}
    bridge_call("court_inbound.sms_receive",
                {"matter_id": MATTER, "sms": sms_b})
    bridge_call("court_inbound.inbound_run",
                {"matter_id": MATTER, "sms_id": "sms-court-0002"})
    guard_intake = False
    try:
        bridge_call("court_inbound.intake",
                    {"matter_id": MATTER, "sms_id": "sms-court-0002",
                     "actor_id": "lawyer-a-synthetic"})
    except Exception as exc:                    # noqa: BLE001
        guard_intake = ("f62_intake_chain_incomplete" in str(exc)
                        or "f62_intake_unreviewed_candidates" in str(exc))
    # 附件篡改：派生副本语料（主夹具只读锚零接触）
    tamper_dir = TEMP / f"juscite-f62-tampercorpus-{profile}"
    if tamper_dir.exists():
        shutil.rmtree(tamper_dir)
    shutil.copytree(corpus, tamper_dir)
    sms_t = {"sms_id": "sms-court-t", "sender": "合成市第一人民法院",
             "sent_at": "2026-10-17T11:00:00+08:00", "text": SMS_A_TEXT,
             "corpus_root": str(tamper_dir),
             "attachments": [{"doc_id": "att_0001",
                              "path": docs["att_0001"]["pdf"]}]}
    bridge_call("court_inbound.sms_receive",
                {"matter_id": MATTER, "sms": sms_t})
    tampered = tamper_dir / docs["att_0001"]["pdf"]
    original = tampered.read_bytes()
    tampered.write_bytes(original + b"F62-SYNTHETIC-TAMPER")
    tamper_ok = False
    try:
        bridge_call("court_inbound.inbound_run",
                    {"matter_id": MATTER, "sms_id": "sms-court-t"})
    except Exception as exc:                    # noqa: BLE001
        tamper_ok = "f62_attachment_changed" in str(exc)
    finally:
        tampered.write_bytes(original)
    record("C08_unreviewed_intake_refused_attachment_tamper_refused",
           guard_intake and tamper_ok,
           f"未人审入库具名拒={guard_intake}（E24：送达事实不由上传日补）；"
           f"副本语料附件篡改→钉定复验拒跑={tamper_ok}（主夹具零接触）")

    # ------------------------------------- C09 桥 fail-closed＋AST 导入闭集
    fc_ok = False
    try:
        bridge("court_inbound.intake",
               {"matter_id": MATTER, "sms_id": "sms-court-0001"}, {})
    except Exception as exc:                    # noqa: BLE001
        fc_ok = "f62_state_root_not_configured" in str(exc)
    unknown_ok = False
    try:
        bridge("court_inbound.explode", {}, config)
    except Exception as exc:                    # noqa: BLE001
        unknown_ok = "method_not_connected" in str(exc)
    tree = ast.parse((REPO / "implementation" / "python" / "court_inbound.py")
                     .read_text(encoding="utf-8"))
    imports = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(a.name.split(".")[0] for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.add(node.module.split(".")[0])
    ast_ok = imports <= IMPORT_WHITELIST
    record("C09_bridge_failclosed_ast_import_closure",
           fc_ok and unknown_ok and ast_ok,
           f"未配置状态根 NOT_CONNECTED={fc_ok}；未知方法拒={unknown_ok}；"
           f"产品面 AST 导入闭集⊆确定性白名单（零网络零模型）={ast_ok} "
           f"imports={sorted(imports)}")

    # --------------------------------------------- C10 主夹具只读锚（跑后不变）
    digest_after = corpus_identity_digest(corpus)
    record("C10_fixture_readonly_anchor",
           digest_after == digest_before,
           f"before={digest_before[:16]}… after={digest_after[:16]}… "
           f"{'不变' if digest_after == digest_before else '漂移！'}"
           f"（合成法院来件附件主夹具零接触）")
    return finish(all(c["ok"] for c in checks))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--profile", action="append",
                    choices=["desktop", "selfhost"], default=None)
    ap.add_argument("--corpus", type=Path,
                    default=TEMP / f"juscite-f62-attfixture-{ATT_SEED}")
    ap.add_argument("--state", type=Path, default=None,
                    help="显式状态根（须不存在或为空；默认按 profile 分 "
                         "%TEMP% 独立根，且每次运行重建）")
    ap.add_argument("--interpreter", type=Path, default=DEFAULT_INTERPRETER)
    ap.add_argument("--anonymizer-src", default=None)
    ap.add_argument("--harness-root", default=None)
    args = ap.parse_args()
    profiles = args.profile or ["desktop"]

    if not args.interpreter.is_file():
        eprint(f"[ENV-MISSING] 钉定解释器不存在：{args.interpreter}")
        return 3
    corpus = args.corpus.resolve()
    if not ensure_fixture(corpus):
        eprint(f"[ENV-MISSING] 附件夹具不可得：{corpus}")
        return 3
    anonymizer_src = resolve_anonymizer_src(args.anonymizer_src)
    if anonymizer_src is None:
        eprint("[ENV-MISSING] anonymizer w2a-u18 源不可得"
               "（--anonymizer-src 指定）")
        return 3
    args.anonymizer_src = anonymizer_src
    harness_root = resolve_harness_root(args.harness_root)
    if harness_root is None:
        eprint(f"[ENV-MISSING] harness {HARNESS_BRANCH} worktree 不可得"
               "（--harness-root 指定）")
        return 3
    args.harness_root = harness_root
    if args.state is not None:
        args.state = args.state.resolve()
    bridge, resolved = load_bridge(anonymizer_src)
    if "w2a-u18" not in resolved:
        eprint(f"[ENV-MISSING] anonymizer 源不在 w2a-u18 树：{resolved}")
        return 3
    print(f"[ENV] anonymizer={resolved}")
    print(f"[ENV] harness={harness_root}")
    print(f"[ENV] interpreter={args.interpreter}")

    all_ok = True
    for profile in profiles:
        print(f"\n===== profile {profile} =====", flush=True)
        if args.state is not None and profile != profiles[0]:
            eprint("[ENV-MISSING] 显式 --state 只支持单 profile 运行")
            return 3
        all_ok = run_profile(profile, args, corpus, harness_root, bridge) \
            and all_ok
    print(f"\n{'RECON_OK' if all_ok else 'RECON_FAIL'}"
          f"（profiles={profiles}）")
    return 0 if all_ok else 2


if __name__ == "__main__":
    raise SystemExit(main())

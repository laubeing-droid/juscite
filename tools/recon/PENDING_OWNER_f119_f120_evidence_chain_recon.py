#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""F119 证据目录/清单生成＋F120 质证意见生成 验收 recon（W4-U51）。

义务 06:F119（v1.5）acceptance「证据编号/页段/待证事项真实生成横向目录；
媒体加工单独可回读」＋06:F120 acceptance「质证意见绑定证据和反方观点，
律师可编辑终审；空证据不编质证」；17 卡两卡 target＝Harness
ApplicationService＋产品 UI，entries P02/P04（F120 另 P01）。

双 profile：
  desktop＝产品桥全链（legal_entry → 真 harness public_entry 子进程径，
  --evidencechain-json 等封闭信封；SQLite 状态根）；
  selfhost＝PgMatterStore 直连 lh-pg-e08（同封闭注册，独立 schema；产品
  面 evidence_catalog/cross_exam 的 harness seam 注入 PG 绑定方法——
  E17/U05/U31 同款 seam 先例），账本面同一方法组同一断言。

全合成材料（E12 语料生成器 24 页全合成＋ffmpeg lavfi 合成视频＋手造最
小 PDF；引文锚点＝E22 冻结面真实行内事实，与 F87 recon 同锚同钉）。
harness 侧钉定 w4-u51 战役分支 worktree（A2 分支链；树必须净）。
夹具建账（create_matter/save_issue/register_material 源材料）经直接
units（F62 recon 先例）；受测面（证据账/媒体账/质证账/生成/决定）全部
走产品桥封闭信封。

用法（juscite worktree w4-u51 仓根 cwd）：
  python -X utf8 tools/recon/PENDING_OWNER_f119_f120_evidence_chain_recon.py --profile desktop --profile selfhost
  [--corpus <dir>] [--pg-dsn ...] [--harness-root <path>] [--anonymizer-src <path>]
  [--formal-root <path>] [--codices-repo <path>]

退出码：0＝全部 profile RECON_OK；2＝RECON_FAIL；3＝环境缺失。
"""
from __future__ import annotations

import argparse
import ast
import base64
import hashlib
import io
import json
import os
import subprocess
import sys
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
TEMP = Path(os.environ.get("TEMP", "."))
HARNESS_BRANCH = "w4-u51"
CORPUS_PAGES = 24
CORPUS_SEED = 20261015
AS_OF = "20261021"
MATTER = "m-f119f120-recon"
MATTER_EMPTY = "m-f119f120-empty"
DEFAULT_PG_DSN = ("postgresql://lh_app:e08-synth-only"
                  "@127.0.0.1:55432/legal_harness")

# E22 冻结面 v1.1（codices 分支 jusbench/w2a-u14-f70-citation）。
DEFAULT_FORMAL_ROOT = (
    r"D:\Codex\1.法律工作区\legal-cn-core-codices工作区\legal-cn-core-codices")
DEFAULT_CODICES_REPO = (
    r"D:\Codex\1.法律工作区\legal-cn-core-codices工作区"
    r"\legal-cn-core-codices-repo\.local\worktrees\w2a-u14")
LCCC_V11_SHA256 = (
    "55eea7c27e08d6b236b7ab7a83810c86ee0898c335c4668d875a492775db863a")

CITE_TITLE = "中华人民共和国个人信息保护法"
CITE_QUOTE = ("为了保护个人信息权益，规范个人信息处理活动，"
              "促进个人信息合理利用，根据宪法，制定本法。")
FABRICATED_TITLE = "中华人民共和国月球资源开发管辖法"

# 产品面确定性 AST 闭集（零网络零模型）：标准库＋本地确定性引擎/冻结面
# ——docx/lxml＝独立检查器解析路径（python-docx lxml 算路）；pypdfium2
# ＝PDF 渲染引擎（F54 同款本地引擎）；author_policy＝F53 冻结策略面；
# citation_verifier＝W2a-U14 冻结引用解析面。
PRODUCT_IMPORT_WHITELIST = {
    "__future__", "base64", "hashlib", "io", "json", "os", "re", "struct",
    "subprocess", "tempfile", "threading", "zipfile", "zlib",
    "xml", "pathlib", "bridge_errors", "legal_entry",
    "docx", "lxml", "pypdfium2", "author_policy", "citation_verifier",
}

MINI_PDF = (b"%PDF-1.4\n1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\n"
            b"endobj\n2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\n"
            b"endobj\n3 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox "
            b"[0 0 612 792] >>\nendobj\ntrailer\n<< /Size 4 /Root 1 0 R >>\n"
            b"startxref\n9\n%%EOF\n")


def eprint(*a) -> None:
    print(*a, file=sys.stderr, flush=True)


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def corpus_identity_digest(corpus: Path) -> str:
    parts = []
    for p in sorted(corpus.rglob("*")):
        if p.is_file():
            parts.append(p.relative_to(corpus).as_posix() + ":"
                         + sha256_bytes(p.read_bytes()))
    return hashlib.sha256("\n".join(parts).encode("utf-8")).hexdigest()


def git(root: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(root), *args], capture_output=True, text=True,
        encoding="utf-8", errors="replace", timeout=60).stdout.strip()


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
    env = os.environ.get("JUSCITE_W4U51_HARNESS_ROOT")
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


def ensure_corpus(corpus: Path) -> bool:
    if (corpus / "corpus_manifest.json").is_file():
        return True
    corpus.parent.mkdir(parents=True, exist_ok=True)
    eprint(f"[GEN] E12 语料不存在，生成（seed={CORPUS_SEED} "
           f"pages={CORPUS_PAGES}）→ {corpus}")
    proc = subprocess.run(
        [sys.executable, "-X", "utf8",
         str(REPO / "tools" / "e12_corpus_gen.py"),
         "--pages", str(CORPUS_PAGES), "--seed", str(CORPUS_SEED),
         "--out", str(corpus)],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        timeout=1800)
    if proc.returncode != 0:
        eprint((proc.stdout or "")[-800:], (proc.stderr or "")[-800:])
        return False
    return (corpus / "corpus_manifest.json").is_file()


def synth_video(workdir: Path) -> bytes | None:
    """ffmpeg lavfi 合成短视频（bitexact 钉定；全合成材料）。"""
    out = workdir / "synth-src.mp4"
    if out.is_file():
        return out.read_bytes()
    workdir.mkdir(parents=True, exist_ok=True)
    argv = ["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i",
            "testsrc=duration=3:size=160x90:rate=2",
            "-c:v", "libx264", "-pix_fmt", "yuv420p",
            "-fflags", "+bitexact", "-flags:v", "+bitexact",
            str(out)]
    proc = subprocess.run(argv, capture_output=True, timeout=300)
    if proc.returncode != 0 or not out.is_file():
        eprint("[ffmpeg]", (proc.stderr or b"")[-400:])
        return None
    return out.read_bytes()


def load_bridge(anonymizer_src: Path):
    sys.path.insert(0, str(REPO / "implementation" / "python"))
    sys.path.insert(0, str(anonymizer_src))
    import legal_anonymizer  # noqa: F401 - 解析面验证
    import legal_entry
    return legal_entry


class Recon:
    def __init__(self) -> None:
        self.checks: list[dict] = []

    def add(self, name: str, ok: bool, detail: str) -> None:
        self.checks.append({"check": name,
                            "status": "PASS" if ok else "FAIL",
                            "detail": detail})
        print(f"[{'PASS' if ok else 'FAIL'}] {name}: {detail}", flush=True)

    @property
    def all_ok(self) -> bool:
        return bool(self.checks) and all(c["status"] == "PASS"
                                         for c in self.checks)


def run_profile(profile: str, legal_entry, harness_root: Path,
                corpus: Path, pg_dsn: str, recon: Recon) -> bool:
    """单 profile 全链对账。desktop＝真子进程径；selfhost＝PG 直连 seam。"""
    state = Path(tempfile.mkdtemp(prefix=f"juscite-f119-{profile}-"))
    scope = {"kind": "matter", "matterId": MATTER}
    empty_scope = {"kind": "matter", "matterId": MATTER_EMPTY}

    def key(rid: str) -> dict:
        return {"requestId": rid, "targetId": None,
                "expectedRevision": None, "inputRefs": []}

    config = {
        "anonymizer_contract": "p09/p10",
        "material_parse_state_root": str(state),
        "evidence_catalog_state_root": str(state / "cat"),
        "cross_exam_state_root": str(state / "cx"),
        "extraction_gate_state_root": str(state / "gate"),
        "codices_import_path": str(CODES_REPO),
        "codices_formal_root": str(FORMAL_ROOT),
        "codices_face_sha256": LCCC_V11_SHA256,
    }
    store = None
    units = None
    patches: list = []
    if profile == "desktop":
        registration = state / "service-local.json"
        registration.write_text(json.dumps(
            {"url": "http://127.0.0.1:1", "password": "synthetic-recon"}),
            encoding="utf-8")
        config.update({
            "harness_public_entry": str(
                harness_root
                / "tools/workflow-tools/harness/public_entry.py"),
            "harness_target": "opencode",
            "harness_state_root": str(state / "matter"),
            "harness_service_registration": str(registration),
            "harness_timeout": 300,
        })
        sys.path.insert(0, str(harness_root / "src"))
        from legal_harness.business.units import HarnessUnits
        from legal_harness.state.matter_store import MatterStore
        store = MatterStore(Path(config["harness_state_root"]))
        units = HarnessUnits(store)

        def call(method, args):
            return legal_entry.call(method, args, config)
    else:
        sys.path.insert(0, str(harness_root / "src"))
        from legal_harness.business.provider_registry import (
            resolve_provider_method)
        from legal_harness.business.units import HarnessUnits
        from legal_harness.state.pg_store import PgMatterStore
        store = PgMatterStore(state / "matter", dsn=pg_dsn,
                              schema="f119_" + uuid.uuid4().hex[:12])
        units = HarnessUnits(store)
        methods = {
            "harness.evidence_register", "harness.evidence_read",
            "harness.evidence_list", "harness.evidence_media_op_record",
            "harness.evidence_media_op_read",
            "harness.evidence_media_op_list",
            "harness.cross_exam_draft_record", "harness.cross_exam_read",
            "harness.cross_exam_list", "harness.formal_propose",
            "harness.formal_decide", "harness.formal_proposal_list",
            "harness.register_material", "harness.read_material",
        }
        bound = {name: resolve_provider_method(name, units)
                 for name in methods}
        import evidence_catalog as ec_module
        import cross_exam as cx_module

        def seam_bridge(method, args, cfg):
            if method in bound:
                return bound[method](**args)
            return legal_entry.call(method, args, config)

        for module in (ec_module, cx_module):
            patcher = (module, "_bridge_call", module._bridge_call,
                       seam_bridge)
            patches.append(patcher)
            setattr(module, "_bridge_call", seam_bridge)

        def call(method, args):
            # selfhost＝账本面直连 PG（同封闭注册）；产品面（解析/生成/
            # 闸）仍走 legal_entry 同一进程径。
            if method in bound:
                return bound[method](**args)
            return legal_entry.call(method, args, config)

    def fixture(fn, *a, **kw):
        return fn(*a, **kw)

    try:
        # ------------------------------------------ C00 钉定卫生（桌面径）
        if profile == "desktop":
            branch = git(harness_root, "rev-parse", "--abbrev-ref", "HEAD")
            head = git(harness_root, "rev-parse", "HEAD")
            dirty = git(harness_root, "status", "--porcelain")
            recon.add(
                "C00_harness_branch_pinned_clean",
                branch == HARNESS_BRANCH and dirty == "",
                f"harness 根＝{HARNESS_BRANCH} 战役分支链（A2）head="
                f"{head[:12]} dirty={bool(dirty)}")
        lccc = Path(CODES_REPO) / "lccc_consumer.py"
        face_ok = (lccc.is_file()
                   and sha256_bytes(lccc.read_bytes()) == LCCC_V11_SHA256)
        recon.add(
            "C00b_codices_face_pinned", face_ok,
            f"E22 冻结面 v1.1 lccc_consumer.py sha256="
            f"{sha256_bytes(lccc.read_bytes())[:16]}…（漂移即拒）")
        if not recon.all_ok:
            return False

        # ------------------------------------------------ C01 合成夹具＋解析
        digest_before = corpus_identity_digest(corpus)
        reg = call("material.parse_register", {"corpus_root": str(corpus)})
        batch_id = reg.get("batch_id")
        if not batch_id:
            eprint("[FATAL] parse_register 失败：", reg)
            recon.add("C01_parse_batch_real_run", False, "登记失败")
            return False
        call("material.parse_process", {"batch_id": batch_id})
        report = call("material.parse_report", {"batch_id": batch_id})
        manifest = json.loads((corpus / "corpus_manifest.json")
                              .read_text(encoding="utf-8"))
        doc_ids = sorted(d["doc_id"] for d in manifest["documents"])
        parse_ok = (report.get("completed") == report.get("registered_pages")
                    and report.get("pending") == 0 and bool(doc_ids))
        recon.add(
            "C01_parse_batch_real_run", parse_ok,
            f"batch={batch_id} completed={report.get('completed')}/"
            f"{report.get('registered_pages')} docs={doc_ids[:3]}…"
            f"（E12 解析真跑＝页段绑定面）")
        if not parse_ok:
            return False

        # --------------------------- C02 harness 夹具（直接 units，F62 先例）
        store.create_matter(MATTER, "cas://f119-recon")
        store.create_matter(MATTER_EMPTY, "cas://f119-empty")
        units.save_issue(
            "lawyer-1", scope, key("iss"),
            {"id": "iss-1", "revision": 1,
             "title": "对方主张货款已付清（合成）", "claimRefs": [],
             "factRefs": [], "partyIds": ["party-defendant"]})
        mat_pdf = units.register_material(
            "lawyer-1", scope, key("mpdf"),
            {"id": "mat-pdf", "kind": "scan",
             "title": "书证源材料（合成 PDF）",
             "bytesB64": base64.b64encode(MINI_PDF).decode("ascii")})
        video_bytes = synth_video(state / "media-src")
        if video_bytes is None:
            recon.add("C02_fixture_video", False,
                      "ffmpeg lavfi 合成视频不可得（引擎缺失）")
            return False
        mat_vid = units.register_material(
            "lawyer-1", scope, key("mvid"),
            # harness MATERIAL_KINDS 闭集无 audio_video（材料类目≠证据
            # 形式类目）；视频源材料按闭集 honest 落 unknown。
            {"id": "mat-vid", "kind": "unknown",
             "title": "视听资料源（合成视频）",
             "bytesB64": base64.b64encode(video_bytes).decode("ascii")})
        recon.add(
            "C02_fixture_materials_issue_pinned",
            mat_pdf["revision"] == 1 and mat_vid["revision"] == 1,
            f"mat-pdf={mat_pdf['sha256'][:12]}… mat-vid="
            f"{mat_vid['sha256'][:12]}…（CAS 钉定）＋反方观点 iss-1 在案"
            f"（直接 units 夹具，F62 recon 先例）")

        # ------------------------------------------------ C03 证据目录登记
        d1, d2 = doc_ids[0], doc_ids[-1]
        call("harness.evidence_register", {
            "actor_id": "lawyer-1", "scope": scope, "key": key("ev1"),
            "evidence": {
                "evidenceId": "ev-1", "evidenceNo": "原告证据一",
                "name": "购销合同（合成）", "kind": "documentary",
                "sourceParty": "plaintiff",
                "materialRef": {"materialId": "mat-pdf", "revision": 1},
                "pageSegments": [{"docId": d1, "pageFrom": 1,
                                  "pageTo": 2}],
                "proveFacts": ["证明双方买卖合同关系（合成）",
                               "证明交付事实（合成）"]}})
        call("harness.evidence_register", {
            "actor_id": "lawyer-1", "scope": scope, "key": key("ev2"),
            "evidence": {
                "evidenceId": "ev-2", "evidenceNo": "原告证据二",
                "name": "现场视频（合成）", "kind": "audio_video",
                "sourceParty": "plaintiff",
                "materialRef": {"materialId": "mat-vid", "revision": 1},
                "pageSegments": [{"docId": d2, "pageFrom": 1,
                                  "pageTo": 1}],
                "proveFacts": ["证明货物现状（合成）"]}})
        ev1_head = call("harness.evidence_read", {
            "scope": scope, "evidence_id": "ev-1"})
        listing = call("harness.evidence_list", {"scope": scope})
        chain_ok = (ev1_head["revision"] == 1 and listing["count"] == 2
                    and [r["evidenceNo"] for r in listing["items"]]
                    == ["原告证据一", "原告证据二"])
        recon.add(
            "C03_evidence_register_chain", chain_ok,
            f"两证据入账（编号/页段/待证事项闭形，封闭信封）＋头行回读 "
            f"revision={ev1_head['revision']} 清单={listing['count']} 行")
        if not chain_ok:
            return False

        neg_ok = dup_ok = False
        try:
            call("harness.evidence_register", {
                "actor_id": "lawyer-1", "scope": scope,
                "key": key("evneg"),
                "evidence": {
                    "evidenceId": "ev-x", "evidenceNo": "原告证据三",
                    "name": "幽灵证据（合成）", "kind": "documentary",
                    "sourceParty": "plaintiff",
                    "materialRef": {"materialId": "mat-missing",
                                    "revision": 1},
                    "pageSegments": [{"docId": d1, "pageFrom": 1,
                                      "pageTo": 1}],
                    "proveFacts": ["无锚证明（合成）"]}})
        except Exception as exc:  # noqa: BLE001
            neg_ok = "f119_material_ref_not_found" in str(exc)
        try:
            call("harness.evidence_register", {
                "actor_id": "lawyer-1", "scope": scope,
                "key": key("evdup"),
                "evidence": {
                    "evidenceId": "ev-y", "evidenceNo": "原告证据一",
                    "name": "抢号证据（合成）", "kind": "documentary",
                    "sourceParty": "plaintiff",
                    "materialRef": {"materialId": "mat-pdf",
                                    "revision": 1},
                    "pageSegments": [{"docId": d1, "pageFrom": 1,
                                      "pageTo": 1}],
                    "proveFacts": ["抢号（合成）"]}})
        except Exception as exc:  # noqa: BLE001
            dup_ok = "f119_evidence_no_conflict" in str(exc)
        recon.add(
            "C04_evidence_ledger_guards", neg_ok and dup_ok,
            f"不锚材料证据具名拒={neg_ok}；同案证据编号唯一={dup_ok}"
            f"（账本级结构断言：目录只能从在账证据真实生成）")

        # ------------------------------------- C05 目录真实生成（八维硬门）
        cat1 = call("evidencecat.generate", {
            "matter_id": MATTER, "parse_batch_id": batch_id,
            "request_id": "req-cat-1"})
        cat_replay = call("evidencecat.generate", {
            "matter_id": MATTER, "parse_batch_id": batch_id,
            "request_id": "req-cat-1"})
        cat2 = call("evidencecat.generate", {
            "matter_id": MATTER, "parse_batch_id": batch_id,
            "request_id": "req-cat-2"})
        cat_ok = (cat1["rows"] == 2 and cat1 == cat_replay
                  and cat1["content_digest"] == cat2["content_digest"])
        recon.add(
            "C05_catalog_generate_gate_replay_determinism", cat_ok,
            f"横向目录真生成 rows={cat1['rows']}（八维硬门过＝可打开/横向/"
            f"干净/表头/行投影/页段绑定/待证事项/链路列）；同请求重放幂等="
            f"{cat1 == cat_replay}；异请求两跑 content_digest="
            f"{cat1['content_digest'][:16]}… 相等＝确定性")
        if not cat_ok:
            return False

        read_out = call("evidencecat.read", {
            "matter_id": MATTER, "request_id": "req-cat-1"})
        import docx as pydocx
        doc = pydocx.Document(io.BytesIO(
            base64.b64decode(read_out["docx_b64"])))
        table = doc.tables[0]
        header = [c.text for c in table.rows[0].cells]
        landscape = str(doc.sections[0].orientation).startswith("LANDSCAPE")
        seg_cell = table.rows[1].cells[4].text
        proj_ok = (len(doc.tables) == 1 and landscape
                   and header == ["证据编号", "证据名称", "证据形式",
                                  "举证方", "页段", "待证事项", "媒体加工",
                                  "关联质证"]
                   and table.rows[1].cells[0].text == "原告证据一"
                   and f"{d1} 第1-2页" in seg_cell
                   and "证明双方买卖合同关系（合成）"
                   in table.rows[1].cells[5].text)
        recon.add(
            "C06_catalog_docx_openable_projection", proj_ok,
            f"独立回读：横向={landscape} 表头八列冻结闭集；页段格＝"
            f"“{seg_cell}”（E12 绑定投影）；待证事项格投影在文")
        if not proj_ok:
            return False

        empty_ok = False
        try:
            call("evidencecat.generate", {
                "matter_id": MATTER_EMPTY, "parse_batch_id": batch_id,
                "request_id": "req-empty"})
        except Exception as exc:  # noqa: BLE001
            empty_ok = "f119_empty_catalog_no_fabrication" in str(exc)
        recon.add(
            "C07_empty_catalog_refused", empty_ok,
            f"空目录具名拒不产空文书={empty_ok}（目录真实生成＝零编行）")

        # ------------------------------------- C08 媒体加工（真跑＋可回读）
        probe = call("evidencecat.media_probe", {})
        engines = probe["engines"]
        pdf_ok = engines["pdf_to_image"].get("available") is True
        recon.add(
            "C08_media_probe_honest", pdf_ok,
            f"引擎探测：pdf_to_image available={pdf_ok}（pypdfium2）；"
            f"video_frame_extract available="
            f"{engines['video_frame_extract'].get('available')} "
            f"engine={engines['video_frame_extract'].get('engine')}")
        if not pdf_ok:
            return False

        mo1 = call("evidencecat.media_process", {
            "matter_id": MATTER, "media_op_id": "mo-pdf-1",
            "actor_id": "assistant-1", "evidence_id": "ev-1",
            "op_kind": "pdf_to_image",
            "source": {"material_id": "mat-pdf", "revision": 1},
            "dpi": 120, "pages": [1]})
        mo2 = call("evidencecat.media_process", {
            "matter_id": MATTER, "media_op_id": "mo-pdf-2",
            "actor_id": "assistant-1", "evidence_id": "ev-1",
            "op_kind": "pdf_to_image",
            "source": {"material_id": "mat-pdf", "revision": 1},
            "dpi": 120, "pages": [1]})
        rd1 = call("evidencecat.media_read", {
            "matter_id": MATTER, "media_op_id": "mo-pdf-1"})
        trail = call("harness.evidence_media_op_read", {
            "scope": scope, "media_op_id": "mo-pdf-1"})
        pdf_det = (mo1["outputs"][0]["sha256"] == mo2["outputs"][0]["sha256"]
                   == rd1["outputs"][0]["sha256"])
        recon.add(
            "C09_media_pdf_real_traceable_deterministic", pdf_det,
            f"PDF→图真跑×2：同参数两跑同 sha="
            f"{mo1['outputs'][0]['sha256'][:16]}…；media_read 逐字节复验"
            f"一致；留痕入账（输入 sha 钉定="
            f"{trail['inputRef']['sha256'][:12]}… 引擎={trail['engine']}）")
        if not pdf_det:
            return False

        if not engines["video_frame_extract"].get("available"):
            recon.add("C10_media_video_real_traceable_deterministic", False,
                      "ffmpeg 缺席＝本机无法真跑（F40 纪律：不假留痕）")
            return False
        mv1 = call("evidencecat.media_process", {
            "matter_id": MATTER, "media_op_id": "mo-vid-1",
            "actor_id": "assistant-1", "evidence_id": "ev-2",
            "op_kind": "video_frame_extract",
            "source": {"material_id": "mat-vid", "revision": 1},
            "seek_times_sec": [0, 1], "max_frames": 2})
        mv2 = call("evidencecat.media_process", {
            "matter_id": MATTER, "media_op_id": "mo-vid-2",
            "actor_id": "assistant-1", "evidence_id": "ev-2",
            "op_kind": "video_frame_extract",
            "source": {"material_id": "mat-vid", "revision": 1},
            "seek_times_sec": [0, 1], "max_frames": 2})
        rdv = call("evidencecat.media_read", {
            "matter_id": MATTER, "media_op_id": "mo-vid-1"})
        same = ([a["sha256"] for a in mv1["outputs"]]
                == [a["sha256"] for a in mv2["outputs"]]
                == [a["sha256"] for a in rdv["outputs"]])
        vid_ok = len(mv1["outputs"]) == 2 and same
        recon.add(
            "C10_media_video_real_traceable_deterministic", vid_ok,
            f"视频抽帧真跑（ffmpeg seek=[0,1]s）：2 帧留痕；两跑＋回读 sha "
            f"逐帧一致={same}（首帧 {mv1['outputs'][0]['sha256'][:16]}…）")
        if not vid_ok:
            return False

        mo_neg = False
        try:
            call("evidencecat.media_process", {
                "matter_id": MATTER, "media_op_id": "mo-neg",
                "actor_id": "assistant-1", "evidence_id": "ev-none",
                "op_kind": "pdf_to_image",
                "source": {"material_id": "mat-pdf", "revision": 1},
                "dpi": 120, "pages": [1]})
        except Exception as exc:  # noqa: BLE001
            mo_neg = "f119_evidence_unresolved" in str(exc)
        ops_list = call("harness.evidence_media_op_list", {"scope": scope})
        recon.add(
            "C11_media_guards_and_ledger",
            mo_neg and ops_list["count"] == 4,
            f"不在账证据加工具名拒={mo_neg}；媒体留痕账 {ops_list['count']}"
            f" 条（2 PDF＋2 视频＝单独可回读，不混目录行）")

        # ------------------------------------- C12 质证（负向四连＋真链）
        neg_empty = neg_ref = neg_asof = neg_gate = False
        try:
            call("crossexam.generate", {
                "matter_id": MATTER_EMPTY, "opinion_id": "cx-e",
                "request_id": "r-e", "actor_id": "a",
                "claims": [{"claim_id": "c", "evidence_id": "ev-1",
                            "counter_issue_id": "iss-1",
                            "position": "authenticity", "text": "x"}]})
        except Exception as exc:  # noqa: BLE001
            neg_empty = ("crossexam_empty_evidence_no_fabrication"
                         in str(exc))
        try:
            call("crossexam.generate", {
                "matter_id": MATTER, "opinion_id": "cx-r",
                "request_id": "r-r", "actor_id": "a",
                "claims": [{"claim_id": "c", "evidence_id": "ev-1",
                            "position": "authenticity", "text": "x"}]})
        except Exception as exc:  # noqa: BLE001
            neg_ref = "crossexam_claim_ref_required" in str(exc)
        try:
            call("crossexam.generate", {
                "matter_id": MATTER, "opinion_id": "cx-a",
                "request_id": "r-a", "actor_id": "a",
                "claims": [{"claim_id": "c", "evidence_id": "ev-1",
                            "counter_issue_id": "iss-1",
                            "position": "legality",
                            "text": f"依据《{CITE_TITLE}》第一条（合成）。"}]})
        except Exception as exc:  # noqa: BLE001
            neg_asof = "crossexam_gate_as_of_required" in str(exc)
        try:
            call("crossexam.generate", {
                "matter_id": MATTER, "opinion_id": "cx-bad",
                "request_id": "r-bad", "actor_id": "a",
                "as_of": AS_OF,
                "claims": [{"claim_id": "c", "evidence_id": "ev-1",
                            "counter_issue_id": "iss-1",
                            "position": "legality",
                            "text": f"依据《{FABRICATED_TITLE}》第一条，"
                                    f"对方主张不能成立（合成）。"}]})
        except Exception as exc:  # noqa: BLE001
            neg_gate = ("crossexam_gate_rejected" in str(exc)
                        and "FABRICATED_TITLE_LOCAL_MISS" in str(exc))
        negs_ok = neg_empty and neg_ref and neg_asof and neg_gate
        recon.add(
            "C12_crossexam_structural_negatives", negs_ok,
            f"空证据不编质证={neg_empty}；无反方观点 ref 主张不生成="
            f"{neg_ref}；引用缺 as_of 拒={neg_asof}；虚构标题过闸整单拒="
            f"{neg_gate}（F87 闸真跑，fail-closed 不静默丢主张）")
        if not negs_ok:
            return False

        gen = call("crossexam.generate", {
            "matter_id": MATTER, "opinion_id": "cx-1",
            "request_id": "r-cx-1", "actor_id": "assistant-1",
            "as_of": AS_OF,
            "claims": [
                {"claim_id": "c-1", "evidence_id": "ev-1",
                 "counter_issue_id": "iss-1", "position": "authenticity",
                 "text": "该证据系原件扫描件，形式完整，真实性无异议（合成）。"},
                {"claim_id": "c-2", "evidence_id": "ev-1",
                 "counter_issue_id": "iss-1", "position": "legality",
                 "text": f"依据《{CITE_TITLE}》第一条：“{CITE_QUOTE}”，"
                         f"对方取得证据的程序合法性存疑（合成）。"},
            ]})
        draft = call("harness.cross_exam_read", {
            "scope": scope, "opinion_id": "cx-1"})
        claims = draft["claims"]
        gated = [c for c in claims if c["citesLaw"]]
        plain = [c for c in claims if not c["citesLaw"]]
        bound_ok = (
            gen["claims_recorded"] == 2 and len(claims) == 2
            and len(gated) == 1 and len(plain) == 1
            and bool(gated) and gated[0]["gateRef"] is not None
            and gated[0]["gateRef"]["gateStatus"] == "CITATION_VERIFIED"
            and plain[0]["gateRef"] is None
            and all(c["evidenceRef"]["id"] == "ev-1" for c in claims)
            and all(c["counterRef"]["id"] == "iss-1" for c in claims))
        recon.add(
            "C13_crossexam_full_chain_bound_gated", bound_ok,
            f"质证真生成：主张 2 条全绑定（证据 ref＋反方观点 ref 各在案）；"
            f"引用主张过 F87 闸 gateStatus=CITATION_VERIFIED（gateBatch="
            f"{gated[0]['gateRef']['gateBatchId'] if gated and gated[0]['gateRef'] else '?'}）；"
            f"非引用主张无闸凭据；意见文书入材料链 material="
            f"{gen['material_id']} 提案={gen['proposal_id']}")
        if not bound_ok:
            return False

        read_cx = call("crossexam.read", {
            "matter_id": MATTER, "opinion_id": "cx-1"})
        proj = read_cx["author_decision_projection"]
        row = proj["rows"][0]
        pre_ok = (len(proj["rows"]) == 1 and row["state"] == "pending"
                  and row["author"] == "lvyin-cross-exam"
                  and row["authorPolicy"]["boundChannel"] == "crossexam"
                  and proj["canonical"]["revision"] == 1)
        recon.add(
            "C14_f53_author_and_pending_proposal", pre_ok,
            f"F53 三方投影：author={row['author']}（机器闭集绑定通道="
            f"crossexam，不伪装律师）；提案 pending；canonical rev="
            f"{proj['canonical']['revision']} source="
            f"{proj['canonical']['source']}")

        no_ref = False
        try:
            call("crossexam.decide", {
                "matter_id": MATTER, "request_id": "r-d0",
                "actor_id": "lawyer-1",
                "proposal_id": gen["proposal_id"],
                "material_id": gen["material_id"], "action": "accept"})
        except Exception as exc:  # noqa: BLE001
            no_ref = "crossexam_decision_ref_required" in str(exc)
        opinion_path = None
        for out_dir in sorted((state / "cx" / "cross-exam" / MATTER
                               / "outputs").iterdir()):
            manifest_path = out_dir / "output.json"
            if not manifest_path.is_file():
                continue
            record = json.loads(manifest_path.read_text(encoding="utf-8"))
            if record.get("request_id") == "r-cx-1":
                opinion_path = out_dir / "opinion.docx"
        if opinion_path is None:
            recon.add("C15_lawyer_final_review_decide", False,
                      "意见产物不可得")
            return False
        doc = pydocx.Document(str(opinion_path))
        doc.paragraphs[0].runs[0].text = "质证意见（cx-1·律师终审）"
        buf = io.BytesIO()
        doc.save(buf)
        dec = call("crossexam.decide", {
            "matter_id": MATTER, "request_id": "r-d1",
            "actor_id": "lawyer-1", "proposal_id": gen["proposal_id"],
            "material_id": gen["material_id"], "action": "accept",
            "reason_ref": {"owner": "host", "kind": "decision",
                           "id": "dr-1", "version": "1"},
            "receipt_ref": {"owner": "host", "kind": "receipt",
                            "id": "rcpt-1", "version": "1"},
            "result_bytes_b64": base64.b64encode(buf.getvalue())
            .decode("ascii")})
        read_cx2 = call("crossexam.read", {
            "matter_id": MATTER, "opinion_id": "cx-1"})
        proj2 = read_cx2["author_decision_projection"]
        row2 = proj2["rows"][0]
        post_ok = (no_ref and "canonical" in dec
                   and row2["state"] == "accepted"
                   and bool(row2.get("decision"))
                   and row2["decision"].get("receiptRef") is not None
                   and proj2["canonical"]["source"] == "user_accept"
                   and proj2["canonical"]["revision"] == 2)
        recon.add(
            "C15_lawyer_final_review_decide", post_ok,
            f"律师编辑终审：空决定面具名拒={no_ref}；accept 带编辑后字节＋"
            f"真实决定引用→canonical rev="
            f"{proj2['canonical']['revision']} source=user_accept"
            f"（F47 人审合同零改动）")

        # ------------------------------------- C16 AST 闭集＋语料锚
        ast_ok = True
        for face in ("evidence_catalog.py", "cross_exam.py"):
            tree = ast.parse((REPO / "implementation" / "python" / face)
                             .read_text(encoding="utf-8"))
            imports = set()
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    imports.update(a.name.split(".")[0]
                                   for a in node.names)
                elif isinstance(node, ast.ImportFrom) and node.module:
                    imports.add(node.module.split(".")[0])
            if not imports <= PRODUCT_IMPORT_WHITELIST:
                ast_ok = False
                eprint(f"[AST] {face}: "
                       f"{sorted(imports - PRODUCT_IMPORT_WHITELIST)}")
        digest_after = corpus_identity_digest(corpus)
        recon.add(
            "C16_ast_closure_and_corpus_anchor",
            ast_ok and digest_after == digest_before,
            f"产品面 AST 导入闭集⊆确定性白名单={ast_ok}（零网络零模型）；"
            f"E12 语料锚 before={digest_before[:12]}… after="
            f"{digest_after[:12]}… 不变")
    finally:
        for module, attr, saved, _value in patches:
            setattr(module, attr, saved)
    return recon.all_ok


def write_evidence(profile: str, recon: Recon, started: str,
                   harness_root: Path, code: int) -> Path:
    evidence_dir = REPO / "docs" / "construction" / "evidence" / "F119" \
        / profile
    evidence_dir.mkdir(parents=True, exist_ok=True)
    (REPO / "docs" / "construction" / "evidence" / "F120" / profile).mkdir(
        parents=True, exist_ok=True)
    summary = {
        "schema": "juscite-f119-f120-evidence-chain-recon/1",
        "unit": "W4-U51",
        "features": ["F119", "F120"],
        "profile": profile,
        "verdict": "RECON_OK" if code == 0 else "RECON_FAIL",
        "started_at": started, "finished_at": now_iso(),
        "harness_root": str(harness_root),
        "harness_branch": HARNESS_BRANCH,
        "harness_head": git(harness_root, "rev-parse", "HEAD"),
        "checks": recon.checks, "check_count": len(recon.checks),
        "failed": [c["check"] for c in recon.checks
                   if c["status"] != "PASS"],
        "scope_note": (
            "F119 横向目录 docx＝产品面纯 Python 真实生成（F45 同构：可打开"
            "/八维硬门/两跑同字节），页段绑定 E12 解析产物页号版本链；媒体加"
            "工单独留痕可回读（PDF→图/视频抽帧真跑）。F120 质证＝绑证据 "
            "ref＋反方观点 ref 生成（无 ref 不生成、空证据不编质证＝结构断"
            "言），引用过 F87 闸（extraction.register→gate 唯一路径），F53 "
            "作者声明透传（lvyin-cross-exam），律师编辑终审＝harness "
            "formal_propose/decide 人审合同（F47 零改动）。harness 侧＝"
            "w4-u51 战役分支链 (A2) schema v33 三账九方法。边界如实：原生 "
            "UI 面不前造（公开面回读）；报告链 F121+ 不前移；E17/E15 账零"
            "写交叉。全程合成材料；%APPDATA% 零触碰；不 push。"),
    }
    payload = json.dumps(summary, ensure_ascii=False, indent=1)
    out = evidence_dir / "f119-f120-evidence-chain-recon.json"
    out.write_text(payload + "\n", encoding="utf-8")
    md = [f"# F119/F120 证据→质证链 recon（{profile}，W4-U51）",
          f"- verdict: **{summary['verdict']}**  profile={profile}",
          f"- harness: {HARNESS_BRANCH}@{summary['harness_head'][:12]}", ""]
    for c in recon.checks:
        md.append(f"- {'✅' if c['status'] == 'PASS' else '❌'} "
                  f"**{c['check']}**: {c['detail']}")
    (evidence_dir / "f119-f120-evidence-chain-recon.md").write_text(
        "\n".join(md) + "\n", encoding="utf-8")
    mirror = (REPO / "docs" / "construction" / "evidence" / "F120" / profile
              / "f119-f120-evidence-chain-recon.json")
    mirror.write_text(payload + "\n", encoding="utf-8")
    print(f"[{profile}] evidence: {out}", flush=True)
    return out


def main() -> int:
    global FORMAL_ROOT, CODES_REPO
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--profile", action="append",
                    choices=["desktop", "selfhost"], default=None)
    ap.add_argument("--corpus", type=Path,
                    default=TEMP / f"juscite-f119-corpus-{CORPUS_SEED}")
    ap.add_argument("--pg-dsn", default=DEFAULT_PG_DSN)
    ap.add_argument("--harness-root", default=None)
    ap.add_argument("--anonymizer-src", default=None)
    ap.add_argument("--formal-root", default=DEFAULT_FORMAL_ROOT)
    ap.add_argument("--codices-repo", default=DEFAULT_CODICES_REPO)
    args = ap.parse_args()
    profiles = args.profile or ["desktop", "selfhost"]
    FORMAL_ROOT = Path(args.formal_root)
    CODES_REPO = Path(args.codices_repo)
    if not FORMAL_ROOT.is_dir():
        eprint(f"[ENV-MISSING] codices 正式面不存在：{FORMAL_ROOT}")
        return 3
    lccc = CODES_REPO / "lccc_consumer.py"
    if not lccc.is_file() or sha256_bytes(lccc.read_bytes()) \
            != LCCC_V11_SHA256:
        eprint("[ENV-MISSING] E22 冻结面 v1.1 不可得或漂移：", lccc)
        return 3
    corpus = args.corpus.resolve()
    if not ensure_corpus(corpus):
        eprint(f"[ENV-MISSING] 语料不可得：{corpus}")
        return 3
    anonymizer_src = resolve_anonymizer_src(args.anonymizer_src)
    if anonymizer_src is None:
        eprint("[ENV-MISSING] anonymizer w2a-u18 源不可得")
        return 3
    harness_root = resolve_harness_root(args.harness_root)
    if harness_root is None:
        eprint(f"[ENV-MISSING] harness {HARNESS_BRANCH} worktree 不可得")
        return 3
    print(f"[ENV] corpus={corpus}")
    print(f"[ENV] harness={harness_root}")
    print(f"[ENV] anonymizer={anonymizer_src}")
    legal_entry = load_bridge(anonymizer_src)

    all_ok = True
    for profile in profiles:
        print(f"\n===== profile {profile} =====", flush=True)
        recon = Recon()
        started = now_iso()
        try:
            ok = run_profile(profile, legal_entry, harness_root, corpus,
                             args.pg_dsn, recon)
        except Exception as exc:  # noqa: BLE001 - recon 必须报告不崩
            recon.add("FATAL_unhandled", False,
                      type(exc).__name__ + ":" + str(exc)[:300])
            ok = False
        code = 0 if (ok and recon.all_ok) else 2
        write_evidence(profile, recon, started, harness_root, code)
        all_ok = all_ok and code == 0
        print(f"[{profile}] "
              + ("RECON_OK" if code == 0 else "RECON_FAIL")
              + f" checks={len(recon.checks)}", flush=True)
    print(f"\n{'RECON_OK' if all_ok else 'RECON_FAIL'}"
          f"（profiles={profiles}）")
    return 0 if all_ok else 2


if __name__ == "__main__":
    raise SystemExit(main())

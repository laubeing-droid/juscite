"""F45 通道① agent CLI 直改文档（清洁版＋批注修订版 DOCX）对账（W2b-U15）
——双 profile（desktop/selfhost）。

对账对象：产品侧 docx_edit 公开面（legal_entry docxedit.* 冻结方法组）×
harness 链头（w2b-u23@08c58853＝w2a-u05→w2a-u06/F114→w2b-u01/F25→
w2b-u11/F47→w2b-u23/E15；本单零 harness 改动，检出只读消费，故不跑
verify.ps1——其触发条件"动 harness 公开面"不成立）。

- desktop profile＝产品桥全链（legal_entry.call → 子进程 public_entry →
  SQLite 状态根）：register_material（rev1 upload）→ docxedit.apply（真
  read_material 回读原稿 → 纯 Python 生成清洁版＋批注修订版 → 独立 lxml
  检查器八维硬门 → add_material_revision source=assistant_edit（F114 闭集）
  → formal_propose channel=machine（U11 合同））。
- selfhost profile＝PgMatterStore 直连 lh-pg-e08（resolve_provider_method
  同一封闭注册；docx_edit.apply_edit harness_call seam 注入，同 W2b-U11
  recon 直连先例）。

全部合成材料：f45_fixtures 纯 stdlib 合成起诉状 DOCX（正文/表格/编号
三要素齐备）＋合成编辑集；harness 检出零字节改动（git 只读命令核对）。

实跑覆盖（PENDING_OWNER_F45_clean_annotated_docx）：
  C01 harness 分支/基/master/工作树干净亲验（只读）；
  C02 双产物真实完整落盘（clean.docx＋annotated.docx，python-docx 独立
  重开）＋清洁版零修订标记/批注修订版标记对账（检查器八维全过）；
  C03 真宿主可开性：LibreOffice headless 双产物→PDF exit 0（26.8.1.1；
  UserInstallation 隔离于临时根，绝不写 %APPDATA%）；
  C04 编号/正文/表格渲染保真（PDF 文本抽取：编号 1-4 连续含插入项、
  替换文本在、表格改值在、删除段消失）；
  C05 旧稿不覆写：第二轮编辑（不同 request/proposal）outputs append-only
  （0001 字节不动）＋harness 版本链 rev1 原稿逐字节可回读；
  C06 U11 合同登记：版本链 [upload, assistant_edit, assistant_edit]、
  formal_proposal pending 锚定各自 assistant_edit 头行、提案字节==清洁版
  字节（formal_proposal_read 逐字节）、quotes==内容编辑定位集（4 条含
  text/reason/sourceRef）、channel=machine；
  C07 F114 负向不回退：add_material_revision 自封 user_accept 具名拒；
  C08 幂等重放：同 request id 重放返回原产物（outputs 不新增、提案账
  不双登）；
  C09 verify 复验面：整跑独立检查器 PASS＋产物篡改响亮拒（覆写被抓）；
  C10 桥负向：未配置 NOT_CONNECTED／未知方法 method_not_connected／
  方法组冻结四方法；
  C11 确定性：同输入两跑同字节＋跨 profile 同 sha256 同 content_digest
  （selfhost 与 desktop 产物逐字节相等——生成面与存储后端无关）。

用法：
  python -X utf8 tools/PENDING_OWNER_f45_clean_annotated_docx_recon.py \
      --profile desktop --profile selfhost

退出码：0 = 全部 profile RECON_OK；2 = RECON_FAIL；3 = 环境缺失。
证据：docs/construction/evidence/F45/<profile>/ JSON＋MD。
"""
from __future__ import annotations

import argparse
import base64
import contextlib
import hashlib
import json
import subprocess
import sys
import tempfile
import uuid as _uuid
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "implementation" / "python"))
sys.path.insert(0, str(REPO_ROOT / "implementation" / "tests"))

import f45_fixtures  # noqa: E402
import legal_entry  # noqa: E402
import docx_edit  # noqa: E402
from legal_entry import HarnessCommandError, NotConnected  # noqa: E402

DEFAULT_HARNESS_ROOT = Path(
    r"D:\Codex\1.法律工作区\legal-harness工作区\legal-harness-repo"
    r"\.local\worktrees\w2b-u15")
DEFAULT_SOFFICE = r"C:\Program Files\LibreOffice\program\soffice.exe"
DEFAULT_PG_DSN = "postgresql://lh_app:e08-synth-only@127.0.0.1:55432/legal_harness"

MATTER = "m-f45-recon"
SCOPE = {"kind": "matter", "matterId": MATTER}
MATERIAL = "mat-f45-docx"
AUTHOR = "lvyin-docxedit"  # F53 作者声明闭集（W2b-U49；docxedit 通道绑定）
EDITED_AT = "2026-10-16T00:00:00Z"

EDIT_ROUND_1 = [
    {"op": "replace_text", "paragraph": 4, "find": "85,000元",
     "replace": "85,000元及利息", "reason": "金额主张改为含利息（合成）"},
    {"op": "insert_paragraph", "after": 6, "text": "判令被告承担保全费用；",
     "reason": "新增保全请求（合成）",
     "numbering": {"numId": 1, "ilvl": 0}, "style": None},
    {"op": "delete_paragraph", "paragraph": 13, "reason": "删除副本附言（合成）"},
    {"op": "replace_cell", "table": 0, "row": 2, "col": 1, "text": "4,250",
     "reason": "违约金试算（合成）"},
    {"op": "comment", "paragraph": 8, "text": "交货证据链待补（合成批注）"},
]
EDIT_ROUND_2 = [
    {"op": "replace_text", "paragraph": 4, "find": "及利息",
     "replace": "及逾期利息（按LPR上浮40%）",
     "reason": "利息主张补计算基准（合成第二轮）"},
    {"op": "comment", "paragraph": 2, "text": "被告主体资格核验批注（合成）"},
]

F45_METHODS = frozenset({
    "docxedit.apply", "docxedit.outputs",
    "docxedit.output", "docxedit.verify",
})


def b64(content: bytes) -> str:
    return base64.b64encode(content).decode("ascii")


def sha(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def key(request_id: str) -> dict:
    return {"requestId": request_id, "targetId": None,
            "expectedRevision": None, "inputRefs": []}


class Recon:
    def __init__(self, harness_root: Path):
        self.harness_root = harness_root
        self.checks: list[dict] = []
        self.digests: dict[str, str] = {}   # 跨 profile 确定性对照

    def step(self, name, ok, **facts):
        entry = {"check": name, "status": "PASS" if ok else "FAIL", **facts}
        self.checks.append(entry)
        print(json.dumps(entry, ensure_ascii=False), flush=True)
        if not ok:
            raise AssertionError(name)

    def expect_error(self, name, call, code_part,
                     error=(HarnessCommandError, ValueError)):
        try:
            call()
        except error as exc:
            self.step(name, code_part in str(exc), code=str(exc))
            return str(exc)
        raise AssertionError(name + ": no typed error raised")

    def git(self, root: Path, *args: str) -> str:
        return subprocess.check_output(
            ["git", "-C", str(root), *args], text=True).strip()

    def branch_checks(self):
        branch = self.git(self.harness_root, "rev-parse", "--abbrev-ref", "HEAD")
        head = self.git(self.harness_root, "rev-parse", "HEAD")
        base = self.git(self.harness_root, "merge-base", "HEAD", "w2b-u11")
        master = self.git(self.harness_root, "rev-parse", "master")
        self.step("c01_harness_branch", branch == "w2b-u15", branch=branch)
        self.step("c01_harness_head_on_chain",
                  head.startswith("08c58853") and base.startswith("88bf1757"),
                  head=head[:12], base=base[:12])
        self.step("c01_harness_master_untouched", master.startswith("929d0802"),
                  master=master[:12])
        dirty = self.git(self.harness_root, "status", "--porcelain")
        self.step("c01_harness_worktree_clean", dirty == "", dirty=dirty[:200])

    # ------------------------------------------------------------------
    def register_source(self, call, source: bytes) -> None:
        call("harness.register_material", {
            "actor_id": "recon-lawyer", "scope": SCOPE, "key": key("reg-1"),
            "material": {"id": MATERIAL, "kind": "office",
                         "title": "民事起诉状（F45 对账合成）",
                         "bytesB64": b64(source)}})

    def apply_round(self, apply_fn, request_id: str, proposal_id: str,
                    edits: list, base_revision: int) -> dict:
        return apply_fn({
            "matter_id": MATTER, "material_id": MATERIAL,
            "base_revision": base_revision, "request_id": request_id,
            "proposal_id": proposal_id, "actor_id": "recon-assistant",
            "author": AUTHOR, "edited_at": EDITED_AT, "edits": edits,
            "note": "F45 通道①对账合成编辑提案"})

    def common_flow(self, profile: str, call, apply_fn, outputs_fn,
                    verify_fn, output_fn, state_root: Path,
                    run_libreoffice: bool):
        source = f45_fixtures.build_source_docx()
        self.register_source(call, source)

        # ---- C02 双产物真实完整＋检查器八维硬门（apply 内部已跑；此处
        #      独立重开产物复核）。
        first = self.apply_round(apply_fn, "f45-req-1", "f45-fp-1",
                                 EDIT_ROUND_1, 1)
        out_dir = state_root / "docx-edit" / MATTER / MATERIAL / "outputs" \
            / "0001"
        clean_bytes = (out_dir / "clean.docx").read_bytes()
        annotated_bytes = (out_dir / "annotated.docx").read_bytes()
        self.step("c02_real_docx_pair_on_disk",
                  first["clean"]["sha256"] == sha(clean_bytes)
                  and first["annotated"]["sha256"] == sha(annotated_bytes)
                  and first["fidelity"]["all_passed"]
                  and first["fidelity"]["checker"] == "python-docx/lxml",
                  clean_sha=first["clean"]["sha256"][:16],
                  annotated_sha=first["annotated"]["sha256"][:16])
        import io
        from docx import Document as Docx
        clean_doc = Docx(io.BytesIO(clean_bytes))
        annotated_doc = Docx(io.BytesIO(annotated_bytes))
        w = docx_edit._q
        marks = [n for n in annotated_doc.element.body.iter()
                 if n.tag in (w("ins"), w("del"), w("delText"),
                              w("commentReference"))]
        self.step("c02_clean_zero_marks_annotated_marked",
                  not [n for n in clean_doc.element.body.iter()
                       if n.tag in (w("ins"), w("del"), w("delText"),
                                    w("commentReference"))]
                  and len(marks) == 16,
                  annotated_marks=len(marks))

        # ---- C03 真宿主可开性（LibreOffice headless 双产物→PDF）。
        if run_libreoffice:
            soffice = _resolve_soffice()
            if soffice is None:
                self.step("c03_libreoffice_opens_both", False,
                          note="soffice_missing")
            pdfs = _soffice_convert(soffice, [
                ("clean.docx", clean_bytes),
                ("annotated.docx", annotated_bytes)])
            ok = all(exit_code == 0 and pdf is not None
                     for _, exit_code, pdf in pdfs)
            self.step("c03_libreoffice_opens_both", ok,
                      exits=[code for _, code, _ in pdfs],
                      bytes=[p.stat().st_size if p else 0
                             for _, _, p in pdfs])

            # ---- C04 编号/正文/表格渲染保真（PDF 文本抽取）。
            clean_pdf = pdfs[0][2]
            text = _pdf_text(clean_pdf).replace(" ", "")
            numbering_ok = all(marker in text for marker in (
                "1.判令被告支付货款85,000元及利息",
                "2.判令被告支付违约金，按日万分之五计算",
                "3.本案诉讼费用由被告承担",
                "4.判令被告承担保全费用"))
            self.step("c04_render_fidelity_numbering_body_table",
                      numbering_ok
                      and "4,250" in text
                      and "附：本起诉状副本一份" not in text,
                      numbering_ok=numbering_ok,
                      deleted_gone="附：本起诉状副本一份" not in text,
                      pdf_excerpt=text[:80])
        else:
            self.step("c03_libreoffice_skipped_selfhost",
                      True, note="desktop 已真跑；两 profile 产物逐字节相等"
                      "（C11），证据同源")

        # ---- C05 旧稿不覆写：第二轮 append-only＋rev1 原稿逐字节回读。
        listing_before = outputs_fn()["outputs"]
        round2 = self.apply_round(apply_fn, "f45-req-2", "f45-fp-2",
                                  EDIT_ROUND_2, 2)
        listing_after = outputs_fn()["outputs"]
        clean1_after = (out_dir / "clean.docx").read_bytes()
        original_readback = call("harness.read_material", {
            "scope": SCOPE, "material_id": MATERIAL, "revision": 1})
        self.step("c05_old_drafts_never_overwritten",
                  clean1_after == clean_bytes
                  and len(listing_after) == len(listing_before) + 1
                  and round2["output_id"] == f"{MATERIAL}:0002"
                  and original_readback["bytesB64"] == b64(source)
                  and original_readback["sha256"] == sha(source),
                  outputs=[item["output_id"]
                           for item in listing_after],
                  rev1_intact=original_readback["sha256"][:12])

        # ---- C06 U11 合同登记（版本链/提案账/quotes/字节相等）。F47 合同
        #      本义：同 material 新提案使旧 pending 转 superseded（分列：
        #      supersededBy 有值、无决定记录）——fp-1 被 fp-2 取代是正确
        #      行为，不是异常。
        chain = [row["source"] for row in call("harness.list_materials", {
            "scope": SCOPE})["materials"][0]["revisions"]]
        proposal1 = call("harness.formal_proposal_read",
                         {"scope": SCOPE, "proposal_id": "f45-fp-1"})
        proposal2 = call("harness.formal_proposal_read",
                         {"scope": SCOPE, "proposal_id": "f45-fp-2"})
        self.step("c06_u11_registration",
                  chain == ["upload", "assistant_edit", "assistant_edit"]
                  and first["harness"]["assistant_edit"]["revision"] == 2
                  and round2["harness"]["assistant_edit"]["revision"] == 3
                  and proposal2["state"] == "pending"
                  and proposal1["state"] == "superseded"
                  and proposal1["supersededBy"] == "f45-fp-2"
                  and proposal1["decisionRef"] is None
                  and proposal1["author"] == AUTHOR,
                  chain=chain, p1=proposal1["state"],
                  p2=proposal2["state"])
        self.step("c06_proposal_bytes_equal_clean",
                  proposal1["bytesB64"] == b64(clean_bytes)
                  and proposal1["proposalSha256"] == sha(clean_bytes)
                  and proposal1["channel"] == "machine"
                  and proposal1["baseRevision"] == 2
                  and proposal2["channel"] == "machine"
                  and proposal2["baseRevision"] == 3
                  and len(proposal1["quotes"]) == 4
                  and proposal1["quotes"][0]["text"] == "85,000元"
                  and proposal1["quotes"][0]["sourceRef"]["id"] == MATERIAL,
                  quotes=len(proposal1["quotes"]),
                  p1_base=proposal1["baseRevision"],
                  p2_base=proposal2["baseRevision"])

        # ---- C07 F114 负向不回退：user_accept 不可自封。
        self.expect_error("c07_user_accept_not_self_declared", lambda: call(
            "harness.add_material_revision", {
                "actor_id": "recon-assistant", "scope": SCOPE,
                "key": key("f45-fake"),
                "revision": {"materialId": MATERIAL,
                             "bytesB64": b64(b"tamper"),
                             "baseRevision": 3,
                             "source": "user_accept"}}),
            "material_source_not_writable")

        # ---- C08 幂等重放：同 request id 返回原产物，不新增不双登。
        outputs_before = len(outputs_fn()["outputs"])
        replay = self.apply_round(apply_fn, "f45-req-1", "f45-fp-1",
                                  EDIT_ROUND_1, 1)
        proposals = call("harness.formal_proposal_list",
                         {"scope": SCOPE, "material_id": MATERIAL})
        self.step("c08_replay_idempotent",
                  replay["replayed"] is True
                  and replay["output_id"] == first["output_id"]
                  and len(outputs_fn()["outputs"]) == outputs_before
                  and proposals["stateCounts"]["pending"] == 1
                  and proposals["stateCounts"]["superseded"] == 1,
                  state_counts=proposals["stateCounts"])

        # ---- C09 verify 复验面：整跑检查器 PASS＋篡改响亮拒（复原）。
        verified = verify_fn({"matter_id": MATTER, "material_id": MATERIAL,
                              "seq": "0001"})
        clean_path = out_dir / "clean.docx"
        pristine = clean_path.read_bytes()
        clean_path.write_bytes(pristine + b"\x00")
        try:
            verify_fn({"matter_id": MATTER, "material_id": MATERIAL,
                       "seq": "0001"})
            tamper_refused = False
        except docx_edit.DocxEditError as exc:
            tamper_refused = "f45_output_bytes_mismatch" in str(exc)
        finally:
            clean_path.write_bytes(pristine)
        readback = output_fn({"matter_id": MATTER, "material_id": MATERIAL,
                              "seq": "0001", "file": "annotated"})
        self.step("c09_verify_face_and_tamper_refused",
                  verified["verified"] is True
                  and verified["fidelity"]["all_passed"] is True
                  and tamper_refused
                  and b64decode_ok(readback["docx_b64"])
                  == annotated_bytes,
                  tamper_refused=tamper_refused)

        # ---- C11 确定性：同输入两跑同字节＋跨 profile 逐字节相等。
        model = docx_edit.parse_source(source)
        plan = docx_edit.plan_edits(model, [dict(e) for e in EDIT_ROUND_1])
        rerun = docx_edit.build_versions(source, model, plan, AUTHOR,
                                         EDITED_AT)
        self.step("c11_deterministic_same_input_same_bytes",
                  rerun["clean"] == clean_bytes
                  and rerun["annotated"] == annotated_bytes,
                  clean_sha=sha(clean_bytes)[:16])
        self.digests[profile] = {
            "clean_sha256": sha(clean_bytes),
            "annotated_sha256": sha(annotated_bytes),
            "clean_digest": first["clean"]["content_digest"],
            "annotated_digest": first["annotated"]["content_digest"],
        }

    def bridge_negatives(self, config):
        source = f45_fixtures.build_source_docx()
        try:
            legal_entry.call("docxedit.apply", {
                "matter_id": MATTER, "material_id": MATERIAL,
                "base_revision": 1, "request_id": "f45-x",
                "proposal_id": "f45-x", "actor_id": "a", "author": AUTHOR,
                "edited_at": EDITED_AT, "edits": EDIT_ROUND_1}, {})
            raise AssertionError("bridge_not_configured_expected")
        except NotConnected as exc:
            self.step("c10_bridge_not_configured",
                      "f45_state_root_not_configured" in str(exc))
        try:
            legal_entry.call("docxedit.host_edit", {}, config)
            raise AssertionError("bridge_unknown_method_expected")
        except NotConnected as exc:
            self.step("c10_bridge_unknown_method_refused",
                      "method_not_connected" in str(exc))
        self.step("c10_method_group_frozen",
                  legal_entry.DOCX_EDIT_METHODS == F45_METHODS)

    # -- profile drivers ---------------------------------------------------
    def run_desktop(self) -> int:
        temporary = tempfile.TemporaryDirectory(prefix="juscite-f45-desktop-")
        state_root = Path(temporary.name) / "state"
        local_root = Path(temporary.name) / "docx-edit-state"
        state_root.mkdir(parents=True)
        registration = Path(temporary.name) / "service-local.json"
        registration.write_text(json.dumps(
            {"url": "http://127.0.0.1:1", "password": "synthetic-recon"}),
            encoding="utf-8")
        config = {
            "harness_public_entry": str(
                self.harness_root / "tools/workflow-tools/harness/public_entry.py"),
            "harness_target": "opencode",
            "harness_state_root": str(state_root),
            "harness_service_registration": str(registration),
            "harness_timeout": 120,
            "docx_edit_state_root": str(local_root),
        }
        for path in (str(self.harness_root / "src"),
                     str(self.harness_root / "tools/workflow-tools")):
            if path not in sys.path:
                sys.path.insert(0, path)
        from legal_harness.state.matter_store import MatterStore
        store = MatterStore(state_root)
        store.create_matter(MATTER, "cas://profile-f45-recon")

        def call(method, args):
            return legal_entry.call(method, args, config)

        def apply_fn(args):
            return legal_entry.call("docxedit.apply", args, config)

        def outputs_fn():
            return legal_entry.call(
                "docxedit.outputs",
                {"matter_id": MATTER, "material_id": MATERIAL}, config)

        def verify_fn(args):
            return legal_entry.call("docxedit.verify", args, config)

        def output_fn(args):
            return legal_entry.call("docxedit.output", args, config)

        print("[profile desktop] SQLite via product bridge subprocess",
              flush=True)
        self.common_flow("desktop", call, apply_fn, outputs_fn, verify_fn,
                         output_fn, local_root, run_libreoffice=True)
        self.bridge_negatives(config)
        return 0

    def run_selfhost(self, dsn: str, desktop_digests: dict) -> int:
        for path in (str(self.harness_root / "src"),
                     str(self.harness_root / "tools/workflow-tools"),
                     str(self.harness_root),
                     str(self.harness_root / "tests")):
            if path not in sys.path:
                sys.path.insert(0, path)
        import contextlib

        from legal_harness.business.provider_registry import (
            resolve_provider_method,
        )
        from legal_harness.business.units import HarnessUnits
        from legal_harness.state.pg_store import PgMatterStore

        temporary = tempfile.TemporaryDirectory(prefix="juscite-f45-selfhost-")
        local_root = Path(temporary.name) / "docx-edit-state"
        store = PgMatterStore(
            Path(temporary.name) / "state", dsn=dsn,
            schema="f45_" + _uuid.uuid4().hex[:12])
        units = HarnessUnits(store)
        methods = ("harness.register_material", "harness.read_material",
                   "harness.list_materials", "harness.add_material_revision",
                   "harness.formal_propose", "harness.formal_proposal_read",
                   "harness.formal_proposal_list")
        bound = {name: resolve_provider_method(name, units)
                 for name in methods}
        store.create_matter(MATTER, "cas://profile-f45-recon")

        def call(method, args):
            return bound[method](**args)

        def apply_fn(args):
            return docx_edit.apply_edit(local_root, {}, args,
                                        harness_call=call)

        def outputs_fn():
            return docx_edit.list_outputs(
                local_root, {"matter_id": MATTER, "material_id": MATERIAL})

        def verify_fn(args):
            return docx_edit.verify_output(local_root, args, {},
                                           harness_call=call)

        def output_fn(args):
            return docx_edit.read_output(local_root, args)

        print("[profile selfhost] PgMatterStore direct (lh-pg-e08)",
              flush=True)
        self.common_flow("selfhost", call, apply_fn, outputs_fn, verify_fn,
                         output_fn, local_root, run_libreoffice=False)
        # C11 跨 profile：产物逐字节相等（生成面与存储后端无关；desktop
        # 摘要自上一 Recon 实例显式传入——两 profile 各自独立实例）。
        selfhost_digests = self.digests.get("selfhost")
        self.step("c11_cross_profile_byte_identical",
                  bool(desktop_digests) and desktop_digests == selfhost_digests,
                  desktop=desktop_digests,
                  selfhost=selfhost_digests)
        store.destroy()
        return 0


def b64decode_ok(payload: str) -> bytes:
    return base64.b64decode(payload)


def _resolve_soffice() -> Path | None:
    raw = Path(DEFAULT_SOFFICE)
    if not raw.is_file():
        return None
    if raw.name.lower() == "soffice.exe":
        com = raw.with_name("soffice.com")
        if com.is_file():
            return com
    return raw


def _soffice_convert(soffice: Path, files: list[tuple[str, bytes]]):
    out_dir = Path(tempfile.mkdtemp(prefix="f45-lo-"))
    profile = (out_dir / "lo-profile").resolve()
    profile.mkdir(parents=True)
    results = []
    for name, payload in files:
        target = out_dir / name
        target.write_bytes(payload)
        proc = subprocess.run(
            [str(soffice), "--headless", "--norestore", "--nolockcheck",
             "-env:UserInstallation=" + profile.as_uri(),
             "--convert-to", "pdf", "--outdir", str(out_dir), str(target)],
            capture_output=True, text=True, encoding="utf-8",
            errors="replace", timeout=300)
        pdf = out_dir / (name[:-5] + ".pdf")
        results.append((name, proc.returncode,
                        pdf if pdf.is_file() else None))
    return results


def _pdf_text(pdf_path: Path) -> str:
    import pypdfium2 as pdfium
    doc = pdfium.PdfDocument(str(pdf_path))
    try:
        return "\n".join(page.get_textpage().get_text_range()
                         for page in doc)
    finally:
        doc.close()


def write_evidence(profile: str, recon: Recon, harness_root: Path,
                   started: str, code: int) -> Path:
    evidence_dir = REPO_ROOT / "docs" / "construction" / "evidence" / "F45" \
        / profile
    evidence_dir.mkdir(parents=True, exist_ok=True)
    finished = datetime.now(timezone.utc).isoformat()
    summary = {
        "schema": "juscite-f45-clean-annotated-docx-recon/1",
        "unit": "W2b-U15",
        "feature": "F45",
        "profile": profile,
        "verdict": "RECON_OK" if code == 0 else "RECON_FAIL",
        "started_at": started,
        "finished_at": finished,
        "harness_worktree": str(harness_root),
        "harness_branch": "w2b-u15 (read-only; 链头 08c58853=w2b-u11@88bf"
                          "1757 同链 E15；本单零 harness 改动)",
        "checks": recon.checks,
        "check_count": len(recon.checks),
        "digests": recon.digests.get(profile),
        "failed": [c["check"] for c in recon.checks
                   if c["status"] != "PASS"],
    }
    payload = json.dumps(summary, ensure_ascii=False, indent=1)
    (evidence_dir / "f45_clean_annotated_docx_recon.json").write_text(
        payload + "\n", encoding="utf-8")
    lines = [f"# F45 通道① 清洁版＋批注修订版 DOCX recon（{profile}）",
             "",
             f"- unit: W2b-U15 · profile: {profile}",
             f"- verdict: **{summary['verdict']}**"
             f" ({len(recon.checks)} checks, exit {code})",
             f"- harness: `{harness_root}` @ w2b-u15（链头 08c58853 只读"
             "消费；master 929d0802 零动；本单零 harness 改动）",
             f"- started: {started} · finished: {finished}",
             "",
             "| # | check | status |",
             "|---|---|---|"]
    for index, check in enumerate(recon.checks, 1):
        lines.append(f"| {index} | {check['check']}"
                     f" | {check['status']} |")
    lines += ["", "全部合成材料（f45_fixtures 纯 stdlib 合成起诉状）；"
              "desktop＝产品桥子进程全链（SQLite 状态根）＋LibreOffice "
              "26.8.1.1 真开性/编号渲染；selfhost＝PgMatterStore 直连 "
              "lh-pg-e08（同封闭注册；产物与 desktop 逐字节相等）。"]
    (evidence_dir / "f45_clean_annotated_docx_recon.md").write_text(
        "\n".join(lines) + "\n", encoding="utf-8")
    return evidence_dir


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--profile", action="append",
                        choices=["desktop", "selfhost"])
    parser.add_argument("--harness-root", type=Path,
                        default=DEFAULT_HARNESS_ROOT)
    parser.add_argument("--pg-dsn", default=DEFAULT_PG_DSN)
    args = parser.parse_args()
    profiles = args.profile or ["desktop"]
    if not (args.harness_root / "tools/workflow-tools/harness/public_entry.py"
            ).exists():
        print("RECON_BLOCKED: harness root missing public_entry:",
              args.harness_root)
        return 3
    failures = 0
    first = True
    desktop_digests: dict = {}
    for profile in profiles:
        started = datetime.now(timezone.utc).isoformat()
        recon = Recon(args.harness_root)
        try:
            if first:
                recon.branch_checks()
            if profile == "desktop":
                code = recon.run_desktop()
                desktop_digests = dict(recon.digests.get("desktop") or {})
            else:
                code = recon.run_selfhost(args.pg_dsn, desktop_digests)
        except Exception as error:  # noqa: BLE001 - reported per profile
            print(f"RECON_FAIL[{profile}]: {error}", flush=True)
            recon.checks.append({"check": "recon_driver", "status": "FAIL",
                                 "error": str(error)[:400]})
            code = 2
        evidence_dir = write_evidence(profile, recon, args.harness_root,
                                       started, code)
        verdict = "RECON_OK" if code == 0 else "RECON_FAIL"
        print(f"[{profile}] {verdict} ({len(recon.checks)} checks,"
              f" exit {code}) evidence={evidence_dir}", flush=True)
        if code != 0:
            failures += 1
        first = False
    return 0 if failures == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())

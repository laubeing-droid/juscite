# -*- coding: utf-8 -*-
"""F56 文书模板起草（模板库＋变量填充＋访谈式三段）对账（W4-U38）
——双 profile（desktop/selfhost）。

对账对象：产品侧 template_drafting 公开面（legal_entry TEMPLATES_METHODS
八方法，06:F56 P04 binding=templates.register/render/save_answers）×
harness 战役分支链头（w4-u31@8f65dc6f＝W4-U31 F05 协作面，基
w4-u01@23f56d70；本单零 harness 改动，检出只读消费，故不跑
verify.ps1——其触发条件"动 harness 公开面"不成立；A2 裁决：分支链常
驻，产品桥消费分支能力，master 929d0802 持续零动）。

- desktop profile＝产品桥全链（legal_entry.call → 子进程 public_entry →
  SQLite 状态根）：templates.register（v1=harness.register_material
  upload＋产品版本/授权账 append-only）→ templates.interview（段①问询）
  → templates.save_answers（段②填充）→ templates.render（段③装配：
  结构/视觉具名硬门→add_material_revision source=assistant_edit∈F114
  闭集→formal_propose channel=machine author=lvyin-templates）。
- selfhost profile＝PgMatterStore 直连 lh-pg-e08（resolve_provider_method
  同一封闭注册；template_drafting harness_call seam 注入，同 W2b-U11/
  U15 recon 直连先例）。

E13 模板结构视觉段承接（A1 落账 00-总协调.md:251「模板结构视觉段归
F56/B4→W4 规划员」）：C07 结构段（05§8「content control外结构、style/
numbering/section/外链/隐私/占位/视觉检查具名」——recon 第二实现独立
复算逐维对照 manifest 具名报告）＋C08 视觉段（desktop 真渲染：装配
DOCX 经 LibreOffice headless→PDF exit 0，答案值在、占位符不在）。

全部合成材料：f56_fixtures 纯 stdlib 合成模板语料（内容控件×7＋无 tag
控件×1＋外链×1＋core.xml 元数据）；harness 检出零字节改动（git 只读
命令核对）。

实跑覆盖（PENDING_OWNER_F56_template_drafting）：
  C01 harness 分支/链头基点/master/工作树干净亲验（只读）；
  C02 模板库登记：版本＋授权元数据 append-only（register→rev1 upload
      ＋versions/0001 可回读；同 id 同 sha 幂等重放；缺授权具名拒）；
  C03 访谈段①：问题集确定性提取（八变量 kind 闭集）＋两跑同形＋
      harness CAS 随读必验（字节回读==登记 sha）；
  C04 缺模板不发明：interview/save_answers/render 对未知模板与未知答
      案表一律 f56_* 具名拒（零发明零静默）；
  C05 段②答案账：合法表 append＋回读相等；缺变量具名清单（不发明值）/
      多变量/浮点金额/坏金额形/坏日历（02-30）全部具名拒；同 id 同内
      容幂等、异内容冲突；
  C06 段③装配：产物真实完整落盘＋harness rev2 assistant_edit＋提案
      pending（channel=machine·author=lvyin-templates·quotes==占位定
      位集 8 条）＋manifest 结构/检查器双 all_passed＋recon lxml 独立
      重开逐控件对账答案；
  C07 E13 结构段（具名八硬维＋外链/隐私信息维，recon 第二实现独立复
      算与 manifest 逐维对照）；
  C08 E13 视觉段（desktop）：LibreOffice 26.x headless→PDF exit 0＋
      答案值在 PDF 文本层＋占位符不在（视觉残留为零）；
  C09 旧稿不覆写＋版本/授权保留：第二轮 outputs append-only（0001 字
      节不动）＋模板版本链 [v1] 不动＋rev1 模板字节逐字节可回读＋授权
      元数据逐字不变；
  C10 U11 合同：版本链 [upload, assistant_edit, assistant_edit]＋fp-1
      superseded/fp-2 pending＋提案字节==装配字节＋F53 author.projection
      可读（boundChannel=templates——W4-U38 闭集扩展使模板装配提案在
      F53 投影面可用，非闭集外作者）；
  C11 F114 负向不回退：user_accept 不可自封；
  C12 幂等重放：同 request id 返回原产物（outputs 不新增、提案账不双
      登）；
  C13 确定性：同输入两跑同字节（纯函数复填）＋跨 profile 装配字节
      sha256/content_digest 逐字相等（生成面与存储后端无关）；
  C14 桥负向：未配置 NOT_CONNECTED／组外伪方法 method_not_connected／
      方法组冻结八方法／author 冒充律师名 f53_author_impersonation／
      通道错绑 f53_author_channel_mismatch（真实代码路径，拒后零半成
      品）。

用法：
  python -X utf8 tools/PENDING_OWNER_f56_template_drafting_recon.py \
      --profile desktop --profile selfhost

退出码：0 = 全部 profile RECON_OK；2 = RECON_FAIL；3 = 环境缺失。
证据：docs/construction/evidence/F56/<profile>/ JSON＋MD。
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import subprocess
import sys
import tempfile
import uuid as _uuid
import zipfile
import io
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "implementation" / "python"))
sys.path.insert(0, str(REPO_ROOT / "implementation" / "tests"))

import f56_fixtures  # noqa: E402
import legal_entry  # noqa: E402
import template_drafting as td  # noqa: E402
from legal_entry import HarnessCommandError, NotConnected  # noqa: E402

DEFAULT_HARNESS_ROOT = Path(
    r"D:\Codex\1.法律工作区\legal-harness工作区\legal-harness-repo"
    r"\.local\worktrees\w4-u31")
DEFAULT_SOFFICE = r"C:\Program Files\LibreOffice\program\soffice.exe"
DEFAULT_PG_DSN = ("postgresql://lh_app:e08-synth-only"
                  "@127.0.0.1:55432/legal_harness")

MATTER = "m-f56-recon"
SCOPE = {"kind": "matter", "matterId": MATTER}
MATERIAL = "mat-f56-tpl"
TEMPLATE_ID = "t-f56-recon"
AUTHOR = "lvyin-templates"  # F53 作者声明闭集（W4-U38 templates 通道）
LICENSE = {"license": "所内受控（合成对账）", "source": "合成模板组",
           "notice": "W4-U38 合成语料·非真实模板"}

W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"

TEMPLATES_METHODS = frozenset({
    "templates.register", "templates.list", "templates.template",
    "templates.interview", "templates.save_answers", "templates.answers",
    "templates.render", "templates.renderings",
})
# 第二轮答案（court 变更→装配字节必变）。
ANSWERS_2 = dict(f56_fixtures.ANSWERS,
                 court="合成市第二中级人民法院（合成）")


def b64(content: bytes) -> str:
    return base64.b64encode(content).decode("ascii")


def sha(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def key(request_id: str) -> dict:
    return {"requestId": request_id, "targetId": None,
            "expectedRevision": None, "inputRefs": []}


def _q(tag: str) -> str:
    return f"{{{W_NS}}}{tag}"


class Recon:
    def __init__(self, harness_root: Path):
        self.harness_root = harness_root
        self.checks: list[dict] = []
        self.digests: dict[str, dict] = {}   # 跨 profile 确定性对照

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
            self.step(name, code_part in str(exc), code=str(exc)[:200])
            return str(exc)
        raise AssertionError(name + ": no typed error raised")

    def git(self, root: Path, *args: str) -> str:
        return subprocess.check_output(
            ["git", "-C", str(root), *args], text=True).strip()

    def branch_checks(self):
        branch = self.git(self.harness_root, "rev-parse",
                          "--abbrev-ref", "HEAD")
        head = self.git(self.harness_root, "rev-parse", "HEAD")
        base = self.git(self.harness_root, "merge-base", "HEAD", "w4-u01")
        master = self.git(self.harness_root, "rev-parse", "master")
        self.step("c01_harness_branch", branch == "w4-u31", branch=branch)
        self.step("c01_harness_head_on_chain",
                  head.startswith("8f65dc6f") and base.startswith("23f56d70"),
                  head=head[:12], base=base[:12],
                  note="A2 战役分支链头（W4-U31 F05 协作面）只读消费")
        self.step("c01_harness_master_untouched",
                  master.startswith("929d0802"), master=master[:12])
        dirty = self.git(self.harness_root, "status", "--porcelain")
        self.step("c01_harness_worktree_clean", dirty == "",
                  dirty=dirty[:200])

    # ------------------------------------------------------------------
    def common_flow(self, profile: str, call, call_face, register_fn,
                    interview_fn, save_fn, render_fn, renderings_fn,
                    answers_fn, register_v2_fn, state_root: Path,
                    run_libreoffice: bool):
        template = f56_fixtures.build_template_docx()
        template_sha = sha(template)

        # ---- C02 模板库登记：版本＋授权 append-only。
        reg = register_fn()
        version_path = (state_root / "templates" / "registry"
                        / TEMPLATE_ID / "versions" / "0001.json")
        manifest = json.loads(version_path.read_text(encoding="utf-8"))
        self.step("c02_register_version_license",
                  reg["replayed"] is False and reg["version"] == 1
                  and reg["sha256"] == template_sha
                  and reg["license"] == LICENSE
                  and manifest["license"] == LICENSE
                  and manifest["material_revision"] == 1
                  and len(reg["variables"]) == 8
                  and reg["controls_total"] == 8,
                  version=reg["version"], sha256=template_sha[:16],
                  license=reg["license"]["license"])
        replay = register_fn()
        self.step("c02_register_idempotent_replay",
                  replay["replayed"] is True and replay["version"] == 1)
        # 缺授权＝具名拒（保留授权不是事后补写；拒在 harness 调用之前
        # ——零半成品）。
        self.expect_error(
            "c02_license_required",
            lambda: call_face("templates.register", {
                "template_id": "t-f56-nolic", "matter_id": MATTER,
                "material_id": "mat-f56-nolic", "title": "无授权模板",
                "actor_id": "recon-lawyer", "license": {"license": ""},
                "bytes_b64": b64(template)}),
            "f56_license_required")

        # ---- C03 访谈段①：问题集确定性提取＋CAS 随读必验。
        face1 = interview_fn({"template_id": TEMPLATE_ID})
        face2 = interview_fn({"template_id": TEMPLATE_ID})
        raw = call("harness.read_material", {
            "scope": SCOPE, "material_id": MATERIAL, "revision": 1})
        cas_bytes = base64.b64decode(raw["bytesB64"])
        questions = [(q["name"], q["kind"], q["required"])
                     for q in face1["questions"]]
        self.step("c03_interview_questions_deterministic",
                  face1["questions"] == face2["questions"]
                  and questions == [
                      ("plaintiff", "text", True),
                      ("plaintiff_address", "text", True),
                      ("defendant", "text", True),
                      ("claim_total", "amount", True),
                      ("interest_total", "amount", True),
                      ("contract_date", "date", True),
                      ("court", "text", True),
                      ("copies", "number", True)]
                  and face1["template"]["sha256"] == template_sha
                  and sha(cas_bytes) == template_sha
                  and raw["sha256"] == template_sha,
                  variables=len(questions),
                  cas_sha=raw["sha256"][:16])

        # ---- C04 缺模板不发明（三段全拒）。
        self.expect_error("c04_missing_template_interview",
                          lambda: interview_fn({"template_id": "nope-tpl"}),
                          "f56_template_not_found")
        self.expect_error("c04_missing_template_answers",
                          lambda: save_fn({"template_id": "nope-tpl",
                                           "matter_id": MATTER,
                                           "answers_id": "ans-x",
                                           "answers": {}}),
                          "f56_template_not_found")
        self.expect_error("c04_missing_template_render",
                          lambda: render_fn({"template_id": "nope-tpl",
                                             "matter_id": MATTER,
                                             "answers_id": "ans-x",
                                             "request_id": "req-x",
                                             "proposal_id": "fp-x",
                                             "actor_id": "recon-assistant",
                                             "author": AUTHOR}),
                          "f56_template_not_found")
        self.expect_error("c04_missing_answers_refused",
                          lambda: render_fn({"template_id": TEMPLATE_ID,
                                             "matter_id": MATTER,
                                             "answers_id": "nope-sheet",
                                             "request_id": "req-x",
                                             "proposal_id": "fp-x",
                                             "actor_id": "recon-assistant",
                                             "author": AUTHOR}),
                          "f56_answers_not_found")

        # ---- C05 段②答案账：append＋校验＋幂等。
        sheet = save_fn({"template_id": TEMPLATE_ID, "matter_id": MATTER,
                         "answers_id": "ans-f56-1",
                         "answers": dict(f56_fixtures.ANSWERS)})
        readback = answers_fn({"template_id": TEMPLATE_ID,
                               "matter_id": MATTER,
                               "answers_id": "ans-f56-1"})
        self.step("c05_answers_append_and_readback",
                  sheet["replayed"] is False
                  and sheet["template_sha256"] == template_sha
                  and sheet["template_version"] == 1
                  and readback["answers"] == f56_fixtures.ANSWERS,
                  answers_sha=sheet["answers_sha256"][:12])
        self.expect_error(
            "c05_missing_variables_named_refusal",
            lambda: save_fn({"template_id": TEMPLATE_ID,
                             "matter_id": MATTER,
                             "answers_id": "ans-f56-bad",
                             "answers": {k: v
                                         for k, v in
                                         f56_fixtures.ANSWERS.items()
                                         if k != "court"}}),
            "f56_answers_missing_variables:court")
        self.expect_error(
            "c05_unknown_variables_refused",
            lambda: save_fn({"template_id": TEMPLATE_ID,
                             "matter_id": MATTER,
                             "answers_id": "ans-f56-bad",
                             "answers": {**f56_fixtures.ANSWERS,
                                         "bogus": "x"}}),
            "f56_answers_unknown_variables")
        self.expect_error(
            "c05_float_amount_refused",
            lambda: save_fn({"template_id": TEMPLATE_ID,
                             "matter_id": MATTER,
                             "answers_id": "ans-f56-bad",
                             "answers": {**f56_fixtures.ANSWERS,
                                         "claim_total": 85000.5}}),
            "f56_answer_not_string")
        self.expect_error(
            "c05_bad_amount_form_refused",
            lambda: save_fn({"template_id": TEMPLATE_ID,
                             "matter_id": MATTER,
                             "answers_id": "ans-f56-bad",
                             "answers": {**f56_fixtures.ANSWERS,
                                         "claim_total": "12.3.4"}}),
            "f56_answer_value_invalid")
        self.expect_error(
            "c05_impossible_calendar_refused",
            lambda: save_fn({"template_id": TEMPLATE_ID,
                             "matter_id": MATTER,
                             "answers_id": "ans-f56-bad",
                             "answers": {**f56_fixtures.ANSWERS,
                                         "contract_date": "2026-02-30"}}),
            "f56_answer_value_invalid")
        replay_sheet = save_fn({"template_id": TEMPLATE_ID,
                                "matter_id": MATTER,
                                "answers_id": "ans-f56-1",
                                "answers": dict(f56_fixtures.ANSWERS)})
        self.step("c05_answers_replay_idempotent",
                  replay_sheet["replayed"] is True)
        self.expect_error(
            "c05_answers_conflict_refused",
            lambda: save_fn({"template_id": TEMPLATE_ID,
                             "matter_id": MATTER,
                             "answers_id": "ans-f56-1",
                             "answers": dict(ANSWERS_2)}),
            "f56_answers_id_conflict")

        # ---- C06 段③装配：真实产物＋harness 登记＋提案。
        first = render_fn({"template_id": TEMPLATE_ID, "matter_id": MATTER,
                           "answers_id": "ans-f56-1", "request_id":
                           "f56-req-1", "proposal_id": "f56-fp-1",
                           "actor_id": "recon-assistant", "author": AUTHOR,
                           "note": "F56 对账合成装配"})
        out_dir = (state_root / "templates" / "renderings" / MATTER
                   / TEMPLATE_ID / "outputs" / "0001")
        assembled_bytes = (out_dir / "assembled.docx").read_bytes()
        self.step("c06_render_assembles_and_registers",
                  first["replayed"] is False
                  and first["assembled"]["sha256"] == sha(assembled_bytes)
                  and first["structure_visual"]["all_passed"] is True
                  and first["independent_check"]["all_passed"] is True
                  and first["independent_check"]["checker"] == "lxml/etree"
                  and first["harness"]["assistant_edit"]["revision"] == 2
                  and first["harness"]["assistant_edit"]["source"]
                  == "assistant_edit"
                  and first["harness"]["proposal"]["state"] == "pending"
                  and first["harness"]["proposal"]["channel"] == "machine"
                  and first["harness"]["proposal"]["author"] == AUTHOR,
                  assembled_sha=first["assembled"]["sha256"][:16],
                  rev=first["harness"]["assistant_edit"]["revision"])
        # recon 独立重开（lxml）逐控件对账答案。
        controls = self._lxml_controls(assembled_bytes)
        expected_controls = {
            "text:plaintiff": ["合成贸易有限责任公司"],
            "text:plaintiff_address": ["合成市合成区合成路1号"],
            "text:defendant": ["合成实业有限公司"],
            "amount:claim_total": ["85,000.00"],
            "amount:interest_total": ["4,250.50"],
            "date:contract_date": ["2026-01-15"],
            "text:court": ["合成市合成区人民法院"],
            "number:copies": ["2"],
        }
        self.step("c06_lxml_independent_control_readback",
                  controls == expected_controls,
                  controls_checked=len(controls))
        listing = renderings_fn({"template_id": TEMPLATE_ID,
                                 "matter_id": MATTER})
        self.step("c06_renderings_append_only_view",
                  listing["count"] == 1
                  and listing["renderings"][0]["output_id"]
                  == f"{TEMPLATE_ID}:0001",
                  outputs=listing["count"])

        # ---- C07 E13 结构段：具名硬维 recon 第二实现独立复算。
        dims = first["structure_visual"]
        recomputed = self._recompute_structure(template, assembled_bytes,
                                               expected_controls)
        self.step("c07_e13_structure_named_dims",
                  all(dims[name] is True for name in (
                      "parts_identical_except_document",
                      "outside_controls_unchanged",
                      "controls_all_filled",
                      "placeholder_residue_zero",
                      "styles_part_identical",
                      "numbering_part_identical",
                      "sections_preserved",
                      "document_rels_identical"))
                  and recomputed["parts_identical"]
                  and recomputed["outside_unchanged"]
                  and recomputed["styles_equal"]
                  and recomputed["numbering_equal"]
                  and recomputed["sections_equal"]
                  and recomputed["external_count"] == 1
                  and dims["external_links"]["count"] == 1
                  and dims["privacy"]["creator"]
                  == "合成模板组（synthetic）",
                  named_dims=dims["named_dims"],
                  external=recomputed["external_count"])

        # ---- C08 E13 视觉段（desktop 真渲染）。
        if run_libreoffice:
            soffice = _resolve_soffice()
            if soffice is None:
                self.step("c08_e13_visual_render", False,
                          note="soffice_missing")
            exit_code, pdf = _soffice_convert(soffice, assembled_bytes)
            if pdf is None:
                self.step("c08_e13_visual_render", False,
                          exit_code=exit_code)
            text = _pdf_text(pdf).replace(" ", "").replace("\n", "")
            answers_present = all(
                marker.replace(" ", "") in text for marker in (
                    "合成贸易有限责任公司", "合成实业有限公司",
                    "85,000.00", "4,250.50", "2026-01-15",
                    "合成市合成区人民法院"))
            placeholders_gone = not any(
                ph.replace(" ", "") in text for ph in (
                    "【原告名称】", "【被告名称】", "【货款总额】",
                    "【受诉法院全称】", "【合同签订日】"))
            self.step("c08_e13_visual_render",
                      exit_code == 0 and answers_present
                      and placeholders_gone,
                      exit_code=exit_code,
                      answers_present=answers_present,
                      placeholders_gone=placeholders_gone,
                      pdf_bytes=pdf.stat().st_size)
        else:
            self.step("c08_visual_skipped_selfhost", True,
                      note="desktop 已真渲染；两 profile 装配字节逐字节"
                           "相等（C13），视觉证据同源")

        # ---- C09 旧稿不覆写＋版本/授权保留。
        _ = save_fn({"template_id": TEMPLATE_ID, "matter_id": MATTER,
                     "answers_id": "ans-f56-2", "answers": dict(ANSWERS_2)})
        second = render_fn({"template_id": TEMPLATE_ID,
                            "matter_id": MATTER,
                            "answers_id": "ans-f56-2",
                            "request_id": "f56-req-2",
                            "proposal_id": "f56-fp-2",
                            "actor_id": "recon-assistant",
                            "author": AUTHOR})
        first_manifest = json.loads((out_dir / "manifest.json")
                                    .read_text(encoding="utf-8"))
        original_readback = call("harness.read_material", {
            "scope": SCOPE, "material_id": MATERIAL, "revision": 1})
        versions = sorted(p.name for p in (state_root / "templates"
                           / "registry" / TEMPLATE_ID / "versions")
                          .glob("*.json"))
        self.step("c09_append_only_and_version_license_preserved",
                  second["output_id"] == f"{TEMPLATE_ID}:0002"
                  and first_manifest["assembled"]["sha256"]
                  == sha(assembled_bytes)
                  and (out_dir / "assembled.docx").read_bytes()
                  == assembled_bytes
                  and versions == ["0001.json"]
                  and base64.b64decode(original_readback["bytesB64"])
                  == template
                  and json.loads(version_path.read_text(
                      encoding="utf-8"))["license"] == LICENSE,
                  outputs=[row["output_id"] for row in renderings_fn(
                      {"template_id": TEMPLATE_ID,
                       "matter_id": MATTER})["renderings"]],
                  rev1_intact=original_readback["sha256"][:12])

        # ---- C09b 模板版本 v2 登记：版本链 append-only＋v1 逐字不动。
        v1_manifest_before = (state_root / "templates" / "registry"
                              / TEMPLATE_ID / "versions" / "0001.json"
                              ).read_bytes()
        reg2 = register_v2_fn()
        v1_manifest_after = (state_root / "templates" / "registry"
                             / TEMPLATE_ID / "versions" / "0001.json"
                             ).read_bytes()
        v2_manifest = json.loads(
            (state_root / "templates" / "registry" / TEMPLATE_ID
             / "versions" / "0002.json").read_text(encoding="utf-8"))
        chain_sources = [row["source"] for row in call(
            "harness.list_materials", {
                "scope": SCOPE})["materials"][0]["revisions"]]
        self.step("c09b_template_version2_append_only",
                  reg2["replayed"] is False and reg2["version"] == 2
                  and v1_manifest_before == v1_manifest_after
                  and v2_manifest["license"] == LICENSE
                  and v2_manifest["sha256"] != manifest["sha256"]
                  and chain_sources[:2] == ["upload", "assistant_edit"]
                  and chain_sources[-1] == "upload",
                  versions=sorted(p.name for p in (
                      state_root / "templates" / "registry" / TEMPLATE_ID
                      / "versions").glob("*.json")),
                  chain=chain_sources,
                  note="v2=别名变更字节→新版本行；v1 逐字节不动；授权逐"
                       "字保留；harness 侧 add_material_revision 缺省 "
                       "source=upload（F114 合同原文：用户侧字节语义）")

        # ---- C10 U11 合同＋F53 投影可用（闭集扩展验证）。
        chain = [row["source"] for row in call("harness.list_materials", {
            "scope": SCOPE})["materials"][0]["revisions"]]
        proposal1 = call("harness.formal_proposal_read",
                         {"scope": SCOPE, "proposal_id": "f56-fp-1"})
        proposal2 = call("harness.formal_proposal_read",
                         {"scope": SCOPE, "proposal_id": "f56-fp-2"})
        projection = self._author_projection(call, MATTER, MATERIAL)
        rows = projection.get("rows", [])
        self.step("c10_u11_chain_and_proposals",
                  chain == ["upload", "assistant_edit", "assistant_edit",
                            "upload"]
                  and proposal1["state"] == "superseded"
                  and proposal1["supersededBy"] == "f56-fp-2"
                  and proposal1["decisionRef"] is None
                  and proposal2["state"] == "pending"
                  and proposal2["channel"] == "machine"
                  and proposal2["author"] == AUTHOR
                  and proposal1["bytesB64"] == b64(assembled_bytes)
                  and proposal1["proposalSha256"] == sha(assembled_bytes)
                  and len(proposal1["quotes"]) == 8
                  and proposal1["quotes"][0]["text"] == "【原告名称】"
                  and proposal1["quotes"][0]["sourceRef"]["id"] == MATERIAL
                  and proposal1["baseRevision"] == 2,
                  chain=chain, p1=proposal1["state"],
                  p2=proposal2["state"])
        self.step("c10_f53_projection_readable_on_template_material",
                  len(rows) == 2
                  and all(row["authorPolicy"]["kind"] == "machine"
                          and row["authorPolicy"]["status"]
                          == "machine_author_ok"
                          and row["authorPolicy"]["boundChannel"]
                          == "templates" for row in rows)
                  and projection["visibility"]["authorVisible"] is True,
                  rows=len(rows),
                  note="W4-U38 闭集扩展：lvyin-templates∈F53 声明闭集，"
                       "模板装配提案在 author.projection 可读（非闭集外"
                       "作者——扩展前该材料会 f53_author_impersonation "
                       "整投影拒）")

        # ---- C11 F114 负向不回退：user_accept 不可自封。
        self.expect_error("c11_user_accept_not_self_declared", lambda: call(
            "harness.add_material_revision", {
                "actor_id": "recon-assistant", "scope": SCOPE,
                "key": key("f56-fake"),
                "revision": {"materialId": MATERIAL,
                             "bytesB64": b64(b"tamper"),
                             "baseRevision": 3,
                             "source": "user_accept"}}),
            "material_source_not_writable")

        # ---- C12 幂等重放。
        outputs_before = renderings_fn({"template_id": TEMPLATE_ID,
                                        "matter_id": MATTER})["count"]
        # 显式钉 v1：C09b 已登记 v2（latest 前移），重放必须钉回原装配
        # 版本——答案表钉 v1 sha，不钉版本＝f56_answers_template_mismatch。
        replay_render = render_fn({"template_id": TEMPLATE_ID,
                                   "matter_id": MATTER,
                                   "version": 1,
                                   "answers_id": "ans-f56-1",
                                   "request_id": "f56-req-1",
                                   "proposal_id": "f56-fp-1",
                                   "actor_id": "recon-assistant",
                                   "author": AUTHOR})
        proposals = call("harness.formal_proposal_list",
                         {"scope": SCOPE, "material_id": MATERIAL})
        self.step("c12_replay_idempotent",
                  replay_render["replayed"] is True
                  and replay_render["output_id"] == first["output_id"]
                  and renderings_fn({"template_id": TEMPLATE_ID,
                                     "matter_id": MATTER})["count"]
                  == outputs_before
                  and proposals["stateCounts"]["pending"] == 1
                  and proposals["stateCounts"]["superseded"] == 1,
                  state_counts=proposals["stateCounts"])

        # ---- C13 确定性：纯函数复填同字节＋跨 profile 摘要对照。
        manifest = json.loads(version_path.read_text(encoding="utf-8"))
        rerun = td.fill_template(template, manifest["variables"],
                                 f56_fixtures.ANSWERS)
        self.step("c13_deterministic_same_input_same_bytes",
                  rerun == assembled_bytes,
                  assembled_sha=sha(assembled_bytes)[:16])
        self.digests[profile] = {
            "assembled_sha256": sha(assembled_bytes),
            "assembled_digest": first["assembled"]["content_digest"],
        }

    def _author_projection(self, call, matter_id: str,
                           material_id: str) -> dict:
        """F53 author.projection（profile 各自的 harness 径）。"""
        raise NotImplementedError

    # ------------------------------------------------------------------
    @staticmethod
    def _lxml_controls(docx_bytes: bytes) -> dict:
        from lxml import etree as LET
        with zipfile.ZipFile(io.BytesIO(docx_bytes)) as zf:
            root = LET.fromstring(zf.read("word/document.xml"))
        w = "{%s}" % W_NS
        controls: dict[str, list[str]] = {}
        for sdt in root.iter(w + "sdt"):
            pr = sdt.find(w + "sdtPr")
            tag_node = pr.find(w + "tag") if pr is not None else None
            tag = tag_node.get(w + "val") if tag_node is not None else None
            if tag is None:
                continue
            text = "".join(t.text or "" for t in sdt.iter(w + "t"))
            controls.setdefault(tag, []).append(text)
        return controls

    @staticmethod
    def _recompute_structure(template: bytes, assembled: bytes,
                             expected_controls: dict) -> dict:
        """recon 第二实现（独立于模块 structure_report 的对照复算）。"""
        with zipfile.ZipFile(io.BytesIO(template)) as src, \
                zipfile.ZipFile(io.BytesIO(assembled)) as dst:
            names = src.namelist()
            parts_identical = (names == dst.namelist()
                               and all(src.read(n) == dst.read(n)
                                       for n in names
                                       if n != "word/document.xml"))
            styles_equal = (src.read("word/styles.xml")
                            == dst.read("word/styles.xml"))
            numbering_equal = (src.read("word/numbering.xml")
                               == dst.read("word/numbering.xml"))
            rels = src.read("word/_rels/document.xml.rels")
        external_count = str(rels).count('TargetMode="External"')

        def _normalized(payload: bytes) -> bytes:
            with zipfile.ZipFile(io.BytesIO(payload)) as zf:
                raw = zf.read("word/document.xml")
            root = ET.fromstring(raw)
            for sdt in root.iter(_q("sdt")):
                pr = sdt.find(_q("sdtPr"))
                tag_node = pr.find(_q("tag")) if pr is not None else None
                if tag_node is None:
                    continue
                content = sdt.find(_q("sdtContent"))
                for child in list(content):
                    content.remove(child)
                run = ET.SubElement(content, _q("r"))
                text = ET.SubElement(run, _q("t"))
                text.set(
                    "{http://www.w3.org/XML/1998/namespace}space",
                    "preserve")
                text.text = "@@RECON-FILLED@@"
            return ET.tostring(root)

        sections = []
        for payload in (template, assembled):
            with zipfile.ZipFile(io.BytesIO(payload)) as zf:
                root = ET.fromstring(zf.read("word/document.xml"))
            sections.append(len(list(root.iter(_q("sectPr")))))
        return {
            "parts_identical": parts_identical,
            "outside_unchanged": _normalized(template)
            == _normalized(assembled),
            "styles_equal": styles_equal,
            "numbering_equal": numbering_equal,
            "sections_equal": sections[0] == sections[1],
            "external_count": external_count,
        }

    # -- bridge negatives（profile 各自的 call 形态）--------------------
    def bridge_negatives_desktop(self, state_root: Path):
        config = {"templates_state_root": str(state_root)}
        try:
            legal_entry.call("templates.list", {}, {})
            raise AssertionError("bridge_not_configured_expected")
        except NotConnected as exc:
            self.step("c14_bridge_not_configured",
                      "f56_state_root_not_configured" in str(exc))
        try:
            legal_entry.call("templates.bogus", {}, config)
            raise AssertionError("bridge_unknown_method_expected")
        except NotConnected as exc:
            self.step("c14_bridge_unknown_method_refused",
                      "method_not_connected" in str(exc))
        self.step("c14_method_group_frozen",
                  legal_entry.TEMPLATES_METHODS == TEMPLATES_METHODS)
        self._author_negatives(lambda method, args: legal_entry.call(
            method, args, config))

    def _author_negatives(self, call_with_config):
        self.expect_error(
            "c14_author_impersonation_refused",
            lambda: call_with_config("templates.render", {
                "template_id": TEMPLATE_ID, "matter_id": MATTER,
                "answers_id": "ans-f56-1", "request_id": "f56-req-imp",
                "proposal_id": "f56-fp-imp",
                "actor_id": "recon-assistant",
                "author": "王律师（合成·伪造）"}),
            "f53_author_impersonation")
        self.expect_error(
            "c14_author_channel_mismatch_refused",
            lambda: call_with_config("templates.render", {
                "template_id": TEMPLATE_ID, "matter_id": MATTER,
                "answers_id": "ans-f56-1", "request_id": "f56-req-mis",
                "proposal_id": "f56-fp-mis",
                "actor_id": "recon-assistant",
                "author": "lvyin-docxedit"}),
            "f53_author_channel_mismatch")

    # -- profile drivers ---------------------------------------------------
    def run_desktop(self) -> int:
        temporary = tempfile.TemporaryDirectory(
            prefix="juscite-f56-desktop-")
        state_root = Path(temporary.name) / "state"
        local_root = Path(temporary.name) / "templates-state"
        state_root.mkdir(parents=True)
        registration = Path(temporary.name) / "service-local.json"
        registration.write_text(json.dumps(
            {"url": "http://127.0.0.1:1", "password": "synthetic-recon"}),
            encoding="utf-8")
        config = {
            "harness_public_entry": str(
                self.harness_root
                / "tools/workflow-tools/harness/public_entry.py"),
            "harness_target": "opencode",
            "harness_state_root": str(state_root),
            "harness_service_registration": str(registration),
            "harness_timeout": 120,
            "templates_state_root": str(local_root),
        }
        for path in (str(self.harness_root / "src"),
                     str(self.harness_root / "tools/workflow-tools")):
            if path not in sys.path:
                sys.path.insert(0, path)
        from legal_harness.state.matter_store import MatterStore
        store = MatterStore(state_root)
        store.create_matter(MATTER, "cas://profile-f56-recon")

        def call(method, args):
            return legal_entry.call(method, args, config)

        def register_fn():
            return legal_entry.call("templates.register", {
                "template_id": TEMPLATE_ID, "matter_id": MATTER,
                "material_id": MATERIAL, "title": "民事起诉状模板（F56 对账"
                "合成）", "actor_id": "recon-lawyer",
                "license": dict(LICENSE),
                "bytes_b64": b64(f56_fixtures.build_template_docx())},
                config)

        def register_v2_fn():
            v2 = _mutate_template_alias()
            return legal_entry.call("templates.register", {
                "template_id": TEMPLATE_ID, "matter_id": MATTER,
                "material_id": MATERIAL, "title": "民事起诉状模板 v2（F56"
                " 对账合成）", "actor_id": "recon-lawyer",
                "license": dict(LICENSE), "bytes_b64": b64(v2)}, config)

        def call_face(method, args):
            return legal_entry.call(method, args, config)

        def interview_fn(args):
            return legal_entry.call("templates.interview", args, config)

        def save_fn(args):
            return legal_entry.call("templates.save_answers", args, config)

        def render_fn(args):
            return legal_entry.call("templates.render", args, config)

        def renderings_fn(args):
            return legal_entry.call("templates.renderings", args, config)

        def answers_fn(args):
            return legal_entry.call("templates.answers", args, config)

        def projection(matter_id, material_id):
            return legal_entry.call("author.projection", {
                "matter_id": matter_id, "material_id": material_id}, config)

        self._author_projection = lambda call_, matter_id, material_id: \
            projection(matter_id, material_id)

        print("[profile desktop] SQLite via product bridge subprocess",
              flush=True)
        self.common_flow("desktop", call, call_face, register_fn,
                         interview_fn, save_fn, render_fn, renderings_fn,
                         answers_fn, register_v2_fn, local_root,
                         run_libreoffice=True)
        self.bridge_negatives_desktop(local_root)
        return 0

    def run_selfhost(self, dsn: str, desktop_digests: dict) -> int:
        for path in (str(self.harness_root / "src"),
                     str(self.harness_root / "tools/workflow-tools"),
                     str(self.harness_root),
                     str(self.harness_root / "tests")):
            if path not in sys.path:
                sys.path.insert(0, path)

        from legal_harness.business.provider_registry import (
            resolve_provider_method,
        )
        from legal_harness.business.units import HarnessUnits
        from legal_harness.state.pg_store import PgMatterStore
        import author_policy as ap

        temporary = tempfile.TemporaryDirectory(
            prefix="juscite-f56-selfhost-")
        local_root = Path(temporary.name) / "templates-state"
        store = PgMatterStore(
            Path(temporary.name) / "state", dsn=dsn,
            schema="f56_" + _uuid.uuid4().hex[:12])
        units = HarnessUnits(store)
        methods = ("harness.register_material", "harness.read_material",
                   "harness.list_materials", "harness.add_material_revision",
                   "harness.formal_propose", "harness.formal_proposal_read",
                   "harness.formal_proposal_list")
        bound = {name: resolve_provider_method(name, units)
                 for name in methods}
        store.create_matter(MATTER, "cas://profile-f56-recon")
        config = {"templates_state_root": str(local_root)}

        def call(method, args):
            return bound[method](**args)

        def register_fn():
            return td.templates_call("templates.register", {
                "template_id": TEMPLATE_ID, "matter_id": MATTER,
                "material_id": MATERIAL, "title": "民事起诉状模板（F56 对账"
                "合成）", "actor_id": "recon-lawyer",
                "license": dict(LICENSE),
                "bytes_b64": b64(f56_fixtures.build_template_docx())},
                config, harness_call=call)

        def register_v2_fn():
            v2 = _mutate_template_alias()
            return td.templates_call("templates.register", {
                "template_id": TEMPLATE_ID, "matter_id": MATTER,
                "material_id": MATERIAL, "title": "民事起诉状模板 v2（F56"
                " 对账合成）", "actor_id": "recon-lawyer",
                "license": dict(LICENSE), "bytes_b64": b64(v2)},
                config, harness_call=call)

        def call_face(method, args):
            return td.templates_call(method, args, config,
                                     harness_call=call)

        def interview_fn(args):
            return td.templates_call("templates.interview", args, config,
                                     harness_call=call)

        def save_fn(args):
            return td.templates_call("templates.save_answers", args, config)

        def render_fn(args):
            return td.templates_call("templates.render", args, config,
                                     harness_call=call)

        def renderings_fn(args):
            return td.templates_call("templates.renderings", args, config)

        def answers_fn(args):
            return td.templates_call("templates.answers", args, config)

        def projection(matter_id, material_id):
            listing = call("harness.formal_proposal_list", {
                "scope": {"kind": "matter", "matterId": matter_id},
                "material_id": material_id})
            return ap.decision_projection(listing, matter_id, material_id)

        self._author_projection = lambda call_, matter_id, material_id: \
            projection(matter_id, material_id)

        print("[profile selfhost] PgMatterStore direct (lh-pg-e08)",
              flush=True)
        self.common_flow("selfhost", call, call_face, register_fn,
                         interview_fn, save_fn, render_fn, renderings_fn,
                         answers_fn, register_v2_fn, local_root,
                         run_libreoffice=False)
        # C14 selfhost 桥负向（面级直调形态）＋作者负向。
        try:
            td.templates_call("templates.list", {}, {})
            raise AssertionError("bridge_not_configured_expected")
        except NotConnected as exc:
            self.step("c14_bridge_not_configured",
                      "f56_state_root_not_configured" in str(exc))
        self.step("c14_method_group_frozen",
                  legal_entry.TEMPLATES_METHODS == TEMPLATES_METHODS)
        # selfhost 面级直调形态：组外伪方法＝面级 f56_method_unknown
        # （method_not_connected 是 legal_entry 分发层的 desktop 形态）。
        self.expect_error(
            "c14_bridge_unknown_method_typed",
            lambda: td.templates_call("templates.bogus", {}, config),
            "f56_method_unknown")
        self._author_negatives(
            lambda method, args: td.templates_call(method, args, config,
                                                   harness_call=call))
        # C13 跨 profile：装配字节逐字节相等（生成面与存储后端无关）。
        selfhost_digests = self.digests.get("selfhost")
        self.step("c13_cross_profile_byte_identical",
                  bool(desktop_digests)
                  and desktop_digests == selfhost_digests,
                  desktop=desktop_digests, selfhost=selfhost_digests)
        store.destroy()
        return 0


_ALIAS_OLD = "受诉法院全称".encode("utf-8")
_ALIAS_NEW = "受诉法院名称".encode("utf-8")


def _mutate_template_alias() -> bytes:
    """模板 v2 对照字节（控件别名变更→sha 变更；zip 内部件改写须解包
    再打包——压缩容器不支持原地替换）。"""
    out = io.BytesIO()
    with zipfile.ZipFile(
            io.BytesIO(f56_fixtures.build_template_docx())) as src, \
            zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as dst:
        for info in src.infolist():
            payload = src.read(info.filename)
            if info.filename == "word/document.xml":
                payload = payload.replace(_ALIAS_OLD, _ALIAS_NEW)
            item = zipfile.ZipInfo(info.filename,
                                   date_time=(1980, 1, 1, 0, 0, 0))
            item.compress_type = zipfile.ZIP_DEFLATED
            dst.writestr(item, payload)
    v2 = out.getvalue()
    assert v2 != f56_fixtures.build_template_docx()
    return v2


def _resolve_soffice() -> Path | None:
    raw = Path(DEFAULT_SOFFICE)
    if not raw.is_file():
        return None
    if raw.name.lower() == "soffice.exe":
        com = raw.with_name("soffice.com")
        if com.is_file():
            return com
    return raw


def _soffice_convert(soffice: Path, payload: bytes):
    out_dir = Path(tempfile.mkdtemp(prefix="f56-lo-"))
    profile = (out_dir / "lo-profile").resolve()
    profile.mkdir(parents=True)
    target = out_dir / "assembled.docx"
    target.write_bytes(payload)
    proc = subprocess.run(
        [str(soffice), "--headless", "--norestore", "--nolockcheck",
         "-env:UserInstallation=" + profile.as_uri(),
         "--convert-to", "pdf", "--outdir", str(out_dir), str(target)],
        capture_output=True, text=True, encoding="utf-8",
        errors="replace", timeout=300)
    pdf = out_dir / "assembled.pdf"
    return proc.returncode, (pdf if pdf.is_file() else None)


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
    evidence_dir = REPO_ROOT / "docs" / "construction" / "evidence" \
        / "F56" / profile
    evidence_dir.mkdir(parents=True, exist_ok=True)
    finished = datetime.now(timezone.utc).isoformat()
    summary = {
        "schema": "juscite-f56-template-drafting-recon/1",
        "unit": "W4-U38",
        "feature": "F56",
        "profile": profile,
        "verdict": "RECON_OK" if code == 0 else "RECON_FAIL",
        "started_at": started,
        "finished_at": finished,
        "harness_worktree": str(harness_root),
        "harness_branch": "w4-u31 (read-only; 链头 8f65dc6f 基 "
                          "w4-u01@23f56d70＝A2 战役分支链；本单零 "
                          "harness 改动)",
        "checks": recon.checks,
        "check_count": len(recon.checks),
        "digests": recon.digests.get(profile),
        "failed": [c["check"] for c in recon.checks
                   if c["status"] != "PASS"],
    }
    payload = json.dumps(summary, ensure_ascii=False, indent=1)
    (evidence_dir / "f56_template_drafting_recon.json").write_text(
        payload + "\n", encoding="utf-8")
    lines = [f"# F56 文书模板起草 recon（{profile}）", "",
             f"- unit: W4-U38 · profile: {profile}",
             f"- verdict: **{summary['verdict']}**"
             f" ({len(recon.checks)} checks, exit {code})",
             f"- harness: `{harness_root}` @ w4-u31（链头 8f65dc6f 只读"
             "消费；master 929d0802 零动；本单零 harness 改动）",
             f"- started: {started} · finished: {finished}", "",
             "| # | check | status |", "|---|---|---|"]
    for index, check in enumerate(recon.checks, 1):
        lines.append(f"| {index} | {check['check']}"
                     f" | {check['status']} |")
    lines += ["", "全部合成材料（f56_fixtures 纯 stdlib 合成模板：内容控件"
              "×7＋无 tag 控件×1＋外链×1＋core.xml 元数据）；E13 模板结构"
              "视觉段承接＝C07 结构段（八硬维具名＋外链/隐私信息维）＋"
              "C08 视觉段（desktop LibreOffice 真渲染：答案在/占位符不在）。"
              "desktop＝产品桥子进程全链（SQLite 状态根）；selfhost＝"
              "PgMatterStore 直连 lh-pg-e08（同封闭注册；装配字节与 "
              "desktop 逐字节相等）。"]
    (evidence_dir / "f56_template_drafting_recon.md").write_text(
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
    if not (args.harness_root
            / "tools/workflow-tools/harness/public_entry.py").exists():
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

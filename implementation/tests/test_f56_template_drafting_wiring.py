"""F56 文书模板起草产品侧接线测试（W4-U38）：模板库＋变量填充＋访谈式
三段。

全部合成材料（f56_fixtures 纯 stdlib 合成模板语料）。templates.* 八方法
走 legal_entry 冻结方法组；harness 登记面（register_material upload /
add_material_revision source=assistant_edit＋formal_propose channel=
machine）经 subprocess seam 注入（单测零仓依赖；真 public_entry 全链
实跑对账在 tools/PENDING_OWNER_f56_template_drafting_recon.py 双
profile）。

本地面（变量确定性提取＋答案校验＋装配＋结构/视觉具名硬门＋独立
lxml 检查器＋append-only＋幂等重放）在 seam 桥下真跑——这些不依赖
harness 检出。
"""

from __future__ import annotations

import base64
import hashlib
import io
import json
import sys
import tempfile
import unittest
import unittest.mock
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import f56_fixtures  # noqa: E402
import legal_entry  # noqa: E402
import template_drafting as td  # noqa: E402
from bridge_errors import NotConnected  # noqa: E402
from template_drafting import TemplateDraftingError  # noqa: E402

TEMPLATES_METHODS = (
    "templates.register", "templates.list", "templates.template",
    "templates.interview", "templates.save_answers", "templates.answers",
    "templates.render", "templates.renderings",
)
AUTHOR = "lvyin-templates"  # F53 作者声明闭集（W4-U38；templates 通道）
LICENSE = {"license": "所内受控（合成）", "source": "合成模板组",
           "notice": None}


def b64(payload: bytes) -> str:
    return base64.b64encode(payload).decode("ascii")


def sha(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def mutate_part(template_bytes: bytes, old: bytes, new: bytes) -> bytes:
    """zip 内部件字节替换（压缩容器不支持原地 replace——解包改再打包）。"""
    out = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(template_bytes)) as src,             zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as dst:
        for info in src.infolist():
            payload = src.read(info.filename)
            if old in payload:
                payload = payload.replace(old, new)
            item = zipfile.ZipInfo(info.filename,
                                   date_time=(1980, 1, 1, 0, 0, 0))
            item.compress_type = zipfile.ZIP_DEFLATED
            dst.writestr(item, payload)
    return out.getvalue()


class StubHarness:
    """harness 登记面 seam（单测零仓依赖）：最小闭包状态。"""

    def __init__(self) -> None:
        self.revision = 0
        self.material_bytes = b""
        self.sources: list = []
        self.proposals: list[dict] = []

    def __call__(self, method: str, args: dict) -> dict:
        if method == "harness.register_material":
            self.revision = 1
            self.material_bytes = base64.b64decode(args["material"]["bytesB64"])
            return {"revision": 1, "sha256": sha(self.material_bytes),
                    "casRef": "sha256-synth"}
        if method == "harness.read_material":
            return {"bytesB64": b64(self.material_bytes),
                    "sha256": sha(self.material_bytes)}
        if method == "harness.list_materials":
            return {"materials": [{"id": "mat-f56",
                                   "currentRevision": self.revision,
                                   "revisions": []}]}
        if method == "harness.add_material_revision":
            self.revision += 1
            self.sources.append(args["revision"].get("source"))
            return {"revision": self.revision,
                    "source": args["revision"].get("source"),
                    "sha256": "synth", "casRef": "synth",
                    "baseRevision": args["revision"].get("baseRevision")}
        if method == "harness.formal_propose":
            self.proposals.append(args["proposal"])
            return {"proposal": {"proposalId":
                                 args["proposal"]["proposalId"],
                                 "state": "pending",
                                 "channel": args["proposal"]["channel"],
                                 "author": args["proposal"]["author"],
                                 "baseRevision":
                                 args["proposal"]["baseRevision"],
                                 "quotes": args["proposal"]["quotes"]}}
        raise AssertionError("unexpected method: " + method)


class F56TestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory(prefix="juscite-f56-test-")
        self.addCleanup(self.tmp.cleanup)
        self.state_root = Path(self.tmp.name) / "state"
        self.config = {"templates_state_root": str(self.state_root)}
        self.harness = StubHarness()




def _register(case: F56TestCase, template_id: str = "t-f56",
              bytes_=None, license_=None, material_id: str = "mat-f56") -> dict:
    return td.register_template(
        case.state_root, case.config, {
            "template_id": template_id, "matter_id": "m-f56",
            "material_id": material_id, "title": "合成起诉状模板（F56）",
            "actor_id": "synth-lawyer",
            "license": license_ or dict(LICENSE),
            "bytes_b64": b64(bytes_ if bytes_ is not None
                             else f56_fixtures.build_template_docx())},
        harness_call=case.harness)


def _save(case: F56TestCase, answers=None, answers_id: str = "ans-1",
          template_id: str = "t-f56", matter_id: str = "m-f56") -> dict:
    return td.save_answers(case.state_root, {
        "template_id": template_id, "matter_id": matter_id,
        "answers_id": answers_id,
        "answers": dict(answers if answers is not None
                        else f56_fixtures.ANSWERS)})


def _render(case: F56TestCase, answers_id: str = "ans-1",
            request_id: str = "req-1", proposal_id: str = "fp-1",
            author: str = AUTHOR, template_id: str = "t-f56",
            matter_id: str = "m-f56") -> dict:
    return td.render(case.state_root, case.config, {
        "template_id": template_id, "matter_id": matter_id,
        "answers_id": answers_id, "request_id": request_id,
        "proposal_id": proposal_id, "actor_id": "synth-assistant",
        "author": author, "note": "F56 单测合成装配"},
        harness_call=case.harness)


def expect_typed(case: F56TestCase, code_part: str, call, *args, **kwargs):
    try:
        call(*args, **kwargs)
    except TemplateDraftingError as exc:
        case.assertIn(code_part, str(exc))
        return str(exc)
    case.fail("expected typed error: " + code_part)


# --------------------------------------------------------------------------
# 1. 方法组＋桥分发
# --------------------------------------------------------------------------

class F56MethodGroupTests(F56TestCase):
    def test_method_group_frozen(self) -> None:
        self.assertEqual(legal_entry.TEMPLATES_METHODS,
                         frozenset(TEMPLATES_METHODS))
        # 伪方法不在冻结组（改授权/直改模板字节/跳过访谈直填）。
        for fake in ("templates.set_license", "templates.rewrite",
                     "templates.fill_raw", "templates.decide"):
            self.assertNotIn(fake, legal_entry.TEMPLATES_METHODS)

    def test_bridge_state_root_not_configured(self) -> None:
        try:
            legal_entry.call("templates.list", {}, {})
        except NotConnected as exc:
            self.assertIn("f56_state_root_not_configured", str(exc))
        else:
            self.fail("expected NOT_CONNECTED")

    def test_bridge_unknown_method_refused(self) -> None:
        # 组外伪方法在 legal_entry 分发层具名拒（method_not_connected）；
        # 组内未知子方法（直调面级）才走 f56_method_unknown。
        try:
            legal_entry.call("templates.bogus", {}, self.config)
        except NotConnected as exc:
            self.assertIn("method_not_connected", str(exc))
        else:
            self.fail("expected NOT_CONNECTED")
        try:
            td.templates_call("templates.bogus", {}, self.config)
        except TemplateDraftingError as exc:
            self.assertIn("f56_method_unknown", str(exc))
        else:
            self.fail("expected typed refusal")


# --------------------------------------------------------------------------
# 2. 变量清单确定性提取（模板自描述；登记级校验）
# --------------------------------------------------------------------------

class F56ExtractionTests(F56TestCase):
    def test_variables_extracted_deterministic(self) -> None:
        model = td.parse_template(f56_fixtures.build_template_docx())
        names = [(v["name"], v["kind"], v["controls"])
                 for v in model["variables"]]
        self.assertEqual(names, [
            ("plaintiff", "text", 1), ("plaintiff_address", "text", 1),
            ("defendant", "text", 1), ("claim_total", "amount", 1),
            ("interest_total", "amount", 1), ("contract_date", "date", 1),
            ("court", "text", 1), ("copies", "number", 1)])
        self.assertEqual(model["tagless_controls"], 1)
        again = td.parse_template(f56_fixtures.build_template_docx())
        self.assertEqual(again["variables"], model["variables"])

    def test_registration_view_and_license(self) -> None:
        view = _register(self)
        self.assertFalse(view["replayed"])
        self.assertEqual(view["version"], 1)
        self.assertEqual(view["license"], LICENSE)
        self.assertEqual(view["controls_total"], 8)
        self.assertEqual(len(view["variables"]), 8)
        # 幂等重放：同 id 同 sha。
        replay = _register(self)
        self.assertTrue(replay["replayed"])
        # 版本账回读。
        stored = legal_entry.call("templates.template",
                                  {"template_id": "t-f56"}, self.config)
        self.assertEqual(stored["sha256"],
                         sha(f56_fixtures.build_template_docx()))
        listing = legal_entry.call("templates.list", {}, self.config)
        self.assertEqual(listing["count"], 1)

    def test_registration_requires_license(self) -> None:
        expect_typed(self, "f56_license_required", _register, self,
                     license_={"license": "", "source": "s"})
        # license 缺位（None 不经 _register 的缺省替换——直调面级）。
        expect_typed(self, "f56_license_required", td.register_template,
                     self.state_root, self.config, {
                         "template_id": "t-f56", "matter_id": "m-f56",
                         "material_id": "mat-f56", "title": "t",
                         "actor_id": "synth-lawyer",
                         "bytes_b64": b64(
                             f56_fixtures.build_template_docx())},
                     harness_call=self.harness)

    def test_registration_refusals(self) -> None:
        # 零控件文档不是模板（不发明变量）。
        expect_typed(self, "f56_template_no_variables", _register, self,
                     bytes_=f56_fixtures.build_plain_docx())
        expect_typed(self, "f56_control_outside_body", _register, self,
                     bytes_=f56_fixtures.build_footer_control_docx())
        # tag 形不合法：kind 闭集外（zip 内部件改写需解包再打包）。
        bad = mutate_part(
            f56_fixtures.build_template_docx(),
            'w:val="amount:claim_total"'.encode("utf-8"),
            'w:val="choice:claim_total"'.encode("utf-8"))
        self.assertNotEqual(bad, f56_fixtures.build_template_docx())
        expect_typed(self, "f56_template_tag_invalid", _register, self,
                     bytes_=bad)

    def test_template_not_found(self) -> None:
        expect_typed(self, "f56_template_not_found",
                     legal_entry.call, "templates.template",
                     {"template_id": "nope"}, self.config)


# --------------------------------------------------------------------------
# 3. 访谈三段：问询→答案校验→装配
# --------------------------------------------------------------------------

class F56InterviewTests(F56TestCase):
    def test_interview_question_set(self) -> None:
        _register(self)
        face = td.interview(self.state_root, self.config,
                            {"template_id": "t-f56"},
                            harness_call=self.harness)
        self.assertEqual(face["segment"], "interview")
        self.assertEqual(
            [(q["name"], q["kind"], q["required"])
             for q in face["questions"]],
            [("plaintiff", "text", True),
             ("plaintiff_address", "text", True),
             ("defendant", "text", True),
             ("claim_total", "amount", True),
             ("interest_total", "amount", True),
             ("contract_date", "date", True),
             ("court", "text", True), ("copies", "number", True)])
        self.assertEqual(face["template"]["sha256"],
                         sha(f56_fixtures.build_template_docx()))
        # 缺模板不发明问题集。
        expect_typed(self, "f56_template_not_found",
                     td.interview, self.state_root, self.config,
                     {"template_id": "nope"}, harness_call=self.harness)


class F56AnswersTests(F56TestCase):
    def setUp(self) -> None:
        super().setUp()
        _register(self)

    def test_answers_append_and_readback(self) -> None:
        sheet = _save(self)
        self.assertFalse(sheet["replayed"])
        self.assertEqual(sheet["template_version"], 1)
        self.assertEqual(sheet["template_sha256"],
                         sha(f56_fixtures.build_template_docx()))
        readback = legal_entry.call("templates.answers", {
            "template_id": "t-f56", "matter_id": "m-f56",
            "answers_id": "ans-1"}, self.config)
        self.assertEqual(readback["answers"], f56_fixtures.ANSWERS)
        # 幂等重放＋异内容冲突。
        replay = _save(self)
        self.assertTrue(replay["replayed"])
        expect_typed(self, "f56_answers_id_conflict", _save, self,
                     answers={**f56_fixtures.ANSWERS,
                              "court": "别家法院（合成）"})

    def test_answers_missing_and_unknown_refuse(self) -> None:
        # 缺变量＝具名清单拒不发明值。
        partial = {k: v for k, v in f56_fixtures.ANSWERS.items()
                   if k != "court"}
        code = expect_typed(self, "f56_answers_missing_variables",
                            _save, self, answers=partial)
        self.assertIn("court", code)
        # 多变量＝具名拒不发明变量。
        expect_typed(self, "f56_answers_unknown_variables", _save, self,
                     answers={**f56_fixtures.ANSWERS, "bogus_var": "x"})

    def test_answer_value_validation(self) -> None:
        # 浮点 JSON 数值拒（金额 Decimal/整分边界）。
        expect_typed(self, "f56_answer_not_string", _save, self,
                     answers={**f56_fixtures.ANSWERS, "claim_total": 85000.5})
        expect_typed(self, "f56_answer_not_string", _save, self,
                     answers={**f56_fixtures.ANSWERS, "claim_total": True})
        # 金额形：千位逗号/纯小数过，算式/多小数点拒（成功案各占独立
        # answers_id——同 id 异内容是冲突负向，不能复用）。
        _save(self, answers={**f56_fixtures.ANSWERS,
                             "claim_total": "1,234,567.89"},
              answers_id="ans-amt")
        expect_typed(self, "f56_answer_value_invalid", _save, self,
                     answers={**f56_fixtures.ANSWERS, "claim_total": "12.3.4"})
        expect_typed(self, "f56_answer_value_invalid", _save, self,
                     answers={**f56_fixtures.ANSWERS, "claim_total": "1+2"})
        # 日期：真日历（2026-02-30 拒）。
        expect_typed(self, "f56_answer_value_invalid", _save, self,
                     answers={**f56_fixtures.ANSWERS,
                              "contract_date": "2026-02-30"})
        _save(self, answers={**f56_fixtures.ANSWERS,
                             "contract_date": "2024-02-29"},
              answers_id="ans-date")
        # 单行：换行/制表/控制字符拒。
        expect_typed(self, "f56_answer_multiline", _save, self,
                     answers={**f56_fixtures.ANSWERS, "court": "a\nb"})
        expect_typed(self, "f56_answer_multiline", _save, self,
                     answers={**f56_fixtures.ANSWERS, "court": "a\tb"})
        # 空白值拒。
        expect_typed(self, "f56_answer_value_invalid", _save, self,
                     answers={**f56_fixtures.ANSWERS, "court": "  "})


class F56RenderTests(F56TestCase):
    def setUp(self) -> None:
        super().setUp()
        _register(self)
        _save(self)

    def test_render_assembles_and_registers(self) -> None:
        face = _render(self)
        self.assertFalse(face["replayed"])
        self.assertTrue(face["structure_visual"]["all_passed"])
        self.assertTrue(face["independent_check"]["all_passed"])
        self.assertEqual(face["independent_check"]["checker"], "lxml/etree")
        self.assertEqual(face["harness"]["assistant_edit"]["source"],
                         "assistant_edit")
        self.assertEqual(face["harness"]["assistant_edit"]["revision"], 2)
        self.assertEqual(face["harness"]["proposal"]["channel"], "machine")
        self.assertEqual(face["harness"]["proposal"]["author"], AUTHOR)
        self.assertEqual(self.harness.sources, ["assistant_edit"])
        proposal = self.harness.proposals[0]
        self.assertEqual(len(proposal["quotes"]), 8)
        self.assertEqual(proposal["quotes"][0]["text"], "【原告名称】")
        self.assertEqual(proposal["quotes"][0]["sourceRef"]["version"], "1")
        # 装配清单回读（renderings append-only 视图）。
        listing = legal_entry.call("templates.renderings", {
            "template_id": "t-f56", "matter_id": "m-f56"}, self.config)
        self.assertEqual(listing["count"], 1)
        self.assertEqual(listing["renderings"][0]["output_id"], "t-f56:0001")

    def test_render_idempotent_replay(self) -> None:
        first = _render(self)
        outputs = len(legal_entry.call("templates.renderings", {
            "template_id": "t-f56", "matter_id": "m-f56"}, self.config)
            ["renderings"])
        replay = _render(self)
        self.assertTrue(replay["replayed"])
        self.assertEqual(replay["output_id"], first["output_id"])
        self.assertEqual(len(legal_entry.call("templates.renderings", {
            "template_id": "t-f56", "matter_id": "m-f56"}, self.config)
            ["renderings"]), outputs)

    def test_render_second_round_append_only(self) -> None:
        _render(self)
        self.harness.proposals.clear()
        _save(self, answers={**f56_fixtures.ANSWERS,
                             "court": "合成市第二中级人民法院（合成）"},
              answers_id="ans-2")
        second = _render(self, answers_id="ans-2", request_id="req-2",
                         proposal_id="fp-2")
        self.assertEqual(second["output_id"], "t-f56:0002")
        listing = legal_entry.call("templates.renderings", {
            "template_id": "t-f56", "matter_id": "m-f56"}, self.config)
        self.assertEqual([row["output_id"] for row in listing["renderings"]],
                         ["t-f56:0001", "t-f56:0002"])
        self.assertEqual(self.harness.revision, 3)

    def test_render_refusals(self) -> None:
        # 缺模板/缺答案/钉定错配/作者冒充/通道错绑 全具名拒。
        expect_typed(self, "f56_template_not_found", _render, self,
                     template_id="nope")
        expect_typed(self, "f56_answers_not_found", _render, self,
                     answers_id="nope")
        # 答案表钉 v1 模板；版本进 v2（别名变更→字节变更→sha 变更）后
        # 旧答案表拒绝直 render 新版本（钉定错配具名拒）。
        v2_bytes = mutate_part(
            f56_fixtures.build_template_docx(),
            "受诉法院全称".encode("utf-8"), "受诉法院名称".encode("utf-8"))
        self.assertNotEqual(v2_bytes, f56_fixtures.build_template_docx())
        td.register_template(
            self.state_root, self.config, {
                "template_id": "t-f56", "matter_id": "m-f56",
                "material_id": "mat-f56", "title": "模板 v2",
                "actor_id": "synth-lawyer", "license": dict(LICENSE),
                "bytes_b64": b64(v2_bytes)}, harness_call=self.harness)
        expect_typed(self, "f56_answers_template_mismatch", _render, self,
                     request_id="req-v2", proposal_id="fp-v2")
        expect_typed(self, "f53_author_impersonation", _render, self,
                     author="王律师（合成·伪造）")
        expect_typed(self, "f53_author_channel_mismatch", _render, self,
                     author="lvyin-docxedit")

    def test_render_answers_must_pin_registered_template(self) -> None:
        # 未知 matter 拒。
        expect_typed(self, "f56_template_matter_mismatch", _save, self,
                     matter_id="m-other")
        expect_typed(self, "f56_template_matter_mismatch", _render, self,
                     matter_id="m-other")


# --------------------------------------------------------------------------
# 4. 结构/视觉具名检查＋确定性
# --------------------------------------------------------------------------

class F56StructureTests(F56TestCase):
    def setUp(self) -> None:
        super().setUp()
        self.template = f56_fixtures.build_template_docx()
        self.model = td.parse_template(self.template)
        self.assembled = td.fill_template(
            self.template, self.model["variables"], f56_fixtures.ANSWERS)

    def test_structure_report_all_pass(self) -> None:
        report = td.structure_report(self.template, self.assembled,
                                     self.model["variables"],
                                     f56_fixtures.ANSWERS)
        self.assertTrue(report["all_passed"], report["failed_dims"])
        self.assertEqual(report["external_links"]["count"], 1)
        self.assertEqual(report["privacy"]["creator"],
                         "合成模板组（synthetic）")
        self.assertTrue(report["privacy"]["part_present"])
        for dim in ("parts_identical_except_document",
                    "outside_controls_unchanged", "controls_all_filled",
                    "placeholder_residue_zero", "styles_part_identical",
                    "numbering_part_identical", "sections_preserved",
                    "document_rels_identical"):
            self.assertTrue(report[dim], dim)

    def test_independent_checker_all_pass(self) -> None:
        checker = td.independent_check(self.template, self.assembled,
                                       self.model["variables"],
                                       f56_fixtures.ANSWERS)
        self.assertTrue(checker["all_passed"], checker["failed_dims"])
        self.assertEqual(checker["checker"], "lxml/etree")

    def _repack(self, payload: bytes, mutate) -> bytes:
        out = io.BytesIO()
        with zipfile.ZipFile(io.BytesIO(payload)) as src, \
                zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as dst:
            for info in src.infolist():
                item = zipfile.ZipInfo(info.filename,
                                       date_time=(1980, 1, 1, 0, 0, 0))
                item.compress_type = zipfile.ZIP_DEFLATED
                dst.writestr(item, mutate(info.filename, src.read(info.filename)))
        return out.getvalue()

    def test_structure_dims_detect_tamper(self) -> None:
        # styles 部件被改：部件恒等＋styles 恒等两维抓出。
        tampered = self._repack(
            self.assembled, lambda name, data:
            data.replace(b"Normal", b"Tamprd")
            if name == "word/styles.xml" else data)
        report = td.structure_report(self.template, tampered,
                                     self.model["variables"],
                                     f56_fixtures.ANSWERS)
        self.assertIn("parts_identical_except_document",
                      report["failed_dims"])
        self.assertIn("styles_part_identical", report["failed_dims"])
        # 占位残留：装配字节里塞回占位文本 → 残留维抓出。
        residue = self._repack(
            self.assembled, lambda name, data:
            data.replace("合成市合成区人民法院".encode("utf-8"),
                         "【受诉法院全称】".encode("utf-8"))
            if name == "word/document.xml" else data)
        report = td.structure_report(self.template, residue,
                                     self.model["variables"],
                                     f56_fixtures.ANSWERS)
        self.assertFalse(report["placeholder_residue_zero"])
        # 控件外结构被改：归一化形不等抓出。
        outside = self._repack(
            self.assembled, lambda name, data:
            data.replace("此致".encode("utf-8"), "此致 ".encode("utf-8"))
            if name == "word/document.xml" else data)
        report = td.structure_report(self.template, outside,
                                     self.model["variables"],
                                     f56_fixtures.ANSWERS)
        self.assertFalse(report["outside_controls_unchanged"])

    def test_structure_failure_gate_unit(self) -> None:
        # 结构硬维拒绝路径为防御性面（装配=fill(template) 纯函数，公开通
        # 路结构性不可产出败维产物）；此处单测硬门本身：败维→具名码形。
        _register(self)
        _save(self)
        bad_assembled = self._repack(
            self.assembled, lambda name, data:
            data.replace(b"Normal", b"Tamprd")
            if name == "word/styles.xml" else data)
        report = td.structure_report(self.template, bad_assembled,
                                     self.model["variables"],
                                     f56_fixtures.ANSWERS)
        self.assertFalse(report["all_passed"])
        code = "f56_structure_check_failed:" + ",".join(
            report["failed_dims"])
        self.assertIn("styles_part_identical", code)

    def test_multi_control_variable_fills_all(self) -> None:
        rep_bytes = f56_fixtures.build_repeat_template_docx()
        model = td.parse_template(rep_bytes)
        self.assertEqual(model["variables"][0]["controls"], 2)
        filled = td.fill_template(rep_bytes, model["variables"],
                                  {"party": "合成当事人"})
        asm = td.parse_template(filled)
        texts = [td._control_text(s) for s in
                 asm["root"].iter(td._q("sdt"))]
        self.assertEqual(texts, ["合成当事人", "合成当事人"])
        report = td.structure_report(rep_bytes, filled, model["variables"],
                                     {"party": "合成当事人"})
        self.assertTrue(report["all_passed"], report["failed_dims"])

    def test_determinism_same_input_same_bytes(self) -> None:
        again = td.fill_template(self.template, self.model["variables"],
                                 f56_fixtures.ANSWERS)
        self.assertEqual(again, self.assembled)
        self.assertEqual(td.content_digest(again),
                         td.content_digest(self.assembled))
        # 装配产物 manifest 零时钟字段（可复现锚：digest 不含容器时间戳）。
        _register(self)
        _save(self)
        face = _render(self)
        self.assertNotIn("recordedAt", json.dumps(face))
        self.assertNotIn("recorded_at", json.dumps(face))


# --------------------------------------------------------------------------
# 5. F53 策略面：templates 通道闭集化（W4-U38 公开改口随在案）
# --------------------------------------------------------------------------

class F56AuthorPolicyTests(F56TestCase):
    def test_templates_channel_in_closed_set(self) -> None:
        view = legal_entry.call("author.policy", {}, {})
        self.assertEqual(
            view["machine_channels"]["templates"],
            {"author": "lvyin-templates", "kind": "machine"})
        binding = legal_entry.call("author.check", {
            "channel": "templates", "author": "lvyin-templates"}, {})
        self.assertEqual(binding, {"channel": "templates",
                                   "author": "lvyin-templates",
                                   "kind": "machine"})


if __name__ == "__main__":
    unittest.main()

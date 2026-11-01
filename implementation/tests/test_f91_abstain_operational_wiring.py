# -*- coding: utf-8 -*-
"""F91 abstain 反修复＋operational 模式产品侧接线测试（工单 W4-U46）。

双夹具（沿 test_f87_extraction_gate_wiring 同款）：
  (a) 合成 codices 正式面（tmp CSV 树＋合成 md 载体）——覆盖证据与
      重过闸的主战场；
  (b) 钉定公开面 v1.1（codices 分支 jusbench/w2a-u14-f70-citation）。

合同硬点（06 行 F91 acceptance / 工单验收硬点）：
  反修复＝对误拒答的纠正必须重新过同一核验闸（不得绕过 F70/F87 引证
  闸直出——重过闸=结构断言：纠正产物走同一 citation_gate/extraction_
  gate 路径）；覆盖充分性判定绑定可具名证据（知识库/法源覆盖面，不模
  型自评）；operational 模式＝操作性任务不受法律闸阻断照常交付，产物
  带『非法律结论』边界标记；fail-closed 红线不松动：未知关键输入仍阻
  断正式结论（08§4）。

全部候选文本/引文均为合成材料；唯一真实数据＝本机 codices 发布件
（只读）。
"""

from __future__ import annotations

import ast
import csv
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python"))

import legal_entry  # noqa: E402
import abstain_operational as ao  # noqa: E402
from bridge_errors import NotConnected  # noqa: E402

# 钉定公开面 v1.1（codices 分支 jusbench/w2a-u14-f70-citation @ dc0caf68e；
# 与 test_f87_extraction_gate_wiring 同钉定）
LCCC_PATH = Path(
    r"D:\Codex\1.法律工作区\legal-cn-core-codices工作区"
    r"\legal-cn-core-codices-repo\.local\worktrees\w2a-u14\lccc_consumer.py"
)
LCCC_SHA256 = (
    "55eea7c27e08d6b236b7ab7a83810c86ee0898c335c4668d875a492775db863a"
)

DOC_COLUMNS = ["WJBS", "BT", "GBRQ", "SXX", "DE_01018", "SXRQ", "SHXRQ",
               "DE_01001", "DE_01021"]


def _body(date8: str, seq: str = "0001") -> str:
    return "0100" + "0000001001" + date8 + seq + "000" + "00"


# 合成行：现行 / 已废止 / 尚未施行（沿 F87 夹具形态）
SYN_DOCS = [
    ("中华人民共和国合成数据保护法", _body("20210820", "0091"), "01",
     "20211101", ""),
    ("中华人民共和国合成旧管理条例", _body("20150101"), "04", "20150601",
     "20200101"),
    ("中华人民共和国合成未来施行法", _body("20260626"), "02", "20270101", ""),
]
SYN_WJBS: dict = {}
SYN_CUR = "中华人民共和国合成数据保护法"
SYN_QUOTE_ART1 = "为了规范合成数据处理活动，保护合成数据权益，制定本法。"


def build_synthetic_formal_root() -> Path:
    root = Path(tempfile.mkdtemp(prefix="f91-synth-"))
    with (root / "legal_documents.csv").open("w", encoding="utf-8-sig",
                                             newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(DOC_COLUMNS)
        for title, body, sxx, sxrq, shxrq in SYN_DOCS:
            wjbs = "1.2.156.3005.6-" + body
            SYN_WJBS[title + "@" + body] = wjbs
            writer.writerow([wjbs, title, body[14:22], sxx, sxx, sxrq, shxrq,
                             body, "国家法律法规数据库"])
    for name in ("legal_contents.csv", "legal_relations.csv",
                 "legal_sources.csv", "cases.csv", "case_legal_references.csv",
                 "case_holdings.csv", "practice_references.csv"):
        (root / name).write_text("WJBS\n", encoding="utf-8-sig")
    cur = SYN_WJBS[SYN_CUR + "@" + _body("20210820", "0091")]
    md_cur = (
        "---\nobject_type: \"legal_document\"\nidentifier: \"%s\"\n---\n\n"
        "# %s\n\n"
        "- **第一条**\u3000\u3000%s\n\n"
        "- **第二条**\u3000\u3000在中华人民共和国境内处理合成数据，适用本法。\n\n"
        "- **第三条**\u3000\u3000处理合成数据应当遵循合法、正当、必要原则。\n"
        % (cur, SYN_CUR, SYN_QUOTE_ART1))
    (root / ("carrier_%s.md" % cur)).write_text(md_cur, encoding="utf-8")
    (root / "README.md").write_text("synthetic F91 test face\n",
                                    encoding="utf-8")
    (root / "SHA256SUMS").write_text("synthetic\n", encoding="utf-8")
    return root


def pinned_config(state_root: Path) -> dict:
    return {
        "abstain_state_root": str(state_root / "abstain"),
        "extraction_gate_state_root": str(state_root / "gate"),
        "codices_import_path": str(LCCC_PATH.parent),
        "codices_formal_root": str(build_synthetic_formal_root()),
        "codices_face_sha256": LCCC_SHA256,
    }


AS_OF = "20261016"


class AbstainRecordNamedRefusalTest(unittest.TestCase):
    """拒答具名入账（防『动不动拒绝用』）＋理由闭集＋fail-closed 不松动。"""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="f91-rec-"))
        self.config = pinned_config(self.tmp)

    def test_record_named_with_closed_reason_set(self):
        result = legal_entry.call(
            "abstain.record",
            {"abstain_id": "abs-ok", "reason": "UNKNOWN_KEY_INPUT",
             "question_text": "本案违约金应如何计算（合成问题）",
             "missing_inputs": ["as_of 时点"]},
            self.config)
        self.assertEqual(result["reason"], "UNKNOWN_KEY_INPUT")
        self.assertTrue(result["question_digest"].strip())
        read = legal_entry.call("abstain.read", {"abstain_id": "abs-ok"},
                                self.config)
        self.assertEqual(read["events"][0]["kind"], "abstain_recorded")
        listing = legal_entry.call("abstain.list", {}, self.config)
        self.assertEqual(listing["count"], 1)

    def test_record_refuses_open_reason_and_empty_missing_inputs(self):
        with self.assertRaises(NotConnected) as caught:
            legal_entry.call(
                "abstain.record",
                {"abstain_id": "abs-1", "reason": "模型觉得不会",
                 "question_text": "q", "missing_inputs": []},
                self.config)
        self.assertIn("not_in_closed_set", str(caught.exception))
        # fail-closed 具名：缺什么要说清，不许空称阻断（08§4 不松动）
        with self.assertRaises(NotConnected) as caught:
            legal_entry.call(
                "abstain.record",
                {"abstain_id": "abs-2", "reason": "UNKNOWN_KEY_INPUT",
                 "question_text": "q", "missing_inputs": []},
                self.config)
        self.assertIn("missing_inputs_required_for_fail_closed",
                      str(caught.exception))

    def test_duplicate_abstain_id_refused(self):
        args = {"abstain_id": "abs-dup", "reason": "COVERAGE_INSUFFICIENT",
                "question_text": "q（合成）"}
        legal_entry.call("abstain.record", args, self.config)
        with self.assertRaises(NotConnected) as caught:
            legal_entry.call("abstain.record", args, self.config)
        self.assertIn("already_registered", str(caught.exception))


class RepairMustRepassGateTest(unittest.TestCase):
    """反修复主战场：覆盖证据具名＋重过闸结构断言＋fail-closed 不松动。"""

    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp(prefix="f91-repair-"))
        cls.config = pinned_config(cls.tmp)
        legal_entry.call(
            "abstain.record",
            {"abstain_id": "abs-r", "reason": "GATE_REJECTED",
             "question_text": "误拒答的题（合成）", "missing_inputs": []},
            cls.config)

    def _repair(self, corrected_text: str, abstain_id: str = "abs-r"):
        return legal_entry.call(
            "abstain.repair_submit",
            {"abstain_id": abstain_id, "corrected_text": corrected_text,
             "as_of": AS_OF},
            self.config)

    def test_good_correction_passes_same_gate_and_is_deliverable(self):
        result = self._repair(
            "依据《%s》第一条：“%s”" % (SYN_CUR, SYN_QUOTE_ART1))
        # 覆盖充分性判定绑定具名证据（每条=一次确定性核验记录）
        self.assertTrue(result["coverage"]["sufficient"])
        self.assertTrue(any(
            item["verified_scoped"] for item in result["coverage"]["evidence"]))
        self.assertIn("verify_citation", result["coverage"]["face"])
        # 重过闸：走同一 extraction_gate 路径（凭据=gate_batch/run_seq）
        self.assertEqual(result["status"], "CORRECTED_DELIVERABLE")
        self.assertTrue(result["gate_ref"]["gateBatchId"].startswith("f91-"))
        self.assertEqual(result["gate_ref"]["gateStatus"],
                         "CITATION_VERIFIED")
        self.assertIn("citation.verify", result["gate_face"])
        self.assertIsNotNone(result["deliverable"])
        # 引用级可交付；命题支持仍不代签（F87 纪律原样）
        self.assertEqual(result["deliverable"]["proposition_support"],
                         "UNSIGNED_QUOTE_EXISTENCE_IS_NOT_PROPOSITION_SUPPORT")
        # 事件链可回读（passed 在案）
        read = legal_entry.call("abstain.read", {"abstain_id": "abs-r"},
                                self.config)
        self.assertEqual(read["events"][-1]["kind"], "repair_gate_passed")

    def test_correction_with_fake_quote_still_rejected(self):
        # fail-closed 红线不松动：纠正候选伪引文 → 闸拒 → 不交付
        result = self._repair("依据《%s》第一条：“凭空捏造的引文。”" % SYN_CUR)
        self.assertEqual(result["status"], "REJECTED_GATE_FAIL_CLOSED")
        self.assertIsNone(result["deliverable"])
        self.assertEqual(result["gate_ref"]["gateStatus"], "REJECTED")
        self.assertTrue(result["rejection_reasons"])

    def test_correction_with_unknown_fail_closed_still_blocked(self):
        # 尚未施行 → 未知 fail-closed → 照样拒（纠正不豁免 fail-closed）
        result = self._repair("依据《中华人民共和国合成未来施行法》第一条")
        self.assertEqual(result["status"], "REJECTED_GATE_FAIL_CLOSED")
        self.assertEqual(result["gate_ref"]["gateStatus"], "REJECTED")

    def test_correction_without_citable_reference_refused_by_coverage(self):
        # 覆盖充分性判定绑定具名证据：零可核引用＝覆盖不足（不收自评）
        result = self._repair("这是没有引用的纠正主张，我方认为应当支持。")
        self.assertEqual(result["status"], "REPAIR_COVERAGE_INSUFFICIENT")
        self.assertIsNone(result["deliverable"])
        self.assertFalse(result["coverage"]["sufficient"])

    def test_correction_with_fabricated_title_refused_by_coverage(self):
        result = self._repair("依据《中华人民共和国合成月球管辖法》第一条")
        self.assertEqual(result["status"], "REPAIR_COVERAGE_INSUFFICIENT")
        self.assertFalse(result["coverage"]["sufficient"])

    def test_repair_cannot_carry_forged_gate_fields(self):
        with self.assertRaises(NotConnected) as caught:
            legal_entry.call(
                "abstain.repair_submit",
                {"abstain_id": "abs-r", "corrected_text": "纠正（合成）",
                 "as_of": AS_OF, "gate_status": "CITATION_VERIFIED"},
                self.config)
        self.assertIn("gate_fields_refused", str(caught.exception))

    def test_repair_requires_as_of_fail_closed(self):
        with self.assertRaises(NotConnected) as caught:
            legal_entry.call(
                "abstain.repair_submit",
                {"abstain_id": "abs-r", "corrected_text": "纠正（合成）"},
                self.config)
        self.assertIn("as_of", str(caught.exception))

    def test_unknown_abstain_id_fails_named(self):
        with self.assertRaises(NotConnected) as caught:
            self._repair("纠正（合成）", abstain_id="abs-nope")
        self.assertIn("abstain_not_registered", str(caught.exception))


class OperationalDeliveryTest(unittest.TestCase):
    """操作性任务照常交付＋『非法律结论』边界标记恒带＋法律字段具名拒。"""

    def setUp(self):
        self.config = {"abstain_state_root": str(Path(
            tempfile.mkdtemp(prefix="f91-op-")) / "abstain")}

    def test_operational_delivers_without_legal_gate_with_boundary(self):
        result = legal_entry.call(
            "operational.deliver",
            {"operation": "normalize", "text": "第一段　　有  空格。\n\n第二段。"},
            self.config)
        self.assertEqual(result["boundary_mark"], "NON_LEGAL_CONCLUSION")
        self.assertIn("非法律结论", result["boundary_note"])
        self.assertIsNone(result["gate_status"])  # 不经法律闸
        self.assertTrue(result["output_sha256"].strip())
        # 确定性：同输入两跑同字节
        again = legal_entry.call(
            "operational.deliver",
            {"operation": "normalize",
             "text": "第一段　　有  空格。\n\n第二段。"},
            self.config)
        self.assertEqual(again["output_sha256"], result["output_sha256"])
        self.assertEqual(again["output"], result["output"])

    def test_operations_closed_set_and_deterministic(self):
        for operation, text in (
                ("extract_text", "# 标题\n正文一"),
                ("split_sections", "# 甲节\n内容\n## 乙节\n内容二"),
                ("renumber", "3. 丙\n1. 甲\n2. 乙")):
            result = legal_entry.call(
                "operational.deliver", {"operation": operation, "text": text},
                self.config)
            self.assertEqual(result["operation"], operation)
            self.assertEqual(result["boundary_mark"], "NON_LEGAL_CONCLUSION")
        with self.assertRaises(NotConnected) as caught:
            legal_entry.call(
                "operational.deliver",
                {"operation": "give_legal_advice", "text": "x"},
                self.config)
        self.assertIn("not_in_closed_set", str(caught.exception))

    def test_operational_refuses_legal_conclusion_fields(self):
        # 操作交付永不冒法律结论：携带法律字段具名拒
        with self.assertRaises(NotConnected) as caught:
            legal_entry.call(
                "operational.deliver",
                {"operation": "normalize", "text": "t",
                 "extra": {"gate_status": "CITATION_VERIFIED"}},
                self.config)
        self.assertIn("legal_fields_refused", str(caught.exception))
        with self.assertRaises(NotConnected):
            legal_entry.call(
                "operational.deliver",
                {"operation": "normalize", "text": "t",
                 "extra": {"legal_conclusion": "胜诉"}},
                self.config)


class StructuralAssertionsTest(unittest.TestCase):
    """结构断言（AST 级）：operational 零法律闸调用；反修复零第二核验。"""

    def test_operational_path_never_imports_legal_gates(self):
        source = Path(ao.__file__).read_text(encoding="utf-8")
        tree = ast.parse(source)
        # operational_deliver 函数体内零 citation/extraction 名字调用
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) \
                    and node.name == "operational_deliver":
                names = {n.id for n in ast.walk(node)
                         if isinstance(n, ast.Name)}
                called = {n.func.id for n in ast.walk(node)
                          if isinstance(n, ast.Call)
                          and isinstance(n.func, ast.Name)}
                self.assertFalse(
                    names & {"verify_citation", "parse_citations",
                             "gate_run", "register"},
                    "operational 路径出现法律闸调用")
                self.assertFalse(
                    called & {"verify_citation", "gate_run"})
                break
        else:
            self.fail("operational_deliver 未找到")

    def test_repair_path_has_no_local_verification(self):
        # 反修复零第二核验算法：核验只经 citation_verifier/extraction_gate
        source = Path(ao.__file__).read_text(encoding="utf-8")
        self.assertIn("from citation_verifier import", source)
        self.assertIn("import extraction_gate", source)
        # 模块内没有自造的引文核验循环（核验函数名只出现于 import 行）
        tree = ast.parse(source)
        defined = {node.name for node in ast.walk(tree)
                   if isinstance(node, ast.FunctionDef)}
        self.assertNotIn("verify_citation", defined)
        self.assertNotIn("parse_citations", defined)

    def test_frozen_method_list_closed(self):
        self.assertEqual(
            legal_entry.ABSTAIN_OPERATIONAL_METHODS,
            {"abstain.record", "abstain.read", "abstain.list",
             "abstain.repair_submit", "operational.deliver"})
        with self.assertRaises(NotConnected) as caught:
            legal_entry.call("abstain.overrule", {}, {})
        self.assertIn("method_not_connected:abstain.overrule",
                      str(caught.exception))

    def test_state_root_required(self):
        with self.assertRaises(NotConnected) as caught:
            legal_entry.call("abstain.record",
                             {"abstain_id": "x", "reason": "GATE_REJECTED",
                              "question_text": "q", "missing_inputs": []},
                             {})
        self.assertIn("abstain_state_root_not_configured",
                      str(caught.exception))


if __name__ == "__main__":
    unittest.main()

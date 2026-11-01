# -*- coding: utf-8 -*-
"""F87 引文核验接抽取路径强制闸产品侧接线测试（工单 W2b-U02）。

双夹具（06 行 F87 / 工单要点）：
  (a) 合成抽取候选批次＋合成 codices 正式面（tmp CSV 树＋合成 md 载体）
      ——闸政策全状态覆盖与记账纪律主战场；
  (b) codices 本地真实数据夹具（钉定面 v1.1 文件＋真实正式目录）——
      真实取文/真实引文/真实旧版本拒绝。

全部候选文本/引文均为合成材料；唯一真实数据＝本机 codices 发布件
（只读）。钉定公开面文件缺失/漂移即响亮失败，不静默跳过。

合同要点（06 行 F87 acceptance / 17 卡）：
  独立核验服务先实现再接抽取（闸复用 citation.*，零第二核验器）；
  quote 存在不等于命题支持（proposition_support 恒不代签）；
  伪引文/旧版本拒绝；格候选不伪已核（未核状态具名 UNVERIFIED）；
  登记面无闸状态旁路；fail-closed（缺 as_of/面未钉定/漂移全响亮拒）。
"""

from __future__ import annotations

import csv
import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python"))

import legal_entry  # noqa: E402
import extraction_gate as eg  # noqa: E402
from bridge_errors import NotConnected  # noqa: E402

# 钉定公开面 v1.1（codices 分支 jusbench/w2a-u14-f70-citation @ dc0caf68e）
LCCC_PATH = Path(
    r"D:\Codex\1.法律工作区\legal-cn-core-codices工作区"
    r"\legal-cn-core-codices-repo\.local\worktrees\w2a-u14\lccc_consumer.py"
)
LCCC_SHA256 = (
    "55eea7c27e08d6b236b7ab7a83810c86ee0898c335c4668d875a492775db863a"
)
# 真实正式目录（本机发布件，只读；缺失即响亮失败——双夹具合同）
REAL_FORMAL_ROOT = Path(
    r"D:\Codex\1.法律工作区\legal-cn-core-codices工作区\legal-cn-core-codices"
)

DOC_COLUMNS = ["WJBS", "BT", "GBRQ", "SXX", "DE_01018", "SXRQ", "SHXRQ",
               "DE_01001", "DE_01021"]


def _body(date8: str, seq: str = "0001") -> str:
    # category[0:4]+agency[4:14]+date[14:22]+seq[22:26]+int[26:29]+type[29:31]
    return "0100" + "0000001001" + date8 + seq + "000" + "00"


# 合成行：现行 / 已废止(有失效日) / 已修订 / 同名新旧版(替代) / 尚未施行
SYN_DOCS = [
    ("中华人民共和国合成数据保护法", _body("20210820", "0091"), "01", "20211101", ""),
    ("中华人民共和国合成旧管理条例", _body("20150101"), "04", "20150601", "20200101"),
    ("中华人民共和国合成修订贸易法", _body("20081227"), "03", "20090101", ""),
    ("中华人民共和国合成换代测定法", _body("20050101"), "03", "20050601", ""),
    ("中华人民共和国合成换代测定法", _body("20210101"), "02", "20270101", ""),
    ("中华人民共和国合成未来施行法", _body("20260626"), "02", "20270101", ""),
]
SYN_WJBS: dict = {}


def build_synthetic_formal_root() -> Path:
    root = Path(tempfile.mkdtemp(prefix="f87-synth-"))
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
    cur = SYN_WJBS["中华人民共和国合成数据保护法@" + _body("20210820", "0091")]
    md_cur = (
        "---\nobject_type: \"legal_document\"\nidentifier: \"%s\"\n---\n\n"
        "# 中华人民共和国合成数据保护法\n\n"
        "- **第一条**\u3000\u3000为了规范合成数据处理活动，保护合成数据权益，制定本法。\n\n"
        "- **第二条**\u3000\u3000在中华人民共和国境内处理合成数据，适用本法。\n\n"
        "- **第三条**\u3000\u3000处理合成数据应当遵循合法、正当、必要原则。\n" % cur)
    (root / ("carrier_%s.md" % cur)).write_text(md_cur, encoding="utf-8")
    (root / "README.md").write_text("synthetic F87 test face\n",
                                    encoding="utf-8")
    (root / "SHA256SUMS").write_text("synthetic\n", encoding="utf-8")
    return root


SYN_CUR = "中华人民共和国合成数据保护法"
SYN_QUOTE_ART1 = "为了规范合成数据处理活动，保护合成数据权益，制定本法。"


def pinned_config(state_root: Path, formal_root: Path | None = None) -> dict:
    return {
        "codices_import_path": str(LCCC_PATH.parent),
        "codices_formal_root": str(formal_root or build_synthetic_formal_root()),
        "extraction_gate_state_root": str(state_root),
        "codices_face_sha256": LCCC_SHA256,
    }


class GatePolicySyntheticTest(unittest.TestCase):
    """闸政策全状态覆盖（合成面）：三态闭集＋理由闭集＋记账纪律。"""

    @classmethod
    def setUpClass(cls):
        cls.state = Path(tempfile.mkdtemp(prefix="f87-gate-state-"))
        cls.config = pinned_config(cls.state)
        cls.candidates = [
            # 1 现行＋真引文 → 引用级过闸（命题支持仍不代签）
            {"text": "依据《%s》第一条：“%s”" % (SYN_CUR, SYN_QUOTE_ART1),
             "provenance": {"source": "material", "doc": "synth_doc_1"}},
            # 2 伪引文（全文亦无）→ REJECTED 伪引文
            {"text": "依据《%s》第一条：“凭空捏造的引文。”" % SYN_CUR,
             "provenance": {"source": "material", "doc": "synth_doc_1"}},
            # 3 张冠李戴（引文真但在第二条）→ REJECTED 误引
            {"text": "依据《%s》第一条：“在中华人民共和国境内处理合成数据，"
                     "适用本法。”" % SYN_CUR,
             "provenance": {"source": "material", "doc": "synth_doc_1"}},
            # 4 旧版本·已废止 → REJECTED 旧版本
            {"text": "依据《中华人民共和国合成旧管理条例》第五条",
             "provenance": {"source": "material", "doc": "synth_doc_1"}},
            # 5 旧版本·已修订 → REJECTED 旧版本
            {"text": "依据《中华人民共和国合成修订贸易法》第二十一条",
             "provenance": {"source": "material", "doc": "synth_doc_1"}},
            # 6 旧版本·替代（同名更新版在库）→ REJECTED 旧版本
            {"text": "依据《中华人民共和国合成换代测定法》第一条",
             "provenance": {"source": "material", "doc": "synth_doc_1"}},
            # 7 虚构标题 → REJECTED 虚构
            {"text": "依据《中华人民共和国合成月球管辖法》第一条",
             "provenance": {"source": "material", "doc": "synth_doc_1"}},
            # 8 尚未施行 → REJECTED 未知 fail-closed
            {"text": "依据《中华人民共和国合成未来施行法》第一条",
             "provenance": {"source": "material", "doc": "synth_doc_1"}},
            # 9 无引用候选 → REJECTED 无引用（不可核即不放行）
            {"text": "本案无引用的候选命题", "provenance": None},
        ]

    def _register(self, batch_id="b1"):
        return legal_entry.call(
            "extraction.register",
            {"batch_id": batch_id, "candidates": self.candidates},
            self.config)

    def test_register_names_unverified_no_gate_fields(self):
        result = self._register()
        self.assertEqual(result["registered"], len(self.candidates))
        # 未核状态具名：每候选 UNVERIFIED（在场，不缺席不伪造）
        self.assertTrue(all(
            status == "UNVERIFIED"
            for status in result["gate_status_by_candidate"].values()))
        read = legal_entry.call("extraction.candidates",
                                {"batch_id": "b1"}, self.config)
        for view, spec in zip(read["candidates"], self.candidates):
            self.assertEqual(view["gate_status"], "UNVERIFIED")
            self.assertEqual(view["proposition_support"], "PENDING_GATE")
            self.assertEqual(view["rejection_reasons"], [])
            # 出处随候选回读（抽取路径→闸→核验的链路事实）
            self.assertEqual(view["provenance"], spec["provenance"])
            # 未过闸＝无闸历史（历史只在过闸后出现，不预造空壳）
            self.assertNotIn("gate_history", view)

    def test_gate_outcomes_closed_sets_and_reasons(self):
        self._register("b2")
        gate = legal_entry.call("extraction.gate",
                                {"batch_id": "b2", "as_of": "20261015"},
                                self.config)
        want = {
            "cand_0001": ("CITATION_VERIFIED", []),
            "cand_0002": ("REJECTED", ["FABRICATED_QUOTE_NOT_IN_REAL_TEXT"]),
            "cand_0003": ("REJECTED", ["MISATTRIBUTED_QUOTE_OTHER_ARTICLE"]),
            "cand_0004": ("REJECTED", ["OLD_VERSION_ABOLISHED"]),
            "cand_0005": ("REJECTED", ["OLD_VERSION_AMENDED"]),
            "cand_0006": ("REJECTED", ["OLD_VERSION_SUPERSEDED"]),
            "cand_0007": ("REJECTED", ["FABRICATED_TITLE_LOCAL_MISS"]),
            "cand_0008": ("REJECTED", ["UNKNOWN_FAIL_CLOSED"]),
            "cand_0009": ("REJECTED", ["NO_CITATION_PARSED"]),
        }
        got = {r["candidate_id"]: (r["gate_status"],
                                   [x["reason"] for x in r["rejection_reasons"]])
               for r in gate["results"]}
        self.assertEqual(got, want)
        self.assertEqual(gate["by_gate_status"],
                         {"CITATION_VERIFIED": 1, "REJECTED": 8})
        # 闸跑元数据：核验面声明＋钉定 sha 回读
        self.assertIn("citation.verify", gate["verification_face"])
        self.assertEqual(gate["face_sha256"], LCCC_SHA256)
        # 状态闭集纪律
        for item in gate["results"]:
            self.assertIn(item["gate_status"], eg.GATE_STATUSES)
            for reason in item["rejection_reasons"]:
                self.assertIn(reason["reason"], eg.REJECTION_REASONS)

    def test_quote_existence_never_signs_proposition_support(self):
        """quote 存在不等于命题支持：最好结局也只是引用级，命题恒不代签。"""
        self._register("b3")
        legal_entry.call("extraction.gate",
                         {"batch_id": "b3", "as_of": "20261015"}, self.config)
        read = legal_entry.call("extraction.candidate",
                                {"batch_id": "b3", "candidate_id": "cand_0001"},
                                self.config)
        self.assertEqual(read["gate_status"], "CITATION_VERIFIED")
        self.assertEqual(read["proposition_support"],
                         "UNSIGNED_QUOTE_EXISTENCE_IS_NOT_PROPOSITION_SUPPORT")
        # 结构性：回读里不存在任何命题支持 PASS 形态字段
        dumped = json.dumps(read, ensure_ascii=False)
        for banned in ('"proposition_supported"', '"supported": true',
                       '"pass": true', '"proposition_pass"'):
            self.assertNotIn(banned, dumped, banned)
        # 引用级记录在场：真引文 quote_in_article=True（引用核验事实可回读）
        citation = read["gate_history"][-1]["citations"][0]
        self.assertEqual(citation["status"], "现行")
        self.assertTrue(citation["verified_scoped"])
        self.assertTrue(citation["quote_in_article"])

    def test_rejected_candidate_proposition_not_applicable(self):
        self._register("b4")
        legal_entry.call("extraction.gate",
                         {"batch_id": "b4", "as_of": "20261015"}, self.config)
        read = legal_entry.call("extraction.candidate",
                                {"batch_id": "b4", "candidate_id": "cand_0002"},
                                self.config)
        self.assertEqual(read["gate_status"], "REJECTED")
        self.assertEqual(read["proposition_support"],
                         "NOT_APPLICABLE_GATE_REJECTED")
        reason = read["rejection_reasons"][0]
        self.assertEqual(reason["reason"], "FABRICATED_QUOTE_NOT_IN_REAL_TEXT")
        self.assertEqual(reason["verifier_code"], "QUOTE_NOT_IN_REAL_TEXT")

    def test_mixed_batch_no_status_bleed(self):
        """同批好坏候选并存：一条 CITATION_VERIFIED 一条 REJECTED 不串门。"""
        self._register("b5")
        legal_entry.call("extraction.gate",
                         {"batch_id": "b5", "as_of": "20261015"}, self.config)
        read = legal_entry.call("extraction.candidates",
                                {"batch_id": "b5"}, self.config)
        by_id = {c["candidate_id"]: c for c in read["candidates"]}
        self.assertEqual(by_id["cand_0001"]["gate_status"],
                         "CITATION_VERIFIED")
        self.assertEqual(by_id["cand_0002"]["gate_status"], "REJECTED")
        self.assertEqual(by_id["cand_0004"]["gate_status"], "REJECTED")

    def test_regate_appends_history_never_erases(self):
        self._register("b6")
        first = legal_entry.call("extraction.gate",
                                 {"batch_id": "b6", "as_of": "20261015"},
                                 self.config)
        second = legal_entry.call("extraction.gate",
                                  {"batch_id": "b6", "as_of": "20261016"},
                                  self.config)
        self.assertEqual(second["run_seq"], 2)
        read = legal_entry.call("extraction.candidate",
                                {"batch_id": "b6", "candidate_id": "cand_0001"},
                                self.config)
        self.assertEqual(len(read["gate_history"]), 2)
        self.assertEqual([h["as_of"] for h in read["gate_history"]],
                         ["20261015", "20261016"])
        # 两次结论一致（同一候选同一法源事实）
        self.assertEqual(first["results"][0]["gate_status"],
                         second["results"][0]["gate_status"])

    def test_gate_parses_citations_from_candidate_text_not_fed_list(self):
        """闸自己从候选文本确定性解析引用（抽取方不能喂预制引用清单）。"""
        self._register("b7")
        legal_entry.call("extraction.gate",
                         {"batch_id": "b7", "as_of": "20261015"}, self.config)
        read = legal_entry.call("extraction.candidate",
                                {"batch_id": "b7", "candidate_id": "cand_0003"},
                                self.config)
        citation = read["gate_history"][-1]["citations"][0]
        self.assertEqual(citation["citation_text"],
                         "《%s》第一条" % SYN_CUR)


class NoBypassDisciplineTest(unittest.TestCase):
    """强制闸结构保证：登记面无闸状态旁路；未核不伪已核。"""

    def setUp(self):
        self.state = Path(tempfile.mkdtemp(prefix="f87-bypass-"))
        self.config = pinned_config(self.state)

    def test_register_refuses_forged_gate_fields(self):
        for field, value in (("gate_status", "CITATION_VERIFIED"),
                             ("verified", True),
                             ("verified_scoped", True),
                             ("citation_records", []),
                             ("proposition_support", "SUPPORTED"),
                             ("rejection_reasons", [])):
            with self.assertRaises(NotConnected) as ctx:
                legal_entry.call("extraction.register", {
                    "batch_id": "forge",
                    "candidates": [{"text": "依据《甲法》第一条",
                                    field: value}]}, self.config)
            self.assertEqual(
                str(ctx.exception),
                "extraction_register_gate_fields_refused:" + field)

    def test_ungated_batch_stays_unverified_in_readback(self):
        legal_entry.call("extraction.register", {
            "batch_id": "never-gated",
            "candidates": [{"text": "依据《%s》第一条：“%s”" % (
                SYN_CUR, SYN_QUOTE_ART1)}]}, self.config)
        read = legal_entry.call("extraction.candidates",
                                {"batch_id": "never-gated"}, self.config)
        self.assertEqual(read["gate_runs"], 0)
        for view in read["candidates"]:
            self.assertEqual(view["gate_status"], "UNVERIFIED")
            self.assertEqual(view["proposition_support"], "PENDING_GATE")
        single = legal_entry.call("extraction.candidate", {
            "batch_id": "never-gated", "candidate_id": "cand_0001"},
            self.config)
        self.assertEqual(single["gate_status"], "UNVERIFIED")

    def test_no_method_can_set_verified_directly(self):
        """冻结方法组闭集外（含任何「标已核」形态）一律 not connected。"""
        for method in ("extraction.mark_verified", "extraction.verify",
                       "extraction.approve", "extraction.gate_override"):
            with self.assertRaises(NotConnected) as ctx:
                legal_entry.call(method, {"batch_id": "x"}, self.config)
            self.assertIn("method_not_connected", str(ctx.exception))


class FailClosedWiringTest(unittest.TestCase):
    """fail-closed：缺 as_of/面未钉定/漂移/未知面/坏参数全响亮拒。"""

    def setUp(self):
        self.state = Path(tempfile.mkdtemp(prefix="f87-failclosed-"))
        self._seq = 0

    def _registered_config(self, **overrides):
        """登记一个新批次（每次唯一 batch_id）并返回 (config, batch_id)。"""
        self._seq += 1
        batch_id = "fc%d" % self._seq
        config = pinned_config(self.state)
        config.update(overrides)
        config = {k: v for k, v in config.items() if v is not None}
        legal_entry.call("extraction.register", {
            "batch_id": batch_id,
            "candidates": [{"text": "依据《%s》第一条" % SYN_CUR}]}, config)
        return config, batch_id

    def test_gate_requires_as_of_fail_closed(self):
        config, batch_id = self._registered_config()
        for args in ({"batch_id": batch_id},
                     {"batch_id": batch_id, "as_of": None}):
            with self.assertRaises(NotConnected) as ctx:
                legal_entry.call("extraction.gate", args, config)
            self.assertEqual(str(ctx.exception),
                             "extraction_gate_as_of_required_fail_closed")

    def test_gate_rejects_malformed_as_of(self):
        config, batch_id = self._registered_config()
        for bad in ("2021-10-31", "2021103", 20261015, "notadate"):
            with self.assertRaises(NotConnected) as ctx:
                legal_entry.call("extraction.gate",
                                 {"batch_id": batch_id, "as_of": bad}, config)
            self.assertEqual(str(ctx.exception),
                             "extraction_gate_as_of_must_be_yyyymmdd")

    def test_gate_refuses_unpinned_face(self):
        config, batch_id = self._registered_config(codices_face_sha256=None)
        with self.assertRaises(NotConnected) as ctx:
            legal_entry.call("extraction.gate",
                             {"batch_id": batch_id, "as_of": "20261015"},
                             config)
        self.assertEqual(str(ctx.exception),
                         "extraction_gate_face_sha_pin_required")

    def test_gate_refuses_malformed_pin(self):
        for bad in ("deadbeef", "XYZ", 123):
            config, batch_id = self._registered_config(
                codices_face_sha256=bad)
            with self.assertRaises(NotConnected) as ctx:
                legal_entry.call("extraction.gate",
                                 {"batch_id": batch_id, "as_of": "20261015"},
                                 config)
            self.assertEqual(str(ctx.exception),
                             "extraction_gate_face_sha_pin_required")

    def test_face_drift_fails_loud(self):
        # 复制面文件改字节 → 钉定 sha 与在盘不符＝响亮失败（模拟漂移）
        drift_dir = Path(tempfile.mkdtemp(prefix="f87-drift-"))
        drifted = drift_dir / "lccc_consumer.py"
        drifted.write_bytes(LCCC_PATH.read_bytes() + b"\n# drift\n")
        config, batch_id = self._registered_config(
            codices_import_path=str(drift_dir))
        with self.assertRaises(NotConnected) as ctx:
            legal_entry.call("extraction.gate",
                             {"batch_id": batch_id, "as_of": "20261015"},
                             config)
        self.assertTrue(str(ctx.exception).startswith(
            "codices_face_sha256_drift:"))
        # 漂移拒后批次状态不被污染：仍 UNVERIFIED
        read = legal_entry.call("extraction.candidates",
                                {"batch_id": batch_id}, config)
        self.assertEqual(read["candidates"][0]["gate_status"], "UNVERIFIED")

    def test_gate_missing_import_path_fails_named(self):
        config, batch_id = self._registered_config(codices_import_path=None)
        with self.assertRaises(NotConnected) as ctx:
            legal_entry.call("extraction.gate",
                             {"batch_id": batch_id, "as_of": "20261015"},
                             config)
        self.assertEqual(str(ctx.exception),
                         "codices_import_path_not_configured")

    def test_state_root_required(self):
        with self.assertRaises(NotConnected) as ctx:
            legal_entry.call("extraction.register", {
                "batch_id": "x", "candidates": [
                    {"text": "依据《甲法》第一条"}]},
                {"codices_import_path": str(LCCC_PATH.parent)})
        self.assertEqual(str(ctx.exception),
                         "extraction_gate_state_root_not_configured")

    def test_unknown_batch_and_candidate_fail_named(self):
        config = pinned_config(self.state)
        with self.assertRaises(NotConnected) as ctx:
            legal_entry.call("extraction.candidates", {"batch_id": "ghost"},
                             config)
        self.assertEqual(str(ctx.exception),
                         "extraction_batch_not_registered:ghost")
        legal_entry.call("extraction.register", {
            "batch_id": "known", "candidates": [{"text": "依据《甲法》第一条"}]},
            config)
        with self.assertRaises(NotConnected) as ctx:
            legal_entry.call("extraction.candidate", {
                "batch_id": "known", "candidate_id": "cand_9999"}, config)
        self.assertEqual(str(ctx.exception),
                         "extraction_candidate_not_found:cand_9999")

    def test_duplicate_batch_and_bad_ids_fail_named(self):
        config = pinned_config(self.state)
        args = {"batch_id": "dup", "candidates": [{"text": "依据《甲法》第一条"}]}
        legal_entry.call("extraction.register", args, config)
        with self.assertRaises(NotConnected) as ctx:
            legal_entry.call("extraction.register", args, config)
        self.assertEqual(str(ctx.exception),
                         "extraction_batch_already_registered:dup")
        for bad_id in ("has space", "../escape", "x" * 65, "", None, 7):
            with self.assertRaises(NotConnected) as ctx:
                legal_entry.call("extraction.register", {
                    "batch_id": bad_id,
                    "candidates": [{"text": "依据《甲法》第一条"}]}, config)
            self.assertEqual(str(ctx.exception),
                             "extraction_batch_id_invalid")

    def test_bad_candidate_shapes_fail_named(self):
        config = pinned_config(self.state)
        for candidates in ([], "notalist", [{"text": ""},
                                            {"text": "依据《甲法》第一条"}],
                           [{"no_text": True}], [ "notadict" ],
                           [{"text": "依据《甲法》第一条",
                             "provenance": "notdict"}]):
            with self.assertRaises(NotConnected):
                legal_entry.call("extraction.register", {
                    "batch_id": "shape", "candidates": candidates}, config)

    def test_non_dict_args_rejected(self):
        config = pinned_config(self.state)
        for method in ("extraction.register", "extraction.gate",
                       "extraction.candidates", "extraction.candidate"):
            with self.assertRaises(NotConnected) as ctx:
                legal_entry.call(method, ["not", "dict"], config)
            self.assertEqual(str(ctx.exception),
                             "extraction_params_invalid")

    def test_unknown_extraction_method_not_connected(self):
        config = pinned_config(self.state)
        with self.assertRaises(NotConnected) as ctx:
            legal_entry.call("extraction.gate_all", {"batch_id": "x"},
                             config)
        self.assertIn("method_not_connected", str(ctx.exception))


class RealDataGateTest(unittest.TestCase):
    """codices 本地真实数据夹具（只读）：真实旧版本拒绝＋真引文过闸。"""

    @classmethod
    def setUpClass(cls):
        if not REAL_FORMAL_ROOT.is_dir():
            raise FileNotFoundError(
                f"real codices formal root missing at {REAL_FORMAL_ROOT} "
                "(dual-fixture contract: synthetic + real local data)")
        cls.state = Path(tempfile.mkdtemp(prefix="f87-real-"))
        cls.config = pinned_config(cls.state, REAL_FORMAL_ROOT)
        cls.candidates = [
            {"text": "依据《中华人民共和国个人信息保护法》第一条："
                     "“为了保护个人信息权益，规范个人信息处理活动，促进"
                     "个人信息合理利用，根据宪法，制定本法。”",
             "provenance": {"source": "material", "doc": "real_doc"}},
            {"text": "依据《中华人民共和国个人信息保护法》第一条："
                     "“嫦娥资源归属月球共同体所有。”",
             "provenance": {"source": "material", "doc": "real_doc"}},
            {"text": "依据《中华人民共和国合同法》第五条",
             "provenance": {"source": "material", "doc": "real_doc"}},
            {"text": "依据《中华人民共和国产品质量法》第二十一条",
             "provenance": {"source": "material", "doc": "real_doc"}},
            {"text": "依据《中华人民共和国商标法》第五十七条",
             "provenance": {"source": "material", "doc": "real_doc",
                            "as_of_override": "20150101"}},
        ]
        legal_entry.call("extraction.register", {
            "batch_id": "real1", "candidates": cls.candidates}, cls.config)
        # 商标法 2015 时点＝旧版本（03 版被同名更新版替代）——单列批
        legal_entry.call("extraction.register", {
            "batch_id": "real2015",
            "candidates": [cls.candidates[4]]}, cls.config)
        cls.gate = legal_entry.call("extraction.gate", {
            "batch_id": "real1", "as_of": "20261015"}, cls.config)
        cls.gate_2015 = legal_entry.call("extraction.gate", {
            "batch_id": "real2015", "as_of": "20150101"}, cls.config)

    def test_real_current_quote_passes_citation_level_only(self):
        read = legal_entry.call("extraction.candidate", {
            "batch_id": "real1", "candidate_id": "cand_0001"}, self.config)
        self.assertEqual(read["gate_status"], "CITATION_VERIFIED")
        self.assertEqual(read["proposition_support"],
                         "UNSIGNED_QUOTE_EXISTENCE_IS_NOT_PROPOSITION_SUPPORT")
        citation = read["gate_history"][-1]["citations"][0]
        self.assertEqual(citation["status"], "现行")
        self.assertTrue(citation["quote_in_article"])

    def test_real_fabricated_quote_rejected(self):
        read = legal_entry.call("extraction.candidate", {
            "batch_id": "real1", "candidate_id": "cand_0002"}, self.config)
        self.assertEqual(read["gate_status"], "REJECTED")
        self.assertEqual(read["rejection_reasons"][0]["reason"],
                         "FABRICATED_QUOTE_NOT_IN_REAL_TEXT")

    def test_real_old_versions_rejected(self):
        abolished = legal_entry.call("extraction.candidate", {
            "batch_id": "real1", "candidate_id": "cand_0003"}, self.config)
        self.assertEqual(abolished["gate_status"], "REJECTED")
        self.assertEqual(abolished["rejection_reasons"][0]["reason"],
                         "OLD_VERSION_ABOLISHED")  # 合同法 已废止
        amended = legal_entry.call("extraction.candidate", {
            "batch_id": "real1", "candidate_id": "cand_0004"}, self.config)
        self.assertEqual(amended["rejection_reasons"][0]["reason"],
                         "OLD_VERSION_AMENDED")  # 产品质量法 已修订

    def test_real_trademark_2015_superseded_rejected(self):
        read = legal_entry.call("extraction.candidate", {
            "batch_id": "real2015", "candidate_id": "cand_0001"},
            self.config)
        self.assertEqual(read["gate_status"], "REJECTED")
        self.assertEqual(read["rejection_reasons"][0]["reason"],
                         "OLD_VERSION_SUPERSEDED")  # 商标法@2015 替代


class FrozenFaceAndModuleDisciplineTest(unittest.TestCase):
    def test_pinned_v11_face_present_and_unchanged(self):
        if not LCCC_PATH.is_file():
            raise FileNotFoundError(
                f"pinned frozen face missing at {LCCC_PATH} (E22 freeze "
                "v1.1, codices branch jusbench/w2a-u14-f70-citation @ "
                "dc0caf68e) — F87 must consume the frozen face, no "
                "substitute allowed")
        digest = hashlib.sha256(LCCC_PATH.read_bytes()).hexdigest()
        self.assertEqual(digest, LCCC_SHA256)

    def test_gate_module_no_network_no_direct_formal_reads(self):
        """闸模块纪律：零网络；法源只经 citation_verifier（不直读正式表）。"""
        import ast
        source = (ROOT / "python" / "extraction_gate.py").read_text(
            encoding="utf-8")
        tree = ast.parse(source)
        network = {"urllib", "requests", "socket", "http", "httpx", "aiohttp"}
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom):
                names = [node.module or ""]
            else:
                names = []
            for name in names:
                self.assertNotIn(name.split(".")[0], network,
                                 "network import: " + name)
        # 不直读正式表：正式表文件名不出现（消费只能经 citation_verifier
        # →E22 冻结面）；csv 模块不导入（无自行解析正式面）
        self.assertNotIn("legal_documents.csv", source)
        self.assertNotIn("legal_relations.csv", source)
        self.assertNotIn("import csv", source)

    def test_gate_module_is_policy_only_no_second_verifier(self):
        """闸零第二核验器：不定义任何效力/取文/引文判定函数，只做映射。"""
        import ast
        source = (ROOT / "python" / "extraction_gate.py").read_text(
            encoding="utf-8")
        tree = ast.parse(source)
        forbidden = {"resolve_effectivity", "document_markdown",
                     "read_markdown_text", "find_by_title",
                     "split_articles", "_support_check", "_status_from_gate"}
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                self.assertNotIn(node.name, forbidden)
        self.assertIn("verify_citation", source)  # 唯一核验权威被真调用


if __name__ == "__main__":
    unittest.main()

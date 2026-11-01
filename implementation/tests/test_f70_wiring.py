# -*- coding: utf-8 -*-
"""F70 引证核验器产品侧接线测试（工单 W2a-U14）。

双夹具（06 行 F70 / 工单要点）：
  (a) 合成引用文档＋合成 codices 正式面（tmp CSV 树＋合成 md 载体）——
      全状态覆盖与记账纪律的主战场；
  (b) codices 本地真实数据夹具（钉定面 v1.1 文件＋真实正式目录）——
      真实取文定位/真实引文支持核验/真实多版本定版。

全部引用文档/引文均为合成材料；唯一真实数据＝本机 codices 发布件
（只读）。钉定公开面文件缺失/漂移即响亮失败，不静默跳过。

合同要点（06 行 F70 acceptance / 17 卡）：
  单引用核验＋全文所有引用逐条范围记账；每引用独立状态
  （现行/已修订/已废止/替代/虚构/失效/误引）；虚构/失效/误引不能标
  全核；无文档级 PASS 笼统结论；引用解析确定性（正则＋状态机）；
  版本/效力经 W2a-U13 statute 面；标题定位经冻结面 find_by_title。
"""

from __future__ import annotations

import csv
import hashlib
import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python"))

import legal_entry  # noqa: E402
import citation_verifier as cv  # noqa: E402
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


# 合成行：现行 / 已废止(有/无失效日) / 已修改 / 同名新旧版(替代形态) /
# 尚未施行 / 无 GB 码
SYN_DOCS = [
    ("中华人民共和国合成数据保护法", _body("20210820", "0091"), "01", "20211101", ""),
    ("中华人民共和国合成旧管理条例", _body("20150101"), "04", "20150601", "20200101"),
    ("中华人民共和国合成无期废止法", _body("20170101"), "04", "20170601", ""),
    ("中华人民共和国合成修订贸易法", _body("20081227"), "03", "20090101", ""),
    ("中华人民共和国合成换代测定法", _body("20050101"), "03", "20050601", ""),
    ("中华人民共和国合成换代测定法", _body("20210101"), "02", "20270101", ""),
    ("中华人民共和国合成未来施行法", _body("20260626"), "02", "20270101", ""),
    ("中华人民共和国合成无码条例", _body("20200101"), "01", "20200601", ""),
]
SYN_WJBS = {}
SYN_MD = {}


def build_synthetic_formal_root() -> Path:
    root = Path(tempfile.mkdtemp(prefix="f70-synth-"))
    with (root / "legal_documents.csv").open("w", encoding="utf-8-sig",
                                             newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(DOC_COLUMNS)
        for title, body, sxx, sxrq, shxrq in SYN_DOCS:
            use_code = "0" if title.startswith("中华人民共和国合成无码") else body
            wjbs = "1.2.156.3005.6-" + body
            SYN_WJBS[title + "@" + body] = wjbs
            writer.writerow([wjbs, title, body[14:22], sxx, sxx, sxrq, shxrq,
                             use_code, "国家法律法规数据库"])
    for name in ("legal_contents.csv", "legal_relations.csv",
                 "legal_sources.csv", "cases.csv", "case_legal_references.csv",
                 "case_holdings.csv", "practice_references.csv"):
        (root / name).write_text("WJBS\n", encoding="utf-8-sig")
    # 合成 md 载体：现行法全文（三条）＋旧换代法全文（两条）
    cur = SYN_WJBS["中华人民共和国合成数据保护法@" + _body("20210820", "0091")]
    old = SYN_WJBS["中华人民共和国合成换代测定法@" + _body("20050101")]
    md_cur = (
        "---\nobject_type: \"legal_document\"\nidentifier: \"%s\"\n---\n\n"
        "# 中华人民共和国合成数据保护法\n\n"
        "- **第一条**\u3000\u3000为了规范合成数据处理活动，保护合成数据权益，制定本法。\n\n"
        "- **第二条**\u3000\u3000在中华人民共和国境内处理合成数据，适用本法。\n\n"
        "  境外处理合成数据，有下列情形之一的，也适用本法：\n\n"
        "  - （一）以向境内提供产品或者服务为目的；\n\n"
        "- **第三条**\u3000\u3000处理合成数据应当遵循合法、正当、必要原则。\n\n"
        "## 第一章\u3000总则附则\n" % cur)
    md_old = (
        "---\nidentifier: \"%s\"\n---\n\n"
        "第一条\u3000旧版合成换代测定法总则条款。\n\n"
        "第二条\u3000旧版合成换代测定法附则条款。\n" % old)
    for wjbs, text in ((cur, md_cur), (old, md_old)):
        SYN_MD[wjbs] = text
        # 载体文件名须匹配冻结面 suffix 索引模式 *_<WJBS>.md
        (root / ("carrier_%s.md" % wjbs)).write_text(text, encoding="utf-8")
    (root / "README.md").write_text("synthetic F70 test face\n",
                                    encoding="utf-8")
    (root / "SHA256SUMS").write_text("synthetic\n", encoding="utf-8")
    return root


def load_lccc_module():
    if not LCCC_PATH.is_file():
        raise FileNotFoundError(
            f"pinned frozen face missing at {LCCC_PATH} (E22 freeze v1.1, "
            "codices branch jusbench/w2a-u14-f70-citation @ dc0caf68e) — "
            "F70 must consume the frozen face, no substitute allowed")
    digest = hashlib.sha256(LCCC_PATH.read_bytes()).hexdigest()
    if digest != LCCC_SHA256:
        raise AssertionError(
            f"pinned lccc_consumer.py drifted: sha256 {digest} != "
            f"{LCCC_SHA256} (face contract changed — update the pin "
            "through a codices branch, never bypass)")
    spec = importlib.util.spec_from_file_location("lccc_consumer_pin", LCCC_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class FrozenFacePinTest(unittest.TestCase):
    def test_pinned_v11_face_present_and_unchanged(self):
        module = load_lccc_module()  # 缺失/漂移即失败
        self.assertTrue(hasattr(module.LcccConsumer, "find_by_title"))

    def test_find_by_title_is_exact_no_fuzzy(self):
        module = load_lccc_module()
        root = build_synthetic_formal_root()
        consumer = module.LcccConsumer(str(root))
        rows = consumer.find_by_title("中华人民共和国合成数据保护法")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["sxx"], "01")
        self.assertEqual(consumer.find_by_title("合成数据保护法"), [])
        self.assertEqual(consumer.find_by_title("不存在的法"), [])


class DeterministicParserTest(unittest.TestCase):
    """引用解析确定性（工作区约束 1）：纯正则＋状态机，无任何模型。"""

    def test_chinese_numerals_full_range(self):
        for text, want in (("一", 1), ("十", 10), ("十五", 15), ("二十", 20),
                           ("一百零一", 101), ("九十九", 99),
                           ("一千二百六十", 1260), ("二千零一", 2001)):
            self.assertEqual(cv.parse_cn_numeral(text), want, text)
        self.assertIsNone(cv.parse_cn_numeral("1"))
        self.assertIsNone(cv.parse_cn_numeral("第"))
        self.assertIsNone(cv.parse_cn_numeral(""))

    def test_parse_basic_citation_shapes(self):
        items = cv.parse_citations(
            "依据《甲法》第一条及《乙法》第二十条第三款，处理如下。")
        self.assertEqual([i["citation_text"] for i in items],
                         ["《甲法》第一条", "《乙法》第二十条第三款"])
        self.assertEqual(items[1]["article_number"], 20)
        self.assertEqual(items[1]["subrefs"], "第三款")

    def test_parse_quote_attached_to_first_article_in_sentence(self):
        items = cv.parse_citations(
            "《甲法》第一条规定：“引文内容甲。”")
        self.assertEqual(items[0]["quote"], "引文内容甲。")
        two = cv.parse_citations(
            "《甲法》第一条、第二条共同规定：“同句引文。”")
        self.assertEqual(two[0]["quote"], "同句引文。")
        self.assertIsNone(two[1]["quote"])

    def test_parse_title_only_citation(self):
        items = cv.parse_citations("根据《甲法》处理。")
        self.assertEqual(len(items), 1)
        self.assertIsNone(items[0]["article_number"])
        self.assertEqual(items[0]["citation_text"], "《甲法》")

    def test_parse_same_input_same_output_and_sorted_spans(self):
        text = "《甲法》第一条。《乙法》第二条。《甲法》第三条之一。"
        first = cv.parse_citations(text)
        for a, b in zip(first, cv.parse_citations(text)):
            self.assertEqual(a, b)
        self.assertEqual([i["span"][0] for i in first],
                         sorted(i["span"][0] for i in first))

    def test_split_articles_state_machine_on_real_carrier_format(self):
        md = (
            "---\nidentifier: \"x\"\n---\n\n"
            "## 目录\n\n- 第一章 总则\n\n"
            "- **第一条**\u3000\u3000总则条款内容。\n\n"
            "  续行内容，含子项：\n\n"
            "  - （一）子项甲；\n\n"
            "- **第二条**\u3000\u3000分则条款内容，本法第一条的引用不算条文起点。\n\n"
            "- **第三条之一**\u3000\u3000修正插条。\n")
        articles = cv.split_articles(md)
        self.assertEqual(sorted(articles), ["1", "2", "3之一"])
        self.assertIn("总则条款内容", articles["1"]["text"])
        self.assertIn("子项甲", articles["1"]["text"])
        self.assertIn("分则条款内容", articles["2"]["text"])
        self.assertIn("修正插条", articles["3之一"]["text"])


class SingleVerifySyntheticTest(unittest.TestCase):
    """单条核验（合成 codices 面）：七状态逐条覆盖。"""

    @classmethod
    def setUpClass(cls):
        cls.root = build_synthetic_formal_root()
        cls.config = {
            "codices_import_path": str(LCCC_PATH.parent),
            "codices_formal_root": str(cls.root),
        }

    def _verify(self, citation, as_of="20261015"):
        return legal_entry.call(
            "citation.verify", {"citation": citation, "as_of": as_of},
            self.config)

    def test_current_with_real_carrier_quote_verified(self):
        result = self._verify(
            "《中华人民共和国合成数据保护法》第一条规定："
            "“为了规范合成数据处理活动，保护合成数据权益，制定本法。”")
        self.assertEqual(result["status"], "现行")
        self.assertTrue(result["verified_scoped"])
        self.assertEqual(result["decision"], "ALLOWED")
        self.assertTrue(result["support"]["article_located"])
        self.assertTrue(result["support"]["quote_in_article"])
        # 引用回读：定位条文真实文本含条文号与内容
        self.assertIn("第一条", result["support"]["article_text"])
        self.assertIn("制定本法", result["support"]["article_text"])

    def test_miscited_quote_fabricated(self):
        result = self._verify(
            "《中华人民共和国合成数据保护法》第一条规定：“凭空捏造的引文。”")
        self.assertEqual(result["status"], "误引")
        self.assertFalse(result["verified_scoped"])
        self.assertEqual(result["code"], "QUOTE_NOT_IN_REAL_TEXT")
        self.assertFalse(result["support"]["quote_in_article"])
        self.assertFalse(result["support"]["quote_in_document"])

    def test_miscited_quote_in_other_article_misattribution(self):
        # 引文真实存在但属于另一条文（第二条）→ 张冠李戴式误引
        result = self._verify(
            "《中华人民共和国合成数据保护法》第一条规定："
            "“在中华人民共和国境内处理合成数据，适用本法。”")
        self.assertEqual(result["status"], "误引")
        self.assertEqual(result["code"], "QUOTE_MISATTRIBUTED")
        self.assertTrue(result["support"]["quote_in_document"])
        self.assertFalse(result["support"]["quote_in_article"])

    def test_miscited_article_number_not_in_real_text(self):
        result = self._verify("《中华人民共和国合成数据保护法》第九十九条")
        self.assertEqual(result["status"], "误引")
        self.assertEqual(result["code"], "ARTICLE_NOT_IN_REAL_TEXT")
        self.assertFalse(result["support"]["article_located"])

    def test_abolished_with_and_without_expiry(self):
        with_expiry = self._verify("《中华人民共和国合成旧管理条例》第五条")
        self.assertEqual(with_expiry["status"], "已废止")
        self.assertEqual(with_expiry["code"], "ABOLISHED_NOT_CITABLE")
        no_expiry = self._verify("《中华人民共和国合成无期废止法》第五条")
        self.assertEqual(no_expiry["status"], "已废止")
        self.assertFalse(no_expiry["verified_scoped"])

    def test_amended(self):
        result = self._verify("《中华人民共和国合成修订贸易法》第二十一条")
        self.assertEqual(result["status"], "已修订")
        self.assertEqual(result["code"], "SUPERSEDED_NOT_CITABLE")
        self.assertEqual(result["replacement"], "unknown")
        self.assertFalse(result["verified_scoped"])

    def test_superseded_when_newer_same_title_version_exists(self):
        # 旧版（03）＋同名新版（02 施行日 2027 未到）：as_of 时无 ALLOWED
        # → 定版到旧版，同名更新版本在库 → 替代
        result = self._verify("《中华人民共和国合成换代测定法》第一条",
                              as_of="20261015")
        self.assertEqual(result["status"], "替代")
        self.assertFalse(result["verified_scoped"])
        self.assertIn("legal_relations", result["replacement_reason"])

    def test_fabricated_title_local_miss_with_declared_gaps(self):
        result = self._verify("《中华人民共和国合成月球管辖法》第一条")
        self.assertEqual(result["status"], "虚构")
        self.assertEqual(result["code"], "LOCAL_FACE_TITLE_MISS")
        self.assertFalse(result["verified_scoped"])
        # 付费/web 缺口具名声明，不判全局不存在
        self.assertIn("PAID", result["degradation"]["reason"])
        self.assertEqual(result["degradation"]["self_collection"], "none")

    def test_not_yet_in_force_fails_closed_unknown(self):
        result = self._verify("《中华人民共和国合成未来施行法》第一条")
        self.assertEqual(result["status"], "未知")
        self.assertEqual(result["code"], "NOT_YET_IN_FORCE_AT_AS_OF")
        self.assertFalse(result["verified_scoped"])

    def test_missing_gb_code_fails_closed(self):
        result = self._verify("《中华人民共和国合成无码条例》第一条")
        self.assertEqual(result["status"], "未知")
        self.assertTrue(result["code"].startswith("FACE_STRUCTURAL_GAP"))

    def test_missing_as_of_fails_closed(self):
        with self.assertRaises(NotConnected) as ctx:
            legal_entry.call("citation.verify",
                             {"citation": "《甲法》第一条"}, self.config)
        self.assertEqual(str(ctx.exception),
                         "citation_as_of_required_fail_closed")

    def test_title_only_citation_scopes_to_statute_level(self):
        result = self._verify("《中华人民共和国合成数据保护法》")
        self.assertEqual(result["status"], "现行")
        self.assertTrue(result["verified_scoped"])
        self.assertIn("title_lookup:hit", result["scope"])
        self.assertFalse(result["support"]["article_located"])


class DocumentAccountingSyntheticTest(unittest.TestCase):
    """全文逐条范围记账＋无文档级 PASS＋反例三拒。"""

    @classmethod
    def setUpClass(cls):
        cls.root = build_synthetic_formal_root()
        cls.config = {
            "codices_import_path": str(LCCC_PATH.parent),
            "codices_formal_root": str(cls.root),
        }
        cls.good_doc = (
            "本案依据《中华人民共和国合成数据保护法》第一条处理："
            "“为了规范合成数据处理活动，保护合成数据权益，制定本法。”"
            "另参《中华人民共和国合成数据保护法》第二条。")
        cls.bad_doc = (
            "原告主张《中华人民共和国合成旧管理条例》第五条（已废止）。"
            "被告引用《中华人民共和国合成月球管辖法》第一条（虚构）。"
            "法院认为《中华人民共和国合成数据保护法》第九十九条（条文不存在）"
            "与《中华人民共和国合成数据保护法》第三条：“处理合成数据应当遵循"
            "合法、正当、必要原则。”（现行真引文）应当一并考量。")

    def _account(self, text, as_of="20261015"):
        return legal_entry.call("citation.verify_document",
                                {"text": text, "as_of": as_of}, self.config)

    def test_per_citation_records_with_independent_status(self):
        result = self._account(self.bad_doc)
        by_text = {r["citation_text"]: r for r in result["citations"]}
        self.assertEqual(
            by_text["《中华人民共和国合成旧管理条例》第五条"]["status"], "已废止")
        self.assertEqual(
            by_text["《中华人民共和国合成月球管辖法》第一条"]["status"], "虚构")
        self.assertEqual(
            by_text["《中华人民共和国合成数据保护法》第九十九条"]["status"], "误引")
        self.assertEqual(
            by_text["《中华人民共和国合成数据保护法》第三条"]["status"], "现行")
        # 同文档内同一法条状态互不覆盖：第三条现行、第九十九条误引并存
        self.assertEqual(result["summary"]["by_status"],
                         {"已废止": 1, "虚构": 1, "误引": 1, "现行": 1})

    def test_counterexamples_never_fully_verified(self):
        result = self._account(self.bad_doc)
        bad = [r for r in result["citations"]
               if r["status"] in cv.NEVER_FULLY_VERIFIED]
        self.assertEqual(len(bad), 2)  # 虚构＋误引（已废止另计）
        for record in result["citations"]:
            if record["status"] in cv.NEVER_FULLY_VERIFIED:
                self.assertFalse(record["verified_scoped"])

    def test_no_document_level_pass_verdict_ever(self):
        for text in (self.good_doc, self.bad_doc, "本文无任何引用。"):
            result = self._account(text)
            dumped = json.dumps(result, ensure_ascii=False)
            for banned in ('"document_pass"', '"all_verified"', '"pass": true',
                           '"overall"', '"verified_document"'):
                self.assertNotIn(banned, dumped, banned)
            self.assertIn(result["summary"]["accounting"],
                          "per_citation_scoped")
            # 好文档也不出笼统结论：逐条记录＋计数即全部产出
            self.assertEqual(
                len(result["citations"]), result["summary"]["total"])

    def test_empty_document_yields_zero_citations_not_error(self):
        result = self._account("本文无任何引用。")
        self.assertEqual(result["summary"]["total"], 0)
        self.assertEqual(result["summary"]["by_status"], {})

    def test_spans_cover_all_citations_in_order(self):
        result = self._account(self.bad_doc)
        spans = [r["span"] for r in result["citations"]]
        self.assertEqual(spans, sorted(spans))
        for record in result["citations"]:
            start, end = record["span"]
            self.assertTrue(self.bad_doc[start:start + 20].startswith("《"))


class RealDataFixtureTest(unittest.TestCase):
    """codices 本地真实数据夹具（只读）：真实取文＋真实引文＋真实多版本。"""

    @classmethod
    def setUpClass(cls):
        if not REAL_FORMAL_ROOT.is_dir():
            raise FileNotFoundError(
                f"real codices formal root missing at {REAL_FORMAL_ROOT} "
                "(dual-fixture contract: synthetic + real local data)")
        cls.config = {
            "codices_import_path": str(LCCC_PATH.parent),
            "codices_formal_root": str(REAL_FORMAL_ROOT),
        }

    def test_real_pipl_article_one_real_quote_verified(self):
        result = legal_entry.call("citation.verify", {
            "citation": "《中华人民共和国个人信息保护法》第一条规定："
                        "“为了保护个人信息权益，规范个人信息处理活动，促进"
                        "个人信息合理利用，根据宪法，制定本法。”",
            "as_of": "20261015"}, self.config)
        self.assertEqual(result["status"], "现行")
        self.assertTrue(result["verified_scoped"])
        self.assertTrue(result["support"]["article_located"])
        self.assertTrue(result["support"]["quote_in_article"])
        self.assertIn("为了保护个人信息权益",
                      result["support"]["article_text"])

    def test_real_pipl_fabricated_quote_miscited(self):
        result = legal_entry.call("citation.verify", {
            "citation": "《中华人民共和国个人信息保护法》第一条规定："
                        "“自然人的人身自由不受侵犯。”",
            "as_of": "20261015"}, self.config)
        self.assertEqual(result["status"], "误引")
        self.assertEqual(result["code"], "QUOTE_NOT_IN_REAL_TEXT")

    def test_real_trademark_multi_version_superseded_at_2015(self):
        # 商标法三版本（03/2014、01/2019、02/2027 未施行）：as_of=2015 无
        # ALLOWED → 定版 03 版，同名更新版在库 → 替代
        result = legal_entry.call("citation.verify", {
            "citation": "《中华人民共和国商标法》第五十七条",
            "as_of": "20150101"}, self.config)
        self.assertEqual(result["status"], "替代")

    def test_real_trademark_current_version_at_2026(self):
        result = legal_entry.call("citation.verify", {
            "citation": "《中华人民共和国商标法》第一条",
            "as_of": "20261015"}, self.config)
        self.assertEqual(result["status"], "现行")


class FailClosedWiringTest(unittest.TestCase):
    def test_verify_without_config_fails_named(self):
        with self.assertRaises(NotConnected) as ctx:
            legal_entry.call("citation.verify",
                             {"citation": "《甲法》第一条", "as_of": "20261015"},
                             {})
        self.assertEqual(str(ctx.exception),
                         "codices_import_path_not_configured")

    def test_unknown_citation_method_not_connected(self):
        with self.assertRaises(NotConnected) as ctx:
            legal_entry.call("citation.check", {}, self._config())
        self.assertIn("method_not_connected", str(ctx.exception))

    def test_verify_requires_exactly_one_citation(self):
        with self.assertRaises(NotConnected) as ctx:
            legal_entry.call("citation.verify",
                             {"citation": "《甲法》第一条与《乙法》第二条",
                              "as_of": "20261015"}, self._config())
        self.assertIn("citation_exactly_one_expected_got:2",
                      str(ctx.exception))
        with self.assertRaises(NotConnected) as ctx:
            legal_entry.call("citation.verify",
                             {"citation": "本句没有引用", "as_of": "20261015"},
                             self._config())
        self.assertIn("citation_exactly_one_expected_got:0",
                      str(ctx.exception))

    def test_malformed_as_of_rejected(self):
        for bad in ("2021-10-31", "2021103", 20261015):
            with self.assertRaises(NotConnected) as ctx:
                legal_entry.call("citation.verify",
                                 {"citation": "《甲法》第一条", "as_of": bad},
                                 self._config())
            self.assertEqual(str(ctx.exception),
                             "citation_as_of_must_be_yyyymmdd")
        # 缺 as_of（None/不传）＝时点缺失 fail-closed 具名码（同 F69 纪律）
        for args in ({"citation": "《甲法》第一条", "as_of": None},
                     {"citation": "《甲法》第一条"}):
            with self.assertRaises(NotConnected) as ctx:
                legal_entry.call("citation.verify", args, self._config())
            self.assertEqual(str(ctx.exception),
                             "citation_as_of_required_fail_closed")

    def test_non_dict_args_rejected(self):
        with self.assertRaises(NotConnected) as ctx:
            legal_entry.call("citation.parse", ["not", "dict"], self._config())
        self.assertEqual(str(ctx.exception), "citation_params_invalid")

    def test_document_requires_text_and_as_of(self):
        for args in ({}, {"text": "《甲法》第一条"}, {"as_of": "20261015"},
                     {"text": "", "as_of": "20261015"}):
            with self.assertRaises(NotConnected):
                legal_entry.call("citation.verify_document", args,
                                 self._config())

    @staticmethod
    def _config():
        return {
            "codices_import_path": str(LCCC_PATH.parent),
            "codices_formal_root": str(build_synthetic_formal_root()),
        }


if __name__ == "__main__":
    unittest.main()

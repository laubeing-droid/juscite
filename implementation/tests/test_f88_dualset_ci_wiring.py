# -*- coding: utf-8 -*-
"""F88 可答/应拒双集合评估＋六指标 CI 门接线测试（工单 W2b-U03）。

夹具（全合成红线）：tools/e12_corpus_gen.py --citations 产物——
合成 codices 正式面（codices_face/ 十文件＋合成 md 载体）＋adversarial
黄金集（可答 12＋应拒 15，标签手钉，seed 钉定 20261016）。标题全部含
「合成」；正文全部手钉虚构；无任何真实法源/案件材料。

合同要点（06 行 F88 acceptance / 17 卡）：
  可答覆盖正确性和应拒正确拒绝共同报告分母；永远拒答不通过；核验器
  统计不冒独立幻觉率；保原六指标 CI 门（judicex gold_runner 阈值表
  逐名适配，阈值原样）；双集合不替删原指标。消费 F70 同源核验面
（citation_verifier 冻结方法路径），不复制第二权威。
"""

from __future__ import annotations

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
import f88_dualset_ci as f88  # noqa: E402
from bridge_errors import NotConnected  # noqa: E402

# 钉定公开面 v1.1（与 F70 同 pin：codices 分支 jusbench/w2a-u14-f70-citation）
LCCC_PATH = Path(
    r"D:\Codex\1.法律工作区\legal-cn-core-codices工作区"
    r"\legal-cn-core-codices-repo\.local\worktrees\w2a-u14\lccc_consumer.py"
)
LCCC_SHA256 = (
    "55eea7c27e08d6b236b7ab7a83810c86ee0898c335c4668d875a492775db863a"
)
F88_SEED = 20261016


def _load_generator():
    spec = importlib.util.spec_from_file_location(
        "e12_corpus_gen_f88", ROOT.parent / "tools" / "e12_corpus_gen.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_GEN = _load_generator()


def build_golden(seed: int = F88_SEED) -> Path:
    out = Path(tempfile.mkdtemp(prefix="f88-golden-"))
    _GEN.build_citations(out, seed)
    return out


class GoldenSetFixtureTest(unittest.TestCase):
    """黄金集夹具：确定性、双集合分母、全合成。"""

    @classmethod
    def setUpClass(cls):
        cls.dir = build_golden()
        cls.golden = json.loads(
            (cls.dir / "f88_golden_set.json").read_text(encoding="utf-8-sig"))

    def test_schema_and_dualset_denominators(self):
        self.assertEqual(self.golden["schema"],
                         "juscite-f88-citations-golden/1")
        counts = self.golden["counts"]
        self.assertEqual(counts["answerable"], 12)
        self.assertEqual(counts["refuse"], 15)
        self.assertEqual(counts["common"], counts["answerable"]
                         + counts["refuse"])
        self.assertEqual(len(self.golden["items"]), counts["common"])
        ids = [item["id"] for item in self.golden["items"]]
        self.assertEqual(len(ids), len(set(ids)))

    def test_same_seed_same_bytes(self):
        other = build_golden()
        digest_names = ("f88_citations_digest.txt", "f88_golden_set.json")
        for name in digest_names:
            self.assertEqual(
                (self.dir / name).read_bytes(),
                (other / name).read_bytes(), name)
        self.assertEqual(
            (self.dir / "f88_citations_digest.txt").read_text(),
            (other / "f88_citations_digest.txt").read_text())

    def test_all_synthetic_titles(self):
        # 全合成红线：合成面标题全部含「合成」；虚构标题不在合成面
        for statute in self.golden["statutes"]:
            self.assertIn("合成", statute["title"])
        face_titles = {s["title"] for s in self.golden["statutes"]}
        for fab in self.golden["fabricated_titles"]:
            self.assertNotIn(fab, face_titles)
            self.assertIn("合成", fab)
        # as_of 钉定常量（非今日函数）
        self.assertRegex(self.golden["fixed_as_of"], r"^\d{8}$")

    def test_pinned_frozen_face_unchanged(self):
        digest = hashlib.sha256(LCCC_PATH.read_bytes()).hexdigest()
        self.assertEqual(digest, LCCC_SHA256)


class RealEvaluationTest(unittest.TestCase):
    """真跑（F70 同源核验面）：六指标＋双集合全过门。"""

    @classmethod
    def setUpClass(cls):
        cls.dir = build_golden()
        cls.golden_path = str(cls.dir / "f88_golden_set.json")
        cls.config = {
            "codices_import_path": str(LCCC_PATH.parent),
            "codices_formal_root": str(cls.dir / "codices_face"),
        }
        cls.report = legal_entry.call(
            "f88.evaluate", {"golden_path": cls.golden_path}, cls.config)

    def test_gate_passes_with_all_conditions(self):
        gate = self.report["gate"]
        self.assertTrue(gate["passed"])
        self.assertEqual(gate["exit_code"], 0)
        self.assertEqual(gate["failures"], [])

    def test_six_metrics_values_and_thresholds(self):
        six = self.report["six_metrics"]
        self.assertEqual(
            set(six),
            {"domain_route_accuracy", "hallucination_rate",
             "citation_accuracy", "false_citation_rate",
             "excerpt_recall", "status_accuracy"})
        want = {"domain_route_accuracy": 1.0, "hallucination_rate": 0.0,
                "citation_accuracy": 1.0, "false_citation_rate": 0.0,
                "excerpt_recall": 1.0, "status_accuracy": 1.0}
        for name, value in want.items():
            self.assertEqual(six[name]["value"], value, name)
            self.assertTrue(six[name]["pass"], name)
            # 原阈值原样保留（judicex gold_runner 阈值表）
            self.assertIn(six[name]["threshold"],
                          (0.90, 0.10, 0.80, 0.05, 0.60), name)

    def test_dualset_rates_with_common_denominators(self):
        dual = self.report["dualset"]
        coverage = dual["answerable_coverage_correct"]
        rejection = dual["refuse_correct_rejection"]
        self.assertEqual(
            (coverage["numerator"], coverage["denominator"]), (12, 12))
        self.assertEqual(
            (rejection["numerator"], rejection["denominator"]), (15, 15))
        # 共同分母：双集合合计同时给出（共同报告分母合同）
        self.assertEqual(coverage["common_denominator"], 27)
        self.assertEqual(rejection["common_denominator"], 27)
        self.assertEqual(dual["denominators"],
                         {"answerable_set": 12, "refuse_set": 15,
                          "common": 27})

    def test_hallucination_basis_is_golden_labels(self):
        halluc = self.report["six_metrics"]["hallucination_rate"]
        self.assertEqual(halluc["basis"],
                         "golden_labels_only_verifier_self_stats_ignored")
        # 分母＝被肯定断言数（12，全落在可答集），非核验器自报任何字段
        self.assertEqual((halluc["numerator"], halluc["denominator"]),
                         (0, 12))

    def test_mean_confidence_excluded_named_not_silent(self):
        excluded = self.report["excluded_from_source_table"]
        self.assertIn("mean_confidence", excluded)
        self.assertNotIn("mean_confidence", self.report["six_metrics"])

    def test_runner_consumes_f70_same_source_face(self):
        self.assertEqual(self.report["runner"],
                         "real:citation_verifier(F70 同源核验面)")

    def test_wilson_ci_reported_for_every_metric(self):
        for name, entry in self.report["six_metrics"].items():
            ci = entry["ci95_wilson"]
            self.assertEqual(len(ci), 2, name)
            self.assertLessEqual(ci[0], entry["value"] + 1e-9, name)
            self.assertGreaterEqual(ci[1], entry["value"] - 1e-9, name)
        for name in ("answerable_coverage_correct",
                     "refuse_correct_rejection"):
            self.assertIn("ci95_wilson", self.report["dualset"][name])


class ControlsTest(unittest.TestCase):
    """adversarial 控制组：永远拒答不通过；全答也不通过。"""

    @classmethod
    def setUpClass(cls):
        cls.dir = build_golden()
        cls.golden_path = str(cls.dir / "f88_golden_set.json")
        cls.config = {
            "codices_import_path": str(LCCC_PATH.parent),
            "codices_formal_root": str(cls.dir / "codices_face"),
        }

    def _control(self, control):
        return legal_entry.call(
            "f88.control_evaluate",
            {"golden_path": self.golden_path, "control": control},
            self.config)

    def test_refuse_all_fails_gate(self):
        report = self._control("refuse_all")
        self.assertFalse(report["gate"]["passed"])
        self.assertEqual(report["gate"]["exit_code"], 1)
        # 永远拒答：可答覆盖正确率=0（共同分母 27 全军覆没）
        coverage = report["dualset"]["answerable_coverage_correct"]
        self.assertEqual(coverage["value"], 0.0)
        self.assertEqual((coverage["numerator"], coverage["denominator"]),
                         (0, 12))
        self.assertEqual(coverage["common_denominator"], 27)
        self.assertIn("answerable_coverage_correct", report["gate"]["failures"])
        self.assertIn("status_accuracy", report["gate"]["failures"])

    def test_answer_all_fails_gate(self):
        report = self._control("answer_all")
        self.assertFalse(report["gate"]["passed"])
        self.assertEqual(report["gate"]["exit_code"], 1)
        # 全答：应拒集被全肯定→假断言率/假引率/状态准确率全面崩
        halluc = report["six_metrics"]["hallucination_rate"]
        self.assertEqual((halluc["numerator"], halluc["denominator"]),
                         (15, 27))
        self.assertGreater(halluc["value"], 0.10)
        false_cit = report["six_metrics"]["false_citation_rate"]
        self.assertGreater(false_cit["value"], 0.05)
        self.assertIn("refuse_correct_rejection", report["gate"]["failures"])

    def test_verifier_self_stats_never_masquerade_as_hallucination(self):
        """核验器统计不冒独立幻觉率：诱饵自报 0.0，评估照实报 15/27。"""
        report = self._control("answer_all")
        decoy = [record for record in report.get("by_item", [])]
        self.assertTrue(decoy)  # 报告结构健全
        halluc = report["six_metrics"]["hallucination_rate"]
        self.assertNotEqual(halluc["value"], 0.0)
        self.assertEqual((halluc["numerator"], halluc["denominator"]),
                         (15, 27))
        self.assertAlmostEqual(halluc["value"], 15 / 27, places=5)
        # 评估入口对自带诱饵的记录重算仍照实（直接复核 evaluate_records）
        golden = f88.load_golden_set(self.golden_path)
        records = f88.run_control(golden, "answer_all")
        decoys = [r.get("self_reported_hallucination_rate") for r in records]
        self.assertTrue(all(d == 0.0 for d in decoys))  # 诱饵确实在
        recheck = f88.evaluate_records(records, golden)
        recheck_halluc = recheck["six_metrics"]["hallucination_rate"]
        self.assertEqual((recheck_halluc["numerator"],
                          recheck_halluc["denominator"]), (15, 27))
        self.assertAlmostEqual(recheck_halluc["value"], 15 / 27, places=5)


class WilsonCITest(unittest.TestCase):
    """Wilson 95% 区间确定性数学（已知值钉定）。"""

    def test_known_values(self):
        # 27/27 与 0/12（真跑实测值的区间形状钉定）
        lo, hi = f88.wilson_ci(27, 27)
        self.assertAlmostEqual(lo, 0.875441, places=5)
        self.assertAlmostEqual(hi, 1.0, places=9)
        lo, hi = f88.wilson_ci(0, 12)
        self.assertAlmostEqual(lo, 0.0, places=9)
        self.assertAlmostEqual(hi, 0.242501, places=5)
        # 中间值单调夹逼点估计
        for k, n in ((13, 27), (14, 27), (10, 12), (4, 4)):
            lo, hi = f88.wilson_ci(k, n)
            p = k / n
            self.assertLessEqual(lo, p + 1e-9)
            self.assertGreaterEqual(hi, p - 1e-9)

    def test_zero_denominator_wide_interval(self):
        self.assertEqual(f88.wilson_ci(0, 0), [0.0, 1.0])


class GoldenLoadFailClosedTest(unittest.TestCase):
    """黄金集装载 fail-closed：schema/缺文件/坏条目具名拒。"""

    def test_missing_path_named(self):
        for bad in (None, "", "   "):
            with self.assertRaises(NotConnected) as ctx:
                f88.load_golden_set(bad)
            self.assertEqual(str(ctx.exception), "f88_golden_path_required")

    def test_missing_file_named(self):
        with self.assertRaises(NotConnected) as ctx:
            f88.load_golden_set(str(Path(tempfile.mkdtemp()) / "nope.json"))
        self.assertTrue(str(ctx.exception)
                        .startswith("f88_golden_file_missing:"))

    def test_schema_mismatch_named(self):
        path = Path(tempfile.mkdtemp()) / "bad.json"
        path.write_text(json.dumps({"schema": "other/1", "items": []}),
                        encoding="utf-8")
        with self.assertRaises(NotConnected) as ctx:
            f88.load_golden_set(str(path))
        self.assertEqual(str(ctx.exception), "f88_golden_schema_mismatch:other/1")

    def test_duplicate_id_and_bad_set_named(self):
        base = {
            "schema": "juscite-f88-citations-golden/1",
            "items": [
                {"id": "x-1", "set": "answerable", "citation": "《甲》第一条",
                 "as_of": "20261016", "must_cite": [], "must_not_cite": [],
                 "expected_excerpts": []},
                {"id": "x-1", "set": "refuse", "citation": "《乙》第二条",
                 "as_of": "20261016", "must_cite": [], "must_not_cite": [],
                 "expected_excerpts": []},
            ],
        }
        path = Path(tempfile.mkdtemp()) / "dup.json"
        path.write_text(json.dumps(base), encoding="utf-8")
        with self.assertRaises(NotConnected) as ctx:
            f88.load_golden_set(str(path))
        self.assertEqual(str(ctx.exception), "f88_golden_item_id_duplicate:x-1")
        base["items"][1]["id"] = "x-2"
        base["items"][1]["set"] = "maybe"
        path = Path(tempfile.mkdtemp()) / "set.json"
        path.write_text(json.dumps(base), encoding="utf-8")
        with self.assertRaises(NotConnected) as ctx:
            f88.load_golden_set(str(path))
        self.assertEqual(str(ctx.exception), "f88_golden_set_invalid:x-2")


class BridgeFailClosedTest(unittest.TestCase):
    """桥面 fail-closed（legal_entry f88.* 冻结方法组）。"""

    @classmethod
    def setUpClass(cls):
        cls.dir = build_golden()
        cls.golden_path = str(cls.dir / "f88_golden_set.json")
        cls.config = {
            "codices_import_path": str(LCCC_PATH.parent),
            "codices_formal_root": str(cls.dir / "codices_face"),
        }

    def test_evaluate_without_config_fails_named(self):
        with self.assertRaises(NotConnected) as ctx:
            legal_entry.call("f88.evaluate",
                             {"golden_path": self.golden_path}, {})
        self.assertEqual(str(ctx.exception),
                         "codices_import_path_not_configured")

    def test_evaluate_missing_golden_named(self):
        with self.assertRaises(NotConnected) as ctx:
            legal_entry.call(
                "f88.evaluate",
                {"golden_path": str(self.dir / "missing.json")}, self.config)
        self.assertTrue(str(ctx.exception)
                        .startswith("f88_golden_file_missing:"))

    def test_unknown_control_named(self):
        with self.assertRaises(NotConnected) as ctx:
            legal_entry.call(
                "f88.control_evaluate",
                {"golden_path": self.golden_path, "control": "half_answer"},
                self.config)
        self.assertEqual(
            str(ctx.exception),
            "f88_control_unknown:half_answer;see:refuse_all,answer_all")

    def test_unknown_method_not_connected(self):
        with self.assertRaises(NotConnected) as ctx:
            legal_entry.call("f88.run_all", {}, self.config)
        self.assertIn("method_not_connected", str(ctx.exception))

    def test_non_dict_args_rejected(self):
        with self.assertRaises(NotConnected) as ctx:
            legal_entry.call("f88.evaluate", ["not", "dict"], self.config)
        self.assertEqual(str(ctx.exception), "f88_params_invalid")


class SixMetricPreservationTest(unittest.TestCase):
    """双集合不替删原指标（结构性）：六名字恒等于源表六行。"""

    def test_six_names_frozen(self):
        self.assertEqual(
            f88.SIX_METRIC_NAMES,
            ("domain_route_accuracy", "hallucination_rate",
             "citation_accuracy", "false_citation_rate",
             "excerpt_recall", "status_accuracy"))

    def test_thresholds_preserved_from_source_table(self):
        by_name = {spec["name"]: spec for spec in f88.SIX_METRIC_SPECS}
        self.assertEqual(by_name["domain_route_accuracy"]["threshold"], 0.90)
        self.assertEqual(by_name["hallucination_rate"]["threshold"], 0.10)
        self.assertEqual(by_name["citation_accuracy"]["threshold"], 0.80)
        self.assertEqual(by_name["false_citation_rate"]["threshold"], 0.05)
        self.assertEqual(by_name["excerpt_recall"]["threshold"], 0.60)
        self.assertEqual(by_name["status_accuracy"]["threshold"], 0.80)

    def test_gate_conditions_include_dualset_additively(self):
        golden = f88.load_golden_set(
            str(build_golden() / "f88_golden_set.json"))
        records = f88.run_control(golden, "refuse_all")
        report = f88.evaluate_records(records, golden)
        gate = f88.gate(report)
        names = {spec["name"] for spec in gate["gate_conditions"]}
        self.assertTrue(set(f88.SIX_METRIC_NAMES) <= names)
        self.assertIn("answerable_coverage_correct", names)
        self.assertIn("refuse_correct_rejection", names)


if __name__ == "__main__":
    unittest.main()

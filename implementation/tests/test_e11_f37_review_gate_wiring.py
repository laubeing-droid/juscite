"""W2a-U09 / E11+F37 资格闸桥面测试：冻结方法组、fail-closed 配置面、
资格闸/清单/分子分母/人审覆盖/三类永不回填经桥同进程闭环（anonymizer 仓
w2a-u09 分支 review_gate_service 公开面）。

真 OCR 材料化与双 profile 验收由 tools/PENDING_OWNER_e11_f37_review_gate_recon.py
承担；此处为引擎无关的桥面合同（全部合成材料）。
"""
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'python'))

_SRC = os.environ.get("JUSCITE_ANONYMIZER_SRC")
if _SRC:
    sys.path.insert(0, _SRC)
try:
    from legal_anonymizer.application import review_gate_service as _rgs
except ImportError:                                    # pragma: no cover
    _rgs = None

from legal_entry import call, NotConnected, REVIEW_GATE_METHODS

SYN_TEXT = ("合成合同：原告合某诚科技有限公司与被告北某建工集团有限公司，"
            "案号（2026）京01民初10001号，电话13700001111。")
SYN_GOLD = [
    {"surface": "合某诚科技有限公司", "class_id": "LEGAL_PERSON"},
    {"surface": "北某建工集团有限公司", "class_id": "LEGAL_PERSON"},
    {"surface": "（2026）京01民初10001号", "class_id": "case_number"},
]


def _cfg(**extra):
    config = {"anonymizer_contract": "p09/p10"}
    config.update(extra)
    return config


@unittest.skipIf(_rgs is None, "anonymizer w2a-u09 src not importable")
class E11F37BridgeContractTests(unittest.TestCase):
    def test_frozen_method_group(self):
        self.assertEqual(REVIEW_GATE_METHODS, frozenset({
            "review.qualification", "review.rule_classes",
            "review.class_coverage", "review.human_coverage",
            "review.never_backfill"}))

    def test_unknown_review_method_stays_not_connected(self):
        with self.assertRaisesRegex(NotConnected,
                                    "method_not_connected:review.explode"):
            call("review.explode", {}, _cfg())

    def test_fail_closed_config(self):
        with self.assertRaisesRegex(
                NotConnected, "anonymizer_p09_p10_not_configured"):
            call("review.qualification", {}, {})
        for method, args in (("review.human_coverage",
                              {"matter_ids": ["m"]}),
                             ("review.never_backfill",
                              {"matter_id": "m"})):
            with self.assertRaisesRegex(
                    NotConnected,
                    "review_gate_state_root_not_configured"):
                call(method, args, _cfg())

    def test_params_invalid_fail_closed(self):
        with self.assertRaisesRegex(NotConnected,
                                    "review_gate_params_invalid"):
            call("review.qualification", "not-a-dict", _cfg())
        with self.assertRaisesRegex(NotConnected,
                                    "review_gate_texts_invalid"):
            call("review.class_coverage", {"texts": "str", "gold": []}, _cfg())
        with self.assertRaisesRegex(NotConnected,
                                    "review_gate_gold_invalid"):
            call("review.class_coverage", {"texts": ["t"], "gold": "x"},
                 _cfg())
        with self.assertRaisesRegex(NotConnected,
                                    "review_gate_stack_invalid"):
            call("review.class_coverage",
                 {"texts": ["t"], "gold": [], "stack": "bogus"}, _cfg())
        with self.assertRaisesRegex(NotConnected,
                                    "review_gate_matter_ids_invalid"):
            call("review.human_coverage", {"matter_ids": [1]},
                 _cfg(review_gate_state_root="x"))
        with self.assertRaisesRegex(NotConnected,
                                    "review_gate_matter_id_required"):
            call("review.never_backfill", {}, _cfg(review_gate_state_root="x"))

    def test_qualification_gate_through_bridge(self):
        report = call("review.qualification", {}, _cfg())
        self.assertEqual(report["gate"]["status"], "REVIEW_REQUIRED")
        self.assertIn("manifest_ner_not_qualified",
                      report["gate"]["reasons"])
        self.assertTrue(report["separation"]["independent"])

    def test_rule_classes_through_bridge(self):
        inventory = call("review.rule_classes", {}, _cfg())["inventory"]
        ids = [c["class_id"] for c in inventory]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertGreaterEqual(len(ids), 14)

    def test_class_coverage_rules_vs_dictionary(self):
        rules = call("review.class_coverage",
                     {"texts": [SYN_TEXT], "gold": SYN_GOLD, "stack": "rules"},
                     _cfg())
        per = {c["class_id"]: c for c in rules["per_class"]}
        self.assertEqual(per["case_number"]["matched_count"], 1)
        self.assertEqual(per["LEGAL_PERSON"]["matched_count"], 0)
        dictionary = {"blacklist": [
            {"value": g["surface"], "type": "LEGAL_PERSON"}
            for g in SYN_GOLD if g["class_id"] == "LEGAL_PERSON"]}
        dict_cov = call("review.class_coverage",
                        {"texts": [SYN_TEXT], "gold": SYN_GOLD,
                         "stack": "rules", "dictionary": dictionary}, _cfg())
        d_per = {c["class_id"]: c for c in dict_cov["per_class"]}
        self.assertEqual(d_per["LEGAL_PERSON"]["matched_count"], 2)
        self.assertEqual(
            d_per["LEGAL_PERSON"]["matched_by_source"].get("dictionary"), 2)
        # 词典救分子，资格事实不变
        self.assertEqual(dict_cov["gate"]["status"], "REVIEW_REQUIRED")

    def test_coverage_response_never_carries_surfaces(self):
        report = call("review.class_coverage",
                      {"texts": [SYN_TEXT], "gold": SYN_GOLD, "stack": "rules"},
                      _cfg())
        blob = json.dumps(report, ensure_ascii=False)
        for surface in ("合某诚", "北某建工", "13700001111"):
            self.assertNotIn(surface, blob)

    def test_human_coverage_and_never_backfill_roundtrip(self):
        from legal_anonymizer.application.state import MatterState
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            state_root = root / "state"
            matter = "m-wiring"
            MatterState(state_root, matter).init("cn-ai-safe-v1")
            st = MatterState(state_root, matter)
            private = st.read_private()
            private["identifier_aliases"] = [
                {"kind": "id_card", "surface": "110101199003078670",
                 "alias": "证件甲"},
                {"kind": "case_number", "surface": "（2026）京01民初10001号",
                 "alias": "案号甲"}]
            st.write_private(private)
            cfg = _cfg(review_gate_state_root=str(state_root))
            hc = call("review.human_coverage",
                      {"matter_ids": [matter]}, cfg)
            self.assertEqual(hc["totals"]["review_required"], 1)
            self.assertEqual(hc["totals"]["receipt_covered"], 0)
            nb = call("review.never_backfill", {"matter_id": matter}, cfg)
            self.assertEqual(nb["never_backfill_kinds"],
                             ["id_card", "phone", "personal_address"])
            hits = nb["aliases_in_never_backfill_kinds"]
            self.assertEqual([h["kind"] for h in hits], ["id_card"])
            blob = json.dumps(nb, ensure_ascii=False)
            self.assertNotIn("110101199003078670", blob)


if __name__ == "__main__":
    unittest.main()

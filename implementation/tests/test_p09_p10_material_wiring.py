"""W1-U05 / E09 early wiring: P09/P10 material entry product bridge.

Same-process closed loop into the pinned anonymizer entries
(14-Python入口证据.csv: P09 cli.py:660 main, sha 6cb8c81e…; P10
pipeline.py:55/118 deidentify/rehydrate, sha 02012b89…). All material below
is synthetic Chinese legal text; the anonymizer repo is consumed read-only
with zero changes. Red line under test: originals and the identity mapping
never cross the bridge — no vault/map in any response, no synthetic surface
in the egress-bound sanitized form beyond what the rules layer honestly
cannot catch (person names -> REVIEW_REQUIRED, E11 deepening pending).
"""
import contextlib
import io
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'python'))
from legal_entry import call, NotConnected

SYN_TEXT = (
    "委托代理合同（合成材料）。\n"
    "委托人：周测敏（测试用合成身份，身份证11010119900307867X，"
    "电话13700009999，邮箱zhoubin@example.com）。\n"
    "代理费123,456.78元，2026年10月15日签订于北京市海淀区。\n"
)
REGEX_CATCHABLE = ("11010119900307867X", "13700009999", "zhoubin@example.com")
CONFIG = {"anonymizer_contract": "p09/p10"}


class MaterialWiringTests(unittest.TestCase):
    def test_roundtrip_closes_and_strips_structured_pii(self):
        r = call("material.roundtrip", {"text": SYN_TEXT}, CONFIG)
        self.assertTrue(r["roundtrip_restored"])
        for surface in REGEX_CATCHABLE:
            self.assertNotIn(surface, r["sanitized_text"])
        self.assertIn("PHONE_1", r["sanitized_text"])
        self.assertIn("ID_1", r["sanitized_text"])
        self.assertIn("EMAIL_1", r["sanitized_text"])

    def test_deidentify_returns_sanitized_and_counts(self):
        r = call("material.deidentify", {"text": SYN_TEXT}, CONFIG)
        self.assertEqual(r["counts"]["token_total"], 3)
        self.assertEqual(r["counts"]["categories"], {"contact": 2, "id": 1})
        self.assertNotIn("roundtrip_restored", r)

    def test_review_required_semantics_preserved_no_fake_model_face(self):
        # Rules provider preferred; local model not installed -> the model
        # layer is honestly reported as not requested (no fake model face);
        # NER qualification unmet => REVIEW_REQUIRED kept for E11.
        r = call("material.deidentify", {"text": SYN_TEXT}, CONFIG)
        self.assertTrue(r["review_required"])
        self.assertFalse(r["model_layer_requested"])
        self.assertEqual(r["provider_name"], "null")
        # person names survive the rules layer — the honest residual that
        # review_required gates (E11 human review deepening follows).
        self.assertIn("周测敏", r["sanitized_text"])

    def test_response_never_carries_mapping_or_original(self):
        for method in ("material.deidentify", "material.roundtrip"):
            r = call(method, {"text": SYN_TEXT}, CONFIG)
            flat = json.dumps(r, ensure_ascii=False)
            self.assertNotIn("vaultengine_map_version", flat)
            self.assertNotIn("surface", flat)
            self.assertNotIn("tokens", r)
            for surface in REGEX_CATCHABLE:
                self.assertNotIn(surface, flat)

    def test_unconfigured_is_not_connected(self):
        for bad in ({}, {"anonymizer_contract": None},
                    {"anonymizer_contract": "p09"}):
            with self.assertRaisesRegex(NotConnected,
                                        "anonymizer_p09_p10_not_configured"):
                call("material.deidentify", {"text": SYN_TEXT}, bad)

    def test_missing_or_empty_text_refused(self):
        for bad in (None, "", 42):
            with self.assertRaisesRegex(NotConnected,
                                        "material_text_required"):
                call("material.roundtrip", {"text": bad}, CONFIG)

    def test_bad_policy_is_config_invalid_not_fake_success(self):
        with self.assertRaisesRegex(NotConnected, "material_config_invalid"):
            call("material.deidentify",
                 {"text": SYN_TEXT, "policy": "aggressive"}, CONFIG)

    def test_standalone_rehydrate_refused_no_placeholder(self):
        # The mapping cannot persist between calls (red line), so a
        # cross-call material.rehydrate has no honest implementation and
        # must stay method_not_connected — never an empty fake success.
        with self.assertRaisesRegex(NotConnected,
                                    "method_not_connected:material.rehydrate"):
            call("material.rehydrate", {"text": SYN_TEXT}, CONFIG)

    def test_p09_cli_main_same_process_offline_face_only(self):
        # P09 entry (cli.py:660 main) wired in-process, mapping-free probe:
        # the provider face honestly reports offline-only detection; no
        # network/model backend is invented.
        from legal_anonymizer.cli import main
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf), \
                contextlib.redirect_stderr(io.StringIO()):
            rc = main(["providers"])
        self.assertEqual(rc, 0)
        face = buf.getvalue()
        self.assertIn("null", face)
        for remote in ("openai", "anthropic", "ollama", "http"):
            self.assertNotIn(remote, face.lower())


if __name__ == '__main__':
    unittest.main()

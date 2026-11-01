# -*- coding: utf-8 -*-
"""W2b-U04 / F89 acceptance: number three-classification exemption wiring.

数字三分类豁免（事实金额/规则数/否定语义；金额由 JC）——全部断言走真
产品入口（implementation/python/legal_entry.py；classify 同进程纯函数，
verify_amount 经 P01 jc.evaluate → jc-harness-local/1 真求值）。确定性
纪律：分类纯正则/状态机零模型（AST 断言＋两跑字节级同输出）；金额
Decimal/Fraction 全程（float 拒收）；歧义必须待核（UNKNOWN 不伪填）；
错误算式反例＝MISMATCH 具名拒绝；保原三分类豁免结构。材料全合成。
"""
import ast
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE / "python"))
import legal_entry
import number_classifier

sys.path.insert(0, str(HERE / "tests"))
import test_p01_jc_wiring as p01

SYNTH_DOC = (
    "《中华人民共和国民法典》第五百八十五条第二款规定当事人可以约定违约金。"
    "原告出借本金100,000元，被告已还款30,000元，尚欠70,000元。"
    "借款本金人民币伍拾万元整，年利率3.85%。"
    "违约金不得超过实际损失的百分之三十；欠款不足500元的不予受理。"
    "诉讼时效期间为三年。合同约定租期三十日。"
    "自2026年8月20日起算，罚款一千元以下。"
)


def _mentions_by_text(result):
    return {m["text"]: m for m in result["mentions"]}


class F89ClassifyTests(unittest.TestCase):
    def test_frozen_method_group(self):
        self.assertEqual(legal_entry.NUMBER_METHODS,
                         frozenset({"number.classify", "number.verify_amount"}))

    def test_three_classes_correct(self):
        result = legal_entry.call("number.classify", {"text": SYNTH_DOC},
                                  config={})
        by_text = _mentions_by_text(result)
        # 事实金额（当事人事实数）
        for text, value in (("100,000元", "100000"), ("30,000元", "30000"),
                            ("70,000元", "70000"), ("人民币伍拾万元整", "500000")):
            self.assertEqual(by_text[text]["class"], "fact_amount", text)
            self.assertEqual(by_text[text]["value"], value, text)
            self.assertEqual(by_text[text]["exemption"]["discipline"],
                             "jc_amount_evaluation", text)
        self.assertEqual(by_text["3.85%"]["class"], "fact_amount")
        self.assertEqual(by_text["3.85%"]["unit"], "percent")
        # 规则数（条文号＋诉讼时效期数）
        self.assertEqual(by_text["第五百八十五条"]["class"], "rule_number")
        self.assertEqual(by_text["第五百八十五条"]["value"], "585")
        self.assertEqual(by_text["第二款"]["class"], "rule_number")
        self.assertEqual(by_text["三年"]["class"], "rule_number")
        self.assertEqual(by_text["三年"]["unit"], "年")
        self.assertEqual(by_text["第五百八十五条"]["exemption"]["discipline"],
                         "rule_borne")
        # 否定语义（辖域有极性）
        self.assertEqual(by_text["百分之三十"]["class"], "negative_semantics")
        self.assertEqual(by_text["百分之三十"]["polarity"], "upper_bound")
        self.assertEqual(by_text["500元"]["class"], "negative_semantics")
        self.assertEqual(by_text["500元"]["polarity"], "below")
        self.assertEqual(by_text["一千元"]["class"], "negative_semantics")
        self.assertEqual(by_text["一千元"]["polarity"], "upper_bound")
        self.assertEqual(by_text["百分之三十"]["exemption"]["discipline"],
                         "polarity_bounded")
        # 计数对账
        self.assertEqual(result["counts"]["total"], len(result["mentions"]))
        for klass in ("fact_amount", "rule_number", "negative_semantics",
                      "unknown"):
            self.assertEqual(
                result["counts"][klass],
                sum(1 for m in result["mentions"] if m["class"] == klass))

    def test_unknown_pending_review_never_guessed(self):
        result = legal_entry.call(
            "number.classify",
            {"text": "合同约定租期三十日；台账编号12345；成功率30%。"},
            config={})
        by_text = _mentions_by_text(result)
        for text, reason in (("三十日", "bare_duration"),
                             ("12345", "bare_number"),
                             ("30%", "bare_percent")):
            self.assertEqual(by_text[text]["class"], "unknown", text)
            self.assertTrue(by_text[text]["pending_review"], text)
            self.assertEqual(by_text[text]["reason"], reason, text)
            self.assertIsNone(by_text[text]["exemption"]["fact_crosscheck"])
            self.assertEqual(by_text[text]["exemption"]["discipline"],
                             "pending_review")
        self.assertTrue(result["pending_review"])

    def test_mixed_and_malformed_forms_pending_not_guessed(self):
        result = legal_entry.call(
            "number.classify",
            {"text": "合计人民币12万五千元；费用合计1,00,000元。"}, config={})
        by_text = _mentions_by_text(result)
        mixed = by_text["人民币12万五千元"]
        self.assertEqual(mixed["class"], "fact_amount")  # 类可定（货币线索）
        self.assertIsNone(mixed["value"])               # 值不猜
        self.assertTrue(mixed["pending_review"])
        self.assertEqual(mixed["reason"], "amount_value_unparseable")
        malformed = by_text["1,00,000元"]
        self.assertIsNone(malformed["value"])
        self.assertTrue(malformed["pending_review"])

    def test_calendar_expressions_pending(self):
        result = legal_entry.call("number.classify",
                                  {"text": "自2026年8月20日起算。"}, config={})
        for mention in result["mentions"]:
            self.assertEqual(mention["class"], "unknown")
            self.assertEqual(mention["reason"], "calendar_expression")

    def test_deterministic_byte_identical(self):
        payload1 = legal_entry.call("number.classify", {"text": SYNTH_DOC},
                                    config={})
        payload2 = legal_entry.call("number.classify", {"text": SYNTH_DOC},
                                    config={})
        self.assertEqual(json.dumps(payload1, ensure_ascii=False,
                                    sort_keys=True),
                         json.dumps(payload2, ensure_ascii=False,
                                    sort_keys=True))
        self.assertEqual(payload1["determinism"], "regex-state-machine")
        self.assertFalse(payload1["model_involved"])

    def test_classify_module_has_no_model_network_or_random(self):
        """不把 LLM 分类叫确定性：分类面零网络/零随机/零模型导入（AST）。"""
        tree = ast.parse((HERE / "python" / "number_classifier.py")
                         .read_text(encoding="utf-8"))
        banned = {"random", "secrets", "urllib", "urllib.request", "requests",
                  "socket", "http", "http.client", "httpx", "aiohttp",
                  "openai", "anthropic", "transformers", "torch",
                  "tensorflow", "onnxruntime"}
        imported = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module.split(".")[0])
        self.assertEqual(imported & banned, set(), imported)

    def test_cn_numeral_state_machine(self):
        for text, want in (("五百八十五", 585), ("十五", 15), ("一百零五", 105),
                           ("一万五千", 15000), ("二十万", 200000),
                           ("三亿五千万", 350000000), ("壹佰", 100),
                           ("捌仟", 8000), ("两万", 20000)):
            self.assertEqual(number_classifier.parse_cn_numeral(text), want,
                             text)
        # 混用/裸单位＝不猜
        self.assertIsNone(number_classifier.parse_cn_numeral("壹佰2"))
        self.assertIsNone(number_classifier.parse_cn_numeral("万"))


class F89AmountViaJCTests(unittest.TestCase):
    """金额值经 JC 公开求值（P01 jc.evaluate → jc-harness-local/1）。"""

    def _config(self, tmp):
        return p01._config(tmp)

    def test_consistent_amount_evaluated_by_jc(self):
        import contextlib
        with contextlib.ExitStack() as stack:
            config = self._config(Path(stack.enter_context(_tempdir())))
            result = legal_entry.call("number.verify_amount", {
            "principal": "100000",
            "payments": [{"payment_id": "P1", "amount": "30000"},
                         {"payment_id": "P2", "amount": "20000"}],
                "claimed_balance": "50000",
            }, config)
        self.assertEqual(result["verdict"], "CONSISTENT")
        self.assertEqual(result["jc_balance"], "50000")
        self.assertEqual(result["delta_jc_minus_claimed"], "0")
        self.assertEqual(result["amounts"]["payments_total"], "50000")
        self.assertEqual(result["jc"]["contract"], "jc-harness-local/1")
        self.assertEqual(result["jc"]["entry"], "P01 jc.evaluate")
        self.assertEqual(result["jc"]["completion"],
                         "exact_finite_scenarios")
        self.assertEqual(result["jc"]["run_identity_ref"]["kind"],
                         "run-identity")
        self.assertTrue(result["jc"]["input_ref"])
        self.assertFalse(result["arithmetic"]["float_used"])

    def test_wrong_formula_counterexample_rejected(self):
        import contextlib
        with contextlib.ExitStack() as stack:
            config = self._config(Path(stack.enter_context(_tempdir())))
            result = legal_entry.call("number.verify_amount", {
                "principal": "100000",
                "payments": [{"payment_id": "P1", "amount": "30000"}],
                "claimed_balance": "80000",   # 错误算式：100000-30000=70000
            }, config)
        self.assertEqual(result["verdict"], "MISMATCH")
        self.assertEqual(result["jc_balance"], "70000")
        self.assertEqual(result["delta_jc_minus_claimed"], "-10000")

    def test_fractional_amounts_exact(self):
        import contextlib
        with contextlib.ExitStack() as stack:
            config = self._config(Path(stack.enter_context(_tempdir())))
            result = legal_entry.call("number.verify_amount", {
                "principal": "1000.50",
                "payments": [{"payment_id": "P1", "amount": "0.25"}],
                "claimed_balance": "1000.25",
            }, config)
        self.assertEqual(result["verdict"], "CONSISTENT")
        self.assertEqual(result["jc_balance"], "1000.25")

    def test_float_amounts_rejected(self):
        with self.assertRaises(legal_entry.NotConnected) as caught:
            legal_entry.call("number.verify_amount",
                             {"principal": 100.5, "claimed_balance": "1"},
                             {"jc_state_root": "x"})
        self.assertEqual(str(caught.exception),
                         "number_face_failed:amount_float_rejected:principal")

    def test_invalid_amounts_named_fail_closed(self):
        for bad in ("-5", "abc", None, True):
            with self.assertRaises(legal_entry.NotConnected) as caught:
                legal_entry.call("number.verify_amount",
                                 {"principal": bad, "claimed_balance": "1"},
                                 {"jc_state_root": "x"})
            self.assertTrue(
                str(caught.exception).startswith("number_face_failed:amount_"),
                str(caught.exception))

    def test_missing_jc_config_not_connected(self):
        with self.assertRaises(legal_entry.NotConnected) as caught:
            legal_entry.call("number.verify_amount",
                             {"principal": "1", "claimed_balance": "1"}, {})
        self.assertEqual(str(caught.exception),
                         "jc_state_root_not_configured")

    def test_unknown_method_fails_closed(self):
        with self.assertRaises(legal_entry.NotConnected) as caught:
            legal_entry.call("number.classify_all", {"text": "1元"}, {})
        self.assertTrue(str(caught.exception)
                        .startswith("method_not_connected:"))

    def test_classify_missing_text_not_connected(self):
        with self.assertRaises(legal_entry.NotConnected) as caught:
            legal_entry.call("number.classify", {}, {})
        self.assertEqual(str(caught.exception),
                         "number_classify_text_required")

    def test_cli_roundtrip_classify_and_verify(self):
        import contextlib
        with contextlib.ExitStack() as stack:
            tmp = Path(stack.enter_context(_tempdir()))
            config = self._config(tmp)
            request = tmp / "request.json"
            config_json = tmp / "config.json"
            request.write_text(json.dumps(
                {"method": "number.classify", "args": {"text": "本金500元"}},
                ensure_ascii=False), encoding="utf-8")
            config_json.write_text(json.dumps(config, ensure_ascii=False),
                                   encoding="utf-8")
            proc = subprocess.run(
                [sys.executable, "-X", "utf8",
                 str(HERE / "python" / "legal_entry.py"),
                 "--request-json", str(request), "--config", str(config_json)],
                capture_output=True, text=True, encoding="utf-8", timeout=300)
            payload = json.loads(proc.stdout)
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            self.assertEqual(payload["status"], "OWNER_RESPONSE")
            self.assertEqual(
                payload["result"]["mentions"][0]["class"], "fact_amount")
            # verify_amount via CLI with a wrong formula → still OWNER_RESPONSE
            # MISMATCH verdict (rejection is a named verdict, not a fake pass)
            request.write_text(json.dumps({
                "method": "number.verify_amount",
                "args": {"principal": "1000", "claimed_balance": "500",
                         "payments": [{"payment_id": "P1",
                                       "amount": "300"}]},
            }, ensure_ascii=False), encoding="utf-8")
            proc2 = subprocess.run(
                [sys.executable, "-X", "utf8",
                 str(HERE / "python" / "legal_entry.py"),
                 "--request-json", str(request), "--config", str(config_json)],
                capture_output=True, text=True, encoding="utf-8", timeout=300)
            payload2 = json.loads(proc2.stdout)
            self.assertEqual(proc2.returncode, 0, proc2.stdout + proc2.stderr)
            self.assertEqual(payload2["result"]["verdict"], "MISMATCH")
            # missing text via CLI → exit 3 named NOT_CONNECTED
            request.write_text(json.dumps(
                {"method": "number.classify", "args": {}},
                ensure_ascii=False), encoding="utf-8")
            proc3 = subprocess.run(
                [sys.executable, "-X", "utf8",
                 str(HERE / "python" / "legal_entry.py"),
                 "--request-json", str(request), "--config", str(config_json)],
                capture_output=True, text=True, encoding="utf-8", timeout=300)
            payload3 = json.loads(proc3.stdout)
            self.assertEqual(proc3.returncode, 3)
            self.assertEqual(payload3["status"], "NOT_CONNECTED")
            self.assertEqual(payload3["code"], "number_classify_text_required")


import contextlib


@contextlib.contextmanager
def _tempdir():
    with tempfile.TemporaryDirectory() as name:
        yield Path(name)


if __name__ == "__main__":
    unittest.main()

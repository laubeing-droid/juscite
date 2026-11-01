# -*- coding: utf-8 -*-
"""W2b-U55 / F107+F108 acceptance: deadline-preset binding + amount words bridge.

06:F107 assertion「14项逐名绑定JC合同/送达起算条件/官方时点/假期范围；缺支
持不固定加天，程序事件非任意业务事件」＋06:F108 assertion「金额大写规范边
界、分位/零/负数/上限正确，数值来源不变」＋W2b-U19 冻结边界（D01-D14 =
9 RULE_MAPPED＋3 PARTIAL＋D07 UNKNOWN＋D14 CONTRACT_UNKNOWN）。

* calc.deadline_presets — read-only per-name binding document (rule contract
  resolved from the versioned registry, named start condition, E22-verified
  official time point, F106 holiday-range consumption);
* calc.deadline_preset_evaluate — one evaluation receipt through the frozen
  deadline engine fed by the W2b-U54 calendar packs; D07/D14 refuse with
  their frozen status (no fixed day addition), arbitrary business events are
  refused against the per-preset closed procedure-event set;
* calc.amount_words — pure uppercase conversion; float input is a named
  refusal (F89 discipline), the receipt echoes value_minor (the value source
  is unchanged).

All materials below are synthetic engineering fixtures. The bridge consumes
the pinned JC w2b-u55 worktree (this wave's chain head, a superset of the
w2b-u54 F105/F106 delivery chain) through the P01 JCClient surface — no
second authority. The codices E22 frozen face is consumed read-only in the
recon tool, never written.
"""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE / "python"))
import legal_entry

JC_REPO = Path(
    r"D:\Codex\1.法律工作区\juris-calculus工作区\juris-calculus\.local\worktrees\w2b-u55")

# Runtime face pinning (W2a-U16 discipline): the whole pytest process must
# resolve compiler_core to THIS wave's JC worktree (w2b-u55 = chain head on
# top of w2b-u56, carrying deadline_presets + amount_words).
if (JC_REPO / "compiler_core" / "deadline_presets.py").is_file():
    sys.path.insert(0, str(JC_REPO))
    for _name in [m for m in list(sys.modules)
                  if m == "compiler_core" or m.startswith("compiler_core.")]:
        del sys.modules[_name]

_LEGAL_ENTRY = HERE / "python" / "legal_entry.py"
_NOW = "2026-10-17T00:00:00+00:00"

_ACTIVE_TMPDIRS = []

# 合成最小规则包（同 F112 先例）：client 构造要求至少一个 rule root；包内容
# 与 F107/F108 面无关（期限规则来自 JC 仓内 configs 版本化注册表）。
RULE_PACK = {
    "schema_version": "jc/local-pack/1.0",
    "pack_version": "1.0.0",
    "sources": [{
        "source_id": "acceptance-statute", "jurisdiction": "TEST",
        "authority_tier": "official_first_party",
        "issuer": "Acceptance Test Authority", "title": "acceptance-statute",
        "publication_time": "2020-01-01T00:00:00Z",
        "effective_from": "2020-01-01T00:00:00Z",
        "retrieved_at": "2026-08-01T00:00:00Z",
        "locator": {"kind": "uri", "value": "example.invalid/acceptance",
                    "page": None, "span_start": None, "span_end": None},
        "content": ("SYNTHETIC acceptance rule text for engineering "
                    "verification only; no legal effect."),
        "structure_sections": ["ART-1"],
    }],
    "rules": [
        {"rule_id": "acc-base", "jurisdiction": "TEST",
         "governing_law": "acceptance-statute", "source_id": "acceptance-statute",
         "modality": "OBLIGATION",
         "premises": [{"fact_key": "acc.contract", "required": True}],
         "conclusion": {"value": "applies"},
         "effective_from": "2020-01-01T00:00:00Z"},
    ],
}


def _config(tmp_path=None):
    if not (JC_REPO / "compiler_core" / "deadline_presets.py").is_file():
        raise AssertionError(
            f"pinned JC w2b-u55 worktree missing at {JC_REPO}; the F107/F108 "
            "bridge cannot be verified")
    holder = tempfile.TemporaryDirectory()
    _ACTIVE_TMPDIRS.append(holder)  # keep alive until process exit
    tmp_path = Path(holder.name)
    rules = tmp_path / "rules"
    rules.mkdir(parents=True, exist_ok=True)
    (rules / "jc-local-pack.json").write_text(
        json.dumps(RULE_PACK, ensure_ascii=False), encoding="utf-8")
    return {
        "jc_state_root": str(tmp_path / "state"),
        "jc_rule_roots": [str(rules)],
        "jc_import_path": str(JC_REPO),
    }


def _run_cli(method, args, config):
    """真产品入口子进程径（legal_entry CLI；同 W2b-U19/U54 recon 纪律）。"""
    with tempfile.TemporaryDirectory() as tmp:
        req = Path(tmp) / "request.json"
        cfg = Path(tmp) / "config.json"
        req.write_text(json.dumps({"method": method, "args": args},
                                  ensure_ascii=False), encoding="utf-8")
        cfg.write_text(json.dumps(config, ensure_ascii=False), encoding="utf-8")
        proc = subprocess.run(
            [sys.executable, "-X", "utf8", str(_LEGAL_ENTRY),
             "--request-json", str(req), "--config", str(cfg)],
            capture_output=True, text=True, encoding="utf-8", timeout=300)
        try:
            payload = json.loads(proc.stdout)
        except json.JSONDecodeError:
            payload = {"status": "RAW", "stdout": proc.stdout[:400]}
        return proc.returncode, payload


def _result(code, out):
    assert code == 0 and out.get("status") == "OWNER_RESPONSE", (code, out)
    return out["result"]


def _failure(code, out):
    assert code == 4 and out.get("status") == "JC_FAILURE", (code, out)
    return str(out.get("code", ""))


class TestFrozenMethodGroups(unittest.TestCase):
    def test_groups_are_closed_frozensets(self):
        self.assertEqual(legal_entry.DEADLINE_PRESET_METHODS, frozenset({
            "calc.deadline_presets", "calc.deadline_preset_evaluate"}))
        self.assertEqual(legal_entry.AMOUNT_WORDS_METHODS, frozenset({
            "calc.amount_words"}))

    def test_unknown_calc_method_not_connected(self):
        config = _config()
        for method in ("calc.deadline_preset_binding", "calc.uppercase",
                       "calc.deadline_presets.evil"):
            with self.assertRaises(legal_entry.NotConnected) as caught:
                legal_entry.call(method, {}, config)
            self.assertIn("method_not_connected", str(caught.exception))


class TestDeadlinePresetBridge(unittest.TestCase):
    def test_binding_document_fourteen_rows_with_frozen_distribution(self):
        code, out = _run_cli("calc.deadline_presets", {}, _config())
        document = _result(code, out)
        self.assertEqual(len(document["presets"]), 14)
        distribution = {}
        for row in document["presets"]:
            self.assertIn(row["start_condition"], row and row["start_condition"])
            self.assertIn(row["official_time_point"]["status"],
                          ("BOUND_E22_VERIFIED", "NOT_BOUND_NO_SINGLE_PROVISION"))
            self.assertEqual(row["holiday_range"]["face"], "jc-calendar-version/1")
            distribution[row["frozen_status"]] = \
                distribution.get(row["frozen_status"], 0) + 1
        self.assertEqual(distribution, {"RULE_MAPPED": 9, "PARTIAL": 3,
                                        "UNKNOWN": 1, "CONTRACT_UNKNOWN": 1})

    def test_evaluate_rolls_over_qingming_with_version_readback(self):
        code, out = _run_cli("calc.deadline_preset_evaluate", {
            "slot": "D01", "now": _NOW,
            "event": {"kind": "service_of_first_instance_judgment",
                      "anchor": {"value": "2026-03-20", "precision": "date"}},
        }, _config())
        receipt = _result(code, out)
        self.assertEqual(receipt["status"], "OK")
        self.assertEqual(receipt["nominal_due_date"], "2026-04-04")
        self.assertEqual(receipt["due_date"], "2026-04-07")
        self.assertTrue(receipt["holiday_extended"])
        self.assertIn("2026", receipt["calendar_versions"])
        self.assertIn("evaluationRef", receipt)
        self.assertEqual(receipt["evaluationRef"]["owner"], "jc")

    def test_frozen_unknown_presets_refuse_without_fixed_days(self):
        config = _config()
        for slot, fragment in (("D07", "deadline_preset_unknown"),
                               ("D14", "deadline_preset_contract_unknown")):
            code, out = _run_cli("calc.deadline_preset_evaluate", {
                "slot": slot, "now": _NOW,
                "event": {"kind": "any", "anchor": {"value": "2026-01-15",
                                                    "precision": "date"}},
            }, config)
            self.assertIn(fragment, _failure(code, out))

    def test_arbitrary_business_event_refused(self):
        code, out = _run_cli("calc.deadline_preset_evaluate", {
            "slot": "D01", "now": _NOW,
            "event": {"kind": "contract_signed",
                      "anchor": {"value": "2026-01-15", "precision": "date"}},
        }, _config())
        self.assertIn("deadline_preset_event_kind_not_in_preset",
                      _failure(code, out))

    def test_out_of_range_calendar_year_structured_unknown_no_dates(self):
        code, out = _run_cli("calc.deadline_preset_evaluate", {
            "slot": "D01", "now": _NOW, "calendar_years": [2027],
            "event": {"kind": "service_of_first_instance_judgment",
                      "anchor": {"value": "2027-01-10", "precision": "date"}},
        }, _config())
        receipt = _result(code, out)
        self.assertEqual(receipt["status"], "UNKNOWN")
        self.assertEqual(receipt["reason_code"], "calendar_year_out_of_range")
        self.assertFalse(receipt["date_fields_present"])
        self.assertNotIn("due_date", receipt)

    def test_period_end_into_uncovered_year_named_gap(self):
        code, out = _run_cli("calc.deadline_preset_evaluate", {
            "slot": "D13", "now": _NOW, "calendar_years": [2025, 2026],
            "event": {"kind": "enforcement_basis_date",
                      "anchor": {"value": "2025-01-15", "precision": "date"},
                      "legal_context": {
                          "subjectQualified": True,
                          "specialRulesReviewed": True,
                          "performanceMode": "unspecified",
                          "judgmentEffectiveAt": {"value": "2025-01-15",
                                                  "precision": "date"}},
        }, }, _config())
        receipt = _result(code, out)
        self.assertEqual(receipt["status"], "UNKNOWN_CALENDAR")
        self.assertEqual(receipt["nominal_due_date"], "2027-01-15")
        self.assertIsNone(receipt["due_date"])
        self.assertFalse(receipt["date_fields_present"])

    def test_unconfigured_state_root_not_connected(self):
        config = _config()
        config["jc_state_root"] = ""
        code, out = _run_cli("calc.deadline_preset_evaluate", {
            "slot": "D01", "now": _NOW,
            "event": {"kind": "service_of_first_instance_judgment",
                      "anchor": {"value": "2026-01-15", "precision": "date"}},
        }, config)
        self.assertEqual(code, 3)
        self.assertEqual(out.get("status"), "NOT_CONNECTED")


class TestAmountWordsBridge(unittest.TestCase):
    def test_uppercase_conversion_echoes_value_minor(self):
        code, out = _run_cli("calc.amount_words", {"value_minor": 1234567},
                             _config())
        sheet = _result(code, out)
        self.assertEqual(sheet["words"], "壹万贰仟叁佰肆拾伍元陆角柒分")
        self.assertEqual(sheet["value_minor"], 1234567)
        self.assertEqual(sheet["value"], "12345.67")
        self.assertIn("amountWordsRef", sheet)
        self.assertEqual(sheet["amountWordsRef"]["owner"], "jc")

    def test_zero_and_negative_named_boundaries(self):
        code, out = _run_cli("calc.amount_words", {"value_minor": 0}, _config())
        self.assertEqual(_result(code, out)["words"], "零元整")
        code, out = _run_cli("calc.amount_words", {"value_minor": -12345},
                             _config())
        sheet = _result(code, out)
        self.assertEqual(sheet["words"], "负壹佰贰拾叁元肆角伍分")
        self.assertTrue(sheet["negative_amount_semantic"])
        self.assertEqual(sheet["value_minor"], -12345)

    def test_float_input_named_refusal(self):
        code, out = _run_cli("calc.amount_words", {"value_minor": 12345.67},
                             _config())
        self.assertIn("amount_float_input_refused", _failure(code, out))

    def test_beyond_cents_and_upper_limit_refused(self):
        config = _config()
        code, out = _run_cli("calc.amount_words",
                             {"value": "12345.675"}, config)
        self.assertIn("amount_words_precision_beyond_cents",
                      _failure(code, out))
        code, out = _run_cli("calc.amount_words",
                             {"value_minor": 10 ** 18}, config)
        self.assertIn("amount_words_upper_limit_exceeded",
                      _failure(code, out))

    def test_unconfigured_state_root_not_connected(self):
        config = _config()
        config["jc_state_root"] = ""
        code, out = _run_cli("calc.amount_words", {"value_minor": 1}, config)
        self.assertEqual(code, 3)
        self.assertEqual(out.get("status"), "NOT_CONNECTED")


if __name__ == "__main__":
    unittest.main()

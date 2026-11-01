# -*- coding: utf-8 -*-
"""W2b-U19 / E21 + F104 acceptance: nine calc families first batch bridge.

E21 freeze: the nine-family / 14-deadline registry is frozen in JC
(compiler_core.calc_families, registry calc-families/1) and consumed here
through the pinned P01 JCClient surface. Three slots stay named scope gaps
(CALC_SCOPE_U0x_NAME_UNKNOWN) — the toolbox seven never fill nine.

F104 first batch: C01/C03/C04/C05/C06 real calculations through the frozen
calc.* bridge methods, Decimal end-to-end with integer-minor output, the
independent checker must agree before a sheet is sealed (its verdict rides
on every sheet), and unsupported named gaps (U slots, BAC rule pack,
compound interest, stacked reductions) surface as typed JC_FAILURE codes —
never a paper answer. C02 stays on the existing register_event +
calculate_deadlines entry (no second authority).

All money inputs and rule packs below are synthetic engineering fixtures;
the statutory bracket constants live in the JC rule packs with their named
official sources and are asserted at their gazette/official values.
"""
import hashlib
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
    r"D:\Codex\1.法律工作区\juris-calculus工作区\juris-calculus\.local\worktrees\w2b-u19")


# Runtime face pinning (W2a-U16 discipline): the whole pytest process must
# resolve compiler_core to THIS wave's JC worktree. The worktree is a
# superset of the pinned main checkout (P01 tests keep passing on it); the
# reverse order (main face first) would lack calc_families entirely.
if (JC_REPO / "compiler_core" / "calc_families.py").is_file():
    sys.path.insert(0, str(JC_REPO))
    for _name in [m for m in list(sys.modules)
                  if m == "compiler_core" or m.startswith("compiler_core.")]:
        del sys.modules[_name]
JC_CALC_FAMILIES_SHA256 = (
    "bda5f119932b7aa026e63facd002d4535c3ec79e28ffdcad38b0d03ef2df7a5c")
JC_CLIENT_SHA256 = (
    "8da6ae0bb3a9f0728e053e3a61953f5698fe75a26210f0c84ca7597ce5427e46")

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


def _require_jc_worktree():
    if not (JC_REPO / "compiler_core" / "calc_families.py").is_file():
        raise AssertionError(
            f"pinned JC w2b-u19 worktree missing at {JC_REPO}; "
            "the calc family bridge cannot be verified")


_ACTIVE_TMPDIRS = []


def _config(tmp_path=None):
    _require_jc_worktree()
    if tmp_path is None:
        holder = tempfile.TemporaryDirectory()
        _ACTIVE_TMPDIRS.append(holder)
        tmp_path = Path(holder.name)
    elif isinstance(tmp_path, tempfile.TemporaryDirectory):
        tmp_path = Path(tmp_path.name)
    else:
        tmp_path = Path(tmp_path)
    rules = tmp_path / "rules"
    rules.mkdir()
    (rules / "jc-local-pack.json").write_text(
        json.dumps(RULE_PACK, ensure_ascii=False), encoding="utf-8")
    return {
        "jc_state_root": str(tmp_path / "state"),
        "jc_rule_roots": [str(rules)],
        "jc_import_path": str(JC_REPO),
    }


def _run_cli(request, config, tmp_path):
    request_json = tmp_path / "request.json"
    config_json = tmp_path / "config.json"
    request_json.write_text(json.dumps(request, ensure_ascii=False), encoding="utf-8")
    config_json.write_text(json.dumps(config, ensure_ascii=False), encoding="utf-8")
    proc = subprocess.run(
        [sys.executable, "-X", "utf8", str(HERE / "python" / "legal_entry.py"),
         "--request-json", str(request_json), "--config", str(config_json)],
        capture_output=True, text=True, encoding="utf-8", timeout=300)
    return proc, json.loads(proc.stdout)


def _calc(method, payload, config):
    return legal_entry.call(method, {"input": payload}, config)


class E21F104CalcFamilyBridgeTests(unittest.TestCase):

    @classmethod
    def tearDownClass(cls):
        while _ACTIVE_TMPDIRS:
            _ACTIVE_TMPDIRS.pop().cleanup()

    def test_pinned_jc_worktree_sha_matches(self):
        _require_jc_worktree()
        for relative, expected in (
                ("compiler_core/calc_families.py", JC_CALC_FAMILIES_SHA256),
                ("compiler_core/client.py", JC_CLIENT_SHA256)):
            digest = hashlib.sha256((JC_REPO / relative).read_bytes()).hexdigest()
            self.assertEqual(digest, expected, f"JC {relative} drifted from the pin")

    def test_frozen_bridge_method_group(self):
        # W2b-U54 same-family extension: the six W2b-U19 calc methods plus
        # calc.rule_base_recon (F105) and calc.calendar_account /
        # calc.calendar_due_date (F106) — still one frozen calc.* group.
        # W4-U48 (F109): calc.damages joins as the C07 v1.5 first-batch
        # extension (ten-slot registry; the nine frozen slots are untouched).
        self.assertEqual(sorted(legal_entry.CALC_FAMILY_METHODS), [
            "calc.arbitration_fee", "calc.calendar_account",
            "calc.calendar_due_date", "calc.contingency_fee", "calc.court_fee",
            "calc.damages", "calc.interest", "calc.preservation_fee",
            "calc.registry", "calc.rule_base_recon"])
        # jc.* frozen list untouched by this wave (P01 contract unchanged)
        self.assertEqual(legal_entry.JC_METHODS, (
            "jc.case_bundle", "jc.evaluate", "jc.read_run",
            "jc.horn_subject_state", "jc.business_delivery_documents",
            "jc.verify_business_delivery"))

    def test_registry_freeze_nine_slots_three_gaps(self):
        config = _config()
        registry = legal_entry.call("calc.registry", {}, config)
        self.assertEqual(registry["registry_version"], "calc-families/1")
        slots = [row["slot"] for row in registry["nine_families"]]
        self.assertEqual(slots, ["C01", "C02", "C03", "C04", "C05", "C06",
                                 "U01", "U02", "U03"])
        named = {row["slot"]: row["zh_name"] for row in registry["nine_families"]}
        self.assertEqual([named[f"C0{i}"] for i in range(1, 7)],
                         ["阶梯利息", "期限", "诉讼费", "财产保全费", "风险代理费", "仲裁费"])
        for slot in ("U01", "U02", "U03"):
            row = next(r for r in registry["nine_families"] if r["slot"] == slot)
            self.assertIsNone(row["zh_name"])
            self.assertEqual(row["status"], f"CALC_SCOPE_{slot}_NAME_UNKNOWN")
        gaps = {row["id"] for row in registry["scope_gaps"]}
        self.assertEqual(gaps, {
            "CALC_SCOPE_U01_NAME_UNKNOWN", "CALC_SCOPE_U02_NAME_UNKNOWN",
            "CALC_SCOPE_U03_NAME_UNKNOWN"})
        # toolbox seven never fill nine: none of the gap slots gained an entry
        self.assertTrue(all(row["public_entry"] is None
                            for row in registry["nine_families"]
                            if row["slot"].startswith("U")))
        self.assertIn("9槽=6具名域+3具名scope gap", registry["denominator_note"])

    def test_registry_freeze_fourteen_deadline_presets(self):
        config = _config()
        registry = legal_entry.call("calc.registry", {}, config)
        rows = registry["deadline_presets"]
        self.assertEqual([row["slot"] for row in rows],
                         [f"D{i:02d}" for i in range(1, 15)])
        statuses = {row["slot"]: row["status"] for row in rows}
        self.assertEqual(statuses["D07"], "UNKNOWN")
        self.assertEqual(statuses["D14"], "CONTRACT_UNKNOWN")
        self.assertEqual([s for s in statuses.values() if s == "RULE_MAPPED"],
                         ["RULE_MAPPED"] * 9)
        # source periods stay labelled competitor declarations
        self.assertTrue(all("竞品声明" in row["source_period"] for row in rows))

    def test_registry_rule_pack_versions_and_sources(self):
        config = _config()
        registry = legal_entry.call("calc.registry", {}, config)
        self.assertEqual(registry["rule_packs"], {
            "C03": "cn-court-fee/sc-481-2007@1",
            "C04": "cn-preservation-fee/sc-481-2007@1",
            "C05": "cn-lawyer-contingency/sft-2021-87@1",
            "C06": "cietac/2024@1",
        })
        c03 = _calc("calc.court_fee", {"amount_minor": 1_000_000}, config)
        self.assertIn("第十三条", c03["source"]["article"])
        self.assertEqual(c03["source"]["effective_from"], "2007-04-01")
        c06 = _calc("calc.arbitration_fee", {
            "institution": "cietac", "table": "out", "amount_minor": 1}, config)
        self.assertIn("6,625,000", c06["source"]["transcription_note"])

    def test_court_fee_gazette_values_and_boundaries(self):
        config = _config()
        # 公报表例：10万元 = 50 + 9万×2.5% = 2,300元
        self.assertEqual(_calc("calc.court_fee", {"amount_minor": 10_000_000},
                               config)["amount_minor"], 230_000)
        self.assertEqual(_calc("calc.court_fee", {"amount_minor": 1_000_000},
                               config)["amount_minor"], 5_000)
        self.assertEqual(_calc("calc.court_fee", {"amount_minor": 1_000_001},
                               config)["amount_minor"], 5_000)
        # 减半（第十六条 简易程序）
        half = _calc("calc.court_fee", {"amount_minor": 10_000_000,
                                        "simplified_procedure": True}, config)
        self.assertEqual(half["amount_minor"], 115_000)
        # 上诉按不服部分（第十七条）
        appeal = _calc("calc.court_fee", {
            "amount_minor": 500_000_000,
            "appeal_amount_minor": 10_000_000}, config)
        self.assertEqual(appeal["amount_minor"], 230_000)

    def test_preservation_fee_cap_and_edges(self):
        config = _config()
        self.assertEqual(_calc("calc.preservation_fee",
                               {"preserved_amount_minor": 100_000},
                               config)["amount_minor"], 3_000)
        self.assertEqual(_calc("calc.preservation_fee",
                               {"preserved_amount_minor": 5_000_000},
                               config)["amount_minor"], 52_000)
        capped = _calc("calc.preservation_fee",
                       {"preserved_amount_minor": 100_000_000}, config)
        self.assertEqual(capped["amount_minor"], 500_000)  # 5,000元封顶
        self.assertEqual(_calc("calc.preservation_fee",
                               {"preserved_amount_minor": 89_600_000},
                               config)["amount_minor"], 500_000)
        self.assertEqual(_calc("calc.preservation_fee",
                               {"preserved_amount_minor": 89_000_000},
                               config)["amount_minor"], 497_000)

    def test_contingency_caps_and_prohibition(self):
        config = _config()
        sheet = _calc("calc.contingency_fee", {
            "case_type": "civil_contract", "target_amount_minor": 100_000_000,
            "agreement": {"mode": "rate", "rate": "0.1"}}, config)
        self.assertEqual(sheet["statutory_cap_minor"], 18_000_000)
        self.assertTrue(sheet["within_cap"] and sheet["certified"])
        over = _calc("calc.contingency_fee", {
            "case_type": "civil_contract", "target_amount_minor": 100_000_000,
            "agreement": {"mode": "rate", "rate": "0.2"}}, config)
        self.assertFalse(over["certified"])  # 超限如实回传，不静默夹取
        self.assertEqual(over["agreement_amount_minor"], 20_000_000)

    def test_arbitration_cietac_values_and_ceiling(self):
        config = _config()
        out = lambda amount: _calc("calc.arbitration_fee", {
            "institution": "cietac", "table": "out", "amount_minor": amount}, config)
        self.assertEqual(out(100_000_000)["amount_minor"], 4_000_000)
        self.assertEqual(out(10_000_000)["amount_minor"], 1_000_000)  # 最低1万
        self.assertEqual(out(100_000_000_000)["amount_minor"], 662_500_000)
        self.assertEqual(out(300_000_000_000)["amount_minor"], 1_512_500_000)
        self.assertEqual(out(400_000_000_000)["amount_minor"],
                         out(300_000_000_000)["amount_minor"])  # 超30亿不计费
        table_in = _calc("calc.arbitration_fee", {
            "institution": "cietac", "table": "in",
            "amount_minor": 100_000_000}, config)
        self.assertEqual(table_in["acceptance_amount_minor"], 1_700_000)
        self.assertEqual(table_in["handling_amount_minor"], 1_950_000)

    def test_interest_real_date_boundaries(self):
        config = _config()
        # 闰日：2024-02-28 → 2024-03-01 = 2天
        leap = _calc("calc.interest", {
            "principal_minor": 365_000,
            "segments": [{"start_date": "2024-02-28", "end_date": "2024-03-01",
                          "annual_rate": "0.01"}]}, config)
        self.assertEqual(leap["amount_minor"], 20)
        # 阶梯换率：段界拼接
        ladder = _calc("calc.interest", {
            "principal_minor": 12_000_000,
            "segments": [
                {"start_date": "2026-01-01", "end_date": "2026-07-01",
                 "annual_rate": "0.06"},
                {"start_date": "2026-07-01", "end_date": "2027-01-01",
                 "annual_rate": "0.08"}]}, config)
        self.assertEqual(len(ladder["segments"]), 2)
        self.assertEqual(ladder["segments"][0]["days"], 181)
        self.assertEqual(ladder["segments"][1]["days"], 184)

    def test_every_sheet_carries_agreed_independent_checker(self):
        config = _config()
        for method, payload in (
                ("calc.court_fee", {"amount_minor": 123_456_789}),
                ("calc.preservation_fee", {"preserved_amount_minor": 987_654_321}),
                ("calc.contingency_fee", {
                    "case_type": "civil_contract", "target_amount_minor": 55_555_555,
                    "agreement": {"mode": "fixed", "fixed_minor": 500_000}}),
                ("calc.arbitration_fee", {
                    "institution": "cietac", "table": "in",
                    "amount_minor": 12_345_678}),
                ("calc.interest", {
                    "principal_minor": 9_999_999,
                    "segments": [{"start_date": "2026-02-28",
                                  "end_date": "2026-12-31",
                                  "annual_rate": "0.037"}]})):
            sheet = _calc(method, payload, config)
            self.assertTrue(sheet["independentChecker"]["agreed"], method)
            self.assertEqual(sheet["independentChecker"]["checker_version"],
                             "calc-family-independent-checker/1")
            self.assertEqual(sheet["calculationReceiptRef"]["kind"],
                             "calc-family-sheet")

    def test_same_input_same_output_deterministic(self):
        config = _config()
        payload = {"amount_minor": 7_777_777_777}
        first = _calc("calc.court_fee", payload, config)
        second = _calc("calc.court_fee", payload, config)
        self.assertEqual(json.dumps(first, sort_keys=True, default=str),
                         json.dumps(second, sort_keys=True, default=str))

    def test_scope_gaps_refuse_typed_not_paper_answers(self):
        config = _config()
        client = legal_entry._jc_client(config)
        # JC public face refuses the unnamed slots with their frozen gap codes
        for slot in ("U01", "U02", "U03"):
            with self.assertRaises(Exception) as caught:
                client.calculate_family({"family": slot, "input": {}})
            self.assertEqual(getattr(caught.exception, "code", None),
                             f"CALC_SCOPE_{slot}_NAME_UNKNOWN")
        with self.assertRaises(Exception) as caught:
            client.calculate_family({"family": "C02", "input": {}})
        self.assertEqual(getattr(caught.exception, "code", None),
                         "calc_family_reuses_deadline_entry")

    def test_unsupported_named_gaps_fail_typed_through_bridge(self):
        config = _config()
        # BAC 具名缺口（非纸面答案）
        with self.assertRaises(legal_entry.JCMethodFailure) as caught:
            _calc("calc.arbitration_fee", {
                "institution": "bac", "table": "out", "amount_minor": 1}, config)
        self.assertIn("rule_pack_absent", str(caught.exception))
        # 复利首批未冻结
        with self.assertRaises(legal_entry.JCMethodFailure) as caught:
            _calc("calc.interest", {
                "principal_minor": 100, "compound": "annual",
                "segments": [{"start_date": "2026-01-01",
                              "end_date": "2026-02-01",
                              "annual_rate": "0.05"}]}, config)
        self.assertIn("interest_compound_not_supported_in_first_batch",
                      str(caught.exception))
        # 双减半旗叠加未认证
        with self.assertRaises(legal_entry.JCMethodFailure) as caught:
            _calc("calc.court_fee", {
                "amount_minor": 1_000_000,
                "simplified_procedure": True,
                "mediation_or_withdrawal": True}, config)
        self.assertIn("court_fee_reduction_stacking_not_certified",
                      str(caught.exception))
        # 禁止风险代理案件类型
        with self.assertRaises(legal_entry.JCMethodFailure) as caught:
            _calc("calc.contingency_fee", {
                "case_type": "criminal_litigation", "target_amount_minor": 1,
                "agreement": {"mode": "fixed", "fixed_minor": 1}}, config)
        self.assertIn("contingency_case_type_prohibited", str(caught.exception))

    def test_bridge_fail_closed_unknown_method_and_missing_config(self):
        with self.assertRaises(legal_entry.NotConnected) as caught:
            legal_entry.call("calc.nope", {}, {"jc_state_root": "x"})
        self.assertEqual(str(caught.exception), "method_not_connected:calc.nope")
        with self.assertRaises(legal_entry.NotConnected) as caught:
            legal_entry.call("calc.registry", {}, {})
        self.assertEqual(str(caught.exception), "jc_state_root_not_configured")
        # jc_state_root set but no rule roots: JC fails loudly (no invented
        # legal capability) rather than answering anything — raw LocalRuntimeError
        with self.assertRaises(Exception) as caught:
            legal_entry.call("calc.court_fee", {"input": {"amount_minor": 1}},
                             {"jc_state_root": str(Path(tempfile.gettempdir()))})
        self.assertIn("rule root", str(caught.exception))

    def test_cli_roundtrip_owner_response_and_typed_failure(self):
        holder = tempfile.TemporaryDirectory()
        _ACTIVE_TMPDIRS.append(holder)
        tmp = Path(holder.name)
        config = _config(tmp)
        request = {"method": "calc.court_fee",
                   "args": {"input": {"amount_minor": 10_000_000}}}
        proc, payload = _run_cli(request, config, tmp)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertEqual(payload["status"], "OWNER_RESPONSE")
        self.assertEqual(payload["result"]["amount"], "2300")
        # typed refusal surfaces as JC_FAILURE exit 4 with the JC code
        proc2, payload2 = _run_cli(
            {"method": "calc.arbitration_fee",
             "args": {"input": {"institution": "bac", "table": "out",
                                "amount_minor": 1}}}, config, tmp)
        self.assertEqual(proc2.returncode, 4)
        self.assertEqual(payload2["status"], "JC_FAILURE")
        self.assertIn("rule_pack_absent", payload2["code"])
        # unknown method NOT_CONNECTED exit 3
        proc3, payload3 = _run_cli({"method": "calc.nope", "args": {}},
                                   config, tmp)
        self.assertEqual(proc3.returncode, 3)
        self.assertEqual(payload3["status"], "NOT_CONNECTED")


if __name__ == "__main__":
    unittest.main()

# -*- coding: utf-8 -*-
"""W2b-U56 / F112 acceptance: rule-pack version governance bridge.

06:F112 assertion「规则包参数/历史/法源/时点版本可回放，修改配置真实改变
相应输出」+ 07 卡（owner=jc+codices；entries P01,P11）：
* calc.rule_pack_ledger — read-only readback of the append-only version
  account (per version: parameter set + digest, named official source with
  locator + retrieved, effective/recorded timestamps, sealed samples);
* calc.rule_pack_replay — any recorded version / any in-range as_of
  recomputes to the sealed output digest (「与当时一致的输出」); out-of-range
  as_of is refused typed;
* calc.rule_pack_delta — same input across two parameter sets, differences
  attributed to the parameter delta rows; a candidate that repeats the
  recorded parameter set is refused (a configuration change that cannot
  change the output is never reportable as one).

All materials below are synthetic engineering fixtures. The bridge consumes
the pinned JC w2b-u56 worktree (the W2b wave chain head, a superset of the
w2b-u27 E19 chain) through the P01 JCClient surface — no second authority.
Registration of a real configuration change is a code-reviewed ledger
extension on the JC side; the bridge has no write channel. The codices E22
frozen face is consumed read-only in the recon tool (sha-pinned), never
written.
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
    r"D:\Codex\1.法律工作区\juris-calculus工作区\juris-calculus\.local\worktrees\w2b-u56")

# Runtime face pinning (W2a-U16 discipline): the whole pytest process must
# resolve compiler_core to THIS wave's JC worktree (w2b-u56 = chain head on
# top of w2b-u27, carrying rule_pack_ledger).
if (JC_REPO / "compiler_core" / "rule_pack_ledger.py").is_file():
    sys.path.insert(0, str(JC_REPO))
    for _name in [m for m in list(sys.modules)
                  if m == "compiler_core" or m.startswith("compiler_core.")]:
        del sys.modules[_name]

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

_C03_INPUT = {"case_category": "property", "amount_minor": 10_000_000}
_EXPECTED_PACKS = {"cietac", "cn-court-fee", "cn-lawyer-contingency",
                   "cn-preservation-fee"}

_ACTIVE_TMPDIRS = []


def _config(tmp_path=None):
    if not (JC_REPO / "compiler_core" / "rule_pack_ledger.py").is_file():
        raise AssertionError(
            f"pinned JC w2b-u56 worktree missing at {JC_REPO}; the F112 "
            "governance bridge cannot be verified")
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
    with tempfile.TemporaryDirectory() as tmp:
        request = Path(tmp) / "request.json"
        conf = Path(tmp) / "config.json"
        request.write_text(json.dumps({"method": method, "args": args},
                                      ensure_ascii=False), encoding="utf-8")
        conf.write_text(json.dumps(config, ensure_ascii=False),
                        encoding="utf-8")
        proc = subprocess.run(
            [sys.executable, "-X", "utf8", str(HERE / "python" / "legal_entry.py"),
             "--request-json", str(request), "--config", str(conf)],
            capture_output=True, text=True, encoding="utf-8", timeout=300)
        try:
            payload = json.loads(proc.stdout)
        except json.JSONDecodeError:
            payload = {"status": "RAW", "stdout": proc.stdout[:400]}
        return proc.returncode, payload


class TestMethodGroupFrozen(unittest.TestCase):
    def test_frozen_method_group(self):
        self.assertEqual(legal_entry.RULE_PACK_GOVERNANCE_METHODS, frozenset({
            "calc.rule_pack_ledger", "calc.rule_pack_replay",
            "calc.rule_pack_delta"}))

    def test_unknown_governance_method_not_connected(self):
        with self.assertRaises(legal_entry.NotConnected) as ctx:
            legal_entry.call("calc.rule_pack_history", {}, _config())
        self.assertIn("not_connected", str(ctx.exception))

    def test_unconfigured_fails_closed(self):
        with self.assertRaises(legal_entry.NotConnected) as ctx:
            legal_entry.call("calc.rule_pack_ledger", {}, {})
        self.assertIn("jc_state_root_not_configured", str(ctx.exception))

    def test_missing_input_not_connected(self):
        with self.assertRaises(legal_entry.NotConnected) as ctx:
            legal_entry.call("calc.rule_pack_replay",
                             {"pack_id": "cn-court-fee", "family": "C03"},
                             _config())
        self.assertIn("rule_pack_governance_input_required", str(ctx.exception))


class TestLedgerReadback(unittest.TestCase):
    def test_ledger_via_cli(self):
        code, out = _run_cli("calc.rule_pack_ledger", {}, _config())
        self.assertEqual(code, 0, out)
        self.assertEqual(out["status"], "OWNER_RESPONSE")
        result = out["result"]
        self.assertEqual(sorted(result["packs"]), sorted(_EXPECTED_PACKS))
        self.assertTrue(result["append_only"])
        for pack_id, row in result["packs"].items():
            version = row["versions"][0]
            # 法源/时点版本账面要件：locator＋retrieved＋双时点戳＋参数集
            self.assertTrue(version["source"]["locator"])
            self.assertEqual(version["source"]["retrieved"], "2026-10-16")
            self.assertTrue(version["effective_from"])
            self.assertTrue(version["recorded_at"])
            self.assertTrue(version["params_digest"].startswith("sha256:"))
            self.assertTrue(version["params"])

    def test_ledger_read_only_deterministic(self):
        config = _config()
        _, first = _run_cli("calc.rule_pack_ledger", {}, config)
        _, second = _run_cli("calc.rule_pack_ledger", {}, config)
        self.assertEqual(
            json.dumps(first["result"], sort_keys=True, ensure_ascii=False),
            json.dumps(second["result"], sort_keys=True, ensure_ascii=False))


class TestReplay(unittest.TestCase):
    def test_replay_sealed_match(self):
        code, out = _run_cli(
            "calc.rule_pack_replay",
            {"pack_id": "cn-court-fee", "family": "C03", "input": dict(_C03_INPUT)},
            _config())
        self.assertEqual(code, 0, out)
        result = out["result"]
        self.assertEqual(result["sealed_reconciliation"]["status"], "MATCH")
        self.assertEqual(result["sheet"]["amount_minor"], 230_000)
        self.assertTrue(result["replayRef"]["digest"].startswith("sha256:"))

    def test_replay_deterministic_across_processes(self):
        config = _config()
        args = {"pack_id": "cn-court-fee", "family": "C03", "input": dict(_C03_INPUT)}
        _, first = _run_cli("calc.rule_pack_replay", args, config)
        _, second = _run_cli("calc.rule_pack_replay", args, config)
        self.assertEqual(first["result"]["output_digest"],
                         second["result"]["output_digest"])

    def test_replay_as_of_resolves_current(self):
        code, out = _run_cli(
            "calc.rule_pack_replay",
            {"pack_id": "cn-court-fee", "family": "C03",
             "input": dict(_C03_INPUT), "as_of": "2026-10-16"},
            _config())
        self.assertEqual(code, 0, out)
        self.assertEqual(out["result"]["pack_version"],
                         "cn-court-fee/sc-481-2007@1")

    def test_as_of_out_of_range_refused_typed(self):
        code, out = _run_cli(
            "calc.rule_pack_replay",
            {"pack_id": "cn-court-fee", "family": "C03",
             "input": dict(_C03_INPUT), "as_of": "2000-01-01"},
            _config())
        self.assertEqual(code, 4)
        self.assertEqual(out["status"], "JC_FAILURE")
        self.assertIn("as_of_before_first_version", out["code"])

    def test_unknown_version_refused_typed(self):
        code, out = _run_cli(
            "calc.rule_pack_replay",
            {"pack_id": "cn-court-fee", "family": "C03",
             "input": dict(_C03_INPUT), "pack_version": "cn-court-fee/never@9"},
            _config())
        self.assertEqual(code, 4)
        self.assertIn("rule_pack_version_unknown", out["code"])


class TestDelta(unittest.TestCase):
    def test_candidate_delta_attributable(self):
        _, ledger = _run_cli("calc.rule_pack_ledger", {}, _config())
        params = ledger["result"]["packs"]["cn-court-fee"]["versions"][0]["params"]
        candidate = json.loads(json.dumps(params))
        candidate["acceptance_brackets"][0][2] = 6_000  # 合成治理演练：50 元 -> 60 元
        code, out = _run_cli(
            "calc.rule_pack_delta",
            {"pack_id": "cn-court-fee", "family": "C03",
             "input": dict(_C03_INPUT), "candidate_params": candidate},
            _config())
        self.assertEqual(code, 0, out)
        result = out["result"]
        self.assertEqual(result["delta_count"], 1)
        self.assertEqual(result["delta"][0]["path"], "/acceptance_brackets/0/2")
        self.assertTrue(result["outputs_differ"])
        self.assertEqual(result["attribution"], "param_delta")
        self.assertEqual(result["from_sheet"]["amount_minor"], 230_000)
        self.assertEqual(result["to_sheet"]["amount_minor"], 231_000)

    def test_no_param_change_refused_typed(self):
        _, ledger = _run_cli("calc.rule_pack_ledger", {}, _config())
        params = ledger["result"]["packs"]["cn-court-fee"]["versions"][0]["params"]
        code, out = _run_cli(
            "calc.rule_pack_delta",
            {"pack_id": "cn-court-fee", "family": "C03",
             "input": dict(_C03_INPUT), "candidate_params": params},
            _config())
        self.assertEqual(code, 4)
        self.assertEqual(out["status"], "JC_FAILURE")
        self.assertIn("rule_pack_version_no_param_change", out["code"])

    def test_delta_needs_exactly_one_target(self):
        config = _config()
        code, out = _run_cli(
            "calc.rule_pack_delta",
            {"pack_id": "cn-court-fee", "family": "C03", "input": dict(_C03_INPUT)},
            config)
        self.assertEqual(code, 4)
        self.assertIn("schema_invalid", out["code"])


if __name__ == "__main__":
    unittest.main()

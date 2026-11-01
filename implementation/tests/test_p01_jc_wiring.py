"""W1-U03 / E09 / P01 acceptance: JC computation entry product-bridge wiring.

Synthetic bundle real evaluation through legal_entry jc.* methods plus owner
read-back after evaluate (verify_run via jc.read_run, and the two-file
business delivery via jc.business_delivery_documents +
jc.verify_business_delivery). Unknown interfaces and missing config must fail
with named codes, never an empty response or a fake success. The JC checkout
is consumed read-only at the path pinned in 14-Python入口证据.csv P01; the
pinned client.py sha256 is asserted so JC drift fails this wiring loudly.
All materials are synthetic (rule pack, business task, selections).
"""
import contextlib
import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from base64 import b64decode, b64encode
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE / "python"))
import legal_entry

JC_REPO = Path(r"D:\Codex\1.法律工作区\juris-calculus工作区\juris-calculus")
JC_CLIENT_SHA256 = "15c2f88f415d1758a628d7f98c1ecb87c623f017ffe1f1040c488d9ad775c7be"
SELECTION_REF = "sha256:" + hashlib.sha256(b"p01-synthetic-selection").hexdigest()

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
        {"rule_id": "acc-exception", "jurisdiction": "TEST",
         "governing_law": "acceptance-statute", "source_id": "acceptance-statute",
         "modality": "OBLIGATION",
         "premises": [{"fact_key": "acc.exception", "required": True}],
         "conclusion": {"value": "exception-applies"},
         "exceptions": [{"target": "acc-base",
                         "condition_fact_key": "acc.exception"}],
         "effective_from": "2020-01-01T00:00:00Z"},
    ],
}

SOURCE_BODY = "SYNTH: principal 1000 due 2026-08-01; payment 300 on 2026-08-20 recognized."
BUSINESS_TASK = {
    "task_id": "task-1", "issue_id": "principal-balance",
    "requirement_id": "SYNTHETIC_EXACT_PRINCIPAL_ANALYTICS_TWO_FILES/1",
    "profile": "SYNTHETIC-CONDITIONAL-PRINCIPAL/1",
    "selection_ref": SELECTION_REF,
    "input": {
        "context": {
            "request": "SYNTHETIC-BUSINESS-CASE-1", "jurisdiction": "TEST",
            "event_time": "2026-08-01", "decision_time": "2026-09-09",
            "procedure": "conditional_analysis", "stage": "analysis",
            "party": "claimant", "issue": "principal-balance",
            "scenario": "finite-conditional-completions", "profile": "grounded",
            "law_version": "source-snapshot-example",
            "interpretation": "explicit-reference", "rulepack_version": "test-1",
            "engine_version": "reference-2.1", "model_version": "synthetic-model-1",
            "evidence_version": "test-evidence-1",
            "target": "award_at_least_threshold", "semantic_scope": "height_bounded",
            "assumptions": ["synthetic assumption A", "synthetic assumption B"],
            "max_depth": 2,
        },
        "spec": {
            "relation_id": "principal-claim", "creditor": "SYN-Creditor",
            "debtor": "SYN-Debtor", "debt_id": "DEBT-1", "principal": "1000",
            "due_day": "2026-08-01", "asof_day": "2026-09-09",
            "sources": [{"source_id": "SYNTHETIC-BASIS", "version": "1",
                         "body": SOURCE_BODY, "start": 0, "end": len(SOURCE_BODY),
                         "quoted": SOURCE_BODY}],
            "payments": [{"payment_id": "P1", "amount": "300",
                          "event_day": "2026-08-20", "payer": "SYN-Debtor",
                          "recipient": "SYN-Creditor", "debt_id": "DEBT-1",
                          "recognition_atom": "payment_recognized",
                          "source_id": "SYNTHETIC-BASIS"}],
            "facts": [{"atom": "payment_recognized", "observed": None}],
            "constraint": {"op": "true", "atom": "", "children": []},
            "approved_policy": "SYNTHETIC-CONDITIONAL-PRINCIPAL/1",
        },
        "model": {
            "weights": [
                {"world": {"atoms": [{"atom": "payment_recognized", "value": True}]},
                 "probability": "2/5"},
                {"world": {"atoms": [{"atom": "payment_recognized", "value": False}]},
                 "probability": "3/5"},
            ],
            "threshold": "800", "costs": ["100", "60", "10", "10"],
            "legal_options": ["600", "850", "1100"],
            "basis": "SYNTHETIC-SETTLEMENT-GRID/1",
        },
        "solve_budget": None,
    },
}


def _require_jc_repo():
    if not (JC_REPO / "compiler_core" / "client.py").is_file():
        raise AssertionError(
            f"pinned JC checkout missing at {JC_REPO} (14-Python入口证据.csv P01); "
            "the jc wiring cannot be verified")


def _config(tmp_path):
    _require_jc_repo()
    rules = tmp_path / "rules"
    rules.mkdir()
    (rules / "jc-local-pack.json").write_text(
        json.dumps(RULE_PACK, ensure_ascii=False), encoding="utf-8")
    return {
        "jc_state_root": str(tmp_path / "state"),
        "jc_rule_roots": [str(rules)],
        "jc_import_path": str(JC_REPO),
    }


def _issue_queries(config):
    """Fixture prep through the same pinned public surface: local_pack claims."""
    client = legal_entry._jc_client(config)
    claims = {row["rule_id"]: row["claim"] for row in client.local_pack()["rules"]}
    return [
        {"issue_id": "issue-base", "claim": claims["acc-base"], "profile": "grounded"},
        {"issue_id": "issue-exception", "claim": claims["acc-exception"], "profile": "grounded"},
    ]


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


class P01JCWiringTests(unittest.TestCase):
    def test_pinned_jc_client_sha_matches_entry_evidence(self):
        _require_jc_repo()
        digest = hashlib.sha256(
            (JC_REPO / "compiler_core" / "client.py").read_bytes()).hexdigest()
        self.assertEqual(digest, JC_CLIENT_SHA256,
                         "JC client.py drifted from the pinned P01 entry evidence")

    def test_frozen_jc_method_list(self):
        self.assertEqual(legal_entry.JC_METHODS, (
            "jc.case_bundle",
            "jc.evaluate",
            "jc.read_run",
            "jc.horn_subject_state",
            "jc.business_delivery_documents",
            "jc.verify_business_delivery",
        ))

    def test_case_bundle_builds_real_bundle(self):
        config = _config(Path(self.enterContext(_tempdir())))
        bundle = legal_entry.call("jc.case_bundle", {
            "case_id": "acceptance-case",
            "decision_time": "2026-09-01T00:00:00Z",
            "facts": [{"fact_key": "acc.contract"}],
            "queries": _issue_queries(config),
        }, config)
        self.assertTrue(bundle["bundle_id"])
        self.assertEqual(bundle["request"]["request_id"], "local-acceptance-case")
        self.assertTrue(bundle["artifacts"])

    def test_horn_evaluate_real_run_and_owner_readback(self):
        config = _config(Path(self.enterContext(_tempdir())))
        queries = _issue_queries(config)
        result = legal_entry.call("jc.evaluate", {
            "bundle": {
                "case_id": "acceptance-case",
                "decision_time": "2026-09-01T00:00:00Z",
                "facts": [{"fact_key": "acc.contract"}, {"fact_key": "acc.exception"}],
                "queries": queries,
            },
            "issue_queries": queries,
        }, config)
        self.assertEqual(result["run_status"], "success")
        self.assertEqual(result["execution_mode"], "local")
        self.assertEqual(result["signature_status"], "not_used")
        self.assertEqual(result["evaluation_count"], 1)
        self.assertEqual([i["issue_id"] for i in result["issues"]],
                         ["issue-base", "issue-exception"])
        # owner read-back 1: verify_run-based read (fresh client, sealed state)
        record = legal_entry.call("jc.read_run",
                                  {"run_identity_ref": result["run_identity_ref"]},
                                  config)
        self.assertEqual(record["run_identity_ref"], result["run_identity_ref"])
        self.assertEqual(record["decision_status"], "accepted_formal_result")
        self.assertEqual(record["signature_status"], "not_used")
        self.assertIn("checker-receipts.json", record["files"])
        # owner read-back 2: sealed Horn subject state for the incremental path
        horn = legal_entry.call("jc.horn_subject_state",
                                {"run_identity_ref": result["run_identity_ref"]},
                                config)
        self.assertEqual(horn["parent_run_ref"], result["run_identity_ref"])
        self.assertTrue(horn["parent_subject_digest"].startswith("sha256:"))
        self.assertEqual(horn["parent_state_ref"]["kind"], "horn-subject-state-v5")

    def test_business_evaluate_and_delivery_readback(self):
        config = _config(Path(self.enterContext(_tempdir())))
        result = legal_entry.call("jc.evaluate", {
            "bundle": {
                "case_id": "business-case",
                "decision_time": "2026-09-11T00:00:00Z",
                "business_tasks": [BUSINESS_TASK],
            },
        }, config)
        self.assertEqual(result["run_status"], "success")
        self.assertEqual(result["evaluation_count"], 1)
        row = result["business_results"][0]
        self.assertEqual(row["completion"], "exact_finite_scenarios")
        self.assertEqual(row["analytics"]["selected"], "850")
        # owner read-back: two-file delivery rendered then verified, no rerun
        docs = legal_entry.call("jc.business_delivery_documents", {
            "run_identity_ref": result["run_identity_ref"],
            "business_task_id": "task-1",
        }, config)
        self.assertEqual(sorted(docs), ["calculation.json", "conditional_principal.txt"])
        verdict = legal_entry.call("jc.verify_business_delivery", {
            "run_identity_ref": result["run_identity_ref"],
            "business_task_id": "task-1",
            "selected_input_ref": SELECTION_REF,
            "artifacts": docs,
        }, config)
        self.assertEqual(verdict["status"], "ACCEPTED")
        # negative: tampered principal text must be named-rejected, not accepted
        tampered = dict(docs)
        tampered["conditional_principal.txt"] = b64encode(
            b64decode(docs["conditional_principal.txt"]).replace(b"1000", b"1200")
        ).decode("ascii")
        rejected = legal_entry.call("jc.verify_business_delivery", {
            "run_identity_ref": result["run_identity_ref"],
            "business_task_id": "task-1",
            "selected_input_ref": SELECTION_REF,
            "artifacts": tampered,
        }, config)
        self.assertEqual(rejected["status"], "REJECTED")
        self.assertIn("PRINCIPAL_FILE_READBACK", rejected["reasons"])

    def test_unknown_jc_method_is_named_not_connected(self):
        # calculate_deadlines exists on JCClient but is reserved for F118 and
        # is not in the frozen bridge list; it must not answer success.
        with self.assertRaises(legal_entry.NotConnected) as caught:
            legal_entry.call("jc.calculate_deadlines", {}, {"jc_state_root": "x"})
        self.assertTrue(str(caught.exception).startswith("jc_method_not_in_frozen_list:"))
        with self.assertRaises(legal_entry.NotConnected) as caught:
            legal_entry.call("jc.nope", {}, {"jc_state_root": "x"})
        self.assertTrue(str(caught.exception).startswith("jc_method_not_in_frozen_list:"))

    def test_missing_config_is_not_connected(self):
        for config in ({}, {"jc_rule_roots": []}, {"jc_import_path": "C:\nonexistent"}):
            with self.assertRaises(legal_entry.NotConnected) as caught:
                legal_entry.call("jc.read_run", {"run_identity_ref": None}, config)
            self.assertEqual(str(caught.exception), "jc_state_root_not_configured")

    def test_bogus_run_ref_is_named_jc_failure_not_fake_success(self):
        config = _config(Path(self.enterContext(_tempdir())))
        bogus = {"kind": "run-identity", "digest": "sha256:" + "00" * 32}
        with self.assertRaises(legal_entry.JCMethodFailure) as caught:
            legal_entry.call("jc.read_run", {"run_identity_ref": bogus}, config)
        self.assertIn("AUDIT_NOT_FOUND", str(caught.exception))

    def test_cli_roundtrip_evaluate_then_cross_process_readback(self):
        tmp = Path(self.enterContext(_tempdir()))
        config = _config(tmp)
        request = {
            "method": "jc.evaluate",
            "args": {"bundle": {
                "case_id": "business-case",
                "decision_time": "2026-09-11T00:00:00Z",
                "business_tasks": [BUSINESS_TASK],
            }},
        }
        proc, payload = _run_cli(request, config, tmp)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertEqual(payload["status"], "OWNER_RESPONSE")
        run_ref = payload["result"]["run_identity_ref"]
        self.assertEqual(run_ref["kind"], "run-identity")
        # cross-process owner read-back through the real CLI entry
        proc2, payload2 = _run_cli(
            {"method": "jc.read_run", "args": {"run_identity_ref": run_ref}},
            config, tmp)
        self.assertEqual(proc2.returncode, 0, proc2.stdout + proc2.stderr)
        self.assertEqual(payload2["status"], "OWNER_RESPONSE")
        self.assertEqual(payload2["result"]["run_identity_ref"], run_ref)
        self.assertEqual(payload2["result"]["request_id"], "local-business-case")
        # unknown method through the CLI: NOT_CONNECTED exit 3, named code
        proc3, payload3 = _run_cli({"method": "jc.calculate_deadlines", "args": {}},
                                   config, tmp)
        self.assertEqual(proc3.returncode, 3)
        self.assertEqual(payload3["status"], "NOT_CONNECTED")
        self.assertTrue(payload3["code"].startswith("jc_method_not_in_frozen_list:"))
        # missing config through the CLI: NOT_CONNECTED exit 3
        proc4, payload4 = _run_cli({"method": "jc.read_run", "args": {}}, {}, tmp)
        self.assertEqual(proc4.returncode, 3)
        self.assertEqual(payload4["status"], "NOT_CONNECTED")
        self.assertEqual(payload4["code"], "jc_state_root_not_configured")
        # JC-side failure through the CLI: JC_FAILURE exit 4, named code
        bogus = {"kind": "run-identity", "digest": "sha256:" + "00" * 32}
        proc5, payload5 = _run_cli(
            {"method": "jc.read_run", "args": {"run_identity_ref": bogus}},
            config, tmp)
        self.assertEqual(proc5.returncode, 4)
        self.assertEqual(payload5["status"], "JC_FAILURE")
        self.assertIn("AUDIT_NOT_FOUND", payload5["code"])


@contextlib.contextmanager
def _tempdir():
    with tempfile.TemporaryDirectory() as name:
        yield Path(name)


if __name__ == "__main__":
    unittest.main()

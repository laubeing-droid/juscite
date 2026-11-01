# -*- coding: utf-8 -*-
"""W3-U05 acceptance: F29 cache partition discipline + F30 airplane mode.

06 rows F29/F30 (both instances desktop/selfhost run the same frozen
surface; the recon tools/PENDING_OWNER_f29_f30_cache_airplane_recon.py is
the full acceptance):

F29 — the bridge exposes cache.plan / cache.fingerprint as PURE DERIVATION
over the SELECTED CORE CACHE (the upstream native promptCacheKey lineage:
ses_ prefix strip, oc28 model-request.ts; shared-prefix ordering,
session/context.ts — both pinned unmodified by the recon). Partition
(IMMUTABLE vs APPEND), prefix fingerprint over the immutable bytes only,
derived invalidation (rule→lineage(+prefix when text re-versioned),
model→lineage only, case→append rotation only), budget gate refusing the
immutable prefix overage by name, NO hit-rate field anywhere, and NO
second cache engine (the face imports hashlib only and stores nothing).

F30 — airplane.status/set/egress_decision: one-click offline posture with
the closed 11-channel egress decision table (E10 inventory §1); while
armed every channel BLOCKED (loopback endpoints stay alive for the two
endpoint-gated channels); the live gates refuse the review_chat model
round and the lcr case retriever BEFORE any connection; offline read/calc
faces are never gated. The upstream desktop landing is
implementation/patches/017 (verify_patch prestate).

All materials are synthetic engineering fixtures; no %APPDATA%, no
network, oc28 read-only.
"""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE / "python"))
import legal_entry  # noqa: E402

OC28 = Path(r"D:\Codex\1.法律工作区\jusbench工作区\oc28")
PATCH_017 = HERE / "patches" / "017-f30-airplane-mode.patch"

BASE_PLAN_ARGS = {
    "affinity": "ses_" + "a" * 64,
    "model": "deepseek-byok/deepseek-chat",
    "case": {"case_id": "m-synth-1", "case_version": "v3"},
    "rules": {"jc.rules.deadline": "1.0.0"},
    "immutable_segments": [
        {"name": "system", "text": "律引系统提示（合成）"},
        {"name": "rulepack:deadline", "text": "D01..D14 frozen text (synthetic)"},
    ],
    "append_segments": [
        {"name": "case:events", "text": "2026-10-17 立案（合成事件）"},
    ],
    "budget_bytes": 4096,
}


def call(method, args, config=None):
    return legal_entry.call(method, args, config or {})


def call_cli(method, args, config):
    with tempfile.TemporaryDirectory() as tmp:
        req = Path(tmp) / "request.json"
        cfg = Path(tmp) / "config.json"
        req.write_text(json.dumps({"method": method, "args": args},
                                  ensure_ascii=False), encoding="utf-8")
        cfg.write_text(json.dumps(config, ensure_ascii=False), encoding="utf-8")
        proc = subprocess.run(
            [sys.executable, "-X", "utf8", str(HERE / "python" / "legal_entry.py"),
             "--request-json", str(req), "--config", str(cfg)],
            capture_output=True, text=True, encoding="utf-8", timeout=120)
        try:
            payload = json.loads(proc.stdout)
        except json.JSONDecodeError:
            payload = {"status": "RAW", "stdout": proc.stdout[:300]}
        return proc.returncode, payload


class F29CachePartition(unittest.TestCase):
    def test_plan_partition_and_fingerprints(self):
        out = call("cache.plan", dict(BASE_PLAN_ARGS))
        self.assertEqual(out["schema"], "lvyin-cache-partition/1")
        self.assertEqual(set(out), {"schema", "partition", "native_cache_key",
                                    "prefix_fingerprint", "append_partition_key",
                                    "lineage_key", "budget"})
        self.assertEqual(out["native_cache_key"], "a" * 64)  # ses_ strip (oc28 transform)
        self.assertEqual(out["partition"]["immutable"]["segments"],
                         ["system", "rulepack:deadline"])
        self.assertEqual(out["partition"]["append"]["segments"], ["case:events"])
        # prefix fingerprint = immutable bytes ONLY (utility agrees)
        fp = call("cache.fingerprint",
                  {"segments": BASE_PLAN_ARGS["immutable_segments"]})
        self.assertEqual(fp["prefix_fingerprint"], out["prefix_fingerprint"])
        self.assertEqual(fp["bytes"], out["budget"]["immutable_bytes"])
        # append content is not part of the prefix fingerprint
        mutated = dict(BASE_PLAN_ARGS)
        mutated["append_segments"] = [
            {"name": "case:events", "text": "完全不同的变动内容（合成）"}]
        self.assertEqual(call("cache.plan", mutated)["prefix_fingerprint"],
                         out["prefix_fingerprint"])

    def test_determinism_and_order_sensitivity(self):
        a = call("cache.plan", dict(BASE_PLAN_ARGS))
        b = call("cache.plan", json.loads(json.dumps(BASE_PLAN_ARGS)))
        self.assertEqual(json.dumps(a, sort_keys=True), json.dumps(b, sort_keys=True))
        reordered = dict(BASE_PLAN_ARGS)
        reordered["immutable_segments"] = list(
            reversed(BASE_PLAN_ARGS["immutable_segments"]))
        self.assertNotEqual(call("cache.plan", reordered)["prefix_fingerprint"],
                            a["prefix_fingerprint"])

    def test_invalidation_matrix(self):
        base = call("cache.plan", dict(BASE_PLAN_ARGS))
        # rule pack version bump → lineage rotates; prefix bytes unchanged
        rule = json.loads(json.dumps(BASE_PLAN_ARGS))
        rule["rules"] = {"jc.rules.deadline": "1.0.1"}
        r = call("cache.plan", rule)
        self.assertNotEqual(r["lineage_key"], base["lineage_key"])
        self.assertEqual(r["prefix_fingerprint"], base["prefix_fingerprint"])
        self.assertEqual(r["append_partition_key"], base["append_partition_key"])
        # model change → lineage only
        model = json.loads(json.dumps(BASE_PLAN_ARGS))
        model["model"] = "ollama-local/qwen3"
        m = call("cache.plan", model)
        self.assertNotEqual(m["lineage_key"], base["lineage_key"])
        self.assertEqual(m["prefix_fingerprint"], base["prefix_fingerprint"])
        self.assertEqual(m["append_partition_key"], base["append_partition_key"])
        # case version change → append partition rotation ONLY
        case = json.loads(json.dumps(BASE_PLAN_ARGS))
        case["case"] = {"case_id": "m-synth-1", "case_version": "v4"}
        c = call("cache.plan", case)
        self.assertNotEqual(c["append_partition_key"], base["append_partition_key"])
        self.assertEqual(c["prefix_fingerprint"], base["prefix_fingerprint"])
        self.assertEqual(c["lineage_key"], base["lineage_key"])
        # rule TEXT re-versioned → prefix bytes + lineage + append all rotate
        text = json.loads(json.dumps(BASE_PLAN_ARGS))
        text["immutable_segments"][1]["text"] = "D01..D15 frozen text v2 (synthetic)"
        t = call("cache.plan", text)
        self.assertNotEqual(t["prefix_fingerprint"], base["prefix_fingerprint"])
        self.assertNotEqual(t["lineage_key"], base["lineage_key"])
        self.assertNotEqual(t["append_partition_key"], base["append_partition_key"])

    def test_budget_gate_named_refusal(self):
        with self.assertRaisesRegex(legal_entry.NotConnected,
                                    "cache_immutable_budget_exceeded"):
            call("cache.plan", dict(BASE_PLAN_ARGS, budget_bytes=8))
        # gate scopes the IMMUTABLE prefix: a huge append never refuses
        immutable_bytes = call("cache.fingerprint",
                               {"segments": BASE_PLAN_ARGS["immutable_segments"]})["bytes"]
        big_append = dict(BASE_PLAN_ARGS, budget_bytes=immutable_bytes,
                          append_segments=[{"name": "case:events",
                                            "text": "x" * 10_000}])
        out = call("cache.plan", big_append)
        self.assertTrue(out["budget"]["within"])
        self.assertEqual(out["budget"]["limit_bytes"], immutable_bytes)
        self.assertGreater(out["budget"]["total_bytes"], 10_000)
        # invalid budget inputs refuse typed
        for bad in (0, -1, "4096", 4096.0, True):
            with self.assertRaises(legal_entry.NotConnected):
                call("cache.plan", dict(BASE_PLAN_ARGS, budget_bytes=bad))

    def test_no_second_cache_engine_and_no_hit_rate(self):
        import ast
        source = (HERE / "python" / "cache_partition.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        modules = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                modules.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                modules.add(node.module)
        self.assertEqual(modules, {"__future__", "hashlib", "bridge_errors"})
        for banned in ("lru_cache", "sqlite3", "shelve", "pickle", "socket",
                       "urllib", "requests", "open(", "Path("):
            self.assertNotIn(banned, source)
        # no module-level mutable store: top-level assignments are constants
        # or frozen constant frozensets only (no dict()/list()/set() state)
        for node in tree.body:
            if isinstance(node, ast.Assign):
                value = node.value
                if isinstance(value, ast.Constant):
                    continue
                if (isinstance(value, ast.Call)
                        and isinstance(value.func, ast.Name)
                        and value.func.id == "frozenset"
                        and len(value.args) == 1
                        and isinstance(value.args[0], (ast.Set, ast.List, ast.Tuple))
                        and all(isinstance(e, ast.Constant) for e in value.args[0].elts)):
                    continue
                self.fail("module-level mutable store found: %s" % ast.dump(node))
        out = call("cache.plan", dict(BASE_PLAN_ARGS))
        blob = json.dumps(out, ensure_ascii=False).lower()
        for banned in ("hit", "rate", "ratio", "percent", "命中率"):
            self.assertNotIn(banned, blob)

    def test_unknown_methods_and_shapes_refuse_typed(self):
        with self.assertRaisesRegex(legal_entry.NotConnected, "method_not_connected"):
            call("cache.warm", {})
        with self.assertRaises(legal_entry.NotConnected):
            call("cache.plan", dict(BASE_PLAN_ARGS, affinity=""))
        with self.assertRaises(legal_entry.NotConnected):
            call("cache.plan", dict(BASE_PLAN_ARGS, case={"case_id": "x"}))
        dup = json.loads(json.dumps(BASE_PLAN_ARGS))
        dup["immutable_segments"].append({"name": "system", "text": "重名（合成）"})
        with self.assertRaises(legal_entry.NotConnected):
            call("cache.plan", dup)

    def test_cli_dispatch(self):
        code, payload = call_cli("cache.plan", dict(BASE_PLAN_ARGS), {})
        self.assertEqual(code, 0)
        self.assertEqual(payload.get("status"), "OWNER_RESPONSE")
        self.assertEqual(payload["result"]["schema"], "lvyin-cache-partition/1")


class F30AirplaneMode(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.state_root = Path(self._tmp.name) / "airplane-state"
        self.config = {"airplane_state_root": str(self.state_root)}
        self.armed = dict(self.config)

    def tearDown(self):
        self._tmp.cleanup()

    def arm(self):
        return call("airplane.set", {"enabled": True, "reason": "合成外勤"}, self.config)

    def test_set_status_flag_shape(self):
        status = call("airplane.status", {}, self.config)
        self.assertFalse(status["enabled"])
        self.assertFalse(status["configured"])
        self.assertEqual(len(status["channels"]), 11)
        armed = self.arm()
        self.assertTrue(armed["enabled"] and armed["configured"])
        flag = json.loads((self.state_root / "airplane-mode.json").read_text(encoding="utf-8"))
        self.assertEqual(flag["enabled"], True)
        self.assertIsInstance(flag["updated_at"], str)
        self.assertEqual(call("airplane.set",
                              {"enabled": False}, self.config)["enabled"], False)
        with self.assertRaisesRegex(legal_entry.NotConnected, "airplane_set_args_invalid"):
            call("airplane.set", {"enabled": "yes"}, self.config)
        with self.assertRaisesRegex(legal_entry.NotConnected,
                                    "airplane_state_root_not_configured"):
            call("airplane.set", {"enabled": True}, {})

    def test_decision_table_armed_blocks_all_channels(self):
        self.arm()
        loopback = {"127.0.0.1", "localhost"}
        for channel in (row["channel"] for row in
                        call("airplane.status", {}, self.config)["channels"]):
            args = {"channel": channel}
            if channel == "case_retriever_http":
                args["endpoint"] = "https://airplane-negtest.example.invalid/v1"
            row = call("airplane.egress_decision", args, self.config)
            if channel in ("model_round_remote", "case_retriever_http"):
                # remote endpoint refused; loopback stays alive (F22 local channel)
                self.assertEqual(row["decision"], "BLOCKED", channel)
                self.assertEqual(row["switch_contribution"], "armed")
                loop_args = dict(args)
                loop_args["endpoint"] = "http://%s:9/x" % sorted(loopback)[0]
                loop_row = call("airplane.egress_decision", loop_args, self.config)
                self.assertEqual(loop_row["decision"], "ALLOWED", channel)
            else:
                self.assertEqual(row["decision"], "BLOCKED", channel)
                self.assertEqual(row["reason_code"],
                                 "airplane_armed_" + channel + "_blocked")

    def test_decision_table_inactive_status_quo_and_standing(self):
        # switch off: bridge-gated channels are ALLOWED (status quo);
        # catalog fetch stays BLOCKED as the STANDING env plane (patch 007)
        row = call("airplane.egress_decision",
                   {"channel": "model_round_remote",
                    "provider_id": "deepseek-byok"}, self.config)
        self.assertEqual(row["decision"], "ALLOWED")
        self.assertEqual(row["switch_contribution"], "inactive")
        row = call("airplane.egress_decision",
                   {"channel": "model_provider_catalog_fetch"}, self.config)
        self.assertEqual(row["decision"], "BLOCKED")
        self.assertEqual(row["switch_contribution"], "standing")
        self.assertEqual(row["reason_code"],
                         "standing_env_opencode_disable_models_fetch")
        for channel in ("webfetch_tool", "self_update_check", "extension_download",
                        "renderer_telemetry_sentry"):
            row = call("airplane.egress_decision", {"channel": channel}, self.config)
            self.assertEqual(row["decision"], "ALLOWED", channel)
            self.assertEqual(row["switch_contribution"], "inactive", channel)
        with self.assertRaisesRegex(legal_entry.NotConnected, "airplane_channel_unknown"):
            call("airplane.egress_decision", {"channel": "carrier_pigeon"}, self.config)

    def test_local_provider_declaration_keeps_model_round_alive(self):
        self.arm()
        config = dict(self.config, airplane_local_providers=["deepseek-byok"])
        row = call("airplane.egress_decision",
                   {"channel": "model_round_remote"}, config)
        self.assertEqual(row["decision"], "ALLOWED")
        self.assertEqual(row["reason_code"], "airplane_loopback_allow")

    def test_live_gate_review_chat_ask_refuses_before_session(self):
        args = {"review_batch_id": "rb-synth", "scope": {"kind": "matter",
                "matterId": "m-1"}, "question": "合成提问"}
        # armed → airplane refusal BEFORE context assembly / session creation
        self.arm()
        code, payload = call_cli("review_chat.ask", args, self.armed)
        self.assertEqual(code, 3)
        self.assertIn("airplane_remote_model_blocked", json.dumps(payload))
        # disarmed (explicit switch off) → the pre-existing unconfigured
        # failure, never an airplane code
        call("airplane.set", {"enabled": False}, self.config)
        code, payload = call_cli("review_chat.ask", args, self.config)
        self.assertNotIn("airplane", json.dumps(payload))

    def test_live_gate_case_retriever_refuses_before_connect(self):
        config = dict(self.armed, cases_contract="lcr/1",
                      cases_url="https://airplane-negtest.example.invalid/v1")
        self.arm()
        code, payload = call_cli("case.search",
                                 {"query": "合成检索词"}, config)
        self.assertEqual(code, 3)
        self.assertIn("airplane_remote_case_retriever_blocked", json.dumps(payload))
        # disarmed: gate inactive — the failure is whatever the unconfigured
        # downstream does, never an airplane code
        call("airplane.set", {"enabled": False}, self.config)
        config_off = dict(self.config, cases_contract="lcr/1",
                          cases_url="https://airplane-negtest.example.invalid/v1")
        code, payload = call_cli("case.search", {"query": "合成检索词"}, config_off)
        self.assertNotIn("airplane", json.dumps(payload))

    def test_unknown_airplane_methods_refuse(self):
        with self.assertRaisesRegex(legal_entry.NotConnected, "method_not_connected"):
            call("airplane.broadcast", {}, self.config)

    def test_desktop_landing_patch_prestate(self):
        self.assertTrue(PATCH_017.is_file())
        text = PATCH_017.read_text(encoding="utf-8")
        for marker in ("OPENCODE_AIRPLANE_MODE", "airplaneModeEnabled",
                       'ExtensionError("airplane")', '"airplane",'):
            self.assertIn(marker, text)
        targets = [
            OC28 / "packages/desktop/src/main/service/background-service.ts",
            OC28 / "packages/desktop/src/main/extension/manager.ts",
            OC28 / "packages/desktop/src/shared/ipc-rpc/extensions.ts",
        ]
        for target in targets:
            self.assertTrue(target.is_file(), str(target))
            proc = subprocess.run(
                [sys.executable, "-X", "utf8",
                 str(HERE.parent / "tools" / "verify_patch.py"),
                 str(PATCH_017), str(target)],
                capture_output=True, text=True, encoding="utf-8", timeout=60)
            self.assertEqual(proc.returncode, 0, proc.stdout)
            self.assertIn("PASS", proc.stdout)


if __name__ == "__main__":
    unittest.main()

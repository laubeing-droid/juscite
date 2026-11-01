"""F47 产品侧接线测试（W2b-U11）：提案/bake 不变式方法组。

全部合成材料。legal_entry 新增 HARNESS_FORMAL_PROPOSAL_METHODS 四方法组，
走 --formalproposal-json 封闭信封（subprocess seam 注入，单测零仓依赖；
真 public_entry 全链实跑对账在
tools/PENDING_OWNER_f47_proposal_bake_recon.py）。fail-closed：未配置桥＝
NOT_CONNECTED（exit 3 具名），绝不空响应冒成功。

合同要点（harness docs/f47-proposal-bake-contract.md）：提案/base/canonical
三分分开（提案行永不落版本链）；状态机 pending/accepted/rejected/
superseded（reject＝人说不、superseded＝被取代，分列）；确认（formal_
decide accept）才登记新干净版本（source=user_accept ∈ F114 闭集）；
base 漂移具名拒不猜改。桥只路由不解释——状态机与 bake 真值校验全部在
harness 公开面。
"""

from __future__ import annotations

import json
import sys
import unittest
import unittest.mock
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python"))

import legal_entry  # noqa: E402
from bridge_errors import HarnessCommandError, NotConnected  # noqa: E402

CONFIG = {
    "harness_public_entry": "X:/synth/harness/public_entry.py",
    "harness_target": "opencode",
    "harness_state_root": "X:/synth/state-root",
    "harness_python": sys.executable,
}
SCOPE = {"kind": "matter", "matterId": "m-f47"}
F47_METHODS = (
    "harness.formal_propose", "harness.formal_decide",
    "harness.formal_proposal_read", "harness.formal_proposal_list",
)


def fake_entry_output(result):
    return json.dumps({"surface": "formalproposal", "method": "synthetic",
                       "result": result})


def patch_execute(testcase, *, stdout="", returncode=0, calls=None):
    def _fake(argv, env, timeout):
        if calls is not None:
            calls.append({"argv": argv, "env": env})
        return SimpleNamespace(stdout=stdout, returncode=returncode)
    patcher = unittest.mock.patch.object(legal_entry, "_execute", _fake)
    patcher.start()
    testcase.addCleanup(patcher.stop)


def command_key(request_id: str) -> dict:
    return {"requestId": request_id, "targetId": None,
            "expectedRevision": None, "inputRefs": []}


class F47BridgeTests(unittest.TestCase):
    """legal_entry 四方法：白名单、formalproposal 信封、fail-closed。"""

    def test_method_group_membership(self) -> None:
        self.assertEqual(legal_entry.HARNESS_FORMAL_PROPOSAL_METHODS,
                         frozenset(F47_METHODS))
        # 伪方法（跳过决定面直接 bake / 直改提案状态）不在冻结组。
        self.assertNotIn("harness.formal_bake",
                         legal_entry.HARNESS_FORMAL_PROPOSAL_METHODS)
        self.assertNotIn("harness.formal_set_state",
                         legal_entry.HARNESS_FORMAL_PROPOSAL_METHODS)

    def test_all_methods_ride_formalproposal_envelope(self) -> None:
        for method in F47_METHODS:
            with self.subTest(method=method):
                captured: list[dict] = []

                def _capture(argv, env, timeout):
                    captured.append({
                        "argv": list(argv),
                        "envelope": json.loads(Path(
                            argv[argv.index("--formalproposal-json") + 1]
                        ).read_text(encoding="utf-8"))})
                    return SimpleNamespace(
                        stdout=fake_entry_output({"receipt": "synthetic"}),
                        returncode=0)

                patcher = unittest.mock.patch.object(legal_entry, "_execute",
                                                     _capture)
                patcher.start()
                self.addCleanup(patcher.stop)
                result = legal_entry.call(method, {
                    "actor_id": "assistant-1", "scope": SCOPE,
                    "key": command_key("r-1"), "proposal": {
                        "proposalId": "fp-1", "materialId": "mat-f47",
                        "baseRevision": 2, "bytesB64": "c3ludGg=",
                        "channel": "word", "author": "assistant-synth",
                        "quotes": [], "note": None}}, CONFIG)
                self.assertEqual(result, {"receipt": "synthetic"})
                argv = captured[0]["argv"]
                self.assertIn("--formalproposal-json", argv)
                for other in ("--materials-json", "--goal-json",
                              "--schedule-json", "--reviewbatch-json"):
                    self.assertNotIn(other, argv)
                self.assertIn("opencode", argv)
                envelope = captured[0]["envelope"]
                self.assertEqual(envelope["method"], method)

    def test_decide_params_verbatim(self) -> None:
        # 桥只路由：decide 参数（部分接受 resultBytesB64）原样进信封，
        # 不在产品侧解释状态机。
        params = {"actor_id": "lawyer-1", "scope": SCOPE,
                  "key": command_key("dec-1"),
                  "decision": {"proposalId": "fp-1", "action": "accept",
                               "reasonRef": {"owner": "harness",
                                             "kind": "reason", "id": "r-1",
                                             "version": "1",
                                             "matterId": "m-f47"},
                               "receiptRef": {"owner": "harness",
                                              "kind": "receipt",
                                              "id": "rc-1", "version": "1",
                                              "matterId": "m-f47"},
                               "resultBytesB64": "c3ludGg="}}
        captured: list[dict] = []

        def _capture(argv, env, timeout):
            captured.append({
                "argv": list(argv),
                "envelope": json.loads(Path(
                    argv[argv.index("--formalproposal-json") + 1]
                ).read_text(encoding="utf-8"))})
            return SimpleNamespace(stdout=fake_entry_output({"baked": True}),
                                   returncode=0)

        patcher = unittest.mock.patch.object(legal_entry, "_execute", _capture)
        patcher.start()
        self.addCleanup(patcher.stop)
        legal_entry.call("harness.formal_decide", params, CONFIG)
        self.assertEqual(captured[0]["envelope"]["params"], params)

    def test_state_machine_typed_codes_surface_through_bridge(self) -> None:
        # 状态机/漂移拒经桥透传（harness 面码原样上浮，桥不吞不改）。
        for code in ("formal_proposal_state_invalid:superseded",
                     "formal_proposal_base_stale:2:3",
                     "formal_proposal_id_conflict:fp-1"):
            with self.subTest(code=code):
                patch_execute(self, stdout=json.dumps({
                    "surface": "formalproposal", "error": code}), returncode=1)
                with self.assertRaisesRegex(HarnessCommandError,
                                            code.split(":")[0]):
                    legal_entry.call("harness.formal_decide", {
                        "actor_id": "lawyer-1", "scope": SCOPE,
                        "key": command_key("dec-x"),
                        "decision": {"proposalId": "fp-1",
                                     "action": "accept",
                                     "reasonRef": {}, "receiptRef": {}}},
                        CONFIG)

    def test_unconfigured_and_unknown_fail_closed(self) -> None:
        calls: list[dict] = []
        patch_execute(self, stdout=fake_entry_output({}), calls=calls)
        with self.assertRaisesRegex(NotConnected,
                                    "harness_public_entry_not_configured"):
            legal_entry.call("harness.formal_propose",
                             {"scope": SCOPE}, {})
        with self.assertRaisesRegex(NotConnected,
                                    "harness_target_not_configured"):
            legal_entry.call("harness.formal_propose",
                             {"scope": SCOPE},
                             {"harness_public_entry": "X:/synth/entry.py"})
        with self.assertRaisesRegex(NotConnected, "method_not_connected"):
            legal_entry.call("harness.formal_bake",
                             {"scope": SCOPE}, CONFIG)
        with self.assertRaisesRegex(NotConnected, "harness_params_invalid"):
            legal_entry.call("harness.formal_decide",
                             ["not-a-dict"], CONFIG)
        self.assertEqual(calls, [])

    def test_protocol_invalid_never_surfaces_stderr(self) -> None:
        # 非 JSON stdout（或 stderr 内容）不透传——只落具名协议错。
        patch_execute(self, stdout="not-json", returncode=1)
        with self.assertRaisesRegex(HarnessCommandError,
                                    "harness_entry_protocol_invalid"):
            legal_entry.call("harness.formal_proposal_list",
                             {"scope": SCOPE, "material_id": "mat-f47"},
                             CONFIG)


if __name__ == "__main__":
    unittest.main()

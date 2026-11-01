"""F25 产品侧接线测试（W2b-U01）：行租约与格generation写守卫方法组。

全部合成材料。legal_entry 新增 HARNESS_BATCH_REVIEW_METHODS 十方法组，走
--reviewbatch-json 封闭信封（subprocess seam 注入，单测零仓依赖；真
public_entry 全链实跑对账在 tools/PENDING_OWNER_f25_lease_generation_recon.py）。
fail-closed：未配置桥＝NOT_CONNECTED（exit 3 具名），绝不空响应冒成功。

合同要点（harness docs/f25-lease-generation-contract.md）：DB 行级租约＋
generation_id 写守卫＋claim 后快照；过期租约/旧 generation 迟到结果具名拒
（lease_expired/lease_not_held/stale_generation），不覆新结果或人工改格；
批量暂停停发新租约、resume 显式续跑。桥只路由不解释——租约与 generation
真值校验全部在 harness 公开面。
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
SCOPE = {"kind": "matter", "matterId": "m-f25"}
F25_METHODS = (
    "harness.review_batch_create", "harness.review_batch_claim",
    "harness.review_batch_submit", "harness.review_batch_human_edit",
    "harness.review_batch_release", "harness.review_batch_pause",
    "harness.review_batch_resume", "harness.review_batch_read",
    "harness.review_batch_claim_log", "harness.review_batch_list",
)


def fake_entry_output(result):
    return json.dumps({"surface": "reviewbatch", "method": "synthetic",
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


class F25BridgeTests(unittest.TestCase):
    """legal_entry 十方法：白名单、reviewbatch 信封、fail-closed。"""

    def test_method_group_membership(self) -> None:
        self.assertEqual(legal_entry.HARNESS_BATCH_REVIEW_METHODS,
                         frozenset(F25_METHODS))
        # 伪方法（强抢租约/直改 generation）不在冻结组。
        self.assertNotIn("harness.review_batch_force",
                         legal_entry.HARNESS_BATCH_REVIEW_METHODS)
        self.assertNotIn("harness.review_batch_bump_generation",
                         legal_entry.HARNESS_BATCH_REVIEW_METHODS)

    def test_all_methods_ride_reviewbatch_envelope(self) -> None:
        for method in F25_METHODS:
            with self.subTest(method=method):
                captured: list[dict] = []

                def _capture(argv, env, timeout):
                    captured.append({
                        "argv": list(argv),
                        "envelope": json.loads(Path(
                            argv[argv.index("--reviewbatch-json") + 1]
                        ).read_text(encoding="utf-8"))})
                    return SimpleNamespace(
                        stdout=fake_entry_output({"receipt": "synthetic"}),
                        returncode=0)

                patcher = unittest.mock.patch.object(legal_entry, "_execute",
                                                     _capture)
                patcher.start()
                self.addCleanup(patcher.stop)
                result = legal_entry.call(method, {
                    "actor_id": "worker-1", "scope": SCOPE,
                    "key": command_key("r-1"), "batch_id": "brt-synth"},
                    CONFIG)
                self.assertEqual(result, {"receipt": "synthetic"})
                argv = captured[0]["argv"]
                self.assertIn("--reviewbatch-json", argv)
                for other in ("--materials-json", "--goal-json",
                              "--schedule-json"):
                    self.assertNotIn(other, argv)
                self.assertIn("opencode", argv)
                envelope = captured[0]["envelope"]
                self.assertEqual(envelope["method"], method)

    def test_envelope_carries_params_verbatim(self) -> None:
        # 桥只路由：claim 参数（TTL/指定行）原样进信封，不在产品侧解释。
        params = {"actor_id": "worker-1", "scope": SCOPE,
                  "key": command_key("cl-1"), "batch_id": "brt-synth",
                  "row_id": "row-2", "lease_ttl_seconds": 120}
        captured: list[dict] = []

        def _capture(argv, env, timeout):
            captured.append({
                "argv": list(argv),
                "envelope": json.loads(Path(
                    argv[argv.index("--reviewbatch-json") + 1]
                ).read_text(encoding="utf-8"))})
            return SimpleNamespace(stdout=fake_entry_output({"leased": True}),
                                   returncode=0)

        patcher = unittest.mock.patch.object(legal_entry, "_execute", _capture)
        patcher.start()
        self.addCleanup(patcher.stop)
        legal_entry.call("harness.review_batch_claim", params, CONFIG)
        self.assertEqual(captured[0]["envelope"]["params"], params)

    def test_late_result_typed_codes_surface_through_bridge(self) -> None:
        # 三路迟到拒经桥透传（harness 面码原样上浮，桥不吞不改）。
        for code in ("stale_generation:amount:carried=0:current=1",
                     "lease_expired:row-1:2026-10-16T00:00:00Z",
                     "lease_not_held:row-1:done"):
            with self.subTest(code=code):
                patch_execute(self, stdout=json.dumps({
                    "surface": "reviewbatch", "error": code}), returncode=1)
                with self.assertRaisesRegex(HarnessCommandError,
                                            code.split(":")[0]):
                    legal_entry.call("harness.review_batch_submit", {
                        "actor_id": "worker-1", "scope": SCOPE,
                        "key": command_key("sb-1"), "batch_id": "brt-synth",
                        "row_id": "row-1", "lease_token": "tok",
                        "cells": [{"cellId": "amount", "value": "x",
                                   "generation": 0}]}, CONFIG)

    def test_unconfigured_and_unknown_fail_closed(self) -> None:
        calls: list[dict] = []
        patch_execute(self, stdout=fake_entry_output({}), calls=calls)
        with self.assertRaisesRegex(NotConnected,
                                    "harness_public_entry_not_configured"):
            legal_entry.call("harness.review_batch_create",
                             {"scope": SCOPE}, {})
        with self.assertRaisesRegex(NotConnected,
                                    "harness_target_not_configured"):
            legal_entry.call("harness.review_batch_create",
                             {"scope": SCOPE},
                             {"harness_public_entry": "X:/synth/entry.py"})
        with self.assertRaisesRegex(NotConnected, "method_not_connected"):
            legal_entry.call("harness.review_batch_force",
                             {"scope": SCOPE}, CONFIG)
        with self.assertRaisesRegex(NotConnected, "harness_params_invalid"):
            legal_entry.call("harness.review_batch_claim",
                             ["not-a-dict"], CONFIG)
        self.assertEqual(calls, [])

    def test_protocol_invalid_never_surfaces_stderr(self) -> None:
        # 非 JSON stdout（或 stderr 内容）不透传——只落具名协议错。
        patch_execute(self, stdout="not-json", returncode=1)
        with self.assertRaisesRegex(HarnessCommandError,
                                    "harness_entry_protocol_invalid"):
            legal_entry.call("harness.review_batch_list",
                             {"scope": SCOPE}, CONFIG)


if __name__ == "__main__":
    unittest.main()

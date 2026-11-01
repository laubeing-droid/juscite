"""E17 产品侧接线测试（W2b-U25）：取证范围与部分失败方法组。

全部合成材料。legal_entry 新增 HARNESS_EVIDENCE_ATTEMPT_METHODS 八方法
组，走 --evidenceattempt-json 封闭信封（subprocess seam 注入，单测零仓
依赖；真 public_entry 全链＋PG 直连对账在
tools/PENDING_OWNER_e17_evidence_attempt_recon.py）。fail-closed：未配置
桥＝NOT_CONNECTED（exit 3 具名），绝不空响应冒成功。

合同要点（harness docs/e17-evidence-attempt-contract.md）：覆盖按
distinct 请求项投影（10 得 4 含 1 不利＝4/10，不用文件数）；没有实际
申请不能记已执行、没有实际收件不能记取得；6 未回应保持未知；真拒绝
与超期必带来源；不利材料进入场景二重评（E15 assessment_delta）；同 4
项重发/重导不变 8/10、费用幂等不双计；关闭＝律师决定面，任务完成与
证明缺口分别呈现。桥只路由不解释——账本真值校验全部在 harness 面。
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
from bridge_errors import HarnessCommandError, NotConnected  # noqa: E401

CONFIG = {
    "harness_public_entry": "X:/synth/harness/public_entry.py",
    "harness_target": "opencode",
    "harness_state_root": "X:/synth/state-root",
    "harness_python": sys.executable,
}
SCOPE = {"kind": "matter", "matterId": "m-e17"}
E17_METHODS = (
    "harness.evidence_attempt_register", "harness.evidence_attempt_apply",
    "harness.evidence_attempt_receipt", "harness.evidence_attempt_resolve",
    "harness.evidence_attempt_cost", "harness.evidence_attempt_close",
    "harness.evidence_attempt_read", "harness.evidence_attempt_list",
)


def fake_entry_output(result):
    return json.dumps({"surface": "evidenceattempt", "method": "synthetic",
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


def href(kind: str, ref_id: str) -> dict:
    return {"owner": "harness", "kind": kind, "id": ref_id,
            "version": "1", "matterId": "m-e17"}


def synth_attempt() -> dict:
    return {
        "attemptId": "ea-1",
        "taskRef": href("task", "t-evidence-1"),
        "title": "十项同粒度取证请求（E17 桥合成）",
        "items": [{
            "itemId": f"ev-{number}",
            "proposition": f"待证命题 ev-{number}（合成）",
            "channel": "法院调查令·银行流水（合成渠道）",
            "authorizationRef": href("authorization", f"auth-ev-{number}"),
            "requestScope": {"project": "货款纠纷",
                             "period": "2025-01~2025-12",
                             "subject": "甲公司", "materialType": "银行流水"},
        } for number in range(1, 11)],
        "note": "全合成取证轮",
    }


class E17BridgeTests(unittest.TestCase):
    """legal_entry 八方法：白名单、evidenceattempt 信封、fail-closed。"""

    def test_method_group_membership(self) -> None:
        self.assertEqual(legal_entry.HARNESS_EVIDENCE_ATTEMPT_METHODS,
                         frozenset(E17_METHODS))
        # 伪方法（跳过申请面直记取得/直接改状态/伪造覆盖数字）不在冻结组。
        self.assertNotIn("harness.evidence_attempt_obtain",
                         legal_entry.HARNESS_EVIDENCE_ATTEMPT_METHODS)
        self.assertNotIn("harness.evidence_attempt_set_status",
                         legal_entry.HARNESS_EVIDENCE_ATTEMPT_METHODS)
        self.assertNotIn("harness.evidence_attempt_set_coverage",
                         legal_entry.HARNESS_EVIDENCE_ATTEMPT_METHODS)

    def test_all_methods_ride_evidenceattempt_envelope(self) -> None:
        args_by_method = {
            "harness.evidence_attempt_register": {
                "actor_id": "assistant-1", "scope": SCOPE,
                "key": command_key("reg-1"), "attempt": synth_attempt()},
            "harness.evidence_attempt_apply": {
                "actor_id": "assistant-1", "scope": SCOPE,
                "key": command_key("app-1"),
                "application": {
                    "attemptId": "ea-1", "applications": [{
                        "applicationId": "app-1-ev-2", "itemId": "ev-2",
                        "sourceRefs": [href("application-receipt",
                                            "ar-1")]}]}},
            "harness.evidence_attempt_receipt": {
                "actor_id": "assistant-1", "scope": SCOPE,
                "key": command_key("rcpt-1"),
                "receipt": {
                    "attemptId": "ea-1", "receipts": [{
                        "receiptId": "r-2", "itemId": "ev-2",
                        "materialRef": href("material", "mat-ev-2"),
                        "completeness": "complete", "relevance": "relevant",
                        "adverse": True, "readable": True,
                        "verificationStatus": "pending"}]}},
            "harness.evidence_attempt_resolve": {
                "actor_id": "assistant-1", "scope": SCOPE,
                "key": command_key("res-1"),
                "resolution": {
                    "attemptId": "ea-1", "resolutions": [{
                        "resolutionId": "res-5", "itemId": "ev-5",
                        "resolution": "refused",
                        "sourceRefs": [href("refusal-notice", "fn-5")]}]}},
            "harness.evidence_attempt_cost": {
                "actor_id": "assistant-1", "scope": SCOPE,
                "key": command_key("cost-1"),
                "cost": {"attemptId": "ea-1", "costId": "fee-1",
                         "amountCents": 30000,
                         "sourceRef": href("cost-voucher", "voucher-300")}},
            "harness.evidence_attempt_close": {
                "actor_id": "lawyer-1", "scope": SCOPE,
                "key": command_key("close-1"),
                "close": {"attemptId": "ea-1",
                          "reasonRef": href("decision", "dec-stop"),
                          "followups": [{"itemId": "ev-1",
                                         "nextStep": "stop"}]}},
            "harness.evidence_attempt_read": {
                "scope": SCOPE, "attempt_id": "ea-1"},
            "harness.evidence_attempt_list": {"scope": SCOPE},
        }
        for method in E17_METHODS:
            with self.subTest(method=method):
                captured: list[dict] = []

                def _capture(argv, env, timeout):
                    captured.append({
                        "argv": list(argv),
                        "envelope": json.loads(Path(
                            argv[argv.index("--evidenceattempt-json") + 1]
                        ).read_text(encoding="utf-8"))})
                    return SimpleNamespace(
                        stdout=fake_entry_output({"receipt": "synthetic"}),
                        returncode=0)

                patcher = unittest.mock.patch.object(legal_entry, "_execute",
                                                     _capture)
                patcher.start()
                self.addCleanup(patcher.stop)
                result = legal_entry.call(method, args_by_method[method],
                                          CONFIG)
                self.assertEqual(result, {"receipt": "synthetic"})
                argv = captured[0]["argv"]
                self.assertIn("--evidenceattempt-json", argv)
                for other in ("--materials-json", "--goal-json",
                              "--schedule-json", "--reviewbatch-json",
                              "--formalproposal-json", "--pathevidence-json"):
                    self.assertNotIn(other, argv)
                self.assertIn("opencode", argv)
                envelope = captured[0]["envelope"]
                self.assertEqual(envelope["method"], method)
                self.assertEqual(envelope["params"], args_by_method[method])

    def test_typed_codes_surface_through_bridge(self) -> None:
        # 合同面具名拒（无申请先收件/拒绝无来源/费用凭据双挂/closed 后
        # 事件）经桥透传（harness 面码原样上浮，桥不吞不改）。
        for method, code in (
            ("harness.evidence_attempt_receipt",
             "evidence_receipt_requires_application:ev-1"),
            ("harness.evidence_attempt_resolve",
             "evidence_resolution_source_required"),
            ("harness.evidence_attempt_cost",
             "evidence_cost_source_conflict:harness:cost-voucher:voucher-300:1"),
            ("harness.evidence_attempt_apply",
             "evidence_attempt_state_invalid:closed"),
        ):
            with self.subTest(code=code):
                patch_execute(self, stdout=json.dumps({
                    "surface": "evidenceattempt", "error": code}),
                    returncode=1)
                with self.assertRaisesRegex(HarnessCommandError,
                                            code.split(":")[0]):
                    legal_entry.call(method, {"scope": SCOPE}, CONFIG)

    def test_unconfigured_and_unknown_fail_closed(self) -> None:
        calls: list[dict] = []
        patch_execute(self, stdout=fake_entry_output({}), calls=calls)
        with self.assertRaisesRegex(NotConnected,
                                    "harness_public_entry_not_configured"):
            legal_entry.call("harness.evidence_attempt_register",
                             {"scope": SCOPE}, {})
        with self.assertRaisesRegex(NotConnected,
                                    "harness_target_not_configured"):
            legal_entry.call("harness.evidence_attempt_register",
                             {"scope": SCOPE},
                             {"harness_public_entry": "X:/synth/entry.py"})
        with self.assertRaisesRegex(NotConnected, "method_not_connected"):
            legal_entry.call("harness.evidence_attempt_send",
                             {"scope": SCOPE}, CONFIG)
        with self.assertRaisesRegex(NotConnected, "harness_params_invalid"):
            legal_entry.call("harness.evidence_attempt_read",
                             ["not-a-dict"], CONFIG)
        self.assertEqual(calls, [])

    def test_protocol_invalid_never_surfaces_stderr(self) -> None:
        patch_execute(self, stdout="not-json", returncode=1)
        with self.assertRaisesRegex(HarnessCommandError,
                                    "harness_entry_protocol_invalid"):
            legal_entry.call("harness.evidence_attempt_list",
                             {"scope": SCOPE}, CONFIG)


if __name__ == "__main__":
    unittest.main()

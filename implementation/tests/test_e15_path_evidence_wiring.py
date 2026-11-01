"""E15 产品侧接线测试（W2b-U23）：路径与新证据合同方法组。

全部合成材料。legal_entry 新增 HARNESS_PATH_EVIDENCE_METHODS 十方法组，
走 --pathevidence-json 封闭信封（subprocess seam 注入，单测零仓依赖；
真 public_entry 全链＋真 JC 公开出口实跑对账在
tools/PENDING_OWNER_e15_path_evidence_contract_recon.py）。fail-closed：
未配置桥＝NOT_CONNECTED（exit 3 具名），绝不空响应冒成功。

合同要点（harness docs/e15-path-evidence-contract.md）：issue 窄字段
不得塞额外（请求/抗辩/救济/要件/反证/并列备位重叠及采用是独立公开合
同，未采用卡片不改正式请求）；branchRefs 由 JC 公开出口原样转录，空＝
该 run 无分支显式标记，不由前端制造；未知不伪支持（重评无依据不得签
变化项）。桥只路由不解释——三账真值校验全部在 harness 公开面。
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
SCOPE = {"kind": "matter", "matterId": "m-e15"}
E15_METHODS = (
    "harness.path_candidate_register", "harness.path_candidate_decide",
    "harness.path_candidate_read", "harness.path_candidate_list",
    "harness.assessment_delta_record", "harness.assessment_delta_read",
    "harness.assessment_delta_list",
    "harness.branch_projection_record", "harness.branch_projection_read",
    "harness.branch_projection_list",
)


def fake_entry_output(result):
    return json.dumps({"surface": "pathevidence", "method": "synthetic",
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


def synth_candidate() -> dict:
    return {
        "candidateId": "r1", "pathType": "claim",
        "title": "违约损害赔偿备位主张（E15 桥合成）",
        "basisRefs": [{"owner": "harness", "kind": "fact",
                       "id": "f-contract", "version": "1",
                       "matterId": "m-e15"}],
        "triggerLocator": {
            "materialRef": {"owner": "harness", "kind": "material",
                            "id": "mat-e15", "version": "1",
                            "matterId": "m-e15"},
            "documentId": "doc-1", "pageIndex": 1, "blockId": "b-1"},
        "elements": [
            {"elementId": "el-1", "statement": "合同有效成立",
             "status": "established",
             "factRefs": [], "counterEvidenceRefs": []},
            {"elementId": "el-2", "statement": "损失数额确定",
             "status": "unknown", "factRefs": [], "counterEvidenceRefs": []}],
        "lawVersionRefs": [
            {"ref": {"owner": "codices", "kind": "statute",
                     "id": "WJBS-583", "version": "1", "matterId": None},
             "locator": "GB583 第577条",
             "supportStatus": "verified_locator_only"}],
        "relation": {"kind": "alternative", "targetCandidateIds": ["r2"]},
        "lossOverlap": {"declared": True, "sameLossWith": ["r2"],
                        "note": "同一损失（合成声明）"},
    }


class E15BridgeTests(unittest.TestCase):
    """legal_entry 十方法：白名单、pathevidence 信封、fail-closed。"""

    def test_method_group_membership(self) -> None:
        self.assertEqual(legal_entry.HARNESS_PATH_EVIDENCE_METHODS,
                         frozenset(E15_METHODS))
        # 伪方法（跳过采用决定面直改候选状态 / 自造分支）不在冻结组。
        self.assertNotIn("harness.path_candidate_adopt",
                         legal_entry.HARNESS_PATH_EVIDENCE_METHODS)
        self.assertNotIn("harness.path_candidate_set_state",
                         legal_entry.HARNESS_PATH_EVIDENCE_METHODS)
        self.assertNotIn("harness.branch_projection_synthesize",
                         legal_entry.HARNESS_PATH_EVIDENCE_METHODS)

    def test_all_methods_ride_pathevidence_envelope(self) -> None:
        args_by_method = {
            "harness.path_candidate_register": {
                "actor_id": "assistant-1", "scope": SCOPE,
                "key": command_key("reg-1"), "candidate": synth_candidate()},
            "harness.path_candidate_decide": {
                "actor_id": "lawyer-1", "scope": SCOPE,
                "key": command_key("dec-1"),
                "decision": {"candidateId": "r1", "action": "adopt",
                             "reasonRef": {"owner": "harness",
                                           "kind": "reason", "id": "r-1",
                                           "version": "1",
                                           "matterId": "m-e15"},
                             "receiptRef": {"owner": "harness",
                                            "kind": "receipt", "id": "rc-1",
                                            "version": "1",
                                            "matterId": "m-e15"},
                             "issue": {"id": "issue-r1", "revision": 1,
                                       "title": "采用后正式争点（合成）",
                                       "claimRefs": [], "factRefs": [],
                                       "partyIds": []}}},
            "harness.path_candidate_read": {
                "scope": SCOPE, "candidate_id": "r1"},
            "harness.path_candidate_list": {"scope": SCOPE},
            "harness.assessment_delta_record": {
                "actor_id": "assistant-1", "scope": SCOPE,
                "key": command_key("ad-1"),
                "delta": {"deltaId": "ad-1", "changeReason": "material",
                          "oldInputRefs": [], "newInputRefs": [],
                          "items": []}},
            "harness.assessment_delta_read": {
                "scope": SCOPE, "delta_id": "ad-1"},
            "harness.assessment_delta_list": {"scope": SCOPE},
            "harness.branch_projection_record": {
                "actor_id": "system-1", "scope": SCOPE,
                "key": command_key("bp-1"),
                "projection": {"projectionId": "bp-1",
                               "jcRunRef": {"owner": "jc",
                                            "kind": "run-identity",
                                            "id": "run-1", "version": "1",
                                            "matterId": "m-e15"},
                               "jcGraphRef": {"owner": "jc",
                                              "kind": "argument-graph",
                                              "id": "g-1", "version": "1",
                                              "matterId": "m-e15"},
                               "profile": "SYNTHETIC", "branches": []}},
            "harness.branch_projection_read": {
                "scope": SCOPE, "projection_id": "bp-1"},
            "harness.branch_projection_list": {"scope": SCOPE},
        }
        for method in E15_METHODS:
            with self.subTest(method=method):
                captured: list[dict] = []

                def _capture(argv, env, timeout):
                    captured.append({
                        "argv": list(argv),
                        "envelope": json.loads(Path(
                            argv[argv.index("--pathevidence-json") + 1]
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
                self.assertIn("--pathevidence-json", argv)
                for other in ("--materials-json", "--goal-json",
                              "--schedule-json", "--reviewbatch-json",
                              "--formalproposal-json"):
                    self.assertNotIn(other, argv)
                self.assertIn("opencode", argv)
                envelope = captured[0]["envelope"]
                self.assertEqual(envelope["method"], method)
                self.assertEqual(envelope["params"], args_by_method[method])

    def test_typed_codes_surface_through_bridge(self) -> None:
        # 合同面具名拒（窄字段塞额外/无依据签变化/前端造分支 ref）经桥
        # 透传（harness 面码原样上浮，桥不吞不改）。
        for method, code in (
            ("harness.path_candidate_decide",
             "fields_not_closed:['elements']"),
            ("harness.assessment_delta_record",
             "assessment_delta_basis_required:strengthened"),
            ("harness.branch_projection_record",
             "branch_ref_owner_invalid"),
            ("harness.path_candidate_decide",
             "path_candidate_state_invalid:rejected"),
        ):
            with self.subTest(code=code):
                patch_execute(self, stdout=json.dumps({
                    "surface": "pathevidence", "error": code}), returncode=1)
                with self.assertRaisesRegex(HarnessCommandError,
                                            code.split(":")[0]):
                    legal_entry.call(method, {"scope": SCOPE}, CONFIG)

    def test_unconfigured_and_unknown_fail_closed(self) -> None:
        calls: list[dict] = []
        patch_execute(self, stdout=fake_entry_output({}), calls=calls)
        with self.assertRaisesRegex(NotConnected,
                                    "harness_public_entry_not_configured"):
            legal_entry.call("harness.path_candidate_register",
                             {"scope": SCOPE}, {})
        with self.assertRaisesRegex(NotConnected,
                                    "harness_target_not_configured"):
            legal_entry.call("harness.path_candidate_register",
                             {"scope": SCOPE},
                             {"harness_public_entry": "X:/synth/entry.py"})
        with self.assertRaisesRegex(NotConnected, "method_not_connected"):
            legal_entry.call("harness.path_candidate_draft",
                             {"scope": SCOPE}, CONFIG)
        with self.assertRaisesRegex(NotConnected, "harness_params_invalid"):
            legal_entry.call("harness.branch_projection_record",
                             ["not-a-dict"], CONFIG)
        self.assertEqual(calls, [])

    def test_protocol_invalid_never_surfaces_stderr(self) -> None:
        patch_execute(self, stdout="not-json", returncode=1)
        with self.assertRaisesRegex(HarnessCommandError,
                                    "harness_entry_protocol_invalid"):
            legal_entry.call("harness.path_candidate_list",
                             {"scope": SCOPE}, CONFIG)


if __name__ == "__main__":
    unittest.main()

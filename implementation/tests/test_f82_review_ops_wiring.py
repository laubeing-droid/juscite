"""F82 产品侧接线测试（W2b-U31）：复核/单格重跑/人工改格三面方法组。

全部合成材料。legal_entry 新增 HARNESS_REVIEW_OPS_METHODS 四方法（复用
--reviewbatch-json 信封）＋TABULAR_REVIEW_OPS_METHODS 四方法（产品面
tabular_review_ops），桥与产品面经 seam 注入单测（零仓依赖；真全链实跑
对账在 tools/PENDING_OWNER_f82_review_ops_recon.py）。fail-closed：未配置
桥＝NOT_CONNECTED（exit 3 具名），绝不空响应冒成功。

合同要点（harness docs/f82-review-ops-contract.md＋产品面模块头）：
复核回执带 reviewer＋决定 ref、机器分子不动（E11 先例）；单格重跑＝
claim→rerun→release 编排（行租约为授权、格为粒度新 generation；迟到/
旧 generation/人改后重跑三路具名拒不覆人改——typed 码原样上浮不改写）；
人工改格走既有 harness.review_batch_human_edit（F25 组，本面无第二写
通道＝F84 红线）；旧值历史沿版本链回读。
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
import tabular_review_ops  # noqa: E402
from bridge_errors import HarnessCommandError, NotConnected  # noqa: E401

CONFIG = {
    "harness_public_entry": "X:/synth/harness/public_entry.py",
    "harness_target": "opencode",
    "harness_state_root": "X:/synth/state-root",
    "harness_python": sys.executable,
}
SCOPE = {"kind": "matter", "matterId": "m-f82ops"}
H82_METHODS = (
    "harness.review_receipt_record", "harness.review_receipt_read",
    "harness.review_cell_rerun", "harness.review_cell_history",
)
OPS_METHODS = (
    "tabular.review_receipt", "tabular.review_status",
    "tabular.cell_rerun", "tabular.cell_history",
)


def fake_entry_output(result):
    return json.dumps({"surface": "reviewbatch", "method": "synthetic",
                       "result": result})


def patch_execute(testcase, *, stdout="", returncode=0, calls=None,
                  envelopes=None):
    """patch legal_entry._execute；envelopes 列表在假执行器内即时读信封
    （真执行器 finally 即删临时文件——读必须发生在调用窗内）。"""
    def _fake(argv, env, timeout):
        if calls is not None:
            calls.append({"argv": argv, "env": env})
        if envelopes is not None:
            argv = list(argv)
            flag = next((item for item in argv
                         if item.startswith("--") and item.endswith("-json")),
                        None)
            if flag is not None:
                envelopes.append({
                    "flag": flag,
                    "payload": json.loads(Path(
                        argv[argv.index(flag) + 1]).read_text(
                        encoding="utf-8"))})
        return SimpleNamespace(stdout=stdout, returncode=returncode)
    patcher = unittest.mock.patch.object(legal_entry, "_execute", _fake)
    patcher.start()
    testcase.addCleanup(patcher.stop)


def command_key(request_id: str) -> dict:
    return {"requestId": request_id, "targetId": None,
            "expectedRevision": None, "inputRefs": []}


def receipt_args(decision: str = "confirmed") -> dict:
    return {
        "review_batch_id": "brt-f82ops", "row_id": "row-1",
        "cell_id": "amount", "actor_id": "lawyer-1", "scope": SCOPE,
        "key": command_key("rr-1"),
        "receipt": {"reviewer": "lawyer-1", "decision": decision,
                    "decisionRef": "review-note-1"},
    }


class BridgeGroupTests(unittest.TestCase):
    def test_method_group_membership(self) -> None:
        self.assertEqual(
            frozenset(H82_METHODS), legal_entry.HARNESS_REVIEW_OPS_METHODS)
        self.assertEqual(
            frozenset(OPS_METHODS), legal_entry.TABULAR_REVIEW_OPS_METHODS)
        # 人工改格走 F25 组（既有），不在本组重复注册（不建第二写通道）。
        self.assertIn("harness.review_batch_human_edit",
                      legal_entry.HARNESS_BATCH_REVIEW_METHODS)
        self.assertNotIn("harness.review_batch_human_edit",
                         legal_entry.HARNESS_REVIEW_OPS_METHODS)
        for forged in ("tabular.review_sign", "tabular.cell_rerun_force",
                       "harness.review_receipt_autoclose",
                       "harness.review_cell_rerun_overwrite_human"):
            self.assertNotIn(forged, legal_entry.HARNESS_REVIEW_OPS_METHODS)
            self.assertNotIn(forged, legal_entry.TABULAR_REVIEW_OPS_METHODS)

    def test_harness_methods_ride_reviewbatch_envelope(self) -> None:
        envelopes = []
        patch_execute(self, stdout=fake_entry_output({"seq": 1}),
                      envelopes=envelopes)
        result = legal_entry.call(
            "harness.review_receipt_record",
            {"actor_id": "lawyer-1", "scope": SCOPE,
             "key": command_key("rr-1"), "batch_id": "brt-f82ops",
             "row_id": "row-1", "cell_id": "amount",
             "receipt": {"reviewer": "lawyer-1", "decision": "confirmed",
                         "decisionRef": "review-note-1"}}, CONFIG)
        self.assertEqual(result, {"seq": 1})
        self.assertEqual(len(envelopes), 1)
        self.assertEqual(envelopes[0]["flag"], "--reviewbatch-json")
        self.assertEqual(envelopes[0]["payload"]["method"],
                         "harness.review_receipt_record")

    def test_unconfigured_and_unknown_fail_closed(self) -> None:
        with self.assertRaises(NotConnected) as caught:
            legal_entry.call("harness.review_cell_rerun", {},
                             {"harness_target": "opencode"})
        self.assertIn("harness_public_entry_not_configured",
                      str(caught.exception))
        with self.assertRaises(NotConnected) as caught:
            legal_entry.call("tabular.review_sign", {}, CONFIG)
        self.assertIn("method_not_connected:tabular.review_sign",
                      str(caught.exception))


class ReceiptTests(unittest.TestCase):
    def test_receipt_passthrough_with_face(self) -> None:
        envelopes = []
        patch_execute(self, stdout=fake_entry_output({"seq": 2}),
                      envelopes=envelopes)
        result = tabular_review_ops.review_receipt(receipt_args(), CONFIG)
        self.assertEqual(result["seq"], 2)
        self.assertIn("W2b-U31", result["face"])
        payload = envelopes[0]["payload"]
        self.assertEqual(
            payload["params"]["receipt"],
            {"reviewer": "lawyer-1", "decision": "confirmed",
             "decisionRef": "review-note-1"})

    def test_receipt_decision_closed_and_body_closed(self) -> None:
        with self.assertRaises(NotConnected) as caught:
            tabular_review_ops.review_receipt(
                receipt_args(decision="corrected"), CONFIG)
        self.assertIn("tabular_receipt_decision_invalid",
                      str(caught.exception))
        args = receipt_args()
        args["receipt"]["signed"] = True
        with self.assertRaises(NotConnected) as caught:
            tabular_review_ops.review_receipt(args, CONFIG)
        self.assertIn("tabular_receipt_body_invalid", str(caught.exception))
        args = receipt_args()
        del args["receipt"]["decisionRef"]
        with self.assertRaises(NotConnected) as caught:
            tabular_review_ops.review_receipt(args, CONFIG)
        self.assertIn("tabular_receipt_body_invalid", str(caught.exception))

    def test_status_projection_read(self) -> None:
        envelopes = []
        patch_execute(
            self,
            stdout=fake_entry_output({
                "projections": [{"rowId": "row-1", "cellId": "amount",
                                 "reviewStatus": "REVIEWED_CONFIRMED"}],
                "counts": {"REVIEWED_CONFIRMED": 1,
                           "REVIEWED_REJECTED": 0, "NOT_REVIEWED": 0}}),
            envelopes=envelopes)
        result = tabular_review_ops.review_status(
            {"review_batch_id": "brt-f82ops", "row_id": "row-1",
             "cell_id": "amount", "scope": SCOPE}, CONFIG)
        self.assertEqual(result["counts"]["REVIEWED_CONFIRMED"], 1)
        payload = envelopes[0]["payload"]
        self.assertEqual(payload["method"], "harness.review_receipt_read")
        self.assertEqual(payload["params"]["row_id"], "row-1")


class RerunTests(unittest.TestCase):
    def _patch_sequenced(self, steps):
        """按调用序回放合成 harness 结果/异常（claim→rerun→release→
        history 依序）。"""
        state = {"index": 0}

        def _fake(method, args, config):
            index = state["index"]
            state["index"] += 1
            step = steps[index]
            if isinstance(step, Exception):
                raise step
            return step(method, args)
        patcher = unittest.mock.patch.object(
            tabular_review_ops, "_harness_call", _fake)
        patcher.start()
        self.addCleanup(patcher.stop)
        return state

    def test_rerun_orchestration_claim_rerun_release(self) -> None:
        order = []

        def _claim(method, args):
            order.append(method)
            self.assertEqual(method, "harness.review_batch_claim")
            return {"lease": {"token": "lease-1", "claimSeq": 1,
                              "claimedAt": "2026-10-16T00:00:00Z",
                              "expiresAt": "2026-10-16T00:10:00Z"},
                    "snapshot": {"cells": {
                        "amount": {"value": None, "generation": 0,
                                   "source": "initial"}}}}

        def _rerun(method, args):
            order.append(method)
            self.assertEqual(method, "harness.review_cell_rerun")
            self.assertEqual(args["lease_token"], "lease-1")
            self.assertEqual(args["generation"], 0)
            return {"cells": {"amount": {"value": "重跑 101 元",
                                         "generation": 1,
                                         "source": "machine"}},
                    "previousGeneration": 0}

        def _release(method, args):
            order.append(method)
            self.assertEqual(args["release"]["reason"], "cell_rerun_done")
            return {"state": "pending"}

        def _history(method, args):
            order.append(method)
            return {"versions": [{"generation": 0, "value": None,
                                  "source": "initial"}],
                    "current": {"generation": 0}}

        self._patch_sequenced([_claim, _rerun, _release, _history])
        result = tabular_review_ops.cell_rerun({
            "review_batch_id": "brt-f82ops", "row_id": "row-1",
            "cell_id": "amount", "value": "重跑 101 元",
            "actor_id": "worker-1", "scope": SCOPE,
            "key": command_key("ru-1")}, CONFIG)
        self.assertEqual(order, [
            "harness.review_batch_claim", "harness.review_cell_rerun",
            "harness.review_batch_release", "harness.review_cell_history"])
        self.assertEqual(result["cell"]["generation"], 1)
        self.assertEqual(result["rowState"], "pending")
        self.assertEqual(result["leaseTrace"]["claimSeq"], 1)
        self.assertEqual(result["history"]["current"]["generation"], 0)

    def test_rerun_refusal_releases_lease_and_surfaces_typed_code(
            self) -> None:
        order = []

        def _claim(method, args):
            order.append(method)
            return {"lease": {"token": "lease-1", "claimSeq": 1,
                              "claimedAt": "t", "expiresAt": "t2"},
                    "snapshot": {"cells": {
                        "amount": {"value": "人改值", "generation": 2,
                                   "source": "human"}}}}

        def _rerun(method, args):
            order.append(method)
            raise HarnessCommandError(
                "review_rerun_human_cell:amount:generation=2")

        def _release(method, args):
            order.append(method)
            self.assertEqual(args["release"]["reason"],
                             "cell_rerun_aborted")
            return {"state": "pending"}

        state = self._patch_sequenced([_claim, _rerun, _release])
        with self.assertRaises(HarnessCommandError) as caught:
            tabular_review_ops.cell_rerun({
                "review_batch_id": "brt-f82ops", "row_id": "row-1",
                "cell_id": "amount", "value": "777 元",
                "actor_id": "worker-1", "scope": SCOPE,
                "key": command_key("ru-2")}, CONFIG)
        # typed 码原样上浮（不改写不吞）；租约已归还（部分失败恢复）。
        self.assertIn("review_rerun_human_cell:amount",
                      str(caught.exception))
        self.assertEqual(order, ["harness.review_batch_claim",
                                 "harness.review_cell_rerun",
                                 "harness.review_batch_release"])

    def test_rerun_claim_contention_surfaces(self) -> None:
        def _claim(method, args):
            raise HarnessCommandError("batch_claim_contended:brt:['leased']")
        self._patch_sequenced([_claim])
        with self.assertRaises(HarnessCommandError) as caught:
            tabular_review_ops.cell_rerun({
                "review_batch_id": "brt-f82ops", "row_id": "row-1",
                "cell_id": "amount", "value": "1 元",
                "actor_id": "worker-1", "scope": SCOPE,
                "key": command_key("ru-3")}, CONFIG)
        self.assertIn("batch_claim_contended", str(caught.exception))

    def test_rerun_args_closed(self) -> None:
        args = {"review_batch_id": "brt-f82ops", "row_id": "row-1",
                "cell_id": "amount", "value": "1 元",
                "actor_id": "worker-1", "scope": SCOPE,
                "key": command_key("ru-4"), "force": True}
        with self.assertRaises(NotConnected) as caught:
            tabular_review_ops.cell_rerun(args, CONFIG)
        self.assertIn("tabular_rerun_args_invalid", str(caught.exception))
        with self.assertRaises(NotConnected) as caught:
            tabular_review_ops.cell_rerun({
                "review_batch_id": "brt-f82ops", "row_id": "row-1",
                "cell_id": "", "value": "1 元",
                "actor_id": "worker-1", "scope": SCOPE,
                "key": command_key("ru-5")}, CONFIG)
        self.assertIn("tabular_cell_id_required", str(caught.exception))

    def test_rerun_cell_not_in_snapshot(self) -> None:
        def _claim(method, args):
            return {"lease": {"token": "lease-1", "claimSeq": 1,
                              "claimedAt": "t", "expiresAt": "t2"},
                    "snapshot": {"cells": {}}}
        self._patch_sequenced([_claim])
        with self.assertRaises(NotConnected) as caught:
            tabular_review_ops.cell_rerun({
                "review_batch_id": "brt-f82ops", "row_id": "row-1",
                "cell_id": "ghost", "value": "1 元",
                "actor_id": "worker-1", "scope": SCOPE,
                "key": command_key("ru-6")}, CONFIG)
        self.assertIn("tabular_rerun_cell_not_in_snapshot:ghost",
                      str(caught.exception))


class HistoryTests(unittest.TestCase):
    def test_history_passthrough(self) -> None:
        envelopes = []
        patch_execute(
            self,
            stdout=fake_entry_output({
                "versions": [{"generation": 0, "value": None,
                              "source": "initial"},
                             {"generation": 1, "value": "重跑 101 元",
                              "source": "machine"}],
                "versionCount": 2,
                "current": {"generation": 1}}),
            envelopes=envelopes)
        result = tabular_review_ops.cell_history(
            {"review_batch_id": "brt-f82ops", "row_id": "row-1",
             "cell_id": "amount", "scope": SCOPE}, CONFIG)
        self.assertEqual(result["versionCount"], 2)
        payload = envelopes[0]["payload"]
        self.assertEqual(payload["method"], "harness.review_cell_history")
        self.assertEqual(payload["params"]["cell_id"], "amount")

    def test_history_args_closed(self) -> None:
        with self.assertRaises(NotConnected) as caught:
            tabular_review_ops.cell_history(
                {"review_batch_id": "brt-f82ops", "row_id": "row-1",
                 "cell_id": "amount", "scope": SCOPE,
                 "includeDeleted": True}, CONFIG)
        self.assertIn("tabular_history_args_invalid", str(caught.exception))


class HumanEditChannelTests(unittest.TestCase):
    """F82-人改：改格唯一写通道＝harness.review_batch_human_edit（F25 组
    经产品桥），三面方法组不含任何改格方法。"""

    def test_human_edit_rides_batch_review_group(self) -> None:
        envelopes = []
        patch_execute(self, stdout=fake_entry_output({"state": "leased"}),
                      envelopes=envelopes)
        result = legal_entry.call(
            "harness.review_batch_human_edit",
            {"actor_id": "lawyer-1", "scope": SCOPE,
             "key": command_key("he-1"), "batch_id": "brt-f82ops",
             "row_id": "row-1",
             "cells": [{"cellId": "amount", "value": "人改值",
                        "generation": 1}]}, CONFIG)
        self.assertEqual(result, {"state": "leased"})
        payload = envelopes[0]["payload"]
        self.assertEqual(payload["method"],
                         "harness.review_batch_human_edit")


if __name__ == "__main__":
    unittest.main()

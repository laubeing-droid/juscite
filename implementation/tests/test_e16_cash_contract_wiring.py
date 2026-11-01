"""E16 产品侧接线测试（W2b-U51）：款源/转移/退款/分配/余额方法组。

全部合成材料。legal_entry 新增 HARNESS_CASH_METHODS 六方法组（走
--cashcontract-json 封闭信封，subprocess seam 注入，单测零仓依赖）与
CASH_CONTRACT_METHODS 两组（cash.balance/cash.allocate 经 P01 JCClient
钉定面）；真 public_entry 全链＋JC 真算＋PG 直连对账在
tools/PENDING_OWNER_e16_cash_contract_recon.py。fail-closed：未配置桥
＝NOT_CONNECTED（exit 3 具名），JC typed 拒＝JC_FAILURE 携码，绝不空
响应冒成功。

合同要点（harness docs/e16-cash-contract.md）：债权款源专属账不借
record_payment（账单通道）；同源去重＝realityKey；转移必钉既有款源
（source_total 不得 230000）；转移/流出/分配行必带 JC 计算回执 ref
（owner=jc sha256，桥只转录不制造）；减免不是实付、改判不是退款；余
额恒带五列净额向量；金额整分 float 具名拒。
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
from bridge_errors import HarnessCommandError, NotConnected  # noqa: F401
from legal_entry import JCMethodFailure  # noqa: F401

CONFIG = {
    "harness_public_entry": "X:/synth/harness/public_entry.py",
    "harness_target": "opencode",
    "harness_state_root": "X:/synth/state-root",
    "harness_python": sys.executable,
}
SCOPE = {"kind": "matter", "matterId": "m-e16"}
HARNESS_METHODS = (
    "harness.cash_entitlement_register", "harness.cash_source_register",
    "harness.cash_transfer_record", "harness.cash_outflow_record",
    "harness.cash_allocation_record", "harness.cash_balance_read",
)
JC_BALANCE_REF = {
    "owner": "jc", "kind": "cash-balance-sheet",
    "id": "jc-cash-0000000000000000000000000000000000000000",
    "version": "1", "matterId": "m-e16",
    "digest": "sha256:" + "0" * 64,
}


def fake_entry_output(result):
    return json.dumps({"surface": "cashcontract", "method": "synthetic",
                       "result": result})


def patch_execute(testcase, *, stdout="", returncode=0, calls=None):
    def _fake(argv, env, timeout):
        if calls is not None:
            entry = {"argv": argv, "env": env}
            # 临时信封文件在 _harness_provider_entry 的 finally 中删除，
            # 必须在 fake 执行点（unlink 前）读取载荷。
            if "--cashcontract-json" in argv:
                path = Path(argv[argv.index("--cashcontract-json") + 1])
                entry["payload"] = json.loads(
                    path.read_text(encoding="utf-8"))
            calls.append(entry)
        return SimpleNamespace(stdout=stdout, returncode=returncode)
    patcher = unittest.mock.patch.object(legal_entry, "_execute", _fake)
    patcher.start()
    testcase.addCleanup(patcher.stop)


def command_key(request_id: str) -> dict:
    return {"requestId": request_id, "targetId": None,
            "expectedRevision": None, "inputRefs": []}


def href(kind: str, ref_id: str) -> dict:
    return {"owner": "harness", "kind": kind, "id": ref_id,
            "version": "1", "matterId": "m-e16"}


def synth_source(source_id: str = "src-A") -> dict:
    return {
        "sourcePaymentId": source_id, "entitlementId": "ent-1",
        "payer": "被执行人甲（合成）", "payee": "客户（合成）",
        "amountMinor": 3_000_000, "currency": "CNY",
        "realityKey": "bank-tx-A-001",
        "voucherRefs": [href("voucher", f"v-{source_id}")],
        "occurredAt": "2026-03-01", "verifiedAt": "2026-03-02",
        "confirmDecisionRef": href("decision", f"dec-{source_id}"),
        "recoveryPurpose": "本金受偿（合成）", "holder": "client",
        "legalEffectStatus": "declared", "note": "桥测试合成款源",
    }


class E16HarnessBridgeTests(unittest.TestCase):
    """legal_entry 六方法：白名单、cashcontract 信封、fail-closed。"""

    def test_method_group_membership(self) -> None:
        self.assertEqual(legal_entry.HARNESS_CASH_METHODS,
                         frozenset(HARNESS_METHODS))
        # 伪造/旁路方法不在冻结组：不借 record_payment 通道记账债权款源、
        # 无直接改余额/删账方法。
        self.assertNotIn("harness.record_payment",
                         legal_entry.HARNESS_CASH_METHODS)
        self.assertNotIn("harness.cash_balance_write",
                         legal_entry.HARNESS_CASH_METHODS)
        self.assertNotIn("harness.cash_source_delete",
                         legal_entry.HARNESS_CASH_METHODS)

    def test_all_methods_ride_cashcontract_envelope(self) -> None:
        calls: list = []
        args_by_method = {
            "harness.cash_entitlement_register": {
                "actor_id": "assistant-1", "scope": SCOPE,
                "key": command_key("ent-1"), "entitlement": {
                    "entitlementId": "ent-1",
                    "nominalRef": href("judgment", "j-1"),
                    "amountMinor": 12_000_000, "currency": "CNY",
                    "obligor": "被执行人（合成）", "creditor": "客户（合成）",
                    "effectiveEvidenceRefs": [href("document", "d-1")]}},
            "harness.cash_source_register": {
                "actor_id": "assistant-1", "scope": SCOPE,
                "key": command_key("src-1"), "source": synth_source()},
            "harness.cash_transfer_record": {
                "actor_id": "assistant-1", "scope": SCOPE,
                "key": command_key("tr-1"), "transfer": {
                    "transferId": "tr-Q-1",
                    "sourcePaymentId": "src-Q",
                    "fromHolder": "court", "toHolder": "client",
                    "amountMinor": 5_000_000, "currency": "CNY",
                    "voucherRefs": [href("voucher", "v-q")],
                    "occurredAt": "2026-03-20",
                    "jcBalanceRef": JC_BALANCE_REF}},
            "harness.cash_outflow_record": {
                "actor_id": "assistant-1", "scope": SCOPE,
                "key": command_key("out-1"), "outflow": {
                    "outflowId": "out-1", "kind": "refund",
                    "amountMinor": 1_000_000, "currency": "CNY",
                    "voucherRefs": [href("voucher", "v-r")],
                    "occurredAt": "2026-03-15",
                    "jcBalanceRef": JC_BALANCE_REF}},
            "harness.cash_allocation_record": {
                "actor_id": "assistant-1", "scope": SCOPE,
                "key": command_key("al-1"), "allocation": {
                    "allocationId": "al-1", "revision": 1,
                    "sourcePaymentId": "src-A", "projectId": "本金",
                    "amountMinor": 3_000_000, "currency": "CNY",
                    "ruleBasis": {"name": "合成规则"},
                    "jcAllocationRef": {
                        "owner": "jc", "kind": "cash-allocation-sheet",
                        "id": "jc-cash-1", "version": "1",
                        "matterId": "m-e16",
                        "digest": "sha256:" + "1" * 64}}},
            "harness.cash_balance_read": {"scope": SCOPE},
        }
        self.assertEqual(set(args_by_method), set(HARNESS_METHODS))
        for method, args in args_by_method.items():
            patch_execute(self, stdout=fake_entry_output({"ok": True}),
                          calls=calls)
            result = legal_entry.call(method, args, CONFIG)
            self.assertEqual(result, {"ok": True}, method)
            entry = calls[-1]
            argv = entry["argv"]
            self.assertIn("--cashcontract-json", argv, method)
            self.assertEqual(entry["payload"]["method"], method)
            self.assertEqual(entry["payload"]["params"], args)
            self.assertIn("--target", argv)
            self.assertEqual(entry["env"].get("LH_LEGAL_STATE_ROOT"),
                             "X:/synth/state-root")
            self.reset_calls(calls)

    def reset_calls(self, calls: list) -> None:
        calls.clear()

    def test_not_configured_named_refusal(self) -> None:
        for method in HARNESS_METHODS:
            with self.assertRaises(NotConnected) as caught:
                legal_entry.call(method, {"scope": SCOPE}, {})
            self.assertIn("harness_public_entry_not_configured",
                          str(caught.exception), method)

    def test_unknown_method_not_connected(self) -> None:
        with self.assertRaises(NotConnected) as caught:
            legal_entry.call("harness.cash_balance_write",
                             {"scope": SCOPE}, CONFIG)
        self.assertIn("method_not_connected", str(caught.exception))

    def test_typed_ledger_error_surfaced(self) -> None:
        patch_execute(self, stdout=json.dumps(
            {"status": "FAIL",
             "error": "cash_source_reality_duplicate:k-1"}), returncode=1)
        with self.assertRaises(HarnessCommandError) as caught:
            legal_entry.call("harness.cash_source_register",
                             {"actor_id": "a", "scope": SCOPE,
                              "key": command_key("x"),
                              "source": synth_source()}, CONFIG)
        self.assertIn("cash_source_reality_duplicate", str(caught.exception))

    def test_non_dict_params_refused(self) -> None:
        for method in HARNESS_METHODS:
            with self.assertRaises(NotConnected) as caught:
                legal_entry.call(method, "not-a-dict", CONFIG)
            self.assertIn("harness_params_invalid", str(caught.exception),
                          method)


class E16CashContractBridgeTests(unittest.TestCase):
    """cash.balance / cash.allocate：P01 钉定面、fail-closed、typed 映射。"""

    def test_method_group_membership(self) -> None:
        self.assertEqual(legal_entry.CASH_CONTRACT_METHODS,
                         frozenset({"cash.balance", "cash.allocate"}))
        # 无只回总数/无向量形态的方法不在冻结组（净额向量恒在）。
        self.assertNotIn("cash.total", legal_entry.CASH_CONTRACT_METHODS)
        self.assertNotIn("cash.balance_total",
                         legal_entry.CASH_CONTRACT_METHODS)

    def test_not_configured_named_refusal(self) -> None:
        # cash.balance 空 events 直达配置检查；cash.allocate 缺输入先吃
        # cash_allocate_input_required（fail fast 在建 client 之前），带
        # 最小输入才到配置检查。
        with self.assertRaises(NotConnected) as caught:
            legal_entry.call("cash.balance", {"matterId": "m-e16"}, {})
        self.assertIn("jc_state_root_not_configured", str(caught.exception))
        with self.assertRaises(NotConnected) as caught:
            legal_entry.call("cash.allocate",
                             {"matterId": "m-e16",
                              "request": {"sources": []}}, {})
        self.assertIn("jc_state_root_not_configured", str(caught.exception))
        with self.assertRaises(NotConnected) as caught:
            legal_entry.call("cash.allocate", {"matterId": "m-e16"}, {})
        self.assertIn("cash_allocate_input_required", str(caught.exception))

    def test_balance_payload_passthrough(self) -> None:
        events = {"sources": [{"sourcePaymentId": "src-A",
                               "amountMinor": 3_000_000,
                               "realityKey": "k-1", "holder": "client"}]}
        observed: dict = {}

        class FakeClient:
            def cash_balance(self, payload):
                observed.update(payload)
                return {"net_vector": {"client_net_minor": 3_000_000},
                        "cashBalanceRef": JC_BALANCE_REF}

        import unittest.mock
        with unittest.mock.patch.object(
                legal_entry, "_jc_client", return_value=FakeClient()):
            result = legal_entry.call("cash.balance",
                                      {"matterId": "m-e16",
                                       "events": events}, {
                                          "jc_state_root": "X:/s"})
        self.assertEqual(observed["matterId"], "m-e16")
        self.assertEqual(observed["sources"], events["sources"])
        self.assertEqual(result["cashBalanceRef"], JC_BALANCE_REF)

    def test_allocate_requires_input(self) -> None:
        import tempfile
        import unittest.mock
        with tempfile.TemporaryDirectory(prefix="juscite-e16-") as state:
            with self.assertRaises(NotConnected) as caught:
                legal_entry.call("cash.allocate", {"matterId": "m-e16"}, {
                    "jc_state_root": state})
            self.assertIn("cash_allocate_input_required",
                          str(caught.exception))

    def test_jc_typed_error_mapping(self) -> None:
        class FakeClient:
            def cash_balance(self, payload):
                error = JCMethodFailure(
                    "jc_error:cash_source_reality_duplicate:duplicate")
                error.code = "cash_source_reality_duplicate"
                raise error

        import unittest.mock
        with unittest.mock.patch.object(
                legal_entry, "_jc_client", return_value=FakeClient()):
            with self.assertRaises(JCMethodFailure) as caught:
                legal_entry.call("cash.balance", {"matterId": "m-e16",
                                                  "events": {}}, {
                    "jc_state_root": "X:/s"})
        self.assertIn("cash_source_reality_duplicate", str(caught.exception))

    def test_non_dict_params_refused(self) -> None:
        for method in ("cash.balance", "cash.allocate"):
            with self.assertRaises(NotConnected) as caught:
                legal_entry.call(method, ["not", "a", "dict"], CONFIG)
            self.assertIn("cash_contract_params_invalid",
                          str(caught.exception), method)


if __name__ == "__main__":
    unittest.main()

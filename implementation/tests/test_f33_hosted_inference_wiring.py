# -*- coding: utf-8 -*-
"""F33 托管模型积分通道（设备签名短 TTL 凭证，子 Key 不落端）产品面
接线测试（工单 W5-U03）。

06 V7-33 行（v2；owner=product；B5）acceptance＝托管短TTL凭证过期失效；
设备/额度绑定；子key不落端。合成先行（裁决#13-19）：真实网关 v2 商业化
时补；本面不接入 legal_entry（UI_HOST_OR_NEW_PRODUCT：不冒已有业务入口）。

合同硬点（本测试主战场）：
  - TTL 过期失效：clock 可注入；exp 后 typed hosted_credential_expired
    且零扣减；边界 exp 当刻仍有效（≤60s 短 TTL 语义）；
  - 设备绑定：异设备到账 hosted_device_mismatch；异钥异名签名
    hosted_signature_invalid（签名覆盖 device_id）；
  - 额度绑定（整型分）：超额签发 hosted_quota_exceeded 零扣减；浮点/
    bool 额度 hosted_quota_not_integer（bool 是 int 子类显式拒）；扣减
    整型精确；重放 hosted_credential_replayed 零双扣；凭证篡改
    hosted_credential_invalid（token 覆盖全字段）；
  - 子key不落端：device_key 经 F12 凭据保险库（DPAPI 密文，落盘零明
    文）；全部回执/凭证 JSON 面、保险库落盘字节零子key；
  - 面纪律：零网络零子进程零 print/logging 零 open；sub_key 名只存在于
    HostedGateway.__init__；legal_entry 零 hosted 接线（不创第二业务
    入口/第二 Agent loop）。

全程合成材料（内存密钥＋临时目录；零真实网关零真实外联）。
"""

from __future__ import annotations

import ast
import base64
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python"))

import hosted_inference  # noqa: E402
from hosted_inference import (  # noqa: E402
    HostedError, HostedGateway, device_signature, new_nonce,
    request_session, store_device_key,
)

HOSTED = ROOT / "python" / "hosted_inference.py"
LEGAL_ENTRY = ROOT / "python" / "legal_entry.py"

SUB_KEY = b"w5u03-synthetic-sub-key-0123456789abcdef"  # 合成子key（仅测试）
START_FEN = 1_500_000  # 整型分（=¥15000.00）


def _code(callable_):
    try:
        callable_()
    except HostedError as exc:
        return str(exc)
    raise AssertionError("expected HostedError")


def _fresh_gateway(clock=None) -> HostedGateway:
    import time
    return HostedGateway(SUB_KEY, START_FEN, clock=clock or time.time)


def _provision_pair(root: str, device_id: str, gateway) -> None:
    receipt = gateway.provision_device(device_id)
    store_device_key(root, device_id,
                     base64.b64decode(receipt["device_key_b64"]))


class F33HappyPath(unittest.TestCase):
    def test_issue_verify_exact_integer_deduction(self):
        with tempfile.TemporaryDirectory(prefix="f33-t-") as root:
            gateway = _fresh_gateway()
            _provision_pair(root, "dev-a", gateway)
            out = request_session(gateway, root, "dev-a", 250_000)
            self.assertIn("credential", out)
            ver = gateway.verify_session(out["credential"], "dev-a")
            self.assertTrue(ver["accepted"])
            self.assertEqual(ver["charged_fen"], 250_000)
            self.assertEqual(ver["remaining_quota_fen"], START_FEN - 250_000)
            self.assertIsInstance(ver["remaining_quota_fen"], int)

    def test_two_sessions_sum_exactly(self):
        with tempfile.TemporaryDirectory(prefix="f33-t-") as root:
            gateway = _fresh_gateway()
            _provision_pair(root, "dev-a", gateway)
            first = request_session(gateway, root, "dev-a", 100_000)
            second = request_session(gateway, root, "dev-a", 250_000)
            gateway.verify_session(first["credential"], "dev-a")
            gateway.verify_session(second["credential"], "dev-a")
            self.assertEqual(gateway.remaining_quota_fen,
                             START_FEN - 350_000)


class F33TtlExpiry(unittest.TestCase):
    def test_expired_typed_reject_no_charge(self):
        t0 = 1_000_000.0
        gateway = HostedGateway(SUB_KEY, START_FEN, clock=lambda: t0)
        with tempfile.TemporaryDirectory(prefix="f33-t-") as root:
            _provision_pair(root, "dev-a", gateway)
            out = request_session(gateway, root, "dev-a", 100_000)
        gateway.clock = lambda: t0 + 60 + 0.001  # exp 后一瞬
        with self.assertRaises(HostedError) as caught:
            gateway.verify_session(out["credential"], "dev-a")
        self.assertEqual(str(caught.exception), "hosted_credential_expired")
        self.assertEqual(gateway.remaining_quota_fen, START_FEN)

    def test_boundary_exp_moment_still_valid(self):
        t0 = 2_000_000.0
        gateway = HostedGateway(SUB_KEY, START_FEN, clock=lambda: t0)
        with tempfile.TemporaryDirectory(prefix="f33-t-") as root:
            _provision_pair(root, "dev-a", gateway)
            out = request_session(gateway, root, "dev-a", 100_000)
        gateway.clock = lambda: t0 + 60  # exp 当刻（≤60s 语义内）
        ver = gateway.verify_session(out["credential"], "dev-a")
        self.assertTrue(ver["accepted"])

    def test_credential_ttl_is_le_60s_by_default(self):
        gateway = _fresh_gateway()
        with tempfile.TemporaryDirectory(prefix="f33-t-") as root:
            _provision_pair(root, "dev-a", gateway)
            out = request_session(gateway, root, "dev-a", 100_000)
        cred = out["credential"]
        self.assertLessEqual(cred["ttl_s"], 60)
        self.assertEqual(cred["exp"] - cred["issued_at"], cred["ttl_s"])


class F33DeviceBinding(unittest.TestCase):
    def test_device_mismatch_typed_reject_no_charge(self):
        with tempfile.TemporaryDirectory(prefix="f33-t-") as root:
            gateway = _fresh_gateway()
            _provision_pair(root, "dev-a", gateway)
            out = request_session(gateway, root, "dev-a", 100_000)
            _provision_pair(root, "dev-b", gateway)
            with self.assertRaises(HostedError) as caught:
                gateway.verify_session(out["credential"], "dev-b")
            self.assertEqual(str(caught.exception), "hosted_device_mismatch")
            self.assertEqual(gateway.remaining_quota_fen, START_FEN)

    def test_signature_covers_device_id(self):
        with tempfile.TemporaryDirectory(prefix="f33-t-") as root:
            gateway = _fresh_gateway()
            _provision_pair(root, "dev-a", gateway)
            _provision_pair(root, "dev-b", gateway)
            key_a = hosted_inference.load_device_key(root, "dev-a")
            nonce = new_nonce()
            # dev-a 的钥签 dev-b 的名——签名绑定设备身份，异名必拒。
            sig = device_signature(key_a, "dev-b", nonce, 100_000)
            with self.assertRaises(HostedError) as caught:
                gateway.issue_session("dev-b", sig, nonce, 100_000)
            self.assertEqual(str(caught.exception), "hosted_signature_invalid")

    def test_wrong_key_signature_rejected(self):
        gateway = _fresh_gateway()
        gateway.provision_device("dev-a")
        nonce = new_nonce()
        sig = device_signature(b"wrong-key-bytes-0123456789abcdef",
                               "dev-a", nonce, 100_000)
        with self.assertRaises(HostedError) as caught:
            gateway.issue_session("dev-a", sig, nonce, 100_000)
        self.assertEqual(str(caught.exception), "hosted_signature_invalid")

    def test_unregistered_device_rejected(self):
        gateway = _fresh_gateway()
        sig = device_signature(b"k" * 32, "ghost", new_nonce(), 100_000)
        with self.assertRaises(HostedError) as caught:
            gateway.issue_session("ghost", sig, new_nonce(), 100_000)
        self.assertEqual(str(caught.exception), "hosted_device_not_registered")


class F33QuotaBinding(unittest.TestCase):
    def test_over_quota_issue_rejected_no_charge(self):
        with tempfile.TemporaryDirectory(prefix="f33-t-") as root:
            gateway = _fresh_gateway()
            _provision_pair(root, "dev-a", gateway)
            with self.assertRaises(HostedError) as caught:
                request_session(gateway, root, "dev-a", START_FEN + 1)
            self.assertEqual(str(caught.exception), "hosted_quota_exceeded")
            self.assertEqual(gateway.remaining_quota_fen, START_FEN)

    def test_float_and_bool_fen_rejected(self):
        gateway = _fresh_gateway()
        with tempfile.TemporaryDirectory(prefix="f33-t-") as root:
            _provision_pair(root, "dev-a", gateway)
            for bad in (1.5, True, False, "100", None):
                with self.assertRaises(HostedError) as caught:
                    request_session(gateway, root, "dev-a", bad)
                self.assertEqual(str(caught.exception),
                                 "hosted_quota_not_integer")
            self.assertEqual(gateway.remaining_quota_fen, START_FEN)

    def test_replay_rejected_no_double_charge(self):
        with tempfile.TemporaryDirectory(prefix="f33-t-") as root:
            gateway = _fresh_gateway()
            _provision_pair(root, "dev-a", gateway)
            out = request_session(gateway, root, "dev-a", 100_000)
            gateway.verify_session(out["credential"], "dev-a")
            with self.assertRaises(HostedError) as caught:
                gateway.verify_session(out["credential"], "dev-a")
            self.assertEqual(str(caught.exception),
                             "hosted_credential_replayed")
            self.assertEqual(gateway.remaining_quota_fen,
                             START_FEN - 100_000)  # 恰扣一次

    def test_tampered_credential_invalid(self):
        with tempfile.TemporaryDirectory(prefix="f33-t-") as root:
            gateway = _fresh_gateway()
            _provision_pair(root, "dev-a", gateway)
            out = request_session(gateway, root, "dev-a", 100_000)
            cred = dict(out["credential"], authorized_fen=START_FEN)
            with self.assertRaises(HostedError) as caught:
                gateway.verify_session(cred, "dev-a")
            self.assertEqual(str(caught.exception),
                             "hosted_credential_invalid")
            self.assertEqual(gateway.remaining_quota_fen, START_FEN)


class F33SubKeyNeverOnDevice(unittest.TestCase):
    def test_device_key_roundtrip_via_f12_vault(self):
        with tempfile.TemporaryDirectory(prefix="f33-t-") as root:
            gateway = _fresh_gateway()
            receipt = gateway.provision_device("dev-a")
            key = base64.b64decode(receipt["device_key_b64"])
            stored = store_device_key(root, "dev-a", key)
            self.assertEqual(stored["backend"], "dpapi")
            self.assertEqual(hosted_inference.load_device_key(root, "dev-a"),
                             key)
            entry = Path(root) / "credentials" / "lvyin.hosted" \
                / "device-dev-a.json"
            self.assertTrue(entry.is_file())
            self.assertNotIn(key, entry.read_bytes())  # 落盘零明文钥

    def test_all_receipts_and_persistence_zero_sub_key(self):
        forms = [SUB_KEY,
                 base64.b64encode(SUB_KEY),
                 SUB_KEY.hex().encode("ascii")]
        with tempfile.TemporaryDirectory(prefix="f33-t-") as root:
            gateway = _fresh_gateway()
            surfaces = []
            prov = gateway.provision_device("dev-a")
            surfaces.append(json.dumps(prov))
            store_device_key(root, "dev-a",
                             base64.b64decode(prov["device_key_b64"]))
            out = request_session(gateway, root, "dev-a", 100_000)
            surfaces.append(json.dumps(out))
            surfaces.append(json.dumps(out["credential"]))
            ver = gateway.verify_session(out["credential"], "dev-a")
            surfaces.append(json.dumps(ver))
            for path in Path(root).rglob("*"):
                if path.is_file():
                    surfaces.append(repr(path.read_bytes()))
            for surface in surfaces:
                blob = surface.encode("utf-8", "surrogateescape")
                for form in forms:
                    self.assertNotIn(form, blob)


class F33FaceDiscipline(unittest.TestCase):
    def test_ast_zero_network_zero_io_zero_log(self):
        tree = ast.parse(HOSTED.read_text(encoding="utf-8"))
        banned = {"urllib", "socket", "http", "ssl", "ftplib", "requests",
                  "httpx", "subprocess", "logging", "os"}
        offenders = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                offenders += [alias.name for alias in node.names
                              if alias.name.split(".")[0] in banned]
            elif isinstance(node, ast.ImportFrom) and node.module \
                    and node.module.split(".")[0] in banned:
                offenders.append(node.module)
            elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name) \
                    and node.func.id in ("print", "open"):
                offenders.append("call:" + node.func.id)
        self.assertEqual(offenders, [])

    def test_ast_sub_key_confined_to_gateway_init(self):
        tree = ast.parse(HOSTED.read_text(encoding="utf-8"))
        offenders = []

        def _walk_function(node, owner: str) -> None:
            for sub in ast.walk(node):
                if isinstance(sub, ast.Name) and sub.id == "sub_key":
                    offenders.append(owner)
                if isinstance(sub, ast.Attribute) and sub.attr == "sub_key":
                    offenders.append(owner)

        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                owner = node.name
                if owner != "__init__":
                    _walk_function(node, owner)
        self.assertEqual(offenders, [],
                         "sub_key 名只许出现在 HostedGateway.__init__")

    def test_legal_entry_zero_hosted_wiring(self):
        text = LEGAL_ENTRY.read_text(encoding="utf-8")
        self.assertNotIn("hosted", text.lower())
        self.assertNotIn("hosted_inference",
                         LEGAL_ENTRY.read_text(encoding="utf-8"))

    def test_error_codes_are_typed_and_material_free(self):
        for code in hosted_inference.HOSTED_ERROR_CODES:
            self.assertTrue(code.startswith("hosted_"))
        exc = HostedError("hosted_quota_exceeded")
        self.assertEqual(str(exc), "hosted_quota_exceeded")


if __name__ == "__main__":
    unittest.main()

# -*- coding: utf-8 -*-
"""F113 产品侧接线测试（W3-U06）：案件/项目/案号稳定身份＋散件归案。

全部合成材料。legal_entry 新增 HARNESS_CASE_ANCHOR_METHODS 六方法组
（走 --caseanchor-json 封闭信封，subprocess seam 注入，单测零仓依赖）；
真 public_entry 全链（SQLite 状态根子进程）与 PgMatterStore 直连对账在
tools/PENDING_OWNER_f03_f113_dualdb_identity_recon.py。fail-closed：
未配置桥＝NOT_CONNECTED（exit 3 具名），账本 typed 拒＝
HarnessCommandError 携码，绝不空响应冒成功。

合同要点（harness docs/f113-case-anchor-contract.md）：identity_kind
闭集 litigation/non_litigation/project；案号可选（非诉无案号合法——
结构性不强制）；案号确定性归一（全角括号/空白差异不产生第二个身份）
后 sha256=case_number_digest；同一归一号至多钉一个案件 current 锚点
（跨案同号 case_number_anchor_conflict 具名拒）；改号=追加 revision
旧行 current=0 不删；散件归案 item_digest+item_ref 互钉、同件归同案
幂等；case_number_resolve=案号→唯一案件锚点稳定解析。
"""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
import unittest.mock
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python"))

import legal_entry  # noqa: E402
from bridge_errors import HarnessCommandError, NotConnected  # noqa: F401

HARNESS_WORKTREE = Path(
    r"D:\Codex\1.法律工作区\legal-harness工作区\legal-harness-repo"
    r"\.local\worktrees\w3-u06")

CONFIG = {
    "harness_public_entry": "X:/synth/harness/public_entry.py",
    "harness_target": "opencode",
    "harness_state_root": "X:/synth/state-root",
    "harness_python": sys.executable,
}
SCOPE = {"kind": "matter", "matterId": "m-f113"}
METHODS = (
    "harness.case_identity_register", "harness.case_identity_read",
    "harness.case_number_resolve", "harness.case_anchor_attach",
    "harness.case_anchor_list", "harness.case_anchor_item_read",
)
ITEM_DIGEST = ("ab" * 32)


def fake_entry_output(result):
    return json.dumps({"surface": "caseanchor", "method": "synthetic",
                       "result": result})


def patch_execute(testcase, *, stdout="", returncode=0, calls=None):
    def _fake(argv, env, timeout):
        if calls is not None:
            entry = {"argv": argv, "env": env}
            if "--caseanchor-json" in argv:
                path = Path(argv[argv.index("--caseanchor-json") + 1])
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


class F113CaseAnchorBridgeTests(unittest.TestCase):
    def test_method_group_membership(self) -> None:
        self.assertEqual(legal_entry.HARNESS_CASE_ANCHOR_METHODS,
                         frozenset(METHODS))
        # 现组零动。
        self.assertNotIn("harness.case_identity_register",
                         legal_entry.HARNESS_VOI_METHODS)
        self.assertNotIn("harness.case_anchor_attach",
                         legal_entry.HARNESS_MATERIAL_METHODS)

    def test_all_methods_ride_caseanchor_envelope(self) -> None:
        calls: list = []
        patch_execute(self, stdout=fake_entry_output({"ok": True,
                                                      "who": "bridge"}),
                      returncode=0, calls=calls)
        for method in METHODS:
            with self.subTest(method=method):
                result = legal_entry.call(method, {"scope": SCOPE}, CONFIG)
                self.assertEqual(result, {"ok": True, "who": "bridge"})
        self.assertEqual(len(calls), len(METHODS))
        for call in calls:
            self.assertIn("--caseanchor-json", call["argv"])
            self.assertIn("--target", call["argv"])
            self.assertEqual(call["env"]["LH_LEGAL_STATE_ROOT"],
                             "X:/synth/state-root")
            self.assertEqual(call["payload"]["params"], {"scope": SCOPE})
        self.assertEqual(calls[0]["payload"]["method"], METHODS[0])

    def test_not_configured_named_refusal(self) -> None:
        with self.assertRaises(NotConnected) as caught:
            legal_entry.call("harness.case_identity_register",
                             {"scope": SCOPE}, {})
        self.assertIn("harness_public_entry_not_configured",
                      str(caught.exception))

    def test_unknown_method_not_connected(self) -> None:
        with self.assertRaises(NotConnected) as caught:
            legal_entry.call("harness.case_identity_delete",
                             {"scope": SCOPE}, CONFIG)
        self.assertIn("method_not_connected:"
                      "harness.case_identity_delete",
                      str(caught.exception))

    def test_typed_ledger_error_surfaced(self) -> None:
        patch_execute(self, stdout=json.dumps(
            {"status": "FAIL", "error":
             "case_number_anchor_conflict:m-other"}),
            returncode=1)
        with self.assertRaises(HarnessCommandError) as caught:
            legal_entry.call("harness.case_identity_register",
                             {"scope": SCOPE,
                              "key": command_key("ci-1"),
                              "identity": {"identityKind": "litigation",
                                           "caseNumber": "（2026）合成民初1号",
                                           "court": None, "note": None}},
                             CONFIG)
        self.assertIn("case_number_anchor_conflict", str(caught.exception))

    def test_non_dict_params_refused(self) -> None:
        patch_execute(self)
        with self.assertRaises(NotConnected) as caught:
            legal_entry.call("harness.case_anchor_attach",
                             "not-a-dict", CONFIG)
        self.assertIn("harness_params_invalid", str(caught.exception))


@unittest.skipUnless(
    (HARNESS_WORKTREE / "tools/workflow-tools/harness/public_entry.py")
    .is_file(),
    "harness w3-u06 worktree not present")
class F113RealPublicEntryChainTests(unittest.TestCase):
    """真产品入口子进程径（桌面 profile 同链）：合成案号全角登记→半角
    变体解析回同一案件→跨案同号具名拒→散件归案幂等。SQLite 状态根
    临时目录，绝不触碰 %APPDATA%。"""

    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory(prefix="juscite-f113-")
        registration = Path(cls.temporary.name) / "service-local.json"
        registration.write_text(json.dumps(
            {"url": "http://127.0.0.1:1", "password": "synthetic-wiring"}),
            encoding="utf-8")
        state_root = Path(cls.temporary.name) / "state"
        state_root.mkdir(parents=True, exist_ok=True)
        cls.config = {
            "harness_public_entry": str(
                HARNESS_WORKTREE / "tools/workflow-tools/harness"
                "/public_entry.py"),
            "harness_target": "opencode",
            "harness_state_root": str(state_root),
            "harness_service_registration": str(registration),
            "harness_python": sys.executable,
            "harness_timeout": 120,
        }

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()

    def test_identity_register_resolve_anchor_roundtrip(self) -> None:
        config = dict(self.config)
        config["harness_state_root"] = self.config["harness_state_root"]
        # 建案件：P04 既有公开面（harness.create_matter）当前不在产品桥
        # 冻结组内——W08 lifecycle 桥接不属本单；同状态根进程内建案（与
        # 子进程 public_entry 共享 LH_LEGAL_STATE_ROOT）。F113 六方法才
        # 是本单被测面。
        sys.path.insert(0, str(HARNESS_WORKTREE / "src"))
        for _name in [m for m in list(sys.modules)
                      if m == "legal_harness"
                      or m.startswith("legal_harness.")]:
            del sys.modules[_name]
        from legal_harness.business.units import HarnessUnits as _Units
        from legal_harness.state.matter_store import MatterStore as _Store
        store = _Store(Path(self.config["harness_state_root"]))
        _Units(store).create_matter("wiring", SCOPE,
                                    command_key("mk-1"),
                                    {"owner": "harness", "kind": "profile",
                                     "id": "prof-1", "version": "1"},
                                    {"owner": "host", "kind": "intake",
                                     "id": "in-1", "version": "1"})
        _Units(store).create_matter(
            "wiring", {"kind": "matter", "matterId": "m-f113-b"},
            command_key("mk-2"),
            {"owner": "harness", "kind": "profile", "id": "prof-1",
             "version": "1"},
            {"owner": "host", "kind": "intake", "id": "in-2",
             "version": "1"})
        for _name in [m for m in list(sys.modules)
                      if m == "legal_harness"
                      or m.startswith("legal_harness.")]:
            del sys.modules[_name]
        sys.path.remove(str(HARNESS_WORKTREE / "src"))
        # 非诉无案号合法。
        non_lit = legal_entry.call(
            "harness.case_identity_register",
            {"actor_id": "wiring", "scope": SCOPE,
             "key": command_key("ci-0"),
             "identity": {"identityKind": "non_litigation",
                          "caseNumber": None, "court": "合成调解中心",
                          "note": "wiring 合成"}},
            config)
        self.assertIsNone(non_lit["identity"]["caseNumberDigest"])
        # 诉讼全角案号登记（含内嵌空白）。
        registered = legal_entry.call(
            "harness.case_identity_register",
            {"actor_id": "wiring", "scope": SCOPE,
             "key": command_key("ci-1"),
             "identity": {"identityKind": "litigation",
                          "caseNumber": "（2026）京0105民初 777号",
                          "court": "合成第一人民法院", "note": None}},
            config)
        digest = registered["identity"]["caseNumberDigest"]
        self.assertEqual(registered["revision"], 2)
        # 半角无空白变体解析回同一案件。
        resolved = legal_entry.call(
            "harness.case_number_resolve",
            {"case_number": "(2026)京0105民初777号"}, config)
        self.assertTrue(resolved["resolved"])
        self.assertEqual(resolved["matterId"], "m-f113")
        self.assertEqual(resolved["caseNumberDigest"], digest)
        # 散件归案＋幂等。
        item_ref = {"owner": "host", "kind": "upload", "id": "散件-w1",
                    "version": "1", "digest": ITEM_DIGEST}
        attached = legal_entry.call(
            "harness.case_anchor_attach",
            {"actor_id": "wiring", "scope": SCOPE,
             "key": command_key("at-1"), "item_ref": dict(item_ref),
             "item_digest": ITEM_DIGEST},
            config)
        self.assertFalse(attached["replayed"])
        reattached = legal_entry.call(
            "harness.case_anchor_attach",
            {"actor_id": "wiring", "scope": SCOPE,
             "key": command_key("at-2"), "item_ref": dict(item_ref),
             "item_digest": ITEM_DIGEST},
            config)
        self.assertTrue(reattached["replayed"])
        listing = legal_entry.call("harness.case_anchor_list",
                                   {"scope": SCOPE}, config)
        self.assertEqual(listing["anchorCount"], 1)
        # 账本 typed 拒经桥面原样上浮（跨案同号）。
        with self.assertRaises(HarnessCommandError) as caught:
            legal_entry.call(
                "harness.case_identity_register",
                {"actor_id": "wiring",
                 "scope": {"kind": "matter", "matterId": "m-f113-b"},
                 "key": command_key("ci-2"),
                 "identity": {"identityKind": "litigation",
                              "caseNumber": "(2026)京0105民初777号",
                              "court": None, "note": None}},
                config)
        self.assertIn("case_number_anchor_conflict:m-f113",
                      str(caught.exception))


if __name__ == "__main__":
    unittest.main()

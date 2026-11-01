# -*- coding: utf-8 -*-
r"""F65 浏览器 CDP 遥控 产品面接线测试（工单 W5-U07）。

06 行 V7-65（v2；owner=product；B5；UI_HOST_OR_NEW_PRODUCT）acceptance：
浏览器按 tab 授权与配对；操作受人工边界，证据和外部副作用可对账。

合同硬点（本测试主战场；transport 注入假件＝零网络零浏览器，W4-U40
F63『唯一网络通道＝注入 transport』同款）：
  - 配对一次性绑定：码原文不落盘；错码/真实流逝过期/同码二次/controller
    不匹配全具名拒；token 只返回一次；
  - 未配对动作具名拒（核心负测）；
  - 按 tab 授权：未授权 tab 动作具名拒（核心负测）；授权前真实 tab 在位
    核对（不存在 tab 具名拒且不消费人工确认）；同 (session,tab) 幂等
    重放不双记（E24 形态）；
  - 人工边界（L6）：授权与动作两张确认面；缺确认/重用/绑定不符/过期全
    具名拒；
  - 外部动作账（E24/W4-U40 append-only 幂等重放形态）：同键同内容重放
    不重执行（transport 调用计数亲证零二跳）；同键异内容具名冲突零落账；
    动作闭集外具名拒；回执 sha256 绑定；evaluate 页面异常具名拒零落账；
  - AST 纪律：回环闸先行（凡 urlopen/create_connection 的函数体必先调
    require_loopback_endpoint·闸自身零网络）；导入闭集钉定；字符串常量
    零非回环 URL 零 APPDATA；拒绝码闭集覆盖全部抛点；零 legal_entry
    接线（UI_HOST_OR_NEW_PRODUCT＝不冒已有业务入口）。

全程合成材料（假 transport＋%TEMP% 状态根，零真实外联，绝不
%APPDATA%\JusBench）。
"""

from __future__ import annotations

import ast
import json
import sys
import tempfile
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python"))

import cdp_remote  # noqa: E402

ENDPOINT = "ws://127.0.0.1:9333"
NAV_URL = "http://127.0.0.1:9333/pages/a"
TAB = {"id": "T1", "type": "page", "url": "about:blank",
       "title": "about:blank", "webSocketDebuggerUrl": "ws://127.0.0.1:1/x"}
EVAL_EXPR = "1+1"


class FakeTransport:
    """假 CDP transport：tab 表固定；命令调用逐笔记数（对账面）。"""

    def __init__(self, tabs=None):
        self.tabs = tabs if tabs is not None else [dict(TAB)]
        self.calls = []
        self.navigate_receipt = {"frameId": "FRAME-1", "loaderId": "LOAD-1"}
        self.evaluate_receipt = {"result": {"type": "string", "value": "9"}}

    def list_tabs(self, endpoint):
        return [dict(t) for t in self.tabs]

    def command(self, ws_url, method, params):
        self.calls.append((ws_url, method, params))
        receipt = (self.navigate_receipt if method == "Page.navigate"
                   else dict(self.evaluate_receipt))
        return {"id": 1, "result": receipt}


class F65Base(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(prefix="f65-test-")
        self.root = Path(self._tmp.name) / "state"
        self.root.mkdir(parents=True)
        self.transport = FakeTransport()
        self.addCleanup(self._tmp.cleanup)

    def paired(self, controller="ctrl-a"):
        issue = cdp_remote.pairing_issue(self.root, {
            "endpoint": ENDPOINT, "controller_id": controller,
            "pairing_ttl_s": 300})
        bind = cdp_remote.pairing_bind(self.root, {
            "session_id": issue["session_id"],
            "pairing_code": issue["pairing_code"],
            "controller_id": controller})
        return issue["session_id"], bind["controller_token"]

    def granted(self):
        session_id, token = self.paired()
        confirm = cdp_remote.human_confirm(self.root, {
            "purpose": "tab_grant", "session_id": session_id,
            "tab_id": "T1", "confirmed_by": "human-1", "synthetic": True})
        cdp_remote.tab_authorize(self.root, {
            "session_id": session_id, "controller_token": token,
            "tab_id": "T1", "human_confirmation": confirm["confirmation"]},
            transport=self.transport)
        return session_id, token

    def ledger_lines(self):
        return len(cdp_remote.ledger_read(self.root, {})["actions"])

    def confirm_events(self):
        path = self.root / "cdp_human_confirmations.jsonl"
        if not path.is_file():
            return []
        return [json.loads(line) for line in
                path.read_text(encoding="utf-8").splitlines() if line.strip()]


class PairingTests(F65Base):
    def test_issue_code_not_persisted(self):
        issue = cdp_remote.pairing_issue(self.root, {
            "endpoint": ENDPOINT, "controller_id": "ctrl-a",
            "pairing_ttl_s": 300})
        blob = "\n".join(p.read_text(encoding="utf-8", errors="ignore")
                         for p in self.root.rglob("*") if p.is_file())
        self.assertNotIn(issue["pairing_code"], blob)
        self.assertIn(issue["session_id"], blob)

    def test_bind_wrong_code(self):
        issue = cdp_remote.pairing_issue(self.root, {
            "endpoint": ENDPOINT, "controller_id": "ctrl-a"})
        with self.assertRaises(cdp_remote.CdpRemoteError) as ctx:
            cdp_remote.pairing_bind(self.root, {
                "session_id": issue["session_id"],
                "pairing_code": "0" * 32, "controller_id": "ctrl-a"})
        self.assertEqual(ctx.exception.code, "cdp_pairing_code_invalid")

    def test_bind_expired(self):
        issue = cdp_remote.pairing_issue(self.root, {
            "endpoint": ENDPOINT, "controller_id": "ctrl-a",
            "pairing_ttl_s": 1})
        time.sleep(1.3)
        with self.assertRaises(cdp_remote.CdpRemoteError) as ctx:
            cdp_remote.pairing_bind(self.root, {
                "session_id": issue["session_id"],
                "pairing_code": issue["pairing_code"],
                "controller_id": "ctrl-a"})
        self.assertEqual(ctx.exception.code, "cdp_pairing_code_expired")

    def test_bind_ok_then_reused(self):
        session_id, token = self.paired()
        self.assertTrue(token)
        issue = next(s for s in
                     cdp_remote.ledger_read(self.root, {})["sessions"]
                     if s["session_id"] == session_id)
        self.assertTrue(issue["bound"])
        with self.assertRaises(cdp_remote.CdpRemoteError) as ctx:
            cdp_remote.pairing_bind(self.root, {
                "session_id": session_id, "pairing_code": "x" * 32,
                "controller_id": "ctrl-a"})
        self.assertEqual(ctx.exception.code, "cdp_pairing_code_reused")

    def test_bind_controller_mismatch(self):
        issue = cdp_remote.pairing_issue(self.root, {
            "endpoint": ENDPOINT, "controller_id": "ctrl-real"})
        with self.assertRaises(cdp_remote.CdpRemoteError) as ctx:
            cdp_remote.pairing_bind(self.root, {
                "session_id": issue["session_id"],
                "pairing_code": issue["pairing_code"],
                "controller_id": "ctrl-else"})
        self.assertEqual(ctx.exception.code, "cdp_controller_mismatch")


class AuthorizationTests(F65Base):
    def test_action_unpaired_rejected(self):
        with self.assertRaises(cdp_remote.CdpRemoteError) as ctx:
            cdp_remote.action_execute(self.root, {
                "session_id": "cdpsess-fake", "controller_token": "forged",
                "tab_id": "T1", "action": "navigate",
                "params": {"url": NAV_URL}, "action_key": "k1",
                "human_confirmation": None}, transport=self.transport)
        self.assertEqual(ctx.exception.code, "cdp_not_paired")
        self.assertEqual(self.transport.calls, [])

    def test_grant_requires_confirmation(self):
        session_id, token = self.paired()
        with self.assertRaises(cdp_remote.CdpRemoteError) as ctx:
            cdp_remote.tab_authorize(self.root, {
                "session_id": session_id, "controller_token": token,
                "tab_id": "T1", "human_confirmation": None},
                transport=self.transport)
        self.assertEqual(ctx.exception.code,
                         "cdp_human_confirmation_required")

    def test_grant_ok_metadata_and_replay(self):
        session_id, token = self.paired()
        confirm = cdp_remote.human_confirm(self.root, {
            "purpose": "tab_grant", "session_id": session_id,
            "tab_id": "T1", "confirmed_by": "human-1", "synthetic": True})
        grant = cdp_remote.tab_authorize(self.root, {
            "session_id": session_id, "controller_token": token,
            "tab_id": "T1",
            "human_confirmation": confirm["confirmation"]},
            transport=self.transport)
        self.assertFalse(grant["replayed"])
        self.assertEqual(grant["grant"]["tab_url"], "about:blank")
        replay = cdp_remote.tab_authorize(self.root, {
            "session_id": session_id, "controller_token": token,
            "tab_id": "T1", "human_confirmation": None},
            transport=self.transport)
        self.assertTrue(replay["replayed"])
        self.assertEqual(replay["grant"], grant["grant"])
        self.assertEqual(len(cdp_remote.ledger_read(
            self.root, {})["grants"]), 1)

    def test_grant_tab_not_found_no_confirm_consumed(self):
        session_id, token = self.paired()
        confirm = cdp_remote.human_confirm(self.root, {
            "purpose": "tab_grant", "session_id": session_id,
            "tab_id": "NOPE", "confirmed_by": "human-1", "synthetic": True})
        with self.assertRaises(cdp_remote.CdpRemoteError) as ctx:
            cdp_remote.tab_authorize(self.root, {
                "session_id": session_id, "controller_token": token,
                "tab_id": "NOPE",
                "human_confirmation": confirm["confirmation"]},
                transport=self.transport)
        self.assertEqual(ctx.exception.code, "cdp_tab_not_found")
        consumed = [e for e in self.confirm_events()
                    if e["event"] == "consumed"]
        self.assertEqual(consumed, [])


class ActionTests(F65Base):
    def test_execute_unauthorized_tab(self):
        session_id, token = self.paired()
        with self.assertRaises(cdp_remote.CdpRemoteError) as ctx:
            cdp_remote.action_execute(self.root, {
                "session_id": session_id, "controller_token": token,
                "tab_id": "T1", "action": "navigate",
                "params": {"url": NAV_URL}, "action_key": "k1",
                "human_confirmation": None}, transport=self.transport)
        self.assertEqual(ctx.exception.code, "cdp_tab_not_authorized")
        self.assertEqual(self.transport.calls, [])

    def test_execute_requires_confirmation(self):
        session_id, token = self.granted()
        with self.assertRaises(cdp_remote.CdpRemoteError) as ctx:
            cdp_remote.action_execute(self.root, {
                "session_id": session_id, "controller_token": token,
                "tab_id": "T1", "action": "navigate",
                "params": {"url": NAV_URL}, "action_key": "k1",
                "human_confirmation": None}, transport=self.transport)
        self.assertEqual(ctx.exception.code,
                         "cdp_human_confirmation_required")
        self.assertEqual(self.transport.calls, [])

    def test_execute_ok_replay_no_second_call_and_conflict(self):
        session_id, token = self.granted()
        confirm = cdp_remote.human_confirm(self.root, {
            "purpose": "action", "session_id": session_id, "tab_id": "T1",
            "action": "navigate", "action_key": "k1",
            "params": {"url": NAV_URL}, "confirmed_by": "human-1",
            "synthetic": True})
        result = cdp_remote.action_execute(self.root, {
            "session_id": session_id, "controller_token": token,
            "tab_id": "T1", "action": "navigate",
            "params": {"url": NAV_URL}, "action_key": "k1",
            "human_confirmation": confirm["confirmation"]},
            transport=self.transport)
        self.assertFalse(result["replayed"])
        self.assertEqual(result["receipt"]["frame_id"], "FRAME-1")
        self.assertEqual(len(self.transport.calls), 1)
        self.assertEqual(self.ledger_lines(), 1)
        replay = cdp_remote.action_execute(self.root, {
            "session_id": session_id, "controller_token": token,
            "tab_id": "T1", "action": "navigate",
            "params": {"url": NAV_URL}, "action_key": "k1",
            "human_confirmation": None}, transport=self.transport)
        self.assertTrue(replay["replayed"])
        self.assertEqual(replay["receipt"], result["receipt"])
        self.assertEqual(replay["receipt_sha256"], result["receipt_sha256"])
        self.assertEqual(len(self.transport.calls), 1)  # 不重执行
        self.assertEqual(self.ledger_lines(), 1)  # 账不双记
        with self.assertRaises(cdp_remote.CdpRemoteError) as ctx:
            cdp_remote.action_execute(self.root, {
                "session_id": session_id, "controller_token": token,
                "tab_id": "T1", "action": "navigate",
                "params": {"url": NAV_URL + "?x=1"}, "action_key": "k1",
                "human_confirmation": None}, transport=self.transport)
        self.assertEqual(ctx.exception.code, "cdp_action_key_conflict")
        self.assertEqual(self.ledger_lines(), 1)
        self.assertEqual(len(self.transport.calls), 1)

    def test_confirmation_single_use_then_mismatch(self):
        session_id, token = self.granted()
        confirm = cdp_remote.human_confirm(self.root, {
            "purpose": "action", "session_id": session_id, "tab_id": "T1",
            "action": "evaluate", "action_key": "k1",
            "params": {"expression": EVAL_EXPR}, "confirmed_by": "human-1",
            "synthetic": True})
        cdp_remote.action_execute(self.root, {
            "session_id": session_id, "controller_token": token,
            "tab_id": "T1", "action": "evaluate",
            "params": {"expression": EVAL_EXPR}, "action_key": "k1",
            "human_confirmation": confirm["confirmation"]},
            transport=self.transport)
        with self.assertRaises(cdp_remote.CdpRemoteError) as ctx:
            cdp_remote.action_execute(self.root, {
                "session_id": session_id, "controller_token": token,
                "tab_id": "T1", "action": "evaluate",
                "params": {"expression": EVAL_EXPR}, "action_key": "k2",
                "human_confirmation": confirm["confirmation"]},
                transport=self.transport)
        self.assertEqual(ctx.exception.code, "cdp_human_confirmation_used")
        other = cdp_remote.human_confirm(self.root, {
            "purpose": "action", "session_id": session_id, "tab_id": "T1",
            "action": "evaluate", "action_key": "k3",
            "params": {"expression": "2+2"}, "confirmed_by": "human-1",
            "synthetic": True})
        with self.assertRaises(cdp_remote.CdpRemoteError) as ctx:
            cdp_remote.action_execute(self.root, {
                "session_id": session_id, "controller_token": token,
                "tab_id": "T1", "action": "evaluate",
                "params": {"expression": EVAL_EXPR}, "action_key": "k2",
                "human_confirmation": other["confirmation"]},
                transport=self.transport)
        self.assertEqual(ctx.exception.code,
                         "cdp_human_confirmation_invalid")
        self.assertEqual(self.ledger_lines(), 1)

    def test_confirmation_expired(self):
        session_id, token = self.granted()
        confirm = cdp_remote.human_confirm(self.root, {
            "purpose": "action", "session_id": session_id, "tab_id": "T1",
            "action": "evaluate", "action_key": "k1",
            "params": {"expression": EVAL_EXPR}, "confirmed_by": "human-1",
            "ttl_s": 1, "synthetic": True})
        time.sleep(1.3)
        with self.assertRaises(cdp_remote.CdpRemoteError) as ctx:
            cdp_remote.action_execute(self.root, {
                "session_id": session_id, "controller_token": token,
                "tab_id": "T1", "action": "evaluate",
                "params": {"expression": EVAL_EXPR}, "action_key": "k1",
                "human_confirmation": confirm["confirmation"]},
                transport=self.transport)
        self.assertEqual(ctx.exception.code,
                         "cdp_human_confirmation_expired")

    def test_unknown_action_closed_set(self):
        session_id, token = self.granted()
        with self.assertRaises(cdp_remote.CdpRemoteError) as ctx:
            cdp_remote.action_execute(self.root, {
                "session_id": session_id, "controller_token": token,
                "tab_id": "T1", "action": "download_file",
                "params": {"url": NAV_URL}, "action_key": "k1",
                "human_confirmation": None}, transport=self.transport)
        self.assertEqual(ctx.exception.code, "cdp_action_unknown")

    def test_evaluate_exception_no_ledger_entry(self):
        session_id, token = self.granted()
        self.transport.evaluate_receipt = {
            "result": {"type": "object"},
            "exceptionDetails": {"text": "TypeError"}}
        confirm = cdp_remote.human_confirm(self.root, {
            "purpose": "action", "session_id": session_id, "tab_id": "T1",
            "action": "evaluate", "action_key": "k1",
            "params": {"expression": "boom"}, "confirmed_by": "human-1",
            "synthetic": True})
        with self.assertRaises(cdp_remote.CdpRemoteError) as ctx:
            cdp_remote.action_execute(self.root, {
                "session_id": session_id, "controller_token": token,
                "tab_id": "T1", "action": "evaluate",
                "params": {"expression": "boom"}, "action_key": "k1",
                "human_confirmation": confirm["confirmation"]},
                transport=self.transport)
        self.assertEqual(ctx.exception.code, "cdp_evaluate_exception")
        self.assertEqual(self.ledger_lines(), 0)  # 失败不编轨迹零落账


class DisciplineTests(F65Base):
    def test_endpoint_gate_nonloopback(self):
        with self.assertRaises(cdp_remote.CdpRemoteError) as ctx:
            cdp_remote.pairing_issue(self.root, {
                "endpoint": "ws://203.0.113.9:9222",
                "controller_id": "ctrl-a"})
        self.assertEqual(ctx.exception.code, "cdp_endpoint_not_local")
        self.assertEqual(cdp_remote.ledger_read(
            self.root, {})["sessions"], [])

    def test_rejection_codes_closed_set_covers_raise_sites(self):
        source = (ROOT / "python" / "cdp_remote.py").read_text("utf-8")
        raised = set()
        for node in ast.walk(ast.parse(source)):
            if (isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Name)
                    and node.func.id == "CdpRemoteError"
                    and node.args
                    and isinstance(node.args[0], ast.Constant)):
                value = node.args[0].value
                raised.add(value.split(":", 1)[0])
        self.assertTrue(raised)
        self.assertTrue(raised.issubset(set(cdp_remote.REJECTION_CODES)),
                        sorted(raised - set(cdp_remote.REJECTION_CODES)))

    def test_ast_gate_first_and_import_closure(self):
        source = (ROOT / "python" / "cdp_remote.py").read_text("utf-8")
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if not isinstance(node, ast.FunctionDef):
                continue
            io_lines = [n.lineno for n in ast.walk(node)
                        if isinstance(n, ast.Call)
                        and isinstance(n.func, ast.Attribute)
                        and n.func.attr in ("urlopen", "create_connection")]
            if not io_lines:
                continue
            gate_lines = [n.lineno for n in ast.walk(node)
                          if isinstance(n, ast.Call)
                          and isinstance(n.func, ast.Name)
                          and n.func.id == "require_loopback_endpoint"]
            self.assertTrue(gate_lines, node.name)
            self.assertLessEqual(min(gate_lines), min(io_lines), node.name)
        gate_fn = next(n for n in ast.walk(tree)
                       if isinstance(n, ast.FunctionDef)
                       and n.name == "require_loopback_endpoint")
        self.assertFalse([n for n in ast.walk(gate_fn)
                          if isinstance(n, ast.Call)
                          and isinstance(n.func, ast.Attribute)
                          and n.func.attr in ("urlopen",
                                              "create_connection")])
        imports = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.update(a.name for a in node.names)
            elif isinstance(node, ast.ImportFrom):
                imports.add(node.module or "")
        self.assertEqual(imports, {"__future__", "hashlib", "json",
                                   "secrets", "time", "urllib.request",
                                   "datetime", "pathlib", "websocket"})

    def test_ast_constants_no_real_hosts_no_appdata(self):
        source = (ROOT / "python" / "cdp_remote.py").read_text("utf-8")
        for node in ast.walk(ast.parse(source)):
            if not isinstance(node, ast.Constant) \
                    or not isinstance(node.value, str):
                continue
            text = node.value
            self.assertNotIn("APPDATA", text)
            if "://" in text:
                host = text.split("://", 1)[1].split("/", 1)[0] \
                    .split(":", 1)[0]
                self.assertIn(host.lower(),
                              ("", "127.0.0.1", "localhost", "::1"),
                              repr(text))

    def test_zero_legal_entry_wiring(self):
        source = (ROOT / "python" / "cdp_remote.py").read_text("utf-8")
        self.assertNotIn("import legal_entry", source)
        self.assertNotIn("from legal_entry", source)


if __name__ == "__main__":
    unittest.main()

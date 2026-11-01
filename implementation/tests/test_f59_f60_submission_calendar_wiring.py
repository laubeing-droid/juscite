# -*- coding: utf-8 -*-
"""W3-U12 / F59+F60 acceptance: submission package + calendar sync bridge.

06:F59 assertion「生成法院要求的材料核对和可读提交包；律师确认正式提交；
缺件提示」——绝不实际对外提交（本组零出站通道：submission_package.py 导
入闭集零网络 AST 钉死；对外提交动作本面与 harness 面都结构性不存在）。
06:F60 assertion「内部事件幂等同步外部日历；取消/改期冲突回流不自动更改
法律期限」——滴答/飞书合成端点先行（裁决#6：幂等回流/不改期限负测；真实
OAuth 授权后补联测）；期限值只消费 F107 冻结引擎/F106 日历账回执（本面
零重算）；端点 URL 只来自显式 config（无内置端点，禁编 URL）。

全合成材料；harness 侧 w3-u12 分支（基 w3-u08@c2cd5c29，schema v28）经
产品桥子进程全链（desktop 链）；synthetic 端点=127.0.0.1 临时 HTTP 服务
（recon 工具再做双 profile 深版）。
"""
import ast
import json
import subprocess
import sys
import tempfile
import threading
import unittest
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE / "python"))
import legal_entry  # noqa: E402

HARNESS_REPO = Path(
    r"D:\Codex\1.法律工作区\legal-harness工作区\legal-harness-repo"
    r"\.local\worktrees\w3-u12")

SCOPE = {"kind": "matter", "matterId": "m-f59f60-wiring"}
NOW = "2026-10-18T00:00:00+00:00"


def key(request_id):
    return {"requestId": request_id, "targetId": None,
            "expectedRevision": None, "inputRefs": []}


def receipt(evaluation_id="jc-wire-1", due_date="2026-04-07"):
    """F107 期限回执形状夹具（合成；recon 用真实 JC 评估）。"""
    return {"status": "OK", "slot": "D01",
            "nominal_due_date": "2026-04-04", "due_date": due_date,
            "holiday_extended": True,
            "evaluationRef": {"owner": "jc", "kind": "deadline-evaluation",
                              "id": evaluation_id,
                              "digest": "sha256:" + "b" * 64}}


class _SyntheticCalendarHandler(BaseHTTPRequestHandler):
    """滴答/飞书合成端点（本机回环临时服务，非任何真实外部设施）。

    POST /events：按 eventKey 幂等创建（重复键返回同一 externalEventId，
    不重复建）；GET /events?matterId&syncId：返回回流事件（改期/取消）。
    所有响应带 synthetic=true。"""

    def log_message(self, *args):  # noqa: D102 - 静默
        pass

    def _reply(self, payload, status=200):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):  # noqa: N802
        length = int(self.headers.get("Content-Length") or 0)
        request = json.loads(self.rfile.read(length).decode("utf-8"))
        server = self.server
        with server.lock:
            server.requests.append(request)
            event_key = request.get("eventKey")
            if event_key in server.events:
                existing = server.events[event_key]
                self._reply({"synthetic": True,
                             "externalEventId": existing})
                return
            external_id = f"synth-{len(server.events) + 1:04d}"
            server.events[event_key] = external_id
        self._reply({"synthetic": True, "externalEventId": external_id})

    def do_GET(self):  # noqa: N802
        query = dict(urllib.parse.parse_qsl(
            urllib.parse.urlparse(self.path).query))
        server = self.server
        target = query.get("syncId")
        with server.lock:
            backflow = [event for event in server.backflow
                        if event.get("syncId") == target]
        self._reply({"synthetic": True, "events": backflow})


def start_synthetic_endpoint(backflow=None):
    server = ThreadingHTTPServer(("127.0.0.1", 0),
                                 _SyntheticCalendarHandler)
    server.lock = threading.Lock()
    server.requests = []
    server.events = {}
    server.backflow = list(backflow or [])
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, f"http://127.0.0.1:{server.server_address[1]}"


def harness_config(tmp):
    registration = tmp / "service-local.json"
    registration.write_text(json.dumps(
        {"url": "http://127.0.0.1:1", "password": "synthetic-wiring"}),
        encoding="utf-8")
    state_root = tmp / "state"
    state_root.mkdir(parents=True, exist_ok=True)
    return {
        "harness_public_entry":
            str(HARNESS_REPO / "tools/workflow-tools/harness/public_entry.py"),
        "harness_target": "opencode",
        "harness_state_root": str(state_root),
        "harness_service_registration": str(registration),
        "harness_timeout": 120,
    }, state_root


class TestSurface(unittest.TestCase):
    def test_method_groups_frozen(self):
        self.assertEqual(
            legal_entry.SUBMISSION_PACKAGE_METHODS,
            frozenset({"submission.checklist_define",
                       "submission.checklist_read",
                       "submission.package_build",
                       "submission.package_confirm",
                       "submission.package_read",
                       "submission.package_list"}))
        self.assertEqual(
            legal_entry.CALENDAR_SYNC_METHODS,
            frozenset({"calendar.sync_event", "calendar.pull_external",
                       "calendar.resolve_conflict", "calendar.sync_read",
                       "calendar.sync_list"}))

    def test_submission_module_zero_egress_imports(self):
        """F59 红线 AST 钉死：可读提交包/确认面导入闭集零网络——对外提交
        动作结构性不存在（不是开关）。"""
        source = (HERE / "python" / "submission_package.py").read_text(
            encoding="utf-8")
        tree = ast.parse(source)
        # 模块级导入闭集零网络（legal_entry 只允许函数内惰性导入＝缺省
        # 派发器，非模块级依赖）。
        module_imports = set()
        for node in tree.body:
            if isinstance(node, ast.Import):
                module_imports.update(alias.name.split(".")[0]
                                      for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                module_imports.add(node.module.split(".")[0])
        self.assertEqual(module_imports, {"json", "__future__"})
        for forbidden in ("socket", "urllib", "http", "requests",
                          "subprocess", "ftplib", "smtplib"):
            self.assertNotIn(forbidden, module_imports)
            self.assertNotIn(f"import {forbidden}", source)

    def test_calendar_module_no_default_endpoint(self):
        """F60 端点纪律：无内置端点/默认 URL（禁编 URL）——URL 只来自显
        式 config。"""
        source = (HERE / "python" / "calendar_sync.py").read_text(
            encoding="utf-8")
        tree = ast.parse(source)
        constants = [node.value for node in ast.walk(tree)
                     if isinstance(node, ast.Constant)
                     and isinstance(node.value, str)]
        # 端点字面量＝带 host 的 URL；scheme 常量（"http://"）是配置校验
        # 前缀，不是端点。
        urls = [value for value in constants
                if value.startswith(("http://", "https://"))
                and len(value) > len("https://")]
        self.assertEqual(urls, [])


class TestBridgeNegatives(unittest.TestCase):
    def test_unconfigured_bridge_refused(self):
        # 完整入参（面内本地校验全过）→ 首个 harness 调用撞未配置桥。
        build_args = {"scope": SCOPE, "actor_id": "product-1",
                      "key": key("neg-0"), "package_id": "pkg-0",
                      "checklist_id": "cl-0", "items": [],
                      "matter_title": "", "court_note": ""}
        with self.assertRaises(legal_entry.NotConnected) as caught:
            legal_entry.call("submission.package_build", build_args, {})
        self.assertIn("harness_public_entry_not_configured",
                      str(caught.exception))
        sync_args = {"scope": SCOPE, "actor_id": "product-1",
                     "key": key("neg-0"), "sync_id": "sync-0",
                     "targetKind": "ticktick", "event_key": "evt-0",
                     "title": "负测", "due_date": "2026-04-07",
                     "nominal_due_date": "2026-04-04",
                     "deadline_receipt": receipt()}
        with self.assertRaises(legal_entry.NotConnected) as caught:
            legal_entry.call("calendar.sync_event", sync_args, {})
        self.assertIn("harness_public_entry_not_configured",
                      str(caught.exception))

    def test_unknown_methods_refused(self):
        with tempfile.TemporaryDirectory(prefix="f59f60-wire-") as tmp:
            config, _ = harness_config(Path(tmp))
            for method in ("submission.submit", "submission.send",
                           "calendar.push", "calendar.deadline_write"):
                with self.assertRaises(legal_entry.NotConnected) as caught:
                    legal_entry.call(method, {"scope": SCOPE}, config)
                self.assertIn("method_not_connected", str(caught.exception))

    def test_endpoint_not_configured_named_refusal_no_traffic(self):
        with tempfile.TemporaryDirectory(prefix="f59f60-wire-") as tmp:
            config, state_root = harness_config(Path(tmp))
            config["harness_python"] = sys.executable
            self._create_matter(state_root)
            args = {"scope": SCOPE, "actor_id": "product-1",
                    "key": key("neg-1"), "sync_id": "sync-neg",
                    "targetKind": "ticktick", "event_key": "evt-neg",
                    "title": "负测（合成）", "due_date": "2026-04-07",
                    "nominal_due_date": "2026-04-04",
                    "deadline_receipt": receipt()}
            with self.assertRaises(legal_entry.NotConnected) as caught:
                legal_entry.call("calendar.sync_event", args, config)
            # 未配置端点＝具名拒；但推送前守门登记已落账（pending_push），
            # 零出站流量（无端点可推）。
            self.assertIn(
                "calendar_sync_failed:calendar_sync_endpoint_not_configured:"
                "ticktick", str(caught.exception))
            read = legal_entry.call("calendar.sync_read",
                                    {"scope": SCOPE, "sync_id": "sync-neg"},
                                    config)
            self.assertEqual(read["state"], "pending_push")

    @staticmethod
    def _create_matter(state_root):
        sys.path.insert(0, str(HARNESS_REPO / "src"))
        for name in [m for m in list(sys.modules)
                     if m == "legal_harness"
                     or m.startswith("legal_harness.")]:
            del sys.modules[name]
        from legal_harness.state.matter_store import MatterStore
        MatterStore(state_root).create_matter(
            SCOPE["matterId"], "cas://wiring-f59f60")


class TestFullChain(unittest.TestCase):
    """desktop 链全流程：产品桥子进程 → harness w3-u12（schema v28），
    F59 渲染/缺件/确认＋F60 幂等推送/冲突回流/不改期限/律师决定。"""

    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory(prefix="f59f60-chain-")
        config, state_root = harness_config(Path(cls._tmp.name))
        config["harness_python"] = sys.executable
        TestBridgeNegatives._create_matter(state_root)
        cls.config = config
        cls.server, cls.endpoint = start_synthetic_endpoint(backflow=[
            {"syncId": "sync-D01", "externalEventId": "synth-0001",
             "eventType": "event_rescheduled",
             "externalDueDate": "2026-04-30",
             "payload": {"source": "synthetic-ticktick",
                         "newDate": "2026-04-30"}},
        ])
        cls.config["calendar_sync_endpoints"] = {
            "ticktick": cls.endpoint, "feishu": cls.endpoint}

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls._tmp.cleanup()

    def test_01_f59_checklist_build_missing_confirm_gate(self):
        defined = legal_entry.call("submission.checklist_define", {
            "actor_id": "lawyer-1", "scope": SCOPE, "key": key("cd-1"),
            "checklist": {"checklistId": "cl-1",
                          "title": "（合成法院）立案材料要求",
                          "items": [
                              {"itemId": "complaint", "title": "起诉状",
                               "required": True},
                              {"itemId": "evidence", "title": "证据清单",
                               "required": True},
                              {"itemId": "idcopy", "title": "主体材料",
                               "required": True}]}}, self.config)
        self.assertEqual(defined["itemCount"], 3)
        # 材料登记走 F08 同一账（产品桥 materials 面）。
        legal_entry.call("harness.register_material", {
            "actor_id": "lawyer-1", "scope": SCOPE, "key": key("rm-1"),
            "material": {"id": "mat-complaint", "kind": "digital_text",
                         "title": "起诉状（合成）",
                         "bytesB64": __import__("base64").b64encode(
                             "起诉状正文合成".encode()).decode()}},
            self.config)
        built = legal_entry.call("submission.package_build", {
            "actor_id": "lawyer-1", "scope": SCOPE, "key": key("pb-1"),
            "package_id": "pkg-1", "checklist_id": "cl-1",
            "matter_title": "买卖合同纠纷（合成）",
            "court_note": "合成法院立案庭",
            "items": [
                {"itemId": "complaint",
                 "materialRefs": [{"id": "mat-complaint"}]},
                {"itemId": "evidence", "materialRefs": []},
                {"itemId": "idcopy", "materialRefs": []},
            ]}, self.config)
        self.assertEqual(built["missingItems"], ["evidence", "idcopy"])
        self.assertEqual(built["submissionChannel"], "none")
        self.assertIn("缺件", built["packageText"])
        # 确定性：同输入第二次 build（新 package id）同渲染字节。
        built2 = legal_entry.call("submission.package_build", {
            "actor_id": "lawyer-1", "scope": SCOPE, "key": key("pb-2"),
            "package_id": "pkg-2", "checklist_id": "cl-1",
            "matter_title": "买卖合同纠纷（合成）",
            "court_note": "合成法院立案庭",
            "items": [
                {"itemId": "complaint",
                 "materialRefs": [{"id": "mat-complaint"}]},
                {"itemId": "evidence", "materialRefs": []},
                {"itemId": "idcopy", "materialRefs": []},
            ]}, self.config)
        self.assertEqual(built["packageText"], built2["packageText"])
        # 人工确认制：无显式 confirm 标志＝具名拒，账面零写入。
        with self.assertRaises(legal_entry.NotConnected) as no_flag:
            legal_entry.call("submission.package_confirm", {
                "actor_id": "lawyer-1", "scope": SCOPE, "key": key("pc-nf"),
                "package_id": "pkg-1",
                "package_sha256": built["packageSha256"],
                "reasonRef": {"owner": "host", "kind": "decision-receipt",
                              "id": "r-1", "version": "1"},
                "receiptRef": {"owner": "host", "kind": "decision-receipt",
                               "id": "rc-1", "version": "1"}}, self.config)
        self.assertIn(
            "submission_package_failed:f59_confirmation_flag_required",
            str(no_flag.exception))
        # 缺件确认＝具名拒（缺件具名提示）。
        with self.assertRaises(legal_entry.HarnessCommandError) as missing:
            legal_entry.call("submission.package_confirm", {
                "confirm": True, "actor_id": "lawyer-1", "scope": SCOPE,
                "key": key("pc-miss"), "package_id": "pkg-1",
                "package_sha256": built["packageSha256"],
                "reasonRef": {"owner": "host", "kind": "decision-receipt",
                              "id": "r-2", "version": "1"},
                "receiptRef": {"owner": "host", "kind": "decision-receipt",
                               "id": "rc-2", "version": "1"}}, self.config)
        self.assertIn("f59_confirm_missing_items:evidence,idcopy",
                      str(missing.exception))

    def test_02_f60_sync_idempotent_backflow_never_moves_deadline(self):
        event_args = {
            "scope": SCOPE, "actor_id": "product-1",
            "sync_id": "sync-D01", "targetKind": "ticktick",
            "event_key": "evt-D01", "title": "上诉期届满（合成）",
            "due_date": "2026-04-07", "nominal_due_date": "2026-04-04",
            "deadline_receipt": receipt(),
        }
        first = legal_entry.call("calendar.sync_event",
                                 dict(event_args, key=key("cs-1")),
                                 self.config)
        self.assertTrue(first["pushed"])
        self.assertEqual(first["legalDueDate"], "2026-04-07")
        push_count = len(self.server.requests)
        # 幂等：同 event_key 同内容重放＝不重复推送、返回既有行。
        replay = legal_entry.call("calendar.sync_event",
                                  dict(event_args, key=key("cs-replay")),
                                  self.config)
        self.assertTrue(replay["replayed"])
        self.assertFalse(replay["pushed"])
        self.assertEqual(len(self.server.requests), push_count)
        # 外部回流（改期 2026-04-30）：冲突具名，法律期限一字不动。
        pulled = legal_entry.call("calendar.pull_external", {
            "scope": SCOPE, "actor_id": "product-1",
            "targetKind": "ticktick", "sync_id": "sync-D01"},
            self.config)
        entry = pulled["recorded"][0]
        self.assertTrue(entry["conflict"])
        self.assertIn("f60_external_reschedule_conflicts_legal:"
                      "2026-04-30!=2026-04-07",
                      str(entry["conflictReason"]))
        projection = pulled["projection"]
        self.assertEqual(projection["state"], "conflict_pending_review")
        self.assertEqual(projection["legalDueDate"], "2026-04-07")
        # 决定闸：无 confirm 标志拒；keep 决定后法律期限仍不变。
        with self.assertRaises(legal_entry.NotConnected) as no_flag:
            legal_entry.call("calendar.resolve_conflict", {
                "scope": SCOPE, "actor_id": "lawyer-1", "key": key("rc-nf"),
                "sync_id": "sync-D01", "action": "keep_legal_deadline",
                "reasonRef": {"owner": "host", "kind": "decision-receipt",
                              "id": "r-3", "version": "1"},
                "receiptRef": {"owner": "host", "kind": "decision-receipt",
                               "id": "rc-3", "version": "1"}}, self.config)
        self.assertIn(
            "calendar_sync_failed:f60_confirmation_flag_required",
            str(no_flag.exception))
        resolved = legal_entry.call("calendar.resolve_conflict", {
            "confirm": True, "scope": SCOPE, "actor_id": "lawyer-1",
            "key": key("rc-1"), "sync_id": "sync-D01",
            "action": "keep_legal_deadline",
            "reasonRef": {"owner": "host", "kind": "decision-receipt",
                          "id": "r-4", "version": "1"},
            "receiptRef": {"owner": "host", "kind": "decision-receipt",
                           "id": "rc-4", "version": "1"}}, self.config)
        self.assertEqual(resolved["state"], "reviewed")
        self.assertEqual(resolved["legalDueDateUnchanged"], "2026-04-07")
        final = legal_entry.call("calendar.sync_read",
                                 {"scope": SCOPE, "sync_id": "sync-D01"},
                                 self.config)
        self.assertEqual(final["legalDueDate"], "2026-04-07")
        self.assertEqual(
            final["deadlineReceipt"]["evaluationRef"]["owner"], "jc")
        # 重复拉取幂等：CommandKey（externalEventId 派生）重放原回执，
        # 事件账仍恰一行、冲突仍具名、法律期限仍不变。
        repulled = legal_entry.call("calendar.pull_external", {
            "scope": SCOPE, "actor_id": "product-1",
            "targetKind": "ticktick", "sync_id": "sync-D01"}, self.config)
        self.assertEqual(repulled["recorded"], pulled["recorded"])
        self.assertEqual(len(repulled["projection"]["externalChanges"]), 1)
        self.assertEqual(repulled["projection"]["legalDueDate"],
                         "2026-04-07")

    def test_03_f59_confirm_after_full_package(self):
        # 补齐材料后新包（pkg-1 保持 draft 历史）→ 确认成功一次终局。
        legal_entry.call("harness.register_material", {
            "actor_id": "lawyer-1", "scope": SCOPE, "key": key("rm-2"),
            "material": {"id": "mat-evidence", "kind": "digital_text",
                         "title": "证据清单（合成）",
                         "bytesB64": __import__("base64").b64encode(
                             "证据清单合成".encode()).decode()}},
            self.config)
        legal_entry.call("harness.register_material", {
            "actor_id": "lawyer-1", "scope": SCOPE, "key": key("rm-3"),
            "material": {"id": "mat-idcopy", "kind": "image",
                         "title": "主体材料（合成）",
                         "bytesB64": __import__("base64").b64encode(
                             "主体材料合成".encode()).decode()}},
            self.config)
        built = legal_entry.call("submission.package_build", {
            "actor_id": "lawyer-1", "scope": SCOPE, "key": key("pb-3"),
            "package_id": "pkg-3", "checklist_id": "cl-1",
            "matter_title": "买卖合同纠纷（合成）",
            "court_note": "合成法院立案庭",
            "items": [
                {"itemId": "complaint",
                 "materialRefs": [{"id": "mat-complaint"}]},
                {"itemId": "evidence",
                 "materialRefs": [{"id": "mat-evidence"}]},
                {"itemId": "idcopy", "materialRefs": [{"id": "mat-idcopy"}]},
            ]}, self.config)
        self.assertEqual(built["missingItems"], [])
        confirmed = legal_entry.call("submission.package_confirm", {
            "confirm": True, "actor_id": "lawyer-1", "scope": SCOPE,
            "key": key("pc-ok"), "package_id": "pkg-3",
            "package_sha256": built["packageSha256"],
            "reasonRef": {"owner": "host", "kind": "decision-receipt",
                          "id": "r-5", "version": "1"},
            "receiptRef": {"owner": "host", "kind": "decision-receipt",
                           "id": "rc-5", "version": "1"}}, self.config)
        self.assertEqual(confirmed["state"], "confirmed")
        self.assertEqual(confirmed["submissionChannel"], "none")


if __name__ == "__main__":  # pragma: no cover
    unittest.main()

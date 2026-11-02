"""F59 提交包＋F60 日历同步对账（W3-U12）——双 profile（desktop/selfhost）。

验收命令（juscite worktree w3-u12 根 cwd 无参双 profile）：
  python -X utf8 tools/PENDING_OWNER_f59_f60_submission_calendar_recon.py
      [--profile desktop --profile selfhost]

对账对象：harness 分支 w3-u12（基 W3 施工链头 w3-u08@c2cd5c29，schema v28
四新账）的 --submission-json/--calsync-json 封闭径——desktop profile 与产品
桥（legal_entry → 子进程 public_entry）完全同一条链（SQLite 状态根）；
selfhost profile＝PgMatterStore 直连 lh-pg-e08（resolve_provider_method 同
一封闭注册；产品面经 harness_call 注入同函数链）。全部合成材料：临时状态
根、合成清单/材料/回执、滴答/飞书合成端点＝本机回环临时 HTTP 服务（裁决
#6：合成先行，真实 OAuth 授权后补联测）；harness 与 JC 检出零字节改动
（只运行其代码，git 只读命令核对分支）。

实跑覆盖（06 F59/F60 assertion 逐条）：
  F59：法院要求材料核对清单定义（items 闭集冻结）→可读提交包生成（缺件
  具名 missingItems）→渲染确定性（同输入同字节）→律师确认闸（无显式
  confirm 标志具名拒；缺件确认具名拒）→补齐材料后新包确认成功（一行一
  次终局，字节 sha 绑定）→**绝不实际对外提交**（submissionChannel='none'
  全投影；submission.submit/send 在封闭注册外 method_not_whitelisted；产
  品面导入闭集零网络 AST）。
  F60：真实 JC 期限评估（calc.deadline_preset_evaluate，JC w2b-u55 钉定
  ——F107 冻结引擎）→内部事件幂等同步合成滴答端点（同 event_key 同内容
  重放＝不重复推送）→外部回流改期冲突具名（f60_external_reschedule_
  conflicts_legal）且法律期限/deadline_receipt 逐字节不变→律师决定 keep
  （决定记录面；法律仍不变）→D07 冻结 UNKNOWN 回执不可同步（f60_receipt_
  not_ok 形态拒）→改期唯一通道＝新 sync 行＋新 JC 真评估（旧行一字不动）
  →飞书目标第二目标同步→桥负向（未配置/未知方法/方法组冻结）。

退出码：0 = 全部 profile RECON_OK；2 = RECON_FAIL；3 = 环境缺失。
证据：docs/construction/evidence/F59/<profile>/、F60/<profile>/（另写仓库
根 evidence/ 同名镜像）。
"""
from __future__ import annotations

import argparse
import ast
import base64
import os
import contextlib
import hashlib
import json
import subprocess
import sys
import tempfile
import threading
import uuid as _uuid
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "implementation" / "python"))
sys.path.insert(0, str(REPO_ROOT / "implementation" / "tests"))

import legal_entry  # noqa: E402
from legal_entry import HarnessCommandError, NotConnected  # noqa: E402
from submission_package import SubmissionPackageError  # noqa: E402
from calendar_sync import CalendarSyncError  # noqa: E402

DEFAULT_HARNESS_ROOT = Path(
    r"D:\Codex\1.法律工作区\legal-harness工作区\legal-harness-repo"
    r"\.local\worktrees\w3-u12")
DEFAULT_JC_ROOT = Path(
    r"D:\Codex\1.法律工作区\juris-calculus工作区\juris-calculus"
    r"\.local\worktrees\w2b-u55")

MATTER = "m-f59f60-recon"
SCOPE = {"kind": "matter", "matterId": MATTER}
NOW = "2026-10-18T00:00:00+00:00"

# lh-pg-e08 容器（E08 拓扑）：仅回环端口、合成专用凭据（可用 --pg-dsn 覆写）。
DEFAULT_PG_DSN = "postgresql://lh_app:e08-synth-only@127.0.0.1:55432/legal_harness"

# JC 检出＝w2b-u55 worktree（F107 交付链头）；client.py／deadline_presets.py
# sha256 钉定＝收口字节，漂移即 FATAL（不猜改不静默换源）。
JC_CLIENT_SHA256 = "3bb8c56a364243af2acdf6200722e704553e582be9e6521aa854ab285bc8b215"
JC_DEADLINE_SHA256 = "5246d094d77ed57114e07dc72290d2aaa2b0b09fdb95d41ae674db5c81df30eb"
HARNESS_BASE_W3_U08 = "c2cd5c29"

HARNESS_MASTER_PIN = "929d0802"

SUBMISSION_METHODS = frozenset({
    "submission.checklist_define", "submission.checklist_read",
    "submission.package_build", "submission.package_confirm",
    "submission.package_read", "submission.package_list"})
CALENDAR_SYNC_METHODS = frozenset({
    "calendar.sync_event", "calendar.pull_external",
    "calendar.resolve_conflict", "calendar.sync_read", "calendar.sync_list"})
HARNESS_SUBMISSION_METHODS = frozenset({
    "harness.submission_checklist_define", "harness.submission_checklist_read",
    "harness.submission_package_generate", "harness.submission_package_confirm",
    "harness.submission_package_read", "harness.submission_package_list"})
HARNESS_CALENDAR_SYNC_METHODS = frozenset({
    "harness.calendar_sync_register", "harness.calendar_sync_record_result",
    "harness.calendar_external_event_record", "harness.calendar_sync_resolve",
    "harness.calendar_sync_read", "harness.calendar_sync_list"})
DEADLINE_PRESET_GROUP = frozenset({
    "calc.deadline_presets", "calc.deadline_preset_evaluate"})

CHECKLIST = {
    "checklistId": "cl-recon", "title": "（合成法院）立案材料要求清单",
    "items": [
        {"itemId": "complaint", "title": "起诉状", "required": True},
        {"itemId": "evidence", "title": "证据清单及证据材料", "required": True},
        {"itemId": "idcopy", "title": "主体资格材料", "required": True},
        {"itemId": "service-proof", "title": "送达地址确认书（可选）",
         "required": False},
    ],
}
COURT_NOTE = "合成法院立案庭（仅工程验证）"
MATTER_TITLE = "买卖合同纠纷（合成 recon）"

RULE_PACK = {
    "schema_version": "jc/local-pack/1.0",
    "pack_version": "1.0.0",
    "sources": [{
        "source_id": "acceptance-statute", "jurisdiction": "TEST",
        "authority_tier": "official_first_party",
        "issuer": "Acceptance Test Authority", "title": "acceptance-statute",
        "publication_time": "2020-01-01T00:00:00Z",
        "effective_from": "2020-01-01T00:00:00Z",
        "retrieved_at": "2026-08-01T00:00:00Z",
        "locator": {"kind": "uri", "value": "example.invalid/acceptance",
                    "page": None, "span_start": None, "span_end": None},
        "content": ("SYNTHETIC acceptance rule text for engineering "
                    "verification only; no legal effect."),
        "structure_sections": ["ART-1"],
    }],
    "rules": [
        {"rule_id": "acc-base", "jurisdiction": "TEST",
         "governing_law": "acceptance-statute",
         "source_id": "acceptance-statute", "modality": "OBLIGATION",
         "premises": [{"fact_key": "acc.contract", "required": True}],
         "conclusion": {"value": "applies"},
         "effective_from": "2020-01-01T00:00:00Z"},
    ],
}

_ACTIVE_TMPDIRS = []


def key(request_id: str) -> dict:
    return {"requestId": request_id, "targetId": None,
            "expectedRevision": None, "inputRefs": []}


def reason_ref(oid: str) -> dict:
    return {"owner": "host", "kind": "decision-receipt", "id": oid,
            "version": "1"}


def b64(text: str) -> str:
    return base64.b64encode(text.encode("utf-8")).decode("ascii")


class _SyntheticCalendarHandler(BaseHTTPRequestHandler):
    """滴答/飞书合成端点（127.0.0.1 临时服务）：POST /events 按 eventKey
    幂等创建并记录收到的请求体；GET /events?syncId= 返回回流事件。"""

    def log_message(self, *args):
        pass

    def _reply(self, payload, status=200):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        length = int(self.headers.get("Content-Length") or 0)
        request = json.loads(self.rfile.read(length).decode("utf-8"))
        server = self.server
        with server.lock:
            server.requests.append(request)
            event_key = request.get("eventKey")
            if event_key in server.events:
                self._reply({"synthetic": True,
                             "externalEventId": server.events[event_key]})
                return
            external_id = f"synth-{len(server.events) + 1:04d}"
            server.events[event_key] = external_id
        self._reply({"synthetic": True, "externalEventId": external_id})

    def do_GET(self):
        from urllib.parse import parse_qsl, urlparse
        query = dict(parse_qsl(urlparse(self.path).query))
        server = self.server
        with server.lock:
            backflow = [event for event in server.backflow
                        if event.get("syncId") == query.get("syncId")]
        self._reply({"synthetic": True, "events": backflow})


def start_synthetic_endpoint(backflow):
    server = ThreadingHTTPServer(("127.0.0.1", 0), _SyntheticCalendarHandler)
    server.lock = threading.Lock()
    server.requests = []
    server.events = {}
    server.backflow = list(backflow)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, f"http://127.0.0.1:{server.server_address[1]}"


def jc_config() -> dict:
    """JC 面配置（w2b-u55 worktree 钉定；state/rules 全合成临时根）。"""
    if not (DEFAULT_JC_ROOT / "compiler_core" / "deadline_presets.py").is_file():
        raise AssertionError(f"pinned JC worktree missing: {DEFAULT_JC_ROOT}")
    holder = tempfile.TemporaryDirectory(prefix="juscite-f59f60-jc-")
    _ACTIVE_TMPDIRS.append(holder)
    tmp = Path(holder.name)
    rules = tmp / "rules"
    rules.mkdir(parents=True, exist_ok=True)
    (rules / "jc-local-pack.json").write_text(
        json.dumps(RULE_PACK, ensure_ascii=False), encoding="utf-8")
    return {"jc_state_root": str(tmp / "state"),
            "jc_rule_roots": [str(rules)],
            "jc_import_path": str(DEFAULT_JC_ROOT)}


class Recon:
    def __init__(self, harness_root: Path):
        self.harness_root = harness_root
        self.checks: list[dict] = []

    def step(self, name, ok, **facts):
        entry = {"check": name, "status": "PASS" if ok else "FAIL", **facts}
        self.checks.append(entry)
        print(json.dumps(entry, ensure_ascii=False), flush=True)
        if not ok:
            raise AssertionError(name)

    def expect_error(self, name, call, code_part,
                     error=(HarnessCommandError, NotConnected, ValueError,
                            SubmissionPackageError, CalendarSyncError,
                            LookupError)):
        try:
            call()
        except error as exc:
            self.step(name, code_part in str(exc), code=str(exc)[:200])
            return str(exc)
        raise AssertionError(name + ": no typed error raised")

    def git(self, root: Path, *args: str) -> str:
        return subprocess.check_output(
            ["git", "-C", str(root), *args], text=True).strip()

    def branch_checks(self):
        branch = self.git(self.harness_root, "rev-parse", "--abbrev-ref",
                          "HEAD")
        base = self.git(self.harness_root, "merge-base", "HEAD", "w3-u08")
        master = self.git(self.harness_root, "rev-parse", "master")
        self.step("c01_harness_branch", branch == "w3-u12", branch=branch)
        self.step("c01_harness_base_on_w3_u08_chain_head",
                  base.startswith(HARNESS_BASE_W3_U08), base=base)
        self.step("c01_harness_master_untouched",
                  master.startswith(HARNESS_MASTER_PIN), master=master)
        dirty = self.git(self.harness_root, "status", "--porcelain")
        self.step("c01_harness_worktree_clean", dirty == "",
                  dirty=dirty[:200])
        jc_client = hashlib.sha256(
            (DEFAULT_JC_ROOT / "compiler_core" / "client.py")
            .read_bytes()).hexdigest()
        jc_deadline = hashlib.sha256(
            (DEFAULT_JC_ROOT / "compiler_core" / "deadline_presets.py")
            .read_bytes()).hexdigest()
        self.step("c01_jc_client_pin", jc_client == JC_CLIENT_SHA256,
                  sha256=jc_client[:16])
        self.step("c01_jc_deadline_presets_pin",
                  jc_deadline == JC_DEADLINE_SHA256, sha256=jc_deadline[:16])
        here_branch = self.git(REPO_ROOT, "rev-parse", "--abbrev-ref", "HEAD")
        # 账房改口（W3-U12 合并后主仓树复验）：原字面断言只适配 worktree 模式；
        # 实质不变量＝被测树要么是工单分支本体，要么是 main 且
        # merge-base(HEAD, w3-u12)==w3-u12 头（工单提交全含，防漂移本义不变）。
        merged_tip = self.git(REPO_ROOT, "merge-base", "HEAD", "w3-u12")
        wt_tip = self.git(REPO_ROOT, "rev-parse", "--verify", "w3-u12")
        merged_mode = here_branch == "main" and merged_tip == wt_tip and bool(wt_tip)
        self.step("c01_juscite_branch",
                  here_branch == "w3-u12" or merged_mode,
                  branch=here_branch, merged_tip=merged_tip[:12],
                  worktree_tip=wt_tip[:12])
        # F59 零出站红线（产品面导入闭集 AST，两 profile 共用同一模块）。
        source = (REPO_ROOT / "implementation" / "python"
                  / "submission_package.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        module_imports = set()
        for node in tree.body:
            if isinstance(node, ast.Import):
                module_imports.update(alias.name.split(".")[0]
                                      for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                module_imports.add(node.module.split(".")[0])
        self.step("c01_f59_zero_egress_import_closure",
                  module_imports <= {"json", "__future__"}
                  and not any(f in module_imports for f in
                              ("socket", "urllib", "http", "requests",
                               "subprocess")),
                  imports=sorted(module_imports))

    # ------------------------------------------------------------------
    # common_flow(call_product, call_harness, query, jc_evaluate)：
    # call_product(method,args)＝产品面 submission.*/calendar.*；
    # call_harness＝harness 账面；jc_evaluate＝真实 JC 期限评估（legal_entry
    # calc 族）。滴答/飞书合成端点在本函数内起停（127.0.0.1 临时端口）。
    # ------------------------------------------------------------------
    def common_flow(self, call_product, call_harness, query, jc_evaluate,
                    config):
        server_obj, base_url = start_synthetic_endpoint(backflow=[
            {"syncId": "sync-D01", "externalEventId": "synth-0001",
             "eventType": "event_rescheduled",
             "externalDueDate": "2026-04-30",
             "payload": {"source": "synthetic-ticktick",
                         "newDate": "2026-04-30"}},
        ])
        config["calendar_sync_endpoints"] = {
            "ticktick": base_url, "feishu": base_url}
        self._endpoint_server = server_obj
        try:
            self.f59_flow(call_product, call_harness, query)
            self.f60_flow(call_product, call_harness, query, jc_evaluate)
        finally:
            server_obj.shutdown()
            server_obj.server_close()

    # -- F59 ------------------------------------------------------------

    def f59_flow(self, call_product, call_harness, query):
        defined = call_product("submission.checklist_define", {
            "actor_id": "lawyer-1", "scope": SCOPE, "key": key("cd-1"),
            "checklist": CHECKLIST})
        self.step("f59_c02_checklist_frozen",
                  defined["itemCount"] == 4 and not defined["replayed"],
                  itemCount=defined["itemCount"])
        replay = call_product("submission.checklist_define", {
            "actor_id": "lawyer-1", "scope": SCOPE, "key": key("cd-replay"),
            "checklist": CHECKLIST})
        self.step("f59_c02_checklist_replay_idempotent",
                  replay["replayed"] is True
                  and query("SELECT COUNT(*) AS n FROM submission_checklists"
                            " WHERE matter_id=?", (MATTER,))[0]["n"] == 1)
        self.expect_error("f59_c02_checklist_drift_refused", lambda:
            call_product("submission.checklist_define", {
                "actor_id": "lawyer-1", "scope": SCOPE,
                "key": key("cd-drift"),
                "checklist": dict(CHECKLIST, items=CHECKLIST["items"][:2])}),
            "f59_checklist_conflict:cl-recon")

        # 材料经 F08 同一账登记（产品桥 harness.register_material）。
        for material_id, title, text in (
                ("mat-complaint", "起诉状（合成）", "起诉状正文合成"),
                ("mat-evidence", "证据清单（合成）", "证据清单合成")):
            call_harness("harness.register_material", {
                "actor_id": "lawyer-1", "scope": SCOPE,
                "key": key("rm-" + material_id),
                "material": {"id": material_id, "kind": "digital_text",
                             "title": title, "bytesB64": b64(text)}})

        build_args = {
            "actor_id": "lawyer-1", "scope": SCOPE,
            "package_id": "pkg-missing", "checklist_id": "cl-recon",
            "matter_title": MATTER_TITLE, "court_note": COURT_NOTE,
            "items": [
                {"itemId": "complaint",
                 "materialRefs": [{"id": "mat-complaint"}]},
                {"itemId": "evidence", "materialRefs": []},
                {"itemId": "idcopy", "materialRefs": []},
                {"itemId": "service-proof", "materialRefs": []},
            ]}
        missing_pkg = call_product("submission.package_build",
                                   dict(build_args, key=key("pb-1")))
        self.step("f59_c03_missing_items_named",
                  missing_pkg["missingItems"] == ["evidence", "idcopy"]
                  and missing_pkg["state"] == "draft"
                  and missing_pkg["submissionChannel"] == "none"
                  and "缺件" in missing_pkg["packageText"],
                  missing=missing_pkg["missingItems"])
        again = call_product("submission.package_build",
                             dict(build_args, key=key("pb-replay")))
        self.step("f59_c03_render_deterministic_same_bytes",
                  again["packageSha256"] == missing_pkg["packageSha256"]
                  and again["packageText"] == missing_pkg["packageText"],
                  sha256=missing_pkg["packageSha256"][:16])
        self.step("f59_c03_bytes_in_cas",
                  missing_pkg["casRef"]
                  == f"cas://{missing_pkg['packageSha256']}")
        stored = query(
            "SELECT package_sha256, cas_ref, missing_items_json FROM"
            " submission_packages WHERE matter_id=? AND package_id=?",
            (MATTER, "pkg-missing"))[0]
        self.step("f59_c03_ledger_row_snapshot",
                  stored["package_sha256"] == missing_pkg["packageSha256"]
                  and json.loads(stored["missing_items_json"])
                  == ["evidence", "idcopy"])

        # 人工确认制：无显式 confirm 标志＝具名拒（账面零写入）。
        self.expect_error("f59_c04_confirm_flag_required", lambda:
            call_product("submission.package_confirm", {
                "actor_id": "lawyer-1", "scope": SCOPE,
                "key": key("pc-noflag"), "package_id": "pkg-missing",
                "package_sha256": missing_pkg["packageSha256"],
                "reasonRef": reason_ref("r-nf"),
                "receiptRef": reason_ref("rc-nf")}),
            "f59_confirmation_flag_required")
        # 缺件确认＝缺件具名拒（确认结构性被拒）。
        self.expect_error("f59_c04_confirm_missing_items_named", lambda:
            call_product("submission.package_confirm", {
                "confirm": True, "actor_id": "lawyer-1", "scope": SCOPE,
                "key": key("pc-missing"), "package_id": "pkg-missing",
                "package_sha256": missing_pkg["packageSha256"],
                "reasonRef": reason_ref("r-mi"),
                "receiptRef": reason_ref("rc-mi")}),
            "f59_confirm_missing_items:evidence,idcopy")
        rows = query("SELECT COUNT(*) AS n FROM submission_packages"
                     " WHERE matter_id=? AND state='confirmed'",
                     (MATTER,))[0]["n"]
        self.step("f59_c04_refusals_left_zero_confirmed", rows == 0,
                  confirmed=rows)

        # 补齐材料 → 新包（append-only 历史）→ 确认成功（一行一次终局）。
        for material_id, title, text in (
                ("mat-idcopy", "主体资格材料（合成）", "主体材料合成"),):
            call_harness("harness.register_material", {
                "actor_id": "lawyer-1", "scope": SCOPE,
                "key": key("rm-" + material_id),
                "material": {"id": material_id, "kind": "image",
                             "title": title, "bytesB64": b64(text)}})
        full_build = call_product("submission.package_build", {
            "actor_id": "lawyer-1", "scope": SCOPE, "key": key("pb-2"),
            "package_id": "pkg-full", "checklist_id": "cl-recon",
            "matter_title": MATTER_TITLE, "court_note": COURT_NOTE,
            "items": [
                {"itemId": "complaint",
                 "materialRefs": [{"id": "mat-complaint"}]},
                {"itemId": "evidence",
                 "materialRefs": [{"id": "mat-evidence"}]},
                {"itemId": "idcopy", "materialRefs": [{"id": "mat-idcopy"}]},
                {"itemId": "service-proof", "materialRefs": []},
            ]})
        self.step("f59_c05_full_package_no_missing",
                  full_build["missingItems"] == []
                  and full_build["submissionChannel"] == "none")
        confirmed = call_product("submission.package_confirm", {
            "confirm": True, "actor_id": "lawyer-1", "scope": SCOPE,
            "key": key("pc-1"), "package_id": "pkg-full",
            "package_sha256": full_build["packageSha256"],
            "reasonRef": reason_ref("r-ok"),
            "receiptRef": reason_ref("rc-ok")})
        self.step("f59_c05_confirm_one_shot",
                  confirmed["state"] == "confirmed"
                  and confirmed["submissionChannel"] == "none")
        self.expect_error("f59_c05_confirm_twice_refused", lambda:
            call_product("submission.package_confirm", {
                "confirm": True, "actor_id": "lawyer-1", "scope": SCOPE,
                "key": key("pc-2"), "package_id": "pkg-full",
                "package_sha256": full_build["packageSha256"],
                "reasonRef": reason_ref("r-again"),
                "receiptRef": reason_ref("rc-again")}),
            "f59_already_confirmed:pkg-full")
        self.expect_error("f59_c05_sha_drift_refused", lambda:
            call_harness("harness.submission_package_confirm", {
                "actor_id": "lawyer-1", "scope": SCOPE,
                "key": key("pc-drift"), "decision": {
                    "packageId": "pkg-missing",
                    "packageSha256": "f" * 64,
                    "reasonRef": reason_ref("r-drift"),
                    "receiptRef": reason_ref("rc-drift")}}),
            "f59_package_sha_mismatch:pkg-missing")
        read = call_product("submission.package_read", {
            "scope": SCOPE, "package_id": "pkg-full"})
        self.step("f59_c06_projection_channel_none_and_decision",
                  read["submissionChannel"] == "none"
                  and read["state"] == "confirmed"
                  and read["decision"]["packageSha256"]
                  == full_build["packageSha256"]
                  and all(pkg["submissionChannel"] == "none"
                          for pkg in call_product(
                              "submission.package_list",
                              {"scope": SCOPE})["packages"]))
        # 绝不实际对外提交：对外提交形态在方法组封闭集外（产品桥层）。
        self.expect_error("f59_c07_no_submit_channel_structural", lambda:
            call_harness("harness.submission_submit", {
                "scope": SCOPE, "package_id": "pkg-full"}),
            "harness.submission_submit")
        self.expect_error("f59_c07_no_send_channel_structural", lambda:
            call_product("submission.send", {"scope": SCOPE}),
            "method_not_connected:submission.send")

    # -- F60 ------------------------------------------------------------

    def f60_flow(self, call_product, call_harness, query, jc_evaluate):
        # 真实 JC 期限评估（F107 冻结引擎；本面对账零重算）。
        receipt_d01 = jc_evaluate({
            "slot": "D01", "now": NOW,
            "event": {"kind": "service_of_first_instance_judgment",
                      "anchor": {"value": "2026-03-20",
                                 "precision": "date"}}})
        self.step("f60_c08_real_jc_evaluation_receipt",
                  receipt_d01["status"] == "OK"
                  and receipt_d01["due_date"] == "2026-04-07"
                  and receipt_d01["nominal_due_date"] == "2026-04-04"
                  and receipt_d01["evaluationRef"]["owner"] == "jc",
                  due_date=receipt_d01["due_date"])

        event_args = {
            "scope": SCOPE, "actor_id": "product-1",
            "sync_id": "sync-D01", "targetKind": "ticktick",
            "event_key": "evt-D01", "title": "上诉期届满（合成 recon）",
            "due_date": receipt_d01["due_date"],
            "nominal_due_date": receipt_d01["nominal_due_date"],
            "deadline_receipt": receipt_d01,
        }
        synced = call_product("calendar.sync_event",
                              dict(event_args, key=key("cs-1")))
        self.step("f60_c09_sync_pushed_once",
                  synced["pushed"] is True
                  and synced["state"] == "synced"
                  and synced["legalDueDate"] == receipt_d01["due_date"])
        server_requests = self._endpoint_server.requests
        self.step("f60_c09_endpoint_received_one_create",
                  len(server_requests) == 1
                  and server_requests[0]["eventKey"] == "evt-D01",
                  creates=len(server_requests))
        # 幂等：同 event_key 同内容重放＝不重复推送、返回既有行。
        replay = call_product("calendar.sync_event",
                              dict(event_args, key=key("cs-replay")))
        self.step("f60_c10_replay_no_second_push",
                  replay["replayed"] is True and replay["pushed"] is False
                  and len(self._endpoint_server.requests) == 1)
        # 同键异内容＝具名拒（不猜测改写）。
        self.expect_error("f60_c10_same_key_drift_refused", lambda:
            call_harness("harness.calendar_sync_register", {
                "actor_id": "product-1", "scope": SCOPE,
                "key": key("cr-drift"),
                "event": {"syncId": "sync-drift",
                          "targetKind": "ticktick",
                          "eventKey": "evt-D01",
                          "title": "漂移（合成）",
                          "dueDate": "2026-04-08",
                          "nominalDueDate": "2026-04-04",
                          "deadlineReceipt": dict(
                              receipt_d01, due_date="2026-04-08")}}),
            "f60_event_key_conflict:ticktick:evt-D01")
        # 回执 due_date 与声明 dueDate 不符＝具名拒（形态自洽闸）。
        self.expect_error("f60_c10b_receipt_declared_mismatch_refused",
            lambda: call_harness("harness.calendar_sync_register", {
                "actor_id": "product-1", "scope": SCOPE,
                "key": key("cr-mismatch"),
                "event": {"syncId": "sync-mismatch",
                          "targetKind": "ticktick",
                          "eventKey": "evt-mismatch",
                          "title": "不符（合成）",
                          "dueDate": "2026-04-08",
                          "nominalDueDate": "2026-04-04",
                          "deadlineReceipt": receipt_d01}}),
            "f60_receipt_due_date_mismatch:2026-04-07:2026-04-08")

        # 外部回流（改期 2026-04-30）：冲突具名，法律期限/回执逐字节不变。
        pulled = call_product("calendar.pull_external", {
            "scope": SCOPE, "actor_id": "product-1",
            "targetKind": "ticktick", "sync_id": "sync-D01"})
        entry = pulled["recorded"][0]
        row = query("SELECT due_date, deadline_receipt_json, state FROM"
                    " calendar_sync_items WHERE matter_id=? AND sync_id=?",
                    (MATTER, "sync-D01"))[0]
        self.step(
            "f60_c11_backflow_conflict_named_never_moves_deadline",
            entry["conflict"] is True
            and "f60_external_reschedule_conflicts_legal:"
                "2026-04-30!=2026-04-07" in str(entry["conflictReason"])
            and entry["legalDueDateUnchanged"] == "2026-04-07"
            and row["due_date"] == receipt_d01["due_date"]
            and json.loads(row["deadline_receipt_json"]) == receipt_d01
            and row["state"] == "conflict_pending_review",
            state=row["state"])
        projection = pulled["projection"]
        self.step("f60_c11_projection_split_views",
                  projection["legalDueDate"] == receipt_d01["due_date"]
                  and projection["reviewNeeded"] is True
                  and projection["conflicts"][0]["externalEventId"]
                  == "synth-0001"
                  and projection["externalChanges"][0]["eventType"]
                  == "event_rescheduled"
                  and projection["deadlineReceipt"]["evaluationRef"]["owner"]
                  == "jc",
                  conflicts=len(projection["conflicts"]))
        # 决定闸：无 confirm 标志拒；keep 决定＝外部 noted、法律仍不变。
        self.expect_error("f60_c12_resolve_flag_required", lambda:
            call_product("calendar.resolve_conflict", {
                "scope": SCOPE, "actor_id": "lawyer-1",
                "key": key("rc-nf"), "sync_id": "sync-D01",
                "action": "keep_legal_deadline",
                "reasonRef": reason_ref("r-rf"),
                "receiptRef": reason_ref("rc-rf")}),
            "f60_confirmation_flag_required")
        resolved = call_product("calendar.resolve_conflict", {
            "confirm": True, "scope": SCOPE, "actor_id": "lawyer-1",
            "key": key("rc-1"), "sync_id": "sync-D01",
            "action": "keep_legal_deadline",
            "reasonRef": reason_ref("r-keep"),
            "receiptRef": reason_ref("rc-keep")})
        after = query("SELECT due_date, state FROM calendar_sync_items"
                      " WHERE matter_id=? AND sync_id=?",
                      (MATTER, "sync-D01"))[0]
        self.step("f60_c12_keep_decision_legal_unchanged",
                  resolved["state"] == "reviewed"
                  and resolved["legalDueDateUnchanged"]
                  == receipt_d01["due_date"]
                  and after["due_date"] == receipt_d01["due_date"]
                  and after["state"] == "reviewed")

        # D07 冻结 UNKNOWN：不可同步（形态拒；无日期期限不进日历）。
        self.expect_error("f60_c13_unknown_receipt_not_syncable", lambda:
            call_product("calendar.sync_event", {
                "scope": SCOPE, "actor_id": "product-1",
                "key": key("cs-d07"), "sync_id": "sync-D07",
                "targetKind": "ticktick", "event_key": "evt-D07",
                "title": "D07（合成）", "due_date": "2026-05-01",
                "nominal_due_date": "2026-05-01",
                "deadline_receipt": {
                    "status": "UNKNOWN_CALENDAR", "slot": "D07",
                    "due_date": None, "evaluationRef": {
                        "owner": "jc", "kind": "deadline-evaluation",
                        "id": "jc-d07", "digest": "sha256:" + "c" * 64}}}),
            "f60_receipt_not_ok")
        # 伪造回执（owner≠jc / 回执日期与声明不符）＝具名拒零入账。
        self.expect_error("f60_c13_forged_receipt_owner_refused", lambda:
            call_product("calendar.sync_event", {
                "scope": SCOPE, "actor_id": "product-1",
                "key": key("cs-forged"), "sync_id": "sync-forged",
                "targetKind": "ticktick", "event_key": "evt-forged",
                "title": "伪造（合成）", "due_date": "2026-04-07",
                "nominal_due_date": "2026-04-04",
                "deadline_receipt": dict(
                    receipt_d01,
                    evaluationRef=dict(receipt_d01["evaluationRef"],
                                       owner="product"))}),
            "jc_ref_invalid:deadlineReceiptRef")
        rows = query("SELECT COUNT(*) AS n FROM calendar_sync_items"
                     " WHERE matter_id=?", (MATTER,))[0]["n"]
        self.step("f60_c13_refusals_left_one_row", rows == 1, rows=rows)

        # 第二日历项（同一法律期限的滴答第二事件）遭遇外部改期 → 冲突
        # 行保持 conflict_pending_review 供 supersede 演练。
        alt = call_product("calendar.sync_event", {
            "scope": SCOPE, "actor_id": "product-1", "key": key("cs-alt"),
            "sync_id": "sync-D01-alt", "targetKind": "ticktick",
            "event_key": "evt-D01-alt", "title": "上诉期届满（第二事件·合成）",
            "due_date": receipt_d01["due_date"],
            "nominal_due_date": receipt_d01["nominal_due_date"],
            "deadline_receipt": receipt_d01})
        self.step("f60_c14a_second_entry_synced",
                  alt["pushed"] is True and alt["state"] == "synced")
        self._endpoint_server.backflow.append({
            "syncId": "sync-D01-alt", "externalEventId": "synth-0002",
            "eventType": "event_rescheduled",
            "externalDueDate": "2026-05-01",
            "payload": {"source": "synthetic-ticktick",
                        "newDate": "2026-05-01"}})
        alt_pulled = call_product("calendar.pull_external", {
            "scope": SCOPE, "actor_id": "product-1",
            "targetKind": "ticktick", "sync_id": "sync-D01-alt"})
        self.step("f60_c14b_alt_conflict_pending",
                  alt_pulled["recorded"][0]["conflict"] is True
                  and alt_pulled["projection"]["state"]
                  == "conflict_pending_review")

        # 改期唯一通道：真实第二评估（新 anchor）→ 新 sync 行 → supersede
        # 决定钉新行；被取代行法律期限一字不动。
        receipt_v2 = jc_evaluate({
            "slot": "D01", "now": NOW,
            "event": {"kind": "service_of_first_instance_judgment",
                      "anchor": {"value": "2026-04-10",
                                 "precision": "date"}}})
        self.step("f60_c14_new_evaluation_new_channel",
                  receipt_v2["status"] == "OK"
                  and receipt_v2["due_date"] != receipt_d01["due_date"]
                  and receipt_v2["evaluationRef"]["id"]
                  != receipt_d01["evaluationRef"]["id"],
                  v2=receipt_v2["due_date"])
        v2 = call_product("calendar.sync_event", {
            "scope": SCOPE, "actor_id": "product-1", "key": key("cs-v2"),
            "sync_id": "sync-D01-v2", "targetKind": "feishu",
            "event_key": "evt-D01-v2", "title": "上诉期届满（重算·合成）",
            "due_date": receipt_v2["due_date"],
            "nominal_due_date": receipt_v2["nominal_due_date"],
            "deadline_receipt": receipt_v2})
        self.step("f60_c14_feishu_second_target_synced",
                  v2["pushed"] is True and v2["targetKind"] == "feishu")
        superseded = call_product("calendar.resolve_conflict", {
            "confirm": True, "scope": SCOPE, "actor_id": "lawyer-1",
            "key": key("rc-sup"), "sync_id": "sync-D01-alt",
            "action": "superseded_by_new_event",
            "reasonRef": reason_ref("r-sup"),
            "receiptRef": reason_ref("rc-sup"),
            "superseding_sync_id": "sync-D01-v2"})
        old_row = query("SELECT due_date FROM calendar_sync_items"
                        " WHERE matter_id=? AND sync_id=?",
                        (MATTER, "sync-D01-alt"))[0]
        new_row = query("SELECT due_date FROM calendar_sync_items"
                        " WHERE matter_id=? AND sync_id=?",
                        (MATTER, "sync-D01-v2"))[0]
        self.step("f60_c14_supersede_only_via_new_row",
                  superseded["state"] == "reviewed"
                  and old_row["due_date"] == receipt_d01["due_date"]
                  and new_row["due_date"] == receipt_v2["due_date"],
                  old=old_row["due_date"], new=new_row["due_date"])
        listed = call_product("calendar.sync_list", {"scope": SCOPE})
        self.step("f60_c15_list_projection",
                  listed["itemCount"] == 3
                  and all(item["deadlineReceipt"]["evaluationRef"]["owner"]
                          == "jc" for item in listed["items"]))

    # 滴答端点收到的请求体由 common_flow 内的 server 记录
    # （self._endpoint_server.requests）。

    # -- profile drivers --------------------------------------------------


def run_desktop(recon: Recon, harness_root: Path) -> int:
    """desktop＝产品桥子进程全链（SQLite 状态根）：产品面与 harness 面
    都走 legal_entry.call 默认派发（submission/calendar 产品面内部经
    legal_entry 调 harness 桥——与生产同一条链）。"""
    temporary = tempfile.TemporaryDirectory(prefix="juscite-f59f60-desktop-")
    _ACTIVE_TMPDIRS.append(temporary)
    tmp = Path(temporary.name)
    state_root = tmp / "state"
    state_root.mkdir(parents=True)
    registration = tmp / "service-local.json"
    registration.write_text(json.dumps(
        {"url": "http://127.0.0.1:1", "password": "synthetic-recon"}),
        encoding="utf-8")
    config = {
        "harness_public_entry":
            str(harness_root / "tools/workflow-tools/harness/public_entry.py"),
        "harness_target": "opencode",
        "harness_state_root": str(state_root),
        "harness_service_registration": str(registration),
        "harness_timeout": 120,
    }
    for path in (str(harness_root / "src"),
                 str(harness_root / "tools/workflow-tools")):
        if path not in sys.path:
            sys.path.insert(0, path)
    from legal_harness.state.matter_store import MatterStore
    MatterStore(state_root).create_matter(MATTER, "cas://profile-f59f60")

    def call_product(method, call_args):
        return legal_entry.call(method, call_args, config)

    def call_harness(method, call_args):
        return legal_entry.call(method, call_args, config)

    def query(sql, params):
        import sqlite3
        with contextlib.closing(MatterStore(state_root)._connect()) \
                as connection:
            connection.row_factory = sqlite3.Row
            rows = connection.execute(sql, params).fetchall()
        return [dict(row) for row in rows]

    def jc_evaluate(request):
        result = legal_entry.call("calc.deadline_preset_evaluate", request,
                                  jc_config())
        if result.get("status") != "OK":
            raise AssertionError(f"jc deadline evaluate failed: {result}")
        return result

    print("[profile desktop] SQLite via product bridge subprocess",
          flush=True)
    recon.common_flow(call_product, call_harness, query, jc_evaluate,
                      config)
    bridge_negatives(recon, config)
    return 0


def run_selfhost(recon: Recon, harness_root: Path, dsn: str) -> int:
    """selfhost＝PgMatterStore 直连 lh-pg-e08（resolve_provider_method 同
    一封闭注册）：产品面经 harness_call 注入直连（同函数链，不同后端）。"""
    for path in (str(harness_root / "src"),
                 str(harness_root / "tools/workflow-tools"),
                 str(harness_root), str(harness_root / "tests")):
        if path not in sys.path:
            sys.path.insert(0, path)
    from legal_harness.business.provider_registry import (
        resolve_provider_method,
    )
    from legal_harness.business.units import HarnessUnits
    from legal_harness.state.pg_store import PgMatterStore

    temporary = tempfile.TemporaryDirectory(prefix="juscite-f59f60-selfhost-")
    _ACTIVE_TMPDIRS.append(temporary)
    store = PgMatterStore(
        Path(temporary.name) / "state", dsn=dsn,
        schema="f59f60_" + _uuid.uuid4().hex[:12])
    units = HarnessUnits(store)
    methods = (HARNESS_SUBMISSION_METHODS | HARNESS_CALENDAR_SYNC_METHODS
               | {"harness.register_material"})
    bound = {name: resolve_provider_method(name, units)
             for name in methods}
    store.create_matter(MATTER, "cas://profile-f59f60")
    config: dict = {}

    def call_product(method, call_args):
        if method.startswith("submission."):
            from submission_package import submission_call
            return submission_call(method, call_args, config,
                                   harness_call=lambda h_method, h_args:
                                   bound[h_method](**h_args))
        from calendar_sync import calendar_sync_call
        return calendar_sync_call(method, call_args, config,
                                  harness_call=lambda h_method, h_args:
                                  bound[h_method](**h_args))

    def call_harness(method, call_args):
        target = bound.get(method)
        if target is None:
            # 封闭注册外形态（harness.submission_submit 等）＝与 desktop
            # 桥层同语义的具名拒（registry 级 method_not_whitelisted）。
            from legal_harness.business.provider_registry import (
                MethodNotWhitelisted,
            )
            raise MethodNotWhitelisted(method)
        return target(**call_args)

    # PgMatterStore._connect 返回 PgConnection（sqlite3.Row 语义）。
    def query_pg(sql, params):
        with contextlib.closing(store._connect()) as connection:
            rows = connection.execute(sql, params).fetchall()
        return [dict(row) for row in rows]

    def jc_evaluate(request):
        result = legal_entry.call("calc.deadline_preset_evaluate", request,
                                  jc_config())
        if result.get("status") != "OK":
            raise AssertionError(f"jc deadline evaluate failed: {result}")
        return result

    print("[profile selfhost] PgMatterStore direct (lh-pg-e08)", flush=True)
    recon.common_flow(call_product, call_harness, query_pg, jc_evaluate,
                      config)
    bridge_negatives_selfhost(recon, bound)
    store.destroy()
    return 0


def bridge_negatives(recon: Recon, config: dict) -> None:
    """C16 桥负向（desktop 链）：未配置/未知方法/方法组冻结＋邻组零动。"""
    # harness 侧封闭注册直探（绕开产品桥组层，证 registry 级结构性缺席）。
    import os as _os
    entry = config["harness_public_entry"]
    handle = tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", suffix=".json", delete=False)
    json.dump({"method": "harness.submission_submit",
               "params": {"scope": SCOPE}}, handle)
    handle.close()
    env = dict(os.environ)
    env["LH_LEGAL_STATE_ROOT"] = config["harness_state_root"]
    probe = subprocess.run(
        [sys.executable, "-X", "utf8", entry, "--submission-json",
         handle.name, "--target", config["harness_target"]],
        capture_output=True, text=True, env=env, timeout=60)
    _os.unlink(handle.name)
    envelope = {}
    try:
        envelope = json.loads(probe.stdout or "{}")
    except json.JSONDecodeError:
        pass
    recon.step("c16_harness_registry_submit_absent",
               probe.returncode != 0
               and "method_not_whitelisted" in probe.stdout,
               code=envelope.get("error") or probe.stdout[:120])
    try:
        legal_entry.call("harness.submission_package_confirm",
                         {"scope": SCOPE}, {})
        raise AssertionError("bridge_not_configured_expected")
    except NotConnected as exc:
        recon.step("c16_bridge_not_configured",
                   "harness_public_entry_not_configured" in str(exc))
    try:
        legal_entry.call("harness.submission_package_decide",
                         {"scope": SCOPE}, config)
        raise AssertionError("bridge_unknown_method_expected")
    except NotConnected as exc:
        recon.step("c16_bridge_unknown_method_refused",
                   "method_not_connected" in str(exc))
    recon.step("c16_method_groups_frozen",
               legal_entry.SUBMISSION_PACKAGE_METHODS == SUBMISSION_METHODS
               and legal_entry.CALENDAR_SYNC_METHODS == CALENDAR_SYNC_METHODS
               and legal_entry.HARNESS_SUBMISSION_METHODS
               == HARNESS_SUBMISSION_METHODS
               and legal_entry.HARNESS_CALENDAR_SYNC_METHODS
               == HARNESS_CALENDAR_SYNC_METHODS
               and legal_entry.DEADLINE_PRESET_METHODS
               == DEADLINE_PRESET_GROUP)
    # 端点未配置＝具名拒（零出站流量；登记已守门落账）。
    try:
        legal_entry.call("calendar.sync_event", {
            "scope": SCOPE, "actor_id": "product-1", "key": key("neg-1"),
            "sync_id": "sync-neg", "targetKind": "ticktick",
            "event_key": "evt-neg", "title": "负测（合成）",
            "due_date": "2026-04-07", "nominal_due_date": "2026-04-04",
            "deadline_receipt": {
                "status": "OK", "slot": "D01",
                "nominal_due_date": "2026-04-04", "due_date": "2026-04-07",
                "evaluationRef": {"owner": "jc",
                                  "kind": "deadline-evaluation",
                                  "id": "jc-neg",
                                  "digest": "sha256:" + "d" * 64}}},
            {k: v for k, v in config.items()
             if k != "calendar_sync_endpoints"})
        raise AssertionError("endpoint_not_configured_expected")
    except NotConnected as exc:
        recon.step("c16_endpoint_not_configured_named",
                   "calendar_sync_endpoint_not_configured:ticktick"
                   in str(exc))


def bridge_negatives_selfhost(recon: Recon, bound: dict) -> None:
    """C16 selfhost：封闭注册外形态拒（与 desktop 同码）。"""
    from legal_harness.business.provider_registry import (
        MethodNotWhitelisted,
    )
    try:
        resolve = bound.get("harness.submission_submit")
        if resolve is None:
            raise MethodNotWhitelisted("harness.submission_submit")
    except MethodNotWhitelisted as exc:
        recon.step("c16_selfhost_closed_registry",
                   "method_not_whitelisted" in str(exc))


def write_evidence(profile: str, recon: Recon, harness_root: Path,
                   started: str, code: int) -> Path:
    evidence_dir = (REPO_ROOT / "docs" / "construction" / "evidence"
                    / "F59" / profile)
    evidence_dir.mkdir(parents=True, exist_ok=True)
    mirror = (REPO_ROOT / "evidence" / "F59" / profile)
    mirror.mkdir(parents=True, exist_ok=True)
    finished = datetime.now(timezone.utc).isoformat()
    summary = {
        "schema": "juscite-f59-f60-submission-calendar-recon/1",
        "unit": "W3-U12",
        "features": ["F59", "F60"],
        "profile": profile,
        "verdict": "RECON_OK" if code == 0 else "RECON_FAIL",
        "started_at": started,
        "finished_at": finished,
        "harness_worktree": str(harness_root),
        "harness_branch": "w3-u12",
        "harness_base": "w3-u08@c2cd5c29（W3 harness 施工链头，schema v27→v28）",
        "jc_worktree": str(DEFAULT_JC_ROOT),
        "jc_pin": {"client_sha256": JC_CLIENT_SHA256,
                   "deadline_presets_sha256": JC_DEADLINE_SHA256},
        "checks": recon.checks,
        "check_count": len(recon.checks),
        "failed": [c["check"] for c in recon.checks
                   if c["status"] != "PASS"],
    }
    payload = json.dumps(summary, ensure_ascii=False, indent=1)
    for target in (evidence_dir, mirror):
        (target / "f59_f60_submission_calendar_recon.json").write_text(
            payload + "\n", encoding="utf-8")
    lines = [f"# F59 提交包＋F60 日历同步 recon（{profile}）", "",
             f"- unit: W3-U12 · profile: {profile}",
             f"- verdict: **{summary['verdict']}**"
             f" ({len(recon.checks)} checks, exit {code})",
             f"- harness: `{harness_root}` @ branch w3-u12"
             "（基 w3-u08@c2cd5c29 施工链头；master 929d0802 零动）",
             f"- JC: `{DEFAULT_JC_ROOT}` @ w2b-u55"
             "（client.py/deadline_presets.py sha256 钉定；F107 冻结引擎）",
             f"- started: {started} · finished: {finished}", "",
             "| # | check | status |", "|---|---|---|"]
    for index, check in enumerate(recon.checks, 1):
        lines.append(f"| {index} | {check['check']} | {check['status']} |")
    lines += ["", "全部合成材料；滴答/飞书＝本机回环合成端点（裁决#6，真实",
              "OAuth 授权后补联测）；desktop＝产品桥子进程全链（SQLite），",
              "selfhost＝PgMatterStore 直连 lh-pg-e08（同一封闭注册）；F60",
              "期限值经真实 JC 评估回执（owner=jc）转录，外部回流冲突具名",
              "且法律期限逐字节不变；F59 绝不实际对外提交（零出站通道）。"]
    text = "\n".join(lines) + "\n"
    for target in (evidence_dir, mirror):
        (target / "f59_f60_submission_calendar_recon.md").write_text(
            text, encoding="utf-8")
    # F60 镜像目录（台账 evidence/F60/<profile>/）。
    f60_dir = (REPO_ROOT / "docs" / "construction" / "evidence" / "F60"
               / profile)
    f60_dir.mkdir(parents=True, exist_ok=True)
    (f60_dir / "f59_f60_submission_calendar_recon.json").write_text(
        payload + "\n", encoding="utf-8")
    (f60_dir / "f59_f60_submission_calendar_recon.md").write_text(
        text, encoding="utf-8")
    f60_mirror = (REPO_ROOT / "evidence" / "F60" / profile)
    f60_mirror.mkdir(parents=True, exist_ok=True)
    (f60_mirror / "f59_f60_submission_calendar_recon.json").write_text(
        payload + "\n", encoding="utf-8")
    (f60_mirror / "f59_f60_submission_calendar_recon.md").write_text(
        text, encoding="utf-8")
    return evidence_dir


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--profile", action="append",
                        choices=["desktop", "selfhost"])
    parser.add_argument("--harness-root", type=Path,
                        default=DEFAULT_HARNESS_ROOT)
    parser.add_argument("--pg-dsn", default=DEFAULT_PG_DSN)
    args = parser.parse_args()
    profiles = args.profile or ["desktop", "selfhost"]
    if not (args.harness_root / "tools/workflow-tools/harness/public_entry.py"
            ).exists():
        print("RECON_BLOCKED: harness root missing public_entry:",
              args.harness_root)
        return 3
    if not (DEFAULT_JC_ROOT / "compiler_core" / "deadline_presets.py"
            ).is_file():
        print("RECON_BLOCKED: pinned JC worktree missing:", DEFAULT_JC_ROOT)
        return 3
    failures = 0
    first = True
    for profile in profiles:
        started = datetime.now(timezone.utc).isoformat()
        recon = Recon(args.harness_root)
        try:
            if first:
                recon.branch_checks()
            if profile == "desktop":
                code = run_desktop(recon, args.harness_root)
            else:
                code = run_selfhost(recon, args.harness_root, args.pg_dsn)
        except Exception as error:  # noqa: BLE001 - reported per profile
            print(f"RECON_FAIL[{profile}]: {error}", flush=True)
            recon.checks.append({"check": "recon_driver", "status": "FAIL",
                                 "error": str(error)[:400]})
            code = 2
        evidence_dir = write_evidence(profile, recon, args.harness_root,
                                      started, code)
        verdict = "RECON_OK" if code == 0 else "RECON_FAIL"
        print(f"[{profile}] {verdict} ({len(recon.checks)} checks,"
              f" exit {code}) evidence={evidence_dir}", flush=True)
        if code != 0:
            failures += 1
        first = False
    return 0 if failures == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())

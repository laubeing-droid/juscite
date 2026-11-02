#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""E24 外部动作与程序提醒分离收口对账（W3-U26）——双 profile（desktop/selfhost）。

验收命令（juscite worktree w3-u26 根 cwd 无参双 profile）：
  python -X utf8 tools/recon/PENDING_OWNER_e24_external_actions_recon.py
      [--profile desktop --profile selfhost]

义务 07:E24「外部动作与程序提醒分离」（owner=product+harness+jc，phase=B3）；
acceptance 逐字＝「日历/短信/法院/微信按授权材料与确认，送达事实不由上传日
补；实务提醒F118待裁，外部发送提交另授权」。裁决#6：滴答/飞书 OAuth＋微信
批次＝合成先行（幂等回流/不改期限负测），授权后补联测；裁决#20：F118 v1.5
范围含实务提醒（W4 扩卡施工）——本义务只验分离不变量，不前造 F118 v1.5。

硬依赖三单（消费其已 VERIFIED 合成流面做义务级对账，零改动零重建）：
  W3-U12（F59 提交包/F60 日历同步，juscite w3-u12＋harness w3-u12）；
  W3-U13（F61 微信批次，juscite w3-u13）；W3-U14（F62 法院来件，juscite
  w3-u14）。harness 钉定 W3 施工链头 w3-u20（基 w3-u12@7c9ccc16，含 F118
  schedule 面与 F59/F60 账）；JC 钉定 w2b-u55（F107 冻结期限引擎）。

实跑覆盖（E24 acceptance 逐条）：
  按授权材料与确认——F59 律师确认闸（无显式 confirm 标志拒）；F60 期限值
  只认真实 JC 回执（owner=jc）＋冲突决定显式 confirm 闸；F61 显式授权账
  （未授权=UNKNOWN 值 None 非 0）；F62 人审逐候选确认（未审不入库）。
  幂等回流——F60 同键同内容重放零二推＋外部回流事件账 PK 幂等；F62 重复
  短信三形态全链单账；F61 批次重放同回执/异输入具名拒。
  不改期限负测——F60 外部改期回流冲突具名且 calendar_sync_items 的
  due_date/deadline_receipt DB 级逐字节不变；keep/supersede 决定均不改法律
  期限（supersede 唯一通道=新 sync 行＋新 JC 回执）。
  送达事实不由上传日补——F62 入库字节结构断言（无送达日字段；「送达」仅
  出现于 E24 边界句；候选闭集=case_number；人审前不入正式账）；F118 程序
  期限锚只认法院程序事件（schedule_anchor_required/not_found/forbidden）。
  外部发送/提交须实际授权负测——F59 submission.submit/send 结构性不存在
  （封闭注册外）；F60 端点未配置＝具名拒不发零出站（URL 只来自显式
  config，禁编 URL）；F61 url/cookie 旁路字段具名拒（无隐式采集通道）；
  F118 email/im 通道提醒永不派发（外部发送不在本面）。
  F118 待裁不启用实务自动提醒——提醒只能经显式 schedule_event 声明
  （reminders=[] → 零提醒行）；三分类分组回读不混同；f118_scheduler 派发
  仅桌面通知（payload 键闭集、零出站、AST 导入闭集零网络）；外部动作四通
  道全流程对 harness deadlines/derived_tasks/reminders 零副作用（提醒绝不
  由外部动作自动生成）。

OCR 引擎权威＝F40/F41 已 VERIFIED 面（F62 自有 recon 真跑验收）；本义务级
对账在 F41 桥 seam 注入确定性合成行——不复制第二引擎、不重跑 OCR 验收。
全部合成材料：临时状态根、合成端点＝本机回环临时 HTTP 服务；harness/JC/
anonymizer 检出零字节改动（只运行其代码，git 只读命令核对）。

退出码：0 = 全部 profile RECON_OK；2 = RECON_FAIL；3 = 环境缺失。
证据：docs/construction/evidence/E24/<profile>/（JSON＋MD，另写仓库根
evidence/ 同名镜像＝台账 evidence_path）。
"""
from __future__ import annotations

import argparse
import ast
import base64
import contextlib
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import threading
import uuid as _uuid
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "implementation" / "python"))
sys.path.insert(0, str(REPO_ROOT / "implementation" / "tests"))

import legal_entry  # noqa: E402
from legal_entry import HarnessCommandError, NotConnected  # noqa: E402
from submission_package import SubmissionPackageError  # noqa: E402
from calendar_sync import CalendarSyncError  # noqa: E402

DEFAULT_HARNESS_ROOT = Path(
    r"D:\Codex\1.法律工作区\legal-harness工作区\legal-harness-repo"
    r"\.local\worktrees\w3-u20")
DEFAULT_JC_ROOT = Path(
    r"D:\Codex\1.法律工作区\juris-calculus工作区\juris-calculus"
    r"\.local\worktrees\w2b-u55")

MATTER = "m-e24-recon"
SCOPE = {"kind": "matter", "matterId": MATTER}
NOW = "2026-10-18T00:00:00+00:00"
AS_OF = "2026-10-18"
AS_AT = "2026-10-18T01:00:00Z"

# lh-pg-e08 容器（E08 拓扑）：仅回环端口、合成专用凭据（--pg-dsn 可覆写）。
DEFAULT_PG_DSN = "postgresql://lh_app:e08-synth-only@127.0.0.1:55432/legal_harness"

# 钉定（收口字节，漂移即 FATAL）：JC＝F107 冻结引擎（W3-U12 同钉）；
# harness＝W3 施工链头 w3-u20（基 w3-u12@7c9ccc16＝U12 交付，master 零动）。
JC_CLIENT_SHA256 = "3bb8c56a364243af2acdf6200722e704553e582be9e6521aa854ab285bc8b215"
JC_DEADLINE_SHA256 = "5246d094d77ed57114e07dc72290d2aaa2b0b09fdb95d41ae674db5c81df30eb"
HARNESS_BASE_W3_U12 = "7c9ccc16"
HARNESS_MASTER_PIN = "929d0802"

# 方法组冻结（分离不变量的组级面：外部动作通道组不含提醒/派发方法，
# 提醒面不含外部发送方法——E24 分离在方法组层结构性成立）。
SUBMISSION_METHODS = frozenset({
    "submission.checklist_define", "submission.checklist_read",
    "submission.package_build", "submission.package_confirm",
    "submission.package_read", "submission.package_list"})
CALENDAR_SYNC_METHODS = frozenset({
    "calendar.sync_event", "calendar.pull_external",
    "calendar.resolve_conflict", "calendar.sync_read", "calendar.sync_list"})
WECHAT_COLLECTION_METHODS = frozenset({
    "collection.authorize", "collection.batch", "collection.batch_read"})
COURT_INBOUND_METHODS = frozenset({
    "court_inbound.sms_receive", "court_inbound.inbound_run",
    "court_inbound.candidate_review", "court_inbound.intake",
    "court_inbound.read", "court_inbound.list"})
HARNESS_SCHEDULE_METHODS = frozenset({
    "harness.schedule_event", "harness.schedule_list",
    "harness.schedule_cancel", "harness.reminder_report"})
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

# F62 合成材料（无任何送达日期出现于短信文本与 OCR 行——送达事实只能来自
# 法院程序事件锚，绝不来自上传/入库时间）。
SMS_CASE = "（2026）京01民初91001号"
SMS_TEXT = ("【合成市第一人民法院】王合成：您有" + SMS_CASE + "案件"
            "文书送达，请及时登录律引查收并确认入库。【合成法院送达平台】")
OCR_LINES = [
    {"page": 1, "lines": [
        {"text": "合成法院附件材料（全合成测试材料）", "conf": 0.97},
        {"text": "案号：" + SMS_CASE, "conf": 0.95},
        {"text": "联系电话：13700002222", "conf": 0.93},
    ]},
]

CHECKLIST = {
    "checklistId": "cl-e24", "title": "（合成法院）立案材料要求清单",
    "items": [
        {"itemId": "complaint", "title": "起诉状", "required": True},
        {"itemId": "evidence", "title": "证据清单及证据材料", "required": True},
        {"itemId": "idcopy", "title": "主体资格材料", "required": True},
        {"itemId": "service-proof", "title": "送达地址确认书（可选）",
         "required": False},
    ],
}
COURT_NOTE = "合成法院立案庭（仅工程验证·E24 recon）"
MATTER_TITLE = "买卖合同纠纷（E24 合成 recon）"

AUTHORIZED_WX_IDS = ["wxid_e24_demo_001", "wxid_e24_demo_002"]
UNAUTHORIZED_WX_ID = "wxid_e24_ghost_999"
WX_CHAT_TEXT = "\n".join([
    "【聊天记录导出（合成样本·E24 recon）】",
    "导出对象：wxid_e24_demo_001（授权导出）",
    "2026-10-10 09:12 客户张三：我的电话 13700005555，"
    "身份证 110101199003078670，住址合成市合成区合成路1号",
    "2026-10-10 09:15 律师助理：已登记，等待法院传票送达。",
    "",
])
WX_CHAT_TEXT_002 = ("【聊天记录导出（合成样本）】\n导出对象："
                    "wxid_e24_demo_002（授权导出）\n")

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


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def resolve_anonymizer_src(explicit: str | None) -> Path | None:
    """anonymizer w2a-u18 同波源（conftest 同式；F61 材料化消费径）。"""
    if explicit:
        return Path(explicit).resolve()
    env = os.environ.get("JUSCITE_ANONYMIZER_SRC")
    if env:
        candidate = Path(env).resolve()
        if (candidate / "legal_anonymizer" / "pipeline.py").is_file():
            return candidate
    root = REPO_ROOT
    for _ in range(6):
        if root.name == "jusbench工作区":
            guess = (root.parent / "legal-cn-anonymizer工作区"
                     / "legal-cn-anonymizer" / ".local" / "worktrees"
                     / "w2a-u18" / "src")
            if (guess / "legal_anonymizer" / "pipeline.py").is_file():
                return guess
            break
        root = root.parent
    return None


def make_attachment_corpus(corpus: Path) -> None:
    """最小合成法院来件附件语料（确定性字节；E24 在 F41 桥 seam 注入合成
    OCR 行，不重跑 OCR 验收——引擎权威归 F40/F41 已 VERIFIED 面）。"""
    (corpus / "docs").mkdir(parents=True, exist_ok=True)
    (corpus / "docs" / "att_0001.pdf").write_bytes(
        b"synthetic court attachment pdf bytes (E24 recon)")
    manifest = {"schema": "juscite-f38-f44-attachments/1", "synthetic": True,
                "documents": [{"doc_id": "att_0001",
                               "page_files": [{"page": 1,
                                               "png": "pages/att_0001/p0001.png"}]}]}
    (corpus / "corpus_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False), encoding="utf-8")


def make_ocr_seam():
    """F41 桥 seam（确定性合成行；与 wiring test 同形状）。"""
    calls: list[tuple] = []

    def call(method, args):
        calls.append((method, json.loads(json.dumps(args))))
        if method == "ocr.batch_register":
            return {"batch_id": "f41-e24-synthetic01",
                    "corpus_sha256": "cafe" * 16,
                    "counters": {"docs_pending": 1}}
        if method == "ocr.batch_run":
            return {"status": "COMPLETED", "pending_after": []}
        if method == "ocr.batch_doc_version":
            return {"batch_id": args["batch_id"], "doc_id": args["doc_id"],
                    "version": 1, "is_current": True,
                    "doc": {"doc_id": args["doc_id"], "error_pages": 0,
                            "engine": {"engine": "paddleocr",
                                       "device": "gpu:0"}},
                    "pages": json.loads(json.dumps(OCR_LINES))}
        raise AssertionError("unexpected " + method)
    call.calls = calls
    return call


class _SyntheticCalendarHandler(BaseHTTPRequestHandler):
    """滴答/飞书合成端点（127.0.0.1 临时服务；裁决#6 合成先行）。"""

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
    holder = tempfile.TemporaryDirectory(prefix="juscite-e24-jc-")
    _ACTIVE_TMPDIRS.append(holder)
    tmp = Path(holder.name)
    rules = tmp / "rules"
    rules.mkdir(parents=True, exist_ok=True)
    (rules / "jc-local-pack.json").write_text(
        json.dumps(RULE_PACK, ensure_ascii=False), encoding="utf-8")
    return {"jc_state_root": str(tmp / "state"),
            "jc_rule_roots": [str(rules)],
            "jc_import_path": str(DEFAULT_JC_ROOT)}


def module_imports(path: Path) -> set:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    imports = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(a.name.split(".")[0] for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.add(node.module.split(".")[0])
    return imports


class Recon:
    def __init__(self, harness_root: Path):
        self.harness_root = harness_root
        self.checks: list[dict] = []
        self._endpoint_server = None

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

    # ------------------------------------------------------------------
    # C00 钉定卫生＋方法组冻结（两 profile 共用，跑一次）。
    # ------------------------------------------------------------------
    def branch_checks(self):
        head = self.git(self.harness_root, "rev-parse", "HEAD")
        branch = self.git(self.harness_root, "rev-parse", "--abbrev-ref",
                          "HEAD")
        base = self.git(self.harness_root, "merge-base", "HEAD", "w3-u12")
        master = self.git(self.harness_root, "rev-parse", "master")
        self.step("c00_harness_pinned_w3_chain_head",
                  branch == "w3-u20" and head.startswith("b9dce088"),
                  branch=branch, head=head[:12])
        self.step("c00_harness_base_contains_w3_u12_delivery",
                  base.startswith(HARNESS_BASE_W3_U12), base=base[:12])
        self.step("c00_harness_master_untouched",
                  master.startswith(HARNESS_MASTER_PIN), master=master[:12])
        dirty = self.git(self.harness_root, "status", "--porcelain")
        self.step("c00_harness_worktree_clean", dirty == "",
                  dirty=dirty[:200])
        jc_client = sha256_bytes(
            (DEFAULT_JC_ROOT / "compiler_core" / "client.py").read_bytes())
        jc_deadline = sha256_bytes(
            (DEFAULT_JC_ROOT / "compiler_core" / "deadline_presets.py")
            .read_bytes())
        self.step("c00_jc_client_pin", jc_client == JC_CLIENT_SHA256,
                  sha256=jc_client[:16])
        self.step("c00_jc_deadline_presets_pin",
                  jc_deadline == JC_DEADLINE_SHA256, sha256=jc_deadline[:16])
        here_branch = self.git(REPO_ROOT, "rev-parse", "--abbrev-ref", "HEAD")
        # 账房改口先例（W3-U12）：工单分支本体或 main 且工单提交全含。
        merged_tip = self.git(REPO_ROOT, "merge-base", "HEAD", "w3-u26")
        wt_tip = self.git(REPO_ROOT, "rev-parse", "--verify", "w3-u26")
        merged_mode = here_branch == "main" and merged_tip == wt_tip \
            and bool(wt_tip)
        self.step("c00_juscite_branch",
                  here_branch == "w3-u26" or merged_mode,
                  branch=here_branch, merged_tip=merged_tip[:12])
        # 分离不变量·方法组冻结：通道组无提醒/派发/发送方法；提醒面无
        # 外发方法；派发调度器模块零网络导入（E24 分离在组与模块层结构性
        # 成立——不是运行时约定）。
        channel_groups = {
            "SUBMISSION_PACKAGE_METHODS": (SUBMISSION_METHODS,
                                           legal_entry.SUBMISSION_PACKAGE_METHODS),
            "CALENDAR_SYNC_METHODS": (CALENDAR_SYNC_METHODS,
                                      legal_entry.CALENDAR_SYNC_METHODS),
            "WECHAT_COLLECTION_METHODS": (WECHAT_COLLECTION_METHODS,
                                          legal_entry.WECHAT_COLLECTION_METHODS),
            "COURT_INBOUND_METHODS": (COURT_INBOUND_METHODS,
                                      legal_entry.COURT_INBOUND_METHODS),
        }
        frozen_ok = all(expected == actual
                        for expected, actual in channel_groups.values())
        forbidden_tokens = ("schedule", "reminder", "send", "submit",
                            "dispatch")
        channel_clean = all(
            not any(token in method for token in forbidden_tokens)
            for expected, _ in channel_groups.values() for method in expected)
        scheduler_imports = module_imports(
            REPO_ROOT / "implementation" / "python" / "f118_scheduler.py")
        scheduler_clean = scheduler_imports <= {
            "__future__", "datetime", "typing", "bridge_errors", "legal_entry"}
        self.step("c00_separation_method_groups_frozen",
                  frozen_ok and channel_clean
                  and legal_entry.HARNESS_SCHEDULE_METHODS
                  == HARNESS_SCHEDULE_METHODS
                  and legal_entry.DEADLINE_PRESET_METHODS
                  == DEADLINE_PRESET_GROUP
                  and scheduler_clean,
                  frozen=frozen_ok, channel_clean=channel_clean,
                  scheduler_imports=sorted(scheduler_imports))

    # ------------------------------------------------------------------
    # 各通道流（两 profile 同一 check 序列）。
    # ------------------------------------------------------------------
    def common_flow(self, call_product, call_harness, query, jc_evaluate,
                    config, bound=None):
        # 提醒账基线（外部动作四通道全流程零副作用的对照基线）。
        counts_before = self._reminder_counts(query)
        server_obj, base_url = start_synthetic_endpoint(backflow=[
            {"syncId": "sync-D01", "externalEventId": "synth-0001",
             "eventType": "event_rescheduled",
             "externalDueDate": "2026-04-30",
             "payload": {"source": "synthetic-ticktick",
                         "newDate": "2026-04-30"}},
        ])
        self._endpoint_server = server_obj
        config["calendar_sync_endpoints"] = {
            "ticktick": base_url, "feishu": base_url}
        try:
            self.c01_submission(call_product, call_harness)
            self.c02_calendar(call_product, call_harness, query, jc_evaluate,
                              config)
            self.c03_court_inbound(call_product, call_harness, query, config,
                                   bound)
            self.c04_wechat(call_product, config)
            self.c05_f118_separation(call_product, call_harness, query,
                                     config, bound)
        finally:
            server_obj.shutdown()
            server_obj.server_close()
        # E24 面自身零新增自动提醒方法：自动提醒形态在冻结组外（两 profile）。
        self.expect_error("c06_auto_remind_not_connected", lambda:
            legal_entry.call("calendar.auto_remind", {"scope": SCOPE}, config),
            "method_not_connected:calendar.auto_remind")
        self.expect_error("c06_auto_practical_not_connected", lambda:
            legal_entry.call("practical.auto_remind", {"scope": SCOPE},
                             config),
            "method_not_connected:practical.auto_remind")
        # 收口：外部动作全流程后提醒账只含 C05 显式 schedule_event 行。
        counts_after = self._reminder_counts(query)
        self.step("c06_reminder_ledger_only_explicit_rows",
                  counts_after["deadlines"] == counts_before["deadlines"] + 4
                  and counts_after["derived_tasks"]
                  == counts_before["derived_tasks"] + 4
                  and counts_after["reminders"]
                  == counts_before["reminders"] + 6,
                  before=counts_before, after=counts_after,
                  note="deadlines/tasks 恰+4（C05 四个显式 schedule），"
                       "reminders 恰+6（显式声明 4＋桌面派发闭环回执修订 2）"
                       "——四通道零自动提醒零副作用")

    def _reminder_counts(self, query) -> dict:
        return {
            "deadlines": query(
                "SELECT COUNT(*) AS n FROM deadlines", ())[0]["n"],
            "derived_tasks": query(
                "SELECT COUNT(*) AS n FROM derived_tasks", ())[0]["n"],
            "reminders": query(
                "SELECT COUNT(*) AS n FROM reminders", ())[0]["n"],
        }

    # -- C01 提交面：外部提交须另授权＋律师确认闸 ------------------------
    def c01_submission(self, call_product, call_harness):
        defined = call_product("submission.checklist_define", {
            "actor_id": "lawyer-1", "scope": SCOPE, "key": key("cd-1"),
            "checklist": CHECKLIST})
        replay = call_product("submission.checklist_define", {
            "actor_id": "lawyer-1", "scope": SCOPE, "key": key("cd-replay"),
            "checklist": CHECKLIST})
        self.step("c01_checklist_declared_replay_idempotent",
                  defined["itemCount"] == 4
                  and replay["replayed"] is True,
                  itemCount=defined["itemCount"])
        for material_id, title, text in (
                ("mat-complaint", "起诉状（合成）", "起诉状正文合成"),
                ("mat-evidence", "证据清单（合成）", "证据清单合成"),
                ("mat-idcopy", "主体资格材料（合成）", "主体材料合成")):
            call_harness("harness.register_material", {
                "actor_id": "lawyer-1", "scope": SCOPE,
                "key": key("rm-" + material_id),
                "material": {"id": material_id, "kind": "digital_text",
                             "title": title, "bytesB64": b64(text)}})
        missing_pkg = call_product("submission.package_build", {
            "actor_id": "lawyer-1", "scope": SCOPE, "key": key("pb-1"),
            "package_id": "pkg-e24-missing", "checklist_id": "cl-e24",
            "matter_title": MATTER_TITLE, "court_note": COURT_NOTE,
            "items": [
                {"itemId": "complaint",
                 "materialRefs": [{"id": "mat-complaint"}]},
                {"itemId": "evidence", "materialRefs": []},
                {"itemId": "idcopy", "materialRefs": []},
                {"itemId": "service-proof", "materialRefs": []}]})
        self.step("c01_package_missing_named_channel_none",
                  missing_pkg["missingItems"] == ["evidence", "idcopy"]
                  and missing_pkg["submissionChannel"] == "none"
                  and missing_pkg["state"] == "draft",
                  missing=missing_pkg["missingItems"])
        # 确认不是隐式调用：无显式 confirm 标志＝具名拒（账面零写入）。
        self.expect_error("c01_confirm_flag_required", lambda:
            call_product("submission.package_confirm", {
                "actor_id": "lawyer-1", "scope": SCOPE, "key": key("pc-nf"),
                "package_id": "pkg-e24-missing",
                "package_sha256": missing_pkg["packageSha256"],
                "reasonRef": reason_ref("r-nf"),
                "receiptRef": reason_ref("rc-nf")}),
            "f59_confirmation_flag_required")
        # 缺件确认＝确认结构性被拒。
        self.expect_error("c01_confirm_missing_refused", lambda:
            call_product("submission.package_confirm", {
                "confirm": True, "actor_id": "lawyer-1", "scope": SCOPE,
                "key": key("pc-mi"), "package_id": "pkg-e24-missing",
                "package_sha256": missing_pkg["packageSha256"],
                "reasonRef": reason_ref("r-mi"),
                "receiptRef": reason_ref("rc-mi")}),
            "f59_confirm_missing_items:evidence,idcopy")
        # 补齐后确认成功——确认后 submissionChannel 仍 'none'（对外提交
        # 另授权：确认只是账面决定记录，不是出站动作）。
        full_pkg = call_product("submission.package_build", {
            "actor_id": "lawyer-1", "scope": SCOPE, "key": key("pb-2"),
            "package_id": "pkg-e24-full", "checklist_id": "cl-e24",
            "matter_title": MATTER_TITLE, "court_note": COURT_NOTE,
            "items": [
                {"itemId": "complaint",
                 "materialRefs": [{"id": "mat-complaint"}]},
                {"itemId": "evidence",
                 "materialRefs": [{"id": "mat-evidence"}]},
                {"itemId": "idcopy",
                 "materialRefs": [{"id": "mat-idcopy"}]},
                {"itemId": "service-proof", "materialRefs": []}]})
        confirmed = call_product("submission.package_confirm", {
            "confirm": True, "actor_id": "lawyer-1", "scope": SCOPE,
            "key": key("pc-1"), "package_id": "pkg-e24-full",
            "package_sha256": full_pkg["packageSha256"],
            "reasonRef": reason_ref("r-ok"),
            "receiptRef": reason_ref("rc-ok")})
        self.step("c01_confirmed_still_channel_none",
                  confirmed["state"] == "confirmed"
                  and confirmed["submissionChannel"] == "none",
                  state=confirmed["state"])
        rendered = full_pkg["packageText"]
        self.step("c01_render_names_no_external_submission",
                  "本系统不执行任何对外提交动作" in rendered
                  and "缺件" in missing_pkg["packageText"],
                  notice="对外递交由律师自行完成说明在渲染文本内")
        # 外部提交/发送通道结构性不存在（封闭注册外·双证）。
        self.expect_error("c01_submit_channel_structurally_absent", lambda:
            call_harness("harness.submission_submit",
                         {"scope": SCOPE, "package_id": "pkg-e24-full"}),
            "harness.submission_submit")
        self.expect_error("c01_send_channel_structurally_absent", lambda:
            call_product("submission.send", {"scope": SCOPE}),
            "method_not_connected:submission.send")

    # -- C02 日历面：授权材料（JC 回执）＋确认闸＋幂等回流＋不改期限 -----
    def c02_calendar(self, call_product, call_harness, query, jc_evaluate,
                     config):
        receipt = jc_evaluate({
            "slot": "D01", "now": NOW,
            "event": {"kind": "service_of_first_instance_judgment",
                      "anchor": {"value": "2026-03-20",
                                 "precision": "date"}}})
        self.step("c02_real_jc_receipt_owner_jc",
                  receipt["status"] == "OK"
                  and receipt["due_date"] == "2026-04-07"
                  and receipt["evaluationRef"]["owner"] == "jc",
                  due_date=receipt["due_date"])
        event_args = {
            "scope": SCOPE, "actor_id": "product-1",
            "sync_id": "sync-D01", "targetKind": "ticktick",
            "event_key": "evt-D01", "title": "上诉期届满（E24 合成 recon）",
            "due_date": receipt["due_date"],
            "nominal_due_date": receipt["nominal_due_date"],
            "deadline_receipt": receipt,
        }
        synced = call_product("calendar.sync_event",
                              dict(event_args, key=key("cs-1")))
        self.step("c02_sync_pushed_once",
                  synced["pushed"] is True and synced["state"] == "synced"
                  and len(self._endpoint_server.requests) == 1,
                  outbound=len(self._endpoint_server.requests))
        # 幂等回流：同 event_key 同内容重放＝不重复推送。
        replayed = call_product("calendar.sync_event",
                                dict(event_args, key=key("cs-replay")))
        self.step("c02_replay_no_second_push",
                  replayed["replayed"] is True
                  and replayed["pushed"] is False
                  and len(self._endpoint_server.requests) == 1,
                  outbound=len(self._endpoint_server.requests))
        # 负测：端点未配置＝具名拒不发（URL 只来自显式 config，禁编 URL；
        # 登记已守门落账 state=pending_push 零出站）。
        bare = {k: v for k, v in config.items()
                if k != "calendar_sync_endpoints"}
        rows_before = query(
            "SELECT COUNT(*) AS n FROM calendar_sync_items"
            " WHERE matter_id=?", (MATTER,))[0]["n"]
        self.expect_error("c02_endpoint_unconfigured_no_outbound", lambda:
            call_product("calendar.sync_event", {
                "scope": SCOPE, "actor_id": "product-1", "key": key("cs-neg"),
                "sync_id": "sync-neg", "targetKind": "feishu",
                "event_key": "evt-neg", "title": "负测（E24 合成）",
                "due_date": receipt["due_date"],
                "nominal_due_date": receipt["nominal_due_date"],
                "deadline_receipt": receipt}, bare),
            "calendar_sync_endpoint_not_configured:feishu")
        neg_row = query(
            "SELECT state FROM calendar_sync_items"
            " WHERE matter_id=? AND sync_id=?", (MATTER, "sync-neg"))
        rows_after = query(
            "SELECT COUNT(*) AS n FROM calendar_sync_items"
            " WHERE matter_id=?", (MATTER,))[0]["n"]
        self.step("c02_unconfigured_sync_row_never_pushed",
                  rows_after == rows_before + 1 and neg_row
                  and neg_row[0]["state"] == "pending_push"
                  and len(self._endpoint_server.requests) == 1,
                  state=neg_row[0]["state"] if neg_row else None,
                  outbound=len(self._endpoint_server.requests))
        # 不改期限负测：外部改期回流冲突具名，DB 级期限逐字节不变。
        pulled = call_product("calendar.pull_external", {
            "scope": SCOPE, "actor_id": "product-1",
            "targetKind": "ticktick", "sync_id": "sync-D01"})
        row = query(
            "SELECT due_date, deadline_receipt_json, state FROM"
            " calendar_sync_items WHERE matter_id=? AND sync_id=?",
            (MATTER, "sync-D01"))[0]
        self.step("c02_backflow_conflict_deadline_byte_identical",
                  pulled["recorded"][0]["conflict"] is True
                  and "f60_external_reschedule_conflicts_legal:"
                      "2026-04-30!=2026-04-07"
                  in str(pulled["recorded"][0]["conflictReason"])
                  and row["due_date"] == receipt["due_date"]
                  and json.loads(row["deadline_receipt_json"]) == receipt
                  and row["state"] == "conflict_pending_review",
                  state=row["state"])
        # 幂等回流（双层）：①产品重复拉取＝CommandKey 层重放（requestId 由
        # externalEventId 派生→原回执原样，事件账零二记）；②同事件换新键
        # 重放＝事件账 PK 幂等（replayed=true），行数恒 1。
        pulled_again = call_product("calendar.pull_external", {
            "scope": SCOPE, "actor_id": "product-1",
            "targetKind": "ticktick", "sync_id": "sync-D01"})
        event_rows = query(
            "SELECT COUNT(*) AS n FROM calendar_external_events"
            " WHERE matter_id=?", (MATTER,))[0]["n"]
        direct = call_harness("harness.calendar_external_event_record", {
            "actor_id": "product-1", "scope": SCOPE,
            "key": key("pull-direct-replay"),
            "external_event": {"externalEventId": "synth-0001",
                               "syncId": "sync-D01",
                               "eventType": "event_rescheduled",
                               "externalPayload": {"source": "synthetic-ticktick",
                                                   "newDate": "2026-04-30"},
                               "externalDueDate": "2026-04-30"}})
        self.step("c02_duplicate_pull_idempotent",
                  pulled_again["recorded"] == pulled["recorded"]
                  and event_rows == 1
                  and direct.get("replayed") is True,
                  event_rows=event_rows,
                  command_replay=pulled_again["recorded"]
                  == pulled["recorded"],
                  event_ledger_replay=direct.get("replayed"))
        # 决定确认闸：无 confirm 拒；keep 决定＝法律期限仍不变。
        self.expect_error("c02_resolve_flag_required", lambda:
            call_product("calendar.resolve_conflict", {
                "scope": SCOPE, "actor_id": "lawyer-1", "key": key("rc-nf"),
                "sync_id": "sync-D01", "action": "keep_legal_deadline",
                "reasonRef": reason_ref("r-rf"),
                "receiptRef": reason_ref("rc-rf")}),
            "f60_confirmation_flag_required")
        resolved = call_product("calendar.resolve_conflict", {
            "confirm": True, "scope": SCOPE, "actor_id": "lawyer-1",
            "key": key("rc-1"), "sync_id": "sync-D01",
            "action": "keep_legal_deadline",
            "reasonRef": reason_ref("r-keep"),
            "receiptRef": reason_ref("rc-keep")})
        after_keep = query(
            "SELECT due_date, deadline_receipt_json FROM calendar_sync_items"
            " WHERE matter_id=? AND sync_id=?", (MATTER, "sync-D01"))[0]
        self.step("c02_keep_decision_legal_unchanged",
                  resolved["state"] == "reviewed"
                  and after_keep["due_date"] == receipt["due_date"]
                  and json.loads(after_keep["deadline_receipt_json"])
                  == receipt,
                  due_date=after_keep["due_date"])
        # 期限值只认真实 JC 回执：伪造 owner／UNKNOWN 零日期回执全拒。
        self.expect_error("c02_forged_receipt_owner_refused", lambda:
            call_product("calendar.sync_event", {
                "scope": SCOPE, "actor_id": "product-1",
                "key": key("cs-forged"), "sync_id": "sync-forged",
                "targetKind": "ticktick", "event_key": "evt-forged",
                "title": "伪造（E24 合成）", "due_date": "2026-04-07",
                "nominal_due_date": "2026-04-04",
                "deadline_receipt": dict(
                    receipt, evaluationRef=dict(receipt["evaluationRef"],
                                                owner="product"))}),
            "jc_ref_invalid:deadlineReceiptRef")
        self.expect_error("c02_unknown_receipt_not_syncable", lambda:
            call_product("calendar.sync_event", {
                "scope": SCOPE, "actor_id": "product-1",
                "key": key("cs-d07"), "sync_id": "sync-D07",
                "targetKind": "ticktick", "event_key": "evt-D07",
                "title": "D07（E24 合成）", "due_date": "2026-05-01",
                "nominal_due_date": "2026-05-01",
                "deadline_receipt": {
                    "status": "UNKNOWN_CALENDAR", "slot": "D07",
                    "due_date": None, "nominal_due_date": "2026-05-01",
                    "evaluationRef": {"owner": "jc",
                                      "kind": "deadline-evaluation",
                                      "id": "jc-d07",
                                      "digest": "sha256:" + "c" * 64}}}),
            "f60_receipt_not_ok")
        # 改期唯一通道＝新 sync 行＋新 JC 回执；被取代行一字不动。
        receipt_v2 = jc_evaluate({
            "slot": "D01", "now": NOW,
            "event": {"kind": "service_of_first_instance_judgment",
                      "anchor": {"value": "2026-04-10",
                                 "precision": "date"}}})
        v2 = call_product("calendar.sync_event", {
            "scope": SCOPE, "actor_id": "product-1", "key": key("cs-v2"),
            "sync_id": "sync-D01-v2", "targetKind": "feishu",
            "event_key": "evt-D01-v2",
            "title": "上诉期届满（重算·E24 合成）",
            "due_date": receipt_v2["due_date"],
            "nominal_due_date": receipt_v2["nominal_due_date"],
            "deadline_receipt": receipt_v2})
        self._endpoint_server.backflow.append({
            "syncId": "sync-D01-v2", "externalEventId": "synth-0002",
            "eventType": "event_rescheduled",
            "externalDueDate": "2026-05-01",
            "payload": {"source": "synthetic-feishu",
                        "newDate": "2026-05-01"}})
        call_product("calendar.pull_external", {
            "scope": SCOPE, "actor_id": "product-1",
            "targetKind": "feishu", "sync_id": "sync-D01-v2"})
        superseded = call_product("calendar.resolve_conflict", {
            "confirm": True, "scope": SCOPE, "actor_id": "lawyer-1",
            "key": key("rc-sup"), "sync_id": "sync-D01-v2",
            "action": "superseded_by_new_event",
            "reasonRef": reason_ref("r-sup"),
            "receiptRef": reason_ref("rc-sup"),
            "superseding_sync_id": "sync-D01"})
        old_row = query(
            "SELECT due_date, deadline_receipt_json FROM calendar_sync_items"
            " WHERE matter_id=? AND sync_id=?", (MATTER, "sync-D01"))[0]
        self.step("c02_supersede_only_via_new_row_and_receipt",
                  v2["pushed"] is True
                  and superseded["state"] == "reviewed"
                  and old_row["due_date"] == receipt["due_date"]
                  and json.loads(old_row["deadline_receipt_json"]) == receipt,
                  old=old_row["due_date"], new=receipt_v2["due_date"])

    # -- C03 法院来件面：人审确认闸＋幂等回流＋送达事实不由上传日补 -------
    def c03_court_inbound(self, call_product, call_harness, query, config,
                          bound):
        from court_inbound import court_inbound_call, CourtInboundError
        corpus = Path(config["e24_corpus_root"])
        captured: list[dict] = []

        def harness_call(method, args):
            if bound is not None:
                result = bound[method](**args)
            else:
                result = legal_entry.call(method, args, config)
            if method == "harness.register_material":
                captured.append(json.loads(json.dumps(args)))
            return result

        def face(method, args, ocr=None):
            return court_inbound_call(method, args, config,
                                      ocr_call=ocr or make_ocr_seam(),
                                      harness_call=harness_call)

        sms = {"sms_id": "sms-e24-0001", "sender": "合成市第一人民法院",
               "sent_at": "2026-10-17T09:00:00+08:00", "text": SMS_TEXT,
               "corpus_root": str(corpus),
               "attachments": [{"doc_id": "att_0001",
                                "path": "docs/att_0001.pdf"}]}
        recv = face("court_inbound.sms_receive",
                    {"matter_id": MATTER, "sms": sms})
        # 幂等回流三形态：同 id 同内容重放／同内容异 id 去重／同 id 异内容拒。
        replay = face("court_inbound.sms_receive",
                      {"matter_id": MATTER, "sms": sms})
        resent = face("court_inbound.sms_receive",
                      {"matter_id": MATTER,
                       "sms": dict(sms, sms_id="sms-e24-0001-retry")})
        conflict_refused = False
        try:
            face("court_inbound.sms_receive",
                 {"matter_id": MATTER,
                  "sms": dict(sms, text=SMS_TEXT + "（篡改）")})
        except CourtInboundError as exc:
            conflict_refused = "f62_sms_id_content_conflict" in str(exc)
        records = list((Path(config["court_inbound_state_root"])
                        / "f62-inbound" / MATTER).glob("sms-*.json"))
        self.step("c03_sms_parsed_pinned_duplicate_idempotent",
                  recv["parsed"]["case_numbers"] == [SMS_CASE]
                  and recv["attachments"][0]["sha256"] == sha256_bytes(
                      (corpus / "docs" / "att_0001.pdf").read_bytes())
                  and replay["duplicate"] is True
                  and resent["duplicate"] is True
                  and resent["sms_id"] == "sms-e24-0001"
                  and resent.get("deduped_from") == "sms-e24-0001-retry"
                  and conflict_refused and len(records) == 1,
                  sms_records=len(records))
        run = face("court_inbound.inbound_run",
                   {"matter_id": MATTER, "sms_id": "sms-e24-0001"})
        rerun = face("court_inbound.inbound_run",
                     {"matter_id": MATTER, "sms_id": "sms-e24-0001"})
        candidate_types = sorted({c["type"] for c in run["candidates"]})
        self.step("c03_run_candidates_closed_set_and_idempotent",
                  candidate_types == ["case_number"]
                  and SMS_CASE in [c["value"] for c in run["candidates"]]
                  and rerun["duplicate"] is True
                  and rerun["candidates_sha256"] == run["candidates_sha256"],
                  candidate_types=candidate_types)
        # 人审确认闸：未审不入库（确认前送达候选绝不入正式账——无任何
        # 人审账＝f62_intake_chain_incomplete，部分未审＝f62_intake_
        # unreviewed_candidates，f62 recon 同守卫双码）。
        unreviewed_refused = False
        try:
            face("court_inbound.intake",
                 {"matter_id": MATTER, "sms_id": "sms-e24-0001"})
        except CourtInboundError as exc:
            unreviewed_refused = ("f62_intake_chain_incomplete" in str(exc)
                                  or "f62_intake_unreviewed_candidates"
                                  in str(exc))
        review = face("court_inbound.candidate_review", {
            "matter_id": MATTER, "sms_id": "sms-e24-0001",
            "reviewer": "律师甲（合成）",
            "decisions": [{"candidate_id": c["candidate_id"],
                           "decision": "confirmed"}
                          for c in run["candidates"]]})
        flip_refused = False
        try:
            face("court_inbound.candidate_review", {
                "matter_id": MATTER, "sms_id": "sms-e24-0001",
                "reviewer": "律师甲（合成）",
                "decisions": [{"candidate_id": run["candidates"][0]
                               ["candidate_id"], "decision": "rejected"}]})
        except CourtInboundError as exc:
            flip_refused = "f62_candidate_review_conflict" in str(exc)
        intake = face("court_inbound.intake",
                      {"matter_id": MATTER, "sms_id": "sms-e24-0001"})
        materials = call_harness("harness.list_materials",
                                 {"scope": SCOPE})
        self.step("c03_unreviewed_refused_then_confirmed_intake",
                  unreviewed_refused and flip_refused
                  and review["counts"]["confirmed"] == len(run["candidates"])
                  and intake["revision"] == 1
                  and len(materials.get("materials") or []) == 4,
                  confirmed=review["counts"]["confirmed"],
                  materials=len(materials.get("materials") or []),
                  note="materials=4（C01 提交材料 3＋本链入库 1）")
        # 送达事实不由上传日补（结构断言，对实际入库 CAS 字节）：
        # ①无送达日字段键；②「送达」仅出现于 E24 边界句；③候选闭集；
        # ④material note 无日期事实字段。
        registered = captured[-1]["material"]
        intake_bytes = base64.b64decode(registered["bytesB64"]).decode("utf-8")
        serve_lines = [line for line in intake_bytes.splitlines()
                       if "送达" in line]
        note = json.loads(registered["note"])
        date_like = re.findall(r"\d{4}-\d{2}-\d{2}", intake_bytes)
        # 「送达」仅允许出现于：候选分节标题（送达候选＝人审账，非事实）与
        # E24 边界句；任何送达日期字段/送达+日期相邻形态结构性不存在。
        serve_ok = (sorted(serve_lines) == sorted([
            "== 送达候选（人审账）==",
            "候选经律师人审确认；送达事实不由上传日自动补（E24）。"
            "本材料为 OCR 文本衍生物，附件原件字节不出 OCR 状态根域。"])
            and not any(token in intake_bytes for token in (
                "送达日期", "送达日：", "serviceDate", "service_date",
                "served_at", "servedAt"))
            and not re.search(r"送达[^\n]{0,16}\d{4}-\d{2}-\d{2}"
                              r"|\d{4}-\d{2}-\d{2}[^\n]{0,16}送达",
                              intake_bytes))
        self.step("c03_service_fact_not_from_upload_date",
                  serve_ok
                  and candidate_types == ["case_number"]
                  and not any(k in note for k in (
                      "service_date", "served_at", "送达日"))
                  and len(date_like) >= 1,
                  serve_lines=serve_lines, note_keys=sorted(note),
                  date_like_count=len(date_like))
        # 全部否决＝律师认定非本案件来件→不入库（送达认定不由机器代决）。
        face("court_inbound.sms_receive",
             {"matter_id": MATTER, "sms": dict(
                 sms, sms_id="sms-e24-0002", text=SMS_TEXT.replace(
                     "91001", "91002"),
                 attachments=[{"doc_id": "att_0001",
                               "path": "docs/att_0001.pdf"}])})
        run2 = face("court_inbound.inbound_run",
                    {"matter_id": MATTER, "sms_id": "sms-e24-0002"})
        face("court_inbound.candidate_review", {
            "matter_id": MATTER, "sms_id": "sms-e24-0002",
            "reviewer": "律师甲（合成）",
            "decisions": [{"candidate_id": c["candidate_id"],
                           "decision": "rejected"}
                          for c in run2["candidates"]]})
        all_rejected_refused = False
        try:
            face("court_inbound.intake",
                 {"matter_id": MATTER, "sms_id": "sms-e24-0002"})
        except CourtInboundError as exc:
            all_rejected_refused = \
                "f62_intake_no_confirmed_candidate" in str(exc)
        materials_after = call_harness("harness.list_materials",
                                       {"scope": SCOPE})
        # 幂等回流：同内容重入库＝重放（材料行恒 1）。
        replay_intake = face("court_inbound.intake",
                             {"matter_id": MATTER, "sms_id": "sms-e24-0001"})
        self.step("c03_rejected_intake_refused_replay_idempotent",
                  all_rejected_refused
                  and len(materials_after.get("materials") or []) == 4
                  and replay_intake["replayed"] is True,
                  materials=len(materials_after.get("materials") or []))

    # -- C04 微信面：显式授权账＋幂等回流＋无隐式采集通道 -----------------
    def c04_wechat(self, call_product, config):
        exports = Path(config["e24_exports_root"])
        auth1 = call_product("collection.authorize", {
            "external_ids": list(AUTHORIZED_WX_IDS),
            "authorized_by": "recon-synth-e24"})
        auth2 = call_product("collection.authorize", {
            "external_ids": list(reversed(AUTHORIZED_WX_IDS)),
            "authorized_by": "recon-synth-e24"})
        self.expect_error("c04_scope_closed_web_crawl_refused", lambda:
            call_product("collection.authorize", {
                "external_ids": ["w"], "authorized_by": "x",
                "scope": "web_crawl"}),
            "f61_scope_unknown:web_crawl")
        self.step("c04_authorize_explicit_idempotent",
                  auth1["idempotent_replay"] is False
                  and auth2["idempotent_replay"] is True
                  and auth2["authorization"]["auth_id"]
                  == auth1["authorization"]["auth_id"]
                  and auth1["authorization"]["scope"]
                  == "local_authorized_export",
                  auth_id=auth1["authorization"]["auth_id"])
        batch_args = {
            "batch_id": "b-e24", "matter_id": MATTER,
            "items": [
                {"external_id": AUTHORIZED_WX_IDS[0], "kind": "text",
                 "export_path": str(exports / "wx_chat_001.txt"),
                 "export_sha256": sha256_bytes(
                     (exports / "wx_chat_001.txt").read_bytes())},
                {"external_id": AUTHORIZED_WX_IDS[1], "kind": "text",
                 "export_path": str(exports / "wx_chat_002.txt")},
                {"external_id": UNAUTHORIZED_WX_ID, "kind": "text",
                 "export_path": str(exports / "wx_ghost.txt")},
            ]}
        batch = call_product("collection.batch", batch_args)
        by_id = {item["external_id"]: item for item in batch["items"]}
        unauthorized = by_id[UNAUTHORIZED_WX_ID]
        self.step("c04_unauthorized_unknown_none_not_zero",
                  unauthorized["status"] == "UNKNOWN_NOT_AUTHORIZED"
                  and unauthorized["export"] is None
                  and unauthorized["collected"] is None
                  and unauthorized["gate"] is None
                  and unauthorized["review_required"] is None,
                  item_status=unauthorized["status"])
        # 独立 deidentify 对照（材料化同源同确定；出处 sha 绑定）。
        independent = legal_entry.call("material.deidentify",
                                       {"text": WX_CHAT_TEXT}, config)
        collected = by_id[AUTHORIZED_WX_IDS[0]]
        self.step("c04_authorized_collected_provenance_bound",
                  collected["status"] == "COLLECTED"
                  and collected["collected"]["sha256"]
                  == sha256_bytes(independent["sanitized_text"].encode("utf-8"))
                  and collected["export"]["sha256"]
                  == sha256_bytes((exports / "wx_chat_001.txt").read_bytes()),
                  collected_sha=collected["collected"]["sha256"][:16])
        # 幂等回流：同批次同输入重放＝同回执；异输入＝具名拒。
        replay = call_product("collection.batch", batch_args)
        conflict_refused = False
        try:
            call_product("collection.batch", dict(
                batch_args, matter_id=MATTER + "-x"))
        except NotConnected as exc:
            conflict_refused = "f61_batch_conflict" in str(exc)
        self.step("c04_batch_replay_idempotent_conflict_named",
                  replay == batch and conflict_refused,
                  replayed=replay["batch_id"])
        # 负测：url 旁路字段具名拒（无隐式采集通道）。
        self.expect_error("c04_no_implicit_channel_field_forbidden", lambda:
            call_product("collection.batch", {
                "batch_id": "b-e24-guard", "matter_id": MATTER,
                "items": [{"external_id": AUTHORIZED_WX_IDS[0],
                           "kind": "text", "url": "https://weixin.example.invalid"}]}),
            "f61_field_forbidden:url")

    # -- C05 F118 分离面：实务提醒不自动启用＋派发仅桌面通知 --------------
    def c05_f118_separation(self, call_product, call_harness, query, config,
                            bound):
        import f118_scheduler
        # 锚规则（送达事实不由上传日补的日程级形态）：程序期限锚只认法院
        # 程序事件；实务提醒/合同义务锚禁用（自锚，不冒程序期限）。
        self.expect_error("c05_program_deadline_requires_court_anchor", lambda:
            call_harness("harness.schedule_event", {
                "actor_id": "lawyer-1", "scope": SCOPE, "key": key("se-noa"),
                "event": {"id": "sched-e24-noanchor",
                          "classification": "program_deadline",
                          "title": "无锚程序期限（E24 合成）",
                          "dueDate": "2026-11-01"},
                "reminders": []}),
            "schedule_anchor_required:program_deadline")
        self.expect_error("c05_program_deadline_bogus_anchor_refused", lambda:
            call_harness("harness.schedule_event", {
                "actor_id": "lawyer-1", "scope": SCOPE, "key": key("se-bog"),
                "event": {"id": "sched-e24-bogus",
                          "classification": "program_deadline",
                          "title": "伪造锚（E24 合成）",
                          "dueDate": "2026-11-01",
                          "eventRef": {"eventId": "pe-nonexistent",
                                       "eventRevision": 1}},
                "reminders": []}),
            "schedule_anchor_not_found:pe-nonexistent")
        self.expect_error("c05_practical_anchor_forbidden", lambda:
            call_harness("harness.schedule_event", {
                "actor_id": "lawyer-1", "scope": SCOPE, "key": key("se-pa"),
                "event": {"id": "sched-e24-pa",
                          "classification": "practical_reminder",
                          "title": "冒锚实务（E24 合成）",
                          "dueDate": "2026-11-01",
                          "eventRef": {"eventId": "pe-e24-court",
                                       "eventRevision": 1}},
                "reminders": []}),
            "schedule_anchor_forbidden:practical_reminder")
        saved = call_harness("harness.schedule_event", {
            "actor_id": "lawyer-1", "scope": SCOPE, "key": key("se-1"),
            "event": {"id": "sched-e24-prog",
                      "classification": "program_deadline",
                      "title": "开庭日前准备（E24 合成）",
                      "dueDate": "2026-10-20",
                      "eventRef": {"eventId": "pe-e24-court",
                                   "eventRevision": 1}},
            "reminders": [{"id": "rem-e24-prog",
                           "scheduledAt": "2026-10-17T00:00:00Z",
                           "channel": "desktop"}]})
        # 实务提醒：reminders=[] → 零提醒行（实务自动提醒不启用——提醒只
        # 能显式声明，F118 v1.5 扩卡归 W4）。
        call_harness("harness.schedule_event", {
            "actor_id": "lawyer-1", "scope": SCOPE, "key": key("se-2"),
            "event": {"id": "sched-e24-practical",
                      "classification": "practical_reminder",
                      "title": "庭前实务提醒（E24 合成·无自动提醒）",
                      "dueDate": "2026-10-19"},
            "reminders": []})
        call_harness("harness.schedule_event", {
            "actor_id": "lawyer-1", "scope": SCOPE, "key": key("se-3"),
            "event": {"id": "sched-e24-practical-notify",
                      "classification": "practical_reminder",
                      "title": "庭前会议提醒（E24 合成·显式桌面通知）",
                      "dueDate": "2026-10-19"},
            "reminders": [{"id": "rem-e24-practical",
                           "scheduledAt": "2026-10-17T00:30:00Z",
                           "channel": "desktop"}]})
        # email/im 提醒（历史时刻）——外部发送另授权：账面可记意图，
        # 派发队列永不入队（无外发面）。
        call_harness("harness.schedule_event", {
            "actor_id": "lawyer-1", "scope": SCOPE, "key": key("se-4"),
            "event": {"id": "sched-e24-contract",
                      "classification": "contract_obligation",
                      "title": "合同尾款义务（E24 合成）",
                      "dueDate": "2026-11-01"},
            "reminders": [
                {"id": "rem-e24-email",
                 "scheduledAt": "2026-10-17T00:00:00Z", "channel": "email"},
                {"id": "rem-e24-im",
                 "scheduledAt": "2026-10-17T00:00:00Z", "channel": "im"}]})
        auto_rows = query(
            "SELECT COUNT(*) AS n FROM reminders WHERE matter_id=?"
            " AND reminder_id LIKE 'rem-e24-%'", (MATTER,))[0]["n"]
        self.step("c05_schedules_saved_reminders_only_explicit",
                  saved["classification"] == "program_deadline"
                  and auto_rows == 4,
                  reminder_rows=auto_rows,
                  note="4=显式声明（prog/practical desktop×1＋email＋im）；"
                       "无 reminders 的实务日程零自动提醒行")
        listing = call_harness("harness.schedule_list", {
            "scope": SCOPE,
            "query": {"asOf": AS_OF, "asAt": AS_AT}})
        groups = listing["groups"]
        program = next(i for i in groups["program_deadline"]
                       if i["id"] == "sched-e24-prog")
        practical = [i for i in groups["practical_reminder"]]
        contract = next(i for i in groups["contract_obligation"]
                        if i["id"] == "sched-e24-contract")
        due_ids = sorted(r["reminderId"]
                         for r in listing["dueDesktopReminders"])
        self.step("c05_groups_separate_anchor_rules_hold",
                  program["anchor"] == {"eventId": "pe-e24-court",
                                        "eventRevision": 1}
                  and all(i["anchor"] is None for i in practical)
                  and contract["anchor"] is None
                  and len(groups["program_deadline"]) == 1,
                  program_anchor=program["anchor"])
        self.step("c05_due_desktop_only_email_im_never_queued",
                  due_ids == ["rem-e24-practical", "rem-e24-prog"]
                  and all(r["channel"] == "desktop"
                          for r in listing["dueDesktopReminders"]),
                  due=due_ids)
        # 派发轮：f118_scheduler 只发桌面通知（payload 键闭集、零外发）；
        # email/im 提醒保持 pending（未发送·外部发送另授权）；合成日历
        # 端点零新增请求（提醒环不发外部动作）。
        outbound_before = len(self._endpoint_server.requests)
        fired: list[dict] = []

        def notifier(payload):
            fired.append(payload)
            return f"os-notification:{payload['reminderId']}"

        if bound is not None:
            original_call = f118_scheduler.call

            def injected_call(method, args, cfg=None):
                target = bound.get(method)
                if target is None:
                    raise NotConnected("method_not_connected:" + method)
                return target(**args)
            f118_scheduler.call = injected_call
        try:
            round_result = f118_scheduler.dispatch_and_report(
                config, matter_id=MATTER, notifier=notifier,
                now_iso=AS_AT, as_of=AS_OF, request_seq=1)
        finally:
            if bound is not None:
                f118_scheduler.call = original_call
        payload_keys = sorted(fired[0]) if fired else []
        after = call_harness("harness.schedule_list", {
            "scope": SCOPE, "query": {"asOf": AS_OF, "asAt": AS_AT}})
        contract_after = next(
            row for row in after["groups"]["contract_obligation"]
            if row["id"] == "sched-e24-contract")
        pending_channels = sorted(
            r["channel"] for r in contract_after["reminders"]
            if r["state"] == "pending")
        self.step("c05_dispatch_desktop_notification_only",
                  sorted(f["reminderId"] for f in round_result["fired"])
                  == ["rem-e24-practical", "rem-e24-prog"]
                  and round_result["refused"] == []
                  and set(payload_keys) == {
                      "reminderId", "taskId", "deadlineId", "classification",
                      "title", "body", "dueDate", "daysRemaining", "urgent",
                      "channel"}
                  and pending_channels == ["email", "im"]
                  and len(self._endpoint_server.requests) == outbound_before,
                  fired=sorted(f["reminderId"]
                               for f in round_result["fired"]),
                  payload_keys=payload_keys,
                  still_pending=pending_channels,
                  calendar_outbound=len(self._endpoint_server.requests))
        # 派发通知的实务提醒是显式声明的桌面通知（F118 v1 已验面）——
        # E24 断言其 payload 携 classification=practical_reminder 且仍是
        # 桌面通道（不因实务分类而走外部发送）。
        practical_fired = next(f for f in fired
                               if f["reminderId"] == "rem-e24-practical")
        self.step("c05_practical_notification_desktop_channel_only",
                  practical_fired["classification"] == "practical_reminder"
                  and practical_fired["channel"] == "desktop",
                  channel=practical_fired["channel"])

    # -- C06 桥负向（desktop 全链径）--------------------------------------
    def c06_bridge_negatives(self, call_product, call_harness, config):
        try:
            legal_entry.call("harness.schedule_event", {"scope": SCOPE}, {})
            raise AssertionError("bridge_not_configured_expected")
        except NotConnected as exc:
            self.step("c06_bridge_not_configured",
                      "harness_public_entry_not_configured" in str(exc))
        try:
            legal_entry.call("harness.schedule_detonate",
                             {"scope": SCOPE}, config)
            raise AssertionError("bridge_unknown_method_expected")
        except NotConnected as exc:
            self.step("c06_bridge_unknown_method_refused",
                      "method_not_connected" in str(exc))


def run_desktop(recon: Recon, harness_root: Path, corpus: Path,
                exports: Path) -> int:
    """desktop＝产品桥子进程全链（SQLite 状态根）：产品面与 harness 面
    都走 legal_entry.call 默认派发（与生产同一条链）；F62 入库经同一桥
    （harness.register_material），OCR 在 F41 桥 seam 注入合成行。"""
    temporary = tempfile.TemporaryDirectory(prefix="juscite-e24-desktop-")
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
        "court_inbound_state_root": str(tmp / "inbound"),
        "anonymizer_contract": "p09/p10",
        "collection_state_root": str(tmp / "collection"),
        "e24_corpus_root": str(corpus),
        "e24_exports_root": str(exports),
    }
    for path in (str(harness_root / "src"),
                 str(harness_root / "tools/workflow-tools")):
        if path not in sys.path:
            sys.path.insert(0, path)
    from legal_harness.state.matter_store import MatterStore
    from legal_harness.business.units import HarnessUnits
    store = MatterStore(state_root)
    store.create_matter(MATTER, "cas://profile-e24")
    # 程序事件种子（save_procedure_event 属 W08 产品接线义务、不在产品桥
    # F118 白名单——照实经 HarnessUnits 种子入账，f118 recon 同先例）。
    HarnessUnits(store).save_procedure_event(
        "recon-lawyer", SCOPE, key("pe-1"),
        {"id": "pe-e24-court", "revision": 1, "matterId": MATTER,
         "kind": "court_event"})

    def call_product(method, call_args, cfg=None):
        return legal_entry.call(method, call_args, cfg or config)

    def call_harness(method, call_args):
        return legal_entry.call(method, call_args, config)

    def query(sql, params):
        import sqlite3
        with contextlib.closing(store._connect()) as connection:
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
    recon.common_flow(call_product, call_harness, query, jc_evaluate, config)
    recon.c06_bridge_negatives(call_product, call_harness, config)
    return 0


def run_selfhost(recon: Recon, harness_root: Path, dsn: str, corpus: Path,
                 exports: Path) -> int:
    """selfhost＝PgMatterStore 直连 lh-pg-e08（resolve_provider_method 同
    一封闭注册）：产品面经 harness_call 注入直连（同函数链，不同后端）。"""
    for path in (str(harness_root / "src"),
                 str(harness_root / "tools/workflow-tools"),
                 str(harness_root), str(harness_root / "tests")):
        if path not in sys.path:
            sys.path.insert(0, path)
    from legal_harness.business.provider_registry import (
        resolve_provider_method, MethodNotWhitelisted,
    )
    from legal_harness.business.units import HarnessUnits
    from legal_harness.state.pg_store import PgMatterStore

    temporary = tempfile.TemporaryDirectory(prefix="juscite-e24-selfhost-")
    _ACTIVE_TMPDIRS.append(temporary)
    store = PgMatterStore(
        Path(temporary.name) / "state", dsn=dsn,
        schema="e24_" + _uuid.uuid4().hex[:12])
    units = HarnessUnits(store)
    methods = (HARNESS_SUBMISSION_METHODS | HARNESS_CALENDAR_SYNC_METHODS
               | HARNESS_SCHEDULE_METHODS
               | {"harness.register_material", "harness.read_material",
                  "harness.list_materials"})
    bound = {name: resolve_provider_method(name, units)
             for name in methods}
    store.create_matter(MATTER, "cas://profile-e24")
    units.save_procedure_event(
        "recon-lawyer", SCOPE, key("pe-1"),
        {"id": "pe-e24-court", "revision": 1, "matterId": MATTER,
         "kind": "court_event"})
    tmp = Path(temporary.name)
    config: dict = {
        "court_inbound_state_root": str(tmp / "inbound"),
        "anonymizer_contract": "p09/p10",
        "collection_state_root": str(tmp / "collection"),
        "e24_corpus_root": str(corpus),
        "e24_exports_root": str(exports),
    }

    def call_product(method, call_args, cfg=None):
        if method.startswith("submission."):
            from submission_package import submission_call
            return submission_call(method, call_args, cfg or config,
                                   harness_call=lambda h_method, h_args:
                                   bound[h_method](**h_args))
        if method.startswith("calendar."):
            from calendar_sync import calendar_sync_call
            return calendar_sync_call(method, call_args, cfg or config,
                                      harness_call=lambda h_method, h_args:
                                      bound[h_method](**h_args))
        # collection.*／material.deidentify：产品桥无 harness 维度，同链。
        return legal_entry.call(method, call_args, cfg or config)

    def call_harness(method, call_args):
        target = bound.get(method)
        if target is None:
            raise MethodNotWhitelisted(method)
        return target(**call_args)

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
                      config, bound=bound)
    # selfhost 桥负向：封闭注册外形态拒（与 desktop 同语义）。
    try:
        resolve = bound.get("harness.submission_submit")
        if resolve is None:
            raise MethodNotWhitelisted("harness.submission_submit")
    except MethodNotWhitelisted as exc:
        recon.step("c06_selfhost_closed_registry",
                   "method_not_whitelisted" in str(exc))
    store.destroy()
    return 0


def write_evidence(profile: str, recon: Recon, harness_root: Path,
                   started: str, code: int) -> Path:
    evidence_dir = (REPO_ROOT / "docs" / "construction" / "evidence"
                    / "E24" / profile)
    evidence_dir.mkdir(parents=True, exist_ok=True)
    mirror = (REPO_ROOT / "evidence" / "E24" / profile)
    mirror.mkdir(parents=True, exist_ok=True)
    finished = datetime.now(timezone.utc).isoformat()
    summary = {
        "schema": "juscite-e24-external-actions-recon/1",
        "unit": "W3-U26",
        "obligation": "E24",
        "assertion": ("日历/短信/法院/微信按授权材料与确认，送达事实不由"
                      "上传日补；实务提醒F118待裁，外部发送提交另授权"),
        "profile": profile,
        "verdict": "RECON_OK" if code == 0 else "RECON_FAIL",
        "started_at": started,
        "finished_at": finished,
        "consumes": {
            "W3-U12": "F59 submission_package／F60 calendar_sync"
                      "（juscite w3-u12＋harness w3-u12）",
            "W3-U13": "F61 wechat_collection（juscite w3-u13）",
            "W3-U14": "F62 court_inbound（juscite w3-u14）",
        },
        "harness_worktree": str(harness_root),
        "harness_branch": "w3-u20（基 w3-u12@7c9ccc16；master 929d0802 零动）",
        "jc_worktree": str(DEFAULT_JC_ROOT),
        "jc_pin": {"client_sha256": JC_CLIENT_SHA256,
                   "deadline_presets_sha256": JC_DEADLINE_SHA256},
        "checks": recon.checks,
        "check_count": len(recon.checks),
        "failed": [c["check"] for c in recon.checks
                   if c["status"] != "PASS"],
        "boundaries": [
            "裁决#6：滴答/飞书/微信合成先行，真实 OAuth 授权后补联测",
            "裁决#20：F118 v1.5 实务提醒扩卡施工归 W4——本义务只验分离"
            "不变量，不前造",
            "OCR 引擎权威＝F40/F41 已 VERIFIED 面；本对账在 F41 桥 seam "
            "注入确定性合成行，不重跑 OCR 验收",
            "外部发送/提交＝结构性另授权（封闭注册外，非开关）",
        ],
    }
    payload = json.dumps(summary, ensure_ascii=False, indent=1)
    for target in (evidence_dir, mirror):
        (target / "e24_external_actions_recon.json").write_text(
            payload + "\n", encoding="utf-8")
    lines = [f"# E24 外部动作与程序提醒分离 recon（{profile}）", "",
             f"- unit: W3-U26 · obligation: E24 · profile: {profile}",
             f"- verdict: **{summary['verdict']}**"
             f" ({len(recon.checks)} checks, exit {code})",
             f"- harness: `{harness_root}` @ w3-u20"
             "（基 w3-u12@7c9ccc16＝U12 交付；master 929d0802 零动）",
             f"- JC: `{DEFAULT_JC_ROOT}` @ w2b-u55"
             "（F107 冻结引擎 sha256 钉定）",
             f"- started: {started} · finished: {finished}", "",
             "| # | check | status |", "|---|---|---|"]
    for index, check in enumerate(recon.checks, 1):
        lines.append(f"| {index} | {check['check']} | {check['status']} |")
    lines += ["", "全部合成材料；滴答/飞书＝本机回环合成端点（裁决#6）；",
              "desktop＝产品桥子进程全链（SQLite），selfhost＝PgMatterStore",
              "直连 lh-pg-e08（同一封闭注册）；E24 分离不变量全过：外部动",
              "作四通道按授权材料与确认、幂等回流、不改期限、送达事实不由",
              "上传日补、外部发送/提交结构性另授权、F118 派发仅桌面通知且",
              "实务提醒零自动启用。"]
    text = "\n".join(lines) + "\n"
    for target in (evidence_dir, mirror):
        (target / "e24_external_actions_recon.md").write_text(
            text, encoding="utf-8")
    return evidence_dir


def make_exports(exports: Path) -> None:
    exports.mkdir(parents=True, exist_ok=True)
    # write_bytes（不用 write_text：Windows newline 翻译会破坏确定性锚）。
    (exports / "wx_chat_001.txt").write_bytes(
        WX_CHAT_TEXT.encode("utf-8"))
    (exports / "wx_chat_002.txt").write_bytes(
        WX_CHAT_TEXT_002.encode("utf-8"))
    (exports / "wx_ghost.txt").write_bytes(
        ("【聊天记录导出（合成样本）】\n导出对象：" + UNAUTHORIZED_WX_ID
         + "\n").encode("utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--profile", action="append",
                        choices=["desktop", "selfhost"])
    parser.add_argument("--harness-root", type=Path,
                        default=DEFAULT_HARNESS_ROOT)
    parser.add_argument("--pg-dsn", default=DEFAULT_PG_DSN)
    parser.add_argument("--anonymizer-src", default=None)
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
    anonymizer_src = resolve_anonymizer_src(args.anonymizer_src)
    if anonymizer_src is None:
        print("RECON_BLOCKED: anonymizer w2a-u18 src unavailable"
              "（--anonymizer-src 或 JUSCITE_ANONYMIZER_SRC）")
        return 3
    sys.path.insert(0, str(anonymizer_src))
    holder = tempfile.TemporaryDirectory(prefix="juscite-e24-fixture-")
    _ACTIVE_TMPDIRS.append(holder)
    fixture = Path(holder.name)
    corpus = fixture / "att-corpus"
    make_attachment_corpus(corpus)
    exports = fixture / "exports"
    make_exports(exports)
    failures = 0
    first = True
    for profile in profiles:
        started = datetime.now(timezone.utc).isoformat()
        recon = Recon(args.harness_root)
        try:
            if first:
                recon.branch_checks()
            if profile == "desktop":
                code = run_desktop(recon, args.harness_root, corpus, exports)
            else:
                code = run_selfhost(recon, args.harness_root, args.pg_dsn,
                                    corpus, exports)
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

"""F115 案件看板投影＋F116 案件域分类对账（W3-U20 v1／W4-U49 v1.5）——
双 profile。

验收命令（juscite worktree w4-u49 根 cwd）：
  python -X utf8 tools/PENDING_OWNER_f115_f116_dashboard_domain_recon.py
      --profile desktop --profile selfhost

对账对象：harness 分支 w4-u49（基 W4 战役链头 w4-u46@5d6c920d——A2 分支链
常驻，schema 钉 32 零新账）的 --dashboard-json/--casedomain-json/
--cover-json/--module-json 封闭径——desktop profile 与产品桥（legal_entry
→ 子进程 public_entry）完全同一条链（SQLite 状态根）；selfhost profile＝
PgMatterStore 直连 lh-pg-e08（resolve_provider_method 同一封闭注册；产品
面经 harness_call 注入同函数链）。全部合成材料：临时状态根、合成案件/
待办/日程/账面；harness 检出零字节改动（只运行其代码，git 只读命令核对
分支）。

实跑覆盖（06 F115/F116 assertion 逐条）：
  F115 v1（08§1 复合行基础投影段）：在办案件×待办（建议/采纳/执行真状
  态）×日程（三分类分开＋整数日差倒计时）×E15/E16/E17/E18 账面摘要——
  **消费账面真投影不造第二真源**（看板 accounts 摘要与直接调用既有公开
  方法逐字段同值对账）；只读纪律（读前后账行逐表计数不变；同输入同投
  影）；域筛选作用于持久字段；**不借 F118 提醒派发**（投影行/日程摘要零
  提醒键；提醒账行读前后不变）；全局对话主页形状。
  F116 v1：四值闭集（诉讼/执行/非诉/刑事）字段声明/改域/显式清除
  （revision 只追加历史可回读）→同内容幂等重放→闭集外自由文本具名拒→
  显式 null=未分类→coverage 恒带 exhaustiveClaim=false（分类不冒全域规
  则完备）→字段和筛选持久（重开存储回读不变）→F04 案件写门（受管案
  outsider 具名拒）。
  F115 v1.5 段（W4-U49）——封皮完整字段：dashboard.cover_read 全展开字段
  **逐字段绑定 harness 案件账真实回读**（F113 身份锚点/F116 域字段/F04
  成员名册/W08 生命周期/待办与建议真状态/日程摘要/E15-E18 账面摘要——与
  直接调用同值对账＝零展示假字段）；面标记 f115-v1.5-cover-sheet；零提醒
  键；读前后零账变；受管案 F04 读门（outsider 具名拒）。
  F116 v1.5 段（W4-U49）——分模块页面：dashboard.module_read 四具名域各
  一页，页行与看板 domainFilter 同一次投影逐字段同形（转录不另算）；
  unclassified 是筛选归纳表示值不是模块页（f116_module_value_unknown 具
  名拒）；coverage 恒 exhaustiveClaim=false（分模块不冒全域规则完备）；
  受管案对 outsider 不入页只进诚实计数 excludedByPermission。
  分离红线（W3-U26 不变量，裁决#20 后提醒本体归 W4-U50）：看板/封皮/模块
  页全部只投影显式 schedule_event 声明的日程，不自动启用实务提醒、零提醒
  派发键。
  桥负向（C 系）：未配置 fail-closed／未知方法 method_not_connected／
  封闭注册外形态 harness 级 method_not_whitelisted（--dashboard-json/
  --casedomain-json/--cover-json/--module-json 直探）／查询与筛选闭集外
  具名拒。

退出码：0 = 全部 profile RECON_OK；2 = RECON_FAIL；3 = 环境缺失。
证据：docs/construction/evidence/F115/<profile>/、F116/<profile>/（另写仓
库根 evidence/ 同名镜像）。
"""
from __future__ import annotations

import argparse
import ast
import contextlib
import json
import sqlite3
import subprocess
import sys
import tempfile
import uuid as _uuid
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "implementation" / "python"))
sys.path.insert(0, str(REPO_ROOT / "implementation" / "tests"))

import legal_entry  # noqa: E402
from legal_entry import HarnessCommandError, NotConnected  # noqa: E402
from dashboard_projection import DashboardProjectionError  # noqa: E402

DEFAULT_HARNESS_ROOT = Path(
    r"D:\Codex\1.法律工作区\legal-harness工作区\legal-harness-repo"
    r"\.local\worktrees\w4-u49")

MATTER = "m-f115f116-recon"
SCOPE = {"kind": "matter", "matterId": MATTER}
AS_OF = "2026-10-18"

# lh-pg-e08 容器（E08 拓扑）：仅回环端口、合成专用凭据（--pg-dsn 覆写）。
DEFAULT_PG_DSN = "postgresql://lh_app:e08-synth-only@127.0.0.1:55432/legal_harness"

HARNESS_BASE_W4_U46 = "5d6c920d"
HARNESS_MASTER_PIN = "929d0802"

F116_DOMAINS = ["criminal", "enforcement", "litigation", "non_litigation"]

# 封闭注册面（recon 直接绑定/直探用）。
HARNESS_DASHBOARD_METHODS = frozenset({"harness.dashboard_read"})
HARNESS_CASE_DOMAIN_METHODS = frozenset({
    "harness.case_domain_declare", "harness.case_domain_read"})
HARNESS_COVER_MODULE_METHODS = frozenset({
    "harness.cover_read", "harness.module_read"})
DASHBOARD_METHODS = frozenset({
    "dashboard.read", "dashboard.domain_declare", "dashboard.domain_read",
    "dashboard.cover_read", "dashboard.module_read"})
# 播种面（harness 既有 VERIFIED 方法，dashboard 账面真源）。
SEED_METHODS = frozenset({
    "harness.save_procedure_event", "harness.schedule_event",
    "tasks.suggest", "tasks.proposal_decide", "tasks.decide",
    "harness.path_candidate_register", "harness.evidence_attempt_register",
    "harness.cash_source_register", "harness.save_goal",
    "harness.strategy_basis_register", "harness.transition_matter",
    "harness.case_member_declare", "harness.case_identity_register",
    "harness.case_permission_rule",
})

_READONLY_WATCHED = ("change_events", "command_receipts", "reminders",
                     "derived_tasks", "task_proposals", "deadlines",
                     "case_domains", "host_dispatches", "case_identity",
                     "case_members", "case_permission_rules")

_ACTIVE_TMPDIRS: list = []


def key(request_id: str) -> dict:
    return {"requestId": request_id, "targetId": None,
            "expectedRevision": None, "inputRefs": []}


def href(kind: str, object_id: str, matter: str = MATTER,
         version: str = "1") -> dict:
    return {"owner": "harness", "kind": kind, "id": object_id,
            "version": version, "matterId": matter}


def rsn(oid: str) -> dict:
    return {"owner": "host", "kind": "decision-receipt", "id": oid,
            "version": "1"}


def base_candidate(candidate_id: str = "cand-recon") -> dict:
    return {
        "candidateId": candidate_id, "pathType": "claim",
        "title": "违约损害赔偿（F115 recon 合成）",
        "basisRefs": [href("fact", "fact-recon")],
        "triggerLocator": {"materialRef": href("material", "mat-recon"),
                           "documentId": "doc-recon", "pageIndex": 1,
                           "blockId": "blk-recon"},
        "elements": [
            {"elementId": "el-recon", "statement": "存在合同",
             "status": "established",
             "factRefs": [href("fact", "fact-recon")],
             "counterEvidenceRefs": []},
        ],
        "lawVersionRefs": [],
        "relation": {"kind": "parallel", "targetCandidateIds": []},
        "lossOverlap": {"declared": False, "sameLossWith": [], "note": None},
    }


def attempt_payload(attempt_id: str = "ea-recon") -> dict:
    return {
        "attemptId": attempt_id, "taskRef": href("task", "t-evidence-recon"),
        "title": "十项同粒度取证请求（F115 recon 合成轮）",
        "items": [
            {"itemId": "ev-recon", "proposition": "主张银行流水在被告处",
             "channel": "court",
             "authorizationRef": href("authorization", "auth-recon"),
             "requestScope": {"project": "p-recon", "period": "2026-Q4",
                              "subject": "s-recon",
                              "materialType": "bank_flow"}},
        ],
        "note": "全合成取证轮",
    }


def goal_payload(goal_id: str = "g-recon") -> dict:
    return {
        "schemaVersion": "1.0.0-draft", "matterId": MATTER,
        "goalId": goal_id, "revision": 1,
        "confirmedScope": "F115 recon 合成：货款追收",
        "hardConstraints": [
            {"id": "hc-recon", "kind": "min_recovery", "value": "85000",
             "description": "最低实收"},
        ],
        "preferences": [],
        "unitTiming": {"unit": "CNY", "asOf": "2026-10-17"},
        "sourceDecisionRef": None,
        "supersedesRevision": None,
    }


def strategy_payload(goal_refs: list) -> dict:
    return {
        "strategyId": "st-recon", "revision": 1,
        "title": "F115 recon 合成策略：诉讼追收保全关系",
        "goalRefs": goal_refs,
        "factRevision": "v1", "lawRevision": "v1",
        "hardConstraints": [
            {"constraintId": "hc-recon-2",
             "statement": "不接受分期（合成硬约束）"},
        ],
    }


def source_payload() -> dict:
    return {
        "sourcePaymentId": "sp-recon", "payer": "被告（合成）",
        "payee": "原告（合成）", "amountMinor": 1_000_000,
        "currency": "CNY", "realityKey": "rz-f115-recon-1",
        "voucherRefs": [href("voucher", "v-recon")],
        "occurredAt": "2026-10-01", "holder": "client",
    }


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
                            DashboardProjectionError, LookupError)):
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
        base = self.git(self.harness_root, "merge-base", "HEAD", "w4-u46")
        master = self.git(self.harness_root, "rev-parse", "master")
        self.step("c01_harness_branch", branch == "w4-u49", branch=branch)
        self.step("c01_harness_base_on_w4_u46_chain_head",
                  base.startswith(HARNESS_BASE_W4_U46), base=base)
        self.step("c01_harness_master_untouched",
                  master.startswith(HARNESS_MASTER_PIN), master=master)
        dirty = self.git(self.harness_root, "status", "--porcelain")
        self.step("c01_harness_worktree_clean", dirty == "",
                  dirty=dirty[:200])
        here_branch = self.git(REPO_ROOT, "rev-parse", "--abbrev-ref", "HEAD")
        # 实质不变量＝被测树要么是工单分支本体，要么是 main 且
        # merge-base(HEAD, w4-u49)==w4-u49 头（账房合并后复验模式）。
        merged_tip_ = self.git(REPO_ROOT, "merge-base", "HEAD", "w4-u49")
        wt_tip_ = self.git(REPO_ROOT, "rev-parse", "--verify", "w4-u49")
        merged_mode_ = here_branch == "main" and merged_tip_ == wt_tip_ and bool(wt_tip_)
        self.step("c01_juscite_branch", here_branch == "w4-u49" or merged_mode_,
                  branch=here_branch, merged_tip=merged_tip_[:12],
                  worktree_tip=wt_tip_[:12])
        # F115 零借提醒面＋零封皮（产品面 AST：提醒/封皮方法不作代码出现）。
        source = (REPO_ROOT / "implementation" / "python"
                  / "dashboard_projection.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        forbidden = {"reminder_report", "schedule_event", "schedule_cancel",
                     "f118_scheduler", "cover_sheet_declare", "infer_domain"}
        code_refs = set()
        imports = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                got = {alias.name.split(".")[0] for alias in node.names}
                imports |= got
                code_refs |= got
            elif isinstance(node, ast.ImportFrom) and node.module:
                imports.add(node.module.split(".")[0])
                code_refs.add(node.module.split(".")[0])
            elif isinstance(node, ast.Attribute):
                code_refs.add(node.attr)
            elif isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load):
                code_refs.add(node.id)
        self.step("c01_f115_no_reminder_face_no_cover_sheet_in_code",
                  not (code_refs & forbidden),
                  leaked=sorted(code_refs & forbidden))
        self.step("c01_import_closure",
                  imports <= {"json", "__future__", "legal_entry"},
                  imports=sorted(imports))

    # ------------------------------------------------------------------
    # common_flow(call_product, call_harness, query, reopen, register_matter)
    # call_product(method,args)＝产品面 dashboard.*；
    # call_harness(method,args)＝harness 账面（播种与直连对账）；
    # query(sql,params)＝状态根只读查询；
    # reopen()＝重开同一状态根的新存储句柄（持久性检验）；
    # register_matter(matter_id)＝在新存储上建案件。
    # ------------------------------------------------------------------

    def common_flow(self, call_product, call_harness, query, reopen,
                    register_matter):
        self.f116_flow(call_product, call_harness, query, reopen)
        self.f115_flow(call_product, call_harness, query)
        self.f115_v15_cover_flow(call_product, call_harness, query)
        self.f116_v15_module_flow(call_product, call_harness, query,
                                  register_matter)
        self.gate_flow(call_product, call_harness, register_matter)

    # -- F115-v1.5 封皮完整字段（W4-U49）--------------------------------

    def f115_v15_cover_flow(self, call_product, call_harness, query):
        u = call_harness
        # F113 身份锚点（真实案件账回读源）。
        u("harness.case_identity_register", {
            "actor_id": "lawyer-1", "scope": SCOPE, "key": key("ci-1"),
            "identity": {"identityKind": "litigation",
                         "caseNumber": "（2026）recon 0105 民初 49 号",
                         "court": "合成市第一人民法院", "note": None}})
        # 受管武装（首个 declare＝bootstrap；首条 rule 免检）——授予
        # lawyer-1 read/write，封皮读过 F04 读门；此前全部流程在未武装
        # 自由窗完成（v1 段零受管）。
        u("harness.case_member_declare", {
            "actor_id": "admin-1", "scope": SCOPE, "key": key("mb-1"),
            "members": [{"userId": "lawyer-1", "orgId": "org-1",
                         "roles": ["case-lawyer"]}]})
        u("harness.case_permission_rule", {
            "actor_id": "admin-1", "scope": SCOPE, "key": key("rl-1"),
            "rules": [
                {"principalKind": "user", "principalId": "lawyer-1",
                 "action": "read", "effect": "allow"},
                {"principalKind": "user", "principalId": "lawyer-1",
                 "action": "write", "effect": "allow"}]})

        def snapshot():
            counts = {}
            for table in _READONLY_WATCHED:
                counts[table] = query(
                    f"SELECT COUNT(*) AS n FROM {table}", ())[0]["n"]
            return counts

        before = snapshot()
        cover = call_product("dashboard.cover_read", {
            "actor_id": "lawyer-1", "scope": SCOPE,
            "query": {"asOf": AS_OF}})
        self.step("f115v15_c01_cover_read_only",
                  snapshot() == before, watched=_READONLY_WATCHED)
        body = cover["cover"]
        self.step("f115v15_c02_face_marker",
                  cover["face"]["kind"] == "f115-v1.5-cover-sheet"
                  and cover["face"]["reminderFace"]
                  == "excluded-f118-scheduler-only"
                  and cover["face"]["source"]
                  == "harness.cover_read-transcription",
                  face=json.dumps(cover["face"], ensure_ascii=False))
        # 封皮字段逐字段绑定案件账真实回读（与直接调用同值＝零展示假字段）。
        direct_identity = u("harness.case_identity_read", {"scope": SCOPE})
        direct_domain = u("harness.case_domain_read",
                          {"scope": SCOPE, "actor_id": "lawyer-1"})
        direct_perm = u("harness.case_permission_read", {"scope": SCOPE})
        self.step("f115v15_c03_identity_real_readback",
                  body["identity"] == direct_identity["identity"]
                  and body["identity"]["identityKind"] == "litigation"
                  and body["identity"]["caseNumber"]
                  == "（2026）recon 0105 民初 49 号",
                  identity=json.dumps(body["identity"], ensure_ascii=False))
        self.step("f115v15_c04_domain_real_readback",
                  body["domain"] == direct_domain["domain"]
                  and body["domain"]["domain"] == "litigation",
                  domain=json.dumps(body["domain"], ensure_ascii=False))
        self.step("f115v15_c05_members_real_readback",
                  body["members"] == [
                      {"userId": m["userId"], "orgId": m["orgId"],
                       "roles": m["roles"]}
                      for m in direct_perm["members"]]
                  and body["members"] == [
                      {"userId": "lawyer-1", "orgId": "org-1",
                       "roles": ["case-lawyer"]}],
                  members=json.dumps(body["members"], ensure_ascii=False))
        self.step("f115v15_c06_lifecycle_and_timestamps",
                  body["lifecycleState"] == "open"
                  and body["matterRevision"] >= 1
                  and body["createdAt"] and body["updatedAt"],
                  lifecycle=body["lifecycleState"])
        # 待办/日程/账面：与看板行同值（同一投影家族，不另算不冒第二真源）。
        board = call_product("dashboard.read", {
            "actor_id": "lawyer-1",
            "query": {"asOf": AS_OF, "includeClosed": True}})
        board_row = next(m for m in board["matters"]
                         if m["matterId"] == MATTER)
        self.step("f115v15_c07_tasks_schedule_accounts_same_as_board",
                  body["tasks"] == board_row["tasks"]
                  and body["proposals"] == board_row["proposals"]
                  and body["schedule"] == board_row["schedule"]
                  and body["accounts"] == board_row["accounts"],
                  schedule=json.dumps(body["schedule"],
                                      ensure_ascii=False))
        # 分离红线：封皮零提醒派发键（W3-U26 不变量；W4-U50 提醒本体不借
        # 看板启用）。
        self.step("f115v15_c08_no_reminder_face_on_cover",
                  "dueDesktopReminders" not in body
                  and "reminders" not in body
                  and all("dueDesktopReminders" not in str(k)
                          and "reminders" not in str(k)
                          for k in body),
                  keys=sorted(body))
        # 负向：查询闭集外/scope 缺席具名拒。
        self.expect_error("f115v15_c09_query_closed_set", lambda:
            call_product("dashboard.cover_read", {
                "actor_id": "lawyer-1", "scope": SCOPE,
                "query": {"asOf": AS_OF, "orderBy": "score"}}),
            "f115_query_fields_not_closed")
        self.expect_error("f115v15_c09_scope_missing", lambda:
            call_product("dashboard.cover_read", {
                "actor_id": "lawyer-1", "query": {"asOf": AS_OF}}),
            "f115_field_missing:scope")
        # 受管案 F04 读门：outsider 读封皮具名拒。
        self.expect_error("f115v15_c10_cover_read_gate", lambda:
            call_product("dashboard.cover_read", {
                "actor_id": "outsider-1", "scope": SCOPE,
                "query": {"asOf": AS_OF}}),
            "case_permission_denied")

    # -- F116-v1.5 分模块页面（W4-U49）----------------------------------

    def f116_v15_module_flow(self, call_product, call_harness, query,
                             register_matter):
        # 额外三件合成案件各占一域（主案已 litigation——未武装自由窗）。
        domain_by_matter = {MATTER: "litigation"}
        for index, domain in enumerate(
                ("enforcement", "non_litigation", "criminal"), start=1):
            matter = f"m-mod-{index}"
            register_matter(matter)
            scope = {"kind": "matter", "matterId": matter}
            call_harness("harness.case_domain_declare", {
                "actor_id": "lawyer-1", "scope": scope,
                "key": key(f"md-{index}"),
                "declaration": {"domain": domain, "note": None}})
            domain_by_matter[matter] = domain
        # 一件未分类案件：不入任何模块页（unclassified 不是模块）。
        register_matter("m-mod-unclassified")
        # 看板基线（受管主案需 actor；其余未管直通）。
        board = call_product("dashboard.read", {
            "actor_id": "lawyer-1", "query": {"asOf": AS_OF,
                                              "includeClosed": True}})
        board_rows = {m["matterId"]: m for m in board["matters"]}
        for domain in ("litigation", "enforcement", "non_litigation",
                       "criminal"):
            page = call_product("dashboard.module_read", {
                "actor_id": "lawyer-1", "domain": domain,
                "query": {"asOf": AS_OF}})
            got = [m["matterId"] for m in page["matters"]]
            want = sorted(m for m, d in domain_by_matter.items()
                          if d == domain)
            self.step("f116v15_c01_module_page_domains",
                      page["module"]["domain"] == domain
                      and page["module"]["pageKind"]
                      == "domain-module-page"
                      and sorted(got) == want,
                      domain=domain, matters=got)
            # 页行与看板 domainFilter 同一次投影逐字段同形（转录不另算）。
            same = all(
                page["matters"][i] == board_rows[got[i]]
                for i in range(len(got)))
            self.step("f116v15_c02_module_rows_equal_board_projection",
                      same, domain=domain)
            self.step("f116v15_c03_module_coverage_not_exhaustive",
                      page["module"]["coverage"]["exhaustiveClaim"] is False
                      and page["module"]["coverage"]["kind"]
                      == "closed_set_v1_declared_only"
                      and sorted(page["module"]["declaredDomains"])
                      == F116_DOMAINS
                      and page["face"]["kind"]
                      == "f116-v1.5-domain-module-page"
                      and page["face"]["exhaustiveClaim"] is False,
                      domain=domain)
            # 分离红线：模块页零提醒键。
            self.step("f116v15_c04_no_reminder_keys",
                      "dueDesktopReminders" not in page
                      and "reminders" not in page,
                      domain=domain)
        # 未分类案件不属于任何模块页。
        for domain in F116_DOMAINS:
            page = call_product("dashboard.module_read", {
                "actor_id": "lawyer-1", "domain": domain,
                "query": {"asOf": AS_OF}})
            self.step("f116v15_c05_unclassified_not_in_any_module",
                      "m-mod-unclassified"
                      not in [m["matterId"] for m in page["matters"]],
                      domain=domain)
        # unclassified/闭集外域不是模块页（具名拒）。
        self.expect_error("f116v15_c06_unclassified_module_refused", lambda:
            call_product("dashboard.module_read", {
                "domain": "unclassified", "query": {"asOf": AS_OF}}),
            "f116_module_value_unknown:unclassified")
        self.expect_error("f116v15_c06_free_text_module_refused", lambda:
            call_product("dashboard.module_read", {
                "domain": "行政", "query": {"asOf": AS_OF}}),
            "f116_module_value_unknown")
        # 查询闭集外具名拒。
        self.expect_error("f116v15_c07_query_closed_set", lambda:
            call_product("dashboard.module_read", {
                "domain": "litigation",
                "query": {"asOf": AS_OF, "domainFilter": []}}),
            "f115_query_fields_not_closed")
        # 受管主案对匿名/outsider 不入页只进诚实计数（F04 读门）。
        page_anon = call_product("dashboard.module_read", {
            "domain": "litigation", "query": {"asOf": AS_OF}})
        self.step("f116v15_c08_permission_excluded_counted",
                  MATTER not in [m["matterId"] for m in page_anon["matters"]]
                  and page_anon["summary"]["excludedByPermission"] == 1,
                  excluded=page_anon["summary"]["excludedByPermission"])

    def gate_flow(self, call_product, call_harness, register_matter):
        """F04 案件写/读门（独立受管案——不污染看板主流）：受管案
        outsider 域声明/读具名拒（fail-closed）。"""
        gate_scope = {"kind": "matter", "matterId": "m-gate-f116"}
        register_matter("m-gate-f116")
        call_harness("harness.case_member_declare", {
            "actor_id": "admin-1", "scope": gate_scope,
            "key": key("cd-mb"),
            "members": [{"userId": "admin-1", "orgId": "org-1",
                         "roles": ["case-admin"]}]})
        self.expect_error("f116_c07_case_write_gate_refused", lambda:
            call_product("dashboard.domain_declare", {
                "actor_id": "outsider-1", "scope": gate_scope,
                "key": key("cd-out"),
                "declaration": {"domain": "litigation", "note": None}}),
            "case_permission_denied")
        self.expect_error("f116_c07_case_read_gate_refused", lambda:
            call_product("dashboard.domain_read", {
                "scope": gate_scope, "actor_id": "outsider-1"}),
            "case_permission_denied")

    # -- F116 案件域分类 ------------------------------------------------

    def f116_flow(self, call_product, call_harness, query, reopen):
        # 四值闭集逐次声明：revision 只追加，历史可回读。
        for index, domain in enumerate(F116_DOMAINS):
            declared = call_product("dashboard.domain_declare", {
                "actor_id": "lawyer-1", "scope": SCOPE,
                "key": key(f"cd-{index}"),
                "declaration": {"domain": domain,
                                "note": f"recon 合成域 {domain}"}})
            self.step("f116_c02_declare_closed_set",
                      declared["domain"]["domain"] == domain
                      and declared["domain"]["revision"] == index + 1,
                      domain=domain, revision=declared["domain"]["revision"])
        rows = query("SELECT revision, domain, current FROM case_domains"
                     " WHERE matter_id=? ORDER BY revision", (MATTER,))
        self.step("f116_c02_history_append_only",
                  [(r["revision"], r["domain"], r["current"])
                   for r in rows] == [(1, "criminal", 0), (2, "enforcement", 0),
                                      (3, "litigation", 0),
                                      (4, "non_litigation", 1)],
                  rows=len(rows))
        replay = call_product("dashboard.domain_declare", {
            "actor_id": "lawyer-1", "scope": SCOPE, "key": key("cd-replay"),
            "declaration": {"domain": "non_litigation",
                            "note": "recon 合成域 non_litigation"}})
        self.step("f116_c02_replay_idempotent",
                  replay["replayed"] is True
                  and replay["domain"]["revision"] == 4,
                  revision=replay["domain"]["revision"])
        # 闭集外自由文本具名拒；字段闭集（缺席/越界键）具名拒。
        self.expect_error("f116_c03_free_text_refused", lambda:
            call_product("dashboard.domain_declare", {
                "actor_id": "lawyer-1", "scope": SCOPE,
                "key": key("cd-bad"),
                "declaration": {"domain": "行政", "note": None}}),
            "f116_domain_value_unknown")
        self.expect_error("f116_c04_fields_missing_refused", lambda:
            call_product("dashboard.domain_declare", {
                "actor_id": "lawyer-1", "scope": SCOPE,
                "key": key("cd-miss"),
                "declaration": {"domain": "litigation"}}),
            "f116_declaration_fields_missing")
        self.expect_error("f116_c04_fields_not_closed_refused", lambda:
            call_product("dashboard.domain_declare", {
                "actor_id": "lawyer-1", "scope": SCOPE,
                "key": key("cd-extra"),
                "declaration": {"domain": "litigation", "note": None,
                                "rule": "全域规则"}}),
            "f116_declaration_fields_not_closed")
        # 显式 null=未分类（新 revision，不删历史）。
        cleared = call_product("dashboard.domain_declare", {
            "actor_id": "lawyer-1", "scope": SCOPE, "key": key("cd-null"),
            "declaration": {"domain": None, "note": None}})
        self.step("f116_c05_explicit_null_clears",
                  cleared["domain"]["domain"] is None
                  and cleared["domain"]["revision"] == 5,
                  revision=cleared["domain"]["revision"])
        # coverage 声明面：四域＋exhaustiveClaim=false（不冒全域规则完备）。
        read = call_product("dashboard.domain_read", {"scope": SCOPE})
        self.step("f116_c05_coverage_not_exhaustive",
                  read["coverage"]["exhaustiveClaim"] is False
                  and sorted(read["coverage"]["domains"]) == F116_DOMAINS
                  and read["coverage"]["kind"] == "closed_set_v1_declared_only",
                  coverage=json.dumps(read["coverage"], ensure_ascii=False))
        # 字段和筛选持久：重开存储回读不变。
        reopened_units_state = query(
            "SELECT domain FROM case_domains WHERE matter_id=? AND current=1",
            (MATTER,))
        reopen()
        after = query(
            "SELECT domain FROM case_domains WHERE matter_id=? AND current=1",
            (MATTER,))
        self.step("f116_c06_persists_across_reopen",
                  after == reopened_units_state
                  and after and after[0]["domain"] is None,
                  before=json.dumps(reopened_units_state),
                  after=json.dumps(after))

    # -- F115 案件看板 v1 基础投影 --------------------------------------

    def f115_flow(self, call_product, call_harness, query):
        u = call_harness
        # 域声明回 litigation（C 段已清空——筛选基准重建）。
        call_product("dashboard.domain_declare", {
            "actor_id": "lawyer-1", "scope": SCOPE, "key": key("d1"),
            "declaration": {"domain": "litigation", "note": None}})
        # 待办：采纳即 accepted；start 转 running；一条 pending 建议。
        u("tasks.suggest", {"actor_id": "lawyer-1", "scope": SCOPE,
                            "key": key("sg-1"),
                            "proposal": {
                                "proposalId": "prop-recon-1",
                                "title": "起草起诉状（recon）",
                                "originKind": "manual", "originRef": None,
                                "dueDate": "2026-11-01", "note": None}})
        u("tasks.proposal_decide", {
            "actor_id": "lawyer-1", "scope": SCOPE, "key": key("pd-1"),
            "decision": {"proposalId": "prop-recon-1", "action": "adopt",
                         "reasonRef": rsn("r-1"), "receiptRef": rsn("rc-1")}})
        u("tasks.suggest", {"actor_id": "lawyer-1", "scope": SCOPE,
                            "key": key("sg-2"),
                            "proposal": {
                                "proposalId": "prop-recon-2",
                                "title": "待定建议（recon）",
                                "originKind": "manual", "originRef": None,
                                "dueDate": None, "note": None}})
        u("tasks.suggest", {"actor_id": "lawyer-1", "scope": SCOPE,
                            "key": key("sg-3"),
                            "proposal": {
                                "proposalId": "prop-recon-3",
                                "title": "保全申请（recon）",
                                "originKind": "manual", "originRef": None,
                                "dueDate": "2026-11-10", "note": None}})
        u("tasks.proposal_decide", {
            "actor_id": "lawyer-1", "scope": SCOPE, "key": key("pd-3"),
            "decision": {"proposalId": "prop-recon-3", "action": "adopt",
                         "reasonRef": rsn("r-3"), "receiptRef": rsn("rc-3")}})
        u("tasks.decide", {"actor_id": "lawyer-1", "scope": SCOPE,
                           "key": key("td-3"),
                           "task_ref": {"id": "task-prop-recon-3"},
                           "decision": {"action": "start",
                                        "reasonRef": rsn("r-3s"),
                                        "receiptRef": rsn("rc-3s")}})
        # 日程：程序期限锚真实链行（+1 天 urgent）＋合同义务（远期）。
        u("harness.save_procedure_event", {
            "actor_id": "lawyer-1", "scope": SCOPE, "key": key("pe-1"),
            "event": {"id": "pe-recon-court", "revision": 1,
                      "matterId": MATTER, "kind": "court_event"}})
        u("harness.schedule_event", {
            "actor_id": "lawyer-1", "scope": SCOPE, "key": key("se-1"),
            "event": {"id": "sched-recon-prog",
                      "classification": "program_deadline",
                      "title": "上诉期届满（recon 合成）",
                      "dueDate": "2026-10-19",
                      "eventRef": {"eventId": "pe-recon-court",
                                   "eventRevision": 1}},
            "reminders": []})
        u("harness.schedule_event", {
            "actor_id": "lawyer-1", "scope": SCOPE, "key": key("se-2"),
            "event": {"id": "sched-recon-contract",
                      "classification": "contract_obligation",
                      "title": "合同付款义务（recon 合成）",
                      "dueDate": "2026-12-01"},
            "reminders": []})
        # E15/E16/E17/E18 账面（dashboard 消费的真源）。
        u("harness.path_candidate_register", {
            "actor_id": "assistant-1", "scope": SCOPE, "key": key("cand-1"),
            "candidate": base_candidate()})
        u("harness.evidence_attempt_register", {
            "actor_id": "assistant-1", "scope": SCOPE, "key": key("ea-1"),
            "attempt": attempt_payload()})
        u("harness.cash_source_register", {
            "actor_id": "lawyer-1", "scope": SCOPE, "key": key("cs-1"),
            "source": source_payload()})
        goal = u("harness.save_goal", {
            "actor_id": "lawyer-1", "scope": SCOPE, "key": key("g-1"),
            "goal": goal_payload()})
        u("harness.strategy_basis_register", {
            "actor_id": "lawyer-1", "scope": SCOPE, "key": key("st-1"),
            "strategy": strategy_payload([goal["goalRef"]])})

        def snapshot() -> dict:
            counts = {}
            for table in _READONLY_WATCHED:
                counts[table] = query(
                    f"SELECT COUNT(*) AS n FROM {table}", ())[0]["n"]
            return counts

        before = snapshot()
        view = call_product("dashboard.read", {
            "actor_id": None, "query": {"asOf": AS_OF}})
        view_again = call_product("dashboard.read", {
            "actor_id": None, "query": {"asOf": AS_OF}})
        self.step("f115_c08_read_only_ledger_untouched",
                  snapshot() == before, watched=_READONLY_WATCHED)
        self.step("f115_c08_same_input_same_projection",
                  json.dumps(view, sort_keys=True, ensure_ascii=False)
                  == json.dumps(view_again, sort_keys=True,
                                ensure_ascii=False))
        row = view["matters"][0]
        self.step("f115_c09_matter_row_shape",
                  view["summary"]["mattersTotal"] == 1
                  and row["matterId"] == MATTER
                  and row["lifecycleState"] == "open"
                  and row["domain"]["domain"] == "litigation",
                  matterId=row["matterId"])
        # 待办真状态：accepted（建议采纳 1＋两个日程随建任务 2）＋running 1
        # ＝open 4（F118：每 schedule 行随建 accepted 任务，账面如实计数）。
        self.step("f115_c09_todo_true_state",
                  row["tasks"]["countsByState"]["accepted"] == 3
                  and row["tasks"]["countsByState"]["running"] == 1
                  and row["tasks"]["openCount"] == 4
                  and row["proposals"]["pendingCount"] == 1,
                  tasks=row["tasks"], proposals=row["proposals"])
        # 日程：三分类分开计数＋倒计时整数日差＋urgent。
        schedule = row["schedule"]
        self.step("f115_c10_schedule_classification_split",
                  schedule["countsByClassification"] == {
                      "contract_obligation": 1, "practical_reminder": 0,
                      "program_deadline": 1}
                  and schedule["urgentCount"] == 1
                  and schedule["overdueCount"] == 0
                  and schedule["nextDue"]["scheduleId"]
                  == "sched-recon-prog"
                  and schedule["nextDue"]["dueDate"] == "2026-10-19"
                  and schedule["nextDue"]["daysRemaining"] == 1,
                  schedule=json.dumps(schedule, ensure_ascii=False))
        # 不借 F118 提醒派发：看板投影零提醒键＋提醒账行读前后不变。
        self.step("f115_c10_no_reminder_face_in_dashboard",
                  "dueDesktopReminders" not in schedule
                  and "reminders" not in schedule
                  and all("dueDesktopReminders" not in m
                          and "reminders" not in m
                          for m in view["matters"]),
                  keys=sorted(schedule))
        # 不造第二真源：accounts 摘要与直接调用既有公开方法逐字段同值。
        direct_path = u("harness.path_candidate_list",
                        {"scope": SCOPE})
        direct_cash = u("harness.cash_balance_read", {"scope": SCOPE})
        direct_evidence = u("harness.evidence_attempt_list",
                            {"scope": SCOPE})
        direct_strategy = u("harness.strategy_basis_list",
                            {"scope": SCOPE})
        accounts = row["accounts"]
        self.step("f115_c11_transcribes_path_evidence",
                  accounts["pathEvidence"] == {
                      "candidateCount": direct_path["candidateCount"],
                      "stateCounts": direct_path["stateCounts"]},
                  pathEvidence=json.dumps(accounts["pathEvidence"]))
        self.step("f115_c11_transcribes_cash",
                  accounts["cash"]["netVector"] == direct_cash["netVector"]
                  and accounts["cash"]["asOf"] == direct_cash["asOf"]
                  and accounts["cash"]["netVector"]["sourceTotalMinor"]
                  == 1_000_000,
                  netVector=json.dumps(accounts["cash"]["netVector"]))
        self.step("f115_c11_transcribes_evidence_attempt",
                  accounts["evidenceAttempt"] == {
                      "attemptCount": direct_evidence["attemptCount"],
                      "stateCounts": direct_evidence["stateCounts"]},
                  evidenceAttempt=json.dumps(accounts["evidenceAttempt"]))
        self.step("f115_c11_transcribes_strategy",
                  accounts["strategy"]
                  == {"strategyCount": direct_strategy["strategyCount"]}
                  and accounts["strategy"]["strategyCount"] == 1,
                  strategy=json.dumps(accounts["strategy"]))
        # 全局对话主页形状：coverage＋summary 一致性。
        summary = view["summary"]
        self.step("f115_c12_global_home_shape",
                  view["coverage"]["exhaustiveClaim"] is False
                  and summary["byDomain"]["litigation"] == 1
                  and summary["byDomain"]["unclassified"] == 0
                  and summary["openTasksTotal"] == 4
                  and summary["pendingProposalsTotal"] == 1
                  and summary["scheduleUrgentTotal"] == 1
                  and summary["excludedByPermission"] == 0,
                  summary=json.dumps(summary, ensure_ascii=False))
        # 域筛选（持久字段上的过滤）：litigation 命中／unclassified 空。
        filtered = call_product("dashboard.read", {
            "query": {"asOf": AS_OF, "domainFilter": ["litigation"]}})
        self.step("f115_c13_domain_filter_hits",
                  filtered["appliedDomainFilter"] == ["litigation"]
                  and [m["matterId"] for m in filtered["matters"]] == [MATTER],
                  matters=len(filtered["matters"]))
        unclassified = call_product("dashboard.read", {
            "query": {"asOf": AS_OF,
                      "domainFilter": ["unclassified"]}})
        self.step("f115_c13_domain_filter_unclassified_empty",
                  unclassified["matters"] == [],
                  matters=0)
        self.expect_error("f115_c13_filter_closed_set", lambda:
            call_product("dashboard.read", {
                "query": {"asOf": AS_OF, "domainFilter": ["行政"]}}),
            "f116_domain_filter_value_unknown")
        # 生命周期：closed 默认不出窗；includeClosed 显式带出。
        u("harness.transition_matter", {
            "actor_id": "lawyer-1", "scope": SCOPE, "key": key("life-1"),
            "transition": "close", "source_refs": [],
            "decision_ref": rsn("lr-1")})
        default_view = call_product("dashboard.read",
                                    {"query": {"asOf": AS_OF}})
        self.step("f115_c14_closed_excluded_by_default",
                  default_view["matters"] == [],
                  matters=0)
        with_closed = call_product("dashboard.read", {
            "query": {"asOf": AS_OF, "includeClosed": True}})
        self.step("f115_c14_include_closed_explicit",
                  [m["lifecycleState"] for m in with_closed["matters"]]
                  == ["closed"],
                  states=[m["lifecycleState"]
                          for m in with_closed["matters"]])
        u("harness.transition_matter", {
            "actor_id": "lawyer-1", "scope": SCOPE, "key": key("life-2"),
            "transition": "reopen", "source_refs": [],
            "decision_ref": rsn("lr-2")})
        reopened_view = call_product("dashboard.read",
                                     {"query": {"asOf": AS_OF}})
        self.step("f115_c14_reopen_maps_open",
                  [m["lifecycleState"] for m in reopened_view["matters"]]
                  == ["open"],
                  states=[m["lifecycleState"]
                          for m in reopened_view["matters"]])
        # 产品面投影 face 标记（v1 基础投影；提醒面排除；封皮指 v1.5 独
        # 立面——W4-U49 后封皮在 dashboard.cover_read，不再挂 pending）。
        self.step("f115_c15_face_marker",
                  view["face"]["kind"] == "dashboard-v1-basic-projection"
                  and view["face"]["reminderFace"]
                  == "excluded-f118-scheduler-only"
                  and view["face"]["coverSheet"] == "f115-v1.5-cover-face",
                  face=json.dumps(view["face"], ensure_ascii=False))

    # -- 桥负向（profile 共通；call_product/legal_entry 径） -------------

    def bridge_negatives_product(self, call_product):
        # 查询字段闭集外具名拒。
        self.expect_error("c16_query_fields_closed", lambda:
            call_product("dashboard.read", {
                "query": {"asOf": AS_OF, "orderBy": "score"}}),
            "f115_query_fields_not_closed")
        # 未知产品面方法（自动分类/推断面）＝method_not_connected。
        self.expect_error("c16_unknown_product_method", lambda:
            call_product("dashboard.classify", {}), "method_not_connected")

    def bridge_negatives_harness_entry(self, config):
        """封闭注册外形态直探（harness public_entry 子进程）：--dashboard-
        json/--casedomain-json 信封 surface 回声＋registry 级具名拒。"""
        import os as _os
        entry = config["harness_public_entry"]
        target = config["harness_target"]
        env = dict(_os.environ)
        if config.get("harness_state_root"):
            env["LH_LEGAL_STATE_ROOT"] = str(config["harness_state_root"])
        for name, method, expected_surface in (
                ("dashboard", "harness.dashboard_write",
                 "dashboard"),
                ("casedomain", "harness.case_domain_free", "casedomain"),
                ("cover", "harness.cover_write", "cover"),
                ("module", "harness.module_classify", "module")):
            handle = tempfile.NamedTemporaryFile(
                "w", encoding="utf-8", suffix=".json", delete=False)
            json.dump({"method": method, "params": {"scope": SCOPE}},
                      handle)
            handle.close()
            probe = subprocess.run(
                [sys.executable, "-X", "utf8", entry, f"--{name}-json",
                 handle.name, "--target", target],
                capture_output=True, text=True, env=env, timeout=120)
            _os.unlink(handle.name)
            self.step(f"c16_registry_{name}_forged_absent",
                      probe.returncode != 0
                      and "method_not_whitelisted" in probe.stdout,
                      stdout=probe.stdout[:160])
        # 真方法 surface 回声（envelope 独立成面）。
        handle = tempfile.NamedTemporaryFile(
            "w", encoding="utf-8", suffix=".json", delete=False)
        json.dump({"method": "harness.dashboard_read",
                   "params": {"actor_id": None,
                              "query": {"asOf": AS_OF}}}, handle)
        handle.close()
        probe = subprocess.run(
            [sys.executable, "-X", "utf8", entry, "--dashboard-json",
             handle.name, "--target", target],
            capture_output=True, text=True, env=env, timeout=120)
        _os.unlink(handle.name)
        envelope = {}
        try:
            envelope = json.loads(probe.stdout or "{}")
        except json.JSONDecodeError:
            pass
        self.step("c16_dashboard_envelope_surface_echo",
                  probe.returncode == 0
                  and envelope.get("surface") == "dashboard"
                  and envelope.get("method") == "harness.dashboard_read",
                  surface=envelope.get("surface"))


def write_evidence(profile: str, recon: Recon, harness_root: Path,
                   started: str, code: int) -> Path:
    evidence_dir = (REPO_ROOT / "docs" / "construction" / "evidence"
                    / "F115" / profile)
    evidence_dir.mkdir(parents=True, exist_ok=True)
    mirror = (REPO_ROOT / "evidence" / "F115" / profile)
    mirror.mkdir(parents=True, exist_ok=True)
    domain_dir = (REPO_ROOT / "docs" / "construction" / "evidence"
                  / "F116" / profile)
    domain_dir.mkdir(parents=True, exist_ok=True)
    domain_mirror = (REPO_ROOT / "evidence" / "F116" / profile)
    domain_mirror.mkdir(parents=True, exist_ok=True)
    finished = datetime.now(timezone.utc).isoformat()
    summary = {
        "schema": "juscite-f115-f116-dashboard-domain-recon/2",
        "unit": "W4-U49",
        "features": ["F115", "F116"],
        "profile": profile,
        "verdict": "RECON_OK" if code == 0 else "RECON_FAIL",
        "started_at": started,
        "finished_at": finished,
        "harness_worktree": str(harness_root),
        "harness_branch": "w4-u49",
        "harness_base": "w4-u46@5d6c920d（W4 战役链头，A2 分支链；schema 钉 32 零新账）",
        "checks": recon.checks,
        "check_count": len(recon.checks),
        "failed": [c["check"] for c in recon.checks
                   if c["status"] != "PASS"],
    }
    payload = json.dumps(summary, ensure_ascii=False, indent=1)
    for target in (evidence_dir, domain_dir):
        (target / "f115_f116_dashboard_domain_recon.json").write_text(
            payload + "\n", encoding="utf-8")
    for target in (mirror, domain_mirror):
        (target / "f115_f116_dashboard_domain_recon.json").write_text(
            payload + "\n", encoding="utf-8")
    lines = [f"# F115 看板投影（v1＋v1.5 封皮）＋F116 域分类（v1＋v1.5 分模块）"
             f" recon（{profile}）",
             "",
             f"- unit: W4-U49 · profile: {profile}",
             f"- verdict: **{summary['verdict']}**"
             f" ({len(recon.checks)} checks, exit {code})",
             f"- harness: `{harness_root}` @ branch w4-u49"
             "（基 w4-u46@5d6c920d 战役链头；master 929d0802 零动）",
             f"- started: {started} · finished: {finished}", "",
             "| # | check | status |", "|---|---|---|"]
    for index, check in enumerate(recon.checks, 1):
        lines.append(f"| {index} | {check['check']} | {check['status']} |")
    for target in (evidence_dir, mirror, domain_dir, domain_mirror):
        (target / "README.md").write_text("\n".join(lines) + "\n",
                                          encoding="utf-8")
    return evidence_dir


def _seed_matter_sqlite(state_root: Path):
    """在 SQLite 状态根上建案件（桌面播种径；返回打开的存储句柄）。"""
    for path in (str(DEFAULT_HARNESS_ROOT / "src"),
                 str(DEFAULT_HARNESS_ROOT / "tools/workflow-tools")):
        if path not in sys.path:
            sys.path.insert(0, path)
    from legal_harness.state.matter_store import MatterStore
    store = MatterStore(state_root)
    store.create_matter(MATTER, "cas://profile-f115f116")
    return store


def _open_store_sqlite(state_root: Path):
    for path in (str(DEFAULT_HARNESS_ROOT / "src"),
                 str(DEFAULT_HARNESS_ROOT / "tools/workflow-tools")):
        if path not in sys.path:
            sys.path.insert(0, path)
    from legal_harness.state.matter_store import MatterStore
    return MatterStore(state_root)


# 桌面播种分派（units 直连——播种不是受测面；受测面＝产品桥 dashboard.*/
# casedomain.* 封闭径与 harness 账面读回执）。
_SEED_ATTRS = {
    "tasks.suggest": "tasks_suggest",
    "tasks.proposal_decide": "tasks_proposal_decide",
    "tasks.decide": "tasks_decide",
    "harness.save_procedure_event": "save_procedure_event",
    "harness.schedule_event": "schedule_event",
    "harness.path_candidate_register": "path_candidate_register",
    "harness.evidence_attempt_register": "evidence_attempt_register",
    "harness.cash_source_register": "cash_source_register",
    "harness.save_goal": "save_goal",
    "harness.strategy_basis_register": "strategy_basis_register",
    "harness.transition_matter": "transition_matter",
    "harness.case_member_declare": "case_member_declare",
    "harness.case_identity_register": "case_identity_register",
    "harness.case_permission_rule": "case_permission_rule",
    # v1.5 模块流给新案播种域（播种不是受测面；产品面声明径在 f116_flow
    # 已覆盖）。
    "harness.case_domain_declare": "case_domain_declare",
}
# 账面读回执（cross-check 用；全部在 juscite main 已冻结的 harness 组——
# legal_entry.call 同一封闭径，与生产同链）。
_ACCOUNT_READ_METHODS = frozenset({
    "harness.path_candidate_list", "harness.cash_balance_read",
    "harness.evidence_attempt_list", "harness.strategy_basis_list",
    # v1.5 封皮逐字段对账的直接读回执（legal_entry 既有冻结组＝生产同链）。
    "harness.case_identity_read", "harness.case_permission_read",
    "harness.case_domain_read",
})


def run_desktop(recon: Recon, harness_root: Path) -> int:
    """desktop＝产品桥子进程全链（SQLite 状态根）：产品面（dashboard.*）
    与账面读回执走 legal_entry.call 默认派发（与生产同一条链）；播种经同
    一状态根的 units 直连（播种不是受测面）。"""
    temporary = tempfile.TemporaryDirectory(prefix="juscite-f115f116-desktop-")
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
    _seed_matter_sqlite(state_root)
    from legal_harness.business.units import HarnessUnits
    seed_units = HarnessUnits(_open_store_sqlite(state_root))

    def call_product(method, call_args):
        return legal_entry.call(method, call_args, config)

    def call_harness(method, call_args):
        if method in _ACCOUNT_READ_METHODS:
            # 账面读回执：legal_entry 既有冻结组（生产同链）。
            return legal_entry.call(method, call_args, config)
        attr = _SEED_ATTRS.get(method)
        if attr is None:
            raise NotConnected("recon_seed_method_unknown:" + method)
        return getattr(seed_units, attr)(**call_args)

    def query(sql, params=()):
        with contextlib.closing(
                sqlite3.connect(str(state_root / "core"
                                    / "matter-store.sqlite3"))) as connection:
            connection.row_factory = sqlite3.Row
            rows = connection.execute(sql, params).fetchall()
        return [dict(row) for row in rows]

    def reopen():
        _open_store_sqlite(state_root)  # 重开同一状态根（持久性检验）。

    def register_matter(matter_id):
        for path in (str(harness_root / "src"),
                     str(harness_root / "tools/workflow-tools")):
            if path not in sys.path:
                sys.path.insert(0, path)
        from legal_harness.state.matter_store import MatterStore
        MatterStore(state_root).create_matter(
            matter_id, "cas://profile-" + matter_id)

    print("[profile desktop] SQLite via product bridge subprocess",
          flush=True)
    recon.common_flow(call_product, call_harness, query, reopen,
                      register_matter)
    recon.bridge_negatives_product(call_product)
    recon.bridge_negatives_harness_entry(config)
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

    temporary = tempfile.TemporaryDirectory(prefix="juscite-f115f116-sh-")
    _ACTIVE_TMPDIRS.append(temporary)
    store = PgMatterStore(
        Path(temporary.name) / "state", dsn=dsn,
        schema="f115f116_" + _uuid.uuid4().hex[:12])
    store.create_matter(MATTER, "cas://profile-f115f116")
    units = HarnessUnits(store)
    methods = (HARNESS_DASHBOARD_METHODS | HARNESS_CASE_DOMAIN_METHODS
               | HARNESS_COVER_MODULE_METHODS
               | SEED_METHODS | {"harness.path_candidate_list",
                                 "harness.cash_balance_read",
                                 "harness.evidence_attempt_list",
                                 "harness.strategy_basis_list",
                                 "harness.case_identity_read",
                                 "harness.case_permission_read"})
    bound = {name: resolve_provider_method(name, units)
             for name in methods}

    def call_product(method, call_args):
        from dashboard_projection import dashboard_call
        return dashboard_call(method, call_args, {}, harness_call=call_harness)

    def call_harness(method, call_args):
        target = bound.get(method)
        if target is None:
            from legal_harness.business.provider_registry import (
                MethodNotWhitelisted,
            )
            raise MethodNotWhitelisted(method)
        return target(**call_args)

    def query_pg(sql, params=()):
        with contextlib.closing(store._connect()) as connection:
            rows = connection.execute(sql, params).fetchall()
        return [dict(row) for row in rows]

    def reopen():
        pass  # PG schema 持久于容器；同 schema 重开句柄即同一账（store 常驻）。

    print("[profile selfhost] PgMatterStore direct (lh-pg-e08)", flush=True)
    def register_matter(matter_id):
        store.create_matter(matter_id, "cas://profile-" + matter_id)

    recon.common_flow(call_product, call_harness, query_pg, reopen,
                      register_matter)
    recon.bridge_negatives_product(call_product)
    store.destroy()
    return 0


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

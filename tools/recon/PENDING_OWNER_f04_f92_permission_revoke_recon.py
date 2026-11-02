"""F04+F92 案件权限真隔离与撤权即时生效对账（W3-U07）——双 profile。

对账对象：harness 分支 w3-u07（基施工链头 w3-u06@605fe821＝w2b-u53→
w3-u03(F24/F26)→w3-u06(F113) 同链接力）的公开面——desktop profile 与产品
桥（legal_entry HARNESS_CASE_PERMISSION_METHODS → 子进程 public_entry
--caseperm-json 信封；F25 reviewbatch／F08 materials 信封同链）同一条链
（SQLite 状态根）；selfhost profile＝PgMatterStore 直连 lh-pg-e08
（resolve_provider_method 同一封闭注册）。desktop 例外如实记：run 事件账
（run_event_append/run_events_read，W3-U03 桥组）＋IFC-2 查询游标面
（query_case_objects，W3-U03 桥组）＋F92 行级权限授予
（review_row_grant，W2b-U40 桥组）三组桥方法在分支待账房并、main 桥面
（w3-u07 基点）尚未携带——该四方法 desktop 径经同一 SQLite 库
resolve_provider_method 直连公开面（与 selfhost 同一封闭注册），其余
全部走桥；check 名保持一致，直连面在 summary.direct_bridge_fallback
如实列出。
全部合成材料：临时状态根、合成成员/规则/veto/批/行/材料字节/run；harness
检出零字节改动（只运行其代码，git 只读命令核对分支）。

优先级语义权威＝juscite docs/construction/f9-permission-precedence.md
（T18 已 VERIFIED）：role→org→user 段序 findLast 末条胜出；org veto 只压
deny 永不放行；规则段 deny 短路 veto；受管案无匹配 fail-closed。撤权即时
生效＝逐操作同事务读账零缓存。合同 harness
docs/f04-f92-case-permission-contract.md。

实跑覆盖：
  C01 分支/基/master/工作树干净亲验 →
  C02 bootstrap＋受管投影（成员/规则/veto 三账经 --caseperm-json）→
  C03 优先级行为负测（F9 四问逐条：段序末条胜出/组织压角色/用户压组织/
      规则段 deny 短路 veto/veto 压 allow/SUPERSEDED 恢复/default/
      membership）→
  C04 真隔离（他 org 未授予者四类面全拒：读/写/事件流/导出）→
  C05 撤权即时生效（同会话四类面：读写/缓存游标/事件流/导出→撤→拒→
      复授→通）→
  C06 缓存面（游标只定位不携权：翻页/续读撤权后同拒）→
  C07 F92 review 可见≠文档读权（行级 read 可见而 read_material 拒；
      export 授/撤行为线）→
  C08 F92 生成/重跑写权逐行＋案件门在前（行有写权案被撤写→案件码）→
  C09 manage 门（武装后自助提权具名拒；bootstrap 窗不死锁）→
  C10 同会话双测一致（F9 验证协议账本同构）→
  C11 DB 级扫描（三账行数）→
  C12 桥负向（未配置 NOT_CONNECTED／未知方法 method_not_connected／
      方法组冻结）。

用法：
  python -X utf8 tools/PENDING_OWNER_f04_f92_permission_revoke_recon.py \
      --profile desktop --profile selfhost

退出码：0 = 全部 profile RECON_OK；2 = RECON_FAIL；3 = 环境缺失。
证据：evidence/F04/<profile>/ 与 evidence/F92/<profile>/（同一 recon 双
落，F04/F92 各持一份）＋docs/construction/evidence/ 镜像。
"""
from __future__ import annotations

import argparse
import contextlib
import json
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

DEFAULT_HARNESS_ROOT = Path(
    r"D:\Codex\1.法律工作区\legal-harness工作区\legal-harness-repo"
    r"\.local\worktrees\w3-u07")

MATTER = "m-f04f92-recon"
SCOPE = {"kind": "matter", "matterId": MATTER}
OTHER_SCOPE = {"kind": "matter", "matterId": "m-f04f92-other"}
BATCH = "brt-recon"
RUN = "run-recon"
DOC_MARKER = "F04F92-SYNTH-DOC-BYTES-MARKER-不外泄"
ADMIN = "recon-admin"
WORKER = "recon-worker"
OUTSIDER = "recon-outsider"
ADMIN_ORG = "org-recon-a"
OUTSIDER_ORG = "org-recon-b"
ALL_ACTIONS = ("read", "write", "events", "export", "manage")

# lh-pg-e08 容器（E08 拓扑）：仅回环端口、合成专用凭据（密钥只在本机容
# 器；可用 LH_E08_PG_DSN 覆写）。
DEFAULT_PG_DSN = "postgresql://lh_app:e08-synth-only@127.0.0.1:55432/legal_harness"

CASEPERM_METHODS = frozenset({
    "harness.case_member_declare", "harness.case_permission_rule",
    "harness.case_permission_veto", "harness.case_permission_read",
})

# 桥组待账房并——desktop 径直连的公开面（同一封闭注册，如实记）：
# F24 run 事件账＋IFC-2 查询（W3-U03）＋F92 行级权限（W2b-U40）。
DIRECT_FALLBACK_NAMES = frozenset({
    "harness.run_event_append", "harness.run_events_read",
    "harness.query_case_objects", "harness.review_row_grant",
})


_KEY_SEQ = {"n": 0}


def key(request_id: str) -> dict:
    """CommandKey：requestId 自动追加流水号——同一探针多次调用不得复用
    id（F25 command_tx 同键同内容幂等重放会把撤销前的成功缓存回来，
    探针必须每次新 id 才测到真实求值）。"""
    _KEY_SEQ["n"] += 1
    return {"requestId": "%s-%d" % (request_id, _KEY_SEQ["n"]),
            "targetId": None, "expectedRevision": None, "inputRefs": []}


def member(user: str, org: str, roles: list) -> dict:
    return {"userId": user, "orgId": org, "roles": roles}


def rule(kind: str, principal: str, action: str, effect: str) -> dict:
    return {"principalKind": kind, "principalId": principal,
            "action": action, "effect": effect}


def veto_entry(org: str, action: str, status: str) -> dict:
    return {"orgId": org, "action": action, "status": status}


def synth_batch(batch_id: str = BATCH, rows: int = 3) -> dict:
    return {
        "id": batch_id, "title": "F04/F92 对账（合成）",
        "columns": [{"id": "amount", "name": "合同金额"}],
        "rows": [
            {"id": "row-%d" % i, "cells": {"amount": None},
             "sourceRef": "mat-recon-doc-%d" % i}
            for i in range(1, rows + 1)
        ],
    }


def expect_bridge_error(call, code_part):
    try:
        call()
    except (HarnessCommandError, ValueError) as exc:
        return code_part in str(exc), str(exc)
    return False, "no typed error raised"


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
                     error=(HarnessCommandError, ValueError)):
        ok, code = expect_bridge_error(call, code_part)
        self.step(name, ok, code=code[:160])
        return code

    def git(self, root: Path, *args: str) -> str:
        return subprocess.check_output(
            ["git", "-C", str(root), *args], text=True).strip()

    def branch_checks(self):
        branch = self.git(self.harness_root, "rev-parse", "--abbrev-ref",
                          "HEAD")
        base = self.git(self.harness_root, "merge-base", "HEAD", "w3-u06")
        master = self.git(self.harness_root, "rev-parse", "master")
        self.step("c01_harness_branch", branch == "w3-u07", branch=branch)
        self.step("c01_harness_base_on_w3_u06", base.startswith("605fe821"),
                  base=base)
        self.step("c01_harness_master_untouched", master.startswith("929d0802"),
                  master=master)
        dirty = self.git(self.harness_root, "status", "--porcelain")
        self.step("c01_harness_worktree_clean", dirty == "", dirty=dirty[:200])

    # ------------------------------------------------------------------
    # C02–C11：call(method, args) 走被测链；query/exec 直读同一库。
    # ------------------------------------------------------------------
    def common_flow(self, profile: str, call, query, execute):
        # ---- C02 bootstrap＋受管投影：三账全经 --caseperm-json 信封。
        declared = call("harness.case_member_declare", {
            "actor_id": ADMIN, "scope": SCOPE, "key": key("mb-boot"),
            "members": [member(ADMIN, ADMIN_ORG, ["case-admin"]),
                        member(WORKER, ADMIN_ORG, ["paralegal"]),
                        member(OUTSIDER, OUTSIDER_ORG, ["paralegal"])]})
        rules = call("harness.case_permission_rule", {
            "actor_id": ADMIN, "scope": SCOPE, "key": key("rl-boot"),
            "rules": [rule("user", ADMIN, action, "allow")
                      for action in ALL_ACTIONS]
                     + [rule("user", WORKER, action, "allow")
                        for action in ("read", "write", "events", "export")]})
        self.step("c02_bootstrap_declared_and_armed",
                  declared["declaredCount"] == 3
                  and rules["ruleCount"] == 9,
                  declared=declared["declaredCount"],
                  rules=rules["ruleCount"])
        projection = call("harness.case_permission_read",
                          {"scope": SCOPE, "actor_id": WORKER})
        self.step("c02_managed_projection_actor_view",
                  projection["managed"] is True
                  and projection["accounting"] == "per_principal_action"
                  and projection["actorView"]["read"]["allowed"] is True
                  and projection["actorView"]["read"]["segment"] == "rule",
                  managed=projection["managed"])
        members = {m["userId"]: m for m in projection["members"]}
        self.step("c02_membership_latest_wins_shape",
                  members[WORKER]["orgId"] == ADMIN_ORG
                  and members[WORKER]["roles"] == ["paralegal"],
                  worker=members.get(WORKER))

        # ---- C03 优先级行为负测（F9 四问账本落点）。
        # ③a role deny + user allow → user 段末条胜出（allow）。
        call("harness.case_permission_rule", {
            "actor_id": ADMIN, "scope": SCOPE, "key": key("rl-p1"),
            "rules": [rule("role", "paralegal", "events", "deny")]})
        # ③b veto（组织硬拒）压 allow；SUPERSEDED 后恢复。
        call("harness.case_permission_veto", {
            "actor_id": ADMIN, "scope": SCOPE, "key": key("vt-p1"),
            "vetoes": [veto_entry(OUTSIDER_ORG, "read", "ACTIVE")]})
        view = call("harness.case_permission_read",
                    {"scope": SCOPE, "actor_id": OUTSIDER})
        self.step("c03_veto_presses_allow_only",
                  view["actorView"]["read"]["allowed"] is False
                  and view["actorView"]["read"]["segment"] == "veto",
                  segment=view["actorView"]["read"]["segment"])
        call("harness.case_permission_veto", {
            "actor_id": ADMIN, "scope": SCOPE, "key": key("vt-p2"),
            "vetoes": [veto_entry(OUTSIDER_ORG, "read", "SUPERSEDED")]})
        view = call("harness.case_permission_read",
                    {"scope": SCOPE, "actor_id": OUTSIDER})
        # veto 撤后无规则 → default（veto 撤除不放行，回到 fail-closed 默认）。
        self.step("c03_veto_lifted_back_to_default",
                  view["actorView"]["read"]["allowed"] is False
                  and view["actorView"]["read"]["segment"] == "default",
                  segment=view["actorView"]["read"]["segment"])
        # ③c worker 加 role deny 后仍 allow（user 段压过 role 段）。
        view = call("harness.case_permission_read",
                    {"scope": SCOPE, "actor_id": WORKER})
        self.step("c03_user_segment_presses_role_deny",
                  view["actorView"]["events"]["allowed"] is True
                  and view["actorView"]["events"]["segment"] == "rule",
                  segment=view["actorView"]["events"]["segment"])

        # ---- 建批/run/材料（受管案由 admin 播种）。
        call("harness.review_batch_create", {
            "actor_id": ADMIN, "scope": SCOPE, "key": key("rb-1"),
            "batch": synth_batch()})
        import base64
        doc = ("合成材料文档：%s；余额 123456.78 元。"
               % DOC_MARKER).encode("utf-8")
        call("harness.register_material", {
            "actor_id": ADMIN, "scope": SCOPE, "key": key("mat-1"),
            "material": {"id": "mat-recon-doc-1", "kind": "digital_text",
                         "title": "合成合同（F04F92 对账）",
                         "bytesB64": base64.b64encode(doc).decode("ascii"),
                         "matterId": MATTER}})
        execute(
            "INSERT INTO runs(run_id,matter_id,task_id,parent_run_id,"
            "work_mode,output_type,interaction_mode,document_contract_ref,"
            "graph_hash,recovery_fingerprint,phase,status,deadline_at,"
            "reserve_minutes,request_hash,request_json,created_at,updated_at)"
            " VALUES(?,?,?,?,?,?,?,?,?,?,'RESEARCH','CREATED',?,?,?,?,?,?)",
            (RUN, MATTER, "task-recon", None, "business", "decision_brief",
             "RUN_TO_COMPLETE", None, "graph-synth", "fp-" + RUN, None, None,
             "req-hash-synth", "{}", "2026-10-18T00:00:00Z",
             "2026-10-18T00:00:00Z"))
        execute(
            "INSERT INTO graph_revisions(run_id,revision,graph_hash,"
            "nodes_json,task_plan_decision_ref,created_at)"
            " VALUES(?,1,?,?,?,?)",
            (RUN, "graph-synth", "[]", "synthetic-seed",
             "2026-10-18T00:00:00Z"))
        call("harness.run_event_append", {
            "actor_id": WORKER, "scope": SCOPE, "key": key("ev-seed"),
            "event": {"runId": RUN, "eventKey": "ek-seed",
                      "eventCode": "run.progress",
                      "payload": {"note": "对账种子事件"},
                      "expectedHeadSeq": None,
                      "terminalReceiptRef": None}})

        # ---- C04 真隔离：他 org 未授予者四类面全拒。
        for action, method, args in (
            ("read", "harness.review_batch_read",
             {"scope": SCOPE, "batch_id": BATCH, "actor_id": OUTSIDER}),
            ("write", "harness.review_batch_claim",
             {"actor_id": OUTSIDER, "scope": SCOPE, "key": key("cl-o"),
              "batch_id": BATCH, "row_id": "row-1"}),
            ("events", "harness.run_events_read",
             {"scope": SCOPE, "run_id": RUN, "actor_id": OUTSIDER}),
            ("export", "harness.read_material",
             {"scope": SCOPE, "material_id": "mat-recon-doc-1",
              "actor_id": OUTSIDER}),
        ):
            def _deny(method=method, args=args, action=action):
                self.expect_error(
                    "c04_outsider_%s_denied" % action,
                    lambda: call(method, args),
                    "case_permission_denied:%s:" % action)
            _deny()

        # ---- C05 撤权即时生效（同会话四类面，不重连）。
        worker_ok = {
            "read": lambda: call("harness.review_batch_read",
                                 {"scope": SCOPE, "batch_id": BATCH,
                                  "actor_id": WORKER}),
            "write": lambda: call("harness.review_batch_claim",
                                  {"actor_id": WORKER, "scope": SCOPE,
                                   "key": key("cl-w"), "batch_id": BATCH,
                                   "row_id": "row-1"}),
            "events": lambda: call("harness.run_events_read",
                                   {"scope": SCOPE, "run_id": RUN,
                                    "actor_id": WORKER}),
            "export": lambda: call("harness.read_material",
                                   {"scope": SCOPE,
                                    "material_id": "mat-recon-doc-1",
                                    "actor_id": WORKER}),
        }
        for action, probe in worker_ok.items():
            probe()  # 撤权前全通（双测一致的前半）。
        call("harness.case_permission_rule", {
            "actor_id": ADMIN, "scope": SCOPE, "key": key("rl-revoke"),
            "rules": [rule("user", WORKER, action, "deny")
                      for action in ("read", "write", "events", "export")]})
        for action, probe in worker_ok.items():
            self.expect_error(
                "c05_revoke_immediate_%s" % action, probe,
                "case_permission_denied:%s:rule" % action)
        call("harness.case_permission_rule", {
            "actor_id": ADMIN, "scope": SCOPE, "key": key("rl-restore"),
            "rules": [rule("user", WORKER, action, "allow")
                      for action in ("read", "write", "events", "export")]})
        # 复授即通（同一会话/同一桥径）：read/events/export 无状态直接复
        # 测；write 的复测＝claim 会撞 row-1 在飞租约（F25 contended 语义
        # 不动它），其恢复证明由 C08 claim row-2 成功兑现。
        for action in ("read", "events", "export"):
            worker_ok[action]()
        self.step("c05_regrant_restores", True, restored=3,
                  write_restore_proven_at="c08")

        # ---- C06 缓存面：游标只定位不携权。
        page = call("harness.query_case_objects",
                    {"scope": SCOPE, "issue_id": None, "cursor": None,
                     "actor_id": WORKER})
        cursor = page.get("nextCursor")
        stream = call("harness.run_events_read",
                      {"scope": SCOPE, "run_id": RUN, "actor_id": WORKER})
        seq_cursor = stream["nextCursor"]
        call("harness.case_permission_rule", {
            "actor_id": ADMIN, "scope": SCOPE, "key": key("rl-revoke2"),
            "rules": [rule("user", WORKER, "read", "deny"),
                      rule("user", WORKER, "events", "deny")]})
        self.expect_error(
            "c06_cursor_cache_denied_after_revoke",
            lambda: call("harness.query_case_objects",
                         {"scope": SCOPE, "issue_id": None,
                          "cursor": cursor, "actor_id": WORKER}),
            "case_permission_denied:read:rule")
        self.expect_error(
            "c06_event_cursor_denied_after_revoke",
            lambda: call("harness.run_events_read",
                         {"scope": SCOPE, "run_id": RUN,
                          "after_seq": seq_cursor or 0,
                          "actor_id": WORKER}),
            "case_permission_denied:events:rule")
        call("harness.case_permission_rule", {
            "actor_id": ADMIN, "scope": SCOPE, "key": key("rl-restore2"),
            "rules": [rule("user", WORKER, "read", "allow"),
                      rule("user", WORKER, "events", "allow")]})

        # ---- C07 F92：review 可见不自动得文档读权。
        call("harness.review_row_grant", {
            "actor_id": ADMIN, "scope": SCOPE, "key": key("rg-1"),
            "batch_id": BATCH,
            "entries": [{"actorId": WORKER, "rowId": "row-1",
                         "level": "read"}]})
        view = call("harness.review_batch_read",
                    {"scope": SCOPE, "batch_id": BATCH,
                     "actor_id": WORKER})
        flat = json.dumps(view, ensure_ascii=False)
        self.step("c07_review_visible_row_filtered",
                  view["permissionFiltered"] is True
                  and [row["id"] for row in view["rows"]] == ["row-1"]
                  and DOC_MARKER not in flat
                  and "bytesB64" not in flat,
                  rows=[row["id"] for row in view["rows"]])
        call("harness.case_permission_rule", {
            "actor_id": ADMIN, "scope": SCOPE, "key": key("rl-revoke3"),
            "rules": [rule("user", WORKER, "export", "deny")]})
        self.expect_error(
            "c07_visible_but_document_read_denied",
            lambda: call("harness.read_material",
                         {"scope": SCOPE,
                          "material_id": "mat-recon-doc-1",
                          "actor_id": WORKER}),
            "case_permission_denied:export:rule")
        call("harness.case_permission_rule", {
            "actor_id": ADMIN, "scope": SCOPE, "key": key("rl-exportok"),
            "rules": [rule("user", WORKER, "export", "allow")]})
        read = call("harness.read_material",
                    {"scope": SCOPE, "material_id": "mat-recon-doc-1",
                     "actor_id": WORKER})
        self.step("c07_export_grant_opens_document_read",
                  DOC_MARKER in base64.b64decode(
                      read["bytesB64"]).decode("utf-8"),
                  material="mat-recon-doc-1")

        # ---- C08 F92：生成/重跑写权逐行＋案件门在前（row-2 新租约——
        # row-1 在 C05 已持有效租约，contended 语义不动它）。
        call("harness.review_row_grant", {
            "actor_id": ADMIN, "scope": SCOPE, "key": key("rg-2"),
            "batch_id": BATCH,
            "entries": [{"actorId": WORKER, "rowId": "row-2",
                         "level": "write"}]})
        claim = call("harness.review_batch_claim",
                     {"actor_id": WORKER, "scope": SCOPE,
                      "key": key("cl-w2"), "batch_id": BATCH,
                      "row_id": "row-2"})
        token = claim["lease"]["token"]
        self.step("c08_row_write_within_case_write",
                  claim["rowId"] == "row-2", rowId=claim["rowId"])
        self.expect_error(
            "c08_row_granularity_row3_denied",
            lambda: call("harness.review_batch_claim",
                         {"actor_id": WORKER, "scope": SCOPE,
                          "key": key("cl-w3"), "batch_id": BATCH,
                          "row_id": "row-3"}),
            "row_permission_denied:row-3:write")
        call("harness.case_permission_rule", {
            "actor_id": ADMIN, "scope": SCOPE, "key": key("rl-revoke4"),
            "rules": [rule("user", WORKER, "write", "deny")]})
        # 行有写权而案被撤写：案件门在前→案件码（非行码）；同 token（撤
        # 销前签发的有效租约）同会话即拒＝撤权立即生效（生成/重跑面）。
        code = self.expect_error(
            "c08_case_gate_before_row_gate",
            lambda: call("harness.review_batch_submit",
                         {"actor_id": WORKER, "scope": SCOPE,
                          "key": key("sb-x"), "batch_id": BATCH,
                          "row_id": "row-2", "lease_token": token,
                          "cells": [{"cellId": "amount", "value": "1 元",
                                     "generation": 0}]}),
            "case_permission_denied:write:rule")
        self.step("c08_case_code_not_row_code",
                  "row_permission_denied" not in code, code=code[:120])
        self.expect_error(
            "c08_rerun_denied_after_case_revoke",
            lambda: call("harness.review_cell_rerun",
                         {"actor_id": WORKER, "scope": SCOPE,
                          "key": key("rr-x"), "batch_id": BATCH,
                          "row_id": "row-2", "cell_id": "amount",
                          "lease_token": token, "value": "重跑",
                          "generation": 0}),
            "case_permission_denied:write:rule")
        call("harness.case_permission_rule", {
            "actor_id": ADMIN, "scope": SCOPE, "key": key("rl-restore4"),
            "rules": [rule("user", WORKER, "write", "allow")]})

        # ---- C09 manage 门：武装后自助提权具名拒。
        self.expect_error(
            "c09_self_elevation_refused",
            lambda: call("harness.case_permission_rule", {
                "actor_id": WORKER, "scope": SCOPE, "key": key("rl-self"),
                "rules": [rule("user", WORKER, "manage", "allow")]}),
            "case_permission_denied:manage:")
        self.expect_error(
            "c09_outsider_membership_first",
            lambda: call("harness.review_batch_read",
                         {"scope": SCOPE, "batch_id": BATCH,
                          "actor_id": "recon-ghost"}),
            "case_permission_denied:read:membership")

        # ---- C10 同会话双测一致（F9 验证协议账本同构）。
        first = call("harness.case_permission_read",
                     {"scope": SCOPE, "actor_id": WORKER})
        second = call("harness.case_permission_read",
                      {"scope": SCOPE, "actor_id": WORKER})
        self.step("c10_double_read_consistent",
                  first["actorView"] == second["actorView"]
                  and first["members"] == second["members"],
                  actions=sorted(first["actorView"]))

        # ---- C11 DB 级扫描：三账行数。
        counts = {}
        for table in ("case_members", "case_permission_rules",
                      "case_permission_vetoes"):
            counts[table] = query(
                "SELECT COUNT(*) AS n FROM %s WHERE matter_id=?" % table,
                (MATTER,))[0]["n"]
        self.step("c11_db_three_ledgers",
                  counts["case_members"] == 3
                  and counts["case_permission_rules"] >= 20
                  and counts["case_permission_vetoes"] == 2,
                  counts=counts)

    def bridge_negatives(self, config):
        # ---- C12 桥负向：未配置/未知方法/方法组冻结。
        try:
            legal_entry.call("harness.case_permission_read",
                             {"scope": SCOPE}, {})
            raise AssertionError("bridge_not_configured_expected")
        except NotConnected as exc:
            self.step("c12_bridge_not_configured",
                      "harness_public_entry_not_configured" in str(exc))
        try:
            legal_entry.call("harness.case_permission_set",
                             {"scope": SCOPE}, config)
            raise AssertionError("bridge_unknown_method_expected")
        except NotConnected as exc:
            self.step("c12_bridge_unknown_method_refused",
                      "method_not_connected" in str(exc))
        self.step("c12_method_group_frozen",
                  legal_entry.HARNESS_CASE_PERMISSION_METHODS
                  == CASEPERM_METHODS)

    # -- profile drivers ---------------------------------------------------

    def run_desktop(self) -> int:
        temporary = tempfile.TemporaryDirectory(
            prefix="juscite-f04f92-desktop-")
        state_root = Path(temporary.name) / "state"
        state_root.mkdir(parents=True)
        registration = Path(temporary.name) / "service-local.json"
        registration.write_text(json.dumps(
            {"url": "http://127.0.0.1:1", "password": "synthetic-recon"}),
            encoding="utf-8")
        config = {
            "harness_public_entry":
                str(self.harness_root
                    / "tools/workflow-tools/harness/public_entry.py"),
            "harness_target": "opencode",
            "harness_state_root": str(state_root),
            "harness_service_registration": str(registration),
            "harness_timeout": 120,
        }
        for path in (str(self.harness_root / "src"),
                     str(self.harness_root / "tools/workflow-tools")):
            if path not in sys.path:
                sys.path.insert(0, path)
        from legal_harness.business.provider_registry import (
            resolve_provider_method,
        )
        from legal_harness.business.units import HarnessUnits
        from legal_harness.state.matter_store import MatterStore
        store = MatterStore(state_root)
        units = HarnessUnits(store)
        store.create_matter(MATTER, "cas://profile-f04f92-recon")
        store.create_matter("m-f04f92-other", "cas://profile-other")

        # 待账房并桥方法组（F24 run 账/IFC-2 查询＝W3-U03；F92 行级权限
        # ＝W2b-U40）：该四方法 desktop 径直连同库公开面（同一封闭注册），
        # 如实记 fallback。
        direct_fallback = {}
        for name in sorted(DIRECT_FALLBACK_NAMES):
            direct_fallback[name] = resolve_provider_method(name, units)
        self.direct_fallback = direct_fallback

        def call(method, args):
            if method in direct_fallback:
                return direct_fallback[method](**args)
            return legal_entry.call(method, args, config)

        def query(sql, params):
            import sqlite3
            with contextlib.closing(store._connect()) as connection:
                connection.row_factory = sqlite3.Row
                rows = connection.execute(sql, params).fetchall()
            return [dict(row) for row in rows]

        def execute(sql, params):
            with store.transaction() as connection:
                connection.execute(sql, params)

        print("[profile desktop] SQLite via product bridge subprocess",
              flush=True)
        self.common_flow("desktop", call, query, execute)
        self.bridge_negatives(config)
        return 0

    def run_selfhost(self, dsn: str) -> int:
        for path in (str(self.harness_root / "src"),
                     str(self.harness_root / "tools/workflow-tools"),
                     str(self.harness_root)):
            if path not in sys.path:
                sys.path.insert(0, path)
        from legal_harness.business.provider_registry import (
            resolve_provider_method,
        )
        from legal_harness.business.units import HarnessUnits
        from legal_harness.state.pg_store import PgMatterStore

        temporary = tempfile.TemporaryDirectory(
            prefix="juscite-f04f92-selfhost-")
        store = PgMatterStore(
            Path(temporary.name) / "state", dsn=dsn,
            schema="f04f92_" + _uuid.uuid4().hex[:12])
        units = HarnessUnits(store)
        methods = set(CASEPERM_METHODS) | {
            "harness.review_batch_create", "harness.review_batch_claim",
            "harness.review_batch_submit", "harness.review_cell_rerun",
            "harness.review_batch_read", "harness.review_row_grant",
            "harness.register_material", "harness.read_material",
            "harness.run_event_append", "harness.run_events_read",
            "harness.query_case_objects",
        }
        bound = {name: resolve_provider_method(name, units)
                 for name in methods}
        store.create_matter(MATTER, "cas://profile-f04f92-recon")
        store.create_matter("m-f04f92-other", "cas://profile-other")

        def call(method, args):
            return bound[method](**args)

        def query(sql, params):
            with contextlib.closing(store._connect()) as connection:
                rows = connection.execute(sql, params).fetchall()
            return [dict(row) for row in rows]

        def execute(sql, params):
            with store.transaction() as connection:
                connection.execute(sql, params)

        print("[profile selfhost] PgMatterStore direct (lh-pg-e08)",
              flush=True)
        try:
            self.common_flow("selfhost", call, query, execute)
        finally:
            store.destroy()
        return 0


def write_evidence(profile: str, recon: Recon, harness_root: Path,
                   started: str, code: int) -> list[Path]:
    finished = datetime.now(timezone.utc).isoformat()
    summary = {
        "schema": "juscite-f04f92-permission-revoke-recon/1",
        "unit": "W3-U07",
        "features": ["F04", "F92"],
        "profile": profile,
        "verdict": "RECON_OK" if code == 0 else "RECON_FAIL",
        "started_at": started,
        "finished_at": finished,
        "harness_worktree": str(harness_root),
        "harness_branch": "w3-u07",
        "harness_base": "w3-u06@605fe821 (w2b-u53→w3-u03/F24F26→"
                        "w3-u06/F113 同链接力)",
        "precedence_authority":
            "docs/construction/f9-permission-precedence.md (T18 VERIFIED)",
        "checks": recon.checks,
        "check_count": len(recon.checks),
        "failed": [c["check"] for c in recon.checks
                   if c["status"] != "PASS"],
    }
    summary["direct_bridge_fallback"] = sorted(DIRECT_FALLBACK_NAMES)         if profile == "desktop" else []
    payload = json.dumps(summary, ensure_ascii=False, indent=1)
    written: list[Path] = []
    for feature in ("F04", "F92"):
        for base in (REPO_ROOT / "evidence" / feature / profile,
                     REPO_ROOT / "docs" / "construction" / "evidence"
                     / feature / profile):
            base.mkdir(parents=True, exist_ok=True)
            path = base / "f04_f92_permission_revoke_recon.json"
            path.write_text(payload + "\n", encoding="utf-8")
            lines = [
                "# F04/F92 案件权限撤权对账（%s·%s）" % (feature, profile),
                "",
                f"- unit: W3-U07 · profile: {profile} · feature: {feature}",
                f"- verdict: **{summary['verdict']}**"
                f" ({len(recon.checks)} checks, exit {code})",
                f"- harness: `{harness_root}` @ branch w3-u07"
                "（基 w3-u06@605fe821；master 929d0802 零动）",
                f"- started: {started} · finished: {finished}",
                "",
                "| # | check | status |",
                "|---|---|---|",
            ]
            for index, check in enumerate(recon.checks, 1):
                lines.append(f"| {index} | {check['check']}"
                             f" | {check['status']} |")
            (base / "f04_f92_permission_revoke_recon.md").write_text(
                "\n".join(lines) + "\n", encoding="utf-8")
            written.append(path)
    return written


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--profile", action="append",
                        choices=["desktop", "selfhost"])
    parser.add_argument("--harness-root", type=Path,
                        default=DEFAULT_HARNESS_ROOT)
    parser.add_argument("--pg-dsn", default=DEFAULT_PG_DSN)
    args = parser.parse_args()
    profiles = args.profile or ["desktop"]
    if not (args.harness_root
            / "tools/workflow-tools/harness/public_entry.py").exists():
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
                # C01 分支/基/master/工作树干净亲验（只跑一次，两 profile
                # 共用同一 harness 检出）。
                recon.branch_checks()
            if profile == "desktop":
                code = recon.run_desktop()
            else:
                code = recon.run_selfhost(args.pg_dsn)
        except Exception as error:  # noqa: BLE001 - reported per profile
            print(f"RECON_FAIL[{profile}]: {error}", flush=True)
            recon.checks.append({"check": "recon_driver", "status": "FAIL",
                                 "error": str(error)[:400]})
            code = 2
        written = write_evidence(profile, recon, args.harness_root,
                                 started, code)
        verdict = "RECON_OK" if code == 0 else "RECON_FAIL"
        print(f"[{profile}] {verdict} ({len(recon.checks)} checks,"
              f" exit {code}) evidence={written[0]}", flush=True)
        if code != 0:
            failures += 1
        first = False
    return 0 if failures == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())

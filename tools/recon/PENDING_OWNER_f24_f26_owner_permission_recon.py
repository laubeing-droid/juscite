"""F24+F26 owner 唯一与工具权限后端强制对账（W3-U03）.

义务（06 F24/F26 acceptance；17 卡落点 Harness ApplicationService/units＋
产品 UI）：

* F24 所选核心 Session 与 Harness 业务 run/goal 各唯一 owner——core
  session 账主=core（服务端账本；e07_live_recon 同键重放 HTTP 409 语义
  活服务复测：同 id 异内容重放幂等返回原入队项、id 撞已投递行=HTTP 409）；
  业务 run 账主=harness（durable run 事件账：幂等键+事件溯源+乐观锁+SSE
  cursor）；goal 账主=harness（T16 case_goals 唯一权威，本 recon 消费其
  save/decide/adopt/read_goal_basis 面）；Host 只有投影/游标/批准恢复
  元数据（run_cursor_store f24-runhost/1：goal 内容键与业务终局键任何
  层级禁入、游标单调、批准幂等、AST 无终局写入 API），不另造业务终局
  （run.terminal 必须钉 owner 链 terminal_results 回执，无链具名拒）；
* F26 未广告/未授权工具不能调用、读写区/执行档位/黑白名单后端强制
  ——harness 工具治理账（读写分区双闸/执行档位/白名单+skill 黑名单，
  denyByDefault literal True＝T07 legal-review 尾置 deny 同款纪律）+
  deny-closed 判定面；活服务权限 oracle 负测矩阵（复用
  tools/e02_tool_closure.py A 组负测形状：直接求值端点
  POST /api/session/:sid/permission 不需要模型轮次）；T07 legal-review
  产品配置面（%APPDATA%\\Juscite 只读快照）与治理合同符合性核对。

profile 语义（E16/E20 recon 同径）：
  desktop ＝产品桥同一链：legal_entry.call → 子进程 public_entry
            （--runledger-json/--toolgov-json 信封；临时 SQLite 状态根）；
  selfhost＝PgMatterStore 直连 lh-pg-e08（每跑独立 schema，跑毕 destroy）；
  活服务段（oc28 serve 临时 XDG 四根，零模型依赖）单跑一次，证据双
  profile 同文。

红线：材料全合成；harness/oc28 检出 git 只读；%APPDATA%\\Juscite 只读
（前后快照比对＝零写入）；绝不触 %APPDATA%\\JusBench；服务密码不打印
不入 git（临时根随跑随删）；不 push。

用法：
  python -X utf8 tools/recon/PENDING_OWNER_f24_f26_owner_permission_recon.py
      [--profile desktop] [--profile selfhost]（默认双 profile）
      [--harness-root <path>] [--pg-dsn <dsn>] [--keep]

退出码：0 = RECON_OK（全 profile＋live 全 PASS）；2 = RECON_FAIL；
3 = RECON_BLOCKED（bun/oc28/harness 分支缺失等机械边界）。
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "implementation" / "python"))

import legal_entry  # noqa: E402
from bridge_errors import SessionRejected  # noqa: E402
from e07_coordinator import create_public_session  # noqa: E402
from legal_entry import HarnessCommandError  # noqa: E402
from opencode_http import Client, TransportError  # noqa: E402
from run_cursor_store import RunCursorStore, RunCursorStoreError  # noqa: E402

DEFAULT_HARNESS_ROOT = Path(
    r"D:\Codex\1.法律工作区\legal-harness工作区\legal-harness-repo"
    r"\.local\worktrees\w3-u03")
DEFAULT_OC28 = Path(r"D:\Codex\1.法律工作区\jusbench工作区\oc28")
DEFAULT_BUN = Path.home() / ".bun" / "bun.exe"
DEFAULT_PG_DSN = "postgresql://lh_app:e08-synth-only@127.0.0.1:55432/legal_harness"
EXPECT_BRANCH = "w3-u03"

DEV_VERSION = "2.0.0-local-f24f26"
EVIDENCE_ROOT = REPO_ROOT / "docs" / "construction" / "evidence"

MATTER = "m-f24f26"
SCOPE = {"kind": "matter", "matterId": MATTER}
RUN_ID = "run-f24f26-recon-1"

GOAL_CONTENT_KEYS = ("confirmedScope", "hardConstraints", "preferences",
                     "unitTiming", "sourceDecisionRef")
TERMINAL_KEYS = ("terminal", "terminalResult", "resultHash",
                 "finalVerdict", "businessOutcome")

GOAL_PAYLOAD = {
    "schemaVersion": "1.0.0-draft", "matterId": MATTER,
    "goalId": "g-f24f26", "revision": 1,
    "confirmedScope": "追回合成货款 80000 元（全合成对账材料）",
    "hardConstraints": [
        {"id": "hc-1", "kind": "min_recovery", "value": "80000",
         "description": "最低实收（合成）"}],
    "preferences": [],
    "unitTiming": {"unit": "CNY", "asOf": "2026-10-18"},
    "sourceDecisionRef": None, "supersedesRevision": None,
}

GOVERNANCE_V1 = {
    "governanceId": "gov-legal-review", "revision": 1,
    "profile": "legal-review",
    "readZones": ["materials/**", "work/**"],
    "writeZones": ["work/**"],
    "executionTier": "NONE",
    "allowedTools": ["read", "glob", "grep", "question", "edit", "skill",
                     "execute"],
    "skillBlacklist": ["skill-exfil", "skill-unknown-pack"],
    "denyByDefault": True,
}

RUN_EVENT_SQL = (
    "INSERT INTO runs(run_id,matter_id,task_id,parent_run_id,work_mode,"
    "output_type,interaction_mode,document_contract_ref,graph_hash,"
    "recovery_fingerprint,phase,status,deadline_at,reserve_minutes,"
    "request_hash,request_json,created_at,updated_at)"
    " VALUES(?,?,?,?,?,?,?,?,?,?,'RESEARCH','CREATED',?,?,?,?,?,?)")
RUN_EVENT_SQL_PARAMS = (
    RUN_ID, MATTER, "task-f24f26", None, "business", "decision_brief",
    "RUN_TO_COMPLETE", None, "graph-synth-f24f26", "fp-f24f26", None, None,
    "req-hash-synth", "{}", "2026-10-18T00:00:00Z", "2026-10-18T00:00:00Z")
# Store 不变式：runs 行必须有对应 graph_revisions 行（_initialize 完整性
# 门），合成 run 种子两行一并落。
GRAPH_REVISION_SQL = (
    "INSERT INTO graph_revisions(run_id,revision,graph_hash,nodes_json,"
    "task_plan_decision_ref,created_at) VALUES(?,1,?,?,?,?)")
GRAPH_REVISION_SQL_PARAMS = (
    RUN_ID, "graph-synth-f24f26", "[]", "synthetic-seed",
    "2026-10-18T00:00:00Z")


def command_key(request_id: str) -> dict:
    return {"requestId": request_id, "targetId": None,
            "expectedRevision": None, "inputRefs": []}


def run_event(event_key: str, event_code: str = "run.progress",
              payload: dict | None = None, **overrides) -> dict:
    event = {"runId": RUN_ID, "eventKey": event_key, "eventCode": event_code,
             "payload": {"cursor": 1} if payload is None else payload,
             "expectedHeadSeq": None, "terminalReceiptRef": None}
    event.update(overrides)
    return event


def terminal_ref() -> dict:
    return {"owner": "harness", "kind": "terminal_result", "id": RUN_ID,
            "version": "1"}


def free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


def port_open(port: int) -> bool:
    with socket.socket() as probe:
        probe.settimeout(1.0)
        return probe.connect_ex(("127.0.0.1", port)) == 0


def verify_branch(root: Path) -> tuple[bool, str]:
    def git(*arguments):
        return subprocess.run(["git", "-C", str(root), *arguments],
                              capture_output=True, text=True,
                              encoding="utf-8", timeout=30)
    if not (root / "tools/workflow-tools/harness/public_entry.py").exists():
        return False, "harness_root_missing:" + str(root)
    branch = git("rev-parse", "--abbrev-ref", "HEAD").stdout.strip()
    head = git("rev-parse", "HEAD").stdout.strip()
    if branch == EXPECT_BRANCH and head:
        return True, "branch={} head={}".format(branch, head[:8])
    return False, "branch_mismatch:{}@{} expected:{}".format(
        branch, head[:8], EXPECT_BRANCH)


class Recon:
    def __init__(self, harness_root: Path, keep: bool, stamp: str):
        self.harness_root = harness_root
        self.keep = keep
        self.stamp = stamp
        self.checks: list[dict] = []
        self.feature_checks: dict[str, list[dict]] = {"F24": [], "F26": []}

    # -- check plumbing ------------------------------------------------------

    def step(self, name, ok, feature=None, **facts):
        entry = {"check": name, "status": "PASS" if ok else "FAIL", **facts}
        self.checks.append(entry)
        if feature in self.feature_checks:
            self.feature_checks[feature].append(entry)
        print(json.dumps(entry, ensure_ascii=False), flush=True)
        if not ok:
            raise AssertionError(name)

    def blocked(self, reason, **facts):
        print(json.dumps({"check": reason, "status": "BLOCKED", **facts},
                         ensure_ascii=False), flush=True)
        print(json.dumps({"status": "RECON_BLOCKED", "reason": reason}))
        raise SystemExit(3)

    # -- static freeze face ---------------------------------------------------

    def branch_checks(self) -> str:
        ok, note = verify_branch(self.harness_root)
        if not ok:
            self.blocked("harness_branch", note=note)
        head = note.split("head=")[-1]
        matter_store = (self.harness_root / "src" / "legal_harness" / "state"
                        / "matter_store.py").read_text(encoding="utf-8")
        registry = (self.harness_root / "src" / "legal_harness" / "business"
                    / "provider_registry.py").read_text(encoding="utf-8")
        entry = (self.harness_root / "tools" / "workflow-tools" / "harness"
                 / "public_entry.py").read_text(encoding="utf-8")
        self.step("c00_harness_freeze_face",
                  "SCHEMA_VERSION = 24" in matter_store
                  and "run_events" in matter_store
                  and "tool_governance_policies" in matter_store
                  and "harness.run_event_append" in registry
                  and "harness.tool_governance_register" in registry
                  and "--runledger-json" in entry and "--toolgov-json" in entry,
                  schema="v24 + run_events/tool_governance_policies",
                  envelopes="--runledger-json/--toolgov-json",
                  head=head)
        return head

    # -- store phase（desktop 桥子进程链 / selfhost PgMatterStore 直连）-------

    def store_phase(self, profile: str, call_harness, expect_error,
                    seed_run) -> None:
        # --- F24 goal owner（消费 T16 goal 账）＋run 事件账 ----------------
        call_harness("harness.save_goal", {
            "actor_id": "recon-lawyer", "scope": SCOPE,
            "key": command_key(profile + "-sg-1"), "goal": GOAL_PAYLOAD})
        account = call_harness("harness.get_goal", {
            "scope": SCOPE, "goal_id": "g-f24f26"})
        self.step("c01_goal_owner_harness_t16",
                  account["goal"]["goalId"] == "g-f24f26"
                  and account["goal"]["revision"] == 1,
                  feature="F24", account="T16 case_goals 唯一权威")
        call_harness("harness.decide_goal_plan", {
            "actor_id": "recon-lawyer", "scope": SCOPE,
            "key": command_key(profile + "-dp-1"),
            "decision": {"goalId": "g-f24f26", "planId": "plan-recon",
                         "planRevision": "1", "decision": "approved"}})
        call_harness("harness.adopt_goal_task", {
            "actor_id": "recon-lawyer", "scope": SCOPE,
            "key": command_key(profile + "-at-1"),
            "adoption": {"goalId": "g-f24f26", "taskId": "task-recon",
                         "action": "adopt",
                         "basis": {"factRevision": "fact-1",
                                   "lawRevision": "law-1"}}})
        basis = call_harness("harness.read_goal_basis", {
            "scope": SCOPE,
            "query": {"goalId": "g-f24f26", "taskId": "task-recon"}})
        self.step("c02_goal_basis_current_after_adopt",
                  basis.get("status") == "CURRENT",
                  feature="F24", status=basis.get("status"))

        seed_run()
        first = call_harness("harness.run_event_append", {
            "actor_id": "recon-host", "scope": SCOPE,
            "key": command_key(profile + "-ev-1"),
            "event": run_event("k1")})
        self.step("c03_run_event_owner_harness",
                  first["event"]["seq"] == 1 and first["headSeq"] == 1
                  and first["receipt"]["ref"]["owner"] == "harness",
                  feature="F24", owner="harness（业务 run 账主）")
        replay = call_harness("harness.run_event_append", {
            "actor_id": "recon-host", "scope": SCOPE,
            "key": command_key(profile + "-ev-1b"),
            "event": run_event("k1")})
        self.step("c04_same_key_same_content_idempotent",
                  replay["replayed"] is True and replay["headSeq"] == 1
                  and replay["event"]["seq"] == 1,
                  feature="F24")
        code = expect_error(lambda: call_harness("harness.run_event_append", {
            "actor_id": "recon-host", "scope": SCOPE,
            "key": command_key(profile + "-ev-2"),
            "event": run_event("k1", payload={"cursor": 2})}))
        self.step("c05_same_key_different_content_refused",
                  "run_event_key_conflict" in code,
                  feature="F24", code=code,
                  semantics="core session inbox 同键重放 HTTP 409 的账本同语义")
        code = expect_error(lambda: call_harness("harness.run_event_append", {
            "actor_id": "recon-host", "scope": SCOPE,
            "key": command_key(profile + "-ev-3"),
            "event": run_event("k2", expectedHeadSeq=0)}))
        self.step("c06_optimistic_head_lock",
                  "run_event_head_conflict" in code,
                  feature="F24", code=code)
        code = expect_error(lambda: call_harness("harness.run_event_append", {
            "actor_id": "recon-host", "scope": SCOPE,
            "key": command_key(profile + "-ev-4"),
            "event": run_event("k3", eventCode="run.terminal",
                               terminalReceiptRef=terminal_ref())}))
        self.step("c07_terminal_needs_owner_chain",
                  "run_terminal_not_in_owner_chain" in code,
                  feature="F24", code=code, rule="不另造业务终局")
        code = expect_error(lambda: call_harness("harness.run_event_append", {
            "actor_id": "recon-host", "scope": SCOPE,
            "key": command_key(profile + "-ev-5"),
            "event": run_event("k4", eventCode="run.terminal",
                               terminalReceiptRef={
                                   "owner": "host",
                                   "kind": "terminal_result",
                                   "id": RUN_ID, "version": "1"})}))
        self.step("c08_host_terminal_ref_invalid",
                  "run_terminal_ref_invalid" in code,
                  feature="F24", code=code)
        page = call_harness("harness.run_events_read", {
            "scope": SCOPE, "run_id": RUN_ID, "after_seq": 0})
        self.step("c09_cursor_read_projection",
                  [item["seq"] for item in page["events"]] == [1]
                  and page["headSeq"] == 1 and page["nextCursor"] == 1,
                  feature="F24", cursor="SSE cursor（after_seq→nextCursor）")
        projection = call_harness("harness.run_projection_read", {
            "scope": SCOPE, "run_id": RUN_ID})
        self.step(
            "c10_owner_projection_unique",
            projection["owners"] == {"businessRun": "harness",
                                     "goal": "harness",
                                     "coreSession": "core"}
            and "run.terminal" not in
            set(projection["hostWritableEventCodes"])
            and projection["terminal"]["terminal"] is False
            and projection["goal"] is not None
            and projection["goal"]["goalId"] == "g-f24f26",
            feature="F24",
            owners=projection["owners"],
            hostWritable=projection["hostWritableEventCodes"],
            note="Host 可写码闭集不含终局码；goal 投影钉 T16 头版本")

        # --- F26 工具治理账 -----------------------------------------------
        registered = call_harness("harness.tool_governance_register", {
            "actor_id": "recon-lawyer", "scope": SCOPE,
            "key": command_key(profile + "-gov-1"),
            "policy": GOVERNANCE_V1})
        self.step("c11_governance_register_active",
                  registered["policy"]["status"] == "ACTIVE"
                  and registered["policy"]["revision"] == 1,
                  feature="F26", denyByDefault="literal True（尾置 deny 纪律）")
        replay_gov = call_harness("harness.tool_governance_register", {
            "actor_id": "recon-lawyer", "scope": SCOPE,
            "key": command_key(profile + "-gov-1b"),
            "policy": GOVERNANCE_V1})
        self.step("c12_governance_replay_idempotent",
                  replay_gov["replayed"] is True, feature="F26")
        code = expect_error(lambda: call_harness(
            "harness.tool_governance_register", {
                "actor_id": "recon-lawyer", "scope": SCOPE,
                "key": command_key(profile + "-gov-2"),
                "policy": dict(GOVERNANCE_V1, denyByDefault=False)}))
        self.step("c13_deny_by_default_required",
                  "tool_governance_deny_by_default_required" in code,
                  feature="F26", code=code)
        code = expect_error(lambda: call_harness(
            "harness.tool_governance_register", {
                "actor_id": "recon-lawyer", "scope": SCOPE,
                "key": command_key(profile + "-gov-3"),
                "policy": dict(GOVERNANCE_V1, allowedTools=["*"])}))
        self.step("c14_wildcard_whitelist_refused",
                  "tool_governance_wildcard_whitelist_invalid" in code,
                  feature="F26", code=code)
        matrix = [
            ({"tool": "read", "resource": "materials/合同摘要.txt"},
             "allow", "read_zone_in_scope"),
            ({"tool": "read", "resource": "C:/Users/x/secrets.env"},
             "deny", "resource_invalid"),
            ({"tool": "edit", "resource": "work/起诉状.docx"},
             "allow", "write_zone_in_scope"),
            ({"tool": "edit", "resource": "materials/原件扫描.pdf"},
             "deny", "write_zone_out_of_scope"),
            ({"tool": "execute", "resource": "*"},
             "deny", "execution_tier_none"),
            ({"tool": "shell", "resource": "echo 合成"},
             "deny", "tool_not_whitelisted"),
            ({"tool": "webfetch", "resource": "https://evil.example/x"},
             "deny", "tool_not_whitelisted"),
            ({"tool": "subagent", "resource": "general"},
             "deny", "tool_not_whitelisted"),
            ({"tool": "skill", "skillId": "skill-exfil"},
             "deny", "skill_blacklisted"),
            ({"tool": "skill", "skillId": "calc-利息"},
             "allow", "whitelisted"),
            ({"tool": "unknown-agent-tool"}, "deny",
             "tool_not_whitelisted"),
        ]
        matrix_ok = True
        observed = []
        for call_payload, verdict, reason in matrix:
            outcome = call_harness("harness.tool_governance_decide", {
                "scope": SCOPE, "governance_id": "gov-legal-review",
                "call": call_payload})
            observed.append({"call": call_payload,
                             "verdict": outcome["verdict"],
                             "reason": outcome["reason"]})
            if outcome["verdict"] != verdict or outcome["reason"] != reason:
                matrix_ok = False
        self.step("c15_governance_decide_deny_closed_matrix",
                  matrix_ok, feature="F26", cases=observed,
                  rule="白名单外/读写越区/执行越档/黑名单/未知形状一律具名 deny")
        superseded = call_harness("harness.tool_governance_register", {
            "actor_id": "recon-lawyer", "scope": SCOPE,
            "key": command_key(profile + "-gov-4"),
            "policy": dict(GOVERNANCE_V1, revision=2,
                           executionTier="WHITELISTED",
                           executionAllowlist=[])})
        view = call_harness("harness.tool_governance_read", {
            "scope": SCOPE, "governance_id": "gov-legal-review"})
        self.step("c16_governance_revision_supersede",
                  superseded["policy"]["status"] == "ACTIVE"
                  and view["active"]["revision"] == 2
                  and view["revisionCount"] == 2
                  and {item["revision"]: item["status"]
                       for item in view["revisions"]}
                  == {1: "SUPERSEDED", 2: "ACTIVE"},
                  feature="F26", revision="append-only＋ACTIVE/SUPERSEDED")
        tier_outcome = call_harness("harness.tool_governance_decide", {
            "scope": SCOPE, "governance_id": "gov-legal-review",
            "call": {"tool": "execute", "resource": "*"}})
        self.step("c17_tier_gate_follows_active_revision",
                  tier_outcome["verdict"] == "deny"
                  and tier_outcome["reason"] == "execution_not_allowlisted"
                  and tier_outcome["revision"] == 2,
                  feature="F26", code=tier_outcome["reason"])

        # --- Host 侧 run_cursor_store（product 模块，双 profile 同证）------
        with tempfile.TemporaryDirectory(prefix="f24f26-hoststore-") as tmp:
            store = RunCursorStore(Path(tmp) / "run-host.json")
            store.record_session_ref(MATTER, "ses_recon_" + profile)
            store.update_cursor(RUN_ID, 1, "2026-10-18T00:00:00Z")
            store.record_approval(RUN_ID, "approved", "rcpt-a", "t1")
            replayed_approval = store.record_approval(RUN_ID, "approved",
                                                      "rcpt-a", "t1")
            state = store.load()
            host_ok = (
                replayed_approval["replayed"] is True
                and state["schema"] == "f24-runhost/1"
                and set(state) == {"schema", "sessionRefs", "runCursors",
                                   "approvals"})
            leaked = [key for key in
                      GOAL_CONTENT_KEYS + TERMINAL_KEYS
                      if _key_in(state, key)]
            try:
                store.update_cursor(RUN_ID, 0, "t-regress")
                host_ok = False
            except RunCursorStoreError:
                pass
            try:
                store.save(dict(state, terminal={"verdict": "win"}))
                host_ok = False
            except RunCursorStoreError:
                pass
            self.step("c18_host_metadata_only_store",
                      host_ok and not leaked,
                      feature="F24", schema="f24-runhost/1",
                      leakedKeys=leaked,
                      rule="Host 只有投影/游标/批准恢复元数据；游标单调；"
                           "终局字段结构性禁入")

    # -- live phase（oc28 serve 临时根；零模型依赖）---------------------------

    def live_phase(self, oc28: Path, bun: Path) -> dict:
        import time as _time

        base = Path(tempfile.mkdtemp(prefix="f24f26-live-"))
        roots = {}
        for name in ("state", "data", "config", "cache"):
            roots[name] = base / "oc" / name
            roots[name].mkdir(parents=True)
        roots["workspace"] = base / "workspace"
        roots["workspace"].mkdir()
        roots["service_log"] = base / "service.log"
        self.temp_base = base
        try:
            appdata_before = _snapshot_appdata()
            # T07 尾置 deny 配置面复刻进临时根（含 policies veto 层）。
            config_dir = roots["config"] / "opencode"
            config_dir.mkdir(parents=True)
            (config_dir / "opencode.json").write_text(json.dumps({
                "default_agent": "legal-review",
                "agents": {"legal-review": {
                    "description": "律引 recon 临时 profile（合成）",
                    "mode": "primary",
                    "permissions": [
                        {"action": "read", "resource": "*",
                         "effect": "deny"},
                        {"action": "read", "resource": "materials/**",
                         "effect": "allow"},
                        {"action": "shell", "resource": "*",
                         "effect": "deny"},
                        {"action": "webfetch", "resource": "*",
                         "effect": "deny"},
                        {"action": "execute", "resource": "*",
                         "effect": "deny"},
                        {"action": "*", "resource": "*",
                         "effect": "deny"}]}},
                "experimental": {"policies": [
                    {"action": "tool.use", "resource": "shell:*",
                     "effect": "deny"}]},
            }, ensure_ascii=False), encoding="utf-8")
            self.port = free_port()
            self.step("l01_topology_temp_roots", True,
                      base=str(base), port=self.port)
            registration = self._launch(oc28, bun, roots)
            client = self._client(registration)
            info = client.request("GET", "/api/info")
            info_value = info.get("data", info) if isinstance(info, dict) \
                else {}
            version = info_value.get("version")
            self.step("l02_service_boot", version == DEV_VERSION,
                      version=version, pin="2.0.28（F-4 dev 双轨记实值）")

            # F-9 守卫先于 transport（死端口＋冲突 allow→SessionRejected）。
            dead = base / "dead-registration.json"
            dead.write_text(json.dumps(
                {"url": "http://127.0.0.1:1",
                 "password": "synthetic-dead"}), encoding="utf-8")
            try:
                create_public_session(
                    {"id": "ses_dead", "title": "x",
                     "location": {"directory": str(roots["workspace"])},
                     "permissions": [
                         {"action": "shell", "resource": "*",
                          "effect": "allow"}]},
                    {"opencode_registration": str(dead),
                     "opencode_timeout": 5},
                    policies=[{"effect": "deny", "action": "tool.use",
                               "resource": "shell:*"}])
                self.step("l03_f9_guard_before_transport", False,
                          code="no-reject")
            except SessionRejected as exc:
                self.step("l03_f9_guard_before_transport",
                          "session_allow_conflicts_policy_deny" in str(exc),
                          code=str(exc)[:80])
            except TransportError:
                self.step("l03_f9_guard_before_transport", False,
                          code="guard_after_transport")

            # 会话创建（core 账本；session 账主=core）。
            session_a = "ses_f24f26_a"
            created = client.request(
                "POST", "/api/session",
                {"id": session_a, "title": "律引 F24 对账 A（合成）",
                 "location": {"directory": str(roots["workspace"])}})
            view = client.session(session_a)
            value = view.get("data", view) if isinstance(view, dict) else {}
            self.step("l04_session_owner_core",
                      created.get("data", created).get("id") == session_a
                      and value.get("title") == "律引 F24 对账 A（合成）",
                      session=session_a,
                      owner="core（session 账本在服务端）")

            # 同键重放：同 id 异内容重放＝幂等返回原入队项（matches() 只比
            # session+type），原文不被改写。
            parked_id = "msg_f24f26_parked"
            client.prompt(session_a, {"id": parked_id,
                                      "text": "（合成）占位入队原文",
                                      "resume": False})
            client.prompt(session_a, {"id": parked_id,
                                      "text": "（合成）同 id 异内容重放",
                                      "resume": False})
            rows = [item for item in self._inbox(client, session_a)
                    if item.get("id") == parked_id]
            self.step("l05_same_key_readmission_idempotent",
                      len(rows) == 1 and rows[0].get("payload", {}).get(
                          "text") == "（合成）占位入队原文",
                      inbox_rows=len(rows),
                      semantics="resubmitRequiresNewMessageId=True 的服务端语义")

            # 409：session A 交付 user 行（resume:true，无模型也落库——
            # 实测 2026-10-18 probe409）→ 跨会话重用同 id＝LifecycleConflict
            # → HTTP 409。
            delivered_id = "msg_f24f26_delivered"
            client.prompt(session_a, {"id": delivered_id,
                                      "text": "（合成）交付行", "resume": True})
            landed = False
            deadline = _time.monotonic() + 30.0
            while _time.monotonic() < deadline:
                if delivered_id in self._history_ids(client, session_a):
                    landed = True
                    break
                _time.sleep(0.5)
            session_b = "ses_f24f26_b"
            client.request("POST", "/api/session",
                           {"id": session_b, "title": "律引 F24 对账 B（合成）",
                            "location": {"directory": str(
                                roots["workspace"])}})
            try:
                client.prompt(session_b, {"id": delivered_id,
                                          "text": "（合成）跨会话撞 id"})
                self.step("l06_same_key_replay_http_409", False and landed,
                          code="no-conflict", delivered=landed)
            except TransportError as exc:
                self.step("l06_same_key_replay_http_409",
                          landed and exc.code == "http_409"
                          and exc.uncertain is False,
                          code=exc.code, uncertain=exc.uncertain,
                          delivered=landed,
                          semantics="e07_live_recon 同键重放 HTTP 409 语义复测")

            # F26 权限 oracle 负测矩阵（e02 A 组形状；免模型）。规则序沿
            # T07 §7.4-1 实测定论：白名单 allow 必须尾置在通配 deny 之后
            # （findLast 取尾——中段 allow 会被尾置 * deny 压成死规则）。
            session_p = "ses_f24f26_perm"
            client.request("POST", "/api/session",
                           {"id": session_p,
                            "title": "律引 F26 权限负测（合成）",
                            "location": {"directory": str(
                                roots["workspace"])},
                            "permissions": [
                                {"action": "shell", "resource": "*",
                                 "effect": "deny"},
                                {"action": "webfetch", "resource": "*",
                                 "effect": "deny"},
                                {"action": "execute", "resource": "*",
                                 "effect": "deny"},
                                {"action": "subagent", "resource": "*",
                                 "effect": "deny"},
                                {"action": "external_directory",
                                 "resource": "*", "effect": "deny"},
                                {"action": "read", "resource": "*",
                                 "effect": "deny"},
                                {"action": "*", "resource": "*",
                                 "effect": "deny"},
                                {"action": "read",
                                 "resource": "materials/**",
                                 "effect": "allow"}]})
            evals = [
                ("n01_shell_deny", "shell", "rm -rf /tmp/合成卷宗", "deny"),
                ("n02_edit_deny", "edit", "案卷/起诉状.docx", "deny"),
                ("n03_webfetch_deny", "webfetch",
                 "https://evil.example/exfil", "deny"),
                ("n04_external_directory_deny", "external_directory",
                 "C:/*", "deny"),
                ("n05_read_whitelist_out_deny", "read",
                 "C:/Users/x/secrets.env", "deny"),
                ("n06_read_whitelist_in_allow", "read",
                 "materials/合成材料.txt", "allow"),
                ("n07_execute_deny", "execute", "*", "deny"),
                ("n08_subagent_deny", "subagent", "general", "deny"),
            ]
            matrix_ok = True
            observed = []
            for name, action, resource, expected in evals:
                outcome = self._evaluate(client, session_p, action, resource)
                observed.append({"check": name, "effect":
                                 outcome.get("effect")})
                if outcome.get("effect") != expected:
                    matrix_ok = False
            self.step("l07_permission_oracle_matrix", matrix_ok,
                      cases=observed,
                      rule="未广告/未授权工具直接求值＝后端强制（e02 A 组形状）")
            persisted = value_permissions(client, session_p)
            self.step("l08_permissions_persisted_fail_closed",
                      any(rule.get("action") == "shell"
                          and rule.get("effect") == "deny"
                          for rule in persisted),
                      rules=len(persisted))
            try:
                client.request("POST", "/api/session",
                               {"id": "ses_f24f26_bad",
                                "title": "x",
                                "location": {"directory": str(
                                    roots["workspace"])},
                                "permissions": [
                                    {"action": "shell", "resource": "*",
                                     "effect": "block"}]})
                self.step("l09_invalid_effect_http_4xx", False, code="accepted")
            except TransportError as exc:
                self.step("l09_invalid_effect_http_4xx",
                          exc.code.startswith("http_4"),
                          code=exc.code)
            # policies veto 层：会话尾置 allow 的 shell 请求被组织策略压成
            # deny（T07 §7.3-3 同构探针）。
            session_v = "ses_f24f26_veto"
            client.request("POST", "/api/session",
                           {"id": session_v, "title": "veto 探针（合成）",
                            "location": {"directory": str(
                                roots["workspace"])},
                            "permissions": [
                                {"action": "shell", "resource": "*",
                                 "effect": "allow"}]})
            veto = self._evaluate(client, session_v, "shell", "echo 合成")
            self.step("l10_policy_veto_overrides_session_allow",
                      veto.get("effect") == "deny",
                      effect=veto.get("effect"),
                      rule="experimental.policies veto 优先于一切规则")

            # T07/T13 产品配置面符合性（%APPDATA%\Juscite 只读）：把活配
            # 置规则与治理合同（GOVERNANCE_V1）对账——执行档位双层 deny
            # （agent 规则＋policies veto）、读写分区 allow 落声明区内、
            # 白名单外零 allow、.env 尾置读闸、skill/mcp 收口。
            product_config = (Path(os.environ["APPDATA"]) / "Juscite"
                              / "config" / "opencode" / "opencode.json")
            if not product_config.exists():
                self.blocked("product_config_missing",
                             path=str(product_config))
            config_document = json.loads(
                product_config.read_text(encoding="utf-8"))
            agent = (config_document.get("agents") or {}).get(
                "legal-review") or {}
            rules = agent.get("permissions") or []
            policies = ((config_document.get("experimental") or {})
                        .get("policies") or [])
            issues = _governance_conformance(GOVERNANCE_V1, rules, policies)
            self.step("l11_t07_config_matches_governance", not issues,
                      nonconformities=issues,
                      agentRules=len(rules), policies=len(policies),
                      path="%APPDATA%\\Juscite\\config\\opencode\\"
                           "opencode.json（只读）",
                      rule="执行档位双层 deny＋读写分区 allow 落声明区＋"
                           "白名单外零 allow＋.env 尾闸＋skill/mcp 收口")
            appdata_after = _snapshot_appdata()
            self.step("l12_appdata_juscite_read_only",
                      appdata_after == appdata_before,
                      watched=sorted(appdata_before))
            return {"sessionOwner": session_a,
                    "inboxReplay": parked_id,
                    "http409": delivered_id,
                    "permissionMatrix": observed}
        finally:
            self._teardown_live(roots, base)

    # -- live helpers ---------------------------------------------------------

    def _launch(self, oc28: Path, bun: Path, roots: dict) -> dict:
        env = {k: v for k, v in os.environ.items()}
        env["XDG_STATE_HOME"] = str(roots["state"])
        env["XDG_DATA_HOME"] = str(roots["data"])
        env["XDG_CONFIG_HOME"] = str(roots["config"])
        env["XDG_CACHE_HOME"] = str(roots["cache"])
        env["OPENCODE_DISABLE_MODELS_FETCH"] = "1"
        env["OPENCODE_CHANNEL"] = "local"
        env["OPENCODE_VERSION"] = DEV_VERSION
        argv = [str(bun), "run", "--cwd", "packages/cli",
                "--define=OPENCODE_VERSION=process.env.OPENCODE_VERSION",
                "src/index.ts", "serve", "--service",
                "--hostname", "127.0.0.1", "--port", str(self.port)]
        log = open(roots["service_log"], "ab")
        self.service = subprocess.Popen(argv, cwd=str(oc28), env=env,
                                        stdout=log,
                                        stderr=subprocess.STDOUT)
        reg_path = roots["state"] / "opencode" / "service-local.json"
        deadline = time.monotonic() + 240.0
        registration = None
        while time.monotonic() < deadline:
            if self.service.poll() is not None:
                self.blocked("service_process_exited",
                             exit_code=self.service.returncode)
            if reg_path.exists():
                try:
                    registration = json.loads(
                        reg_path.read_text(encoding="utf-8"))
                except (json.JSONDecodeError, UnicodeDecodeError):
                    registration = None
            if registration is not None and registration.get("password"):
                try:
                    self._client(registration).request("GET", "/api/info")
                    return registration
                except TransportError:
                    pass
            time.sleep(1.0)
        self.blocked("service_ready_timeout", log=str(roots["service_log"]))

    @staticmethod
    def _client(registration: dict, timeout: float = 60.0) -> Client:
        token = base64.b64encode(("opencode:"
                                  + registration["password"]).encode()
                                 ).decode("ascii")
        return Client(registration["url"],
                      headers={"Authorization": "Basic " + token},
                      timeout=timeout)

    def _teardown_live(self, roots: dict, base: Path) -> None:
        service = getattr(self, "service", None)
        if service is not None and service.poll() is None:
            reg_path = roots["state"] / "opencode" / "service-local.json"
            try:
                registration = json.loads(
                    reg_path.read_text(encoding="utf-8"))
                subprocess.run(["taskkill", "/F", "/T", "/PID",
                                str(registration.get("pid"))],
                               capture_output=True, timeout=60)
            except Exception:  # noqa: BLE001 - teardown best effort
                subprocess.run(["taskkill", "/F", "/T", "/PID",
                                str(service.pid)],
                               capture_output=True, timeout=60)
        if not self.keep:
            shutil.rmtree(base, ignore_errors=True)
        else:
            print(json.dumps({"kept_temp_root": str(base)},
                             ensure_ascii=False), flush=True)

    @staticmethod
    def _inbox(client: Client, session_id: str) -> list:
        inbox = client.inbox(session_id)
        return [item for item in
                (inbox.get("data", []) if isinstance(inbox, dict) else [])
                if isinstance(item, dict)]

    @staticmethod
    def _history_ids(client: Client, session_id: str) -> list:
        from urllib.parse import quote

        messages: list = []
        path = "/api/session/{}/message?order=asc".format(quote(session_id,
                                                              safe=""))
        while path:
            listing = client.request("GET", path)
            if not isinstance(listing, dict):
                return messages
            messages.extend(listing.get("data", []))
            cursor = (listing.get("cursor") or {}).get("next")
            path = ("/api/session/{}/message?cursor={}".format(
                quote(session_id, safe=""), quote(str(cursor), safe=""))
                if cursor else None)
        return [m.get("id") for m in messages if isinstance(m, dict)]

    @staticmethod
    def _evaluate(client: Client, session_id: str, action: str,
                  resource: str) -> dict:
        outcome = client.request(
            "POST", "/api/session/{}/permission".format(session_id),
            {"action": action, "resources": [resource]})
        return outcome.get("data", outcome) if isinstance(outcome, dict) \
            else {}


def value_permissions(client: Client, session_id: str) -> list:
    view = client.session(session_id)
    value = view.get("data", view) if isinstance(view, dict) else {}
    return value.get("permissions") or []


def _zone_prefix(zone: str) -> str:
    prefix = zone
    for suffix in ("/**", "/*", "**", "*"):
        if prefix.endswith(suffix):
            prefix = prefix[:-len(suffix)]
            break
    return prefix.rstrip("/")


def _pattern_within(pattern: str, zones: list) -> bool:
    """allow 资源模式是否落在声明分区（前缀覆盖，确定性）。"""
    prefix = _zone_prefix(pattern)
    return any(prefix == _zone_prefix(zone)
               or prefix.startswith(_zone_prefix(zone) + "/")
               for zone in zones)


def _governance_conformance(policy: dict, rules: list,
                            policies: list) -> list:
    """产品配置面 vs 治理合同符合性（读侧纯函数，返回具名 nonconformities）。

    义务映射：执行档位（NONE）＝执行/网络/子代理族 agent 规则与 policies
    veto 双层具名 deny（后端强制双保险）；读写分区双闸＝read/glob/grep
    allow 落 readZones、edit/write allow 落 writeZones；白名单＝allow
    动作 ⊆ 声明 allowedTools（全禁比黑名单更严＝保守符合）；尾置 .env
    读闸＋skill/mcp veto（未广告面收口）。
    """
    issues: list = []
    allows = [rule for rule in rules if rule.get("effect") == "allow"]
    denies = [rule for rule in rules if rule.get("effect") == "deny"]
    deny_actions = {rule.get("action") for rule in denies}
    tool_vetoes = {
        str(item.get("resource") or "").split(":")[0]
        for item in policies
        if item.get("effect") == "deny" and item.get("action") == "tool.use"}
    integration_vetoes = {
        str(item.get("resource") or "").split(":")[0]
        for item in policies
        if item.get("effect") == "deny"
        and item.get("action") == "integration.use"}
    if not any(rule.get("action") == "*" and rule.get("resource") == "*"
               for rule in denies):
        issues.append("lead_deny_missing")
    if policy["executionTier"] == "NONE":
        # 执行族＝harness _TOOL_EXECUTION_FAMILY 同集（shell/execute）：
        # 档位 NONE 要求 agent 规则与 policies veto 双层具名 deny。
        for action in ("shell", "execute"):
            if action not in deny_actions:
                issues.append(f"tier_agent_deny_missing:{action}")
            if action not in tool_vetoes:
                issues.append(f"tier_policy_veto_missing:{action}")
    # 未授权族（网络/子代理）：未广告/未授权不能调用＝agent 层具名 deny
    # （policies veto 对 webfetch/websearch 另在产品面在位，合同要求取严）。
    for action in ("webfetch", "websearch", "subagent"):
        if action not in deny_actions:
            issues.append(f"unauthorized_family_deny_missing:{action}")
    if "external_directory" not in deny_actions:
        issues.append("external_directory_agent_deny_missing")
    if "external_directory" not in tool_vetoes:
        issues.append("external_directory_policy_veto_missing")
    for rule in allows:
        action = rule.get("action")
        resource = str(rule.get("resource") or "")
        if action in {"read", "glob", "grep"}:
            if not _pattern_within(resource, policy["readZones"]):
                issues.append(f"read_allow_out_of_zone:{resource}")
        elif action in {"edit", "write", "patch"}:
            if not _pattern_within(resource, policy["writeZones"]):
                issues.append(f"write_allow_out_of_zone:{resource}")
        elif action not in set(policy["allowedTools"]):
            issues.append(f"allow_not_whitelisted:{action}")
    if not any(rule.get("action") == "read"
               and ".env" in str(rule.get("resource") or "")
               for rule in denies):
        issues.append("env_read_deny_missing")
    if "skill" not in deny_actions and "skill" not in integration_vetoes:
        issues.append("skill_gate_missing")
    if "mcp" not in integration_vetoes:
        issues.append("mcp_veto_missing")
    return issues


def _key_in(node, key: str) -> bool:
    if isinstance(node, dict):
        if key in node:
            return True
        return any(_key_in(value, key) for value in node.values())
    if isinstance(node, list):
        return any(_key_in(item, key) for item in node)
    return False


def _snapshot_appdata() -> dict:
    appdata = Path(os.environ["APPDATA"]) / "Juscite"
    snapshot = {}
    for relative in ("config/opencode/opencode.json",):
        target = appdata / relative
        if target.exists():
            stat = target.stat()
            snapshot[relative] = (stat.st_size, stat.st_mtime_ns)
    state_dir = appdata / "state" / "opencode"
    if state_dir.is_dir():
        for item in sorted(state_dir.glob("*.json")):
            stat = item.stat()
            snapshot["state/opencode/" + item.name] = (
                stat.st_size, stat.st_mtime_ns)
    return snapshot


def write_evidence(feature: str, profile: str, stamp: str,
                   payload: dict, kind: str = "recon") -> Path:
    directory = EVIDENCE_ROOT / feature / profile
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{feature.lower()}-{profile}-{kind}-{stamp}.json"
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=1),
                    encoding="utf-8")
    return path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--profile", action="append",
                        choices=["desktop", "selfhost"])
    parser.add_argument("--harness-root", type=Path,
                        default=DEFAULT_HARNESS_ROOT)
    parser.add_argument("--oc28", type=Path, default=DEFAULT_OC28)
    parser.add_argument("--bun", type=Path, default=DEFAULT_BUN)
    parser.add_argument("--pg-dsn", default=None)
    parser.add_argument("--keep", action="store_true")
    arguments = parser.parse_args()
    profiles = arguments.profile or ["desktop", "selfhost"]
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    recon = Recon(arguments.harness_root, arguments.keep, stamp)
    head = recon.branch_checks()
    if not arguments.oc28.is_dir():
        recon.blocked("oc28_missing", path=str(arguments.oc28))
    bun = (arguments.bun if arguments.bun.exists()
           else Path(shutil.which("bun") or ""))
    if not bun.exists():
        recon.blocked("bun_not_found")
    failures = 0
    live_payload: dict | None = None
    for profile in profiles:
        started = datetime.now(timezone.utc).isoformat()
        before = len(recon.checks)
        try:
            if profile == "desktop":
                state_holder = tempfile.TemporaryDirectory(
                    prefix="juscite-f24f26-harness-")
                state_root = Path(state_holder.name) / "state"
                state_root.mkdir(parents=True)
                for path in (str(arguments.harness_root / "src"),
                             str(arguments.harness_root
                                 / "tools/workflow-tools")):
                    if path not in sys.path:
                        sys.path.insert(0, path)
                from legal_harness.state.matter_store import MatterStore
                store = MatterStore(state_root)
                store.create_matter(MATTER, "cas://profile-f24f26")

                def seed_run(_store=store):
                    with _store.transaction() as connection:
                        connection.execute(RUN_EVENT_SQL,
                                           RUN_EVENT_SQL_PARAMS)
                        connection.execute(GRAPH_REVISION_SQL,
                                           GRAPH_REVISION_SQL_PARAMS)

                def call_harness(method, call_args,
                                 _hr=arguments.harness_root,
                                 _root=state_root):
                    config = {
                        "harness_public_entry": str(
                            _hr / "tools" / "workflow-tools" / "harness"
                            / "public_entry.py"),
                        "harness_target": "workbuddy",
                        "harness_state_root": str(_root),
                    }
                    return legal_entry.call(method, call_args, config)

                def expect_error(callable_):
                    try:
                        callable_()
                    except HarnessCommandError as error:
                        return str(error)
                    return ""

                try:
                    recon.store_phase("desktop", call_harness, expect_error,
                                      seed_run)
                finally:
                    state_holder.cleanup()
            else:
                import uuid as _uuid

                dsn = (arguments.pg_dsn
                       or os.environ.get("LH_E08_PG_DSN") or DEFAULT_PG_DSN)
                sys.path.insert(0, str(arguments.harness_root / "src"))
                sys.path.insert(0, str(arguments.harness_root
                                       / "tools" / "workflow-tools"))
                from legal_harness.state.pg_store import PgMatterStore
                from legal_harness.business.provider_registry import (
                    resolve_provider_method)
                from legal_harness.business.units import HarnessUnits
                from legal_harness.business.units import UnitsError
                holder = tempfile.TemporaryDirectory(
                    prefix="juscite-f24f26-selfhost-")
                holder.cleanup()
                pg_store = PgMatterStore(
                    Path(holder.name), dsn=dsn,
                    schema="f24f26_recon_" + _uuid.uuid4().hex[:12])
                pg_store.create_matter(MATTER, "cas://profile-f24f26")
                units = HarnessUnits(pg_store)

                def seed_run(_store=pg_store):
                    with _store.transaction() as connection:
                        connection.execute(RUN_EVENT_SQL,
                                           RUN_EVENT_SQL_PARAMS)
                        connection.execute(GRAPH_REVISION_SQL,
                                           GRAPH_REVISION_SQL_PARAMS)

                def call_harness(method, call_args):
                    return resolve_provider_method(method, units)(**call_args)

                def expect_error(callable_):
                    try:
                        callable_()
                    except UnitsError as error:
                        return str(error)
                    return ""

                print("[profile selfhost] PgMatterStore direct (lh-pg-e08)",
                      dsn.split("@")[-1], flush=True)
                try:
                    recon.store_phase("selfhost", call_harness, expect_error,
                                      seed_run)
                finally:
                    try:
                        pg_store.destroy()
                    except Exception:  # noqa: BLE001 - cleanup best effort
                        pass
                    holder.cleanup()
            profile_checks = recon.checks[before:]
            recon.step("c99_profile_complete", True, profile=profile)
            profile_checks = recon.checks[before:]
            for feature in ("F24", "F26"):
                payload = {
                    "schema": f"juscite-{feature.lower()}-recon/1",
                    "unit": "W3-U03", "feature": feature,
                    "profile": profile, "startedAt": started,
                    "harnessBranch": EXPECT_BRANCH, "harnessHead": head,
                    "checks": [item for item in profile_checks
                               if item.get("feature") in (None, feature)],
                    "summary": {
                        "total": len(profile_checks),
                        "pass": sum(1 for item in profile_checks
                                    if item["status"] == "PASS")},
                }
                path = write_evidence(feature, profile, stamp, payload)
                print(json.dumps({"evidence": str(path)},
                                 ensure_ascii=False), flush=True)
        except AssertionError as exc:
            failures += 1
            print(f"[{profile}] RECON_FAIL: {exc}", flush=True)
        except Exception as exc:  # noqa: BLE001 - recon reports, never crashes
            failures += 1
            print(f"[{profile}] RECON_ERROR: {type(exc).__name__}: {exc}",
                  flush=True)
    # live 段单跑一次（core session 账主/409 语义/权限 oracle 与 profile 无关）。
    try:
        started = datetime.now(timezone.utc).isoformat()
        before = len(recon.checks)
        recon.live_phase(arguments.oc28, bun)
        live_checks = recon.checks[before:]
        live_payload = {
            "schema": "juscite-f24f26-live-recon/1",
            "unit": "W3-U03", "startedAt": started,
            "oc28": str(arguments.oc28),
            "checks": live_checks,
            "summary": {"total": len(live_checks),
                        "pass": sum(1 for item in live_checks
                                    if item["status"] == "PASS")},
        }
        for feature in ("F24", "F26"):
            for profile in profiles:
                payload = dict(live_payload)
                payload["feature"] = feature
                payload["profile"] = profile
                payload["note"] = "core session 活服务证据双 profile 同文"
                path = write_evidence(
                    feature, profile, stamp,
                    dict(payload,
                         schema=f"juscite-{feature.lower()}-live-recon/1"),
                    kind="live")
                print(json.dumps({"evidence": str(path)},
                                 ensure_ascii=False), flush=True)
    except AssertionError as exc:
        failures += 1
        print(f"[live] LIVE_RECON_FAIL: {exc}", flush=True)
    except SystemExit as exc:
        if exc.code == 3:
            return 3
        raise
    if failures:
        print(json.dumps({"status": "RECON_FAIL", "failures": failures}))
        return 2
    print(json.dumps({"status": "RECON_OK",
                      "checks": len(recon.checks),
                      "profiles": profiles}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

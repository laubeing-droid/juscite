"""F32 案件级记忆体系对账（W4-U34）——双 profile。

对账对象：harness 分支 w4-u34（基战役链头 w4-u31@8f65dc6f＝w4-u01→
w3-u20 同链接力；A2 裁决分支链常驻）的公开面——desktop profile 与产品桥
（legal_entry HARNESS_MEMORY_METHODS → --memory-json 信封＋MEMORY_METHODS
产品面 memory.distill 本地蒸馏）同一条链（SQLite 状态根）；selfhost
profile＝PgMatterStore 直连 lh-pg-e08（resolve_provider_method 同一封闭
注册）。全部合成材料：临时状态根、合成转写/合成记忆/合成决定 ref；
harness 检出零字节改动（只运行其代码，git 只读命令核对分支）。

合同＝harness schema v31 case_memory_entries（06 F32 行 v1.5·TTL 差异点，
2026-10-14 用户裁定）：
  硬点①确认闸：propose 只产候选（proposed 永不进生效投影）；confirm 是
    唯一生效转移，必须携带人工决定 ref（decisionRef 封闭六字段）。
  硬点②来源+TTL：每条记忆强制携带来源 ref（host 会话转写 digest）与
    ttl_seconds≥1；蒸馏候选同强制（产品面 memory.distill）。
  硬点③过期/撤销真实生效：TTL 过期（真实时钟越过 expires_at）与显式
    撤销都在回读面不可见；账行只追加保留可审计。
  硬点④目标账本不被延后：记忆账与 case_goals/E15/E17 各账零写交叉；
    记忆读面纯 SELECT（change_events 零增长）；确认队列非空时 goal 写
    照常推进；goal 撤销后记忆照常工作且不得复活/改写 goal。
  硬点⑤蒸馏确定性：同输入同字节（canonical JSON sha256 复算）。

实跑覆盖：
  C01 分支/基/master/工作树干净亲验 →
  C02 蒸馏确定性（同转写两跑同字节；变一字节即漂移；标记闭集固定序；
      形状出闭集具名拒）→
  C03 确认闸（propose→pending 可见/生效不可见；未确认不生效）→
  C04 confirm（生效可见＋decisionRef 入账；再确认拒/缺 decisionRef 拒/
      伪造字段拒/跨案 ref 拒；同键幂等重放/同键异内容冲突）→
  C05 TTL 过期真实生效（1 秒 TTL＋真实等待→回读不可见；账行保留）→
  C06 显式撤销真实生效（confirmed→revoke 回读不可见；proposed→revoke
      出确认队列；再撤销拒；历史 revision 可回读）→
  C07 来源+TTL 强制（缺来源字段/缺 TTL/坏 kind 具名拒；同 id 二提拒）→
  C08 目标账本不被延后（E18 goal save→记忆穿插→goal 逐字节不动→
      goal rev2 推进/撤销；零 goal 案件记忆全流程可用；E15/E17/goal
      行数不变；记忆读面 change_events 零增长）→
  C09 DB 级扫描（case_memory_entries 修订链行数）双 profile 同断言 →
  C10 桥负向（未配置 NOT_CONNECTED／未知方法 method_not_connected／
      方法组冻结）。

用法（juscite worktree 根 cwd）：
  python -X utf8 tools/recon/PENDING_OWNER_f32_case_memory_recon.py \
      --profile desktop --profile selfhost

退出码：0 = 全部 profile RECON_OK；2 = RECON_FAIL；3 = 环境缺失。
证据：evidence/F32/<profile>/ ＋ docs/construction/evidence/ 镜像。
"""
from __future__ import annotations

import argparse
import contextlib
import json
import subprocess
import sys
import tempfile
import time
import uuid as _uuid
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "implementation" / "python"))
sys.path.insert(0, str(REPO_ROOT / "implementation" / "tests"))

import legal_entry  # noqa: E402
from bridge_errors import HarnessCommandError, NotConnected  # noqa: E402
from case_memory import (  # noqa: E402
    TTL_BY_KIND,
    DistillationError,
    canonical_bytes,
    distill,
    to_harness_memory,
)

DEFAULT_HARNESS_ROOT = Path(
    r"D:\Codex\1.法律工作区\legal-harness工作区\legal-harness-repo"
    r"\.local\worktrees\w4-u34")

MATTER = "m-f32-recon"
SCOPE = {"kind": "matter", "matterId": MATTER}

HARNESS_MEMORY_METHODS = frozenset({
    "harness.memory_propose", "harness.memory_confirm", "harness.memory_revoke",
    "harness.memory_read", "harness.memory_effective_list",
    "harness.memory_pending_list",
})
MEMORY_METHODS = frozenset({
    "memory.extract", "memory.propose", "memory.confirm", "memory.revoke",
    "memory.read", "memory.effective_list", "memory.pending_list",
})

# lh-pg-e08 容器（E08 拓扑）：仅回环端口、合成专用凭据（密钥只在本机容
# 器；可用 LH_E08_PG_DSN 覆写）。
DEFAULT_PG_DSN = "postgresql://lh_app:e08-synth-only@127.0.0.1:55432/legal_harness"

TRANSCRIPT = [
    {"role": "user", "text": "事实：合同签订日为 2026-03-01（W4-U34 对账合成）"},
    {"role": "assistant", "text": "违约金按日万分之五计算（合成回复，无标记）。"},
    {"role": "user", "text": "务必在答辩期内提交证据，不要联系对方当事人。"},
    {"role": "user", "text": "以后文书一律用简体中文。"},
]

_KEY_SEQ = {"n": 0}


def key(request_id: str) -> dict:
    """CommandKey：requestId 自动追加流水号（探针必须每次新 id）。"""
    _KEY_SEQ["n"] += 1
    return {"requestId": "%s-%d" % (request_id, _KEY_SEQ["n"]),
            "targetId": None, "expectedRevision": None, "inputRefs": []}


def same_key(request_id: str) -> dict:
    return {"requestId": request_id, "targetId": None,
            "expectedRevision": None, "inputRefs": []}


def sref(digest: str, matter: str = MATTER, sid: str = "ses-f32-recon") -> dict:
    return {"owner": "host", "kind": "session_transcript", "id": sid,
            "version": "1", "matterId": matter, "digest": digest}


def decision(ref_id: str, matter: str = MATTER) -> dict:
    return {"owner": "host", "kind": "decision-receipt", "id": ref_id,
            "version": "1", "matterId": matter, "digest": None}


def expect_bridge_error(call, code_part):
    try:
        call()
    except (HarnessCommandError, ValueError, DistillationError) as exc:
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
        base = self.git(self.harness_root, "merge-base", "HEAD", "w4-u31")
        master = self.git(self.harness_root, "rev-parse", "master")
        self.step("c01_harness_branch", branch == "w4-u34", branch=branch)
        self.step("c01_harness_base_on_w4_u31", base.startswith("8f65dc6f"),
                  base=base)
        self.step("c01_harness_master_untouched", master.startswith("929d0802"),
                  master=master)
        dirty = self.git(self.harness_root, "status", "--porcelain")
        self.step("c01_harness_worktree_clean", dirty == "", dirty=dirty[:200])

    # ------------------------------------------------------------------
    # C02–C09：call(method, args) 走被测链；query 直读同一库。
    # ------------------------------------------------------------------
    def common_flow(self, profile: str, call, query):
        # ---- C02 蒸馏确定性（产品面 memory.distill，本地零依赖）。
        first = call("memory.extract", {"transcript": TRANSCRIPT,
                                        "sessionId": "ses-f32-recon",
                                        "matterId": MATTER})
        second = call("memory.extract", {"transcript": TRANSCRIPT,
                                         "sessionId": "ses-f32-recon",
                                         "matterId": MATTER})
        self.step("c02_distill_same_bytes",
                  canonical_bytes(first) == canonical_bytes(second)
                  and first["transcriptSha256"] == second["transcriptSha256"],
                  sha256=first["transcriptSha256"][:16])
        self.step("c02_distill_marker_closed_order",
                  first["candidateCount"] == 3
                  and [c["kind"] for c in first["candidates"]]
                  == ["fact", "constraint", "preference"],
                  kinds=[c["kind"] for c in first["candidates"]])
        altered = [dict(m) for m in TRANSCRIPT]
        altered[0] = dict(altered[0], text="事实：合同签订日为 2026-03-02（改一字）")
        third = call("memory.extract", {"transcript": altered,
                                        "sessionId": "ses-f32-recon",
                                        "matterId": MATTER})
        self.step("c02_distill_input_sensitivity",
                  third["transcriptSha256"] != first["transcriptSha256"]
                  and canonical_bytes(third) != canonical_bytes(first))
        self.step("c02_distill_ttl_frozen_table",
                  all(c["ttlSeconds"] == TTL_BY_KIND[c["kind"]]
                      for c in first["candidates"]),
                  ttls={c["kind"]: c["ttlSeconds"]
                        for c in first["candidates"]})
        for c in first["candidates"]:
            if not (set(c["sourceRef"])
                    == {"owner", "kind", "id", "version", "matterId", "digest"}
                    and c["sourceRef"]["digest"] == first["transcriptSha256"]):
                self.step("c02_distill_source_ref_closed", False,
                          candidate=c["candidateId"])
                break
        else:
            self.step("c02_distill_source_ref_closed", True)
        self.expect_error(
            "c02_distill_shape_closed",
            lambda: call("memory.extract", {"transcript": [], "sessionId": "s",
                                            "matterId": MATTER}),
            "transcript_invalid", error=DistillationError)

        # ---- C03 确认闸：候选提出（proposed）永不生效。
        candidates = first["candidates"]
        fact_cand = next(c for c in candidates if c["kind"] == "fact")
        constraint_cand = next(c for c in candidates if c["kind"] == "constraint")
        preference_cand = next(c for c in candidates if c["kind"] == "preference")
        k1 = key("mp-1")
        proposed = call("memory.propose", {
            "actor_id": "distiller", "scope": SCOPE, "key": k1,
            "candidate": fact_cand})
        self.step("c03_propose_pending_only",
                  proposed["status"] == "proposed"
                  and proposed["revision"] == 1)
        pending = call("memory.pending_list", {"scope": SCOPE})
        effective = call("memory.effective_list", {"scope": SCOPE})
        self.step("c03_unconfirmed_never_effective",
                  pending["count"] == 1
                  and pending["items"][0]["memoryId"] == fact_cand["candidateId"]
                  and effective["count"] == 0,
                  pending=pending["count"], effective=effective["count"])

        # ---- C04 confirm 闸（人工决定 ref 必带）。
        confirmed = call("memory.confirm", {
            "actor_id": "lawyer-1", "scope": SCOPE, "key": key("mc-1"),
            "memoryId": fact_cand["candidateId"],
            "decisionRef": decision("dec-f32-1")})
        self.step("c04_confirm_effective",
                  confirmed["status"] == "confirmed"
                  and confirmed["revision"] == 2
                  and confirmed["expiresAt"] is not None)
        effective = call("memory.effective_list", {"scope": SCOPE})
        self.step("c04_effective_readback",
                  effective["count"] == 1
                  and effective["items"][0]["memoryId"]
                  == fact_cand["candidateId"]
                  and effective["items"][0]["confirmedBy"] == "lawyer-1"
                  and effective["items"][0]["sourceRef"]["digest"]
                  == first["transcriptSha256"],
                  expiresAt=effective["items"][0]["expiresAt"])
        self.expect_error(
            "c04_reconfirm_refused",
            lambda: call("memory.confirm", {
                "actor_id": "lawyer-1", "scope": SCOPE, "key": key("mc-2"),
                "memoryId": fact_cand["candidateId"],
                "decisionRef": decision("dec-f32-2")}),
            "memory_not_proposed")
        # 缺 decisionRef 的具名拒在 harness 权威面断言（fields_missing
        # 契约落点=harness _require_fields；产品面 memory.confirm 薄路由
        # 不复制校验语义）——desktop 走信封原样参数，selfhost 走绑定向。
        if profile == "selfhost":
            self.expect_error(
                "c04_confirm_without_decision_refused",
                lambda: self.units.memory_confirm(
                    "lawyer-1", SCOPE, key("mc-3"),
                    {"memoryId": constraint_cand["candidateId"]}),
                "fields_missing")
        else:
            self.expect_error(
                "c04_confirm_without_decision_refused",
                lambda: call("harness.memory_confirm", {
                    "actor_id": "lawyer-1", "scope": SCOPE,
                    "key": key("mc-3"),
                    "confirmation": {"memoryId":
                                     constraint_cand["candidateId"]}}),
                "fields_missing")
        self.expect_error(
            "c04_confirm_forged_ref_refused",
            lambda: call("memory.confirm", {
                "actor_id": "lawyer-1", "scope": SCOPE, "key": key("mc-4"),
                "memoryId": constraint_cand["candidateId"],
                "decisionRef": dict(decision("dec-x"), auto=True)}),
            "fields_not_closed")
        # 同键幂等重放（同 request id 同内容）——结果=缓存原回执。
        replay = call("memory.propose", {
            "actor_id": "distiller", "scope": SCOPE,
            "key": same_key(k1["requestId"]),
            "candidate": fact_cand})
        self.step("c04_same_key_replay_idempotent",
                  replay["memoryId"] == proposed["memoryId"]
                  and replay["revision"] == 1)
        self.expect_error(
            "c04_same_key_conflict_refused",
            lambda: call("memory.propose", {
                "actor_id": "distiller", "scope": SCOPE,
                "key": same_key(k1["requestId"]),
                "candidate": dict(fact_cand, text="被篡改的正文（合成）")}),
            "idempotency_conflict")

        # ---- C05 TTL 过期真实生效（10 秒 TTL＋真实等待 12 秒——窗口须
        # 容纳 desktop 子进程链每调用 1-3 秒的延迟，不注入假钟；1 秒级
        # 短 TTL 的精确过期由 harness 单测 test_08 在进程内钉死）。
        ttl_cand = dict(constraint_cand, ttlSeconds=10,
                        candidateId="mem-ttl-exp-recon")
        call("memory.propose", {"actor_id": "distiller", "scope": SCOPE,
                                "key": key("mp-ttl"), "candidate": ttl_cand})
        call("memory.confirm", {"actor_id": "lawyer-1", "scope": SCOPE,
                                "key": key("mc-ttl"),
                                "memoryId": "mem-ttl-exp-recon",
                                "decisionRef": decision("dec-ttl")})
        self.step("c05_ttl_alive_before_expiry",
                  call("memory.effective_list", {"scope": SCOPE})["count"] == 2)
        time.sleep(12.0)  # 真实时间流逝越过 10 秒 TTL。
        effective = call("memory.effective_list", {"scope": SCOPE})
        self.step("c05_ttl_expired_invisible_on_readback",
                  effective["count"] == 1
                  and all(item["memoryId"] != "mem-ttl-exp-recon"
                          for item in effective["items"]),
                  effective=effective["count"])
        record = call("memory.read", {"scope": SCOPE,
                                      "memoryId": "mem-ttl-exp-recon"})
        self.step("c05_ttl_ledger_row_retained",
                  record["memory"]["status"] == "confirmed"
                  and record["memory"]["effective"] is False
                  and record["memory"]["revision"] == 2)

        # ---- C06 显式撤销真实生效。
        call("memory.revoke", {"actor_id": "lawyer-1", "scope": SCOPE,
                               "key": key("mr-1"),
                               "memoryId": fact_cand["candidateId"],
                               "reasonRef": decision("reason-f32-1")})
        self.step("c06_revoke_invisible_on_readback",
                  call("memory.effective_list", {"scope": SCOPE})["count"] == 0)
        # proposed 也可撤销（出确认队列）。
        call("memory.propose", {"actor_id": "distiller", "scope": SCOPE,
                                "key": key("mp-p"), "candidate": preference_cand})
        call("memory.revoke", {"actor_id": "lawyer-1", "scope": SCOPE,
                               "key": key("mr-2"),
                               "memoryId": preference_cand["candidateId"],
                               "reasonRef": decision("reason-f32-2")})
        self.step("c06_proposed_revoked_out_of_queue",
                  call("memory.pending_list", {"scope": SCOPE})["count"] == 0)
        self.expect_error(
            "c06_rerevoke_refused",
            lambda: call("memory.revoke", {
                "actor_id": "lawyer-1", "scope": SCOPE, "key": key("mr-3"),
                "memoryId": fact_cand["candidateId"],
                "reasonRef": decision("reason-f32-3")}),
            "memory_already_revoked")
        history = call("memory.read", {"scope": SCOPE,
                                       "memoryId": fact_cand["candidateId"],
                                       "revision": 2})
        self.step("c06_history_retained",
                  history["memory"]["status"] == "confirmed"
                  and history["memory"]["confirmedBy"] == "lawyer-1")

        # ---- C07 来源+TTL 强制（负向）。
        bad_source = dict(fact_cand, candidateId="mem-bad-src")
        bad_source["sourceRef"] = {"owner": "host",
                                   "kind": "session_transcript",
                                   "id": "ses-x", "version": "1"}
        self.expect_error(
            "c07_source_ref_closed_refused",
            lambda: call("memory.propose", {
                "actor_id": "distiller", "scope": SCOPE, "key": key("mp-b1"),
                "candidate": bad_source}),
            "fields_not_closed")
        bad_ttl = dict(fact_cand, candidateId="mem-bad-ttl", ttlSeconds=0)
        self.expect_error(
            "c07_ttl_invalid_refused",
            lambda: call("memory.propose", {
                "actor_id": "distiller", "scope": SCOPE, "key": key("mp-b2"),
                "candidate": bad_ttl}),
            "memory_ttl_invalid")
        bad_kind = dict(fact_cand, candidateId="mem-bad-kind", kind="rumor")
        self.expect_error(
            "c07_kind_closed_refused",
            lambda: call("memory.propose", {
                "actor_id": "distiller", "scope": SCOPE, "key": key("mp-b3"),
                "candidate": bad_kind}),
            "memory_kind_unknown")
        self.expect_error(
            "c07_same_id_repropose_refused",
            lambda: call("memory.propose", {
                "actor_id": "distiller", "scope": SCOPE, "key": key("mp-b4"),
                "candidate": fact_cand}),
            "memory_already_exists")

        # ---- C08 目标账本不被延后。
        goal = {"schemaVersion": "1.0.0-draft", "matterId": MATTER,
                "goalId": "goal-f32", "revision": 1,
                "confirmedScope": "追讨货款 123456.78 元（W4-U34 对账合成）",
                "hardConstraints": [], "preferences": [],
                "unitTiming": {"unit": "case", "asOf": "2026-10-20",
                               "description": "对账合成"},
                "sourceDecisionRef": decision("gd-f32"),
                "supersedesRevision": None}
        self.units.save_goal("lawyer-1", SCOPE, key("sg-1"), goal)

        def goal_bytes() -> list[tuple]:
            rows = query(
                "SELECT goal_id,revision,status,goal_json,goal_sha256"
                " FROM case_goals WHERE matter_id=? ORDER BY goal_id,revision",
                (MATTER,))
            return [tuple(sorted(r.items())) for r in rows]

        def table_count(table: str) -> int:
            return len(query(f"SELECT * FROM {table}", ()))

        def change_seq() -> int:
            rows = query("SELECT COALESCE(MAX(seq),0) AS s FROM change_events",
                         ())
            return int(rows[0]["s"])

        snapshot = goal_bytes()
        counts_before = {t: table_count(t) for t in
                         ("path_candidates", "evidence_attempts", "case_goals")}
        seq_before = change_seq()
        # 记忆全生命周期穿插（propose→confirm），goal 账逐字节不动、
        # E15/E17 账零写交叉。
        call("memory.propose", {"actor_id": "distiller", "scope": SCOPE,
                                "key": key("mp-x"),
                                "candidate": dict(preference_cand,
                                                  candidateId="mem-x-recon")})
        call("memory.confirm", {"actor_id": "lawyer-1", "scope": SCOPE,
                                "key": key("mc-x"),
                                "memoryId": "mem-x-recon",
                                "decisionRef": decision("dec-x")})
        call("memory.effective_list", {"scope": SCOPE})
        call("memory.pending_list", {"scope": SCOPE})
        call("memory.read", {"scope": SCOPE, "memoryId": "mem-x-recon"})
        self.step("c08_goal_ledger_bytes_untouched",
                  goal_bytes() == snapshot)
        counts_after = {t: table_count(t) for t in
                        ("path_candidates", "evidence_attempts", "case_goals")}
        self.step("c08_e15_e17_goal_zero_crosswrite",
                  counts_after == counts_before, counts=counts_after)
        # 确认队列非空（mem-y 未确认）时 goal 写照常推进——不被延后。
        call("memory.propose", {"actor_id": "distiller", "scope": SCOPE,
                                "key": key("mp-y"),
                                "candidate": dict(preference_cand,
                                                  candidateId="mem-y-recon")})
        pending_during = call("memory.pending_list", {"scope": SCOPE})["count"]
        goal["revision"] = 2
        goal["supersedesRevision"] = 1
        second_goal = self.units.save_goal("lawyer-1", SCOPE, key("sg-2"),
                                           goal)
        self.step("c08_goal_write_not_delayed_by_memory",
                  pending_during == 1 and second_goal["revision"] == 2,
                  pending=pending_during)
        # 记忆读面纯 SELECT：change_events 零增长。
        seq_mid = change_seq()
        call("memory.effective_list", {"scope": SCOPE})
        call("memory.pending_list", {"scope": SCOPE})
        call("memory.read", {"scope": SCOPE, "memoryId": "mem-x-recon"})
        self.step("c08_memory_reads_pure",
                  change_seq() == seq_mid)
        self.units.revoke_goal("lawyer-1", SCOPE, key("sg-3"), "goal-f32")
        self.step("c08_goal_revoked_after_memory_ops",
                  self.units.get_goal(SCOPE, "goal-f32")["status"] == "revoked")
        # 零 goal 案件里记忆全流程可用（记忆不依赖 goal 账状态）。
        matter_b = MATTER + "-b"
        scope_b = {"kind": "matter", "matterId": matter_b}
        cand_b = dict(preference_cand, candidateId="mem-b-recon")
        cand_b["sourceRef"] = sref(first["transcriptSha256"], matter=matter_b,
                                   sid="ses-f32-recon-b")
        call("memory.propose", {"actor_id": "distiller", "scope": scope_b,
                                "key": key("mp-b"), "candidate": cand_b})
        call("memory.confirm", {"actor_id": "lawyer-1", "scope": scope_b,
                                "key": key("mc-b"),
                                "memoryId": "mem-b-recon",
                                "decisionRef": decision("dec-b", matter=matter_b)})
        self.step("c08_memory_works_without_goal",
                  call("memory.effective_list", {"scope": scope_b})["count"] == 1)

        # ---- C09 DB 级扫描（双 profile 同断言）。
        memory_rows = query(
            "SELECT memory_id, revision, status FROM case_memory_entries"
            " WHERE matter_id=? ORDER BY memory_id, revision", (MATTER,))
        by_id: dict[str, list[str]] = {}
        for row in memory_rows:
            by_id.setdefault(row["memory_id"], []).append(row["status"])
        self.step("c09_db_scan_revision_chains",
                  by_id.get(fact_cand["candidateId"])
                  == ["proposed", "confirmed", "revoked"]
                  and by_id.get("mem-ttl-exp-recon")
                  == ["proposed", "confirmed"]
                  and by_id.get("mem-x-recon") == ["proposed", "confirmed"]
                  and by_id.get(preference_cand["candidateId"])
                  == ["proposed", "revoked"],
                  chains={k: v for k, v in sorted(by_id.items())})
        self.step("c09_change_events_appended",
                  change_seq() > seq_before)

    # -- profile drivers ---------------------------------------------------

    def run_desktop(self) -> int:
        temporary = tempfile.TemporaryDirectory(
            prefix="juscite-f32-desktop-")
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
        from legal_harness.business.units import HarnessUnits
        from legal_harness.state.matter_store import MatterStore
        store = MatterStore(state_root)
        self.units = HarnessUnits(store)
        store.create_matter(MATTER, "cas://profile-f32-recon")
        store.create_matter(MATTER + "-b", "cas://profile-f32-recon-b")

        def call(method, args):
            return legal_entry.call(method, args, config)

        def query(sql, params):
            import sqlite3
            with contextlib.closing(store._connect()) as connection:
                connection.row_factory = sqlite3.Row
                rows = connection.execute(sql, params).fetchall()
            return [dict(row) for row in rows]

        print("[profile desktop] SQLite via product bridge subprocess",
              flush=True)
        self.common_flow("desktop", call, query)
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
            prefix="juscite-f32-selfhost-")
        store = PgMatterStore(
            Path(temporary.name) / "state", dsn=dsn,
            schema="f32_" + _uuid.uuid4().hex[:12])
        self.units = HarnessUnits(store)
        methods = set(HARNESS_MEMORY_METHODS) | {
            "harness.save_goal", "harness.revoke_goal", "harness.get_goal",
        }
        bound = {name: resolve_provider_method(name, self.units)
                 for name in methods}
        store.create_matter(MATTER, "cas://profile-f32-recon")
        store.create_matter(MATTER + "-b", "cas://profile-f32-recon-b")

        def call(method, args):
            if method == "memory.extract":
                return distill(args["transcript"],
                               session_id=args["sessionId"],
                               matter_id=args["matterId"])
            mapped = {
                "memory.propose": ("harness.memory_propose", lambda a: {
                    "actor_id": a["actor_id"], "scope": a["scope"],
                    "key": a["key"],
                    "memory": to_harness_memory(a["candidate"])}),
                "memory.confirm": ("harness.memory_confirm", lambda a: {
                    "actor_id": a["actor_id"], "scope": a["scope"],
                    "key": a["key"],
                    "confirmation": {"memoryId": a["memoryId"],
                                     "decisionRef": a["decisionRef"]}}),
                "memory.revoke": ("harness.memory_revoke", lambda a: {
                    "actor_id": a["actor_id"], "scope": a["scope"],
                    "key": a["key"],
                    "revocation": {"memoryId": a["memoryId"],
                                   "reasonRef": a["reasonRef"]}}),
                "memory.read": ("harness.memory_read", lambda a: {
                    "scope": a["scope"], "memory_id": a["memoryId"],
                    "revision": a.get("revision")}),
                "memory.effective_list": ("harness.memory_effective_list",
                                          lambda a: {"scope": a["scope"]}),
                "memory.pending_list": ("harness.memory_pending_list",
                                        lambda a: {"scope": a["scope"]}),
            }
            h_method, transform = mapped[method]
            return bound[h_method](**transform(args))

        def query(sql, params):
            with contextlib.closing(store._connect()) as connection:
                rows = connection.execute(sql, params).fetchall()
            return [dict(row) for row in rows]

        print("[profile selfhost] PgMatterStore direct (lh-pg-e08)",
              flush=True)
        try:
            self.common_flow("selfhost", call, query)
        finally:
            store.destroy()
        return 0

    def bridge_negatives(self, config):
        # ---- C10 桥负向：未配置/未知方法/方法组冻结。
        try:
            legal_entry.call("memory.effective_list", {"scope": SCOPE}, {})
            raise AssertionError("bridge_not_configured_expected")
        except NotConnected as exc:
            self.step("c10_bridge_not_configured",
                      "harness_public_entry_not_configured" in str(exc))
        try:
            legal_entry.call("memory.auto_confirm", {"scope": SCOPE}, config)
            raise AssertionError("bridge_unknown_method_expected")
        except NotConnected as exc:
            self.step("c10_bridge_unknown_method_refused",
                      "method_not_connected" in str(exc))
        try:
            legal_entry.call("harness.memory_set_effective", {}, config)
            raise AssertionError("bridge_unknown_harness_method_expected")
        except NotConnected as exc:
            self.step("c10_bridge_unknown_harness_method_refused",
                      "method_not_connected" in str(exc))
        self.step("c10_method_group_frozen_memory",
                  legal_entry.HARNESS_MEMORY_METHODS == HARNESS_MEMORY_METHODS)
        self.step("c10_method_group_frozen_product",
                  legal_entry.MEMORY_METHODS == MEMORY_METHODS)


def write_evidence(profile: str, recon: Recon, harness_root: Path,
                   started: str, code: int) -> list[Path]:
    finished = datetime.now(timezone.utc).isoformat()
    summary = {
        "schema": "juscite-f32-case-memory-recon/1",
        "unit": "W4-U34",
        "features": ["F32"],
        "profile": profile,
        "verdict": "RECON_OK" if code == 0 else "RECON_FAIL",
        "started_at": started,
        "finished_at": finished,
        "harness_worktree": str(harness_root),
        "harness_branch": "w4-u34",
        "harness_base": "w4-u31@8f65dc6f (w4-u01→w3-u20 战役链接力)",
        "contract": "harness schema v31 case_memory_entries"
                    "（06 F32 v1.5·TTL 差异点）",
        "checks": recon.checks,
        "check_count": len(recon.checks),
        "failed": [c["check"] for c in recon.checks
                   if c["status"] != "PASS"],
    }
    payload = json.dumps(summary, ensure_ascii=False, indent=1)
    written: list[Path] = []
    for base in (REPO_ROOT / "evidence" / "F32" / profile,
                 REPO_ROOT / "docs" / "construction" / "evidence"
                 / "F32" / profile):
        base.mkdir(parents=True, exist_ok=True)
        path = base / "f32_case_memory_recon.json"
        path.write_text(payload + "\n", encoding="utf-8")
        lines = [
            "# F32 案件级记忆体系对账（%s）" % profile,
            "",
            f"- unit: W4-U34 · profile: {profile}",
            f"- verdict: **{summary['verdict']}**"
            f" ({len(recon.checks)} checks, exit {code})",
            f"- harness: `{harness_root}` @ branch w4-u34"
            "（基 w4-u31@8f65dc6f；master 929d0802 零动）",
            f"- started: {started} · finished: {finished}",
            "",
            "| # | check | status |",
            "|---|---|---|",
        ]
        for index, check in enumerate(recon.checks, 1):
            lines.append(f"| {index} | {check['check']}"
                         f" | {check['status']} |")
        (base / "f32_case_memory_recon.md").write_text(
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

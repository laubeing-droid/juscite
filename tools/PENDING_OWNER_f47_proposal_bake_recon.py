"""F47 提案/bake 不变式对账（W2b-U11）——双 profile（desktop/selfhost）。

对账对象：harness 分支 w2b-u11（基于 w2b-u01@0d5c79bc＝w2a-u05→w2a-u06
(F114)→w2b-u01(F25) 同链）的 public_entry --formalproposal-json 封闭径
——desktop profile 与产品桥（legal_entry → 子进程 public_entry）完全同
一条链（SQLite 状态根）；selfhost profile＝PgMatterStore 直连 lh-pg-e08
（resolve_provider_method 同一封闭注册）。全部合成材料：临时状态根、
合成 matter/正式交付物/提案/宿主实际文件字节；harness 检出零字节改动
（只运行其代码，git 只读命令核对分支）。

实跑覆盖（PENDING_OWNER_F47_proposal_bake）：
  正式链衔接（commit_formal 产物语义经 W05/F08/F114 面登记：register
  rev1=upload → add_material_revision(source=generated) rev2＝canonical
  base）→ 提案 pending（三分分开：canonical 头行一字不动、版本链零新增、
  提案只在提案账）→ 提案 CAS 回读 → 重复命中幂等返回 → base 漂移具名拒
  （不猜改）→ reject（人说不：canonical 不动、有决定记录、无 supersededBy）
  → 拒后新提案（canonical 未动 base 仍原样）→ 双提案取代（superseded
  分列：supersededBy 有值、无决定记录）→ 全接受 bake（canonical 前进
  rev3 source=user_accept＝F114 闭集、字节=提案字节、resultSource=
  proposal_bytes、decisionRef 同事务可回读）→ 部分接受 bake（rev4＝宿主
  实际文件字节、resultSource=host_result_bytes、提案原字节不改写）→
  决定态再决定拒（state_invalid）→ superseded 再决定拒 → F114 负向不
  回退（add_material_revision 自封 user_accept 拒）→ DB 级扫描（提案账
  与版本链分离、bake 行 100% decisionRef join）→ 桥负向（未配置
  NOT_CONNECTED／未知方法 method_not_connected／方法组冻结）。

用法：
  python -X utf8 tools/PENDING_OWNER_f47_proposal_bake_recon.py \
      --profile desktop --profile selfhost

退出码：0 = 全部 profile RECON_OK；2 = RECON_FAIL；3 = 环境缺失。
证据：docs/construction/evidence/F47/<profile>/ JSON＋MD。
"""
from __future__ import annotations

import argparse
import base64
import contextlib
import hashlib
import json
import subprocess
import sys
import tempfile
import uuid as _uuid
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "implementation" / "python"))

import legal_entry  # noqa: E402
from legal_entry import HarnessCommandError, NotConnected  # noqa: E402

DEFAULT_HARNESS_ROOT = Path(
    r"D:\Codex\1.法律工作区\legal-harness工作区\legal-harness-repo\.local\worktrees\w2b-u11")

MATTER = "m-f47-recon"
SCOPE = {"kind": "matter", "matterId": MATTER}
MATERIAL = "mat-formal-f47"
# lh-pg-e08 容器（E08 拓扑）：仅回环端口、合成专用凭据（LH_PG_PASSWORD
# 同源，密钥只在本机容器；可用 LH_E08_PG_DSN 覆写）。
DEFAULT_PG_DSN = "postgresql://lh_app:e08-synth-only@127.0.0.1:55432/legal_harness"

# 合成字节：正式交付物 base / 提案1 / 宿主部分接受实际文件 / 第二轮提案 /
# 第二轮宿主实际文件。
BASE_BYTES = "民事起诉状（F47 对账合成正式交付物）。诉讼请求：支付货款85,000元。\n".encode("utf-8")
PROPOSAL_1 = "民事起诉状（F47 对账合成提案1）。诉讼请求：支付货款85,000元及利息。\n".encode("utf-8")
PARTIAL_1 = "民事起诉状（F47 对账合成部分接受宿主实际文件）。诉讼请求：支付货款85,000元。\n".encode("utf-8")
PROPOSAL_2 = "民事起诉状（F47 对账合成提案2，第二轮修订）。\n".encode("utf-8")
HOST_RESULT_2 = "民事起诉状（F47 对账合成第二轮宿主实际文件）。\n".encode("utf-8")

F47_METHODS = frozenset({
    "harness.formal_propose", "harness.formal_decide",
    "harness.formal_proposal_read", "harness.formal_proposal_list",
})


def b64(content: bytes) -> str:
    return base64.b64encode(content).decode("ascii")


def key(request_id: str) -> dict:
    return {"requestId": request_id, "targetId": None,
            "expectedRevision": None, "inputRefs": []}


def ref(kind: str, ref_id: str) -> dict:
    return {"owner": "harness", "kind": kind, "id": ref_id,
            "version": "1", "matterId": MATTER}


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
        # desktop 桥链迟到码冒 HarnessCommandError；selfhost 直连公开面冒
        # UnitsError（ValueError 子类）——两者都只认 code_part 在码里。
        try:
            call()
        except error as exc:
            self.step(name, code_part in str(exc), code=str(exc))
            return str(exc)
        raise AssertionError(name + ": no typed error raised")

    def git(self, root: Path, *args: str) -> str:
        return subprocess.check_output(
            ["git", "-C", str(root), *args], text=True).strip()

    def branch_checks(self):
        branch = self.git(self.harness_root, "rev-parse", "--abbrev-ref", "HEAD")
        base = self.git(self.harness_root, "merge-base", "HEAD", "w2b-u01")
        master = self.git(self.harness_root, "rev-parse", "master")
        self.step("c01_harness_branch", branch == "w2b-u11", branch=branch)
        self.step("c01_harness_base_on_w2b_u01", base.startswith("0d5c79bc"),
                  base=base)
        self.step("c01_harness_master_untouched", master.startswith("929d0802"),
                  master=master)
        dirty = self.git(self.harness_root, "status", "--porcelain")
        self.step("c01_harness_worktree_clean", dirty == "", dirty=dirty[:200])

    # ------------------------------------------------------------------
    # C02–C12：call(method, args) 走被测链；query(sql, params) 直读库。
    # ------------------------------------------------------------------
    def common_flow(self, profile: str, call, query):
        # ---- C02 正式链衔接：交付物登记（W05/F08/F114 面）＝canonical base。
        call("harness.register_material", {
            "actor_id": "recon-lawyer", "scope": SCOPE, "key": key("reg-1"),
            "material": {"id": MATERIAL, "kind": "office",
                         "title": "民事起诉状（F47 对账合成）",
                         "bytesB64": b64(BASE_BYTES)}})
        call("harness.add_material_revision", {
            "actor_id": "recon-system", "scope": SCOPE, "key": key("reg-2"),
            "revision": {"materialId": MATERIAL, "bytesB64": b64(BASE_BYTES),
                         "baseRevision": 1, "source": "generated",
                         "note": "commit_formal 合成回执产物登记"}})
        listing = call("harness.formal_proposal_list",
                       {"scope": SCOPE, "material_id": MATERIAL})
        base_head = listing["canonical"]
        revisions_before = query(
            "SELECT COUNT(*) AS n FROM material_candidates WHERE matter_id=?"
            " AND material_id=?", (MATTER, MATERIAL))[0]["n"]
        self.step("c02_formal_deliverable_base",
                  base_head["revision"] == 2
                  and base_head["source"] == "generated"
                  and base_head["sha256"] == hashlib.sha256(
                      BASE_BYTES).hexdigest()
                  and revisions_before == 2,
                  head=base_head["revision"], source=base_head["source"])

        # ---- C03 提案 pending：三分分开（canonical 一字不动、版本链零增）。
        proposal_1 = call("harness.formal_propose", {
            "actor_id": "recon-assistant", "scope": SCOPE, "key": key("fp-1"),
            "proposal": {"proposalId": "fp-1", "materialId": MATERIAL,
                         "baseRevision": 2, "bytesB64": b64(PROPOSAL_1),
                         "channel": "word", "author": "assistant-synth",
                         "quotes": [{"text": "诉讼请求：支付货款85,000元",
                                     "reason": "金额主张改为含利息",
                                     "sourceRef": ref("material", MATERIAL)}],
                         "note": "全合成提案"}})
        listing = call("harness.formal_proposal_list",
                       {"scope": SCOPE, "material_id": MATERIAL})
        canonical_pending = listing["canonical"]
        revisions_pending = query(
            "SELECT COUNT(*) AS n FROM material_candidates WHERE matter_id=?"
            " AND material_id=?", (MATTER, MATERIAL))[0]["n"]
        ledger_pending = query(
            "SELECT COUNT(*) AS n FROM formal_proposals WHERE matter_id=?",
            (MATTER,))[0]["n"]
        pending_row = listing["proposals"][0]
        self.step("c03_pending_three_way_separated",
                  canonical_pending["revision"] == 2
                  and canonical_pending["sha256"] == base_head["sha256"]
                  and revisions_pending == revisions_before
                  and ledger_pending == 1
                  and pending_row["state"] == "pending"
                  and pending_row["baseRevision"] == 2
                  and pending_row["baseCasRef"] == base_head["casRef"]
                  and pending_row["decisionRef"] is None
                  and pending_row["supersededBy"] is None
                  and proposal_1["duplicate"] is False,
                  canonical_rev=canonical_pending["revision"],
                  revisions=revisions_pending, ledger=ledger_pending)

        # ---- C04 提案 CAS 回读（随读必验，字节逐位）。
        readback = call("harness.formal_proposal_read",
                        {"scope": SCOPE, "proposal_id": "fp-1"})
        self.step("c04_proposal_bytes_readback",
                  readback["bytesB64"] == b64(PROPOSAL_1)
                  and readback["proposalSha256"]
                  == hashlib.sha256(PROPOSAL_1).hexdigest()
                  and readback["quotes"][0]["text"] == "诉讼请求：支付货款85,000元",
                  sha256=readback["proposalSha256"][:16])

        # ---- C05 重复命中：同 material＋base＋字节 pending 已存在＝原样返回。
        dup = call("harness.formal_propose", {
            "actor_id": "recon-assistant", "scope": SCOPE, "key": key("fp-dup"),
            "proposal": {"proposalId": "fp-dup", "materialId": MATERIAL,
                         "baseRevision": 2, "bytesB64": b64(PROPOSAL_1),
                         "channel": "machine", "author": "assistant-synth",
                         "quotes": [], "note": None}})
        ledger_after_dup = query(
            "SELECT COUNT(*) AS n FROM formal_proposals WHERE matter_id=?",
            (MATTER,))[0]["n"]
        self.step("c05_duplicate_idempotent",
                  dup["duplicate"] is True
                  and dup["proposal"]["proposalId"] == "fp-1"
                  and ledger_after_dup == 1,
                  ledger=ledger_after_dup)

        # ---- C06 base 漂移：具名拒、零新行（不猜改、不自动重锚）。
        self.expect_error("c06_base_drift_refused", lambda: call(
            "harness.formal_propose", {
                "actor_id": "recon-assistant", "scope": SCOPE,
                "key": key("fp-drift"),
                "proposal": {"proposalId": "fp-drift",
                             "materialId": MATERIAL, "baseRevision": 1,
                             "bytesB64": b64(PROPOSAL_1),
                             "channel": "machine", "author": "a",
                             "quotes": [], "note": None}}),
            "formal_proposal_base_stale:1:2")
        ledger_after_drift = query(
            "SELECT COUNT(*) AS n FROM formal_proposals WHERE matter_id=?",
            (MATTER,))[0]["n"]
        self.step("c06_drift_no_row_created", ledger_after_drift == 1,
                  ledger=ledger_after_drift)

        # ---- C07 reject＝人说不：canonical 一字不动、决定记录、无 supersededBy。
        rejected = call("harness.formal_decide", {
            "actor_id": "recon-lawyer", "scope": SCOPE, "key": key("dec-rej"),
            "decision": {"proposalId": "fp-1", "action": "reject",
                         "reasonRef": ref("reason", "r-rej"),
                         "receiptRef": ref("receipt", "rc-rej")}})
        listing = call("harness.formal_proposal_list",
                       {"scope": SCOPE, "material_id": MATERIAL})
        rejected_row = [item for item in listing["proposals"]
                        if item["proposalId"] == "fp-1"][0]
        revisions_after_reject = query(
            "SELECT COUNT(*) AS n FROM material_candidates WHERE matter_id=?"
            " AND material_id=?", (MATTER, MATERIAL))[0]["n"]
        self.step("c07_reject_canonical_untouched",
                  rejected["canonical"]["revision"] == 2
                  and rejected["canonical"]["sha256"]
                  == base_head["sha256"]
                  and revisions_after_reject == revisions_before
                  and rejected_row["state"] == "rejected"
                  and rejected_row["decisionRef"]["action"] == "reject"
                  and rejected_row["supersededBy"] is None
                  and rejected_row["bakedRevision"] is None,
                  canonical_rev=rejected["canonical"]["revision"],
                  revisions=revisions_after_reject)

        # ---- C08 拒后新提案（canonical 未动 base 仍 2）＋双提案取代分列。
        call("harness.formal_propose", {
            "actor_id": "recon-assistant", "scope": SCOPE, "key": key("fp-2"),
            "proposal": {"proposalId": "fp-2", "materialId": MATERIAL,
                         "baseRevision": 2, "bytesB64": b64(PROPOSAL_2),
                         "channel": "machine", "author": "assistant-synth",
                         "quotes": [], "note": None}})
        superseder = call("harness.formal_propose", {
            "actor_id": "recon-assistant", "scope": SCOPE, "key": key("fp-3"),
            "proposal": {"proposalId": "fp-3", "materialId": MATERIAL,
                         "baseRevision": 2, "bytesB64": b64(PROPOSAL_1),
                         "channel": "word", "author": "assistant-synth",
                         "quotes": [], "note": None}})
        listing = call("harness.formal_proposal_list",
                       {"scope": SCOPE, "material_id": MATERIAL})
        by_id = {item["proposalId"]: item for item in listing["proposals"]}
        self.step("c08_superseded_distinct_from_rejected",
                  by_id["fp-2"]["state"] == "superseded"
                  and by_id["fp-2"]["supersededBy"] == "fp-3"
                  and by_id["fp-2"]["decisionRef"] is None
                  and by_id["fp-1"]["state"] == "rejected"
                  and by_id["fp-3"]["state"] == "pending"
                  and superseder["supersededCount"] == 1
                  and listing["stateCounts"] == {
                      "accepted": 0, "pending": 1,
                      "rejected": 1, "superseded": 1},
                  counts=listing["stateCounts"])
        # 决定过的提案再决定／被取代的提案决定：状态机具名拒。
        self.expect_error("c08_decided_redecide_refused", lambda: call(
            "harness.formal_decide", {
                "actor_id": "recon-lawyer", "scope": SCOPE,
                "key": key("dec-rej-2"),
                "decision": {"proposalId": "fp-1", "action": "accept",
                             "reasonRef": ref("reason", "r-x"),
                             "receiptRef": ref("receipt", "rc-x")}}),
            "formal_proposal_state_invalid:rejected")
        self.expect_error("c08_superseded_decide_refused", lambda: call(
            "harness.formal_decide", {
                "actor_id": "recon-lawyer", "scope": SCOPE,
                "key": key("dec-sup"),
                "decision": {"proposalId": "fp-2", "action": "accept",
                             "reasonRef": ref("reason", "r-x"),
                             "receiptRef": ref("receipt", "rc-x")}}),
            "formal_proposal_state_invalid:superseded")

        # ---- C09 全接受 bake：canonical 前进 rev3＝user_accept（F114 闭集）。
        accepted = call("harness.formal_decide", {
            "actor_id": "recon-lawyer", "scope": SCOPE, "key": key("dec-acc"),
            "decision": {"proposalId": "fp-3", "action": "accept",
                         "reasonRef": ref("reason", "r-acc"),
                         "receiptRef": ref("receipt", "rc-acc")}})
        baked = call("harness.read_material", {
            "scope": SCOPE, "material_id": MATERIAL, "revision": 3})
        self.step("c09_full_accept_bakes_user_accept",
                  accepted["canonical"]["revision"] == 3
                  and accepted["canonical"]["source"] == "user_accept"
                  and baked["sha256"] == hashlib.sha256(PROPOSAL_1).hexdigest()
                  and baked["bytesB64"] == b64(PROPOSAL_1)
                  and baked["source"] == "user_accept"
                  and baked["baseRevision"] == 2
                  and baked["resultSource"] == "proposal_bytes"
                  and baked["proposalRef"]["proposalId"] == "fp-3"
                  and baked["decisionRef"]["decisionId"]
                  == accepted["decisionId"]
                  and accepted["proposal"]["bakedRevision"] == 3,
                  canonical_rev=accepted["canonical"]["revision"],
                  source=baked["source"])

        # ---- C10 部分接受 bake：宿主重读实际文件回流 CAS 新版本。
        call("harness.formal_propose", {
            "actor_id": "recon-assistant", "scope": SCOPE, "key": key("fp-4"),
            "proposal": {"proposalId": "fp-4", "materialId": MATERIAL,
                         "baseRevision": 3, "bytesB64": b64(PROPOSAL_2),
                         "channel": "word", "author": "assistant-synth",
                         "quotes": [], "note": None}})
        partial = call("harness.formal_decide", {
            "actor_id": "recon-lawyer", "scope": SCOPE, "key": key("dec-par"),
            "decision": {"proposalId": "fp-4", "action": "accept",
                         "reasonRef": ref("reason", "r-par"),
                         "receiptRef": ref("receipt", "rc-par"),
                         "resultBytesB64": b64(HOST_RESULT_2)}})
        baked4 = call("harness.read_material", {
            "scope": SCOPE, "material_id": MATERIAL, "revision": 4})
        proposal4 = call("harness.formal_proposal_read",
                         {"scope": SCOPE, "proposal_id": "fp-4"})
        chain = [row["source"] for row in call("harness.list_materials", {
            "scope": SCOPE})["materials"][0]["revisions"]]
        self.step("c10_partial_accept_host_result_bytes",
                  partial["canonical"]["revision"] == 4
                  and baked4["sha256"]
                  == hashlib.sha256(HOST_RESULT_2).hexdigest()
                  and baked4["bytesB64"] == b64(HOST_RESULT_2)
                  and baked4["resultSource"] == "host_result_bytes"
                  and baked4["proposalRef"]["proposalSha256"]
                  == hashlib.sha256(PROPOSAL_2).hexdigest()
                  and proposal4["bytesB64"] == b64(PROPOSAL_2)
                  and chain == ["upload", "generated", "user_accept",
                                "user_accept"],
                  chain=chain)

        # ---- C11 F114 负向不回退：user_accept 不可经材料面自封。
        self.expect_error("c11_user_accept_not_self_declorable", lambda: call(
            "harness.add_material_revision", {
                "actor_id": "recon-assistant", "scope": SCOPE,
                "key": key("fake-bake"),
                "revision": {"materialId": MATERIAL,
                             "bytesB64": b64(PROPOSAL_1),
                             "baseRevision": 4, "source": "user_accept"}}),
            "material_source_not_writable")

        # ---- C12 DB 级扫描：提案账与版本链分离；bake 行 100% 有决定。
        # CASE WHEN 造整数（PG 上裸 LIKE 布尔会以 't'/'f' 文本回来，'f'
        # 也是 truthy——跨后端必须显式整形）。
        ledger = query(
            "SELECT proposal_id, state, superseded_by, baked_revision,"
            " decision_ref_present FROM (SELECT proposal_id, state,"
            " superseded_by, baked_revision,"
            " CASE WHEN proposal_json LIKE '%decisionRef%' THEN 1 ELSE 0 END"
            " AS decision_ref_present"
            " FROM formal_proposals WHERE matter_id=?)"
            " ORDER BY proposal_id", (MATTER,))
        states = {row["proposal_id"]: row["state"] for row in ledger}
        baked_rows = query(
            "SELECT COUNT(*) AS n FROM material_candidates WHERE matter_id=?"
            " AND material_id=? AND CASE WHEN material_json"
            " LIKE '%user_accept%' THEN 1 ELSE 0 END = 1",
            (MATTER, MATERIAL))[0]["n"]
        total = query(
            "SELECT COUNT(*) AS n FROM material_candidates WHERE matter_id=?"
            " AND material_id=?", (MATTER, MATERIAL))[0]["n"]
        decided = [row for row in ledger
                   if row["state"] in ("accepted", "rejected")]
        superseded = [row for row in ledger if row["state"] == "superseded"]
        self.step("c12_ledger_vs_chain_separated",
                  states == {"fp-1": "rejected", "fp-2": "superseded",
                             "fp-3": "accepted", "fp-4": "accepted"},
                  states=states,
                  note="fp-dup 重复命中不落行；fp-drift 漂移拒不落行")
        self.step("c12_decision_join_complete",
                  all(row["decision_ref_present"] for row in decided)
                  and all(not row["decision_ref_present"]
                          for row in superseded)
                  and baked_rows == 2 and total == 4,
                  decided=[row["proposal_id"] for row in decided],
                  superseded=[row["proposal_id"] for row in superseded],
                  user_accept_rows=baked_rows, total=total)

    def bridge_negatives(self, config):
        # ---- C13 桥负向：未配置/未知方法/方法组冻结。
        try:
            legal_entry.call("harness.formal_propose",
                             {"scope": SCOPE}, {})
            raise AssertionError("bridge_not_configured_expected")
        except NotConnected as exc:
            self.step("c13_bridge_not_configured",
                      "harness_public_entry_not_configured" in str(exc))
        try:
            legal_entry.call("harness.formal_bake",
                             {"scope": SCOPE}, config)
            raise AssertionError("bridge_unknown_method_expected")
        except NotConnected as exc:
            self.step("c13_bridge_unknown_method_refused",
                      "method_not_connected" in str(exc))
        self.step("c13_method_group_frozen",
                  legal_entry.HARNESS_FORMAL_PROPOSAL_METHODS == F47_METHODS)

    # -- profile drivers ---------------------------------------------------

    def run_desktop(self) -> int:
        temporary = tempfile.TemporaryDirectory(prefix="juscite-f47-desktop-")
        state_root = Path(temporary.name) / "state"
        state_root.mkdir(parents=True)
        registration = Path(temporary.name) / "service-local.json"
        registration.write_text(json.dumps(
            {"url": "http://127.0.0.1:1", "password": "synthetic-recon"}),
            encoding="utf-8")
        config = {
            "harness_public_entry":
                str(self.harness_root / "tools/workflow-tools/harness/public_entry.py"),
            "harness_target": "opencode",
            "harness_state_root": str(state_root),
            "harness_service_registration": str(registration),
            "harness_timeout": 120,
        }
        for path in (str(self.harness_root / "src"),
                     str(self.harness_root / "tools/workflow-tools")):
            if path not in sys.path:
                sys.path.insert(0, path)
        from legal_harness.state.matter_store import MatterStore
        store = MatterStore(state_root)
        store.create_matter(MATTER, "cas://profile-f47-recon")

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
                     str(self.harness_root),
                     str(self.harness_root / "tests")):
            if path not in sys.path:
                sys.path.insert(0, path)
        import contextlib

        from legal_harness.business.provider_registry import (
            resolve_provider_method,
        )
        from legal_harness.business.units import HarnessUnits
        from legal_harness.state.pg_store import PgMatterStore

        temporary = tempfile.TemporaryDirectory(prefix="juscite-f47-selfhost-")
        store = PgMatterStore(
            Path(temporary.name) / "state", dsn=dsn,
            schema="f47_" + _uuid.uuid4().hex[:12])
        units = HarnessUnits(store)
        bound = {name: resolve_provider_method(name, units)
                 for name in F47_METHODS}
        bound["harness.register_material"] = resolve_provider_method(
            "harness.register_material", units)
        bound["harness.add_material_revision"] = resolve_provider_method(
            "harness.add_material_revision", units)
        bound["harness.read_material"] = resolve_provider_method(
            "harness.read_material", units)
        bound["harness.list_materials"] = resolve_provider_method(
            "harness.list_materials", units)
        store.create_matter(MATTER, "cas://profile-f47-recon")

        def call(method, args):
            return bound[method](**args)

        def query(sql, params):
            with contextlib.closing(store._connect()) as connection:
                rows = connection.execute(sql, params).fetchall()
            return [dict(row) for row in rows]

        print("[profile selfhost] PgMatterStore direct (lh-pg-e08)",
              flush=True)
        self.common_flow("selfhost", call, query)
        store.destroy()
        return 0


def write_evidence(profile: str, recon: Recon, harness_root: Path,
                   started: str, code: int) -> Path:
    evidence_dir = REPO_ROOT / "docs" / "construction" / "evidence" / "F47" \
        / profile
    evidence_dir.mkdir(parents=True, exist_ok=True)
    finished = datetime.now(timezone.utc).isoformat()
    summary = {
        "schema": "juscite-f47-proposal-bake-recon/1",
        "unit": "W2b-U11",
        "feature": "F47",
        "profile": profile,
        "verdict": "RECON_OK" if code == 0 else "RECON_FAIL",
        "started_at": started,
        "finished_at": finished,
        "harness_worktree": str(harness_root),
        "harness_branch": "w2b-u11",
        "harness_base": "w2b-u01@0d5c79bc (w2a-u05→w2a-u06/F114→w2b-u01/F25)",
        "checks": recon.checks,
        "check_count": len(recon.checks),
        "failed": [c["check"] for c in recon.checks
                   if c["status"] != "PASS"],
    }
    payload = json.dumps(summary, ensure_ascii=False, indent=1)
    (evidence_dir / "f47_proposal_bake_recon.json").write_text(
        payload + "\n", encoding="utf-8")
    lines = [f"# F47 提案/bake 不变式 recon（{profile}）",
             "",
             f"- unit: W2b-U11 · profile: {profile}",
             f"- verdict: **{summary['verdict']}**"
             f" ({len(recon.checks)} checks, exit {code})",
             f"- harness: `{harness_root}` @ branch w2b-u11"
             "（基 w2b-u01@0d5c79bc；master 929d0802 零动）",
             f"- started: {started} · finished: {finished}",
             "",
             "| # | check | status |",
             "|---|---|---|"]
    for index, check in enumerate(recon.checks, 1):
        lines.append(f"| {index} | {check['check']}"
                     f" | {check['status']} |")
    lines += ["", "全部合成材料；desktop＝产品桥子进程全链（SQLite 状态根），"
              "selfhost＝PgMatterStore 直连 lh-pg-e08（同一封闭注册）。"]
    (evidence_dir / "f47_proposal_bake_recon.md").write_text(
        "\n".join(lines) + "\n", encoding="utf-8")
    return evidence_dir


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--profile", action="append",
                        choices=["desktop", "selfhost"])
    parser.add_argument("--harness-root", type=Path,
                        default=DEFAULT_HARNESS_ROOT)
    parser.add_argument("--pg-dsn", default=DEFAULT_PG_DSN)
    args = parser.parse_args()
    profiles = args.profile or ["desktop"]
    if not (args.harness_root / "tools/workflow-tools/harness/public_entry.py").exists():
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

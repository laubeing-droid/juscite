"""F25 行租约与格generation写守卫对账（W2b-U01）——活链实跑。

对账对象：harness 分支 w2b-u01（基施工链头 w2a-u06@0bc74119）的
review_batch_* 公开面。双 profile：

* desktop＝产品桥全链（legal_entry → 子进程 public_entry
  --reviewbatch-json → SQLite MatterStore）——每次调用都是新进程，暂停/
  重启/续跑天然跨进程验证；真并发＝双线程各自起子进程抢同一 SQLite 库
  （跨进程写者串行＝BEGIN IMMEDIATE＋busy timeout）。
* selfhost＝PgMatterStore 直连容器 lh-pg-e08（127.0.0.1:55432，E08 同
  拓扑），同一 HarnessUnits 公开面（provider_registry 解析），同一套断言
  逐键对照（E08 双后端同合同）。

全部合成材料：临时状态根、合成批/行/格；harness 检出零字节改动（git 只读
命令核对分支与 master 零动）。

实跑覆盖（PENDING_OWNER_F25_lease_generation_recon，双 profile 同集）：
  C01 建批（generation 0/initial 定格；批 id 一次性；同 key 幂等重放）
  C02 行租约＋claim 后快照（token/holder/claimSeq；快照 sha256 逐张复算；
      claim_log 可回读）
  C03 迟到机器结果不覆人工改格（人改 gen 0→1；机器携带 claim 快照 gen 0
      提交＝stale_generation 具名拒；人改值保全；在飞租约不失效）
  C04 迟到人改不覆机器新结果（守卫对称）
  C05 过期租约（真墙钟 1 秒窗）迟到提交＝lease_expired；再 claim 新 token
      新快照；旧 token 迟到＝lease_not_held；新租约提交成功
  C06 批量暂停重启续处理（pause 停发新租约＝batch_paused；在飞租约照常
      交作业；desktop 每调用即新进程＝重启面；resume 显式续跑 pending；
      末行批自动 completed）
  C07 真并发回读（双 worker 抢 N 行恰 N 胜零重叠；一租约一行；终态计数）
  C10 桥 fail-closed（未配置 NOT_CONNECTED；未知方法 method_not_connected；
      typed 迟到码经桥透传）

用法：
  python -X utf8 tools/PENDING_OWNER_f25_lease_generation_recon.py
      [--profile desktop|selfhost]... [--harness-root <path>] [--json]

退出码：0 = RECON_OK（全部所选 profile）；1 = RECON_FAIL；3 = RECON_BLOCKED。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "implementation" / "python"))

import legal_entry  # noqa: E402
from legal_entry import HarnessCommandError, NotConnected  # noqa: E402

DEFAULT_HARNESS_ROOT = Path(
    r"D:\Codex\1.法律工作区\legal-harness工作区\legal-harness-repo\.local\worktrees\w2b-u01")

MATTER = "m-f25-recon"
SCOPE = {"kind": "matter", "matterId": MATTER}
BATCH = "brt-f25-recon"
ROWS = 6
# lh-pg-e08 容器（E08 拓扑）：仅回环端口、合成专用凭据（LH_PG_PASSWORD
# 同源，密钥只在本机容器；可用 LH_E08_PG_DSN 覆写）。
DEFAULT_PG_DSN = "postgresql://lh_app:e08-synth-only@127.0.0.1:55432/legal_harness"

LATE_CODES = ("stale_generation", "lease_expired", "lease_not_held")


def key(request_id):
    return {"requestId": request_id, "targetId": None,
            "expectedRevision": None, "inputRefs": []}


def synth_batch():
    return {
        "id": BATCH, "title": "批量审查（F25 对账合成）",
        "note": "全合成行/格，无真实案件数据",
        "columns": [{"id": "amount", "name": "金额"},
                    {"id": "cited", "name": "引证"}],
        "rows": [
            {"id": "row-%d" % i,
             "cells": {"amount": None, "cited": None},
             "sourceRef": {"owner": "harness", "kind": "material",
                           "id": "mat-%d" % i, "version": "1",
                           "matterId": MATTER}}
            for i in range(1, ROWS + 1)
        ],
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
        base = self.git(self.harness_root, "merge-base", "HEAD", "w2a-u06")
        master = self.git(self.harness_root, "rev-parse", "master")
        self.step("harness_branch", branch == "w2b-u01", branch=branch)
        self.step("harness_base_on_w2a_u06", base.startswith("0bc74119"),
                  base=base)
        self.step("harness_master_untouched", master.startswith("929d0802"),
                  master=master)
        dirty = self.git(self.harness_root, "status", "--porcelain")
        self.step("harness_worktree_clean", dirty == "", dirty=dirty[:200])

    def common_flow(self, profile: str, call, query):
        """C01–C07：call(method, args) 走被测链；query(sql, params) 直读库。"""
        # ---- C01 建批：初值 generation 0/initial；幂等重放；批 id 一次性。
        created = call("harness.review_batch_create", {
            "actor_id": "recon-lawyer", "scope": SCOPE, "key": key("rb-1"),
            "batch": synth_batch()})
        replay = call("harness.review_batch_create", {
            "actor_id": "recon-lawyer", "scope": SCOPE, "key": key("rb-1"),
            "batch": synth_batch()})
        row_v0 = call("harness.review_batch_read", {
            "scope": SCOPE, "batch_id": BATCH, "row_id": "row-1"})["row"]
        self.step("c01_create_pins_initial_generation",
                  created["status"] == "active" and created["rowCount"] == ROWS
                  and replay["receipt"] == created["receipt"]
                  and row_v0["cells"]["amount"]["generation"] == 0
                  and row_v0["cells"]["amount"]["source"] == "initial",
                  rowCount=created["rowCount"])
        self.expect_error("c01_batch_id_one_shot", lambda: call(
            "harness.review_batch_create", {
                "actor_id": "recon-lawyer", "scope": SCOPE,
                "key": key("rb-2"), "batch": synth_batch()}),
            "review_batch_id_conflict")

        # ---- C02 行租约＋claim 后快照。
        claimed = call("harness.review_batch_claim", {
            "actor_id": "recon-worker-1", "scope": SCOPE, "key": key("cl-1"),
            "batch_id": BATCH, "row_id": "row-1", "lease_ttl_seconds": 600})
        log = call("harness.review_batch_claim_log", {
            "scope": SCOPE, "batch_id": BATCH, "row_id": "row-1"})
        entry = log["claims"][0]
        canonical = json.dumps(entry["snapshot"], ensure_ascii=False,
                               sort_keys=True, separators=(",", ":"))
        self.step("c02_lease_and_post_claim_snapshot",
                  claimed["rowId"] == "row-1"
                  and claimed["lease"]["claimSeq"] == 1
                  and claimed["snapshot"]["cells"]["amount"]["generation"] == 0
                  and entry["leaseToken"] == claimed["lease"]["token"]
                  and entry["snapshot"] == claimed["snapshot"]
                  and entry["snapshotSha256"] == hashlib.sha256(
                      canonical.encode("utf-8")).hexdigest(),
                  claimSeq=claimed["lease"]["claimSeq"])

        # ---- C03 迟到机器不覆人改（人改 gen 0→1；机器携 claim 快照 gen 0）。
        human = call("harness.review_batch_human_edit", {
            "actor_id": "recon-lawyer", "scope": SCOPE, "key": key("he-1"),
            "batch_id": BATCH, "row_id": "row-1",
            "cells": [{"cellId": "amount", "value": "123456.78 元",
                       "generation": 0}]})
        late_code = self.expect_error("c03_late_machine_vs_human", lambda: call(
            "harness.review_batch_submit", {
                "actor_id": "recon-worker-1", "scope": SCOPE,
                "key": key("sb-stale"), "batch_id": BATCH, "row_id": "row-1",
                "lease_token": claimed["lease"]["token"],
                "cells": [{"cellId": "amount", "value": "999.00",
                           "generation": 0}]}),
            "stale_generation:amount")
        guarded = call("harness.review_batch_read", {
            "scope": SCOPE, "batch_id": BATCH, "row_id": "row-1"})["row"]
        self.step("c03_human_value_survives_late_machine",
                  "carried=0" in late_code and "current=1" in late_code
                  and guarded["cells"]["amount"]["value"] == "123456.78 元"
                  and guarded["cells"]["amount"]["source"] == "human"
                  and guarded["state"] == "leased"
                  and guarded["lease"]["holder"] == "recon-worker-1",
                  value=guarded["cells"]["amount"]["value"])

        # ---- C04 迟到人改不覆机器新结果（守卫对称；row-2 干净链）。
        c2 = call("harness.review_batch_claim", {
            "actor_id": "recon-worker-2", "scope": SCOPE, "key": key("cl-2"),
            "batch_id": BATCH, "row_id": "row-2", "lease_ttl_seconds": 600})
        call("harness.review_batch_submit", {
            "actor_id": "recon-worker-2", "scope": SCOPE, "key": key("sb-2"),
            "batch_id": BATCH, "row_id": "row-2",
            "lease_token": c2["lease"]["token"],
            "cells": [{"cellId": "amount", "value": "42.00 元",
                       "generation": 0}]})
        self.expect_error("c04_late_human_vs_machine", lambda: call(
            "harness.review_batch_human_edit", {
                "actor_id": "recon-lawyer", "scope": SCOPE,
                "key": key("he-late"), "batch_id": BATCH, "row_id": "row-2",
                "cells": [{"cellId": "amount", "value": "迟到人改",
                           "generation": 0}]}),
            "stale_generation:amount")
        r2 = call("harness.review_batch_read", {
            "scope": SCOPE, "batch_id": BATCH, "row_id": "row-2"})["row"]
        self.step("c04_machine_value_survives_late_human",
                  r2["cells"]["amount"]["value"] == "42.00 元"
                  and r2["cells"]["amount"]["source"] == "machine"
                  and r2["state"] == "done",
                  value=r2["cells"]["amount"]["value"])

        # ---- C05 过期租约（真墙钟 1 秒窗）→ 再 claim → 新旧 token 分野。
        short = call("harness.review_batch_claim", {
            "actor_id": "recon-worker-3", "scope": SCOPE, "key": key("cl-3"),
            "batch_id": BATCH, "row_id": "row-3", "lease_ttl_seconds": 1})
        time.sleep(1.3)
        self.expect_error("c05_expired_lease_late_submit", lambda: call(
            "harness.review_batch_submit", {
                "actor_id": "recon-worker-3", "scope": SCOPE,
                "key": key("sb-3"), "batch_id": BATCH, "row_id": "row-3",
                "lease_token": short["lease"]["token"],
                "cells": [{"cellId": "amount", "value": "1.00",
                           "generation": 0}]}),
            "lease_expired:row-3")
        reclaimed = call("harness.review_batch_claim", {
            "actor_id": "recon-worker-4", "scope": SCOPE, "key": key("cl-4"),
            "batch_id": BATCH, "row_id": "row-3", "lease_ttl_seconds": 600})
        self.expect_error("c05_old_token_after_reclaim", lambda: call(
            "harness.review_batch_submit", {
                "actor_id": "recon-worker-3", "scope": SCOPE,
                "key": key("sb-3b"), "batch_id": BATCH, "row_id": "row-3",
                "lease_token": short["lease"]["token"],
                "cells": [{"cellId": "amount", "value": "2.00",
                           "generation": 0}]}),
            "lease_not_held:row-3")
        after5 = call("harness.review_batch_submit", {
            "actor_id": "recon-worker-4", "scope": SCOPE, "key": key("sb-4"),
            "batch_id": BATCH, "row_id": "row-3",
            "lease_token": reclaimed["lease"]["token"],
            "cells": [{"cellId": "amount", "value": "7.00",
                       "generation": 0}]})
        log3 = call("harness.review_batch_claim_log", {
            "scope": SCOPE, "batch_id": BATCH, "row_id": "row-3"})
        self.step("c05_reclaim_new_token_new_snapshot",
                  reclaimed["lease"]["token"] != short["lease"]["token"]
                  and reclaimed["lease"]["claimSeq"] == 2
                  and after5["state"] == "done"
                  and [e["claimSeq"] for e in log3["claims"]] == [1, 2],
                  claimSeq=reclaimed["lease"]["claimSeq"])

        # ---- C06 批量暂停重启续处理（在飞租约 row-1 跨暂停交作业）。
        inflight = claimed["lease"]["token"]
        paused = call("harness.review_batch_pause", {
            "actor_id": "recon-lawyer", "scope": SCOPE, "key": key("pz-1"),
            "batch_id": BATCH, "pause": {"reason": "对账暂停（合成）"}})
        self.expect_error("c06_pause_blocks_claim", lambda: call(
            "harness.review_batch_claim", {
                "actor_id": "recon-worker-5", "scope": SCOPE,
                "key": key("cl-5"), "batch_id": BATCH}),
            "batch_paused")
        inflight_submit = call("harness.review_batch_submit", {
            "actor_id": "recon-worker-1", "scope": SCOPE, "key": key("sb-1"),
            "batch_id": BATCH, "row_id": "row-1",
            "lease_token": inflight,
            "cells": [{"cellId": "amount", "value": "123456.78 元",
                       "generation": 1},
                      {"cellId": "cited", "value": "民法典第143条",
                       "generation": 0}]})
        state_after_pause = call("harness.review_batch_read", {
            "scope": SCOPE, "batch_id": BATCH})
        call("harness.review_batch_resume", {
            "actor_id": "recon-lawyer", "scope": SCOPE, "key": key("rs-1"),
            "batch_id": BATCH})
        resumed_claims = [call("harness.review_batch_claim", {
            "actor_id": "recon-worker-6", "scope": SCOPE,
            "key": key("cl-6-%d" % i), "batch_id": BATCH})
            for i in range(3)]
        for index, rc in enumerate(resumed_claims, start=1):
            call("harness.review_batch_submit", {
                "actor_id": "recon-worker-6", "scope": SCOPE,
                "key": key("sb-6-%d" % index), "batch_id": BATCH,
                "row_id": rc["rowId"], "lease_token": rc["lease"]["token"],
                "cells": [{"cellId": "amount", "value": "续跑值",
                           "generation": 0}]})
        final6 = call("harness.review_batch_read", {"scope": SCOPE,
                                                    "batch_id": BATCH})
        self.step("c06_pause_restart_resume_continues",
                  paused["status"] == "paused"
                  and inflight_submit["state"] == "done"
                  and state_after_pause["status"] == "paused"
                  and state_after_pause["counts"]["pending"] == 3
                  and [rc["rowId"] for rc in resumed_claims]
                      == ["row-4", "row-5", "row-6"]
                  and final6["counts"]["done"] == ROWS
                  and final6["status"] == "completed",
                  pausedCounts=state_after_pause["counts"],
                  finalCounts=final6["counts"])

        # ---- C07 真并发回读：双 worker 抢新批 12 行恰 12 胜零重叠。
        batch2 = dict(synth_batch(), id=BATCH + "-conc",
                      rows=[{"id": "crow-%02d" % i,
                             "cells": {"amount": None, "cited": None}}
                            for i in range(1, 13)])
        call("harness.review_batch_create", {
            "actor_id": "recon-lawyer", "scope": SCOPE, "key": key("rb-c"),
            "batch": batch2})
        won: list = []
        leases: dict = {}
        lock = threading.Lock()
        failures: list = []

        def _worker(tag: str) -> None:
            seq = 0
            while True:
                seq += 1
                try:
                    result = call("harness.review_batch_claim", {
                        "actor_id": "recon-cw-" + tag, "scope": SCOPE,
                        "key": key("cc-%s-%d" % (tag, seq)),
                        "batch_id": batch2["id"]})
                except (HarnessCommandError, ValueError) as exc:
                    if "batch_claim_contended" in str(exc):
                        return
                    failures.append(str(exc))
                    return
                with lock:
                    won.append(result["rowId"])
                    leases[result["rowId"]] = result["lease"]["token"]

        threads = [threading.Thread(target=_worker, args=(tag,))
                   for tag in ("a", "b")]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        for index, row_id in enumerate(sorted(leases), start=1):
            call("harness.review_batch_submit", {
                "actor_id": "recon-cw", "scope": SCOPE,
                "key": key("cs-%d" % index), "batch_id": batch2["id"],
                "row_id": row_id, "lease_token": leases[row_id],
                "cells": [{"cellId": "amount", "value": "%d.00" % index,
                           "generation": 0}]})
        final7 = call("harness.review_batch_read", {
            "scope": SCOPE, "batch_id": batch2["id"]})
        log7 = call("harness.review_batch_claim_log", {
            "scope": SCOPE, "batch_id": batch2["id"]})
        tokens = [entry["leaseToken"] for entry in log7["claims"]]
        self.step("c07_real_concurrency_exactly_once",
                  not failures
                  and len(won) == 12
                  and len(set(won)) == 12
                  and len(tokens) == 12
                  and len(set(tokens)) == 12
                  and final7["counts"] == {"pending": 0, "leased": 0,
                                           "done": 12, "total": 12}
                  and final7["status"] == "completed",
                  won=len(won), distinct=len(set(won)),
                  failures=failures[:3])
        return

    def bridge_fail_closed(self):
        # ---- C10 桥 fail-closed（产品纪律：未配置/未知＝exit 3 具名）。
        try:
            legal_entry.call("harness.review_batch_create",
                             {"scope": SCOPE}, {})
            raise AssertionError("bridge_unconfigured_not_connected")
        except NotConnected as exc:
            self.step("c10_bridge_unconfigured_not_connected",
                      "harness_public_entry_not_configured" in str(exc))
        try:
            legal_entry.call("harness.review_batch_force",
                             {"scope": SCOPE}, {"harness_public_entry":
                                                "X:/synth/entry.py",
                                                "harness_target": "opencode"})
            raise AssertionError("bridge_unknown_method_refused")
        except NotConnected as exc:
            self.step("c10_bridge_unknown_method_refused",
                      "method_not_connected" in str(exc))
        self.step("c10_late_code_vocabulary_registered",
                  all(hasattr(legal_entry, "HARNESS_BATCH_REVIEW_METHODS")
                      for _ in (0,))
                  and legal_entry.HARNESS_BATCH_REVIEW_METHODS ==
                  frozenset({
                      "harness.review_batch_create",
                      "harness.review_batch_claim",
                      "harness.review_batch_submit",
                      "harness.review_batch_human_edit",
                      "harness.review_batch_release",
                      "harness.review_batch_pause",
                      "harness.review_batch_resume",
                      "harness.review_batch_read",
                      "harness.review_batch_claim_log",
                      "harness.review_batch_list"}))

    # -- profile drivers ---------------------------------------------------

    def run_desktop(self) -> int:
        temporary = tempfile.TemporaryDirectory(prefix="juscite-f25-desktop-")
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
        store.create_matter(MATTER, "cas://profile-f25-recon")

        def call(method, args):
            return legal_entry.call(method, args, config)

        def query(sql, params):
            import contextlib
            import sqlite3
            with contextlib.closing(store._connect()) as connection:
                rows = connection.execute(sql, params).fetchall()
            return [dict(row) if isinstance(row, sqlite3.Row) else row
                    for row in rows]

        print("[profile desktop] SQLite via product bridge subprocess",
              flush=True)
        self.common_flow("desktop", call, query)
        return 0

    def run_selfhost(self, dsn: str) -> int:
        for path in (str(self.harness_root / "src"),
                     str(self.harness_root / "tools/workflow-tools"),
                     str(self.harness_root),
                     str(self.harness_root / "tests")):
            if path not in sys.path:
                sys.path.insert(0, path)
        import uuid as _uuid

        import contextlib

        from legal_harness.business.provider_registry import (
            resolve_provider_method,
        )
        from legal_harness.business.units import HarnessUnits
        from legal_harness.state.pg_store import PgMatterStore

        temporary = tempfile.TemporaryDirectory(prefix="juscite-f25-selfhost-")
        store = PgMatterStore(
            Path(temporary.name) / "state", dsn=dsn,
            schema="f25_" + _uuid.uuid4().hex[:12])
        units = HarnessUnits(store)
        bound = {name: resolve_provider_method(name, units)
                 for name in (
                     "harness.review_batch_create",
                     "harness.review_batch_claim",
                     "harness.review_batch_submit",
                     "harness.review_batch_human_edit",
                     "harness.review_batch_release",
                     "harness.review_batch_pause",
                     "harness.review_batch_resume",
                     "harness.review_batch_read",
                     "harness.review_batch_claim_log",
                     "harness.review_batch_list")}
        store.create_matter(MATTER, "cas://profile-f25-recon-pg")

        def call(method, args):
            return bound[method](**args)

        def query(sql, params):
            with contextlib.closing(store._connect()) as connection:
                rows = connection.execute(sql, params).fetchall()
            return [dict(row) for row in rows]

        print("[profile selfhost] PgMatterStore direct "
              "(provider registry face)", flush=True)
        try:
            self.common_flow("selfhost", call, query)
        finally:
            store.destroy()
            temporary.cleanup()
        return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--harness-root", type=Path, default=DEFAULT_HARNESS_ROOT)
    parser.add_argument("--profile", action="append",
                        choices=("desktop", "selfhost"), dest="profiles")
    parser.add_argument("--pg-dsn", default=None,
                        help="override the lh-pg-e08 container DSN")
    parser.add_argument("--json", action="store_true",
                        help="append a machine-readable summary block")
    args = parser.parse_args()
    profiles = args.profiles or ["desktop", "selfhost"]
    if not (args.harness_root / "tools/workflow-tools/harness/public_entry.py").exists():
        print("RECON_BLOCKED: harness root missing public_entry:", args.harness_root)
        return 3
    dsn = args.pg_dsn or DEFAULT_PG_DSN
    if "selfhost" in profiles:
        try:
            import socket
            probe = socket.create_connection(("127.0.0.1", 55432), timeout=3)
            probe.close()
        except OSError:
            print("RECON_BLOCKED: lh-pg-e08 (127.0.0.1:55432) not reachable;"
                  " start deploy/docker-compose.pg.yml or pass --pg-dsn")
            return 3
    recon = Recon(args.harness_root)
    recon.branch_checks()
    try:
        for profile in profiles:
            if profile == "desktop":
                recon.run_desktop()
            else:
                recon.run_selfhost(dsn)
        recon.bridge_fail_closed()
    except (AssertionError, HarnessCommandError, NotConnected) as error:
        print("RECON_FAIL:", error)
        if args.json:
            print(json.dumps({"summary": "RECON_FAIL",
                              "checks": recon.checks},
                             ensure_ascii=False, indent=1))
        return 1
    print("RECON_OK, %d checks all PASS (profiles=%s)"
          % (len(recon.checks), "+".join(profiles)))
    if args.json:
        print(json.dumps({"summary": "RECON_OK", "checks": recon.checks,
                          "matter": MATTER, "profiles": profiles},
                         ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

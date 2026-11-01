# -*- coding: utf-8 -*-
"""F82 复核/单格重跑/人工改格三面验收对账（PENDING_OWNER 版，工单 W2b-U31）。

闭环合同（06 F82 acceptance 后四 token 的后三＋失效回读；05§8 行租约＋
格守卫；08§3 批量审查矩阵：租约抢占/旧generation迟到/人改单格/源version
变化/部分失败恢复；harness docs/f82-review-ops-contract.md）：
  复核＝人审回执账（机器分子不动——E11 先例）＋复核状态投影；
  单格重跑＝以行为租约、格为粒度新 generation（三路具名拒不覆人改）；
  人工改格＝复用 F25 review_batch_human_edit（产品桥唯一写通道）；
  失效回读＝重跑后旧值历史可回读＋支持戳 STALE_CELL_ADVANCED（U05 面）。

分段（每 profile 同集 13 检）：
  C01 复核回执：登记回读（reviewer＋决定 ref）＋投影 REVIEWED_CONFIRMED
       ＋翻案追加取末条 REVIEWED_REJECTED（F82-复核 公开面）
  C02 复核语义钉死：决定闭集外/决定 ref 缺失 exit 3 具名；机器分子不动
       （复核前后格面＋支持投影逐键相等）
  C03 单格重跑（编排径）：claim→rerun→release——格 gen+1/source=machine/
       行回 pending/leaseTrace 在案（F82-重跑 公开面）
  C04 重跑三路具名拒不覆人改①迟到：他人持有效租约＝tabular.cell_rerun
       编排 claim 即 contended 具名上浮；旧 token 重跑＝lease_not_held
  C05 重跑三路具名拒②旧 generation：携带世代落后＝stale_generation
       carried/current 对照（harness 面直呼）
  C06 重跑三路具名拒③人改后重跑：人改（F82-人改 公开面）后即使携正确
       generation 也 review_rerun_human_cell 拒；人改值保全
  C07 人改写守卫：迟到人改（携旧 generation）＝stale_generation 具名拒
       不覆机器新值（F25 底座在重跑语境复验）
  C08 失效回读值侧：重跑后旧值历史三代可回读（tabular.cell_history）
  C09 失效回读支持侧：重跑推进格→既有戳投影 STALE_CELL_ADVANCED
       （stamped/current/currentSource 回读，旧戳保全）
  C10 复核状态面：批投影 counts（confirmed/rejected/not_reviewed）＋
       completed 批迟到回执照记
  C11 桥 fail-closed：未知方法/未配置/DTO 闭集外 全 exit 3 具名
  C12 回读确定性：tabular.read＋tabular.review_status 两跑投影语义相等
  C13 幂等重放：同 CommandKey 重跑重放＝同结果不双推进

双 profile：
  desktop＝产品桥子进程全链（legal_entry CLI→[tabular.*→harness
  public_entry 子进程]→SQLite MatterStore）——每次调用即新进程＝跨进程
  状态在库验证；
  selfhost＝PgMatterStore 直连容器 lh-pg-e08（provider registry 面）＋
  产品面同进程调用（review-ops seam 指向 PG 绑定方法）。

用法（juscite worktree w2b-u31 根 cwd）：
  python -X utf8 tools/PENDING_OWNER_f82_review_ops_recon.py \
      --profile desktop --profile selfhost

exit 0＝全部 profile 全部检过（RECON_OK）；证据 JSON 写 evidence/F82/
<profile>/。只读消费（harness 冻结面），不发任何网络请求，不写正式目录，
不触碰 oc28 与 %APPDATA%。
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

RUN_DATE = time.strftime("%Y%m%d")
REPO_ROOT = Path(__file__).resolve().parents[1]
LEGAL_ENTRY = REPO_ROOT / "implementation" / "python" / "legal_entry.py"
MATTER = "m-f82ops-recon"

DEFAULT_HARNESS_ROOT = (
    r"D:\Codex\1.法律工作区\legal-harness工作区\legal-harness-repo"
    r"\.local\worktrees\w2b-u31"
)

FACE_SHA = "a" * 64
PAGE_SHA = "b" * 64

COLUMNS = [
    {"id": "amount", "name": "合同金额", "format": "decimal-string",
     "version": "1", "gold": {"kind": "number", "expect": "123456.78"}},
    {"id": "cited", "name": "法律依据", "format": "text", "version": "1",
     "gold": {"kind": "text"}},
]

SCOPE = {"kind": "matter", "matterId": MATTER}
BATCH = "brt-f82ops"


def command_key(request_id: str) -> dict:
    return {"requestId": "f82ops-" + request_id, "targetId": None,
            "expectedRevision": None, "inputRefs": []}


def synth_stamp(run_seq: int = 1) -> dict:
    """合成核验戳：形态与 U05 面一致（内容全合成；用于重跑后 STALE 投影）。"""
    return {
        "gate": {
            "via": "extraction.gate(W2b-U02)",
            "face": "citation.verify(W2a-U14 VERIFIED)→lccc_consumer",
            "faceSha256": FACE_SHA, "asOf": RUN_DATE, "runSeq": run_seq,
            "extractionBatchId": "exb-synth", "candidateId": "cand_0001",
            "gateStatus": "CITATION_VERIFIED", "rejectionReasons": [],
        },
        "citations": [{
            "citationText": "《中华人民共和国个人信息保护法》第一条",
            "status": "现行", "verifiedScoped": True,
            "quoteInArticle": True,
        }],
        "provenance": {"source": "material_extraction", "doc": "synth_doc",
                       "page": 3, "textSha256": PAGE_SHA},
    }


class Checks:
    def __init__(self):
        self.items: list[dict] = []

    def add(self, check_id: str, ok: bool, detail: str) -> bool:
        self.items.append(
            {"id": check_id, "status": "PASS" if ok else "FAIL",
             "detail": detail})
        print("[%s] %s — %s" % ("PASS" if ok else "FAIL", check_id, detail))
        return ok

    @property
    def all_passed(self) -> bool:
        return all(item["status"] == "PASS" for item in self.items)

    @property
    def passed_count(self) -> int:
        return sum(1 for item in self.items if item["status"] == "PASS")


def expect_typed(checks: Checks, check_id: str, outcome: dict,
                 code_part: str) -> None:
    code = str(outcome.get("code", ""))
    checks.add(check_id, code.startswith(code_part),
               "typed 码=%s" % (code or outcome))


def common_flow(checks: Checks, call) -> dict:
    # --- 底座：建批（4 行×2 列；行序 row-1..4）＋列合同 --------------------
    created = call("harness.review_batch_create", {
        "actor_id": "lawyer-1", "scope": SCOPE, "key": command_key("rb1"),
        "batch": {"id": BATCH, "title": "F82 三面（W2b-U31 合成）",
                  "columns": [{"id": c["id"], "name": c["name"]}
                              for c in COLUMNS],
                  "rows": [{"id": "row-%d" % i,
                            "cells": {"amount": None, "cited": None}}
                           for i in range(1, 5)]}})
    if created.get("status") != "active":
        raise SystemExit("FATAL: 建批失败：%s" % created)
    call("harness.review_columns_define", {
        "actor_id": "lawyer-1", "scope": SCOPE, "key": command_key("rc1"),
        "batch_id": BATCH, "columns": COLUMNS})

    # --- C01 复核回执＋翻案（F82-复核 公开面）----------------------------
    first = call("tabular.review_receipt", {
        "review_batch_id": BATCH, "row_id": "row-1", "cell_id": "amount",
        "receipt": {"reviewer": "lawyer-1", "decision": "confirmed",
                    "decisionRef": "note-1"},
        "actor_id": "lawyer-1", "scope": SCOPE, "key": command_key("rr1")})
    overturn = call("tabular.review_receipt", {
        "review_batch_id": BATCH, "row_id": "row-1", "cell_id": "amount",
        "receipt": {"reviewer": "lawyer-2", "decision": "rejected",
                    "decisionRef": "note-2"},
        "actor_id": "lawyer-2", "scope": SCOPE, "key": command_key("rr2")})
    status = call("tabular.review_status", {"review_batch_id": BATCH,
                                            "scope": SCOPE})
    by_cell = {(p.get("rowId"), p.get("cellId")): p
               for p in status.get("projections", [])}
    checks.add(
        "C01_receipt_record_overturn_last_wins",
        first.get("seq") == 1 and overturn.get("seq") == 2
        and by_cell[("row-1", "amount")]["reviewStatus"]
        == "REVIEWED_REJECTED"
        and by_cell[("row-1", "amount")]["entryCount"] == 2
        and by_cell[("row-2", "amount")]["reviewStatus"] == "NOT_REVIEWED",
        "回执 seq1/2 翻案追加取末条 REVIEWED_REJECTED；未复核格 "
        "NOT_REVIEWED；counts=%s" % status.get("counts"))

    # --- C02 复核语义钉死（闭集＋机器分子不动）--------------------------
    bad_decision = call("tabular.review_receipt", {
        "review_batch_id": BATCH, "row_id": "row-1", "cell_id": "amount",
        "receipt": {"reviewer": "lawyer-1", "decision": "corrected",
                    "decisionRef": "note-x"},
        "actor_id": "lawyer-1", "scope": SCOPE, "key": command_key("rrx")})
    no_ref = call("tabular.review_receipt", {
        "review_batch_id": BATCH, "row_id": "row-1", "cell_id": "amount",
        "receipt": {"reviewer": "lawyer-1", "decision": "confirmed"},
        "actor_id": "lawyer-1", "scope": SCOPE, "key": command_key("rry")})
    row_before = call("harness.review_batch_read",
                      {"scope": SCOPE, "batch_id": BATCH, "row_id": "row-1"})
    molecules_before = json.dumps(
        row_before.get("row", {}).get("cells", {}),
        sort_keys=True, ensure_ascii=False)
    call("tabular.review_receipt", {
        "review_batch_id": BATCH, "row_id": "row-1", "cell_id": "cited",
        "receipt": {"reviewer": "lawyer-9", "decision": "confirmed",
                    "decisionRef": "note-3"},
        "actor_id": "lawyer-9", "scope": SCOPE, "key": command_key("rr3")})
    row_after = call("harness.review_batch_read",
                     {"scope": SCOPE, "batch_id": BATCH, "row_id": "row-1"})
    molecules_after = json.dumps(
        row_after.get("row", {}).get("cells", {}),
        sort_keys=True, ensure_ascii=False)
    checks.add(
        "C02_receipt_pinned_no_machine_molecules",
        bad_decision.get("exit") == 3
        and str(bad_decision.get("payload", {}).get("code", "")).startswith(
            "tabular_receipt_decision_invalid")
        and no_ref.get("exit") == 3
        and str(no_ref.get("payload", {}).get("code", "")).startswith(
            "tabular_receipt_body_invalid")
        and molecules_before == molecules_after,
        "决定闭集外/决定 ref 缺失 exit 3 具名；复核前后格面逐键相等"
        "（机器分子不动——E11 先例）")

    # --- C03 单格重跑编排径（F82-重跑 公开面）----------------------------
    rerun = call("tabular.cell_rerun", {
        "review_batch_id": BATCH, "row_id": "row-2", "cell_id": "amount",
        "value": "999,999.99 元", "actor_id": "worker-1", "scope": SCOPE,
        "key": command_key("ru1")})
    row2 = call("harness.review_batch_read",
                {"scope": SCOPE, "batch_id": BATCH, "row_id": "row-2"})
    cell2 = row2.get("row", {}).get("cells", {}).get("amount", {})
    checks.add(
        "C03_cell_rerun_claim_rerun_release",
        rerun.get("cell", {}).get("generation") == 1
        and rerun.get("cell", {}).get("source") == "machine"
        and rerun.get("cell", {}).get("value") == "999,999.99 元"
        and rerun.get("previousGeneration") == 0
        and rerun.get("rowState") == "pending"
        and row2.get("row", {}).get("state") == "pending"
        and cell2.get("generation") == 1,
        "重跑编排 claim→rerun→release：gen0→1/source=machine/行回 pending；"
        "leaseTrace=%s" % rerun.get("leaseTrace"))

    # --- C04 三路拒①迟到（租约抢占＋易主）--------------------------------
    holder = call("harness.review_batch_claim", {
        "actor_id": "worker-a", "scope": SCOPE, "key": command_key("clA"),
        "batch_id": BATCH, "row_id": "row-3", "lease_ttl_seconds": 600})
    contended = call("tabular.cell_rerun", {
        "review_batch_id": BATCH, "row_id": "row-3", "cell_id": "amount",
        "value": "1 元", "actor_id": "worker-b", "scope": SCOPE,
        "key": command_key("ru2")})
    checks.add(
        "C04_rerun_lease_refusals_named",
        holder.get("lease", {}).get("token")
        and str(contended.get("code", "")).startswith(
            "batch_claim_contended"),
        "他人持有效租约＝编排 claim 即 batch_claim_contended 具名上浮"
        "（typed 码=%s）" % contended.get("code"))

    # --- C05 三路拒②旧 generation（harness 面直呼）----------------------
    stale = call("harness.review_cell_rerun", {
        "actor_id": "worker-a", "scope": SCOPE, "key": command_key("ru3"),
        "batch_id": BATCH, "row_id": "row-3", "cell_id": "amount",
        "lease_token": holder["lease"]["token"], "value": "2 元",
        "generation": 5})
    stale2 = call("harness.review_cell_rerun", {
        "actor_id": "worker-a", "scope": SCOPE, "key": command_key("ru4"),
        "batch_id": BATCH, "row_id": "row-3", "cell_id": "amount",
        "lease_token": "ghost-token", "value": "2 元", "generation": 0})
    checks.add(
        "C05_rerun_stale_generation_and_lease_named",
        str(stale.get("code", "")).startswith("stale_generation:amount")
        and "carried=5" in str(stale.get("code", ""))
        and "current=0" in str(stale.get("code", ""))
        and str(stale2.get("code", "")).startswith("lease_not_held:row-3"),
        "旧 generation 迟到＝stale_generation carried=5/current=0；旧/"
        "伪造 token＝lease_not_held:row-3")

    # --- C06 三路拒③人改后重跑（F82-人改 公开面＝human_edit 经产品桥）---
    human = call("harness.review_batch_human_edit", {
        "actor_id": "lawyer-1", "scope": SCOPE, "key": command_key("he1"),
        "batch_id": BATCH, "row_id": "row-3",
        "cells": [{"cellId": "amount", "value": "人改核正值",
                   "generation": 0}]})
    rerun_after_human = call("harness.review_cell_rerun", {
        "actor_id": "worker-a", "scope": SCOPE, "key": command_key("ru5"),
        "batch_id": BATCH, "row_id": "row-3", "cell_id": "amount",
        "lease_token": holder["lease"]["token"], "value": "777 元",
        "generation": 1})
    row3 = call("harness.review_batch_read",
                {"scope": SCOPE, "batch_id": BATCH, "row_id": "row-3"})
    cell3 = row3.get("row", {}).get("cells", {}).get("amount", {})
    checks.add(
        "C06_rerun_after_human_edit_refused",
        human.get("cells", {}).get("amount", {}).get("source") == "human"
        and str(rerun_after_human.get("code", "")).startswith(
            "review_rerun_human_cell:amount")
        and cell3.get("value") == "人改核正值"
        and cell3.get("source") == "human",
        "人改（携当前 gen0→gen1 human）后即使携正确 generation=1 重跑也"
        " review_rerun_human_cell 拒；人改值保全")

    # --- C07 人改写守卫（迟到人改不覆机器新值）--------------------------
    late_human = call("harness.review_batch_human_edit", {
        "actor_id": "lawyer-2", "scope": SCOPE, "key": command_key("he2"),
        "batch_id": BATCH, "row_id": "row-2",
        "cells": [{"cellId": "amount", "value": "迟到人改",
                   "generation": 0}]})
    checks.add(
        "C07_late_human_edit_stale_generation",
        str(late_human.get("code", "")).startswith("stale_generation:amount")
        and "current=1" in str(late_human.get("code", "")),
        "迟到人改（携 gen0，格已 gen1）＝stale_generation 具名拒——迟到"
        "人改不覆机器新值（typed 码=%s）" % late_human.get("code"))

    # --- C08 失效回读值侧（旧值历史）------------------------------------
    history = call("tabular.cell_history", {
        "review_batch_id": BATCH, "row_id": "row-2", "cell_id": "amount",
        "scope": SCOPE})
    versions = [(v.get("generation"), v.get("value"), v.get("source"))
                for v in history.get("versions", [])]
    checks.add(
        "C08_cell_history_old_values_readable",
        versions == [(0, None, "initial"), (1, "999,999.99 元",
                                            "machine")],
        "重跑后旧值历史可回读：%s（三代含初值）" % versions)

    # --- C09 失效回读支持侧（STALE 投影）--------------------------------
    call("harness.review_support_record", {
        "actor_id": "worker-1", "scope": SCOPE, "key": command_key("st1"),
        "batch_id": BATCH, "row_id": "row-2", "cell_id": "amount",
        "entry": synth_stamp()})
    before_stale = call("harness.review_support_read", {
        "scope": SCOPE, "batch_id": BATCH, "row_id": "row-2",
        "cell_id": "amount"})
    call("harness.review_support_record", {
        "actor_id": "worker-1", "scope": SCOPE, "key": command_key("st2"),
        "batch_id": BATCH, "row_id": "row-4", "cell_id": "cited",
        "entry": synth_stamp(run_seq=2)})
    rerun4 = call("tabular.cell_rerun", {
        "review_batch_id": BATCH, "row_id": "row-4", "cell_id": "cited",
        "value": "重抽引证", "actor_id": "worker-1", "scope": SCOPE,
        "key": command_key("ru6")})
    after_stale = call("harness.review_support_read", {
        "scope": SCOPE, "batch_id": BATCH, "row_id": "row-4",
        "cell_id": "cited"})
    projection = (after_stale.get("projections") or [{}])[0]
    checks.add(
        "C09_support_stale_after_rerun",
        (before_stale.get("projections") or [{}])[0].get(
            "supportStatus") == "SUPPORTED_CITATION_LEVEL"
        and rerun4.get("cell", {}).get("generation") == 1
        and projection.get("supportStatus") == "STALE_CELL_ADVANCED"
        and projection.get("detail", {}).get("stampedGeneration") == 0
        and projection.get("detail", {}).get("currentGeneration") == 1
        and projection.get("detail", {}).get("currentSource") == "machine"
        and projection.get("entryCount") == 1,
        "重跑推进格→既有戳投影 STALE_CELL_ADVANCED（stamped=0/current=1/"
        "machine）；旧戳保全 entryCount=1")

    # --- C10 复核状态面（counts＋completed 迟到回执）--------------------
    status2 = call("tabular.review_status", {"review_batch_id": BATCH,
                                             "scope": SCOPE})
    counts = status2.get("counts", {})
    late_receipt = call("tabular.review_receipt", {
        "review_batch_id": BATCH, "row_id": "row-4", "cell_id": "cited",
        "receipt": {"reviewer": "lawyer-3", "decision": "confirmed",
                    "decisionRef": "note-4"},
        "actor_id": "lawyer-3", "scope": SCOPE, "key": command_key("rr4")})
    checks.add(
        "C10_receipt_projection_counts",
        counts.get("REVIEWED_CONFIRMED") == 1
        and counts.get("REVIEWED_REJECTED") == 1
        and counts.get("NOT_REVIEWED") == 6
        and late_receipt.get("seq") == 1,
        "批投影 counts=%s；回执不随批状态关门" % counts)

    # --- C11 桥 fail-closed ----------------------------------------------
    unknown = call("tabular.review_sign", {"scope": SCOPE})
    unconfigured = call("tabular.review_status",
                        {"review_batch_id": BATCH, "scope": SCOPE},
                        config_override={"harness_public_entry": None})
    ghost = call("tabular.cell_history", {
        "review_batch_id": "ghost", "row_id": "row-1", "cell_id": "amount",
        "scope": SCOPE})
    checks.add(
        "C11_bridge_fail_closed",
        unknown.get("exit") == 3
        and str(unknown.get("payload", {}).get("code", "")).startswith(
            "method_not_connected:tabular.review_sign")
        and unconfigured.get("exit") == 3
        and str(unconfigured.get("payload", {}).get("code", "")).startswith(
            "harness_public_entry_not_configured")
        and str(ghost.get("code", "")).startswith(
            "review_batch_not_found:ghost"),
        "未知方法/未配置桥 exit 3 具名；未知批次 typed 码=%s"
        % ghost.get("code"))

    # --- C12 回读确定性 ---------------------------------------------------
    table_a = call("tabular.read", {"review_batch_id": BATCH,
                                    "scope": SCOPE})
    status_a = call("tabular.review_status", {"review_batch_id": BATCH,
                                              "scope": SCOPE})
    table_b = call("tabular.read", {"review_batch_id": BATCH,
                                    "scope": SCOPE})
    status_b = call("tabular.review_status", {"review_batch_id": BATCH,
                                              "scope": SCOPE})
    checks.add(
        "C12_readback_determinism",
        json.dumps(table_a, sort_keys=True, ensure_ascii=False)
        == json.dumps(table_b, sort_keys=True, ensure_ascii=False)
        and json.dumps(status_a, sort_keys=True, ensure_ascii=False)
        == json.dumps(status_b, sort_keys=True, ensure_ascii=False),
        "tabular.read＋tabular.review_status 两跑投影语义相等")

    # --- C13 幂等重放 -----------------------------------------------------
    replay = call("tabular.cell_rerun", {
        "review_batch_id": BATCH, "row_id": "row-2", "cell_id": "amount",
        "value": "999,999.99 元", "actor_id": "worker-1", "scope": SCOPE,
        "key": command_key("ru1")})
    row2_final = call("harness.review_batch_read",
                      {"scope": SCOPE, "batch_id": BATCH,
                       "row_id": "row-2"})
    checks.add(
        "C13_command_key_idempotent_replay",
        replay.get("cell", {}).get("generation") == 1
        and row2_final.get("row", {}).get("cells", {}).get(
            "amount", {}).get("generation") == 1,
        "同 CommandKey 重跑重放＝同结果（gen 不双推进，恒 1）")

    return {
        "receipt_counts": counts,
        "rerun_history_versions": versions,
        "support_projection_after_rerun": projection.get("supportStatus"),
    }


# ---------------------------------------------------------------------- #
# profile drivers
# ---------------------------------------------------------------------- #


class Recon:
    def __init__(self, harness_root: Path):
        self.harness_root = harness_root
        self.checks = Checks()

    def base_config(self, state_root: Path) -> dict:
        registration = state_root.parent / "service-local.json"
        registration.write_text(json.dumps(
            {"url": "http://127.0.0.1:1", "password": "synthetic-recon"}),
            encoding="utf-8")
        return {
            "harness_public_entry": str(
                self.harness_root
                / "tools/workflow-tools/harness/public_entry.py"),
            "harness_target": "opencode",
            "harness_state_root": str(state_root),
            "harness_service_registration": str(registration),
            "harness_timeout": 180,
            "harness_python": sys.executable,
        }

    # -- desktop: full product-bridge subprocess chain --------------------
    def run_desktop(self) -> None:
        temporary = tempfile.TemporaryDirectory(prefix="juscite-f82ops-d-")
        self.add_cleanup(temporary.cleanup)
        base = Path(temporary.name)
        state_root = base / "state"
        state_root.mkdir(parents=True)
        config = self.base_config(state_root)
        for path in (str(self.harness_root / "src"),):
            if path not in sys.path:
                sys.path.insert(0, path)
        from legal_harness.state.matter_store import MatterStore
        MatterStore(state_root).create_matter(MATTER,
                                              "cas://profile-f82ops-d")

        def call(method, args, config_override=None):
            merged = dict(config)
            if config_override:
                for key, value in config_override.items():
                    if value is None:
                        merged.pop(key, None)
                    else:
                        merged[key] = value
            outcome = call_entry(method, args, merged)
            if outcome["exit"] == 0:
                return outcome["result"] if outcome["result"] \
                    is not None else {}
            payload = outcome["payload"]
            return {"exit": outcome["exit"], "payload": payload,
                    "code": payload.get("code")
                    if isinstance(payload, dict) else None}

        print("[profile desktop] SQLite via product bridge subprocess "
              "(legal_entry CLI→harness public_entry)", flush=True)
        common_flow(self.checks, call)

    # -- selfhost: PgMatterStore direct + in-process product faces --------
    def run_selfhost(self, dsn: str) -> None:
        import contextlib
        import uuid as _uuid

        for path in (str(self.harness_root / "src"),
                     str(self.harness_root / "tools/workflow-tools"),
                     str(self.harness_root), str(self.harness_root / "tests"),
                     str(REPO_ROOT / "implementation/python")):
            if path not in sys.path:
                sys.path.insert(0, path)
        from legal_harness.business.provider_registry import (
            resolve_provider_method,
        )
        from legal_harness.business.units import HarnessUnits
        from legal_harness.state.pg_store import PgMatterStore

        temporary = tempfile.TemporaryDirectory(prefix="juscite-f82ops-s-")
        self.add_cleanup(temporary.cleanup)
        base = Path(temporary.name)
        store = PgMatterStore(
            base / "state", dsn=dsn,
            schema="f82ops_" + _uuid.uuid4().hex[:12])
        units = HarnessUnits(store)
        names = (
            "harness.review_batch_create", "harness.review_batch_claim",
            "harness.review_batch_submit", "harness.review_batch_human_edit",
            "harness.review_batch_release", "harness.review_batch_read",
            "harness.review_columns_define", "harness.review_columns_read",
            "harness.review_support_record",
            "harness.review_support_invalidate",
            "harness.review_support_read",
            "harness.review_receipt_record",
            "harness.review_receipt_read",
            "harness.review_cell_rerun", "harness.review_cell_history")
        bound = {name: resolve_provider_method(name, units)
                 for name in names}
        store.create_matter(MATTER, "cas://profile-f82ops-pg")
        import tabular_review_ops
        from bridge_errors import NotConnected as NotConnected_

        def _bound_call(method, args, cfg):
            return bound[method](**args)

        patcher = unittest_mock_patch(
            tabular_review_ops, "_harness_call", _bound_call)
        patcher.start()
        self.add_cleanup(patcher.stop)

        def call(method, args, config_override=None):
            # config_override 只在 fail-closed 检查看得到（本径无子进程）。
            if config_override and config_override.get(
                    "harness_public_entry") is None:
                return {"exit": 3, "payload": {
                    "status": "NOT_CONNECTED",
                    "code": "harness_public_entry_not_configured"}}
            if method.startswith("harness."):
                if method not in bound:
                    return {"exit": 3, "payload": {
                        "status": "NOT_CONNECTED",
                        "code": "method_not_connected:" + method}}
                try:
                    return bound[method](**args)
                except Exception as exc:  # harness 面码原样上浮（不吞不改）
                    return {"exit": 1, "code": str(exc), "payload": {
                        "status": "HARNESS_FAIL", "code": str(exc)}}
            # tabular.*（桥形态对齐：冻结方法组外＝NOT_CONNECTED 具名）
            import legal_entry
            if method not in legal_entry.TABULAR_REVIEW_OPS_METHODS:
                return {'exit': 3, 'payload': {
                    'status': 'NOT_CONNECTED',
                    'code': 'method_not_connected:' + method}}
            try:
                return tabular_review_ops.review_ops_call(method, args, {})
            except NotConnected_ as exc:
                return {"exit": 3, "payload": {"status": "NOT_CONNECTED",
                                               "code": str(exc)}}
            except Exception as exc:  # 同进程径 harness UnitsError 原样
                return {"exit": 1, "code": str(exc), "payload": {
                    "status": "HARNESS_FAIL", "code": str(exc)}}

        print("[profile selfhost] PgMatterStore direct (provider registry "
              "face) + in-process product faces", flush=True)
        try:
            common_flow(self.checks, call)
        finally:
            store.destroy()

    # -- tiny cleanup registry --------------------------------------------
    def add_cleanup(self, fn) -> None:
        self._cleanups.append(fn)

    _cleanups: list = []

    def cleanup(self) -> None:
        for fn in reversed(self._cleanups):
            try:
                fn()
            except Exception:
                pass


def unittest_mock_patch(target, attribute, replacement):
    import unittest.mock
    return unittest.mock.patch.object(target, attribute, replacement)


def call_entry(method: str, args: dict, config: dict) -> dict:
    """真产品入口子进程调用（legal_entry CLI）；返回 {exit, payload, code}。"""
    request_handle = tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", suffix=".json", delete=False)
    config_handle = tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", suffix=".json", delete=False)
    try:
        json.dump({"method": method, "args": args}, request_handle,
                  ensure_ascii=False)
        request_handle.close()
        json.dump(config, config_handle, ensure_ascii=False)
        config_handle.close()
        proc = subprocess.run(
            [sys.executable, "-X", "utf8", str(LEGAL_ENTRY),
             "--request-json", request_handle.name,
             "--config", config_handle.name],
            capture_output=True, text=True, encoding="utf-8",
            timeout=900, cwd=str(REPO_ROOT))
        try:
            payload = json.loads(proc.stdout)
        except json.JSONDecodeError:
            payload = {"_raw": proc.stdout[-500:]}
        return {"exit": proc.returncode, "payload": payload,
                "code": payload.get("code") if isinstance(payload, dict)
                else None,
                "result": payload.get("result") if isinstance(payload, dict)
                else None}
    finally:
        os.unlink(request_handle.name)
        os.unlink(config_handle.name)


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
    sys.path.insert(0, str(REPO_ROOT / "implementation/python"))
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", action="append",
                        choices=("desktop", "selfhost"), dest="profiles",
                        help="发行形态（可重复；不给则双形态全跑）")
    parser.add_argument("--harness-root", default=DEFAULT_HARNESS_ROOT)
    parser.add_argument(
        "--pg-dsn",
        default="postgresql://lh_app:e08-synth-only@127.0.0.1:55432/"
                "legal_harness",
        help="selfhost PgMatterStore 直连 DSN（默认＝本机合成容器 "
             "lh-pg-e08，deploy/docker-compose.pg.yml 同拓扑；合成专用"
             "凭据）")
    parser.add_argument("--evidence-root", default="evidence/F82")
    args = parser.parse_args()
    profiles = args.profiles or ["desktop", "selfhost"]

    if not os.path.isfile(os.path.join(
            args.harness_root,
            "tools/workflow-tools/harness/public_entry.py")):
        print("FATAL: harness 公开入口不在 %s（w2b-u31 worktree）"
              % args.harness_root)
        return 2

    recon = Recon(Path(args.harness_root))
    per_profile: dict = {}
    all_ok = True
    try:
        for profile in profiles:
            recon.checks = Checks()
            if profile == "desktop":
                recon.run_desktop()
            else:
                recon.run_selfhost(args.pg_dsn)
            commit = subprocess.run(
                ["git", "rev-parse", "HEAD"], capture_output=True, text=True,
                cwd=str(REPO_ROOT)).stdout.strip()
            harness_commit = subprocess.run(
                ["git", "rev-parse", "HEAD"], capture_output=True, text=True,
                cwd=str(args.harness_root)).stdout.strip()
            evidence = {
                "run_date": RUN_DATE,
                "profile": profile,
                "command": "python -X utf8 " + " ".join(sys.argv[1:]),
                "cwd": str(REPO_ROOT),
                "subject_commit": commit,
                "harness_commit": harness_commit,
                "checks": recon.checks.items,
                "passed": recon.checks.passed_count,
                "total": len(recon.checks.items),
                "overall": "PASS" if recon.checks.all_passed else "FAIL",
            }
            out_dir = REPO_ROOT / args.evidence_root / profile
            out_dir.mkdir(parents=True, exist_ok=True)
            (out_dir / ("f82-review-ops-recon-%s.json"
                        % time.strftime("%Y%m%dT%H%M%S%z"))).write_text(
                json.dumps(evidence, ensure_ascii=False, indent=1),
                encoding="utf-8")
            per_profile[profile] = evidence
            all_ok = all_ok and recon.checks.all_passed
            print("---")
            print("profile=%s: %d/%d checks" % (
                profile, recon.checks.passed_count,
                len(recon.checks.items)))
    finally:
        recon.cleanup()
    print("RECON_%s（%s）" % ("OK" if all_ok else "FAIL",
                             "+".join(profiles)))
    return 0 if all_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())

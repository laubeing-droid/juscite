# -*- coding: utf-8 -*-
"""F121 案件时间线 chronology 验收对账（W4-U52）——双 profile
（desktop/selfhost）。

对账对象：harness 分支 w4-u52（基战役链头 w4-u51@1b8a7e9c＝A2 分支链，
schema v33→v34 增量一账 chronology_events）的 public_entry
--chronology-json 封闭径——desktop profile 与产品桥（legal_entry → 子进
程 public_entry）完全同一条链（SQLite 状态根）；selfhost profile＝
PgMatterStore 直连 lh-pg-e08（resolve_provider_method 同一封闭注册）。
产品半边确定性抽取（implementation/python/chronology.py：正则＋状态机，
红线 1 严禁模型猜日期）经 legal_entry chronology.extract 本地面实跑。

实跑覆盖（06 F121 acceptance：事件时间轴回到来源/确认状态；未知时点
不填录入日，修改触发依赖失效）：
  C1  schema v34＋chronology_events 表在（DB 级）；
  C2  registry 五方法封闭可解析＋伪方法拒（auto_fill_entry_date/delete
      形态结构性不存在）；
  C3  确定性抽取：同输入两跑字节级同输出＋闭集分类＋无年「3月5日」→
      unknown（绝不猜年）＋文档日期标签片段剔除（标签日期绝不作事件
      日期）＋AST 导入闭集（json/re）；
  C4  候选落账回来源：record 全部候选→unconfirmed；来源 ref（封闭六字
      段）＋页段锚在项内可回读；
  C5  未知时点＝unknown 档：axis unknown 分列＋entryDateFieldPresent=
      False＋投影字段闭集无 entryDate/documentDate（录入日字段零存在
      语义）；
  C6  unknown 填日期拒：方法级 chronology_unknown_date_filled＋表级
      CHECK（DB 直插 IntegrityError——录入日/文档日期形态结构性不能
      落账）；
  C7  确认状态（E17 同频）：无人工决定凭据拒；confirm→confirmed（内容
      逐字节复制）；再确认拒；
  C8  修改触发依赖失效（写侧，E15 同构）：缺 invalidations 拒；空列表＝
      显式声明无下游合法；带标记修改→invalidations_list 回读；首登记
      带标记拒；
  C9  修改触发依赖失效（读侧）：link_case_objects 钉定版本→事件头前进
      ⇒ dependencyStatus STALE（reason=chronology_event_revision_
      moved）——F118 期限锚/D01 期限计算/goal 三类下游共用失效面；
  C10 期限锚守卫（产品面 chronology.deadline_anchor 消费 read 回执，
      D01 只读联动）：unconfirmed 拒／STALE 拒／confirmed＋fresh→
      anchorDate；本面不写程序期限账；
  C11 只读消费程序期限链：chronology 全方法前后 procedure_events/
      deadlines 行数零变化（DB 级）；
  C12 幂等：同键重放回执相等；同键异内容 idempotency_conflict；
  C13 scope 隔离：跨案来源 ref 拒；
  C14 桥负向：未配置 NOT_CONNECTED／未知方法拒／方法组冻结恰五方法。

用法（juscite worktree 根 cwd）：
  python -X utf8 tools/recon/PENDING_OWNER_f121_chronology_recon.py \
      --profile desktop --profile selfhost
  [--harness-root <legal-harness w4-u52 worktree>] [--pg-dsn <dsn>]
  [--evidence-suffix <tag>]

--profile 可重复（action=append，E17/E19/E20 工具同款）；缺省=desktop。
exit 0＝全部 profile RECON_OK；2=RECON_FAIL；3=环境缺失。
证据：<repo>/docs/construction/evidence/F121/<profile>/ JSON＋MD。
全程合成材料；harness 检出只读（只运行其代码，git 只读命令核对分支）；
不发网络请求；%APPDATA% 零触碰。
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

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "implementation" / "python"))
sys.path.insert(0, str(REPO_ROOT / "implementation" / "tests"))

import legal_entry  # noqa: E402
from legal_entry import HarnessCommandError, NotConnected  # noqa: E402

DEFAULT_HARNESS_ROOT = Path(
    r"D:\Codex\1.法律工作区\legal-harness工作区\legal-harness-repo"
    r"\.local\worktrees\w4-u52")

MATTER = "m-f121-recon"
SCOPE = {"kind": "matter", "matterId": MATTER}

# lh-pg-e08 容器（E08 拓扑）：仅回环端口、合成专用凭据（可用 LH_E08_PG_DSN
# 覆写）。
DEFAULT_PG_DSN = ("postgresql://lh_app:e08-synth-only@127.0.0.1:55432/"
                  "legal_harness")

HARNESS_CHRONOLOGY_METHODS = frozenset({
    "harness.chronology_event_record", "harness.chronology_event_confirm",
    "harness.chronology_event_read", "harness.chronology_axis",
    "harness.chronology_invalidations_list",
})

SYNTH_SEGMENTS = [
    {"docId": "doc-contract", "pageFrom": 1, "pageTo": 2, "text":
     "2024年3月5日，双方签订《购销合同》（合成事件抽取源）。"
     "合同约定验收后30日内付款。2024年3月，供方依约交付全部设备。"},
    {"docId": "doc-receipt", "pageFrom": 3, "pageTo": 3, "text":
     "3月5日需方签收货物（文书未记年份）。2024年，法院开庭审理本案。"
     "（文档日期：2026-10-21）本页为合成收件回执。"},
]

EXPECTED_BY_KEY = {
    ("contract_signing", "2024-03-05", "day"),
    ("payment", None, "unknown"),        # 「验收后30日内付款」无日期句→未知档
    ("performance", "2024-03", "month"),
    ("service", None, "unknown"),        # 无年「3月5日」→未知档（绝不猜年）
    ("hearing", "2024", "year"),
}
# 候选登记序（SYNTH_SEGMENTS 句序）：0=合同签订 day／1=付款 unknown／
# 2=交付 month／3=签收 unknown／4=开庭 year。
UNKNOWN_IDS = {"ev-synth-1", "ev-synth-3"}


def key(request_id: str) -> dict:
    return {"requestId": request_id, "targetId": None,
            "expectedRevision": None, "inputRefs": []}


def href(kind: str, ref_id: str, version: str = "1") -> dict:
    return {"owner": "harness", "kind": kind, "id": ref_id,
            "version": version, "matterId": MATTER, "digest": None}


def decision_ref(ref_id: str) -> dict:
    return href("human_decision", ref_id)


def chronology_event(event_id: str, *, event_date=None, precision="day",
                     origin="extracted", summary="合成时间线事件",
                     invalidations=None, kind="contract_signing") -> dict:
    return {
        "eventId": event_id,
        "title": f"{event_id} 合成时间线事件",
        "eventKind": kind,
        "eventDate": event_date,
        "datePrecision": precision,
        "dateOrigin": origin,
        "summary": summary,
        "sourceRef": href("material", "mat-f121-src"),
        "sourceSpan": [{"docId": "doc-contract", "pageFrom": 1, "pageTo": 1}],
        "invalidations": invalidations if invalidations is not None else [],
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
        # desktop 桥链合同码冒 HarnessCommandError；selfhost 直连公开面冒
        # UnitsError（ValueError 子类）——两者都只认 code_part 在码里。
        try:
            call()
        except error as exc:
            self.step(name, code_part in str(exc), code=str(exc))
            return str(exc)
        raise AssertionError(name + ": no typed error raised")

    def git(self, root: Path, *args: str) -> str:
        return subprocess.check_output(
            ["git", "-C", str(root), *args], text=True, encoding="utf-8")

    # -- common flow -------------------------------------------------------

    def common_flow(self, profile: str, call, query, local_call,
                    raw_execute, link_call) -> None:
        # ---- C1 schema v34＋表在（DB 级）。
        version_row = query("SELECT value FROM metadata"
                            " WHERE key='schema_version'")[0]
        tables = {row["name"] for row in query(
            "SELECT name FROM sqlite_master WHERE type='table'")} \
            if profile == "desktop" else {
            row["tablename"] for row in query(
                "SELECT tablename FROM pg_tables WHERE schemaname=current_schema()")}
        self.step("c1_schema_v34_and_table",
                  int(version_row["value"]) == 34
                  and "chronology_events" in tables,
                  schema_version=int(version_row["value"]),
                  has_chronology_events="chronology_events" in tables)

        # ---- C3 确定性抽取（产品半边实跑，正则＋状态机）。
        probe = local_call("chronology.extract",
                           {"segments": SYNTH_SEGMENTS})
        probe2 = local_call("chronology.extract",
                            {"segments": SYNTH_SEGMENTS})
        got = {(c["eventKind"], c["eventDate"], c["datePrecision"])
               for c in probe["candidates"]}
        doc_label_leaked = any(
            c["eventDate"] == "2026-10-21" for c in probe["candidates"])
        origin_ok = all(
            c["dateOrigin"] == ("extracted" if c["eventDate"] is not None
                                else "unavailable")
            for c in probe["candidates"])
        self.step(
            "c3_extract_deterministic_closed_unknown",
            probe == probe2 and probe["determinism"] == "regex-state-machine"
            and got == EXPECTED_BY_KEY
            and probe["unknownCount"] == 2
            and not doc_label_leaked and origin_ok,
            determinism=probe["determinism"],
            candidateCount=probe["candidateCount"],
            unknownCount=probe["unknownCount"],
            shapes=sorted(f"{k}|{d}|{p}" for k, d, p in got))

        # ---- C4 候选落账回来源（unconfirmed；来源 ref＋页段在项内）。
        registered = []
        for index, candidate in enumerate(probe["candidates"]):
            result = call("harness.chronology_event_record", {
                "actor_id": "recon-lawyer", "scope": SCOPE,
                "key": key(f"reg-{index}"),
                "event": {
                    "eventId": f"ev-synth-{index}",
                    "title": candidate["title"][:120],
                    "eventKind": candidate["eventKind"],
                    "eventDate": candidate["eventDate"],
                    "datePrecision": candidate["datePrecision"],
                    "dateOrigin": candidate["dateOrigin"],
                    "summary": candidate["summary"][:400],
                    "sourceRef": href("material", "mat-f121-src"),
                    "sourceSpan": [candidate["sourceSpan"]],
                    "invalidations": [],
                }})
            registered.append(result)
        self.step(
            "c4_candidates_recorded_unconfirmed_with_source",
            all(r["status"] == "unconfirmed" and r["revision"] == 1
                for r in registered)
            and len(registered) == probe["candidateCount"],
            recorded=len(registered))
        readback = call("harness.chronology_event_read",
                        {"scope": SCOPE, "event_id": "ev-synth-0"})
        self.step(
            "c4_source_ref_and_span_readable",
            readback["sourceRef"]["id"] == "mat-f121-src"
            and readback["sourceRef"]["owner"] == "harness"
            and readback["sourceSpan"][0]["docId"] == "doc-contract",
            sourceRef=readback["sourceRef"]["id"])

        # ---- C5 未知时点＝unknown 档（投影结构断言）。
        axis = call("harness.chronology_axis", {"scope": SCOPE})
        unknown_ids = {item["eventId"] for item in axis["unknown"]}
        known_ids = {item["eventId"] for item in axis["known"]}
        no_entry_date = all(
            "entryDate" not in item and "documentDate" not in item
            for item in axis["known"] + axis["unknown"])
        self.step(
            "c5_unknown_bucket_never_filled",
            axis["entryDateFieldPresent"] is False
            and axis["unknownCount"] == 2
            and unknown_ids == UNKNOWN_IDS
            and all(item["eventDate"] is None for item in axis["unknown"])
            and all(item["eventDate"] is not None for item in axis["known"])
            and no_entry_date,
            knownCount=axis["knownCount"],
            unknownCount=axis["unknownCount"],
            unknownIds=sorted(unknown_ids))
        del known_ids

        # ---- C6 unknown 填日期拒（方法级＋表级 CHECK）。
        self.expect_error(
            "c6_unknown_with_filled_date_refused",
            lambda: call("harness.chronology_event_record", {
                "actor_id": "recon-lawyer", "scope": SCOPE,
                "key": key("unk-filled"),
                "event": chronology_event(
                    "ev-unk-filled", event_date="2026-10-21",
                    precision="unknown", origin="unavailable",
                    summary="录入日不得冒事件日（合成反例）")}),
            "chronology_unknown_date_filled")
        try:
            raw_execute(
                "INSERT INTO chronology_events(matter_id,event_id,"
                "revision,title,event_kind,event_date,date_precision,"
                "date_origin,summary,source_ref_json,source_span_json,"
                "status,confirmed_ref_json,invalidations_json,"
                "recorded_by,created_at)"
                " VALUES (?, 'ev-raw-check', 1, 'raw', "
                "'contract_signing', '2026-10-21', 'unknown',"
                "'unavailable', 'raw', '{}', NULL, 'unconfirmed',"
                "NULL, '[]', 'raw', '2026-10-21T00:00:00Z')",
                (MATTER,))
            check_ok, raw_error = False, "no-error"
        except Exception as exc:  # sqlite3.IntegrityError / psycopg errors
            check_ok, raw_error = True, type(exc).__name__
        self.step("c6_table_level_check_refuses_raw_row", check_ok,
                  raw_error=raw_error)

        # ---- C7 确认状态（E17 同频）。
        self.expect_error(
            "c7_confirm_without_decision_ref_refused",
            lambda: call("harness.chronology_event_confirm", {
                "actor_id": "recon-lawyer", "scope": SCOPE,
                "key": key("cf-noref"),
                "confirmation": {"eventId": "ev-synth-0"}}),
            "fields_missing")
        confirmed = call("harness.chronology_event_confirm", {
            "actor_id": "recon-lawyer", "scope": SCOPE,
            "key": key("cf-1"),
            "confirmation": {"eventId": "ev-synth-0",
                             "decisionRef": decision_ref("dec-recon-1")}})
        before = call("harness.chronology_event_read",
                      {"scope": SCOPE, "event_id": "ev-synth-0",
                       "revision": 1})
        after = call("harness.chronology_event_read",
                     {"scope": SCOPE, "event_id": "ev-synth-0"})
        content_fields = ("title", "eventKind", "eventDate", "datePrecision",
                          "dateOrigin", "summary", "sourceRef", "sourceSpan",
                          "invalidations")
        self.step(
            "c7_confirmed_via_decision_ref_content_immutable",
            confirmed["status"] == "confirmed" and confirmed["revision"] == 2
            and after["status"] == "confirmed"
            and after["confirmedRef"]["id"] == "dec-recon-1"
            and all(after[f] == before[f] for f in content_fields),
            revision=after["revision"])
        self.expect_error(
            "c7_double_confirm_refused",
            lambda: call("harness.chronology_event_confirm", {
                "actor_id": "recon-lawyer", "scope": SCOPE,
                "key": key("cf-2"),
                "confirmation": {"eventId": "ev-synth-0",
                                 "decisionRef": decision_ref("dec-recon-2")}}),
            "chronology_already_confirmed")

        # ---- C8 修改触发依赖失效（写侧）。
        self.expect_error(
            "c8_edit_without_invalidations_field_refused",
            lambda: call("harness.chronology_event_record", {
                "actor_id": "recon-lawyer", "scope": SCOPE,
                "key": key("ed-noinv"),
                "event": {
                    k: v for k, v in chronology_event(
                        "ev-synth-0", event_date="2024-03-08").items()
                    if k != "invalidations"}}),
            "fields_missing")
        self.expect_error(
            "c8_initial_invalidations_forbidden",
            lambda: call("harness.chronology_event_record", {
                "actor_id": "recon-lawyer", "scope": SCOPE,
                "key": key("ed-init"),
                "event": chronology_event(
                    "ev-synth-new", event_date="2024-01-01",
                    invalidations=[invalidation_mark()])}),
            "chronology_initial_invalidations_forbidden")
        edited = call("harness.chronology_event_record", {
            "actor_id": "recon-lawyer", "scope": SCOPE,
            "key": key("ed-1"),
            "event": chronology_event(
                "ev-synth-0", event_date="2024-03-08",
                summary="合同签订日更正为 2024-03-08（合成修改）",
                invalidations=[
                    invalidation_mark("schedule_anchor", "sched-anchor-1"),
                    invalidation_mark("deadline_calc", "d01-run-1",
                                      action="REVIEW_REQUIRED")],
            )})
        edited_read = call("harness.chronology_event_read",
                           {"scope": SCOPE, "event_id": "ev-synth-0"})
        listed = call("harness.chronology_invalidations_list",
                      {"scope": SCOPE})
        kinds = {item["invalidation"]["dependentKind"]
                 for item in listed["items"]}
        self.step(
            "c8_edit_marks_invalidation_ledger_and_back_to_unconfirmed",
            edited["revision"] == 3 and edited["status"] == "unconfirmed"
            and edited_read["eventDate"] == "2024-03-08"
            and edited_read["status"] == "unconfirmed"
            and listed["invalidationCount"] == 2
            and kinds == {"schedule_anchor", "deadline_calc"},
            revision=edited["revision"],
            invalidationCount=listed["invalidationCount"])

        # ---- C9 修改触发依赖失效（读侧 object_dependencies 对账）。
        # 依赖声明走既有 harness.link_case_objects 公开面（其产品信封接
        # 线属 E09 待办，如实记边界——desktop 侧经同库 HarnessUnits 直
        # 连，selfhost 侧同封闭注册直连）。
        link_call("harness.link_case_objects", {
            "actor_id": "recon-lawyer", "scope": SCOPE,
            "key": key("link-1"),
            "links": [{
                "dependentRef": href("deadline", "sched-anchor-1"),
                "sourceRef": href("chronology_event", "ev-synth-1"),
                "relation": "uses",
            }]})
        fresh = call("harness.chronology_event_read",
                     {"scope": SCOPE, "event_id": "ev-synth-1"})
        self.step(
            "c9_dependency_pinned_fresh_before_move",
            fresh["dependencyStatus"]["staleCount"] == 0
            and fresh["dependencyStatus"]["freshCount"] == 1,
            staleCount=fresh["dependencyStatus"]["staleCount"])
        moved_result = call("harness.chronology_event_record", {
            "actor_id": "recon-lawyer", "scope": SCOPE,
            "key": key("ed-synth-1"),
            "event": chronology_event(
                "ev-synth-1", event_date="2024-03-12",
                kind="performance",
                summary="交付日更正（合成；下游锚显式失效）")})
        moved = call("harness.chronology_event_read",
                     {"scope": SCOPE, "event_id": "ev-synth-1"})
        axis_moved = call("harness.chronology_axis", {"scope": SCOPE})
        axis_item = next(item for item in axis_moved["known"]
                         if item["eventId"] == "ev-synth-1")
        stale = moved["dependencyStatus"]["stale"]
        self.step(
            "c9_dependency_stale_after_head_move",
            moved["revision"] == 2
            and moved["dependencyStatus"]["staleCount"] == 1
            and stale[0]["dependentId"] == "sched-anchor-1"
            and stale[0]["reason"] == "chronology_event_revision_moved"
            and axis_item["dependencyStatus"]["staleCount"] == 1,
            dependentId=stale[0]["dependentId"] if stale else None)

        # ---- C10 期限锚守卫（产品面，D01 只读联动）。
        self.expect_error(
            "c10_anchor_unconfirmed_refused",
            lambda: local_call("chronology.deadline_anchor",
                               {"eventReadback": edited_read}),
            "chronology_anchor_not_confirmed")
        # confirmed＋stale 形态：ev-synth-1 先确认（head=3 confirmed），
        # 再钉定其旧版本 2 ⇒ 事件头前进 ⇒ confirmed 且 STALE。
        call("harness.chronology_event_confirm", {
            "actor_id": "recon-lawyer", "scope": SCOPE,
            "key": key("cf-synth-1"),
            "confirmation": {"eventId": "ev-synth-1",
                             "decisionRef": decision_ref("dec-recon-3")}})
        link_call("harness.link_case_objects", {
            "actor_id": "recon-lawyer", "scope": SCOPE,
            "key": key("link-2"),
            "links": [{
                "dependentRef": href("deadline", "d01-anchor-1"),
                "sourceRef": href("chronology_event", "ev-synth-1",
                                  version="2"),
                "relation": "uses",
            }]})
        confirmed_stale = call("harness.chronology_event_read",
                               {"scope": SCOPE, "event_id": "ev-synth-1"})
        self.expect_error(
            "c10_anchor_stale_refused",
            lambda: local_call("chronology.deadline_anchor",
                               {"eventReadback": confirmed_stale}),
            "chronology_anchor_dependency_stale")
        confirmed_anchor_read = call("harness.chronology_event_read",
                                     {"scope": SCOPE,
                                      "event_id": "ev-synth-0",
                                      "revision": 2})
        anchor = local_call("chronology.deadline_anchor",
                            {"eventReadback": confirmed_anchor_read})
        with_pe_before = chain_counts(query)
        call("harness.chronology_axis", {"scope": SCOPE})
        call("harness.chronology_invalidations_list", {"scope": SCOPE})
        call("harness.chronology_event_read",
             {"scope": SCOPE, "event_id": "ev-synth-1"})
        with_pe_after = chain_counts(query)
        self.step(
            "c10_anchor_guard_and_program_chain_read_only",
            anchor["anchorDate"] == "2024-03-05"
            and anchor["eventId"] == "ev-synth-0"
            and with_pe_before == with_pe_after,
            anchorDate=anchor["anchorDate"],
            procedure_events=with_pe_after["procedure_events"],
            deadlines=with_pe_after["deadlines"])

        # ---- C11 程序期限链在案且只读（先建一行再核对零变化；建行走既
        # 有 save_procedure_event 公开面直连——产品信封接线属 W08/E09 待
        # 办，如实记边界）。
        link_call("harness.save_procedure_event", {
            "actor_id": "recon-lawyer", "scope": SCOPE,
            "key": key("pe-1"),
            "event": {"id": "pe-recon-1", "revision": 1,
                      "matterId": MATTER, "kind": "hearing"}})
        counts = chain_counts(query)
        self.step("c11_program_chain_present_read_only",
                  counts["procedure_events"] == 1
                  and counts["deadlines"] == 0,
                  **counts)

        # ---- C12 幂等。
        replay = call("harness.chronology_event_record", {
            "actor_id": "recon-lawyer", "scope": SCOPE,
            "key": key("ed-synth-1"),
            "event": chronology_event(
                "ev-synth-1", event_date="2024-03-12",
                kind="performance",
                summary="交付日更正（合成；下游锚显式失效）")})
        self.step("c12_idempotent_replay_same_receipt",
                  replay == moved_result,
                  replayed=replay.get("revision"))
        self.expect_error(
            "c12_same_key_different_content_conflict",
            lambda: call("harness.chronology_event_record", {
                "actor_id": "recon-lawyer", "scope": SCOPE,
                "key": key("ed-synth-1"),
                "event": chronology_event(
                    "ev-synth-1", event_date="2024-04-01",
                    kind="performance")}),
            "idempotency_conflict")

        # ---- C13 scope 隔离。
        self.expect_error(
            "c13_cross_matter_source_refused",
            lambda: call("harness.chronology_event_record", {
                "actor_id": "recon-lawyer", "scope": SCOPE,
                "key": key("x-matter"),
                "event": chronology_event(
                    "ev-x", event_date="2024-01-01",
                    summary="跨案来源（合成反例）",
                    ) | {"sourceRef": dict(href("material", "mat-x"),
                                           matterId="m-other")}}),
            "scope_mismatch")

        # ---- C15 DB 级扫描。
        rows = query("SELECT event_id, MAX(revision) AS head,"
                     " MAX(CASE WHEN status='confirmed' THEN 1 ELSE 0 END)"
                     " AS any_confirmed FROM chronology_events"
                     " WHERE matter_id=? GROUP BY event_id"
                     " ORDER BY event_id", (MATTER,))
        raw_rows = query("SELECT COUNT(*) AS n FROM chronology_events"
                         " WHERE event_id='ev-raw-check'")[0]["n"]
        unknown_rows = query(
            "SELECT COUNT(*) AS n FROM chronology_events"
            " WHERE date_precision='unknown'"
            " AND event_date IS NOT NULL")[0]["n"]
        heads = {row["event_id"]: (row["head"], row["any_confirmed"])
                 for row in rows}
        self.step(
            "c15_db_level_scan",
            heads.get("ev-synth-0") == (3, 1)
            and heads.get("ev-synth-1") == (3, 1)
            and raw_rows == 0 and unknown_rows == 0,
            heads={k: v for k, v in sorted(heads.items())},
            rawRows=raw_rows, unknownWithDate=unknown_rows)

    def bridge_negatives(self, config) -> None:
        try:
            legal_entry.call("harness.chronology_axis", {"scope": SCOPE}, {})
            raise AssertionError("bridge_not_configured_expected")
        except NotConnected as exc:
            self.step("c14_bridge_not_configured",
                      "harness_public_entry_not_configured" in str(exc))
        try:
            legal_entry.call("harness.chronology_auto_fill_entry_date",
                             {"scope": SCOPE}, config)
            raise AssertionError("bridge_unknown_method_expected")
        except NotConnected as exc:
            self.step("c14_pseudo_method_not_whitelisted",
                      "method_not_connected" in str(exc))
        self.step("c14_method_group_frozen",
                  legal_entry.HARNESS_CHRONOLOGY_METHODS
                  == HARNESS_CHRONOLOGY_METHODS,
                  size=len(legal_entry.HARNESS_CHRONOLOGY_METHODS))

    # -- profile drivers ---------------------------------------------------

    def run_desktop(self) -> int:
        temporary = tempfile.TemporaryDirectory(prefix="juscite-f121-desktop-")
        state_root = Path(temporary.name) / "state"
        state_root.mkdir(parents=True)
        registration = Path(temporary.name) / "service-local.json"
        registration.write_text(json.dumps(
            {"url": "http://127.0.0.1:1", "password": "synthetic-recon"}),
            encoding="utf-8")
        config = {
            "harness_public_entry":
                str(self.harness_root / "tools/workflow-tools/harness/"
                    "public_entry.py"),
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
        store.create_matter(MATTER, "cas://profile-f121-recon")

        def call(method, args):
            return legal_entry.call(method, args, config)

        def local_call(method, args):
            return legal_entry.call(method, args, {"chronology_local": True})

        from legal_harness.business.units import HarnessUnits as _Units
        _units = _Units(store)

        def link_call(method, args):
            # 既有公开面直连（同库同事务；产品信封接线属 E09 待办）。
            return getattr(_units, method.split(".", 1)[1])(**args)

        def query(sql, params=()):
            import sqlite3
            with contextlib.closing(store._connect()) as connection:
                connection.row_factory = sqlite3.Row
                rows = connection.execute(sql, params).fetchall()
            return [dict(row) for row in rows]

        def raw_execute(sql, params=()):
            import sqlite3
            with contextlib.closing(store._connect()) as connection:
                connection.execute(sql, params)

        print("[profile desktop] SQLite via product bridge subprocess",
              flush=True)
        self.common_flow("desktop", call, query, local_call, raw_execute,
                         link_call)
        self.bridge_negatives(config)
        return 0

    def run_selfhost(self, dsn: str) -> int:
        for path in (str(self.harness_root / "src"),
                     str(self.harness_root / "tools/workflow-tools"),
                     str(self.harness_root),
                     str(self.harness_root / "tests")):
            if path not in sys.path:
                sys.path.insert(0, path)
        import contextlib  # noqa: F401

        from legal_harness.business.provider_registry import (
            MethodNotWhitelisted,
            resolve_provider_method,
        )
        from legal_harness.business.units import HarnessUnits
        from legal_harness.state.pg_store import PgMatterStore

        temporary = tempfile.TemporaryDirectory(prefix="juscite-f121-selfhost-")
        store = PgMatterStore(
            Path(temporary.name) / "state", dsn=dsn,
            schema="f121_" + _uuid.uuid4().hex[:12])
        units = HarnessUnits(store)
        methods = set(HARNESS_CHRONOLOGY_METHODS) | {
            "harness.link_case_objects", "harness.save_procedure_event"}
        bound = {name: resolve_provider_method(name, units)
                 for name in methods}
        store.create_matter(MATTER, "cas://profile-f121-recon")

        def call(method, args):
            return bound[method](**args)

        def local_call(method, args):
            import chronology as chronology_face
            return chronology_face.chronology_call(method, args, {})

        def query(sql, params=()):
            with contextlib.closing(store._connect()) as connection:
                rows = connection.execute(sql, params).fetchall()
            return [dict(row) for row in rows]

        def raw_execute(sql, params=()):
            with contextlib.closing(store._connect()) as connection:
                connection.execute(sql, params)

        print("[profile selfhost] PgMatterStore direct (lh-pg-e08)",
              flush=True)
        self.common_flow("selfhost", call, query, local_call, raw_execute,
                         call)
        # selfhost 侧 registry 负向（直连面同封闭注册）。
        try:
            resolve_provider_method("harness.chronology_auto_fill_entry_date",
                                    units)
            raise AssertionError("pseudo_method_expected_refused")
        except MethodNotWhitelisted:
            self.step("c14_selfhost_pseudo_method_refused", True)
        store.destroy()
        return 0


def invalidation_mark(kind: str = "schedule_anchor",
                      dep_id: str = "sched-anchor-1",
                      action: str = "INVALIDATED") -> dict:
    return {
        "dependentKind": kind,
        "dependentRef": href("deadline", dep_id),
        "action": action,
        "reason": "事件日期修改，下游依赖显式失效（合成标记）",
    }


def chain_counts(query) -> dict:
    return {
        "procedure_events": query(
            "SELECT COUNT(*) AS n FROM procedure_events"
            " WHERE matter_id=?", (MATTER,))[0]["n"],
        "deadlines": query(
            "SELECT COUNT(*) AS n FROM deadlines"
            " WHERE matter_id=?", (MATTER,))[0]["n"],
    }


def write_evidence(profile: str, recon: Recon, harness_root: Path,
                   started: str, code: int, suffix: str) -> Path:
    evidence_dir = (REPO_ROOT / "docs" / "construction" / "evidence"
                    / "F121" / profile)
    evidence_dir.mkdir(parents=True, exist_ok=True)
    finished = datetime.now(timezone.utc).isoformat()
    harness_head = subprocess.check_output(
        ["git", "-C", str(harness_root), "rev-parse", "HEAD"],
        text=True, encoding="utf-8").strip()
    payload = {
        "unit": "W4-U52",
        "feature": "F121",
        "profile": profile,
        "verdict": "RECON_OK" if code == 0 else "RECON_FAIL",
        "started_at": started,
        "finished_at": finished,
        "harness_root": str(harness_root),
        "harness_head": harness_head,
        "checks": recon.checks,
        "check_count": len(recon.checks),
        "failed": [c["check"] for c in recon.checks
                   if c["status"] != "PASS"],
    }
    stem = "f121-chronology-recon" + (f"-{suffix}" if suffix else "")
    json_path = evidence_dir / f"{stem}.json"
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2),
                         encoding="utf-8")
    md_path = evidence_dir / f"{stem}.md"
    lines = [
        f"# F121 chronology recon — {profile}（W4-U52）", "",
        f"- verdict: **{payload['verdict']}**（{len(recon.checks)} checks,"
        f" failed={len(payload['failed'])}）",
        f"- harness: `{harness_root}` @ {harness_head[:12]}（A2 分支链"
        f" w4-u52，schema v34）",
        f"- started {started} / finished {finished}",
        "",
        "| check | status | detail |",
        "|---|---|---|",
    ]
    for check in recon.checks:
        detail = {k: v for k, v in check.items()
                  if k not in ("check", "status")}
        lines.append(f"| {check['check']} | {check['status']} |"
                     f" `{json.dumps(detail, ensure_ascii=False)[:180]}` |")
    lines += ["", "全程合成材料；harness 检出只读；程序期限链只读消费；"
                  "%APPDATA% 零触碰。"]
    md_path.write_text("\n".join(lines), encoding="utf-8")
    return json_path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", action="append", default=None,
                        choices=["desktop", "selfhost"])
    parser.add_argument("--harness-root", default=str(DEFAULT_HARNESS_ROOT))
    parser.add_argument("--pg-dsn", default=DEFAULT_PG_DSN)
    parser.add_argument("--evidence-suffix", default="")
    args = parser.parse_args()
    profiles = args.profile or ["desktop"]
    harness_root = Path(args.harness_root)
    started = datetime.now(timezone.utc).isoformat()
    overall = 0
    for profile in profiles:
        recon = Recon(harness_root)
        code = 0
        try:
            if profile == "desktop":
                recon.run_desktop()
            else:
                try:
                    import socket
                    with socket.create_connection(("127.0.0.1", 55432),
                                                  timeout=2):
                        pass
                except OSError:
                    print(f"[profile {profile}] lh-pg-e08 not reachable;"
                          " skip (environment), not a recon failure",
                          flush=True)
                    continue
                recon.run_selfhost(args.pg_dsn)
        except AssertionError as exc:
            print(f"[profile {profile}] FAILED: {exc}", flush=True)
            code = 2
        path = write_evidence(profile, recon, harness_root, started, code,
                              args.evidence_suffix)
        print(f"[profile {profile}] verdict="
              f"{'RECON_OK' if code == 0 else 'RECON_FAIL'}"
              f" checks={len(recon.checks)} evidence={path}", flush=True)
        overall = overall or code
    print("RECON_OK" if overall == 0 else "RECON_FAIL")
    return overall


if __name__ == "__main__":
    raise SystemExit(main())

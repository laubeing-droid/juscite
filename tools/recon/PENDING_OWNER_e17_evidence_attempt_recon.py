"""E17 取证范围与部分失败对账（W2b-U25）——双 profile（desktop/selfhost）。

对账对象：harness 分支 w2b-u25（基于施工链头 w2b-u05@32da892e＝
w2a-u05→w2a-u06(F114)→w2b-u01(F25)→w2b-u11(F47)→w2b-u23(E15)→
w2b-u05(F82) 同链接力）的 public_entry --evidenceattempt-json 封闭径
——desktop profile 与产品桥（legal_entry → 子进程 public_entry）完全
同一条链（SQLite 状态根）；selfhost profile＝PgMatterStore 直连
lh-pg-e08（resolve_provider_method 同一封闭注册）。全部合成材料：临时
状态根、合成任务/授权/申请/收件/拒绝/费用；harness 检出零字节改动
（只运行其代码，git 只读命令核对分支）。

实跑覆盖（PENDING_OWNER_E17_evidence_attempt，04§6/05§9.4 合成规格）：
  登记十项同粒度请求（planned 0/10）→ 塞 fileCount 字段拒＋缺授权 ref
  拒＋请求范围空拒＋收件先于申请拒（没有实际申请不能记已执行）→
  十项申请全带凭据（unresponsive 保持未知）→ 收 4 含 1 不利（覆盖
  4/10；6 未回应保持未知；不用文件数——投影无文件计数字段）→ 不利
  材料 adverseMaterialRefs 经 E15 assessment_delta_record 进入场景二
  重评（跨合同实测）→ 已知费用 300 元入账＋重导同内容幂等不双数费＋
  同凭据双挂拒 → 同 4 项重发再收仍 4/10（不变 8/10）→ 真拒绝/超期
  带来源落地（无来源具名拒）→ 替代轮 substituteFor 可回读（目标缺失
  拒）→ 关闭：taskStatus=closed 与 proofGap.open 分别呈现（本轮任务
  可结束但证明缺口不被勾掉）＋无理由拒＋双关闭拒＋closed 后事件拒
  → DB 级扫描（两账行数/事件账条数/重评账跨合同行）→ 桥负向（未配置
  NOT_CONNECTED／未知方法 method_not_connected／方法组冻结）。

用法：
  python -X utf8 tools/recon/PENDING_OWNER_e17_evidence_attempt_recon.py \
      --profile desktop --profile selfhost

退出码：0 = 全部 profile RECON_OK；2 = RECON_FAIL；3 = 环境缺失。
证据：docs/construction/evidence/E17/<profile>/ JSON＋MD。
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
    r"D:\Codex\1.法律工作区\legal-harness工作区\legal-harness-repo\.local\worktrees\w2b-u25")

MATTER = "m-e17-recon"
SCOPE = {"kind": "matter", "matterId": MATTER}

# lh-pg-e08 容器（E08 拓扑）：仅回环端口、合成专用凭据（LH_PG_PASSWORD
# 同源，密钥只在本机容器；可用 LH_E08_PG_DSN 覆写）。
DEFAULT_PG_DSN = "postgresql://lh_app:e08-synth-only@127.0.0.1:55432/legal_harness"

E17_METHODS = frozenset({
    "harness.evidence_attempt_register", "harness.evidence_attempt_apply",
    "harness.evidence_attempt_receipt", "harness.evidence_attempt_resolve",
    "harness.evidence_attempt_cost", "harness.evidence_attempt_close",
    "harness.evidence_attempt_read", "harness.evidence_attempt_list",
})

OBTAINED_ITEMS = ("ev-2", "ev-4", "ev-6", "ev-8")
ALL_ITEMS = tuple(f"ev-{number}" for number in range(1, 11))
UNRESPONSIVE_AFTER_RESOLVE = ("ev-1", "ev-3", "ev-9", "ev-10")


def key(request_id: str) -> dict:
    return {"requestId": request_id, "targetId": None,
            "expectedRevision": None, "inputRefs": []}


def href(kind: str, ref_id: str) -> dict:
    return {"owner": "harness", "kind": kind, "id": ref_id,
            "version": "1", "matterId": MATTER}


def synth_item(item_id: str) -> dict:
    return {
        "itemId": item_id,
        "proposition": f"待证命题：{item_id}（E17 对账合成）",
        "channel": "法院调查令·银行流水（合成渠道）",
        "authorizationRef": href("authorization", f"auth-{item_id}"),
        "requestScope": {"project": "货款纠纷", "period": "2025-01~2025-12",
                         "subject": "甲公司", "materialType": "银行流水"},
        "deadlineNote": "十五个工作日内回复（合成期限）",
        "note": "全合成请求项",
    }


def synth_attempt(attempt_id: str = "ea-1") -> dict:
    return {
        "attemptId": attempt_id,
        "taskRef": href("task", "t-evidence-1"),
        "title": "十项同粒度取证请求（E17 对账合成轮）",
        "items": [synth_item(item_id) for item_id in ALL_ITEMS],
        "note": "全合成取证轮",
    }


def application(attempt_id: str, item_ids, tag: str) -> dict:
    return {"attemptId": attempt_id, "applications": [
        {"applicationId": f"app-{tag}-{item_id}", "itemId": item_id,
         "sourceRefs": [href("application-receipt", f"ar-{tag}-{item_id}")],
         "note": f"实际申请凭据（合成 {tag}）"}
        for item_id in item_ids]}


def receipt(receipt_id: str, item_id: str, *, adverse: bool = False,
            completeness: str = "complete") -> dict:
    return {"receiptId": receipt_id, "itemId": item_id,
            "materialRef": href("material", f"mat-{item_id}"),
            "completeness": completeness, "relevance": "relevant",
            "adverse": adverse, "readable": True,
            "verificationStatus": "pending",
            "resultRefs": [href("result-source", f"rs-{receipt_id}")],
            "note": "实际收件（合成）"}


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
            ["git", "-C", str(root), *args], text=True).strip()

    def branch_checks(self):
        branch = self.git(self.harness_root, "rev-parse", "--abbrev-ref", "HEAD")
        base = self.git(self.harness_root, "merge-base", "HEAD", "w2b-u05")
        master = self.git(self.harness_root, "rev-parse", "master")
        self.step("c01_harness_branch", branch == "w2b-u25", branch=branch)
        self.step("c01_harness_base_on_w2b_u05", base.startswith("32da892e"),
                  base=base)
        self.step("c01_harness_master_untouched", master.startswith("929d0802"),
                  master=master)
        dirty = self.git(self.harness_root, "status", "--porcelain")
        self.step("c01_harness_worktree_clean", dirty == "", dirty=dirty[:200])

    # ------------------------------------------------------------------
    # C02–C12：call(method, args) 走被测链；query(sql, params) 直读库。
    # ------------------------------------------------------------------
    def common_flow(self, profile: str, call, query):
        # ---- C02 登记十项同粒度请求：planned 0/10、缺口全开、零文件数。
        registered = call("harness.evidence_attempt_register", {
            "actor_id": "recon-assistant", "scope": SCOPE,
            "key": key("reg-1"), "attempt": synth_attempt()})
        view = registered["attempt"]
        flat = json.dumps(view, ensure_ascii=False)
        self.step("c02_ten_registered_all_planned_zero_coverage",
                  view["state"] == "open"
                  and view["counts"]["planned"] == 10
                  and view["coverage"]["requested"] == 10
                  and view["coverage"]["obtained"] == 0
                  and view["coverage"]["coverageRatio"] == "0/10"
                  and view["coverage"]["measure"] == "requested_items"
                  and view["proofGap"]["open"] is True
                  and len(view["proofGap"]["gapItemIds"]) == 10
                  # 不用文件数：投影无文件计数字段。
                  and "fileCount" not in flat and "file_count" not in flat
                  and "filesObtained" not in flat,
                  ratio=view["coverage"]["coverageRatio"])

        # ---- C03 登记负向：塞 fileCount 字段拒（闭集）；缺授权 ref 拒；
        # 请求范围空拒；收件先于申请拒（没有实际申请不能记已执行）。
        stuffed = synth_attempt("ea-stuff")
        stuffed["fileCount"] = 4
        self.expect_error("c03_stuffed_file_count_refused", lambda: call(
            "harness.evidence_attempt_register", {
                "actor_id": "recon-assistant", "scope": SCOPE,
                "key": key("reg-stuff"), "attempt": stuffed}),
            "fields_not_closed")
        no_auth = synth_attempt("ea-noauth")
        del no_auth["items"][0]["authorizationRef"]
        self.expect_error("c03_item_without_authorization_refused", lambda: call(
            "harness.evidence_attempt_register", {
                "actor_id": "recon-assistant", "scope": SCOPE,
                "key": key("reg-noauth"), "attempt": no_auth}),
            "fields_missing")
        empty_scope = synth_attempt("ea-emptscope")
        empty_scope["items"][0]["requestScope"] = {
            "project": " ", "period": "", "subject": None,
            "materialType": ""}
        self.expect_error("c03_empty_request_scope_refused", lambda: call(
            "harness.evidence_attempt_register", {
                "actor_id": "recon-assistant", "scope": SCOPE,
                "key": key("reg-emptscope"), "attempt": empty_scope}),
            "evidence_item_request_scope_empty")
        self.expect_error("c03_receipt_before_application_refused", lambda: call(
            "harness.evidence_attempt_receipt", {
                "actor_id": "recon-assistant", "scope": SCOPE,
                "key": key("rcpt-early"),
                "receipt": {"attemptId": "ea-1",
                            "receipts": [receipt("r-early", "ev-1")]}}),
            "evidence_receipt_requires_application:ev-1")
        events_after_negatives = query(
            "SELECT COUNT(*) AS n FROM evidence_events WHERE matter_id=?",
            (MATTER,))[0]["n"]
        self.step("c03_negatives_left_zero_events", events_after_negatives == 0,
                  events=events_after_negatives)

        # ---- C04 十项申请全带凭据：unresponsive 保持未知（不是拒绝或
        # 事实为假）；申请无凭据拒。
        applied = call("harness.evidence_attempt_apply", {
            "actor_id": "recon-assistant", "scope": SCOPE,
            "key": key("app-1"), "application": application(
                "ea-1", ALL_ITEMS, "1")})
        view = applied["attempt"]
        self.step("c04_ten_applied_all_unresponsive_unknown",
                  view["counts"]["unresponsive"] == 10
                  and view["coverage"]["coverageRatio"] == "0/10"
                  and view["proofGap"]["open"] is True
                  and all(item["applications"]
                          and item["status"] == "unresponsive"
                          for item in view["items"]),
                  unresponsive=view["counts"]["unresponsive"])
        no_source = application("ea-1", ["ev-1"], "nosrc")
        no_source["applications"][0]["sourceRefs"] = []
        self.expect_error("c04_apply_without_source_refused", lambda: call(
            "harness.evidence_attempt_apply", {
                "actor_id": "recon-assistant", "scope": SCOPE,
                "key": key("app-nosrc"), "application": no_source}),
            "evidence_application_source_required")

        # ---- C05 收 4 含 1 不利：覆盖 4/10；6 未回应保持未知。
        obtained = call("harness.evidence_attempt_receipt", {
            "actor_id": "recon-assistant", "scope": SCOPE,
            "key": key("rcpt-1"),
            "receipt": {"attemptId": "ea-1", "receipts": [
                receipt("r-2", "ev-2", adverse=True),
                receipt("r-4", "ev-4"),
                receipt("r-6", "ev-6", completeness="partial"),
                receipt("r-8", "ev-8")]}})
        view = obtained["attempt"]
        by_id = {item["itemId"]: item for item in view["items"]}
        self.step("c05_four_of_ten_with_one_adverse",
                  view["coverage"]["requested"] == 10
                  and view["coverage"]["obtained"] == 4
                  and view["coverage"]["adverseObtained"] == 1
                  and view["coverage"]["coverageRatio"] == "4/10"
                  and view["counts"]["unresponsive"] == 6
                  and by_id["ev-2"]["adverse"] is True
                  and by_id["ev-6"]["lastReceipt"]["completeness"]
                  == "partial"
                  and view["adverseMaterialRefs"]
                  == [href("material", "mat-ev-2")]
                  # 未回应≠拒绝/事实假：无 sourced resolution 不得改写。
                  and by_id["ev-1"]["status"] == "unresponsive"
                  and by_id["ev-1"]["resolution"] is None,
                  ratio=view["coverage"]["coverageRatio"])

        # ---- C06 不利材料进入场景二重评（E15 assessment_delta 跨合同）。
        delta = call("harness.assessment_delta_record", {
            "actor_id": "recon-assistant", "scope": SCOPE,
            "key": key("adverse-delta"),
            "delta": {"deltaId": "ad-e17-adverse", "changeReason": "material",
                      "oldInputRefs": [href("material", "mat-e17-base")],
                      "newInputRefs": view["adverseMaterialRefs"],
                      "items": [
                          {"kind": "fact", "ref": href("fact", "f-loss"),
                           "outcome": "weakened",
                           "reason": "不利材料进入复评：削弱损失数额认定（合成）",
                           "basisRefs": [{"owner": "jc", "kind": "issue-result",
                                          "id": "ir-e17", "version": "1",
                                          "matterId": MATTER}]},
                          {"kind": "issue", "ref": href("issue", "issue-base"),
                           "outcome": "undetermined",
                           "reason": "6 项未回应，命题状态未知不伪支持（合成）",
                           "basisRefs": []}],
                      "counterEvidenceRefs": [href("material", "mat-ev-2")],
                      "rescopeRefs": [href("artifact", "a-brief")],
                      "note": "E17 不利材料触发场景二重评（全合成）"}})
        delta_read = call("harness.assessment_delta_read", {
            "scope": SCOPE, "delta_id": "ad-e17-adverse"})["delta"]
        self.step("c06_adverse_material_into_reevaluation",
                  delta["delta"]["deltaId"] == "ad-e17-adverse"
                  and delta_read["delta"]["newInputRefs"]
                  == [href("material", "mat-ev-2")]
                  and [item["outcome"] for item
                       in delta_read["delta"]["items"]]
                  == ["weakened", "undetermined"],
                  newInputs=delta_read["delta"]["newInputRefs"])

        # ---- C07 已知费用 300 元：入账＋重导幂等不双数费＋同凭据双挂拒。
        cost = call("harness.evidence_attempt_cost", {
            "actor_id": "recon-assistant", "scope": SCOPE,
            "key": key("cost-1"),
            "cost": {"attemptId": "ea-1", "costId": "fee-1",
                     "amountCents": 30000,
                     "sourceRef": href("cost-voucher", "voucher-300"),
                     "scopeItemIds": list(ALL_ITEMS),
                     "note": "已知费用300元（合成）"}})
        replay = call("harness.evidence_attempt_cost", {
            "actor_id": "recon-assistant", "scope": SCOPE,
            "key": key("cost-1-reimport"),
            "cost": {"attemptId": "ea-1", "costId": "fee-1",
                     "amountCents": 30000,
                     "sourceRef": href("cost-voucher", "voucher-300"),
                     "scopeItemIds": list(ALL_ITEMS),
                     "note": "已知费用300元（合成）"}})
        self.step("c07_cost_recorded_reimport_idempotent",
                  cost["attempt"]["totalCostCents"] == {"CNY": 30000}
                  and replay["replayed"] is True
                  and replay["attempt"]["totalCostCents"] == {"CNY": 30000},
                  total=replay["attempt"]["totalCostCents"])
        self.expect_error("c07_same_voucher_second_cost_refused", lambda: call(
            "harness.evidence_attempt_cost", {
                "actor_id": "recon-assistant", "scope": SCOPE,
                "key": key("cost-2-clash"),
                "cost": {"attemptId": "ea-1", "costId": "fee-2",
                         "amountCents": 30000,
                         "sourceRef": href("cost-voucher", "voucher-300")}}),
            "evidence_cost_source_conflict")
        self.expect_error("c07_cost_without_voucher_refused", lambda: call(
            "harness.evidence_attempt_cost", {
                "actor_id": "recon-assistant", "scope": SCOPE,
                "key": key("cost-nov"),
                "cost": {"attemptId": "ea-1", "costId": "fee-n",
                         "amountCents": 30000, "sourceRef": None}}),
            "ref_invalid")

        # ---- C08 同 4 项重发再收：仍 4/10（不变 8/10），费用不重复。
        resent = call("harness.evidence_attempt_apply", {
            "actor_id": "recon-assistant", "scope": SCOPE,
            "key": key("app-2"),
            "application": application("ea-1", OBTAINED_ITEMS, "2")})
        reobtained = call("harness.evidence_attempt_receipt", {
            "actor_id": "recon-assistant", "scope": SCOPE,
            "key": key("rcpt-2"),
            "receipt": {"attemptId": "ea-1", "receipts": [
                receipt("r-2b", "ev-2", adverse=True),
                receipt("r-4b", "ev-4"),
                receipt("r-6b", "ev-6"),
                receipt("r-8b", "ev-8")]}})
        view = reobtained["attempt"]
        by_id = {item["itemId"]: item for item in view["items"]}
        self.step("c08_resend_same_four_stays_4_of_10",
                  resent["applied"] == 4
                  and view["coverage"]["coverageRatio"] == "4/10"
                  and view["coverage"]["obtained"] == 4
                  and view["counts"]["obtained"] == 4
                  and view["counts"]["unresponsive"] == 6
                  and len(by_id["ev-2"]["applications"]) == 2
                  and len(by_id["ev-2"]["receipts"]) == 2
                  and view["totalCostCents"] == {"CNY": 30000},
                  ratio=view["coverage"]["coverageRatio"],
                  total=view["totalCostCents"])

        # ---- C09 真拒绝与超期须来源：带来源落地；无来源具名拒。
        resolved = call("harness.evidence_attempt_resolve", {
            "actor_id": "recon-assistant", "scope": SCOPE,
            "key": key("res-1"),
            "resolution": {"attemptId": "ea-1", "resolutions": [
                {"resolutionId": "res-5", "itemId": "ev-5",
                 "resolution": "refused",
                 "sourceRefs": [href("refusal-notice", "fn-5")],
                 "note": "对方书面拒绝（合成）"},
                {"resolutionId": "res-7", "itemId": "ev-7",
                 "resolution": "overdue",
                 "sourceRefs": [href("deadline-record", "dr-7")],
                 "note": "超期无回应（合成）"}]}})
        view = resolved["attempt"]
        by_id = {item["itemId"]: item for item in view["items"]}
        no_source = {"attemptId": "ea-1", "resolutions": [
            {"resolutionId": "res-nosrc", "itemId": "ev-9",
             "resolution": "refused", "sourceRefs": []}]}
        self.expect_error("c09_resolution_without_source_refused", lambda: call(
            "harness.evidence_attempt_resolve", {
                "actor_id": "recon-assistant", "scope": SCOPE,
                "key": key("res-nosrc"), "resolution": no_source}),
            "evidence_resolution_source_required")
        self.step("c09_refused_overdue_sourced_recorded",
                  by_id["ev-5"]["status"] == "refused"
                  and by_id["ev-7"]["status"] == "overdue"
                  and by_id["ev-5"]["resolution"]["sourceRefs"]
                  == [href("refusal-notice", "fn-5")]
                  and view["counts"]["unresponsive"] == 4
                  and view["counts"]["refused"] == 1
                  and view["counts"]["overdue"] == 1
                  and sorted(view["proofGap"]["unresponsiveItemIds"])
                  == sorted(UNRESPONSIVE_AFTER_RESOLVE)
                  # 终局仍属证明缺口（缺口不被勾掉）。
                  and "ev-5" in view["proofGap"]["gapItemIds"]
                  and "ev-7" in view["proofGap"]["gapItemIds"],
                  counts=view["counts"])

        # ---- C10 替代轮：substituteFor 引用可回读；目标缺失拒。
        substitute = synth_attempt("ea-2")
        substitute["items"] = [dict(synth_item("ev-5-sub"),
                                    substituteFor={"attemptId": "ea-1",
                                                   "itemId": "ev-5"})]
        sub_registered = call("harness.evidence_attempt_register", {
            "actor_id": "recon-assistant", "scope": SCOPE,
            "key": key("reg-sub"), "attempt": substitute})
        sub_view = sub_registered["attempt"]["items"][0]
        substitute_missing = synth_attempt("ea-2b")
        substitute_missing["items"] = [dict(
            synth_item("ev-x-sub"),
            substituteFor={"attemptId": "ea-404", "itemId": "ev-1"})]
        self.expect_error("c10_substitute_target_missing_refused", lambda: call(
            "harness.evidence_attempt_register", {
                "actor_id": "recon-assistant", "scope": SCOPE,
                "key": key("reg-sub404"), "attempt": substitute_missing}),
            "evidence_substitute_attempt_not_found:ea-404")
        self.step("c10_substitute_round_readable",
                  sub_view["substituteFor"] == {"attemptId": "ea-1",
                                                "itemId": "ev-5"},
                  substituteFor=sub_view["substituteFor"])

        # ---- C11 关闭：任务完成与证明缺口分别呈现；负向三连。
        closed = call("harness.evidence_attempt_close", {
            "actor_id": "recon-lawyer", "scope": SCOPE,
            "key": key("close-1"),
            "close": {"attemptId": "ea-1",
                      "reasonRef": href("decision", "dec-stop-round-1"),
                      "followups": [
                          {"itemId": "ev-1", "nextStep": "stop",
                           "note": "客户指示停止（合成）"},
                          {"itemId": "ev-3", "nextStep": "resend"},
                          {"itemId": "ev-9", "nextStep": "substitute",
                           "nextTaskRef": href("task", "t-substitute-9")}],
                      "note": "本轮申请/收件任务结束（合成）"}})
        view = closed["attempt"]
        self.step("c11_close_task_and_gap_presented_separately",
                  view["state"] == "closed"
                  and view["taskStatus"] == "closed"
                  and view["proofGap"]["open"] is True
                  and len(view["proofGap"]["gapItemIds"]) == 6
                  and view["coverage"]["coverageRatio"] == "4/10"
                  and [followup["nextStep"]
                       for followup in view["close"]["followups"]]
                  == ["stop", "resend", "substitute"]
                  and view["close"]["followups"][2]["nextTaskRef"]
                  == href("task", "t-substitute-9"),
                  taskStatus=view["taskStatus"],
                  gapOpen=view["proofGap"]["open"])
        self.expect_error("c11_close_without_reason_refused", lambda: call(
            "harness.evidence_attempt_close", {
                "actor_id": "recon-lawyer", "scope": SCOPE,
                "key": key("close-noreason"), "close": {"attemptId": "ea-1"}}),
            "fields_missing")
        self.expect_error("c11_double_close_refused", lambda: call(
            "harness.evidence_attempt_close", {
                "actor_id": "recon-lawyer", "scope": SCOPE,
                "key": key("close-2"),
                "close": {"attemptId": "ea-1",
                          "reasonRef": href("decision", "dec-stop-2")}}),
            "evidence_attempt_state_invalid:closed")
        self.expect_error("c11_event_after_close_refused", lambda: call(
            "harness.evidence_attempt_apply", {
                "actor_id": "recon-assistant", "scope": SCOPE,
                "key": key("app-late"),
                "application": application("ea-1", ["ev-1"], "late")}),
            "evidence_attempt_state_invalid:closed")

        # ---- C12 DB 级扫描：两账行数＋事件账条数＋重评账跨合同行。
        attempts_db = query(
            "SELECT attempt_id, state FROM evidence_attempts"
            " WHERE matter_id=? ORDER BY attempt_id", (MATTER,))
        events_db = query(
            "SELECT event_kind, COUNT(*) AS n FROM evidence_events"
            " WHERE matter_id=? AND attempt_id='ea-1' GROUP BY event_kind",
            (MATTER,))
        deltas_db = query(
            "SELECT COUNT(*) AS n FROM assessment_deltas WHERE matter_id=?",
            (MATTER,))[0]["n"]
        kind_counts = {row["event_kind"]: row["n"] for row in events_db}
        self.step("c12_db_level_scan",
                  [(row["attempt_id"], row["state"]) for row in attempts_db]
                  == [("ea-1", "closed"), ("ea-2", "open")]
                  and kind_counts == {"application": 14, "cost": 1,
                                      "receipt": 8, "resolution": 2}
                  and deltas_db == 1,
                  attempts=[(row["attempt_id"], row["state"])
                            for row in attempts_db],
                  events=kind_counts, deltas=deltas_db)

        # ---- C13（共用）回读面：read/list。
        read = call("harness.evidence_attempt_read", {
            "scope": SCOPE, "attempt_id": "ea-1"})["attempt"]
        listing = call("harness.evidence_attempt_list", {"scope": SCOPE})
        self.step("c12_readback_faces",
                  read["attemptId"] == "ea-1" and read["state"] == "closed"
                  and listing["attemptCount"] == 2
                  and listing["stateCounts"] == {"closed": 1, "open": 1},
                  stateCounts=listing["stateCounts"])

    def bridge_negatives(self, config):
        # ---- C13 桥负向：未配置/未知方法/方法组冻结。
        try:
            legal_entry.call("harness.evidence_attempt_register",
                             {"scope": SCOPE}, {})
            raise AssertionError("bridge_not_configured_expected")
        except NotConnected as exc:
            self.step("c13_bridge_not_configured",
                      "harness_public_entry_not_configured" in str(exc))
        try:
            legal_entry.call("harness.evidence_attempt_send",
                             {"scope": SCOPE}, config)
            raise AssertionError("bridge_unknown_method_expected")
        except NotConnected as exc:
            self.step("c13_bridge_unknown_method_refused",
                      "method_not_connected" in str(exc))
        self.step("c13_method_group_frozen",
                  legal_entry.HARNESS_EVIDENCE_ATTEMPT_METHODS == E17_METHODS)

    # -- profile drivers ---------------------------------------------------

    def run_desktop(self) -> int:
        temporary = tempfile.TemporaryDirectory(prefix="juscite-e17-desktop-")
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
        store.create_matter(MATTER, "cas://profile-e17-recon")

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

        temporary = tempfile.TemporaryDirectory(prefix="juscite-e17-selfhost-")
        store = PgMatterStore(
            Path(temporary.name) / "state", dsn=dsn,
            schema="e17_" + _uuid.uuid4().hex[:12])
        units = HarnessUnits(store)
        methods = set(E17_METHODS) | {
            "harness.assessment_delta_record", "harness.assessment_delta_read"}
        bound = {name: resolve_provider_method(name, units)
                 for name in methods}
        store.create_matter(MATTER, "cas://profile-e17-recon")

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
    evidence_dir = REPO_ROOT / "docs" / "construction" / "evidence" / "E17" \
        / profile
    evidence_dir.mkdir(parents=True, exist_ok=True)
    finished = datetime.now(timezone.utc).isoformat()
    summary = {
        "schema": "juscite-e17-evidence-attempt-recon/1",
        "unit": "W2b-U25",
        "feature": "E17",
        "profile": profile,
        "verdict": "RECON_OK" if code == 0 else "RECON_FAIL",
        "started_at": started,
        "finished_at": finished,
        "harness_worktree": str(harness_root),
        "harness_branch": "w2b-u25",
        "harness_base": "w2b-u05@32da892e (w2a-u05→w2a-u06/F114→w2b-u01/F25"
                        "→w2b-u11/F47)→w2b-u23/E15→w2b-u05/F82)",
        "checks": recon.checks,
        "check_count": len(recon.checks),
        "failed": [c["check"] for c in recon.checks
                   if c["status"] != "PASS"],
    }
    payload = json.dumps(summary, ensure_ascii=False, indent=1)
    (evidence_dir / "e17_evidence_attempt_recon.json").write_text(
        payload + "\n", encoding="utf-8")
    lines = [f"# E17 取证范围与部分失败 recon（{profile}）",
             "",
             f"- unit: W2b-U25 · profile: {profile}",
             f"- verdict: **{summary['verdict']}**"
             f" ({len(recon.checks)} checks, exit {code})",
             f"- harness: `{harness_root}` @ branch w2b-u25"
             "（基 w2b-u05@32da892e；master 929d0802 零动）",
             f"- started: {started} · finished: {finished}",
             "",
             "| # | check | status |",
             "|---|---|---|"]
    for index, check in enumerate(recon.checks, 1):
        lines.append(f"| {index} | {check['check']}"
                     f" | {check['status']} |")
    lines += ["", "全部合成材料；desktop＝产品桥子进程全链（SQLite 状态根），"
              "selfhost＝PgMatterStore 直连 lh-pg-e08（同一封闭注册）；"
              "C05＝10 同粒度请求收 4 含 1 不利（覆盖 4/10，6 未回应保持"
              "未知）；C06＝不利材料经 E15 assessment_delta 进入场景二重评"
              "（跨合同实测）；C08＝同 4 项重发再收仍 4/10 不变 8/10、"
              "费用重导幂等不双计；C11＝关闭后 taskStatus=closed 与 "
              "proofGap.open 分别呈现（证明缺口不被勾掉）。"]
    (evidence_dir / "e17_evidence_attempt_recon.md").write_text(
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

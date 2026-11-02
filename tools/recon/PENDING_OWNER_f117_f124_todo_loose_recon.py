"""F117+F124 待办真状态与散件归案对账（W3-U08）——双 profile。

对账对象：harness 分支 w3-u08（基施工链头 w3-u07@c9fb3b29＝w2b-u53→
w3-u03(F24/F26)→w3-u06(F113)→w3-u07(F04/F92) 同链接力）的公开面——
desktop profile 与产品桥（legal_entry HARNESS_TASK_METHODS → --tasks-json
信封＋HARNESS_LOOSE_DOC_METHODS → --loosedocs-json 信封；本单方法组全桥
径，无直连 fallback）同一条链（SQLite 状态根）；selfhost profile＝
PgMatterStore 直连 lh-pg-e08（resolve_provider_method 同一封闭注册）。
全部合成材料：临时状态根、合成候选/取证轮/散件字节/任务；harness 检出
零字节改动（只运行其代码，git 只读命令核对分支）。

合同＝harness docs/f117-f124-todo-loose-contract.md：
  F117 待办建议/采用/执行/完成真状态；每任务终局 owner 与结果绑定——
  建议账（task_proposals）只记建议与决定，采用才落 derived_tasks 既有任
  务账（不造第二任务账）；建议 origin 闭集消费 E15/E17 账面（owner 闭集
  ＋真实回账）；complete 必带终局 owner＋结果绑定（在案 kind 回账验证）；
  done 终局。
  F124 不建案即可处理文档；归案后身份/版本/审阅链不丢——散件三账
  matter-less（零案号合法的结构面）；版本字节进同一 CAS；归案＝同一事
  务（F113 case_anchors 锚点＋F08 材料链 revision 1＋散件行冻结）；归案
  前版本/审阅链原样可回读，归案后版本演进唯一走 F08/F114 材料链。

实跑覆盖：
  C01 分支/基/master/工作树干净亲验 →
  C02 F117 建议账（E15/E17 origin 真实回账＋manual 显式 null；origin 不
      回账/owner 闭集外/kind 错配/同 id 冲突全具名拒）→
  C03 F117 采用/拒绝（adopt→derived_tasks accepted＋origin 可回读＋建议
      行 taskRef 互链；reject→案件数据零动；非 pending 拒；清单计数）→
  C04 F117 执行/完成真状态（start→running；重复 start 拒；complete 无
      绑定/finalOwner 闭集外/结果 ref 伪造全拒；complete 整载荷保留；
      done 终局）→
  C05 F117 既有四动作零动＋legacy 任务写路径（本单修复的死损行为证据）
      ＋同键幂等重放 →
  C06 F124 散件 matter-less 处理（零案件登记/版本链/审阅钉版本；决定来
      源自封拒/baseRevision 漂移拒）→
  C07 F124 归案单事务（anchor+material rev1+冻结；sha 同址身份不断；材
      料 source=F114 真值；归案后 loose_read 全链回读；锚点反查；归案后
      散件面写具名拒；F08 链继续演化）→
  C08 F124 事务回滚与幂等（material id 冲突整事务回滚：锚点 0/未冻结；
      已归案再归拒）→
  C09 双测一致（desktop/selfhost 同断言集）＋DB 级扫描（建议/散件/任务
      修订链行数）→
  C10 桥负向（未配置 NOT_CONNECTED／未知方法 method_not_connected／方法
      组冻结）。

用法：
  python -X utf8 tools/PENDING_OWNER_f117_f124_todo_loose_recon.py \
      --profile desktop --profile selfhost

退出码：0 = 全部 profile RECON_OK；2 = RECON_FAIL；3 = 环境缺失。
证据：evidence/F117/<profile>/ 与 evidence/F124/<profile>/（同一 recon 双
落，F117/F124 各持一份）＋docs/construction/evidence/ 镜像。
"""
from __future__ import annotations

import argparse
import base64
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
    r"\.local\worktrees\w3-u08")

MATTER = "m-f117f124-recon"
SCOPE = {"kind": "matter", "matterId": MATTER}
CAND = "cand-f117"
ATTEMPT = "ea-f117"
LOOSE = "loose-f117f124"

TASK_METHODS = frozenset({
    "tasks.suggest", "tasks.proposal_decide", "tasks.proposal_list",
    "tasks.list", "tasks.decide",
})
LOOSE_METHODS = frozenset({
    "harness.loose_register", "harness.loose_add_revision",
    "harness.loose_record_review", "harness.loose_read",
    "harness.loose_list", "harness.loose_file",
})

# lh-pg-e08 容器（E08 拓扑）：仅回环端口、合成专用凭据（密钥只在本机容
# 器；可用 LH_E08_PG_DSN 覆写）。
DEFAULT_PG_DSN = "postgresql://lh_app:e08-synth-only@127.0.0.1:55432/legal_harness"

LOOSE_V1 = "散件初稿：买卖合同纠纷，余额 123456.78 元（W3-U08 对账合成，不入案）"
LOOSE_V2 = ("散件二稿：买卖合同纠纷，余额 123456.78 元；"
            "补送达条款（W3-U08 对账合成）")

_KEY_SEQ = {"n": 0}


def key(request_id: str) -> dict:
    """CommandKey：requestId 自动追加流水号（同键同内容幂等重放——探针
    必须每次新 id 才测到真实求值）。"""
    _KEY_SEQ["n"] += 1
    return {"requestId": "%s-%d" % (request_id, _KEY_SEQ["n"]),
            "targetId": None, "expectedRevision": None, "inputRefs": []}


def same_key(request_id: str) -> dict:
    return {"requestId": request_id, "targetId": None,
            "expectedRevision": None, "inputRefs": []}


def href(kind: str, object_id: str) -> dict:
    return {"owner": "harness", "kind": kind, "id": object_id,
            "version": "1", "matterId": MATTER}


def rsn(oid: str) -> dict:
    return {"owner": "host", "kind": "decision-receipt", "id": oid,
            "version": "1"}


def b64(text: str) -> str:
    return base64.b64encode(text.encode("utf-8")).decode("ascii")


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
        base = self.git(self.harness_root, "merge-base", "HEAD", "w3-u07")
        master = self.git(self.harness_root, "rev-parse", "master")
        self.step("c01_harness_branch", branch == "w3-u08", branch=branch)
        self.step("c01_harness_base_on_w3_u07", base.startswith("c9fb3b29"),
                  base=base)
        self.step("c01_harness_master_untouched", master.startswith("929d0802"),
                  master=master)
        dirty = self.git(self.harness_root, "status", "--porcelain")
        self.step("c01_harness_worktree_clean", dirty == "", dirty=dirty[:200])

    # ------------------------------------------------------------------
    # C02–C09：call(method, args) 走被测链；query 直读同一库。
    # ------------------------------------------------------------------
    def common_flow(self, profile: str, call, query):
        # ---- 种子：E15 候选＋E17 取证轮（建议 origin 消费的真实账面行）。
        self.units.save_fact("lawyer-1", SCOPE, key("seed-fact"),
                             {"id": "fact-r", "revision": 1,
                              "text": "买卖合同成立且已交付（合成）",
                              "establishment": "candidate",
                              "sourceLocations": [
                                  {"materialRef": href("material", "mat-x"),
                                   "documentId": "doc-r", "pageIndex": 1,
                                   "blockId": "blk-r"}],
                              "partyIds": [], "issueIds": []})
        self.units.path_candidate_register(
            "assistant-1", SCOPE, key("seed-cand"),
            {"candidateId": CAND, "pathType": "claim",
             "title": "违约损害赔偿（对账合成）",
             "basisRefs": [href("fact", "fact-r")],
             "triggerLocator": {"materialRef": href("material", "mat-x"),
                                "documentId": "doc-r", "pageIndex": 1,
                                "blockId": "blk-r"},
             "elements": [
                 {"elementId": "el-1", "statement": "存在合同",
                  "status": "established",
                  "factRefs": [href("fact", "fact-r")],
                  "counterEvidenceRefs": []}],
             "lawVersionRefs": [],
             "relation": {"kind": "parallel", "targetCandidateIds": []},
             "lossOverlap": {"declared": False, "sameLossWith": [],
                             "note": None}})
        attempt = self.units.evidence_attempt_register(
            "assistant-1", SCOPE, key("seed-ea"),
            {"attemptId": ATTEMPT, "taskRef": href("task", "t-seed"),
             "title": "取证轮（对账合成）",
             "items": [{"itemId": "ev-r", "proposition": "主张银行流水",
                        "channel": "court",
                        "authorizationRef": href("authorization", "auth-r"),
                        "requestScope": {"project": "p-r", "period": "2026-Q4",
                                         "subject": "s-r",
                                         "materialType": "bank_flow"}}]})
        attempt_ref = attempt["attempt"]["ref"]

        # ---- C02 F117 建议账。
        suggested = call("tasks.suggest", {
            "actor_id": "lawyer-1", "scope": SCOPE, "key": key("sg-e15"),
            "proposal": {"proposalId": "prop-e15", "title": "起草催告函（E15 拟工作）",
                         "originKind": "path_candidate",
                         "originRef": href("path_candidate", CAND),
                         "dueDate": "2026-11-01",
                         "note": "对账合成建议"}})
        self.step("c02_suggest_e15_origin_pending",
                  suggested["state"] == "pending"
                  and suggested["originKind"] == "path_candidate",
                  state=suggested["state"])
        call("tasks.suggest", {
            "actor_id": "lawyer-1", "scope": SCOPE, "key": key("sg-e17"),
            "proposal": {"proposalId": "prop-e17", "title": "跟进催告取证轮",
                         "originKind": "evidence_attempt",
                         "originRef": attempt_ref}})
        call("tasks.suggest", {
            "actor_id": "lawyer-1", "scope": SCOPE, "key": key("sg-manual"),
            "proposal": {"proposalId": "prop-manual", "title": "口头交代事项",
                         "originKind": "manual", "originRef": None}})
        self.expect_error(
            "c02_suggest_origin_not_in_ledger_refused",
            lambda: call("tasks.suggest", {
                "actor_id": "lawyer-1", "scope": SCOPE, "key": key("sg-bad"),
                "proposal": {"proposalId": "prop-bad", "title": "x",
                             "originKind": "path_candidate",
                             "originRef": href("path_candidate", "nope")}}),
            "task_origin_ref_not_found:path_candidate:nope")
        bad_owner = href("path_candidate", CAND)
        bad_owner["owner"] = "somewhere-else"
        self.expect_error(
            "c02_suggest_owner_closed_set_refused",
            lambda: call("tasks.suggest", {
                "actor_id": "lawyer-1", "scope": SCOPE,
                "key": key("sg-owner"),
                "proposal": {"proposalId": "prop-owner", "title": "x",
                             "originKind": "path_candidate",
                             "originRef": bad_owner}}),
            "task_origin_ref_owner_invalid")
        mismatched = href("evidence_attempt", CAND)
        self.expect_error(
            "c02_suggest_kind_mismatch_refused",
            lambda: call("tasks.suggest", {
                "actor_id": "lawyer-1", "scope": SCOPE,
                "key": key("sg-kind"),
                "proposal": {"proposalId": "prop-kind", "title": "x",
                             "originKind": "path_candidate",
                             "originRef": mismatched}}),
            "task_origin_ref_kind_mismatch")
        self.expect_error(
            "c02_suggest_non_manual_without_ref_refused",
            lambda: call("tasks.suggest", {
                "actor_id": "lawyer-1", "scope": SCOPE, "key": key("sg-noref"),
                "proposal": {"proposalId": "prop-noref", "title": "x",
                             "originKind": "path_candidate"}}),
            "task_origin_ref_required")
        # 同键同内容幂等重放；同 id 新键 conflict。
        replayed = call("tasks.suggest", {
            "actor_id": "lawyer-1", "scope": SCOPE,
            "key": same_key("sg-e15-replay"),
            "proposal": {"proposalId": "prop-e15b", "title": "同键重放",
                         "originKind": "manual", "originRef": None}})
        self.expect_error(
            "c02_suggest_id_conflict_refused",
            lambda: call("tasks.suggest", {
                "actor_id": "lawyer-1", "scope": SCOPE, "key": key("sg-dup"),
                "proposal": {"proposalId": "prop-manual", "title": "换内容",
                             "originKind": "manual", "originRef": None}}),
            "task_proposal_id_conflict:prop-manual")
        del replayed

        # ---- C03 F117 采用/拒绝。
        adopted = call("tasks.proposal_decide", {
            "actor_id": "lawyer-1", "scope": SCOPE, "key": key("pd-e15"),
            "decision": {"proposalId": "prop-e15", "action": "adopt",
                         "reasonRef": rsn("r-adopt"),
                         "receiptRef": rsn("rc-adopt")}})
        self.step("c03_adopt_writes_existing_task_ledger",
                  adopted["taskRef"]["id"] == "task-prop-e15"
                  and adopted["taskRef"]["version"] == "1"
                  and adopted["taskRef"]["kind"] == "derived-task",
                  taskRef=adopted.get("taskRef"))
        listing = call("tasks.list", {"scope": SCOPE, "cursor": None})
        adopted_tasks = [item for item in listing["items"]
                         if item["id"] == "task-prop-e15"]
        self.step("c03_adopted_task_carries_origin",
                  len(adopted_tasks) == 1
                  and adopted_tasks[0]["state"] == "accepted"
                  and adopted_tasks[0]["origin"]["originKind"] == "path_candidate"
                  and adopted_tasks[0]["origin"]["originRef"]["id"] == CAND,
                  found=len(adopted_tasks))
        rejected = call("tasks.proposal_decide", {
            "actor_id": "lawyer-1", "scope": SCOPE, "key": key("pd-rej"),
            "decision": {"proposalId": "prop-e17", "action": "reject",
                         "reasonRef": rsn("r-rej"),
                         "receiptRef": rsn("rc-rej")}})
        self.step("c03_reject_leaves_case_data_untouched",
                  "taskRef" not in rejected
                  and not [item for item in listing["items"]
                           if item["id"] == "task-prop-e17"],
                  rejected=True)
        self.expect_error(
            "c03_decide_only_pending_refused",
            lambda: call("tasks.proposal_decide", {
                "actor_id": "lawyer-1", "scope": SCOPE, "key": key("pd-2nd"),
                "decision": {"proposalId": "prop-e15", "action": "reject",
                             "reasonRef": rsn("r-2nd"),
                             "receiptRef": rsn("rc-2nd")}}),
            "task_proposal_state_invalid:adopted")
        proposals = call("tasks.proposal_list", {"scope": SCOPE})
        self.step("c03_proposal_list_counts",
                  proposals["proposalCount"] == 4
                  and proposals["stateCounts"] ==
                  {"adopted": 1, "pending": 2, "rejected": 1},
                  stateCounts=proposals["stateCounts"])

        # ---- C04 F117 执行/完成真状态。
        started = call("tasks.decide", {
            "actor_id": "lawyer-1", "scope": SCOPE, "key": key("td-start"),
            "task_ref": {"id": "task-prop-e15"},
            "decision": {"action": "start", "reasonRef": rsn("r-start"),
                         "receiptRef": rsn("rc-start")}})
        self.step("c04_start_accepted_to_running", started["revision"] == 2,
                  revision=started["revision"])
        self.expect_error(
            "c04_double_start_refused",
            lambda: call("tasks.decide", {
                "actor_id": "lawyer-1", "scope": SCOPE,
                "key": key("td-start2"),
                "task_ref": {"id": "task-prop-e15"},
                "decision": {"action": "start", "reasonRef": rsn("r-s2"),
                             "receiptRef": rsn("rc-s2")}}),
            "task_state_invalid:running")
        self.expect_error(
            "c04_complete_without_binding_refused",
            lambda: call("tasks.decide", {
                "actor_id": "lawyer-1", "scope": SCOPE, "key": key("td-c0"),
                "task_ref": {"id": "task-prop-e15"},
                "decision": {"action": "complete", "reasonRef": rsn("r-c0"),
                             "receiptRef": rsn("rc-c0")}}),
            "fields_missing")
        self.expect_error(
            "c04_complete_final_owner_closed_set_refused",
            lambda: call("tasks.decide", {
                "actor_id": "lawyer-1", "scope": SCOPE, "key": key("td-c1"),
                "task_ref": {"id": "task-prop-e15"},
                "decision": {"action": "complete", "reasonRef": rsn("r-c1"),
                             "receiptRef": rsn("rc-c1"),
                             "finalOwner": "bigcorp", "resultRefs": []}}),
            "task_final_owner_invalid")
        self.expect_error(
            "c04_complete_result_ref_must_resolve_refused",
            lambda: call("tasks.decide", {
                "actor_id": "lawyer-1", "scope": SCOPE, "key": key("td-c2"),
                "task_ref": {"id": "task-prop-e15"},
                "decision": {"action": "complete", "reasonRef": rsn("r-c2"),
                             "receiptRef": rsn("rc-c2"),
                             "finalOwner": "harness",
                             "resultRefs": [href("material", "nope")]}}),
            "task_result_ref_not_found:material:nope")
        stuffed = href("path_candidate", CAND)
        stuffed["extra"] = "payload"
        self.expect_error(
            "c04_complete_result_ref_fields_closed_refused",
            lambda: call("tasks.decide", {
                "actor_id": "lawyer-1", "scope": SCOPE, "key": key("td-c3"),
                "task_ref": {"id": "task-prop-e15"},
                "decision": {"action": "complete", "reasonRef": rsn("r-c3"),
                             "receiptRef": rsn("rc-c3"),
                             "finalOwner": "harness",
                             "resultRefs": [stuffed]}}),
            "task_result_ref_fields_not_closed")
        completed = call("tasks.decide", {
            "actor_id": "lawyer-1", "scope": SCOPE, "key": key("td-done"),
            "task_ref": {"id": "task-prop-e15"},
            "decision": {"action": "complete", "reasonRef": rsn("r-done"),
                         "receiptRef": rsn("rc-done"),
                         "finalOwner": "harness",
                         "resultRefs": [href("path_candidate", CAND)]}})
        self.step("c04_complete_binds_owner_and_results",
                  completed["revision"] == 3, revision=completed["revision"])
        listing = call("tasks.list", {"scope": SCOPE, "cursor": None})
        done = [item for item in listing["items"]
                if item["id"] == "task-prop-e15"][-1]
        self.step("c04_done_task_projection",
                  done["state"] == "done" and done["finalOwner"] == "harness"
                  and done["resultRefs"][0]["kind"] == "path_candidate"
                  and done["title"] == "起草催告函（E15 拟工作）"
                  and done["dueDate"] == "2026-11-01"
                  and done["origin"]["originKind"] == "path_candidate"
                  and bool(done["completedAt"]),
                  state=done["state"])
        self.expect_error(
            "c04_done_is_terminal",
            lambda: call("tasks.decide", {
                "actor_id": "lawyer-1", "scope": SCOPE, "key": key("td-post"),
                "task_ref": {"id": "task-prop-e15"},
                "decision": {"action": "accept", "reasonRef": rsn("r-post"),
                             "receiptRef": rsn("rc-post")}}),
            "task_state_terminal")
        # 外域 owner 结果只做形态校验（真值在各域公开面）。
        call("tasks.proposal_decide", {
            "actor_id": "lawyer-1", "scope": SCOPE, "key": key("pd-manual"),
            "decision": {"proposalId": "prop-manual", "action": "adopt",
                         "reasonRef": rsn("r-ma"),
                         "receiptRef": rsn("rc-ma")}})
        call("tasks.decide", {
            "actor_id": "lawyer-1", "scope": SCOPE, "key": key("td-foreign"),
            "task_ref": {"id": "task-prop-manual"},
            "decision": {"action": "complete", "reasonRef": rsn("r-fgn"),
                         "receiptRef": rsn("rc-fgn"), "finalOwner": "jc",
                         "resultRefs": [{"owner": "jc", "kind": "run",
                                         "id": "run-foreign", "version": "1"}]}})
        listing = call("tasks.list", {"scope": SCOPE, "cursor": None})
        foreign = [item for item in listing["items"]
                   if item["id"] == "task-prop-manual"][-1]
        self.step("c04_foreign_owner_result_shape_checked",
                  foreign["state"] == "done"
                  and foreign["finalOwner"] == "jc"
                  and foreign["resultRefs"][0]["owner"] == "jc",
                  finalOwner=foreign["finalOwner"])

        # ---- C05 既有四动作零动＋legacy 写路径（死损修复行为证据）。
        # 专用任务（prop-manual 已在 C04 完成为终局——终局不可再决定）。
        call("tasks.suggest", {
            "actor_id": "lawyer-1", "scope": SCOPE, "key": key("sg-actions"),
            "proposal": {"proposalId": "prop-actions", "title": "四动作链任务",
                         "originKind": "manual", "originRef": None}})
        call("tasks.proposal_decide", {
            "actor_id": "lawyer-1", "scope": SCOPE, "key": key("pd-actions"),
            "decision": {"proposalId": "prop-actions", "action": "adopt",
                         "reasonRef": rsn("r-ac"),
                         "receiptRef": rsn("rc-ac")}})
        task_id = "task-prop-actions"
        for index, (action, want) in enumerate((
                ("needs_review", "proposed"), ("accept", "accepted"),
                ("withdraw", "cancelled"), ("accept", "accepted")), 1):
            call("tasks.decide", {
                "actor_id": "lawyer-1", "scope": SCOPE,
                "key": key("td-e-%d" % index), "task_ref": {"id": task_id},
                "decision": {"action": action, "reasonRef": rsn("r-e"),
                             "receiptRef": rsn("rc-e")}})
            items = [item for item in
                     call("tasks.list", {"scope": SCOPE, "cursor": None})
                     ["items"] if item["id"] == task_id]
            latest = max(items, key=lambda item: item["revision"])
            self.step("c05_legacy_action_%d_%s" % (index, action),
                      latest["state"] == want, state=latest["state"])
        # legacy schedule 任务经 tasks.decide 写路径（本单修复的参数数/列序
        # 死损——修复前该写路径必炸）。
        self.units.schedule_event(
            "lawyer-1", SCOPE, key("seed-sched"),
            {"id": "sched-legacy", "classification": "practical_reminder",
             "title": "开庭准备（对账合成）", "dueDate": "2026-11-09",
             "note": None}, [])
        legacy = [item for item in
                  call("tasks.list", {"scope": SCOPE, "cursor": None})["items"]
                  if item.get("source") == "schedule_event"][-1]
        decided = call("tasks.decide", {
            "actor_id": "lawyer-1", "scope": SCOPE, "key": key("td-legacy"),
            "task_ref": {"id": legacy["id"]},
            "decision": {"action": "accept", "reasonRef": rsn("r-lg"),
                         "receiptRef": rsn("rc-lg")}})
        self.step("c05_legacy_task_write_path_ok",
                  decided["revision"] == 2, revision=decided["revision"])

        # ---- C06 F124 散件 matter-less 处理（无案件参数）。
        registered = call("harness.loose_register", {
            "key": key("lr-1"),
            "doc": {"looseId": LOOSE, "title": "散件合同（对账合成）",
                    "bytesB64": b64(LOOSE_V1), "source": "upload",
                    "note": "对账合成散件"}})
        self.step("c06_loose_register_without_case",
                  registered["state"] == "open" and registered["revision"] == 1
                  and registered["ref"]["kind"] == "loose_document",
                  sha256=registered["sha256"][:12])
        revised = call("harness.loose_add_revision", {
            "key": key("lv-1"),
            "revision": {"looseId": LOOSE, "bytesB64": b64(LOOSE_V2),
                         "source": "assistant_edit", "baseRevision": 1,
                         "note": "补送达条款"}})
        self.step("c06_loose_version_chain",
                  revised["revision"] == 2
                  and revised["source"] == "assistant_edit",
                  revision=revised["revision"])
        review = call("harness.loose_record_review", {
            "key": key("lrv-1"),
            "review": {"looseId": LOOSE, "reviewId": "lrev-r", "revision": 2,
                       "reviewKind": "citation_check",
                       "review": {"citations": 2, "verified": 2},
                       "note": "引用核验（合成）"}})
        self.step("c06_loose_review_pinned",
                  review["pinnedRevision"] == 2, pinned=review["pinnedRevision"])
        self.expect_error(
            "c06_loose_decision_source_forgery_refused",
            lambda: call("harness.loose_add_revision", {
                "key": key("lv-2"),
                "revision": {"looseId": LOOSE, "bytesB64": b64("v3"),
                             "source": "user_accept"}}),
            "loose_source_not_writable:user_accept")
        self.expect_error(
            "c06_loose_base_revision_stale_refused",
            lambda: call("harness.loose_add_revision", {
                "key": key("lv-3"),
                "revision": {"looseId": LOOSE, "bytesB64": b64("v3"),
                             "baseRevision": 1}}),
            "loose_base_revision_stale:1:2")
        self.expect_error(
            "c06_loose_review_unknown_revision_refused",
            lambda: call("harness.loose_record_review", {
                "key": key("lrv-2"),
                "review": {"looseId": LOOSE, "reviewId": "lrev-2",
                           "revision": 9, "reviewKind": "note",
                           "review": {}}}),
            "loose_revision_not_found:9")

        # ---- C07 F124 归案单事务。
        filed = call("harness.loose_file", {
            "actor_id": "lawyer-1", "scope": SCOPE, "key": key("lf-1"),
            "filing": {"looseId": LOOSE, "materialId": "mat-filed",
                       "materialKind": "digital_text"}})
        view = call("harness.loose_read", {"loose_id": LOOSE})
        self.step("c07_file_identity_same_cas_address",
                  filed["materialSha256"] == view["revisions"][-1]["sha256"]
                  and filed["materialRef"]["id"] == "mat-filed",
                  sha256=filed["materialSha256"][:12])
        material = call("harness.read_material",
                        {"scope": SCOPE, "material_id": "mat-filed"})
        self.step("c07_filed_material_rev1_f114_truth",
                  material["revision"] == 1
                  and material["sha256"] == filed["materialSha256"]
                  and material["source"] == "assistant_edit"
                  and material["admission"] == "candidate",
                  source=material["source"])
        self.step("c07_loose_frozen_with_filing_links",
                  view["state"] == "filed"
                  and view["filing"]["materialRef"]["id"] == "mat-filed"
                  and view["filing"]["anchorRef"]["kind"] == "case_anchor"
                  and view["filing"]["looseHeadRevision"] == 2,
                  state=view["state"])
        self.step("c07_pre_filing_chains_intact_after_filing",
                  [item["revision"] for item in view["revisions"]] == [1, 2]
                  and [item["reviewId"] for item in view["reviews"]]
                  == ["lrev-r"],
                  revisions=len(view["revisions"]),
                  reviews=len(view["reviews"]))
        anchors = self.units.case_anchor_item_read(
            view["revisions"][-1]["sha256"])
        self.step("c07_anchor_reverse_read",
                  anchors["anchorCount"] == 1
                  and anchors["anchors"][0]["matterId"] == MATTER,
                  anchors=anchors["anchorCount"])
        self.expect_error(
            "c07_post_filing_loose_version_refused",
            lambda: call("harness.loose_add_revision", {
                "key": key("lv-after"),
                "revision": {"looseId": LOOSE, "bytesB64": b64("v3")}}),
            "loose_already_filed")
        self.expect_error(
            "c07_post_filing_loose_review_refused",
            lambda: call("harness.loose_record_review", {
                "key": key("lrv-after"),
                "review": {"looseId": LOOSE, "reviewId": "lrev-x",
                           "revision": 2, "reviewKind": "note",
                           "review": {}}}),
            "loose_already_filed")
        advanced = call("harness.add_material_revision", {
            "actor_id": "lawyer-1", "scope": SCOPE, "key": key("mr-1"),
            "revision": {"materialId": "mat-filed",
                         "bytesB64": b64("归案后三稿（对账合成）"),
                         "source": "upload", "baseRevision": 1}})
        self.step("c07_post_filing_evolution_via_f08_chain",
                  advanced["revision"] == 2, revision=advanced["revision"])
        listing = call("harness.loose_list", {"state": None})
        self.step("c07_loose_list_projection",
                  any(item["looseId"] == LOOSE and item["state"] == "filed"
                      for item in listing["documents"]),
                  count=listing["documentCount"])

        # ---- C08 事务回滚与幂等。
        self.units.loose_register(
            key("lr-2"), {"looseId": LOOSE + "-b", "title": "第二散件（合成）",
                          "bytesB64": b64("第二散件字节（合成）"),
                          "source": "upload"})
        self.units.register_material(
            "lawyer-1", SCOPE, key("seed-mat"),
            {"id": "mat-taken", "kind": "digital_text", "title": "既有材料",
             "bytesB64": b64("既有字节（合成）")})
        self.expect_error(
            "c08_material_id_conflict_refused",
            lambda: call("harness.loose_file", {
                "actor_id": "lawyer-1", "scope": SCOPE, "key": key("lf-2"),
                "filing": {"looseId": LOOSE + "-b",
                           "materialId": "mat-taken",
                           "materialKind": "digital_text"}}),
            "material_id_conflict:mat-taken")
        rolled = call("harness.loose_read", {"loose_id": LOOSE + "-b"})
        self.step("c08_conflict_rolls_back_whole_transaction",
                  rolled["state"] == "open" and rolled["filing"] is None
                  and self.units.case_anchor_item_read(
                      rolled["revisions"][-1]["sha256"])["anchorCount"] == 0,
                  state=rolled["state"])
        self.expect_error(
            "c08_refile_filed_loose_refused",
            lambda: call("harness.loose_file", {
                "actor_id": "lawyer-1", "scope": SCOPE, "key": key("lf-3"),
                "filing": {"looseId": LOOSE, "materialId": "mat-2",
                           "materialKind": "digital_text"}}),
            "loose_already_filed")

        # ---- C09 DB 级扫描。
        counts = {}
        for table in ("task_proposals", "derived_tasks", "loose_documents",
                      "loose_document_revisions", "loose_document_reviews",
                      "case_anchors", "material_candidates"):
            counts[table] = len(query(
                "SELECT * FROM %s" % table, ()))
        self.step("c09_db_scan_counts",
                  counts["task_proposals"] == 5
                  and counts["derived_tasks"] >= 5
                  and counts["loose_documents"] == 2
                  and counts["loose_document_revisions"] == 3
                  and counts["loose_document_reviews"] == 1
                  and counts["case_anchors"] == 1
                  and counts["material_candidates"] >= 3,
                  counts=counts)

    def bridge_negatives(self, config):
        # ---- C10 桥负向：未配置/未知方法/方法组冻结。
        try:
            legal_entry.call("tasks.suggest", {"scope": SCOPE}, {})
            raise AssertionError("bridge_not_configured_expected")
        except NotConnected as exc:
            self.step("c10_bridge_not_configured",
                      "harness_public_entry_not_configured" in str(exc))
        try:
            legal_entry.call("tasks.create", {"scope": SCOPE}, config)
            raise AssertionError("bridge_unknown_method_expected")
        except NotConnected as exc:
            self.step("c10_bridge_unknown_method_refused",
                      "method_not_connected" in str(exc))
        try:
            legal_entry.call("harness.loose_import", {}, config)
            raise AssertionError("bridge_unknown_loose_method_expected")
        except NotConnected as exc:
            self.step("c10_bridge_unknown_loose_method_refused",
                      "method_not_connected" in str(exc))
        self.step("c10_method_group_frozen_tasks",
                  legal_entry.HARNESS_TASK_METHODS == TASK_METHODS)
        self.step("c10_method_group_frozen_loose",
                  legal_entry.HARNESS_LOOSE_DOC_METHODS == LOOSE_METHODS)

    # -- profile drivers ---------------------------------------------------

    def run_desktop(self) -> int:
        temporary = tempfile.TemporaryDirectory(
            prefix="juscite-f117f124-desktop-")
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
        store.create_matter(MATTER, "cas://profile-f117f124-recon")

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
            prefix="juscite-f117f124-selfhost-")
        store = PgMatterStore(
            Path(temporary.name) / "state", dsn=dsn,
            schema="f117f124_" + _uuid.uuid4().hex[:12])
        self.units = HarnessUnits(store)
        methods = set(TASK_METHODS) | set(LOOSE_METHODS) | {
            "harness.save_fact", "harness.path_candidate_register",
            "harness.evidence_attempt_register", "harness.schedule_event",
            "harness.register_material", "harness.read_material",
            "harness.add_material_revision", "harness.case_anchor_item_read",
        }
        bound = {name: resolve_provider_method(name, self.units)
                 for name in methods}
        store.create_matter(MATTER, "cas://profile-f117f124-recon")

        def call(method, args):
            return bound[method](**args)

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


def write_evidence(profile: str, recon: Recon, harness_root: Path,
                   started: str, code: int) -> list[Path]:
    finished = datetime.now(timezone.utc).isoformat()
    summary = {
        "schema": "juscite-f117f124-todo-loose-recon/1",
        "unit": "W3-U08",
        "features": ["F117", "F124"],
        "profile": profile,
        "verdict": "RECON_OK" if code == 0 else "RECON_FAIL",
        "started_at": started,
        "finished_at": finished,
        "harness_worktree": str(harness_root),
        "harness_branch": "w3-u08",
        "harness_base": "w3-u07@c9fb3b29 (w2b-u53→w3-u03/F24F26→"
                        "w3-u06/F113→w3-u07/F04F92 同链接力)",
        "contract": "harness docs/f117-f124-todo-loose-contract.md",
        "checks": recon.checks,
        "check_count": len(recon.checks),
        "failed": [c["check"] for c in recon.checks
                   if c["status"] != "PASS"],
    }
    payload = json.dumps(summary, ensure_ascii=False, indent=1)
    written: list[Path] = []
    for feature in ("F117", "F124"):
        for base in (REPO_ROOT / "evidence" / feature / profile,
                     REPO_ROOT / "docs" / "construction" / "evidence"
                     / feature / profile):
            base.mkdir(parents=True, exist_ok=True)
            path = base / "f117_f124_todo_loose_recon.json"
            path.write_text(payload + "\n", encoding="utf-8")
            lines = [
                "# F117/F124 待办真状态与散件归案对账（%s·%s）"
                % (feature, profile),
                "",
                f"- unit: W3-U08 · profile: {profile} · feature: {feature}",
                f"- verdict: **{summary['verdict']}**"
                f" ({len(recon.checks)} checks, exit {code})",
                f"- harness: `{harness_root}` @ branch w3-u08"
                "（基 w3-u07@c9fb3b29；master 929d0802 零动）",
                f"- started: {started} · finished: {finished}",
                "",
                "| # | check | status |",
                "|---|---|---|",
            ]
            for index, check in enumerate(recon.checks, 1):
                lines.append(f"| {index} | {check['check']}"
                             f" | {check['status']} |")
            (base / "f117_f124_todo_loose_recon.md").write_text(
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

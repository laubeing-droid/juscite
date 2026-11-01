# -*- coding: utf-8 -*-
"""F82 复核/单格重跑/人工改格三面产品桥（工单 W2b-U31）。

本模块是**编排与薄透传**，不是第二账本、不是第二写通道：

  - 复核（F82-复核）：tabular.review_receipt → harness.review_receipt_
    record（回执带 reviewer＋决定 ref；机器分子不动——E11 先例）＋
    tabular.review_status → harness.review_receipt_read（复核状态投影）；
  - 单格重跑（F82-重跑）：tabular.cell_rerun 编排 claim→rerun→release
    三步（以行为租约、格为粒度新 generation；迟到/旧 generation/人改后
    重跑三路具名拒不覆人改；done 行不可 claim＝完成行走新一轮）；
  - 人工改格（F82-人改）：复用既有 harness.review_batch_human_edit
    （legal_entry F25 冻结方法组；本面不建第二写通道——F84 红线：改格
    必经写权限方法）；
  - 失效回读（值侧）：tabular.cell_history → harness.review_cell_history
    （沿版本链旧值历史）；支持侧 STALE/INVALIDATED 投影复用 U05 面。

金额纪律：本面不解释值语义（透传 JSON 值；Decimal 对照在 tabular.read
投影）。未配置/未知方法 fail-closed exit 3 具名（legal_entry 纪律）。
"""

from __future__ import annotations

from bridge_errors import NotConnected

REVIEW_OPS_FACE_NOTE = (
    "tabular-review-ops(W2b-U31): harness.review_receipt_*(W2b-U31)"
    "+harness.review_cell_rerun/history(W2b-U31)"
    "+harness.review_batch_*(W2b-U01)")

# 复核决定闭集（与 harness review_receipt_record 同集；产品侧只做透传
# 前校验，权威在 harness）。
REVIEW_DECISIONS = frozenset({"confirmed", "rejected"})

_RECEIPT_ARGS_FIELDS = frozenset({
    "review_batch_id", "row_id", "cell_id", "receipt", "actor_id",
    "scope", "key",
})
_RECEIPT_BODY_FIELDS = frozenset({
    "reviewer", "decision", "decisionRef", "note",
})
_STATUS_ARGS_FIELDS = frozenset({
    "review_batch_id", "row_id", "cell_id", "scope",
})
_RERUN_ARGS_FIELDS = frozenset({
    "review_batch_id", "row_id", "cell_id", "value", "actor_id",
    "scope", "key",
})
_HISTORY_ARGS_FIELDS = frozenset({
    "review_batch_id", "row_id", "cell_id", "scope",
})


def _harness_call(method: str, args: dict, config: dict) -> dict:
    """harness 公开面分派 seam（默认=legal_entry.call 子进程径；selfhost
    侧 PG 直连部署由调用方替换本 seam——同 U05 先例）。"""
    import legal_entry
    return legal_entry.call(method, args, config)


def _require(args: dict, fields: frozenset, code: str,
             optional: frozenset = frozenset({})) -> None:
    """DTO 闭集校验：必带字段缺一即拒、闭集外字段即拒（无旁路）。"""
    if not isinstance(args, dict) or set(args) - set(fields) \
            or (set(fields) - set(optional)) - set(args):
        raise NotConnected(code)


def _scope_of(args: dict) -> dict:
    scope = args.get("scope")
    if not isinstance(scope, dict) or scope.get("kind") != "matter" \
            or not isinstance(scope.get("matterId"), str) \
            or not scope.get("matterId"):
        raise NotConnected("tabular_scope_invalid")
    return scope


def _command_key(args: dict) -> dict:
    key = args.get("key")
    if not isinstance(key, dict) or not isinstance(key.get("requestId"), str) \
            or not key.get("requestId"):
        raise NotConnected("tabular_command_key_invalid")
    return key


def _cell_target(args: dict) -> tuple:
    for field in ("review_batch_id", "row_id", "cell_id"):
        if not isinstance(args.get(field), str) or not args.get(field):
            raise NotConnected("tabular_%s_required" % field)
    return args["review_batch_id"], args["row_id"], args["cell_id"]


# ---------------------------------------------------------------------- #
# tabular.review_receipt —— 复核回执登记（薄透传；权威在 harness）
# ---------------------------------------------------------------------- #


def review_receipt(args: dict, config: dict) -> dict:
    _require(args, _RECEIPT_ARGS_FIELDS, "tabular_receipt_args_invalid")
    scope = _scope_of(args)
    _command_key(args)
    batch_id, row_id, cell_id = _cell_target(args)
    receipt = args.get("receipt")
    if not isinstance(receipt, dict) \
            or set(receipt) - set(_RECEIPT_BODY_FIELDS) \
            or {"reviewer", "decision", "decisionRef"} - set(receipt):
        raise NotConnected("tabular_receipt_body_invalid")
    if receipt.get("decision") not in REVIEW_DECISIONS:
        raise NotConnected("tabular_receipt_decision_invalid:"
                           + str(receipt.get("decision")))
    payload = {"actor_id": args.get("actor_id"), "scope": scope,
               "key": args["key"], "batch_id": batch_id,
               "row_id": row_id, "cell_id": cell_id, "receipt": receipt}
    result = _harness_call("harness.review_receipt_record", payload,
                           config)
    result["face"] = REVIEW_OPS_FACE_NOTE
    return result


# ---------------------------------------------------------------------- #
# tabular.review_status —— 复核状态投影（只读）
# ---------------------------------------------------------------------- #


def review_status(args: dict, config: dict) -> dict:
    _require(args, _STATUS_ARGS_FIELDS, "tabular_status_args_invalid",
             optional=frozenset({"row_id", "cell_id"}))
    scope = _scope_of(args)
    batch_id = args.get("review_batch_id")
    if not isinstance(batch_id, str) or not batch_id:
        raise NotConnected("tabular_batch_id_required")
    payload = {"scope": scope, "batch_id": batch_id}
    for field in ("row_id", "cell_id"):
        if args.get(field) is not None:
            if not isinstance(args[field], str) or not args[field]:
                raise NotConnected("tabular_%s_invalid" % field)
            payload[field] = args[field]
    result = _harness_call("harness.review_receipt_read", payload, config)
    result["face"] = REVIEW_OPS_FACE_NOTE
    return result


# ---------------------------------------------------------------------- #
# tabular.cell_rerun —— 单格重跑（claim→rerun→release 编排）
# ---------------------------------------------------------------------- #


def cell_rerun(args: dict, config: dict) -> dict:
    """单格重跑编排：claim 行租约（新租约新快照）→ 以快照世代重跑单格
    → release（行回 pending，格面新值保全）。

    - 行被他人持有效租约＝claim 具名拒 batch_claim_contended（租约抢占
      如实上浮）；done 行不可 claim（完成行走新一轮——批 id 一次性）；
    - 重跑三路具名拒由 harness 面承担（本编排用刚发放的租约＋快照世代，
      租约路在本径不可迟到；人改格即使世代正确也 review_rerun_human_cell
      拒）；重跑被拒时若已持租约则 release(reason=cell_rerun_aborted)
      归还行（部分失败恢复），归还会失败如实上浮不吞。
    """
    _require(args, _RERUN_ARGS_FIELDS, "tabular_rerun_args_invalid")
    scope = _scope_of(args)
    _command_key(args)
    actor_id = args.get("actor_id")
    if not isinstance(actor_id, str) or not actor_id:
        raise NotConnected("tabular_actor_invalid")
    batch_id, row_id, cell_id = _cell_target(args)
    base = {"actor_id": actor_id, "scope": scope}
    claimed = _harness_call("harness.review_batch_claim", {
        **base, "key": {"requestId": args["key"]["requestId"] + ":claim",
                        "targetId": None, "expectedRevision": None,
                        "inputRefs": []},
        "batch_id": batch_id, "row_id": row_id,
        "lease_ttl_seconds": 600}, config)
    snapshot_cells = (claimed.get("snapshot") or {}).get("cells") or {}
    cell_snapshot = snapshot_cells.get(cell_id)
    if cell_snapshot is None:
        raise NotConnected("tabular_rerun_cell_not_in_snapshot:" + cell_id)
    rerun_args = {
        **base, "key": {"requestId": args["key"]["requestId"] + ":rerun",
                        "targetId": None, "expectedRevision": None,
                        "inputRefs": []},
        "batch_id": batch_id, "row_id": row_id, "cell_id": cell_id,
        "lease_token": claimed["lease"]["token"],
        "value": args.get("value"),
        "generation": cell_snapshot.get("generation", 0)}
    try:
        rerun = _harness_call("harness.review_cell_rerun", rerun_args,
                              config)
    except BaseException:
        # 部分失败恢复（best-effort）：归还刚拿的租约（行回 pending）；
        # 归还失败不掩盖原始具名拒——typed 码原样上浮（exit 面随来源：
        # 子进程径=HarnessCommandError，同进程径=UnitsError）。
        try:
            _harness_call("harness.review_batch_release", {
                **base,
                "key": {"requestId": args["key"]["requestId"] + ":release",
                        "targetId": None, "expectedRevision": None,
                        "inputRefs": []},
                "batch_id": batch_id, "row_id": row_id,
                "lease_token": claimed["lease"]["token"],
                "release": {"reason": "cell_rerun_aborted"}}, config)
        except Exception:
            pass
        raise
    released = _harness_call("harness.review_batch_release", {
        **base,
        "key": {"requestId": args["key"]["requestId"] + ":release",
                "targetId": None, "expectedRevision": None,
                "inputRefs": []},
        "batch_id": batch_id, "row_id": row_id,
        "lease_token": claimed["lease"]["token"],
        "release": {"reason": "cell_rerun_done"}}, config)
    history = _harness_call("harness.review_cell_history", {
        "scope": scope, "batch_id": batch_id, "row_id": row_id,
        "cell_id": cell_id}, config)
    return {
        "reviewBatchId": batch_id, "rowId": row_id, "cellId": cell_id,
        "rowState": released.get("state"),
        "cell": (rerun.get("cells") or {}).get(cell_id),
        "previousGeneration": rerun.get("previousGeneration"),
        "leaseTrace": {"claimSeq": claimed["lease"]["claimSeq"],
                       "claimedAt": claimed["lease"]["claimedAt"],
                       "releasedState": released.get("state")},
        "history": history,
        "face": REVIEW_OPS_FACE_NOTE,
    }


# ---------------------------------------------------------------------- #
# tabular.cell_history —— 旧值历史回读（只读）
# ---------------------------------------------------------------------- #


def cell_history(args: dict, config: dict) -> dict:
    _require(args, _HISTORY_ARGS_FIELDS, "tabular_history_args_invalid")
    scope = _scope_of(args)
    batch_id, row_id, cell_id = _cell_target(args)
    result = _harness_call("harness.review_cell_history", {
        "scope": scope, "batch_id": batch_id, "row_id": row_id,
        "cell_id": cell_id}, config)
    result["face"] = REVIEW_OPS_FACE_NOTE
    return result


# ---------------------------------------------------------------------- #
# legal_entry 冻结方法组分发（tabular.* review-ops 组）
# ---------------------------------------------------------------------- #


def review_ops_call(method: str, args: dict, config: dict) -> dict:
    """legal_entry 冻结方法组分发。未列方法绝不落到这里。"""
    if method == "tabular.review_receipt":
        return review_receipt(args, config)
    if method == "tabular.review_status":
        return review_status(args, config)
    if method == "tabular.cell_rerun":
        return cell_rerun(args, config)
    return cell_history(args, config)  # tabular.cell_history

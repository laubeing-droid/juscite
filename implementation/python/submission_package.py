# -*- coding: utf-8 -*-
"""F59 立案材料准备/提交包（W3-U12；06:F59 双实例；17 卡人工确认制）。

法院要求材料核对清单＋可读提交包生成、律师确认才正式提交、缺件具名提示
——绝不实际对外提交。

落点与分工（harness 账面见 legal-harness 仓 w3-u12 分支合同
docs/f59-f60-submission-calendar-contract.md）：
- harness 两账：submission_checklists（清单声明账，items 闭集冻结）＋
  submission_packages（可读提交包时点对账账：可读字节进同一 CAS、逐 item
  材料映射回 F08 材料链头版、缺件具名入账、律师确认＝包行内决定面
  draft→confirmed）。
- 本面（产品侧）：①可读提交包的确定性渲染（同输入同字节——无时钟、无
  随机、模板固定，材料 sha 在 harness 快照不在渲染文本）；②律师确认的
  显式标志闸（confirm 字段非 True＝f59_confirmation_flag_required 具名
  拒——人工确认制不是隐式调用）；③harness 六方法的转发投影。

**绝不实际对外提交（结构性，不是开关）**：本模块导入闭集零网络（无
socket/urllib/http/requests/subprocess——wiring 测试 AST 钉死）；对外
提交动作在本面与 harness 面都结构性不存在（harness.provider 封闭注册外
method_not_whitelisted）；投影恒带 submissionChannel='none'。

config：复用 harness 桥同域键（harness_public_entry/harness_target/
harness_state_root/harness_service_registration/harness_timeout）。
错误码不携材料内容（document-adapter 同基线）。
"""
from __future__ import annotations

import json

SUBMISSION_METHODS = frozenset({
    "submission.checklist_define",
    "submission.checklist_read",
    "submission.package_build",
    "submission.package_confirm",
    "submission.package_read",
    "submission.package_list",
})

_RENDER_LINE = "=" * 46


class SubmissionPackageError(RuntimeError):
    """具名错误（f59_* 码），绝不携材料内容。"""


def _harness(method: str, args: dict, config: dict, harness_call) -> dict:
    result = harness_call(method, args)
    if not isinstance(result, dict):
        raise SubmissionPackageError(
            "f59_harness_receipt_invalid:" + method)
    return result


def _require(args: dict, field: str) -> object:
    value = args.get(field)
    if value is None:
        raise SubmissionPackageError("f59_field_missing:" + field)
    return value


def render_package(checklist: dict, provisions: list, matter_id: str,
                   matter_title: str, court_note: str) -> str:
    """可读提交包渲染（确定性：同输入同字节）。

    只用输入字段与清单声明——无时钟、无随机、无环境读取；材料映射的
    版本/摘要真值在 harness 快照（本渲染不复制第二份逐字节证据）。缺件
    项逐条具名呈现（required 且无映射）。"""
    items = checklist.get("items") or []
    provided = {}
    for entry in provisions or []:
        provided[str(entry.get("itemId"))] = list(entry.get("materialRefs")
                                                  or [])
    lines = [
        "法院要求材料核对与提交包（可读版）",
        _RENDER_LINE,
        f"案件：{matter_title or matter_id}",
        f"核对清单：{checklist.get('title', '')}",
        f"清单编号：{checklist.get('checklistId', '')}",
        "",
        "逐项核对：",
    ]
    missing = []
    for item in items:
        item_id = str(item.get("itemId"))
        refs = provided.get(item_id, [])
        required = bool(item.get("required"))
        if refs:
            state = "已附"
            detail = "；".join(str(ref) for ref in refs)
        elif required:
            state = "缺件"
            detail = "（必需项未附，须补齐后方可提交）"
            missing.append(item_id)
        else:
            state = "未附（可选）"
            detail = "（可选项，缺席不阻确认）"
        marker = "[必需]" if required else "[可选]"
        lines.append(f"  {marker} {item.get('title', '')}"
                     f"（{item_id}）：{state} {detail}")
    lines += ["", "缺件清单："]
    if missing:
        lines += [f"  - {item_id}" for item_id in missing]
        lines.append("  上述必需项缺件；确认（正式提交标记）将具名拒绝。")
    else:
        lines.append("  （无——必需项全部已附）")
    lines += [
        "",
        "提交说明：",
        "  本包为内部核对与确认记录；本系统不执行任何对外提交动作，",
        "  对外递交由律师在法院要求的方式下自行完成。",
        f"  （courtNote: {court_note or '-'}）",
        "",
    ]
    return "\n".join(lines)


def submission_call(method: str, args: dict, config: dict,
                    harness_call=None) -> dict:
    """F59 产品面唯一入口（legal_entry 冻结方法组分派）。

    harness_call 注入点：缺省＝legal_entry.call（desktop 桥子进程全链）；
    selfhost recon 注入 resolve_provider_method 直连同封闭注册。"""
    if harness_call is None:
        from legal_entry import call as _entry_call

        def harness_call(h_method, h_args):
            return _entry_call(h_method, h_args, config)

    if method == "submission.checklist_define":
        return _harness("harness.submission_checklist_define", {
            "actor_id": _require(args, "actor_id"),
            "scope": _require(args, "scope"),
            "key": _require(args, "key"),
            "checklist": _require(args, "checklist"),
        }, config, harness_call)
    if method == "submission.checklist_read":
        return _harness("harness.submission_checklist_read", {
            "scope": _require(args, "scope"),
            "checklist_id": _require(args, "checklist_id"),
        }, config, harness_call)
    if method == "submission.package_build":
        return _package_build(args, config, harness_call)
    if method == "submission.package_confirm":
        return _package_confirm(args, config, harness_call)
    if method == "submission.package_read":
        return _harness("harness.submission_package_read", {
            "scope": _require(args, "scope"),
            "package_id": _require(args, "package_id"),
        }, config, harness_call)
    if method == "submission.package_list":
        return _harness("harness.submission_package_list", {
            "scope": _require(args, "scope"),
        }, config, harness_call)
    raise SubmissionPackageError("f59_method_not_connected:" + method)


def _package_build(args: dict, config: dict, harness_call) -> dict:
    scope = _require(args, "scope")
    checklist_id = _require(args, "checklist_id")
    provisions = _require(args, "items")
    if not isinstance(provisions, list):
        raise SubmissionPackageError("f59_items_invalid")
    matter_id = scope.get("matterId") if isinstance(scope, dict) else None
    checklist = _harness("harness.submission_checklist_read", {
        "scope": scope, "checklist_id": checklist_id,
    }, config, harness_call)["checklist"]
    rendered = render_package(
        checklist, provisions, str(matter_id or ""),
        str(args.get("matter_title") or ""),
        str(args.get("court_note") or ""))
    import base64 as _b64
    generated = _harness("harness.submission_package_generate", {
        "actor_id": _require(args, "actor_id"),
        "scope": scope,
        "key": _require(args, "key"),
        "package": {
            "packageId": _require(args, "package_id"),
            "checklistId": checklist_id,
            "bytesB64": _b64.b64encode(
                rendered.encode("utf-8")).decode("ascii"),
            "items": provisions,
        },
    }, config, harness_call)
    generated["packageText"] = rendered
    generated["submissionChannel"] = "none"
    return generated


def _package_confirm(args: dict, config: dict, harness_call) -> dict:
    """律师确认闸（人工确认制）：显式 confirm 标志必带且为 True——确认
    不是隐式调用；缺标志＝f59_confirmation_flag_required 具名拒（账面
    零写入）。confirm 只在 harness 决定面落一行决定记录；对外提交动作
    结构性不存在。"""
    if args.get("confirm") is not True:
        raise SubmissionPackageError("f59_confirmation_flag_required")
    result = _harness("harness.submission_package_confirm", {
        "actor_id": _require(args, "actor_id"),
        "scope": _require(args, "scope"),
        "key": _require(args, "key"),
        "decision": {
            "packageId": _require(args, "package_id"),
            "packageSha256": _require(args, "package_sha256"),
            "reasonRef": _require(args, "reasonRef"),
            "receiptRef": _require(args, "receiptRef"),
        },
    }, config, harness_call)
    result["submissionChannel"] = "none"
    return result

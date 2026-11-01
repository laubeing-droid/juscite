# -*- coding: utf-8 -*-
"""F60 内部事件幂等同步外部日历（W3-U12；06:F60 双实例；裁决#6）。

内部事件幂等同步外部日历（滴答/飞书）；取消/改期冲突回流不自动更改法律
期限。期限面消费 F107 冻结引擎（calc.deadline_preset_evaluate 回执，
evaluationRef owner=jc）与 F106 日历账——本面绝不重算期限，只把回执值
原样入账（harness 登记时一次写入，无 UPDATE 路径）。

落点与分工（harness 两账见 legal-harness 仓 w3-u12 分支合同）：
- harness calendar_sync_items（同步账：UNIQUE(matter,target,event_key)＋
  payload_hash 同键同内容重放、异内容具名拒）＋calendar_external_events
  （外部回流事件账：取消/改期冲突具名，法律期限与外部状态分列）。
- 本面（产品侧）：①编排＝register（推送前守门）→HTTP 推送→record_
  result；②外部回流拉取 pull→逐事件入账（幂等 requestId 派生）；③冲突
  律师决定显式 confirm 闸。谁发起谁控制：产品发起，harness 只记账守门。

端点纪律（裁决#6 合成先行）：端点 URL 只来自显式 config
（calendar_sync_endpoints={ticktick:..., feishu:...}）；未配置目标＝
NotConnected calendar_sync_endpoint_not_configured 具名拒——本模块无任
何内置端点/默认 URL（禁编 URL，P11 同纪律）。真实 OAuth 授权后补联测；
合成端点回执带 synthetic 标记。
"""
from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request

CALENDAR_SYNC_METHODS = frozenset({
    "calendar.sync_event",
    "calendar.pull_external",
    "calendar.resolve_conflict",
    "calendar.sync_read",
    "calendar.sync_list",
})

_TARGET_KINDS = ("ticktick", "feishu")
_HTTP_TIMEOUT_S = 10.0


class CalendarSyncError(RuntimeError):
    """具名错误（f60_* 码），绝不携材料内容。"""


def _harness(method: str, args: dict, harness_call) -> dict:
    result = harness_call(method, args)
    if not isinstance(result, dict):
        raise CalendarSyncError("f60_harness_receipt_invalid:" + method)
    return result


def _require(args: dict, field: str):
    value = args.get(field)
    if value is None:
        raise CalendarSyncError("f60_field_missing:" + field)
    return value


def _endpoint(config: dict, target_kind: str) -> str:
    endpoints = config.get("calendar_sync_endpoints")
    if not isinstance(endpoints, dict) or not endpoints.get(target_kind):
        raise CalendarSyncError(
            "calendar_sync_endpoint_not_configured:" + target_kind)
    url = str(endpoints[target_kind])
    if not url.startswith(("http://", "https://")):
        raise CalendarSyncError("calendar_sync_endpoint_invalid:" + target_kind)
    return url


def _http_json(url: str, *, method: str, body: dict | None = None,
               query: dict | None = None) -> dict:
    if query:
        url = url + "?" + urllib.parse.urlencode(query)
    data = None
    if body is not None:
        data = json.dumps(body, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        url, data=data, method=method,
        headers={"Content-Type": "application/json; charset=utf-8"})
    try:
        with urllib.request.urlopen(request, timeout=_HTTP_TIMEOUT_S) \
                as response:
            payload = json.loads(
                response.read().decode("utf-8"), )
    except urllib.error.HTTPError as exc:
        raise CalendarSyncError(
            f"f60_endpoint_http_error:{exc.code}") from None
    except (urllib.error.URLError, OSError, ValueError) as exc:
        raise CalendarSyncError(
            "f60_endpoint_unreachable") from exc
    if not isinstance(payload, dict):
        raise CalendarSyncError("f60_endpoint_response_invalid")
    return payload


def calendar_sync_call(method: str, args: dict, config: dict,
                       harness_call=None) -> dict:
    """F60 产品面唯一入口（legal_entry 冻结方法组分派）。

    harness_call 注入点：缺省＝legal_entry.call（desktop 桥子进程全链）；
    selfhost recon 注入 resolve_provider_method 直连同封闭注册。"""
    if harness_call is None:
        from legal_entry import call as _entry_call

        def harness_call(h_method, h_args):
            return _entry_call(h_method, h_args, config)

    if method == "calendar.sync_event":
        return _sync_event(args, config, harness_call)
    if method == "calendar.pull_external":
        return _pull_external(args, config, harness_call)
    if method == "calendar.resolve_conflict":
        return _resolve_conflict(args, config, harness_call)
    if method == "calendar.sync_read":
        return _harness("harness.calendar_sync_read", {
            "scope": _require(args, "scope"),
            "sync_id": _require(args, "sync_id"),
        }, harness_call)
    if method == "calendar.sync_list":
        return _harness("harness.calendar_sync_list", {
            "scope": _require(args, "scope"),
        }, harness_call)
    raise CalendarSyncError("f60_method_not_connected:" + method)


def _sync_event(args: dict, config: dict, harness_call) -> dict:
    """内部期限事件 → 外部日历（幂等）。

    ①推送前守门：harness.calendar_sync_register 先落账（JC 期限回执互
    钉 owner=jc＋回执形态自洽）——登记拒绝则零出站流量；同 event_key 同
    内容重放直接返回既有行（不重复推送）。②HTTP 推送（显式配置端点）。
    ③结果回记（externalEventId；端点侧同 eventKey 幂等去重）。④投影
    回读（legalDueDate 与外部状态分列）。"""
    target_kind = _require(args, "targetKind")
    if target_kind not in _TARGET_KINDS:
        raise CalendarSyncError("f60_target_kind_invalid:" + str(target_kind))
    scope = _require(args, "scope")
    sync_id = _require(args, "sync_id")
    event_key = _require(args, "event_key")
    matter_id = scope.get("matterId") if isinstance(scope, dict) else None
    deadline_receipt = _require(args, "deadline_receipt")
    registered = _harness("harness.calendar_sync_register", {
        "actor_id": _require(args, "actor_id"),
        "scope": scope,
        "key": _require(args, "key"),
        "event": {
            "syncId": sync_id,
            "targetKind": target_kind,
            "eventKey": event_key,
            "title": _require(args, "title"),
            "dueDate": _require(args, "due_date"),
            "nominalDueDate": _require(args, "nominal_due_date"),
            "deadlineReceipt": deadline_receipt,
        },
    }, harness_call)
    if registered.get("replayed") is True:
        # 同键同内容：幂等重放，不重复推送。
        projection = _harness("harness.calendar_sync_read", {
            "scope": scope, "sync_id": sync_id}, harness_call)
        return dict(projection, replayed=True, pushed=False)
    endpoint = _endpoint(config, target_kind)
    pushed_ok = False
    external_event_id = None
    try:
        response = _http_json(
            endpoint.rstrip("/") + "/events", method="POST", body={
                "eventKey": event_key, "title": args.get("title"),
                "dueDate": args.get("due_date"),
                "matterId": matter_id, "syncId": sync_id,
            })
        external_event_id = response.get("externalEventId")
        if isinstance(external_event_id, str) and external_event_id:
            pushed_ok = True
    except CalendarSyncError:
        pushed_ok = False
    recorded = _harness("harness.calendar_sync_record_result", {
        "actor_id": args.get("actor_id"), "scope": scope,
        "key": {"requestId": f"push-{sync_id}-{event_key}",
                "targetId": None, "expectedRevision": None,
                "inputRefs": []},
        "result": {"syncId": sync_id,
                   "status": "synced" if pushed_ok else "sync_failed",
                   "externalEventId": external_event_id},
    }, harness_call)
    projection = _harness("harness.calendar_sync_read", {
        "scope": scope, "sync_id": sync_id}, harness_call)
    return dict(projection, replayed=False, pushed=pushed_ok,
                recordState=recorded.get("state"))


def _pull_external(args: dict, config: dict, harness_call) -> dict:
    """外部回流拉取（取消/改期冲突回流）：GET 显式配置端点 → 逐事件入
    harness 事件账（requestId 由 externalEventId 派生＝重复拉取幂等）。
    冲突具名返回；法律期限值随投影回读（永不因回流而变）。"""
    target_kind = _require(args, "targetKind")
    if target_kind not in _TARGET_KINDS:
        raise CalendarSyncError("f60_target_kind_invalid:" + str(target_kind))
    scope = _require(args, "scope")
    sync_id = _require(args, "sync_id")
    matter_id = scope.get("matterId") if isinstance(scope, dict) else None
    endpoint = _endpoint(config, target_kind)
    payload = _http_json(endpoint.rstrip("/") + "/events", method="GET",
                         query={"matterId": matter_id, "syncId": sync_id})
    events = payload.get("events")
    if events is None:
        events = []
    if not isinstance(events, list):
        raise CalendarSyncError("f60_endpoint_events_invalid")
    recorded = []
    for event in events:
        if not isinstance(event, dict):
            raise CalendarSyncError("f60_endpoint_events_invalid")
        external_event_id = event.get("externalEventId")
        if not isinstance(external_event_id, str) or not external_event_id:
            raise CalendarSyncError("f60_endpoint_events_invalid")
        entry = _harness("harness.calendar_external_event_record", {
            "actor_id": _require(args, "actor_id"), "scope": scope,
            "key": {"requestId": f"pull-{target_kind}-{external_event_id}",
                    "targetId": None, "expectedRevision": None,
                    "inputRefs": []},
            "external_event": {
                "externalEventId": external_event_id,
                "syncId": sync_id,
                "eventType": _require(event, "eventType"),
                "externalPayload": event.get("payload") or {},
                "externalDueDate": event.get("externalDueDate"),
            },
        }, harness_call)
        recorded.append(entry)
    projection = _harness("harness.calendar_sync_read", {
        "scope": scope, "sync_id": sync_id}, harness_call)
    return {"recorded": recorded, "projection": projection,
            "endpointSynthetic": bool(payload.get("synthetic"))}


def _resolve_conflict(args: dict, config: dict, harness_call) -> dict:
    """冲突律师决定闸（显式 confirm）：缺标志＝f60_confirmation_flag_
    required 具名拒。决定只是 harness 决定记录——法律期限仍不被本调用
    更改。"""
    if args.get("confirm") is not True:
        raise CalendarSyncError("f60_confirmation_flag_required")
    return _harness("harness.calendar_sync_resolve", {
        "actor_id": _require(args, "actor_id"),
        "scope": _require(args, "scope"),
        "key": _require(args, "key"),
        "resolution": {
            "syncId": _require(args, "sync_id"),
            "action": _require(args, "action"),
            "reasonRef": _require(args, "reasonRef"),
            "receiptRef": _require(args, "receiptRef"),
            "supersedingSyncId": args.get("superseding_sync_id"),
        },
    }, harness_call)

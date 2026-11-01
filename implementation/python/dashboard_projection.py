# -*- coding: utf-8 -*-
"""F115 案件看板投影＋F116 案件域分类产品面（工单 W3-U20 v1／W4-U49 v1.5）。

06 F115 assertion：v1实际在办待办/日程投影；全局对话主页，v1.5封皮完整字
段另验；不借F118未裁启用实务自动提醒。06 F116 assertion：诉讼/执行/非诉/
刑事等字段和筛选持久；分类不冒全域规则完备（v1 只做分类字段，分模块页面
v1.5）。

v1 段（W3-U20）：dashboard.read 唯一只读取数入口＋dashboard.domain_
declare/domain_read 薄转发。
v1.5 段（W4-U49）：dashboard.cover_read——案卷封皮全展开，字段全部绑定
harness 案件账真实回读（harness.cover_read 转录 F113 身份/F116 域/F04 名
册/W08 生命周期/待办/日程/E15-E18 账，本面零字段发明，只做形状守卫＋面
标记）；dashboard.module_read——域分类分模块页面（诉讼/执行/非诉/刑事四
具名域各一页，转录 harness.module_read＝看板 domainFilter 同一次投影；
unclassified 是筛选归纳表示值不是模块页，分模块不冒全域规则完备——
coverage 恒 exhaustiveClaim=false）。

**不借 F118 提醒派发（结构性，不是开关）**：本面所有方法与渲染守卫都拒
绝 dueDesktopReminders/reminders 键进入投影（f115_reminder_face_not_in_
dashboard 具名拒）；提醒派发唯一通道＝F118 调度器（f118_scheduler）——
W3-U26 分离不变量维持（裁决#20 后提醒本体归 W4-U50，看板侧仍不自动启用
实务提醒）。

config：复用 harness 桥同域键（harness_public_entry/harness_target/
harness_state_root/harness_service_registration/harness_timeout）。
错误码不携材料内容。
"""
from __future__ import annotations

DASHBOARD_FACE_NOTE = (
    "dashboard(W3-U20 v1/W4-U49 v1.5): harness.dashboard_read（v1 基础投"
    "影，只读聚合）+harness.case_domain_declare/read（四值闭集字段账）+"
    "harness.cover_read（v1.5 封皮全展开，字段绑定案件账真实回读）+"
    "harness.module_read（v1.5 域分类分模块页面）；提醒派发面=F118 调度器"
    "（本面拒绝该键）")

# legal_entry 冻结方法组（五方法，全部显式动作；组外即 method_not_connected
# ——自动分类/推断/提醒方法不存在于封闭面）。
DASHBOARD_METHODS = frozenset({
    "dashboard.read",
    "dashboard.domain_declare",
    "dashboard.domain_read",
    "dashboard.cover_read",
    "dashboard.module_read",
})

# 域闭集（与 harness case_domains CHECK 同集；wiring 测试与 recon 以
# harness coverage.domains 回执运行时对账——漂移＝f116_domain_set_drift
# 具名拒，不靠本表冒权威）。
DOMAIN_LABELS_CLOSED = ("litigation", "enforcement", "non_litigation",
                        "criminal")
# 筛选值闭集＝四具名域＋unclassified（域为 null 的案件在筛选归纳里的
# 表示值；unclassified 不可声明）。
DOMAIN_FILTER_VALUES_CLOSED = DOMAIN_LABELS_CLOSED + ("unclassified",)
# 生命周期归纳闭集（W08 TRANSITIONS 语义映射，harness 同集）。
LIFECYCLE_STATES_CLOSED = ("open", "stage_change", "closed")
# 提醒派发面键（F118 调度器独占；面板投影出现即具名拒）。
_REMINDER_FACE_KEYS = ("dueDesktopReminders", "reminders")
# 封皮键（v1 基础投影面出现即具名拒——封皮在 dashboard.cover_read 独立
# 面，不进看板行）。
_COVER_SHEET_KEYS = ("coverSheet", "cover", "封皮")
# v1.5 封皮/模块页投影面标记（dashboard.cover_read/module_read 响应携带；
# 提醒派发面照旧排除）。
COVER_FACE_KIND = "f115-v1.5-cover-sheet"
MODULE_FACE_KIND = "f116-v1.5-domain-module-page"


class DashboardProjectionError(RuntimeError):
    """具名错误（f115_*/f116_* 码），绝不携材料内容。"""


def _harness(method: str, args: dict, config: dict, harness_call) -> dict:
    result = harness_call(method, args)
    if not isinstance(result, dict):
        raise DashboardProjectionError(
            "f115_harness_receipt_invalid:" + method)
    return result


def _require(args: dict, field: str) -> object:
    value = args.get(field)
    if value is None:
        raise DashboardProjectionError("f115_field_missing:" + field)
    return value


def _validate_coverage(coverage: object) -> None:
    """coverage 声明面守卫：exhaustiveClaim=true＝分类完备性主张＝具名拒
    （分类不冒全域规则完备在渲染侧的机械形态）；域集与本面闭集漂移＝具名
    拒（以 harness 回执为运行时权威，不靠本地常量冒第二真源）。"""
    if not isinstance(coverage, dict):
        raise DashboardProjectionError("f115_coverage_invalid")
    if coverage.get("exhaustiveClaim") is not False:
        raise DashboardProjectionError("f115_exhaustive_claim_refused")
    domains = coverage.get("domains")
    if not isinstance(domains, list) \
            or sorted(str(item) for item in domains) \
            != sorted(DOMAIN_LABELS_CLOSED):
        raise DashboardProjectionError("f116_domain_set_drift")


def _validate_row(row: object) -> None:
    """逐 matter 行守卫：域值/生命周期闭集＋提醒派发键/封皮键出现即具名拒
    （不静默渲染、不渲染可能越界的面）。"""
    if not isinstance(row, dict) or not isinstance(row.get("matterId"), str):
        raise DashboardProjectionError("f115_row_invalid")
    schedule = row.get("schedule")
    if not isinstance(schedule, dict):
        raise DashboardProjectionError("f115_schedule_invalid")
    for key in _REMINDER_FACE_KEYS:
        if key in schedule or key in row:
            raise DashboardProjectionError(
                "f115_reminder_face_not_in_dashboard:" + key)
    for key in _COVER_SHEET_KEYS:
        if key in row:
            raise DashboardProjectionError(
                "f115_cover_sheet_not_in_v1:" + key)
    domain = row.get("domain")
    if domain is not None:
        if not isinstance(domain, dict):
            raise DashboardProjectionError("f116_domain_row_invalid")
        value = domain.get("domain")
        if value is not None and value not in DOMAIN_LABELS_CLOSED:
            raise DashboardProjectionError(
                "f116_domain_value_unknown:" + str(value))
    lifecycle = row.get("lifecycleState")
    if lifecycle not in LIFECYCLE_STATES_CLOSED:
        raise DashboardProjectionError(
            "f115_lifecycle_state_unknown:" + str(lifecycle))


def _validate_projection(view: dict) -> None:
    _validate_coverage(view.get("coverage"))
    if view.get("face") is not None:
        raise DashboardProjectionError("f115_face_key_reserved")
    matters = view.get("matters")
    if not isinstance(matters, list):
        raise DashboardProjectionError("f115_matters_invalid")
    for row in matters:
        _validate_row(row)
    summary = view.get("summary")
    if not isinstance(summary, dict):
        raise DashboardProjectionError("f115_summary_invalid")
    by_domain = summary.get("byDomain")
    if not isinstance(by_domain, dict):
        raise DashboardProjectionError("f115_summary_invalid")
    if set(by_domain) - set(DOMAIN_FILTER_VALUES_CLOSED):
        raise DashboardProjectionError("f116_domain_value_unknown:"
                                       + "summary.byDomain")


def dashboard_call(method: str, args: dict, config: dict,
                   harness_call=None) -> dict:
    """F115/F116 产品面唯一入口（legal_entry 冻结方法组分派）。

    harness_call 注入点：缺省＝legal_entry.call（desktop 桥子进程全链）；
    selfhost recon 注入 resolve_provider_method 直连同封闭注册。"""
    if harness_call is None:
        from legal_entry import call as _entry_call

        def harness_call(h_method, h_args):
            return _entry_call(h_method, h_args, config)

    if method == "dashboard.read":
        return _dashboard_read(args, config, harness_call)
    if method == "dashboard.domain_declare":
        return _domain_declare(args, config, harness_call)
    if method == "dashboard.domain_read":
        return _domain_read(args, config, harness_call)
    if method == "dashboard.cover_read":
        return _cover_read(args, config, harness_call)
    if method == "dashboard.module_read":
        return _module_read(args, config, harness_call)
    raise DashboardProjectionError("dashboard_method_not_connected:" + method)


def _dashboard_read(args: dict, config: dict, harness_call) -> dict:
    query = args.get("query")
    if query is None:
        query = {}
    if not isinstance(query, dict):
        raise DashboardProjectionError("f115_query_invalid")
    extra = set(query) - {"asOf", "domainFilter", "includeClosed"}
    if extra:
        raise DashboardProjectionError(
            "f115_query_fields_not_closed:" + ",".join(sorted(extra)))
    domain_filter = query.get("domainFilter")
    if domain_filter is not None:
        if not isinstance(domain_filter, list) or not domain_filter:
            raise DashboardProjectionError("f115_domain_filter_invalid")
        for value in domain_filter:
            if value not in DOMAIN_FILTER_VALUES_CLOSED:
                raise DashboardProjectionError(
                    "f116_domain_filter_value_unknown:" + str(value))
    view = _harness("harness.dashboard_read", {
        "actor_id": args.get("actor_id"),
        "query": query,
    }, config, harness_call)
    # 渲染前形状守卫：越界面/完备性主张/封皮键/提醒派发键一律具名拒。
    _validate_projection(view)
    view["face"] = {
        "kind": "dashboard-v1-basic-projection",
        "reminderFace": "excluded-f118-scheduler-only",
        "coverSheet": "f115-v1.5-cover-face",
    }
    return view


def _validate_identity_row(identity: object) -> None:
    """封皮身份行守卫（F113 转录）：identityKind/案号域不越本面闭集。"""
    if identity is None:
        return
    if not isinstance(identity, dict):
        raise DashboardProjectionError("f115_cover_identity_invalid")
    if identity.get("identityKind") not in \
            ("litigation", "non_litigation", "project"):
        raise DashboardProjectionError(
            "f115_cover_identity_kind_unknown:"
            + str(identity.get("identityKind")))


def _validate_members(members: object) -> None:
    """封皮成员名册守卫（F04 转录）：列表行 userId/orgId/roles 必备。"""
    if not isinstance(members, list):
        raise DashboardProjectionError("f115_cover_members_invalid")
    for member in members:
        if not isinstance(member, dict) \
                or not isinstance(member.get("userId"), str) \
                or not isinstance(member.get("orgId"), str) \
                or not isinstance(member.get("roles"), list):
            raise DashboardProjectionError("f115_cover_members_invalid")
        for key in _REMINDER_FACE_KEYS:
            if key in member:
                raise DashboardProjectionError(
                    "f115_reminder_face_not_in_dashboard:" + key)


def _cover_read(args: dict, config: dict, harness_call) -> dict:
    """F115-v1.5 案卷封皮全展开（只读）：薄转发 harness.cover_read（字段
    全部绑定案件账真实回读——本面零字段发明，只做形状守卫＋面标记）；
    提醒派发键出现即具名拒（F118 调度器独占，W3-U26 分离不变量）。"""
    query = args.get("query")
    if query is None:
        query = {}
    if not isinstance(query, dict):
        raise DashboardProjectionError("f115_query_invalid")
    extra = set(query) - {"asOf"}
    if extra:
        raise DashboardProjectionError(
            "f115_query_fields_not_closed:" + ",".join(sorted(extra)))
    scope = _require(args, "scope")
    result = _harness("harness.cover_read", {
        "actor_id": args.get("actor_id"),
        "scope": scope,
        "query": query,
    }, config, harness_call)
    body = result.get("cover")
    if not isinstance(body, dict):
        raise DashboardProjectionError("f115_cover_body_invalid")
    for key in _REMINDER_FACE_KEYS:
        if key in body:
            raise DashboardProjectionError(
                "f115_reminder_face_not_in_dashboard:" + key)
    _validate_coverage(result.get("coverage"))
    _validate_identity_row(body.get("identity"))
    _validate_members(body.get("members", []))
    if body.get("lifecycleState") not in LIFECYCLE_STATES_CLOSED:
        raise DashboardProjectionError(
            "f115_lifecycle_state_unknown:" + str(body.get("lifecycleState")))
    domain = body.get("domain")
    if domain is not None:
        value = domain.get("domain") if isinstance(domain, dict) else None
        if value is not None and value not in DOMAIN_LABELS_CLOSED:
            raise DashboardProjectionError(
                "f116_domain_value_unknown:" + str(value))
    result["face"] = {
        "kind": COVER_FACE_KIND,
        "reminderFace": "excluded-f118-scheduler-only",
        "source": "harness.cover_read-transcription",
    }
    return result


def _module_read(args: dict, config: dict, harness_call) -> dict:
    """F116-v1.5 域分类分模块页面（只读）：薄转发 harness.module_read（=
    看板 domainFilter 同一次投影）；模块只按四具名域开页——unclassified
    是筛选归纳表示值不是模块页（f116_module_value_unknown 具名拒），分模
    块不冒全域规则完备（coverage exhaustiveClaim=false 守卫不变）。"""
    domain = _require(args, "domain")
    if domain not in DOMAIN_LABELS_CLOSED:
        raise DashboardProjectionError(
            "f116_module_value_unknown:" + str(domain))
    query = args.get("query")
    if query is None:
        query = {}
    if not isinstance(query, dict):
        raise DashboardProjectionError("f115_query_invalid")
    extra = set(query) - {"asOf", "includeClosed"}
    if extra:
        raise DashboardProjectionError(
            "f115_query_fields_not_closed:" + ",".join(sorted(extra)))
    result = _harness("harness.module_read", {
        "actor_id": args.get("actor_id"),
        "domain": domain,
        "query": query,
    }, config, harness_call)
    module = result.get("module")
    if not isinstance(module, dict):
        raise DashboardProjectionError("f116_module_invalid")
    if module.get("domain") != domain:
        raise DashboardProjectionError("f116_module_domain_mismatch")
    _validate_coverage(module.get("coverage"))
    declared = module.get("declaredDomains")
    if not isinstance(declared, list) \
            or sorted(str(item) for item in declared) \
            != sorted(DOMAIN_LABELS_CLOSED):
        raise DashboardProjectionError("f116_domain_set_drift")
    matters = result.get("matters")
    if not isinstance(matters, list):
        raise DashboardProjectionError("f115_matters_invalid")
    for row in matters:
        _validate_row(row)
    for key in _REMINDER_FACE_KEYS:
        if key in result:
            raise DashboardProjectionError(
                "f115_reminder_face_not_in_dashboard:" + key)
    result["face"] = {
        "kind": MODULE_FACE_KIND,
        "reminderFace": "excluded-f118-scheduler-only",
        "exhaustiveClaim": False,
    }
    return result


def _domain_declare(args: dict, config: dict, harness_call) -> dict:
    declaration = _require(args, "declaration")
    if not isinstance(declaration, dict):
        raise DashboardProjectionError("f116_declaration_invalid")
    missing = {"domain", "note"} - set(declaration)
    if missing:
        # 显式 null 才是「无域/无注」：缺席键不隐式补齐（E20 输入闭集
        # 同纪律——与 harness case_domain_declare 的 fields_missing 同构）。
        raise DashboardProjectionError(
            "f116_declaration_fields_missing:" + ",".join(sorted(missing)))
    extra = set(declaration) - {"domain", "note"}
    if extra:
        raise DashboardProjectionError(
            "f116_declaration_fields_not_closed:"
            + ",".join(sorted(extra)))
    domain = declaration.get("domain")
    if domain is not None and domain not in DOMAIN_LABELS_CLOSED:
        raise DashboardProjectionError(
            "f116_domain_value_unknown:" + str(domain))
    result = _harness("harness.case_domain_declare", {
        "actor_id": _require(args, "actor_id"),
        "scope": _require(args, "scope"),
        "key": _require(args, "key"),
        "declaration": {"domain": domain, "note": declaration.get("note")},
    }, config, harness_call)
    row = result.get("domain")
    if not isinstance(row, dict) or "domain" not in row:
        raise DashboardProjectionError("f116_domain_row_invalid")
    return result


def _domain_read(args: dict, config: dict, harness_call) -> dict:
    result = _harness("harness.case_domain_read", {
        "scope": _require(args, "scope"),
        "actor_id": args.get("actor_id"),
    }, config, harness_call)
    _validate_coverage(result.get("coverage"))
    return result

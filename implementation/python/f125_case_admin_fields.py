"""F125 律所案管延伸 · 字段登记面（W5-U16，裁决#21「字段准备先行」）。

纯声明模块：四域数据字段的登记字典＋边界元数据。零 I/O、零建库、
零迁移、零桥方法——公开业务面结构性未启用（06 interface_gap
＝PENDING_SCOPE_NO_ENABLE 纪律，不假定批准；authority/05:238
「F32/F125待裁不通过场景五暗自启用」同频）。

权威钉定（只读引用，非本模块发明）：
  - authority/06 V7-125 行：owner=product+harness；
    python_entry_binding 逐字红线「record_time/issue_bill/record_payment
    仅律师账单，不债权回款」；interface_gap=PENDING_SCOPE_NO_ENABLE；
    status=PENDING_USER_DECISION。
  - authority/17 F125 卡 implementation_steps：「新场景字段在同owner扩
    不新库」——本登记面即按此纪律只备字段；落库=范围裁定后于既有
    owner 公开面扩，本模块不承载任何运行时真源（不复制第二权威，
    06 implementation 列原文）。
  - 00-总协调.md 裁决#21：「F125 v2 范围＝字段准备先行（财务对账/
    审批用印/归档借阅具体范围仍待裁；E16 真实回款不随它延迟）」。
  - LawLink 数据模型整段参考（03-功能分母.csv:127「LawLink
    收案→财务→审批→归档全流程+边界声明」；竞品情报
    2026-10-12/github-cn/raw/readmes/lawflow-boop__LawLink.md）。

字段类型闭集 FIELD_TYPES；金额一律 minor_units（整分，int 端到端，
与 E16 款源账 cash 面「金额整分端到端」同纪律——legal_entry.py
CASH_CONTRACT_METHODS 注释）；本模块对债权回款零字段零通道
（E16 款源账 VERIFIED 零改动）。

回收点（具名）：用户对财务对账/审批用印/归档借阅/审批回避具体范围
裁定后的 F125 v2 施工工单（06 status PENDING_USER_DECISION 翻行时）；
范围裁定前本登记面不进任何运行时链路。
"""
from __future__ import annotations

# 登记面版本（合同面单一来源；recon 钉定同值）。
REGISTRY_ID = "juscite-f125-field-prep/1"

# 字段类型闭集。minor_units＝整分整数（金额唯一合法类型；禁 float）。
FIELD_TYPES = frozenset({
    "id", "ref", "enum", "minor_units", "date", "datetime", "text",
    "bool",
})

# 公开业务面启用总闸：结构常量 False。本登记面无任何消费者，任何
# 运行时链路（桥/公共入口/UI）不得引用本模块产生业务行为；翻转此值
# 属范围裁定后 v2 施工工单的裁决面，字段准备阶段结构性不可达。
ENABLED = False

META = {
    "feature": "F125",
    "feature_name": "律所案管延伸（财务对账/审批用印/归档借阅/审批回避）",
    "owner": "product+harness",
    "python_entry": "P04",
    "authority_rows": [
        "authority/06-全量功能施工映射.csv V7-125（status="
        "PENDING_USER_DECISION；interface_gap=PENDING_SCOPE_NO_ENABLE）",
        "authority/17-逐项代码实施卡.csv F125 卡（新场景字段在同owner扩"
        "不新库）",
        "00-总协调.md §6.1 裁决#21（字段准备先行；E16 真实回款不随它延迟）",
    ],
    "interface_gap": "PENDING_SCOPE_NO_ENABLE",
    # 06 python_entry_binding 逐字红线（一字不改）。
    "billing_channel_redline": (
        "record_time/issue_bill/record_payment仅律师账单，不债权回款"),
    # 结构性分账边界：四域字段均属律所经营案管面；债权回款（案件应收
    # 现金）归 E16 款源账专属面，本登记面零字段零通道（03 功能分母
    # 「财务账单不得代债权回款」）。
    "cash_boundary": (
        "债权回款归 E16 款源账专属面（harness.cash_*）；本登记面零"
        "回款字段、零 F08 账单通道引用（财务账单不得代债权回款）"),
    "no_new_store": True,       # 17 卡：新场景字段在同owner扩不新库
    "second_authority": False,  # 06 implementation：不复制第二权威
    "lawlink_reference": (
        "竞品情报/2026-10-12/github-cn/raw/readmes/lawflow-boop__LawLink.md"
        "（03-功能分母.csv:127「LawLink 收案→财务→审批→归档全流程+边界"
        "声明」；整段参考非背书）"),
    "recovery_point": (
        "回收点＝用户对财务对账/审批用印/归档借阅/审批回避具体范围裁定"
        "后的 F125 v2 施工工单（06 status PENDING_USER_DECISION 翻行时）"),
    "e16_non_delay": (
        "E16 款源账 VERIFIED 零改动回归；案件真实回款不随本登记面延迟"
        "（裁决#21 逐字）"),
}

# 域顺序固定＝登记面枚举顺序；域键为稳定英文标识，中文名随 DOMAIN_NAMES。
DOMAIN_ORDER = ("finance_reconciliation", "approval_seal",
                "archive_borrow", "approval_recusal")

DOMAIN_NAMES = {
    "finance_reconciliation": "财务对账",
    "approval_seal": "审批用印",
    "archive_borrow": "归档借阅",
    "approval_recusal": "审批回避",
}


def _f(ftype, required, note, values=None):
    field = {"type": ftype, "required": required, "note": note}
    if values is not None:
        field["values"] = tuple(values)
    return field


# ---- 域一：财务对账（LawLink「财务与对账」段整段参考）-----------------
# LawLink 原文五操作：实收登记后确认、应收核销、发票关联、补充协议及
# 财务更正 → entry_kind 五值闭集。律所经营财务面，非债权回款。
FINANCE_RECONCILIATION_FIELDS = {
    "recon_entry_id": _f("id", True, "对账条目唯一标识"),
    "matter_ref": _f("ref", True, "关联案件/事项"),
    "entry_kind": _f("enum", True, "LawLink 五操作闭集",
                     values=("receipt_confirm", "receivable_writeoff",
                             "invoice_link", "supplement_agreement",
                             "finance_correction")),
    "amount_minor": _f("minor_units", True, "金额整分（int，禁 float）"),
    "currency": _f("enum", True, "币种闭集（扩币种属范围裁定）",
                   values=("CNY",)),
    "occurred_on": _f("date", True, "业务发生日"),
    "invoice_ref": _f("ref", False, "发票关联（invoice_link 必带）"),
    "agreement_ref": _f("ref", False, "补充协议引用"),
    "correction_reason": _f("text", False,
                            "更正原因（finance_correction 必带）"),
    "evidence_ref": _f("ref", True, "具名证据绑定（每条主张绑具名证据）"),
    "note": _f("text", False, "备注"),
}

# ---- 域二：审批用印（LawLink「统一审批」段整段参考）-------------------
# 五审批类：收案、文书、归档、开票及用章；「保留处理记录并区分批准与
# 后续执行」→ decision 与 execution_status 分列。
APPROVAL_SEAL_FIELDS = {
    "approval_id": _f("id", True, "审批单唯一标识"),
    "matter_ref": _f("ref", True, "关联案件/事项"),
    "approval_kind": _f("enum", True, "LawLink 五审批类闭集",
                        values=("intake", "document", "archive",
                                "invoicing", "seal")),
    "applicant_ref": _f("ref", True, "申请人"),
    "approver_ref": _f("ref", True, "审批人"),
    "authorization_ref": _f("ref", False, "事项授权匹配引用"),
    "seal_rule_ref": _f("ref", False, "印章规则（seal 类必带）"),
    "requested_at": _f("datetime", True, "申请时间"),
    "decided_at": _f("datetime", False, "审批时间（未决为空）"),
    "decision": _f("enum", False, "处理记录：批准/驳回",
                   values=("approved", "rejected")),
    "execution_status": _f("enum", True, "批准与后续执行分列",
                           values=("pending", "executed", "failed",
                                   "cancelled")),
    "execution_evidence_ref": _f("ref", False, "执行凭据"),
    "reason": _f("text", False, "审批意见"),
}

# ---- 域三：归档借阅（LawLink「归档与借阅」段整段参考）-----------------
# 本所制度、送审快照、归档收尾、补充归档及限时只读借阅；LawLink 边界
# 「未配置本所归档制度时不能提交正式归档」→ formal_archive 必带
# policy_ref；「限时只读借阅」→ borrow_mode 单值闭集。
ARCHIVE_BORROW_FIELDS = {
    "archive_id": _f("id", True, "归档卷唯一标识"),
    "matter_ref": _f("ref", True, "关联案件/事项"),
    "archive_kind": _f("enum", True, "归档形态闭集",
                       values=("formal_archive", "supplement_archive",
                               "review_snapshot")),
    "policy_ref": _f("ref", False,
                     "本所归档制度（formal_archive 必带）"),
    "snapshot_ref": _f("ref", False, "送审快照引用"),
    "finalized_ref": _f("ref", False, "归档收尾产物引用"),
    "archived_at": _f("date", False, "归档完成日"),
    "borrow_id": _f("id", False, "借阅单唯一标识（借阅半边）"),
    "borrower_ref": _f("ref", False, "借阅人"),
    "borrow_mode": _f("enum", False, "借阅形态闭集（限时只读）",
                      values=("timed_readonly",)),
    "borrow_until": _f("datetime", False,
                       "借阅到期（到期真实性验证属范围裁定）"),
    "borrow_status": _f("enum", False, "借阅状态闭集",
                        values=("active", "returned", "expired")),
}

# ---- 域四：审批回避（LawLink 边界声明整段参考）------------------------
# 「默认禁止审批本人申请。单人执业须显式设置本人审批例外，仍须匹配
# 事项授权及印章规则」→ 规则默认在、例外须显式引用。
APPROVAL_RECUSAL_FIELDS = {
    "recusal_id": _f("id", True, "回避记录唯一标识"),
    "approval_ref": _f("ref", True, "关联审批单"),
    "rule_kind": _f("enum", True, "回避规则闭集（默认禁止审批本人申请）",
                    values=("self_application_bar",)),
    "actor_ref": _f("ref", True, "被回避/匹配的审批人"),
    "exception_ref": _f("ref", False, "显式本人审批例外（单人执业）"),
    "scope_binding_ref": _f("ref", False, "事项授权及印章规则匹配引用"),
    "decided_by_ref": _f("ref", True, "回避判定人"),
    "reason": _f("text", True, "回避理由"),
    "decided_at": _f("datetime", True, "判定时间"),
}

DOMAIN_FIELDS = {
    "finance_reconciliation": FINANCE_RECONCILIATION_FIELDS,
    "approval_seal": APPROVAL_SEAL_FIELDS,
    "archive_borrow": ARCHIVE_BORROW_FIELDS,
    "approval_recusal": APPROVAL_RECUSAL_FIELDS,
}


def field_names(domain: str) -> tuple:
    """域内字段名元组（登记顺序）。域键必须在闭集内。"""
    if domain not in DOMAIN_FIELDS:
        raise KeyError("f125_field_domain_unknown:" + domain)
    return tuple(DOMAIN_FIELDS[domain])


def validate() -> None:
    """登记面自洽闭式校验（Fail-Fast，零静默）。

    只断言登记面自身契约：域闭集、字段名域内唯一、类型闭集、枚举带
    闭集值、总闸 False。不触碰任何存储。
    """
    if ENABLED is not False:
        raise AssertionError("f125_field_prep_must_be_disabled")
    if tuple(DOMAIN_FIELDS) != DOMAIN_ORDER:
        raise AssertionError("f125_field_domain_set_drift")
    for domain, fields in DOMAIN_FIELDS.items():
        seen = set()
        for name, spec in fields.items():
            if name in seen:
                raise AssertionError(
                    "f125_field_duplicate:" + domain + ":" + name)
            seen.add(name)
            if spec["type"] not in FIELD_TYPES:
                raise AssertionError(
                    "f125_field_type_unknown:" + domain + ":" + name)
            if spec["type"] == "enum" and not spec.get("values"):
                raise AssertionError(
                    "f125_enum_needs_closed_values:" + domain + ":" + name)

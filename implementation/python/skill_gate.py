# -*- coding: utf-8 -*-
"""F96 技能执行合同＋验收格式守门产品面（W3-U18）。

义务 06:F96（17 卡；F96-desktop/F96-selfhost 双实例）：「技能执行合同+验收
格式（fail-closed 门禁/证据四态/时点门禁/法源登记表/自带 evals）」＋台账
断言「技能自带证据/法源/时点/失败合同和 evals 真实守门；未核不签 PASS」
＋03 行「复用既有 QC/证据状态，不加每 skill 独立复杂门禁平台」＋08§3 引
证矩阵（与「测试绿≠内容通过」同构：测试绿≠内容通过；未核≠通过）。

落点（本面＝技能执行合同守门的唯一产品面；UI 仅调用/展示；W3-U16 先例
SKILL 通道唯一产品执行面同构）：技能 SKILL.md 正文恰一块
```lvyin-skill-contract 封闭 JSON（执行合同）→ skill.gate.validate（合
同校验）→ skill.gate.run（自带 evals 真实执行＋法源登记表逐条真核验＋
时点门禁 → 回执）→ skill.gate.verify_receipt（回执绑定核验）。

- 证据四态（闭集，复用既有 QC 证据语义不建第二平台）：
    VERIFIED   真跑且断言过（回执绑定技能字节 sha）
    UNVERIFIED 无回执（未核）——绝不签 PASS
    STALE      回执对应技能字节已被改（旧核不覆盖新内容）——不签 PASS
    REFUSED    真跑且正确拒绝（负向 eval / 已废止法源）
- 未核不签 PASS（结构性）：PASS 只能由 skill.gate.run 真实执行产生；无回
  执 verify_receipt→UNVERIFIED pass_allowed=False；pytest 绿（测试绿）
  与本门（内容通过）是独立分母——同构 08§3。
- 时点门禁：合同 as_of 必须为 ISO 日期且不得晚于运行日（未来时点合同无
  效）；法源登记表每条自带 as_of 透传既有 statute 面（缺/unknown 不签现
  行＝fail-closed 沿用 F69）。
- 法源登记表：合同 sources[] 逐条经既有 statute.resolve（E22 冻结面
  lccc_consumer）真核验登记；kind 闭集仅 {statute}——企业数据等无数据源
  的来源类型在合同层就没有可声明的类型（f96_source_kind_unknown），「无
  数据源不编企业调查」（F97 台账断言）由合同闭集结构保证。
- 失败合同：failure 两键闭值（named_refusal_not_pass /
  named_gap_no_fabrication）——声明「假成功/编造补数」形态的合同在校验
  层即拒（f96_failure_contract_invalid）。
- 自带 evals 真实守门：kind 闭集 {calculation, review_instantiate,
  citation, refusal}——calculation 经既有 skill.calculate（P01 JCClient
  真算）、review_instantiate 经既有 skill.review_instantiate（F25/F82
  底座真建批）、citation 经既有 statute.citation_gate（F69 引证闸）——
  全部复用既有冻结面，零第二权威；refusal 为结构级守门（合同三条件核
  验；LLM 运行时行为面属 E09 后续，本面无模型边界如实声明）。

fail-closed：typed error（SkillGateError 的 str 只有 f96_* 错误码，绝不
携材料内容）；未配置 harness/jc/codices config＝NotConnected（桥既有码
exit 3）。无状态根（合同与回执由调用方持存；核验无隐藏状态）。
"""
from __future__ import annotations

import hashlib
import json
import re
from datetime import date, datetime, timezone

from bridge_errors import NotConnected
from skill_semantics import (read_skill, _blocks_of, _body_of,
                             SkillSemanticsError)

SCHEMA = "juscite-f96-skill-gate/1"

# legal_entry 冻结方法组（唯一入口；组外方法绝不落到本面）。
SKILL_GATE_METHODS = frozenset({
    "skill.gate.validate",
    "skill.gate.run",
    "skill.gate.verify_receipt",
})

# 合同封闭块（fenced 围栏语言标记；正文恰一块）。
CONTRACT_BLOCK_LANG = "lvyin-skill-contract"

# 证据四态闭集（06:F96；复用既有 QC/证据状态语义）。
EVIDENCE_STATES = frozenset({"VERIFIED", "UNVERIFIED", "STALE", "REFUSED"})

GATE_PASS = "PASS"
GATE_NOT_PASS = "NOT_PASS"

# 法源登记表来源类型闭集：仅 statute（经 E22 冻结面真核验）。企业数据库/
# 第三方商业数据（F144 v1.5 MCP 连接器）未接入前没有可声明的类型——无数
# 据源只能具名缺口（refusal eval / failure 合同），不能编。
SOURCE_KINDS = frozenset({"statute"})

# refusal eval 场景闭集（v1：企业调查无数据源——F97 台账断言直落）。
REFUSAL_SCENARIOS = frozenset({"corporate_investigation_no_data_source"})

# eval kind 闭集（全部复用既有冻结执行面）。
EVAL_KINDS = frozenset({"calculation", "review_instantiate", "citation",
                        "refusal"})

# 引证闸决定闭集（F69 citation_gate decision）。
GATE_DECISIONS = frozenset({"ALLOWED", "BLOCKED", "UNKNOWN"})

_ISO_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_COMPACT_DATE_RE = re.compile(r"^\d{8}$")
_AS_OF_DATE_RE = re.compile(
    r"^(\d{4})-(\d{2})-(\d{2})$")

_CONTRACT_FIELDS = frozenset(
    {"as_of", "evidence", "sources", "failure", "evals"})
_EVIDENCE_FIELDS = frozenset({"mode"})
_FAILURE_DOC = {"on_gate_fail": "named_refusal_not_pass",
                "on_missing_data": "named_gap_no_fabrication"}
_SOURCE_FIELDS = frozenset({"id", "kind", "wjbs", "code31", "as_of"})

_EVAL_BASE_FIELDS = frozenset({"id", "kind"})
_EVAL_FIELDS_BY_KIND = {
    "calculation": frozenset({"matter_id", "input", "expect"}),
    "review_instantiate": frozenset({"matter_id", "batch_id", "expect"}),
    "citation": frozenset({"wjbs", "code31", "as_of", "expect"}),
    "refusal": frozenset({"scenario", "expect"}),
}


class SkillGateError(ValueError):
    """Typed F96 face failure; str() is a code, never material content."""


def _fail(code: str) -> SkillGateError:
    return SkillGateError(code)


def _require(args: dict, fields: frozenset, code: str) -> None:
    """DTO 闭集校验：必带字段缺一即拒、闭集外字段即拒（无旁路）。"""
    if not isinstance(args, dict) or set(args) != set(fields):
        raise NotConnected(code)


def _text(value, code: str) -> str:
    if not isinstance(value, str) or not value:
        raise _fail(code)
    return value


def _valid_iso_date(value: str) -> bool:
    if not _ISO_DATE_RE.match(value):
        return False
    try:
        date.fromisoformat(value)
    except ValueError:
        return False
    return True


def _valid_compact_date(value: str) -> bool:
    if not _COMPACT_DATE_RE.match(value):
        return False
    try:
        datetime.strptime(value, "%Y%m%d").date()
    except ValueError:
        return False
    return True


def _selected_skill(args: dict) -> dict:
    """选中纪律：调用方携带 skill_id，本面按同一 id 规则重推——不一致即拒
    （不得守门未选中的 skill；同 skill_semantics._selected_skill）。"""
    parsed = read_skill(_text(args.get("skill_path"),
                              "f96_skill_path_invalid"))
    selected = _text(args.get("skill_id"), "f96_skill_id_invalid")
    if parsed["id"] != selected:
        raise _fail("f96_skill_id_mismatch:" + parsed["id"]
                    + "!=" + selected)
    return parsed


# ---------------------------------------------------------------------- #
# 执行合同解析（fail-closed 闭集校验）
# ---------------------------------------------------------------------- #


def _expect_calculation(expect, code: str) -> dict:
    if not isinstance(expect, dict) or not expect \
            or set(expect) - {"amount_minor", "refused_code"} \
            or "amount_minor" in expect and "refused_code" in expect:
        raise _fail(code)
    if "amount_minor" in expect:
        value = expect["amount_minor"]
        if not isinstance(value, int) or isinstance(value, bool):
            raise _fail(code)
        return {"amount_minor": value}
    return {"refused_code": _text(expect["refused_code"], code)}


def _contract_of(parsed: dict) -> dict:
    """正文恰一块合同封闭块 → 闭集校验后的合同文档（含块 sha256）。
    块缺失/不唯一/JSON 坏/字段闭集外/闭值外/未来 as_of 一律 typed 拒。"""
    try:
        raw = _blocks_of(_body_of(parsed), CONTRACT_BLOCK_LANG,
                         "f96_contract_block_missing",
                         "f96_contract_block_not_unique")
    except SkillSemanticsError as exc:
        # 块锚解析复用 skill_semantics 同一实现；类型归一为本面 typed 拒
        # （missing/not_unique 码即 f96_*，透传不改写）。
        raise _fail(str(exc)) from None
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        raise _fail("f96_contract_json_invalid") from None
    if not isinstance(data, dict) or set(data) != _CONTRACT_FIELDS:
        raise _fail("f96_contract_fields_invalid")
    # 时点门禁：ISO 日期＋不得晚于运行日（未来时点合同无效）。
    as_of = _text(data["as_of"], "f96_contract_as_of_invalid")
    if not _valid_iso_date(as_of):
        raise _fail("f96_contract_as_of_invalid")
    if date.fromisoformat(as_of) > datetime.now(timezone.utc).date():
        raise _fail("f96_contract_as_of_in_future")
    # 证据四态声明：唯一合法 mode（采用四态记账）。
    evidence = data["evidence"]
    if not isinstance(evidence, dict) or set(evidence) != _EVIDENCE_FIELDS \
            or evidence["mode"] != "four_state":
        raise _fail("f96_contract_evidence_mode_invalid")
    # 失败合同：两键闭值（假成功/编造补数形态无合法值可写）。
    if data["failure"] != _FAILURE_DOC:
        raise _fail("f96_failure_contract_invalid")
    # 法源登记表：可空；非空逐条闭集（kind∈SOURCE_KINDS；wjbs/code31 恰
    # 一；as_of 8 位透传 statute 面）。
    raw_sources = data["sources"]
    if not isinstance(raw_sources, list):
        raise _fail("f96_sources_invalid")
    sources = []
    seen = set()
    for item in raw_sources:
        if not isinstance(item, dict) or set(item) != _SOURCE_FIELDS:
            raise _fail("f96_source_fields_invalid")
        source_id = _text(item["id"], "f96_source_id_invalid")
        if source_id in seen:
            raise _fail("f96_source_duplicate:" + source_id)
        seen.add(source_id)
        if item["kind"] not in SOURCE_KINDS:
            raise _fail("f96_source_kind_unknown:" + str(item["kind"]))
        wjbs, code31 = item["wjbs"], item["code31"]
        if bool(wjbs) == bool(code31) or not (
                isinstance(wjbs, str) or isinstance(code31, str)):
            raise _fail("f96_source_identifier_invalid")
        source_as_of = _text(item["as_of"], "f96_source_as_of_invalid")
        if not _valid_compact_date(source_as_of):
            raise _fail("f96_source_as_of_invalid")
        sources.append({"id": source_id, "kind": item["kind"],
                        "wjbs": wjbs if isinstance(wjbs, str) else None,
                        "code31": code31 if isinstance(code31, str)
                        else None,
                        "as_of": source_as_of})
    # 自带 evals：非空；kind 决定字段闭集；expect 结构随 kind。
    raw_evals = data["evals"]
    if not isinstance(raw_evals, list) or not raw_evals:
        raise _fail("f96_evals_invalid")
    evals = []
    seen_ids = set()
    for item in raw_evals:
        if not isinstance(item, dict) or not _EVAL_BASE_FIELDS <= set(item):
            raise _fail("f96_eval_fields_invalid")
        kind = item["kind"]
        if kind not in EVAL_KINDS:
            raise _fail("f96_eval_kind_unknown:" + str(kind))
        if set(item) != _EVAL_BASE_FIELDS | _EVAL_FIELDS_BY_KIND[kind]:
            raise _fail("f96_eval_fields_invalid")
        eval_id = _text(item["id"], "f96_eval_id_invalid")
        if eval_id in seen_ids:
            raise _fail("f96_eval_duplicate:" + eval_id)
        seen_ids.add(eval_id)
        expect = item.get("expect")
        if kind == "calculation":
            matter_id = _text(item["matter_id"], "f96_eval_field_invalid")
            if not isinstance(item["input"], dict) or not item["input"]:
                raise _fail("f96_eval_field_invalid")
            entry = {"matter_id": matter_id, "input": item["input"],
                     "expect": _expect_calculation(
                         expect, "f96_eval_expect_invalid")}
        elif kind == "review_instantiate":
            matter_id = _text(item["matter_id"], "f96_eval_field_invalid")
            batch_id = _text(item["batch_id"], "f96_eval_field_invalid")
            if not isinstance(expect, dict) \
                    or set(expect) != {"column_ids"} \
                    or not isinstance(expect["column_ids"], list) \
                    or not expect["column_ids"] or not all(
                        isinstance(c, str) and c
                        for c in expect["column_ids"]):
                raise _fail("f96_eval_expect_invalid")
            entry = {"matter_id": matter_id, "batch_id": batch_id,
                     "expect": {"column_ids": sorted(
                         expect["column_ids"])}}
        elif kind == "citation":
            wjbs, code31 = item.get("wjbs"), item.get("code31")
            if bool(wjbs) == bool(code31):
                raise _fail("f96_eval_identifier_invalid")
            eval_as_of = _text(item.get("as_of"),
                               "f96_eval_field_invalid")
            if not _valid_compact_date(eval_as_of):
                raise _fail("f96_eval_field_invalid")
            if not isinstance(expect, dict) or set(expect) != {"decision"} \
                    or expect["decision"] not in GATE_DECISIONS:
                raise _fail("f96_eval_expect_invalid")
            entry = {"expect": {"decision": expect["decision"]},
                     "identifier": {"wjbs": wjbs
                                    if isinstance(wjbs, str) else None,
                                    "code31": code31
                                    if isinstance(code31, str) else None},
                     "as_of": eval_as_of}
        else:  # refusal
            scenario = _text(item.get("scenario"),
                             "f96_eval_field_invalid")
            if scenario not in REFUSAL_SCENARIOS:
                raise _fail("f96_eval_scenario_unknown:" + scenario)
            if not isinstance(expect, dict) or set(expect) != {"outcome"} \
                    or expect["outcome"] != "refused":
                raise _fail("f96_eval_expect_invalid")
            entry = {"expect": {"outcome": "refused"},
                     "scenario": scenario}
        evals.append({"id": eval_id, "kind": kind, **entry})
    return {
        "as_of": as_of,
        "evidence_mode": evidence["mode"],
        "failure": dict(_FAILURE_DOC),
        "sources": sources,
        "evals": evals,
        "sha256": hashlib.sha256(raw.encode("utf-8")).hexdigest(),
    }


def validate_skill(args: dict) -> dict:
    """合同校验面：解析＋闭集校验（不执行 evals；无回执产生——validate
    后未 run 的技能守门状态恒 UNVERIFIED，不签 PASS）。"""
    parsed = _selected_skill(args)
    contract = _contract_of(parsed)
    return {
        "schema": SCHEMA,
        "face": "validate",
        "skill": {"id": parsed["id"],
                  "contentSha256": parsed["contentSha256"]},
        "contractSha256": contract["sha256"],
        "as_of": contract["as_of"],
        "evidenceMode": contract["evidence_mode"],
        "failure": contract["failure"],
        "sources": [{"id": s["id"], "kind": s["kind"]}
                    for s in contract["sources"]],
        "evals": [{"id": e["id"], "kind": e["kind"]}
                  for e in contract["evals"]],
    }


# ---------------------------------------------------------------------- #
# 守门执行：自带 evals 真跑＋法源登记表真核验 → 回执
# ---------------------------------------------------------------------- #


def _entry_call(method: str, args: dict, config: dict):
    """既有冻结面分派 seam（默认＝legal_entry.call 同进程径；selfhost 侧
    seam 注入同 skill_semantics._harness_call 先例）。"""
    import legal_entry
    return legal_entry.call(method, args, config)


def _entry_call_outcome(method: str, args: dict, config: dict) -> dict:
    """统一收集执行结局：ok(result) / refused(code) / error(类型名)。
    legal_entry 桥的 typed 拒＝NotConnected；JC typed 拒＝JCMethodFailure
    （JC_FAILURE exit 4）。其余异常（执行环境故障）记为 error——守门器必
    须总能产出回执（eval 失败＝内容判定 NOT_PASS，不是吞异常；detail 只
    携类型名，材料内容绝不进码）。"""
    import legal_entry
    from bridge_errors import NotConnected as _NC
    try:
        return {"ok": True, "result": _entry_call(method, args, config),
                "code": None}
    except _NC as exc:
        return {"ok": False, "result": None, "code": str(exc)}
    except legal_entry.JCMethodFailure as exc:
        return {"ok": False, "result": None, "code": str(exc)}
    except Exception as exc:  # noqa: BLE001 — 门禁器必须产出回执
        return {"ok": False, "result": None,
                "code": "execution_error:" + type(exc).__name__}


def _run_eval_calculation(contract_eval: dict, skill: dict, config: dict,
                          parsed_path: str) -> dict:
    outcome = _entry_call_outcome(
        "skill.calculate",
        {"skill_path": parsed_path, "skill_id": skill["id"],
         "matter_id": contract_eval["matter_id"],
         "input": contract_eval["input"]},
        config)
    expect = contract_eval["expect"]
    if "refused_code" in expect:
        if outcome["ok"]:
            return {"state": "UNVERIFIED", "passed": False,
                    "detail": "expected_refusal_but_executed"}
        code = outcome["code"] or ""
        if expect["refused_code"] in code:
            return {"state": "REFUSED", "passed": True,
                    "detail": "refused:" + expect["refused_code"]}
        return {"state": "REFUSED", "passed": False,
                "detail": "refused_wrong_code:" + code[:80]}
    if not outcome["ok"]:
        return {"state": "UNVERIFIED", "passed": False,
                "detail": "execution_refused:" + (outcome["code"]
                                                  or "")[:80]}
    sheet = (outcome["result"] or {}).get("result") or {}
    actual = sheet.get("amount_minor")
    if actual == expect["amount_minor"]:
        return {"state": "VERIFIED", "passed": True,
                "detail": "amount_minor=%s" % actual}
    return {"state": "UNVERIFIED", "passed": False,
            "detail": "amount_mismatch expected=%s actual=%s" % (
                expect["amount_minor"], actual)}


def _run_eval_review(contract_eval: dict, skill: dict, config: dict,
                     parsed_path: str) -> dict:
    key = {"requestId": "f96gate-%s-%s" % (skill["id"],
                                           contract_eval["id"]),
           "targetId": None, "expectedRevision": None, "inputRefs": []}
    outcome = _entry_call_outcome(
        "skill.review_instantiate",
        {"skill_path": parsed_path, "skill_id": skill["id"],
         "matter_id": contract_eval["matter_id"],
         "batch_id": contract_eval["batch_id"], "key": key},
        config)
    if not outcome["ok"]:
        return {"state": "UNVERIFIED", "passed": False,
                "detail": "execution_refused:" + (outcome["code"]
                                                  or "")[:80]}
    created = outcome["result"] or {}
    got = sorted(c.get("id") for c in created.get("templateColumns") or [])
    want = contract_eval["expect"]["column_ids"]
    if created.get("batchId") == contract_eval["batch_id"] and got == want:
        return {"state": "VERIFIED", "passed": True,
                "detail": "batch=%s columns=%d" % (created["batchId"],
                                                   len(got))}
    return {"state": "UNVERIFIED", "passed": False,
            "detail": "columns_mismatch got=%s want=%s" % (
                ",".join(got), ",".join(want))}


def _run_eval_citation(contract_eval: dict, config: dict) -> dict:
    ident = contract_eval["identifier"]
    query = {"as_of": contract_eval["as_of"]}
    if ident["wjbs"]:
        query["wjbs"] = ident["wjbs"]
    else:
        query["code31"] = ident["code31"]
    outcome = _entry_call_outcome("statute.citation_gate", query, config)
    if not outcome["ok"]:
        return {"state": "UNVERIFIED", "passed": False,
                "detail": "execution_refused:" + (outcome["code"]
                                                  or "")[:80]}
    decision = (outcome["result"] or {}).get("decision")
    want = contract_eval["expect"]["decision"]
    if decision == want:
        return {"state": "VERIFIED", "passed": True,
                "detail": "decision=%s" % decision}
    return {"state": "UNVERIFIED", "passed": False,
            "detail": "decision_mismatch got=%s want=%s" % (decision,
                                                            want)}


def _run_eval_refusal(contract_eval: dict, contract: dict) -> dict:
    """结构级守门（如实声明：LLM 运行时行为面属 E09 后续，本面无模型）：
    场景在闭集＋合同 failure 声明 named_gap_no_fabrication＋法源登记表类
    型闭集无企业数据来源——三条件全真才给 REFUSED(过)。任一不真即守门器
    自身被破坏＝UNVERIFIED 不过（绝不假成功）。"""
    conditions = {
        "scenario_in_closed_set":
            contract_eval["scenario"] in REFUSAL_SCENARIOS,
        "failure_contract_no_fabrication":
            contract["failure"]["on_missing_data"]
            == "named_gap_no_fabrication",
        "no_corporate_source_kind":
            all(s["kind"] in SOURCE_KINDS for s in contract["sources"]),
    }
    if all(conditions.values()):
        return {"state": "REFUSED", "passed": True,
                "detail": "scenario=%s conditions=%s" % (
                    contract_eval["scenario"],
                    ",".join("%s=%s" % (k, str(v).lower())
                             for k, v in sorted(conditions.items())))}
    return {"state": "UNVERIFIED", "passed": False,
            "detail": "gate_structural_violation"}


def _verify_source(source: dict, config: dict) -> dict:
    """法源登记表逐条真核验（既有 statute.citation_gate＝F69 引证闸：可
    引性同闸，与引证矩阵同构——已废止检索到也不许引；unknown 不签现行）。"""
    query = {"as_of": source["as_of"]}
    if source["wjbs"]:
        query["wjbs"] = source["wjbs"]
    else:
        query["code31"] = source["code31"]
    outcome = _entry_call_outcome("statute.citation_gate", query, config)
    if not outcome["ok"]:
        return {"id": source["id"], "state": "UNVERIFIED",
                "status": None,
                "detail": "execution_refused:" + (outcome["code"]
                                                  or "")[:80]}
    face = outcome["result"] or {}
    decision = face.get("decision")
    status = face.get("status_label")
    if decision == "ALLOWED":
        return {"id": source["id"], "state": "VERIFIED",
                "status": status, "detail": "citable_at_as_of"}
    if decision == "BLOCKED":
        return {"id": source["id"], "state": "REFUSED",
                "status": status, "detail": "not_citable_at_as_of"}
    return {"id": source["id"], "state": "UNVERIFIED", "status": status,
            "detail": "decision_unknown_fail_closed:" + str(face.get(
                "code", ""))[:60]}


def run_gate(args: dict, config: dict) -> dict:
    """守门执行：evals 全部真跑（各自既有冻结面）＋sources 逐条真核验＋
    时点门（合同校验含未来拒）→ 回执。

    PASS ⇔ 每 eval 真跑且断言过（VERIFIED 或 REFUSED-passed）∧每登记法源
    VERIFIED。其余一律 NOT_PASS＋具名 reasons。evals 数与合同不等（执行
    层异常）→ eval_not_executed，绝不以部分执行签 PASS。"""
    parsed = _selected_skill(args)
    contract = _contract_of(parsed)
    skill = {"id": parsed["id"], "contentSha256": parsed["contentSha256"]}
    executed = []
    for contract_eval in contract["evals"]:
        kind = contract_eval["kind"]
        if kind == "calculation":
            outcome = _run_eval_calculation(contract_eval, skill, config,
                                            parsed["path"])
        elif kind == "review_instantiate":
            outcome = _run_eval_review(contract_eval, skill, config,
                                       parsed["path"])
        elif kind == "citation":
            outcome = _run_eval_citation(contract_eval, config)
        else:
            outcome = _run_eval_refusal(contract_eval, contract)
        executed.append({"id": contract_eval["id"], "kind": kind,
                         "state": outcome["state"],
                         "passed": outcome["passed"],
                         "detail": outcome["detail"]})
    registry = [_verify_source(s, config) for s in contract["sources"]]
    reasons = []
    if len(executed) != len(contract["evals"]):
        reasons.append("eval_not_executed")
    for item in executed:
        if not item["passed"]:
            reasons.append("eval_failed:" + item["id"])
    for item in registry:
        if item["state"] != "VERIFIED":
            reasons.append("source_not_verified:" + item["id"])
    gate = GATE_PASS if not reasons else GATE_NOT_PASS
    receipt = {
        "schema": SCHEMA,
        "face": "run",
        "skill": skill,
        "contractSha256": contract["sha256"],
        "as_of": contract["as_of"],
        "gate": gate,
        "reasons": reasons,
        "evals": executed,
        "sourcesRegistry": registry,
        "executedAt": datetime.now(timezone.utc).strftime(
            "%Y-%m-%dT%H:%M:%SZ"),
    }
    receipt["receiptSha256"] = hashlib.sha256(
        json.dumps(receipt, ensure_ascii=False, sort_keys=True,
                   separators=(",", ":")).encode("utf-8")).hexdigest()
    return receipt


def verify_receipt(args: dict) -> dict:
    """回执绑定核验（证据四态裁决面）：
    - 无回执 → UNVERIFIED pass_allowed=False（未核不签 PASS）
    - 回执结构/digest 坏 → typed 拒（f96_receipt_invalid/_digest_mismatch）
    - 回执技能 id 不匹配 → typed 拒（f96_receipt_skill_mismatch）
    - 技能字节已变（contentSha256 不等）→ STALE pass_allowed=False
    - 绑定成立 → VERIFIED；pass_allowed=（回执 gate==PASS）"""
    skill_path = _text(args.get("skill_path"), "f96_skill_path_invalid")
    receipt = args.get("receipt")
    if receipt is None:
        return {"schema": SCHEMA, "face": "verify_receipt",
                "state": "UNVERIFIED", "pass_allowed": False,
                "reason": "no_receipt"}
    if not isinstance(receipt, dict) or receipt.get("schema") != SCHEMA \
            or receipt.get("face") != "run" \
            or not isinstance(receipt.get("skill"), dict) \
            or receipt.get("gate") not in (GATE_PASS, GATE_NOT_PASS):
        raise _fail("f96_receipt_invalid")
    digest = receipt.get("receiptSha256")
    body = {k: v for k, v in receipt.items() if k != "receiptSha256"}
    recomputed = hashlib.sha256(
        json.dumps(body, ensure_ascii=False, sort_keys=True,
                   separators=(",", ":")).encode("utf-8")).hexdigest()
    if digest != recomputed:
        raise _fail("f96_receipt_digest_mismatch")
    parsed = read_skill(skill_path)
    if parsed["id"] != receipt["skill"].get("id"):
        raise _fail("f96_receipt_skill_mismatch")
    if parsed["contentSha256"] != receipt["skill"].get("contentSha256"):
        return {"schema": SCHEMA, "face": "verify_receipt",
                "state": "STALE", "pass_allowed": False,
                "receipt_gate": receipt["gate"],
                "skill_content_sha256": parsed["contentSha256"],
                "reason": "skill_bytes_changed_since_receipt"}
    return {"schema": SCHEMA, "face": "verify_receipt",
            "state": "VERIFIED",
            "pass_allowed": receipt["gate"] == GATE_PASS,
            "gate": receipt["gate"]}


def gate_call(method: str, args: dict, config: dict) -> dict:
    if not isinstance(args, dict):
        raise NotConnected("f96_params_invalid")
    if method == "skill.gate.validate":
        _require(args, {"skill_path", "skill_id"},
                 "f96_validate_params_invalid")
        return validate_skill(args)
    if method == "skill.gate.run":
        _require(args, {"skill_path", "skill_id"},
                 "f96_run_params_invalid")
        return run_gate(args, config)
    if method == "skill.gate.verify_receipt":
        _require(args, {"skill_path", "receipt"},
                 "f96_verify_params_invalid")
        return verify_receipt(args)
    raise NotConnected("method_not_connected:" + method)

# -*- coding: utf-8 -*-
"""F88 可答/应拒双集合评估＋六指标 CI 门（工单 W2b-U03）。

评估面（不复制第二权威）：本模块**只消费** F70 同源核验面
（citation_verifier.citation_call——legal_entry citation.* 冻结方法组分发的
同一核验核心；版本/效力经 statute_validity，法源经 E22 冻结面
lccc_consumer v1.1）。评估=对黄金集标签逐条对账，不改核验语义。

六指标（06 行 F88「保原六指标CI门」）出处＝judicex gold_runner.py 阈值表
（蓝图 L13；竞品情报 2026-10-12/repos/TEARDOWN-doc-haus-judicex.md §3.2），
逐名适配到引证核验域，阈值原样保留：

  | 指标 | 适配定义 | 阈值 |
  |---|---|---|
  | domain_route_accuracy | 题→所引版本路由正确：记录 identifier==expected_wjbs（虚构题=None） | ≥0.90 |
  | hallucination_rate | 假断言率：verified_scoped=True 的断言中落在应拒集（黄金标签）的比例 | ≤0.10 |
  | citation_accuracy | Σ|已证条文∩must_cite| / Σ|must_cite|（可答集累计） | ≥0.80 |
  | false_citation_rate | Σ|被肯定条文∩must_not_cite| / Σ全部被肯定引用（全集合） | ≤0.05 |
  | excerpt_recall | expected_excerpts 在 support.article_text 回读命中比例 | ≥0.60 |
  | status_accuracy | 逐条 status==expected_status（双集合共同分母） | ≥0.80 |

源表第 7 行 mean_confidence 无确定性核验面对应物（编造置信分=幻觉），
具名排除不改六指标（EXCLUDED_FROM_SOURCE_TABLE）。

双集合合同（06 行 F88 acceptance）：
  - 可答覆盖正确率 / 应拒正确拒绝率**共同报告分母**（set 分母＋双集合合计
    共同分母同时给出）；
  - 永远拒答不通过：可答覆盖正确率阈值 ≥0.90 入门（refuse_all 控制组
    gate 必 FAIL）；全答也不通过（answer_all 控制组必 FAIL）；
  - 双集合为新增报告面，**不替删原六指标**（six_metrics 键恒为源六名）；
  - 核验器统计不冒独立幻觉率：hallucination_rate 只由
    (verified_scoped, 黄金集集合归属) 对账得出，绝不读核验器自报统计
    （answer_all 控制组自带诱饵 self_reported_hallucination_rate=0.0，
    评估照实报 15/27——独立性由构造证明）。

CI 门语义：源表「任何阈值不达→进程非零退出（CI 门）」——门=阈值点估计
＋非零退出码；每个比例指标另报 Wilson 95% 置信区间（ci95）入证据，
区间不替代阈值判定（judicex 原门即点估计门，区间为 F88 追加可观测性）。
"""

from __future__ import annotations

import json
import math
import os
import re

from bridge_errors import NotConnected

GOLDEN_SCHEMA = "juscite-f88-citations-golden/1"
REPORT_SCHEMA = "juscite-f88-dualset-report/1"
STATUS_CURRENT = "现行"

# Wilson 95%（z=1.96 精确常量，确定性）
Z95 = 1.96

SIX_METRIC_SPECS = (
    {"name": "domain_route_accuracy", "op": ">=", "threshold": 0.90,
     "definition": "题→所引版本路由正确：identifier==expected_wjbs"
                   "（虚构题=None）比例（双集合共同分母）"},
    {"name": "hallucination_rate", "op": "<=", "threshold": 0.10,
     "definition": "假断言率：verified_scoped=True 断言落在应拒集的比例"
                   "（只对黄金标签计算，不读核验器自报统计）"},
    {"name": "citation_accuracy", "op": ">=", "threshold": 0.80,
     "definition": "Σ|已证条文∩must_cite|/Σ|must_cite|（可答集累计）"},
    {"name": "false_citation_rate", "op": "<=", "threshold": 0.05,
     "definition": "Σ|被肯定条文∩must_not_cite|/Σ全部被肯定引用"
                   "（全集合累计分母）"},
    {"name": "excerpt_recall", "op": ">=", "threshold": 0.60,
     "definition": "expected_excerpts 在 support.article_text 回读命中比例"},
    {"name": "status_accuracy", "op": ">=", "threshold": 0.80,
     "definition": "逐条 status==expected_status 比例（双集合共同分母）"},
)
SIX_METRIC_NAMES = tuple(spec["name"] for spec in SIX_METRIC_SPECS)

# 双集合新增门条件（06 行 F88：共同分母＋永远拒答不通过；阈值取与源表
# 准确率最高档一致的 0.90——设计裁量已入台账边界，不冒源表名义）
DUALSET_SPECS = (
    {"name": "answerable_coverage_correct", "op": ">=", "threshold": 0.90,
     "definition": "可答覆盖正确率：现行且 verified_scoped=True / |可答集|"
                   "（另报共同分母）"},
    {"name": "refuse_correct_rejection", "op": ">=", "threshold": 0.90,
     "definition": "应拒正确拒绝率：未肯定且 status==expected_status / "
                   "|应拒集|（另报共同分母）"},
)

EXCLUDED_FROM_SOURCE_TABLE = {
    "mean_confidence": "源表第 7 行 mean_confidence：确定性核验面无置信"
                       "模型，编造置信分=幻觉；具名排除，不改六指标",
}

METRICS_SOURCE = (
    "judicex gold_runner.py 阈值表（蓝图 L13；竞品情报 2026-10-12/repos/"
    "TEARDOWN-doc-haus-judicex.md §3.2）六行逐名适配引证核验域，阈值原样"
)

CONTROLS = ("refuse_all", "answer_all")

DATE8_RE = re.compile(r"^\d{8}$")


# ---------------------------------------------------------------------- #
# Wilson 置信区间（确定性纯数学）
# ---------------------------------------------------------------------- #

def wilson_ci(k: int, n: int, z: float = Z95) -> list:
    """二比例 Wilson score 区间；n=0 → [0.0, 1.0]（无样本不收敛，如实宽区间）。"""
    if n <= 0:
        return [0.0, 1.0]
    p = k / n
    z2 = z * z
    denom = 1.0 + z2 / n
    centre = (p + z2 / (2.0 * n)) / denom
    half = (z * math.sqrt(p * (1.0 - p) / n + z2 / (4.0 * n * n))) / denom
    return [max(0.0, centre - half), min(1.0, centre + half)]


def _rate(num: int, den: int) -> float:
    return (num / den) if den else 0.0


def _metric_entry(name: str, op: str, threshold: float, value: float,
                  num: int, den: int, extra: dict | None = None) -> dict:
    passed = (value >= threshold) if op == ">=" else (value <= threshold)
    entry = {
        "value": round(value, 6),
        "op": op,
        "threshold": threshold,
        "pass": passed,
        "numerator": num,
        "denominator": den,
        "ci95_wilson": [round(lo, 6) for lo in wilson_ci(num, den)],
        "zero_denominator_note": (None if den else
                                  "分母=0：值按 0.0 记（不猜）；"
                                  "相关门条件由其他指标兜住"),
    }
    if extra:
        entry.update(extra)
    return entry


# ---------------------------------------------------------------------- #
# 黄金集装载（fail-closed 校验）
# ---------------------------------------------------------------------- #

def load_golden_set(path) -> dict:
    if not isinstance(path, str) or not path.strip():
        raise NotConnected("f88_golden_path_required")
    if not os.path.isfile(path):
        raise NotConnected("f88_golden_file_missing:" + path)
    try:
        with open(path, "r", encoding="utf-8-sig") as handle:
            golden = json.load(handle)
    except (OSError, json.JSONDecodeError) as exc:
        raise NotConnected("f88_golden_not_loadable:" + type(exc).__name__) from None
    if not isinstance(golden, dict) or golden.get("schema") != GOLDEN_SCHEMA:
        raise NotConnected("f88_golden_schema_mismatch:%s"
                           % (golden.get("schema") if isinstance(golden, dict)
                              else type(golden).__name__))
    items = golden.get("items")
    if not isinstance(items, list) or not items:
        raise NotConnected("f88_golden_items_required")
    seen: set = set()
    for item in items:
        if not isinstance(item, dict):
            raise NotConnected("f88_golden_item_not_dict")
        item_id = item.get("id")
        if not isinstance(item_id, str) or not item_id:
            raise NotConnected("f88_golden_item_id_required")
        if item_id in seen:
            raise NotConnected("f88_golden_item_id_duplicate:" + item_id)
        seen.add(item_id)
        if item.get("set") not in ("answerable", "refuse"):
            raise NotConnected("f88_golden_set_invalid:" + item_id)
        if not isinstance(item.get("citation"), str) or not item["citation"]:
            raise NotConnected("f88_golden_citation_required:" + item_id)
        if not isinstance(item.get("as_of"), str) or not DATE8_RE.match(
                item["as_of"]):
            raise NotConnected("f88_golden_as_of_malformed:" + item_id)
        for key in ("must_cite", "must_not_cite", "expected_excerpts"):
            value = item.get(key)
            if not isinstance(value, list) or not all(
                    isinstance(v, (int, str)) for v in value):
                raise NotConnected(
                    "f88_golden_%s_malformed:%s" % (key, item_id))
    return golden


# ---------------------------------------------------------------------- #
# 受测系统跑批（同源核验面）与控制组（adversarial 退化系统）
# ---------------------------------------------------------------------- #

def run_real(golden: dict, config: dict) -> list:
    """真跑：逐条经 F70 同源核验面（citation.verify 同一核心）。

    刻意经 citation_verifier.citation_call('citation.verify', …)——与
    legal_entry 桥分发的冻结方法路径同源，不复制第二核验实现。
    """
    import citation_verifier

    records = []
    for item in golden["items"]:
        response = citation_verifier.citation_call(
            "citation.verify",
            {"citation": item["citation"], "as_of": item["as_of"]},
            config)
        response["golden_id"] = item["id"]
        records.append(response)
    return records


def _control_refuse_all(item: dict) -> dict:
    """退化系统①：永远拒答（一切未知、绝不肯定）。"""
    return {
        "golden_id": item["id"],
        "citation_text": item["citation"],
        "status": "未知",
        "code": "CONTROL_REFUSE_ALL",
        "decision": "UNKNOWN",
        "identifier": None,
        "article_number": None,
        "verified_scoped": False,
        "support": None,
    }


def _control_answer_all(item: dict) -> dict:
    """退化系统②：永远作答（一切现行、全肯定、回读照抄期望片段）。

    条文号经确定性解析器从引用串取真值（撒谎系统也会引用具体条文，
    这才让 false_citation_rate 在 must_not_cite 上真实受罚）。自带诱饵
    自报统计 self_reported_hallucination_rate=0.0——评估器必须无视它
    （核验器统计不冒独立幻觉率），照实对黄金标签报假断言率。
    """
    import citation_verifier

    parsed = citation_verifier.parse_citations(item["citation"])
    article = parsed[0].get("article_number") if parsed else None
    echo = "。".join(item.get("expected_excerpts") or []) or "合成回读占位。"
    return {
        "golden_id": item["id"],
        "citation_text": item["citation"],
        "status": STATUS_CURRENT,
        "code": "CONTROL_ANSWER_ALL",
        "decision": "ALLOWED",
        "identifier": "1.2.156.3005.6-" + "9" * 31,
        "article_number": article,
        "verified_scoped": True,
        "support": {"article_text": echo, "article_located": True,
                    "quote_in_article": True},
        "self_reported_hallucination_rate": 0.0,
        "self_reported_stats_note": "诱饵：核验器自报统计（评估器必须无视）",
    }


_CONTROL_BUILDERS = {"refuse_all": _control_refuse_all,
                     "answer_all": _control_answer_all}


def run_control(golden: dict, control: str) -> list:
    if control not in _CONTROL_BUILDERS:
        raise NotConnected("f88_control_unknown:" + str(control))
    return [_CONTROL_BUILDERS[control](item) for item in golden["items"]]


# ---------------------------------------------------------------------- #
# 双集合评估（对黄金标签逐条对账）
# ---------------------------------------------------------------------- #

def evaluate_records(records: list, golden: dict) -> dict:
    items = {item["id"]: item for item in golden["items"]}
    ids = [record.get("golden_id") for record in records]
    if sorted(ids) != sorted(items):
        raise NotConnected("f88_records_golden_mismatch")
    answerable = [it for it in golden["items"] if it["set"] == "answerable"]
    refuse = [it for it in golden["items"] if it["set"] == "refuse"]
    common = len(answerable) + len(refuse)

    domain_hits = 0
    affirmed_total = 0
    halluc_hits = 0
    cite_hits = 0
    cite_total = 0
    false_hits = 0
    excerpt_hits = 0
    excerpt_total = 0
    status_hits = 0
    ans_ok = 0
    ref_ok = 0
    by_item = []
    for record in records:
        item = items[record["golden_id"]]
        affirmed = record.get("verified_scoped") is True
        status = record.get("status")
        identifier = record.get("identifier")
        article = record.get("article_number")
        text = ((record.get("support") or {}).get("article_text") or "")
        entry = {"id": item["id"], "set": item["set"],
                 "status": status, "expected_status": item["expected_status"],
                 "affirmed": affirmed}
        # domain_route（路由＝定位到黄金期望版本；虚构题期望 None）
        routed = (identifier or None) == (item.get("expected_wjbs") or None)
        if routed:
            domain_hits += 1
        entry["routed"] = routed
        # 假断言（只看黄金集合归属＋affirmed；不读任何自报字段）
        if affirmed:
            affirmed_total += 1
            if item["set"] == "refuse":
                halluc_hits += 1
        # 可答集：must_cite 命中（cited＝被肯定的条文号）
        if item["set"] == "answerable":
            must = list(item.get("must_cite") or [])
            cite_total += len(must)
            hit = 1 if (affirmed and article is not None
                        and article in must) else 0
            cite_hits += hit
            entry["must_cite_hit"] = bool(hit)
            if status == STATUS_CURRENT and affirmed:
                ans_ok += 1
                entry["answerable_correct"] = True
            else:
                entry["answerable_correct"] = False
        else:
            must_not = set(item.get("must_not_cite") or [])
            violated = affirmed and article is not None and article in must_not
            if violated:
                false_hits += 1
            entry["false_citation_violation"] = bool(violated)
            entry["refuse_correct"] = (not affirmed
                                       and status == item["expected_status"])
            if entry["refuse_correct"]:
                ref_ok += 1
        # 引用回读片段
        hits = [e for e in (item.get("expected_excerpts") or [])
                if isinstance(e, str) and e in text]
        excerpt_total += len(item.get("expected_excerpts") or [])
        excerpt_hits += len(hits)
        entry["excerpt_hits"] = "%d/%d" % (
            len(hits), len(item.get("expected_excerpts") or []))
        if status == item["expected_status"]:
            status_hits += 1
        by_item.append(entry)

    six = {
        "domain_route_accuracy": _metric_entry(
            "domain_route_accuracy", ">=", 0.90,
            _rate(domain_hits, common), domain_hits, common),
        "hallucination_rate": _metric_entry(
            "hallucination_rate", "<=", 0.10,
            _rate(halluc_hits, affirmed_total), halluc_hits, affirmed_total,
            {"basis": "golden_labels_only_verifier_self_stats_ignored"}),
        "citation_accuracy": _metric_entry(
            "citation_accuracy", ">=", 0.80,
            _rate(cite_hits, cite_total), cite_hits, cite_total),
        "false_citation_rate": _metric_entry(
            "false_citation_rate", "<=", 0.05,
            _rate(false_hits, affirmed_total), false_hits, affirmed_total),
        "excerpt_recall": _metric_entry(
            "excerpt_recall", ">=", 0.60,
            _rate(excerpt_hits, excerpt_total), excerpt_hits, excerpt_total),
        "status_accuracy": _metric_entry(
            "status_accuracy", ">=", 0.80,
            _rate(status_hits, common), status_hits, common),
    }
    dualset = {
        "answerable_coverage_correct": _metric_entry(
            "answerable_coverage_correct", ">=", 0.90,
            _rate(ans_ok, len(answerable)), ans_ok, len(answerable),
            {"common_denominator": common}),
        "refuse_correct_rejection": _metric_entry(
            "refuse_correct_rejection", ">=", 0.90,
            _rate(ref_ok, len(refuse)), ref_ok, len(refuse),
            {"common_denominator": common}),
        "denominators": {
            "answerable_set": len(answerable),
            "refuse_set": len(refuse),
            "common": common,
        },
        "note": "可答覆盖正确率与应拒正确拒绝率共同报告分母（集合分母＋"
                "双集合合计）；永远拒答→可答覆盖=0 不过门；双集合为新增"
                "报告面，不替删原六指标",
    }
    return {
        "schema": REPORT_SCHEMA,
        "metrics_source": METRICS_SOURCE,
        "six_metrics": six,
        "dualset": dualset,
        "excluded_from_source_table": EXCLUDED_FROM_SOURCE_TABLE,
        "golden": {"seed": golden.get("seed"),
                   "fixed_as_of": golden.get("fixed_as_of"),
                   "counts": golden.get("counts")},
        "by_item": by_item,
    }


# ---------------------------------------------------------------------- #
# CI 门（judicex 阈值门语义：任一阈值不达→非零退出）
# ---------------------------------------------------------------------- #

def gate(report: dict) -> dict:
    failures = [name for name in SIX_METRIC_NAMES
                if not report["six_metrics"][name]["pass"]]
    failures += [spec["name"] for spec in DUALSET_SPECS
                 if not report["dualset"][spec["name"]]["pass"]]
    return {
        "passed": not failures,
        "failures": failures,
        "exit_code": 0 if not failures else 1,
        "policy": "任一阈值不达→非零退出（judicex gold_runner CI 门语义；"
                  "ci95 区间入证据不替代阈值判定）",
        "gate_conditions": (
            [dict(spec) for spec in SIX_METRIC_SPECS]
            + [dict(spec) for spec in DUALSET_SPECS]),
    }


# ---------------------------------------------------------------------- #
# legal_entry 冻结方法组分发（f88.*）
# ---------------------------------------------------------------------- #

def f88_call(method: str, args: dict, config: dict) -> dict:
    if method == "f88.evaluate":
        golden = load_golden_set(args.get("golden_path"))
        records = run_real(golden, config)
        report = evaluate_records(records, golden)
        report["runner"] = "real:citation_verifier(F70 同源核验面)"
        report["gate"] = gate(report)
        return report
    if method == "f88.control_evaluate":
        control = args.get("control")
        if control not in CONTROLS:
            raise NotConnected(
                "f88_control_unknown:%s;see:%s" % (control, ",".join(CONTROLS)))
        golden = load_golden_set(args.get("golden_path"))
        records = run_control(golden, control)
        report = evaluate_records(records, golden)
        report["runner"] = "control:" + control
        report["control_note"] = (
            "adversarial 退化系统（永远拒答/永远作答）：用于证明双集合门"
            "拒绝两个退化策略——永远拒答不通过、全答也不通过；"
            "answer_all 自报统计为诱饵，评估照实对黄金标签报告")
        report["gate"] = gate(report)
        return report
    raise NotConnected("f88_method_not_in_frozen_list:" + method)


# ---------------------------------------------------------------------- #
# CI 门 CLI：python -X utf8 f88_dualset_ci.py --golden <黄金集> …
# ---------------------------------------------------------------------- #

def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(
        description="F88 双集合评估＋六指标 CI 门（exit 0=门过；1=阈值不达；"
                    "3=未连接具名）")
    parser.add_argument("--golden", required=True,
                        help="f88_golden_set.json 路径（e12_corpus_gen "
                             "--citations 产物）")
    parser.add_argument("--codices-import-path", required=True,
                        help="E22 冻结面 v1.1 目录（含 lccc_consumer.py）")
    parser.add_argument("--codices-formal-root", required=True,
                        help="法源正式目录（合成面 codices_face 或真实发布件）")
    parser.add_argument("--control", choices=CONTROLS, default=None,
                        help="adversarial 控制组（永远拒答/永远作答）——"
                             "证明双集合门拒绝退化策略")
    args = parser.parse_args(argv)

    config = {"codices_import_path": args.codices_import_path,
              "codices_formal_root": args.codices_formal_root}
    try:
        if args.control:
            report = f88_call("f88.control_evaluate",
                              {"golden_path": args.golden,
                               "control": args.control}, config)
        else:
            report = f88_call("f88.evaluate", {"golden_path": args.golden},
                              config)
    except NotConnected as exc:
        print(json.dumps({"status": "NOT_CONNECTED", "code": str(exc)},
                         ensure_ascii=False))
        return 3
    print(json.dumps(report, ensure_ascii=False, default=str))
    return report["gate"]["exit_code"]


if __name__ == "__main__":
    raise SystemExit(main())

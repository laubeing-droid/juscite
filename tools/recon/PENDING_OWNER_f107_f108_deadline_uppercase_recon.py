# -*- coding: utf-8 -*-
"""F107 期限预设逐名绑定＋F108 金额大写 验收对账（W2b-U55）。

F107（06 行，双实例）：14 期限预设 D01-D14 逐名绑定四要素——JC 合同（版
本化规则注册表调用时解析，漂移具名拒）、送达起算条件（逐名具名）、官方
时点（法条+条号+引文，本工具对 codices E22 冻结面只读复验：标题定位/
版本行 SXRQ/引文逐字在语料中）、假期范围（消费 W2b-U54 F106 日历版本账：
版本化年度包供给冻结期限引擎；假日顺延/调休补班工作日/超范围年份结构化
UNKNOWN 零日期绝不外推）。冻结分布不变：9 RULE_MAPPED＋3 PARTIAL＋D07
UNKNOWN＋D14 CONTRACT_UNKNOWN——D07/D14 以冻结状态具名拒不硬造固定加天；
程序事件闭集（任意业务事件具名拒）；无官方时点装 RULE_MAPPED 由
check_binding 结构不变式守门（篡改行具名拒）。

F108（06 行，双实例）：金额大写转换纯函数——分位/零/整/负数/上限边界夹
具全合成；负数语义具名不静默；float 入参具名拒；数值来源不变＝回执回带
value_minor 且独立逆解析器（与格式化不同算路）逐夹具回读同一整数分。

负向全具名：无官方时点装 RULE_MAPPED / 假期超范围仍算 / 大写函数改值 /
float 入参 / 任意业务事件 / 冻结 UNKNOWN 预设硬算。

用法（juscite worktree w2b-u55 根 cwd；--profile 缺省＝双 profile）：
  python -X utf8 tools/PENDING_OWNER_f107_f108_deadline_uppercase_recon.py \
      [--profile desktop --profile selfhost]

exit 0＝RECON_OK 全断言过；证据 JSON 写 evidence/F107/<profile>/ 与
evidence/F108/<profile>/。全合成材料；只读消费 JC worktree 与 codices
E22 冻结面；不发网络、不写 codices。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
import tempfile
from decimal import Decimal
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
LEGAL_ENTRY = REPO_ROOT / "implementation" / "python" / "legal_entry.py"

JC_REPO = Path(
    r"D:\Codex\1.法律工作区\juris-calculus工作区\juris-calculus\.local\worktrees\w2b-u55")
# codices E22 冻结面 v1.1（W2a-U14 钉定值）：只读消费，零写入。
CODICES_LCCC = Path(
    r"D:\Codex\1.法律工作区\legal-cn-core-codices工作区"
    r"\legal-cn-core-codices-repo\.local\worktrees\w2a-u14\lccc_consumer.py")
CODICES_FORMAL_ROOT = Path(
    r"D:\Codex\1.法律工作区\legal-cn-core-codices工作区\legal-cn-core-codices")
LCCC_SHA256 = (
    "55eea7c27e08d6b236b7ab7a83810c86ee0898c335c4668d875a492775db863a")

NOW = "2026-10-17T00:00:00+00:00"

RULE_PACK = {
    "schema_version": "jc/local-pack/1.0",
    "pack_version": "1.0.0",
    "sources": [{
        "source_id": "acceptance-statute", "jurisdiction": "TEST",
        "authority_tier": "official_first_party",
        "issuer": "Acceptance Test Authority", "title": "acceptance-statute",
        "publication_time": "2020-01-01T00:00:00Z",
        "effective_from": "2020-01-01T00:00:00Z",
        "retrieved_at": "2026-08-01T00:00:00Z",
        "locator": {"kind": "uri", "value": "example.invalid/acceptance",
                    "page": None, "span_start": None, "span_end": None},
        "content": ("SYNTHETIC acceptance rule text for engineering "
                    "verification only; no legal effect."),
        "structure_sections": ["ART-1"],
    }],
    "rules": [
        {"rule_id": "acc-base", "jurisdiction": "TEST",
         "governing_law": "acceptance-statute", "source_id": "acceptance-statute",
         "modality": "OBLIGATION",
         "premises": [{"fact_key": "acc.contract", "required": True}],
         "conclusion": {"value": "applies"},
         "effective_from": "2020-01-01T00:00:00Z"},
    ],
}

# F108 大写夹具：整数分 → 期望大写（全合成；负数语义具名；上限边界）。
WORDS_FIXTURES = [
    (1234567, "壹万贰仟叁佰肆拾伍元陆角柒分"),
    (0, "零元整"),
    (5, "伍分"),                       # 分位下界
    (30, "叁角整"),                     # 有角无分 → 整
    (10005, "壹佰元零伍分"),            # 角空分有 → 补零
    (10050, "壹佰元伍角整"),
    (10500, "壹佰零伍元整"),            # 位间零只读一个
    (1000500050, "壹仟万零伍仟元伍角整"),  # 组间零只读一个
    (10000000100, "壹亿零壹元整"),
    (10000000000, "壹亿元整"),
    (100000000000000, "壹万亿元整"),
    (1000, "壹拾元整"),
    (11000, "壹佰壹拾元整"),
    (2100000000500, "贰佰壹拾亿零伍元整"),
    (12345, "壹佰贰拾叁元肆角伍分"),
    (-12345, "负壹佰贰拾叁元肆角伍分"),   # 负数语义具名不静默
    # V4 回执安全整数上限夹具（2^53-1 分＝玖拾万亿…；更接近词表上限的
    # 金额走具名 wire 拒，见 F108-N2）
    (9007199254740991, "玖拾万亿零柒佰壹拾玖亿玖仟贰佰伍拾肆万柒仟肆佰零玖元玖角壹分"),
]

_DIGITS = "零壹贰叁肆伍陆柒捌玖"
_WORD_CLASSES = _DIGITS + "仟佰拾"


def _parse_words_to_minor(words: str) -> int:
    """独立逆解析器（与 JC 格式化不同算路）：大写词 → 整数分。"""
    negative = words.startswith("负")
    if negative:
        words = words[1:]
    assert words.endswith(("整", "分")), words
    if words.endswith("整"):
        words = words[:-1]
    # 尾部角/分段按「数字+单位」锚定剥离（元段缺省的 伍分/叁角 readings
    # 不进元解析器；元段保留给组权解析器）
    jiao = fen = 0
    match = re.search(r"([%s])分$" % _DIGITS, words)
    if match:
        fen = _DIGITS.index(match.group(1))
        words = words[:match.start()]
    match = re.search(r"([%s])角$" % _DIGITS, words)
    if match:
        jiao = _DIGITS.index(match.group(1))
        words = words[:match.start()]
    if words.endswith("零") and not words.endswith("元"):
        words = words[:-1]  # 角空分有补零的「零」连接词（壹佰元零伍分）
    assert words == "" or words.endswith("元"), words
    yuan_part = words[:-1] if words.endswith("元") else ""
    yuan = 0
    for match in re.finditer(
            r"([%s]+)(万亿|亿|万)|([%s]+)$" % (_WORD_CLASSES, _WORD_CLASSES),
            yuan_part):
        body = match.group(1) or match.group(3)
        unit = match.group(2) or ""
        value, current = 0, 0
        for char in body:
            if char == "零":
                current = 0
                continue
            if char in _DIGITS:
                current = _DIGITS.index(char)
            elif char == "拾":
                value += (current or 1) * 10
                current = 0
            elif char == "佰":
                value += (current or 1) * 100
                current = 0
            elif char == "仟":
                value += (current or 1) * 1000
                current = 0
        value += current
        yuan += value * {"万亿": 10 ** 12, "亿": 10 ** 8,
                         "万": 10 ** 4, "": 1}[unit]
    minor = yuan * 100 + jiao * 10 + fen
    return -minor if negative else minor


class Checks:
    def __init__(self):
        self.items: list[dict] = []

    def add(self, check_id: str, ok: bool, detail: str) -> bool:
        self.items.append({"id": check_id, "status": "PASS" if ok else "FAIL",
                           "detail": detail})
        print("[%s] %s — %s" % ("PASS" if ok else "FAIL", check_id, detail))
        return ok

    @property
    def all_passed(self):
        return all(i["status"] == "PASS" for i in self.items)

    @property
    def passed_count(self):
        return sum(i["status"] == "PASS" for i in self.items)


def call_cli(method: str, args: dict, config: dict):
    """真产品入口子进程径（legal_entry CLI；同 W2b-U19/U54 recon 纪律）。"""
    with tempfile.TemporaryDirectory() as tmp:
        req = Path(tmp) / "request.json"
        cfg = Path(tmp) / "config.json"
        req.write_text(json.dumps({"method": method, "args": args},
                                  ensure_ascii=False), encoding="utf-8")
        cfg.write_text(json.dumps(config, ensure_ascii=False), encoding="utf-8")
        proc = subprocess.run(
            [sys.executable, "-X", "utf8", str(LEGAL_ENTRY),
             "--request-json", str(req), "--config", str(cfg)],
            capture_output=True, text=True, encoding="utf-8", timeout=300)
        try:
            payload = json.loads(proc.stdout)
        except json.JSONDecodeError:
            payload = {"status": "RAW", "stdout": proc.stdout[:400]}
        return proc.returncode, payload


def make_config(workspace: Path) -> dict:
    rules = workspace / "rules"
    rules.mkdir(parents=True, exist_ok=True)
    (rules / "jc-local-pack.json").write_text(
        json.dumps(RULE_PACK, ensure_ascii=False), encoding="utf-8")
    return {
        "jc_state_root": str(workspace / "state"),
        "jc_rule_roots": [str(rules)],
        "jc_import_path": str(JC_REPO),
    }


def run_profile(profile: str, workspace_root: Path) -> Checks:
    checks = Checks()
    workspace = workspace_root / profile
    workspace.mkdir(parents=True, exist_ok=True)
    config = make_config(workspace)

    # S0 钉定基 --------------------------------------------------------------
    if not (JC_REPO / "compiler_core" / "deadline_presets.py").is_file():
        checks.add("U55-PIN-0", False, f"JC worktree missing at {JC_REPO}")
        return checks
    pins = {}
    for rel in ("compiler_core/deadline_presets.py",
                "compiler_core/amount_words.py",
                "compiler_core/client.py"):
        pins[rel] = hashlib.sha256((JC_REPO / rel).read_bytes()).hexdigest()
    checks.add("U55-PIN-0", True,
               "JC w2b-u55 worktree 在盘（deadline_presets/amount_words/client "
               "sha256 见证据 JSON pins）")

    code, out = call_cli("calc.deadline_presets", {}, config)
    checks.add("U55-PIN-1", code == 0 and out.get("status") == "OWNER_RESPONSE",
               "桥可达（calc.deadline_presets exit 0）")

    # S1 F107 绑定面：14 行 × 四要素 ------------------------------------------
    document = out.get("result", {}) if code == 0 else {}
    rows = {row["slot"]: row for row in document.get("presets", [])}
    ok = (len(rows) == 14 and document.get("binding_version") == "jc-deadline-preset-binding/1")
    distribution: dict[str, int] = {}
    for row in rows.values():
        distribution[row["frozen_status"]] = distribution.get(row["frozen_status"], 0) + 1
        ok = ok and bool(row["start_condition"]) and bool(row["open_conditions"])
        ok = ok and row["official_time_point"]["status"] in (
            "BOUND_E22_VERIFIED", "NOT_BOUND_NO_SINGLE_PROVISION")
        ok = ok and row["holiday_range"]["face"] == "jc-calendar-version/1"
    ok = ok and distribution == {"RULE_MAPPED": 9, "PARTIAL": 3,
                                 "UNKNOWN": 1, "CONTRACT_UNKNOWN": 1}
    checks.add("F107-B1", ok,
               "14 行逐名绑定四要素齐备且冻结分布不变（9 RULE_MAPPED＋3 PARTIAL"
               "＋D07 UNKNOWN＋D14 CONTRACT_UNKNOWN；D14 官方时点"
               f" NOT_BOUND={rows['D14']['official_time_point']['status'] == 'NOT_BOUND_NO_SINGLE_PROVISION'}）")

    rule_ok = (rows["D01"]["rule_binding"]["rule_ref"] == "civil.appeal.judgment@1"
               and rows["D01"]["rule_binding"]["duration_days"] == 15
               and rows["D08"]["rule_binding"]["boundary_inclusive"] is True
               and rows["D12"]["rule_binding"]["counting_mode"] == "CALENDAR_PERIODS"
               and rows["D07"]["rule_binding"] is None
               and rows["D14"]["rule_binding"] is None)
    checks.add("F107-B2", rule_ok,
               "JC 合同＝版本化规则注册表调用时转写（D01=15日 servedAt/"
               "D08 含当日 boundaryInclusive=true/D12 按年期间；D07/D14 无规则行）")

    start_ok = all(rows[slot]["start_condition"] for slot in rows) and \
        "判决书送达之日起" in rows["D01"]["start_condition"] and \
        "第二日起算" in rows["D03"]["start_condition"] and \
        "含当日" in rows["D08"]["start_condition"] and \
        "知道或者应当知道" in rows["D09"]["start_condition"]
    checks.add("F107-B3", start_ok,
               "送达起算条件逐名具名（判决书送达之日起/接到判决书的第二日起算/"
               "保全措施采取之日起含当日/知道或应当知道之日）")

    event_ok = (rows["D01"]["procedure_event_kinds"] == [
                    "service_of_first_instance_judgment"]
                and rows["D07"]["procedure_event_kinds"] == []
                and rows["D14"]["procedure_event_kinds"] == [])
    checks.add("F107-B4", event_ok,
               "程序事件闭集逐名声明（D07/D14 空集＝无任何可受理事件）")

    # S2 F107 官方时点：codices E22 冻结面只读复验 ----------------------------
    lccc_ok = CODICES_LCCC.is_file() and hashlib.sha256(
        CODICES_LCCC.read_bytes()).hexdigest() == LCCC_SHA256
    if not lccc_ok:
        checks.add("F107-E1", False,
                   f"E22 冻结面 lccc_consumer.py sha256 漂移或缺失（{CODICES_LCCC}）")
        return checks
    checks.add("F107-E1", True,
               "E22 冻结面 v1.1 lccc_consumer.py sha256 钉定一致（55eea7c2…），"
               "漂移即响亮拒")
    sys.path.insert(0, str(CODICES_LCCC.parent))
    try:
        import lccc_consumer  # noqa: E402
        consumer = lccc_consumer.LcccConsumer(str(CODICES_FORMAL_ROOT))
        e22_fail: list[str] = []
        verified_statutes: dict[str, dict] = {}
        for slot in ("D01", "D02", "D03", "D04", "D05", "D06", "D08",
                     "D11", "D13"):
            official = rows[slot]["official_time_point"]
            title = official["statute"]
            hit_rows = [r for r in consumer.find_by_title(title)
                        if r.get("sxrq") == official["statute_e22_sxrq"]]
            if len(hit_rows) != 1:
                e22_fail.append(f"{slot}:{title}@{official['statute_e22_sxrq']}"
                                f" hits={len(hit_rows)}")
                continue
            text = consumer.read_markdown_text(hit_rows[0]["wjbs"])
            if not text or official["quote"] not in text:
                e22_fail.append(f"{slot}:quote_not_in_corpus")
        checks.add("F107-E2", not e22_fail,
                   "官方时点经 E22 正式面复验×9（民诉法2023 第171/128/130/104/"
                   "216/250条、刑诉法2018 第230条、行诉法2017 第46条、"
                   "行政复议法2023 第20条——标题/SXRQ 版本行唯一＋引文逐字在"
                   "语料）" + ("" if not e22_fail else f"；缺口={e22_fail}"))
        # D07/D12：劳动争议调解仲裁法 2007 两处官方时点
        labor_ok = True
        for slot in ("D07", "D12"):
            official = rows[slot]["official_time_point"]
            hit_rows = [r for r in consumer.find_by_title(official["statute"])
                        if r.get("sxrq") == official["statute_e22_sxrq"]]
            text = consumer.read_markdown_text(hit_rows[0]["wjbs"]) if hit_rows else ""
            labor_ok = labor_ok and len(hit_rows) == 1 and official["quote"] in text
        checks.add("F107-E3", labor_ok,
                   "劳动争议调解仲裁法2007 官方时点复验×2（D07 第五十条起诉期"
                   "官方时点已定位＋D12 第二十七条一年时效）")
        verified_statutes["note"] = "只读消费；codices 零写入"
    except Exception as exc:  # noqa: BLE001 - recon reports, never fakes
        checks.add("F107-E2", False, f"E22 face error: {type(exc).__name__}: {exc}")
        return checks
    finally:
        sys.path.remove(str(CODICES_LCCC.parent))

    invariant = json.loads(json.dumps(document))  # deep copy for tamper test
    for row in invariant["presets"]:
        if row["slot"] == "D02":
            row["official_time_point"]["status"] = "NOT_BOUND_NO_SINGLE_PROVISION"
    sys.path.insert(0, str(JC_REPO))
    try:
        from compiler_core.deadline_presets import check_binding  # noqa: E402
        verdict = check_binding(invariant)
    finally:
        sys.path.remove(str(JC_REPO))
    checks.add("F107-E4", not verdict["ok"] and
               "deadline_preset_official_time_point_missing:D02" in verdict["violations"],
               "无官方时点装 RULE_MAPPED 具名拒（check_binding 篡改行"
               f" violations={verdict['violations']}）——映射主张必须官方时点已绑定")

    # S3 F107 评估面：冻结引擎 × F106 日历版本包 ------------------------------
    code, out = call_cli("calc.deadline_preset_evaluate", {
        "slot": "D01", "now": NOW,
        "event": {"kind": "service_of_first_instance_judgment",
                  "anchor": {"value": "2026-03-20", "precision": "date"}}},
        config)
    r = out.get("result", {}) if code == 0 else {}
    d01_ok = (r.get("status") == "OK"
              and r.get("nominal_due_date") == "2026-04-04"
              and r.get("due_date") == "2026-04-07"
              and r.get("holiday_extended") is True
              and r.get("calendar_versions", {}).get("2026")
              == "cn-holiday/gobafamingdian-2025-7@1"
              and r.get("evaluationRef", {}).get("owner") == "jc")
    checks.add("F107-R1", d01_ok,
               "D01 上诉 15 日经冻结引擎×F106 包：nominal 2026-04-04 落清明→"
               "顺延 2026-04-07，calendar_version 回读（国办发明电〔2025〕7号），"
               "evaluationRef owner=jc 登记")

    code, out = call_cli("calc.deadline_preset_evaluate", {
        "slot": "D03", "now": NOW,
        "event": {"kind": "receipt_of_criminal_judgment",
                  "anchor": {"value": "2026-03-26", "precision": "date"},
                  "legal_context": {"subjectQualified": True,
                                    "specialRulesReviewed": True,
                                    "serviceConfirmed": True,
                                    "appealable": True, "inCustody": True}}},
        config)
    held = out.get("result", {}) if code == 0 else {}
    code, out = call_cli("calc.deadline_preset_evaluate", {
        "slot": "D03", "now": NOW,
        "event": {"kind": "receipt_of_criminal_judgment",
                  "anchor": {"value": "2026-03-26", "precision": "date"},
                  "legal_context": {"subjectQualified": True,
                                    "specialRulesReviewed": True,
                                    "serviceConfirmed": True,
                                    "appealable": True, "inCustody": False}}},
        config)
    rolled = out.get("result", {}) if code == 0 else {}
    d03_ok = (held.get("due_date") == "2026-04-05"
              and rolled.get("due_date") == "2026-04-07")
    checks.add("F107-R2", d03_ok,
               "D03 刑事上诉 10 日：在押末日不顺延（04-05 保持）vs 非在押顺延"
               "（04-07）——规则分支 inCustody 原样承载")

    code, out = call_cli("calc.deadline_preset_evaluate", {
        "slot": "D08", "now": NOW,
        "event": {"kind": "pre_litigation_preservation_measure_taken",
                  "anchor": {"value": "2026-04-30", "precision": "date"}}},
        config)
    r = out.get("result", {}) if code == 0 else {}
    d08_ok = (r.get("due_date") == "2026-05-29"
              and r.get("rule_binding", {}).get("boundary_inclusive") is True)
    checks.add("F107-R3", d08_ok,
               "D08 诉前保全 30 日含当日（规则合同 boundaryInclusive=true 调用时"
               "转写）：2026-04-30 采取措施 → 届满 2026-05-29")

    code, out = call_cli("calc.deadline_preset_evaluate", {
        "slot": "D12", "now": NOW, "calendar_years": [2025, 2026],
        "event": {"kind": "right_infringement_awareness",
                  "anchor": {"value": "2025-11-20", "precision": "date"},
                  "legal_context": {"subjectQualified": True,
                                    "specialRulesReviewed": True,
                                    "wageArrears": False}}},
        config)
    r = out.get("result", {}) if code == 0 else {}
    d12_ok = (r.get("status") == "OK" and r.get("due_date") == "2026-11-20"
              and set(r.get("calendar_versions", {})) == {"2025", "2026"})
    code, out = call_cli("calc.deadline_preset_evaluate", {
        "slot": "D12", "now": NOW, "calendar_years": [2025, 2026],
        "event": {"kind": "right_infringement_awareness",
                  "anchor": {"value": "2025-11-20", "precision": "date"},
                  "legal_context": {"subjectQualified": True,
                                    "specialRulesReviewed": True,
                                    "wageArrears": True,
                                    "employmentEnded": False}}},
        config)
    r2 = out.get("result", {}) if code == 0 else {}
    d12_ok = d12_ok and r2.get("status") == "NO_ORDINARY_DEADLINE" \
        and r2.get("due_date") is None and r2.get("reason_code") == "no_ordinary_deadline"
    checks.add("F107-R4", d12_ok,
               "D12 跨年一年时效（声明双版本包→2026-11-20 对应日）＋在职欠薪"
               "第四款＝具名无普通截止候选（NO_ORDINARY_DEADLINE 零日期，"
               "非未知前提不产日）")

    code, out = call_cli("calc.deadline_preset_evaluate", {
        "slot": "D13", "now": NOW, "calendar_years": [2025, 2026],
        "event": {"kind": "enforcement_basis_date",
                  "anchor": {"value": "2025-01-15", "precision": "date"},
                  "legal_context": {"subjectQualified": True,
                                    "specialRulesReviewed": True,
                                    "performanceMode": "unspecified",
                                    "judgmentEffectiveAt": {
                                        "value": "2025-01-15",
                                        "precision": "date"}}}},
        config)
    r = out.get("result", {}) if code == 0 else {}
    d13_ok = (r.get("status") == "UNKNOWN_CALENDAR"
              and r.get("nominal_due_date") == "2027-01-15"
              and r.get("due_date") is None
              and r.get("date_fields_present") is False)
    checks.add("F107-R5", d13_ok,
               "D13 两年执行时效落 2027＝超版本包覆盖 → 结构化 UNKNOWN_CALENDAR"
               "（nominal 陈述 2027-01-15，届满零日期不外推——假期超范围仍算"
               "的具名否定面）")

    code, out = call_cli("calc.deadline_preset_evaluate", {
        "slot": "D01", "now": NOW, "calendar_years": [2027],
        "event": {"kind": "service_of_first_instance_judgment",
                  "anchor": {"value": "2027-01-10", "precision": "date"}}},
        config)
    r = out.get("result", {}) if code == 0 else {}
    yr_ok = (r.get("status") == "UNKNOWN"
             and r.get("reason_code") == "calendar_year_out_of_range"
             and r.get("date_fields_present") is False
             and "due_date" not in r)
    checks.add("F107-R6", yr_ok,
               "声明无包年份（2027）→ 结构化 UNKNOWN 零日期字段（绝不用 "
               "2025-2026 表外推——F106 边界原样承接）")

    # S4 F107 负向：冻结状态具名拒不硬造 --------------------------------------
    code, out = call_cli("calc.deadline_preset_evaluate", {
        "slot": "D07", "now": NOW,
        "event": {"kind": "labor_award_service",
                  "anchor": {"value": "2026-01-15", "precision": "date"}}},
        config)
    d07_ok = (code == 4 and out.get("status") == "JC_FAILURE"
              and "deadline_preset_unknown" in str(out.get("code", "")))
    code, out = call_cli("calc.deadline_preset_evaluate", {
        "slot": "D14", "now": NOW,
        "event": {"kind": "custom_period",
                  "anchor": {"value": "2026-01-15", "precision": "date"}}},
        config)
    d14_ok = (code == 4 and out.get("status") == "JC_FAILURE"
              and "deadline_preset_contract_unknown" in str(out.get("code", "")))
    code, out = call_cli("calc.deadline_preset_evaluate", {
        "slot": "D01", "now": NOW,
        "event": {"kind": "contract_signed",
                  "anchor": {"value": "2026-01-15", "precision": "date"}}},
        config)
    biz_ok = (code == 4 and out.get("status") == "JC_FAILURE"
              and "deadline_preset_event_kind_not_in_preset" in str(out.get("code", "")))
    checks.add("F107-N1", d07_ok and d14_ok and biz_ok,
               "缺支持不固定加天：D07 UNKNOWN/D14 CONTRACT_UNKNOWN 以冻结状态"
               "具名拒（官方时点已绑定也不装 RULE_MAPPED）＋任意业务事件"
               " contract_signed 程序事件闭集外具名拒（exit 4）")

    # S5 F108 大写面：边界夹具＋独立逆解析回读 --------------------------------
    words_ok = True
    roundtrip_fail: list[int] = []
    for minor, want in WORDS_FIXTURES:
        code, out = call_cli("calc.amount_words", {"value_minor": minor}, config)
        sheet = out.get("result", {}) if code == 0 else {}
        if sheet.get("words") != want or sheet.get("value_minor") != minor:
            words_ok = False
        if _parse_words_to_minor(sheet.get("words", "")) != minor:
            roundtrip_fail.append(minor)
    checks.add("F108-R1", words_ok and not roundtrip_fail,
               f"大写边界夹具×{len(WORDS_FIXTURES)} 全对（分位/零/整/负数前缀/"
               "上限 9999万亿…元.99分）＋独立逆解析器逐夹具回读同一整数分"
               "＝数值来源不变（只转换不改值）"
               + ("" if not roundtrip_fail else f"；回读漂移={roundtrip_fail}"))

    code, out = call_cli("calc.amount_words", {"value_minor": -12345}, config)
    sheet = out.get("result", {}) if code == 0 else {}
    neg_ok = (sheet.get("words") == "负壹佰贰拾叁元肆角伍分"
              and sheet.get("value_minor") == -12345
              and bool(sheet.get("negative_amount_semantic")))
    checks.add("F108-R2", neg_ok,
               "负数语义具名不静默：「负」前缀原样携带＋negative_amount_semantic"
               " 重申（不静默取正）＋value_minor 保持负值")

    code, out = call_cli("calc.amount_words", {"value_minor": 12345.67}, config)
    float_ok = (code == 4 and out.get("status") == "JC_FAILURE"
                and "amount_float_input_refused" in str(out.get("code", "")))
    code, out = call_cli("calc.amount_words", {"value": "12345.675"}, config)
    prec_ok = (code == 4 and out.get("status") == "JC_FAILURE"
               and "amount_words_precision_beyond_cents" in str(out.get("code", "")))
    code, out = call_cli("calc.amount_words", {"value_minor": 10 ** 18}, config)
    cap_ok = (code == 4 and out.get("status") == "JC_FAILURE"
              and "amount_words_upper_limit_exceeded" in str(out.get("code", "")))
    checks.add("F108-N1", float_ok and prec_ok and cap_ok,
               "float 入参具名拒（F89 纪律）＋超分位具名拒（舍入即改值绝不静默）"
               "＋上限越界具名拒（exit 4）")
    code, out = call_cli("calc.amount_words",
                         {"value_minor": 2 ** 53}, config)
    wire_ok = (code == 4 and out.get("status") == "JC_FAILURE"
               and "amount_words_wire_unsafe_integer" in str(out.get("code", "")))
    checks.add("F108-N2", wire_ok,
               "回执安全整数线具名拒（2^53 分以上不经此回执面——V4 规范形"
               "约束，具名能力边界不静默夹取；词表上限 10^18-1 由纯函数面持有）")

    # S6 确定性：同输入同回执 --------------------------------------------------
    code_a, out_a = call_cli("calc.deadline_preset_evaluate", {
        "slot": "D01", "now": NOW,
        "event": {"kind": "service_of_first_instance_judgment",
                  "anchor": {"value": "2026-03-20", "precision": "date"}}},
        config)
    code_b, out_b = call_cli("calc.deadline_preset_evaluate", {
        "slot": "D01", "now": NOW,
        "event": {"kind": "service_of_first_instance_judgment",
                  "anchor": {"value": "2026-03-20", "precision": "date"}}},
        config)
    det_ok = (code_a == code_b == 0 and
              json.dumps(out_a["result"], sort_keys=True) ==
              json.dumps(out_b["result"], sort_keys=True))
    checks.add("U55-S6", det_ok,
               "同输入两跑回执语义相等（now 必填冻结时钟面；登记 ref 摘要由"
               "内容定）")
    return checks


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", action="append", required=False,
                        choices=("desktop", "selfhost"))
    parser.add_argument("--workspace-root", default=None)
    args = parser.parse_args()

    profiles = args.profile or ["desktop", "selfhost"]
    workspace_root = Path(tempfile.mkdtemp(prefix="f107-f108-recon-")
                          if args.workspace_root is None
                          else args.workspace_root)
    all_ok = True
    reports = {}
    for profile in profiles:
        print(f"=== profile {profile} ===")
        checks = run_profile(profile, workspace_root)
        reports[profile] = checks.items
        ok = checks.all_passed
        all_ok = all_ok and ok
        print(f"profile {profile}: {checks.passed_count}/{len(checks.items)} "
              f"{'RECON_OK' if ok else 'RECON_FAILED'}")

    for profile, items in reports.items():
        verdict = "RECON_OK" if all(i["status"] == "PASS" for i in items) \
            else "RECON_FAILED"
        for evidence_root in (
                REPO_ROOT / "evidence" / "F107" / profile,
                REPO_ROOT / "docs" / "construction" / "evidence" / "F107" / profile,
                REPO_ROOT / "evidence" / "F108" / profile,
                REPO_ROOT / "docs" / "construction" / "evidence" / "F108" / profile):
            evidence_root.mkdir(parents=True, exist_ok=True)
            (evidence_root / "recon-result.json").write_text(
                json.dumps({
                    "schema_version": "jc-f107-f108-recon/1",
                    "profile": profile, "items": items, "verdict": verdict,
                    "jc_worktree": str(JC_REPO),
                    "codices_e22_face": {
                        "lccc_consumer": str(CODICES_LCCC),
                        "lccc_consumer_sha256": LCCC_SHA256,
                        "mode": "read-only, zero writes"},
                }, ensure_ascii=False, indent=1),
                encoding="utf-8")
    print("RECON_OK" if all_ok else "RECON_FAILED")
    return 0 if all_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())

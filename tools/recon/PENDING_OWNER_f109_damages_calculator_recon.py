# -*- coding: utf-8 -*-
"""F109 赔偿金计算器（人损/交通/工伤）验收对账（W4-U48）。

06:F109（F109-desktop/F109-selfhost 双实例，owner=jc+product，inputs
E21,E22；17 卡 stage「✅v1.5 首批扩充（不进 v1 首批九个）」，
acceptance=人损/交通/工伤地域年度基数与规则前提完整；不拿旧标准或缺值
补 0）。经 P01 JCClient（jc_import_path 指向 JC 仓 w4-u48 worktree＝
基链头 w4-u45@066ad59，四文件 sha256 钉定漂移响亮拒）真跑：

分段：
  S1 registry 十槽冻结（九槽 byte-stable＋v1_5_families 具名 C07 行；
     U01-U03 三 scope gap 不填不动——12号文档§2「不得以 F109 填槽」；
     v1 规则包版本字段不动）
  S2 F109 真算（人损/交通：山东2025 残疾赔偿金 56444×20×0.3＝338664 元、
     江苏2025 死亡赔偿金 75 岁以上按 5 年、年龄走年边界 60/61/74/75；
     工伤：一次性工亡补助金＝全国2025 56502×20＝1,130,040 元、2024=
     54188×20、一次性伤残补助金十级月数表、第64条 60%–300% 封顶保底与
     分位半进位、按月伤残津贴、丧葬补助金 6 个月；浙江第27条 月数表与
     距退休线性递减）
  S3 独立 checker（每张计算书 agreed＋版本串；同输入两跑 JSON 字节相等）
  S4 具名缺口 typed 拒（未装地区/年度 rule_pack_absent——绝不拿旧年度
     标准或他地区值补位；全国行拒用于人损基数（第22条省级口径）；人损
     丧葬费具名缺口；31省一次性补助金不装样子；工资规则前提缺失；float
     入参拒；桥未知方法/未配置 exit 3；C07 pack 注入拒）
  S5 法源钉定（统计基数 4 行全带官方 locator+retrieved＝2026-10-20 直读；
     三部法规经 E22 冻结语料 identifier+source_sha256；浙江递减读法歧义
     转录注记在案）

用法（juscite worktree w4-u48 根 cwd）：
  python -X utf8 tools/recon/PENDING_OWNER_f109_damages_calculator_recon.py \
      --profile desktop --profile selfhost

exit 0＝RECON_OK 全断言过；证据 JSON/MD 写 evidence/F109/<profile>/。
全合成材料；只读消费 JC worktree 与 E22 冻结基线；不发网络。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import tempfile
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
LEGAL_ENTRY = REPO_ROOT / "implementation" / "python" / "legal_entry.py"
EVIDENCE_ROOT = REPO_ROOT / "docs" / "construction" / "evidence"

JC_REPO = Path(
    r"D:\Codex\1.法律工作区\juris-calculus工作区\juris-calculus"
    r"\.local\worktrees\w4-u48")
JC_SHA256 = {
    "compiler_core/damages.py":
        "468084da6b68f2d81d585f273a2b8346ef655da8862ec349514ef175a1da037c",
    "compiler_core/damages_checker.py":
        "4fce8adb6c1d9614aaa78e096b0b3dc0eb41f3ee214c931c8e94c383441fe305",
    "compiler_core/calc_families.py":
        "6d226940e781546a5bd74e965dd9d734057718fd3a4ef6307576c63323ec22c7",
    "compiler_core/calc_checker.py":
        "ac48575611c6eddc13c06c7080c9fc8d9d6954a6b498a9b991b1021bc89c4442",
}

SD, JS, ZJ = "370000", "320000", "330000"
WAGE_SRC = "synthetic-certified-wage-fact"

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

# 官方钉定值（2026-10-20 官方公报直读 / E22 冻结语料逐字）
OFFICIAL = {
    "death_benefit_2025_minor": 113004000,   # 56502 元 × 20
    "death_benefit_2024_minor": 108376000,   # 54188 元 × 20
    "sd_disability_minor": 33866400,         # 56444 × 20 年 × 0.3
    "js_death_75_minor": 34478000,           # 68956 × 5 年
}


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
    """真产品入口子进程径（legal_entry CLI；同 F104 recon 纪律）。"""
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


def expect_calc(checks: Checks, cid: str, payload: dict, config: dict,
                expected: dict):
    code, out = call_cli("calc.damages", {"input": payload}, config)
    ok = code == 0 and out.get("status") == "OWNER_RESPONSE"
    if ok:
        for key, value in expected.items():
            if out["result"].get(key) != value:
                ok = False
                break
    checks.add(cid, ok,
               f"C07 {json.dumps(expected, ensure_ascii=False)} -> exit {code} "
               + (json.dumps({k: out['result'].get(k) for k in expected},
                             ensure_ascii=False) if out.get('result') else out.get('status', '')))
    return out


def expect_typed_failure(checks: Checks, cid: str, payload: dict,
                         config: dict, code_fragment: str):
    code, out = call_cli("calc.damages", {"input": payload}, config)
    ok = (code == 4 and out.get("status") == "JC_FAILURE"
          and code_fragment in str(out.get("code", "")))
    checks.add(cid, ok, f"typed refusal {code_fragment} -> exit {code} "
                        f"{str(out.get('code', out.get('status', '')))[:140]}")


def run_profile(profile: str, workspace_root: Path) -> Checks:
    checks = Checks()
    workspace = workspace_root / profile
    workspace.mkdir(parents=True, exist_ok=True)
    config = make_config(workspace)

    # S1 registry ten-slot freeze --------------------------------------------
    if not (JC_REPO / "compiler_core" / "damages.py").is_file():
        checks.add("F109-PIN-0", False, f"JC worktree missing at {JC_REPO}")
        return checks
    pins_ok = all(
        hashlib.sha256((JC_REPO / rel).read_bytes()).hexdigest() == want
        for rel, want in JC_SHA256.items())
    checks.add("F109-PIN-0", pins_ok,
               "JC w4-u48 worktree sha256 四钉定（damages/damages_checker/calc_families/calc_checker）")

    code, out = call_cli("calc.registry", {}, config)
    reg = out.get("result", {}) if out.get("status") == "OWNER_RESPONSE" else {}
    slots = [r.get("slot") for r in reg.get("nine_families", [])]
    checks.add("F109-R1", code == 0 and slots ==
               ["C01", "C02", "C03", "C04", "C05", "C06", "U01", "U02", "U03"],
               f"九槽冻结 byte-stable slots={slots}")
    v15 = reg.get("v1_5_families", [])
    c07 = v15[0] if len(v15) == 1 else {}
    checks.add("F109-R2", c07.get("slot") == "C07"
               and c07.get("zh_name") == "赔偿金"
               and c07.get("status") == "SUPPORTED_V1_5_BATCH"
               and "不进 v1 首批九个" in str(c07.get("stage_note", ""))
               and "不填 U01-U03 scope gap" in str(c07.get("stage_note", "")),
               f"C07 具名第十槽（v1.5 首批扩充）={json.dumps({k: c07.get(k) for k in ('slot', 'zh_name', 'status')}, ensure_ascii=False)}")
    gaps_ok = all(r.get("zh_name") is None and r.get("public_entry") is None
                  for r in reg.get("nine_families", [])
                  if r.get("slot", "").startswith("U"))
    packs_ok = reg.get("rule_packs") == {
        "C03": "cn-court-fee/sc-481-2007@1",
        "C04": "cn-preservation-fee/sc-481-2007@1",
        "C05": "cn-lawyer-contingency/sft-2021-87@1",
        "C06": "cietac/2024@1"}
    checks.add("F109-R3", gaps_ok and packs_ok
               and "9槽=6具名域+3具名scope gap" in reg.get("denominator_note", ""),
               "U01-U03 三 gap 不填不动（12号文档§2）；v1 规则包版本字段不动；分母注记扩十槽")

    # S2 real calculations -----------------------------------------------------
    expect_calc(checks, "F109-PI-1",
                {"domain": "personal_injury", "item": "disability_compensation",
                 "region": SD, "year": 2025, "age": 45,
                 "disability_index": "0.3"}, config,
                {"amount_minor": OFFICIAL["sd_disability_minor"],
                 "amount": "338664"})
    expect_calc(checks, "F109-PI-2",
                {"domain": "traffic", "item": "death_compensation",
                 "region": JS, "year": 2025, "age": 78}, config,
                {"amount_minor": OFFICIAL["js_death_75_minor"]})
    age_years = {(60, 20), (61, 19), (74, 6), (75, 5)}
    walk_ok = True
    for age, years in sorted(age_years):
        _, outw = call_cli("calc.damages", {"input": {
            "domain": "personal_injury", "item": "death_compensation",
            "region": SD, "year": 2025, "age": age}}, config)
        got = outw.get("result", {}).get("input", {}).get("income_years")
        if got != years:
            walk_ok = False
    checks.add("F109-PI-3", walk_ok,
               "年龄走年边界 60→20/61→19/74→6/75→5（法释第12/15条）")
    expect_calc(checks, "F109-WI-1",
                {"domain": "work_injury", "item": "death_benefit",
                 "year": 2025}, config,
                {"amount_minor": OFFICIAL["death_benefit_2025_minor"],
                 "amount": "1130040"})
    expect_calc(checks, "F109-WI-2",
                {"domain": "work_injury", "item": "death_benefit",
                 "year": 2024}, config,
                {"amount_minor": OFFICIAL["death_benefit_2024_minor"]})
    months = {1: 27, 2: 25, 3: 23, 4: 21, 5: 18, 6: 16,
              7: 13, 8: 11, 9: 9, 10: 7}
    grade_ok = True
    for grade, m in months.items():
        _, outg = call_cli("calc.damages", {"input": {
            "domain": "work_injury", "item": "lump_sum_disability",
            "grade": grade, "monthly_wage_minor": 600000,
            "regional_avg_monthly_wage_minor": 700000,
            "regional_wage_source": WAGE_SRC}}, config)
        if outg.get("result", {}).get("amount_minor") != 600000 * m:
            grade_ok = False
    checks.add("F109-WI-3", grade_ok,
               "一次性伤残补助金十级月数表（条例35/36/37条）27/25/23/21/18/16/13/11/9/7 全中")
    clamp_ok = True
    for wage, applied, clamped in ((100000, "floor_60", 420000),
                                   (5000000, "cap_300", 2100000),
                                   (650000, "none", 650000)):
        _, outc = call_cli("calc.damages", {"input": {
            "domain": "work_injury", "item": "lump_sum_disability",
            "grade": 10, "monthly_wage_minor": wage,
            "regional_avg_monthly_wage_minor": 700000,
            "regional_wage_source": WAGE_SRC}}, config)
        row = outc.get("result", {})
        if (row.get("steps", [{}])[0].get("clamp_applied") != applied
                or row.get("input", {}).get("clamped_monthly_wage_minor") != clamped):
            clamp_ok = False
    _, outf = call_cli("calc.damages", {"input": {
        "domain": "work_injury", "item": "lump_sum_disability",
        "grade": 10, "monthly_wage_minor": 0,
        "regional_avg_monthly_wage_minor": 7,
        "regional_wage_source": WAGE_SRC}}, config)
    if outf.get("result", {}).get("input", {}).get("clamped_monthly_wage_minor") != 4:
        clamp_ok = False  # 60%×7分=4.2分 → ROUND_HALF_UP → 4分
    checks.add("F109-WI-4", clamp_ok,
               "第64条封顶保底 60%/300%/居中不裁剪＋分位半进位（4.2分→4分）")
    expect_calc(checks, "F109-WI-5",
                {"domain": "work_injury", "item": "disability_allowance",
                 "grade": 2, "monthly_wage_minor": 600000,
                 "regional_avg_monthly_wage_minor": 700000,
                 "regional_wage_source": WAGE_SRC,
                 "difficult_to_arrange_work": True}, config,
                {"amount_minor": 510000, "amount_basis": "per_month"})  # 85%
    expect_calc(checks, "F109-WI-6",
                {"domain": "work_injury", "item": "funeral_subsidy",
                 "regional_avg_monthly_wage_minor": 700000,
                 "regional_wage_source": WAGE_SRC}, config,
                {"amount_minor": 4200000})  # 6 × 7000 元
    zj_ok = True
    for grade, m in ((5, 30), (6, 25), (7, 10), (8, 7), (9, 4), (10, 2)):
        _, outz = call_cli("calc.damages", {"input": {
            "domain": "work_injury", "item": "zj_one_time_medical",
            "region": ZJ, "grade": grade,
            "province_avg_monthly_wage_minor": 800000,
            "province_wage_source": WAGE_SRC}}, config)
        if outz.get("result", {}).get("amount_minor") != 800000 * m:
            zj_ok = False
    checks.add("F109-ZJ-1", zj_ok,
               "浙江省第27条一次性工伤医疗补助金月数 30/25/10/7/4/2 全中（唯一已取得文本源省份）")
    dec_ok = True
    for years, ratio, amount in ((5, "1", 3200000), (3, "0.6", 1920000),
                                 (1, "0.2", 640000)):
        _, outd = call_cli("calc.damages", {"input": {
            "domain": "work_injury", "item": "zj_one_time_employment",
            "region": ZJ, "grade": 9,
            "province_avg_monthly_wage_minor": 800000,
            "province_wage_source": WAGE_SRC,
            "years_to_retirement": years}}, config)
        row = outd.get("result", {})
        if (row.get("steps", [{}])[-1].get("retirement_ratio") != ratio
                or row.get("amount_minor") != amount):
            dec_ok = False
    checks.add("F109-ZJ-2", dec_ok,
               "就业补助金距退休线性递减（每岁-20% 读法，转录注记在案）满5年全额/3年60%/1年20%")

    # S3 checker agreement + determinism --------------------------------------
    payloads = [
        {"domain": "personal_injury", "item": "disability_compensation",
         "region": SD, "year": 2025, "age": 45, "disability_index": "0.3"},
        {"domain": "traffic", "item": "death_compensation",
         "region": JS, "year": 2025, "age": 78},
        {"domain": "work_injury", "item": "death_benefit", "year": 2025},
        {"domain": "work_injury", "item": "lump_sum_disability",
         "grade": 8, "monthly_wage_minor": 800000,
         "regional_avg_monthly_wage_minor": 700000,
         "regional_wage_source": WAGE_SRC},
        {"domain": "work_injury", "item": "zj_one_time_employment",
         "region": ZJ, "grade": 9,
         "province_avg_monthly_wage_minor": 800000,
         "province_wage_source": WAGE_SRC, "years_to_retirement": 3},
    ]
    checker_ok = True
    versions = set()
    for payload in payloads:
        _, outs = call_cli("calc.damages", {"input": payload}, config)
        row = outs.get("result", {})
        chk = row.get("independentChecker", {})
        versions.add(str(chk.get("checker_version")))
        if not chk.get("agreed") or not row.get("calculationReceiptRef"):
            checker_ok = False
    checks.add("F109-CHK-1", checker_ok and versions == {"jc-damages-independent-checker/1"},
               f"五张计算书独立 checker 全同意并封章（receipt ref 在案）versions={versions}")
    det_ok = True
    for payload in payloads:
        _, o1 = call_cli("calc.damages", {"input": payload}, config)
        _, o2 = call_cli("calc.damages", {"input": payload}, config)
        if json.dumps(o1.get("result", {}).get("calculationReceiptRef"), sort_keys=True) != \
           json.dumps(o2.get("result", {}).get("calculationReceiptRef"), sort_keys=True):
            det_ok = False
        body1 = {k: v for k, v in o1.get("result", {}).items() if k != "matterId"}
        body2 = {k: v for k, v in o2.get("result", {}).items() if k != "matterId"}
        if json.dumps(body1, sort_keys=True, ensure_ascii=False) != \
           json.dumps(body2, sort_keys=True, ensure_ascii=False):
            det_ok = False
    checks.add("F109-CHK-2", det_ok, "同输入两算（独立子进程）JSON 字节相等（确定性）")

    # S4 named-gap typed refusals ----------------------------------------------
    expect_typed_failure(checks, "F109-GAP-1",
                         {"domain": "personal_injury",
                          "item": "death_compensation",
                          "region": SD, "year": 2024, "age": 50}, config,
                         "rule_pack_absent")   # 未装年度——绝不拿 2025 补位
    expect_typed_failure(checks, "F109-GAP-2",
                         {"domain": "personal_injury",
                          "item": "death_compensation",
                          "region": "440000", "year": 2025, "age": 50}, config,
                         "rule_pack_absent")   # 未装省份——不装样子
    _, outg2 = call_cli("calc.damages", {"input": {
        "domain": "personal_injury", "item": "death_compensation",
        "region": "440000", "year": 2025, "age": 50}}, config)
    checks.add("F109-GAP-3", "不拿旧年度或其他地区标准补位" in str(outg2.get("code", "")) + str(outg2.get("detail", "")),
               "缺口 detail 具名「不拿旧年度或其他地区标准补位」")
    expect_typed_failure(checks, "F109-GAP-4",
                         {"domain": "personal_injury", "item": "death_compensation",
                          "region": "CN", "year": 2025, "age": 50}, config,
                         "damages_region_not_provincial")  # 全国行拒用于人损（第22条）
    expect_typed_failure(checks, "F109-GAP-5",
                         {"domain": "personal_injury", "item": "funeral_expenses",
                          "region": SD, "year": 2025, "age": 50}, config,
                         "rule_pack_absent")   # 丧葬费具名缺口
    expect_typed_failure(checks, "F109-GAP-6",
                         {"domain": "work_injury", "item": "zj_one_time_medical",
                          "region": SD, "grade": 7,
                          "province_avg_monthly_wage_minor": 800000,
                          "province_wage_source": WAGE_SRC}, config,
                         "rule_pack_absent")   # 31省不装样子
    expect_typed_failure(checks, "F109-GAP-7",
                         {"domain": "work_injury", "item": "lump_sum_disability",
                          "grade": 8, "monthly_wage_minor": 600000}, config,
                         "damages_wage_premise_missing")
    expect_typed_failure(checks, "F109-GAP-8",
                         {"domain": "work_injury", "item": "lump_sum_disability",
                          "grade": 8, "monthly_wage_minor": 600000.5,
                          "regional_avg_monthly_wage_minor": 700000,
                          "regional_wage_source": WAGE_SRC}, config,
                         "damages_float_input_refused")
    code3, out3 = call_cli("calc.damages_x", {"input": {}}, config)
    checks.add("F109-FC-1", code3 == 3 and out3.get("status") == "NOT_CONNECTED",
               f"桥未知方法 fail-closed exit {code3}")
    code4, out4 = call_cli("calc.damages", {"input": {
        "domain": "work_injury", "item": "death_benefit", "year": 2025}}, {})
    checks.add("F109-FC-2", code4 == 3
               and "jc_state_root_not_configured" in str(out4.get("code", "")),
               f"未配置 jc_state_root fail-closed exit {code4}")
    # U01-U03 gap codes via in-process face
    sys.path.insert(0, str(LEGAL_ENTRY.parent))
    try:
        import legal_entry as le  # noqa: F401
        client = le._jc_client(config)
        gap_codes = []
        for slot in ("U01", "U02", "U03"):
            try:
                client.calculate_family({"family": slot, "input": {}})
            except Exception as exc:  # noqa: BLE001 - typed code below
                gap_codes.append(getattr(exc, "code", type(exc).__name__))
        checks.add("F109-GAP-9",
                   gap_codes == [f"CALC_SCOPE_U{s}_NAME_UNKNOWN"
                                 for s in ("01", "02", "03")],
                   f"扩槽后 U01-U03 typed gap codes={gap_codes}（不填不动）")
    finally:
        sys.path.remove(str(LEGAL_ENTRY.parent))

    # S5 provenance --------------------------------------------------------------
    _, outp = call_cli("calc.damages", {"input": {
        "domain": "work_injury", "item": "death_benefit", "year": 2025}}, config)
    src = json.dumps(outp.get("result", {}).get("sources", []), ensure_ascii=False)
    prov_ok = ("stats.gov.cn" in src and "2026-10-20" in src
               and "工伤保险条例" in src
               and "1.2.156.3005.6-0400000000300020101220037500000" in src)
    _, outp2 = call_cli("calc.damages", {"input": {
        "domain": "work_injury", "item": "zj_one_time_medical", "region": ZJ,
        "grade": 7, "province_avg_monthly_wage_minor": 800000,
        "province_wage_source": WAGE_SRC}}, config)
    src2 = json.dumps(outp2.get("result", {}).get("sources", []), ensure_ascii=False)
    checks.add("F109-SRC-1", prov_ok,
               "工亡面法源钉定：全国公报 locator（stats.gov.cn）+retrieved=2026-10-20＋条例 E22 冻结 identifier")
    checks.add("F109-SRC-2",
               "浙江省工伤保险条例" in src2
               and "1.2.156.3005.6-0700330000100120200924004400000" in src2
               and "每增加一周岁递减百分之二十" in src2,
               "浙江第27条 E22 冻结 identifier＋递减读法歧义转录注记在案")
    _, outr = call_cli("calc.registry", {}, config)
    row = json.dumps(outr.get("result", {}).get("v1_5_families", []), ensure_ascii=False)
    checks.add("F109-SRC-3",
               "法释〔2022〕14号" in row and "cn-urban-disposable-income@1" in row,
               "C07 registry 行携带解释面与统计基数包版本")
    return checks


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", action="append",
                        choices=("desktop", "selfhost"), required=True)
    args = parser.parse_args()

    run_stamp = time.strftime("%Y%m%d-%H%M%S")
    overall_ok = True
    profiles = args.profile
    for profile in profiles:
        print(f"\n===== profile {profile} =====")
        with tempfile.TemporaryDirectory(prefix=f"f109-{profile}-") as tmp:
            checks = run_profile(profile, Path(tmp))
        doc = {
            "schema": "f109-damages-calculator-recon/1",
            "unit": "W4-U48",
            "profile": profile,
            "run_stamp": run_stamp,
            "command": f"python -X utf8 tools/recon/PENDING_OWNER_f109_damages_calculator_recon.py "
                       f"--profile {' --profile '.join(profiles)}",
            "jc_worktree": str(JC_REPO),
            "jc_branch": "w4-u48 (base = w4-u45@066ad59 chain head)",
            "pins": JC_SHA256,
            "official_anchors": {
                "national_urban_income_2024_yuan": 54188,
                "national_urban_income_2025_yuan": 56502,
                "shandong_urban_income_2025_yuan": 56444,
                "jiangsu_urban_income_2025_yuan": 68956,
                "retrieved": "2026-10-20",
            },
            "checks": checks.items,
            "status": "RECON_OK" if checks.all_passed else "RECON_FAIL",
            "passed": checks.passed_count,
            "total": len(checks.items),
        }
        out_dir = EVIDENCE_ROOT / "F109" / profile
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "damages-recon.json").write_text(
            json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")
        md = [
            f"# F109 赔偿金计算器 recon — {profile}（W4-U48）",
            "",
            f"- status: **{doc['status']}** {checks.passed_count}/{len(checks.items)}",
            f"- command: `{doc['command']}`（worktree 根 cwd）",
            f"- JC: `{JC_REPO}`（分支 w4-u48，四文件 sha256 钉定漂移响亮拒）",
            "- 官方基数（2026-10-20 直读）：全国2024=54188 元／全国2025=56502 元／"
            "山东2025=56444 元／江苏2025=68956 元；工亡 2026=56502×20=1,130,040 元。",
            "- 具名缺口：未装地区/年度拒算（不拿旧年度标准或缺值补 0）；人损丧葬费"
            "（省级职工月平均工资未取得）；31省一次性工伤补助金只装浙江"
            "（E22 冻结语料）。",
            "",
            "| # | 检查 | 状态 | 说明 |",
            "|---|---|---|---|",
        ]
        for item in checks.items:
            md.append(f"| {len(md)-9} | {item['id']} | {item['status']} | "
                      f"{item['detail'].replace('|', chr(92)+'|')} |")
        (out_dir / "damages-recon.md").write_text(
            "\n".join(md) + "\n", encoding="utf-8")
        print(f"[{doc['status']}] {profile}: {checks.passed_count}/{len(checks.items)}")
        overall_ok = overall_ok and checks.all_passed
    return 0 if overall_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())

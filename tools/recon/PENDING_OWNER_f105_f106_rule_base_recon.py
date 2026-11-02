# -*- coding: utf-8 -*-
"""F105 官方规则基准对拍＋F106 日历版本账与超范围未知 验收对账（W2b-U54）。

F105（06 行，双实例）：MatterVibe 只是差异发现不是真值——JC 侧对拍夹具
（竞品情报快照只读＋合成转录，绝无真实客户数据）×官方基准（W2b-U19 版本化
规则包 481号令/司发通〔2021〕87号/CIETAC 2024 全带 locator+retrieved）的
确定性对拍报告。差异仅陈述不裁真伪：报告无 pass/fail 字段（对拍报告不当
验收真值）；竞品错值不改 JC 输出（对拍后官方值逐项复验不变）；北仲
RULE_PACK_ABSENT 缺口不被竞品表填塞；U01-U03 槽不被工具箱 7 件填塞
（12号文档：F110 已砍文本去重/字数统计；calendar_shift 月末夹取差异必须在
夹具行——12号文档§3.1）。

F106（06 行，双实例）：日历版本账——2025/2026 全国假日＋调休补班表内嵌全
带官方文号（国办发明电〔2024〕16号/〔2025〕7号）与版本串回读；实际年份/
地区/调休补班/起算规则版本逐项回读；次日起算语义（按日届满日=起算日+count；
按月/年走 calendar_shift 月末夹取）；期间末日逢休息日顺延（调休补班日为
工作日）；超范围年份→结构化 UNKNOWN 零日期字段（绝不用 2025-2026 表外推，
也不给日期）。

负向四拒全具名：竞品值覆盖官方值 / 无版本号日历命中 / 超范围年份给出日期 /
对拍报告当验收真值。

用法（juscite worktree w2b-u54 根 cwd；--profile 缺省＝双 profile）：
  python -X utf8 tools/PENDING_OWNER_f105_f106_rule_base_recon.py \
      [--profile desktop --profile selfhost]

exit 0＝RECON_OK 全断言过；证据 JSON 写 evidence/F105/<profile>/ 与
evidence/F106/<profile>/。全合成材料；只读消费 JC worktree；不发网络。
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

REPO_ROOT = Path(__file__).resolve().parents[1]
LEGAL_ENTRY = REPO_ROOT / "implementation" / "python" / "legal_entry.py"
EVIDENCE_ROOT = REPO_ROOT / "docs" / "construction" / "evidence"

JC_REPO = Path(
    r"D:\Codex\1.法律工作区\juris-calculus工作区\juris-calculus\.local\worktrees\w2b-u54")
JC_RULE_BASE_RECON_SHA256 = (
    "c63bc829284b1cbbd3d62fd93cd346288c29d9ed0471a71ebd92f3d42546f177")
JC_CALENDAR_VERSIONS_SHA256 = (
    "b1e4765f4a965c5c329d1a8fbbfd1d45e0444ba26f211252558ee06d54e6fd2c")
JC_CLIENT_SHA256 = (
    "a6ca652755c71a846cbc68be598dde826500453f23a8ecb0527fec0e14e5b01a")

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
    """真产品入口子进程径（legal_entry CLI；同 W2b-U19 recon 纪律）。"""
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

    # S0 JC w2b-u54 worktree pin ---------------------------------------------
    if not (JC_REPO / "compiler_core" / "rule_base_recon.py").is_file():
        checks.add("U54-PIN-0", False, f"JC worktree missing at {JC_REPO}")
        return checks
    pins_ok = all(
        hashlib.sha256((JC_REPO / rel).read_bytes()).hexdigest() == want
        for rel, want in (
            ("compiler_core/rule_base_recon.py", JC_RULE_BASE_RECON_SHA256),
            ("compiler_core/calendar_versions.py", JC_CALENDAR_VERSIONS_SHA256),
            ("compiler_core/client.py", JC_CLIENT_SHA256)))
    checks.add("U54-PIN-0", pins_ok,
               "JC w2b-u54 worktree sha256 三钉定（rule_base_recon/calendar_versions/client）")

    code, out = call_cli("calc.registry", {}, config)
    group_ok = code == 0
    checks.add("U54-PIN-1", group_ok, "桥可达（calc.registry exit 0）")

    # S1 F105 对拍报告：差异仅陈述不裁真伪 --------------------------------------
    code, out = call_cli("calc.rule_base_recon", {}, config)
    ok = code == 0 and out.get("status") == "OWNER_RESPONSE"
    report = out.get("result", {}) if ok else {}
    ok = ok and report.get("recon_id") == "f105-rule-base-recon" \
        and report.get("disposition") == "difference_statement_only" \
        and report.get("truth_adjudication") == "REFUSED_NOT_ACCEPTANCE_TRUTH" \
        and not any(k in report for k in ("verdict", "passed", "agreed", "ok")) \
        and all(row.get("relation") in report.get("relation_vocabulary", [])
                for row in report.get("rows", [])) \
        and report.get("reconRef", {}).get("kind") == "rule-base-recon-report"
    checks.add("F105-R1", ok,
               "对拍报告 statement-only：无 pass/fail 字段，行级闭集 relation，"
               "reconRef 登记可回读（对拍报告≠验收真值）")
    if not ok:
        checks.add("F105-R1-DEBUG", False, json.dumps(out, ensure_ascii=False)[:600])
        return checks

    rows = {(row["section"], row["item"]): row for row in report["rows"]}
    court_rows = [key for key in rows if key[0] == "court_fee" and key[1].endswith("档")]
    court_ok = (len(court_rows) == 10
                and all(rows[key]["relation"] == "AGREE" for key in court_rows)
                and rows[("court_fee", "样例 标的100,000元")]["relation"] == "AGREE"
                and "2300" in rows[("court_fee", "样例 标的100,000元")]["jc_value"])
    checks.add("F105-R2", court_ok,
               "诉讼费十段逐档对拍（481号令第十三条 vs MatterVibe COURT_TIERS）"
               "全 AGREE＋公报样例 2300 元双算一致")

    pres_ok = (rows[("preservation_fee", "首段")]["relation"] == "AGREE"
               and rows[("preservation_fee", "封顶")]["relation"] == "AGREE"
               and "5000" in rows[("preservation_fee", "封顶")]["jc_value"]
               and rows[("preservation_fee", "样例 保全标的50,000元")]["relation"] == "AGREE")
    checks.add("F105-R3", pres_ok,
               "保全 30 起/1%/0.5%/5000 封顶逐项对拍＋5 万样例 520 元双算一致")

    arb_accept = rows[("arbitration", "贸仲受理费 样例100万元")]
    arb_handle = rows[("arbitration", "贸仲处理费 样例100万元")]
    arb_ok = (arb_accept["relation"] == "DIFFER"
              and "17000" in arb_accept["jc_value"]
              and "18550" in arb_accept["competitor_value"]
              and arb_handle["relation"] == "AGREE"
              and rows[("arbitration", "北仲（BAC）")]["relation"] == "GAP_JC_SIDE"
              and "RULE_PACK_ABSENT" in rows[("arbitration", "北仲（BAC）")]["jc_value"]
              and rows[("arbitration", "贸仲表（一）涉外")]["relation"] == "NOT_COMPARABLE")
    checks.add("F105-R4", arb_ok,
               "贸仲北仲落段 26 档对拍：受理费 100 万官方 17000 vs 通行流传版 "
               "18550＝DIFFER（差异仅陈述）；处理费 19500＝AGREE；"
               "北仲缺口保持；涉外表夹具缺面如实 NOT_COMPARABLE")

    month_end = rows[("calendar", "月末/闰日加法语义")]
    month_ok = (month_end["relation"] == "SEMANTICS_DIFFER"
                and "2026-02-28" in month_end["jc_value"]
                and "2026-03-03" in month_end["competitor_value"]
                and "2025-02-28" in month_end["jc_value"]
                and "2025-03-01" in month_end["competitor_value"])
    checks.add("F105-R5", month_ok,
               "calendar_shift 月末/闰日夹取 vs JS setMonth/setFullYear 溢出"
               "——12号文档§3.1 要求的夹具行在报告（JC 语义不随竞品改）")

    denom_ok = ("工具箱 7 件" in rows[("denominator", "九族分母纪律")]["competitor_value"]
                and rows[("denominator", "U01-U03 槽位")]["relation"] == "GAP_JC_SIDE")
    checks.add("F105-R6", denom_ok,
               "分母纪律重申：工具箱 7 件≠九族（F110 已砍文本去重/字数统计不填槽）；"
               "U01-U03 保持 NAME_UNKNOWN")

    # S2 F105 负向：竞品值不改 JC 输出＋缺口不被填塞 ----------------------------
    code, out = call_cli("calc.arbitration_fee", {
        "input": {"institution": "cietac", "table": "in",
                  "amount_minor": 100_000_000}}, config)
    sheet = out.get("result", {}) if code == 0 else {}
    no_override_1 = (sheet.get("acceptance_amount_minor") == 1_700_000
                     and sheet.get("handling_amount_minor") == 1_950_000)
    code, out = call_cli("calc.court_fee", {"input": {"amount_minor": 10_000_000}}, config)
    no_override_2 = out.get("result", {}).get("amount_minor") == 230_000
    code, out = call_cli("calc.arbitration_fee", {
        "input": {"institution": "bac", "table": "out", "amount_minor": 1}}, config)
    bac_refused = (code == 4 and out.get("status") == "JC_FAILURE"
                   and "rule_pack_absent" in str(out.get("code", "")))
    checks.add("F105-N1", no_override_1 and no_override_2 and bac_refused,
               "对拍后官方值逐项复验不变（竞品 18550 未进入 JC 输出：受理费 17000/"
               "诉讼费 2300）＋北仲仍 typed 拒 rule_pack_absent（竞品表不补缺口）"
               "——竞品错值不得强迫 JC 一致")

    client_module = str(LEGAL_ENTRY.parent)
    sys.path.insert(0, client_module)
    try:
        import legal_entry as le  # noqa: F401
        client = le._jc_client(config)
        gap_codes = []
        for slot in ("U01", "U02", "U03"):
            try:
                client.calculate_family({"family": slot, "input": {}})
            except Exception as exc:  # noqa: BLE001 - typed code below
                gap_codes.append(getattr(exc, "code", type(exc).__name__))
        checks.add("F105-N2",
                   gap_codes == [f"CALC_SCOPE_U{s}_NAME_UNKNOWN"
                                 for s in ("01", "02", "03")],
                   f"U01-U03 对拍后仍具名拒 {gap_codes}（工具箱件零填槽）")
    finally:
        sys.path.remove(client_module)

    # S3 F106 日历版本账：版本回读 ---------------------------------------------
    code, out = call_cli("calc.calendar_account", {
        "request": {"year": 2026, "region": "CN-mainland"}}, config)
    acc26 = out.get("result", {}) if code == 0 else {}
    acc26_ok = (acc26.get("status") == "COVERED"
                and acc26.get("calendar_version") == "cn-holiday/gobafamingdian-2025-7@1"
                and acc26.get("source", {}).get("document_number") == "国办发明电〔2025〕7号"
                and acc26.get("adjusted_workdays") == [
                    "2026-01-04", "2026-02-14", "2026-02-28",
                    "2026-05-09", "2026-09-20", "2026-10-10"]
                and acc26.get("region") == "CN-mainland"
                and str(acc26.get("start_rule", {}).get("version", "")).startswith(
                    "cn-procedure-period-start/"))
    checks.add("F106-R1", acc26_ok,
               "2026 版本账回读：年份/地区/调休补班六日/官方文号/版本串/起算规则版本")

    code, out = call_cli("calc.calendar_account", {
        "request": {"year": 2025, "region": "CN-mainland"}}, config)
    acc25 = out.get("result", {}) if code == 0 else {}
    acc25_ok = (acc25.get("calendar_version") == "cn-holiday/gobafamingdian-2024-16@1"
                and acc25.get("source", {}).get("document_number") == "国办发明电〔2024〕16号")
    checks.add("F106-R2", acc25_ok, "2025 版本账回读（国办发明电〔2024〕16号）")

    due_cases = [
        ("F106-R3", {"year": 2026, "region": "CN-mainland",
                     "anchor_date": "2026-06-01", "count": 15, "unit": "days"},
         {"due_date": "2026-06-16", "rolled": False},
         "次日起算：15 日自 6/1 起算→届满 6/16（起算日不计入）"),
        ("F106-R4", {"year": 2026, "region": "CN-mainland",
                     "anchor_date": "2026-02-14", "count": 14, "unit": "days"},
         {"due_date": "2026-02-28", "rolled": False},
         "调休补班周六（2026-02-28）按工作日＝届满日不滚动"),
        ("F106-R5", {"year": 2026, "region": "CN-mainland",
                     "anchor_date": "2026-09-25", "count": 1, "unit": "days"},
         {"due_date": "2026-09-28", "rolled": True, "roll_reason": "中秋"},
         "假日顺延＋原因回读（中秋 9/25-9/27→9/28）"),
        ("F106-R6", {"year": 2026, "region": "CN-mainland",
                     "anchor_date": "2026-01-31", "count": 1, "unit": "months"},
         {"due_date": "2026-02-28"},
         "按月期间走 calendar_shift 月末夹取（JC 冻结语义）"),
    ]
    for cid, request, expected, note in due_cases:
        code, out = call_cli("calc.calendar_due_date", {"request": request}, config)
        result = out.get("result", {}) if code == 0 else {}
        ok = code == 0 and result.get("status") == "OK"
        if ok:
            for key, value in expected.items():
                if result.get(key) != value:
                    ok = False
                    break
        ok = ok and str(result.get("calendar_version", "")).startswith("cn-holiday/") \
            and "国办发明电" in result.get("source", {}).get("document_number", "")
        checks.add(cid, ok, f"{note}；版本号回读={result.get('calendar_version')}")

    # S4 F106 超范围未知：零日期字段 -------------------------------------------
    code, out = call_cli("calc.calendar_account", {
        "request": {"year": 2027, "region": "CN-mainland"}}, config)
    unk = out.get("result", {}) if code == 0 else {}
    unk_ok = (code == 0 and unk.get("status") == "UNKNOWN"
              and unk.get("reason_code") == "calendar_year_out_of_range"
              and unk.get("date_fields_present") is False
              and "holidays" not in unk and "adjusted_workdays" not in unk
              and unk.get("covered_calendar_versions", {}).get("2025")
              == "cn-holiday/gobafamingdian-2024-16@1")
    code, out = call_cli("calc.calendar_due_date", {
        "request": {"year": 2026, "region": "CN-mainland",
                    "anchor_date": "2026-12-20", "count": 30, "unit": "days"}}, config)
    unk_due = out.get("result", {}) if code == 0 else {}
    unk_ok = unk_ok and (unk_due.get("status") == "UNKNOWN"
                         and unk_due.get("reason_code") == "calendar_year_out_of_range"
                         and "due_date" not in unk_due
                         and "nominal_due_date" not in unk_due)
    checks.add("F106-N1", unk_ok,
               "超范围年份→结构化 UNKNOWN 零日期（2027 直查＋2026-12-20+30日跨年）；"
               "已内嵌版本仍如实列出（不外推不给日期）")

    # S5 typed 拒＋fail-closed＋确定性 ------------------------------------------
    code, out = call_cli("calc.calendar_account", {
        "request": {"year": "2026", "region": "CN-mainland"}}, config)
    typed_ok = (code == 4 and out.get("status") == "JC_FAILURE"
                and "calendar_year_invalid" in str(out.get("code", "")))
    code, out = call_cli("calc.calendar_due_date", {
        "request": {"year": 2026, "region": "CN-mainland",
                    "anchor_date": "2026-01-01", "count": 1,
                    "unit": "fortnights"}}, config)
    typed_ok = typed_ok and (code == 4 and "calendar_unit_unknown" in str(out.get("code", "")))
    checks.add("U54-FC-1", typed_ok,
               "坏形输入 typed 拒（calendar_year_invalid/calendar_unit_unknown）→ exit 4")

    code, out = call_cli("calc.rule_base", {}, config)
    fc1 = code == 3 and out.get("status") == "NOT_CONNECTED"
    code, out = call_cli("calc.rule_base_recon", {}, {})
    fc2 = code == 3 and "jc_state_root_not_configured" in str(out.get("code", ""))
    checks.add("U54-FC-2", fc1 and fc2,
               "桥未知方法/未配置 jc_state_root fail-closed exit 3")

    _, recon_a = call_cli("calc.rule_base_recon", {}, config)
    _, recon_b = call_cli("calc.rule_base_recon", {}, config)
    det1 = json.dumps(recon_a, sort_keys=True, ensure_ascii=False) == \
        json.dumps(recon_b, sort_keys=True, ensure_ascii=False)
    cal_request = {"request": {"year": 2026, "region": "CN-mainland",
                               "anchor_date": "2026-10-01", "count": 1,
                               "unit": "days"}}
    _, cal_a = call_cli("calc.calendar_due_date", cal_request, config)
    _, cal_b = call_cli("calc.calendar_due_date", cal_request, config)
    det2 = json.dumps(cal_a, sort_keys=True, ensure_ascii=False) == \
        json.dumps(cal_b, sort_keys=True, ensure_ascii=False)
    checks.add("U54-DET-1", det1 and det2,
               "同输入同回执字节（对拍报告＋日历届满日，子进程独立两跑）")

    return checks


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", action="append",
                        choices=("desktop", "selfhost"),
                        default=None,
                        help="缺省＝desktop＋selfhost 双 profile")
    args = parser.parse_args()
    profiles = args.profile or ["desktop", "selfhost"]

    run_stamp = time.strftime("%Y%m%d-%H%M%S")
    overall_ok = True
    for profile in profiles:
        print(f"\n===== profile {profile} =====")
        with tempfile.TemporaryDirectory(prefix=f"u54-f105-f106-{profile}-") as tmp:
            checks = run_profile(profile, Path(tmp))
        doc = {
            "schema": "w2b-u54-f105-f106-rule-base-recon/1",
            "unit": "W2b-U54",
            "profile": profile,
            "run_stamp": run_stamp,
            "command": f"python -X utf8 tools/PENDING_OWNER_f105_f106_rule_base_recon.py"
                       f"{' --profile ' + ' --profile '.join(profiles) if args.profile else ''}",
            "jc_worktree": str(JC_REPO),
            "pins": {
                "rule_base_recon": JC_RULE_BASE_RECON_SHA256,
                "calendar_versions": JC_CALENDAR_VERSIONS_SHA256,
                "client": JC_CLIENT_SHA256,
            },
            "checks": checks.items,
            "status": "RECON_OK" if checks.all_passed else "RECON_FAIL",
            "passed": checks.passed_count,
            "total": len(checks.items),
        }
        for duty in ("F105", "F106"):
            out_dir = EVIDENCE_ROOT / duty / profile
            out_dir.mkdir(parents=True, exist_ok=True)
            (out_dir / "rule-base-recon.json").write_text(
                json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"[{doc['status']}] {profile}: {checks.passed_count}/{len(checks.items)}")
        overall_ok = overall_ok and checks.all_passed
    return 0 if overall_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())

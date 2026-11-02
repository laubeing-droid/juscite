# -*- coding: utf-8 -*-
"""E21 规则族与计算分母冻结＋F104 具名九计算族首批 验收对账（W2b-U19）。

E21（07 义务行）：九计算族/14 期限准确名称和入口冻结——经 P01 JCClient
（jc_import_path 指向 JC 仓 w2b-u19 worktree，sha256 钉定漂移响亮拒）读
JC 公开 registry（calc-families/1）；官方时点/日历/舍入/边界/独立 checker。

F104（06 行，双实例）：具名九计算族首批——C01/C03/C04/C05/C06 经
legal_entry 冻结方法组 calc.* 真算（Decimal 全程、整数分输出、同输入同
输出）；12 号文档三处名称缺口纪律：U01/U02/U03 保持
CALC_SCOPE_U0x_NAME_UNKNOWN（未命名槽不凑数，不得以工具箱 7 件或
F108/F109 填槽）；unsupported 具名缺口（BAC 规则包缺席/复利/叠加减免
半/禁止案件类型）typed 错误回传，非纸面答案。

分段：
  S1 E21 registry 冻结（九槽六名三缺口/14 预设状态/规则包版本/分母纪律/
     注册表确定性两读同值）
  S2 F104 首批真算（法院公报镜像样例值/段边界/减半/上诉基数；保全封顶；
     风险代理五档限额与超限如实；贸仲表一/表二官方值＋最低费＋超30亿不计
     费；利息闰日月末真实日期边界＋阶梯换率段界）
  S3 独立 checker（每张计算书 checker agreed＋版本；同输入两算字节相等）
  S4 具名缺口 typed 拒绝（U01-U03/C02 复用/BAC/复利/叠加减半/禁止类型/
     桥未知方法/未配置 fail-closed；CLI exit 3/4 语义）
  S5 法源钉定（规则包 source 带 locator+retrieved；CIETAC 转录注记含
     6,625,000 读数歧义与裁定记录）

用法（juscite worktree w2b-u19 根 cwd）：
  python -X utf8 tools/recon/PENDING_OWNER_e21_f104_calc_family_recon.py \
      --profile desktop --profile selfhost

exit 0＝RECON_OK 全断言过；证据 JSON 写 evidence/E21/<profile>/ 与
evidence/F104/<profile>/。全合成材料；只读消费 JC worktree；不发网络。
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
    r"D:\Codex\1.法律工作区\juris-calculus工作区\juris-calculus\.local\worktrees\w2b-u19")
JC_CALC_FAMILIES_SHA256 = (
    "bda5f119932b7aa026e63facd002d4535c3ec79e28ffdcad38b0d03ef2df7a5c")
JC_CALC_CHECKER_SHA256 = (
    "c41ae4062fbfdac5d214235de886b2e1f201c133c5f0217c0c31c186aa53cc31")
JC_CLIENT_SHA256 = (
    "8da6ae0bb3a9f0728e053e3a61953f5698fe75a26210f0c84ca7597ce5427e46")

# 合成规则包（工程夹具；测试材料全合成红线）。计算族不消费规则内容，
# create_local_client 只要求在册规则根存在且可加载。
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

# 12 号文档 §2：MatterVibe 工具箱 7 件——不得用于填九槽
TOOLBOX_SEVEN = {"期限", "诉讼费", "风险代理费", "仲裁费", "金额大写", "文本去重", "字数统计"}


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
    """真产品入口子进程径（legal_entry CLI；同 F64/F69 recon 纪律）。"""
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


def expect_calc(checks: Checks, cid: str, method: str, payload: dict,
                config: dict, expected: dict):
    code, out = call_cli(method, {"input": payload}, config)
    ok = code == 0 and out.get("status") == "OWNER_RESPONSE"
    if ok:
        for key, value in expected.items():
            if out["result"].get(key) != value:
                ok = False
                break
    checks.add(cid, ok,
               f"{method} {json.dumps(expected, ensure_ascii=False)}"
               f" -> exit {code} "
               + (json.dumps({k: out['result'].get(k) for k in expected},
                             ensure_ascii=False) if out.get('result') else out.get('status', '')))
    return out


def expect_typed_failure(checks: Checks, cid: str, method: str, payload: dict,
                          config: dict, code_fragment: str):
    code, out = call_cli(method, {"input": payload}, config)
    ok = (code == 4 and out.get("status") == "JC_FAILURE"
          and code_fragment in str(out.get("code", "")))
    checks.add(cid, ok, f"{method} typed refusal {code_fragment} -> exit {code} "
                        f"{out.get('code', out.get('status', ''))[:120]}")


def run_profile(profile: str, workspace_root: Path) -> Checks:
    checks = Checks()
    workspace = workspace_root / profile
    workspace.mkdir(parents=True, exist_ok=True)
    config = make_config(workspace)

    # S1 E21 registry freeze -------------------------------------------------
    if not (JC_REPO / "compiler_core" / "calc_families.py").is_file():
        checks.add("E21-PIN-0", False, f"JC worktree missing at {JC_REPO}")
        return checks
    pins_ok = all(
        hashlib.sha256((JC_REPO / rel).read_bytes()).hexdigest() == want
        for rel, want in (
            ("compiler_core/calc_families.py", JC_CALC_FAMILIES_SHA256),
            ("compiler_core/calc_checker.py", JC_CALC_CHECKER_SHA256),
            ("compiler_core/client.py", JC_CLIENT_SHA256)))
    checks.add("E21-PIN-0", pins_ok, "JC w2b-u19 worktree sha256 三钉定（calc_families/calc_checker/client）")

    code, out = call_cli("calc.registry", {}, config)
    reg = out.get("result", {}) if out.get("status") == "OWNER_RESPONSE" else {}
    slots = [r.get("slot") for r in reg.get("nine_families", [])]
    checks.add("E21-R1", code == 0 and slots ==
               ["C01", "C02", "C03", "C04", "C05", "C06", "U01", "U02", "U03"],
               f"九槽冻结 slots={slots}")
    named = {r["slot"]: r.get("zh_name") for r in reg.get("nine_families", [])}
    six_ok = [named.get(f"C0{i}") for i in range(1, 7)] == [
        "阶梯利息", "期限", "诉讼费", "财产保全费", "风险代理费", "仲裁费"]
    checks.add("E21-R2", six_ok, f"六具名域名称冻结 {json.dumps(named, ensure_ascii=False)}")
    gap_rows = [r for r in reg.get("nine_families", []) if r["slot"].startswith("U")]
    gaps_ok = (len(gap_rows) == 3
               and all(r.get("status") == f"CALC_SCOPE_{r['slot']}_NAME_UNKNOWN"
                       and r.get("zh_name") is None and r.get("public_entry") is None
                       for r in gap_rows))
    toolbox_never_fills = TOOLBOX_SEVEN.isdisjoint(
        {r.get("zh_name") for r in gap_rows if r.get("zh_name")})
    checks.add("E21-R3", gaps_ok and toolbox_never_fills,
               "三具名 scope gap 保持 NAME_UNKNOWN，工具箱 7 件零填槽")
    presets = reg.get("deadline_presets", [])
    status_counts: dict[str, int] = {}
    for row in presets:
        status_counts[row.get("status", "")] = status_counts.get(row.get("status", ""), 0) + 1
    d14 = next((r for r in presets if r.get("slot") == "D14"), {})
    d07 = next((r for r in presets if r.get("slot") == "D07"), {})
    presets_ok = (len(presets) == 14
                  and status_counts.get("RULE_MAPPED") == 9
                  and status_counts.get("PARTIAL") == 3
                  and d07.get("status") == "UNKNOWN" and d07.get("rule") is None
                  and d14.get("status") == "CONTRACT_UNKNOWN"
                  and all("竞品声明" in r.get("source_period", "") for r in presets))
    checks.add("E21-R4", presets_ok,
               f"14 期限预设冻结 statuses={json.dumps(status_counts)}")
    packs_ok = reg.get("rule_packs") == {
        "C03": "cn-court-fee/sc-481-2007@1",
        "C04": "cn-preservation-fee/sc-481-2007@1",
        "C05": "cn-lawyer-contingency/sft-2021-87@1",
        "C06": "cietac/2024@1"}
    checks.add("E21-R5", packs_ok, f"规则包版本冻结 {json.dumps(reg.get('rule_packs'), ensure_ascii=False)}")
    code2, out2 = call_cli("calc.registry", {}, config)
    checks.add("E21-R6", code2 == 0 and json.dumps(out.get("result"), sort_keys=True, default=str)
               == json.dumps(out2.get("result"), sort_keys=True, default=str),
               "registry 两读同值（冻结确定性）")

    # S2 F104 first batch real values ---------------------------------------
    expect_calc(checks, "F104-C03-1", "calc.court_fee",
                {"amount_minor": 10_000_000}, config,
                {"amount_minor": 230_000})            # 公报镜像样例 2300元
    expect_calc(checks, "F104-C03-2", "calc.court_fee",
                {"amount_minor": 1_000_000}, config, {"amount_minor": 5_000})
    expect_calc(checks, "F104-C03-3", "calc.court_fee",
                {"amount_minor": 2_000_000_000}, config, {"amount_minor": 14_180_000})
    expect_calc(checks, "F104-C03-4", "calc.court_fee",
                {"amount_minor": 10_000_000, "simplified_procedure": True},
                config, {"amount_minor": 115_000, "reduction_applied": "simplified_procedure"})
    expect_calc(checks, "F104-C03-5", "calc.court_fee",
                {"amount_minor": 500_000_000, "appeal_amount_minor": 10_000_000},
                config, {"amount_minor": 230_000})
    expect_calc(checks, "F104-C04-1", "calc.preservation_fee",
                {"preserved_amount_minor": 5_000_000}, config, {"amount_minor": 52_000})
    expect_calc(checks, "F104-C04-2", "calc.preservation_fee",
                {"preserved_amount_minor": 100_000_000}, config, {"amount_minor": 500_000})
    expect_calc(checks, "F104-C04-3", "calc.preservation_fee",
                {"preserved_amount_minor": 89_000_000}, config, {"amount_minor": 497_000})
    expect_calc(checks, "F104-C05-1", "calc.contingency_fee", {
        "case_type": "civil_contract", "target_amount_minor": 100_000_000,
        "agreement": {"mode": "rate", "rate": "0.1"}},
        config, {"statutory_cap_minor": 18_000_000, "certified": True})
    expect_calc(checks, "F104-C05-2", "calc.contingency_fee", {
        "case_type": "civil_contract", "target_amount_minor": 100_000_000,
        "agreement": {"mode": "rate", "rate": "0.2"}},
        config, {"certified": False,
                 "refusal_reasons": ["agreement_fee_exceeds_statutory_cap_ladder"]})
    expect_calc(checks, "F104-C06-1", "calc.arbitration_fee", {
        "institution": "cietac", "table": "out", "amount_minor": 100_000_000},
        config, {"amount_minor": 4_000_000})
    expect_calc(checks, "F104-C06-2", "calc.arbitration_fee", {
        "institution": "cietac", "table": "out", "amount_minor": 10_000_000},
        config, {"amount_minor": 1_000_000})          # 最低 1 万元
    expect_calc(checks, "F104-C06-3", "calc.arbitration_fee", {
        "institution": "cietac", "table": "out", "amount_minor": 100_000_000_000},
        config, {"amount_minor": 662_500_000})        # 10亿=662.5万（歧义档钉定）
    expect_calc(checks, "F104-C06-4", "calc.arbitration_fee", {
        "institution": "cietac", "table": "out", "amount_minor": 300_000_000_000},
        config, {"amount_minor": 1_512_500_000})      # 30亿=1512.5万计费顶点
    _, out4b = call_cli("calc.arbitration_fee", {
        "input": {"institution": "cietac", "table": "out",
                  "amount_minor": 400_000_000_000}}, config)
    checks.add("F104-C06-5",
               out4b.get("result", {}).get("amount_minor") == 1_512_500_000,
               "超30亿元部分不再计费：40亿==30亿")
    expect_calc(checks, "F104-C06-6", "calc.arbitration_fee", {
        "institution": "cietac", "table": "in", "amount_minor": 100_000_000},
        config, {"acceptance_amount_minor": 1_700_000,
                 "handling_amount_minor": 1_950_000})
    expect_calc(checks, "F104-C01-1", "calc.interest", {
        "principal_minor": 365_000,
        "segments": [{"start_date": "2024-02-28", "end_date": "2024-03-01",
                      "annual_rate": "0.01"}]},
        config, {"amount_minor": 20})                  # 闰日 2 天
    expect_calc(checks, "F104-C01-2", "calc.interest", {
        "principal_minor": 365_000,
        "segments": [{"start_date": "2026-01-31", "end_date": "2026-03-01",
                      "annual_rate": "0.01"}]},
        config, {"amount_minor": 290})                 # 月末跨二月 29 天
    expect_calc(checks, "F104-C01-3", "calc.interest", {
        "principal_minor": 1_000_000_000,
        "segments": [
            {"start_date": "2026-01-01", "end_date": "2026-07-01", "annual_rate": "0.06"},
            {"start_date": "2026-07-01", "end_date": "2027-01-01", "annual_rate": "0.08"}]},
        config, {"amount_minor": 70_082_192})          # 1000万阶梯换率（精确有理数舍入）

    # S3 independent checker + determinism -----------------------------------
    families = (
        ("calc.court_fee", {"amount_minor": 123_456_789}),
        ("calc.preservation_fee", {"preserved_amount_minor": 987_654_321}),
        ("calc.contingency_fee", {
            "case_type": "civil_contract", "target_amount_minor": 55_555_555,
            "agreement": {"mode": "tiered_rate", "tiers": [
                {"upper_exclusive_minor": 1_000_000_000, "rate": "0.12"},
                {"upper_exclusive_minor": None, "rate": "0.07"}]}}),
        ("calc.arbitration_fee", {
            "institution": "cietac", "table": "out", "amount_minor": 12_345_678_901}),
        ("calc.interest", {
            "principal_minor": 9_999_999,
            "segments": [{"start_date": "2026-02-28", "end_date": "2026-12-31",
                          "annual_rate": "0.037"}]}),
    )
    checker_ok = True
    determinism_ok = True
    for method, payload in families:
        _, first = call_cli(method, {"input": payload}, config)
        _, second = call_cli(method, {"input": payload}, config)
        row = first.get("result", {})
        if not (row.get("independentChecker", {}).get("agreed") is True
                and row.get("independentChecker", {}).get("checker_version")
                == "calc-family-independent-checker/1"
                and row.get("calculationReceiptRef", {}).get("kind")
                == "calc-family-sheet"):
            checker_ok = False
        if json.dumps(first, sort_keys=True, default=str) != \
                json.dumps(second, sort_keys=True, default=str):
            determinism_ok = False
    checks.add("F104-CHK-1", checker_ok,
               "五族计算书全部独立 checker agreed＋版本钉定＋盖章回执")
    checks.add("F104-DET-1", determinism_ok,
               "同输入同输出：五族两算（子进程独立）JSON 字节相等")

    # S4 unsupported named gaps typed refusals -------------------------------
    for slot in ("U01", "U02", "U03"):
        code, outu = call_cli("jc.evaluate", {}, config)  # bridge has no U-slot method
        # the bridge surface itself carries no U-slot entry: the frozen method
        # list is the entry freeze. JC-side refusal asserted via python import.
    sys.path.insert(0, str(LEGAL_ENTRY.parent))
    try:
        import legal_entry as le  # noqa: F401  (same-process face for gap codes)
        client = le._jc_client(config)
        gap_codes = []
        for slot in ("U01", "U02", "U03"):
            try:
                client.calculate_family({"family": slot, "input": {}})
            except Exception as exc:  # noqa: BLE001 - typed code below
                gap_codes.append(getattr(exc, "code", type(exc).__name__))
        try:
            client.calculate_family({"family": "C02", "input": {}})
        except Exception as exc:  # noqa: BLE001
            c02_code = getattr(exc, "code", type(exc).__name__)
        else:
            c02_code = ""
        checks.add("E21-GAP-1",
                   gap_codes == [f"CALC_SCOPE_U{s}_NAME_UNKNOWN" for s in ("01", "02", "03")]
                   and c02_code == "calc_family_reuses_deadline_entry",
                   f"U01-U03 typed gap codes={gap_codes}；C02 复用拒绝={c02_code}")
    finally:
        sys.path.remove(str(LEGAL_ENTRY.parent))

    expect_typed_failure(checks, "F104-GAP-2", "calc.arbitration_fee", {
        "institution": "bac", "table": "out", "amount_minor": 1}, config,
        "rule_pack_absent")
    expect_typed_failure(checks, "F104-GAP-3", "calc.interest", {
        "principal_minor": 100, "compound": "annual",
        "segments": [{"start_date": "2026-01-01", "end_date": "2026-02-01",
                      "annual_rate": "0.05"}]}, config,
        "interest_compound_not_supported_in_first_batch")
    expect_typed_failure(checks, "F104-GAP-4", "calc.court_fee", {
        "amount_minor": 1_000_000, "simplified_procedure": True,
        "mediation_or_withdrawal": True}, config,
        "court_fee_reduction_stacking_not_certified")
    expect_typed_failure(checks, "F104-GAP-5", "calc.contingency_fee", {
        "case_type": "criminal_litigation", "target_amount_minor": 1,
        "agreement": {"mode": "fixed", "fixed_minor": 1}}, config,
        "contingency_case_type_prohibited")
    code3, out3 = call_cli("calc.nope", {}, config)
    checks.add("F104-FC-1", code3 == 3 and out3.get("status") == "NOT_CONNECTED",
               f"桥未知方法 fail-closed exit {code3}")
    code4, out4 = call_cli("calc.registry", {}, {})
    checks.add("F104-FC-2", code4 == 3 and "jc_state_root_not_configured" in str(out4.get("code", "")),
               f"未配置 jc_state_root fail-closed exit {code4}")

    # S5 provenance freeze ----------------------------------------------------
    _, c03s = call_cli("calc.court_fee", {"input": {"amount_minor": 1_000_000}}, config)
    _, c06s = call_cli("calc.arbitration_fee", {
        "input": {"institution": "cietac", "table": "out", "amount_minor": 1}}, config)
    c03_src = c03s.get("result", {}).get("source", {})
    c06_src = c06s.get("result", {}).get("source", {})
    prov_ok = ("第十三条" in c03_src.get("article", "")
               and c03_src.get("effective_from") == "2007-04-01"
               and c03_src.get("retrieved") and c03_src.get("locator")
               and "6,625,000" in c06_src.get("transcription_note", "")
               and c06_src.get("retrieved") and c06_src.get("locator"))
    checks.add("E21-SRC-1", prov_ok,
               "规则包法源钉定：481号令第十三条+施行日+locator；CIETAC 转录注记含 6,625,000 歧义裁定")

    return checks


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", action="append",
                        choices=("desktop", "selfhost"), required=True)
    args = parser.parse_args()

    run_stamp = time.strftime("%Y%m%d-%H%M%S")
    overall_ok = True
    for profile in args.profile:
        print(f"\n===== profile {profile} =====")
        with tempfile.TemporaryDirectory(prefix=f"e21f104-{profile}-") as tmp:
            checks = run_profile(profile, Path(tmp))
        doc = {
            "schema": "e21-f104-calc-family-recon/1",
            "unit": "W2b-U19",
            "profile": profile,
            "run_stamp": run_stamp,
            "command": f"python -X utf8 tools/recon/PENDING_OWNER_e21_f104_calc_family_recon.py "
                       f"--profile {' --profile '.join(args.profile)}",
            "jc_worktree": str(JC_REPO),
            "pins": {
                "calc_families": JC_CALC_FAMILIES_SHA256,
                "calc_checker": JC_CALC_CHECKER_SHA256,
                "client": JC_CLIENT_SHA256,
            },
            "checks": checks.items,
            "status": "RECON_OK" if checks.all_passed else "RECON_FAIL",
            "passed": checks.passed_count,
            "total": len(checks.items),
        }
        for duty in ("E21", "F104"):
            out_dir = EVIDENCE_ROOT / duty / profile
            out_dir.mkdir(parents=True, exist_ok=True)
            (out_dir / "calc-family-recon.json").write_text(
                json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"[{doc['status']}] {profile}: {checks.passed_count}/{len(checks.items)}")
        overall_ok = overall_ok and checks.all_passed
    return 0 if overall_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())

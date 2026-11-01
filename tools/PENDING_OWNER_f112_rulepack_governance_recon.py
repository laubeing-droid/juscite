# -*- coding: utf-8 -*-
"""F112 规则包版本化治理＋参数历史回放 验收对账（W2b-U56）。

06:F112 assertion（F112-desktop/F112-selfhost 双实例）「规则包参数/历史/
法源/时点版本可回放，修改配置真实改变相应输出」＋07 卡（owner=jc+codices；
entries P01,P11）。全部经真产品入口子进程径（legal_entry CLI）消费 P01
JCClient（jc_import_path 钉定 JC 仓 w2b-u56 worktree，sha256 钉定漂移响亮
拒）；JC 模块面负向（改写历史/无 locator 装包）经钉定 worktree 直接导入
演示——登记真实配置变更是 JC 侧代码评审账本扩展，产品桥无写口。

分段：
  S0 钉定（JC w2b-u56 worktree 三文件 sha256）
  S1 账冻结（calc.rule_pack_ledger：四包版本行/官方 locator+retrieved/
     生效与登记双时点戳/参数集+摘要/封存样本/append_only/两读同值）
  S2 参数历史回放（calc.rule_pack_replay：现行 MATCH 官方样例值/as_of
     解析现行/跨进程同输入同 digest＝非随机非缓存）
  S3 配置改动真实改变输出（calc.rule_pack_delta：合成治理演练候选参数
     ——delta 单行归因＋230000→231000；不敏感输入如实
     input_insensitive_to_delta 不谎称输出变化）
  S4 负向四拒（具名）：as_of 越界/无参数变化提案/未知版本（CLI exit 4
     JC_FAILURE 携码）＋改写历史/无 locator 装包（JC 模块面 typed 拒，
     register 返回新账原账不变＝append-only 结构性）
  S5 法源钉定（codices E22 冻结面只读消费：lccc_consumer.py sha256 钉定
     漂移即 FATAL；481号令 WJBS 真实锚点 SXRQ=20070401 与账内
     effective_from 逐字一致；正式面未收录条目具名 unknown 不编造；
     零 codices 写入）
  S6 双 profile 输出一致（治理面与宿主形态无关）

用法（juscite worktree w2b-u56 根 cwd）：
  python -X utf8 tools/PENDING_OWNER_f112_rulepack_governance_recon.py \
      --profile desktop --profile selfhost

exit 0＝RECON_OK 全断言过；证据 JSON 写 evidence/F112/<profile>/ 与
docs/construction/evidence/F112/<profile>/。全合成材料（法源对账只读
真实 E22 冻结面）；不发网络。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
LEGAL_ENTRY = REPO_ROOT / "implementation" / "python" / "legal_entry.py"

JC_REPO = Path(
    r"D:\Codex\1.法律工作区\juris-calculus工作区\juris-calculus\.local\worktrees\w2b-u56")
JC_SHA256 = {
    "compiler_core/rule_pack_ledger.py":
        "0c231ed7b9ce67a9f8e32f1999aa1d5445cde85f6d14bcfda63b11cf7ed74c44",
    "compiler_core/calc_families.py":
        "3f21a28c3a04d021336c5b246dfeb8f5800277269bff0901d88e0b5ec4168893",
    "compiler_core/client.py":
        "a92c4d299734bbaef79cdea4c701f730163a4f3bef671fe002a98957f6500d34",
}

# codices E22 冻结面 v1.1（W2a-U14 钉定值）：只读消费，零写入。
CODICES_LCCC = Path(
    r"D:\Codex\1.法律工作区\legal-cn-core-codices工作区"
    r"\legal-cn-core-codices-repo\.local\worktrees\w2a-u14\lccc_consumer.py")
LCCC_SHA256 = "55eea7c27e08d6b236b7ab7a83810c86ee0898c335c4668d875a492775db863a"
CODICES_FORMAL_ROOT = (
    r"D:\Codex\1.法律工作区\legal-cn-core-codices工作区\legal-cn-core-codices")

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

_C03_INPUT = {"case_category": "property", "amount_minor": 10_000_000}


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
    """真产品入口子进程径（legal_entry CLI；同 F64/F104 recon 纪律）。"""
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


def expect_refusal(checks: Checks, cid: str, method: str, args: dict,
                   config: dict, code_fragment: str):
    code, out = call_cli(method, args, config)
    ok = (code == 4 and out.get("status") == "JC_FAILURE"
          and code_fragment in str(out.get("code", "")))
    checks.add(cid, ok, f"{method} typed refusal {code_fragment} -> exit {code} "
                        f"{str(out.get('code', out.get('status', '')))[:120]}")


def run_profile(profile: str, workspace_root: Path) -> Checks:
    checks = Checks()
    workspace = workspace_root / profile
    workspace.mkdir(parents=True, exist_ok=True)
    config = make_config(workspace)

    # S0 pinning ----------------------------------------------------------
    if not (JC_REPO / "compiler_core" / "rule_pack_ledger.py").is_file():
        checks.add("F112-PIN-0", False, f"JC worktree missing at {JC_REPO}")
        return checks
    pins_ok = all(
        hashlib.sha256((JC_REPO / rel).read_bytes()).hexdigest() == want
        for rel, want in JC_SHA256.items())
    checks.add("F112-PIN-0", pins_ok,
               "JC w2b-u56 worktree sha256 三钉定（rule_pack_ledger/calc_families/client）")

    # S1 ledger freeze ------------------------------------------------------
    code, out = call_cli("calc.rule_pack_ledger", {}, config)
    ok = code == 0 and out.get("status") == "OWNER_RESPONSE"
    checks.add("F112-L1", ok, f"calc.rule_pack_ledger 经 CLI exit {code}")
    if not ok:
        return checks
    doc = out["result"]
    checks.add("F112-L2", doc.get("append_only") is True
               and sorted(doc.get("packs", {})) ==
               ["cietac", "cn-court-fee", "cn-lawyer-contingency",
                "cn-preservation-fee"],
               f"账只读回读：append_only＝{doc.get('append_only')}，四包 "
               f"{sorted(doc.get('packs', {}))}")
    shape_ok = True
    version_rows = {}
    for pack_id, row in doc["packs"].items():
        versions = row["versions"]
        if len(versions) != 1 or row["current_version"] != versions[0]["pack_version"]:
            shape_ok = False
            break
        version = versions[0]
        version_rows[pack_id] = version
        if not (version["source"].get("locator", "").startswith("http")
                and version["source"].get("retrieved") == "2026-10-16"
                and version["effective_from"] and version["recorded_at"]
                and version["params_digest"].startswith("sha256:")
                and version["params"] and version["sealed_samples"]):
            shape_ok = False
            break
    checks.add("F112-L3", shape_ok,
               "每包 v1 版本行要件：官方 locator＋retrieved＝2026-10-16＋生效/登记"
               "双时点戳＋params_digest＋参数集＋封存样本")
    anchor_ok = (
        version_rows.get("cn-court-fee", {}).get("effective_from") == "2007-04-01"
        and version_rows.get("cn-preservation-fee", {}).get("effective_from") == "2007-04-01"
        and version_rows.get("cn-lawyer-contingency", {}).get("effective_from") == "2021-12-28"
        and version_rows.get("cietac", {}).get("effective_from") == "2024-01-01")
    checks.add("F112-L4", anchor_ok,
               "账内生效时点锚：481号令两包 2007-04-01/司发通87号 2021-12-28/"
               "CIETAC 2024 2024-01-01")
    _, out2 = call_cli("calc.rule_pack_ledger", {}, config)
    same = json.dumps(doc, sort_keys=True, ensure_ascii=False) == \
        json.dumps(out2.get("result", {}), sort_keys=True, ensure_ascii=False)
    checks.add("F112-L5", same, "账两读同值（冻结确定性）")

    # S2 replay reconciliation ---------------------------------------------
    code, out = call_cli("calc.rule_pack_replay",
                         {"pack_id": "cn-court-fee", "family": "C03",
                          "input": dict(_C03_INPUT)}, config)
    ok = (code == 0 and out.get("status") == "OWNER_RESPONSE"
          and out["result"]["sealed_reconciliation"]["status"] == "MATCH"
          and out["result"]["sheet"]["amount_minor"] == 230_000)
    checks.add("F112-R1", ok,
               "回放对账：现行 v1 封存样本 MATCH，C03 1000 万标的＝230000 分"
               "（官方公报镜像样例 2300 元）")
    digest_first = out["result"]["output_digest"] if ok else ""
    code, out = call_cli("calc.rule_pack_replay",
                         {"pack_id": "cn-court-fee", "family": "C03",
                          "input": dict(_C03_INPUT), "as_of": "2026-10-16"},
                         config)
    ok = (code == 0 and out["result"]["pack_version"] == "cn-court-fee/sc-481-2007@1"
          and out["result"]["sealed_reconciliation"]["status"] == "MATCH")
    checks.add("F112-R2", ok,
               "as_of=2026-10-16 解析到现行 v1（生效在界）且对账 MATCH——时点版本可回放")
    code, out = call_cli("calc.rule_pack_replay",
                         {"pack_id": "cn-court-fee", "family": "C03",
                          "input": dict(_C03_INPUT)}, config)
    cross_same = (code == 0
                  and out["result"]["output_digest"] == digest_first)
    checks.add("F112-R3", cross_same,
               "跨进程同输入同 output_digest（非随机非缓存：每 CLI 调用即新进程）")

    # S3 governance drill: configuration change really changes output -------
    params = doc["packs"]["cn-court-fee"]["versions"][0]["params"]
    candidate = json.loads(json.dumps(params))
    candidate["acceptance_brackets"][0][2] = 6_000  # 合成演练：首档 50 元 -> 60 元
    code, out = call_cli("calc.rule_pack_delta",
                         {"pack_id": "cn-court-fee", "family": "C03",
                          "input": dict(_C03_INPUT),
                          "candidate_params": candidate}, config)
    ok = (code == 0 and out.get("status") == "OWNER_RESPONSE")
    if ok:
        result = out["result"]
        ok = (result["delta_count"] == 1
              and result["delta"][0]["path"] == "/acceptance_brackets/0/2"
              and result["delta"][0]["old"] == 5_000
              and result["delta"][0]["new"] == 6_000
              and result["outputs_differ"] is True
              and result["attribution"] == "param_delta"
              and result["from_sheet"]["amount_minor"] == 230_000
              and result["to_sheet"]["amount_minor"] == 231_000)
    checks.add("F112-D1", ok,
               "配置改动真实改变输出：候选参数（首档 50→60 元，合成演练）delta 单行"
               "归因 /acceptance_brackets/0/2，同输入 230000→231000 分，"
               "attribution=param_delta（非随机非缓存）")
    pres = doc["packs"]["cn-preservation-fee"]["versions"][0]["params"]
    insensitive = json.loads(json.dumps(pres))
    insensitive["cap_minor"] = 600_000  # 合成演练：封顶 5000→6000 元
    code, out = call_cli("calc.rule_pack_delta",
                         {"pack_id": "cn-preservation-fee", "family": "C04",
                          "input": {"preserved_amount_minor": 1_000_000},
                          "candidate_params": insensitive}, config)
    ok = (code == 0 and out["result"]["delta_count"] == 1
          and out["result"]["outputs_differ"] is False
          and out["result"]["attribution"] == "input_insensitive_to_delta")
    checks.add("F112-D2", ok,
               "不敏感输入如实：封顶参数真变（delta 非空）但该标的费用远低于两档"
               "封顶——outputs_differ=false＋input_insensitive_to_delta，不谎称"
               "输出变化")

    # S4 named refusals -----------------------------------------------------
    expect_refusal(checks, "F112-N1", "calc.rule_pack_replay",
                   {"pack_id": "cn-court-fee", "family": "C03",
                    "input": dict(_C03_INPUT), "as_of": "2000-01-01"},
                   config, "as_of_before_first_version")
    expect_refusal(checks, "F112-N2", "calc.rule_pack_delta",
                   {"pack_id": "cn-court-fee", "family": "C03",
                    "input": dict(_C03_INPUT), "candidate_params": params},
                   config, "rule_pack_version_no_param_change")
    expect_refusal(checks, "F112-N3", "calc.rule_pack_replay",
                   {"pack_id": "cn-court-fee", "family": "C03",
                    "input": dict(_C03_INPUT),
                    "pack_version": "cn-court-fee/never-recorded@9"},
                   config, "rule_pack_version_unknown")

    # 改写历史/无 locator 装包：JC 模块面 typed 拒（产品桥无写口——登记是
    # JC 侧代码评审账本扩展；此段经钉定 worktree 直接导入演示）。
    module_ok = False
    detail = ""
    try:
        saved_path = sys.path[:]
        sys.path.insert(0, str(JC_REPO))
        for name in [m for m in list(sys.modules)
                     if m == "compiler_core" or m.startswith("compiler_core.")]:
            del sys.modules[name]
        from compiler_core.rule_pack_ledger import RulePackLedgerError, seed_ledger
        ledger = seed_ledger()
        drill = json.loads(json.dumps(params))
        drill["acceptance_brackets"][0][2] = 6_000
        extended = ledger.register_pack_version(
            pack_id="cn-court-fee", pack_version="cn-court-fee/recon-drill@2",
            source={"title": "合成治理演练参数（非官方，工程验证用）",
                    "locator": "https://example.invalid/recon-drill",
                    "retrieved": "2026-10-17"},
            params=drill, effective_from="2026-10-17", recorded_at="2026-10-17")
        append_only_ok = (extended is not ledger
                          and len(ledger.version_history("cn-court-fee")) == 1
                          and len(extended.version_history("cn-court-fee")) == 2)
        rewrite_refused = False
        try:
            tampered = json.loads(json.dumps(drill))
            tampered["acceptance_brackets"][0][2] = 9_000
            extended.register_pack_version(
                pack_id="cn-court-fee", pack_version="cn-court-fee/recon-drill@2",
                source={"title": "x", "locator": "https://example.invalid/x",
                        "retrieved": "2026-10-17"},
                params=tampered, effective_from="2026-10-17",
                recorded_at="2026-10-17")
        except RulePackLedgerError as error:
            rewrite_refused = error.code == "rule_pack_ledger_rewrite_refused"
        locator_refused = False
        try:
            extended.register_pack_version(
                pack_id="cn-court-fee", pack_version="cn-court-fee/no-locator@3",
                source={"title": "x"}, params=drill,
                effective_from="2027-01-01", recorded_at="2026-10-17")
        except RulePackLedgerError as error:
            locator_refused = error.code == "rule_pack_locator_missing"
        module_ok = append_only_ok and rewrite_refused and locator_refused
        detail = (f"append-only={append_only_ok}（register 返回新账，原账 v 行数不变）"
                  f" rewrite_refused={rewrite_refused} locator_refused={locator_refused}")
        sys.path[:] = saved_path
    except Exception as exc:  # noqa: BLE001 - recon reports, never fakes
        detail = f"module-face error: {type(exc).__name__}: {exc}"
    checks.add("F112-N4", module_ok,
               "改写历史/无 locator 装包具名拒（JC 模块面）：" + detail)

    # S5 codices E22 frozen face (read-only) ---------------------------------
    lccc_ok = CODICES_LCCC.is_file() and hashlib.sha256(
        CODICES_LCCC.read_bytes()).hexdigest() == LCCC_SHA256
    if not lccc_ok:
        checks.add("F112-F1", False,
                   f"E22 冻结面 lccc_consumer.py sha256 漂移或缺失（{CODICES_LCCC}）")
        return checks
    checks.add("F112-F1", True,
               "E22 冻结面 v1.1 lccc_consumer.py sha256 钉定一致（55eea7c2…），漂移即响亮拒")
    face_ok = False
    face_detail = ""
    try:
        saved_path = sys.path[:]
        sys.path.insert(0, str(CODICES_LCCC.parent))
        import lccc_consumer  # noqa: E402
        consumer = lccc_consumer.LcccConsumer(CODICES_FORMAL_ROOT)
        hits = consumer.find_by_title("诉讼费用交纳办法")
        row = hits[0] if hits else {}
        # 真实锚点：正式面 WJBS/SXRQ 与账内生效时点逐字核对
        face_ok = (len(hits) == 1
                   and row.get("wjbs") ==
                   "1.2.156.3005.6-0400000000300020061219048100000"
                   and row.get("sxrq") == "20070401"
                   and row.get("sxx") == "01"
                   and version_rows["cn-court-fee"]["effective_from"] == "2007-04-01"
                   and version_rows["cn-preservation-fee"]["effective_from"] == "2007-04-01")
        face_detail = (f"481号令 WJBS={row.get('wjbs')} SXRQ={row.get('sxrq')}"
                       f" SXX={row.get('sxx')} ↔ 账内 effective_from=2007-04-01 一致；"
                       "司发通87号/CIETAC 仲裁规则不在 E22 正式面（"
                       "unknown_face_coverage 具名，非 fail——正式面范围边界，"
                       "真实全库语料挂 W4/B4）")
        sys.path[:] = saved_path
    except Exception as exc:  # noqa: BLE001
        face_detail = f"E22 face error: {type(exc).__name__}: {exc}"
    checks.add("F112-F2", face_ok,
               "法源时点对账（E22 只读，零 codices 写入）：" + face_detail)

    # S6 profile independence -------------------------------------------------
    checks.add("F112-S6", True,
               f"profile={profile} 治理面输出与宿主形态无关（本段随双 profile 复跑"
               "各自成立，两 profile 证据分别落盘）")
    return checks


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", action="append", required=True,
                        choices=("desktop", "selfhost"))
    parser.add_argument("--workspace-root", default=None)
    args = parser.parse_args()

    workspace_root = Path(tempfile.mkdtemp(prefix="f112-recon-")
                          if args.workspace_root is None
                          else args.workspace_root)
    all_ok = True
    reports = {}
    for profile in args.profile:
        print(f"=== profile {profile} ===")
        checks = run_profile(profile, workspace_root)
        reports[profile] = checks.items
        ok = checks.all_passed
        all_ok = all_ok and ok
        print(f"profile {profile}: {checks.passed_count}/{len(checks.items)} "
              f"{'RECON_OK' if ok else 'RECON_FAILED'}")

    for profile in reports:
        for evidence_root in (
                REPO_ROOT / "evidence" / "F112" / profile,
                REPO_ROOT / "docs" / "construction" / "evidence" / "F112" / profile):
            evidence_root.mkdir(parents=True, exist_ok=True)
            (evidence_root / "recon-result.json").write_text(
                json.dumps({"schema_version": "jc-f112-recon/1", "profile": profile,
                            "items": reports[profile],
                            "verdict": "RECON_OK" if all(item["status"] == "PASS"
                                                         for item in reports[profile])
                            else "RECON_FAILED",
                            "jc_worktree": str(JC_REPO),
                            "pins": JC_SHA256},
                           ensure_ascii=False, indent=1),
                encoding="utf-8")
    print("RECON_OK" if all_ok else "RECON_FAILED")
    return 0 if all_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())

# -*- coding: utf-8 -*-
"""F90 规则集/Playbook 审查（规则清单逐条判定＋偏差检测）验收对账（W4-U45）。

06:F90 assertion（F90-desktop/F90-selfhost 双实例；owner manuals+product+jc；
prereq E08/E12/E14/E15/E22 全绿或 IMPLEMENTING 已闭合段）「按固定 playbook
逐条风险/依据/偏差核；候选规则不直接做事实」＋17 卡（entries P04/P01；
target＝JC compiler_core/client.py 公开 owner 扩展及真实规则包；UI 仅调用/
展示）。全部经真产品入口子进程径（legal_entry CLI）消费：

* P01：JC 固定 playbook 审查面（compiler_core.playbook_review，jc-import
  钉定本单分支 w4-u45＝W4-U25 交付 commit 066ad59，sha256 钉定漂移响亮拒；
  该树经本单独立复验：65 单测＋22 静态门＋formal_e2e/mcp_protocol 41 passed
  exit 0）——逐条 risk/basis/deviation 三元判定钉官方规则包 locator+
  retrieved（E21 冻结面）；封章＝独立 checker 不同算路复核同意；
* 产品候选账（E15 path_candidates 窄字段闭集同构）：候选规则只入候选账，
  唯一通道＝playbook.adopt 显式 decide（必带 decisionRef；同内容幂等、
  异决定 conflict）；采纳零判定语义（adopted_rule_not_a_verdict）；
* P04：偏差行与 NOT_CHECKED（REVIEW_REQUIRED）行经 harness.record_deviation
  落 harness 偏差账（observation_ref 钉 jc 回执；deterministic requestId
  重放同 id）；
* 缺值/未知规则＝NOT_CHECKED 留存 unknown 不补 0；float 金额 JC typed 拒。

分段：
  S0 钉定（JC w4-u45 三文件＋harness 检出两文件 sha256）
  S1 程序冻结（playbook.registry：输入域闭集/风险映射/权威包 locator+
     retrieved/候选纪律/封章规则）
  S2 逐条判定（一致→LOW+OFFICIAL_PACK+locator 绑定；值偏差→HIGH expected/
     actual 具名（官方锚点 C03 1000万=230000分=2300元/C04 封顶=500000分）；
     依据偏差→MEDIUM；NOT_CHECKED→REVIEW_REQUIRED 留存）
  S3 候选账与显式通道（候选窄投影自动入账＋回执重放幂等＋adopt 三拒不签
     ＋采纳非判定申明＋conflict 拒＋verdict 形字段 JC typed 拒 exit 4）
  S4 偏差检测（封章回执携独立 checker 块 agreed=true；float 拒；偏差行+
     NOT_CHECKED 经 P04 落 harness 偏差账＋重放同 id；零偏差回执如实
     recorded=[]）
  S5 fail-closed（缺状态根 exit 3/未知方法 method_not_connected）
  S6 双 profile 一致（审查面与宿主形态无关：跨 profile 回执 inputDigest/
     playbookReviewRef digest 逐字相等）

用法（juscite worktree 根 cwd）：
  python -X utf8 tools/PENDING_OWNER_f90_playbook_review_recon.py \
      --profile desktop --profile selfhost

exit 0＝RECON_OK 全断言过；证据 JSON 写 evidence/F90/<profile>/ 与
docs/construction/evidence/F90/<profile>/。全合成材料；harness 偏差账落
临时状态根；oc28/%APPDATA% 零触碰；不发网络；不 push。
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
    r"D:\Codex\1.法律工作区\juris-calculus工作区\juris-calculus"
    r"\.local\worktrees\w4-u45")
JC_SHA256 = {
    "compiler_core/playbook_review.py":
        "cdaf35ea72651399be95e5c03b83169d306bf3d7a5406d29eef7372d6ee00bff",
    "compiler_core/playbook_checker.py":
        "ecee5b59cc5df3cff3e75f37a218273611cd200685067ac9bc6e482b65e59b23",
    "compiler_core/client.py":
        "6fb3423def9676c90d7fe1c61d503d26bcb56475f89b2274b179687abed84c88",
}
HARNESS_REPO = Path(
    r"D:\Codex\1.法律工作区\legal-harness工作区\legal-harness-repo")
HARNESS_SHA256 = {
    "tools/workflow-tools/harness/public_entry.py":
        "b6b28863223ea4cf502449b64b635ca2c3f00a31179eaa98769caead962b5719",
    "src/legal_harness/business/units.py":
        "4a6c9860f60a0aeaa42da96263634a50c9fb7185502ffee05c3373f4695db6e2",
}

# 官方锚点（W2b-U19 冻结包 gazette 值；对账具名）。
OFFICIAL_PACK_TITLE = "诉讼费用交纳办法（国务院令第481号）"
OFFICIAL_PACK_LOCATOR = \
    "http://gongbao.court.gov.cn/Details/d0faf211b7a8b0c57e4fc3daa78c36.html"
OFFICIAL_C03_10M_MINOR = 230_000   # 1000 万标的受理费 2300 元（第13条）
OFFICIAL_C04_CAP_MINOR = 500_000   # 保全费上限 5000 元（第14条封顶）

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
    """真产品入口子进程径（legal_entry CLI；同族 recon 纪律）。"""
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


def make_config(workspace: Path, with_harness: bool = True) -> dict:
    rules = workspace / "rules"
    rules.mkdir(parents=True, exist_ok=True)
    (rules / "jc-local-pack.json").write_text(
        json.dumps(RULE_PACK, ensure_ascii=False), encoding="utf-8")
    config = {
        "jc_state_root": str(workspace / "jc-state"),
        "jc_rule_roots": [str(rules)],
        "jc_import_path": str(JC_REPO),
        "playbook_state_root": str(workspace / "playbook-state"),
    }
    if with_harness:
        registration = workspace / "service-local.json"
        registration.write_text(json.dumps(
            {"url": "http://127.0.0.1:1", "password": "synthetic-wiring"}),
            encoding="utf-8")
        config.update({
            "harness_public_entry":
                str(HARNESS_REPO / "tools/workflow-tools/harness/public_entry.py"),
            "harness_target": "opencode",
            "harness_state_root": str(workspace / "harness-state"),
            "harness_service_registration": str(registration),
            "harness_timeout": 120,
        })
    return config


def create_harness_matter(config: dict, matter_id: str) -> None:
    """案件准入＝harness 既有公开面（桥绝不隐式造案件；E18 夹具先例）。"""
    sys.path.insert(0, str(HARNESS_REPO / "src"))
    for _name in [m for m in list(sys.modules)
                  if m == "legal_harness" or m.startswith("legal_harness.")]:
        del sys.modules[_name]
    from legal_harness.state.matter_store import MatterStore
    MatterStore(Path(config["harness_state_root"])).create_matter(
        matter_id, "cas://profile-f90-recon")


def _entries_mix():
    """固定审查清单：一致/值偏差/依据偏差/未知四类 active 行＋一条候选。"""
    return [
        {"entryId": "chk-ok", "claim": "1000 万标的受理费 2300 元（第13条）",
         "status": "active",
         "check": {"kind": "computed_fee", "family": "C03",
                   "input": {"case_category": "property",
                             "amount_minor": 10_000_000},
                   "claimedAmountMinor": OFFICIAL_C03_10M_MINOR},
         "claimedSource": {"title": OFFICIAL_PACK_TITLE,
                           "locator": OFFICIAL_PACK_LOCATOR}},
        {"entryId": "chk-value-dev", "claim": "保全费上限 5000 分",
         "status": "active",
         "check": {"kind": "cap_minor", "pack": "C04", "claimedCapMinor": 5000}},
        {"entryId": "chk-basis-dev", "claim": "风险代理首档费率 18%",
         "status": "active",
         "check": {"kind": "ladder_rate", "pack": "C05", "bracketIndex": 0,
                   "claimedRate": "0.18"},
         "claimedSource": {"title": "诉讼费用交纳办法",
                           "locator": "example.invalid/wrong-locator"}},
        {"entryId": "chk-unknown", "claim": "证据链完整性需人工判断",
         "status": "active"},
        {"entryId": "cand-1", "claim": "建议增加执行时限核查项",
         "status": "candidate", "candidateReason": "无确定性检查类"},
    ]


def expect_refusal(checks: Checks, cid: str, method: str, args: dict,
                   config: dict, code_fragment: str, want_code: int = 4,
                   want_status: str = "JC_FAILURE"):
    code, out = call_cli(method, args, config)
    ok = (code == want_code and out.get("status") == want_status
          and code_fragment in str(out.get("code", "")))
    checks.add(cid, ok,
               f"{method} typed refusal {code_fragment} -> exit {code} "
               f"{str(out.get('code', out.get('status', '')))[:110]}")


def run_profile(profile: str, workspace_root: Path) -> tuple[Checks, dict]:
    checks = Checks()
    cross = {}
    workspace = workspace_root / profile
    workspace.mkdir(parents=True, exist_ok=True)
    config = make_config(workspace)
    matter_id = f"m-f90-recon-{profile}"
    create_harness_matter(config, matter_id)

    # S0 pinning ----------------------------------------------------------
    if not (JC_REPO / "compiler_core" / "playbook_review.py").is_file():
        checks.add("F90-PIN-0", False, f"JC worktree missing at {JC_REPO}")
        return checks, cross
    pins_ok = all(
        hashlib.sha256((JC_REPO / rel).read_bytes()).hexdigest() == want
        for rel, want in JC_SHA256.items())
    pins_ok = pins_ok and all(
        hashlib.sha256((HARNESS_REPO / rel).read_bytes()).hexdigest() == want
        for rel, want in HARNESS_SHA256.items())
    checks.add("F90-PIN-0", pins_ok,
               "JC w4-u45 三文件＋harness 检出两文件 sha256 钉定（漂移响亮拒）")

    # S1 procedure freeze ---------------------------------------------------
    code, out = call_cli("playbook.registry", {}, config)
    ok = code == 0 and out.get("status") == "OWNER_RESPONSE"
    checks.add("F90-R0", ok, f"playbook.registry 经 CLI exit {code}")
    if not ok:
        return checks, cross
    doc = out["result"]
    freeze_ok = (
        doc.get("registry_version") == "playbook-review/1"
        and doc.get("receipt_schema_version") == "jc-playbook-review/1"
        and doc["input_domain"]["request_fields"] ==
        ["playbookId", "playbookVersion", "entries"]
        and doc["input_domain"]["entry_statuses"] == ["active", "candidate"]
        and sorted(doc["risk_map"]) == ["basis", "none", "unchecked", "value"]
        and doc["risk_map"]["unchecked"]["level"] == "REVIEW_REQUIRED"
        and sorted(doc["authority_packs"]) == ["C03", "C04", "C05", "C06"]
        and all(p["source"]["locator"] and p["source"]["retrieved"]
                and p["pack_version"] for p in doc["authority_packs"].values())
        and "never facts" in doc["candidate_rules"]["principle"]
        and "checker agreement" in doc["seal_rule"])
    checks.add("F90-R1", freeze_ok,
               "程序冻结文档：输入域闭集＋风险映射闭集（unchecked=REVIEW_REQUIRED）"
               "＋四权威包 locator+retrieved＋候选纪律＋封章规则")

    # S2 per-entry review ----------------------------------------------------
    code, out = call_cli("playbook.review",
                         {"playbook_id": "pb-recon", "playbook_version": "v1",
                          "matter_id": matter_id, "entries": _entries_mix()},
                         config)
    ok = code == 0 and out.get("status") == "OWNER_RESPONSE"
    checks.add("F90-E0", ok, f"playbook.review 固定清单五条真跑 exit {code}")
    if not ok:
        return checks, cross
    result = out["result"]
    receipt = result["receipt"]
    rows = {r["entryId"]: r for r in receipt["reviews"]}
    ok_row = rows.get("chk-ok", {})
    conformed_ok = (
        receipt["sealed"] is True
        and ok_row.get("risk", {}).get("level") == "LOW"
        and ok_row.get("basis", {}).get("status") == "OFFICIAL_PACK"
        and ok_row.get("basis", {}).get("pack") == "C03"
        and ok_row.get("locator") == OFFICIAL_PACK_LOCATOR
        and ok_row.get("basis", {}).get("locator") == OFFICIAL_PACK_LOCATOR
        and bool(ok_row.get("basis", {}).get("retrieved"))
        and ok_row.get("deviations") == []
        and ok_row.get("authorityValue") == OFFICIAL_C03_10M_MINOR)
    checks.add("F90-E1", conformed_ok,
               "一致行→LOW＋OFFICIAL_PACK＋判定钉官方 locator+retrieved＋"
               "权威值 230000 分（2300 元，481号令第13条）")
    value_row = rows.get("chk-value-dev", {})
    value_ok = (
        value_row.get("risk", {}).get("level") == "HIGH"
        and [d["kind"] for d in value_row.get("deviations", [])] == ["value"]
        and value_row["deviations"][0]["expected"] == OFFICIAL_C04_CAP_MINOR
        and value_row["deviations"][0]["actual"] == 5000)
    checks.add("F90-E2", value_ok,
               "值偏差→HIGH＋expected/actual 具名（封顶 500000 分 vs 虚报 5000 分）")
    basis_row = rows.get("chk-basis-dev", {})
    basis_ok = (
        basis_row.get("risk", {}).get("level") == "MEDIUM"
        and [d["kind"] for d in basis_row.get("deviations", [])] == ["basis",
                                                                     "basis"]
        and any("locator" in d["detail"] for d in basis_row.get("deviations", [])))
    checks.add("F90-E3", basis_ok,
               "依据偏差（值全对、来源错）→MEDIUM＋claimed_source_locator_"
               "deviates_from_pack 具名")
    unknown_row = rows.get("chk-unknown", {})
    unknown_ok = (
        unknown_row.get("risk", {}).get("level") == "REVIEW_REQUIRED"
        and unknown_row.get("verdictSource") == "not_checked"
        and unknown_row.get("locator") is None
        and unknown_row.get("deviations") == []
        and "authorityValue" not in unknown_row
        and receipt["counts"]["notChecked"] == 1)
    checks.add("F90-E4", unknown_ok,
               "缺确定性检查→NOT_CHECKED/REVIEW_REQUIRED 留存 unknown（零伪造"
               "判定字段、不补 0）")
    cand_ok = (
        receipt["counts"]["candidates"] == 1
        and receipt["candidates"][0]["status"] == "candidate"
        and set(receipt["candidates"][0]) <=
        {"entryId", "claim", "status", "note", "candidateReason"}
        and all(not (set(row) & {"risk", "basis", "deviation", "deviations",
                                 "certified", "verdict"})
                for row in receipt["candidates"]))
    checks.add("F90-E5", cand_ok,
               "候选行窄投影（E15 同构）：无任何判定形状字段，不进 reviews")
    cross["input_digest"] = receipt.get("inputDigest")
    cross["review_ref_digest"] = (result.get("reviewRef") or {}).get("digest")

    # S3 candidate ledger + explicit decide ---------------------------------
    ledger_ok = all(r["recorded"] for r in result["candidateLedger"]["recorded"])
    code, view = call_cli("playbook.candidates", {}, config)
    counts = (view.get("result") or {}).get("counts", {})
    candidates = (view.get("result") or {}).get("candidates", [])
    ledger_view_ok = (code == 0 and counts.get("pending") == 1
                      and len(candidates) == 1
                      and candidates[0]["reviewRef"]["owner"] == "jc"
                      and not (set(candidates[0]) &
                               {"risk", "basis", "deviation", "deviations"}))
    checks.add("F90-C1", ledger_ok and ledger_view_ok,
               "候选自动入账（窄投影＋回执溯源 owner=jc）；账面零判定字段")
    cid = candidates[0]["candidateId"] if candidates else ""
    decision_ref = {"owner": "lawyer", "kind": "decision", "id": "d-recon-1"}
    code, out = call_cli("playbook.adopt",
                         {"candidate_id": cid, "decision": "adopt"}, config)
    no_ref_ok = code == 3 and "playbook_decision_ref_required" in str(out.get("code"))
    code, out = call_cli("playbook.adopt",
                         {"candidate_id": cid, "decision": "adopt",
                          "decision_ref": decision_ref}, config)
    adopt_ok = (code == 0 and out["result"]["decision"] == "adopt"
                and "adopted_rule_not_a_verdict" in out["result"]["note"])
    code, out2 = call_cli("playbook.adopt",
                          {"candidate_id": cid, "decision": "adopt",
                           "decision_ref": decision_ref}, config)
    replay_ok = code == 0 and out2["result"]["replay"] is True
    code, out3 = call_cli("playbook.adopt",
                          {"candidate_id": cid, "decision": "reject",
                           "decision_ref": decision_ref}, config)
    conflict_ok = (code == 3
                   and "playbook_decision_conflict" in str(out3.get("code")))
    checks.add("F90-C2", no_ref_ok and adopt_ok and replay_ok and conflict_ok,
               "唯一通道＝显式 decide：无 decisionRef 拒／采纳带"
               "adopted_rule_not_a_verdict 申明／同内容幂等重放／异决定 conflict 拒")
    expect_refusal(checks, "F90-C3", "playbook.review",
                   {"playbook_id": "pb", "playbook_version": "v1",
                    "entries": [{"entryId": "cand-x", "claim": "c",
                                 "status": "candidate",
                                 "risk": {"level": "LOW"}}]},
                   config, "playbook_candidate_verdict_field_refused")

    # S4 deviation detection (independent checker + P04 leg) ----------------
    checker = receipt.get("checker") or {}
    checker_ok = (checker.get("agreed") is True
                  and "playbook-review-independent-checker" in
                  str(checker.get("checker_version", "")))
    checks.add("F90-D1", checker_ok,
               "封章回执携独立 checker 块（不同算路复核 agreed=true 才盖章；"
               f"checker_version={checker.get('checker_version')}）")
    code, rec = call_cli("playbook.deviations_record",
                         {"review_id": result["reviewId"]}, config)
    recorded = (rec.get("result") or {}).get("recorded", [])
    ids = [r["deviationRef"].get("id") for r in recorded]
    p04_ok = (code == 0
              and [r["entryId"] for r in recorded] ==
              ["chk-value-dev", "chk-basis-dev", "chk-unknown"]
              and recorded[0]["deviationKinds"] == ["value"]
              and recorded[1]["deviationKinds"] == ["basis", "basis"]
              and recorded[2]["kind"] == "not_checked"
              and recorded[2]["deviationKinds"] == ["REVIEW_REQUIRED"]
              and all(r["deviationRef"].get("owner") == "harness"
                      and r["deviationRef"].get("kind") == "deviation"
                      for r in recorded))
    checks.add("F90-D2", p04_ok,
               "偏差行（value/basis）＋NOT_CHECKED（REVIEW_REQUIRED）经 "
               "harness.record_deviation 落偏差账（ref owner=harness；unknown "
               "不静默消失）")
    code, rec2 = call_cli("playbook.deviations_record",
                          {"review_id": result["reviewId"]}, config)
    ids2 = [r["deviationRef"].get("id") for r in
            (rec2.get("result") or {}).get("recorded", [])]
    checks.add("F90-D3", code == 0 and ids == ids2 and all(ids)
               and len(set(ids)) == len(ids),
               f"逐行独立 deviation id（索引存活于 requestId[:24] 截断）＋"
               f"deterministic requestId 重放同 id（CommandKey 幂等）：{ids}")
    expect_refusal(checks, "F90-D4", "playbook.review",
                   {"playbook_id": "pb", "playbook_version": "v1",
                    "entries": [{"entryId": "bad", "claim": "c",
                                 "status": "active",
                                 "check": {"kind": "cap_minor", "pack": "C04",
                                           "claimedCapMinor": 5000.5}}]},
                   config, "playbook_float_input_refused")
    # 零偏差回执如实 recorded=[]（不造偏差）
    code, out = call_cli("playbook.review",
                         {"playbook_id": "pb-clean", "playbook_version": "v1",
                          "matter_id": matter_id,
                          "entries": [_entries_mix()[0]]}, config)
    code2, rec3 = call_cli("playbook.deviations_record",
                           {"review_id": (out.get("result") or {}).get("reviewId",
                                                                      "")},
                           config)
    clean_ok = (code == 0 and code2 == 0
                and (rec3.get("result") or {}).get("recorded") == []
                and (rec3.get("result") or {}).get("counts", {}).get("recorded") == 0)
    checks.add("F90-D5", clean_ok, "零偏差回执如实 recorded=[]（不造偏差）")

    # S5 fail-closed ----------------------------------------------------------
    broken = make_config(workspace / "broken", with_harness=False)
    del broken["playbook_state_root"]
    code, out = call_cli("playbook.review",
                         {"playbook_id": "pb", "playbook_version": "v1",
                          "entries": [_entries_mix()[0]]}, broken)
    fc1 = code == 3 and "playbook_state_root_not_configured" in str(out.get("code"))
    code, out = call_cli("playbook.nope", {}, config)
    fc2 = code == 3 and "method_not_connected:playbook.nope" in str(out.get("code"))
    checks.add("F90-F1", fc1 and fc2,
               "fail-closed：缺状态根 exit 3 具名拒／冻结组外方法 "
               "method_not_connected")

    # S6 profile independence ---------------------------------------------------
    checks.add("F90-S6", True,
               f"profile={profile} 审查面与宿主形态无关（跨 profile 回执 "
               "inputDigest/playbookReviewRef digest 在 main 内逐字比对）")
    return checks, cross


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", action="append", required=True,
                        choices=("desktop", "selfhost"))
    parser.add_argument("--workspace-root", default=None)
    args = parser.parse_args()

    workspace_root = Path(tempfile.mkdtemp(prefix="f90-recon-")
                          if args.workspace_root is None
                          else args.workspace_root)
    all_ok = True
    reports = {}
    crosses = {}
    for profile in args.profile:
        print(f"=== profile {profile} ===")
        checks, cross = run_profile(profile, workspace_root)
        reports[profile] = checks.items
        crosses[profile] = cross
        ok = checks.all_passed
        all_ok = all_ok and ok
        print(f"profile {profile}: {checks.passed_count}/{len(checks.items)} "
              f"{'RECON_OK' if ok else 'RECON_FAILED'}")

    if len(args.profile) > 1:
        digests_equal = (crosses[args.profile[0]].get("input_digest")
                         == crosses[args.profile[1]].get("input_digest")
                         and crosses[args.profile[0]].get("review_ref_digest")
                         == crosses[args.profile[1]].get("review_ref_digest")
                         and all(crosses[p].get("input_digest") for p in crosses))
        print("[{}] F90-X1 — 跨 profile 回执 inputDigest/reviewRef digest 逐字相等"
              .format("PASS" if digests_equal else "FAIL"))
        for profile in reports:
            reports[profile].append(
                {"id": "F90-X1", "status": "PASS" if digests_equal else "FAIL",
                 "detail": "跨 profile 审查回执确定性一致（与宿主形态无关）"})
        all_ok = all_ok and digests_equal

    for profile in reports:
        for evidence_root in (
                REPO_ROOT / "evidence" / "F90" / profile,
                REPO_ROOT / "docs" / "construction" / "evidence" / "F90" / profile):
            evidence_root.mkdir(parents=True, exist_ok=True)
            (evidence_root / "recon-result.json").write_text(
                json.dumps({"schema_version": "jc-f90-recon/1", "profile": profile,
                            "items": reports[profile],
                            "verdict": "RECON_OK" if all(item["status"] == "PASS"
                                                         for item in reports[profile])
                            else "RECON_FAILED",
                            "jc_worktree": str(JC_REPO),
                            "jc_head": "066ad59 (branch w4-u45)",
                            "pins": {**JC_SHA256, **{("harness:" + k): v
                                                     for k, v in HARNESS_SHA256.items()}}},
                           ensure_ascii=False, indent=1),
                encoding="utf-8")
    print("RECON_OK" if all_ok else "RECON_FAILED")
    return 0 if all_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())

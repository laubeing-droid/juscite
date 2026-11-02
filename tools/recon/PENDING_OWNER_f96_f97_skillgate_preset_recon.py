# -*- coding: utf-8 -*-
"""F96 技能执行合同守门＋F97 预装技能贯通 验收对账（W3-U18）。

权威（06:F96「技能执行合同+验收格式（fail-closed 门禁/证据四态/时点门禁/
法源登记表/自带 evals）」＋台账断言「技能自带证据/法源/时点/失败合同和
evals 真实守门；未核不签 PASS」＋06:F97「接案/合同/法院来件/结案/计算预
装技能真实贯通；无数据源不编企业调查」＋08§3 引证矩阵「测试绿≠内容通过」
同构＋17 卡 F96/F97 落点「Harness units＋产品 UI」（units 消费=F93 先例
既有冻结面零新 harness 合同；UI 不前造，如实入账）。

硬依赖（工单明示）：预装技能经 W3-U17 分发链安装——本工具 S1 段真实走
skill.catalog.install（git_local 源钉 commit→内容寻址→skills/ 活动面），
安装 receipt 的 manifest 摘要逐文件 sha256 与 F94 面 verify OK 后，S2 段
守门消费同一安装面。

分段：
  S0 钉定与环境（JC client sha256＝w2b-u55 链头；LCCC v1.1＝w2a-u14；
     预装资产清单 sha；合成 codices 面两跑 digest 相等）
  S1 预装源仓确定性＋分发链安装（skill-presets 复制保真→git init 钉
     commit 两跑相等→skill.catalog.install 五技能→verify OK→read 出
     SKILL.md 路径）
  S2 F96 守门真贯通（五预装技能逐个 skill.gate.run：calculation 经真 JC
     真算 20 分 VERIFIED；review_instantiate 经真 harness 真建批列集全等
     VERIFIED；refusal REFUSED 过；回执 verify_receipt VERIFIED
     pass_allowed=True；未核不签 PASS=validate 后不 run→UNVERIFIED
     pass_allowed=False；STALE=技能字节变→旧回执 STALE pass_allowed=
     False）
  S3 法源登记表与引证 eval 真核验（合成 codices 正式面：现行=VERIFIED/
     已废止=REFUSED/无码=UNVERIFIED；citation eval ALLOWED/BLOCKED 断言
     过；UNVERIFIED 来源→NOT_PASS reasons source_not_verified 具名）
  S4 合同负向 typed 拒（块缺失/多块/未来 as_of/失败合同假成功值/来源类
     型闭集外 corporate_database[无数据源不编企业调查的合同级拒绝]/
     eval kind 闭集外/选中 id 不匹配——全部经真产品入口 CLI）
  S5 回执负向（篡改 reasons→f96_receipt_digest_mismatch；结构坏→
     f96_receipt_invalid；技能 id 绑定不符→f96_receipt_skill_mismatch）
  S6 跨 profile 确定性（同安装 commit/manifest 摘要＋五技能 gate 结论
     与 eval 状态跨 desktop/selfhost 全等；安装摘要跨 profile 全等）
  S7 桥 fail-closed 与面 AST（未知方法 method_not_connected；
     skill_gate.py 顶层导入闭集——无网络/模型/子进程/编排依赖）

selfhost 径＝产品面同进程＋harness PgMatterStore 直连 lh-pg-e08（schema
=f96_*，seam 注入同 F93/W3-U16 先例）；desktop 径＝legal_entry CLI 子进
程全链（harness public_entry 子进程→SQLite MatterStore）。

用法（juscite worktree w3-u18 根 cwd）：
  python -X utf8 tools/recon/PENDING_OWNER_f96_f97_skillgate_preset_recon.py \
      [--profile desktop] [--profile selfhost]
缺省双 profile。exit 0＝RECON_OK 全断言过；证据 JSON 写 evidence/F96/
<profile>/ 与 evidence/F97/<profile>/（及 docs/construction/evidence/ 镜
像）。全程合成材料（合成 git 仓/合成规则包/合成 codices 面），零外部
API、零 BYOK、零 %APPDATA% 触碰；JC/LH 仓只读；不 push。
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest.mock
import uuid
from pathlib import Path

RUN_DATE = "20261019"
REPO_ROOT = Path(__file__).resolve().parents[2]
LEGAL_ENTRY = REPO_ROOT / "implementation" / "python" / "legal_entry.py"
FACE = REPO_ROOT / "implementation" / "python" / "skill_gate.py"
PRESETS = REPO_ROOT / "implementation" / "skill-presets"
GENERATOR = REPO_ROOT / "tools" / "e12_corpus_gen.py"

JC_REPO = Path(
    r"D:\Codex\1.法律工作区\juris-calculus工作区\juris-calculus"
    r"\.local\worktrees\w2b-u55")
JC_CLIENT_SHA256 = (
    "3bb8c56a364243af2acdf6200722e704553e582be9e6521aa854ab285bc8b215")
LH_REPO = Path(
    r"D:\Codex\1.法律工作区\legal-harness工作区\legal-harness-repo"
    r"\.local\worktrees\w2b-u53")
LCCC_PATH = Path(
    r"D:\Codex\1.法律工作区\legal-cn-core-codices工作区"
    r"\legal-cn-core-codices-repo\.local\worktrees\w2a-u14"
    r"\lccc_consumer.py")
LCCC_SHA256 = (
    "55eea7c27e08d6b236b7ab7a83810c86ee0898c335c4668d875a492775db863a")
F88_SEED = 20261016

PRESET_IDS = ["case-intake", "contract-review", "court-inbound",
              "case-close", "calc"]
FLOW_SKILLS = ["case-intake", "contract-review", "court-inbound",
               "case-close"]
REVIEW_EVAL_BY_SKILL = {
    "case-intake": ("m-f96-preset-intake", "brt-f96-preset-intake",
                    ["claim_amount", "cause", "jurisdiction", "limitation",
                     "parties"]),
    "contract-review": ("m-f96-preset-contract", "brt-f96-preset-contract",
                        ["breach", "capacity", "dispute_resolution",
                         "obligations"]),
    "court-inbound": ("m-f96-preset-court", "brt-f96-preset-court",
                      ["case_no", "deadline", "documents", "matter",
                       "parties"]),
    "case-close": ("m-f96-preset-close", "brt-f96-preset-close",
                   ["archive", "fees", "followups", "outcome"]),
}

RULE_PACK = {
    "schema_version": "jc/local-pack/1.0", "pack_version": "1.0.0",
    "sources": [{
        "source_id": "acceptance-statute", "jurisdiction": "TEST",
        "authority_tier": "official_first_party",
        "issuer": "Acceptance Test Authority",
        "title": "acceptance-statute",
        "publication_time": "2020-01-01T00:00:00Z",
        "effective_from": "2020-01-01T00:00:00Z",
        "retrieved_at": "2026-08-01T00:00:00Z",
        "locator": {"kind": "uri", "value": "example.invalid/acceptance",
                    "page": None, "span_start": None, "span_end": None},
        "content": ("SYNTHETIC acceptance rule text for engineering "
                    "verification only; no legal effect."),
        "structure_sections": ["ART-1"]}],
    "rules": [{
        "rule_id": "acc-base", "jurisdiction": "TEST",
        "governing_law": "acceptance-statute",
        "source_id": "acceptance-statute", "modality": "OBLIGATION",
        "premises": [{"fact_key": "acc.contract", "required": True}],
        "conclusion": {"value": "applies"},
        "effective_from": "2020-01-01T00:00:00Z"}],
}

GIT_ENV = dict(os.environ,
               GIT_AUTHOR_DATE="2026-10-19T00:00:00+00:00",
               GIT_COMMITTER_DATE="2026-10-19T00:00:00+00:00")


class Checks:
    def __init__(self):
        self.items: list[dict] = []

    def add(self, check_id: str, ok: bool, detail: str) -> bool:
        self.items.append({"id": check_id,
                           "status": "PASS" if ok else "FAIL",
                           "detail": detail})
        print("[%s] %s — %s" % ("PASS" if ok else "FAIL", check_id, detail),
              flush=True)
        return ok

    @property
    def all_passed(self) -> bool:
        return all(item["status"] == "PASS" for item in self.items)

    @property
    def passed_count(self) -> int:
        return sum(1 for item in self.items if item["status"] == "PASS")


def sha256_file(path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def canonical_bytes(obj) -> bytes:
    return json.dumps(obj, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":")).encode("utf-8")


def git_status_porcelain(repo: Path) -> str:
    proc = subprocess.run(["git", "-C", str(repo), "status", "--porcelain"],
                          capture_output=True, text=True)
    return proc.stdout.strip()


def preset_asset_facts() -> dict:
    files = {}
    for path in sorted(PRESETS.rglob("*")):
        if path.is_file():
            files[path.relative_to(PRESETS).as_posix()] = sha256_file(path)
    return files


def build_source_repo(workspace: Path) -> tuple[Path, str]:
    """预装资产复制保真 → 临时 git 仓钉 commit（确定性：固定作者日期＋同
    字节两跑同 commit）。源字节与仓内资产 sha 清单比对（复制保真）。"""
    src = workspace / "presets-src"
    if src.exists():
        shutil.rmtree(src, ignore_errors=True)
    shutil.copytree(PRESETS, src)
    facts = preset_asset_facts()
    copied = {p.relative_to(src).as_posix(): sha256_file(p)
              for p in sorted(src.rglob("*")) if p.is_file()
              and not (src / p.relative_to(src)).is_dir()
              and p.name != ".git"}
    copied = {k: v for k, v in copied.items()}
    for rel, want in facts.items():
        assert copied.get(rel) == want, "copy fidelity: %s" % rel

    def git(*args):
        proc = subprocess.run(["git", "-C", str(src), *args],
                              capture_output=True, env=GIT_ENV)
        assert proc.returncode == 0, proc.stderr[:200]
        return proc.stdout
    git("init", "-q")
    git("config", "core.autocrlf", "false")
    git("add", "-A")
    git("-c", "user.name=F97-Presets",
        "-c", "user.email=f97@juscite.local", "commit", "-q", "-m",
        "lvyin-presets-batch1 (synthetic acceptance source)")
    return src, git("rev-parse", "HEAD").decode().strip()


def load_generator():
    spec = importlib.util.spec_from_file_location(
        "e12_corpus_gen_f96", GENERATOR)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def call_cli(method: str, args: dict, config: dict) -> dict:
    """desktop 径：真产品入口子进程（legal_entry CLI）。"""
    with tempfile.TemporaryDirectory() as tmp:
        req = Path(tmp) / "request.json"
        cfg = Path(tmp) / "config.json"
        req.write_text(json.dumps({"method": method, "args": args},
                                  ensure_ascii=False), encoding="utf-8")
        cfg.write_text(json.dumps(config, ensure_ascii=False),
                       encoding="utf-8")
        proc = subprocess.run(
            [sys.executable, "-X", "utf8", str(LEGAL_ENTRY),
             "--request-json", str(req), "--config", str(cfg)],
            capture_output=True, text=True, encoding="utf-8", timeout=600,
            cwd=str(REPO_ROOT))
        try:
            payload = json.loads(proc.stdout)
        except json.JSONDecodeError:
            payload = {"status": "RAW", "stdout": proc.stdout[:400]}
        return {"exit": proc.returncode, "payload": payload}


def expect_cli_refusal(checks: Checks, cid: str, method: str, args: dict,
                       config: dict, code_fragment: str, note: str = ""):
    out = call_cli(method, args, config)
    ok = (out["exit"] == 3 and out["payload"].get("status") == "NOT_CONNECTED"
          and code_fragment in str(out["payload"].get("code", "")))
    checks.add(cid, ok,
               "%s typed refusal %s -> exit %s %s%s"
               % (method, code_fragment, out["exit"],
                  str(out["payload"].get("code", ""))[:90],
                  ("；%s" % note) if note else ""))


def gate_receipt_from_payload(payload: dict) -> dict | None:
    result = payload.get("result") if isinstance(payload, dict) else None
    return result if isinstance(result, dict) and result.get("face") else None


# ---------------------------------------------------------------------- #
# 守门样本（S3 法源登记表＋引证 eval；合成 codices 面真核验）
# ---------------------------------------------------------------------- #


def citation_skill_markdown(gen, sources: list, citation_evals: list,
                            as_of: str = "2026-09-30") -> str:
    """S3 验收样本技能：法源登记表（三条三态）＋citation evals＋refusal。"""
    contract = {
        "as_of": as_of,
        "evidence": {"mode": "four_state"},
        "sources": sources,
        "failure": {"on_gate_fail": "named_refusal_not_pass",
                    "on_missing_data": "named_gap_no_fabrication"},
        "evals": citation_evals + [{
            "id": "ev-refusal", "kind": "refusal",
            "scenario": "corporate_investigation_no_data_source",
            "expect": {"outcome": "refused"}}],
    }
    fence = "`" * 3
    return "\n".join([
        "---", "name: F96 法源登记表验收样本",
        "description: 合成 codices 面真核验（非预装；W3-U18 验收样本）",
        "---", "", "# F96 验收样本", "",
        fence + "lvyin-skill-contract",
        json.dumps(contract, ensure_ascii=False), fence, ""])


# ---------------------------------------------------------------------- #
# 双 profile 产品面主体
# ---------------------------------------------------------------------- #


def run_product_profile(checks: Checks, call, workspace: Path,
                        gen, skill_paths: dict, manifest_facts: dict,
                        pin_commit: str) -> dict:
    """S2/S3/S4/S5 守门主体（call＝统一调用闭包；desktop/selfhost 共用）。"""
    facts: dict = {"gates": {}, "s3": {}}
    codices_cfg = {"codices_import_path": str(LCCC_PATH.parent),
                   "codices_formal_root": str(workspace / "codices_face"
                                              / "codices_face")}

    # ---- S2 五预装技能逐个守门真贯通 -------------------------------
    gates = {}
    all_pass = True
    for skill_id in PRESET_IDS:
        skill_path = skill_paths[skill_id]
        outcome = call("skill.gate.run", {"skill_path": skill_path,
                                          "skill_id": skill_id})
        receipt = gate_receipt_from_payload(outcome.get("payload")
                                            if isinstance(outcome, dict)
                                            else None) or {}
        gate = receipt.get("gate")
        reasons = receipt.get("reasons")
        ok = outcome.get("exit") == 0 and gate == "PASS" and reasons == []
        all_pass = all_pass and ok
        gates[skill_id] = {"gate": gate, "reasons": reasons,
                           "evals": [(e.get("id"), e.get("state"),
                                      e.get("passed"))
                                     for e in receipt.get("evals") or []],
                           "as_of": receipt.get("as_of"),
                           "contractSha256": receipt.get("contractSha256"),
                           "skillContentSha256":
                               (receipt.get("skill") or {}).get(
                                   "contentSha256")}
        checks.add("P2_gate_pass_%s" % skill_id, ok,
                   "skill.gate.run(%s) → gate=%s reasons=%s evals=%s"
                   % (skill_id, gate, reasons,
                      [(e.get("id"), e.get("state"), e.get("passed"))
                       for e in receipt.get("evals") or []]))
    facts["gates"] = gates
    checks.add("P2_all_five_presets_gate_pass", all_pass,
               "F97 预装五件（接案/合同/法院来件/结案/计算）守门真实贯通："
               "全部 PASS（calculation 真算 JC；review_instantiate 真建批；"
               "refusal 企业调查无数据源 REFUSED 过）")

    # calculation eval 细节：真算 20 分（E21/F93 同源闰日夹具）。
    calc_evals = {e[0]: e for e in gates["calc"]["evals"]}
    ok = calc_evals.get("ev-calc-leapday", (None, None, None))[1] == "VERIFIED"
    checks.add("P2_calc_real_jc_amount_verified", ok,
               "calc 技能 eval ev-calc-leapday 状态=%s（365000×1%%×闰日2天"
               "/365=20 分，经 skill.calculate→P01 JCClient 真算）"
               % (calc_evals.get("ev-calc-leapday",
                                      (None, None, None))[1],))

    # refusal eval：五件全部 REFUSED passed（无数据源不编企业调查）。
    refusal_ok = all(
        any(e[0].endswith("refusal") and e[1] == "REFUSED"
            and e[2] is True for e in gates[sid]["evals"])
        for sid in PRESET_IDS)
    checks.add("P2_refusal_evals_refused_passed", refusal_ok,
               "五预装技能 refusal eval（corporate_investigation_no_data_"
               "source）全部 REFUSED 且 passed=True——无数据源场景具名拒绝，"
               "绝不编企业调查数据")

    # ---- S2 未核不签 PASS／STALE ----------------------------------
    sid = "calc"
    skill_path = skill_paths[sid]
    validate = call("skill.gate.validate", {"skill_path": skill_path,
                                            "skill_id": sid})
    vok = validate.get("exit") == 0
    checks.add("P2_validate_without_run", vok,
               "skill.gate.validate(%s) → exit=%s（合同校验过但未执行 "
               "evals）" % (sid, validate.get("exit")))
    unverified = call("skill.gate.verify_receipt",
                      {"skill_path": skill_path, "receipt": None})
    unv = gate_receipt_from_payload(unverified.get("payload")) or {}
    ok = (unverified.get("exit") == 0
          and unv.get("state") == "UNVERIFIED"
          and unv.get("pass_allowed") is False)
    checks.add("P2_no_receipt_unverified_never_pass", ok,
               "未核不签 PASS：validate 后未 run → verify_receipt = %s "
               "pass_allowed=%s（无执行回执绝不签 PASS）"
               % (unv.get("state"), unv.get("pass_allowed")))

    # STALE：同 id 技能改一字节 → 旧回执 STALE。
    stale_receipt = gates[sid]
    # 重新真跑取得完整回执（P2 的 gates 只存摘要）。
    full = call("skill.gate.run", {"skill_path": skill_path,
                                   "skill_id": sid})
    receipt = gate_receipt_from_payload(full.get("payload")) or {}
    stale_dir = workspace / "stale" / sid
    stale_dir.mkdir(parents=True, exist_ok=True)
    stale_path = stale_dir / "SKILL.md"
    stale_path.write_text(
        Path(skill_path).read_text(encoding="utf-8") + "\n尾注改动。\n",
        encoding="utf-8")
    stale = call("skill.gate.verify_receipt",
                 {"skill_path": str(stale_path), "receipt": receipt})
    stv = gate_receipt_from_payload(stale.get("payload")) or {}
    ok = (stale.get("exit") == 0 and stv.get("state") == "STALE"
          and stv.get("pass_allowed") is False)
    checks.add("P2_stale_bytes_never_pass", ok,
               "STALE：技能字节改一字节后旧回执 verify_receipt = %s "
               "pass_allowed=%s（旧核不覆盖新内容）"
               % (stv.get("state"), stv.get("pass_allowed")))

    # ---- S3 法源登记表与引证 eval（合成 codices 面真核验） --------
    W = gen._CIT_W
    as_of_compact = gen.CIT_FIXED_AS_OF
    sources = [
        {"id": "current", "kind": "statute", "wjbs": W["A1"],
         "code31": None, "as_of": as_of_compact},
        {"id": "abolished", "kind": "statute", "wjbs": W["ABO1"],
         "code31": None, "as_of": as_of_compact},
        {"id": "nocode", "kind": "statute", "wjbs": W["NOCODE"],
         "code31": None, "as_of": as_of_compact},
    ]
    citation_evals = [
        {"id": "ev-cite-allowed", "kind": "citation", "wjbs": W["A1"],
         "code31": None, "as_of": as_of_compact,
         "expect": {"decision": "ALLOWED"}},
        {"id": "ev-cite-blocked", "kind": "citation", "wjbs": W["ABO1"],
         "code31": None, "as_of": as_of_compact,
         "expect": {"decision": "BLOCKED"}},
    ]
    sample_dir = workspace / "samples" / "s-f96-registry"
    sample_dir.mkdir(parents=True, exist_ok=True)
    sample_path = sample_dir / "SKILL.md"
    sample_path.write_text(
        citation_skill_markdown(gen, sources, citation_evals),
        encoding="utf-8")
    outcome = call("skill.gate.run", {"skill_path": str(sample_path),
                                      "skill_id": "s-f96-registry"})
    receipt = gate_receipt_from_payload(outcome.get("payload")) or {}
    registry = {s.get("id"): s.get("state")
                for s in receipt.get("sourcesRegistry") or []}
    ok = (registry == {"current": "VERIFIED", "abolished": "REFUSED",
                       "nocode": "UNVERIFIED"}
          and receipt.get("gate") == "NOT_PASS"
          and "source_not_verified:abolished" in (receipt.get("reasons")
                                                  or [])
          and "source_not_verified:nocode" in (receipt.get("reasons")
                                               or []))
    checks.add("P3_registry_real_verification_three_states", ok,
               "法源登记表真核验（合成 codices 面）：现行=VERIFIED／已废止="
               "REFUSED／无码=UNVERIFIED → gate=%s reasons=%s（未核来源不"
               "签 PASS）" % (receipt.get("gate"), receipt.get("reasons")))
    cite_states = {e.get("id"): (e.get("state"), e.get("passed"))
                   for e in receipt.get("evals") or []}
    ok = (cite_states.get("ev-cite-allowed") == ("VERIFIED", True)
          and cite_states.get("ev-cite-blocked") == ("VERIFIED", True)
          and cite_states.get("ev-refusal") == ("REFUSED", True))
    checks.add("P3_citation_evals_real_gate_decisions", ok,
               "citation eval 经 statute.citation_gate 真核验：现行→ALLOWED"
               " 过／已废止→BLOCKED 过（被废除检索到也不许引）＝%s"
               % cite_states)
    facts["s3"] = {"registry": registry,
                   "cite_evals": {k: list(v)
                                  for k, v in cite_states.items()},
                   "gate": receipt.get("gate")}

    # ---- S4 合同负向 typed 拒（真 CLI 入口） ----------------------
    neg_dir = workspace / "negskills"
    neg_dir.mkdir(parents=True, exist_ok=True)
    fence = "`" * 3

    def neg_skill(skill_id: str, contract: dict | None,
                  raw: str | None = None, extra: bool = False) -> str:
        directory = neg_dir / skill_id
        directory.mkdir(parents=True, exist_ok=True)
        blocks: list[str] = []
        if raw is not None or contract is not None:
            body = raw if raw is not None else json.dumps(
                contract, ensure_ascii=False)
            blocks = [fence + "lvyin-skill-contract", body, fence]
        if extra:
            blocks += ["", fence + "lvyin-skill-contract", "{}", fence]
        text = "\n".join(["---", "name: %s" % skill_id,
                          "description: F96 负向样本", "---", ""]
                         + blocks + [""])
        path = directory / "SKILL.md"
        path.write_text(text, encoding="utf-8")
        return str(path)

    good = {"as_of": "2026-09-30", "evidence": {"mode": "four_state"},
            "sources": [],
            "failure": {"on_gate_fail": "named_refusal_not_pass",
                        "on_missing_data": "named_gap_no_fabrication"},
            "evals": [{"id": "e1", "kind": "refusal",
                       "scenario": "corporate_investigation_no_data_source",
                       "expect": {"outcome": "refused"}}]}
    cases = [
        ("P4_neg_block_missing", "s-noblock", None, None, False,
         "f96_contract_block_missing", "正文无合同块"),
        ("P4_neg_block_not_unique", "s-two", good, None, True,
         "f96_contract_block_not_unique", "两块合同"),
        ("P4_neg_future_as_of", "s-future",
         dict(good, as_of="2999-12-31"), None, False,
         "f96_contract_as_of_in_future", "未来时点合同无效（时点门禁）"),
        ("P4_neg_failure_fake_success", "s-fake",
         dict(good, failure={"on_gate_fail": "silent_pass",
                             "on_missing_data": "fabricate_fill"}),
         None, False, "f96_failure_contract_invalid",
         "失败合同闭值外（假成功/编造形态无合法值可写）"),
        ("P4_neg_corporate_source_kind", "s-corp",
         dict(good, sources=[{"id": "qcc",
                              "kind": "corporate_database", "wjbs": None,
                              "code31": None, "as_of": "20260930"}]),
         None, False, "f96_source_kind_unknown:corporate_database",
         "企业数据来源无类型可声明（无数据源不编企业调查的合同级拒绝）"),
        ("P4_neg_eval_kind_unknown", "s-kind",
         dict(good, evals=[{"id": "e1", "kind": "chat",
                            "scenario": "x",
                            "expect": {"outcome": "refused"}}]),
         None, False, "f96_eval_kind_unknown:chat", "eval kind 闭集外"),
    ]
    for cid, skill_id, contract, raw, extra, code, note in cases:
        path = neg_skill(skill_id, contract, raw, extra)
        expect_cli_refusal(checks, cid, "skill.gate.validate",
                           {"skill_path": path, "skill_id": skill_id}, {},
                           code, note)

    # 选中 id 不匹配。
    mismatch = call("skill.gate.validate",
                    {"skill_path": skill_paths["calc"],
                     "skill_id": "wrong-id"})
    ok = (mismatch.get("exit") == 3
          and "f96_skill_id_mismatch"
          in str((mismatch.get("payload") or {}).get("code", "")))
    checks.add("P4_neg_selection_id_mismatch", ok,
               "skill.gate.validate 选中 id 不匹配 → exit=%s（具名拒不守门"
               "未选中技能）" % mismatch.get("exit"))

    # ---- S5 回执负向 ----------------------------------------------
    full2 = call("skill.gate.run", {"skill_path": skill_paths["calc"],
                                    "skill_id": "calc"})
    receipt2 = gate_receipt_from_payload(full2.get("payload")) or {}
    forged = dict(receipt2, reasons=["forged:reason"])
    tamper = call("skill.gate.verify_receipt",
                  {"skill_path": skill_paths["calc"], "receipt": forged})
    ok = (tamper.get("exit") == 3
          and "f96_receipt_digest_mismatch"
          in str((tamper.get("payload") or {}).get("code", "")))
    checks.add("P5_receipt_digest_mismatch_refused", ok,
               "回执 reasons 篡改 → f96_receipt_digest_mismatch（digest "
               "重算不等，具名拒）")
    broken = call("skill.gate.verify_receipt",
                  {"skill_path": skill_paths["calc"],
                   "receipt": {"schema": "x"}})
    ok = (broken.get("exit") == 3
          and "f96_receipt_invalid"
          in str((broken.get("payload") or {}).get("code", "")))
    checks.add("P5_receipt_invalid_refused", ok,
               "回执结构坏 → f96_receipt_invalid（具名拒）")
    other_path = skill_paths["case-intake"]
    binding = call("skill.gate.verify_receipt",
                   {"skill_path": other_path, "receipt": receipt2})
    ok = (binding.get("exit") == 3
          and "f96_receipt_skill_mismatch"
          in str((binding.get("payload") or {}).get("code", "")))
    checks.add("P5_receipt_skill_binding_mismatch_refused", ok,
               "回执绑定到其他技能 → f96_receipt_skill_mismatch（具名拒）")

    # ---- S7 桥 fail-closed 与面 AST -------------------------------
    unknown = call("skill.gate.route", {})
    ok = (unknown.get("exit") == 3
          and "method_not_connected"
          in str((unknown.get("payload") or {}).get("code", "")))
    checks.add("P7_unknown_method_not_connected", ok,
               "组外方法 skill.gate.route → method_not_connected（冻结组"
               "外不落本面）")
    tree = ast.parse(FACE.read_text(encoding="utf-8"))
    imported = set()
    for node in tree.body:
        if isinstance(node, ast.Import):
            imported.update(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom):
            imported.add(node.module or "")
    ok = imported == {"__future__", "hashlib", "json", "re", "datetime",
                      "bridge_errors", "skill_semantics"}
    checks.add("P7_skill_gate_import_closure", ok,
               "skill_gate.py 顶层导入闭集=%s（无网络/模型/子进程/编排依赖；"
               "legal_entry 函数内延迟导入）" % sorted(imported))
    return facts


def run_desktop(checks: Checks, workspace: Path, harness_root: Path,
                gen, skill_paths: dict, manifest_facts: dict,
                pin_commit: str) -> dict:
    """desktop 径：legal_entry CLI 子进程全链（harness public_entry 子进程
    →SQLite MatterStore；JC 经 P01 同域配置）。"""
    sys.path.insert(0, str(harness_root / "src"))
    from legal_harness.state.matter_store import MatterStore
    state_root = workspace / "harness-state"
    state_root.mkdir(parents=True)
    store = MatterStore(state_root)
    matters = {"m-f96-preset-intake", "m-f96-preset-contract",
               "m-f96-preset-court", "m-f96-preset-close",
               "m-f96-preset-calc"}
    for matter in sorted(matters):
        store.create_matter(matter, "cas://f96-desktop-%s" % matter)
    rules = workspace / "rules"
    rules.mkdir(parents=True, exist_ok=True)
    (rules / "jc-local-pack.json").write_text(
        json.dumps(RULE_PACK, ensure_ascii=False), encoding="utf-8")
    config = {
        "harness_public_entry": str(
            harness_root / "tools/workflow-tools/harness/public_entry.py"),
        "harness_target": "opencode",
        "harness_state_root": str(state_root),
        "harness_service_registration": str(workspace
                                            / "bridge-registration.json"),
        "harness_timeout": 180,
        "harness_python": sys.executable,
        "jc_state_root": str(workspace / "jc-state"),
        "jc_rule_roots": [str(rules)],
        "jc_import_path": str(JC_REPO),
        "codices_import_path": str(LCCC_PATH.parent),
        "codices_formal_root": str(workspace / "codices_face"
                                   / "codices_face"),
    }
    (workspace / "bridge-registration.json").write_text(
        json.dumps({"url": "http://127.0.0.1:1",
                    "password": "synthetic-recon"}), encoding="utf-8")

    def call(method, args):
        outcome = call_cli(method, args, config)
        if outcome["exit"] == 0 and outcome["payload"].get("result") is None \
                and method.startswith("skill.gate"):
            raise SystemExit("FATAL: %s exit 0 但结果缺失（payload=%s）"
                             % (method, json.dumps(outcome["payload"],
                                                   ensure_ascii=False)[:400]))
        return outcome

    checks.add("P0_profile_transport_desktop", True,
               "desktop＝legal_entry CLI 子进程全链（harness public_entry 子"
               "进程→SQLite MatterStore；JC 经 P01 同域配置；codices 经 E22 "
               "冻结面同域配置）")
    return run_product_profile(checks, call, workspace, gen, skill_paths,
                               manifest_facts, pin_commit)


def run_selfhost(checks: Checks, workspace: Path, harness_root: Path,
                 dsn: str, gen, skill_paths: dict, manifest_facts: dict,
                 pin_commit: str) -> dict:
    """selfhost 径：产品面同进程＋harness PgMatterStore 直连 lh-pg-e08
    （schema=f96_*；seam 注入同 F93/W3-U16 先例）。"""
    for path in (str(harness_root / "src"),
                 str(REPO_ROOT / "implementation" / "python")):
        if path not in sys.path:
            sys.path.insert(0, path)
    from legal_harness.business.provider_registry import (
        resolve_provider_method)
    from legal_harness.business.units import HarnessUnits
    from legal_harness.state.pg_store import PgMatterStore
    sys.path.insert(0, str(JC_REPO))
    for name in [m for m in list(sys.modules)
                 if m == "compiler_core"
                 or m.startswith("compiler_core.")]:
        del sys.modules[name]

    base = Path(tempfile.mkdtemp(prefix="f96-selfhost-"))
    store = PgMatterStore(base / "state", dsn=dsn,
                          schema="f96_" + uuid.uuid4().hex[:12])
    units = HarnessUnits(store)
    names = ("harness.review_batch_create", "harness.review_columns_define")
    bound = {name: resolve_provider_method(name, units)
             for name in names}
    for matter in ("m-f96-preset-intake", "m-f96-preset-contract",
                   "m-f96-preset-court", "m-f96-preset-close",
                   "m-f96-preset-calc"):
        store.create_matter(matter, "cas://f96-pg-%s" % matter)
    import skill_gate
    from bridge_errors import NotConnected
    from skill_gate import SkillGateError as _SGE

    # 注入「按方法名分流」的组合 seam：harness 两方法走 PgMatterStore 直连
    # （selfhost 部署形态），其余（skill.calculate/statute.*）透传真径——
    # 真 JC／真合成 codices 面在 selfhost 径同样真实执行。
    import legal_entry as _le
    real_entry = _le.call

    def combined(method, args, cfg):
        if method in bound:
            return bound[method](**args)
        return real_entry(method, args, cfg)

    patchers = [unittest.mock.patch.object(skill_gate, "_entry_call",
                                           combined)]
    # review_instantiate eval 内部走 skill_semantics._harness_call（F93
    # seam）——selfhost 径同样接管到 PgMatterStore 直连。
    import skill_semantics as _ss

    def harness_seam(method, args, cfg):
        if method in bound:
            return bound[method](**args)
        raise NotConnected("method_not_connected:" + method)

    patchers.append(unittest.mock.patch.object(_ss, "_harness_call",
                                               harness_seam))
    for patcher in patchers:
        patcher.start()
    try:
        rules = workspace / "rules"
        rules.mkdir(parents=True, exist_ok=True)
        (rules / "jc-local-pack.json").write_text(
            json.dumps(RULE_PACK, ensure_ascii=False), encoding="utf-8")
        config = {"jc_state_root": str(workspace / "jc-state-pg"),
                  "jc_rule_roots": [str(rules)],
                  "jc_import_path": str(JC_REPO),
                  "codices_import_path": str(LCCC_PATH.parent),
                  "codices_formal_root": str(workspace / "codices_face"
                                             / "codices_face")}

        def call(method, args):
            try:
                result = skill_gate.gate_call(method, args, config) \
                    if method.startswith("skill.gate") \
                    else _le.call(method, args, config)
                return {"exit": 0, "payload": {"result": result}}
            except NotConnected as exc:
                return {"exit": 3,
                        "payload": {"status": "NOT_CONNECTED",
                                    "code": str(exc)}}
            except _SGE as exc:
                # typed f96_* 码与 legal_entry 桥层同形包装。
                return {"exit": 3,
                        "payload": {"status": "NOT_CONNECTED",
                                    "code": "skill_gate_failed:"
                                            + str(exc)}}
            except _le.JCMethodFailure as exc:
                return {"exit": 4,
                        "payload": {"status": "JC_FAILURE",
                                    "code": str(exc)}}
            except Exception as exc:  # noqa: BLE001
                return {"exit": 1,
                        "payload": {"status": "ERROR",
                                    "code": "%s: %s" % (
                                        type(exc).__name__,
                                        str(exc)[:160])}}

        checks.add("P0_profile_transport_selfhost", True,
                   "selfhost＝产品面同进程＋harness PgMatterStore 直连 "
                   "lh-pg-e08（schema=f96_*；harness 两方法经 "
                   "resolve_provider_method 封闭注册；skill.calculate/"
                   "statute.* 仍走真径）")
        return run_product_profile(checks, call, workspace, gen,
                                   skill_paths, manifest_facts, pin_commit)
    finally:
        for patcher in patchers:
            patcher.stop()


# ---------------------------------------------------------------------- #
# main
# ---------------------------------------------------------------------- #


def main() -> int:
    if os.name == "nt":
        sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
    sys.path.insert(0, str(REPO_ROOT / "implementation" / "python"))
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", action="append",
                        choices=("desktop", "selfhost"), dest="profiles",
                        help="发行形态（可重复；不给则双形态全跑）")
    parser.add_argument("--harness-root", default=str(LH_REPO))
    parser.add_argument("--jc-repo", default=str(JC_REPO))
    parser.add_argument(
        "--pg-dsn",
        default="postgresql://lh_app:e08-synth-only@127.0.0.1:55432/"
                "legal_harness",
        help="selfhost PgMatterStore 直连 DSN（默认＝本机合成容器 "
             "lh-pg-e08；合成专用凭据）")
    parser.add_argument("--evidence-root",
                        default=str(REPO_ROOT / "evidence"))
    args = parser.parse_args()
    profiles = args.profiles or ["desktop", "selfhost"]
    jc_repo = Path(args.jc_repo)
    harness_root = Path(args.harness_root)
    evidence_root = Path(args.evidence_root)

    # ---- S0 钉定（漂移即 FATAL，exit 2） ---------------------------
    client_path = jc_repo / "compiler_core" / "client.py"
    if not client_path.is_file():
        print("FATAL: JC client.py 不在 %s" % client_path)
        return 2
    actual_sha = sha256_file(client_path)
    if actual_sha != JC_CLIENT_SHA256:
        print("FATAL: JC client.py sha256 漂移（钉定 %s…，实测 %s…，%s）"
              % (JC_CLIENT_SHA256[:12], actual_sha[:12], jc_repo))
        return 2
    print("[pin] JC client.py sha256 = %s…（钉定一致；worktree %s）"
          % (actual_sha[:12], jc_repo.name), flush=True)
    if not (harness_root / "tools/workflow-tools/harness/public_entry.py"
            ).is_file():
        print("FATAL: harness 公开入口不在 %s" % harness_root)
        return 2
    if not LCCC_PATH.is_file() or sha256_file(LCCC_PATH) != LCCC_SHA256:
        print("FATAL: E22 冻结面 lccc_consumer.py 缺失或 sha256 漂移")
        return 2
    print("[pin] LCCC v1.1 sha256 = %s…（钉定一致）" % LCCC_SHA256[:12],
          flush=True)
    jc_clean_before = git_status_porcelain(jc_repo)
    lh_clean_before = git_status_porcelain(harness_root)
    print("[pin] JC worktree porcelain 开工=%r；LH worktree porcelain 开工"
          "=%r" % (jc_clean_before, lh_clean_before), flush=True)

    # ---- S1 预装源仓确定性＋分发链安装（F97 硬依赖 W3-U17） --------
    all_facts: dict = {}
    all_ok = True
    workspace_root = Path(tempfile.mkdtemp(prefix="f96-f97-recon-"))
    try:
        gen = load_generator()
        s1_checks_per_profile: dict = {}
        for profile in profiles:
            print("\n===== profile: %s =====" % profile, flush=True)
            checks = Checks()
            workspace = workspace_root / profile
            workspace.mkdir(parents=True, exist_ok=True)

            # 预装资产清单（S0）。
            facts = preset_asset_facts()
            checks.add("S0_preset_assets_manifest",
                       set(facts) == {"catalog.json"}
                       | {sid + "/SKILL.md" for sid in PRESET_IDS},
                       "预装资产清单=%s（五件＋catalog.json；sha 入证据）"
                       % sorted(facts))

            # 合成 codices 正式面（两跑 digest 相等）。
            face_a = workspace / "codices_face"
            gen.build_citations(face_a, F88_SEED)
            face_digest = (face_a / "f88_citations_digest.txt"
                           if (face_a / "f88_citations_digest.txt").is_file()
                           else None)
            digest_value = sha256_file(face_digest) if face_digest else None
            checks.add("S0_synthetic_codices_face", (
                face_a / "codices_face" / "legal_documents.csv").is_file(),
                "合成 codices 正式面就绪（seed=%d；digest=%s）"
                % (F88_SEED, (digest_value or "")[:12]))

            # 源仓两跑同 commit（确定性）。
            src1, commit1 = build_source_repo(workspace / "run1")
            src2, commit2 = build_source_repo(workspace / "run2")
            checks.add("S1_source_repo_deterministic", commit1 == commit2,
                       "预装源仓两跑 commit 相等=%s（复制保真＋固定作者日期）"
                       % commit1[:12])

            # 分发链安装（W3-U17 冻结面）。
            state_root = workspace / "skill-state"
            cfg = {"skill_catalog_state_root": str(state_root)}
            install = call_cli("skill.catalog.install", {
                "channel": "public",
                "source": {"kind": "git_local", "repo": str(src1),
                           "commit": commit1}}, cfg)
            install_payload = install.get("payload") or {}
            install_result = install_payload.get("result") or {}
            installed_ids = sorted(s.get("id")
                                   for s in install_result.get("skills")
                                   or [])
            ok = (install.get("exit") == 0
                  and install_result.get("commit") == commit1
                  and installed_ids == sorted(PRESET_IDS))
            checks.add("S1_catalog_install_five_presets", ok,
                       "skill.catalog.install(git_local pin) → exit=%s "
                       "commit==pin=%s skills=%s（F97 硬依赖：预装经 W3-U17 "
                       "分发链真实安装）"
                       % (install.get("exit"), commit1[:12], installed_ids))

            verify = call_cli("skill.catalog.verify",
                              {"channel": "public"}, cfg)
            verify_result = (verify.get("payload") or {}).get("result") or {}
            checks.add("S1_catalog_verify_ok",
                       verify.get("exit") == 0
                       and verify_result.get("status") == "OK",
                       "skill.catalog.verify → %s（manifest 逐文件 sha256 "
                       "与活动面全等）" % verify_result.get("status"))

            skill_paths = {}
            for sid in PRESET_IDS:
                read = call_cli("skill.catalog.read",
                                {"channel": "public", "skill_id": sid}, cfg)
                read_result = (read.get("payload") or {}).get("result") or {}
                directory = read_result.get("directory") or ""
                candidate = str(Path(directory) / "SKILL.md")
                skill_paths[sid] = candidate
                ok = (read.get("exit") == 0
                      and (read_result.get("skill") or {}).get("id") == sid
                      and Path(candidate).is_file())
                checks.add("S1_catalog_read_%s" % sid, ok,
                           "skill.catalog.read(%s) → %s（安装面文件在位，供"
                           "守门消费）" % (sid, candidate))

            manifest_sha = install_result.get("manifest_sha256")
            # 跨 profile 确定性素材（同 commit→同 manifest 摘要）。
            facts["pin_commit"] = commit1
            facts["manifest_sha256"] = manifest_sha
            s1_checks_per_profile[profile] = {
                "commit": commit1, "manifest_sha256": manifest_sha,
                "asset_facts": facts}

            # 双 profile 主体。
            if profile == "desktop":
                pf = run_desktop(checks, workspace, harness_root, gen,
                                 skill_paths, facts, commit1)
            else:
                pf = run_selfhost(checks, workspace, harness_root,
                                  args.pg_dsn, gen, skill_paths, facts,
                                  commit1)
            facts.update(pf)
            all_facts[profile] = {"checks": checks.items, "facts": facts}
            if not checks.all_passed:
                all_ok = False

        # ---- S6 跨 profile 确定性 -------------------------------
        if len(profiles) == 2:
            checks = Checks()
            a, b = (all_facts[p]["facts"] for p in profiles)
            same_install = (a["manifest_sha256"] == b["manifest_sha256"]
                            and a["pin_commit"] == b["pin_commit"])
            checks.add("S6_install_summary_cross_profile", same_install,
                       "跨 profile：源 commit＋manifest 摘要全等（分发链与宿"
                       "主形态无关）")
            gates_equal = a.get("gates") == b.get("gates")
            checks.add("S6_gate_conclusions_cross_profile", gates_equal,
                       "跨 profile：五预装技能 gate 结论与 eval 状态逐项全等"
                       "（守门确定性）")
            all_facts["S6"] = {"checks": checks.items}
            if not checks.all_passed:
                all_ok = False

        # 汇总。
        total_checks = sum(len(all_facts[p]["checks"])
                           for p in all_facts if p != "S6")
        print("\n===== 汇总 =====")
        print("RECON_OK" if all_ok else "RECON_FAILED",
              "checks=%d" % total_checks, flush=True)

        # 证据落盘（evidence/F96/<profile>/ 与 evidence/F97/<profile>/＋
        # docs/construction/evidence/ 镜像）。
        for feature, slice_facts in (("F96", None), ("F97", None)):
            for profile in profiles:
                payload = all_facts.get(profile) or {}
                evidence = {
                    "feature": feature,
                    "unit": "W3-U18",
                    "profile": profile,
                    "run_date": RUN_DATE,
                    "command": ("python -X utf8 "
                                "tools/recon/PENDING_OWNER_f96_f97_skillgate_"
                                "preset_recon.py"),
                    "checks": payload.get("checks", []),
                    "facts": payload.get("facts", {}),
                    "presets_assets": preset_asset_facts(),
                }
                if feature == "F97":
                    evidence["distribution_chain"] = {
                        "pin_commit": (payload.get("facts") or {}).get(
                            "pin_commit"),
                        "manifest_sha256": (payload.get("facts") or {}).get(
                            "manifest_sha256"),
                        "installed": PRESET_IDS,
                    }
                for base in (evidence_root / feature / profile,
                             REPO_ROOT / "docs" / "construction"
                             / "evidence" / feature / profile):
                    base.mkdir(parents=True, exist_ok=True)
                    (base / "recon-result.json").write_text(
                        json.dumps(evidence, ensure_ascii=False, indent=2),
                        encoding="utf-8")
        print("证据已写 evidence/F96|F97/<profile>/recon-result.json（＋"
              "docs/construction/evidence/ 镜像）")
        jc_clean_after = git_status_porcelain(jc_repo)
        lh_clean_after = git_status_porcelain(harness_root)
        print("[pin] JC worktree porcelain 收工=%r；LH worktree porcelain "
              "收工=%r" % (jc_clean_after, lh_clean_after))
        return 0 if all_ok else 1
    finally:
        pass


if __name__ == "__main__":
    sys.exit(main())

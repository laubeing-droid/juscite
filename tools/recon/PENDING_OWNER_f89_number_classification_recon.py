# -*- coding: utf-8 -*-
"""F89 数字三分类豁免验收对账（PENDING_OWNER 版，工单 W2b-U04）。

事实金额/规则数/否定语义三分类＋金额经 JC 公开求值，全部断言走真产品
入口（implementation/python/legal_entry.py 子进程径）。金额值经 P01
冻结面 jc.evaluate → jc-harness-local/1 business task（JC 侧 Fraction
精确＝产品侧 Decimal 全程无浮点）；JC 检出只读钉定 sha256（漂移即
FATAL）。

分段：
  S1 三分类正确分类（合成文书）：事实金额（货币/利率/中文数字/大写/混
     形态）、规则数（条文号/款/项/诉讼时效期数）、否定语义（辖域前缀
     线索/后缀界线线索，极性随记）逐 mention 断言＋计数对账＋三分类
     豁免结构绑定。
  S2 歧义待核：裸期限/裸数/裸百分数/日历表达式/混形态值不可解析 →
     unknown＋pending_review＋具名 reason；事实金额值不可解析＝类可定
     值待核（不伪填）。
  S3 金额经 JC：正确算式 CONSISTENT（含小数精确、多笔付款、中文数字
     值接线）；响应携 jc-harness-local/1 契约＋run/input refs；Decimal
     全程（float 拒收）。
  S4 错误算式反例拒绝：错主张余额 → MISMATCH 具名（两侧精确值＋差值）。
  S5 确定性纪律：同输入两跑字节级同输出；number_classifier.py AST 零
     网络/零随机/零模型导入（不把 LLM 分类叫确定性）；classify 面零
     JC/零配置依赖（分类不求值金额，两权分离）。
  S6 桥 fail-closed：未知方法/缺 text/缺 jc 配置/float 金额 → exit 3
     具名 NOT_CONNECTED。

用法（juscite worktree w2b-u04 根 cwd）：
  python -X utf8 tools/recon/PENDING_OWNER_f89_number_classification_recon.py --profile desktop --profile selfhost

exit 0＝所请求全部 profile 断言全过（每 profile 各 RECON_OK）；证据 JSON
写 <root>/<profile>/。只读消费，不发任何网络请求；材料全合成。
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

RUN_DATE = time.strftime("%Y%m%d")
REPO_ROOT = Path(__file__).resolve().parents[2]
LEGAL_ENTRY = REPO_ROOT / "implementation" / "python" / "legal_entry.py"
NUMBER_MODULE = REPO_ROOT / "implementation" / "python" / "number_classifier.py"

DEFAULT_JC_REPO = r"D:\Codex\1.法律工作区\juris-calculus工作区\juris-calculus"
JC_CLIENT_SHA256 = (
    "15c2f88f415d1758a628d7f98c1ecb87c623f017ffe1f1040c488d9ad775c7be"
)
JC_CLIENT_REL = "compiler_core/client.py"

# 合成规则包（与 P01 验收同构；工程验证专用，无法律效力）
RULE_PACK = {
    "schema_version": "jc/local-pack/1.0",
    "pack_version": "1.0.0",
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

# S1 合成文书（全部工程合成，无真实案件材料）
SYNTH_DOC = (
    "《中华人民共和国民法典》第五百八十五条第二款第三项规定，当事人可以约定违约金。"
    "原告出借本金100,000元，被告已还款30,000元，尚欠70,000元。"
    "借款本金人民币伍拾万元整，年利率3.85%。"
    "违约金不得超过实际损失的百分之三十；欠款不足500元的不予受理。"
    "诉讼时效期间为三年。罚款一千元以下。"
)

BANNED_IMPORTS = {
    "random", "secrets", "urllib", "requests", "socket", "http", "httpx",
    "aiohttp", "openai", "anthropic", "transformers", "torch", "tensorflow",
    "onnxruntime",
}


class Checks:
    def __init__(self):
        self.items: list[dict] = []

    def add(self, check_id: str, ok: bool, detail: str) -> bool:
        self.items.append({"id": check_id,
                           "status": "PASS" if ok else "FAIL",
                           "detail": detail})
        print("[%s] %s — %s" % ("PASS" if ok else "FAIL", check_id, detail))
        return ok

    @property
    def all_passed(self) -> bool:
        return all(item["status"] == "PASS" for item in self.items)

    @property
    def passed_count(self) -> int:
        return sum(1 for item in self.items if item["status"] == "PASS")


def sha256_file(path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def jc_config(jc_repo: str, base: Path) -> dict:
    rules = base / "rules"
    rules.mkdir(parents=True, exist_ok=True)
    (rules / "jc-local-pack.json").write_text(
        json.dumps(RULE_PACK, ensure_ascii=False), encoding="utf-8")
    return {
        "jc_state_root": str(base / "state"),
        "jc_rule_roots": [str(rules)],
        "jc_import_path": jc_repo,
    }


def call_entry(method: str, args: dict, config: dict) -> dict:
    """真产品入口子进程调用；返回 {exit, payload}。"""
    request_handle = tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", suffix=".json", delete=False)
    config_handle = tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", suffix=".json", delete=False)
    try:
        json.dump({"method": method, "args": args}, request_handle,
                  ensure_ascii=False)
        request_handle.close()
        json.dump(config, config_handle, ensure_ascii=False)
        config_handle.close()
        proc = subprocess.run(
            [sys.executable, "-X", "utf8", str(LEGAL_ENTRY),
             "--request-json", request_handle.name,
             "--config", config_handle.name],
            capture_output=True, text=True, encoding="utf-8",
            timeout=600, cwd=str(REPO_ROOT))
        try:
            payload = json.loads(proc.stdout)
        except json.JSONDecodeError:
            payload = {"_raw": proc.stdout[-500:]}
        return {"exit": proc.returncode, "payload": payload}
    finally:
        os.unlink(request_handle.name)
        os.unlink(config_handle.name)


def _classify(checks: Checks, text: str, config: dict, check_id: str) -> dict:
    response = call_entry("number.classify", {"text": text}, config)
    payload = response["payload"]
    result = payload.get("result", {}) if isinstance(payload, dict) else {}
    ok = (response["exit"] == 0
          and payload.get("status") == "OWNER_RESPONSE"
          and result.get("determinism") == "regex-state-machine"
          and result.get("model_involved") is False)
    checks.add(check_id, ok, "exit=%s status=%s determinism=%s" % (
        response["exit"], payload.get("status"), result.get("determinism")))
    return result


def section_s1(checks: Checks, config: dict) -> dict:
    result = _classify(checks, SYNTH_DOC, config, "S1_classify_owner_response")
    by_text = {m["text"]: m for m in result.get("mentions", [])}

    fact_expect = {"100,000元": "100000", "30,000元": "30000",
                   "70,000元": "70000", "人民币伍拾万元整": "500000"}
    ok = all(by_text.get(t, {}).get("class") == "fact_amount"
             and by_text.get(t, {}).get("value") == v
             and by_text[t]["exemption"]["discipline"] == "jc_amount_evaluation"
             for t, v in fact_expect.items())
    ok = ok and by_text.get("3.85%", {}).get("class") == "fact_amount" \
        and by_text["3.85%"]["unit"] == "percent"
    checks.add("S1_fact_amount_classified", ok,
               "事实金额 4 笔货币值精确＋利率 3.85%%＝fact_amount，豁免纪律"
               "=jc_amount_evaluation")

    ok = (by_text.get("第五百八十五条", {}).get("class") == "rule_number"
          and by_text["第五百八十五条"]["value"] == "585"
          and by_text.get("第二款", {}).get("class") == "rule_number"
          and by_text.get("第三项", {}).get("class") == "rule_number"
          and by_text.get("三年", {}).get("class") == "rule_number"
          and by_text["三年"]["unit"] == "年"
          and by_text["第五百八十五条"]["exemption"]["discipline"]
          == "rule_borne")
    checks.add("S1_rule_number_classified", ok,
               "条文号 585＋款/项跟随＋诉讼时效三年＝rule_number，豁免纪律"
               "=rule_borne")

    ok = (by_text.get("百分之三十", {}).get("class") == "negative_semantics"
          and by_text["百分之三十"]["polarity"] == "upper_bound"
          and by_text.get("500元", {}).get("class") == "negative_semantics"
          and by_text["500元"]["polarity"] == "below"
          and by_text.get("一千元", {}).get("class") == "negative_semantics"
          and by_text["一千元"]["polarity"] == "upper_bound"
          and by_text["百分之三十"]["exemption"]["discipline"]
          == "polarity_bounded")
    checks.add("S1_negative_semantics_classified", ok,
               "辖域前缀（不得超过→upper_bound/不足→below）＋后缀界线"
               "（一千元以下→upper_bound）＝negative_semantics，极性随记")

    counts = result.get("counts", {})
    mentions = result.get("mentions", [])
    ok = (counts.get("total") == len(mentions)
          and all(counts.get(k) == sum(1 for m in mentions
                                       if m["class"] == k)
                  for k in ("fact_amount", "rule_number",
                            "negative_semantics", "unknown")))
    checks.add("S1_counts_reconcile", ok, "逐 mention 计数对账：%s" % counts)
    return result


def section_s2(checks: Checks, config: dict) -> None:
    result = _classify(
        checks,
        "合同约定租期三十日；台账编号12345；成功率30%；自2026年8月20日起算。",
        config, "S2_classify_ambiguous_doc")
    by_text = {m["text"]: m for m in result.get("mentions", [])}
    ok = all(by_text.get(t, {}).get("class") == "unknown"
             and by_text[t]["pending_review"] is True
             and by_text[t]["reason"] == reason
             and by_text[t]["exemption"] == {"fact_crosscheck": None,
                                             "discipline": "pending_review"}
             for t, reason in (("三十日", "bare_duration"),
                               ("12345", "bare_number"),
                               ("30%", "bare_percent"),
                               ("2026年", "calendar_expression")))
    ok = ok and result.get("pending_review") is True
    checks.add("S2_unknown_pending_review_named", ok,
               "裸期限/裸数/裸百分数/日历表达式→unknown＋pending_review＋"
               "具名 reason（UNKNOWN 不伪填不猜）")

    mixed = _classify(checks, "合计人民币12万五千元；费用合计1,00,000元。",
                      config, "S2_classify_mixed_form")
    by_text = {m["text"]: m for m in mixed.get("mentions", [])}
    ok = (by_text.get("人民币12万五千元", {}).get("class") == "fact_amount"
          and by_text["人民币12万五千元"]["value"] is None
          and by_text["人民币12万五千元"]["pending_review"] is True
          and by_text["人民币12万五千元"]["reason"]
          == "amount_value_unparseable"
          and by_text.get("1,00,000元", {}).get("value") is None)
    checks.add("S2_mixed_form_value_pending_not_guessed", ok,
               "混形态（阿拉伯＋中文混写）与不成组千位逗号：类可定、值=None"
               "＋待核（绝不猜值）")


def section_s3(checks: Checks, config: dict) -> list:
    results = []
    # 正确算式（多笔付款）
    r = call_entry("number.verify_amount", {
        "principal": "100000",
        "payments": [{"payment_id": "P1", "amount": "30000"},
                     {"payment_id": "P2", "amount": "20000"}],
        "claimed_balance": "50000",
    }, config)
    payload = r["payload"].get("result", {}) if r["exit"] == 0 else {}
    ok = (r["exit"] == 0 and payload.get("verdict") == "CONSISTENT"
          and payload.get("jc_balance") == "50000"
          and payload.get("delta_jc_minus_claimed") == "0"
          and payload.get("amounts", {}).get("payments_total") == "50000")
    checks.add("S3_correct_formula_consistent_via_jc", ok,
               "100000−(30000+20000)=50000 经 JC 求值 CONSISTENT（delta=0）")
    results.append(payload)

    # 小数精确（Decimal/Fraction 全程无浮点误差）
    r = call_entry("number.verify_amount", {
        "principal": "1000.50",
        "payments": [{"payment_id": "P1", "amount": "0.25"}],
        "claimed_balance": "1000.25",
    }, config)
    payload = r["payload"].get("result", {}) if r["exit"] == 0 else {}
    ok = (r["exit"] == 0 and payload.get("verdict") == "CONSISTENT"
          and payload.get("jc_balance") == "1000.25")
    checks.add("S3_fractional_exact_decimal_all_the_way", ok,
               "1000.50−0.25=1000.25 小数位精确（float 会丢位处仍精确；"
               "产品侧 Decimal＋JC 侧 Fraction）")
    results.append(payload)

    # 契约面：jc-harness-local/1＋run/input refs＋P01 入口（17 卡：保存
    # input/result refs 与 unknown）
    ok = all(p.get("jc", {}).get("contract") == "jc-harness-local/1"
             and p.get("jc", {}).get("entry") == "P01 jc.evaluate"
             and p.get("jc", {}).get("completion")
             == "exact_finite_scenarios"
             and p.get("jc", {}).get("run_identity_ref", {})
             .get("kind") == "run-identity"
             and p.get("jc", {}).get("input_ref")
             and p.get("arithmetic", {}).get("float_used") is False
             for p in results if p)
    checks.add("S3_jc_contract_and_refs_recorded", ok,
               "金额求值记录 jc-harness-local/1 契约＋run_identity_ref＋"
               "input_ref（P01 冻结面）＋float_used=False")
    return results


def section_s4(checks: Checks, config: dict) -> None:
    # 错误算式反例：文书主张 80000，JC 求值 70000 → MISMATCH 具名拒绝
    r = call_entry("number.verify_amount", {
        "principal": "100000",
        "payments": [{"payment_id": "P1", "amount": "30000"}],
        "claimed_balance": "80000",
    }, config)
    payload = r["payload"].get("result", {}) if r["exit"] == 0 else {}
    ok = (r["exit"] == 0 and payload.get("verdict") == "MISMATCH"
          and payload.get("jc_balance") == "70000"
          and payload.get("claimed_balance") == "80000"
          and payload.get("delta_jc_minus_claimed") == "-10000")
    checks.add("S4_wrong_formula_counterexample_rejected", ok,
               "错误算式反例（主张 80000≠JC 求值 70000）→ MISMATCH 具名"
               "（两侧精确值＋差值 -10000），绝不静默放行")
    # float 金额拒收（Decimal 红线）
    r = call_entry("number.verify_amount", {
        "principal": 100.5, "claimed_balance": "1",
    }, {"jc_state_root": "unused"})
    payload = r["payload"]
    ok = (r["exit"] == 3 and payload.get("status") == "NOT_CONNECTED"
          and payload.get("code")
          == "number_face_failed:amount_float_rejected:principal")
    checks.add("S4_float_amount_rejected", ok,
               "float 金额入参 → exit 3 %s" % payload.get("code"))


def section_s5(checks: Checks, config: dict) -> None:
    # 同输入两跑字节级同输出
    r1 = call_entry("number.classify", {"text": SYNTH_DOC}, config)
    r2 = call_entry("number.classify", {"text": SYNTH_DOC}, config)
    canonical1 = json.dumps(r1["payload"], ensure_ascii=False, sort_keys=True)
    canonical2 = json.dumps(r2["payload"], ensure_ascii=False, sort_keys=True)
    checks.add("S5_deterministic_byte_identical", canonical1 == canonical2,
               "同输入两跑 JSON 规范形逐字节相等（零随机/零时钟）")
    # AST：分类模块零网络/零随机/零模型导入
    tree = ast.parse(NUMBER_MODULE.read_text(encoding="utf-8"))
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(a.name.split(".")[0] for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".")[0])
    checks.add("S5_no_model_network_random_imports",
               not (imported & BANNED_IMPORTS),
               "number_classifier.py 导入面=%s（无模型/网络/随机）"
               % sorted(imported))
    # 分类面零 JC 依赖（分类不求值金额；金额求值单独经 verify_amount→JC）
    checks.add("S5_classify_face_has_no_jc_dependency",
               "compiler_core" not in NUMBER_MODULE.read_text(encoding="utf-8")
               and "legal_entry" not in NUMBER_MODULE.read_text(encoding="utf-8"),
               "分类纯函数不吃 jc 配置（三分类≠金额求值，不把分类面混入"
               "求值面）")


def section_s6(checks: Checks, config: dict) -> None:
    r = call_entry("number.classify_all", {"text": "1元"}, config)
    payload = r["payload"]
    checks.add("S6A_unknown_method_fails_named_exit3",
               r["exit"] == 3 and payload.get("status") == "NOT_CONNECTED"
               and str(payload.get("code"))
               .startswith("method_not_connected:"),
               "number.classify_all → exit=%s %s/%s" % (
                   r["exit"], payload.get("status"), payload.get("code")))
    r = call_entry("number.classify", {}, config)
    payload = r["payload"]
    checks.add("S6B_missing_text_fails_named_exit3",
               r["exit"] == 3 and payload.get("status") == "NOT_CONNECTED"
               and payload.get("code") == "number_classify_text_required",
               "classify 缺 text → exit=%s %s" % (r["exit"],
                                                  payload.get("code")))
    r = call_entry("number.verify_amount",
                   {"principal": "1", "claimed_balance": "1"}, {})
    payload = r["payload"]
    checks.add("S6C_missing_jc_config_fails_named_exit3",
               r["exit"] == 3 and payload.get("status") == "NOT_CONNECTED"
               and payload.get("code") == "jc_state_root_not_configured",
               "verify_amount 缺 jc 配置 → exit=%s %s" % (
                   r["exit"], payload.get("code")))


def run_profile(profile: str, args, client_digest: str) -> tuple[Checks, dict]:
    """跑一个 profile 的全部断言；返回 (checks, evidence)。"""
    with tempfile.TemporaryDirectory(prefix="f89-recon-") as scratch:
        config = jc_config(args.jc_repo, Path(scratch))
        checks = Checks()
        s1 = section_s1(checks, config)
        section_s2(checks, config)
        s3 = section_s3(checks, config)
        section_s4(checks, config)
        section_s5(checks, config)
        section_s6(checks, config)
    commit = subprocess.run(
        ["git", "rev-parse", "HEAD"], capture_output=True, text=True,
        cwd=str(REPO_ROOT)).stdout.strip()
    evidence = {
        "run_date": RUN_DATE,
        "profile": profile,
        "command": "python -X utf8 %s --profile %s --jc-repo %s" % (
            sys.argv[0], profile, args.jc_repo),
        "cwd": str(REPO_ROOT),
        "subject_commit": commit,
        "frozen_face": {
            "jc_client.py(P01)": client_digest,
            "number_classifier.py": sha256_file(NUMBER_MODULE),
        },
        "synthetic_doc": SYNTH_DOC,
        "classification_counts": s1.get("counts"),
        "amount_samples": [
            {"verdict": p.get("verdict"), "claimed": p.get("claimed_balance"),
             "jc_balance": p.get("jc_balance"),
             "delta": p.get("delta_jc_minus_claimed")}
            for p in s3 if p
        ],
        "checks": checks.items,
        "passed": checks.passed_count,
        "total": len(checks.items),
        "overall": "PASS" if checks.all_passed else "FAIL",
    }
    out_dir = REPO_ROOT / args.evidence_root / profile
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "f89-number-classification-recon.json").write_text(
        json.dumps(evidence, ensure_ascii=False, indent=1),
        encoding="utf-8")
    print("---")
    print("RECON_%s %d/%d checks — profile=%s" % (
        "OK" if checks.all_passed else "FAIL",
        checks.passed_count, len(checks.items), profile))
    return checks, evidence


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", action="append",
                        choices=("desktop", "selfhost"), dest="profiles",
                        help="可重复：--profile desktop --profile selfhost")
    parser.add_argument("--jc-repo", default=DEFAULT_JC_REPO)
    parser.add_argument("--evidence-root", default="evidence/F89")
    args = parser.parse_args()
    profiles = args.profiles or ["desktop"]

    client_path = os.path.join(args.jc_repo, JC_CLIENT_REL)
    if not Path(client_path).is_file():
        print("FATAL: P01 钉定 JC 检出缺 %s" % client_path)
        return 2
    client_digest = sha256_file(client_path)
    if client_digest != JC_CLIENT_SHA256:
        print("FATAL: JC client.py sha256 漂移（P01 钉定失效）")
        return 2

    all_checks = []
    for profile in profiles:
        checks, _ = run_profile(profile, args, client_digest)
        all_checks.append((profile, checks))
    return 0 if all(c.all_passed for _, c in all_checks) else 1


if __name__ == "__main__":
    raise SystemExit(main())

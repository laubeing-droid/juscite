# -*- coding: utf-8 -*-
"""W4-U48 / F109 acceptance: damages calculator (C07) bridge wiring.

06:F109 (F109-desktop/F109-selfhost; owner jc+product; entries P01; 17 card
stage「✅v1.5 首批扩充（不进 v1 首批九个）」): the C07 damages family is
consumed through the pinned P01 JCClient surface at the JC w4-u48 branch
head (based on the W4-U25 delivered commit 066ad59). The registry readback
shows TEN slots — the frozen nine byte-stable plus the named C07 row in
``v1_5_families``, with the three CALC_SCOPE_U0x_NAME_UNKNOWN gaps still
unfilled (12号文档§2: F109 never fills a gap). Real calculations ride the
existing sealed calc-family sheet path: independent checker agreement
before sealing, input/result refs registered owner=jc, typed JC refusals
surface as JC_FAILURE carrying the JC code — a missing region/year base is
``rule_pack_absent`` (never last year's figure, never 0), incomplete wage
rule premises refuse by name, floats refuse (F89).

All money inputs below are synthetic engineering fixtures; statutory
constants are asserted at their gazette values (法释〔2022〕14号/
工伤保险条例586号修订/浙江省工伤保险条例第27条, read from the E22 frozen
codices baseline) and statistical bases at their official communiqué values
(2026-10-20 直读: 全国2024=54188元, 全国2025=56502元, 山东2025=56444元,
江苏2025=68956元).
"""
import json
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE / "python"))
import legal_entry  # noqa: E402

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

# 官方锚点（2026-10-20 直读钉定）：
SD = "370000"
JS = "320000"
ZJ = "330000"
WAGE_SRC = "synthetic-certified-wage-fact"

# 全国城镇居民人均可支配收入 2025 = 56502 元 → 工亡一次性补助金 = ×20
OFFICIAL_DEATH_BENEFIT_2025_MINOR = 113004000
# 山东 2025 = 56444 元 × 20 年 × 0.3 = 338664 元
OFFICIAL_SD_DISABILITY_MINOR = 33866400
# 江苏 2025 = 68956 元 × 5 年（75 岁以上按 5 年）
OFFICIAL_JS_DEATH_75_MINOR = 34478000
# 工伤十级 7 个月 × 本金工资 8000 元（封顶保底内）
OFFICIAL_GRADE10_LUMP_MINOR = 5600000

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


def _require_pins():
    if not (JC_REPO / "compiler_core" / "damages.py").is_file():
        raise AssertionError(
            f"pinned JC w4-u48 worktree missing at {JC_REPO}; "
            "the F109 damages bridge cannot be verified")
    for relative, want in JC_SHA256.items():
        import hashlib
        got = hashlib.sha256((JC_REPO / relative).read_bytes()).hexdigest()
        assert got == want, f"{relative} drifted: {got[:12]}… != pinned {want[:12]}…"


_ACTIVE_TMPDIRS = []


def _config(tmp_path=None):
    _require_pins()
    holder = tempfile.TemporaryDirectory()
    _ACTIVE_TMPDIRS.append(holder)   # keep alive for the subprocess lifetime
    tmp_path = Path(holder.name)
    rules = tmp_path / "rules"
    rules.mkdir(parents=True, exist_ok=True)
    (rules / "jc-local-pack.json").write_text(
        json.dumps(RULE_PACK, ensure_ascii=False), encoding="utf-8")
    return {
        "jc_state_root": str(tmp_path / "state"),
        "jc_rule_roots": [str(rules)],
        "jc_import_path": str(JC_REPO),
    }


def call_cli(method: str, args: dict, config: dict):
    """真产品入口子进程径（legal_entry CLI；P01 桥同 F104 recon 纪律）。"""
    with tempfile.TemporaryDirectory() as tmp:
        req = Path(tmp) / "request.json"
        cfg = Path(tmp) / "config.json"
        req.write_text(json.dumps({"method": method, "args": args},
                                  ensure_ascii=False), encoding="utf-8")
        cfg.write_text(json.dumps(config, ensure_ascii=False), encoding="utf-8")
        proc = subprocess.run(
            [sys.executable, "-X", "utf8", str(HERE / "python" / "legal_entry.py"),
             "--request-json", str(req), "--config", str(cfg)],
            capture_output=True, text=True, encoding="utf-8", timeout=300)
        try:
            payload = json.loads(proc.stdout)
        except json.JSONDecodeError:
            payload = {"status": "RAW", "stdout": proc.stdout[:400]}
        return proc.returncode, payload


import unittest  # noqa: E402


class F109DamagesWiring(unittest.TestCase):
    def test_ten_slot_registry_via_bridge(self):
        config = _config()
        code, out = call_cli("calc.registry", {}, config)
        self.assertEqual(code, 0)
        registry = out["result"]
        slots = [row["slot"] for row in registry["nine_families"]]
        self.assertEqual(slots, ["C01", "C02", "C03", "C04", "C05",
                                 "C06", "U01", "U02", "U03"])
        v15 = registry["v1_5_families"]
        self.assertEqual([row["slot"] for row in v15], ["C07"])
        self.assertEqual(v15[0]["zh_name"], "赔偿金")
        self.assertEqual(v15[0]["status"], "SUPPORTED_V1_5_BATCH")
        # gaps stay unfilled
        for gap in registry["nine_families"]:
            if gap["slot"].startswith("U"):
                self.assertIsNone(gap["zh_name"])
                self.assertIsNone(gap["public_entry"])
        # v1 frozen rule_packs byte-stable (C07 packs live on the C07 row)
        self.assertEqual(registry["rule_packs"], {
            "C03": "cn-court-fee/sc-481-2007@1",
            "C04": "cn-preservation-fee/sc-481-2007@1",
            "C05": "cn-lawyer-contingency/sft-2021-87@1",
            "C06": "cietac/2024@1"})

    def test_disability_shandong_official_value_and_checker(self):
        config = _config()
        code, out = call_cli("calc.damages", {"input": {
            "domain": "personal_injury", "item": "disability_compensation",
            "region": SD, "year": 2025, "age": 45,
            "disability_index": "0.3"}}, config)
        self.assertEqual(code, 0, out)
        sheet = out["result"]
        self.assertEqual(sheet["amount_minor"], OFFICIAL_SD_DISABILITY_MINOR)
        self.assertEqual(sheet["amount"], "338664")
        self.assertTrue(sheet["independentChecker"]["agreed"])
        self.assertIn("calculationReceiptRef", sheet)
        self.assertEqual(sheet["matterId"], "unscoped")

    def test_death_benefit_75_and_work_death_2025(self):
        config = _config()
        code, out = call_cli("calc.damages", {"matter_id": "m-f109-1",
                                              "input": {
            "domain": "traffic", "item": "death_compensation",
            "region": JS, "year": 2025, "age": 78}}, config)
        self.assertEqual(code, 0, out)
        self.assertEqual(out["result"]["amount_minor"],
                         OFFICIAL_JS_DEATH_75_MINOR)
        code, out = call_cli("calc.damages", {"input": {
            "domain": "work_injury", "item": "death_benefit",
            "year": 2025}}, config)
        self.assertEqual(code, 0, out)
        self.assertEqual(out["result"]["amount_minor"],
                         OFFICIAL_DEATH_BENEFIT_2025_MINOR)

    def test_work_injury_lump_sum_and_grade_table(self):
        config = _config()
        months = {1: 27, 2: 25, 3: 23, 4: 21, 5: 18, 6: 16,
                  7: 13, 8: 11, 9: 9, 10: 7}
        for grade, m in months.items():
            code, out = call_cli("calc.damages", {"input": {
                "domain": "work_injury", "item": "lump_sum_disability",
                "grade": grade, "monthly_wage_minor": 800000,
                "regional_avg_monthly_wage_minor": 700000,
                "regional_wage_source": WAGE_SRC}}, config)
            self.assertEqual(code, 0, out)
            self.assertEqual(out["result"]["amount_minor"], 800000 * m)

    def test_missing_base_is_typed_rule_pack_absent(self):
        config = _config()
        for payload in (
            {"domain": "personal_injury", "item": "death_compensation",
             "region": SD, "year": 2024, "age": 50},       # 未装年度
            {"domain": "personal_injury", "item": "death_compensation",
             "region": "440000", "year": 2025, "age": 50},  # 未装省份
            {"domain": "personal_injury", "item": "funeral_expenses",
             "region": SD, "year": 2025, "age": 50},        # 丧葬费具名缺口
            {"domain": "work_injury", "item": "zj_one_time_medical",
             "region": SD, "grade": 7,
             "province_avg_monthly_wage_minor": 800000,
             "province_wage_source": WAGE_SRC},             # 31省不装样子
        ):
            code, out = call_cli("calc.damages", {"input": payload}, config)
            self.assertEqual(code, 4, (payload, out))
            self.assertEqual(out["status"], "JC_FAILURE")
            self.assertIn("rule_pack_absent", str(out.get("code", "")))

    def test_wage_premise_missing_and_float_refused(self):
        config = _config()
        code, out = call_cli("calc.damages", {"input": {
            "domain": "work_injury", "item": "lump_sum_disability",
            "grade": 8, "monthly_wage_minor": 600000}}, config)
        self.assertEqual(code, 4)
        self.assertIn("damages_wage_premise_missing", str(out.get("code", "")))
        code, out = call_cli("calc.damages", {"input": {
            "domain": "work_injury", "item": "lump_sum_disability",
            "grade": 8, "monthly_wage_minor": 600000.5,
            "regional_avg_monthly_wage_minor": 700000,
            "regional_wage_source": WAGE_SRC}}, config)
        self.assertEqual(code, 4)
        self.assertIn("damages_float_input_refused", str(out.get("code", "")))

    def test_unconfigured_bridge_fails_closed(self):
        code, out = call_cli("calc.damages", {"input": {
            "domain": "work_injury", "item": "death_benefit", "year": 2025}}, {})
        self.assertEqual(code, 3)
        self.assertEqual(out["status"], "NOT_CONNECTED")

    def test_unknown_method_never_reaches_calculator(self):
        config = _config()
        code, out = call_cli("calc.damages_x", {"input": {}}, config)
        self.assertEqual(code, 3)
        self.assertEqual(out["status"], "NOT_CONNECTED")

    def test_c07_pack_injection_refused(self):
        # F112 注入通道不适用 C07：JC typed 拒
        config = _config()
        code, out = call_cli("calc.rule_pack_replay", {
            "pack_id": "cn-urban-disposable-income",
            "family": "C07",
            "input": {"domain": "work_injury", "item": "death_benefit",
                      "year": 2025}}, config)
        self.assertEqual(code, 4)
        self.assertIn("rule_pack_unknown", str(out.get("code", "")))


if __name__ == "__main__":
    unittest.main()

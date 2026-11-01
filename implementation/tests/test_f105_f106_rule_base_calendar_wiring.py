# -*- coding: utf-8 -*-
"""W2b-U54 acceptance: F105 rule-base recon + F106 calendar version bridge.

F105 (06:F105 assertion): the MatterVibe fixture is difference-finding,
never ground truth — the recon report through the frozen calc.* bridge is
a statement-only document (closed relations, no pass/fail verdict), it is
NOT acceptance truth, competitor wrong values never modify JC output, the
BAC RULE_PACK_ABSENT gap stays closed, and the U01-U03 slots stay
CALC_SCOPE_*_NAME_UNKNOWN (toolbox seven ≠ nine families; the F110-cut
文本去重/字数统计 never fill slots).

F106 (06:F106 assertion): the versioned calendar account reads back the
actual year, region, adjusted workdays (调休补班) and document-number
version on every dated answer; the next-day start rule is applied for day
periods; an out-of-range year returns the structured UNKNOWN receipt with
NO date fields — the 2025/2026 tables never extrapolate.

All materials are synthetic; the pinned JC w2b-u54 worktree is consumed
read-only (same-wave pinning per W2a-U16 discipline, re-asserted in
setUp so cross-wave module caching cannot silently substitute another
worktree's compiler_core).
"""
import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE / "python"))
import legal_entry

JC_REPO = Path(
    r"D:\Codex\1.法律工作区\juris-calculus工作区\juris-calculus\.local\worktrees\w2b-u54")

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

_ACTIVE_TMPDIRS = []


def _pin_jc_worktree():
    """Fresh same-wave pin: purge any cached compiler_core (earlier wave
    tests in the same pytest process may have imported w2b-u19/w2b-u27)
    and resolve the next import to THIS unit's worktree."""
    if not (JC_REPO / "compiler_core" / "rule_base_recon.py").is_file():
        raise AssertionError(
            f"pinned JC w2b-u54 worktree missing at {JC_REPO}; "
            "the F105/F106 bridge cannot be verified")
    while str(JC_REPO) in sys.path:
        sys.path.remove(str(JC_REPO))
    sys.path.insert(0, str(JC_REPO))
    for name in [m for m in list(sys.modules)
                 if m == "compiler_core" or m.startswith("compiler_core.")]:
        del sys.modules[name]


def _config(tmp_path=None):
    _pin_jc_worktree()
    if tmp_path is None:
        holder = tempfile.TemporaryDirectory()
        _ACTIVE_TMPDIRS.append(holder)
        tmp_path = Path(holder.name)
    elif isinstance(tmp_path, tempfile.TemporaryDirectory):
        tmp_path = Path(tmp_path.name)
    else:
        tmp_path = Path(tmp_path)
    rules = tmp_path / "rules"
    rules.mkdir(parents=True, exist_ok=True)
    (rules / "jc-local-pack.json").write_text(
        json.dumps(RULE_PACK, ensure_ascii=False), encoding="utf-8")
    return {
        "jc_state_root": str(tmp_path / "state"),
        "jc_rule_roots": [str(rules)],
        "jc_import_path": str(JC_REPO),
    }


def _run_cli(request, config, tmp_path):
    request_json = tmp_path / "request.json"
    config_json = tmp_path / "config.json"
    request_json.write_text(json.dumps(request, ensure_ascii=False), encoding="utf-8")
    config_json.write_text(json.dumps(config, ensure_ascii=False), encoding="utf-8")
    proc = subprocess.run(
        [sys.executable, "-X", "utf8", str(HERE / "python" / "legal_entry.py"),
         "--request-json", str(request_json), "--config", str(config_json)],
        capture_output=True, text=True, encoding="utf-8", timeout=300)
    return proc, json.loads(proc.stdout)


class F105F106RuleBaseCalendarWiringTests(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        _pin_jc_worktree()

    @classmethod
    def tearDownClass(cls):
        while _ACTIVE_TMPDIRS:
            _ACTIVE_TMPDIRS.pop().cleanup()

    # -- bridge freeze ----------------------------------------------------

    def test_pinned_jc_worktree_carries_u54_modules(self):
        for relative in ("compiler_core/rule_base_recon.py",
                         "compiler_core/calendar_versions.py"):
            digest = hashlib.sha256(
                (JC_REPO / relative).read_bytes()).hexdigest()
            self.assertEqual(len(digest), 64)

    def test_same_family_extension_of_calc_group(self):
        self.assertTrue({"calc.rule_base_recon", "calc.calendar_account",
                         "calc.calendar_due_date"}
                        .issubset(legal_entry.CALC_FAMILY_METHODS))
        # W4-U48 (F109): calc.damages joins as the C07 v1.5 extension — ten
        # methods in the one frozen calc.* group.
        self.assertEqual(len(legal_entry.CALC_FAMILY_METHODS), 10)
        # P01 frozen jc.* list untouched
        self.assertEqual(legal_entry.JC_METHODS, (
            "jc.case_bundle", "jc.evaluate", "jc.read_run",
            "jc.horn_subject_state", "jc.business_delivery_documents",
            "jc.verify_business_delivery"))

    # -- F105: difference statement, never ground truth --------------------

    def test_recon_report_is_statement_only(self):
        config = _config()
        report = legal_entry.call("calc.rule_base_recon", {}, config)
        self.assertEqual(report["recon_id"], "f105-rule-base-recon")
        self.assertEqual(report["disposition"], "difference_statement_only")
        self.assertEqual(report["truth_adjudication"],
                         "REFUSED_NOT_ACCEPTANCE_TRUTH")
        for forbidden in ("verdict", "passed", "agreed", "ok"):
            self.assertNotIn(forbidden, report)
        for row in report["rows"]:
            self.assertIn(row["relation"], report["relation_vocabulary"])
        # named faces: 诉讼费十段 AGREE / 贸仲受理费 DIFFER / 北仲缺口保持
        rows = {(row["section"], row["item"]): row for row in report["rows"]}
        self.assertEqual(
            sum(1 for (section, item) in rows
                if section == "court_fee" and item.endswith("档")), 10)
        self.assertEqual(
            rows[("arbitration", "贸仲受理费 样例100万元")]["relation"], "DIFFER")
        self.assertEqual(rows[("arbitration", "北仲（BAC）")]["relation"],
                         "GAP_JC_SIDE")
        self.assertIn("RULE_PACK_ABSENT",
                      rows[("arbitration", "北仲（BAC）")]["jc_value"])
        # 12号文档§3.1：月末夹取差异必须在夹具
        month_end = rows[("calendar", "月末/闰日加法语义")]
        self.assertEqual(month_end["relation"], "SEMANTICS_DIFFER")
        self.assertIn("2026-02-28", month_end["jc_value"])
        self.assertIn("2026-03-03", month_end["competitor_value"])

    def test_competitor_values_never_override_official_output(self):
        config = _config()
        legal_entry.call("calc.rule_base_recon", {}, config)
        # 对拍之后官方值原样：竞品通行流传版 18550 没有进入 JC 输出
        sheet = legal_entry.call("calc.arbitration_fee", {
            "input": {"institution": "cietac", "table": "in",
                      "amount_minor": 100_000_000}}, config)
        self.assertEqual(sheet["acceptance_amount_minor"], 1_700_000)
        self.assertEqual(sheet["handling_amount_minor"], 1_950_000)
        self.assertEqual(legal_entry.call("calc.court_fee", {
            "input": {"amount_minor": 10_000_000}}, config)["amount_minor"],
            230_000)
        # 北仲缺口对拍后仍 typed 拒——竞品表不补缺口
        with self.assertRaises(legal_entry.JCMethodFailure) as caught:
            legal_entry.call("calc.arbitration_fee", {
                "input": {"institution": "bac", "table": "out",
                          "amount_minor": 1}}, config)
        self.assertIn("rule_pack_absent", str(caught.exception))
        # U01-U03 槽对拍后仍具名拒——工具箱 7 件不填槽
        client = legal_entry._jc_client(config)
        for slot in ("U01", "U02", "U03"):
            with self.assertRaises(Exception) as caught:
                client.calculate_family({"family": slot, "input": {}})
            self.assertEqual(getattr(caught.exception, "code", None),
                             f"CALC_SCOPE_{slot}_NAME_UNKNOWN")

    # -- F106: versioned calendar, unknown out of range --------------------

    def test_calendar_account_reads_back_version_and_adjusted_workdays(self):
        config = _config()
        account = legal_entry.call("calc.calendar_account", {
            "request": {"year": 2026, "region": "CN-mainland"}}, config)
        self.assertEqual(account["status"], "COVERED")
        self.assertEqual(account["year"], 2026)
        self.assertEqual(account["region"], "CN-mainland")
        self.assertEqual(account["calendar_version"],
                         "cn-holiday/gobafamingdian-2025-7@1")
        self.assertEqual(account["source"]["document_number"],
                         "国办发明电〔2025〕7号")
        self.assertEqual(account["adjusted_workdays"], [
            "2026-01-04", "2026-02-14", "2026-02-28",
            "2026-05-09", "2026-09-20", "2026-10-10"])
        self.assertTrue(account["start_rule"]["version"].startswith(
            "cn-procedure-period-start/"))

    def test_out_of_range_year_returns_unknown_without_dates(self):
        config = _config()
        for year in (2027, 2030, 2024):
            receipt = legal_entry.call("calc.calendar_account", {
                "request": {"year": year, "region": "CN-mainland"}}, config)
            self.assertEqual(receipt["status"], "UNKNOWN")
            self.assertEqual(receipt["reason_code"], "calendar_year_out_of_range")
            self.assertFalse(receipt["date_fields_present"])
            self.assertNotIn("holidays", receipt)
        due = legal_entry.call("calc.calendar_due_date", {
            "request": {"year": 2026, "region": "CN-mainland",
                        "anchor_date": "2026-12-20", "count": 30,
                        "unit": "days"}}, config)
        self.assertEqual(due["status"], "UNKNOWN")
        self.assertEqual(due["reason_code"], "calendar_year_out_of_range")
        self.assertNotIn("due_date", due)

    def test_due_date_next_day_start_adjusted_workday_and_holiday_roll(self):
        config = _config()
        # 次日起算：届满日＝起算日＋count
        plain = legal_entry.call("calc.calendar_due_date", {
            "request": {"year": 2026, "region": "CN-mainland",
                        "anchor_date": "2026-06-01", "count": 15,
                        "unit": "days"}}, config)
        self.assertEqual(plain["due_date"], "2026-06-16")
        self.assertTrue(plain["start_rule"]["applied"])
        # 调休补班周六＝工作日（2026-02-28）
        adjusted = legal_entry.call("calc.calendar_due_date", {
            "request": {"year": 2026, "region": "CN-mainland",
                        "anchor_date": "2026-02-14", "count": 14,
                        "unit": "days"}}, config)
        self.assertEqual(adjusted["due_date"], "2026-02-28")
        self.assertFalse(adjusted["rolled"])
        # 假日顺延并回读原因（中秋 9/25-9/27 → 9/28）
        rolled = legal_entry.call("calc.calendar_due_date", {
            "request": {"year": 2026, "region": "CN-mainland",
                        "anchor_date": "2026-09-25", "count": 1,
                        "unit": "days"}}, config)
        self.assertEqual(rolled["due_date"], "2026-09-28")
        self.assertTrue(rolled["rolled"])
        self.assertEqual(rolled["roll_reason"], "中秋")
        # 月末夹取（JC 冻结语义，与竞品 JS 溢出的差异在对拍夹具陈述）
        clamped = legal_entry.call("calc.calendar_due_date", {
            "request": {"year": 2026, "region": "CN-mainland",
                        "anchor_date": "2026-01-31", "count": 1,
                        "unit": "months"}}, config)
        self.assertEqual(clamped["due_date"], "2026-02-28")
        # 带日期的答案必带版本号——无版本号日历命中结构性不存在
        for receipt in (plain, adjusted, rolled, clamped):
            self.assertTrue(receipt["calendar_version"].startswith("cn-holiday/"))
            self.assertIn("国办发明电", receipt["source"]["document_number"])

    # -- bridge fail-closed -------------------------------------------------

    def test_typed_failures_and_not_connected(self):
        config = _config()
        # 恶意/坏形输入：JC typed 拒 → JC_FAILURE（exit 4）
        with self.assertRaises(legal_entry.JCMethodFailure) as caught:
            legal_entry.call("calc.calendar_account", {
                "request": {"year": "2026", "region": "CN-mainland"}}, config)
        self.assertIn("calendar_year_invalid", str(caught.exception))
        with self.assertRaises(legal_entry.JCMethodFailure) as caught:
            legal_entry.call("calc.rule_base_recon",
                             {"request": {"x": 1}}, config)
        self.assertIn("recon_request_unknown_field", str(caught.exception))
        # 缺 request
        with self.assertRaises(legal_entry.NotConnected):
            legal_entry.call("calc.calendar_account", {}, config)
        # 未知方法 / 未配置：NOT_CONNECTED（exit 3）
        with self.assertRaises(legal_entry.NotConnected) as caught:
            legal_entry.call("calc.rule_base", {}, config)
        self.assertEqual(str(caught.exception),
                         "method_not_connected:calc.rule_base")
        with self.assertRaises(legal_entry.NotConnected):
            legal_entry.call("calc.rule_base_recon", {}, {})

    def test_cli_roundtrip_owner_response_jc_failure_not_connected(self):
        holder = tempfile.TemporaryDirectory()
        _ACTIVE_TMPDIRS.append(holder)
        tmp = Path(holder.name)
        config = _config(tmp)
        proc, payload = _run_cli(
            {"method": "calc.calendar_due_date",
             "args": {"request": {"year": 2026, "region": "CN-mainland",
                                  "anchor_date": "2026-10-01", "count": 1,
                                  "unit": "days"}}}, config, tmp)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertEqual(payload["status"], "OWNER_RESPONSE")
        # 国庆 10/1 休 → 顺延；10/8（周四）工作日
        self.assertEqual(payload["result"]["due_date"], "2026-10-08")
        self.assertTrue(payload["result"]["rolled"])
        # UNKNOWN 也是结构化 OWNER_RESPONSE（超范围年份→unknown 不是崩溃）
        proc2, payload2 = _run_cli(
            {"method": "calc.calendar_account",
             "args": {"request": {"year": 2027, "region": "CN-mainland"}}},
            config, tmp)
        self.assertEqual(proc2.returncode, 0)
        self.assertEqual(payload2["result"]["status"], "UNKNOWN")
        # typed 拒绝 exit 4
        proc3, payload3 = _run_cli(
            {"method": "calc.calendar_due_date",
             "args": {"request": {"year": 2026, "region": "CN-mainland",
                                  "anchor_date": "2026-01-01", "count": 1,
                                  "unit": "fortnights"}}}, config, tmp)
        self.assertEqual(proc3.returncode, 4)
        self.assertEqual(payload3["status"], "JC_FAILURE")
        self.assertIn("calendar_unit_unknown", payload3["code"])
        # 未知方法 exit 3
        proc4, payload4 = _run_cli({"method": "calc.calendar", "args": {}},
                                   config, tmp)
        self.assertEqual(proc4.returncode, 3)
        self.assertEqual(payload4["status"], "NOT_CONNECTED")

    def test_bridge_determinism_same_input_same_bytes(self):
        request = {"method": "calc.rule_base_recon", "args": {}}
        results = []
        for _ in range(2):
            holder = tempfile.TemporaryDirectory()
            _ACTIVE_TMPDIRS.append(holder)
            proc, payload = _run_cli(request, _config(Path(holder.name)),
                                     Path(holder.name))
            self.assertEqual(proc.returncode, 0)
            results.append(json.dumps(payload, sort_keys=True,
                                      ensure_ascii=False))
        self.assertEqual(results[0], results[1])


if __name__ == "__main__":
    unittest.main()

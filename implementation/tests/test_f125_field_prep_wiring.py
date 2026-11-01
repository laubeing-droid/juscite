"""W5-U16 / F125 字段准备 wiring：登记面结构＋桥面未启用负测。

裁决#21「字段准备先行」：四域字段登记面（财务对账/审批用印/归档
借阅/审批回避，LawLink 数据模型整段参考）＋公开业务面结构性未启用
（06 interface_gap=PENDING_SCOPE_NO_ENABLE）。红线逐字（06
python_entry_binding）：record_time/issue_bill/record_payment 仅律师
账单，不债权回款——登记面零 F08 账单通道标识符。金额唯一
minor_units（整分 int）。本测试只守登记面与桥面零泄漏；E16 款源账
零改动回归（台账＋字节钉＋行为级复跑）归验收 recon。
"""
import ast
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "python"))

import f125_case_admin_fields as registry  # noqa: E402
from legal_entry import NotConnected, call  # noqa: E402

REDLINE_NAMES = ("record_time", "issue_bill", "record_payment")
REDLINE_PINNED = (
    "record_time/issue_bill/record_payment仅律师账单，不债权回款")
NOT_ENABLED_METHODS = (
    "f125.finance_recon_read",
    "f125.approval_seal_submit",
    "f125.archive_borrow_request",
    "f125.approval_recusal_decide",
    "harness.f125_case_admin_read",
)
EXPECTED_DOMAIN_FIELDS = {
    "finance_reconciliation": 11,
    "approval_seal": 13,
    "archive_borrow": 12,
    "approval_recusal": 9,
}


class F125FieldPrepRegistryTest(unittest.TestCase):
    def test_registry_disabled_and_valid(self):
        self.assertIs(registry.ENABLED, False)
        registry.validate()  # Fail-Fast 内审过＝静默

    def test_four_domains_exact(self):
        self.assertEqual(
            tuple(registry.DOMAIN_FIELDS),
            ("finance_reconciliation", "approval_seal",
             "archive_borrow", "approval_recusal"))
        self.assertEqual(
            dict(registry.DOMAIN_NAMES),
            {"finance_reconciliation": "财务对账",
             "approval_seal": "审批用印",
             "archive_borrow": "归档借阅",
             "approval_recusal": "审批回避"})
        counts = {d: len(f) for d, f in registry.DOMAIN_FIELDS.items()}
        self.assertEqual(counts, EXPECTED_DOMAIN_FIELDS)

    def test_money_minor_units_only(self):
        money = [d + ":" + n
                 for d, fs in registry.DOMAIN_FIELDS.items()
                 for n, spec in fs.items()
                 if spec["type"] == "minor_units"]
        self.assertEqual(
            money, ["finance_reconciliation:amount_minor"])
        self.assertFalse(any("float" in t or "double" in t
                             for t in registry.FIELD_TYPES))

    def test_meta_pins(self):
        self.assertEqual(registry.REGISTRY_ID,
                         "juscite-f125-field-prep/1")
        self.assertEqual(registry.META["billing_channel_redline"],
                         REDLINE_PINNED)
        self.assertEqual(registry.META["interface_gap"],
                         "PENDING_SCOPE_NO_ENABLE")
        self.assertIs(registry.META["no_new_store"], True)
        self.assertIs(registry.META["second_authority"], False)
        self.assertIn("回收点", registry.META["recovery_point"])
        self.assertIn("E16", registry.META["e16_non_delay"])


class F125FieldPrepBridgeTest(unittest.TestCase):
    def test_f125_methods_not_connected(self):
        for method in NOT_ENABLED_METHODS:
            with self.assertRaises(NotConnected) as ctx:
                call(method, {"args": {}}, {})
            self.assertIn("method_not_connected:" + method,
                          str(ctx.exception))


class F125FieldPrepAstTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        base = Path(__file__).resolve().parents[1] / "python"
        cls.reg_tree = ast.parse(
            (base / "f125_case_admin_fields.py").read_text(
                encoding="utf-8"))
        cls.legal_tree = ast.parse(
            (base / "legal_entry.py").read_text(encoding="utf-8"))

    def test_registry_pure_declaration(self):
        imports = set()
        for node in ast.walk(self.reg_tree):
            if isinstance(node, ast.Import):
                imports.update(a.name for a in node.names)
            elif isinstance(node, ast.ImportFrom):
                imports.add(node.module or "")
        self.assertEqual(imports, {"__future__"})

    def test_zero_bill_channel_identifiers(self):
        hits = []
        for node in ast.walk(self.reg_tree):
            if isinstance(node, (ast.Name, ast.Attribute)):
                ident = getattr(node, "id", None) or getattr(
                    node, "attr", None)
                if ident in REDLINE_NAMES:
                    hits.append(ident)
            elif isinstance(node, ast.Constant) and isinstance(
                    node.value, str):
                if (any(n in node.value for n in REDLINE_NAMES)
                        and "仅律师账单" not in node.value):
                    hits.append(node.value[:40])
        self.assertEqual(hits, [])

    def test_legal_entry_zero_f125_dispatch(self):
        leaks = []
        for node in ast.walk(self.legal_tree):
            raw = None
            if isinstance(node, ast.Constant) and isinstance(
                    node.value, str):
                raw = node.value
            elif isinstance(node, (ast.Name, ast.Attribute, ast.arg)):
                raw = (getattr(node, "id", None)
                       or getattr(node, "attr", None)
                       or getattr(node, "arg", None))
            if raw and "f125" in raw.lower():
                leaks.append(raw)
        self.assertEqual(leaks, [])


if __name__ == "__main__":
    unittest.main()

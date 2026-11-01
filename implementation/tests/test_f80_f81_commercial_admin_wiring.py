"""W5-U02 / F80＋F81 商业服务端合成先行桥面测试：冻结方法组、fail-closed
配置面、真实幂等回执（重放同回执/异输入冲突）、撤销与余额（append-only
台账＋整型分＋余额恒非负不变量）、签到一日一签（确定性日历日）、邀请
一码一兑（双腿回执）、F81 策略真实应用到运行面（声明→桥求值→商业行为
改变端到端）、深管理不替代最小 v1 管理台（键闭集全商业面键，case.* 探
测具名拒）、案件工作台零运营位（导入图：商业/策略模块不被任何案件/业
务模块 import）、不继承上游厂商账号营销（字段闭集＋产物零营销字段）、
AST 零网络零 URL。全部合成材料（合成 org/user/金额；裁决#13-19 商业
服务端合成先行，真实托管设施 v2 商业化时补）。
"""
import ast
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'python'))

from legal_entry import (call, NotConnected, COMMERCIAL_METHODS,
                         ORG_ADMIN_METHODS)
import commercial_service as comm
import org_policy_admin as org

PY_DIR = Path(__file__).resolve().parents[1] / 'python'
MARKETING_KEYS = ('promo', 'upsell', 'newsletter', 'campaign', 'utm_')
EXPECTED_IMPORTS = {'__future__', 'hashlib', 'json', 'os', 'datetime',
                    'pathlib'}


def _cfg(root: Path) -> dict:
    return {"commercial_state_root": str(root / "comm"),
            "org_policy_state_root": str(root / "orgp")}


class F80F81CommercialAdminWiringTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.cfg = _cfg(self.root)
        self.acc = call("commercial.account_open",
                        {"org_id": "合成组织-1", "user_ref": "synth-u-1"},
                        self.cfg)["account"]["account_id"]

    def tearDown(self):
        self._tmp.cleanup()

    # -- AST 结构面（负测先行＝结构性事实）---------------------------------
    def _module_ast_audit(self, path):
        source = path.read_text(encoding='utf-8')
        tree = ast.parse(source)
        imported = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(a.name.split('.')[0] for a in node.names)
            elif isinstance(node, ast.ImportFrom) and node.level == 0:
                imported.add((node.module or '').split('.')[0])
        self.assertEqual(imported, EXPECTED_IMPORTS,
                         f"{path.name} 导入闭集漂移")
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                low = node.value.lower()
                for part in ('http', 'https', 'ftp', 'ws', 'wss'):
                    self.assertNotIn(part + ':' + '/' + '/', low,
                                     f"{path.name} 字符串常量含 URL 模式")
                for key in MARKETING_KEYS:
                    self.assertNotIn(key, low,
                                     f"{path.name} 常量含营销字段 {key}")
            names = []
            if isinstance(node, ast.Name):
                names.append(node.id)
            elif isinstance(node, ast.Attribute):
                names.append(node.attr)
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                names.append(node.name)
            elif isinstance(node, ast.arg):
                names.append(node.arg)
            for name in names:
                for kw in ('cookie', 'webdriver', 'selenium'):
                    self.assertNotIn(kw, name.lower())

    def test_ast_no_network_no_url_no_marketing(self):
        self._module_ast_audit(PY_DIR / 'commercial_service.py')
        self._module_ast_audit(PY_DIR / 'org_policy_admin.py')

    def _import_roots(self, path: Path) -> set:
        tree = ast.parse(path.read_text(encoding='utf-8'))
        roots = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                roots.update(a.name.split('.')[0] for a in node.names)
            elif isinstance(node, ast.ImportFrom) and node.level == 0:
                roots.add((node.module or '').split('.')[0])
        return roots

    def test_import_graph_case_workbench_zero_slots(self):
        """案件工作台零运营位（结构性）：商业/策略模块只被 legal_entry
        （桥装配）import——任何案件/业务模块都未挂载商业运营位；两模块
        互不 import（桥装配，策略以投影注入）。"""
        offenders = []
        for path in PY_DIR.glob('*.py'):
            if path.name in ('legal_entry.py', 'commercial_service.py',
                             'org_policy_admin.py'):
                continue
            roots = self._import_roots(path)
            if {'commercial_service', 'org_policy_admin'} & roots:
                offenders.append(path.name)
        self.assertEqual(offenders, [],
                         f"商业面被业务模块挂载: {offenders}")
        self.assertNotIn('org_policy_admin',
                         self._import_roots(PY_DIR / 'commercial_service.py'))
        self.assertNotIn('commercial_service',
                         self._import_roots(PY_DIR / 'org_policy_admin.py'))

    # -- 冻结面（不冒已有业务入口）-----------------------------------------
    def test_frozen_method_groups_exact(self):
        self.assertEqual(COMMERCIAL_METHODS, frozenset({
            "commercial.account_open", "commercial.credit_grant",
            "commercial.checkin", "commercial.invite_issue",
            "commercial.invite_redeem", "commercial.revoke",
            "commercial.balance_read"}))
        self.assertEqual(ORG_ADMIN_METHODS, frozenset({
            "orgadmin.policy_declare", "orgadmin.policy_read",
            "orgadmin.policy_apply"}))

    def test_no_collision_with_existing_business_entries(self):
        import legal_entry as le
        groups = {k: v for k, v in vars(le).items()
                  if k.endswith('_METHODS')
                  and isinstance(v, (frozenset, set))}
        for name in ('COMMERCIAL_METHODS', 'ORG_ADMIN_METHODS'):
            mine = groups[name]
            for other_name, other in groups.items():
                if other_name == name:
                    continue
                self.assertFalse(mine & other,
                                 f"{name} 与 {other_name} 交集 "
                                 f"{sorted(mine & other)}")

    def test_fail_closed_config_and_unknown_method(self):
        for method, cfg, needle in (
                ("commercial.credit_grant", {},
                 "commercial_state_root_not_configured"),
                ("orgadmin.policy_declare", {},
                 "org_policy_state_root_not_configured")):
            with self.assertRaisesRegex(NotConnected, needle):
                call(method, {"account_id": "a"}, cfg)
        with self.assertRaisesRegex(NotConnected,
                                    "method_not_connected:commercial.explode"):
            call("commercial.explode", {}, self.cfg)
        with self.assertRaisesRegex(
                NotConnected, "method_not_connected:orgadmin.explode"):
            call("orgadmin.explode", {}, self.cfg)
        with self.assertRaisesRegex(NotConnected,
                                    "commercial_params_invalid"):
            call("commercial.credit_grant", "not-a-dict", self.cfg)
        with self.assertRaisesRegex(NotConnected,
                                    "org_admin_params_invalid"):
            call("orgadmin.policy_read", "not-a-dict", self.cfg)

    # -- F80：账户/发放（幂等回执＋整型分）---------------------------------
    def test_account_open_idempotent_deterministic(self):
        a1 = call("commercial.account_open",
                  {"org_id": "合成组织-1", "user_ref": "synth-u-1"},
                  self.cfg)
        self.assertTrue(a1["idempotent_replay"])
        self.assertEqual(a1["account"]["account_id"], self.acc)
        a2 = call("commercial.account_open",
                  {"org_id": "合成组织-1", "user_ref": "synth-u-2"},
                  self.cfg)
        self.assertFalse(a2["idempotent_replay"])
        self.assertNotEqual(a2["account"]["account_id"], self.acc)
        self.assertEqual(comm.account_id_for("o", "u"),
                         comm.account_id_for("o", "u"))

    def test_credit_grant_receipt_idempotent_conflict(self):
        args = {"account_id": self.acc, "request_id": "rq-1",
                "reason": "signup_bonus", "delta_cents": 1000}
        g1 = call("commercial.credit_grant", args, self.cfg)
        self.assertFalse(g1["idempotent_replay"])
        self.assertEqual(g1["receipt"]["delta_cents"], 1000)
        self.assertEqual(g1["receipt"]["status"], "ACTIVE")
        self.assertIsInstance(g1["receipt"]["balance_after_cents"], int)
        g2 = call("commercial.credit_grant", args, self.cfg)
        self.assertTrue(g2["idempotent_replay"])
        self.assertEqual(g2["receipt"], g1["receipt"])
        with self.assertRaisesRegex(NotConnected,
                                    "f80_credit_grant_conflict"):
            call("commercial.credit_grant",
                 {**args, "delta_cents": 1001}, self.cfg)
        with self.assertRaisesRegex(NotConnected,
                                    "f80_reason_unknown:referral_kickback"):
            call("commercial.credit_grant",
                 {**args, "request_id": "rq-2",
                  "reason": "referral_kickback"}, self.cfg)

    def test_credit_grant_integer_cents_discipline(self):
        for bad in (10.5, "100", True):
            with self.assertRaisesRegex(
                    NotConnected, "f80_delta_invalid:not_integer_cents"):
                call("commercial.credit_grant",
                     {"account_id": self.acc, "request_id": "rq-bad",
                      "reason": "manual_adjust", "delta_cents": bad},
                     self.cfg)
        for bad in (0, -5):
            with self.assertRaisesRegex(
                    NotConnected, "f80_delta_invalid:must_be_positive"):
                call("commercial.credit_grant",
                     {"account_id": self.acc, "request_id": "rq-neg",
                      "reason": "manual_adjust", "delta_cents": bad},
                     self.cfg)

    # -- F80：签到（一日一签，确定性日历日）---------------------------------
    def test_checkin_daily_idempotent_and_closed_day(self):
        c1 = call("commercial.checkin",
                  {"account_id": self.acc, "request_id": "ck-1",
                   "day": "2026-10-22"}, self.cfg)
        self.assertEqual(c1["receipt"]["delta_cents"],
                         comm.CHECKIN_REWARD_CENTS)
        self.assertEqual(c1["receipt"]["day"], "2026-10-22")
        c2 = call("commercial.checkin",
                  {"account_id": self.acc, "request_id": "ck-1",
                   "day": "2026-10-22"}, self.cfg)
        self.assertTrue(c2["idempotent_replay"])
        self.assertEqual(c2["receipt"], c1["receipt"])
        with self.assertRaisesRegex(NotConnected,
                                    "f80_checkin_already_done:2026-10-22"):
            call("commercial.checkin",
                 {"account_id": self.acc, "request_id": "ck-2",
                  "day": "2026-10-22"}, self.cfg)
        c3 = call("commercial.checkin",
                  {"account_id": self.acc, "request_id": "ck-3",
                   "day": "2026-10-23"}, self.cfg)
        self.assertFalse(c3["idempotent_replay"])

    def test_checkin_day_format_named_rejects(self):
        for bad in (20261022, "20261022", "2026-13-01", "not-a-day"):
            with self.assertRaisesRegex(NotConnected, "f80_day_invalid"):
                call("commercial.checkin",
                     {"account_id": self.acc, "request_id": "ck-bad",
                      "day": bad}, self.cfg)

    # -- F80：邀请（一码一兑双腿回执）---------------------------------------
    def test_invite_issue_redeem_two_legs(self):
        iv = call("commercial.invite_issue",
                  {"account_id": self.acc, "request_id": "iv-1"}, self.cfg)
        code = iv["invite_code"]
        iv2 = call("commercial.invite_issue",
                   {"account_id": self.acc, "request_id": "iv-1"}, self.cfg)
        self.assertTrue(iv2["idempotent_replay"])
        self.assertEqual(iv2["invite_code"], code)
        friend = call("commercial.account_open",
                      {"org_id": "合成组织-1", "user_ref": "synth-u-2"},
                      self.cfg)["account"]["account_id"]
        rd = call("commercial.invite_redeem",
                  {"account_id": friend, "request_id": "rd-1",
                   "invite_code": code}, self.cfg)
        self.assertFalse(rd["idempotent_replay"])
        self.assertEqual(rd["redemption"]["redeemer_receipt"]["delta_cents"],
                         comm.INVITE_REDEEM_REWARD_CENTS)
        self.assertEqual(rd["redemption"]["inviter_receipt"]["delta_cents"],
                         comm.INVITE_REFERRAL_REWARD_CENTS)
        self.assertEqual(rd["redemption"]["redeemer_receipt"]
                         ["invite_redeem_id"],
                         rd["redemption"]["inviter_receipt"]
                         ["invite_redeem_id"])
        rd2 = call("commercial.invite_redeem",
                   {"account_id": friend, "request_id": "rd-1",
                    "invite_code": code}, self.cfg)
        self.assertTrue(rd2["idempotent_replay"])
        self.assertEqual(rd2["redemption"], rd["redemption"])
        with self.assertRaisesRegex(NotConnected,
                                    "f80_invite_code_already_used"):
            other = call("commercial.account_open",
                         {"org_id": "合成组织-1", "user_ref": "synth-u-3"},
                         self.cfg)["account"]["account_id"]
            call("commercial.invite_redeem",
                 {"account_id": other, "request_id": "rd-2",
                  "invite_code": code}, self.cfg)
        with self.assertRaisesRegex(NotConnected, "f80_invite_self_redeem"):
            call("commercial.invite_redeem",
                 {"account_id": self.acc, "request_id": "rd-3",
                  "invite_code": code}, self.cfg)
        with self.assertRaisesRegex(NotConnected, "f80_invite_code_unknown"):
            call("commercial.invite_redeem",
                 {"account_id": friend, "request_id": "rd-4",
                  "invite_code": "c80inv-nonexistent"}, self.cfg)

    # -- F80：撤销与余额（append-only；回执冻结；余额恒非负）-----------------
    def test_revoke_appends_only_receipt_frozen_balance_falls(self):
        g = call("commercial.credit_grant",
                 {"account_id": self.acc, "request_id": "rv-g",
                  "reason": "manual_adjust", "delta_cents": 700},
                 self.cfg)
        v = call("commercial.revoke",
                 {"account_id": self.acc, "request_id": "rv-1",
                  "receipt_id": g["receipt"]["receipt_id"]}, self.cfg)
        self.assertFalse(v["idempotent_replay"])
        self.assertEqual(v["revocation"]["delta_cents"], 700)
        self.assertEqual(v["revocation"]["balance_after_cents"], 0)
        # append-only：原发放条目零改写——发放回执重放与签发时逐键相等
        # （含签发时余额；status 仍签发时 ACTIVE，撤销由撤销记录推导）。
        g_replay = call("commercial.credit_grant",
                        {"account_id": self.acc, "request_id": "rv-g",
                         "reason": "manual_adjust", "delta_cents": 700},
                        self.cfg)
        self.assertEqual(g_replay["receipt"], g["receipt"])
        v2 = call("commercial.revoke",
                  {"account_id": self.acc, "request_id": "rv-1",
                   "receipt_id": g["receipt"]["receipt_id"]}, self.cfg)
        self.assertTrue(v2["idempotent_replay"])
        self.assertEqual(v2["revocation"], v["revocation"])
        with self.assertRaisesRegex(NotConnected,
                                    "f80_receipt_already_revoked"):
            call("commercial.revoke",
                 {"account_id": self.acc, "request_id": "rv-2",
                  "receipt_id": g["receipt"]["receipt_id"]}, self.cfg)
        with self.assertRaisesRegex(NotConnected, "f80_receipt_unknown"):
            call("commercial.revoke",
                 {"account_id": self.acc, "request_id": "rv-3",
                  "receipt_id": "c80r-nonexistent"}, self.cfg)
        bal = call("commercial.balance_read",
                   {"account_id": self.acc}, self.cfg)
        self.assertEqual(bal["balance_cents"], 0)
        self.assertEqual(bal["grants_active"], 0)
        self.assertEqual(bal["grants_revoked"], 1)
        self.assertEqual(bal["revocations"], 1)

    def test_balance_never_negative_structural_invariant(self):
        # 撤销只减该笔发放且该笔此前必在余额内——任意序列后余额恒非负。
        g1 = call("commercial.credit_grant",
                  {"account_id": self.acc, "request_id": "bn-1",
                   "reason": "signup_bonus", "delta_cents": 500}, self.cfg)
        c1 = call("commercial.checkin",
                  {"account_id": self.acc, "request_id": "bn-2",
                   "day": "2026-10-22"}, self.cfg)
        call("commercial.revoke",
             {"account_id": self.acc, "request_id": "bn-3",
              "receipt_id": g1["receipt"]["receipt_id"]}, self.cfg)
        bal = call("commercial.balance_read",
                   {"account_id": self.acc}, self.cfg)
        self.assertGreaterEqual(bal["balance_cents"], 0)
        self.assertEqual(bal["balance_cents"],
                         c1["receipt"]["delta_cents"])

    # -- F81：策略账（声明/求值/应用；深管理不替代最小 v1 管理台）-----------
    def _declare(self, request_id, key, value, *, user_ref=None,
                 org_id="合成组织-1"):
        args = {"org_id": org_id, "policy_key": key, "value": value,
                "declared_by": "synth-admin", "request_id": request_id}
        if user_ref is not None:
            args["user_ref"] = user_ref
        return call("orgadmin.policy_declare", args, self.cfg)

    def test_policy_declare_append_only_idempotent_conflict(self):
        d1 = self._declare("pd-1", "commercial.checkin_enabled", False)
        self.assertFalse(d1["idempotent_replay"])
        self.assertEqual(d1["record"]["segment"], "org")
        d2 = self._declare("pd-1", "commercial.checkin_enabled", False)
        self.assertTrue(d2["idempotent_replay"])
        self.assertEqual(d2["record"], d1["record"])
        with self.assertRaisesRegex(NotConnected, "f81_declare_conflict"):
            self._declare("pd-1", "commercial.checkin_enabled", True)

    def test_policy_key_closed_set_v1_console_not_replaced(self):
        for key in ("case.permission.override", "harness.case_permission",
                    "material.deidentify", "commercial.unknown_knob"):
            with self.assertRaisesRegex(
                    NotConnected, "f81_policy_key_unknown:" + key):
                self._declare("pd-key-" + key, key, True)
        with self.assertRaisesRegex(NotConnected,
                                    "f81_policy_value_invalid:expect_bool"):
            self._declare("pd-v1", "commercial.checkin_enabled", "yes")
        with self.assertRaisesRegex(
                NotConnected,
                "f81_policy_value_invalid:expect_non_negative_int_cents"):
            self._declare("pd-v2", "commercial.max_credit_grant_cents",
                          -1)
        with self.assertRaisesRegex(
                NotConnected,
                "f81_policy_value_invalid:expect_non_negative_int_cents"):
            self._declare("pd-v3", "commercial.max_credit_grant_cents",
                          2.5)

    def test_evaluation_f9_semantics_user_beats_org_last_wins(self):
        self._declare("pe-1", "commercial.max_credit_grant_cents", 2000)
        self._declare("pe-2", "commercial.max_credit_grant_cents", 500,
                      user_ref="synth-u-1")
        pr = call("orgadmin.policy_read",
                  {"org_id": "合成组织-1", "user_ref": "synth-u-1"},
                  self.cfg)
        self.assertEqual(pr["effective"]["commercial.max_credit_grant_cents"],
                         500)
        segments = [(t["segment"], t["value"]) for t in pr["trace"]
                    if t["policy_key"] == "commercial.max_credit_grant_cents"]
        self.assertEqual(segments, [("org", 2000), ("user", 500)])
        # 同段声明序 findLast 末条胜出（改值＝追加新记录）
        self._declare("pe-3", "commercial.max_credit_grant_cents", 900,
                      user_ref="synth-u-1")
        pr2 = call("orgadmin.policy_read",
                   {"org_id": "合成组织-1", "user_ref": "synth-u-1"},
                   self.cfg)
        self.assertEqual(pr2["effective"]["commercial.max_credit_grant_cents"],
                         900)
        # 无 user 段记录的用户落 org 段值；org-only 读不收 user 段
        other = call("orgadmin.policy_read",
                     {"org_id": "合成组织-1", "user_ref": "synth-u-9"},
                     self.cfg)
        self.assertEqual(other["effective"]["commercial.max_credit_grant_cents"],
                         2000)
        org_only = call("orgadmin.policy_read",
                        {"org_id": "合成组织-1"}, self.cfg)
        self.assertEqual(org_only["effective"]["commercial.max_credit_grant_cents"],
                         2000)
        self.assertEqual(org_only["user_ref"], None)

    def test_policy_apply_receipt(self):
        self._declare("pa-1", "commercial.checkin_enabled", False)
        self._declare("pa-2", "commercial.max_credit_grant_cents", 1500,
                      user_ref="synth-u-1")
        ap = call("orgadmin.policy_apply",
                  {"org_id": "合成组织-1", "user_ref": "synth-u-1"},
                  self.cfg)
        self.assertEqual(ap["surface"], "commercial_service")
        self.assertEqual(ap["applied"],
                         {"commercial.checkin_enabled": False,
                          "commercial.max_credit_grant_cents": 1500})
        with self.assertRaisesRegex(NotConnected, "f81_user_ref_required"):
            call("orgadmin.policy_apply",
                 {"org_id": "合成组织-1"}, self.cfg)

    # -- F81→F80 真实应用端到端（声明即时改变运行面行为）---------------------
    def test_policy_really_applied_to_runtime_surface(self):
        # 先正常签到一日，随后声明关闭——新签到具名拒，历史重放仍幂等成立。
        c1 = call("commercial.checkin",
                  {"account_id": self.acc, "request_id": "ra-1",
                   "day": "2026-10-22"}, self.cfg)
        self._declare("ra-pd-1", "commercial.checkin_enabled", False)
        ap = call("orgadmin.policy_apply",
                  {"org_id": "合成组织-1", "user_ref": "synth-u-1"},
                  self.cfg)
        self.assertIs(ap["applied"]["commercial.checkin_enabled"], False)
        with self.assertRaisesRegex(NotConnected,
                                    "f80_checkin_disabled_by_policy"):
            call("commercial.checkin",
                 {"account_id": self.acc, "request_id": "ra-2",
                  "day": "2026-10-23"}, self.cfg)
        replay = call("commercial.checkin",
                      {"account_id": self.acc, "request_id": "ra-1",
                       "day": "2026-10-22"}, self.cfg)
        self.assertTrue(replay["idempotent_replay"])
        self.assertEqual(replay["receipt"], c1["receipt"])
        # 上限真实应用：org 段 2000 → 超限拒；user 段覆盖 800 → 新限生效。
        self._declare("ra-pd-2", "commercial.max_credit_grant_cents", 2000)
        with self.assertRaisesRegex(
                NotConnected, "f80_grant_exceeds_policy_cap:2000"):
            call("commercial.credit_grant",
                 {"account_id": self.acc, "request_id": "ra-3",
                  "reason": "manual_adjust", "delta_cents": 5000},
                 self.cfg)
        self._declare("ra-pd-3", "commercial.max_credit_grant_cents", 800,
                      user_ref="synth-u-1")
        with self.assertRaisesRegex(
                NotConnected, "f80_grant_exceeds_policy_cap:800"):
            call("commercial.credit_grant",
                 {"account_id": self.acc, "request_id": "ra-4",
                  "reason": "manual_adjust", "delta_cents": 801},
                 self.cfg)
        ok = call("commercial.credit_grant",
                  {"account_id": self.acc, "request_id": "ra-5",
                   "reason": "manual_adjust", "delta_cents": 800},
                  self.cfg)
        self.assertEqual(ok["receipt"]["delta_cents"], 800)
        # 被拒操作不产生回执（策略闸先于入账）：余额只含签到+800。
        bal = call("commercial.balance_read",
                   {"account_id": self.acc}, self.cfg)
        self.assertEqual(bal["balance_cents"],
                         c1["receipt"]["delta_cents"] + 800)

    def test_commercial_runs_without_policy_root(self):
        """org_policy_state_root 未配置＝无策略（商业面默认开放）。"""
        cfg = {"commercial_state_root": str(self.root / "comm-solo")}
        r = call("commercial.account_open",
                 {"org_id": "o", "user_ref": "u"}, cfg)
        g = call("commercial.credit_grant",
                 {"account_id": r["account"]["account_id"],
                  "request_id": "solo-1", "reason": "signup_bonus",
                  "delta_cents": 10 ** 9}, cfg)
        self.assertEqual(g["receipt"]["delta_cents"], 10 ** 9)

    # -- 旁路字段＋产物面（案件上下文进不了商业面；零营销字段）---------------
    def test_bypass_and_case_fields_refused(self):
        for field, value in (("case_id", "synth-case"),
                             ("matter_id", "synth-matter"),
                             ("url", "synth-bypass"),
                             ("cookie", "synth-bypass"),
                             ("promo_banner", "synth-upsell"),
                             ("utm_campaign", "synth-track")):
            with self.assertRaisesRegex(
                    NotConnected, "f80_field_forbidden:" + field):
                call("commercial.credit_grant",
                     {"account_id": self.acc, "request_id": "bf-1",
                      "reason": "manual_adjust", "delta_cents": 1,
                      field: value}, self.cfg)
        with self.assertRaisesRegex(NotConnected, "f81_field_forbidden"):
            call("orgadmin.policy_declare",
                 {"org_id": "o", "policy_key": "commercial.checkin_enabled",
                  "value": True, "declared_by": "a", "request_id": "bf-2",
                  "telemetry_opt_out": True}, self.cfg)

    def test_state_root_artifacts_clean(self):
        call("commercial.credit_grant",
             {"account_id": self.acc, "request_id": "art-1",
              "reason": "signup_bonus", "delta_cents": 300}, self.cfg)
        call("orgadmin.policy_declare",
             {"org_id": "合成组织-1", "user_ref": "synth-u-1",
              "policy_key": "commercial.max_credit_grant_cents",
              "value": 100, "declared_by": "synth-admin",
              "request_id": "art-2"}, self.cfg)
        blob = ""
        for p in sorted(self.root.rglob("*.json")):
            blob += p.read_text(encoding="utf-8")
        for part in ("http", "https", "ftp"):
            self.assertNotIn(part + ":" + "/" + "/", blob.lower())
        for key in MARKETING_KEYS:
            self.assertNotIn(key, blob)
        self.assertNotIn("synth-case", blob)


if __name__ == "__main__":
    unittest.main()

"""F115/F116 产品侧接线测试（W3-U20 v1＋W4-U49 v1.5）：案件看板基础投影
＋案件域分类＋封皮完整字段＋分模块页面。

全部合成材料。legal_entry 新增 HARNESS_DASHBOARD_METHODS（--dashboard-json
信封）/HARNESS_CASE_DOMAIN_METHODS（--casedomain-json 信封）/DASHBOARD_
METHODS（产品面 dashboard_projection 三方法），桥与产品面经 seam 注入单测
（零仓依赖；真全链实跑对账在 tools/PENDING_OWNER_f115_f116_dashboard_
domain_recon.py）。

权威断言（06 F115「v1实际在办待办/日程投影；全局对话主页，v1.5封皮完整
字段另验；不借F118未裁启用实务自动提醒」＋06 F116「诉讼/执行/非诉/刑事
等字段和筛选持久；分类不冒全域规则完备」）在本测试的机械形态：
  - 不造第二真源：产品面只转录 harness.dashboard_read 回执（seam 注入假
    回执校验形状守卫，真全链 recon 对账投影==直接账面调用）；
  - 不借 F118 提醒派发：投影行/日程摘要出现 dueDesktopReminders/reminders
    键＝f115_reminder_face_not_in_dashboard 具名拒（面即守，不是开关）；
  - 零封皮：行出现封皮键＝f115_cover_sheet_not_in_v1 具名拒（封皮归
    F115-v1.5/B4）；
  - 分类不冒全域规则完备：coverage.exhaustiveClaim 非 False＝
    f115_exhaustive_claim_refused 具名拒；域集与 harness 回执漂移＝
    f116_domain_set_drift；域值/筛选值闭集外具名拒；
  - 显式声明才有域：方法组无任何自动分类/推断方法（组外
    dashboard_method_not_connected）；AST 源面零提醒方法名、零封皮方法名；
  - fail-closed：未配置桥/未知方法/DTO 闭集外字段＝NOT_CONNECTED。
"""

from __future__ import annotations

import ast
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python"))

import legal_entry  # noqa: E402
import dashboard_projection as dp  # noqa: E402
from bridge_errors import NotConnected  # noqa: E402

CONFIG = {
    "harness_public_entry": "X:/synth/harness/public_entry.py",
    "harness_target": "opencode",
    "harness_state_root": "X:/synth/state-root",
    "harness_python": sys.executable,
}


def coverage() -> dict:
    return {"kind": "closed_set_v1_declared_only",
            "domains": ["criminal", "enforcement", "litigation",
                        "non_litigation"],
            "unclassifiedValue": "unclassified",
            "exhaustiveClaim": False}


def synth_view() -> dict:
    """合成 harness.dashboard_read 投影（形状同 harness 合同）。"""
    return {
        "asOf": "2026-10-18",
        "coverage": coverage(),
        "appliedDomainFilter": None,
        "includeClosed": False,
        "matters": [{
            "matterId": "m-f115",
            "matterRevision": 1,
            "lifecycleState": "open",
            "domain": {"matterId": "m-f115", "domain": "litigation",
                       "note": None, "revision": 1, "current": True,
                       "recordHash": "ab" * 32, "createdAt":
                           "2026-10-18T00:00:00Z"},
            "identity": None,
            "tasks": {"countsByState": {"accepted": 1, "cancelled": 0,
                                        "done": 0, "proposed": 0,
                                        "running": 1},
                      "openCount": 2},
            "proposals": {"countsByState": {"adopted": 1, "pending": 1,
                                            "rejected": 0},
                          "pendingCount": 1},
            "schedule": {"countsByClassification": {
                "contract_obligation": 0, "practical_reminder": 0,
                "program_deadline": 1},
                "urgentCount": 1, "overdueCount": 0,
                "nextDue": {"scheduleId": "sched-prog",
                            "classification": "program_deadline",
                            "title": "上诉期届满（合成）",
                            "dueDate": "2026-10-19", "daysRemaining": 1}},
            "accounts": {
                "pathEvidence": {"candidateCount": 1,
                                 "stateCounts": {"adopted": 0, "pending": 1,
                                                 "rejected": 0}},
                "cash": {"asOf": None, "netVector": {
                    "sourceTotalMinor": 1000000, "clientGrossMinor": 1000000,
                    "outflowTotalMinor": 0, "clientNetMinor": 1000000,
                    "courtHeldMinor": 0, "otherHeldMinor": 0,
                    "allocatedTotalMinor": 0, "unallocatedTotalMinor": 1000000,
                    "entitlementTotalMinor": 0, "overEntitlementMinor": 0}},
                "evidenceAttempt": {"attemptCount": 1,
                                    "stateCounts": {"closed": 0, "open": 1}},
                "strategy": {"strategyCount": 1},
            },
        }],
        "summary": {"mattersTotal": 1,
                    "byLifecycle": {"closed": 0, "open": 1,
                                    "stage_change": 0},
                    "byDomain": {"criminal": 0, "enforcement": 0,
                                 "litigation": 1, "non_litigation": 0,
                                 "unclassified": 0},
                    "openTasksTotal": 2, "pendingProposalsTotal": 1,
                    "scheduleUrgentTotal": 1, "excludedByPermission": 0},
    }


def seam_view(view: dict | None = None):
    captured: dict = {}

    def harness_call(method: str, args: dict) -> dict:
        captured["method"] = method
        captured["args"] = args
        return view if view is not None else synth_view()

    return harness_call, captured


class F115F116DashboardWiringTests(unittest.TestCase):
    # -- 封闭方法组 ----------------------------------------------------

    def test_method_groups_frozen_and_aligned(self) -> None:
        self.assertEqual(
            legal_entry.HARNESS_DASHBOARD_METHODS,
            frozenset({"harness.dashboard_read"}))
        self.assertEqual(
            legal_entry.HARNESS_CASE_DOMAIN_METHODS,
            frozenset({"harness.case_domain_declare",
                       "harness.case_domain_read"}))
        self.assertEqual(legal_entry.HARNESS_COVER_METHODS,
                         frozenset({"harness.cover_read"}))
        self.assertEqual(legal_entry.HARNESS_MODULE_METHODS,
                         frozenset({"harness.module_read"}))
        self.assertEqual(legal_entry.DASHBOARD_METHODS, dp.DASHBOARD_METHODS)
        self.assertEqual(
            dp.DASHBOARD_METHODS,
            frozenset({"dashboard.read", "dashboard.domain_declare",
                       "dashboard.domain_read", "dashboard.cover_read",
                       "dashboard.module_read"}))

    def test_forged_methods_not_in_groups(self) -> None:
        # 自动分类/推断、提醒派发、封皮——全部不在封闭面（结构性不存在）。
        for forged in ("dashboard.classify", "dashboard.infer_domain",
                       "dashboard.remind", "dashboard.fire_reminders",
                       "dashboard.cover_sheet", "dashboard.write",
                       "dashboard.domain_infer", "dashboard.cover_declare",
                       "dashboard.module_classify"):
            self.assertNotIn(forged, dp.DASHBOARD_METHODS)
            with self.assertRaises(NotConnected) as caught:
                legal_entry.call(forged, {}, CONFIG)
            self.assertIn("method_not_connected:" + forged,
                          str(caught.exception))

    # -- AST 源面：零提醒方法、零封皮方法、导入闭集 -------------------

    def test_source_ast_closed(self) -> None:
        source = (ROOT / "python" / "dashboard_projection.py").read_text(
            encoding="utf-8")
        tree = ast.parse(source)
        # 提醒派发方法名（F118 调度器独占）不作为代码出现：本面绝不借提醒
        # 通道（文档字符串的边界声明不算代码）。
        forbidden_names = {"reminder_report", "schedule_event",
                           "schedule_cancel", "f118_scheduler",
                           "cover_sheet_declare", "infer_domain"}
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    self.assertNotIn(alias.name.split(".")[0], forbidden_names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                self.assertNotIn(node.module.split(".")[0], forbidden_names)
            elif isinstance(node, ast.Attribute):
                self.assertNotIn(node.attr, forbidden_names)
            elif isinstance(node, ast.Name) and isinstance(node.ctx,
                                                           ast.Load):
                self.assertNotIn(node.id, forbidden_names)
        imported = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(alias.name.split(".")[0]
                                for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module.split(".")[0])
        self.assertEqual(imported - {"__future__", "legal_entry"}, set())

    # -- 只读投影转录＋形状守卫 ---------------------------------------

    def test_read_transcribes_and_stamps_face(self) -> None:
        harness_call, captured = seam_view()
        view = dp.dashboard_call("dashboard.read",
                                 {"actor_id": "lawyer-1",
                                  "query": {"asOf": "2026-10-18"}},
                                 CONFIG, harness_call=harness_call)
        self.assertEqual(captured["method"], "harness.dashboard_read")
        self.assertEqual(captured["args"],
                         {"actor_id": "lawyer-1",
                          "query": {"asOf": "2026-10-18"}})
        self.assertEqual(view["matters"][0]["accounts"]["strategy"],
                         {"strategyCount": 1})
        self.assertEqual(view["face"]["kind"],
                         "dashboard-v1-basic-projection")
        self.assertEqual(view["face"]["reminderFace"],
                         "excluded-f118-scheduler-only")
        self.assertEqual(view["face"]["coverSheet"],
                         "f115-v1.5-cover-face")

    def test_read_reminder_face_key_refused(self) -> None:
        view = synth_view()
        view["matters"][0]["schedule"]["dueDesktopReminders"] = []
        harness_call, _ = seam_view(view)
        with self.assertRaises(dp.DashboardProjectionError) as caught:
            dp.dashboard_call("dashboard.read", {}, CONFIG,
                              harness_call=harness_call)
        self.assertIn("f115_reminder_face_not_in_dashboard:"
                      "dueDesktopReminders", str(caught.exception))

    def test_read_cover_sheet_key_refused(self) -> None:
        view = synth_view()
        view["matters"][0]["coverSheet"] = {"fields": []}
        harness_call, _ = seam_view(view)
        with self.assertRaises(dp.DashboardProjectionError) as caught:
            dp.dashboard_call("dashboard.read", {}, CONFIG,
                              harness_call=harness_call)
        self.assertIn("f115_cover_sheet_not_in_v1", str(caught.exception))

    def test_read_exhaustive_claim_refused(self) -> None:
        view = synth_view()
        view["coverage"]["exhaustiveClaim"] = True
        harness_call, _ = seam_view(view)
        with self.assertRaises(dp.DashboardProjectionError) as caught:
            dp.dashboard_call("dashboard.read", {}, CONFIG,
                              harness_call=harness_call)
        self.assertIn("f115_exhaustive_claim_refused", str(caught.exception))

    def test_read_domain_set_drift_refused(self) -> None:
        view = synth_view()
        view["coverage"]["domains"] = ["litigation", "enforcement"]
        harness_call, _ = seam_view(view)
        with self.assertRaises(dp.DashboardProjectionError) as caught:
            dp.dashboard_call("dashboard.read", {}, CONFIG,
                              harness_call=harness_call)
        self.assertIn("f116_domain_set_drift", str(caught.exception))

    def test_read_unknown_domain_value_refused(self) -> None:
        view = synth_view()
        view["matters"][0]["domain"]["domain"] = "行政"
        harness_call, _ = seam_view(view)
        with self.assertRaises(dp.DashboardProjectionError) as caught:
            dp.dashboard_call("dashboard.read", {}, CONFIG,
                              harness_call=harness_call)
        self.assertIn("f116_domain_value_unknown", str(caught.exception))

    def test_read_unknown_lifecycle_refused(self) -> None:
        view = synth_view()
        view["matters"][0]["lifecycleState"] = "archived"
        harness_call, _ = seam_view(view)
        with self.assertRaises(dp.DashboardProjectionError) as caught:
            dp.dashboard_call("dashboard.read", {}, CONFIG,
                              harness_call=harness_call)
        self.assertIn("f115_lifecycle_state_unknown", str(caught.exception))

    # -- 查询与筛选闭集 ------------------------------------------------

    def test_query_and_filter_closed_sets(self) -> None:
        harness_call, captured = seam_view()
        dp.dashboard_call("dashboard.read",
                          {"query": {"asOf": "2026-10-18",
                                     "domainFilter": ["litigation",
                                                      "unclassified"]}},
                          CONFIG, harness_call=harness_call)
        self.assertEqual(captured["args"]["query"]["domainFilter"],
                         ["litigation", "unclassified"])
        with self.assertRaises(dp.DashboardProjectionError) as caught:
            dp.dashboard_call("dashboard.read",
                              {"query": {"domainFilter": ["行政"]}},
                              CONFIG, harness_call=harness_call)
        self.assertIn("f116_domain_filter_value_unknown", str(caught.exception))
        with self.assertRaises(dp.DashboardProjectionError) as caught:
            dp.dashboard_call("dashboard.read",
                              {"query": {"domainFilter": []}}, CONFIG,
                              harness_call=harness_call)
        self.assertIn("f115_domain_filter_invalid", str(caught.exception))
        with self.assertRaises(dp.DashboardProjectionError) as caught:
            dp.dashboard_call("dashboard.read",
                              {"query": {"asOf": "2026-10-18",
                                         "orderBy": "score"}}, CONFIG,
                              harness_call=harness_call)
        self.assertIn("f115_query_fields_not_closed", str(caught.exception))

    # -- 域声明：显式动作＋薄转发 --------------------------------------

    def test_domain_declare_forwards_normalized(self) -> None:
        harness_call, captured = seam_view({
            "domain": {"matterId": "m-f115", "domain": "litigation",
                       "note": None, "revision": 1, "current": True,
                       "recordHash": "ab" * 32,
                       "createdAt": "2026-10-18T00:00:00Z"},
            "replayed": False, "receipt": {"ref": {}}})
        dp.dashboard_call("dashboard.domain_declare",
                          {"actor_id": "lawyer-1",
                           "scope": {"kind": "matter",
                                     "matterId": "m-f115"},
                           "key": {"requestId": "k-1", "targetId": None,
                                   "expectedRevision": None,
                                   "inputRefs": []},
                           "declaration": {"domain": "litigation",
                                           "note": None}},
                          CONFIG, harness_call=harness_call)
        self.assertEqual(captured["method"], "harness.case_domain_declare")
        self.assertEqual(captured["args"]["declaration"],
                         {"domain": "litigation", "note": None})
        with self.assertRaises(dp.DashboardProjectionError) as caught:
            dp.dashboard_call("dashboard.domain_declare",
                              {"declaration": {"domain": "行政",
                                               "note": None}}, CONFIG,
                              harness_call=harness_call)
        self.assertIn("f116_domain_value_unknown", str(caught.exception))
        with self.assertRaises(dp.DashboardProjectionError) as caught:
            dp.dashboard_call("dashboard.domain_declare",
                              {"declaration": {"domain": "litigation",
                                               "note": None,
                                               "rule": "全域"}},
                              CONFIG, harness_call=harness_call)
        self.assertIn("f116_declaration_fields_not_closed", str(caught.exception))

    def test_domain_read_validates_coverage(self) -> None:
        harness_call, captured = seam_view({
            "matterId": "m-f115", "domain": None, "revisionCount": 0,
            "coverage": coverage()})
        dp.dashboard_call("dashboard.domain_read",
                          {"scope": {"kind": "matter",
                                     "matterId": "m-f115"}},
                          CONFIG, harness_call=harness_call)
        self.assertEqual(captured["method"], "harness.case_domain_read")
        bad = {"matterId": "m-f115", "domain": None, "revisionCount": 0,
               "coverage": {"exhaustiveClaim": True}}
        harness_call, _ = seam_view(bad)
        with self.assertRaises(dp.DashboardProjectionError) as caught:
            dp.dashboard_call("dashboard.domain_read",
                              {"scope": {"kind": "matter",
                                         "matterId": "m-f115"}},
                              CONFIG, harness_call=harness_call)
        self.assertIn("f115_exhaustive_claim_refused", str(caught.exception))

    # -- v1.5 封皮：薄转发＋形状守卫＋面标记（W4-U49）------------------

    def test_cover_read_transcribes_and_stamps_face(self) -> None:
        cover_view = {
            "matterId": "m-f115",
            "asOf": "2026-10-18",
            "coverage": coverage(),
            "cover": {
                "matterId": "m-f115", "matterRevision": 1,
                "createdAt": "2026-10-18T00:00:00Z",
                "updatedAt": "2026-10-18T00:00:00Z",
                "lifecycleState": "open",
                "lifecycleLastTransition": None,
                "lifecycleRecordedAt": None,
                "identity": {"matterId": "m-f115",
                             "identityKind": "litigation",
                             "caseNumber": "（2026）合成 0105 民初 49 号",
                             "caseNumberDigest": "cd" * 32,
                             "court": "合成市第一人民法院", "note": None,
                             "revision": 1, "current": True,
                             "recordHash": "ab" * 32,
                             "createdAt": "2026-10-18T00:00:00Z"},
                "domain": {"matterId": "m-f115", "domain": "litigation",
                           "note": None, "revision": 1, "current": True,
                           "recordHash": "ab" * 32,
                           "createdAt": "2026-10-18T00:00:00Z"},
                "members": [{"userId": "lawyer-1", "orgId": "org-1",
                             "roles": ["case-lawyer"]}],
                "tasks": {"countsByState": {}, "openCount": 0},
                "proposals": {"countsByState": {}, "pendingCount": 0},
                "schedule": {"countsByClassification": {}, "urgentCount": 0,
                             "overdueCount": 0, "nextDue": None},
                "accounts": {"pathEvidence": {"candidateCount": 0,
                                              "stateCounts": {}},
                             "cash": {"asOf": None, "netVector": {}},
                             "evidenceAttempt": {"attemptCount": 0,
                                                 "stateCounts": {}},
                             "strategy": {"strategyCount": 0}},
            },
        }
        harness_call, captured = seam_view(cover_view)
        view = dp.dashboard_call(
            "dashboard.cover_read",
            {"actor_id": "lawyer-1",
             "scope": {"kind": "matter", "matterId": "m-f115"},
             "query": {"asOf": "2026-10-18"}},
            CONFIG, harness_call=harness_call)
        self.assertEqual(captured["method"], "harness.cover_read")
        self.assertEqual(captured["args"],
                         {"actor_id": "lawyer-1",
                          "scope": {"kind": "matter",
                                    "matterId": "m-f115"},
                          "query": {"asOf": "2026-10-18"}})
        self.assertEqual(view["face"]["kind"], dp.COVER_FACE_KIND)
        self.assertEqual(view["face"]["reminderFace"],
                         "excluded-f118-scheduler-only")
        # 零字段发明：面标记外，回执正文与 harness 转录逐键同构。
        self.assertEqual(view["cover"], cover_view["cover"])

    def test_cover_read_guard_refusals(self) -> None:
        base = seam_view()[0]

        def cover_with(view_mut):
            def harness_call(method, args):
                return view_mut
            return harness_call

        # 提醒派发键进封皮＝具名拒（F118 调度器独占）。
        bad = {
            "matterId": "m-f115", "asOf": "2026-10-18",
            "coverage": coverage(),
            "cover": {"matterId": "m-f115", "lifecycleState": "open",
                      "dueDesktopReminders": []},
        }
        with self.assertRaises(dp.DashboardProjectionError) as caught:
            dp.dashboard_call("dashboard.cover_read", {"scope": {}}, CONFIG,
                              harness_call=cover_with(bad))
        self.assertIn("f115_reminder_face_not_in_dashboard",
                      str(caught.exception))
        # exhaustiveClaim=true＝具名拒（分类不冒全域规则完备）。
        bad2 = {"matterId": "m-f115", "asOf": None,
                "coverage": {"exhaustiveClaim": True},
                "cover": {"matterId": "m-f115",
                          "lifecycleState": "open", "members": []}}
        with self.assertRaises(dp.DashboardProjectionError) as caught:
            dp.dashboard_call("dashboard.cover_read", {"scope": {}}, CONFIG,
                              harness_call=cover_with(bad2))
        self.assertIn("f115_exhaustive_claim_refused", str(caught.exception))
        # 生命周期闭集外＝具名拒。
        bad3 = {"matterId": "m-f115", "asOf": None, "coverage": coverage(),
                "cover": {"matterId": "m-f115",
                          "lifecycleState": "archived", "members": []}}
        with self.assertRaises(dp.DashboardProjectionError) as caught:
            dp.dashboard_call("dashboard.cover_read", {"scope": {}}, CONFIG,
                              harness_call=cover_with(bad3))
        self.assertIn("f115_lifecycle_state_unknown", str(caught.exception))
        # scope 缺席＝具名拒。
        with self.assertRaises(dp.DashboardProjectionError) as caught:
            dp.dashboard_call("dashboard.cover_read", {}, CONFIG,
                              harness_call=base)
        self.assertIn("f115_field_missing:scope", str(caught.exception))

    # -- v1.5 分模块页面：四具名域开页＋unclassified 不是模块（W4-U49）--

    def test_module_read_transcribes_and_stamps_face(self) -> None:
        board = synth_view()
        module_view = {
            "module": {"domain": "litigation",
                       "pageKind": "domain-module-page",
                       "coverage": coverage(),
                       "declaredDomains": ["criminal", "enforcement",
                                           "litigation",
                                           "non_litigation"]},
            "asOf": board["asOf"], "includeClosed": False,
            "matters": board["matters"], "summary": {
                "mattersTotal": 1,
                "byLifecycle": board["summary"]["byLifecycle"],
                "openTasksTotal": 2, "pendingProposalsTotal": 1,
                "scheduleUrgentTotal": 1, "excludedByPermission": 0},
        }
        harness_call, captured = seam_view(module_view)
        view = dp.dashboard_call(
            "dashboard.module_read",
            {"domain": "litigation", "query": {"asOf": "2026-10-18"}},
            CONFIG, harness_call=harness_call)
        self.assertEqual(captured["method"], "harness.module_read")
        self.assertEqual(captured["args"]["domain"], "litigation")
        self.assertEqual(view["face"]["kind"], dp.MODULE_FACE_KIND)
        self.assertIs(view["face"]["exhaustiveClaim"], False)
        self.assertEqual(view["module"]["domain"], "litigation")

    def test_module_read_refusals(self) -> None:
        harness_call = seam_view()[0]

        def cover_with(view_mut):
            def harness_call(method, args):
                return view_mut
            return harness_call

        # unclassified 是筛选归纳表示值——不是模块页（具名拒）。
        with self.assertRaises(dp.DashboardProjectionError) as caught:
            dp.dashboard_call("dashboard.module_read",
                              {"domain": "unclassified"}, CONFIG,
                              harness_call=harness_call)
        self.assertIn("f116_module_value_unknown:unclassified",
                      str(caught.exception))
        # 闭集外自由文本域＝具名拒。
        with self.assertRaises(dp.DashboardProjectionError) as caught:
            dp.dashboard_call("dashboard.module_read",
                              {"domain": "行政"}, CONFIG,
                              harness_call=harness_call)
        self.assertIn("f116_module_value_unknown", str(caught.exception))
        # 模块页 coverage exhaustiveClaim=true＝具名拒。
        bad = {"module": {"domain": "litigation",
                          "pageKind": "domain-module-page",
                          "coverage": {"exhaustiveClaim": True},
                          "declaredDomains": ["criminal", "enforcement",
                                              "litigation",
                                              "non_litigation"]},
               "asOf": None, "matters": [], "summary": {}}
        with self.assertRaises(dp.DashboardProjectionError) as caught:
            dp.dashboard_call("dashboard.module_read",
                              {"domain": "litigation"}, CONFIG,
                              harness_call=cover_with(bad))
        self.assertIn("f115_exhaustive_claim_refused", str(caught.exception))
        # declaredDomains 漂移＝具名拒（不冒新增域）。
        bad2 = {"module": {"domain": "litigation",
                           "pageKind": "domain-module-page",
                           "coverage": coverage(),
                           "declaredDomains": ["criminal", "enforcement",
                                               "litigation", "tax"]},
                "asOf": None, "matters": [], "summary": {}}
        with self.assertRaises(dp.DashboardProjectionError) as caught:
            dp.dashboard_call("dashboard.module_read",
                              {"domain": "litigation"}, CONFIG,
                              harness_call=cover_with(bad2))
        self.assertIn("f116_domain_set_drift", str(caught.exception))

    # -- fail-closed：未配置桥＝具名拒 ---------------------------------

    def test_unconfigured_bridge_fails_closed(self) -> None:
        with self.assertRaises(NotConnected) as caught:
            legal_entry.call("dashboard.read", {}, {
                "harness_target": "opencode"})
        self.assertIn("harness_public_entry_not_configured",
                      str(caught.exception))
        with self.assertRaises(NotConnected) as caught:
            legal_entry.call("dashboard.read", {}, {
                "harness_public_entry": "X:/synth/harness/public_entry.py"})
        self.assertIn("harness_target_not_configured", str(caught.exception))


if __name__ == "__main__":
    unittest.main()

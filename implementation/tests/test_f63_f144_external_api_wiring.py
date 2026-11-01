"""W4-U40 / F63＋F144 外部 API 负测先行桥面测试：冻结方法组、fail-closed
配置面、未授权/缺 token/适配器缺席三态值恒 None（不造空轨迹/不编企业数
据）、凭证绑定取证时间/来源水印（E17 有凭据才记取得语义）、失败不编轨
迹、旁路字段具名拒、幂等回流、AST 零网络零 URL——经桥同进程闭环。全部
合成材料（合成回执/合成连接器会话显式 synth；真实 EMS API/MCP 连接器授
权调用属裁决#8-12 授权后补联测，不编其形状）。

AST 面断言（负测先行纪律）：ems_evidence.py/enterprise_connector.py 导
入闭集零网络模块、字符串常量零 URL 模式（连冻结常量都不存在——禁编
URL）、标识符零采集旁路关键字。
"""
import ast
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'python'))

from legal_entry import (call, NotConnected, EMS_EVIDENCE_METHODS,
                         ENTERPRISE_CONNECTOR_METHODS)
import ems_evidence as ems
import enterprise_connector as ent

WAYBILL = "1130000000012"
COMPANY = "合成市合成科技有限公司"


def _synth_ems_receipt(_waybill):
    return {"provider": "ems_synth",
            "retrieved_at": "2026-10-21T08:00:00Z",
            "trace": [{"time": "2026-10-20T09:00:00Z", "desc": "【合成】收寄"},
                      {"time": "2026-10-21T07:30:00Z",
                       "desc": "【合成】投递并签收"}],
            "cost_cents": 300}


class _SynthSession:
    def __init__(self, provider):
        self.provider = provider

    def query(self, company_name=None, credit_code=None):
        return {"provider": self.provider,
                "retrieved_at": "2026-10-21T08:30:00Z",
                "quota_remaining": 87,
                "payload": {"name": COMPANY, "status": "存续（合成样本）"}}


def _synth_session_factory(provider):
    return _SynthSession(provider)


class F63F144ExternalApiNegtestWiringTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.ems_cfg = {"ems_evidence_state_root": str(self.root / "ems")}
        self.ent_cfg = {"enterprise_connector_state_root":
                        str(self.root / "ent")}
        self._env = {v: os.environ.get(v) for v in
                     ("EMS_API_TOKEN", "QCC_MCP_TOKEN", "TYC_MCP_TOKEN")}
        for v in self._env:
            os.environ.pop(v, None)

    def tearDown(self):
        for v, saved in self._env.items():
            if saved is None:
                os.environ.pop(v, None)
            else:
                os.environ[v] = saved
        self._tmp.cleanup()

    # -- AST 结构面（负测先行＝结构性事实）---------------------------------
    def _ast_audit(self, path):
        source = Path(path).read_text(encoding='utf-8')
        tree = ast.parse(source)
        imported = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(a.name.split('.')[0] for a in node.names)
            elif isinstance(node, ast.ImportFrom) and node.level == 0:
                imported.add((node.module or '').split('.')[0])
        self.assertEqual(imported,
                         {'__future__', 'hashlib', 'json', 'os', 'datetime',
                          'pathlib'})
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                low = node.value.lower()
                for part in ('http', 'https', 'ftp', 'ws', 'wss'):
                    self.assertNotIn(part + ':' + '/' + '/', low)
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

    def test_ast_no_network_no_url_no_bypass(self):
        py = Path(__file__).resolve().parents[1] / 'python'
        self._ast_audit(py / 'ems_evidence.py')
        self._ast_audit(py / 'enterprise_connector.py')

    # -- 冻结面 ------------------------------------------------------------
    def test_frozen_method_groups(self):
        self.assertEqual(EMS_EVIDENCE_METHODS, frozenset({
            "ems.action_authorize", "ems.evidence_query",
            "ems.evidence_read"}))
        self.assertEqual(ENTERPRISE_CONNECTOR_METHODS, frozenset({
            "enterprise.connector_status", "enterprise.diligence_query",
            "enterprise.diligence_read"}))

    def test_fail_closed_config_and_unknown_method(self):
        for method, cfg, needle in (
                ("ems.evidence_query", {},
                 "ems_evidence_state_root_not_configured"),
                ("enterprise.diligence_query", {},
                 "enterprise_connector_state_root_not_configured")):
            with self.assertRaisesRegex(NotConnected, needle):
                call(method, {"query_id": "q", "matter_id": "m",
                              "items": []}, cfg)
        with self.assertRaisesRegex(NotConnected,
                                    "method_not_connected:ems.explode"):
            call("ems.explode", {}, self.ems_cfg)
        with self.assertRaisesRegex(
                NotConnected, "method_not_connected:enterprise.explode"):
            call("enterprise.explode", {}, self.ent_cfg)
        with self.assertRaisesRegex(NotConnected,
                                    "ems_evidence_params_invalid"):
            call("ems.evidence_query", "not-a-dict", self.ems_cfg)
        with self.assertRaisesRegex(NotConnected,
                                    "enterprise_connector_params_invalid"):
            call("enterprise.diligence_query", "not-a-dict", self.ent_cfg)

    # -- F63：授权账（E24 形态）＋闸序＋具名缺口----------------------------
    def _authorize_ems(self):
        """模块级直调前提：授权在账＋token 在位（闸序＝面语义，非测试便捷）。"""
        call("ems.action_authorize",
             {"authorized_by": "synth-lawyer"}, self.ems_cfg)
        os.environ["EMS_API_TOKEN"] = "JUSCITE-SYNTH-TOKEN-NOT-REAL"

    def _token_ent(self):
        os.environ["QCC_MCP_TOKEN"] = "JUSCITE-SYNTH-TOKEN-NOT-REAL"
        os.environ["TYC_MCP_TOKEN"] = "JUSCITE-SYNTH-TOKEN-NOT-REAL"
    def test_f63_authorize_ledger_idempotent_scope_closed(self):
        r1 = call("ems.action_authorize",
                  {"authorized_by": "synth-lawyer"}, self.ems_cfg)
        self.assertEqual(r1["authorization"]["scope"],
                         "ems_official_api_query")
        r2 = call("ems.action_authorize",
                  {"authorized_by": "synth-lawyer"}, self.ems_cfg)
        self.assertTrue(r2["idempotent_replay"])
        self.assertEqual(r2["authorization"]["auth_id"],
                         r1["authorization"]["auth_id"])
        with self.assertRaisesRegex(NotConnected,
                                    "f63_scope_unknown:web_scrape"):
            call("ems.action_authorize",
                 {"authorized_by": "x", "scope": "web_scrape"}, self.ems_cfg)

    def test_f63_unauthorized_then_token_gap_gate_order(self):
        # 未授权动作（授权闸先行）：值恒 None（UNKNOWN 不是 0 不造空轨迹）。
        unauth_cfg = {"ems_evidence_state_root":
                      str(self.root / "ems-unauth")}
        r0 = call("ems.evidence_query",
                  {"query_id": "q0", "matter_id": "m",
                   "items": [{"waybill_no": WAYBILL}]}, unauth_cfg)
        self.assertEqual(r0["items"][0]["status"], "ACTION_NOT_AUTHORIZED")
        self.assertIsNone(r0["items"][0]["trajectory"])
        self.assertIsNone(r0["items"][0]["credential"])
        # 已授权缺 token：PAID_TOKEN_NOT_CONFIGURED（W2a-U13 先例同码）。
        call("ems.action_authorize",
             {"authorized_by": "synth-lawyer"}, self.ems_cfg)
        r1 = call("ems.evidence_query",
                  {"query_id": "q1", "matter_id": "m",
                   "items": [{"waybill_no": WAYBILL}]}, self.ems_cfg)
        self.assertEqual(r1["items"][0]["status"], "TOKEN_NOT_CONFIGURED")
        self.assertEqual(r1["items"][0]["reason"],
                         "PAID_TOKEN_NOT_CONFIGURED")
        self.assertIsNone(r1["items"][0]["trajectory"])
        self.assertIsNone(r1["items"][0]["credential"])
        # token 在位仍 ADAPTER_ABSENT：客户端未建不可能自采（构造级）。
        os.environ["EMS_API_TOKEN"] = "JUSCITE-SYNTH-TOKEN-NOT-REAL"
        r2 = call("ems.evidence_query",
                  {"query_id": "q2", "matter_id": "m",
                   "items": [{"waybill_no": WAYBILL}]}, self.ems_cfg)
        self.assertEqual(r2["items"][0]["status"], "ADAPTER_ABSENT")
        self.assertEqual(r2["items"][0]["reason"],
                         "EMS_ADAPTER_ABSENT_PENDING_AUTHORIZATION")
        self.assertIsNone(r2["items"][0]["trajectory"])
        self.assertIsNone(r2["items"][0]["credential"])
        self.assertEqual(r2["adapter"], "absent")

    def test_f63_seal_binds_time_watermark_and_deterministic(self):
        self._authorize_ems()
        qr = ems.run_query(self.root / "ems",
                           {"query_id": "q", "matter_id": "m",
                            "items": [{"waybill_no": WAYBILL}]},
                           transport=_synth_ems_receipt)
        item = qr["items"][0]
        self.assertEqual(item["status"], "EVIDENCE_SEALED")
        cred = item["credential"]
        self.assertEqual(cred["evidence_time_utc"], "2026-10-21T08:00:00Z")
        self.assertEqual(cred["source_watermark"]["provider"], "ems_synth")
        self.assertEqual(len(cred["source_watermark"]["receipt_sha256"]), 64)
        self.assertEqual(cred["trace_count"], 2)
        self.assertEqual(len(item["trajectory"]), 2)
        self.assertEqual(cred["cost_cents"], 300)
        # 轨迹描述只留哈希（描述原文不落账）。
        self.assertNotIn("投递并签收", item["trajectory"][1]["desc_sha256"])
        self.assertEqual(
            ems.seal_from_receipt(WAYBILL, _synth_ems_receipt(WAYBILL))["seal"],
            cred["seal"])
        self.assertEqual(
            ems.seal_from_receipt(WAYBILL, _synth_ems_receipt(WAYBILL))["seal"],
            cred["seal"])

    def test_f63_failure_no_trajectory_and_cost_discipline(self):
        self._authorize_ems()

        def _boom(_w):
            raise RuntimeError("synth network down")

        def _bad(_w):
            return {"provider": "ems_synth", "retrieved_at": None,
                    "trace": "not-a-list"}

        def _float(_w):
            r = _synth_ems_receipt(_w)
            r["cost_cents"] = 3.5
            return r

        qr = ems.run_query(self.root / "ems",
                           {"query_id": "q", "matter_id": "m",
                            "items": [{"waybill_no": WAYBILL}]},
                           transport=_boom)
        self.assertEqual(qr["items"][0]["status"], "QUERY_FAILED")
        self.assertIsNone(qr["items"][0]["trajectory"])
        qr2 = ems.run_query(self.root / "ems",
                            {"query_id": "q2", "matter_id": "m",
                             "items": [{"waybill_no": WAYBILL}]},
                            transport=_bad)
        self.assertEqual(qr2["items"][0]["status"], "RECEIPT_INVALID")
        self.assertIsNone(qr2["items"][0]["credential"])
        with self.assertRaisesRegex(
                ems.EmsEvidenceError,
                "f63_receipt_invalid:cost_not_integer_cents"):
            ems.seal_from_receipt(WAYBILL, _float(WAYBILL))

    def test_f63_replay_conflict_read_and_bypass_fields(self):
        self._authorize_ems()
        qr = ems.run_query(self.root / "ems",
                           {"query_id": "q", "matter_id": "m",
                            "items": [{"waybill_no": WAYBILL}]},
                           transport=_synth_ems_receipt)
        replay = ems.run_query(self.root / "ems",
                               {"query_id": "q", "matter_id": "m",
                                "items": [{"waybill_no": WAYBILL}]},
                               transport=_synth_ems_receipt)
        self.assertEqual(replay, qr)
        with self.assertRaisesRegex(ems.EmsEvidenceError,
                                    "f63_query_conflict"):
            ems.run_query(self.root / "ems",
                          {"query_id": "q", "matter_id": "m",
                           "items": [{"waybill_no": "1130000000999"}]},
                          transport=_synth_ems_receipt)
        self.assertEqual(
            call("ems.evidence_read", {"query_id": "q"}, self.ems_cfg), qr)
        with self.assertRaisesRegex(NotConnected, "f63_field_forbidden:url"):
            call("ems.evidence_query",
                 {"query_id": "qn", "matter_id": "m",
                  "items": [{"waybill_no": WAYBILL,
                             "url": "synth-bypass-value"}]}, self.ems_cfg)
        with self.assertRaisesRegex(NotConnected,
                                    "f63_field_forbidden:cookie"):
            call("ems.evidence_query",
                 {"query_id": "qn2", "matter_id": "m",
                  "items": [{"waybill_no": WAYBILL,
                             "cookie": "synth-bypass-value"}]}, self.ems_cfg)
        with self.assertRaisesRegex(NotConnected,
                                    "f63_field_forbidden:ems_endpoint"):
            call("ems.evidence_query",
                 {"query_id": "qn3", "matter_id": "m",
                  "ems_endpoint": "synth-bypass-value",
                  "items": [{"waybill_no": WAYBILL}]}, self.ems_cfg)

    def test_f63_state_root_artifacts_zero_url_zero_token(self):
        self._authorize_ems()
        ems.run_query(self.root / "ems",
                      {"query_id": "q", "matter_id": "m",
                       "items": [{"waybill_no": WAYBILL}]},
                      transport=_synth_ems_receipt)
        blob = ""
        for p in sorted(self.root.rglob("*.json")):
            blob += p.read_text(encoding="utf-8")
        for part in ("http", "https"):
            self.assertNotIn(part + ":" + "/" + "/", blob.lower())
        self.assertNotIn("JUSCITE-SYNTH-TOKEN-NOT-REAL", blob)

    # -- F144：连接器形态＋具名缺口＋回执转录-------------------------------
    def test_f144_connector_status_named_gap(self):
        status = call("enterprise.connector_status", {}, self.ent_cfg)
        self.assertEqual(status["form"], "mcp_connector_no_self_collection")
        self.assertEqual(status["sessions_established"], 0)
        self.assertEqual(status["self_collection"], "none")
        self.assertEqual(status["url_disclosure"], "none")
        self.assertEqual(len(status["gaps"]), 1)
        self.assertEqual(status["gaps"][0]["reason"],
                         "PAID_TOKEN_NOT_CONFIGURED")
        self.assertEqual(status["gaps"][0]["detail"],
                         "QCC_MCP_TOKEN;TYC_MCP_TOKEN")

    def test_f144_token_gap_then_session_absent_values_none(self):
        r1 = call("enterprise.diligence_query",
                  {"query_id": "q1", "matter_id": "m",
                   "items": [{"provider": "qcc_mcp",
                              "company_name": COMPANY}]}, self.ent_cfg)
        self.assertEqual(r1["items"][0]["status"], "TOKEN_NOT_CONFIGURED")
        self.assertEqual(r1["items"][0]["reason"],
                         "PAID_TOKEN_NOT_CONFIGURED")
        self.assertIsNone(r1["items"][0]["data"])
        self.assertIsNone(r1["items"][0]["credential"])
        os.environ["QCC_MCP_TOKEN"] = "JUSCITE-SYNTH-TOKEN-NOT-REAL"
        os.environ["TYC_MCP_TOKEN"] = "JUSCITE-SYNTH-TOKEN-NOT-REAL"
        r2 = call("enterprise.diligence_query",
                  {"query_id": "q2", "matter_id": "m",
                   "items": [{"provider": "tyc_mcp",
                              "credit_code": "91340100SYNTH0001X"}]},
                  self.ent_cfg)
        self.assertEqual(r2["items"][0]["status"], "SESSION_ABSENT")
        self.assertEqual(r2["items"][0]["reason"],
                         "CONNECTOR_SESSION_ABSENT_PENDING_AUTHORIZATION")
        self.assertIsNone(r2["items"][0]["data"])
        self.assertIsNone(r2["items"][0]["credential"])
        self.assertEqual(r2["sessions_established"], 0)

    def test_f144_provider_closed_set_and_key_discipline(self):
        with self.assertRaisesRegex(
                NotConnected, "f144_provider_unknown:unknowncorp_mcp"):
            call("enterprise.diligence_query",
                 {"query_id": "q", "matter_id": "m",
                  "items": [{"provider": "unknowncorp_mcp",
                             "company_name": "合成公司"}]}, self.ent_cfg)
        with self.assertRaisesRegex(
                NotConnected, "f144_query_key_exactly_one_required"):
            call("enterprise.diligence_query",
                 {"query_id": "q2", "matter_id": "m",
                  "items": [{"provider": "qcc_mcp",
                             "company_name": COMPANY,
                             "credit_code": "91340100SYNTH0001X"}]},
                 self.ent_cfg)
        with self.assertRaisesRegex(NotConnected,
                                    "f144_field_forbidden:url"):
            call("enterprise.diligence_query",
                 {"query_id": "q3", "matter_id": "m",
                  "items": [{"provider": "qcc_mcp",
                             "company_name": COMPANY,
                             "url": "synth-bypass-value"}]}, self.ent_cfg)
        with self.assertRaisesRegex(NotConnected,
                                    "f144_field_forbidden:cookie"):
            call("enterprise.diligence_query",
                 {"query_id": "q4", "matter_id": "m",
                  "items": [{"provider": "qcc_mcp",
                             "company_name": COMPANY,
                             "cookie": "synth-bypass-value"}]}, self.ent_cfg)

    def test_f144_receipt_binds_source_time_quota_no_payload_leak(self):
        self._token_ent()
        qr = ent.diligence_query(
            self.root / "ent",
            {"query_id": "q", "matter_id": "m",
             "items": [{"provider": "qcc_mcp", "company_name": COMPANY}]},
            session_factory=_synth_session_factory)
        item = qr["items"][0]
        self.assertEqual(item["status"], "DILIGENCE_RECORDED")
        cred = item["credential"]
        self.assertEqual(cred["provider"], "qcc_mcp")
        self.assertEqual(cred["retrieved_at"], "2026-10-21T08:30:00Z")
        self.assertEqual(cred["quota_remaining"], 87)
        self.assertEqual(item["data"]["payload_field_count"], 2)
        # 企业数据原文不落账。
        ledger = (self.root / "ent" / "queries" / "q.json").read_text(
            encoding="utf-8")
        self.assertNotIn(COMPANY, ledger)
        self.assertNotIn("存续（合成样本）", ledger)
        # seal 确定性。
        again = ent.record_from_receipt(
            {"provider": "qcc_mcp", "company_name": COMPANY,
             "credit_code": None},
            _SynthSession("qcc_mcp").query())
        self.assertEqual(again["seal"], cred["seal"])

    def test_f144_failure_no_data_and_closed_set_receipt(self):
        self._token_ent()

        def _boom(_provider):
            raise RuntimeError("synth connector down")

        class _BadProviderSession:
            def query(self, company_name=None, credit_code=None):
                return {"provider": "unknowncorp_mcp",
                        "retrieved_at": "2026-10-21T08:30:00Z",
                        "quota_remaining": 1, "payload": {}}

        class _NoQuotaSession:
            def query(self, company_name=None, credit_code=None):
                return {"provider": "tyc_mcp",
                        "retrieved_at": "2026-10-21T08:30:00Z",
                        "payload": {"k": "v"}}

        qr = ent.diligence_query(
            self.root / "ent",
            {"query_id": "q1", "matter_id": "m",
             "items": [{"provider": "qcc_mcp",
                        "company_name": COMPANY}]},
            session_factory=_boom)
        self.assertEqual(qr["items"][0]["status"], "QUERY_FAILED")
        self.assertIsNone(qr["items"][0]["data"])
        qr2 = ent.diligence_query(
            self.root / "ent",
            {"query_id": "q2", "matter_id": "m",
             "items": [{"provider": "tyc_mcp", "company_name": COMPANY}]},
            session_factory=lambda _p: _BadProviderSession())
        self.assertEqual(qr2["items"][0]["status"], "RECEIPT_INVALID")
        self.assertEqual(qr2["items"][0]["reason"],
                         "f144_receipt_invalid:provider_not_in_closed_set")
        qr3 = ent.diligence_query(
            self.root / "ent",
            {"query_id": "q3", "matter_id": "m",
             "items": [{"provider": "tyc_mcp", "company_name": COMPANY}]},
            session_factory=lambda _p: _NoQuotaSession())
        self.assertEqual(qr3["items"][0]["reason"],
                         "f144_receipt_invalid:quota_remaining_missing")
        self.assertIsNone(qr3["items"][0]["data"])

    def test_f144_replay_conflict_read(self):
        self._token_ent()
        qr = ent.diligence_query(
            self.root / "ent",
            {"query_id": "q", "matter_id": "m",
             "items": [{"provider": "qcc_mcp", "company_name": COMPANY}]},
            session_factory=_synth_session_factory)
        replay = ent.diligence_query(
            self.root / "ent",
            {"query_id": "q", "matter_id": "m",
             "items": [{"provider": "qcc_mcp", "company_name": COMPANY}]},
            session_factory=_synth_session_factory)
        self.assertEqual(replay, qr)
        with self.assertRaisesRegex(ent.EnterpriseConnectorError,
                                    "f144_query_conflict"):
            ent.diligence_query(
                self.root / "ent",
                {"query_id": "q", "matter_id": "m",
                 "items": [{"provider": "tyc_mcp",
                            "company_name": "别家合成公司"}]},
                session_factory=_synth_session_factory)
        self.assertEqual(
            call("enterprise.diligence_read", {"query_id": "q"},
                 self.ent_cfg), qr)
        with self.assertRaisesRegex(NotConnected, "f144_query_not_found"):
            call("enterprise.diligence_read", {"query_id": "nope"},
                 self.ent_cfg)


if __name__ == "__main__":
    unittest.main()

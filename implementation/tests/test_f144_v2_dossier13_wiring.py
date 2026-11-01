"""W5-U15 / F144-v2 企业尽调技能包 13 件全量桥面测试。

台账 F144-v2（B5 composite 段）断言「13 件套全量 v2」（06 source_stage
拍板文逐字；13 件清单唯一权威＝zhiexa-skill-market.md §1 启信宝 13 件
套，03-功能分母 F144 引）。W4-U40 九条负测纪律全继承：提供商闭集零
URL／缺 token PAID_TOKEN_NOT_CONFIGURED 不自采不编数据／SESSION_ABSENT
结构性不可达／回执转录绑定 出处-时间-额度-sha256 水印-确定性 seal／失
败三路 data-credential 恒 None／url-cookie 旁路字段具名拒＋恰一查询键
／AST 双验零网络导入零 URL 字面量／状态根产物零 URL 零 token 值／幂等
重放逐键相等。真实授权半边挂 F144-desktop/selfhost 回收点（W5-U19 守
账）不并单——全部合成材料（合成回执/合成会话显式 synth）。
"""
import ast
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'python'))

from legal_entry import (call, NotConnected, DOSSIER13_METHODS,
                         ENTERPRISE_CONNECTOR_METHODS)
import enterprise_connector as ent
import dossier13 as d13

COMPANY = "合成市合成科技有限公司"
SYNTH_TOKEN = "JUSCITE-SYNTH-TOKEN-NOT-REAL"

# 权威清单（zhiexa-skill-market.md §1 逐字；本测试钉定 13 件全量）。
AUTHORITY_PIECE_NAMES = (
    "企业优先级排序", "全景尽调报告", "公司风险速查",
    "关联企业传导风险", "前置准入核验", "司法与经营风险体检",
    "合作前主体核验", "国内企业关联关系", "多次关系寻源",
    "客户准入快速筛查", "招投标情报雷达", "负面舆情扫描",
    "重点区域企业检索",
)


class _SynthSession:
    def __init__(self, provider):
        self.provider = provider

    def query(self, company_name=None, credit_code=None):
        return {"provider": self.provider,
                "retrieved_at": "2026-10-23T08:30:00Z",
                "quota_remaining": 87,
                "payload": {"name": COMPANY, "status": "存续（合成样本）"}}


def _synth_session_factory(provider):
    return _SynthSession(provider)


class F144V2Dossier13WiringTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.d13_cfg = {"dossier13_state_root": str(self.root / "d13")}
        self._env = {v: os.environ.get(v)
                     for v in ("QCC_MCP_TOKEN", "TYC_MCP_TOKEN")}
        for v in self._env:
            os.environ.pop(v, None)

    def tearDown(self):
        for v, saved in self._env.items():
            if saved is None:
                os.environ.pop(v, None)
            else:
                os.environ[v] = saved
        self._tmp.cleanup()

    # -- AST 结构面（纪律⑦：导入闭集零网络模块＋字符串常量零 URL＋标识
    #    符零旁路关键字——dossier13 导入 enterprise_connector＝闭集单一权
    #    威的本地零网络产品模块）----------------------------------------
    def _ast_audit(self, path, expected_imports):
        source = Path(path).read_text(encoding='utf-8')
        tree = ast.parse(source)
        imported = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(a.name.split('.')[0] for a in node.names)
            elif isinstance(node, ast.ImportFrom) and node.level == 0:
                imported.add((node.module or '').split('.')[0])
        self.assertEqual(imported, expected_imports)
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

    def test_ast_dossier13_no_network_no_url_no_bypass(self):
        py = Path(__file__).resolve().parents[1] / 'python'
        self._ast_audit(
            py / 'dossier13.py',
            {'__future__', 'hashlib', 'json', 'os', 'datetime', 'pathlib',
             'enterprise_connector'})

    def test_frozen_method_groups(self):
        self.assertEqual(DOSSIER13_METHODS, frozenset({
            "dossier13.pack_read", "dossier13.run_dossier",
            "dossier13.dossier_read"}))
        # 提供商闭集单一权威：dossier13 不复制第二闭集。
        self.assertEqual(ent.PROVIDER_CATEGORIES, ("qcc_mcp", "tyc_mcp"))

    # -- 件目录面：13/13 全量闭集（全量＝不是 12 也不是 14）---------------
    def test_pack_read_full_set_13_verbatim_names(self):
        pack = call("dossier13.pack_read", {}, self.d13_cfg)
        self.assertEqual(pack["piece_count"], 13)
        self.assertTrue(pack["full_set"])
        self.assertEqual(pack["form"], "skill_pack_no_self_collection")
        self.assertEqual(pack["self_collection"], "none")
        self.assertEqual(pack["url_disclosure"], "none")
        self.assertEqual(pack["providers"], ["qcc_mcp", "tyc_mcp"])
        names = tuple(p["name"] for p in pack["pieces"])
        self.assertEqual(names, AUTHORITY_PIECE_NAMES)
        ids = [p["piece_id"] for p in pack["pieces"]]
        self.assertEqual(len(ids), len(set(ids)))
        blob = json.dumps(pack, ensure_ascii=False)
        self.assertNotIn(':' + '/' + '/', blob)

    def test_fail_closed_config_unknown_method_params(self):
        with self.assertRaisesRegex(
                NotConnected, "dossier13_state_root_not_configured"):
            call("dossier13.run_dossier",
                 {"dossier_id": "d", "matter_id": "m",
                  "piece_id": "panorama-report", "providers": ["qcc_mcp"],
                  "company_name": COMPANY}, {})
        with self.assertRaisesRegex(
                NotConnected, "method_not_connected:dossier13.explode"):
            call("dossier13.explode", {}, self.d13_cfg)
        with self.assertRaisesRegex(NotConnected,
                                    "dossier13_params_invalid"):
            call("dossier13.run_dossier", "not-a-dict", self.d13_cfg)

    # -- 纪律②：缺 token→PAID_TOKEN_NOT_CONFIGURED 不自采不编数据---------
    def test_run_piece_token_gap_values_none(self):
        r = call("dossier13.run_dossier",
                 {"dossier_id": "d-tok", "matter_id": "m",
                  "piece_id": "panorama-report",
                  "providers": ["qcc_mcp", "tyc_mcp"],
                  "company_name": COMPANY}, self.d13_cfg)
        self.assertEqual(r["piece_id"], "panorama-report")
        self.assertEqual(r["piece_name"], "全景尽调报告")
        for seg in r["segments"]:
            self.assertEqual(seg["status"], "TOKEN_NOT_CONFIGURED")
            self.assertEqual(seg["reason"], "PAID_TOKEN_NOT_CONFIGURED")
            self.assertIsNone(seg["data"])
            self.assertIsNone(seg["credential"])
        self.assertEqual(r["counts"]["token_not_configured"], 2)
        self.assertEqual(r["sessions_established"], 0)

    # -- 纪律①：提供商闭集外具名拒＋件闭集外具名拒------------------------
    def test_run_piece_closed_set_refusals(self):
        with self.assertRaisesRegex(NotConnected,
                                    "d13_provider_unknown:unknowncorp_mcp"):
            call("dossier13.run_dossier",
                 {"dossier_id": "d-bad", "matter_id": "m",
                  "piece_id": "company-risk-quick-scan",
                  "providers": ["unknowncorp_mcp"],
                  "company_name": COMPANY}, self.d13_cfg)
        with self.assertRaisesRegex(NotConnected,
                                    "d13_piece_unknown:no-such-piece"):
            call("dossier13.run_dossier",
                 {"dossier_id": "d-bad2", "matter_id": "m",
                  "piece_id": "no-such-piece",
                  "providers": ["qcc_mcp"],
                  "company_name": COMPANY}, self.d13_cfg)

    # -- 纪律③：token 在位仍 SESSION_ABSENT（桥 session_factory 恒 None
    #    ＝真实调用路径结构性不可达，客户端未建不可能自采）----------------
    def test_run_piece_session_absent_structural(self):
        os.environ["QCC_MCP_TOKEN"] = SYNTH_TOKEN
        os.environ["TYC_MCP_TOKEN"] = SYNTH_TOKEN
        r = call("dossier13.run_dossier",
                 {"dossier_id": "d-sess", "matter_id": "m",
                  "piece_id": "counterparty-verification",
                  "providers": ["qcc_mcp", "tyc_mcp"],
                  "credit_code": "91340100SYNTH0001X"}, self.d13_cfg)
        self.assertEqual(r["query_key"], "credit_code")
        for seg in r["segments"]:
            self.assertEqual(seg["status"], "SESSION_ABSENT")
            self.assertEqual(seg["reason"],
                             "CONNECTOR_SESSION_ABSENT_PENDING_AUTHORIZATION")
            self.assertIsNone(seg["data"])
            self.assertIsNone(seg["credential"])
        self.assertEqual(r["sessions_established"], 0)

    # -- 纪律④：合成回执转录绑定 出处/时间/额度＋sha256 水印＋确定性
    #    seal（凭证逐字承连接器产物＝单一权威零重算；企业原文不落账）------
    def test_run_piece_recorded_binds_credential_verbatim(self):
        os.environ["QCC_MCP_TOKEN"] = SYNTH_TOKEN
        os.environ["TYC_MCP_TOKEN"] = SYNTH_TOKEN
        r = d13.run_dossier(self.root / "d13",
                            {"dossier_id": "d-seal", "matter_id": "m",
                             "piece_id": "panorama-report",
                             "providers": ["qcc_mcp"],
                             "company_name": COMPANY},
                            session_factory=_synth_session_factory)
        seg = r["segments"][0]
        self.assertEqual(seg["status"], "DILIGENCE_RECORDED")
        cred = seg["credential"]
        self.assertEqual(cred["provider"], "qcc_mcp")
        self.assertEqual(cred["retrieved_at"], "2026-10-23T08:30:00Z")
        self.assertEqual(cred["quota_remaining"], 87)
        self.assertEqual(len(cred["source_watermark"]["payload_sha256"]), 64)
        self.assertEqual(seg["data"]["payload_sha256"],
                         cred["source_watermark"]["payload_sha256"])
        # 单一权威：凭证与连接器面 record_from_receipt 重算逐键相等。
        recompute = ent.record_from_receipt(
            {"provider": "qcc_mcp", "company_name": COMPANY,
             "credit_code": None}, _SynthSession("qcc_mcp").query())
        self.assertEqual(recompute, cred)
        # 企业数据原文不落账（档案文件原文扫描零企业名）。
        raw = (self.root / "d13" / "dossiers" / "d-seal.json").read_text(
            encoding="utf-8")
        self.assertNotIn(COMPANY, raw)
        self.assertNotIn("存续（合成样本）", raw)

    # -- 纪律⑤：失败三路 data/credential 恒 None（绝不编占位企业字段）----
    def test_run_piece_failure_three_ways_no_data(self):
        os.environ["QCC_MCP_TOKEN"] = SYNTH_TOKEN
        os.environ["TYC_MCP_TOKEN"] = SYNTH_TOKEN

        def _boom(_p):
            raise RuntimeError("synth connector down")

        r1 = d13.run_dossier(self.root / "d13",
                             {"dossier_id": "d-fail", "matter_id": "m",
                              "piece_id": "bidding-radar",
                              "providers": ["qcc_mcp"],
                              "company_name": COMPANY},
                             session_factory=_boom)
        self.assertEqual(r1["segments"][0]["status"], "QUERY_FAILED")
        self.assertEqual(r1["segments"][0]["reason"],
                         "connector_failed:RuntimeError")
        self.assertIsNone(r1["segments"][0]["data"])
        self.assertIsNone(r1["segments"][0]["credential"])

        class _BadSession:
            def query(self, company_name=None, credit_code=None):
                return {"provider": "unknowncorp_mcp",
                        "retrieved_at": "2026-10-23T08:30:00Z",
                        "payload": {}}

        r2 = d13.run_dossier(self.root / "d13",
                             {"dossier_id": "d-bad", "matter_id": "m",
                              "piece_id": "negative-publicity-scan",
                              "providers": ["tyc_mcp"],
                              "company_name": COMPANY},
                             session_factory=lambda _p: _BadSession())
        self.assertEqual(r2["segments"][0]["status"], "RECEIPT_INVALID")
        self.assertEqual(r2["segments"][0]["reason"],
                         "f144_receipt_invalid:provider_not_in_closed_set")
        self.assertIsNone(r2["segments"][0]["data"])

        class _NoQuotaSession:
            def query(self, company_name=None, credit_code=None):
                return {"provider": "tyc_mcp",
                        "retrieved_at": "2026-10-23T08:30:00Z",
                        "payload": {"k": "v"}}

        r3 = d13.run_dossier(self.root / "d13",
                             {"dossier_id": "d-noquota", "matter_id": "m",
                              "piece_id": "key-region-search",
                              "providers": ["tyc_mcp"],
                              "company_name": COMPANY},
                             session_factory=lambda _p: _NoQuotaSession())
        self.assertEqual(r3["segments"][0]["reason"],
                         "f144_receipt_invalid:quota_remaining_missing")
        self.assertIsNone(r3["segments"][0]["data"])
        self.assertIsNone(r3["segments"][0]["credential"])

    # -- 纪律⑥：旁路字段顶层具名拒＋恰一查询键----------------------------
    def test_run_piece_bypass_fields_and_key_discipline(self):
        for field in ("url", "cookie"):
            with self.assertRaisesRegex(
                    NotConnected, "d13_field_forbidden:" + field):
                call("dossier13.run_dossier",
                     {"dossier_id": "d-neg-" + field, "matter_id": "m",
                      "piece_id": "pre-admission-check",
                      "providers": ["qcc_mcp"],
                      "company_name": COMPANY,
                      field: "synth-bypass-value"}, self.d13_cfg)
        with self.assertRaisesRegex(
                NotConnected, "d13_query_key_exactly_one_required"):
            call("dossier13.run_dossier",
                 {"dossier_id": "d-both", "matter_id": "m",
                  "piece_id": "pre-admission-check",
                  "providers": ["qcc_mcp"],
                  "company_name": COMPANY,
                  "credit_code": "91340100SYNTH0001X"}, self.d13_cfg)
        with self.assertRaisesRegex(
                NotConnected, "d13_query_key_exactly_one_required"):
            call("dossier13.run_dossier",
                 {"dossier_id": "d-none", "matter_id": "m",
                  "piece_id": "pre-admission-check",
                  "providers": ["qcc_mcp"]}, self.d13_cfg)

    # -- 纪律⑧：状态根产物零 URL 零 token 值-------------------------------
    def test_artifacts_zero_url_zero_token(self):
        os.environ["QCC_MCP_TOKEN"] = SYNTH_TOKEN
        d13.run_dossier(self.root / "d13",
                        {"dossier_id": "d-scan", "matter_id": "m",
                         "piece_id": "affiliate-risk-transmission",
                         "providers": ["qcc_mcp"],
                         "company_name": COMPANY},
                        session_factory=_synth_session_factory)
        blob = "\n".join(
            p.read_text(encoding="utf-8", errors="replace")
            for p in sorted(self.root.rglob("*.json")))
        for part in ("http", "https", "ftp", "ws", "wss"):
            self.assertNotIn(part + ":" + "/" + "/", blob.lower())
        self.assertNotIn(SYNTH_TOKEN, blob)

    # -- 纪律⑨：幂等重放逐键相等／异输入具名 conflict／回读投影相等--------
    def test_replay_conflict_read(self):
        r = call("dossier13.run_dossier",
                 {"dossier_id": "d-idem", "matter_id": "m",
                  "piece_id": "multi-hop-relation",
                  "providers": ["qcc_mcp", "tyc_mcp"],
                  "company_name": COMPANY}, self.d13_cfg)
        replay = call("dossier13.run_dossier",
                      {"dossier_id": "d-idem", "matter_id": "m",
                       "piece_id": "multi-hop-relation",
                       "providers": ["qcc_mcp", "tyc_mcp"],
                       "company_name": COMPANY}, self.d13_cfg)
        self.assertEqual(replay, r)
        with self.assertRaisesRegex(NotConnected, "d13_dossier_conflict"):
            call("dossier13.run_dossier",
                 {"dossier_id": "d-idem", "matter_id": "m",
                  "piece_id": "multi-hop-relation",
                  "providers": ["tyc_mcp"],
                  "company_name": COMPANY}, self.d13_cfg)
        self.assertEqual(
            call("dossier13.dossier_read", {"dossier_id": "d-idem"},
                 self.d13_cfg), r)
        with self.assertRaisesRegex(NotConnected, "d13_dossier_not_found"):
            call("dossier13.dossier_read", {"dossier_id": "nope"},
                 self.d13_cfg)
        with self.assertRaisesRegex(NotConnected, "d13_field_forbidden:evil"):
            call("dossier13.dossier_read",
                 {"dossier_id": "d", "evil": "x"}, self.d13_cfg)

    # -- 全量覆盖：13 件全跑各落一档（13/13，不缺件不重件）----------------
    def test_full_pack_coverage_13_dossiers(self):
        os.environ["QCC_MCP_TOKEN"] = SYNTH_TOKEN
        os.environ["TYC_MCP_TOKEN"] = SYNTH_TOKEN
        seen = []
        for piece in d13.PIECE_IDS:
            r = d13.run_dossier(
                self.root / "d13",
                {"dossier_id": "cov-" + piece, "matter_id": "m",
                 "piece_id": piece, "providers": ["qcc_mcp", "tyc_mcp"],
                 "company_name": COMPANY},
                session_factory=_synth_session_factory)
            seen.append(r["piece_id"])
            self.assertEqual(r["piece_name"],
                             dict(d13.DOSSIER13_PIECES)[piece])
            self.assertEqual(r["counts"]["diligence_recorded"], 2)
        self.assertEqual(len(seen), 13)
        self.assertEqual(sorted(seen), sorted(d13.PIECE_IDS))
        self.assertEqual(len(list((self.root / "d13" / "dossiers")
                                  .glob("*.json"))), 13)


if __name__ == "__main__":
    unittest.main()

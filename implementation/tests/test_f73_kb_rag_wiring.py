# -*- coding: utf-8 -*-
"""W4-U43 / F73 用户自建知识库 RAG 接线验收（implementation/tests）。

06:F73 acceptance「经验/所内知识按授权/快照/出处检索，向量质量与过期
治理真实，不串案」＋17 卡步骤「固定内容 hash/权限→公开读取→实际任务
消费→来源回执和验证；不公开私域蒸馏」的产品面断言：

* KB_METHODS 冻结四方法；kb_rag 零 legal_cn_manuals/lcr/网络 import
  （manuals 仓零引擎代码铁律＋f71_hybrid/1 接口级复用不互锁）；
* 授权 fail-closed（public 恒在/firm 显式/private 永不可授权）；
* 内容快照 sha256 全字段＋read 逐次重算，漂移具名拒；
* 质量评分与过期治理真实（因子具名回显，过期降权标记不静默）；
* 分案隔离（跨案结构性不可见）；
* 出处 sourceRefs（C16 ref 形状）随命中/回读携带；
* 检索质量金标：合成主题语 recall@1/MRR=1.0，两跑逐字节同。

全部材料为工程合成条目（标注合成，无法条引文）；状态根 %TEMP% 级
TemporaryDirectory；零网络；零 %APPDATA% 触碰。
"""
import ast
import json
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE / "python"))
import kb_rag  # noqa: E402
import legal_entry  # noqa: E402


def _meta(kb_id, *, scope="public", quality=0.8, last_verified=None,
          window=None, matter=None, sources=None, title=None, body=None):
    return {"kbId": kb_id,
            "title": title or ("合成条目·" + kb_id + "（工程验证用，无法律效力）"),
            "body": body or ("# 合成（SYNTHETIC）\n这是 %s 的工程合成经验条目，"
                             "用于知识库检索验收，无任何真实法条引文。" % kb_id),
            "readScope": scope, "qualityScore": quality,
            "lastVerified": last_verified, "freshnessWindowDays": window,
            "matterId": matter,
            "sourceRefs": sources or [{"owner": "kb", "kind": "kb-source",
                                       "id": "syn-origin-" + kb_id}],
            "topics": []}


class _Env:
    """独立临时状态根（每用例自持，用毕清理）；store 每次访问重建
    （状态全部落盘，重建即持久化路径的持续检验）。"""

    def __init__(self, backend=None):
        self.holder = tempfile.TemporaryDirectory(prefix="f73-kb-test-")
        self.config = {"kb_state_root": self.holder.name}
        if backend:
            self.config["kb_backend"] = backend

    @property
    def store(self):
        return kb_rag.KbStore(self.holder.name,
                              self.config.get("kb_backend"))

    def close(self):
        self.holder.cleanup()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()


class TestMethodGroupFrozen(unittest.TestCase):
    def test_frozen_method_group_is_the_kb_quartet(self):
        self.assertEqual(legal_entry.KB_METHODS, frozenset({
            "kb.entry_put", "kb.search", "kb.read", "kb.stats"}))

    def test_engine_import_closure_has_no_manuals_cases_network(self):
        allowed = {"__future__", "datetime", "hashlib", "json", "math",
                   "os", "re", "typing"}
        source = (HERE / "python" / "kb_rag.py").read_text(encoding="utf-8")
        imports = set()
        for node in ast.walk(ast.parse(source)):
            if isinstance(node, ast.Import):
                imports.update(a.name.split(".")[0] for a in node.names)
            elif isinstance(node, ast.ImportFrom) and node.level == 0:
                imports.add((node.module or "").split(".")[0])
        self.assertEqual(sorted(imports), sorted(allowed))

    def test_retrieval_contract_names_f71_interface_without_importing_it(self):
        self.assertEqual(kb_rag.KB_RETRIEVAL_CONTRACT, "f71_hybrid/1")
        self.assertEqual(kb_rag.LOCAL_BACKEND_ID, "local-deterministic-v1")
        self.assertEqual(sorted(kb_rag.BACKENDS),
                         ["local-deterministic-v1"])

    def test_private_never_in_authorized_scopes_constant(self):
        self.assertEqual(kb_rag.READ_SCOPES, ("public", "firm", "private"))
        self.assertNotIn(kb_rag.PRIVATE_SCOPE, kb_rag._ALLOWED_FIRM)


class TestEntrySnapshotAndProvenance(unittest.TestCase):
    def test_digest_is_canonical_full_field_sha256(self):
        meta = _meta("kb-dig-1", last_verified="2026-10-01", window=365)
        with _Env() as env:
            out = env.store.entry_put(meta)
            self.assertTrue(out["revised"])
            self.assertEqual(out["entryDigest"],
                             kb_rag.entry_digest(meta))
            again = env.store.entry_put(meta)
            self.assertFalse(again["revised"])  # 幂等：同内容不追加修订
            self.assertEqual(again["revision"], out["revision"])

    def test_revision_supersede_keeps_history_readable(self):
        meta = _meta("kb-rev-1", body="合成正文第一版（SYNTHETIC）")
        with _Env() as env:
            v1 = env.store.entry_put(meta)
            meta2 = dict(meta, body="合成正文第二版（SYNTHETIC）")
            v2 = env.store.entry_put(meta2)
            self.assertEqual(v2["revision"], 2)
            self.assertEqual(v2["superseded"]["revision"], 1)
            old = env.store.read({"kbId": "kb-rev-1", "version": 1})
            self.assertIn("第一版", old["body"])
            self.assertEqual(old["entryRef"]["digest"], v1["entryDigest"])

    def test_read_recomputes_digest_tamper_named_refusal(self):
        meta = _meta("kb-tam-1")
        with _Env() as env:
            env.store.entry_put(meta)
            path = Path(env.holder.name) / "entries.jsonl"
            rows = [json.loads(l) for l in
                    path.read_text(encoding="utf-8").splitlines() if l]
            rows[0]["content"]["body"] = "被篡改的正文（SYNTHETIC tamper probe）"
            path.write_text(
                "\n".join(json.dumps(r, ensure_ascii=False, sort_keys=True)
                          for r in rows) + "\n", encoding="utf-8")
            with self.assertRaises(kb_rag.KbRagError) as ctx:
                env.store.read({"kbId": "kb-tam-1"})
            self.assertIn("kb_digest_mismatch", str(ctx.exception))

    def test_entry_without_provenance_refused(self):
        meta = _meta("kb-nosrc-1")
        meta["sourceRefs"] = []
        with self.assertRaises(kb_rag.KbRagError) as ctx:
            kb_rag.validate_entry_args(meta)
        self.assertIn("kb_entry_invalid", str(ctx.exception))
        with self.assertRaises(kb_rag.KbRagError):
            kb_rag.validate_entry_args(
                _meta("kb-badsrc-1", sources=[{"owner": "kb", "id": "x"}]))


class TestAuthorizationMatrix(unittest.TestCase):
    def test_public_visible_firm_hidden_until_authorized(self):
        with _Env() as env:
            env.store.entry_put(_meta("kb-pub-1", scope="public"))
            env.store.entry_put(_meta("kb-firm-1", scope="firm",
                                      body="所内受控合成条目：内部结算复核清单（工程样本）"))
            q = {"query": "内部结算复核清单 合成条目"}
            pub = env.store.search(dict(q))
            self.assertIn("kb-pub-1", [h["entryRef"]["id"] for h in pub["hits"]])
            self.assertNotIn("kb-firm-1", [h["entryRef"]["id"] for h in pub["hits"]])
            firm = env.store.search(dict(q, authorizedReadScopes=["firm"]))
            ids = [h["entryRef"]["id"] for h in firm["hits"]]
            self.assertIn("kb-firm-1", ids)
            self.assertEqual(firm["authorizedReadScopes"], ["firm", "public"])

    def test_private_never_authorizable_and_never_read(self):
        with _Env() as env:
            env.store.entry_put(_meta("kb-priv-1", scope="private",
                                      body="个人私域合成蒸馏条目（工程样本）"))
            with self.assertRaises(kb_rag.KbRagError) as ctx:
                env.store.search({"query": "私域蒸馏",
                                  "authorizedReadScopes": ["private"]})
            self.assertIn("kb_scope_mismatch", str(ctx.exception))
            hits = env.store.search({"query": "私域蒸馏 合成",
                                     "authorizedReadScopes": ["firm"]})
            self.assertNotIn("kb-priv-1", [h["entryRef"]["id"] for h in hits["hits"]])
            with self.assertRaises(kb_rag.KbRagError) as ctx:
                env.store.read({"kbId": "kb-priv-1"})
            self.assertIn("kb_scope_mismatch", str(ctx.exception))
            stats = env.store.stats()
            self.assertEqual(stats["byScope"]["private"], 1)  # 在库但永不出面


class TestQualityAndExpiry(unittest.TestCase):
    def test_quality_factor_breaks_tie_and_is_echoed(self):
        with _Env() as env:
            env.store.entry_put(_meta("kb-qual-low", quality=0.3))
            env.store.entry_put(_meta("kb-qual-high", quality=0.9))
            out = env.store.search({"query": "工程合成经验条目 知识库检索验收"})
            ids = [h["entryRef"]["id"] for h in out["hits"]]
            self.assertEqual(ids, ["kb-qual-high", "kb-qual-low"])
            scores = {h["entryRef"]["id"]: h["score"] for h in out["hits"]}
            self.assertEqual(scores["kb-qual-high"]["qualityFactor"], 0.95)
            self.assertEqual(scores["kb-qual-low"]["qualityFactor"], 0.65)

    def test_expired_marked_and_downweighted_never_silent(self):
        import datetime as dt
        today = dt.datetime.now(dt.timezone.utc).date().isoformat()
        with _Env() as env:
            env.store.entry_put(_meta("kb-stale-old", quality=0.8,
                                      last_verified="2020-01-01", window=30))
            env.store.entry_put(_meta("kb-stale-new", quality=0.8,
                                      last_verified=today, window=365))
            out = env.store.search({"query": "工程合成经验条目 知识库检索验收"})
            hits = {h["entryRef"]["id"]: h for h in out["hits"]}
            self.assertTrue(hits["kb-stale-old"]["stale"])
            self.assertEqual(hits["kb-stale-old"]["staleReason"],
                             "freshness_expired")
            self.assertEqual(hits["kb-stale-old"]["score"]["stalenessFactor"], 0.5)
            self.assertFalse(hits["kb-stale-new"]["stale"])
            self.assertGreater(hits["kb-stale-new"]["score"]["effective"],
                               hits["kb-stale-old"]["score"]["effective"])
            # 回执过期计数＝可验口径（返回命中中的过期条数），响应与
            # usage log 双面一致。
            self.assertEqual(out["staleCount"], 1)
            log = (Path(env.holder.name) / "usage-log.jsonl").read_text(
                encoding="utf-8").splitlines()
            receipts = [json.loads(l) for l in log if l]
            self.assertEqual(receipts[-1]["staleCount"], 1)

    def test_unverified_marked_freshness_unknown(self):
        with _Env() as env:
            env.store.entry_put(_meta("kb-unv-1"))
            out = env.store.search({"query": "工程合成经验条目"})
            hit = out["hits"][0]
            self.assertTrue(hit["stale"])
            self.assertEqual(hit["staleReason"], "freshness_unknown")


class TestCaseIsolation(unittest.TestCase):
    def test_cross_case_structurally_invisible(self):
        with _Env() as env:
            env.store.entry_put(_meta("kb-ma-1", matter="m-atok-a"))
            env.store.entry_put(_meta("kb-glob-1", matter=None))
            q = {"query": "工程合成经验条目"}
            in_a = env.store.search(dict(q, matterId="m-atok-a"))
            self.assertIn("kb-ma-1", [h["entryRef"]["id"] for h in in_a["hits"]])
            in_b = env.store.search(dict(q, matterId="m-atok-b"))
            self.assertNotIn("kb-ma-1", [h["entryRef"]["id"] for h in in_b["hits"]])
            self.assertIn("kb-glob-1", [h["entryRef"]["id"] for h in in_b["hits"]])
            glob = env.store.search(dict(q))
            self.assertNotIn("kb-ma-1", [h["entryRef"]["id"] for h in glob["hits"]])
            self.assertIn("kb-glob-1", [h["entryRef"]["id"] for h in glob["hits"]])


class TestRetrievalQuality(unittest.TestCase):
    TOPICS = {
        "t1": "押金 结算 租赁 物业交割 退还",
        "t2": "仲裁 时效 劳动关系 申请期限",
        "t3": "知识产权 许可 侵权 合同条款",
        "t4": "工期 签证 施工 监理 计日",
    }

    def _corpus(self):
        entries = []
        for tid, words in self.TOPICS.items():
            for n in (1, 2, 3):
                entries.append(_meta(
                    "kb-%s-%d" % (tid, n), quality=0.9,
                    body="合成经验条目（SYNTHETIC）：%s 相关要点 %d。%s。"
                         "工程验证样本，无法条引文。" % (words, n, words)))
        entries.append(_meta("kb-noise-1", quality=0.9,
                             body="合成噪声条目：天气记录 食谱 旅行笔记 工程样本"))
        return entries

    def test_golden_recall_mrr_and_determinism(self):
        with _Env() as env:
            for meta in self._corpus():
                env.store.entry_put(meta)
            for tid, words in self.TOPICS.items():
                golden = {"kb-%s-1" % tid, "kb-%s-2" % tid, "kb-%s-3" % tid}
                out = env.store.search({"query": words, "topK": 4})
                self.assertEqual(out["hits"][0]["entryRef"]["id"] in golden,
                                 True, tid)
                first_golden_rank = next(
                    i for i, h in enumerate(out["hits"], 1)
                    if h["entryRef"]["id"] in golden)
                self.assertEqual(first_golden_rank, 1, tid)
            again = env.store.search({"query": self.TOPICS["t1"], "topK": 4})
            first = env.store.search({"query": self.TOPICS["t1"], "topK": 4})
            strip = lambda r: json.dumps(r["hits"], ensure_ascii=False,
                                         sort_keys=True)
            self.assertEqual(strip(first), strip(again))  # 两跑逐字节同

    def test_vector_component_discriminates(self):
        backend = kb_rag.LocalDeterministicBackend()
        golden = "押金 结算 租赁 物业交割 退还 相关合成条目全文"
        noise = "天气记录 食谱 旅行笔记 工程样本"
        query = self.TOPICS["t1"]
        g = backend.score_components(query, golden)
        n = backend.score_components(query, noise)
        self.assertGreater(g["vector"], n["vector"])
        self.assertGreater(g["vector"], 0.0)


class TestBridgeWiring(unittest.TestCase):
    def test_unconfigured_root_fails_closed(self):
        with self.assertRaises(legal_entry.NotConnected) as ctx:
            legal_entry.call("kb.search", {"query": "x"}, {})
        self.assertIn("kb_state_root_not_configured", str(ctx.exception))

    def test_unknown_backend_named_refusal(self):
        with _Env(backend="definitely-not-a-backend") as env:
            with self.assertRaises(legal_entry.NotConnected) as ctx:
                legal_entry.call("kb.stats", {}, env.config)
            self.assertIn("kb_backend_unknown", str(ctx.exception))

    def test_in_process_roundtrip_via_bridge(self):
        with _Env() as env:
            put = legal_entry.call("kb.entry_put", _meta("kb-bridge-1"),
                                   env.config)
            self.assertTrue(put["revised"])
            out = legal_entry.call(
                "kb.search", {"query": "工程合成经验条目"}, env.config)
            self.assertEqual(out["backend"], "local-deterministic-v1")
            self.assertEqual(out["retrievalContract"], "f71_hybrid/1")
            self.assertEqual(out["hits"][0]["entryRef"]["id"], "kb-bridge-1")
            read = legal_entry.call("kb.read",
                                    {"kbId": "kb-bridge-1"}, env.config)
            self.assertEqual(read["entryRef"]["digest"],
                             put["entryDigest"])
            stats = legal_entry.call("kb.stats", {}, env.config)
            self.assertEqual(stats["entryCount"], 1)

    def test_non_kb_method_stays_not_connected(self):
        with self.assertRaises(legal_entry.NotConnected):
            legal_entry.call("kb.distill", {}, {"kb_state_root": "x"})
        with self.assertRaises(legal_entry.NotConnected):
            legal_entry.call("kb.read", {}, {"kb_state_root": "x"})  # 缺 kbId


if __name__ == "__main__":
    unittest.main()

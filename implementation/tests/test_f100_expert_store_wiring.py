# -*- coding: utf-8 -*-
"""W5-U04 / F100 专家分身/专家商店 接线验收（implementation/tests）。

06:F100 acceptance「专家内容授权/来源/适用范围准确；分身不冒真人实时
意见」＋17 卡步骤「固定内容 hash/权限→公开读取→实际任务消费→来源
回执和验证；不公开私域蒸馏」的产品面断言：

* EXPERT_METHODS 冻结五方法（无 publish/enable/distill/observe 写面）；
  expert_store 零 legal_cn_manuals/lcr/网络 import（manuals 仓零引擎
  代码铁律＋不复制第二权威——公开消费只经既有冻结通道）；
* 「分身不冒真人实时意见」结构面：grounding 闭集只认 pinned_pack
  （live/realtime 形具名拒）＋declaresRealTime True 具名拒＋validated
  卡片恒存 False＋consult 应答恒携 nonLive 声明；
* 授权面：synthetic_original 不得挂署名/凭据；authorized_excerpt 必须
  attributedTo＋authorizationRef；适用范围声明是准入要件；private 内容
  不入包、private 永不可授权（不公开私域蒸馏）；
* 内容快照 sha256 全字段（含正文）＋逐次重算，漂移具名拒；
* 商店货架（store_list/store_read）永不携条目正文（字节级断言）；
* consult 确定性词面评分金标（合成主题 recall@1=1.0·两跑同分）＋零词
  面重叠＝f100_out_of_scope_abstain 具名弃答；
* 来源回执：consult 回执落盘＋verify_receipt 全量重算（receiptId/卡片
  /条目三级），篡改/漂移具名拒不假 PASS。

全部材料为工程合成样本（标注合成，无法条引文，无真人署名——署名字
段本身是「合成署名·工程验证样本」）；状态根 %TEMP% 级
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
import expert_store  # noqa: E402
import legal_entry  # noqa: E402

SYN_MARK = ("本条为工程合成验收材料（SYNTHETIC），无任何真实法条引文、"
            "无真实案情。")

SYN_TOPICS = {
    "t1": ("押金结算退还", "押金 结算 租赁 物业交割 退还",
           "租赁押金结算应在物业交割后按清单核验扣除项，剩余押金限期退还，"
           "异议须留痕。"),
    "t2": ("仲裁时效管理", "仲裁 时效 劳动关系 申请期限",
           "劳动关系争议申请仲裁的时效台账要点：起算、中止、中断事由逐项"
           "留痕，逾期风险主动提示。"),
    "t3": ("知识产权许可审查", "知识产权 许可 侵权 合同条款",
           "知识产权许可合同条款审查要点：许可范围、分许可限制、侵权责任"
           "分担与终止后义务。"),
    "t4": ("工期签证台账", "工期 签证 施工 监理 计日",
           "建设工程工期签证与监理计日记录管理：事件发生后限期书面签证，"
           "顺延申请附证据链。"),
}


def synth_body(tid: str, n: int) -> str:
    name, _q, point = SYN_TOPICS[tid]
    return ("# 合成经验条目·%s·%d（工程验证样本）\n%s\n%s\n"
            % (name, n, point, SYN_MARK))


def card_args(expert_id="exp-syn-1", *, display="合成专家·甲（工程验证样本）",
              scope="public", topics_of=None):
    """合成专家卡：4 主题×3 条目（全部同一 scope），grounding/attribution
    合法缺省（synthetic_original＋pinned_pack）。"""
    items = []
    for tid in SYN_TOPICS:
        for n in (1, 2, 3):
            items.append({
                "title": "合成经验条目·%s·%d（工程验证样本）"
                         % (SYN_TOPICS[tid][0], n),
                "body": synth_body(tid, n),
                "readScope": scope,
                "sourceRefs": [{"owner": "synthetic", "kind": "syn-doc",
                                "id": "syn-%s-%d" % (tid, n),
                                "digest": expert_store.sha256_hex(
                                    expert_store.canonical_json(
                                        {"syn": tid, "n": n}))}],
                "topics": [SYN_TOPICS[tid][0]] + (topics_of or []),
            })
    return {"expertId": expert_id, "displayName": display,
            "grounding": {"kind": "pinned_pack", "declaresRealTime": False},
            "attribution": {"authorship": "synthetic_original"},
            "applicableScopes": ["工程合成验收场景"],
            "items": items}


class _Env:
    """独立临时状态根（每用例自持，用毕清理）；store 每次访问重建
    （状态全部落盘，重建即持久化路径的持续检验）。"""

    def __init__(self):
        self.holder = tempfile.TemporaryDirectory(prefix="f100-expert-test-")
        self.config = {"expert_state_root": self.holder.name}

    @property
    def store(self):
        return expert_store.ExpertStore(self.holder.name)

    def close(self):
        self.holder.cleanup()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()


def refuse_code(exc: Exception) -> str:
    """NotConnected 载荷里的 typed 码（expert 组前缀 expert_failed: 后段）。"""
    text = str(exc)
    return text.split("expert_failed:", 1)[1] \
        if text.startswith("expert_failed:") else text


class F100ExpertStoreWiring(unittest.TestCase):
    def test_frozen_method_group_is_the_expert_five(self):
        self.assertEqual(
            legal_entry.EXPERT_METHODS,
            {"expert.define", "expert.store_list", "expert.store_read",
             "expert.consult", "expert.verify_receipt"})
        # 无发布/启用/蒸馏/观察写面（E23 断言面同频；裁决#7 Observer 不启用）。
        banned = ("publish", "enable", "distill", "observe", "install")
        self.assertFalse(any(b in m for m in legal_entry.EXPERT_METHODS
                             for b in banned))

    def test_engine_import_closure_has_no_manuals_cases_network(self):
        tree = ast.parse(
            (HERE / "python" / "expert_store.py").read_text(encoding="utf-8"))
        mods = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                mods.update(a.name for a in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                mods.add(node.module)
        allowed = {"__future__", "datetime", "hashlib", "json", "math",
                   "os", "re", "typing"}
        self.assertEqual(mods - allowed, set(),
                         "expert_store import 闭集越界：%s" % (mods - allowed))

    def test_card_digest_is_canonical_full_field_sha256(self):
        with _Env() as env:
            args = card_args()
            out = env.store.define(args)
            meta = expert_store.validate_card_args(args)
            self.assertEqual(out["cardDigest"],
                             expert_store.sha256_hex(
                                 expert_store.canonical_json(
                                     expert_store.card_view(meta))))
            # 正文一字之变 → 卡片 hash 变（含正文的快照才叫固定内容 hash）。
            changed = card_args()
            changed["items"][0]["body"] += "增补一字"
            out2 = env.store.define(changed)
            self.assertNotEqual(out["cardDigest"], out2["cardDigest"])

    def test_grounding_closed_set_refuses_live_forms(self):
        with _Env() as env:
            for kind in ("live", "realtime_opinions", "online_feed",
                         "pinned_pack_live"):
                args = card_args()
                args["grounding"] = {"kind": kind}
                with self.assertRaises(expert_store.ExpertStoreError) as cm:
                    env.store.define(args)
                self.assertTrue(str(cm.exception).startswith(
                    "f100_grounding_kind_refused:"), kind)

    def test_declares_real_time_true_refused_and_validated_stores_false(self):
        with _Env() as env:
            args = card_args()
            args["grounding"] = {"kind": "pinned_pack",
                                 "declaresRealTime": True}
            with self.assertRaises(expert_store.ExpertStoreError) as cm:
                env.store.define(args)
            self.assertEqual(str(cm.exception), "f100_realtime_claim_refused")
            out = env.store.define(card_args())
            env2 = expert_store.ExpertStore(env.holder.name)
            row = [r for r in env2._load()
                   if r["expertId"] == out["cardRef"]["id"]][0]
            self.assertIs(row["card"]["grounding"]["declaresRealTime"], False)

    def test_authorized_excerpt_requires_attribution_and_ref(self):
        with _Env() as env:
            base = {"expertId": "exp-ae", "displayName": "x",
                    "grounding": {"kind": "pinned_pack"},
                    "applicableScopes": ["s"],
                    "items": card_args()["items"]}
            for attribution in (
                    {"authorship": "authorized_excerpt"},
                    {"authorship": "authorized_excerpt",
                     "attributedTo": "某人"},
                    {"authorship": "authorized_excerpt",
                     "authorizationRef": "ref-1"}):
                args = dict(base, attribution=attribution)
                with self.assertRaises(expert_store.ExpertStoreError) as cm:
                    env.store.define(args)
                self.assertEqual(str(cm.exception),
                                 "f100_authorization_missing")
            # 齐备才入店（attributedTo/authorizationRef 为合成样本值）。
            ok = dict(base, attribution={
                "authorship": "authorized_excerpt",
                "attributedTo": "合成署名·乙（工程验证样本）",
                "authorizationRef": "syn-authz-ref-001"})
            self.assertTrue(env.store.define(ok)["revised"])

    def test_synthetic_original_conflicts_with_attribution(self):
        with _Env() as env:
            args = card_args()
            args["attribution"] = {
                "authorship": "synthetic_original",
                "attributedTo": "合成署名·丙（工程验证样本）"}
            with self.assertRaises(expert_store.ExpertStoreError) as cm:
                env.store.define(args)
            self.assertEqual(str(cm.exception), "f100_attribution_conflict")

    def test_applicable_scopes_declaration_required(self):
        with _Env() as env:
            for scopes in ([], None, [""], "劳动用工"):
                args = card_args()
                if scopes is None:
                    del args["applicableScopes"]
                else:
                    args["applicableScopes"] = scopes
                with self.assertRaises(expert_store.ExpertStoreError) as cm:
                    env.store.define(args)
                self.assertEqual(str(cm.exception),
                                 "f100_scope_declaration_required")

    def test_private_item_not_bindable_and_scope_closed_set(self):
        self.assertEqual(expert_store.CARD_SCOPES, ("public", "firm"))
        self.assertNotIn(expert_store.PRIVATE_SCOPE,
                         expert_store.CARD_SCOPES)
        with _Env() as env:
            args = card_args()
            args["items"][0]["readScope"] = "private"
            with self.assertRaises(expert_store.ExpertStoreError) as cm:
                env.store.define(args)
            self.assertEqual(str(cm.exception),
                             "f100_private_content_not_bindable")

    def test_define_idempotent_and_supersede_keeps_history(self):
        with _Env() as env:
            first = env.store.define(card_args())
            self.assertEqual((first["revision"], first["revised"]), (1, True))
            again = env.store.define(card_args())
            self.assertEqual((again["revision"], again["revised"]), (1, False))
            self.assertEqual(again["cardDigest"], first["cardDigest"])
            changed = card_args()
            changed["items"][0]["title"] += "（修订）"
            second = env.store.define(changed)
            self.assertEqual((second["revision"], second["revised"]), (2, True))
            self.assertEqual(second["superseded"],
                             {"revision": 1, "cardDigest": first["cardDigest"]})
            # 历史可回读（v1 仍是原 hash）。
            old = env.store.store_read({"expertId": "exp-syn-1", "version": 1})
            self.assertEqual(old["cardRef"]["digest"], first["cardDigest"])

    def test_store_read_and_list_never_carry_bodies(self):
        with _Env() as env:
            env.store.define(card_args())
            listing = env.store.store_list({})
            read = env.store.store_read({"expertId": "exp-syn-1"})
            for tid in SYN_TOPICS:
                for n in (1, 2, 3):
                    needle = SYN_TOPICS[tid][2][:20]
                    blob = json.dumps(listing, ensure_ascii=False) \
                        + json.dumps(read, ensure_ascii=False)
                    self.assertNotIn(needle, blob,
                                     "货架泄漏条目正文：%s" % tid)
            # 货架元数据仍带全授权/来源/适用范围面。
            card = read["items"][0]
            self.assertIn("itemDigest", card)
            self.assertIn("sourceRefs", card)
            self.assertIn("applicableScopes", read)

    def test_public_visible_firm_hidden_until_authorized(self):
        with _Env() as env:
            env.store.define(card_args("exp-pub"))
            env.store.define(card_args("exp-firm", scope="firm"))
            pub_only = env.store.store_list({})
            self.assertEqual([c["expertId"] for c in pub_only["cards"]],
                             ["exp-pub"])
            both = env.store.store_list({"authorizedReadScopes": ["firm"]})
            self.assertEqual([c["expertId"] for c in both["cards"]],
                             ["exp-firm", "exp-pub"])
            # 未授权 firm 卡：store_read/consult 都具名拒。
            with self.assertRaises(expert_store.ExpertStoreError) as cm:
                env.store.store_read({"expertId": "exp-firm"})
            self.assertEqual(str(cm.exception), "f100_scope_mismatch")
            with self.assertRaises(expert_store.ExpertStoreError) as cm:
                env.store.consult({"expertId": "exp-firm",
                                   "query": "许可 合同 条款"})
            self.assertEqual(str(cm.exception), "f100_scope_mismatch")
            # 授权后照常消费。
            hit = env.store.consult({"expertId": "exp-firm",
                                     "authorizedReadScopes": ["firm"],
                                     "query": "知识产权 许可 合同条款"})
            self.assertEqual(hit["hits"][0]["readScope"], "firm")

    def test_private_never_authorizable(self):
        with _Env() as env:
            env.store.define(card_args())
            with self.assertRaises(expert_store.ExpertStoreError) as cm:
                env.store.store_list({"authorizedReadScopes": ["private"]})
            self.assertEqual(
                str(cm.exception),
                "f100_scope_mismatch:private_never_authorizable")

    def test_consult_golden_hits_and_determinism(self):
        import copy
        with _Env() as env:
            env.store.define(card_args())
            first_hits = {}
            for tid, order in SYN_TOPICS.items():
                tid_order = list(SYN_TOPICS).index(tid)
                out = env.store.consult(
                    {"expertId": "exp-syn-1",
                     "query": order[1], "topK": 1})
                # 主题级 recall@1：top1 必须落在本主题条目集内（主题内 3
                # 条互为近重复，逐字条目号不作金标——F73 同口径）。
                self.assertIn(out["hits"][0]["itemRef"]["itemId"],
                              {"it-%d" % (tid_order * 3 + k) for k in (1, 2, 3)},
                              "主题 %s top1 越题" % tid)
                first_hits[tid] = out["hits"]
            # 两跑逐字节同分（零模型零随机）。
            second = expert_store.ExpertStore(env.holder.name)
            for tid in SYN_TOPICS:
                out = second.consult({"expertId": "exp-syn-1",
                                      "query": SYN_TOPICS[tid][1], "topK": 1})
                self.assertEqual(out["hits"], first_hits[tid])
            # 摘录确定性：满长正文截断带省略号，短文全文。
            self.assertTrue(all(len(h["excerpt"]) <=
                                expert_store.EXCERPT_CHARS + 1
                                for h in first_hits["t1"]))

    def test_out_of_scope_query_named_abstain(self):
        with _Env() as env:
            env.store.define(card_args())
            for query in ("天气预报 今天穿什么", "菜谱 红烧肉 做法",
                          "股票 行情 涨跌"):
                with self.assertRaises(expert_store.ExpertStoreError) as cm:
                    env.store.consult({"expertId": "exp-syn-1",
                                       "query": query})
                self.assertEqual(str(cm.exception),
                                 "f100_out_of_scope_abstain", query)
            # 弃答不落回执账（无消费即无回执）。
            self.assertFalse(env.store._consult_path
                             and Path(env.store._consult_path).exists())

    def test_verify_receipt_roundtrip_pass(self):
        with _Env() as env:
            env.store.define(card_args())
            out = env.store.consult({"expertId": "exp-syn-1",
                                     "query": SYN_TOPICS["t2"][1], "topK": 2})
            verdict = env.store.verify_receipt({"receiptId": out["receiptId"]})
            self.assertEqual(verdict["verdict"], "PASS")
            self.assertEqual(verdict["hitCount"], len(out["hits"]))
            self.assertEqual(verdict["cardDigest"], out["grounding"]["cardDigest"])
            for ref, hit in zip(verdict["items"], out["hits"]):
                self.assertEqual(ref, hit["itemRef"])

    def test_verify_receipt_tampered_log_named_refusal(self):
        with _Env() as env:
            env.store.define(card_args())
            out = env.store.consult({"expertId": "exp-syn-1",
                                     "query": SYN_TOPICS["t3"][1]})
            rid = out["receiptId"]
            self.assertEqual(env.store.verify_receipt(
                {"receiptId": rid})["verdict"], "PASS")
            # 篡改回执账一行（换 cardDigest 字段）→ receiptId 重算不符。
            path = Path(env.store._consult_path)
            lines = path.read_text(encoding="utf-8").splitlines()
            bad = json.loads(lines[0])
            bad["cardDigest"] = "0" * 64
            lines[0] = json.dumps(bad, ensure_ascii=False, sort_keys=True)
            path.write_text("\n".join(lines) + "\n", encoding="utf-8")
            with self.assertRaises(expert_store.ExpertStoreError) as cm:
                env.store.verify_receipt({"receiptId": rid})
            self.assertEqual(str(cm.exception), "f100_receipt_tampered")
            # 未知回执具名拒不假 PASS。
            with self.assertRaises(expert_store.ExpertStoreError) as cm:
                env.store.verify_receipt({"receiptId": "deadbeef"})
            self.assertEqual(str(cm.exception), "f100_receipt_not_found")

    def test_card_tamper_named_refusal_everywhere(self):
        with _Env() as env:
            env.store.define(card_args())
            out = env.store.consult({"expertId": "exp-syn-1",
                                     "query": SYN_TOPICS["t1"][1]})
            path = Path(env.store._cards_path)
            row = json.loads(path.read_text(encoding="utf-8").splitlines()[0])
            row["card"]["items"][0]["body"] += "篡改一字"
            path.write_text(json.dumps(row, ensure_ascii=False,
                                       sort_keys=True) + "\n",
                            encoding="utf-8")
            for call, kwargs in (
                    ("store_read", {"expertId": "exp-syn-1"}),
                    ("consult", {"expertId": "exp-syn-1",
                                 "query": SYN_TOPICS["t1"][1]})):
                with self.assertRaises(expert_store.ExpertStoreError) as cm:
                    getattr(env.store, call)(kwargs)
                self.assertEqual(str(cm.exception),
                                 "f100_card_digest_mismatch", call)
            with self.assertRaises(expert_store.ExpertStoreError) as cm:
                env.store.verify_receipt({"receiptId": out["receiptId"]})
            self.assertEqual(
                str(cm.exception),
                "f100_receipt_verify_failed:card_digest_drift")

    def test_unconfigured_root_fails_closed(self):
        with self.assertRaises(expert_store.ExpertStoreError) as cm:
            expert_store.ExpertStore(None)
        self.assertEqual(str(cm.exception), "f100_state_root_not_configured")
        with self.assertRaises(expert_store.ExpertStoreError) as cm:
            expert_store.expert_call("expert.store_list", {}, {})
        self.assertEqual(
            str(cm.exception), "f100_state_root_not_configured")

    def test_non_expert_method_stays_not_connected(self):
        with _Env() as env:
            with self.assertRaises(expert_store.ExpertStoreError) as cm:
                expert_store.expert_call("expert.vanish", {},
                                         env.config)
            self.assertTrue(str(cm.exception).startswith(
                "f100_method_not_in_frozen_list:"))
        with self.assertRaises(legal_entry.NotConnected):
            legal_entry.call("persona.summon", {}, {})
        with self.assertRaises(legal_entry.NotConnected):
            legal_entry.call("observer.start", {}, {})

    def test_in_process_roundtrip_via_bridge(self):
        with _Env() as env:
            defined = legal_entry.call("expert.define", card_args(),
                                       env.config)
            self.assertEqual(defined["cardScope"], "public")
            read = legal_entry.call("expert.store_read",
                                    {"expertId": "exp-syn-1"}, env.config)
            # 客端 canonical 重算卡片 hash 逐字相等（store_read 元数据面
            # 自足可验——货架不携正文但仍绑定快照 hash）。
            self.assertEqual(read["cardRef"]["digest"],
                             defined["cardDigest"])
            consulted = legal_entry.call(
                "expert.consult",
                {"expertId": "exp-syn-1", "query": SYN_TOPICS["t4"][1]},
                env.config)
            # 不冒真人实时意见声明恒携（acceptance 第二分句逐字面）。
            self.assertIs(consulted["nonLive"]["declaresRealTime"], False)
            self.assertIn("不代表任何真人的实时意见",
                          consulted["nonLive"]["statement"])
            self.assertEqual(consulted["grounding"]["kind"], "pinned_pack")
            verdict = legal_entry.call("expert.verify_receipt",
                                       {"receiptId": consulted["receiptId"]},
                                       env.config)
            self.assertEqual(verdict["verdict"], "PASS")
            # 来源回执可回溯：命中 sourceRefs 携合成源 digest（数据原样）。
            self.assertTrue(all(h["sourceRefs"] for h in consulted["hits"]))


if __name__ == "__main__":
    unittest.main()

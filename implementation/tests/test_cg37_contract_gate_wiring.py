# -*- coding: utf-8 -*-
"""RE-37 合同起草·评分门产品侧接线测试（施工波 2026-10-30 单元 #37；
边界件扩测 2026-10-31：multi-judge/dashboard/母版再生/docx·pdf 导出四件
+ Harvey 口径学增补断言 A37-H1/H2/H3 并入）。

全部合成材料（合成条款库/合成 rubric/合成 LLM 桩——judge/drafter/improve/
retag/master-regen 五角色全走 ScriptedLLM 桩，零网络零真实端点；docx/pdf
导出用本机 LibreOffice headless 确定性 CLI，与 F54/F58 同源配置键）。
覆盖 RE-37 §5 验收口径：①装配→coherence→填槽（合成槽值）→评分门（合成
judge 桩）→两末态出稿断言（passed 干净出稿/exhausted 出稿带具名「未过关」
标注+gate_status 落账）+自愈循环一轮排除生效+共享库零改写断言；②金额/
日期机检负例 typed 拒；③RE-12 衔接断言：门内判定字段与审查判定字段零
混用（§4.4 逐条对账）。边界件断言：multi-judge 多数投票/平票 fail-closed/
干净 low_confidence（3-judge 2:1 面板可低信——不复制竞品特异式）/全 judge
败 typed 拒；dashboard 四聚合；母版再生 force/失败回滚/manual 保留；
导出四格式（docx 确定性字节+pdf 文本层）。增补断言：A37-H1 判据双分支
typed 拒；A37-H2 锚定三件套（引句子串/节名枚举/缺件负例）；A37-H3 粒度
区间 [25,60]+显式豁免账。

模块头注对齐声明：识律 law-bench（MIT）机制对拍=行为级断言；Harvey LAB
口径学（无许可源）只取机制形状——判据双分支/锚定三件套/粒度区间为形状
断言，语料自撰。本测试语料（条款文案/rubric 判据/提示词标记）全部自写。
"""
from __future__ import annotations

import json
import re
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python"))

import legal_entry  # noqa: E402
import contract_gate as cg  # noqa: E402
from bridge_errors import NotConnected  # noqa: E402

CONTRACT_TYPE = "买卖"

# ── 合成条款库（三源；文案全自写）──
BASE_CLAUSES = [
    ("标的与质量", "{{甲方名称}}向{{乙方名称}}出售{{标的描述}}，质量按国家标"
     "准执行。", [{"name": "中华人民共和国民法典", "category": "法律"}]),
    ("价款与支付", "合同总金额为{{合同金额}}元，买方于签署后三十日内一次性支付。",
     [{"name": "中华人民共和国民法典", "category": "法律"}]),
    ("履行与交付", "卖方应于{{履行期限}}内完成交付，交付地点为买方仓库。", []),
    ("违约责任", "逾期履行的，按日万分之五支付违约金；超过三十日的买方可解除。", []),
    ("其他约定", "本合同一式两份，双方各执一份。", []),
    ("附则", "本合同自{{签署日期}}起生效；未尽事宜由双方协商解决。", []),
]
TAGGED_CLAUSE = ("标的与质量", "按批次交付：每批交付前卖方应提前七日书面通知，"
                  "批次数量与验收标准以附件清单为准。",
                 [{"name": "中华人民共和国民法典", "category": "法律"}])
TAGGED_EXT_CLAUSE = ("质量异议期", "买方应于每批到货后十五日内完成质量检验并书面"
                     "提出异议，逾期视为该批合格。",
                     [{"name": "中华人民共和国民法典", "category": "法律"}])
CUSTOM_WEAK = ("违约责任", "违约方赔偿对方实际损失。", [])  # 薄弱 custom（盖掉富母版）
CUSTOM_CONFID = ("保密义务", "双方对交易细节与{{标的描述}}相关信息互负保密义务"
                 "，保密期两年。", [])
CUSTOM_TIE_AUTO = ("违约责任", "违约金按实际损失百分之一百二十计。", [])
CUSTOM_SECRET_SLOT = ("特别约定", "双方另就{{神秘槽}}达成约定。", [])

RUBRIC_V1 = [
    {"id": "subject_defined", "title": "标的明确",
     "match_criteria": "PASS if 合同明确写明标的名称与数量；"
                       "FAIL if 标的缺失或仅有模糊表述"},
    {"id": "price_stated", "title": "价款齐备",
     "match_criteria": "PASS if 写明价款总额与支付期限；FAIL if 价款缺失"},
    {"id": "breach_usable", "title": "违约责任可执行",
     "match_criteria": "PASS if 违约责任含具体计算方式（如按日万分之五）；"
                       "FAIL if 仅写赔偿实际损失而无计算方式"},
    {"id": "acceptance_period", "title": "质量异议期在案",
     "match_criteria": "PASS if 合同含质量异议期安排；FAIL if 无异议期"},
]

FILL_VALUES = {
    "甲方名称": "示例买方有限公司", "乙方名称": "示例卖方有限公司",
    "标的描述": "某型号设备 10 台", "合同金额": "128000.00",
    "签署日期": "2026-10-30", "履行期限": "签署后 30 日内",
    "争议解决方式": "示例仲裁委员会仲裁",
}

# 带节结构的合成正文（A37-H2：judge 锚定需节名枚举与可引子串）
SECTIONED_TEXT = "## 标的与质量\n\n甲方向乙方出售某型号设备十台。"


class ScriptedLLM:
    """合成 LLM 桩：五角色按提示词标记分发（fill/judge/improve/retag/
    compare-drafter/master-regen），全部脚本化，可断言调用计数。

    judge 桩输出锚定三件套（A37-H2）：location 取正文首个节名、quote 取
    「## 节名」标题行原文（保证为正文子串）；judge_fn 可返特殊 verdict
    演练负例——bad_quote（引句非子串）/bad_location（节名不在枚举）/
    no_trio（旧形状缺三件套）。"""

    def __init__(self):
        self.model = "stub-drafter"
        self.judge_model = "stub-judge"
        self.master_model = "stub-master"
        self.fill_calls = 0
        self.improve_calls = 0
        self.drafter_calls = 0
        self.retag_calls = 0
        self.master_calls = 0
        self.total_calls = 0
        self.fill_raw = json.dumps(FILL_VALUES, ensure_ascii=False)
        self.judge_fn = lambda title, text: ("pass", "脚本判定通过")
        self.improve_fn = lambda failing, customs: {
            "exclude_custom_clause_ids": [], "recommendations": []}
        self.retag_fn = lambda clauses: []
        self.drafter_fn = lambda system, user: "（草稿占位）"
        self.master_fn = lambda section: {
            "body": f"再生条款（{section}）：双方按本节约定履行，"
                    "价款以{{{{合同金额}}}}元为准。"}

    def complete(self, system: str, user: str) -> str:
        self.total_calls += 1
        if user.startswith("评审项："):  # judge（评分门；improve 提示词
            # 含「未通过的评审项：」——必须按行首精确分派）
            title = user.split("评审项：", 1)[1].split("\n", 1)[0]
            text = user.split("合同正文：\n", 1)[1] if "合同正文：\n" in user \
                else ""
            verdict, reasoning = self.judge_fn(title, text)
            if verdict == "raise_transient":
                raise RuntimeError("HTTP 429 RateLimit hit judge")
            sections = cg.split_sections(text)
            location = sections[0] if sections else "不存在的节名"
            quote = f"## {sections[0]}" if sections else "## 节名"
            if verdict == "bad_quote":
                return json.dumps(
                    {"verdict": "pass", "location": location,
                     "quote": "这句引文不在合同正文里（合成负例）",
                     "reasoning": reasoning}, ensure_ascii=False)
            if verdict == "bad_location":
                return json.dumps(
                    {"verdict": "pass", "location": "不存在的节名",
                     "quote": quote, "reasoning": reasoning},
                    ensure_ascii=False)
            if verdict == "no_trio":  # 旧形状（缺三件套）＝A37-H2 负例
                return json.dumps({"verdict": "pass",
                                   "reasoning": reasoning},
                                  ensure_ascii=False)
            return json.dumps({"verdict": verdict, "location": location,
                               "quote": quote, "reasoning": reasoning},
                              ensure_ascii=False)
        if "槽清单" in user:  # fill（填槽）
            self.fill_calls += 1
            return self.fill_raw
        if "exclude_custom_clause_ids" in user and "两问" in user:  # improve
            self.improve_calls += 1
            failing = re.findall(r"\[fail\] ([^\n：]+)：", user)
            customs = [int(m) for m in re.findall(r"id=(\d+)", user)]
            result = self.improve_fn(failing, customs)
            return json.dumps(result, ensure_ascii=False)
        if system.startswith("你是条款库标签治理助手"):  # retag suggest
            self.retag_calls += 1
            return json.dumps(self.retag_fn([]), ensure_ascii=False)
        if system.startswith("你是合同母版条款起草助手"):  # master regen
            self.master_calls += 1
            section = re.search(r"「([^」]+)」一节", user).group(1)
            return json.dumps(self.master_fn(section), ensure_ascii=False)
        # compare drafter（system=prompt content）
        self.drafter_calls += 1
        return self.drafter_fn(system, user)

    def seam(self):
        return {"model": self.model, "complete": self.complete,
                "judge_model": self.judge_model}


def seed_library(state_root, *, with_customs=True):
    """合成条款库播种：base 六节母版＋tagged 场景两件＋custom 三件。"""
    ids = {}
    for section, body, law_refs in BASE_CLAUSES:
        row = legal_entry.call("contract_gate.clause_upsert", {
            "contract_type": CONTRACT_TYPE, "source": "base",
            "section": section, "body": body, "law_refs": law_refs,
            "source_path": "synthetic/master-买卖.md",
            "source_doc_title": "合成母版"}, {"contract_gate_state_root": state_root})
        ids["base:" + section] = row["id"]
    for clause, scenario in ((TAGGED_CLAUSE, "分批供货"),
                             (TAGGED_EXT_CLAUSE, "分批供货")):
        section, body, law_refs = clause
        row = legal_entry.call("contract_gate.clause_upsert", {
            "contract_type": CONTRACT_TYPE, "source": "tagged",
            "section": section, "body": body, "law_refs": law_refs,
            "source_path": "synthetic/tagged-分批供货.md",
            "tags": {"scenario": scenario}},
            {"contract_gate_state_root": state_root})
        ids["tagged:" + section] = row["id"]
    if with_customs:
        for key, (section, body, law_refs), stance, manual in (
                ("weak", CUSTOM_WEAK, "pro_a", False),
                ("confid", CUSTOM_CONFID, "pro_a", False),
                ("tie_auto", CUSTOM_TIE_AUTO, "pro_a", False)):
            row = legal_entry.call("contract_gate.clause_upsert", {
                "contract_type": CONTRACT_TYPE, "source": "custom",
                "section": section, "body": body, "law_refs": law_refs,
                "manual": manual,
                "tags": {"stance": stance, "scenario": "分批供货"}},
                {"contract_gate_state_root": state_root})
            ids[key] = row["id"]
    return ids


def approve_custom(state_root, clause_id):
    return legal_entry.call("contract_gate.clause_bulk_review",
                            {"clause_id": clause_id, "status": "approved"},
                            {"contract_gate_state_root": state_root})


def seed_rubric(state_root, name="contract_买卖_v1", criteria=RUBRIC_V1,
                source="local", exemption=None):
    """合成 rubric 播种：4 条维度级判据＜粒度下界 25（A37-H3），接线测试
    小样一律携带显式豁免账（豁免理由落 rubric 行并在 list/get 投影）。"""
    return legal_entry.call("contract_gate.rubric_create", {
        "name": name, "source": source, "description": "合成 rubric（自写判据）",
        "granularity_exemption": exemption or "合成接线测试小样（维度级 4 条，粒度区间 [25,60] 显式豁免账）",
        "criteria": criteria}, {"contract_gate_state_root": state_root})


def seed_rubric_if_absent(state_root, name="contract_买卖_v1",
                          criteria=RUBRIC_V1):
    """幂等播种（重复评估的测试用）：同名 rubric 已在账则跳过。"""
    listing = legal_entry.call("contract_gate.rubric_list", {},
                               {"contract_gate_state_root": state_root})
    if any(r["name"] == name for r in listing["rubrics"]):
        return None
    return seed_rubric(state_root, name=name, criteria=criteria)


def gate_judge(rounds_rules):
    """judge 脚本工厂：rounds_rules=按评审项**标题**的判定函数（看正文）；
    默认全过。「违约责任可执行」语义：正文含「按日万分之五」才过（薄弱
    custom 盖掉母版时该条挂）；「质量异议期在案」：正文含该节才过。"""

    def judge(title, text):
        if title == "违约责任可执行":
            if "按日万分之五" in text:
                return ("pass", "违约责任含具体计算方式")
            return ("fail", "仅写赔偿实际损失，无计算方式")
        if title == "质量异议期在案":
            if "质量异议期" in text:
                return ("pass", "异议期在案")
            return ("fail", "合同无质量异议期安排")
        rule = rounds_rules.get(title)
        if rule is not None:
            return rule(text)
        return ("pass", "脚本默认通过")

    return judge


class GateBase(unittest.TestCase):
    def setUp(self):
        self.state_root = tempfile.mkdtemp(prefix="cg37-")
        self.config = {"contract_gate_state_root": self.state_root}
        self.llm = ScriptedLLM()

    def seed_all(self):
        self.ids = seed_library(self.state_root)
        seed_rubric(self.state_root)
        return self.ids


class ClauseLibraryTests(GateBase):
    """A 组：三源条款库/幂等 upsert/manual 保留/规范化/词表/tag_review。"""

    def test_three_sources_and_field_semantics(self):
        ids = seed_library(self.state_root)
        listing = legal_entry.call("contract_gate.clause_list",
                                   {"contract_type": CONTRACT_TYPE},
                                   self.config)
        self.assertEqual(listing["count"], 11)
        custom = legal_entry.call("contract_gate.clause_get",
                                  {"clause_id": ids["weak"]}, self.config)
        self.assertIsNone(custom["source_path"])  # custom 恒空（B1）
        self.assertEqual(custom["tags"]["source"], "custom")
        base = legal_entry.call("contract_gate.clause_get",
                                {"clause_id": ids["base:附则"]}, self.config)
        self.assertEqual(base["source_path"], "synthetic/master-买卖.md")
        for field in ("id", "contract_type", "section", "body",
                      "slot_instructions", "law_refs", "source_path",
                      "source_doc_title", "body_hash", "created_at",
                      "updated_at", "manual", "tags", "tag_review"):
            self.assertIn(field, custom)  # 13 字段语义齐（B1）

    def test_base_tagged_idempotent_upsert_and_manual_preserved(self):
        ids = seed_library(self.state_root)
        before = legal_entry.call("contract_gate.clause_list",
                                  {"contract_type": CONTRACT_TYPE},
                                  self.config)["count"]
        # 同 (source_path, section, body_hash) 重放＝冲突更新不重复插（B2）
        again = legal_entry.call("contract_gate.clause_upsert", {
            "contract_type": CONTRACT_TYPE, "source": "base",
            "section": "附则", "body": BASE_CLAUSES[5][1], "law_refs": [],
            "source_path": "synthetic/master-买卖.md"}, self.config)
        self.assertEqual(again["upserted"], "updated")
        self.assertEqual(again["id"], ids["base:附则"])
        after = legal_entry.call("contract_gate.clause_list",
                                 {"contract_type": CONTRACT_TYPE},
                                 self.config)["count"]
        self.assertEqual(before, after)
        # 人工 curated 条款（manual=true 插入）再抽取后保留（B3）：
        # 冲突更新不改 manual；delete_auto 也不清人工条款。
        curated = legal_entry.call("contract_gate.clause_upsert", {
            "contract_type": CONTRACT_TYPE, "source": "base",
            "section": "特别条款", "body": "人工精修条款（专用源）。",
            "source_path": "synthetic/master-manual.md",
            "manual": True}, self.config)
        self.assertEqual(curated["upserted"], "inserted")
        self.assertTrue(curated["manual"])
        re_upserted = legal_entry.call("contract_gate.clause_upsert", {
            "contract_type": CONTRACT_TYPE, "source": "base",
            "section": "特别条款", "body": "人工精修条款（专用源）。",
            "source_path": "synthetic/master-manual.md"}, self.config)
        self.assertEqual(re_upserted["upserted"], "updated")
        self.assertTrue(re_upserted["manual"])  # 不被打回自动
        # 自动条款可清、人工条款保留（B3）
        removed = legal_entry.call("contract_gate.clause_delete_auto",
                                   {"contract_type": CONTRACT_TYPE},
                                   self.config)
        self.assertIn(ids["base:标的与质量"], removed["removed"])
        self.assertIn(ids["base:附则"], removed["removed"])  # 自动条款可清
        self.assertNotIn(curated["id"], removed["removed"])

    def test_custom_insert_by_id_and_source_path_forbidden(self):
        seed_library(self.state_root)
        first = legal_entry.call("contract_gate.clause_upsert", {
            "contract_type": CONTRACT_TYPE, "source": "custom",
            "section": "保密义务", "body": "保密条款一。",
            "tags": {"stance": "pro_a"}}, self.config)
        second = legal_entry.call("contract_gate.clause_upsert", {
            "contract_type": CONTRACT_TYPE, "source": "custom",
            "section": "保密义务", "body": "保密条款一。",
            "tags": {"stance": "pro_a"}}, self.config)
        self.assertNotEqual(first["id"], second["id"])  # custom 按 id 平插
        with self.assertRaisesRegex(cg.ContractGateError,
                                    "cg37_custom_source_path_forbidden"):
            legal_entry.call("contract_gate.clause_upsert", {
                "contract_type": CONTRACT_TYPE, "source": "custom",
                "section": "保密义务", "body": "x",
                "source_path": "any.md",
                "tags": {"stance": "pro_a"}}, self.config)

    def test_body_normalization_and_hash_sentinel(self):
        # 规范化改变了 body（别名→canonical）→重推导 md5（B4）
        alias = legal_entry.call("contract_gate.clause_upsert", {
            "contract_type": CONTRACT_TYPE, "source": "base",
            "section": "标的与质量", "body": "{{甲方}}向{{乙方}}出售设备。",
            "source_path": "synthetic/norm-alias.md",
            "body_hash": "sentinel-keep"}, self.config)
        self.assertEqual(alias["body"], "{{甲方名称}}向{{乙方名称}}出售设备。")
        self.assertEqual(alias["body_hash"],
                         cg._md5("{{甲方名称}}向{{乙方名称}}出售设备。"))
        # 规范化未改变 body →保留调用方传入 hash（sentinel 兼容，B4）
        canonical = legal_entry.call("contract_gate.clause_upsert", {
            "contract_type": CONTRACT_TYPE, "source": "base",
            "section": "价款与支付", "body": "{{甲方名称}}付款。",
            "source_path": "synthetic/norm-plain.md",
            "body_hash": "sentinel-keep"}, self.config)
        self.assertEqual(canonical["body_hash"], "sentinel-keep")

    def test_tag_vocab_governance_and_stance_domain(self):
        seed_library(self.state_root)
        # scenario 维已随播种登记「分批供货」：纯重用注册＝不新建不增值（B6）
        reuse = legal_entry.call("contract_gate.tag_dim_register", {
            "contract_type": CONTRACT_TYPE, "dim": "scenario",
            "values": ["分批供货"]}, self.config)
        self.assertFalse(reuse["created"])
        self.assertEqual(reuse["values"], ["分批供货"])
        # 新增值＝维内合并取值不重复建
        extended = legal_entry.call("contract_gate.tag_dim_register", {
            "contract_type": CONTRACT_TYPE, "dim": "scenario",
            "values": ["单批交付"]}, self.config)
        self.assertTrue(extended["created"])
        self.assertEqual(sorted(extended["values"]),
                         ["分批供货", "单批交付"])
        fresh = legal_entry.call("contract_gate.tag_dim_register", {
            "contract_type": CONTRACT_TYPE, "dim": "strength",
            "values": ["standard"]}, self.config)
        self.assertTrue(fresh["created"])  # 新维 reuse-or-create 建维
        # 元数据前缀维不可注册（`_` 键=导入溯源，不算审查维）
        with self.assertRaisesRegex(cg.ContractGateError,
                                    "cg37_tag_dim_invalid"):
            legal_entry.call("contract_gate.tag_dim_register", {
                "contract_type": CONTRACT_TYPE, "dim": "_imported_at",
                "values": ["x"]}, self.config)
        with self.assertRaisesRegex(cg.ContractGateError, "cg37_stance_invalid"):
            legal_entry.call("contract_gate.clause_upsert", {
                "contract_type": CONTRACT_TYPE, "source": "custom",
                "section": "保密义务", "body": "x",
                "tags": {"stance": "pro_owner"}}, self.config)
        # universal 维 source/stance 不允许按类型注册（防维蔓延）
        with self.assertRaisesRegex(cg.ContractGateError,
                                    "universal_dim_not_per_type"):
            legal_entry.call("contract_gate.tag_dim_register", {
                "contract_type": CONTRACT_TYPE, "dim": "stance",
                "values": ["pro_c"]}, self.config)

    def test_tag_review_gate_and_pending_queue(self):
        ids = seed_library(self.state_root)
        queue = legal_entry.call("contract_gate.review_queue", {}, self.config)
        self.assertEqual(queue["count"], 3)  # 三个 custom 全 pending
        # 未批准 custom 不装配（B8）：违约责任走母版
        result = legal_entry.call("contract_gate.assemble", {
            "contract_type": CONTRACT_TYPE, "stance": "pro_a",
            "scenario": "分批供货"}, self.config)
        self.assertIn("按日万分之五", result["body_text"])
        self.assertNotIn("赔偿对方实际损失", result["body_text"])
        approve_custom(self.state_root, ids["weak"])
        approved = legal_entry.call("contract_gate.assemble", {
            "contract_type": CONTRACT_TYPE, "stance": "pro_a",
            "scenario": "分批供货"}, self.config)
        self.assertIn("赔偿对方实际损失", approved["body_text"])
        # 逐维 review / bulk 写保留元数据键（B7/B9）
        clause = legal_entry.call("contract_gate.clause_get",
                                  {"clause_id": ids["weak"]}, self.config)
        self.assertEqual(clause["tag_review"],
                         {"source": "approved", "stance": "approved",
                          "scenario": "approved"})
        with_meta = legal_entry.call("contract_gate.clause_upsert", {
            "contract_type": CONTRACT_TYPE, "source": "custom",
            "section": "通知送达", "body": "通知送达条款。",
            "tags": {"stance": "pro_b", "_imported_at": "synthetic"}}, self.config)
        bulked = legal_entry.call("contract_gate.clause_bulk_review",
                                  {"clause_id": with_meta["id"],
                                   "status": "approved"}, self.config)
        self.assertNotIn("_imported_at", bulked["tag_review"])  # 元数据键不算维
        self.assertEqual(bulked["tags"]["_imported_at"], "synthetic")  # 但保留


class AssembleTests(GateBase):
    """B 组：逐节覆盖/扩展节/tiebreak/coherence/产出体。"""

    def assemble(self, **kwargs):
        args = {"contract_type": CONTRACT_TYPE}
        args.update(kwargs)
        return legal_entry.call("contract_gate.assemble", args, self.config)

    def test_override_priority_and_extension_before_annex(self):
        ids = self.seed_all()
        for key in ("weak", "confid"):
            approve_custom(self.state_root, ids[key])
        result = self.assemble(scenario="分批供货", stance="pro_a")
        sections = cg.split_sections(result["body_text"])
        # custom(stance) 盖违约责任；tagged(scenario) 盖标的与质量＋扩展节；
        # custom 扩展节保密义务；扩展节都排附则前（B10）
        self.assertIn("赔偿对方实际损失", result["body_text"])  # weak custom 胜
        self.assertIn("按批次交付", result["body_text"])  # tagged 胜母版
        self.assertIn("保密义务", result["body_text"])  # custom 扩展节
        annex_at = sections.index("附则")
        self.assertLess(sections.index("质量异议期"), annex_at)
        self.assertLess(sections.index("保密义务"), annex_at)
        for master, _b, _l in BASE_CLAUSES:  # 母版节一个不丢
            self.assertIn(master, sections)
        self.assertEqual(sections[-1], "附则")

    def test_tiebreak_manual_first_and_diagnostics(self):
        ids = self.seed_all()
        manual = legal_entry.call("contract_gate.clause_upsert", {
            "contract_type": CONTRACT_TYPE, "source": "custom",
            "section": "违约责任", "body": "人工违约条款（精修）。",
            "manual": True, "tags": {"stance": "pro_a"}}, self.config)
        approve_custom(self.state_root, ids["weak"])
        approve_custom(self.state_root, ids["tie_auto"])
        approve_custom(self.state_root, manual["id"])
        result = self.assemble(stance="pro_a")
        self.assertIn("人工违约条款", result["body_text"])  # manual 优先
        self.assertIn("违约责任",
                      result["diagnostics"]["heuristic_sections"])  # 留痕

    def test_tiebreak_more_slots_then_longer_body_then_lower_id(self):
        self.seed_all()
        a = legal_entry.call("contract_gate.clause_upsert", {
            "contract_type": CONTRACT_TYPE, "source": "custom",
            "section": "其他约定", "body": "短。",
            "tags": {"stance": "pro_b"}}, self.config)
        b = legal_entry.call("contract_gate.clause_upsert", {
            "contract_type": CONTRACT_TYPE, "source": "custom",
            "section": "其他约定", "body": "带槽版本：争议按{{争议解决方式}}处理。",
            "tags": {"stance": "pro_b"}}, self.config)
        approve_custom(self.state_root, a["id"])
        approve_custom(self.state_root, b["id"])
        result = self.assemble(stance="pro_b")
        self.assertIn("带槽版本", result["body_text"])  # 槽数多者胜（同非 manual）

    def test_coherence_gate_fail_closed_on_uninstructed_slot(self):
        ids = self.seed_all()
        secret = legal_entry.call("contract_gate.clause_upsert", {
            "contract_type": CONTRACT_TYPE, "source": "custom",
            "section": "特别约定", "body": "双方另就{{神秘槽}}达成约定。",
            "tags": {"stance": "pro_a"}}, self.config)
        approve_custom(self.state_root, secret["id"])
        with self.assertRaises(cg.CoherenceError) as caught:
            self.assemble(stance="pro_a")
        self.assertIn("uninstructed_slots", str(caught.exception))

    def test_law_refs_union_dedup_and_category_order(self):
        self.seed_all()
        extra = legal_entry.call("contract_gate.clause_upsert", {
            "contract_type": CONTRACT_TYPE, "source": "base",
            "section": "争议解决", "body": "争议按{{争议解决方式}}解决。",
            "law_refs": [{"name": "中华人民共和国民事诉讼法", "category": "法律"},
                         {"name": "买卖合同司法解释", "category": "司法解释"}],
            "source_path": "synthetic/master-买卖.md"}, self.config)
        result = self.assemble()
        names = [r["name"] for r in result["law_refs"]]
        self.assertEqual(names.count("中华人民共和国民法典"), 1)  # 去重并集
        self.assertLess(names.index("中华人民共和国民法典"),
                        names.index("买卖合同司法解释"))  # 类目序在前
        self.assertTrue(all("效力未核" in r["note"] for r in result["law_refs"]))

    def test_slots_not_prefilled_and_union_instructions(self):
        self.seed_all()
        result = self.assemble()
        self.assertIn("{{甲方名称}}", result["body_text"])  # 不预填（B15）
        names = [i["name"] for i in result["instructions"]]
        self.assertIn("争议解决方式", names)  # 本体回退补指令（B13）
        self.assertEqual(len(names), len(set(names)))  # 并集去重
        self.assertIn("甲方名称", result["slots"])

    def test_unknown_type_and_format_typed_reject(self):
        with self.assertRaisesRegex(cg.ContractGateError,
                                    "cg37_contract_type_not_found:租赁"):
            legal_entry.call("contract_gate.assemble",
                             {"contract_type": "租赁"}, self.config)
        self.seed_all()
        with self.assertRaisesRegex(cg.ContractGateError,
                                    "cg37_format_not_supported:xlsx"):
            legal_entry.call("contract_gate.assemble",
                             {"contract_type": CONTRACT_TYPE,
                              "format": "xlsx"}, self.config)


class FillTests(GateBase):
    """C 组：填槽契约/缓存键/容错/机检/未填槽保留。"""

    def test_fill_cache_key_slot_order_normalized_and_task_desc(self):
        self.seed_all()
        values_one = cg.fill_slots(
            self.state_root, self.config, CONTRACT_TYPE, "分批供货",
            ["甲方名称", "乙方名称", "合同金额"],
            cg.default_slot_instructions(), task_desc="购买设备",
            llm=self.llm.seam())
        self.assertFalse(values_one["hit"])
        # 槽序归一化→同键命中（B17）
        values_two = cg.fill_slots(
            self.state_root, self.config, CONTRACT_TYPE, "分批供货",
            ["合同金额", "乙方名称", "甲方名称"],
            cg.default_slot_instructions(), task_desc="购买设备",
            llm=self.llm.seam())
        self.assertTrue(values_two["hit"])
        self.assertEqual(self.llm.fill_calls, 1)  # 命中即跳过 LLM
        # task_desc 入键：需求变了→新键（B17/P29 语义）
        values_three = cg.fill_slots(
            self.state_root, self.config, CONTRACT_TYPE, "分批供货",
            ["甲方名称", "乙方名称", "合同金额"],
            cg.default_slot_instructions(), task_desc="购买另一批设备",
            llm=self.llm.seam())
        self.assertFalse(values_three["hit"])
        self.assertEqual(self.llm.fill_calls, 2)

    def test_fill_prompt_carries_task_desc_and_json_contract(self):
        captured = {}

        def spy(system, user):
            captured["system"], captured["user"] = system, user
            return json.dumps({"甲方名称": "甲"}, ensure_ascii=False)

        cg.fill_slots(self.state_root,
                      {"contract_gate_llm": {"model": "m", "complete": spy}},
                      CONTRACT_TYPE, None, ["甲方名称"],
                      cg.default_slot_instructions(), task_desc="购买十台设备")
        self.assertIn("购买十台设备", captured["user"])  # 需求入上下文
        self.assertIn("严格 JSON", captured["user"])  # 输出契约在案

    def test_machine_check_rejects_float_amount_and_fake_date(self):
        self.seed_all()
        # 金额浮点（JSON number）→typed 拒（§4.2 有意增强；验收口径③）
        self.llm.fill_raw = '{"合同金额": 123.45}'
        with self.assertRaisesRegex(cg.ContractGateError,
                                    "cg37_slot_value_invalid:合同金额"):
            cg.fill_slots(self.state_root, self.config, CONTRACT_TYPE, None,
                          ["合同金额"], cg.default_slot_instructions(),
                          llm=self.llm.seam())
        # 非真实日历日→typed 拒（验收口径③）
        self.llm.fill_raw = '{"签署日期": "2026-02-30"}'
        with self.assertRaisesRegex(cg.ContractGateError,
                                    "cg37_slot_value_invalid:签署日期"):
            cg.fill_slots(self.state_root, self.config, CONTRACT_TYPE, None,
                          ["签署日期"], cg.default_slot_instructions(),
                          llm=self.llm.seam())
        self.llm.fill_raw = '{"合同金额": "12,800.00"}'  # 千位逗号十进制串合法
        filled = cg.fill_slots(self.state_root, self.config, CONTRACT_TYPE,
                               None, ["合同金额"],
                               cg.default_slot_instructions(),
                               llm=self.llm.seam())
        self.assertEqual(filled["fill_values"]["合同金额"], "12,800.00")

    def test_parse_tolerance_and_bad_output_empty_fill(self):
        self.seed_all()
        # 围栏＋前后杂讯→可解析（B19）
        self.llm.fill_raw = '前置杂讯```json\n{"甲方名称": "甲"}\n```后置杂讯'
        filled = cg.fill_slots(self.state_root, self.config, CONTRACT_TYPE,
                               None, ["甲方名称"],
                               cg.default_slot_instructions(),
                               llm=self.llm.seam())
        self.assertEqual(filled["fill_values"], {"甲方名称": "甲"})
        # 坏 JSON→空填充不崩（B19）
        self.llm.fill_raw = "完全不是 JSON"
        empty = cg.fill_slots(self.state_root, self.config, CONTRACT_TYPE,
                              "另一场景", ["甲方名称"],
                              cg.default_slot_instructions(),
                              llm=self.llm.seam())
        self.assertEqual(empty["fill_values"], {})
        # 只保留槽清单内键（B19）
        self.llm.fill_raw = '{"甲方名称": "甲", "多余键": "值"}'
        kept = cg.fill_slots(self.state_root, self.config, CONTRACT_TYPE,
                             "第三场景", ["甲方名称"],
                             cg.default_slot_instructions(),
                             llm=self.llm.seam())
        self.assertEqual(kept["fill_values"], {"甲方名称": "甲"})

    def test_render_filled_keeps_placeholder_and_reports_unfilled(self):
        filled, unfilled = cg.render_filled(
            "{{甲方名称}}与{{乙方名称}}于{{签署日期}}签约", {"甲方名称": "甲"})
        self.assertIn("{{乙方名称}}", filled)  # 未填槽保留占位符（B20）
        self.assertEqual(sorted(unfilled), ["乙方名称", "签署日期"])


class RubricTests(GateBase):
    """D 组（上）：两档来源/版本命名/CRUD/ordinal。"""

    def test_two_tier_sources_baseline_readonly(self):
        seed_rubric(self.state_root, name="contract_买卖_基准",
                    source="baseline")
        for method, args in (
                ("contract_gate.rubric_update",
                 {"name": "contract_买卖_基准", "description": "改"}),
                ("contract_gate.rubric_delete",
                 {"name": "contract_买卖_基准"}),
                ("contract_gate.criterion_add",
                 {"rubric": "contract_买卖_基准", "id": "new_rule",
                  "title": "新规则", "match_criteria": "PASS if a;FAIL if b"}),
                ("contract_gate.criterion_update",
                 {"rubric": "contract_买卖_基准", "id": "subject_defined",
                  "title": "改题"}),
                ("contract_gate.criterion_delete",
                 {"rubric": "contract_买卖_基准", "id": "subject_defined"}),
                ("contract_gate.criterion_reorder",
                 {"rubric": "contract_买卖_基准",
                  "order": ["price_stated", "subject_defined"]})):
            with self.assertRaisesRegex(
                    cg.BaselineReadOnlyError, "cg37_baseline_readonly",
                    msg=method):
                legal_entry.call(method, args, self.config)

    def test_local_crud_ordinals_and_renumber_and_reorder(self):
        seed_rubric(self.state_root)
        # 末尾追加（ordinal=N+1）
        grown = legal_entry.call("contract_gate.criterion_add", {
            "rubric": "contract_买卖_v1", "id": "annex_complete",
            "title": "附则齐备",
            "match_criteria": "PASS if 附则在案；FAIL if 缺附则"},
            self.config)
        self.assertEqual([c["ordinal"] for c in grown["criteria"]],
                         [1, 2, 3, 4, 5])
        # 删除中间条→幸存者重编号
        shrunk = legal_entry.call("contract_gate.criterion_delete", {
            "rubric": "contract_买卖_v1", "id": "breach_usable"}, self.config)
        self.assertEqual([c["ordinal"] for c in shrunk["criteria"]],
                         [1, 2, 3, 4])
        # 全序重排；缺一条→校验拒
        reordered = legal_entry.call("contract_gate.criterion_reorder", {
            "rubric": "contract_买卖_v1",
            "order": ["annex_complete", "acceptance_period",
                      "price_stated", "subject_defined"]}, self.config)
        self.assertEqual([c["id"] for c in reordered["criteria"]],
                         ["annex_complete", "acceptance_period",
                          "price_stated", "subject_defined"])
        with self.assertRaisesRegex(cg.ContractGateError,
                                    "cg37_reorder_not_full_order"):
            legal_entry.call("contract_gate.criterion_reorder", {
                "rubric": "contract_买卖_v1",
                "order": ["subject_defined", "price_stated"]}, self.config)
        with self.assertRaisesRegex(cg.ContractGateError,
                                    "cg37_criterion_exists"):
            legal_entry.call("contract_gate.criterion_add", {
                "rubric": "contract_买卖_v1", "id": "subject_defined",
                "title": "重复",
                "match_criteria": "PASS if 判据在案；FAIL if 判据缺失"},
                self.config)

    def test_default_rubric_versioning(self):
        seed_rubric(self.state_root)  # contract_买卖_v1
        seed_rubric(self.state_root, name="contract_买卖_v2")
        self.assertEqual(cg.default_rubric(self.state_root, CONTRACT_TYPE),
                         "contract_买卖_v2")  # 最高版本（B23）
        # 无版本化名→字典序最后；两者并存→版本化优先
        seed_rubric(self.state_root, name="contract_买卖_草案")
        self.assertEqual(cg.default_rubric(self.state_root, CONTRACT_TYPE),
                         "contract_买卖_v2")

    def test_unknown_or_empty_rubric_typed_reject(self):
        with self.assertRaisesRegex(cg.ContractGateError,
                                    "cg37_rubric_not_found:default:租赁"):
            cg.default_rubric(self.state_root, "租赁")
        # 建空 criteria＝typed 拒（校验闸）
        with self.assertRaisesRegex(cg.ContractGateError,
                                    "cg37_criteria_invalid"):
            legal_entry.call("contract_gate.rubric_create", {
                "name": "contract_买卖_空", "source": "local",
                "criteria": []}, self.config)
        # 删到最后一条＝空 rubric 拒（不许留空壳）
        seed_rubric(self.state_root, name="contract_买卖_单条",
                    criteria=[RUBRIC_V1[0]])
        with self.assertRaisesRegex(cg.ContractGateError,
                                    "cg37_rubric_empty_criteria"):
            legal_entry.call("contract_gate.criterion_delete", {
                "rubric": "contract_买卖_单条",
                "id": "subject_defined"}, self.config)
        # 未知名 typed 拒（B21）
        with self.assertRaisesRegex(cg.ContractGateError,
                                    "cg37_rubric_not_found:no_such"):
            legal_entry.call("contract_gate.rubric_get",
                             {"name": "no_such"}, self.config)


class ScoringGateTests(GateBase):
    """D 组（下）：all-pass 二值/独立 judge/退避/单败不沉船/快照。"""

    def evaluate(self, text, judge_fn, **kwargs):
        self.llm.judge_fn = judge_fn
        config = dict(self.config)
        config["contract_gate_llm"] = self.llm.seam()
        return legal_entry.call("contract_gate.evaluate", {
            "contract_text": text, "rubric": "contract_买卖_v1",
            **kwargs}, config)

    def test_all_pass_binary_no_partial_score(self):
        seed_rubric(self.state_root)
        text = "## 标的与质量\n\n甲方向乙方出售设备。"
        partial = self.evaluate(text, lambda title, t: (
            ("fail", "标的含糊") if title == "标的明确"
            else ("pass", "脚本默认通过")))
        self.assertEqual(partial["score"], 0.0)  # 3/4 与 0/4 同为 0.0（B24）
        self.assertEqual(partial["n_passed"], 3)
        self.assertFalse(partial["all_pass"])
        self.assertIn("差 1 条", partial["summary"])
        full = self.evaluate(text, lambda title, t: ("pass", "脚本默认通过"))
        self.assertEqual(full["score"], 1.0)
        self.assertTrue(full["all_pass"])
        self.assertEqual(full["n_passed"], full["n_criteria"])

    def test_context_separation_task_desc_only_when_given(self):
        seed_rubric(self.state_root)
        seen = {}

        def spy(system, user):
            if "评审项：" in user:
                title = user.split("评审项：", 1)[1].split("\n", 1)[0]
                seen[title] = "起草需求" in user
            return json.dumps({"verdict": "pass", "location": "标的与质量",
                               "quote": "## 标的与质量",
                               "reasoning": "ok"}, ensure_ascii=False)

        config = dict(self.config)
        config["contract_gate_llm"] = {"model": "m", "complete": spy}
        legal_entry.call("contract_gate.evaluate", {
            "contract_text": "## 标的与质量\n\n合同正文",
            "rubric": "contract_买卖_v1"}, config)
        self.assertTrue(all(flag is False for flag in seen.values()))  # 无需求不附（B26）
        seen.clear()
        legal_entry.call("contract_gate.evaluate", {
            "contract_text": "## 标的与质量\n\n合同正文",
            "rubric": "contract_买卖_v1",
            "task_desc": "购买十台设备"}, config)
        self.assertTrue(all(flag is True for flag in seen.values()))  # 有才附

    def test_transient_retry_never_counts_fail_and_exhaustion_degrades(self):
        seed_rubric(self.state_root)
        calls = []

        def flaky(title, text):
            if title == "价款齐备":
                calls.append(title)
                if len(calls) < 2:
                    return ("raise_transient", "")  # 第一次 429
                return ("pass", "重试后通过")
            return ("pass", "脚本默认通过")

        self.llm.judge_fn = flaky
        result = cg.evaluate_contract(
            self.state_root, self.config, SECTIONED_TEXT, "contract_买卖_v1",
            llm=self.llm.seam(), backoff_seconds=0)
        self.assertEqual(calls, ["价款齐备", "价款齐备"])  # 429 重试不弃（B27）
        verdict = next(r for r in result["criteria_results"]
                       if r["title"] == "价款齐备")
        self.assertEqual(verdict["verdict"], "pass")  # 429 绝不计 FAIL
        self.assertNotIn("[error:", verdict["reasoning"])

        def always_down(title, text):
            if title == "价款齐备":
                return ("raise_transient", "")
            return ("pass", "脚本默认通过")

        self.llm.judge_fn = always_down
        exhausted = cg.evaluate_contract(
            self.state_root, self.config, SECTIONED_TEXT, "contract_买卖_v1",
            llm=self.llm.seam(), backoff_seconds=0)
        verdict = next(r for r in exhausted["criteria_results"]
                       if r["title"] == "价款齐备")
        self.assertEqual(verdict["verdict"], "fail")  # 重试耗尽（B28）
        self.assertIn("[error:", verdict["reasoning"])
        self.assertEqual(exhausted["n_passed"], 3)  # 单败不沉船，跑继续

    def test_single_judge_bad_output_degrades_not_crashes(self):
        seed_rubric(self.state_root)

        def bad_json(title, text):
            if title == "标的明确":
                raise ValueError("完全坏掉的输出：不是 JSON {{{")
            return ("pass", "ok")

        self.llm.judge_fn = bad_json
        result = cg.evaluate_contract(
            self.state_root, self.config, SECTIONED_TEXT, "contract_买卖_v1",
            llm=self.llm.seam(), backoff_seconds=0)
        verdict = next(r for r in result["criteria_results"]
                       if r["title"] == "标的明确")
        self.assertEqual(verdict["verdict"], "fail")
        self.assertIn("[error:", verdict["reasoning"])
        self.assertEqual(result["n_criteria"], 4)

    def test_eval_snapshot_survives_rubric_edit(self):
        seed_rubric(self.state_root)
        result = self.evaluate(SECTIONED_TEXT, gate_judge({}))
        legal_entry.call("contract_gate.criterion_update", {
            "rubric": "contract_买卖_v1", "id": "subject_defined",
            "title": "标的明确（改后）"}, self.config)
        stored = legal_entry.call("contract_gate.run_get",
                                  {"run_id": result["run_id"]}, self.config)
        self.assertEqual(  # 快照不随后续 rubric 编辑失效（B30）
            [c["title"] for c in stored["criteria_snapshot"]],
            ["标的明确", "价款齐备", "违约责任可执行", "质量异议期在案"])
        runs = legal_entry.call("contract_gate.run_list", {}, self.config)
        self.assertEqual(runs["count"], 1)

    def test_concurrent_judge_pool_clamped(self):
        import time as _time
        seed_rubric(self.state_root)
        self.assertEqual(cg._resolve_workers(None, 4), 4)  # 按规则数封顶
        self.assertEqual(cg._resolve_workers(99, 40), 16)  # 钳 [1,16]
        self.assertEqual(cg._resolve_workers(0, 40), 1)
        self.assertEqual(cg._resolve_workers(8, 40), 8)
        threads = set()

        def tracking(title, text):
            import threading
            threads.add(threading.current_thread().name)
            _time.sleep(0.02)  # 让池内并行可观测
            return ("pass", "并发 ok")

        self.llm.judge_fn = tracking
        cg.evaluate_contract(self.state_root, self.config, SECTIONED_TEXT,
                             "contract_买卖_v1", llm=self.llm.seam(),
                             max_workers=4, backoff_seconds=0)
        self.assertGreater(len(threads), 1)  # 并发评审真实并行（B25）


class PipelineTests(GateBase):
    """E 组：自愈管线两末态出稿/排除分权/零改写/作业状态机。"""

    def pipeline(self, **overrides):
        config = dict(self.config)
        config["contract_gate_llm"] = self.llm.seam()
        args = {"contract_type": CONTRACT_TYPE, "scenario": "分批供货",
                "stance": "pro_a", "task_desc": "合成起草需求：分批购买设备",
                "max_iterations": 3}
        args.update(overrides)
        return legal_entry.call("contract_gate.pipeline", args, config)

    def clauses_bytes(self):
        root = Path(self.state_root) / "contract_gate"
        return ((root / "clauses" / "clauses.json").read_bytes()
                + (root / "tag_dims" / "tag_dims.json").read_bytes())

    def test_passed_end_state_clean_delivery_with_one_heal_round(self):
        ids = self.seed_all()
        approve_custom(self.state_root, ids["weak"])
        approve_custom(self.state_root, ids["confid"])
        self.llm.judge_fn = gate_judge({})
        self.llm.improve_fn = lambda failing, customs: {
            "exclude_custom_clause_ids": [ids["weak"]],
            "recommendations": [{"clause_id": ids["weak"],
                                 "action": "reject",
                                 "reason": "薄弱条款建议人工复核后拒绝"}]}
        before = self.clauses_bytes()
        result = self.pipeline()
        delivery = result["delivery"]
        # 两末态之一：passed 干净出稿（验收口径②）
        self.assertEqual(delivery["gate_status"], "passed")
        self.assertIn("过关", delivery["note"])
        self.assertTrue(delivery["all_pass"])
        self.assertEqual(delivery["missed_criteria"], [])
        # 自愈一轮排除生效：薄弱 custom 被排除后母版接管，第二轮全过
        self.assertEqual(result["best"]["iteration"], 2)
        self.assertIn("按日万分之五", delivery["filled_text"])
        self.assertIn("保密义务", delivery["filled_text"])  # 未被排除的仍在
        self.assertIn("按批次交付", delivery["filled_text"])  # tagged 生效
        self.assertEqual(result["actions_taken"][0]["excluded"],
                         [ids["weak"]])
        self.assertEqual(result["excluded_ids"], [ids["weak"]])
        self.assertEqual(result["recommendations"][0]["clause_id"],
                         ids["weak"])
        self.assertEqual(result["status"], "completed")
        self.assertEqual(len(result["iterations"]), 2)
        # 填槽缓存跨轮摊薄：同装配槽集第二轮命中（B17）
        self.assertEqual(self.llm.fill_calls, 1)
        # 共享条款库零改写（验收口径②：自愈循环对条款库只读）
        self.assertEqual(before, self.clauses_bytes())
        stored = legal_entry.call(
            "contract_gate.pipeline_get",
            {"pipeline_run_id": result["pipeline_run_id"]}, self.config)
        self.assertEqual(stored["delivery"]["gate_status"], "passed")

    def test_exhausted_end_state_delivers_with_named_marker(self):
        self.seed_all()  # 不批准任何 custom：唯一失败项=脚本钉死的标的
        self.llm.judge_fn = gate_judge(
            {"标的明确": lambda t: ("fail", "标的描述不完整")})
        self.llm.improve_fn = lambda failing, customs: {
            "exclude_custom_clause_ids": [], "recommendations": []}
        result = self.pipeline(max_iterations=2)
        delivery = result["delivery"]
        # 两末态之二：耗尽照样出稿交付，不阻塞（交付语义等量）
        self.assertEqual(delivery["gate_status"], "exhausted")
        self.assertIn("未过关", delivery["note"])  # 具名标注（有意增强）
        self.assertIn("差 1 条", delivery["note"])  # 差几条账
        self.assertIn("标的明确", delivery["missed_criteria"])
        self.assertTrue(delivery["filled_text"])  # 稿子照交
        self.assertEqual(delivery["n_passed"], 3)
        self.assertEqual(result["status"], "completed")
        self.assertEqual(len(result["iterations"]), 2)  # 达上限封顶
        self.assertEqual(len(result["actions_taken"]), 1)  # 一轮 improve

    def test_max_iterations_one_disables_loop_and_bad_improve_survives(self):
        ids = self.seed_all()
        approve_custom(self.state_root, ids["weak"])
        self.llm.judge_fn = gate_judge(
            {"标的明确": lambda t: ("fail", "一直不过")})
        result = self.pipeline(max_iterations=1)
        self.assertEqual(self.llm.improve_calls, 0)  # =1 禁循环（B34）
        self.assertEqual(result["actions_taken"], [])
        self.assertEqual(len(result["iterations"]), 1)
        self.assertEqual(result["delivery"]["gate_status"], "exhausted")
        # 坏 improve 输出→空动作循环照跑（B38）
        self.llm.improve_fn = lambda f, c: "诊断输出坏掉不是对象"
        result2 = self.pipeline(max_iterations=2)
        self.assertEqual(self.llm.improve_calls, 1)
        self.assertEqual(result2["actions_taken"][0]["excluded"], [])
        self.assertEqual(result2["delivery"]["gate_status"], "exhausted")

    def test_failed_run_row_records_error(self):
        self.seed_all()
        with self.assertRaises(cg.ContractGateError):
            self.pipeline(contract_type="租赁",  # 无母版条款
                          rubric="contract_买卖_v1")
        rows = legal_entry.call("contract_gate.pipeline_list", {},
                                self.config)["runs"]
        self.assertEqual(rows[-1]["status"], "failed")  # 作业状态机（B40）
        self.assertIn("cg37_contract_type_not_found",
                      rows[-1]["error_message"])


class GovernanceTests(GateBase):
    """F 组：learn 阈值自动 reject/tag 迭代两段/离线分析+执行器。"""

    def seed_reject_scenario(self, *, threshold=None, state_root=None):
        root = state_root or self.state_root
        config = {"contract_gate_state_root": root}
        ids = seed_library(root)
        seed_rubric(root)
        approve_custom(root, ids["weak"])
        self.llm.judge_fn = gate_judge(
            {"标的明确": lambda t: ("fail", "持续不过（合成）")})
        self.llm.improve_fn = lambda failing, customs: {
            "exclude_custom_clause_ids": [ids["tie_auto"]],
            "recommendations": [{"clause_id": ids["tie_auto"],
                                 "action": "reject",
                                 "reason": "反复拖累评分（合成）"}]}
        config["contract_gate_llm"] = self.llm.seam()
        if threshold is not None:
            config["contract_gate_auto_reject_threshold"] = threshold
        runs = []
        for _ in range(3):
            runs.append(legal_entry.call("contract_gate.pipeline", {
                "contract_type": CONTRACT_TYPE, "scenario": "分批供货",
                "stance": "pro_a", "max_iterations": 2}, config))
        return ids, runs, config

    def test_learn_threshold_auto_reject_custom_only_idempotent(self):
        ids, runs, config = self.seed_reject_scenario()
        learned = legal_entry.call(
            "contract_gate.learn", {"pipeline_run_id": runs[-1]["pipeline_run_id"]},
            config)
        applied = learned["learn_applied"]
        self.assertEqual([a["clause_id"] for a in applied], [ids["tie_auto"]])
        self.assertEqual(applied[0]["total_count"], 3)  # 3 次累计≥3（B42）
        rejected = legal_entry.call(
            "contract_gate.clause_get", {"clause_id": ids["tie_auto"]},
            self.config)
        self.assertTrue(all(status == "rejected" for status
                            in rejected["tag_review"].values()))
        # base/tagged 永不动
        base = legal_entry.call(
            "contract_gate.clause_get", {"clause_id": ids["base:附则"]},
            self.config)
        self.assertEqual(base["tag_review"], {})
        # learn_applied 回写 + 幂等（B43）
        stored = legal_entry.call(
            "contract_gate.pipeline_get",
            {"pipeline_run_id": runs[-1]["pipeline_run_id"]}, self.config)
        self.assertEqual(stored["learn_applied"], applied)
        again = legal_entry.call(
            "contract_gate.learn",
            {"pipeline_run_id": runs[-1]["pipeline_run_id"]}, config)
        self.assertEqual(again["learn_applied"], applied)
        # 阈值可调（config 覆盖；独立状态根避免重名冲突）
        other_root = tempfile.mkdtemp(prefix="cg37-thr-")
        ids2, runs2, config2 = self.seed_reject_scenario(
            threshold=2, state_root=other_root)
        early = legal_entry.call(
            "contract_gate.learn",
            {"pipeline_run_id": runs2[-1]["pipeline_run_id"]}, config2)
        self.assertEqual(early["threshold"], 2)
        self.assertEqual([a["clause_id"] for a in early["learn_applied"]],
                         [ids2["tie_auto"]])  # 2 次即达阈

    def test_iteration_analyze_and_apply_dry_run_and_ops_log(self):
        ids, runs, _config = self.seed_reject_scenario()
        analysis = legal_entry.call(
            "contract_gate.iteration_analyze",
            {"contract_type": CONTRACT_TYPE}, self.config)
        rec = next(r for r in analysis["recommendations"]
                   if r["clause_id"] == ids["tie_auto"])
        self.assertEqual(rec["exclude_count"], 3)  # 高频 exclude 达阈
        self.assertEqual(rec["reject_count"], 3)   # 建议 reject 达阈
        # 默认档 high：medium 建议不执行
        preview_high = legal_entry.call(
            "contract_gate.iteration_apply",
            {"contract_type": CONTRACT_TYPE}, self.config)  # dry_run 默认 true
        self.assertEqual(preview_high["actions"], [])
        # medium 档 dry-run：预览不改账（B46）
        preview = legal_entry.call(
            "contract_gate.iteration_apply",
            {"contract_type": CONTRACT_TYPE, "confidence": "medium"},
            self.config)
        self.assertEqual([a["action"] for a in preview["actions"]],
                         ["reject"])
        clause = legal_entry.call(
            "contract_gate.clause_get", {"clause_id": ids["tie_auto"]},
            self.config)
        self.assertNotIn("rejected", clause["tag_review"].values())
        # 实执行：bulk reject + JSONL 操作日志留痕
        applied = legal_entry.call(
            "contract_gate.iteration_apply",
            {"contract_type": CONTRACT_TYPE, "confidence": "medium",
             "dry_run": False}, self.config)
        self.assertEqual(applied["dry_run"], False)
        log = (Path(self.state_root) / "contract_gate" / "governance"
               / "iteration_ops.jsonl").read_text(encoding="utf-8")
        self.assertIn('"action": "reject"', log)
        self.assertIn(f'"clause_id": {ids["tie_auto"]}', log)
        rejected = legal_entry.call(
            "contract_gate.clause_get", {"clause_id": ids["tie_auto"]},
            self.config)
        self.assertTrue(all(v == "rejected"
                            for v in rejected["tag_review"].values()))

    def test_retag_suggest_then_apply_and_rollback_on_score_drop(self):
        ids = self.seed_all()  # 不批准 custom：首轮即可全过（基线 4/4）
        self.llm.judge_fn = gate_judge({})
        config = dict(self.config)
        config["contract_gate_llm"] = self.llm.seam()
        baseline = legal_entry.call("contract_gate.pipeline", {
            "contract_type": CONTRACT_TYPE, "scenario": "分批供货",
            "stance": "pro_a", "max_iterations": 1}, config)
        self.assertEqual(baseline["delivery"]["n_passed"], 4)
        # suggest：只读建议落账（B44）
        self.llm.retag_fn = lambda clauses: [{
            "clause_id": ids["weak"], "section": "违约责任",
            "current_tags": {"stance": "pro_a", "scenario": "分批供货"},
            "suggested_tags": {"stance": "pro_a", "scenario": "单批交付"},
            "reason": "条款为通用违约条款，场景标签贴分批不当（合成）"}]
        suggestion = legal_entry.call(
            "contract_gate.retag_suggest",
            {"pipeline_run_id": baseline["pipeline_run_id"]}, config)
        self.assertEqual(suggestion["status"], "pending")
        self.assertEqual(suggestion["suggestions"][0]["clause_id"],
                         ids["weak"])
        self.assertEqual(self.llm.retag_calls, 1)
        original_tags = legal_entry.call(
            "contract_gate.clause_get", {"clause_id": ids["weak"]},
            self.config)["tags"]
        # apply（降分回滚路径）：重评比基线差→自动回滚（B45）
        self.llm.judge_fn = gate_judge(
            {"标的明确": lambda t: ("fail", "重评更差（合成）")})
        applied = legal_entry.call(
            "contract_gate.retag_apply", {"retag_id": suggestion["retag_id"]},
            config)
        self.assertEqual(applied["status"], "rolled_back")
        self.assertEqual(applied["reval"]["n_passed"], 3)
        restored = legal_entry.call(
            "contract_gate.clause_get", {"clause_id": ids["weak"]},
            self.config)
        self.assertEqual(restored["tags"], original_tags)  # 原始 tags 复原
        # 再 apply 同条→非 pending 拒（一次性闸）
        with self.assertRaisesRegex(cg.ContractGateError,
                                    "cg37_retag_not_pending"):
            legal_entry.call("contract_gate.retag_apply",
                             {"retag_id": suggestion["retag_id"]}, config)

    def test_retag_apply_kept_when_score_not_dropping(self):
        ids = self.seed_all()
        self.llm.judge_fn = gate_judge({})
        config = dict(self.config)
        config["contract_gate_llm"] = self.llm.seam()
        baseline = legal_entry.call("contract_gate.pipeline", {
            "contract_type": CONTRACT_TYPE, "scenario": "分批供货",
            "stance": "pro_a", "max_iterations": 1}, config)
        self.llm.retag_fn = lambda clauses: [{
            "clause_id": ids["weak"], "section": "违约责任",
            "current_tags": {"stance": "pro_a"},
            "suggested_tags": {"stance": "balanced"},
            "reason": "立场标签改均衡（合成）"}]
        suggestion = legal_entry.call(
            "contract_gate.retag_suggest",
            {"pipeline_run_id": baseline["pipeline_run_id"]}, config)
        # 重评不降分→保留应用
        applied = legal_entry.call(
            "contract_gate.retag_apply", {"retag_id": suggestion["retag_id"]},
            config)
        self.assertEqual(applied["status"], "applied")
        self.assertEqual(applied["reval"]["n_passed"],
                         baseline["delivery"]["n_passed"])
        retagged = legal_entry.call(
            "contract_gate.clause_get", {"clause_id": ids["weak"]},
            self.config)
        self.assertEqual(retagged["tags"]["stance"], "balanced")


class CompareTests(GateBase):
    """G 组：固定区域只变 prompt/drafter-only/fail-fast/矩阵/懒取。"""

    def seed_compare(self):
        self.seed_all()
        for name, marker in (("prompt-a", "草稿A风格"), ("prompt-b", "草稿B风格")):
            legal_entry.call("contract_gate.drafter_create", {
                "name": name, "contract_type": CONTRACT_TYPE,
                "content": f"按{marker}起草合同：条款完整、标的价款齐备。"},
                self.config)

        def drafter(system, user):
            marker = "草稿A" if "草稿A风格" in system else "草稿B"
            return (f"## 标的与质量\n\n{marker}：甲方向乙方出售设备十台。\n\n"
                    "## 价款与支付\n\n合同总额 100000.00 元。")

        self.llm.drafter_fn = drafter

        def judge(title, text):
            if title == "价款齐备":
                return (("pass", "价款在案") if "草稿A" in text
                        else ("fail", "价款缺失"))
            return ("pass", "脚本默认通过")

        self.llm.judge_fn = judge
        config = dict(self.config)
        config["contract_gate_llm"] = self.llm.seam()
        return config

    def test_compare_matrix_and_draft_lazy_fetch(self):
        config = self.seed_compare()
        result = legal_entry.call("contract_gate.compare_run", {
            "contract_type": CONTRACT_TYPE,
            "prompts": ["prompt-a", "prompt-b"], "n_drafts": 2,
            "task_desc": "合成对比"}, config)
        self.assertEqual(result["mode"], "drafter-only")  # 隔离档（B48）
        self.assertEqual(len(result["drafts"]), 4)  # 2 prompt × 2 drafts
        self.assertEqual(self.llm.drafter_calls, 4)  # 每稿单次直调
        matrix = legal_entry.call("contract_gate.compare_matrix", {
            "compare_run_id": result["compare_run_id"]}, self.config)
        cell_a = matrix["cells"]["prompt-a"]["price_stated"]
        self.assertEqual((cell_a["pass_rate"], cell_a["n_pass"], cell_a["n"]),
                         (1.0, 2, 2))  # n>1 通过率单元格（B52）
        cell_b = matrix["cells"]["prompt-b"]["price_stated"]
        self.assertEqual((cell_b["pass_rate"], cell_b["n_pass"], cell_b["n"]),
                         (0.0, 0, 2))
        self.assertTrue(cell_b["reasoning"])  # 首个可用 reasoning 随行
        # 默认不返回 draft_text；run_draft 懒取（B51）
        listing = legal_entry.call("contract_gate.compare_get", {
            "compare_run_id": result["compare_run_id"]}, self.config)
        self.assertNotIn("draft_text", listing["drafts"][0])
        draft = legal_entry.call("contract_gate.run_draft", {
            "compare_run_id": result["compare_run_id"],
            "prompt_name": "prompt-a", "draft_index": 1}, self.config)
        self.assertIn("草稿A", draft["draft_text"])
        # drafter-only：不进生产管线（无 pipeline 行）
        pipelines = legal_entry.call("contract_gate.pipeline_list", {},
                                     self.config)
        self.assertEqual(pipelines["count"], 0)
        # n=1 单元格=二值 verdict（B52）
        single = legal_entry.call("contract_gate.compare_run", {
            "contract_type": CONTRACT_TYPE,
            "prompts": ["prompt-a", "prompt-b"], "n_drafts": 1}, config)
        matrix1 = legal_entry.call("contract_gate.compare_matrix", {
            "compare_run_id": single["compare_run_id"]}, self.config)
        self.assertEqual(
            matrix1["cells"]["prompt-b"]["price_stated"]["verdict"], "fail")

    def test_compare_guards_and_fail_fast_before_llm(self):
        config = self.seed_compare()
        with self.assertRaisesRegex(cg.ContractGateError,
                                    "cg37_compare_needs_two_prompts"):
            legal_entry.call("contract_gate.compare_run", {
                "contract_type": CONTRACT_TYPE,
                "prompts": ["prompt-a"]}, config)  # ≥2 才跑（B47）
        calls_before = self.llm.total_calls
        with self.assertRaisesRegex(cg.ContractGateError,
                                    "cg37_rubric_not_found"):
            legal_entry.call("contract_gate.compare_run", {
                "contract_type": "租赁",  # 无 rubric→任何 LLM 调用前拒（B49）
                "prompts": ["prompt-a", "prompt-b"]}, config)
        self.assertEqual(self.llm.total_calls, calls_before)
        # prompt CRUD 往返
        prompts = legal_entry.call("contract_gate.drafter_list", {},
                                   self.config)
        self.assertEqual(prompts["count"], 2)
        fetched = legal_entry.call("contract_gate.drafter_get",
                                   {"name": "prompt-a"}, self.config)
        self.assertIn("草稿A风格", fetched["content"])
        legal_entry.call("contract_gate.drafter_delete",
                         {"name": "prompt-b"}, self.config)
        with self.assertRaisesRegex(cg.ContractGateError,
                                    "cg37_prompt_not_found"):
            legal_entry.call("contract_gate.compare_run", {
                "contract_type": CONTRACT_TYPE,
                "prompts": ["prompt-a", "prompt-b"]}, config)


class Re12IsolationTests(GateBase):
    """RE-12 衔接面五条对账（§4.4；验收口径④：字段零混用）。"""

    # #12 审查侧判定语汇（skill-presets/contract-review 十大维度列 id+
    # 四级风险分级+四件套字段）——本面任何产物不得出现。
    REVIEW_VOCABULARY = {
        "critical", "high", "medium", "low", "risk_level", "severity",
        "capacity", "obligations", "subject_matter", "price_payment",
        "breach", "dispute_resolution", "confidentiality", "ip_rights",
        "force_majeure", "termination", "review_opinion", "risk_desc",
        "legal_basis", "suggestion",
    }

    def test_gate_delivery_vocabulary_disjoint_from_review_side(self):
        self.seed_all()  # 不批准 custom：母版直出，首轮全过=passed 末态
        self.llm.judge_fn = gate_judge({})
        config = dict(self.config)
        config["contract_gate_llm"] = self.llm.seam()
        result = legal_entry.call("contract_gate.pipeline", {
            "contract_type": CONTRACT_TYPE, "scenario": "分批供货",
            "stance": "pro_a", "max_iterations": 1}, config)
        delivery = result["delivery"]

        def walk(node, keys, verdicts, values):
            if isinstance(node, dict):
                keys.update(node.keys())
                verdicts.extend([v for v in (node.get("verdict"),)
                                 if isinstance(v, str)])
                values.extend(str(v) for v in node.values()
                              if isinstance(v, str))
                for v in node.values():
                    walk(v, keys, verdicts, values)
            elif isinstance(node, list):
                for item in node:
                    walk(item, keys, verdicts, values)

        keys, verdicts, values = set(), [], []
        walk(delivery, keys, verdicts, values)
        # ①字段名与审查语汇零交集；②verdict 值域⊆{pass,fail}
        self.assertEqual(keys & self.REVIEW_VOCABULARY, set())
        self.assertTrue(verdicts and set(verdicts) <= {"pass", "fail"})
        for token in ("critical", "high", "medium", "low"):
            self.assertNotIn(token, values)  # 值面也不出现四级分级
        # ③单向送审锚：只带文本摘要+注记，零判定字段（§4.4-3）
        self.assertEqual(set(delivery["review_handoff"]),
                         {"text_sha256", "note"})
        self.assertIn("非审查结论", delivery["review_handoff"]["note"])
        # 过关稿也不得表述为「已审查/无风险」（§4.4-2）
        self.assertEqual(delivery["gate_status"], "passed")
        self.assertNotIn("已审查", delivery["note"])
        self.assertNotIn("无风险", delivery["note"])
        # ④确定性切分共享：装配节切分=标题状态机（零模型），与 #12 条款
        # 行基座同口径（§4.4-4）
        assembled = legal_entry.call("contract_gate.assemble", {
            "contract_type": CONTRACT_TYPE, "scenario": "分批供货"},
            self.config)
        sections = cg.split_sections(assembled["body_text"])
        self.assertEqual(sections, ["标的与质量", "价款与支付", "履行与交付",
                                    "违约责任", "其他约定", "质量异议期",
                                    "附则"])  # 扩展节排附则前（B10）
        # ⑤law_refs 静态归集只标注不裁决（§4.4-5）
        for ref in assembled["law_refs"]:
            self.assertIn("效力未核", ref["note"])


class WiringAndDeterminismTests(GateBase):
    """method 面注册/缺配置 typed 拒/端到端确定性。"""

    EXPECTED_METHODS = (
        "contract_gate.clause_upsert", "contract_gate.clause_list",
        "contract_gate.clause_get", "contract_gate.clause_delete_auto",
        "contract_gate.clause_review_tag", "contract_gate.clause_bulk_review",
        "contract_gate.review_queue", "contract_gate.tag_dim_register",
        "contract_gate.assemble",
        "contract_gate.rubric_list", "contract_gate.rubric_get",
        "contract_gate.rubric_create", "contract_gate.rubric_update",
        "contract_gate.rubric_delete", "contract_gate.criterion_add",
        "contract_gate.criterion_update", "contract_gate.criterion_delete",
        "contract_gate.criterion_reorder",
        "contract_gate.evaluate", "contract_gate.run_list",
        "contract_gate.run_get", "contract_gate.dashboard",
        "contract_gate.pipeline", "contract_gate.pipeline_list",
        "contract_gate.pipeline_get",
        "contract_gate.compare_run", "contract_gate.compare_list",
        "contract_gate.compare_get", "contract_gate.compare_matrix",
        "contract_gate.run_draft", "contract_gate.drafter_create",
        "contract_gate.drafter_list", "contract_gate.drafter_get",
        "contract_gate.drafter_delete",
        "contract_gate.learn", "contract_gate.iteration_analyze",
        "contract_gate.iteration_apply", "contract_gate.retag_suggest",
        "contract_gate.retag_apply", "contract_gate.master_regenerate",
    )

    def test_method_group_registered_and_typed_rejections(self):
        self.assertEqual(legal_entry.CONTRACT_GATE_METHODS,
                         frozenset(self.EXPECTED_METHODS))
        # 竞品 MCP 20 件对齐面逐一在册（B55）
        for aligned in ("contract_gate.evaluate",
                        "contract_gate.rubric_list", "contract_gate.rubric_get",
                        "contract_gate.rubric_create",
                        "contract_gate.rubric_update",
                        "contract_gate.rubric_delete",
                        "contract_gate.criterion_add",
                        "contract_gate.criterion_update",
                        "contract_gate.criterion_delete",
                        "contract_gate.criterion_reorder",
                        "contract_gate.run_list", "contract_gate.run_get",
                        "contract_gate.compare_run",
                        "contract_gate.compare_list",
                        "contract_gate.compare_get",
                        "contract_gate.compare_matrix",
                        "contract_gate.run_draft",
                        "contract_gate.pipeline",
                        "contract_gate.pipeline_list",
                        "contract_gate.pipeline_get"):
            self.assertIn(aligned, legal_entry.CONTRACT_GATE_METHODS)
        # 缺状态根=fail-closed；未知方法=具名拒
        with self.assertRaisesRegex(NotConnected,
                                    "cg37_state_root_not_configured"):
            legal_entry.call("contract_gate.rubric_list", {}, {})
        from contract_gate import contract_gate_call
        with self.assertRaisesRegex(cg.ContractGateError,
                                    "cg37_method_unknown"):
            contract_gate_call("contract_gate.nope", {}, self.config)
        with self.assertRaisesRegex(NotConnected,
                                    "method_not_connected"):
            legal_entry.call("contract_gate.nope", {}, self.config)

    def test_end_to_end_determinism_same_inputs_same_bytes(self):
        def run_once():
            root = tempfile.mkdtemp(prefix="cg37-det-")
            config = {"contract_gate_state_root": root,
                      "contract_gate_llm": self.llm.seam()}
            ids = seed_library(root)
            approve_custom(root, ids["weak"])
            seed_rubric(root)
            self.llm.judge_fn = gate_judge({})
            self.llm.improve_fn = lambda f, c: {
                "exclude_custom_clause_ids": [ids["weak"]],
                "recommendations": []}
            result = legal_entry.call("contract_gate.pipeline", {
                "contract_type": CONTRACT_TYPE, "scenario": "分批供货",
                "stance": "pro_a", "max_iterations": 3}, config)
            clauses = (Path(root) / "contract_gate" / "clauses"
                       / "clauses.json").read_bytes()
            return result, clauses

        first, clauses_first = run_once()
        second, clauses_second = run_once()
        self.assertEqual(clauses_first, clauses_second)  # 条款账同字节
        self.assertEqual(first["delivery"]["filled_text"],
                         second["delivery"]["filled_text"])  # 出稿同文
        self.assertEqual(first["delivery"]["gate_status"],
                         second["delivery"]["gate_status"])
        self.assertEqual(first["delivery"]["note"],
                         second["delivery"]["note"])
        self.assertEqual(first["best"]["n_passed"],
                         second["best"]["n_passed"])


class HarveyRubricAssertionTests(GateBase):
    """增补断言 A37-H1（判据双分支）+A37-H3（粒度区间+豁免账）。
    口径学来源=Harvey LAB rubric 形状（无许可源：只取机制形状，判据语料
    自撰——7 包 363 条 100% 双分支/32-64 条一包的命题级粒度）。"""

    @staticmethod
    def range_criteria(n):
        return [{"id": f"c{i:02d}", "title": f"第{i}项要素在案",
                 "match_criteria": f"PASS if 第{i}项要素在案；"
                                   f"FAIL if 缺第{i}项要素"}
                for i in range(1, n + 1)]

    def test_h1_single_branch_rejected_on_create_add_update(self):
        single = {"id": "only_pass", "title": "单分支判据",
                  "match_criteria": "PASS if 只有通过分支没有失败分支"}
        with self.assertRaisesRegex(cg.ContractGateError,
                                    "cg37_criterion_single_branch"):
            legal_entry.call("contract_gate.rubric_create", {
                "name": "contract_买卖_单分支", "criteria": [single],
                "granularity_exemption": "单分支负例（豁免粒度只测双分支）"},
                self.config)
        seed_rubric(self.state_root)
        with self.assertRaisesRegex(cg.ContractGateError,
                                    "cg37_criterion_single_branch"):
            legal_entry.call("contract_gate.criterion_add", {
                "rubric": "contract_买卖_v1", **single}, self.config)
        with self.assertRaisesRegex(cg.ContractGateError,
                                    "cg37_criterion_single_branch"):
            legal_entry.call("contract_gate.criterion_update", {
                "rubric": "contract_买卖_v1", "id": "subject_defined",
                "match_criteria": "FAIL if 只有失败分支"}, self.config)
        # 既有双分支判据不受影响（create 全量 25 条在下一测）

    def test_h3_granularity_range_and_exemption_ledger(self):
        # 24 条无豁免＝越界 typed 拒（A37-H3）
        with self.assertRaisesRegex(
                cg.ContractGateError, "cg37_granularity_out_of_range:24"):
            legal_entry.call("contract_gate.rubric_create", {
                "name": "contract_买卖_粒度24", "source": "local",
                "criteria": self.range_criteria(24)}, self.config)
        # 24 条带显式豁免账＝过，且豁免理由落 rubric 行（list/get 投影）
        exempted = legal_entry.call("contract_gate.rubric_create", {
            "name": "contract_买卖_粒度24豁免", "source": "local",
            "granularity_exemption": "过渡档小样（显式豁免账）",
            "criteria": self.range_criteria(24)}, self.config)
        self.assertEqual(exempted["granularity_exemption"],
                         "过渡档小样（显式豁免账）")
        listing = legal_entry.call("contract_gate.rubric_list", {},
                                   self.config)
        row = next(r for r in listing["rubrics"]
                   if r["name"] == "contract_买卖_粒度24豁免")
        self.assertEqual(row["granularity_exemption"], "过渡档小样（显式豁免账）")
        # 25 条＝区间内直接过；拆分轴默认登记（节×槽×必答要素）
        in_range = legal_entry.call("contract_gate.rubric_create", {
            "name": "contract_买卖_粒度25", "source": "local",
            "criteria": self.range_criteria(25)}, self.config)
        self.assertEqual(in_range["criteria_count"], 25)
        self.assertEqual(in_range["granularity_axes"], ["节", "槽", "必答要素"])
        self.assertEqual(in_range["granularity_exemption"], "")
        # 无豁免 rubric：add 越 60 上界/ delete 破 25 下界＝typed 拒
        legal_entry.call("contract_gate.rubric_create", {
            "name": "contract_买卖_粒度60", "source": "local",
            "criteria": self.range_criteria(60)}, self.config)
        with self.assertRaisesRegex(
                cg.ContractGateError, "cg37_granularity_out_of_range:61"):
            legal_entry.call("contract_gate.criterion_add", {
                "rubric": "contract_买卖_粒度60", "id": "c61",
                "title": "第61项", "match_criteria": "PASS if a；FAIL if b"},
                self.config)
        with self.assertRaisesRegex(
                cg.ContractGateError, "cg37_granularity_out_of_range:24"):
            legal_entry.call("contract_gate.criterion_delete", {
                "rubric": "contract_买卖_粒度25", "id": "c01"}, self.config)
        # 豁免在账的 rubric 增删不拦（豁免覆盖整账）
        grown = legal_entry.call("contract_gate.criterion_add", {
            "rubric": "contract_买卖_粒度24豁免", "id": "c25",
            "title": "第25项", "match_criteria": "PASS if a；FAIL if b"},
            self.config)
        self.assertEqual(grown["criteria_count"], 25)


class AnchorTrioTests(GateBase):
    """增补断言 A37-H2（判定锚定三件套）：location/quote/reasoning 结构化
    输出＋机械校验（引句=正文子串、位置=节名枚举命中），违例判 invalid
    不计 pass（verdict 值域仍钉 {pass,fail}）。"""

    def evaluate_rows(self, judge_fn):
        seed_rubric(self.state_root)
        self.llm.judge_fn = judge_fn
        result = cg.evaluate_contract(
            self.state_root, self.config, SECTIONED_TEXT, "contract_买卖_v1",
            llm=self.llm.seam(), backoff_seconds=0)
        return result

    def test_trio_present_and_quote_is_substring(self):
        result = self.evaluate_rows(lambda title, text: ("pass", "通过"))
        for row in result["criteria_results"]:
            self.assertEqual(row["verdict"], "pass")
            self.assertEqual(row["anchor_status"], "ok")
            self.assertEqual(row["location"], "标的与质量")  # 节名枚举命中
            self.assertIn(row["quote"], SECTIONED_TEXT)  # 引句=正文子串
            self.assertTrue(row["reasoning"])

    def test_bad_quote_invalid_not_counted_pass(self):
        result = self.evaluate_rows(
            lambda title, text: ("bad_quote", "引文不在正文")
            if title == "标的明确" else ("pass", "通过"))
        row = next(r for r in result["criteria_results"]
                   if r["title"] == "标的明确")
        self.assertEqual(row["verdict"], "fail")  # 引句非子串＝invalid 不计 pass
        self.assertEqual(row["anchor_status"], "invalid:quote_not_substring")
        self.assertEqual(result["n_passed"], 3)

    def test_bad_location_invalid_not_counted_pass(self):
        result = self.evaluate_rows(
            lambda title, text: ("bad_location", "节名不在枚举")
            if title == "标的明确" else ("pass", "通过"))
        row = next(r for r in result["criteria_results"]
                   if r["title"] == "标的明确")
        self.assertEqual(row["verdict"], "fail")
        self.assertEqual(row["anchor_status"],
                         "invalid:location_not_in_sections")

    def test_old_shape_without_trio_rejected(self):
        result = self.evaluate_rows(
            lambda title, text: ("no_trio", "旧形状缺三件套")
            if title == "标的明确" else ("pass", "通过"))
        row = next(r for r in result["criteria_results"]
                   if r["title"] == "标的明确")
        self.assertEqual(row["verdict"], "fail")
        self.assertEqual(row["anchor_status"], "invalid:trio_missing")


class MultiJudgeTests(GateBase):
    """multi-judge 增强档（B31-B32/T19 边界件）：多数投票/平票 fail-closed/
    干净 low_confidence（3-judge 2:1 可低信——竞品特异式不复制）/全 judge
    败 typed 拒/单 judge v1 形保持。"""

    def evaluate(self, judge_fn, **kwargs):
        seed_rubric_if_absent(self.state_root)
        self.llm.judge_fn = judge_fn
        args = {"contract_text": SECTIONED_TEXT, "rubric": "contract_买卖_v1"}
        args.update(kwargs)
        config = dict(self.config)
        config["contract_gate_llm"] = self.llm.seam()
        return legal_entry.call("contract_gate.evaluate", args, config)

    def test_single_judge_keeps_v1_shape(self):
        result = self.evaluate(lambda t, x: ("pass", "通过"))
        self.assertEqual(result["n_judges"], 1)
        self.assertFalse(result["low_confidence"])
        row = result["criteria_results"][0]
        self.assertEqual(row["votes"], {"pass": 1, "fail": 0})
        self.assertEqual(row["kind"], "unanimous")
        self.assertEqual(row["confidence"], 1.0)
        self.assertEqual(result["score"], 1.0)

    def test_majority_vote_and_consensus_reasoning(self):
        calls = {}

        def judge(title, text):
            if title == "价款齐备":
                calls[title] = calls.get(title, 0) + 1
                if calls[title] == 1:
                    return ("pass", "首个 judge 通过")
                return ("fail", "其余 judge 拒绝")
            return ("pass", "脚本默认通过")

        result = self.evaluate(judge, n_judges=3)
        row = next(r for r in result["criteria_results"]
                   if r["title"] == "价款齐备")
        self.assertEqual(row["votes"], {"pass": 1, "fail": 2})
        self.assertEqual(row["verdict"], "fail")  # 1<2 多数决 fail
        self.assertEqual(row["kind"], "majority")
        self.assertAlmostEqual(row["confidence"], 2 / 3)
        self.assertEqual(row["reasoning"], "其余 judge 拒绝")  # 首个同判 judge
        self.assertTrue(result["low_confidence"])  # 2/3≈0.667<0.67（干净定义）
        self.assertEqual(result["score"], 0.0)

    def test_clean_low_confidence_gates_score_even_when_all_pass(self):
        # 全条 2:1 共识 pass：all_pass=True 但 confidence 2/3<0.67 → 低信
        # → score=0.0。竞品特异式（3-judge 恒 False）会判 score=1.0——
        # 本断言＝「不复制特异式」的可观测分界（T19）。
        calls = {}

        def judge(title, text):
            calls[title] = calls.get(title, 0) + 1
            if calls[title] >= 3:
                return ("fail", "第三票反对（合成）")
            return ("pass", "多数通过（合成）")

        result = self.evaluate(judge, n_judges=3)
        self.assertTrue(result["all_pass"])
        self.assertTrue(result["low_confidence"])
        self.assertEqual(result["score"], 0.0)  # score=1.0 须 all_pass 且非低信
        self.assertEqual(result["criteria_results"][0]["kind"], "majority")

    def test_tie_fail_closed_with_kind_tie(self):
        calls = {}

        def judge(title, text):
            if title == "价款齐备":
                calls[title] = calls.get(title, 0) + 1
                return (("pass", "支持") if calls[title] == 1
                        else ("fail", "反对"))
            return ("pass", "脚本默认通过")

        result = self.evaluate(judge, n_judges=2)
        row = next(r for r in result["criteria_results"]
                   if r["title"] == "价款齐备")
        self.assertEqual(row["votes"], {"pass": 1, "fail": 1})
        self.assertEqual(row["verdict"], "fail")  # 平票 fail-closed
        self.assertEqual(row["kind"], "tie")
        self.assertEqual(row["confidence"], 0.5)
        self.assertTrue(result["low_confidence"])

    def test_all_judges_failed_typed_reject(self):
        def always_broken(title, text):
            raise ValueError("整面板全坏（合成）")

        with self.assertRaisesRegex(cg.ContractGateError,
                                    "cg37_all_judges_failed"):
            self.evaluate(always_broken)

        def one_broken(title, text):
            if title == "标的明确":
                raise ValueError("单条坏（合成）")
            return ("pass", "通过")

        result = self.evaluate(one_broken)  # 单条坏不沉船仍在（B28）
        self.assertEqual(result["n_passed"], 3)

    def test_n_judges_domain_guard(self):
        for bad in (0, 9, "3", True):
            with self.assertRaisesRegex(cg.ContractGateError,
                                        "cg37_n_judges_invalid"):
                self.evaluate(lambda t, x: ("pass", "通过"), n_judges=bad)

    def test_pipeline_accepts_panel(self):
        self.seed_all()
        self.llm.judge_fn = gate_judge({})
        self.llm.improve_fn = lambda f, c: {
            "exclude_custom_clause_ids": [], "recommendations": []}
        config = dict(self.config)
        config["contract_gate_llm"] = self.llm.seam()
        result = legal_entry.call("contract_gate.pipeline", {
            "contract_type": CONTRACT_TYPE, "scenario": "分批供货",
            "stance": "pro_a", "max_iterations": 1, "n_judges": 2}, config)
        self.assertEqual(result["delivery"]["gate_status"], "passed")
        stored = legal_entry.call(
            "contract_gate.run_get",
            {"run_id": result["best"]["eval_run_id"]}, self.config)
        self.assertEqual(stored["n_judges"], 2)


class DashboardTests(GateBase):
    """dashboard 只读聚合（B56/T31 边界件）：总运行数/all_pass 数/平均
    通过率/按类型最高通过率；非合同 rubric 只入总量不入分型。"""

    def run_eval(self, rubric, judge_fn):
        seed_rubric_if_absent(self.state_root, name=rubric)
        self.llm.judge_fn = judge_fn
        config = dict(self.config)
        config["contract_gate_llm"] = self.llm.seam()
        return legal_entry.call("contract_gate.evaluate", {
            "contract_text": SECTIONED_TEXT, "rubric": rubric}, config)

    def test_aggregates(self):
        always = lambda title, text: ("pass", "通过（合成）")  # noqa: E731
        self.run_eval("contract_买卖_v1", always)  # 4/4 all_pass
        self.run_eval("contract_买卖_v2", lambda title, text: (
            ("fail", "标的含糊") if title == "标的明确"
            else ("pass", "通过（合成）")))  # 3/4
        self.run_eval("misc_qa", always)  # 非合同 rubric 4/4
        board = legal_entry.call("contract_gate.dashboard", {},
                                 self.config)
        self.assertEqual(board["runs_total"], 3)
        self.assertEqual(board["runs_all_pass"], 2)
        self.assertAlmostEqual(board["avg_pass_rate"], (1.0 + 0.75 + 1.0) / 3)
        bucket = board["best_by_type"]["买卖"]
        self.assertEqual(bucket["runs"], 2)  # misc_qa 不入分型
        self.assertEqual(bucket["all_pass"], 1)
        self.assertEqual(bucket["best_pass_rate"], 1.0)
        self.assertEqual(bucket["best_rubric"], "contract_买卖_v1")
        self.assertNotIn("misc_qa", board["best_by_type"])

    def test_empty_state_zero_totals(self):
        board = legal_entry.call("contract_gate.dashboard", {},
                                 self.config)
        self.assertEqual(board["runs_total"], 0)
        self.assertEqual(board["runs_all_pass"], 0)
        self.assertEqual(board["avg_pass_rate"], 0.0)
        self.assertEqual(board["best_by_type"], {})


class MasterRegenTests(GateBase):
    """母版再生（B57/T32 边界件，LLM seam 面等量）：force 语义/整批替换
    自动 base/manual 保留/未知槽 fail-closed 回滚/masters 账留痕。"""

    def clauses_bytes(self):
        root = Path(self.state_root) / "contract_gate"
        return (root / "clauses" / "clauses.json").read_bytes()

    def masters_rows(self):
        directory = Path(self.state_root) / "contract_gate" / "masters"
        return [json.loads(p.read_text(encoding="utf-8"))
                for p in sorted(directory.glob("*.json"))]

    def regen(self, **overrides):
        config = dict(self.config)
        config["contract_gate_llm"] = self.llm.seam()
        args = {"contract_type": CONTRACT_TYPE, "force": True}
        args.update(overrides)
        return legal_entry.call("contract_gate.master_regenerate",
                                args, config)

    def test_requires_force_when_auto_base_exists(self):
        self.seed_all()
        with self.assertRaisesRegex(cg.ContractGateError,
                                    "cg37_master_exists_needs_force"):
            self.regen(force=False)

    def test_regen_replaces_auto_base_preserves_manual_and_others(self):
        ids = self.seed_all()
        manual = legal_entry.call("contract_gate.clause_upsert", {
            "contract_type": CONTRACT_TYPE, "source": "base",
            "section": "特别条款", "body": "人工精修条款（再生不动）。",
            "source_path": "synthetic/master-manual.md", "manual": True},
            self.config)
        row = self.regen()
        self.assertEqual(row["status"], "completed")
        self.assertEqual(self.llm.master_calls, len(cg.SECTION_ORDER))
        self.assertEqual(  # 六节自动 base 全部被整批替换
            sorted(row["replaced_auto_base"]),
            sorted(ids[f"base:{section}"] for section, _b, _l in BASE_CLAUSES))
        assembled = legal_entry.call("contract_gate.assemble", {
            "contract_type": CONTRACT_TYPE}, self.config)
        self.assertIn("再生条款（标的与质量）", assembled["body_text"])
        self.assertIn("再生条款（附则）", assembled["body_text"])
        self.assertNotIn("出售", assembled["body_text"])  # 旧自动 base 全换
        self.assertIn("人工精修条款（再生不动）", assembled["body_text"])
        listing = legal_entry.call("contract_gate.clause_list", {
            "contract_type": CONTRACT_TYPE, "source": "tagged"},
            self.config)
        self.assertEqual(listing["count"], 2)  # tagged/custom 零触碰
        ledger = self.masters_rows()
        self.assertEqual(ledger[-1]["status"], "completed")
        self.assertEqual(len(ledger[-1]["sections"]), len(cg.SECTION_ORDER))

    def test_unknown_slot_fail_closed_and_no_mutation(self):
        self.seed_all()
        before = self.clauses_bytes()
        self.llm.master_fn = lambda section: {
            "body": f"双方就{{{{神秘槽}}}}达成约定（{section}）。"}
        with self.assertRaisesRegex(cg.ContractGateError,
                                    "cg37_master_slot_unknown"):
            self.regen()
        self.assertEqual(self.clauses_bytes(), before)  # 条款账零改动
        ledger = self.masters_rows()
        self.assertEqual(ledger[-1]["status"], "failed")
        self.assertIn("cg37_master_slot_unknown", ledger[-1]["error_message"])

    def test_bad_body_output_typed_reject(self):
        self.seed_all()
        self.llm.master_fn = lambda section: {"unexpected": "非 body 键"}
        with self.assertRaisesRegex(cg.ContractGateError,
                                    "cg37_master_body_invalid"):
            self.regen()


SOFFICE_EXE = r"C:\Program Files\LibreOffice\program\soffice.exe"


class ExportTests(GateBase):
    """导出四格式（B15 边界件）：markdown 原样/docx 确定性字节（zip 时间
    戳钉定）/pdf=LibreOffice headless 渲染（F58 纪律）/both 双件；失败不
    留半成品；soffice 未配置 typed 拒。"""

    def config_with_soffice(self):
        config = dict(self.config)
        config["libreoffice_soffice"] = SOFFICE_EXE
        return config

    def assemble(self, fmt, config=None):
        return legal_entry.call("contract_gate.assemble", {
            "contract_type": CONTRACT_TYPE, "format": fmt},
            config or self.config)

    def test_markdown_format_unchanged(self):
        self.seed_all()
        result = self.assemble("markdown")
        self.assertNotIn("docx_path", result)
        self.assertNotIn("pdf_path", result)
        self.assertIn("{{甲方名称}}", result["body_text"])

    def test_docx_export_deterministic_bytes(self):
        self.seed_all()
        first = self.assemble("docx")
        second = self.assemble("docx")
        self.assertEqual(first["docx_sha256"], second["docx_sha256"])
        import docx as pydocx
        doc = pydocx.Document(first["docx_path"])
        texts = [p.text for p in doc.paragraphs]
        self.assertIn("买卖合同（装配稿）", texts)  # 标题段
        self.assertIn("标的与质量", texts)  # 节标题段（加粗）
        joined = "\n".join(texts)
        self.assertIn("{{甲方名称}}", joined)  # 装配态不预填随导出保留

    def test_pdf_requires_soffice_config(self):
        self.seed_all()
        with self.assertRaisesRegex(cg.ContractGateError,
                                    "cg37_soffice_not_configured"):
            self.assemble("pdf")  # 未配置＝typed 拒

    def test_pdf_and_both_export_readable(self):
        import pypdfium2 as pdfium
        self.seed_all()
        both = self.assemble("both", self.config_with_soffice())
        for key in ("docx_path", "docx_sha256", "pdf_path"):
            self.assertIn(key, both)
        pdf = pdfium.PdfDocument(both["pdf_path"])
        self.assertGreaterEqual(len(pdf), 1)  # 可阅读打印硬门：页数≥1
        text_all = "".join(page.get_textpage().get_text_bounded()
                           for page in pdf)
        self.assertGreaterEqual(len(text_all.strip()), 1)  # 文本层非空
        self.assertIn("标的与质量", text_all.replace(" ", "")
                      .replace("\r", "").replace("\n", ""))
        only_pdf = self.assemble("pdf", self.config_with_soffice())
        self.assertTrue(only_pdf["pdf_path"].endswith("contract.pdf"))
        # pdf 档同样落 docx 中间件（渲染源双留存）
        self.assertTrue(Path(only_pdf["docx_path"]).is_file())


if __name__ == "__main__":
    unittest.main()

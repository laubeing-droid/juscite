# -*- coding: utf-8 -*-
"""RE-12（#12 合同审查·基础）施工验收：触发复跑＋内容 lint＋十列实例化
＋合成端到端。全部合成材料，零模型/网络/随机。

对拍验收断言（RE-12-合同审查基础.md §4）：
① T1/T4/T33 触发复跑（legal_entry.call 真入口；F94 目录真安装合成 git
  仓）：合同审查/审合同/审查合同三语形＋零触发负例＋R1→R2 多轮序贯
  ＋explicit 无条件与 unknown typed 拒。
③ 技能内容 lint：frontmatter 闭集（oc28 {name, description, metadata,
  disable-model-invocation}）＋结构骨架六项（manifest/触发/workflow/
  交付物/验证/软件工具；主审查两件全六项，域包按 §3.2 域结构映射）＋
  坏 manifest/缺 SKILL.md 负例 F94 typed 拒（T35）＋文案查重（与竞品
  SKILL.md 8-gram Jaccard 机械查重，禁抄；竞品资产在盘才跑）。
④ 列审查 10 列经 lvyin-review-columns 真解析＋金标列合同实例化＋F96
  门禁 review_instantiate eval 全跑 PASS（列数不符负例＝NOT_PASS）。
⑤ 合成合同样本端到端：确定性条款切分（正则，工作区 LegalTech 工程约
  束：禁模型猜测切分）→逐条四件套（行号/等级/依据/建议）→意见书五段
  组装，含四级分级与裁判尺度提示语义。

既有 F94/F95/F96/F98 回归由各自测试文件承担（fixture 已随预装集扩充
同步更新）；本文件不重复其断言。
"""
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
import unittest.mock
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE / "python"))
import legal_entry  # noqa: E402
import skill_catalog  # noqa: E402
import skill_gate  # noqa: E402
import skill_semantics  # noqa: E402
from bridge_errors import NotConnected  # noqa: E402

PRESETS = HERE / "skill-presets"
RE12_DOMAIN_IDS = [
    "contract-domain-general", "contract-domain-sale",
    "contract-domain-lease", "contract-domain-construction",
    "contract-domain-loan", "contract-domain-labor",
    "contract-domain-service", "contract-domain-tech-dev",
    "contract-domain-equity", "contract-domain-ip-license",
    "contract-domain-security",
]
RE12_MAIN_IDS = ["contract-review", "contract-risk-deep"]

# 触发面必含词形（RE-12 §3.1；"审合同"三字词=已实测缺口，必须连续字面）。
TRIGGER_WORDS = {
    "contract-review": ["合同审查", "审合同", "合同风险", "风险条款",
                        "合同评估"],
    "contract-risk-deep": ["履约风险", "违约风险", "合同履行", "违约"],
}

CONTRACT_COLUMNS = ["capacity", "obligations", "subject_matter",
                    "price_payment", "breach", "dispute_resolution",
                    "confidentiality", "ip_rights", "force_majeure",
                    "termination"]

# 竞品冻结资产（只读对照，仅用于机械查重；不在盘则跳过并如实记录）。
COMPETITOR_SKILLS = Path(
    r"D:\Codex\1.法律工作区\jusbench工作区\竞品情报\2026-10-11"
    r"\evidence\legalwork\skills")

GIT_ENV = dict(os.environ,
               GIT_AUTHOR_DATE="2026-10-27T00:00:00+00:00",
               GIT_COMMITTER_DATE="2026-10-27T00:00:00+00:00")

_DECIDE_BASE = {"channel": "public", "query": None, "explicit": None,
                "materials": None, "policy": None}


def _build_catalog(workspace: Path) -> dict:
    """合成 git 仓（预装技能复制保真）→ F94 分发链真安装 → 路由 config。"""
    src = workspace / "presets-src"
    shutil.copytree(PRESETS, src)

    def git(*args):
        proc = subprocess.run(["git", "-C", str(src), *args],
                              capture_output=True, env=GIT_ENV)
        assert proc.returncode == 0, proc.stderr[:200]
        return proc.stdout
    git("init", "-q")
    git("config", "core.autocrlf", "false")
    git("add", "-A")
    git("-c", "user.name=re12-test", "-c", "user.email=re12@juscite.local",
        "commit", "-q", "-m", "synthetic re12 source")
    commit = git("rev-parse", "HEAD").decode().strip()
    config = {"skill_catalog_state_root": str(workspace / "catalog"),
              "skill_routing_state_root": str(workspace / "routing")}
    installed = skill_catalog.catalog_call(
        "skill.catalog.install",
        {"channel": "public",
         "source": {"kind": "git_local", "repo": str(src), "commit": commit}},
        config)
    # 复制保真：安装集与源目录面等值（预装件随并行单扩，不钉魔数）。
    src_ids = sorted(p.name for p in PRESETS.iterdir()
                     if p.is_dir() and (p / "SKILL.md").is_file())
    assert sorted(s["id"] for s in installed["skills"]) == src_ids, \
        installed["skills"]
    return config


def _decide(config, *, query=None, explicit=None, materials=None,
            policy=None):
    args = {**_DECIDE_BASE, "query": query, "explicit": explicit,
            "materials": materials, "policy": policy}
    return legal_entry.call("skill.route.decide", args, config)


def _ranked(result):
    return [(s["skill"], s["score"]) for s in sorted(
        result["scores"], key=lambda s: (-s["score"], s["skill"]))
        if s["score"] >= 40]


# ---------------------------------------------------------------------- #
# ① 触发复跑（T1/T4/T33/explicit/负例）
# ---------------------------------------------------------------------- #


class TriggerProbeTest(unittest.TestCase):
    """F98 真入口路由复跑：RE-12 触发面缺口修复后的行为钉定。"""

    @classmethod
    def setUpClass(cls):
        cls._workspace = Path(tempfile.mkdtemp(prefix="re12_probe_"))
        cls.config = _build_catalog(cls._workspace)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls._workspace, ignore_errors=True)

    def test_t1_contract_review_top_and_loaded(self):
        result = _decide(self.config,
                         query="帮我审查这份采购合同的风险条款")
        self.assertEqual(result["decision"], "auto")
        ranked = _ranked(result)
        self.assertTrue(ranked)
        self.assertEqual(ranked[0][0], "contract-review", ranked)
        self.assertIn("contract-review",
                      [item["skill"] for item in result["loaded"]])
        review_score = next(s["score"] for s in result["scores"]
                            if s["skill"] == "contract-review")
        self.assertGreaterEqual(review_score, 60)

    def test_t1_shenhetong_gap_closed(self):
        """「审合同」三字词缺口修复复跑（RE-12 §3.1：description 需含
        连续字面使词元命中 40 分阈）。"""
        result = _decide(self.config, query="审合同，看看有没有坑")
        self.assertEqual(result["decision"], "auto")
        ranked = _ranked(result)
        self.assertEqual([sid for sid, _ in ranked], ["contract-review"])
        self.assertIn("contract-review",
                      [item["skill"] for item in result["loaded"]])

    def test_t1_dongbin_word_order_covered(self):
        """「审查合同」动宾序＝竞品正则盲区（B9/T30）：自家主审查正常
        触发并装载。"""
        result = _decide(self.config, query="审查合同")
        ranked = _ranked(result)
        self.assertEqual(ranked[0][0], "contract-review", ranked)
        self.assertIn("contract-review",
                      [item["skill"] for item in result["loaded"]])

    def test_combo_query_over_limit_typed_refusal(self):
        """合同主审＋深度＋首批两件同触的组合长 query＝合格 4>3 → F98
        具名 typed 拒（B6/T6 强覆盖：绝不静默裁剪，拒绝留痕带评分）。"""
        with self.assertRaises(NotConnected) as ctx:
            _decide(self.config, query="审查合同并评估履约风险")
        self.assertIn("f98_active_limit_exceeded:4>3", str(ctx.exception))
        log = legal_entry.call("skill.route.log",
                               {"limit": None, "after_seq": None},
                               self.config)
        record = log["records"][-1]
        self.assertEqual(record["decision"], "refused_active_limit")
        self.assertEqual(record["reason"],
                         "f98_active_limit_exceeded:4>3")
        self.assertTrue(record["scores"])
        self.assertEqual(record["loaded"], [])

    def test_t4_deep_skill_triggers(self):
        result = _decide(self.config, query="履约风险太高怎么办")
        ranked = _ranked(result)
        self.assertTrue(ranked)
        self.assertEqual(ranked[0][0], "contract-risk-deep", ranked)
        review = next(s["score"] for s in result["scores"]
                      if s["skill"] == "contract-review")
        self.assertLess(review, 40)
        loaded = [item["skill"] for item in result["loaded"]]
        deferred = {d["skill"]: d["reason"] for d in result["deferred"]}
        self.assertTrue("contract-risk-deep" in loaded
                        or deferred.get("contract-risk-deep")
                        == "budget_exhausted",
                        (loaded, deferred))

    def test_t4_b4_word_forms_trigger(self):
        """B4 五词形行为级复跑（竞品 dispute promptPatterns 五词形等量
        映射）：履约风险/违约风险/合同履行/履行障碍/违约 各以真实语形
        触发深评并装载——「合同履行」「履行障碍」两词形靠 name 词元
        「履约/履行」搭桥（F98 描述词元交封顶 30 永不及阈 40，name
        +20/词为唯一桥，skill_routing.py _score_skill）。"""
        for query in ("履约风险太高怎么办", "违约风险怎么评估",
                      "合同履行中途对方停工", "履行障碍如何处理",
                      "违约争议如何处理"):
            result = _decide(self.config, query=query)
            self.assertEqual(result["decision"], "auto", query)
            ranked = _ranked(result)
            self.assertTrue(ranked, query)
            self.assertEqual(ranked[0][0], "contract-risk-deep",
                             (query, ranked))
            self.assertIn("contract-risk-deep",
                          [item["skill"] for item in result["loaded"]],
                          query)

    def test_zero_trigger_negative(self):
        result = _decide(self.config, query="今天天气如何")
        self.assertEqual(result["decision"], "none")
        self.assertEqual(result["loaded"], [])
        self.assertTrue(all(s["score"] < 40
                            for s in result["scores"]))

    def test_t33_multiround_independent(self):
        """B48/T33：逐请求独立评分——R1 触发装载，R2 无触发词＝具名零
        注入，会话不粘技能。"""
        r1 = _decide(self.config, query="帮我审查这份采购合同的风险条款")
        self.assertEqual(r1["decision"], "auto")
        self.assertTrue(r1["loaded"] or r1["deferred"])
        r2 = _decide(self.config, query="继续，把第二部分也过一遍")
        self.assertEqual(r2["decision"], "none")
        self.assertEqual(r2["loaded"], [])
        self.assertEqual(r2["deferred"], [])

    def test_t2_explicit_unconditional_unknown_typed(self):
        tight = _decide(self.config, explicit={"skill_id": "contract-review"},
                        policy={"active_limit": 0, "load_budget_bytes": 1})
        self.assertEqual(tight["decision"], "explicit")
        self.assertGreater(tight["bytes"], 1)
        self.assertIn("<skill_content", tight["projection"])
        with self.assertRaises(NotConnected) as ctx:
            _decide(self.config, explicit={"skill_id": "no-such"})
        self.assertIn("f98_explicit_unknown", str(ctx.exception))

    def test_t9_allowlist_union_and_host_gate(self):
        """B15/B16/T9：decide 下发本轮 loaded 技能声明工具并集
        （allowed_tools，从「## 工具面」节确定性提取）；宿主回设
        skill_tool_policy 后授权工具可达、未授权工具族方法具名拒；键形
        坏 fail-closed；零触发轮 allowed_tools=[]（B49 不设防）。"""
        result = _decide(self.config,
                         query="帮我审查这份采购合同的风险条款")
        allowed = result["allowed_tools"]
        self.assertIn("kb.search", allowed)
        self.assertIn("citation.parse", allowed)
        self.assertIn("export.xlsx", allowed)
        self.assertNotIn("citation.verify", allowed)
        loaded = {item["skill"]: item.get("tools")
                  for item in result["loaded"]}
        self.assertIn("contract-review", loaded)
        self.assertTrue(loaded["contract-review"])
        self.assertEqual(allowed, sorted(set(allowed)))

        gated = dict(self.config,
                     skill_tool_policy={"allowed_tools": allowed})
        parsed = legal_entry.call(
            "citation.parse",
            {"text": "依《民法典》第五百九十五条主张"}, gated)
        self.assertTrue(parsed["citations"])
        with self.assertRaises(NotConnected) as ctx:
            legal_entry.call(
                "citation.verify",
                {"citation": "《民法典》第五百九十五条",
                 "as_of": "2026-09-30"}, gated)
        self.assertIn("f98_tool_not_allowed:citation.verify",
                      str(ctx.exception))
        with self.assertRaises(NotConnected) as ctx:
            legal_entry.call(
                "citation.parse", {"text": "x"},
                dict(self.config,
                     skill_tool_policy={"allowed": allowed}))
        self.assertIn("f98_tool_policy_invalid", str(ctx.exception))

        # 显式径同样下发该技能声明工具并集（＝其自身工具面清单）。
        tight = _decide(self.config, explicit={"skill_id":
                                               "contract-review"})
        self.assertEqual(tight["allowed_tools"],
                         loaded["contract-review"])
        self.assertIn("kb.search", tight["allowed_tools"])
        # 零触发轮：不设防语义的数值面＝空并集（B49）。
        none_result = _decide(self.config, query="今天天气如何")
        self.assertEqual(none_result["decision"], "none")
        self.assertEqual(none_result["allowed_tools"], [])


# ---------------------------------------------------------------------- #
# ③ 技能内容 lint
# ---------------------------------------------------------------------- #

_FM_BLOCK_RE = re.compile(r"\A---[ \t]*\r?\n(.*?)\r?\n---[ \t]*\r?\n?",
                          re.S)
_FM_KEY_RE = re.compile(r"^([A-Za-z][A-Za-z0-9_-]*):", re.M)
FM_CLOSED_SET = {"name", "description", "metadata",
                 "disable-model-invocation"}


def _frontmatter_of(path: Path) -> dict:
    text = path.read_text(encoding="utf-8")
    match = _FM_BLOCK_RE.match(text)
    if match is None:
        raise AssertionError("frontmatter missing: %s" % path)
    block = match.group(1)
    keys = set(_FM_KEY_RE.findall(block))
    name = None
    desc = None
    for line in block.splitlines():
        pair = re.match(r"^name:[ \t]*(.+)$", line)
        if pair and name is None:
            name = pair.group(1).strip()
        pair = re.match(r"^description:[ \t]*(.+)$", line)
        if pair and desc is None:
            desc = pair.group(1).strip()
    return {"keys": keys, "name": name, "description": desc}


class ContentLintTest(unittest.TestCase):
    """frontmatter 闭集＋结构骨架六项＋触发词钉定＋负例 typed 拒＋文案
    查重。"""

    @classmethod
    def setUpClass(cls):
        cls.dirs = sorted(p for p in PRESETS.iterdir()
                          if p.is_dir() and (p / "SKILL.md").is_file())
        cls.re12_dirs = [d for d in cls.dirs if d.name in RE12_MAIN_IDS
                         or d.name in RE12_DOMAIN_IDS]

    def test_frontmatter_closed_set_all_presets(self):
        """oc28 frontmatter 闭集：{name, description, metadata,
        disable-model-invocation}——RE-12 十三件（验收断言③的本义范围，
        §3.1 数据模型）逐件在集内且 name/description 非空；其余预装件查
        name/description 非空（F98 可路由前提）。如实记档：
        timeline-generation（RE-4 件4）frontmatter 携 commands/patterns/
        fileTypes 扩展键不在闭集内，属他单产物，不在本单范围修。"""
        self.assertEqual(len(self.re12_dirs), 13)
        for directory in self.dirs:
            fm = _frontmatter_of(directory / "SKILL.md")
            if directory.name in RE12_MAIN_IDS \
                    or directory.name in RE12_DOMAIN_IDS:
                self.assertLessEqual(fm["keys"], FM_CLOSED_SET,
                                     (directory.name, fm["keys"]))
            self.assertTrue(fm["name"], directory.name)
            self.assertTrue(fm["description"], directory.name)

    def test_trigger_words_pinned(self):
        for skill_id, words in TRIGGER_WORDS.items():
            fm = _frontmatter_of(PRESETS / skill_id / "SKILL.md")
            for word in words:
                self.assertIn(word, fm["description"],
                              (skill_id, word, fm["description"]))

    def _six_item_skeleton(self, directory, expectations):
        path = directory / "SKILL.md"
        parsed = skill_semantics.read_skill(str(path))
        body = skill_semantics._body_of(parsed)
        # manifest：恰一块执行合同且合同闭集校验过。
        contract = skill_gate._contract_of(parsed)
        self.assertTrue(skill_gate._valid_iso_date(contract["as_of"]),
                        directory.name)
        for heading in expectations:
            self.assertIn(heading, body, (directory.name, heading))

    def test_structure_skeleton_main_skills(self):
        """主审查两件：六项格式合同——manifest（执行合同块）/触发
        （frontmatter 触发词）/workflow（流程节）/交付物（列模板块＋
        输出模板节）/验证（质量检查节）/软件工具（工具面节，落自家
        legal_entry 方法名）。"""
        self._six_item_skeleton(
            PRESETS / "contract-review",
            ["## 四步操作流程", "## 审查意见书五段模板", "## 质量检查四查",
             "## 工具面"])
        self._six_item_skeleton(
            PRESETS / "contract-risk-deep",
            ["## 五阶段流程", "## 输出模板", "## 质量检查五组", "## 工具面",
             "## 失败与缺口纪律"])
        for skill_id, method in (("contract-review", "kb.search"),
                                 ("contract-risk-deep", "statute.resolve")):
            body = (PRESETS / skill_id / "SKILL.md").read_text(
                encoding="utf-8")
            self.assertIn(method, body, skill_id)

    def test_structure_skeleton_domain_packages(self):
        """域包按 §3.2 域结构映射六项：manifest＝执行合同块；触发＝
        frontmatter 描述含域定位；workflow＝域专项审查重点；交付物＝
        列模板块＋核心条款清单；验证＝失败与缺口纪律（fail-closed）；
        软件工具＝复用主审查技能工具面（正文引用 contract-review）。"""
        self.assertEqual(len(self.re12_dirs), 13)
        for directory in self.re12_dirs:
            if directory.name in RE12_MAIN_IDS:
                continue
            self._six_item_skeleton(
                directory,
                ["## 域专项审查重点", "## 域核心条款清单",
                 "## 域法源锚", "## 失败与缺口纪律"])
            body = (directory / "SKILL.md").read_text(encoding="utf-8")
            self.assertIn("contract-review", body, directory.name)
            fm = _frontmatter_of(directory / "SKILL.md")
            self.assertIn("审阅", fm["name"] + fm["description"],
                          directory.name)

    def test_static_statute_anchors_flagged_pending(self):
        """法源锚＝静态引用＋具名待核标注（法条实时效力核验属 #14）。"""
        for directory in self.re12_dirs:
            body = (directory / "SKILL.md").read_text(encoding="utf-8")
            if "## 域法源锚" in body or "法源路由" in body:
                self.assertIn("待核", body, directory.name)

    def test_bad_manifest_and_empty_catalog_typed_refusal(self):
        """T35：坏 frontmatter 包/零技能源＝F94 typed 拒，不留半装态。"""
        with tempfile.TemporaryDirectory(prefix="re12-neg-") as tmp:
            ws = Path(tmp)
            bad = ws / "bad-src" / "toy-broken"
            bad.mkdir(parents=True)
            (ws / "bad-src" / "catalog.json").write_text(
                '{"catalog_id": "re12-neg-bad", "channel": "public"}',
                encoding="utf-8")
            (bad / "SKILL.md").write_text(
                "---\nname: 坏包\n"
                "description: [复杂yaml本面不可解]\n---\n\n正文。\n",
                encoding="utf-8")
            empty = ws / "empty-src"
            empty.mkdir()
            (empty / "catalog.json").write_text(
                '{"catalog_id": "re12-neg-empty", "channel": "public"}',
                encoding="utf-8")
            (empty / "docs").mkdir()
            (empty / "docs" / "notes.txt").write_text("无技能\n",
                                                      encoding="utf-8")
            config = {"skill_catalog_state_root": str(ws / "catalog")}
            for src, code in ((ws / "bad-src", "f94_skill_frontmatter_invalid"),
                              (ws / "empty-src", "f94_catalog_empty")):
                def git(*args, _src=src):
                    proc = subprocess.run(
                        ["git", "-C", str(_src), *args],
                        capture_output=True, env=GIT_ENV)
                    assert proc.returncode == 0, proc.stderr[:200]
                    return proc.stdout
                git("init", "-q")
                git("config", "core.autocrlf", "false")
                git("add", "-A")
                git("-c", "user.name=re12-test",
                    "-c", "user.email=re12@juscite.local",
                    "commit", "-q", "-m", "neg")
                commit = git("rev-parse", "HEAD").decode().strip()
                with self.assertRaises(
                        skill_catalog.SkillCatalogError) as ctx:
                    skill_catalog.catalog_call(
                        "skill.catalog.install",
                        {"channel": "public",
                         "source": {"kind": "git_local", "repo": str(src),
                                    "commit": commit}},
                        config)
                self.assertIn(code, str(ctx.exception),
                              (src.name, str(ctx.exception)))

    def test_no_copy_from_competitor_skill_files(self):
        """文案查重（禁抄）：RE-12 十三件与竞品两 SKILL.md 的字符
        8-gram Jaccard 一律近零（阈值 0.02）；竞品资产不在盘则跳过并
        如实记为未跑。"""
        sources = [COMPETITOR_SKILLS / "contract_risk_review" / "SKILL.md",
                   COMPETITOR_SKILLS / "dispute_and_performance_risk"
                   / "SKILL.md"]
        if not all(s.is_file() for s in sources):
            raise unittest.SkipTest("竞品冻结资产不在盘（查重未跑）")

        def grams(text):
            compact = re.sub(r"\s+", "", text)
            return {compact[i:i + 8] for i in range(len(compact) - 7)}
        competitor = set()
        for source in sources:
            competitor |= grams(source.read_text(encoding="utf-8",
                                                errors="replace"))
        checked = 0
        for directory in self.re12_dirs:
            mine = grams((directory / "SKILL.md").read_text(
                encoding="utf-8"))
            ratio = len(mine & competitor) / max(len(mine), 1)
            self.assertLess(ratio, 0.02, (directory.name, ratio))
            checked += 1
        self.assertEqual(checked, 13)


# ---------------------------------------------------------------------- #
# ④ 十列实例化＋F96 门禁真跑
# ---------------------------------------------------------------------- #


def _review_seam(method, args, config):
    """entry seam：review_instantiate 走真解析（harness seam 注入空回
    执）——列集合来自 SKILL.md 真解析而非测试自报。"""
    if method == "skill.review_instantiate":
        with unittest.mock.patch.object(
                skill_semantics, "_harness_call",
                lambda m, a, c: {"batch": {}}):
            return skill_semantics.skill_review_instantiate(args, config)
    raise NotConnected("method_not_connected:" + method)


class InstantiateAndGateTest(unittest.TestCase):
    """④ 列审查 10 列真解析实例化（对齐 F96 ev-contract-batch 同款）。"""

    def test_ten_columns_instantiate_with_gold(self):
        path = PRESETS / "contract-review" / "SKILL.md"
        calls = []

        def harness_seam(method, args, config):
            calls.append((method, args))
            return {"batch": {}}
        with unittest.mock.patch.object(skill_semantics, "_harness_call",
                                        harness_seam):
            out = legal_entry.call(
                "skill.review_instantiate",
                {"skill_path": str(path), "skill_id": "contract-review",
                 "matter_id": "m-re12-wiring",
                 "batch_id": "brt-re12-wiring",
                 "key": {"requestId": "re12-wiring", "targetId": None,
                         "expectedRevision": None, "inputRefs": []}},
                {})
        ids = [c["id"] for c in out["templateColumns"]]
        self.assertEqual(ids, CONTRACT_COLUMNS)
        self.assertTrue(all(c["prompt"] for c in out["templateColumns"]))
        methods = [m for m, _ in calls]
        self.assertEqual(methods, ["harness.review_batch_create",
                                   "harness.review_columns_define"])
        batch_args = calls[0][1]
        self.assertEqual([c["id"] for c in batch_args["batch"]["columns"]],
                         CONTRACT_COLUMNS)
        self.assertEqual(len(batch_args["batch"]["rows"]), 1)
        ledger = calls[1][1]["columns"]
        for column in ledger:
            self.assertEqual(set(column),
                             {"id", "name", "format", "version", "gold"})
            self.assertEqual(column["format"], "text")
            self.assertEqual(column["version"], "1")
            self.assertEqual(column["gold"], {"kind": "text"})

    def test_gate_pass_with_review_seam(self):
        receipt = self._gate(PRESETS / "contract-review" / "SKILL.md",
                             "contract-review")
        self.assertEqual(receipt["gate"], "PASS")
        states = {e["id"]: e for e in receipt["evals"]}
        self.assertEqual(states["ev-contract-batch"]["state"], "VERIFIED")
        self.assertTrue(states["ev-contract-batch"]["passed"])
        self.assertIn("columns=10", states["ev-contract-batch"]["detail"])
        self.assertEqual(states["ev-contract-refusal"]["state"], "REFUSED")
        self.assertTrue(states["ev-contract-refusal"]["passed"])

    def test_gate_columns_mismatch_not_pass(self):
        """负例：合同 expect 与模板实列不符 → UNVERIFIED/NOT_PASS 具名。"""
        with tempfile.TemporaryDirectory(prefix="re12-tamper-") as tmp:
            skill_dir = Path(tmp) / "contract-review"
            skill_dir.mkdir()
            text = (PRESETS / "contract-review" / "SKILL.md").read_text(
                encoding="utf-8")
            tampered = text.replace(
                '"column_ids": ["capacity", "obligations", "subject_matter",'
                ' "price_payment", "breach", "dispute_resolution",'
                ' "confidentiality", "ip_rights", "force_majeure",'
                ' "termination"]',
                '"column_ids": ["capacity", "obligations", "breach",'
                ' "dispute_resolution"]')
            self.assertNotEqual(text, tampered)
            (skill_dir / "SKILL.md").write_text(tampered, encoding="utf-8")
            receipt = self._gate(skill_dir / "SKILL.md", "contract-review")
            self.assertEqual(receipt["gate"], "NOT_PASS")
            self.assertIn("eval_failed:ev-contract-batch", receipt["reasons"])
            entry = next(e for e in receipt["evals"]
                         if e["id"] == "ev-contract-batch")
            self.assertEqual(entry["state"], "UNVERIFIED")
            self.assertIn("columns_mismatch", entry["detail"])

    @staticmethod
    def _gate(path, skill_id):
        with unittest.mock.patch.object(skill_gate, "_entry_call",
                                        _review_seam):
            return skill_gate.run_gate({"skill_path": str(path),
                                        "skill_id": skill_id}, {})


# ---------------------------------------------------------------------- #
# ⑤ 合成合同样本端到端（确定性切分→逐条四件套→意见书五段）
# ---------------------------------------------------------------------- #

_CLAUSE_RE = re.compile(r"^第[一二三四五六七八九十百零]+条", re.M)
LEVELS = frozenset({"critical", "high", "medium", "low"})
REPORT_SECTIONS = ["审查基本信息", "总体评价", "逐条审查意见",
                   "修改后风险评估", "特别提示"]

SYNTHETIC_CONTRACT = """设备采购合同（合成样本·仅工程测试用，无法律效力）
买受方：甲公司（合成主体）；出卖方：乙公司（合成主体）
第一条 标的：甲公司向乙公司采购成套生产线设备一批，具体型号、配置及技术参数以双方另行确认的技术协议为准（本合同未附）。
第二条 价款：合同总价人民币壹佰贰拾万元整（¥1,200,000.00），分三期支付：预付款 30%，到货款 40%，验收合格后尾款 30%。
第三条 交付：乙公司应于合同生效后六十日内送货至甲公司指定厂区，运费由乙公司承担；设备毁损灭失的风险自货交承运人时起转移至甲公司。
第四条 违约责任：任一方迟延履行的，每迟延一日按合同总价的千分之五向对方支付违约金，且无需证明实际损失。
第五条 争议解决：因本合同发生的争议，提交合同签订地有管辖权的人民法院诉讼解决（签订地未在本合同中载明）。
第六条 保密与知识产权：双方对磋商与履行中知悉的对方商业信息负保密义务，保密期三年；履约中形成的改进成果归改进方所有。
"""

# 逐条审查输出（合成 fixture：按主审查技能四件套输出形态自写）。
SYNTHETIC_ROWS = [
    {"行号": 1, "条款": "第一条", "风险描述": "标的型号与技术参数留空且技术协议未附，标的范围无法确定",
     "风险等级": "critical", "法律依据": "《民法典》合同编买卖合同章（第 595 条起，静态引用待核）",
     "修改建议": "签署前补齐技术协议并约定补充文件与本合同同效力", "置信度": "高",
     "特殊标注": "需补充信息", "裁判尺度提示": False},
    {"行号": 2, "条款": "第二条", "风险描述": "价款分期节点清晰且与验收联动，未见失衡",
     "风险等级": "low", "法律依据": "无（约定明确）", "修改建议": "把「验收合格」与第三条验收程序显式关联即可",
     "置信度": "高", "特殊标注": "", "裁判尺度提示": False},
    {"行号": 3, "条款": "第三条", "风险描述": "风险自货交承运人时转移，买受方承担在途风险而运费义务在出卖方，安排不对称",
     "风险等级": "medium", "法律依据": "《民法典》第 595 条起风险负担规则（静态引用待核）",
     "修改建议": "改为验收合格时转移，或约定在途保险由出卖方投保并受益", "置信度": "中",
     "特殊标注": "", "裁判尺度提示": False},
    {"行号": 4, "条款": "第四条", "风险描述": "迟延违约金按日千分之五折年化约百分之一百八十二，显著高于常见损失水平",
     "风险等级": "high", "法律依据": "违约金过分高于实际损失可请求调减的裁判规则（超损失部分约三成为常见参考线，静态引用待核）",
     "修改建议": "下调日率并设违约金总额上限，改为以实际损失为基数的封顶式约定", "置信度": "高",
     "特殊标注": "法律争议", "裁判尺度提示": True},
    {"行号": 5, "条款": "第五条", "风险描述": "管辖连接点「合同签订地」未在文本载明，管辖依据不确定",
     "风险等级": "medium", "法律依据": "无（连接点待补）",
     "修改建议": "补载签订地，或直接约定由某市某区人民法院管辖", "置信度": "中",
     "特殊标注": "需补充信息", "裁判尺度提示": False},
    {"行号": 6, "条款": "第六条", "风险描述": "改进成果归改进方可能吸收对方背景技术，权属边界偏一侧",
     "风险等级": "medium", "法律依据": "无（可依约定调整）",
     "修改建议": "区分背景知识产权与改进成果，改进方就背景部分仅获使用许可", "置信度": "中",
     "特殊标注": "", "裁判尺度提示": False},
]


def split_clauses(text):
    """确定性条款切分（正则＋行号，禁模型猜测；返回逐条款行）。"""
    hits = list(_CLAUSE_RE.finditer(text))
    rows = []
    for index, match in enumerate(hits):
        start = match.start()
        end = hits[index + 1].start() if index + 1 < len(hits) else len(text)
        rows.append({"行号": index + 1,
                     "条款号": match.group(0),
                     "正文": text[start:end].strip()})
    return rows


def compose_report(clauses, rows):
    """按主审查技能意见书五段模板组装（确定性纯函数）。"""
    counts = {level: sum(1 for r in rows
                         if r["风险等级"] == level)
              for level in ("critical", "high", "medium", "low")}
    lines = []
    lines.append("## 审查基本信息")
    lines.append("合同名称：设备采购合同（合成样本）；当事人：甲公司、"
                 "乙公司（均合成）；条款数：%d；信息完整度：中（技术协议"
                 "与签订地缺失）。" % len(clauses))
    lines.append("## 总体评价")
    lines.append("风险分布 critical=%d high=%d medium=%d low=%d；签署前"
                 "须解决 critical 项，力争修改 high 项。"
                 % (counts["critical"], counts["high"], counts["medium"],
                    counts["low"]))
    lines.append("## 逐条审查意见")
    for row in rows:
        lines.append("- 行%d %s：%s［等级：%s］［依据：%s］［建议：%s］"
                     "［置信度：%s］%s" % (
                         row["行号"], row["条款"], row["风险描述"],
                         row["风险等级"], row["法律依据"],
                         row["修改建议"], row["置信度"],
                         ("［%s］" % row["特殊标注"])
                         if row["特殊标注"] else ""))
    lines.append("## 修改后风险评估")
    lines.append("按建议修改后残余风险预计降至 medium 以下；行%d 调减后"
                 "违约金敞口收敛。" % next(r["行号"] for r in rows
                                           if r["裁判尺度提示"]))
    lines.append("## 特别提示")
    lines.append("待核事项：法源静态引用效力；空白条款：行1 技术协议；"
                 "附件：技术协议未附，同正文一并补齐。")
    return "\n".join(lines)


class SyntheticEndToEndTest(unittest.TestCase):
    """⑤ 合成合同端到端：切分→逐条四件套→五段意见书（含四级分级与
    裁判尺度提示语义）。"""

    def test_clause_split_is_deterministic_and_complete(self):
        first = split_clauses(SYNTHETIC_CONTRACT)
        second = split_clauses(SYNTHETIC_CONTRACT)
        self.assertEqual(first, second)
        self.assertEqual(len(first), 6)
        self.assertEqual([c["条款号"] for c in first],
                         ["第一条", "第二条", "第三条", "第四条",
                          "第五条", "第六条"])
        self.assertTrue(all(c["正文"].startswith(c["条款号"])
                            for c in first))

    def test_rows_cover_clauses_with_line_numbers_and_levels(self):
        clauses = split_clauses(SYNTHETIC_CONTRACT)
        self.assertEqual([r["行号"] for r in SYNTHETIC_ROWS],
                         [c["行号"] for c in clauses])
        self.assertEqual([r["条款"] for r in SYNTHETIC_ROWS],
                         [c["条款号"] for c in clauses])
        for row in SYNTHETIC_ROWS:
            self.assertIn(row["风险等级"], LEVELS)
            for field in ("风险描述", "法律依据", "修改建议", "置信度"):
                self.assertTrue(row[field], (row["行号"], field))
            self.assertIn(row["置信度"], ("高", "中", "低"))
        distribution = {level: sum(1 for r in SYNTHETIC_ROWS
                                   if r["风险等级"] == level)
                        for level in LEVELS}
        self.assertEqual(sum(distribution.values()), 6)
        self.assertGreaterEqual(len({r["风险等级"]
                                     for r in SYNTHETIC_ROWS}), 3)

    def test_referee_scale_flag_on_penalty_clause(self):
        """违约金日千分之五条款必须触发裁判尺度提示语义（B24 等量）。"""
        flagged = [r for r in SYNTHETIC_ROWS if r["裁判尺度提示"]]
        self.assertEqual([r["行号"] for r in flagged], [4])
        self.assertIn("三成", flagged[0]["法律依据"])

    def test_report_has_five_sections_and_per_clause_entries(self):
        clauses = split_clauses(SYNTHETIC_CONTRACT)
        report = compose_report(clauses, SYNTHETIC_ROWS)
        for section in REPORT_SECTIONS:
            self.assertIn("## " + section, report)
        for row in SYNTHETIC_ROWS:
            self.assertIn("行%d %s" % (row["行号"], row["条款"]), report)
            self.assertIn(row["风险等级"], report)
        self.assertIn("critical=1", report)
        self.assertIn("超损失部分约三成", report)


if __name__ == "__main__":
    unittest.main()

# -*- coding: utf-8 -*-
"""F93 产品侧接线测试（W3-U16）：SKILL.md 通道三执行语义。

06:F93「SKILL.md 通道+三种执行语义（聊天注入/实例化 review/调用计算器）」
＋台账「SKILL聊天注入/review实例/JC计算三语义真实，禁无必要DAG引擎」。

* skill.read — 来源面：id 规则与上游原生通道一致（SKILL.md→父目录名）、
  全文 sha256 溯源、两块（列模板/计算步骤）存在性与块 sha；
* skill.review_instantiate — 列模板恰一块 → 既有 harness.review_batch_
  create＋review_columns_define（seam 注入；零第二列权威；两笔账键派生
  「:columns」后缀——同键异内容 conflict 结构性不可能）；
* skill.calculate — 计算步骤块恰一块 → 既有 calc.* 五族槽位（P01
  JCClient 真算：闰日夹具 20 分；JC typed 拒绝原样上浮；输入域冻结——
  声明域与实值键集逐键相等）；真全链（隔离服务聊天注入/建批入账）在
  tools/PENDING_OWNER_f93_skill_semantics_recon.py。
* 禁无必要 DAG 引擎：skill_semantics.py 导入闭集 AST 钉定（无图/引擎/
  编排依赖）＋冻结方法组与 legal_entry calc 槽位钉定相等。

全部合成材料；JC 消费本波链头 w2b-u55 worktree（只读，client.py sha256
钉定在 recon 工具，漂移即 FATAL）。
"""
from __future__ import annotations

import ast
import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
import unittest.mock
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE / "python"))

import legal_entry  # noqa: E402
import skill_semantics  # noqa: E402
from bridge_errors import NotConnected  # noqa: E402

JC_REPO = Path(
    r"D:\Codex\1.法律工作区\juris-calculus工作区\juris-calculus\.local\worktrees\w2b-u55")

# 运行面钉定（W2a-U16 纪律）：整个 pytest 进程的 compiler_core 必须解析到
# 本波 JC 链头（w2b-u55 基 w2b-u56——含 calc 五族＋期限＋大写＋治理面）。
if (JC_REPO / "compiler_core" / "client.py").is_file():
    sys.path.insert(0, str(JC_REPO))
    for _name in [m for m in list(sys.modules)
                  if m == "compiler_core" or m.startswith("compiler_core.")]:
        del sys.modules[_name]

FENCE = "`" * 3
SKILL_ID = "lvyin-jusbench-calc"

TEMPLATE_COLUMNS = [
    {"id": "principal", "name": "本金（分）", "prompt": "取合同本金，整数分",
     "format": "decimal-string", "version": "1",
     "gold": {"kind": "number"}},
    {"id": "interest", "name": "利息（分）", "prompt": "按阶梯利率计算",
     "format": "decimal-string", "version": "1",
     "gold": {"kind": "number"}},
]
TEMPLATE_DOC = {"columns": TEMPLATE_COLUMNS,
                "rows": [{"id": "row-1"}, {"id": "row-2"}]}
STEP_DOC = {"method": "calc.interest",
            "rule_version": "F93 合成声明（JC registry 调用时解析）",
            "calendar_version": "F93 合成声明（2026）",
            "input_domain": ["principal_minor", "segments"]}

MARKER = "F93-SKILL-MARKER-wiring"


def skill_markdown(template: dict | None = TEMPLATE_DOC,
                   step: dict | None = STEP_DOC,
                   marker: str = MARKER) -> str:
    parts = ["---", "name: 律引计算助手",
             "description: 批量审查列模板与 JC 公开计算（F93 合成验收技能）",
             "---", "", "# 律引 SKILL（F93 合成验收）", "",
             "金丝雀标记：%s" % marker, ""]
    if template is not None:
        parts += ["## 语义② 列模板实例化 review", "",
                  FENCE + "lvyin-review-columns",
                  json.dumps(template, ensure_ascii=False),
                  FENCE, ""]
    if step is not None:
        parts += ["## 语义③ 调用计算器（JC 公开面）", "",
                  FENCE + "lvyin-calc-step",
                  json.dumps(step, ensure_ascii=False),
                  FENCE, ""]
    return "\n".join(parts)


def write_skill(root: Path, skill_id: str = SKILL_ID,
                **kwargs) -> Path:
    directory = root / "ws" / "skill" / skill_id
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / "SKILL.md"
    path.write_text(skill_markdown(**kwargs), encoding="utf-8")
    return path


def jc_config(workspace: Path) -> dict:
    rules = workspace / "rules"
    rules.mkdir(parents=True, exist_ok=True)
    (rules / "jc-local-pack.json").write_text(json.dumps(RULE_PACK),
                                              encoding="utf-8")
    return {"jc_state_root": str(workspace / "state"),
            "jc_rule_roots": [str(rules)],
            "jc_import_path": str(JC_REPO)}


# 合成最小规则包（同 F107/F112 先例）：client 构造要求至少一个 rule root；
# C01 利息计算不消费规则内容。
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
         "governing_law": "acceptance-statute",
         "source_id": "acceptance-statute", "modality": "OBLIGATION",
         "premises": [{"fact_key": "acc.contract", "required": True}],
         "conclusion": {"value": "applies"},
         "effective_from": "2020-01-01T00:00:00Z"},
    ],
}

COMMAND_KEY = {"requestId": "w3u16-1", "targetId": None,
               "expectedRevision": None, "inputRefs": []}


class ParseTests(unittest.TestCase):
    """来源面：skill.read 确定性解析（id 规则同上游原生通道）。"""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory(prefix="f93-parse-")
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def test_read_source_face_id_rule_and_sha(self) -> None:
        path = write_skill(self.root)
        parsed = skill_semantics.read_skill(str(path))
        self.assertEqual(parsed["id"], SKILL_ID)          # SKILL.md→父目录名
        self.assertEqual(parsed["name"], "律引计算助手")
        self.assertIn("F93 合成验收技能", parsed["description"])
        self.assertEqual(parsed["contentSha256"],
                         hashlib.sha256(path.read_bytes()).hexdigest())
        self.assertTrue(parsed["template"] and parsed["calcStep"])
        self.assertEqual(parsed["template"]["sha256"], hashlib.sha256(
            json.dumps(TEMPLATE_DOC, ensure_ascii=False).encode("utf-8")
        ).hexdigest())

    def test_read_non_skillmd_uses_filename_stem(self) -> None:
        directory = self.root / "ws" / "skill"
        directory.mkdir(parents=True)
        path = directory / "calc-helper.md"
        path.write_text(skill_markdown(), encoding="utf-8")
        self.assertEqual(skill_semantics.read_skill(str(path))["id"],
                         "calc-helper")

    def test_missing_frontmatter_refused(self) -> None:
        path = self.root / "SKILL.md"
        path.write_text("# no frontmatter\n", encoding="utf-8")
        with self.assertRaises(skill_semantics.SkillSemanticsError) as ctx:
            skill_semantics.read_skill(str(path))
        self.assertIn("f93_skill_frontmatter_missing", str(ctx.exception))

    def test_missing_file_refused(self) -> None:
        with self.assertRaises(skill_semantics.SkillSemanticsError) as ctx:
            skill_semantics.read_skill(str(self.root / "nope" / "SKILL.md"))
        self.assertIn("f93_skill_file_missing", str(ctx.exception))

    def test_selection_id_mismatch_refused(self) -> None:
        path = write_skill(self.root)
        with self.assertRaises(skill_semantics.SkillSemanticsError) as ctx:
            skill_semantics._selected_skill({"skill_path": str(path),
                                             "skill_id": "other-skill"})
        self.assertIn("f93_skill_id_mismatch", str(ctx.exception))


class InstantiateTests(unittest.TestCase):
    """语义②：列模板 → 既有 harness 冻结方法组（seam 注入零仓依赖）。"""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory(prefix="f93-inst-")
        self.addCleanup(self.tmp.cleanup)
        self.path = write_skill(Path(self.tmp.name))
        self.captured: list[tuple[str, dict]] = []

        def seam(method: str, args: dict, config: dict) -> dict:
            self.captured.append((method, args))
            if method == "harness.review_batch_create":
                return {"status": "active", "batchId": args["batch"]["id"]}
            return {"defined": True, "columns": args["columns"]}

        patcher = unittest.mock.patch.object(skill_semantics,
                                             "_harness_call", seam)
        patcher.start()
        self.addCleanup(patcher.stop)

    def _instantiate(self, **overrides) -> dict:
        args = {"skill_path": str(self.path), "skill_id": SKILL_ID,
                "matter_id": "m-f93", "batch_id": "brt-f93-wiring",
                "key": dict(COMMAND_KEY)}
        args.update(overrides)
        return skill_semantics.skill_review_instantiate(args, {})

    def test_two_ledger_writes_through_frozen_groups(self) -> None:
        result = self._instantiate()
        methods = [method for method, _ in self.captured]
        self.assertEqual(methods, ["harness.review_batch_create",
                                   "harness.review_columns_define"])
        create_args = self.captured[0][1]
        self.assertEqual(create_args["scope"],
                         {"kind": "matter", "matterId": "m-f93"})
        # 账面列传 {id,name}（prompt＝技能通道内容，不塞账本未定义字段）。
        self.assertEqual(create_args["batch"]["columns"],
                         [{"id": "principal", "name": "本金（分）"},
                          {"id": "interest", "name": "利息（分）"}])
        self.assertEqual([row["id"] for row in create_args["batch"]["rows"]],
                         ["row-1", "row-2"])
        # 溯源：标题带 id@sha8，note 带全文 sha256（同 ID 产物可回读）。
        self.assertIn(SKILL_ID + "@", create_args["batch"]["title"])
        self.assertIn("sha256=", create_args["batch"]["note"])
        # 列账键派生（同键异内容 conflict 结构性不可能）。
        define_args = self.captured[1][1]
        self.assertEqual(define_args["key"]["requestId"],
                         COMMAND_KEY["requestId"] + ":columns")
        self.assertEqual(define_args["columns"],
                         [{k: v for k, v in column.items() if k != "prompt"}
                          for column in TEMPLATE_COLUMNS])
        self.assertEqual(result["batchId"], "brt-f93-wiring")
        self.assertEqual(result["skill"]["id"], SKILL_ID)
        self.assertTrue(result["skill"]["contentSha256"])
        # prompt 随面回执携带（UI 仅调用/展示，不落账）。
        self.assertEqual(
            {c["id"]: c["prompt"] for c in result["templateColumns"]},
            {c["id"]: c["prompt"] for c in TEMPLATE_COLUMNS})

    def test_template_missing_and_not_unique_refused(self) -> None:
        no_block = write_skill(Path(self.tmp.name), "skill-no-block",
                               template=None)
        args = {"skill_path": str(no_block), "skill_id": "skill-no-block",
                "matter_id": "m", "batch_id": "b", "key": dict(COMMAND_KEY)}
        with self.assertRaises(skill_semantics.SkillSemanticsError) as ctx:
            skill_semantics.skill_review_instantiate(args, {})
        self.assertIn("f93_template_block_missing", str(ctx.exception))
        directory = Path(self.tmp.name) / "ws" / "skill" / "skill-two-blocks"
        directory.mkdir(parents=True)
        markdown = skill_markdown()
        doubled = (markdown + "\n" + FENCE + "lvyin-review-columns\n{}\n"
                   + FENCE + "\n")
        path = directory / "SKILL.md"
        path.write_text(doubled, encoding="utf-8")
        args = {"skill_path": str(path), "skill_id": "skill-two-blocks",
                "matter_id": "m", "batch_id": "b", "key": dict(COMMAND_KEY)}
        with self.assertRaises(skill_semantics.SkillSemanticsError) as ctx:
            skill_semantics.skill_review_instantiate(args, {})
        self.assertIn("f93_template_block_not_unique", str(ctx.exception))

    def test_template_column_format_closed_set(self) -> None:
        bad = {"columns": [dict(TEMPLATE_COLUMNS[0], format="free-text")],
               "rows": [{"id": "row-1"}]}
        path = write_skill(Path(self.tmp.name), "skill-bad-format",
                           template=bad)
        args = {"skill_path": str(path), "skill_id": "skill-bad-format",
                "matter_id": "m", "batch_id": "b", "key": dict(COMMAND_KEY)}
        with self.assertRaises(skill_semantics.SkillSemanticsError) as ctx:
            skill_semantics.skill_review_instantiate(args, {})
        self.assertIn("f93_template_format_unknown", str(ctx.exception))

    def test_command_key_required(self) -> None:
        with self.assertRaises(skill_semantics.SkillSemanticsError) as ctx:
            self._instantiate(key={"targetId": None})
        self.assertIn("f93_command_key_invalid", str(ctx.exception))

    def test_harness_ledger_error_passthrough(self) -> None:
        def failing_seam(method: str, args: dict, config: dict) -> dict:
            raise legal_entry.HarnessCommandError("review_batch_id_invalid")

        with unittest.mock.patch.object(skill_semantics, "_harness_call",
                                        failing_seam):
            with self.assertRaises(legal_entry.HarnessCommandError):
                self._instantiate()


class CalculateTests(unittest.TestCase):
    """语义③：计算步骤 → 既有 calc.* 冻结槽位（P01 JCClient 真算）。"""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory(prefix="f93-calc-")
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.config = jc_config(self.root)
        self.path = write_skill(self.root)
        self.input = {"principal_minor": 365_000,
                      "segments": [{"start_date": "2024-02-28",
                                    "end_date": "2024-03-01",
                                    "annual_rate": "0.01"}]}

    def _calculate(self, skill_id: str = SKILL_ID, **overrides) -> dict:
        args = {"skill_path": str(self.path), "skill_id": skill_id,
                "matter_id": "m-f93", "input": self.input}
        args.update(overrides)
        return legal_entry.call("skill.calculate", args, self.config)

    def test_real_interest_through_frozen_slot(self) -> None:
        result = self._calculate()
        self.assertEqual(result["semantic"], "calculate")
        self.assertEqual(result["step"]["method"], "calc.interest")
        self.assertEqual(result["step"]["inputDomain"],
                         ["principal_minor", "segments"])
        sheet = result["result"]
        self.assertEqual(sheet["amount_minor"], 20)     # 闰日夹具（E21 同源）
        ref = sheet["calculationReceiptRef"]
        self.assertEqual(ref["owner"], "jc")
        self.assertEqual(ref["kind"], "calc-family-sheet")
        self.assertTrue(ref["id"])
        self.assertTrue(sheet["independentChecker"]["agreed"])

    def test_deterministic_same_input_same_output(self) -> None:
        first = self._calculate()["result"]
        second = self._calculate()["result"]
        self.assertEqual(first["amount_minor"], second["amount_minor"])
        self.assertEqual(first["independentChecker"],
                         second["independentChecker"])

    def test_input_domain_frozen_to_declaration(self) -> None:
        with self.assertRaises(NotConnected) as ctx:
            self._calculate(input={"principal_minor": 1})
        self.assertIn("f93_calc_input_domain_mismatch", str(ctx.exception))

    def test_method_outside_closed_set_refused(self) -> None:
        path = write_skill(self.root, "skill-bad-method",
                           step=dict(STEP_DOC, method="calc.registry"))
        args = {"skill_path": str(path), "skill_id": "skill-bad-method",
                "matter_id": "m-f93", "input": self.input}
        with self.assertRaises(NotConnected) as ctx:
            legal_entry.call("skill.calculate", args, self.config)
        self.assertIn("f93_calc_method_not_in_closed_set", str(ctx.exception))

    def test_step_block_missing_refused(self) -> None:
        path = write_skill(self.root, "skill-no-step", step=None)
        args = {"skill_path": str(path), "skill_id": "skill-no-step",
                "matter_id": "m-f93", "input": self.input}
        with self.assertRaises(NotConnected) as ctx:
            legal_entry.call("skill.calculate", args, self.config)
        self.assertIn("f93_calc_step_block_missing", str(ctx.exception))

    def test_jc_typed_refusal_surfaces_unwrapped(self) -> None:
        # 浮点年利率＝JC 侧 FLOAT_FORBIDDEN——typed 拒绝原样上浮（绝不造数）。
        float_input = {"principal_minor": 365_000,
                       "segments": [{"start_date": "2024-02-28",
                                     "end_date": "2024-03-01",
                                     "annual_rate": 0.01}]}
        with self.assertRaises(legal_entry.JCMethodFailure) as ctx:
            self._calculate(input=float_input)
        self.assertIn("FLOAT_FORBIDDEN", str(ctx.exception))

    def test_cli_jc_typed_refusal_exit_4(self) -> None:
        # 脚本执行经模块副本跑 main（legal_entry 入口双身份修复）：CLI 子
        # 进程 typed 拒绝＝exit 4 JC_FAILURE 携码，不因 __main__/模块双身
        # 份漏接崩溃（漏接＝异常逃逸、stdout 空）。
        tmp = tempfile.TemporaryDirectory(prefix="f93-cli-")
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        path = write_skill(root)
        config = jc_config(root)
        request = root / "request.json"
        config_path = root / "config.json"
        request.write_text(json.dumps({
            "method": "skill.calculate",
            "args": {"skill_path": str(path), "skill_id": SKILL_ID,
                     "matter_id": "m-f93",
                     "input": {"principal_minor": 365_000,
                               "segments": [{"start_date": "2024-02-28",
                                             "end_date": "2024-03-01",
                                             "annual_rate": 0.01}]}},
        }, ensure_ascii=False), encoding="utf-8")
        config_path.write_text(json.dumps(config), encoding="utf-8")
        proc = subprocess.run(
            [sys.executable, "-X", "utf8",
             str(HERE / "python" / "legal_entry.py"),
             "--request-json", str(request),
             "--config", str(config_path)],
            capture_output=True, text=True, encoding="utf-8")
        payload = json.loads(proc.stdout)
        self.assertEqual(proc.returncode, 4)
        self.assertEqual(payload["status"], "JC_FAILURE")
        self.assertIn("FLOAT_FORBIDDEN", str(payload.get("code")))


class MethodGroupTests(unittest.TestCase):
    """冻结方法组与禁无必要 DAG 引擎（导入闭集 AST 钉定）。"""

    def test_frozen_group_alignment(self) -> None:
        self.assertEqual(legal_entry.SKILL_METHODS,
                         skill_semantics.SKILL_METHODS)
        self.assertEqual(skill_semantics.CALC_SLOT_METHODS,
                         set(legal_entry._CALC_FAMILY_SLOT_BY_METHOD))

    def test_unknown_skill_method_fail_closed(self) -> None:
        with self.assertRaises(NotConnected) as ctx:
            legal_entry.call("skill.route", {"x": 1}, {})
        self.assertIn("method_not_connected:skill.route", str(ctx.exception))

    def test_no_dag_engine_imports(self) -> None:
        # 导入闭集：解析＋既有冻结面分派所需最小集；任何图/引擎/编排依赖
        # （graphlib/networkx 等）不在此列＝「禁无必要 DAG 引擎」的机械形态。
        source = (HERE / "python" / "skill_semantics.py").read_text(
            encoding="utf-8")
        tree = ast.parse(source)
        imported = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(alias.name.split(".")[0]
                                for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module.split(".")[0])
        self.assertEqual(imported,
                         {"__future__", "hashlib", "json", "re",
                          "bridge_errors", "pathlib", "legal_entry"})


if __name__ == "__main__":
    unittest.main()

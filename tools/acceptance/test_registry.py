"""registry 单元测试：合成小 CSV 驱动（tempfile 造输入），不读仓库权威数据。

覆盖：宿主拆分（Word/WPS、双发行形态、单形态）、砍行、已裁定行、
状态词表、命令占位、phase 最早批次、分母校验、未完成分组、
复合行分期/方面拆（T26 G1/G2：合成拆分表注入，含逐字校验与守卫）。

运行：
  python -X utf8 -B -m unittest tools.acceptance.test_registry -v
  python -X utf8 -B -m unittest discover -s tools/acceptance
"""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import registry
from registry import (
    ADJUDICATED_REASON,
    CUT_ROW_REASON,
    LEDGER_FIELDS,
    PENDING_OWNER_IMPLEMENTATION,
    RegistryError,
    build_ledger,
    group_incomplete,
    read_ledger,
    validate,
    write_ledger,
)


def r06(source_id: str, *, stage: str = "v1", status: str = "NOT_RUN", **over) -> dict:
    row = {c: "" for c in registry.COLUMNS_06}
    row.update({
        "v7_id": f"V7-{source_id}",
        "source_id": source_id,
        "source_feature": f"{source_id} 功能",
        "stage": stage,
        "owner": "product",
        "phase": "B0-B3",
        "construction_prerequisites": "none",
        "acceptance": f"{source_id} 验收断言",
        "profiles": "desktop;selfhost",
        "command": "待owner实现验收入口后登记实际命令；本轮无产品执行",
        "cwd": "待真实施工仓/部署根冻结，源仓保留不改",
        "subject": "验收时准确commit/package；本轮静态refs不证明clean",
        "evidence_path": f"evidence/{source_id}/<profile>/",
        "status": status,
        "exit_code": "",
    })
    row.update(over)
    return row


def r07(obligation_id: str, *, status: str = "NOT_RUN", **over) -> dict:
    row = {c: "" for c in registry.COLUMNS_07}
    row.update({
        "obligation_id": obligation_id,
        "title": f"{obligation_id} 义务",
        "owner": "product",
        "phase": "B0",
        "prerequisites": "none",
        "acceptance": f"{obligation_id} 验收断言",
        "status": status,
        "command": "施工后owner登记真实入口和cwd，不造现有脚本",
        "subject": "待实际验收冻结",
        "evidence_path": f"evidence/{obligation_id}/<profile>/",
        "exit_code": "",
    })
    row.update(over)
    return row


def by_id(instances: list[dict]) -> dict:
    return {i["obligation_id"]: i for i in instances}


class SplitTest(unittest.TestCase):
    def test_dual_release_splits_two_instances(self):
        inst = by_id(build_ledger([r06("X01")], []))
        self.assertEqual(sorted(inst), ["X01-desktop", "X01-selfhost"])
        self.assertEqual([inst[k]["host"] for k in sorted(inst)], ["desktop", "selfhost"])
        self.assertTrue(all(i["status"] == "NOT_RUN" for i in inst.values()))
        self.assertTrue(all(i["failure_reason"] == "" for i in inst.values()))

    def test_single_profile_row_gets_one_instance(self):
        inst = by_id(build_ledger([r06("X05", profiles="desktop")], []))
        self.assertEqual(sorted(inst), ["X05-desktop"])
        self.assertEqual(inst["X05-desktop"]["profile"], "desktop")

    def test_word_wps_row_splits_two_host_instances(self):
        row = r06("X03", source_feature="通道② Word/WPS 双插件+原生修订红线")
        inst = by_id(build_ledger([row], []))
        self.assertEqual(sorted(inst), ["X03-word", "X03-wps"])
        self.assertEqual(inst["X03-word"]["evidence_path"], "evidence/X03/word/")
        self.assertEqual(inst["X03-wps"]["evidence_path"], "evidence/X03/wps/")

    def test_word_only_row_gets_single_word_instance(self):
        row = r06("X06", source_feature="Word 面板 quick_actions",
                  acceptance="quick_action读取实际选区/上下文且受权限")
        inst = by_id(build_ledger([row], []))
        self.assertEqual(sorted(inst), ["X06-word"])

    def test_cut_row_excluded_without_host_split(self):
        row = r06("X02", stage="砍", status="EXCLUDED",
                  acceptance="不进入施工与完成分母；检查无被其他项暗中启用")
        inst = by_id(build_ledger([row], []))
        self.assertEqual(sorted(inst), ["X02"])
        self.assertEqual(inst["X02"]["status"], "EXCLUDED")
        self.assertEqual(inst["X02"]["failure_reason"], CUT_ROW_REASON)
        self.assertEqual(inst["X02"]["host"], "")
        self.assertEqual(inst["X02"]["evidence_path"], "evidence/X02/<profile>/")

    def test_pending_row_not_run_and_still_split(self):
        row = r06("X04", status="PENDING_USER_DECISION", phase="B4")
        inst = by_id(build_ledger([row], []))
        self.assertEqual(sorted(inst), ["X04-desktop", "X04-selfhost"])
        self.assertTrue(all(i["status"] == "NOT_RUN" for i in inst.values()))
        self.assertTrue(all(i["failure_reason"] == ADJUDICATED_REASON for i in inst.values()))
        self.assertTrue(all(i["phase"] == "B4" for i in inst.values()))


class FieldMappingTest(unittest.TestCase):
    def test_prose_command_registered_pending(self):
        inst = by_id(build_ledger([r06("X01")], []))
        cmd = inst["X01-desktop"]
        self.assertEqual(cmd["command"], PENDING_OWNER_IMPLEMENTATION)
        self.assertEqual(cmd["cwd"], PENDING_OWNER_IMPLEMENTATION)

    def test_real_command_passes_through(self):
        row = r06("X05", profiles="desktop",
                  command="python -X utf8 tools/acceptance/registry.py validate",
                  cwd="D:/real/repo")
        inst = by_id(build_ledger([row], []))
        self.assertEqual(inst["X05-desktop"]["command"],
                         "python -X utf8 tools/acceptance/registry.py validate")
        self.assertEqual(inst["X05-desktop"]["cwd"], "D:/real/repo")

    def test_obligation_fields_mapped(self):
        row = r07("E01", phase="B2/B4", prerequisites="E01,E04", owner="harness")
        inst = by_id(build_ledger([], [row]))["E01"]
        self.assertEqual(inst["source_id"], "")
        self.assertEqual(inst["host"], "")
        self.assertEqual(inst["phase"], "B2")
        self.assertEqual(inst["inputs"], "E01,E04")
        self.assertEqual(inst["owner"], "harness")
        self.assertEqual(inst["command"], PENDING_OWNER_IMPLEMENTATION)

    def test_phase_earliest_batch(self):
        self.assertEqual(registry.earliest_batch("B2/B4"), "B2")
        self.assertEqual(registry.earliest_batch("B0/S0;B3全量"), "S0")
        self.assertEqual(registry.earliest_batch("B3"), "B3")
        self.assertEqual(registry.earliest_batch("无批次说明"), "无批次说明")

    def test_six_phase_column_kept_verbatim_for_06_rows(self):
        row = r06("X01", phase="B0-B4;v1基础/v1.5通道或封皮独立实例")
        inst = build_ledger([row], [])
        self.assertTrue(all(i["phase"] == "B0-B4;v1基础/v1.5通道或封皮独立实例" for i in inst))


class VocabTest(unittest.TestCase):
    def test_unknown_status_06_raises(self):
        with self.assertRaises(RegistryError):
            build_ledger([r06("X01", status="MAYBE")], [])

    def test_unknown_status_07_raises(self):
        with self.assertRaises(RegistryError):
            build_ledger([], [r07("E01", status="DONE")])

    def test_duplicate_obligation_id_raises(self):
        with self.assertRaises(RegistryError):
            build_ledger([], [r07("E01"), r07("E01")])


SEG_STAGE = {
    "X01": [("v1.5", "acceptance", "X01后期段实测", "B4",
             "照抄 06 acceptance 的 v1.5 段")],
}
SEG_ASPECT = {
    "X01": [
        ("列", "acceptance", "列", "B0-B3", "照抄 06 acceptance token「列」"),
        ("溯源", "acceptance", "出处", "B0-B3",
         "照抄 06 acceptance token「出处」；08:11 称「溯源」"),
        ("复核", "acceptance", "复核", "B0-B3", "照抄 06 acceptance token「复核」"),
        ("重跑", "acceptance", "单格重跑", "B0-B3", "照抄 06 acceptance token「单格重跑」"),
        ("人改", "acceptance", "人工改格", "B0-B3", "照抄 06 acceptance token「人工改格」"),
    ],
}
BASE_IDS = {"X01-desktop", "X01-selfhost"}


class ExpandMergeTest(unittest.TestCase):
    """expand 合并语义：既有实例整行保留（销账状态不被权威重写覆盖），只补新增。"""

    def test_merge_keeps_existing_rows_and_appends_new(self):
        row = r06("X01", acceptance="X01基础断言；X01后期段实测")
        existing = by_id(build_ledger([row], []))
        # 模拟手工销账：既有实例状态/证据已推进
        existing["X01-desktop"] = dict(existing["X01-desktop"], status="VERIFIED",
                                       failure_reason="已验", evidence_path="evidence/x/")
        expected = build_ledger([row], [], segments=SEG_STAGE)
        merged, kept, appended = registry.merge_with_existing(
            expected, list(existing.values()))
        self.assertEqual(kept, ["X01-desktop", "X01-selfhost"])
        self.assertEqual(appended, ["X01-v1.5"])
        self.assertEqual(len(merged), 3)
        self.assertEqual(merged[0], existing["X01-desktop"])  # 整行原样（只增不改）
        self.assertEqual(merged[2]["obligation_id"], "X01-v1.5")

    def test_merge_extra_id_fails_closed(self):
        expected = build_ledger([r06("X01")], [])
        stale = [dict(expected[0], obligation_id="X09-desktop")]
        with self.assertRaises(RegistryError):
            registry.merge_with_existing(expected, stale)

    def test_merge_without_existing_returns_expected(self):
        expected = build_ledger([r06("X01")], [])
        merged, kept, appended = registry.merge_with_existing(expected, None)
        self.assertEqual(merged, expected)
        self.assertEqual(kept, [])
        self.assertEqual(len(appended), 2)


class CompositeStageSplitTest(unittest.TestCase):
    """分期拆（G1/G2）：后期段每段 1 子实例，宿主实例只增不改。"""

    def test_stage_segment_added_and_base_untouched(self):
        row = r06("X01", acceptance="X01基础断言；X01后期段实测")
        plain = by_id(build_ledger([row], []))
        split = by_id(build_ledger([row], [], segments=SEG_STAGE))
        self.assertEqual(set(plain), BASE_IDS)
        self.assertEqual(set(split), BASE_IDS | {"X01-v1.5"})
        for oid, inst in plain.items():
            self.assertEqual(split[oid], inst)  # 宿主实例逐字段原样（只增不改）
        sub = split["X01-v1.5"]
        self.assertEqual(sub["host"], "")
        self.assertEqual(sub["profile"], "desktop;selfhost")
        self.assertEqual(sub["phase"], "B4")
        self.assertEqual(sub["assertion"], "X01后期段实测（照抄 06 acceptance 的 v1.5 段）")
        self.assertEqual(sub["evidence_path"], "evidence/X01/<profile>/")  # 无宿主可替换，保留原值
        self.assertEqual(sub["status"], "NOT_RUN")
        self.assertEqual(sub["failure_reason"], "")

    def test_segment_assertion_must_be_verbatim_in_column(self):
        row = r06("X01", acceptance="X01基础断言")  # 不含后期段文字
        with self.assertRaises(RegistryError):
            build_ledger([row], [], segments=SEG_STAGE)

    def test_v2_segment_phase_b5(self):
        row = r06("X01", stage="v1.5", acceptance="X01基础断言；X01十三件套全量")
        seg = {"X01": [("v2", "acceptance", "X01十三件套全量", "B5", "照抄 06 source_stage 拍板文")]}
        inst = by_id(build_ledger([row], [], segments=seg))
        self.assertEqual(inst["X01-v2"]["phase"], "B5")

    def test_validate_detects_missing_and_accepts_full_split_ledger(self):
        row = r06("X01", acceptance="X01基础断言；X01后期段实测")
        denom = mini_denom([row], [])
        full = build_ledger([row], [], segments=SEG_STAGE)
        _, problems = validate(denom, [row], [], full, segments=SEG_STAGE)
        self.assertEqual(problems, [])
        _, problems = validate(denom, [row], [], full[1:], segments=SEG_STAGE)
        self.assertTrue(any("缺实例" in p for p in problems))


class CompositeAspectSplitTest(unittest.TestCase):
    """方面拆（G1）：F82 型五方面各 1 子实例，phase 随本行批次。"""

    def test_five_aspect_sub_instances_added(self):
        row = r06("X01", phase="B0-B3",
                  acceptance="列/批量/出处/支持状态/复核/单格重跑/人工改格/失效回读")
        inst = by_id(build_ledger([row], [], segments=SEG_ASPECT))
        aspects = {"X01-列", "X01-溯源", "X01-复核", "X01-重跑", "X01-人改"}
        self.assertEqual(set(inst), BASE_IDS | aspects)
        for oid, sub in inst.items():
            if oid in aspects:
                self.assertEqual(sub["phase"], "B0-B3")
                self.assertEqual(sub["host"], "")
                self.assertEqual(sub["status"], "NOT_RUN")
        self.assertEqual(inst["X01-溯源"]["assertion"],
                         "出处（照抄 06 acceptance token「出处」；08:11 称「溯源」）")
        self.assertEqual(inst["X01-重跑"]["assertion"],
                         "单格重跑（照抄 06 acceptance token「单格重跑」）")

    def test_row_without_segment_column_text_raises(self):
        row = r06("X01", acceptance="与拆分表无关的断言")
        with self.assertRaises(RegistryError):
            build_ledger([row], [], segments=SEG_ASPECT)


class CompositeGuardTest(unittest.TestCase):
    """守卫：08:11 点名的「独立实例」声明必须落实为拆分表条目（fail-closed）。"""

    def test_marker_with_cross_stage_without_entry_raises(self):
        row = r06("X01", phase="B0-B4;v1基础/v1.5通道独立实例",
                  source_stage="v1 基础+付费通道 v1.5")
        with self.assertRaises(RegistryError):
            build_ledger([row], [])

    def test_marker_with_cross_stage_and_entry_passes(self):
        row = r06("X01", phase="B0-B4;v1基础/v1.5通道独立实例",
                  source_stage="v1 基础+付费通道 v1.5",
                  acceptance="X01基础断言；X01后期段实测")
        inst = by_id(build_ledger([row], [], segments=SEG_STAGE))
        self.assertEqual(set(inst), BASE_IDS | {"X01-v1.5"})

    def test_marker_without_cross_stage_mention_needs_no_entry(self):
        # 同既有夹具形态：phase 带「独立实例」字样但源文字无跨期档位（历史注记）。
        row = r06("X01", phase="B0-B4;v1基础/v1.5通道或封皮独立实例")
        self.assertEqual(set(by_id(build_ledger([row], []))), BASE_IDS)

    def test_version_pin_is_not_later_stage(self):
        # OpenCode v2.0.28 是版本 pin，不算跨期（F21 mention-only 的机械依据）。
        self.assertFalse(registry.later_stage_mentioned({
            "stage": "v1", "source_stage": "固定 OpenCode v2.0.28 原生服务",
            "acceptance": "", "preserved_historical_requirements": ""}))
        self.assertTrue(registry.later_stage_mentioned({
            "stage": "v1", "source_stage": "v1 策略+付费通道 v1.5",
            "acceptance": "", "preserved_historical_requirements": ""}))
        self.assertFalse(registry.later_stage_mentioned({
            "stage": "v1.5", "source_stage": "", "acceptance": "",
            "preserved_historical_requirements": "v1 先靠权限闸+假名，加密随后补"}))

    def test_cut_row_in_table_raises(self):
        row = r06("X01", stage="砍", status="EXCLUDED")
        with self.assertRaises(RegistryError):
            build_ledger([row], [], segments=SEG_STAGE)

    def test_pending_row_in_table_raises(self):
        row = r06("X01", status="PENDING_USER_DECISION", phase="B5",
                  acceptance="待具体范围裁定；X01后期段实测")
        with self.assertRaises(RegistryError):
            build_ledger([row], [], segments=SEG_STAGE)

    def test_pending_row_without_table_not_split(self):
        # E27 裁决 #21：F125 型待裁行不拆子实例，挂账 B5 前随范围裁定。
        row = r06("X01", status="PENDING_USER_DECISION", phase="B5",
                  acceptance="待具体范围裁定；v2案管财务/审批/用印/借阅独立验收")
        inst = by_id(build_ledger([row], []))
        self.assertEqual(set(inst), BASE_IDS)
        self.assertTrue(all(i["failure_reason"] == ADJUDICATED_REASON
                            for i in inst.values()))


def mini_denom(rows06, rows07) -> dict:
    from collections import Counter
    stages = Counter(r["stage"] for r in rows06)
    pending = sum(1 for r in rows06 if r["status"] == "PENDING_USER_DECISION")
    return {
        "source_rows": len(rows06),
        "functional_rows": len(rows06) - stages.get("非功能-许可", 0),
        "excluded_function_rows": stages.get("砍", 0),
        "pending_function_rows": pending,
        "nonexcluded_function_rows": len(rows06) - stages.get("砍", 0),
        "stage_counts": dict(stages),
        "mapped_rows": len(rows06),
        "additional_engineering_obligations": len(rows07),
        "note": "合成测试分母",
    }


class ValidateTest(unittest.TestCase):
    def setUp(self):
        self.rows06 = [
            r06("X01"),
            r06("X02", stage="砍", status="EXCLUDED"),
            r06("X03", source_feature="通道② Word/WPS 双插件"),
            r06("X04", status="PENDING_USER_DECISION"),
            r06("X05", profiles="desktop"),
        ]
        self.rows07 = [r07("E01", phase="B2/B4"), r07("E02", phase="B0/S0;B3全量")]
        self.denom = mini_denom(self.rows06, self.rows07)
        self.ledger = build_ledger(self.rows06, self.rows07)

    def test_consistent_inputs_pass(self):
        counts, problems = validate(self.denom, self.rows06, self.rows07, self.ledger)
        self.assertEqual(problems, [])
        self.assertEqual(counts["来源功能行(06)"], 5)
        self.assertEqual(counts["工程义务(07)"], 2)
        self.assertEqual(counts["台账实例总数"], len(self.ledger))
        # 5 行来源 → 砍1 + 双形态2行x2 + word/wps 1行x2 + desktop 1行 = 8，加义务 2 = 10
        self.assertEqual(len(self.ledger), 10)

    def test_denominator_mismatch_detected(self):
        bad = dict(self.denom, source_rows=99)
        _, problems = validate(bad, self.rows06, self.rows07, self.ledger)
        self.assertTrue(any("source_rows" in p for p in problems))

    def test_extra_status_detected(self):
        broken = [dict(i, status="DONE") if i["obligation_id"] == "X01-selfhost" else i
                  for i in self.ledger]
        _, problems = validate(self.denom, self.rows06, self.rows07, broken)
        self.assertTrue(any("词表外" in p for p in problems))
        self.assertTrue(any("四状态计数总和" in p for p in problems))

    def test_missing_row_detected(self):
        _, problems = validate(self.denom, self.rows06, self.rows07, self.ledger[1:])
        self.assertTrue(any("缺实例" in p for p in problems))

    def test_excluded_count_mismatch_detected(self):
        tampered = [dict(i, status="NOT_RUN", failure_reason="") if i["obligation_id"] == "X02" else i
                    for i in self.ledger]
        _, problems = validate(self.denom, self.rows06, self.rows07, tampered)
        self.assertTrue(any("EXCLUDED" in p for p in problems))

    def test_adjudicated_excluded_not_in_cut_equality(self):
        # §6.1a A1（W2b-U60 主控升级裁决）：裁决性 EXCLUDED（如 word 宿主半边
        # 永久结转）不入砍行等式，单独计数；砍行类仍与砍行数互钉。
        adj = [dict(i, status="EXCLUDED",
                    failure_reason="裁决性 EXCLUDED（A1：Word 不安装）")
               if i["obligation_id"] == "X01-desktop" else i
               for i in self.ledger]
        counts, problems = validate(self.denom, self.rows06, self.rows07, adj)
        self.assertEqual(problems, [])
        self.assertEqual(counts["台账 status=EXCLUDED(裁决性)"], 1)

    def test_foreign_excluded_reason_detected(self):
        # 既非砍行亦非裁决性的 EXCLUDED＝为过门偷改状态，fail-closed。
        rogue = [dict(i, status="EXCLUDED", failure_reason="随手排除")
                 if i["obligation_id"] == "X01-selfhost" else i
                 for i in self.ledger]
        _, problems = validate(self.denom, self.rows06, self.rows07, rogue)
        self.assertTrue(any("既非砍行" in p for p in problems))


class FileRoundtripTest(unittest.TestCase):
    def test_write_and_read_ledger_roundtrip(self):
        rows06 = [r06("X01"), r06("X02", stage="砍", status="EXCLUDED")]
        rows07 = [r07("E01", phase="B2/B4")]
        instances = build_ledger(rows06, rows07)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "acceptance-ledger.csv"
            write_ledger(path, instances)
            raw = path.read_bytes()
            # 固定 CRLF 字节（对齐仓库既有台账产物，expand diff 只含新增行）
            self.assertEqual(raw.count(b"\r\n"), len(instances) + 1)  # 表头+实例
            self.assertEqual(raw.count(b"\n") - raw.count(b"\r\n"), 0)  # 无裸 LF
            loaded = read_ledger(path)
        self.assertEqual([i["obligation_id"] for i in loaded],
                         [i["obligation_id"] for i in instances])
        self.assertEqual(list(loaded[0]), LEDGER_FIELDS)
        with tempfile.TemporaryDirectory() as tmp:
            bad = Path(tmp) / "x.csv"
            bad.write_text("obligation_id\nX\n", encoding="utf-8")
            with self.assertRaises(RegistryError):
                read_ledger(bad)


class GroupIncompleteTest(unittest.TestCase):
    def test_grouping_by_phase_owner_excludes_done(self):
        rows06 = [r06("X01", phase="B1", owner="product"),
                  r06("X02", stage="砍", status="EXCLUDED")]
        ledger = build_ledger(rows06, [r07("E01", phase="B2/B4", owner="harness")])
        verified = [dict(i, status="VERIFIED") if i["obligation_id"] == "X01-desktop" else i
                    for i in ledger]
        groups = group_incomplete(verified)
        self.assertEqual(groups[("B1", "product")], ["X01-selfhost"])
        self.assertEqual(groups[("B2", "harness")], ["E01"])
        self.assertNotIn(("B0-B3", "product"), groups)  # X02 是 EXCLUDED，不算未完成


if __name__ == "__main__":
    unittest.main()

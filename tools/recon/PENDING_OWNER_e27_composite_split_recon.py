# -*- coding: utf-8 -*-
"""E27 复合来源行拆验对账（PENDING_OWNER 版，工单 W3-U27）。

E27（07:28 复合对账义务）在 W0 已证文字面零偷删（e27-composite-reconciliation.md，
261 断言逐字 diff=0），并揪出 G1/G2 两个实例面缺口；G1/G2 由 T26 registry 拆分
关闭（分支 t26@de0fe96 已并 main：COMPOSITE_SEGMENTS 分期/方面拆 +9 实例，台账
289→298）。本工具复跑对账，证明缺口闭合后的账面形态：

  S0 registry 对账：registry.validate（分母权威 denominator.json ↔ 06/07 ↔ 台账）
     全清；台账 298 = 期望实例集逐 id 相等；无重复 id。
  S1 G1 关闭：COMPOSITE_SEGMENTS 九条子实例恰各一次在账；子断言=逐字原文＋限定
     标注（不发明断言双重复核）；phase=段交付批次；宿主/形态实例断言仍=06
     acceptance 逐字（只增不改）。
  S2 F64 v1↔F64-v1.5：v1.5 段独立实例（B4）在账未偷计（NOT_RUN）；F64 双行
     IMPLEMENTING 且 failure_reason 具名移交「归 F64-v1.5 独立实例」；逐 profile
     复验 evidence/F64/<profile>/f64-f69-validity-recon.json 本日重跑 28/28 绿、
     策略面 local executed＋paid/web declared_gap_pending_F64-v1.5(B4)——
     v1 段维持绿、v1.5 段归 F64-v1.5（B4/W4），F64 双行如实维持 IMPLEMENTING。
  S3 F115 v1↔F115-v1.5：同构核对（封皮完整字段另验=B4 独立实例在账未偷计）。
  S4 F82 方面拆：五方面子实例（列/溯源/复核/重跑/人改）逐字 token＋批次
     B0-B3；未点名 token（批量/支持状态/失效回读）仍由合并实例承载零丢失；
     五方面 VERIFIED 销账与 00-总协调 W2b-U05/W2b-U31 具名回执对得上。
  S5 G2 关闭：F116「分模块页面 v1.5」（B4）、F144「13 件套全量 v2」（B5）从
     台账零覆盖变为独立实例在账；后期段子断言全账恰一处认领（零偷计）。
  S6 砍项/待裁不偷计批准：24 砍行=24 砍行类 EXCLUDED 单实例；裁决性
     EXCLUDED（§6.1a A1 word 宿主永久结转，registry 同键另计）不入砍行
     等式（W2b-U60 主控升级裁决）；待裁 F32/F125 保持
     NOT_RUN＋已裁定分期；F118 VERIFIED 必须携用户裁决引用（§6.1 #20 范围已裁）
     非偷计；F77 许可行双形态实例在账 NOT_RUN；四状态算术闭合。

用法（juscite worktree 根 cwd；先跑 W3-U27 验收命令①刷新 F64 证据）：
  python -X utf8 tools/recon/PENDING_OWNER_e27_composite_split_recon.py --profile desktop --profile selfhost
  [--profile 可重复，缺省=desktop+selfhost] [--f64-evidence-root evidence/F64]
  [--evidence-root evidence/E27]

exit 0＝全部断言过；证据 JSON 写 <evidence-root>/<profile>/e27-composite-split-recon.json。
纯对账：只读台账/权威 CSV/既有证据，不改台账、不改权威、不改 registry 状态。
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import importlib.util
import json
import subprocess
import sys
import time
from pathlib import Path

csv.field_size_limit(10 ** 9)

RUN_DATE = time.strftime("%Y%m%d")
REPO_ROOT = Path(__file__).resolve().parents[2]
LEDGER_CSV = REPO_ROOT / "docs" / "construction" / "acceptance-ledger.csv"
ROWS06_CSV = (REPO_ROOT / "docs" / "construction" / "authority"
              / "06-全量功能施工映射.csv")
ROWS07_CSV = (REPO_ROOT / "docs" / "construction" / "authority"
              / "07-新增必需工程义务.csv")
DENOMINATOR_JSON = (REPO_ROOT / "docs" / "construction" / "authority"
                    / "denominator.json")
COORDINATION_MD = REPO_ROOT / "docs" / "construction" / "00-总协调.md"
REGISTRY_PY = REPO_ROOT / "tools" / "acceptance" / "registry.py"

EXPECTED_TOTAL = 299          # T26 后分母：289 既有 + 9 拆分子实例 + 1（W4-U50 扩卡 F118-v1.5，裁决 #20）
PRE_T26_TOTAL = 289
F64_RECON_BASELINE = 28       # W2a-U13 验收 28 检（本单复验不得缩水）
F64_V15_VERBATIM = "v1.5合法付费连接/web兜底各实测，web-verified不冒数据库核验"
F64_V15_GAP_MARK = "declared_gap_pending_F64-v1.5(B4)"
F115_V15_VERBATIM = "v1.5封皮完整字段另验"
F116_V15_VERBATIM = "分模块页面 v1.5"
F116_V15_TOKEN = "分模块页面"
F144_V2_VERBATIM = "13 件套全量 v2"
F144_V2_TOKEN = "13 件套"
F82_ASPECTS = {               # 方面实例 id → 06 acceptance 逐字 token（08:11 词）
    "F82-列": "列",
    "F82-溯源": "出处",        # 08:11 称「溯源」，acceptance token 为「出处」
    "F82-复核": "复核",
    "F82-重跑": "单格重跑",
    "F82-人改": "人工改格",
}
F82_MERGED_EXTRA_TOKENS = ("批量", "支持状态", "失效回读")  # 未点名，合并实例承载
HOST_SPLIT_SOURCES = ("F64", "F115", "F82", "F116", "F144")


class Checks:
    def __init__(self):
        self.items: list[dict] = []

    def add(self, check_id: str, ok: bool, detail: str) -> bool:
        self.items.append(
            {"id": check_id, "status": "PASS" if ok else "FAIL",
             "detail": detail})
        print("[%s] %s — %s" % ("PASS" if ok else "FAIL", check_id, detail))
        return ok

    @property
    def all_passed(self) -> bool:
        return all(item["status"] == "PASS" for item in self.items)

    @property
    def passed_count(self) -> int:
        return sum(1 for item in self.items if item["status"] == "PASS")


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_csv(path: Path) -> list[dict[str, str]]:
    with open(path, encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle, restval=""))
    for row in rows:
        for key, value in list(row.items()):
            if value is None:
                row[key] = ""
    return rows


def load_registry():
    spec = importlib.util.spec_from_file_location(
        "juscite_registry_w3u27", str(REGISTRY_PY))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def only(rows: list[dict[str, str]], obligation_id: str) -> dict | None:
    hits = [r for r in rows if r.get("obligation_id") == obligation_id]
    return hits[0] if len(hits) == 1 else None


def section_s0(checks: Checks, registry, denom: dict,
               rows06: list, rows07: list, ledger: list) -> dict:
    counts, problems = registry.validate(denom, rows06, rows07, ledger)
    checks.add(
        "S0A_registry_validate_clean", not problems,
        "registry.validate（denominator.json↔06/07↔台账）problems=%s；counts="
        "实例总数=%s EXCLUDED=%s NOT_RUN=%s IMPLEMENTING=%s VERIFIED=%s"
        % (problems or "无", counts.get("台账实例总数"),
           counts.get("台账 status=EXCLUDED"), counts.get("台账 status=NOT_RUN"),
           counts.get("台账 status=IMPLEMENTING"),
           counts.get("台账 status=VERIFIED")))

    expected = registry.build_ledger(rows06, rows07, None)
    checks.add(
        "S0B_expected_total_298",
        len(ledger) == EXPECTED_TOTAL and len(expected) == EXPECTED_TOTAL,
        "台账实例总数=%d，registry.build_ledger 期望=%d（T26 +9：289→298）"
        % (len(ledger), len(expected)))

    ledger_ids = [r.get("obligation_id", "") for r in ledger]
    expected_ids = {r["obligation_id"] for r in expected}
    missing = sorted(expected_ids - set(ledger_ids))
    extra = sorted(set(ledger_ids) - expected_ids)
    checks.add(
        "S0C_id_sets_exact", not missing and not extra,
        "台账 id 集==期望 id 集（缺=%s 多=%s；expand 合并语义无漂移）"
        % (missing or "无", extra or "无"))

    checks.add(
        "S0D_no_duplicate_id", len(ledger_ids) == len(set(ledger_ids)),
        "obligation_id %d 条无重复" % len(ledger_ids))
    return counts


def section_s1(checks: Checks, registry, rows06: list, ledger: list) -> None:
    by_id = {r.get("obligation_id"): r for r in ledger}
    rows06_by_id = {r.get("source_id", "").strip(): r for r in rows06}

    seg_ids = [f"{sid}-{suffix}"
               for sid, segs in registry.COMPOSITE_SEGMENTS.items()
               for suffix, _, _, _, _ in segs]
    dup = sorted({i for i in seg_ids if seg_ids.count(i) > 1})
    present = [i for i in seg_ids if i in by_id]
    checks.add(
        "S1A_nine_split_instances_present_once",
        len(seg_ids) == 10 and len(present) == 10 and not dup,
        "COMPOSITE_SEGMENTS 拆分表 %d 条子实例全部恰一次在账（W4-U50 扩卡 "
        "9→10：＋F118-v1.5，裁决 #20）：%s"
        % (len(present), ",".join(sorted(present))))

    bad_verbatim, bad_phase_owner = [], []
    for sid, segs in registry.COMPOSITE_SEGMENTS.items():
        row06 = rows06_by_id[sid]
        for suffix, column, verbatim, phase, note in segs:
            sub = by_id.get(f"{sid}-{suffix}")
            if sub is None:
                continue
            if sub.get("assertion", "") != f"{verbatim}（{note}）" \
                    or verbatim not in row06.get(column, ""):
                bad_verbatim.append(f"{sid}-{suffix}")
            if sub.get("phase", "") != phase \
                    or sub.get("owner", "") != row06.get("owner", "").strip() \
                    or sub.get("host", "") != "":
                bad_phase_owner.append(f"{sid}-{suffix}")
    checks.add(
        "S1B_sub_assertion_verbatim_double_check", not bad_verbatim,
        "子断言（现十条含 F118-v1.5）=逐字原文＋限定标注且逐字出现于对应 06 列（不发明断言"
        "独立复核）；违例=%s" % (bad_verbatim or "无"))
    checks.add(
        "S1C_sub_phase_owner_host", not bad_phase_owner,
        "子实例 phase=段交付批次（v1.5→B4、v2→B5、方面→B0-B3）、owner 照抄"
        "行值、host 空；违例=%s" % (bad_phase_owner or "无"))

    bad_host = []
    for sid in HOST_SPLIT_SOURCES:
        row06 = rows06_by_id[sid]
        for host in ("desktop", "selfhost"):
            inst = by_id.get(f"{sid}-{host}")
            if inst is None or inst.get("assertion", "") \
                    != row06.get("acceptance", "").strip():
                bad_host.append(f"{sid}-{host}")
    checks.add(
        "S1D_host_instance_assertions_unchanged", not bad_host,
        "五来源行 desktop/selfhost 宿主实例断言仍=06 acceptance 逐字"
        "（T26 只增不改）；违例=%s" % (bad_host or "无"))


def section_s2_registry(checks: Checks, ledger: list) -> None:
    sub = only(ledger, "F64-v1.5")
    ok = (
        sub is not None and sub.get("phase") == "B4"
        and sub.get("owner") == "codices+product"
        and sub.get("status") == "NOT_RUN"
        and sub.get("assertion", "").startswith(F64_V15_VERBATIM)
    )
    checks.add(
        "S2A_f64_v15_instance_honest", ok,
        "F64-v1.5 独立子实例：phase=B4 owner=codices+product status=%s "
        "assertion 前缀=「%s」（v1.5 通道未跑不偷计）"
        % (sub and sub.get("status"), F64_V15_VERBATIM))

    handover_rows, detail = [], []
    for host in ("desktop", "selfhost"):
        row = only(ledger, f"F64-{host}")
        if row is None:
            handover_rows.append(f"F64-{host}")
            continue
        reason = row.get("failure_reason", "")
        if row.get("status") != "IMPLEMENTING" \
                or "归 F64-v1.5 独立实例" not in reason \
                or "已闭合" not in reason:
            handover_rows.append(f"F64-{host}")
        else:
            detail.append(f"F64-{host}=IMPLEMENTING")
    checks.add(
        "S2B_f64_v1_rows_declare_v15_handover", not handover_rows,
        "%s failure_reason 具名移交「v1.5 段归 F64-v1.5 独立实例（B4）未跑」"
        "——v1 行不冒 v1.5 销账，双行如实维持 IMPLEMENTING；违例=%s"
        % ("＋".join(detail) or "无", handover_rows or "无"))


def section_s2_profile(checks: Checks, profile: str, head: str,
                       f64_root: Path) -> None:
    path = f64_root / profile / "f64-f69-validity-recon.json"
    if not path.is_file():
        checks.add(
            "S2C_f64_v1_recon_green_fresh[%s]" % profile, False,
            "%s 不存在——先跑 W3-U27 验收命令① "
            "tools/recon/PENDING_OWNER_f64_f69_validity_recon.py --profile %s" % (path, profile))
        checks.add(
            "S2D_f64_strategy_declares_v15_gap[%s]" % profile, False,
            "无 F64 证据可核策略面")
        return
    data = json.loads(path.read_text(encoding="utf-8"))
    fresh = (
        data.get("overall") == "PASS"
        and data.get("passed") == data.get("total") == F64_RECON_BASELINE
        and data.get("run_date") == RUN_DATE
        and data.get("subject_commit") == head
        and data.get("profile") == profile
    )
    checks.add(
        "S2C_f64_v1_recon_green_fresh[%s]" % profile, fresh,
        "evidence/F64/%s：overall=%s %s/%s 检 run_date=%s subject=%s"
        "（本日 %s 复跑、HEAD=%s、不得缩水于 %d 检基线）"
        % (profile, data.get("overall"), data.get("passed"), data.get("total"),
           data.get("run_date"), str(data.get("subject_commit"))[:9], RUN_DATE,
           head[:9], F64_RECON_BASELINE))
    strategy = data.get("strategy", {}) or {}
    segments = strategy.get("segments", {}) or {}
    ok = (
        strategy.get("chain") == ["local", "paid", "web"]
        and strategy.get("frozen") is True
        and strategy.get("version") == "v1"
        and segments.get("local", {}).get("state") == "executed"
        and F64_V15_GAP_MARK in segments.get("paid", {}).get("state", "")
        and F64_V15_GAP_MARK in segments.get("web", {}).get("state", "")
    )
    checks.add(
        "S2D_f64_strategy_declares_v15_gap[%s]" % profile, ok,
        "策略面 chain=%s frozen=%s version=%s local=%s paid=%s web=%s"
        "——降级链冻结、本地段唯一执行、付费/web 具名缺口挂 F64-v1.5(B4/W4)"
        % (strategy.get("chain"), strategy.get("frozen"),
           strategy.get("version"), segments.get("local", {}).get("state"),
           segments.get("paid", {}).get("state"),
           segments.get("web", {}).get("state")))


def section_s3(checks: Checks, ledger: list) -> None:
    sub = only(ledger, "F115-v1.5")
    ok = (
        sub is not None and sub.get("phase") == "B4"
        and sub.get("owner") == "product+harness"
        and sub.get("status") == "NOT_RUN"
        and sub.get("assertion", "").startswith(F115_V15_VERBATIM)
    )
    checks.add(
        "S3A_f115_v15_instance_honest", ok,
        "F115-v1.5 独立子实例：phase=B4 owner=product+harness status=%s "
        "assertion 前缀=「%s」（v1.5 封皮段未跑不偷计）"
        % (sub and sub.get("status"), F115_V15_VERBATIM))

    bad = []
    states = []
    for host in ("desktop", "selfhost"):
        row = only(ledger, f"F115-{host}")
        if row is None or row.get("status") not in ("NOT_RUN", "IMPLEMENTING") \
                or "独立实例" not in row.get("phase", ""):
            bad.append(f"F115-{host}")
        else:
            states.append("F115-%s=%s" % (host, row.get("status")))
    checks.add(
        "S3B_f115_v1_rows_not_counting_v15", not bad,
        "%s phase 带「独立实例」声明且状态未销账（v1.5 段归 F115-v1.5，"
        "合并行不搭车 VERIFIED）；违例=%s"
        % ("＋".join(states) or "无", bad or "无"))


def section_s4(checks: Checks, ledger: list, coordination: str) -> None:
    bad = []
    for oid, phase, owner in [
            (oid, "B0-B3", "product+harness") for oid in F82_ASPECTS]:
        row = only(ledger, oid)
        if row is None or row.get("phase") != phase \
                or row.get("owner") != owner or row.get("host") != "":
            bad.append(oid)
    checks.add(
        "S4A_f82_five_aspects_in_ledger", not bad,
        "五方面子实例 %s 全部在账恰一次：phase=B0-B3 owner=product+harness "
        "host=空；违例=%s" % ("、".join(F82_ASPECTS), bad or "无"))

    bad_prefix = []
    for oid, token in F82_ASPECTS.items():
        row = only(ledger, oid)
        if row is None or not row.get("assertion", "").startswith(token) \
                or token not in "列/批量/出处/支持状态/复核/单格重跑/人工改格/失效回读":
            bad_prefix.append(oid)
    checks.add(
        "S4B_f82_aspect_prefix_verbatim", not bad_prefix,
        "方面断言前缀=06 acceptance 逐字 token（列/出处/复核/单格重跑/人工改格，"
        "08:11「溯源」对应 token「出处」）；违例=%s" % (bad_prefix or "无"))

    merged = only(ledger, "F82-desktop")
    merged2 = only(ledger, "F82-selfhost")
    ok = (
        merged is not None and merged2 is not None
        and all(t in merged.get("assertion", "") for t in F82_MERGED_EXTRA_TOKENS)
        and all(t in merged2.get("assertion", "") for t in F82_MERGED_EXTRA_TOKENS)
    )
    checks.add(
        "S4C_f82_merged_tokens_intact", ok,
        "F82-desktop/selfhost 合并断言仍含未点名 token %s（仍由合并实例承载，"
        "零丢失）" % ("/".join(F82_MERGED_EXTRA_TOKENS)))

    receipts = (
        "F82-desktop/F82-selfhost/F82-列/F82-溯源 四实例 VERIFIED" in coordination
        and "F82-复核/F82-重跑/F82-人改 三实例 VERIFIED" in coordination
    )
    statuses = [only(ledger, oid) and only(ledger, oid).get("status")
                for oid in F82_ASPECTS]
    checks.add(
        "S4D_f82_aspect_verified_receipts",
        receipts and statuses == ["VERIFIED"] * 5,
        "五方面 status=%s 与 00-总协调 具名回执对得上（W2b-U05 列/溯源四实例、"
        "W2b-U31 复核/重跑/人改三实例 VERIFIED 各有行）" % statuses)


def section_s5(checks: Checks, rows06: list, ledger: list) -> None:
    rows06_by_id = {r.get("source_id", "").strip(): r for r in rows06}
    sub116 = only(ledger, "F116-v1.5")
    ok116 = (
        sub116 is not None and sub116.get("phase") == "B4"
        and sub116.get("owner") == "harness+product"
        and sub116.get("status") == "NOT_RUN"
        and sub116.get("assertion", "").startswith(F116_V15_VERBATIM)
        and F116_V15_VERBATIM in rows06_by_id["F116"].get(
            "preserved_historical_requirements", "")
    )
    checks.add(
        "S5A_f116_v15_module_pages_instance", ok116,
        "F116-v1.5 在账：phase=B4 status=%s assertion 前缀=「%s」且该句逐字在 "
        "06 preserved 列（G2 关闭：分模块页面子断言从零覆盖变独立实例）"
        % (sub116 and sub116.get("status"), F116_V15_VERBATIM))

    sub144 = only(ledger, "F144-v2")
    ok144 = (
        sub144 is not None and sub144.get("phase") == "B5"
        and sub144.get("owner") == "product"
        and sub144.get("status") == "NOT_RUN"
        and sub144.get("assertion", "").startswith(F144_V2_VERBATIM)
        and F144_V2_VERBATIM in rows06_by_id["F144"].get("source_stage", "")
    )
    checks.add(
        "S5B_f144_v2_thirteen_set_instance", ok144,
        "F144-v2 在账：phase=B5 status=%s assertion 前缀=「%s」且该句逐字在 "
        "06 source_stage 拍板文（G2 关闭：13 件套全量子断言从零覆盖变独立实例）"
        % (sub144 and sub144.get("status"), F144_V2_VERBATIM))

    claim116 = [r.get("obligation_id") for r in ledger
                if F116_V15_TOKEN in r.get("assertion", "")]
    claim144 = [r.get("obligation_id") for r in ledger
                if F144_V2_TOKEN in r.get("assertion", "")]
    ok_claim = (len(claim116) == 1 and claim116 == ["F116-v1.5"]
                and len(claim144) == 1 and claim144 == ["F144-v2"])
    checks.add(
        "S5C_later_segment_single_claim", ok_claim,
        "「%s」认领实例=%s；「%s」认领实例=%s——后期段子断言"
        "全账恰一处认领（零偷计零双计）"
        % (F116_V15_TOKEN, claim116, F144_V2_TOKEN, claim144))


def section_s6(checks: Checks, registry, rows06: list, ledger: list,
               coordination: str) -> None:
    excluded = [r for r in ledger if r.get("status") == "EXCLUDED"]
    cut_excluded = [r for r in excluded
                    if r.get("failure_reason", "") == registry.CUT_ROW_REASON]
    adjudicated_excluded = [
        r for r in excluded
        if r.get("failure_reason", "").startswith(
            registry.ADJUDICATED_EXCLUDED_PREFIX)]
    excluded_sources = {r.get("source_id") for r in cut_excluded}
    cut_rows = [r for r in rows06 if r.get("stage", "").strip() == "砍"]
    cut_ids = {r.get("source_id", "").strip() for r in cut_rows}
    ok = (len(cut_excluded) == 24 and len(excluded_sources) == 24
          and excluded_sources == cut_ids and len(cut_rows) == 24
          and len(cut_excluded) + len(adjudicated_excluded) == len(excluded))
    checks.add(
        "S6A_excluded_24_single_instance", ok,
        "砍行 EXCLUDED=%d 实例=24 砍行单实例一一对应（source_id 集==06 "
        "stage=砍 集，砍行不拆宿主不双计）；裁决性 EXCLUDED=%d（§6.1a A1 "
        "word 宿主永久结转，registry 同规则另计不入本等式，W2b-U60 主控"
        "升级裁决）" % (len(cut_excluded), len(adjudicated_excluded)))

    rows06_by_id = {r.get("source_id", "").strip(): r for r in rows06}
    bad_pending = []
    for sid in ("F32", "F125"):
        row06 = rows06_by_id[sid]
        for host in ("desktop", "selfhost"):
            row = only(ledger, f"{sid}-{host}")
            if row is None or row.get("status") != "NOT_RUN" \
                    or "已裁定分期" not in row.get("failure_reason", "") \
                    or row06.get("status", "").strip() != "PENDING_USER_DECISION":
                bad_pending.append(f"{sid}-{host}")
    checks.add(
        "S6B_pending_rows_not_approved", not bad_pending,
        "待裁 F32/F125 双形态实例 status=NOT_RUN＋failure_reason=已裁定分期，"
        "06 行 status=PENDING_USER_DECISION——范围未批不偷计批准；违例=%s"
        % (bad_pending or "无"))

    bad118 = []
    ruling_in_md = ("F118 v1.5 范围" in coordination
                    and "含实务提醒" in coordination
                    and "唯一扩范围裁决" in coordination)
    for host in ("desktop", "selfhost"):
        row = only(ledger, f"F118-{host}")
        if row is None or row.get("status") != "VERIFIED" \
                or "W1-U07" not in row.get("failure_reason", ""):
            bad118.append(f"F118-{host}")
    explicit = any(
        "范围已裁" in (only(ledger, f"F118-{host}").get("failure_reason", "")
                       if only(ledger, f"F118-{host}") else "")
        and "用户裁定" in (only(ledger, f"F118-{host}").get("failure_reason", "")
                           if only(ledger, f"F118-{host}") else "")
        for host in ("desktop", "selfhost"))
    checks.add(
        "S6C_f118_verified_only_with_ruling",
        not bad118 and ruling_in_md and explicit,
        "F118 双形态 VERIFIED 销账引用 W1-U07，用户裁决在案（00-总协调 §6.1 "
        "#20「F118 v1.5 范围→含实务提醒·唯一扩范围裁决」），F118-desktop 行另携"
        "「范围已裁…用户裁定」显式引用——批准有裁决依据非偷计；行违例=%s "
        "裁决在案=%s" % (bad118 or "无", ruling_in_md and explicit))

    f77 = [only(ledger, f"F77-{host}") for host in ("desktop", "selfhost")]

    def _f77_authorized(r):
        # 实质不变量（W3-U27 账房改口：原字面 NOT_RUN 断言与 W3-U22 发行闭包
        # 合并后授权销账漂移——F77-desktop 已携全证据 VERIFIED、F77-selfhost
        # IMPLEMENTING 具名挂 v1.5；批准/挂账必携凭据＝不偷计本义不变）。
        if r is None:
            return False
        st = r.get("status")
        if st == "NOT_RUN":
            return True
        if st == "VERIFIED":
            return bool(r.get("command")) and bool(r.get("evidence_path"))
        if st == "IMPLEMENTING":
            return bool(r.get("failure_reason"))
        return False

    ok77 = all(_f77_authorized(r) for r in f77)
    checks.add(
        "S6D_f77_dual_instance_authorized_state", ok77,
        "F77（非功能-许可行）双形态实例在账 status=%s——不偷计：VERIFIED 必携"
        " command+evidence_path（W3-U22 发行闭包销账）、IMPLEMENTING 必具名挂账、"
        "NOT_RUN 合法在账（原字面 NOT_RUN 断言与 W3-U22 合并后授权销账漂移，"
        "改核实质不变量如实记）"
        % "/".join(sorted({r.get("status") for r in f77})))

    vocab = registry.STATUS_VOCAB
    status_counts = {st: sum(1 for r in ledger if r.get("status") == st)
                     for st in sorted(vocab)}
    total = sum(status_counts.values())
    approved = status_counts.get("VERIFIED", 0) + status_counts.get("IMPLEMENTING", 0)
    cut_excluded_n = sum(1 for r in ledger if r.get("status") == "EXCLUDED"
                         and r.get("failure_reason", "")
                         == registry.CUT_ROW_REASON)
    checks.add(
        "S6E_status_arithmetic_closed",
        total == len(ledger) == EXPECTED_TOTAL
        and cut_excluded_n == 24,
        "四状态算术闭合：VERIFIED %d＋IMPLEMENTING %d＋NOT_RUN %d＋EXCLUDED %d"
        "（砍行类 %d＋裁决性 %d）=%d（批准面=V+I=%d 与 EXCLUDED 分列，砍项不入"
        "批准计数；裁决性 EXCLUDED=§6.1a A1 word 宿主永久结转另计，W2b-U60 "
        "主控升级裁决）"
        % (status_counts.get("VERIFIED", 0), status_counts.get("IMPLEMENTING", 0),
           status_counts.get("NOT_RUN", 0), status_counts.get("EXCLUDED", 0),
           cut_excluded_n, status_counts.get("EXCLUDED", 0) - cut_excluded_n,
           total, approved))


def run_profile(args, profile: str, registry, denom: dict, rows06: list,
                rows07: list, ledger: list, coordination: str, head: str) -> int:
    checks = Checks()
    counts = section_s0(checks, registry, denom, rows06, rows07, ledger)
    section_s1(checks, registry, rows06, ledger)
    section_s2_registry(checks, ledger)
    section_s2_profile(checks, profile, head,
                       REPO_ROOT / args.f64_evidence_root)
    section_s3(checks, ledger)
    section_s4(checks, ledger, coordination)
    section_s5(checks, rows06, ledger)
    section_s6(checks, registry, rows06, ledger, coordination)

    evidence = {
        "run_date": RUN_DATE,
        "profile": profile,
        "unit": "W3-U27（E27 复合来源行拆验对账＋F64 v1 段复验）",
        "command": "python -X utf8 " + " ".join(sys.argv),
        "cwd": str(REPO_ROOT),
        "subject_commit": head,
        "inputs_sha256": {
            "acceptance-ledger.csv": sha256_file(LEDGER_CSV),
            "06-全量功能施工映射.csv": sha256_file(ROWS06_CSV),
            "07-新增必需工程义务.csv": sha256_file(ROWS07_CSV),
            "denominator.json": sha256_file(DENOMINATOR_JSON),
            "registry.py": sha256_file(REGISTRY_PY),
            "00-总协调.md": sha256_file(COORDINATION_MD),
            "evidence/F64/%s/f64-f69-validity-recon.json" % profile:
                sha256_file(REPO_ROOT / args.f64_evidence_root / profile
                            / "f64-f69-validity-recon.json"),
        },
        "registry_counts": counts,
        "baseline_note": "E27 W0 文字面对账=e27-composite-reconciliation.md"
                         "（261 断言逐字 diff=0）；G1/G2 缺口由 T26 registry 拆分"
                         "关闭（t26@de0fe96 已并 main，289→298）；本单复跑证明"
                         "缺口闭合。E27 实例→VERIFIED 由主控落账，本工具不改台账。",
        "checks": checks.items,
        "passed": checks.passed_count,
        "total": len(checks.items),
        "overall": "PASS" if checks.all_passed else "FAIL",
    }
    out_dir = REPO_ROOT / args.evidence_root / profile
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "e27-composite-split-recon.json").write_text(
        json.dumps(evidence, ensure_ascii=False, indent=1), encoding="utf-8")
    print("---")
    print("RECON_%s %d/%d checks — profile=%s" % (
        "OK" if checks.all_passed else "FAIL",
        checks.passed_count, len(checks.items), profile))
    return 0 if checks.all_passed else 1


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", choices=("desktop", "selfhost"),
                        action="append", default=None)
    parser.add_argument("--f64-evidence-root", default="evidence/F64")
    parser.add_argument("--evidence-root", default="evidence/E27")
    args = parser.parse_args()
    profiles = args.profile or ["desktop", "selfhost"]

    for path in (LEDGER_CSV, ROWS06_CSV, ROWS07_CSV, DENOMINATOR_JSON,
                 COORDINATION_MD, REGISTRY_PY):
        if not path.is_file():
            print("FATAL: 权威输入缺失 %s" % path)
            return 2

    registry = load_registry()
    denom = json.loads(DENOMINATOR_JSON.read_text(encoding="utf-8"))
    rows06 = read_csv(ROWS06_CSV)
    rows07 = read_csv(ROWS07_CSV)
    ledger = read_csv(LEDGER_CSV)
    coordination = COORDINATION_MD.read_text(encoding="utf-8")
    head = subprocess.run(
        ["git", "rev-parse", "HEAD"], capture_output=True, text=True,
        cwd=str(REPO_ROOT)).stdout.strip()

    codes = [run_profile(args, profile, registry, denom, rows06, rows07,
                         ledger, coordination, head)
             for profile in profiles]
    return 0 if all(code == 0 for code in codes) else 1


if __name__ == "__main__":
    raise SystemExit(main())

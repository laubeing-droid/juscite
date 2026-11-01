"""律引（JusBench）验收实例注册器（T01 验收入口脚手架）。

把权威输入确定性地展开为义务实例台账 docs/construction/acceptance-ledger.csv：
  - docs/construction/authority/06-全量功能施工映射.csv（144 来源功能行）
  - docs/construction/authority/07-新增必需工程义务.csv（28 项工程义务）
  - docs/construction/authority/denominator.json（分母权威值）

子命令：
  expand    展开权威输入为台账：既有实例按 obligation_id 原样保留（销账状态
            不被覆盖，只增不改），仅补新增实例；台账出现期望外实例即报错
            （不做静默删除）；台账文件不存在时生成首版
  validate  核对分母与台账一致性（不符 exit 2）
  report    按 phase/owner 汇总打印未完成清单

拆分规则（照 08-验收与施工顺序.md §1，机械执行，不做语义猜测）：
  - stage=砍 → 每行 1 实例，status=EXCLUDED，failure_reason=裁剪行，不拆宿主；
  - 06 status=PENDING_USER_DECISION（已裁定分期行，现 F32/F118/F125）
      → status=NOT_RUN，failure_reason=已裁定分期，仍按宿主拆实例，但不做
    分期/方面拆（F125 四块子实例挂账 B5 前随范围裁定，E27 裁决 #21）；
    例外：F118 的 v1.5 范围已经 §6.1 裁决 #20 落裁（2026-10-15「含实务提醒」，
    唯一扩范围裁决；宿主实例 W1-U07 销账已引同裁决），故 F118 准入复合拆分表
    （常量 ADJUDICATED_SEGMENT_OK）——F32/F125 范围未裁，仍禁入表；
  - 其余非砍行按宿主拆：source_feature+acceptance 含 Word/WPS 的宿主各一实例
    （host=word / host=wps）；否则按 profiles 拆（desktop;selfhost → desktop
    与 selfhost 两实例，单值 → 单实例）；profiles 为空时缺省 host=desktop；
  - 复合行分期/方面拆（T26 关闭 E27 G1/G2，表 COMPOSITE_SEGMENTS，规则详见
    docs/construction/t26-registry-split.md）：08 §1 点名分别拆验的行
    （F64 策略v1/付费web通道v1.5、F115 基础投影v1/封皮完整化v1.5、
    F82 列/溯源/复核/重跑/人改）与 E27 清查出的后期段子断言行（F116
    分模块页面v1.5、F144 13件套全量v2）→ 每段新增 1 条子实例
    （id=<source_id>-<段后缀>，host 空、profile 照抄行值、phase=段交付批次：
    v1.5 段→B4、v2 段→B5、方面段随本行批次）；宿主/形态实例与其断言逐字节
    保持原样（只增不改）。子断言文字必须逐字出现于该行对应 06 列（代码强制，
    不发明断言；拿不准的照抄原文并在限定标注里写明出处）；行 phase 自带
    「独立实例」标记且源文字提及晚于自身档位的行必须在表内，缺条目即
    RegistryError（08:11 点名拆验未落实=权威漂移，fail-closed）；
  - 07 每项义务 1 实例，phase 带多个批次时按最早批次登记。

命令/cwd 只有登记了真实可执行命令才原样入账；空值或以中文说明文字开头
（如"待owner实现…"/"施工后…"）一律登记 PENDING_OWNER_IMPLEMENTATION，
不发明可跑命令（08 §1：未实现验收入口时登记待施工）。

状态词表：NOT_RUN / IMPLEMENTING / VERIFIED / EXCLUDED，非法值报错退出。
EXCLUDED 分两类记账（W2b-U60 主控升级裁决，落实 §6.1a A1 2026-10-18
「Word 不安装·word 宿主半边永久结转按 EXCLUDED 处理」）：
  - 砍行 EXCLUDED：failure_reason=裁剪行，与 06 砍行数互钉（validate 等式）；
  - 裁决性 EXCLUDED：failure_reason 以「裁决性 EXCLUDED」开头（附裁决号），
    validate 单独计数（台账 status=EXCLUDED(裁决性)）不入砍行等式；
    既非砍行亦非裁决性的 EXCLUDED 一律报不符（防为过门偷改状态）。
仅用 Python 3.12 标准库。
"""

from __future__ import annotations

import csv
import json
import re
import sys
from collections import Counter
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
AUTHORITY_DIR = REPO_ROOT / "docs" / "construction" / "authority"
ROWS_06_CSV = AUTHORITY_DIR / "06-全量功能施工映射.csv"
ROWS_07_CSV = AUTHORITY_DIR / "07-新增必需工程义务.csv"
DENOMINATOR_JSON = AUTHORITY_DIR / "denominator.json"
LEDGER_CSV = REPO_ROOT / "docs" / "construction" / "acceptance-ledger.csv"

# 台账字段照 08 §1 记录字段；末位附加 phase 供 report 按 phase/owner 汇总。
LEDGER_FIELDS = [
    "obligation_id", "source_id", "assertion", "profile", "host", "owner",
    "inputs", "trigger", "command", "cwd", "subject", "expected",
    "exit_code", "actual", "evidence_path", "status", "failure_reason",
    "phase",
]

STATUS_NOT_RUN = "NOT_RUN"
STATUS_IMPLEMENTING = "IMPLEMENTING"
STATUS_VERIFIED = "VERIFIED"
STATUS_EXCLUDED = "EXCLUDED"
STATUS_VOCAB = {STATUS_NOT_RUN, STATUS_IMPLEMENTING, STATUS_VERIFIED, STATUS_EXCLUDED}

PENDING_OWNER_IMPLEMENTATION = "PENDING_OWNER_IMPLEMENTATION"
CUT_ROW_REASON = "裁剪行"
ADJUDICATED_REASON = "已裁定分期"
# 裁决性 EXCLUDED 类前缀（§6.1a A1 永久结转，W2b-U60 主控升级裁决）；
# 与 E28 S3D / 本单 recon 工具同键。
ADJUDICATED_EXCLUDED_PREFIX = "裁决性 EXCLUDED"

BATCH_ORDER = ["S0", "B0", "B1", "B2", "B3", "B4", "B5"]
_BATCH_TOKEN = re.compile(r"S0|B[0-5]")

# 权威输入的表头契约（expand 前校验，防权威 schema 漂移静默漏列）。
COLUMNS_06 = (
    "v7_id", "source_id", "source_feature", "implementation_name",
    "source_stage", "stage", "decision_evidence", "owner", "phase",
    "implementation", "construction_prerequisites",
    "legacy_semantic_links_not_dag", "acceptance", "profiles", "command",
    "cwd", "subject", "evidence_path", "status", "exit_code", "source_path",
    "source_line", "source_rationale", "python_entry_ids",
    "python_entry_binding", "interface_gap",
    "preserved_historical_requirements", "near_term_s0",
)
COLUMNS_07 = (
    "obligation_id", "title", "owner", "phase", "prerequisites",
    "acceptance", "status", "command", "subject", "evidence_path",
    "exit_code",
)
REQUIRED_06 = (
    "source_id", "source_feature", "stage", "owner", "phase",
    "construction_prerequisites", "acceptance", "profiles", "command",
    "cwd", "subject", "evidence_path", "status", "exit_code",
)
REQUIRED_07 = (
    "obligation_id", "owner", "phase", "prerequisites", "acceptance",
    "status", "command", "subject", "evidence_path", "exit_code",
)

# 复合行分期/方面拆分表（T26 关闭 E27 G1/G2；依据 08:11 点名 + e27-composite-
# reconciliation.md §2/§4，逐条出处见该文档）。
#
# 表项：source_id -> [(段后缀, 断言来源列, 逐字子串, phase, 限定标注), ...]
#   - 每段生成 1 条子实例：obligation_id=<source_id>-<段后缀>，host=""，
#     profile/owner/inputs/subject/command/cwd 照抄宿主实例规则，
#     evidence_path 保留权威原值（无宿主可替换 <profile>，同砍行），
#     assertion=<逐字子串>（<限定标注>），phase=段交付批次（08 §2：v1.5→B4、
#     v2→B5、方面段随本行批次）。
#   - 「逐字子串」必须原样出现于该行「断言来源列」，build_ledger 机器校验，
#     否则 RegistryError——"不发明新断言"由代码保证，不是约定。
#   - 宿主/形态实例不改动（只增不改）；砍行与 PENDING_USER_DECISION 行不得
#     进表（F125 挂账 B5 前随范围裁定）。
COMPOSITE_SEGMENTS: dict[str, list[tuple[str, str, str, str, str]]] = {
    # 08:11「F64策略v1、付费/web通道v1.5」：既有 F64-desktop/selfhost 即 v1 策略
    # 实例（只增不改），此处补 v1.5 付费/web 通道段（06 acceptance 的 v1.5 段逐字）。
    "F64": [
        ("v1.5", "acceptance",
         "v1.5合法付费连接/web兜底各实测，web-verified不冒数据库核验",
         "B4", "照抄 06 acceptance 的 v1.5 段"),
    ],
    # 08:11「F115基础投影v1、封皮完整化v1.5」：既有实例即 v1 基础投影，补 v1.5
    # 封皮段（06 acceptance 原文含「另验」，即另立实例之意）。
    "F115": [
        ("v1.5", "acceptance", "v1.5封皮完整字段另验", "B4",
         "照抄 06 acceptance 的 v1.5 段"),
    ],
    # E27 G2：v1.5 分模块页面子断言只在 preserved 列（06 acceptance 无 v1.5 段）。
    "F116": [
        ("v1.5", "preserved_historical_requirements",
         "分模块页面 v1.5", "B4",
         "照抄 06 preserved_historical_requirements「v1 只做分类字段，分模块页面 v1.5」；"
         "06 acceptance 无 v1.5 段"),
    ],
    # E27 G2：v2 13 件套全量只在 source_stage 拍板文（06 acceptance 无 v2 段）。
    "F144": [
        ("v2", "source_stage", "13 件套全量 v2", "B5",
         "照抄 06 source_stage 拍板文「…13 件套全量 v2」；06 acceptance 无 v2 段"),
    ],
    # 08:11「F82列/溯源/复核/重跑/人改分别」：五方面各 1 子实例，id 用 08 原词，
    # 断言=06 acceptance token 逐字（「溯源」对应 token「出处」，标注里桥接）；
    # 其余 token（批量/支持状态/失效回读）仍由既有合并实例承载，不另拆。
    "F82": [
        ("列", "acceptance", "列", "B0-B3", "照抄 06 acceptance token「列」"),
        ("溯源", "acceptance", "出处", "B0-B3",
         "照抄 06 acceptance token「出处」；08:11 称「溯源」"),
        ("复核", "acceptance", "复核", "B0-B3", "照抄 06 acceptance token「复核」"),
        ("重跑", "acceptance", "单格重跑", "B0-B3", "照抄 06 acceptance token「单格重跑」"),
        ("人改", "acceptance", "人工改格", "B0-B3", "照抄 06 acceptance token「人工改格」"),
    ],
    # 裁决 #20（00-总协调 §6.1，2026-10-15）唯一扩范围裁决：F118 v1.5 含实务
    # 提醒（宿主实例 F118-desktop/selfhost=W1-U07 已 VERIFIED 的程序期限链 v1
    # 段，只增不改）。子断言照抄 06 preserved_historical_requirements 功能面
    # 逐字（06 acceptance 无 v1.5 段，F116-v1.5 同先例）；实务提醒面（显式
    # 声明/倒计时 urgent/撤销/时刻窗全链，零隐式生成零外发）归本子实例
    # （W4-U50 扩卡实施，验收 tools/PENDING_OWNER_f118_v15_practical_
    # reminders_recon.py）。
    "F118": [
        ("v1.5", "preserved_historical_requirements",
         "期限提醒/日程闭环（schedule_event+系统通知+节点倒计时 urgent）", "B4",
         "裁决#20（00-总协调 §6.1）v1.5 含实务提醒＝唯一扩范围裁决；"
         "照抄 06 preserved_historical_requirements 功能面逐字"
         "（06 acceptance 无 v1.5 段）"),
    ],
}

# 「独立实例」守卫用：行 phase 自带标记（F64/F115）=08:11 点名拆验的自我声明。
INDEPENDENT_INSTANCE_MARKER = "独立实例"
# 已裁分期行准入复合拆分表的白名单（范围裁决已落账者）：
#   F118 —— §6.1 裁决 #20（00-总协调.md:239，2026-10-15）「F118 v1.5 范围含
#   实务提醒」＝唯一扩范围裁决；宿主实例 F118-desktop/selfhost 的 W1-U07 销账
#   failure_reason 已引同裁决。表内条目见 COMPOSITE_SEGMENTS["F118"]。
#   F32/F125 范围仍未裁（裁决 #21 挂账），不在白名单——禁入表不变。
ADJUDICATED_SEGMENT_OK = frozenset({"F118"})
_STAGE_ORDER = {"v1": 0, "v1.5": 1, "v2": 2}
# 晚档位 token 正则；排除版本 pin（如 OpenCode v2.0.28，v2 后随「.」不命中）。
_STAGE_PATTERNS = (
    ("v1.5", 1, re.compile(r"v1\.5(?![0-9.])")),
    ("v2", 2, re.compile(r"v2(?![0-9.])")),
)


class RegistryError(Exception):
    """输入不满足契约（表头缺列/状态词表外等）；CLI 层转为 exit 2。"""


def _read_csv(path: Path) -> list[dict[str, str]]:
    with open(path, encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f, restval=""))
    for row in rows:
        for key, value in list(row.items()):
            if value is None:
                row[key] = ""
    return rows


def _require_columns(rows: list[dict[str, str]], required, label: str) -> None:
    if not rows:
        return  # 空输入本身合法（如 07 暂无义务）；行数由 validate 对照分母把关
    missing = [c for c in required if c not in rows[0]]
    if missing:
        raise RegistryError(f"{label}：表头缺少必需列 {missing}")


def _is_prose_note(value: str) -> bool:
    """空串，或首字符是中文说明文字（如"待owner实现…"/"施工后…"）→ 非真实命令。"""
    v = value.strip()
    if not v:
        return True
    return "\u4e00" <= v[0] <= "\u9fff"


def resolve_command(value: str) -> str:
    return PENDING_OWNER_IMPLEMENTATION if _is_prose_note(value) else value.strip()


def earliest_batch(phase: str) -> str:
    """'B2/B4'→B2；'B0/S0;B3全量'→S0；无批次记号时原样返回。"""
    tokens = set(_BATCH_TOKEN.findall(phase))
    if not tokens:
        return phase
    return min(tokens, key=BATCH_ORDER.index)


def word_wps_hosts(text: str) -> list[str]:
    hosts = []
    if "Word" in text:
        hosts.append("word")
    if "WPS" in text:
        hosts.append("wps")
    return hosts


def hosts_for_feature_row(row: dict[str, str]) -> list[str]:
    """非砍功能行的宿主实例拆分（机械规则，见模块 docstring）。"""
    text = f"{row.get('source_feature', '')}\n{row.get('acceptance', '')}"
    hosts = word_wps_hosts(text)
    if hosts:
        return hosts
    profiles = [p.strip() for p in row.get("profiles", "").split(";") if p.strip()]
    return profiles if profiles else ["desktop"]


def later_stage_mentioned(row: dict[str, str]) -> bool:
    """行权威文字是否提及晚于自身 stage 的交付档位（机械正则，不做语义猜测）。

    仅用于「独立实例」守卫；版本 pin（如 OpenCode v2.0.28，v2 后随「.」）
    与更早档位（如 v1.5 行内的 v1 注记）不算跨期。
    """
    own = _STAGE_ORDER.get(row.get("stage", "").strip())
    if own is None:
        return False
    text = "\n".join(row.get(c, "") for c in
                     ("source_stage", "acceptance",
                      "preserved_historical_requirements"))
    return any(order > own and pat.search(text) for _, order, pat in _STAGE_PATTERNS)


def composite_sub_instances(row: dict[str, str], source_id: str,
                            segments: dict) -> list[dict[str, str]]:
    """按拆分表为复合行生成分期/方面子实例（只增不改：宿主实例另行原样登记）。

    子断言逐字校验失败即 RegistryError——"不发明新断言"在此强制。
    """
    status, reason = _status_for_feature_row(row, source_id)
    base = {
        "source_id": source_id,
        "profile": row.get("profiles", "").strip(),
        "owner": row.get("owner", "").strip(),
        "inputs": row.get("construction_prerequisites", "").strip(),
        "trigger": "",
        "command": resolve_command(row.get("command", "")),
        "cwd": resolve_command(row.get("cwd", "")),
        "subject": row.get("subject", "").strip(),
        "expected": "",
        "exit_code": row.get("exit_code", "").strip(),
        "actual": "",
    }
    subs: list[dict[str, str]] = []
    for suffix, column, verbatim, phase, note in segments[source_id]:
        if verbatim not in row.get(column, ""):
            raise RegistryError(
                f"06 行 {source_id}：拆分表子断言「{verbatim}」不是 {column} 列"
                "逐字原文（不得发明断言，须照抄源行后改表）"
            )
        subs.append({
            **base,
            "obligation_id": f"{source_id}-{suffix}",
            "assertion": f"{verbatim}（{note}）",
            "host": "",
            "evidence_path": row.get("evidence_path", "").strip(),
            "status": status,
            "failure_reason": reason,
            "phase": phase,
        })
    return subs


def _status_for_feature_row(row: dict[str, str], source_id: str) -> tuple[str, str]:
    stage = row.get("stage", "").strip()
    status06 = row.get("status", "").strip()
    if stage == "砍":
        return STATUS_EXCLUDED, CUT_ROW_REASON
    if status06 == "PENDING_USER_DECISION":
        return STATUS_NOT_RUN, ADJUDICATED_REASON
    if status06 in STATUS_VOCAB:
        return status06, ""
    raise RegistryError(
        f"06 行 {source_id}：status '{status06}' 在状态词表外"
        f"（允许 {'/'.join(sorted(STATUS_VOCAB))} 及 PENDING_USER_DECISION）"
    )


def build_ledger(rows06: list[dict[str, str]], rows07: list[dict[str, str]],
                 segments: dict | None = None) -> list[dict[str, str]]:
    """权威行 → 义务实例（纯函数，不落盘）。

    segments=复合行分期/方面拆分表；None 用模块表 COMPOSITE_SEGMENTS，
    测试注入合成表。宿主/形态实例不受表影响（只增不改）。
    """
    if segments is None:
        segments = COMPOSITE_SEGMENTS
    _require_columns(rows06, REQUIRED_06, "06-全量功能施工映射.csv")
    _require_columns(rows07, REQUIRED_07, "07-新增必需工程义务.csv")

    instances: list[dict[str, str]] = []
    for row in rows06:
        source_id = row.get("source_id", "").strip()
        if not source_id:
            raise RegistryError("06 存在 source_id 为空的行")
        status, reason = _status_for_feature_row(row, source_id)
        stage = row.get("stage", "").strip()
        status06 = row.get("status", "").strip()
        if source_id in segments and (status == STATUS_EXCLUDED
                                      or status06 == "PENDING_USER_DECISION"):
            if source_id not in ADJUDICATED_SEGMENT_OK:
                raise RegistryError(
                    f"06 行 {source_id}：砍行/已裁定分期行不得进复合拆分表"
                    "（F125 子实例挂账 B5 前随范围裁定，E27 裁决 #21；"
                    "白名单 ADJUDICATED_SEGMENT_OK 仅收范围已裁行，"
                    "现 F118＝裁决 #20）"
                )
        if (status != STATUS_EXCLUDED and status06 != "PENDING_USER_DECISION"
                and INDEPENDENT_INSTANCE_MARKER in row.get("phase", "")
                and later_stage_mentioned(row)
                and source_id not in segments):
            raise RegistryError(
                f"06 行 {source_id}：phase 声明「独立实例」且源文字跨期，"
                "但复合拆分表无条目（08:11 点名拆验未落实=权威漂移，"
                "先裁决补表再 expand）"
            )
        base = {
            "source_id": source_id,
            "assertion": row.get("acceptance", "").strip(),
            "profile": row.get("profiles", "").strip(),
            "owner": row.get("owner", "").strip(),
            "inputs": row.get("construction_prerequisites", "").strip(),
            "trigger": "",
            "command": resolve_command(row.get("command", "")),
            "cwd": resolve_command(row.get("cwd", "")),
            "subject": row.get("subject", "").strip(),
            "expected": "",
            "exit_code": row.get("exit_code", "").strip(),
            "actual": "",
            "phase": row.get("phase", "").strip(),
        }
        if status == STATUS_EXCLUDED:
            # 砍行：不拆宿主，evidence_path 保留权威原值（无实例宿主可替换）。
            instances.append({
                **base,
                "obligation_id": source_id,
                "host": "",
                "evidence_path": row.get("evidence_path", "").strip(),
                "status": status,
                "failure_reason": reason,
            })
        else:
            for host in hosts_for_feature_row(row):
                evidence = row.get("evidence_path", "").strip().replace("<profile>", host)
                instances.append({
                    **base,
                    "obligation_id": f"{source_id}-{host}",
                    "host": host,
                    "evidence_path": evidence,
                    "status": status,
                    "failure_reason": reason,
                })
            if source_id in segments:
                # 复合行分期/方面拆：子实例紧跟本行宿主实例登记（只增不改）。
                instances.extend(composite_sub_instances(row, source_id, segments))

    for row in rows07:
        oid = row.get("obligation_id", "").strip()
        if not oid:
            raise RegistryError("07 存在 obligation_id 为空的行")
        status07 = row.get("status", "").strip()
        if status07 not in STATUS_VOCAB:
            raise RegistryError(
                f"07 行 {oid}：status '{status07}' 在状态词表外"
                f"（允许 {'/'.join(sorted(STATUS_VOCAB))}）"
            )
        instances.append({
            "obligation_id": oid,
            "source_id": "",
            "assertion": row.get("acceptance", "").strip(),
            "profile": "",
            "host": "",
            "owner": row.get("owner", "").strip(),
            "inputs": row.get("prerequisites", "").strip(),
            "trigger": "",
            "command": resolve_command(row.get("command", "")),
            "cwd": resolve_command(row.get("cwd", "")),
            "subject": row.get("subject", "").strip(),
            "expected": "",
            "exit_code": row.get("exit_code", "").strip(),
            "actual": "",
            "evidence_path": row.get("evidence_path", "").strip(),
            "status": status07,
            "failure_reason": "",
            "phase": earliest_batch(row.get("phase", "").strip()),
        })

    for inst in instances:
        if inst["status"] not in STATUS_VOCAB:
            raise RegistryError(f"实例 {inst['obligation_id']}：状态 {inst['status']} 词表外")
    ids = [i["obligation_id"] for i in instances]
    if len(set(ids)) != len(ids):
        dup = sorted({i for i in ids if ids.count(i) > 1})
        raise RegistryError(f"obligation_id 重复：{dup}")
    return instances


def merge_with_existing(expected: list[dict[str, str]],
                        existing: list[dict[str, str]] | None,
                        ) -> tuple[list[dict[str, str]], list[str], list[str]]:
    """按 obligation_id 合并期望实例与既有台账（只增不改）。

    已存在的实例整行原样保留——台账上的销账状态（status/failure_reason/
    evidence_path 等手工登记）不因 expand 被权威输入覆盖；新实例按期望次序
    落在归属位置。existing 出现期望外的 id 属权威删改或手工加行，fail-closed
    报错，不做静默删除。返回 (merged, kept_ids, appended_ids)。
    """
    if not existing:
        return expected, [], [i["obligation_id"] for i in expected]
    old = {r["obligation_id"]: r for r in existing}
    if len(old) != len(existing):
        raise RegistryError("既有台账 obligation_id 有重复，先人工修复再 expand")
    extra = sorted(set(old) - {i["obligation_id"] for i in expected})
    if extra:
        raise RegistryError(
            f"既有台账存在期望外实例 {extra[:10]}"
            f"{'...' if len(extra) > 10 else ''}（权威已删改或手工加行，"
            "须先裁决处理，expand 不做静默删除）"
        )
    merged: list[dict[str, str]] = []
    kept: list[str] = []
    appended: list[str] = []
    for inst in expected:
        oid = inst["obligation_id"]
        if oid in old:
            merged.append(old[oid])
            kept.append(oid)
        else:
            merged.append(inst)
            appended.append(oid)
    return merged, kept, appended


def write_ledger(path: Path, instances: list[dict[str, str]]) -> None:
    # 行尾用 CRLF：与仓库既有 acceptance-ledger.csv 产物一致（T26 核对 blob），
    # 保证 expand 重生成的 diff 恰好只含新增实例行（既有实例逐字节保留可被
    # git diff 直接验证）。
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=LEDGER_FIELDS, extrasaction="raise",
                                lineterminator="\r\n")
        writer.writeheader()
        writer.writerows(instances)


def read_ledger(path: Path) -> list[dict[str, str]]:
    rows = _read_csv(path)
    _require_columns(rows, LEDGER_FIELDS, str(path))
    return rows


def load_inputs() -> tuple[list[dict[str, str]], list[dict[str, str]], dict]:
    rows06 = _read_csv(ROWS_06_CSV)
    rows07 = _read_csv(ROWS_07_CSV)
    with open(DENOMINATOR_JSON, encoding="utf-8") as f:
        denom = json.load(f)
    return rows06, rows07, denom


def _merged_stage_expectations(denom: dict) -> dict[str, int]:
    """denominator.json 的 stage_counts 把已裁定行单列（待裁-v1.5/待裁-v2），
    06 的 stage 列已并入 v1.5/v2，故合并后比对。"""
    sc = denom.get("stage_counts", {})
    return {
        "v1": sc.get("v1", 0),
        "v1.5": sc.get("v1.5", 0) + sc.get("待裁-v1.5", 0),
        "v2": sc.get("v2", 0) + sc.get("待裁-v2", 0),
        "砍": sc.get("砍", 0),
        "非功能-许可": sc.get("非功能-许可", 0),
    }


def validate(denom: dict, rows06: list[dict[str, str]], rows07: list[dict[str, str]],
             ledger: list[dict[str, str]],
             segments: dict | None = None) -> tuple[dict, list[str]]:
    """核对分母与台账一致性。返回 (counts, problems)；problems 非空即不符。

    segments 透传 build_ledger（与被检台账同一张拆分表；None=模块表）。
    """
    problems: list[str] = []
    counts: dict[str, object] = {}

    source_rows = len(rows06)
    counts["来源功能行(06)"] = source_rows
    if source_rows != denom.get("source_rows"):
        problems.append(f"06 行数 {source_rows} != denominator.source_rows {denom.get('source_rows')}")

    stage_actual = Counter(r.get("stage", "").strip() for r in rows06)
    stage_expected = _merged_stage_expectations(denom)
    for stage, want in stage_expected.items():
        counts[f"stage={stage}"] = stage_actual.get(stage, 0)
        if stage_actual.get(stage, 0) != want:
            problems.append(f"stage={stage} 实际 {stage_actual.get(stage, 0)} != 分母 {want}")
    if sum(stage_actual.values()) != source_rows:
        problems.append(f"stage 计数总和 {sum(stage_actual.values())} != 行数 {source_rows}")

    license_rows = stage_actual.get("非功能-许可", 0)
    counts["功能行"] = source_rows - license_rows
    counts["许可行"] = license_rows
    if license_rows != source_rows - denom.get("functional_rows", 0):
        problems.append(
            f"功能+许可拆分不符：许可行 {license_rows}，"
            f"应为 {source_rows} - functional_rows {denom.get('functional_rows')}"
        )

    cut_rows = stage_actual.get("砍", 0)
    if cut_rows != denom.get("excluded_function_rows"):
        problems.append(f"砍行 {cut_rows} != denominator.excluded_function_rows {denom.get('excluded_function_rows')}")

    pending = sum(1 for r in rows06 if r.get("status", "").strip() == "PENDING_USER_DECISION")
    counts["已裁定分期行"] = pending
    if pending != denom.get("pending_function_rows"):
        problems.append(f"已裁定行 {pending} != denominator.pending_function_rows {denom.get('pending_function_rows')}")

    obligations = len(rows07)
    counts["工程义务(07)"] = obligations
    if obligations != denom.get("additional_engineering_obligations"):
        problems.append(
            f"07 义务数 {obligations} != denominator.additional_engineering_obligations "
            f"{denom.get('additional_engineering_obligations')}"
        )

    status_counts = Counter(i.get("status", "") for i in ledger)
    for bad in sorted(set(status_counts) - STATUS_VOCAB):
        problems.append(f"台账出现词表外状态 '{bad}' x{status_counts[bad]}")
    for st in sorted(STATUS_VOCAB):
        counts[f"台账 status={st}"] = status_counts.get(st, 0)
    total = len(ledger)
    counts["台账实例总数"] = total
    covered = sum(status_counts.get(st, 0) for st in STATUS_VOCAB)
    if covered != total:
        problems.append(f"四状态计数总和 {covered} != 实例总数 {total}")
    ledger_excluded = [i for i in ledger if i.get("status") == STATUS_EXCLUDED]
    cut_excluded = [i for i in ledger_excluded
                    if i.get("failure_reason", "") == CUT_ROW_REASON]
    adjudicated_excluded = [
        i for i in ledger_excluded
        if i.get("failure_reason", "").startswith(ADJUDICATED_EXCLUDED_PREFIX)
    ]
    other_excluded = (len(ledger_excluded) - len(cut_excluded)
                      - len(adjudicated_excluded))
    if other_excluded:
        problems.append(
            f"台账 {other_excluded} 条 EXCLUDED 既非砍行"
            f"（failure_reason={CUT_ROW_REASON}）亦非裁决性"
            f"（failure_reason 以「{ADJUDICATED_EXCLUDED_PREFIX}」开头）"
            "——EXCLUDED 仅允许砍行/裁决性两类，防为过门偷改状态"
        )
    if len(cut_excluded) != cut_rows:
        problems.append(
            f"台账砍行 EXCLUDED {len(cut_excluded)} != 砍行 {cut_rows}"
        )
    counts["台账 status=EXCLUDED(裁决性)"] = len(adjudicated_excluded)

    expected = build_ledger(rows06, rows07, segments)
    expected_ids = {i["obligation_id"] for i in expected}
    ledger_ids = [i.get("obligation_id", "") for i in ledger]
    missing = sorted(expected_ids - set(ledger_ids))
    extra = sorted(set(ledger_ids) - expected_ids)
    if missing:
        problems.append(f"台账缺实例 {missing[:10]}{'...' if len(missing) > 10 else ''}")
    if extra:
        problems.append(f"台账多出实例 {extra[:10]}{'...' if len(extra) > 10 else ''}")
    if len(set(ledger_ids)) != len(ledger_ids):
        problems.append("台账 obligation_id 有重复")
    counts["期望实例总数(重算)"] = len(expected)

    return counts, problems


def group_incomplete(ledger: list[dict[str, str]]) -> dict[tuple[str, str], list[str]]:
    """未完成（NOT_RUN/IMPLEMENTING）实例按 (phase, owner) 分组。"""
    groups: dict[tuple[str, str], list[str]] = {}
    for inst in ledger:
        if inst.get("status") in (STATUS_NOT_RUN, STATUS_IMPLEMENTING):
            key = (inst.get("phase", ""), inst.get("owner", ""))
            groups.setdefault(key, []).append(inst.get("obligation_id", ""))
    return groups


def _batch_sort_key(phase: str) -> int:
    token = earliest_batch(phase)
    return BATCH_ORDER.index(token) if token in BATCH_ORDER else len(BATCH_ORDER)


def cmd_expand() -> int:
    rows06, rows07, _ = load_inputs()
    instances = build_ledger(rows06, rows07)
    existing = read_ledger(LEDGER_CSV) if LEDGER_CSV.exists() else None
    merged, kept, appended = merge_with_existing(instances, existing)
    write_ledger(LEDGER_CSV, merged)
    by_status = Counter(i["status"] for i in merged)
    print(f"[registry] expand：06 来源行 {len(rows06)}，07 义务 {len(rows07)}，"
          f"实例 {len(merged)}（保留既有 {len(kept)}，新增 {len(appended)}）"
          f"→ {LEDGER_CSV.relative_to(REPO_ROOT)}")
    if appended:
        print(f"[registry]   新增：{', '.join(appended)}")
    for st in sorted(STATUS_VOCAB):
        print(f"[registry]   status={st}: {by_status.get(st, 0)}")
    return 0


def cmd_validate() -> int:
    rows06, rows07, denom = load_inputs()
    ledger = read_ledger(LEDGER_CSV)
    counts, problems = validate(denom, rows06, rows07, ledger)
    print(f"[registry] validate：分母权威 {DENOMINATOR_JSON.relative_to(REPO_ROOT)}")
    for key in sorted(counts):
        print(f"[registry]   {key}: {counts[key]}")
    if problems:
        print(f"[registry] validate：{len(problems)} 处不符", file=sys.stderr)
        for p in problems:
            print(f"[registry]   不符：{p}", file=sys.stderr)
        return 2
    print("[registry] validate：分母与台账一致，PASS")
    return 0


def cmd_report() -> int:
    ledger = read_ledger(LEDGER_CSV)
    status_counts = Counter(i.get("status", "") for i in ledger)
    print(f"[registry] report：实例总数 {len(ledger)}，"
          + "，".join(f"{st} {status_counts.get(st, 0)}" for st in sorted(STATUS_VOCAB)))
    groups = group_incomplete(ledger)
    if not groups:
        print("[registry] report：无未完成实例")
        return 0
    total_incomplete = sum(len(v) for v in groups.values())
    print(f"[registry] report：未完成 {total_incomplete} 实例，按 phase/owner 汇总——")
    for (phase, owner) in sorted(groups, key=lambda k: (_batch_sort_key(k[0]), k[0], k[1])):
        ids = groups[(phase, owner)]
        print(f"[registry]   phase={phase}  owner={owner}  共 {len(ids)}")
        print(f"[registry]     {', '.join(ids)}")
    return 0


def main(argv: list[str] | None = None) -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass
    args = list(sys.argv[1:] if argv is None else argv)
    commands = {"expand": cmd_expand, "validate": cmd_validate, "report": cmd_report}
    if not args or args[0] not in commands:
        print("用法：python -X utf8 registry.py {expand|validate|report}", file=sys.stderr)
        print("拆分规则见本文件模块 docstring：宿主/形态拆 + 复合行分期/方面拆"
              "（表 COMPOSITE_SEGMENTS，只增不改）。", file=sys.stderr)
        return 2
    try:
        return commands[args[0]]()
    except RegistryError as exc:
        print(f"[registry] 错误：{exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())

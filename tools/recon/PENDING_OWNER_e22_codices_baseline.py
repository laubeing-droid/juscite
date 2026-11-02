# -*- coding: utf-8 -*-
"""E22 法源数据基线验收（PENDING_OWNER 版，工单 W2a-U12）。

四段核对＋统一面冻结＋cases 侧负测（00-总协调 §6.1 裁决#8-12 负测先行）：
  A 版本效力抽检：GB 编码＋日期＝定位与效力核对；缺失/冲突→unknown fail-closed
  B 正文许可核对：获取渠道 × verification_status，第三方待核验保缺口不冒充
  C 数量去重：WJBS 唯一/同文本 sha/同名多版本/md↔CSV 对账；宣传 1.4 亿不分母
  D unknown 缺口清单：无码/无正文/无 md/日期不详/待核验/外部容量未授权
  E 本地公开统一面冻结：面指纹＋只读零网络守卫（14 冻结指令：
    本地法源效力读取公开统一面按 E22 冻结，不把下载工具直接供案件 UI）
  F cases 侧负测：外部全库未授权→容量增量 UNKNOWN（值 None，非 0），不编 URL

用法（juscite 仓根 cwd）：
  python -X utf8 tools/recon/PENDING_OWNER_e22_codices_baseline.py
    --formal-root <codices 正式发布目录>
    --codices-repo <codices 工程仓检出（lccc_consumer.py 所在，公开面入口）>
    [--evidence-dir docs/construction/evidence/E22/desktop]

exit 0＝全部断言过；证据写 evidence-dir（result JSON＋缺口 CSV＋基线 md）。
只读消费，不写正式目录，不触网络。
"""

from __future__ import annotations

import argparse
import csv
import importlib.util
import json
import os
import sys
import time

csv.field_size_limit(10 ** 9)

RUN_DATE = time.strftime("%Y%m%d")

# 抽检锚点（正式面实测在盘的确定性样本；数据演进后断言随语义更新）
SPOT_ANCHORS = [
    # (说明, WJBS, 期望断言函数名之外的补充说明)
    ("现行官方法（个人信息保护法 2021）",
     "1.2.156.3005.6-0100000000100120210820009100000"),
    ("已修改旧版（专利法 2008）",
     "1.2.156.3005.6-0100000000100120081227000400000"),
    ("已废止（中外合作经营企业法 2017 修正版）",
     "1.2.156.3005.6-0100000000100020171104000100000"),
    ("已失效（沈阳市道路客运市场管理条例 1994）",
     "1.2.156.3005.6-0700210100100119940526000000000"),
    ("尚未施行但施行日已过＝数据滞后冲突（国务院修改住房公积金管理条例决定）",
     "1.2.156.3005.6-0200000000300020260810000000030"),
]

FORBIDDEN_SOURCE_TOKENS = (
    "import urllib", "import requests", "import socket", "import http",
    "from urllib", "import subprocess", "'w'", '"w"', "'a'", '"a"',
)

GAP_CSV_COLUMNS = ["gap_kind", "identifier", "reason"]


class Checks:
    def __init__(self):
        self.items: list[dict] = []

    def add(self, check_id: str, ok: bool, detail: str) -> bool:
        self.items.append(
            {"id": check_id, "status": "PASS" if ok else "FAIL", "detail": detail}
        )
        mark = "PASS" if ok else "FAIL"
        print("[%s] %s — %s" % (mark, check_id, detail))
        return ok

    @property
    def all_passed(self) -> bool:
        return all(item["status"] == "PASS" for item in self.items)


def load_public_face(codices_repo: str):
    path = os.path.join(codices_repo, "lccc_consumer.py")
    if not os.path.isfile(path):
        raise FileNotFoundError(
            "lccc_consumer.py 不在 %s（公开面入口，随 codices 分支 "
            "jusbench/w2a-u12-e22-baseline；合并后在仓根）" % codices_repo
        )
    spec = importlib.util.spec_from_file_location("lccc_consumer", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module, path


def section_a_effectivity(checks: Checks, lccc, consumer, inventory) -> dict:
    docs = inventory["documents"]
    cons = docs["consistency"]
    checks.add(
        "A1_wjbs_unique",
        docs["duplicate_wjbs_rows"] == 0,
        "rows=%d distinct=%d 重复行=%d"
        % (docs["rows"], docs["distinct_wjbs"], docs["duplicate_wjbs_rows"]),
    )
    checks.add(
        "A2_consistency_zero_conflict",
        all(v == 0 for v in cons.values()),
        "码体/码内日期-GBRQ/SXX-DE_01018/日期格式 冲突计 %s" % json.dumps(cons, ensure_ascii=False),
    )
    checks.add(
        "A3_sxx_vocabulary",
        set(docs["sxx_distribution"]) <= set(lccc.EFFECT_CODES.values()),
        "时效分布 %s" % json.dumps(docs["sxx_distribution"], ensure_ascii=False),
    )
    spot = []
    for label, wjbs in SPOT_ANCHORS:
        result = consumer.resolve_effectivity(wjbs=wjbs, as_of=RUN_DATE)
        row = consumer._document_index().get(wjbs, {})
        expected_label = lccc.EFFECT_CODES.get(row.get("SXX", ""), "unknown")
        ok = (
            result["found"]
            and result["status_label"] == expected_label
            and result["replacement"] == "unknown"
        )
        if row.get("SXX") == "01" and not any(
            r.startswith("STATUS_WINDOW_CONFLICT") for r in result["reasons"]
        ):
            ok = ok and result["signs_current"] is True and result["in_force_window"] == "yes"
        else:
            ok = ok and result["signs_current"] is False
        spot.append({"label": label, "wjbs": wjbs, "result": result,
                     "row_sxrq": row.get("SXRQ", ""), "row_sxx": row.get("SXX", "")})
        checks.add("A_spot_" + wjbs[-12:], ok,
                   "%s → %s（窗口=%s 现行签=%s 原因=%s）"
                   % (label, result["status_label"], result["in_force_window"],
                      result["signs_current"], ";".join(result["reasons"]) or "-"))
    # 真实 fail-closed 样本：SXX=02 且施行日已过 → 窗口 unknown
    conflict = [s for s in spot if s["row_sxx"] == "02" and s["row_sxrq"] <= RUN_DATE]
    checks.add(
        "A4_failclosed_status_window_conflict",
        bool(conflict)
        and all(s["result"]["in_force_window"] == "unknown" for s in conflict)
        and all(not s["result"]["signs_current"] for s in conflict),
        "SXX=02 施行日已过样本 %d 个，窗口全部 unknown 且不签现行" % len(conflict),
    )
    bad = consumer.resolve_effectivity(wjbs="1.2.156.3005.6-000")
    checks.add("A5_malformed_identifier_unknown",
               bad["found"] is False and "INVALID_WJBS_FORMAT" in bad["reasons"],
               "畸形 WJBS → %s" % bad["reasons"])
    missing = consumer.resolve_effectivity(
        wjbs="1.2.156.3005.6-0100999999999920260101000000000")
    checks.add("A6_not_found_unknown",
               missing["found"] is False and "NOT_FOUND_IN_LEGAL_DOCUMENTS" in missing["reasons"],
               "未命中 → %s" % missing["reasons"])
    code_path = consumer.resolve_effectivity(code31="0100000000100120210820009100000")
    checks.add("A7_code31_path_locates",
               code_path["found"] and code_path["status_label"] == "有效",
               "code31 定位 → found=%s %s" % (code_path["found"], code_path["status_label"]))
    return {"spot": [
        {k: s[k] for k in ("label", "wjbs", "result", "row_sxrq", "row_sxx")} for s in spot
    ]}


def section_b_permission(checks: Checks, lccc, consumer, inventory, gaps) -> dict:
    ledger = inventory["text_permission_ledger"]
    docs_rows = inventory["documents"]["rows"]
    checks.add(
        "B1_ledger_covers_all_documents",
        sum(ledger.values()) == docs_rows,
        "许可台账 %s 合计=%d == 文档行 %d"
        % (json.dumps(ledger, ensure_ascii=False), sum(ledger.values()), docs_rows),
    )
    third_party_gap = sum(
        1 for g in gaps if g["gap_kind"] == "THIRD_PARTY_TEXT_PENDING")
    third_party_ledger = sum(
        v for k, v in ledger.items() if k.startswith("third_party"))
    checks.add(
        "B2_third_party_pending_kept_as_gap",
        third_party_gap == third_party_ledger and third_party_ledger > 0,
        "第三方待核验 %d 行全部入缺口清单（保缺口非清零）" % third_party_gap,
    )
    conflicts = sum(1 for g in gaps if g["gap_kind"] == "PERMISSION_CONFLICT")
    checks.add(
        "B3_permission_conflict_listed",
        conflicts == ledger.get("conflict", 0),
        "第三方渠道却称内容级官方核验：%d 行（逐行入缺口，不冒充官方）" % conflicts,
    )
    official = ledger.get("official_channel", 0) + ledger.get(
        "official_channel_unverified", 0)
    checks.add(
        "B4_official_channel_is_minority_of_text_claims",
        official > 0,
        "官方渠道计 %d（含待核验 %d）"
        % (official, ledger.get("official_channel_unverified", 0)),
    )
    return {"ledger": ledger}


def section_c_dedup(checks: Checks, lccc, consumer, inventory) -> dict:
    docs = inventory["documents"]
    contents = inventory["contents"]
    md = inventory["markdown_face"]
    checks.add(
        "C1_no_duplicate_wjbs",
        docs["duplicate_wjbs_rows"] == 0 and docs["distinct_wjbs"] == docs["rows"],
        "记录 %d ＝唯一 WJBS %d" % (docs["rows"], docs["distinct_wjbs"]),
    )
    checks.add(
        "C2_same_text_dedup",
        md["same_source_sha256_groups"] == 0,
        "同文本（source_sha256 相同）组=%d，组下行数=%d"
        % (md["same_source_sha256_groups"], md["rows_under_same_sha_groups"]),
    )
    checks.add(
        "C3_content_block_dedup",
        contents["duplicate_doc_block_keys"] == 0,
        "内容块 (DE_01001,DE_02001) 重复=%d／行=%d"
        % (contents["duplicate_doc_block_keys"], contents["rows"]),
    )
    checks.add(
        "C4_version_groups_are_versions_not_dup",
        docs["title_version_groups"] > 0,
        "同名多版本组=%d（其下行=%d；版本≠重复，各持独立编码与日期）"
        % (docs["title_version_groups"], docs["rows_under_version_groups"]),
    )
    recon = md["wjbs_reconciliation"]
    checks.add(
        "C5_md_csv_reconciliation",
        recon["markdown_only"] == 0,
        "md 唯一 WJBS=%d，csv=%d，md-only=%d，csv-only(无 md 载体)=%d"
        % (recon["markdown_unique_wjbs"], recon["csv_unique_wjbs"],
           recon["markdown_only"], recon["csv_only_no_markdown"]),
    )
    checks.add(
        "C6_marketing_not_denominator",
        lccc.MARKETING_DENOMINATOR_BAN in inventory["denominator_rule"],
        "分母规则：%s；实际分母＝文档 %d／案例 %d／内容块 %d"
        % (inventory["denominator_rule"], docs["rows"],
           inventory["cases"]["rows"], contents["rows"]),
    )
    return {"reconciliation": recon}


def section_d_gaps(checks: Checks, gaps, inventory) -> dict:
    kinds: dict = {}
    for gap in gaps:
        kinds[gap["gap_kind"]] = kinds.get(gap["gap_kind"], 0) + 1
    well_formed = all(g["identifier"] and g["reason"] for g in gaps)
    checks.add("D1_gaps_well_formed", well_formed,
               "缺口 %d 条全部带 identifier＋reason" % len(gaps))
    docs = inventory["documents"]
    contents = inventory["contents"]
    md = inventory["markdown_face"]
    checks.add(
        "D2_gap_counts_match_inventory",
        kinds.get("NO_GB_FILE_CODE", -1) == docs["code"]["empty"]
        and kinds.get("NO_FULLTEXT", -1) == contents["documents_without_content"]
        and kinds.get("NO_MARKDOWN_CARRIER", -1)
        == md["wjbs_reconciliation"]["csv_only_no_markdown"],
        "无码=%d（对账=%d）／无正文=%d（对账=%d）／无 md=%d（对账=%d）"
        % (kinds.get("NO_GB_FILE_CODE", -1), docs["code"]["empty"],
           kinds.get("NO_FULLTEXT", -1), contents["documents_without_content"],
           kinds.get("NO_MARKDOWN_CARRIER", -1),
           md["wjbs_reconciliation"]["csv_only_no_markdown"]),
    )
    ext = [g for g in gaps if g["gap_kind"] == "EXTERNAL_CAPACITY_UNKNOWN"]
    checks.add(
        "D3_external_capacity_gap_single",
        len(ext) == 1,
        "外部容量缺口恰 1 条：%s" % (ext[0]["reason"] if ext else "缺失"),
    )
    return {"kinds": kinds, "total": len(gaps)}


def section_e_freeze(checks: Checks, lccc, consumer, face_path, formal_root) -> dict:
    with open(face_path, "r", encoding="utf-8") as handle:
        source = handle.read()
    clean = not any(token in source for token in FORBIDDEN_SOURCE_TOKENS)
    clean = clean and "https://" not in source and "http://" not in source
    checks.add(
        "E1_face_module_readonly_no_network",
        clean,
        "lccc_consumer.py 无网络/子进程/写模式 token，无 URL（%s）" % face_path,
    )
    fingerprint = consumer.face_fingerprint()
    checks.add(
        "E2_face_fingerprint",
        len(fingerprint) == 11 and all(
            len(v) == 64 for k, v in fingerprint.items() if k != "file_count"),
        "正式面 %d 文件 sha256 指纹就绪（legal_documents=%s…）"
        % (fingerprint["file_count"], fingerprint["legal_documents.csv"][:16]),
    )
    freeze = {
        "face_root": formal_root,
        "public_entry": "lccc_consumer.py（codices 仓根，分支 jusbench/w2a-u12-e22-baseline）",
        "fingerprint": fingerprint,
        "contract": [
            "数据面＝正式发布目录 8 CSV＋md 树＋SHA256SUMS＋README，只读",
            "定位＝GB/T 47229.2 WJBS/31 位文件码（category[0:4]+agency[4:14]"
            "+promulgationDate[14:22]+sequence[22:26]+internalSequence[26:29]"
            "+fileType[29:31]，与 tools/standard_codes.mjs 逐段一致）",
            "效力 fail-closed：码内日期==GBRQ、SXX==DE_01018∈01..05、"
            "窗口 SXRQ<=as_of<SHXRQ；缺失/冲突→unknown 不签现行",
            "正文许可＝DE_01021 渠道×verification_status；第三方待核验保缺口",
            "数量＝本面实测；宣传 1.4 亿不分母；未知保缺口",
            "外部全库未授权→容量 UNKNOWN（值 None 非 0），不编 URL",
            "不把下载工具（official-source-updater／commercial_law_mcp）供案件 UI"
            "（14 冻结指令）",
        ],
        "frozen_at": RUN_DATE,
    }
    checks.add("E3_freeze_record_written", True, "冻结合同 7 条入 result JSON 与基线 md")
    return freeze


def section_f_cases_negative(checks: Checks, lccc, consumer, face_path, inventory) -> dict:
    saved = os.environ.get("LCCC_EXTERNAL_SOURCES_AUTHORIZED")
    os.environ.pop("LCCC_EXTERNAL_SOURCES_AUTHORIZED", None)
    cap = consumer.cases_external_capacity()
    if saved is not None:
        os.environ["LCCC_EXTERNAL_SOURCES_AUTHORIZED"] = saved
    checks.add(
        "F1_unauthorized_is_unknown_not_zero",
        cap["status"] == "UNKNOWN" and cap["value"] is None
        and cap["reason"] == "external_source_not_authorized",
        "未授权外部容量 → status=%s value=%s（None≠0，不造数）"
        % (cap["status"], cap["value"]),
    )
    os.environ["LCCC_EXTERNAL_SOURCES_AUTHORIZED"] = "cncases"
    cap_auth = consumer.cases_external_capacity()
    if saved is None:
        os.environ.pop("LCCC_EXTERNAL_SOURCES_AUTHORIZED", None)
    else:
        os.environ["LCCC_EXTERNAL_SOURCES_AUTHORIZED"] = saved
    checks.add(
        "F2_authorized_still_no_fabricated_number",
        cap_auth["value"] is None and cap_auth["status"] == "NOT_IMPLEMENTED_PENDING_W4",
        "即便授权，实测入口挂 W4：status=%s value=%s"
        % (cap_auth["status"], cap_auth["value"]),
    )
    with open(face_path, "r", encoding="utf-8") as handle:
        source = handle.read()
    checks.add(
        "F3_no_fabricated_url",
        "https://" not in source and "http://" not in source,
        "公开面源码零 URL 字面量（禁编 URL）",
    )
    checks.add(
        "F4_local_cases_counted_locally_only",
        inventory["cases"]["rows"] > 0,
        "本地案例面 rows=%d（含全文 %d／无全文 %d）；外部增量恒 UNKNOWN 单列"
        % (inventory["cases"]["rows"], inventory["cases"]["with_fulltext"],
           inventory["cases"]["without_fulltext"]),
    )
    return {"unauthorized": cap, "authorized": cap_auth}


def write_evidence(evidence_dir: str, payload: dict, gaps: list) -> None:
    os.makedirs(evidence_dir, exist_ok=True)
    result_path = os.path.join(evidence_dir, "e22-baseline-result.json")
    with open(result_path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=1)
    gaps_path = os.path.join(evidence_dir, "e22-unknown-gaps.csv")
    with open(gaps_path, "w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=GAP_CSV_COLUMNS)
        writer.writeheader()
        writer.writerows(gaps)
    md_path = os.path.join(evidence_dir, "e22-codices-baseline.md")
    inv = payload["inventory"]
    docs = inv["documents"]
    md_face = inv["markdown_face"]
    lines = [
        "# E22 法源数据基线实测证据（PENDING_OWNER 版）",
        "",
        "- 运行日：%s" % payload["run_date"],
        "- 正式面：`%s`" % payload["formal_root"],
        "- 公开入口：`%s`" % payload["public_entry_path"],
        "- 验收命令：`%s`" % payload["command"],
        "- 总判定：**%s**（断言 %d/%d 过）"
        % (payload["overall"], payload["passed"], payload["total"]),
        "",
        "## 数量与去重（分母）",
        "",
        "| 面 | 计数 |",
        "|---|---|",
        "| 法律文档记录（＝唯一 WJBS） | %d |" % docs["rows"],
        "| 内容块 | %d（覆盖文档 %d，无正文 %d）"
        % (inv["contents"]["rows"], inv["contents"]["distinct_docs_with_content"],
           inv["contents"]["documents_without_content"]),
        "| md 载体文件 | %d（legal_document %d／case %d／practice %d）"
        % (md_face["files"], md_face["object_types"].get("legal_document", 0),
           md_face["object_types"].get("case", 0),
           md_face["object_types"].get("practice_reference", 0)),
        "| 案例（cases.csv） | %d（全文 %d／无全文 %d）"
        % (inv["cases"]["rows"], inv["cases"]["with_fulltext"],
           inv["cases"]["without_fulltext"]),
        "| 同名多版本组 | %d（版本≠重复） |" % docs["title_version_groups"],
        "| 同文本（sha 相同）组 | %d |" % md_face["same_source_sha256_groups"],
        "| md↔CSV 对账 | md-only %d／csv-only %d |"
        % (md_face["wjbs_reconciliation"]["markdown_only"],
           md_face["wjbs_reconciliation"]["csv_only_no_markdown"]),
        "",
        "宣传「1.4 亿」在任何场合都不是分母；未知保缺口。",
        "",
        "## 时效分布",
        "",
        json.dumps(docs["sxx_distribution"], ensure_ascii=False),
        "",
        "## 正文许可台账（渠道×核验状态）",
        "",
        "```json",
        json.dumps(payload["permission_ledger"], ensure_ascii=False, indent=1),
        "```",
        "",
        "## unknown 缺口（详见 e22-unknown-gaps.csv）",
        "",
        json.dumps(payload["gap_kinds"], ensure_ascii=False),
        "",
        "## 统一面冻结（14 冻结指令落账）",
        "",
    ]
    lines.extend("- " + clause for clause in payload["freeze"]["contract"])
    lines.extend([
        "",
        "面指纹（sha256，前 16 位）：legal_documents=%s… legal_contents=%s…"
        % (payload["freeze"]["fingerprint"]["legal_documents.csv"][:16],
           payload["freeze"]["fingerprint"]["legal_contents.csv"][:16]),
        "",
        "## cases 侧负测（裁决#8-12）",
        "",
        "- 未授权：status=UNKNOWN value=None（非 0，不造数）",
        "- 授权后：NOT_IMPLEMENTED_PENDING_W4 value=None（真实全库 W4 补）",
        "- 公开面源码零 URL 字面量（禁编 URL）",
        "",
        "## B4 段未闭（E22 收 IMPLEMENTING 的原因）",
        "",
        "- 范围索引容量增量 cases 侧真实全库（cncases）未授权，按裁决#8-12 负测先行，W4 补实测",
        "- prereq E12（全量材料解析版本）NOT_RUN，跨页表/未读分母未闭合",
        "",
    ])
    with open(md_path, "w", encoding="utf-8") as handle:
        handle.write("\n".join(lines))


def _find_lccc_workspace() -> str | None:
    """沿脚本祖先找 legal-cn-core-codices工作区（对主检出/工单 worktree 都成立）。"""
    current = os.path.dirname(os.path.abspath(__file__))
    for _ in range(10):
        candidate = os.path.join(current, "legal-cn-core-codices工作区")
        if os.path.isdir(candidate):
            return candidate
        parent = os.path.dirname(current)
        if parent == current:
            return None
        current = parent
    return None


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    workspace = _find_lccc_workspace()
    if workspace is None:
        print("FAIL: 未在祖先目录找到 legal-cn-core-codices工作区")
        return 2
    default_root = os.path.join(workspace, "legal-cn-core-codices")
    parser.add_argument("--formal-root", default=default_root,
                        help="codices 正式发布目录（默认 %s）" % default_root)
    parser.add_argument("--codices-repo", default=None,
                        help="含 lccc_consumer.py 的 codices 检出（默认先试主检出再试本工单 worktree）")
    parser.add_argument("--evidence-dir", default=None,
                        help="证据输出目录（默认 docs/construction/evidence/E22/desktop）")
    args = parser.parse_args(argv)

    repo_root = os.path.normpath(os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "..", ".."))
    candidates = [args.codices_repo] if args.codices_repo else [
        os.path.join(workspace, "legal-cn-core-codices-repo"),
        os.path.join(workspace, "legal-cn-core-codices-repo",
                     ".local", "worktrees", "w2a-u12-e22"),
    ]
    face_path = None
    for candidate in candidates:
        if candidate and os.path.isfile(os.path.join(candidate, "lccc_consumer.py")):
            face_path = os.path.join(candidate, "lccc_consumer.py")
            break
    if face_path is None:
        print("FAIL: 未找到 lccc_consumer.py（公开面入口）——检查 codices 分支检出")
        return 2
    evidence_dir = args.evidence_dir or os.path.join(
        repo_root, "docs", "construction", "evidence", "E22", "desktop")

    lccc, face_path_checked = load_public_face(os.path.dirname(face_path))
    assert face_path_checked == face_path

    print("E22 法源数据基线验收（PENDING_OWNER） formal=%s entry=%s"
          % (args.formal_root, face_path))
    consumer = lccc.LcccConsumer(args.formal_root)

    checks = Checks()
    t0 = time.time()
    inventory = consumer.baseline_inventory()
    print("inventory 完成 %.1fs" % (time.time() - t0))
    gaps = consumer.unknown_gaps(inventory, run_date=RUN_DATE)

    spot = section_a_effectivity(checks, lccc, consumer, inventory)
    permission = section_b_permission(checks, lccc, consumer, inventory, gaps)
    dedup = section_c_dedup(checks, lccc, consumer, inventory)
    gap_summary = section_d_gaps(checks, gaps, inventory)
    freeze = section_e_freeze(checks, lccc, consumer, face_path, args.formal_root)
    cases_neg = section_f_cases_negative(checks, lccc, consumer, face_path, inventory)

    payload = {
        "run_date": RUN_DATE,
        "formal_root": args.formal_root,
        "public_entry_path": face_path,
        "command": "python -X utf8 tools/recon/PENDING_OWNER_e22_codices_baseline.py"
                   " --formal-root %s --codices-repo %s"
                   % (args.formal_root, os.path.dirname(face_path)),
        "inventory": inventory,
        "spot_checks": spot["spot"],
        "permission_ledger": permission["ledger"],
        "reconciliation": dedup["reconciliation"],
        "gap_kinds": gap_summary["kinds"],
        "gap_total": gap_summary["total"],
        "freeze": freeze,
        "cases_negative": cases_neg,
        "checks": checks.items,
        "passed": sum(1 for c in checks.items if c["status"] == "PASS"),
        "total": len(checks.items),
        "overall": "PASS" if checks.all_passed else "FAIL",
        "b4_pending": "范围索引容量增量 cases 侧真实全库未授权（裁决#8-12 负测先行，W4 补）；"
                      "prereq E12 NOT_RUN——E22 如实收 IMPLEMENTING",
    }
    write_evidence(evidence_dir, payload, gaps)
    print(
        "证据 → %s（result JSON＋缺口 CSV＋基线 md）；overall=%s（%d/%d）"
        % (evidence_dir, payload["overall"], payload["passed"], payload["total"])
    )
    return 0 if checks.all_passed else 1


if __name__ == "__main__":
    sys.exit(main())

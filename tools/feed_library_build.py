# -*- coding: utf-8 -*-
"""一次性融入进库脚本（施工波-20261030 · 单元=融入进库）。

把 ≈2686 中国法侧件按三层口径落成「库被喂」索引库（manifest）：
  L1 直接进层 = readable 中国侧成品（cn- 前缀 + 中性无前缀；外域前缀出局）
  L2 复核层   = held-551-纯复核名单.md 名单驱动的 held 记录（复核未放行，禁入直接进层）
  L3 储备层   = reserve 池（RESERVE_BY_DESIGN）中国侧活件（剔退役/剔境外待适配/剔已在 L2）

甄别四刀归宿（决策台账 2026-10-29 代码黏着性判据/带码件三验/广场否决三行）：
  本库 2686 件全部为蒸馏记录（纯文）→ 默认手册线；tool_capability 类标工作台参照（B 面）；
  带码直吸件（pe-vc Apache-2.0 / contract-review-3 MIT-0）在 sources 包级处置，不在本库范围；
  广场零上架（长尾不占页面，只经 K5 推送/manual.search/办案包方法组三通道被喂）。

本脚本只建索引（manifest），不搬运正文——归档区只进不改，正文出域走 manuals 信任管线
（lh-distill-ingest/1，合同草案 ingest-contract-draft.md），本库不是第二真源。

计数=脚本输出（stdout 汇总行），非账面估算；断言失败即退出非零（fail-fast）。
确定性：无随机源、排序稳定、无时间戳（仅日期），重跑字节一致。
"""
import json
import hashlib
import re
import sys
from pathlib import Path
from collections import Counter, defaultdict

ARCHIVE = Path(r"D:/Codex/1.法律工作区/legal-cn-distillation工作区/legal-cn-distill-skills/4.归档区/20260925")
W1 = ARCHIVE / "route3-2049-skills-final-v1"
ROSTER = Path(r"D:/Codex/1.法律工作区/jusbench工作区/竞品情报/2026-10-29-规格波/held-551-纯复核名单.md")
OUT = Path(__file__).resolve().parents[1] / "docs" / "库被喂" / "manifests"
GEN_DATE = "2026-10-30"

# 决策台账 :54（境外裁决·融入总账定版）的外域前缀集：us 682/eu 51/fr 21/uk 9/au/de/jp 各1 + gdpr 14 + icelandic 9 = 789
FOREIGN_PREFIX = {"us", "eu", "fr", "uk", "au", "de", "jp", "gdpr", "icelandic"}
SOURCE_ROOT = str(W1).replace("\\", "/")


def zone(issue_key: str) -> str:
    p = issue_key.split("-")[0]
    if p == "cn":
        return "cn"
    return "foreign" if p in FOREIGN_PREFIX else "neutral"


def sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def knife_dest(asset_types) -> str:
    return "workbench_ref" if "tool_capability" in asset_types else "manuals"


def main() -> int:
    # ---- 载账（held/retirements/复核账先行，报数前必查） ----
    readable_dir = W1 / "readable"
    readable_files = sorted(f for f in os_list(readable_dir) if f.endswith(".md"))
    all_records = [json.loads(l) for l in open(W1 / "workbench" / "all_records.jsonl", encoding="utf-8")]
    held = [json.loads(l) for l in open(W1 / "workbench" / "held_records.jsonl", encoding="utf-8")]
    retired_ids = set(json.load(open(W1 / "workbench" / "retirements.json", encoding="utf-8")).keys())
    export_files = json.load(open(W1 / "EXPORT_FILES.json", encoding="utf-8"))["files"]
    issue_reviews = json.load(open(W1 / "workbench" / "issue_reviews.json", encoding="utf-8"))

    by_issue = defaultdict(list)
    for r in all_records:
        by_issue[r["record"]["issue_key"]].append(r)
    held_by_id = {r["record_id"]: r for r in held}

    def hr(r):
        return set(r.get("hold_reasons") or [])

    def ssr(r):
        v = r.get("source_support_review")
        return v.get("status") if isinstance(v, dict) else v

    # ---- L1 直接进层：readable 中国侧 ----
    L1 = []
    for fn in readable_files:
        ik = fn[:-3]
        z = zone(ik)
        if z not in ("cn", "neutral"):
            continue
        rel = "readable/" + fn
        p = readable_dir / fn
        digest = sha256_file(p)
        L1.append({
            "issue_key": ik,
            "title": by_issue[ik][0]["record"].get("title", ""),
            "zone": z,
            "asset_types": sorted({r["record"].get("asset_type") for r in by_issue[ik]}),
            "rel_path": rel,
            "sha256": digest,
            "bytes": p.stat().st_size,
            "knife_dest": knife_dest(sorted({r["record"].get("asset_type") for r in by_issue[ik]})),
        })
    # 死件核查：L1 内 issue 全记录皆退役者必须为 0（死件不进，决策台账 :54）
    l1_all_retired = [it["issue_key"] for it in L1
                      if by_issue[it["issue_key"]] and all(r["record_id"] in retired_ids for r in by_issue[it["issue_key"]])]
    assert not l1_all_retired, f"L1 含全退役 issue：{l1_all_retired[:5]}"
    # 双侧清单交叉核：脚本实算 sha 与归档区 EXPORT_FILES.json 表对照
    l1_sha_crosscheck_bad = [it["rel_path"] for it in L1
                             if export_files.get(it["rel_path"]) != it["sha256"]]

    # ---- L2 复核层：551 名单驱动 ----
    roster = []  # (行号, 状态, 标题)
    for line in open(ROSTER, encoding="utf-8"):
        m = re.match(r"^\s*(\d+)\. \[(\w+)\] (.+?)\s*$", line)
        if m:
            roster.append((int(m.group(1)), m.group(2), m.group(3)))
    assert len(roster) == 551, f"名单解析 {len(roster)} 行 ≠ 551"
    roster_status = Counter(s for _, s, _ in roster)
    assert roster_status == {"NOT_REVIEWED": 506, "NEEDS_REVISION": 9, "STALE_REVIEW": 36}, roster_status

    ssr_recs = [r for r in held if "SOURCE_SUPPORT_REVIEW_PENDING_OR_REVISION" in hr(r)]
    title2ssr = defaultdict(list)
    for r in ssr_recs:
        title2ssr[r["record"]["title"]].append(r)
    L2_map = {}
    roster_nos = defaultdict(list)
    for no, st, t in roster:
        for r in title2ssr.get(t, []):
            L2_map[r["record_id"]] = r
            roster_nos[r["record_id"]].append(no)
    retired_reason = json.load(open(W1 / "workbench" / "retirements.json", encoding="utf-8"))
    L2 = []
    for rid, r in sorted(L2_map.items(), key=lambda kv: min(roster_nos[kv[0]])):
        rec = r["record"]
        assert rid in held_by_id  # 名单权威：含退役标记件（退役账重叠单列字段，见 overview）
        at = [rec.get("asset_type")] if rec.get("asset_type") else []
        L2.append({
            "record_id": rid,
            "issue_key": rec["issue_key"],
            "title": rec["title"],
            "zone": zone(rec["issue_key"]),
            "roster_no": roster_nos[rid],
            "review_status": ssr(r),
            "hold_reasons": sorted(hr(r)),
            "record_hash": r.get("record_hash"),
            "in_retirements": rid in retired_ids,
            "retirement_reason": retired_reason.get(rid, {}).get("reason") if rid in retired_ids else None,
            "readable_export_exists": (rec["issue_key"] + ".md") in set(readable_files),
            "knife_dest": knife_dest(at),
        })
    assert len(L2) == 551, f"L2 {len(L2)} ≠ 551"
    # 记录级复核状态分布必须与名单行分布一致（506/9/36）
    assert Counter(it["review_status"] for it in L2) == roster_status, Counter(it["review_status"] for it in L2)
    # 红线：复核未放行件禁入直接进层——L2 记录必须是 held（无 readable 正文导出通道），且与 L1 条目级零混
    assert all(it["record_id"] in held_by_id for it in L2)
    l2_retired_n = sum(1 for it in L2 if it["in_retirements"])

    # ---- L3 储备层：reserve 池中国侧活件 ----
    L2_ids = {it["record_id"] for it in L2}
    L3 = []
    for r in held:
        if "RESERVE_BY_DESIGN" not in hr(r):
            continue
        if zone(r["record"]["issue_key"]) not in ("cn", "neutral"):
            continue
        if hr(r) & {"RETIRED", "JURISDICTION_ADAPTATION_REQUIRED"}:
            continue  # 死件/境外池出局（决策台账 :54）
        if r["record_id"] in retired_ids or r["record_id"] in L2_ids:
            continue  # 退役账/复核名单已归层
        rec = r["record"]
        at = [rec.get("asset_type")] if rec.get("asset_type") else []
        L3.append({
            "record_id": r["record_id"],
            "issue_key": rec["issue_key"],
            "title": rec["title"],
            "zone": zone(rec["issue_key"]),
            "asset_type": rec.get("asset_type"),
            "hold_reasons": sorted(hr(r)),
            "record_hash": r.get("record_hash"),
            "readable_export_exists": (rec["issue_key"] + ".md") in set(readable_files),
            "knife_dest": knife_dest(at),
        })
    L3.sort(key=lambda x: x["record_id"])
    assert not ({it["record_id"] for it in L3} & L2_ids)
    assert not ({it["record_id"] for it in L3} & retired_ids)

    # ---- 落盘 manifest ----
    OUT.mkdir(parents=True, exist_ok=True)
    counts = {
        "L1_直接进层": len(L1),
        "L2_复核层": len(L2),
        "L3_储备层": len(L3),
        "合计": len(L1) + len(L2) + len(L3),
    }

    def layer_header(layer, rule, items):
        return {
            "library": "库被喂（长尾融入索引库）",
            "layer": layer,
            "generated": GEN_DATE,
            "source_root": SOURCE_ROOT,
            "rule": rule,
            "item_count": len(items),
            "plaza_listing": 0,
            "plaza_note": "长尾不上广场（决策台账 2026-10-29 广场否决+融合机制定调行）；喂料三通道=K5 推送/manual.search/办案包方法组钉哈希",
            "knife_note": "甄别四刀：带码直吸件（pe-vc Apache-2.0/contract-review-3 MIT-0，决策台账带码件三验行）在 sources 包级处置不在本库；本库全件为蒸馏记录（纯文）→manuals=手册线，workbench_ref=工作台参照（tool_capability 类）",
        }

    manifests = {
        "L1-直接进层.json": (layer_header("L1 直接进层",
            "readable/*.md ∧ 前缀∈{cn-,中性}（外域前缀集 us/eu/fr/uk/au/de/jp/gdpr/icelandic 出局，决策台账 :54 口径）；"
            "断言=零全退役 issue（死件不进）、sha256 与归档区 EXPORT_FILES.json 双侧对照", L1), L1),
        "L2-复核层.json": (layer_header("L2 复核层",
            "held-551-纯复核名单.md（551 行，状态 506 NOT_REVIEWED/9 NEEDS_REVISION/36 STALE_REVIEW）按标题精确匹配 "
            "SOURCE_SUPPORT_REVIEW_PENDING_OR_REVISION 的 held 记录；名单权威含退役标记件（退役账重叠见 "
            "in_retirements 字段与 00-库总览）；复核未放行，禁入直接进层；放行须经复核后转层", L2), L2),
        "L3-储备层.json": (layer_header("L3 储备层",
            "reserve 池（hold_reasons 含 RESERVE_BY_DESIGN）∧ 前缀∈{cn-,中性} ∧ 剔 RETIRED（退役账 903）∧ 剔 "
            "JURISDICTION_ADAPTATION_REQUIRED（境外池）∧ 剔已在 L2 名单——按需取（模板/规则候选/计算候选/测试用例等）", L3), L3),
    }
    for name, (header, items) in manifests.items():
        header["items"] = items
        header["counts_snapshot"] = counts
        with open(OUT / name, "w", encoding="utf-8", newline="\n") as f:
            json.dump(header, f, ensure_ascii=False, indent=1)
            f.write("\n")

    # 口径差登记（诚实账）：账面 218 vs 脚本实测
    overview = {
        "library": "库被喂（长尾融入索引库）",
        "generated": GEN_DATE,
        "source_root": SOURCE_ROOT,
        "roster_source": str(ROSTER).replace("\\", "/"),
        "counts": counts,
        "ledger_account": {"直接进": 1917, "复核放行": 551, "储备": 218, "合计≈": 2686},
        "discrepancies": [
            "L3 储备层：账面 218（决策台账 :54，≈2686 为上限口径，无名单落盘）vs 本脚本规则导出 "
            f"{len(L3)}——差 {218 - len(L3)} 件口径未调和=UNKNOWN，以脚本输出为准报数、差因留账",
            f"L2∩退役账重叠：{l2_retired_n}/551 名单件带退役标记（多数=REPLACED_BY_EXPLICIT_REVISION 被显式修订替换）——"
            "名单权威保留在复核层，复核时须对后继版本裁定，未放行前不外溢",
            f"L1∩L2 issue 级重叠：{len({i['issue_key'] for i in L2} & {i['issue_key'] for i in L1})} 个 issue 既有已放行 readable 成品（L1 条目）又有待复核 held 变体（L2 条目）——条目级两层零混，issue 级重叠如实登记",
            "6672→2686 修正：6672=readable 2706+held 3063+退役 903 的未剔重总口径（本脚本是推导，账面原文为『修正：初估 3400 系未剔成品层外域件』，决策台账 :54）",
        ],
        "l2_retirements_overlap": l2_retired_n,
        "exclusions_mechanical": {
            "readable_外域前缀件": sum(1 for f in readable_files if zone(f[:-3]) == "foreign"),
            "held_境外池_JURISDICTION": sum(1 for r in held if "JURISDICTION_ADAPTATION_REQUIRED" in hr(r)),
            "退役账": len(retired_ids),
        },
        "l1_sha_crosscheck_with_EXPORT_FILES": {"mismatch": len(l1_sha_crosscheck_bad), "bad": l1_sha_crosscheck_bad[:5]},
        "l2_status_split": dict(Counter(it["review_status"] for it in L2)),
        "l1_zone_split": dict(Counter(it["zone"] for it in L1)),
        "l2_zone_split": dict(Counter(it["zone"] for it in L2)),
        "l3_zone_split": dict(Counter(it["zone"] for it in L3)),
        "knife_dest_split": {k: dict(Counter(it["knife_dest"] for it in v)) for k, v in
                             {"L1": L1, "L2": L2, "L3": L3}.items()},
    }
    with open(OUT / "00-库总览.json", "w", encoding="utf-8", newline="\n") as f:
        json.dump(overview, f, ensure_ascii=False, indent=1)
        f.write("\n")

    # ---- 抽样 20 件路径实核（8 L1 + 6 L2 + 6 L3，等距确定性取样） ----
    def pick(items, n):
        return [items[round(i * (len(items) - 1) / (n - 1))] for i in range(n)]

    sample = [("L1", it) for it in pick(L1, 8)] + [("L2", it) for it in pick(L2, 6)] + [("L3", it) for it in pick(L3, 6)]
    print("== 抽样 20 件路径实核 ==")
    fails = 0
    for layer, it in sample:
        if layer == "L1":
            p = W1 / it["rel_path"]
            ok = p.is_file() and sha256_file(p) == it["sha256"] and export_files.get(it["rel_path"]) == it["sha256"]
            detail = it["rel_path"]
        else:
            src = held_by_id.get(it["record_id"])
            ok = src is not None and src.get("record_hash") == it["record_hash"]
            if layer == "L3":
                ok = ok and it["record_id"] not in retired_ids
            detail = f"workbench/held_records.jsonl#{it['record_id']}"
        print(f"[{'PASS' if ok else 'FAIL'}] {layer} {detail}")
        fails += 0 if ok else 1

    print("== 计数（脚本输出） ==")
    for k, v in counts.items():
        print(f"{k}: {v}")
    print(f"账面对照: 1917+551+218≈2686（决策台账 :54）；实测差=L3 {218 - len(L3)} 件（UNKNOWN 口径差，见 00-库总览.json）")
    print(f"L1 sha 双侧对照 EXPORT_FILES.json: mismatch={len(l1_sha_crosscheck_bad)}")
    print(f"抽样实核: {20 - fails}/20 PASS")
    return 0 if fails == 0 and not l1_sha_crosscheck_bad else 1


def os_list(d: Path):
    import os
    return os.listdir(d)


if __name__ == "__main__":
    sys.exit(main())

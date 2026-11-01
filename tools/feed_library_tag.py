# -*- coding: utf-8 -*-
"""库被喂五维旁挂打标脚本（施工波二轮-20261030 · 单元=五维打标）。

对 docs/库被喂/manifests/ 三层 2627 件做确定性脚本批标，产物=旁挂 tags 文件
（docs/库被喂/tags/<层>.tags.json）——manifest 字节不动（哈希稳定，用户
2026-10-30 裁决），只打标不路由生效（喂料三通道与 K5 一律不消费本件）。

五维=FILTER_DIMS 冻结键序（legal-cn-manuals-repo/src/legal_cn_manuals/contracts.py:74），
逐条 classification 五键全出现、值均 string[]（ingest-contract-draft.md §8 :93 未知枚举拒绝）：
  methodTypes      = 条目 kind 直取：L1 manifest.asset_types / L3 manifest.asset_type /
                     L2 归档 workbench/all_records.jsonl record.asset_type（record_hash 双侧核对）
                     词表=contracts.py:43 CONTENT_KINDS 17 值，越值即退出非零。
  causeIds         = 题名规则表确定性映射，只允许 harness 现存三现值
                     （benchmark-scenarios SC-SALE-001/SC-LEND-001/SC-CONS-001 package.json:5）；
                     词表无值不映射不硬造（ingest-contract-draft.md §8 causeIds 行）；
                     外围税务件不硬塞案由目录（同 :§8）。
  procedureStages  = 全空——词表未冻结（W08/W10 对齐未落，ingest §8；决策台账 :53）。
  roles            = 全空——本库条目无角色面，roles 只由技能线/办案包场景打
                     （五维打标方案 §四；harness experience.py:30-36 五角色非本库打）。
  topics           = 全空——0b 受控标签表未冻结，自由文本禁直灌 classification。

确定性：固定种子、稳定排序、无时间戳（仅日期）、重跑字节一致；断言失败即退出非零。
只读归档区与 manifest，只写 docs/库被喂/tags/，不碰 manifest、不动 manuals 代码。

用法：
  python tools/feed_library_tag.py --dry-run   # 只打印 causeIds 规则命中与计数，不写文件
  python tools/feed_library_tag.py             # 落盘三个旁挂 tags 文件 + stdout 汇总
  python tools/feed_library_tag.py --sample    # 追加打印 30 件分层抽样单（种子 20261030）
"""
import argparse
import json
import random
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANIFESTS = ROOT / "docs" / "库被喂" / "manifests"
TAGS_OUT = ROOT / "docs" / "库被喂" / "tags"
ARCHIVE = Path(
    r"D:/Codex/1.法律工作区/legal-cn-distillation工作区/"
    r"legal-cn-distill-skills/4.归档区/20260925/route3-2049-skills-final-v1"
)

TODAY = "2026-10-31"
SAMPLE_SEED = 20261030

# —— methodTypes 词表：contracts.py:43 CONTENT_KINDS（17 值，只读引用，不 import 内部实现）——
CONTENT_KINDS = {
    "method", "source_note", "knowledge_note", "reference", "workflow",
    "template", "expression_example", "rule_candidate", "calculation_candidate",
    "strategy_candidate", "forecast_material", "tool_capability",
    "prompt_pattern", "engineering_pattern", "test_case", "persona",
    "personal_practice",
}

# —— causeIds 词表：harness benchmark 现存三现值（SC-*-001 package.json:5）——
CAUSE_LEND = "civil_commercial_contract_lending"
CAUSE_SALE = "civil_commercial_contract_sale"
CAUSE_CONS = "construction_project_subcontract"
CAUSE_VOCAB = {CAUSE_LEND, CAUSE_SALE, CAUSE_CONS}

FILTER_DIMS = ("causeIds", "procedureStages", "roles", "topics", "methodTypes")

# —— causeIds 题名规则表（确定性；每条命中都在 stdout 逐条列出供人核）——
# 规则只认题名主语对准案由域的条目；案由仅作列举出现的合集不映射（宁缺勿错）。
CAUSE_RULES = [
    ("R-LEND-01", lambda t: "民间借贷" in t, {CAUSE_LEND}),
    ("R-SALE-01", lambda t: t.startswith("买卖合同") or "买卖合同纠纷" in t, {CAUSE_SALE}),
    ("R-CONS-01", lambda t: "建设工程" in t, {CAUSE_CONS}),
    ("R-CONS-02", lambda t: re.search(r"(?<!构)建工", t) is not None, {CAUSE_CONS}),  # 负向断言防「构建工具」误命中
    ("R-CONS-03", lambda t: ("施工合同" in t) or ("施工/EPC" in t), {CAUSE_CONS}),
    ("R-CONS-04", lambda t: re.search(r"工程价款|工程造价|工程量清单|违法分包|转包|优先受偿权", t) is not None, {CAUSE_CONS}),
    ("R-CONS-05", lambda t: "施工主体" in t, {CAUSE_CONS}),
]

# 题名枚举多案由的对照/案例库件：只打题名实列且词表有的值（部分覆盖，如实登记）
CAUSE_ENUM_ITEMS = {
    "cn-cause-of-action-elements": {CAUSE_LEND, CAUSE_SALE},   # 题名列民间借贷/买卖合同（劳动/侵权无词表值，不硬造）
    "cn-litigation-training-cases": {CAUSE_LEND},              # 题名列民间借贷（劳动/刑事无词表值，不硬造）
}

# 排除表：题名命中规则但条目主语不是该案由域的，逐条具名排除
CAUSE_EXCLUDES = {
    # 主语=外围税务测算/合规（ingest §8：外围税务按全类型去向，不硬塞案由目录）
    "cn-construction-prepay-calc": "外围税务件，不硬塞案由目录",
    "cn-construction-tax-compliance": "外围税务件，不硬塞案由目录",
    # 主语=工具/样板/合集，案由仅为列举或素材面
    "cn-contract-drafting": "十二类合同红线合集，案由仅列举",
    "cn-civil-agreement-template": "六类范本合集，案由仅列举",
    "cn-solo-company-doc-templates": "文书模板合集，案由仅列举",
    "cn-contract-risk-review": "多类合同红线合集，案由仅列举",
    "cn-rights-enforcement-path": "维权路径速查，案由仅列举",
    "cn-wealth-transfer-tax-calc": "传承税务测算，案由仅列举",
    "cn-civil-procedure-anchors": "程序锚点集，借贷仅为列举点",
    "cn-personal-rights-strategy": "维权策略合集，借贷仅为列举点",
    "regulatory-contract-drafting-qc": "监管性借贷合同=金融监管域，非民间借贷现值",
    "cn-loan-need-clarification": "泛借贷需求整理，不落民间借贷现值",
    "cn-contract-review": "合同审查量化基准，案由仅列举",
    "cn-bid-document-generation": "标书生成工具，分包仅为功能列举",
    "legal-diagram-visualization": "图表样板五类，建工仅为素材面",
    "cn-execution-interest-calculation": "迟延履行利息=执行域通用，不落民间借贷现值",
    "cn-interest-calculation": "利息口径通用件，不落民间借贷现值",
    "cn-interest-loss-calculation": "利息损失通用件，不落民间借贷现值",
}


def fail(msg):
    print("TAG_FAIL: " + msg, file=sys.stderr)
    sys.exit(1)


def load_archive_asset_types():
    """record_id -> asset_type（归档区 all_records.jsonl；只读）。"""
    out = {}
    with open(ARCHIVE / "workbench" / "all_records.jsonl", encoding="utf-8") as f:
        for line in f:
            d = json.loads(line)
            out[d["record_id"]] = (d["record"].get("asset_type"), d.get("record_hash"))
    return out


def classify_cause(issue_key, title):
    """返回 (values, basis) 或 (None, None)。排除表命中→(None, 排除理由)。"""
    if issue_key in CAUSE_EXCLUDES:
        return None, "EXCLUDE「%s」" % CAUSE_EXCLUDES[issue_key]
    values = set()
    rules_hit = []
    for rid, pred, vals in CAUSE_RULES:
        if pred(title):
            values |= vals
            rules_hit.append(rid)
    if issue_key in CAUSE_ENUM_ITEMS:
        values |= CAUSE_ENUM_ITEMS[issue_key]
        rules_hit.append("R-ENUM")
    if not values:
        return None, None
    assert values <= CAUSE_VOCAB, "causeIds 越词表: %s" % values
    return sorted(values), "+".join(rules_hit)


def build_layer(layer_file, archive_map):
    with open(MANIFESTS / layer_file, encoding="utf-8") as f:
        manifest = json.load(f)
    items = manifest["items"]
    tag_items = []
    cause_hits = []
    for it in items:
        ik, title = it["issue_key"], it["title"]
        # methodTypes：三层来源不同，锚一致
        if layer_file.startswith("L1"):
            kinds = it["asset_types"]
            mt_basis = "manifest.items[].asset_types"
            anchor = {"rel_path": it["rel_path"], "sha256": it["sha256"]}
        elif layer_file.startswith("L2"):
            if it["record_id"] not in archive_map:
                fail("L2 record_id 不在归档 all_records: %s" % it["record_id"])
            kind, rec_hash = archive_map[it["record_id"]]
            if rec_hash != it["record_hash"]:
                fail("L2 record_hash 双侧不一致: %s" % it["record_id"])
            kinds = [kind]
            mt_basis = "归档 workbench/all_records.jsonl record.asset_type（record_hash 双侧核对一致）"
            anchor = {"record_id": it["record_id"], "record_hash": it["record_hash"]}
        else:
            kind = it["asset_type"]
            if it["record_id"] in archive_map:
                a_kind, rec_hash = archive_map[it["record_id"]]
                if rec_hash != it["record_hash"]:
                    fail("L3 record_hash 双侧不一致: %s" % it["record_id"])
                if a_kind != kind:
                    fail("L3 asset_type 与归档不一致: %s" % it["record_id"])
            kinds = [kind]
            mt_basis = "manifest.items[].asset_type（与归档 record.asset_type 双侧核对一致）"
            anchor = {"record_id": it["record_id"], "record_hash": it["record_hash"]}
        unknown = [k for k in kinds if k not in CONTENT_KINDS]
        if unknown:
            fail("methodTypes 越词表（未知枚举拒绝）: %s %s" % (ik, unknown))
        cause_vals, cause_basis = classify_cause(ik, title)
        if cause_vals:
            cause_hits.append({"layer": layer_file[:2], "issue_key": ik, "title": title,
                               "values": cause_vals, "basis": cause_basis})
        classification = {
            "causeIds": cause_vals if cause_vals else [],
            "procedureStages": [],
            "roles": [],
            "topics": [],
            "methodTypes": sorted(kinds),
        }
        assert tuple(classification.keys()) == FILTER_DIMS
        tag_items.append({
            "issue_key": ik,
            "anchor": anchor,
            "classification": classification,
            "basis": {"methodTypes": mt_basis,
                      "causeIds": cause_basis if cause_vals else None},
        })
    return manifest, tag_items, cause_hits


def sidecar_doc(sidecar_of, item_count, extra_note=None):
    doc = {
        "library": "库被喂（长尾融入索引库）",
        "sidecar_of": sidecar_of,
        "generated": TODAY,
        "generator": "tools/feed_library_tag.py",
        "mode": "TAG_ONLY_NOT_ROUTED：旁挂打标件，manifest 字节不动；打标≠业务生效，"
                "喂料三通道（K5 推送/manual.search/办案包方法组）与复核放行裁定均不消费本件",
        "vocab": {
            "methodTypes": "legal-cn-manuals-repo/src/legal_cn_manuals/contracts.py:43 "
                           "CONTENT_KINDS 17 值（只读引用；未知枚举=拒绝）",
            "causeIds": "legal-harness-repo/tests/fixtures/benchmark-scenarios/"
                        "SC-SALE-001|SC-LEND-001|SC-CONS-001 各 package.json:5 三现值；"
                        "词表无值不映射不硬造、外围税务不硬塞案由目录"
                        "（legal-cn-manuals-repo/reports/ingest-contract-draft.md §8）",
            "procedureStages": "全空：词表未冻结（W08/W10 对齐未落，ingest §8）——不预打，预打必返工",
            "roles": "全空：本库条目无角色面，roles 只由技能线/办案包场景打（五维打标方案 §四）",
            "topics": "全空：0b 受控标签表未冻结，自由文本禁直灌 classification（ingest §8）",
        },
        "consume_semantics": "缺标签=该维筛选激活时不命中≠不限（ingest-contract-draft.md §8）；"
                             "空数组为 fail-closed 安全方向",
        "item_count": item_count,
        "items": None,
    }
    if extra_note:
        doc["note"] = extra_note
    return doc


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="只打印规则命中与计数，不写文件")
    ap.add_argument("--sample", action="store_true", help="追加打印 30 件分层抽样单")
    args = ap.parse_args()

    archive_map = load_archive_asset_types()
    layers = ["L1-直接进层.json", "L2-复核层.json", "L3-储备层.json"]
    built = {}
    all_cause_hits = []
    for lf in layers:
        manifest, tag_items, cause_hits = build_layer(lf, archive_map)
        if len(tag_items) != manifest["item_count"] or len(tag_items) != len(manifest["items"]):
            fail("%s 覆盖数不符：tags=%d manifest=%d" % (lf, len(tag_items), manifest["item_count"]))
        built[lf] = (manifest, tag_items)
        all_cause_hits.extend(cause_hits)

    print("== causeIds 规则命中（逐条人核清单，%d 条）==" % len(all_cause_hits))
    for h in sorted(all_cause_hits, key=lambda x: (x["layer"], x["issue_key"])):
        print("  [%s] %s | %s | %s | %s" % (h["layer"], h["issue_key"], h["values"], h["basis"], h["title"][:52]))

    print("== 覆盖计数 ==")
    total = 0
    for lf in layers:
        _, tag_items = built[lf]
        n_cause = sum(1 for t in tag_items if t["classification"]["causeIds"])
        n_mt = sum(1 for t in tag_items if t["classification"]["methodTypes"])
        total += len(tag_items)
        print("  %s items=%d methodTypes非空=%d causeIds非空=%d" % (lf, len(tag_items), n_mt, n_cause))
    print("  合计=%d（要求 2627）" % total)
    if total != 2627:
        fail("全覆盖断言失败：total=%d != 2627" % total)

    if args.sample:
        print("== 抽样单（种子 %d，L1 15 / L2 8 / L3 7 + causeIds 命中件全核）==" % SAMPLE_SEED)
        rng = random.Random(SAMPLE_SEED)
        for lf, n in [("L1-直接进层.json", 15), ("L2-复核层.json", 8), ("L3-储备层.json", 7)]:
            _, tag_items = built[lf]
            picks = sorted(rng.sample(range(len(tag_items)), n))
            manifest_items = json.load(open(MANIFESTS / lf, encoding="utf-8"))["items"]
            for i in picks:
                it = manifest_items[i]
                src = it.get("rel_path") or it.get("record_id")
                print("  SAMPLE[%s] #%d %s | %s" % (lf[:2], i, src, it["title"][:52]))
        for h in sorted(all_cause_hits, key=lambda x: (x["layer"], x["issue_key"])):
            print("  SAMPLE[cause核] [%s] %s | %s" % (h["layer"], h["issue_key"], h["title"][:52]))

    if args.dry_run:
        print("DRY_RUN：未写任何文件")
        return

    TAGS_OUT.mkdir(parents=True, exist_ok=True)
    for lf in layers:
        manifest, tag_items = built[lf]
        doc = sidecar_doc(sidecar_of=lf, item_count=len(tag_items))
        doc["items"] = tag_items
        out = TAGS_OUT / (lf.replace(".json", "") + ".tags.json")
        tmp = out.with_suffix(".tmp")
        with open(tmp, "w", encoding="utf-8", newline="\n") as f:
            json.dump(doc, f, ensure_ascii=False, indent=1, sort_keys=False)
            f.write("\n")
        tmp.replace(out)
        print("WROTE %s (%d 件)" % (out, len(tag_items)))
    print("TAG_PASS：三层旁挂打标完成，manifest 未触碰")


if __name__ == "__main__":
    main()

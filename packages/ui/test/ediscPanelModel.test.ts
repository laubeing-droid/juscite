// 【功能 #42 电子数据取证】取证面板 UI 合同测试（RE-42 §3.3 展示逻辑纯函数面）：
// 五分区页签、A4 三态徽章闭集、B4 行地址三件套、C2 归类看板分组、E3 批注按页分组、
// D2 校验可读差异、F10 律师闸；施工波三轮对拍收尾面=F1 四类排除/F2 形式六要素/
// F4 三性闭集/F6 四类缺口行/G5 任务状态徽章。
// Node 环境零 DOM——面板 React 壳薄胶水，行为锚点在纯函数（同 materialAttachments 先例）。
// 文案断言只钉「档位标签/可读结构」自写词条。
import { describe, expect, it } from "vitest";
import {
  EDISC_ATTR_BADGE, EDISC_ATTR_CONCLUSIONS, EDISC_FACT_EXCLUSIONS, EDISC_FORMAL_ELEMENTS, EDISC_GAP_KINDS,
  EDISC_KIND_LABELS, EDISC_LEVEL_BADGE, EDISC_OCR_BADGE, EDISC_PARSE_BADGE, EDISC_SECTIONS,
  EDISC_TASK_STATUS_BADGE, EDISC_TRIPLE_ATTRIBUTES,
  canExportReviewReport, formatGapEntry, formatRowAddress, groupAnnotationsByPage, groupClassificationsByCategory,
  missingFormalElements, rowRefOf, summarizeTaskProgress, summarizeVerify,
} from "@juscite/legal/kernel/ediscUiModel";

describe("ediscPanelModel 五分区与徽章闭集", () => {
  it("五分区页签=RE-42 §3.3 五页顺序（源列表/行浏览/归类看板/页卡阅读/审查工作台）", () => {
    expect(EDISC_SECTIONS.map((s) => s.key)).toEqual(["sources", "rows", "board", "pages", "review"]);
    expect(EDISC_SECTIONS.every((s) => s.label.length > 0)).toBe(true);
  });

  it("解析徽章覆盖桥 parseStatus 四态闭集（pending/parsing/done/failed）", () => {
    expect(Object.keys(EDISC_PARSE_BADGE).sort()).toEqual(["done", "failed", "parsing", "pending"]);
    expect(EDISC_PARSE_BADGE.done.label).not.toBe(EDISC_PARSE_BADGE.pending.label);
    expect(EDISC_PARSE_BADGE.failed.cls).toContain("red"); // 失败态红色可辨
  });

  it("OCR 徽章覆盖两态；类型标签覆盖四种进场类型（chat/statement/table/generic）", () => {
    expect(Object.keys(EDISC_OCR_BADGE).sort()).toEqual(["not_required", "required"]);
    expect(Object.keys(EDISC_KIND_LABELS).sort()).toEqual(["chat", "generic", "statement", "table"]);
    expect(EDISC_OCR_BADGE.required.label).toContain("OCR");
  });

  it("三档色标互异且含默认档存疑保留（F3：✅/✅+⚠️/❌ 三档）", () => {
    expect(Object.keys(EDISC_LEVEL_BADGE).sort()).toEqual(["doubt", "insufficient", "ok"]);
    const cls = new Set(Object.values(EDISC_LEVEL_BADGE).map((b) => b.cls));
    expect(cls.size).toBe(3);
    expect(EDISC_LEVEL_BADGE.doubt.cls).toContain("amber"); // 默认档琥珀警示
  });
});

describe("ediscPanelModel 行地址与分组", () => {
  it("rowRefOf 产出 B4 三件套引用（kind/sourceId/tableName/行区间），可直接作归类 refs", () => {
    const ref = rowRefOf("esrc_abc", "流水", 7);
    expect(ref).toEqual({ kind: "rows", sourceId: "esrc_abc", tableName: "流水", rowStart: 7, rowEnd: 7 });
  });

  it("formatRowAddress 单行与区间两形态可读（行区间即引用地址）", () => {
    expect(formatRowAddress(rowRefOf("esrc_abc", "流水", 7))).toContain("第 7 行");
    expect(formatRowAddress({ kind: "rows", sourceId: "esrc_abc", tableName: "流水", rowStart: 2, rowEnd: 5 })).toContain("第 2-5 行");
    expect(formatRowAddress(rowRefOf("esrc_abc", "流水", 7))).toContain("esrc_abc"); // 源 id 入地址
  });

  it("归类看板按 category 稳定分组：首现顺序为组序、组内保持返回序", () => {
    const items = [
      { id: "1", category: "收支" }, { id: "2", category: "往来" },
      { id: "3", category: "收支" }, { id: "4", category: "往来" },
    ];
    const groups = groupClassificationsByCategory(items);
    expect(groups.map((g) => g.category)).toEqual(["收支", "往来"]);
    expect(groups[0].items.map((i) => i.id)).toEqual(["1", "3"]);
    expect(groups[1].items.map((i) => i.id)).toEqual(["2", "4"]);
    expect(groupClassificationsByCategory([])).toEqual([]);
  });

  it("批注按页分组：页码升序、同页保序（E3 批注列表按页分组）", () => {
    const annots = [
      { id: "a", pageNumber: 3 }, { id: "b", pageNumber: 1 },
      { id: "c", pageNumber: 3 }, { id: "d", pageNumber: 2 },
    ];
    const groups = groupAnnotationsByPage(annots);
    expect(groups.map((g) => g.page)).toEqual([1, 2, 3]);
    expect(groups.find((g) => g.page === 3)!.items.map((a) => a.id)).toEqual(["a", "c"]);
    expect(groupAnnotationsByPage([])).toEqual([]);
  });
});

describe("ediscPanelModel 校验可读差异（D2：失败不静默）", () => {
  it("通过路径：通过行+回跳统计行，缺漏可核对", () => {
    const lines = summarizeVerify({ ok: true, checked: 6, problems: [], backjumpChecked: 6, backjumpMismatched: 0, candidates: 2 });
    expect(lines).toHaveLength(2);
    expect(lines[0]).toContain("校验通过");
    expect(lines[0]).toContain("2 个清单项");
    expect(lines[1]).toContain("0/6");
  });

  it("未通过路径：问题逐行可读（锚引用+具体问题），不静默吞掉", () => {
    const lines = summarizeVerify({
      ok: false, checked: 3,
      problems: [{ ref: "流水 第 4 行", issue: "锚处行不存在" }, { ref: "聊天记录 第 2 行", issue: "引用回跳不一致" }],
      backjumpChecked: 3, backjumpMismatched: 1, candidates: 1,
    });
    expect(lines[0]).toContain("校验未通过");
    expect(lines[0]).toContain("2 处问题");
    expect(lines).toContain("· 流水 第 4 行：锚处行不存在");
    expect(lines).toContain("· 聊天记录 第 2 行：引用回跳不一致");
    expect(lines.at(-1)).toContain("1/3");
  });
});

describe("ediscPanelModel 律师闸（F10：导出前逐项过目，无豁免通道）", () => {
  it("有审查标注且未确认 → 拒绝导出并给具名理由", () => {
    const r = canExportReviewReport({ flagCount: 3, lawyerConfirmed: false });
    expect(r.ok).toBe(false);
    expect(r.reason).toContain("3 条");
    expect(r.reason).toContain("律师");
  });

  it("律师勾选确认后放行", () => {
    const r = canExportReviewReport({ flagCount: 3, lawyerConfirmed: true });
    expect(r).toEqual({ ok: true, reason: "" });
  });

  it("零标注无须闸（报告可出，闸不拦空面）", () => {
    expect(canExportReviewReport({ flagCount: 0, lawyerConfirmed: false }).ok).toBe(true);
  });
});

describe("ediscPanelModel 对拍收尾面（施工波三轮：F1/F2/F4/F6/G5）", () => {
  it("F1 四类排除闭集=无争议/生效文书确认/法律适用/公知（登记面纪律提示）", () => {
    expect([...EDISC_FACT_EXCLUSIONS]).toHaveLength(4);
    expect(EDISC_FACT_EXCLUSIONS).toContain("各方均无争议的事实");
    expect(EDISC_FACT_EXCLUSIONS).toContain("已由生效裁判文书确认的事实");
    expect(EDISC_FACT_EXCLUSIONS).toContain("纯法律适用问题");
    expect(EDISC_FACT_EXCLUSIONS).toContain("公知事实");
  });

  it("F2 形式六要素闭集六项定序（名称/形成时间/出具方/原件或复印件/证明目的/对应待证事实）", () => {
    expect([...EDISC_FORMAL_ELEMENTS]).toEqual(["名称", "形成时间", "出具方", "原件或复印件", "证明目的", "对应待证事实"]);
  });

  it("F2 缺项计算：空白/纯空格算缺，按六要素原序返回；全给则空数组", () => {
    expect(missingFormalElements({})).toEqual([...EDISC_FORMAL_ELEMENTS]);
    expect(missingFormalElements({ 名称: "  ", 形成时间: "2026-03" })).toEqual(["名称", "出具方", "原件或复印件", "证明目的", "对应待证事实"]);
    const full = Object.fromEntries(EDISC_FORMAL_ELEMENTS.map((k) => [k, `v-${k}`]));
    expect(missingFormalElements(full)).toEqual([]);
  });

  it("F4 三性属性三件+结论三档闭集；结论色标互异（绿/琥珀/红可辨）", () => {
    expect([...EDISC_TRIPLE_ATTRIBUTES]).toEqual(["真实性", "合法性", "关联性"]);
    expect([...EDISC_ATTR_CONCLUSIONS]).toEqual(["符合", "存疑", "不符合"]);
    const cls = new Set(Object.values(EDISC_ATTR_BADGE).map((b) => b.cls));
    expect(cls.size).toBe(3);
    expect(EDISC_ATTR_BADGE.存疑.cls).toContain("amber");
    expect(EDISC_ATTR_BADGE.不符合.cls).toContain("red");
  });

  it("F6 四类缺口闭集定序；行格式带类目方括号+建议+渠道+期限警示", () => {
    expect([...EDISC_GAP_KINDS]).toEqual(["完全缺口", "证明力不足", "证据链断裂", "形式瑕疵"]);
    const line = formatGapEntry({
      kind: "完全缺口", factText: "货款结算方式约定", suggestion: "调取对公账户全程流水",
      sourceChannel: "向银行申请调取", difficulty: "中", deadlineNote: "举证期限届满前 15 日",
    });
    expect(line).toContain("【完全缺口】");
    expect(line).toContain("建议补充：调取对公账户全程流水");
    expect(line).toContain("取得渠道：向银行申请调取");
    expect(line).toContain("期限警示：举证期限届满前 15 日");
    const noDeadline = formatGapEntry({ kind: "形式瑕疵", factText: "", suggestion: "补齐出具方", sourceChannel: "", difficulty: "", deadlineNote: "" });
    expect(noDeadline).toContain("（未指定）");
    expect(noDeadline).toContain("取得渠道：待定");
    expect(noDeadline).not.toContain("期限警示");
  });

  it("G5 任务状态徽章四态互异（运行/暂停/完成/取消）；进度行含检查点与失败计数", () => {
    expect(Object.keys(EDISC_TASK_STATUS_BADGE).sort()).toEqual(["canceled", "done", "paused", "running"]);
    expect(EDISC_TASK_STATUS_BADGE.paused.label).toContain("断点");
    const cls = new Set(Object.values(EDISC_TASK_STATUS_BADGE).map((b) => b.cls));
    expect(cls.size).toBe(4);
    const line = summarizeTaskProgress({ status: "paused", total: 5, done: 2, failed: 1, pending: 2, checkpoint: 3 });
    expect(line).toContain("检查点 3/5");
    expect(line).toContain("成功 2");
    expect(line).toContain("失败 1");
    expect(line).toContain("待处理 2");
  });
});

// 【施工波二轮·可视化B轨 UI 件】面板侧纯函数合同测试（大事记投影/摄入载荷/对抗视图摘要）。
// Node 环境零 DOM：浏览器面只做薄胶水（fetch 文本+RPC 转发+下载），行为锚点在纯函数。
// 判据守卫本体在桥面 @juscite/vizb（真桥接线由 tools/bridge/vizb_panel_synthetic.mts
// 隔离端口自测覆盖），本文件只钉投影裁决与载荷形状。
// 显式 .ts 后缀导入：vitest/vite 直解 TS 源，不依赖 .js→.ts 映射。
import { describe, expect, it } from "vitest";
import {
  buildIntakePayload, projectChronicleFactBase, sanitizeDownloadName,
  type ChronicleEventLike,
} from "../src/panels/chronicleView.ts";
import { parseConfrontationSemantic, summarizeConfrontation } from "../src/panels/confrontationView.ts";

const DOC_TEXT = "2026年3月1日，张三通过银行转账向李四出借人民币二十万元整，双方约定借款期限为六个月。"
  + "2026年9月1日借款到期后，李四未归还任何本金。2026年10月15日，张三向李四发出催款函。合成材料。";
const DOCS = [{ filename: "借款协议.txt", text: DOC_TEXT, truncated: false }];

function ev(p: Partial<ChronicleEventLike> & { eventId: string }): ChronicleEventLike {
  return {
    eventType: "开庭", date: "2026-03-01", note: null,
    sourceRefs: [{ filename: "借款协议.txt", locator: "p1¶1", quote: "张三通过银行转账向李四出借人民币二十万元整" }],
    payload: null,
    ...p,
  };
}

describe("projectChronicleFactBase 投影裁决", () => {
  it("有日期+有引文出处的事件编入，factNo 顺序分配", () => {
    const r = projectChronicleFactBase(
      [ev({ eventId: "e1" }), ev({ eventId: "e2", eventType: "判决", date: "2026-09-01" })],
      DOCS, "合成案",
    );
    expect(r.included).toBe(2);
    expect(r.factBase.facts.map((f) => f.factNo)).toEqual([1, 2]);
    expect(r.factBase.caseTitle).toBe("合成案");
  });

  it("无日期事件不编入且如实计入 excluded（不造日 fail-closed）", () => {
    const r = projectChronicleFactBase([ev({ eventId: "e1", date: null })], DOCS, "合成案");
    expect(r.included).toBe(0);
    expect(r.factBase.facts).toEqual([]);
    expect(r.excluded).toEqual([{ eventId: "e1", eventType: "开庭", reason: expect.stringContaining("无确切日期") }]);
  });

  it("无引文出处事件不编入（笔记是撰述不是照录）", () => {
    const r = projectChronicleFactBase(
      [ev({ eventId: "e1", sourceRefs: [{ filename: "借款协议.txt" }] })], DOCS, "合成案",
    );
    expect(r.included).toBe(0);
    expect(r.excluded[0]!.reason).toContain("引文");
  });

  it("材料文本未取到的事件不编入（引用无法核照录）", () => {
    const r = projectChronicleFactBase(
      [ev({ eventId: "e1", sourceRefs: [{ filename: "缺席材料.txt", quote: "任意" }] })], DOCS, "合成案",
    );
    expect(r.included).toBe(0);
    expect(r.excluded[0]!.reason).toContain("文本未取到");
  });

  it("verb/title/content/locator 原样透传（不本地改写；判定在桥面）", () => {
    const r = projectChronicleFactBase(
      [ev({ eventId: "e1", eventType: "还款期", sourceRefs: [{ filename: "借款协议.txt", locator: "第3页", quote: "借款期限为六个月" }] })],
      DOCS, "合成案",
    );
    const f = r.factBase.facts[0]!;
    expect(f.verb).toBe("还款期"); // 表外动词透传，桥面 C-verb-off-table 拒绝
    expect(f.title).toBe("还款期");
    expect(f.content).toBe("借款期限为六个月");
    expect(f.locator).toBe("第3页"); // 非 p¶ 形态透传，桥面 A-locator 拒绝
    expect(f.datePrecision).toBe("day");
    expect(f.evidenceNo).toBeNull();
    expect(f.dispute).toBeNull();
    expect(f.volume).toBe("卷一");
  });

  it("同源事实按引文在源文首现位置排序（切分可复原保序）", () => {
    const late = ev({ eventId: "late", eventType: "催告", date: "2026-10-15", sourceRefs: [{ filename: "借款协议.txt", quote: "张三向李四发出催款函" }] });
    const early = ev({ eventId: "early", eventType: "出借", date: "2026-03-01", sourceRefs: [{ filename: "借款协议.txt", quote: "2026年3月1日，张三通过银行转账" }] });
    const r = projectChronicleFactBase([late, early], DOCS, "合成案"); // 入序故意晚事件在前
    expect(r.factBase.facts.map((f) => f.content)).toEqual([
      "2026年3月1日，张三通过银行转账",
      "张三向李四发出催款函",
    ]);
  });

  it("evidenceNo 恒 null、uncertainty 起底恒空（机械联动在桥面）", () => {
    const r = projectChronicleFactBase([ev({ eventId: "e1" })], DOCS, "合成案");
    expect(r.factBase.uncertainty).toEqual([]);
    expect(r.factBase.facts.every((f) => f.evidenceNo === null)).toBe(true);
  });

  it("subjects 透传 payload.subjects（非字符串项滤除）", () => {
    const r = projectChronicleFactBase(
      [ev({ eventId: "e1", payload: { subjects: ["张三", 42, "", "李四"] } })], DOCS, "合成案",
    );
    expect(r.factBase.facts[0]!.subjects).toEqual(["张三", "李四"]);
  });

  it("docs 按引文材料去重、单册口径；schema 恒为封闭串", () => {
    const r = projectChronicleFactBase(
      [ev({ eventId: "e1" }), ev({ eventId: "e2", sourceRefs: [{ filename: "借款协议.txt", quote: "借款到期" }] })],
      DOCS, "合成案",
    );
    expect(r.factBase.docs).toHaveLength(1);
    expect(r.factBase.docs[0]).toMatchObject({ docId: "借款协议.txt", volume: "卷一" });
    expect(r.factBase.schema).toBe("juscite.vizb.chronicle.factbase@1");
  });

  it("同输入两跑投影逐字节一致（确定性纪律）", () => {
    const events = [ev({ eventId: "e1" }), ev({ eventId: "e2", date: null })];
    const a = JSON.stringify(projectChronicleFactBase(events, DOCS, "合成案"));
    const b = JSON.stringify(projectChronicleFactBase(events, DOCS, "合成案"));
    expect(a).toBe(b);
  });
});

describe("buildIntakePayload 摄入对账载荷", () => {
  it("整份单页口径：每材料 1 页全文；manifest 不带 pageCount（页数轨不查）", () => {
    const p = buildIntakePayload(DOCS, ["借款协议.txt"], []);
    expect(p.pages).toEqual([{ docId: "借款协议.txt", pageNo: 1, text: DOC_TEXT }]);
    expect(p.manifest).toEqual([{ docId: "借款协议.txt", label: "借款协议.txt", kind: "unknown" }]);
    expect(p.skips).toEqual([]);
  });

  it("忽略∩引用 → skips 带理由留痕；忽略但未被引用不进 skips", () => {
    const p = buildIntakePayload(DOCS, ["借款协议.txt", "调解书.txt"], ["借款协议.txt", "无关材料.txt"]);
    expect(p.skips).toEqual([{ docId: "借款协议.txt", reason: expect.stringContaining("明示不读") }]);
  });
});

describe("对抗视图面板侧纯函数", () => {
  const semantic = JSON.stringify({
    schema: "juscite.vizb.confrontation@1",
    caseTitle: "甲诉乙买卖合同纠纷（合成）",
    internalOnly: true,
    maturity: "L2",
    claims: [{ no: "诉1" }],
    defenses: [{ no: "抗1" }],
    sources: [{ name: "起诉状.txt", text: "…" }],
    toComplete: ["待补一"],
    elements: [
      { no: "要件1", issue: "合同关系成立", burden: "claimant", lawConfidence: "high", evidenceConfidence: "mid", disputed: true, evidenceStandardMet: true },
      { no: "要件2", issue: "货款支付条件成就", burden: "claimant", lawConfidence: "mid", evidenceConfidence: "low", disputed: true, evidenceStandardMet: false },
    ],
  });

  it("合法语义解析+摘要行：三标与争议标记只读展示，不判决定性", () => {
    const p = parseConfrontationSemantic(semantic);
    expect(p.ok).toBe(true);
    const s = summarizeConfrontation(p.value);
    expect(s.ok).toBe(true);
    expect(s.rows).toHaveLength(2);
    expect(s.rows[0]).toMatchObject({ no: "要件1", burden: "claimant", lawConfidence: "high", disputed: true, evidenceStandardMet: true });
    expect(s.claimsCount).toBe(1);
    expect(s.defensesCount).toBe(1);
    expect(s.sourcesCount).toBe(1);
    expect(s.toCompleteCount).toBe(1);
    expect(s.internalOnly).toBe(true);
  });

  it("非 JSON/非对象 → ok=false 带 error 不抛（判定以桥面为准）", () => {
    const bad = parseConfrontationSemantic("{不是 JSON");
    expect(bad.ok).toBe(false);
    expect(bad.error).toContain("JSON 解析失败");
    const arr = parseConfrontationSemantic("[1,2]");
    expect(arr.ok).toBe(false);
    expect(summarizeConfrontation(null).ok).toBe(false);
    expect(summarizeConfrontation({}).rows).toEqual([]);
  });
});

describe("sanitizeDownloadName", () => {
  it("去路径分隔与保留字符，空回退「案件」", () => {
    expect(sanitizeDownloadName('张三诉李四（合成）: *借款?"案')).toBe("张三诉李四（合成） 借款案");
    expect(sanitizeDownloadName("  ")).toBe("案件");
  });
});

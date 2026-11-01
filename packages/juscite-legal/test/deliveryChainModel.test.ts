// 【施工波三轮·#7 证据目录全量面】交付链内核合同测试（RE-7 §4 对拍 22/23/23a 的数据面）。
// D1 路径提取（扩展名字母开头/拒日期假扩展名/拒裸域名）；D3 双层过滤（内部过程文件两路径
// 同裁+草稿脚本启发式：assistant 全 draft 回退、tool 无回退）；D5 版本族去重（后缀折叠/
// 跨扩展名不折叠/用户件恒前）；D4 两层短路（docx 唯一产物免复述轮+"文件在哪"追问复用）。
import { describe, expect, it } from "vitest";
import {
  extractDeliveredPaths, isDeliveryPathToken, isInternalProcessFile, isDraftLikeName,
  filterDeliveries, stripVersionSuffix, deliveryFamilyKey, dedupeVersionFamily,
  completedWordDeliveryMessage, deliveredWordLocationAnswer, requestedArtifactKinds,
  type DeliveryCandidate,
} from "../src/kernel/deliveryChainModel.ts";

describe("deliveryChainModel D1 消息内文件路径提取（对拍 22 前置）", () => {
  it("提取正文中的交付路径（含中文文件名、盘符路径、URL 路径）", () => {
    const text = "目录已生成：证据目录.docx，另一件在 D:\\cases\\证据合集.pdf，线上留档 https://example.com/cases/清单.txt";
    expect(extractDeliveredPaths(text)).toEqual(["证据目录.docx", "D:\\cases\\证据合集.pdf", "https://example.com/cases/清单.txt"]);
  });

  it("拒日期假扩展名（2025.03.07）与版本号（v1.2）——扩展名不以字母开头即出局", () => {
    expect(isDeliveryPathToken("2025.03.07")).toBe(false);
    expect(isDeliveryPathToken("v1.2")).toBe(false);
    expect(isDeliveryPathToken("第2.1条")).toBe(false);
  });

  it("拒裸域名 token（example.com/cdn.site.org 不算文件）；裸文件名按白名单扩展名放行", () => {
    expect(isDeliveryPathToken("example.com")).toBe(false);
    expect(isDeliveryPathToken("cdn.example.site.org")).toBe(false);
    expect(isDeliveryPathToken("证据目录.docx")).toBe(true);
    expect(isDeliveryPathToken("清单.xlsx")).toBe(true);
    expect(isDeliveryPathToken("归档.zip")).toBe(true);
  });
});

describe("deliveryChainModel D3 双层过滤（对拍 22）", () => {
  it("内部过程文件硬过滤：assistant 与工具事件两路径同裁", () => {
    const candidates: DeliveryCandidate[] = [
      { path: "out/batch_cmds.json", source: "assistant" },
      { path: "work/events.jsonl", source: "tool" },
      { path: "tmp/parse_x12.py", source: "tool" },
      { path: "extract_线索/中间.md", source: "assistant" },
      { path: "交付/证据目录.docx", source: "assistant" },
    ];
    const kept = filterDeliveries(candidates);
    expect(kept.map((c) => c.path)).toEqual(["交付/证据目录.docx"]);
    expect(isInternalProcessFile("a/batch_cmds.json")).toBe(true);
    expect(isInternalProcessFile("scratch/anything.md")).toBe(true);
  });

  it("混合交付『证据目录.pdf+merge_evidence.py』→脚本出局仅留 pdf（对拍 22 点名案例）", () => {
    const kept = filterDeliveries([
      { path: "证据目录.pdf", source: "assistant" },
      { path: "merge_evidence.py", source: "assistant" },
    ]);
    expect(kept.map((c) => c.path)).toEqual(["证据目录.pdf"]);
    expect(isDraftLikeName("export_rows.py")).toBe(true);
    expect(isDraftLikeName("代理词草稿.docx")).toBe(true);
  });

  it("assistant 显式路径全 draft-like 时整体保留（用户要的就是脚本/草稿）；工具路径无回退", () => {
    const allDraft = filterDeliveries([
      { path: "build_catalog.py", source: "assistant" },
      { path: "fix_index.py", source: "assistant" },
    ]);
    expect(allDraft).toHaveLength(2); // 全 draft 回退：整体保留
    const toolDraft = filterDeliveries([{ path: "build_catalog.py", source: "tool" }]);
    expect(toolDraft).toHaveLength(0); // 工具路径过滤无回退
  });
});

describe("deliveryChainModel D5 版本族去重（对拍 23a）", () => {
  it("版本后缀族剥除：v2/rev2/final/终稿/定稿/copy/副本/（1）", () => {
    expect(stripVersionSuffix("证据目录v2")).toBe("证据目录");
    expect(stripVersionSuffix("证据目录（v2）")).toBe("证据目录");
    expect(stripVersionSuffix("证据目录 rev2")).toBe("证据目录");
    expect(stripVersionSuffix("证据目录-final")).toBe("证据目录");
    expect(stripVersionSuffix("证据目录终稿")).toBe("证据目录");
    expect(stripVersionSuffix("证据目录定稿")).toBe("证据目录");
    expect(stripVersionSuffix("证据目录-copy")).toBe("证据目录");
    expect(stripVersionSuffix("证据目录副本")).toBe("证据目录");
    expect(stripVersionSuffix("证据目录（1）")).toBe("证据目录");
    expect(stripVersionSuffix("证据目录v2副本")).toBe("证据目录"); // 叠剥
    expect(stripVersionSuffix("无后缀")).toBe("无后缀");
  });

  it("族键=stem::ext：同族折叠后来者顶替；跨扩展名不折叠（docx+pdf=两件并列）", () => {
    expect(deliveryFamilyKey("证据目录.docx")).toBe("证据目录::docx");
    expect(deliveryFamilyKey("证据目录v2.docx")).toBe("证据目录::docx");
    expect(deliveryFamilyKey("证据目录.pdf") === deliveryFamilyKey("证据目录.docx")).toBe(false);
  });

  it("去重：用户件恒在前；agent 同族只留最后一份且落位最新处", () => {
    const out = dedupeVersionFamily([
      { filename: "证据目录.docx", producer: "agent" },
      { filename: "用户上传.docx", producer: "user" },
      { filename: "证据目录v2.docx", producer: "agent" },
      { filename: "证据目录终稿.docx", producer: "agent" },
      { filename: "合集.pdf", producer: "agent" },
    ]);
    expect(out.map((i) => i.filename)).toEqual(["用户上传.docx", "证据目录终稿.docx", "合集.pdf"]);
  });
});

describe("deliveryChainModel D4① docx 唯一产物免复述轮（对拍 23 第一层）", () => {
  const ok = { path: "D:\\out\\证据目录.docx", status: "ok" as const, kind: "docx" as const };

  it("恰好只请求 docx 且有成功交付 → 确定性落点话术（含路径）", () => {
    const msg = completedWordDeliveryMessage({ requestedArtifacts: [{ kind: "docx" }], deliveries: [ok] });
    expect(msg).toContain("Word 文档");
    expect(msg).toContain("D:\\out\\证据目录.docx");
  });

  it("请求多产物/非 docx 请求/无成功交付/只有 inspect 操作 → 不短路", () => {
    expect(completedWordDeliveryMessage({ requestedArtifacts: [{ kind: "docx" }, { kind: "pdf" }], deliveries: [ok] })).toBeNull();
    expect(completedWordDeliveryMessage({ requestedArtifacts: [{ kind: "xlsx" }], deliveries: [ok] })).toBeNull();
    expect(completedWordDeliveryMessage({ requestedArtifacts: [{ kind: "docx" }], deliveries: [{ ...ok, status: "error" }] })).toBeNull();
    expect(completedWordDeliveryMessage({ requestedArtifacts: [{ kind: "docx" }], deliveries: [{ ...ok, kind: "inspect" }] })).toBeNull();
  });

  it("请求档探测闭集四类（docx/xlsx/pdf/pptx）；无格式词为空", () => {
    expect(requestedArtifactKinds("帮我出一份 Word 文档目录")).toEqual(["docx"]);
    expect(requestedArtifactKinds("给我 Excel 清单和 PDF 合集")).toEqual(["xlsx", "pdf"]);
    expect(requestedArtifactKinds("出一份目录")).toEqual([]);
  });
});

describe("deliveryChainModel D4② 文件在哪追问复用（对拍 23 第二层）", () => {
  const history = [
    { path: "旧.pdf", status: "ok" as const, kind: "other" as const },
    { path: "D:\\out\\目录一.docx", status: "ok" as const, kind: "docx" as const },
    { path: "D:\\out\\目录二.docx", status: "ok" as const, kind: "docx" as const },
  ];

  it("≤80 字+位置追问词 → 复用最近一次成功 docx 路径作答", () => {
    const a = deliveredWordLocationAnswer({ message: "生成的文件放在哪了？", history, allowReuse: true });
    expect(a).toContain("D:\\out\\目录二.docx");
  });

  it("授权语（放哪都行/随便）不触发；超 80 字不触发；无位置词不触发", () => {
    expect(deliveredWordLocationAnswer({ message: "放哪都行", history, allowReuse: true })).toBeNull();
    expect(deliveredWordLocationAnswer({ message: "随便放", history, allowReuse: true })).toBeNull();
    expect(deliveredWordLocationAnswer({ message: "文件在哪？" + "补".repeat(80), history, allowReuse: true })).toBeNull();
    expect(deliveredWordLocationAnswer({ message: "帮我继续整理", history, allowReuse: true })).toBeNull();
  });

  it("首轮无交付（allowReuse=false=stepIndex>0 闸）与 pdf-only 历史都不复用（限 docx）", () => {
    expect(deliveredWordLocationAnswer({ message: "文件在哪？", history, allowReuse: false })).toBeNull();
    expect(deliveredWordLocationAnswer({
      message: "文件在哪？",
      history: [{ path: "a.pdf", status: "ok", kind: "other" }],
      allowReuse: true,
    })).toBeNull();
  });
});

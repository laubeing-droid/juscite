// 【功能 #6 材料上传解析】UI 侧纯函数合同测试（RE-6 §4 对拍验收面）：
// 图片压缩尝试序列规划（对拍 6）、粘贴分流（对拍 3/4 含富文本长文本优先裁决）、附件类型判定
// （对拍 36 分类口径）。Node 环境零 DOM——浏览器 canvas 路径只做薄胶水，行为锚点在纯函数。
import { describe, expect, it } from "vitest";
import {
  IMAGE_QUALITY_LADDER,
  IMAGE_SCALE_STEP,
  TEXT_FALLBACK_MAX_EDGE_PX,
  planImageCompressionSteps,
} from "@/lib/materialImageCompress.js";
import {
  MATERIAL_PASTE_TEXT_MIN_CHARS,
  attachmentKindOf,
  collectIngestableEntries,
  isIngestableMaterialName,
  planPasteIngest,
  type FsEntryLike,
} from "@/lib/bridgeMaterialAttachments.js";

describe("materialImageCompress.planImageCompressionSteps", () => {
  it("限内图片不产生压缩尝试（wasCompressed=false 路径）", () => {
    const steps = planImageCompressionSteps({ width: 1920, height: 1080, bytes: 1024 * 1024 });
    expect(steps).toEqual([]);
  });

  it("仅超体量时首轮全尺寸走质量阶梯（对拍 6：0.86→0.32 逐级）", () => {
    const steps = planImageCompressionSteps({ width: 1000, height: 800, bytes: 6 * 1024 * 1024 });
    expect(steps.length).toBeGreaterThanOrEqual(IMAGE_QUALITY_LADDER.length);
    expect(steps.slice(0, IMAGE_QUALITY_LADDER.length).map((s) => s.quality)).toEqual([...IMAGE_QUALITY_LADDER]);
    expect(steps[0].scale).toBe(1);
  });

  it("仅超边长时首轮即降尺寸到上限（4096px 上限）", () => {
    const steps = planImageCompressionSteps({ width: 8192, height: 4096, bytes: 1024 });
    expect(steps[0].scale).toBeCloseTo(4096 / 8192, 10);
    expect(steps.every((s) => s.quality > 0 && s.quality <= 1)).toBe(true);
  });

  it("整轮未收敛则尺寸逐轮 ×0.75", () => {
    const steps = planImageCompressionSteps({ width: 1000, height: 1000, bytes: 6 * 1024 * 1024 });
    const firstOfRound2 = steps[IMAGE_QUALITY_LADDER.length];
    expect(firstOfRound2.scale).toBeCloseTo(1 * IMAGE_SCALE_STEP, 10);
  });

  it("同输入输出恒定（确定性，禁浮点抖动）", () => {
    const a = planImageCompressionSteps({ width: 5000, height: 3000, bytes: 9 * 1024 * 1024 });
    const b = planImageCompressionSteps({ width: 5000, height: 3000, bytes: 9 * 1024 * 1024 });
    expect(a).toEqual(b);
  });

  it("textFallback 上限常量=1280px（对拍 6 副本口径钉死）", () => {
    expect(TEXT_FALLBACK_MAX_EDGE_PX).toBe(1280);
  });
});

describe("bridgeMaterialAttachments.planPasteIngest", () => {
  const imageFile = { name: "photo.png", type: "image/png" };

  it("纯图片粘贴→files（对拍 3：粘贴图片直接上传）", () => {
    const plan = planPasteIngest({ files: [imageFile], text: "" });
    expect(plan).toMatchObject({ kind: "files", droppedFileCount: 0 });
  });

  it("≥200 字纯文本→long-text 转附件（对拍 4 阈值）", () => {
    const plan = planPasteIngest({ files: [], text: "甲".repeat(MATERIAL_PASTE_TEXT_MIN_CHARS) });
    expect(plan.kind).toBe("long-text");
    expect(plan.text.length).toBe(MATERIAL_PASTE_TEXT_MIN_CHARS);
  });

  it("199 字不转附件（阈值下限外的短文本归输入框职责）", () => {
    const plan = planPasteIngest({ files: [], text: "甲".repeat(MATERIAL_PASTE_TEXT_MIN_CHARS - 1) });
    expect(plan.kind).toBe("none");
  });

  it("长正文与内嵌图片并存→长文本优先、图片整批丢弃（对拍 4 富文本裁决）", () => {
    const plan = planPasteIngest({
      files: [imageFile, { name: "shot.jpg", type: "image/jpeg" }],
      text: "长".repeat(300),
    });
    expect(plan).toMatchObject({ kind: "long-text", droppedFileCount: 2 });
  });

  it("短文本+图片并存→按 files 处理（不丢弃文件）", () => {
    const plan = planPasteIngest({ files: [imageFile], text: "短" });
    expect(plan.kind).toBe("files");
  });

  it("空粘贴→none（不产生附件不报错）", () => {
    expect(planPasteIngest({ files: [], text: "" }).kind).toBe("none");
  });
});

describe("bridgeMaterialAttachments.attachmentKindOf", () => {
  it("扩展名+MIME 双口径分类（对拍 36 预览路由与徽章共用）", () => {
    expect(attachmentKindOf("起诉状.docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document")).toBe("docx");
    expect(attachmentKindOf("判决书.pdf", "application/pdf")).toBe("pdf");
    expect(attachmentKindOf("收据.jpg", "image/jpeg")).toBe("image");
    expect(attachmentKindOf("证据.png")).toBe("image");
    expect(attachmentKindOf("会议录音.m4a", "audio/mp4")).toBe("audio");
    expect(attachmentKindOf("庭审录像.mp4", "video/mp4")).toBe("video");
    expect(attachmentKindOf("合同.md", "text/markdown")).toBe("text");
    expect(attachmentKindOf("清单.csv", "")).toBe("text");
    expect(attachmentKindOf("压缩包.zip", "application/zip")).toBe("other");
  });

  it("MIME 带参数与大小写不影响判定", () => {
    expect(attachmentKindOf("a.txt", "text/plain; charset=utf-8")).toBe("text");
    expect(attachmentKindOf("B.PNG", "Image/PNG")).toBe("image");
  });
});

// ── 目录拖拽白名单收集（对拍 30 前半/§3 批量：目录拖拽仅收白名单扩展名）──
function fakeFile(name: string, body = "x"): File {
  return new File([body], name);
}
function fakeFileEntry(name: string, file: File): FsEntryLike {
  return { isFile: true, isDirectory: false, name, file: (ok) => ok(file) };
}
function fakeDirEntry(name: string, children: FsEntryLike[], batchSize = 2): FsEntryLike {
  // readEntries 分批出（每批 batchSize 条），复刻浏览器 readEntries 上限语义
  return {
    isFile: false,
    isDirectory: true,
    name,
    createReader: () => {
      let cursor = 0;
      return {
        readEntries: (ok) => {
          const batch = children.slice(cursor, cursor + batchSize);
          cursor += batch.length;
          ok(batch);
        },
      };
    },
  };
}

describe("bridgeMaterialAttachments 目录拖拽白名单（对拍 30）", () => {
  it("isIngestableMaterialName：白名单内 true、未知扩展名/无扩展名 false", () => {
    for (const name of ["a.pdf", "b.docx", "c.txt", "d.md", "e.png", "f.jpg", "g.jpeg", "h.webp", "i.gif", "j.bmp", "大写.PDF", "无空格 名.docx"]) {
      expect(isIngestableMaterialName(name)).toBe(true);
    }
    for (const name of ["x.xyz", "y.exe", "z.zip", "no-ext", "w.doc", "v.tiff", "u.csv", "m.json", ".hidden"]) {
      expect(isIngestableMaterialName(name)).toBe(false);
    }
  });

  it("目录树展开：递归收集白名单件、未知扩展名跳过、单件读败不中断（对拍 43 同源）", async () => {
    const good = fakeFile("合同要点.txt");
    const tree: FsEntryLike[] = [
      fakeFileEntry("合同要点.txt", good),
      fakeFileEntry("恶意.exe", fakeFile("恶意.exe")),
      {
        isFile: true,
        isDirectory: false,
        name: "读败件.pdf",
        file: (_ok, err) => err?.(new Error("io")),
      },
      fakeDirEntry("证据目录", [
        fakeFileEntry("收据.jpg", fakeFile("收据.jpg")),
        fakeDirEntry("更深", [fakeFileEntry("判决书.pdf", fakeFile("判决书.pdf"))]),
      ]),
      fakeFileEntry("坏件.png", fakeFile("坏件.png")),
    ];
    const files = await collectIngestableEntries(tree);
    expect(files.map((f) => f.name).sort()).toEqual(["判决书.pdf", "合同要点.txt", "坏件.png", "收据.jpg"]);
  });

  it("readEntries 分批读到空批为止（每批上限语义）", async () => {
    const many = Array.from({ length: 5 }, (_, i) => fakeFileEntry(`件${i}.txt`, fakeFile(`件${i}.txt`)));
    const files = await collectIngestableEntries([fakeDirEntry("目录", many, 2)]);
    expect(files).toHaveLength(5);
  });

  it("非目录入口与空树安全收空", async () => {
    expect(await collectIngestableEntries([])).toEqual([]);
    expect(await collectIngestableEntries([fakeFileEntry("x.xyz", fakeFile("x.xyz"))])).toEqual([]);
  });
});

// 【施工波三轮·#7 证据目录全量面】技能触发语义内核合同测试（RE-7 §4 对拍 1~8 与 1a 的内核面）。
// Node 环境零 DOM；分值档位/排序/预算/上限/双语义（回合 startsWith vs 目录检索 includes）/
// 知识库线程短路/注入文本结构逐项钉死。真实技能包字节（implementation/skill-presets 两件）用于
// 双命中与预算实景（同规格 §5"触发语义以 node 同构模拟对拍（真实 SKILL.md 字节）"口径）。
import { describe, expect, it } from "vitest";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import {
  planSkillInjection, searchSkills, loadSkill, buildSkillInstructionText, byteLengthUtf8,
  SKILL_INJECTION_BUDGET_BYTES, MAX_SKILLS_PER_TURN,
  type ActivatableSkill,
} from "../src/kernel/skillActivationModel.ts";

const PRESETS = fileURLToPath(new URL("../../../implementation/skill-presets/", import.meta.url));
const catalogMeta = JSON.parse(readFileSync(PRESETS + "evidence-catalog/skill.json", "utf-8"));
const materialsMeta = JSON.parse(readFileSync(PRESETS + "evidence-materials/skill.json", "utf-8"));
const catalogBody = readFileSync(PRESETS + "evidence-catalog/SKILL.md", "utf-8");
const materialsBody = readFileSync(PRESETS + "evidence-materials/SKILL.md", "utf-8");

// 桥注册形（同 bridge_host BUILTIN_SKILLS 投影）：builtin=native 四通道；aliasIds=preset 原生 id
const evCatalog: ActivatableSkill = {
  id: "juscite-builtin-evidence-catalog", aliasIds: [catalogMeta.id], name: catalogMeta.name, description: catalogMeta.description,
  body: catalogBody, triggers: catalogMeta.triggers, priority: 0, scope: "builtin", rootPath: "implementation/skill-presets/evidence-catalog",
};
const evMaterials: ActivatableSkill = {
  id: "juscite-builtin-evidence-materials", aliasIds: [materialsMeta.id], name: materialsMeta.name, description: materialsMeta.description,
  body: materialsBody, triggers: materialsMeta.triggers, priority: 0, scope: "builtin", rootPath: "implementation/skill-presets/evidence-materials",
};
const REGISTRY = [evCatalog, evMaterials];

const plan = (text: string, skills: ActivatableSkill[] = REGISTRY, opts: { attachmentFilenames?: string[]; threadKind?: "conversation" | "knowledge-qa" } = {}) =>
  planSkillInjection({ skills, text, attachmentFilenames: opts.attachmentFilenames, threadKind: opts.threadKind ?? "conversation" });

describe("skillActivationModel 通道与分值（对拍 1~4）", () => {
  it("pattern 通道：『帮我生成证据目录』双技能命中、各 500 分（对拍 1/A1/A5）", () => {
    const p = plan("帮我生成证据目录");
    expect(p.activations.map((a) => a.skill.id)).toEqual([
      "juscite-builtin-evidence-catalog", // id 字典序排前（同分时）
      "juscite-builtin-evidence-materials",
    ]);
    expect(p.activations.every((a) => a.score === 500)).toBe(true);
  });

  it("非命中消息『帮我起草起诉状』不注入任何证据技能（对拍 1a/A10 反向断言）", () => {
    const p = plan("帮我起草起诉状");
    expect(p.activations.filter((a) => a.skill.id.includes("evidence"))).toHaveLength(0);
  });

  it("command 通道=回合 startsWith：句首 /evidencecat 命中 900 分；句中出现的 /evidencecat 不算命令（对拍 2/A2）", () => {
    const p1 = plan("/evidencecat 帮我做目录");
    expect(p1.activations[0].skill.id).toBe("juscite-builtin-evidence-catalog");
    expect(p1.activations[0].score).toBe(900);
    const p2 = plan("我想问一下 /evidencecat 是干嘛的");
    expect(p2.activations).toHaveLength(0); // 句中不算命令、无触发词/扩展名 → 不激活
  });

  it("explicit 三形态+名称点名 1000 分压过一切（对拍 3/A3）", () => {
    for (const mark of ["$evidence-catalog", "@evidence-catalog", "/skill:evidence-catalog", "$证据目录生成"]) {
      const p = plan(mark + " 出目录");
      expect(p.activations[0].skill.id).toBe("juscite-builtin-evidence-catalog");
      expect(p.activations[0].channels).toContain("explicit");
      expect(p.activations[0].score).toBe(1000);
    }
  });

  it("fileType 通道：附件名与消息内扩展名扫描都命中（对拍 4/A4）", () => {
    const p1 = plan("把材料整理一下", REGISTRY, { attachmentFilenames: ["起诉状.docx"] });
    expect(p1.activations.map((a) => a.skill.id)).toContain("juscite-builtin-evidence-catalog");
    const p2 = plan("把这份 .docx 材料整理成证据清单");
    expect(p2.activations.map((a) => a.skill.id)).toEqual([
      "juscite-builtin-evidence-catalog",
      "juscite-builtin-evidence-materials",
    ]);
    expect(p2.activations[0].channels).toEqual(["pattern", "fileType"]); // 两通道齐列，取高档计分
    expect(p2.activations[0].score).toBe(500);
  });

  it("『整理证据材料并出PDF合集』仅姊妹技能命中（主技能 pattern 不含整理证据——对拍 5/A5 后半）", () => {
    const p = plan("整理证据材料并出PDF合集");
    expect(p.activations.map((a) => a.skill.id)).toEqual(["juscite-builtin-evidence-materials"]);
  });
});

describe("skillActivationModel 预算/上限/排序（对拍 5/A5-A6）", () => {
  const fat: ActivatableSkill = { id: "a-fat", name: "胖技能", body: "巨".repeat(13000), scope: "builtin", triggers: { promptPatterns: ["证据目录"] } };
  const small: ActivatableSkill = { id: "b-small", name: "小技能", body: "短正文", scope: "builtin", triggers: { promptPatterns: ["证据目录"] } };

  it("真实技能包双注入合计在 24000 字节预算内（对拍 5 实景）", () => {
    const p = plan("制作一份证据清单");
    expect(p.activations).toHaveLength(2);
    const total = p.activations.reduce((n, a) => n + a.instructionBytes, 0);
    expect(total).toBeLessThanOrEqual(SKILL_INJECTION_BUDGET_BYTES);
    expect(total).toBeGreaterThan(9000); // 真实正文体量（两包 9605B+包装），非空壳
  });

  it("超预算技能静默跳过（无报错），预算内的小技能仍注入（A6）", () => {
    const p = plan("证据目录", [fat, small]);
    expect(p.activations.map((a) => a.skill.id)).toEqual(["b-small"]);
    expect(p.skippedOverBudget.map((a) => a.skill.id)).toEqual(["a-fat"]);
    expect(p.block).toContain("小技能");
  });

  it("每回合上限 3 个技能（A6）", () => {
    const skills = [1, 2, 3, 4].map((n) => ({
      id: `s${n}`, name: `技能${n}`, body: `正文${n}`, scope: "builtin" as const,
      triggers: { promptPatterns: ["证据目录"] },
    }));
    const p = plan("证据目录", skills);
    expect(p.activations).toHaveLength(MAX_SKILLS_PER_TURN);
    expect(p.activations.map((a) => a.skill.id)).toEqual(["s1", "s2", "s3"]); // 同分 id 字典序取前三
  });

  it("explicit 压过一切：explicit 命中者排最前，即使 id 靠后（A3/A5 排序）", () => {
    const early = { id: "a-early", name: "早", body: "x", scope: "builtin" as const, triggers: { promptPatterns: ["证据"] } };
    const late = { id: "z-late", name: "晚", body: "y", scope: "builtin" as const, triggers: { promptPatterns: ["证据"] } };
    const p = plan("$z-late 证据", [early, late]);
    expect(p.activations[0].skill.id).toBe("z-late");
    expect(p.activations[0].score).toBe(1000);
  });

  it("knowledge-qa 线程整体短路：任何通道都不注入（对拍 8/A9）", () => {
    const p = plan("/evidencecat 证据目录", REGISTRY, { threadKind: "knowledge-qa" });
    expect(p.activations).toHaveLength(0);
    expect(p.block).toBeNull();
  });
});

describe("skillActivationModel supplemental 语义（A6 keyword 通道边界）", () => {
  it("用户根 supplemental 默认不自动注入：pattern/命令/fileType 均不触发，explicit 点名仍可（对拍 7/A6）", () => {
    const user = { id: "user-mytool", name: "我的工具", body: "正文", scope: "user" as const, triggers: { promptPatterns: ["证据目录"], commands: ["/mytool"] } };
    expect(plan("帮我生成证据目录", [user]).activations).toHaveLength(0);
    expect(plan("/mytool 开始", [user]).activations).toHaveLength(0);
    expect(plan("$user-mytool 开始", [user]).activations).toHaveLength(1);
  });

  it("keyword 通道（200 分）仅 supplemental 技能可走；native 技能给 keywords 也不生效", () => {
    const user = { id: "user-k", name: "K", body: "正文", scope: "user" as const, autoInject: true, keywords: ["欠条"] };
    const native = { id: "native-k", name: "N", body: "正文", scope: "builtin" as const, keywords: ["欠条"] };
    expect(plan("看看这张欠条", [user]).activations[0].score).toBe(200);
    expect(plan("看看这张欠条", [native]).activations).toHaveLength(0);
  });
});

describe("skillActivationModel 检索与加载双语义（对拍 6/A7）", () => {
  it("searchSkills：空 query=全列（reason=list）；命令检索=includes（与回合 startsWith 双语义）", () => {
    expect(searchSkills({ skills: REGISTRY, query: "" }).map((h) => h.reason)).toEqual(["list", "list"]);
    const hits = searchSkills({ skills: REGISTRY, query: "怎么用 /evidencecat 这个命令" });
    expect(hits[0].skill.id).toBe("juscite-builtin-evidence-catalog");
    expect(hits[0].reason).toContain("command(includes)"); // 句中包含也算目录命中（回合激活则必须句首）
  });

  it("loadSkill：精确 id 与插件限定 id 末段后缀皆可加载（不受预算限制）；未找到给建议列表不抛错", () => {
    expect(loadSkill({ skills: REGISTRY, id: "juscite-builtin-evidence-catalog" }).status).toBe("ok");
    const bySuffix = loadSkill({ skills: REGISTRY, id: "juscite-builtin.evidence-catalog" });
    expect(bySuffix.status).toBe("ok");
    expect(bySuffix.skill?.id).toBe("juscite-builtin-evidence-catalog");
    const big = loadSkill({ skills: [{ ...evCatalog, body: "巨".repeat(30000) }], id: "juscite-builtin-evidence-catalog" });
    expect(big.status).toBe("ok"); // 加载全文不受注入预算限制
    const nf = loadSkill({ skills: REGISTRY, id: "evidence-nope" });
    expect(nf.status).toBe("not-found");
    expect((nf.suggestions ?? []).join(" ")).toContain("evidence-catalog"); // 建议列表话术数据面
  });
});

describe("skillActivationModel 注入文本结构（RE-7 §3 技能类附加格式）", () => {
  it("注入文本=Active Skill 行+来源+激活原因+根路径+执行合同+描述+正文全文", () => {
    const p = plan("$evidence-catalog 出目录");
    const text = buildSkillInstructionText(p.activations[0]);
    expect(text).toContain("Active Skill: 证据目录生成 (juscite-builtin-evidence-catalog)");
    expect(text).toContain("来源：内置预装（builtin）");
    expect(text).toContain("激活原因：");
    expect(text).toContain("技能根路径：implementation/skill-presets/evidence-catalog");
    expect(text).toContain("执行合同：把技能当操作流程而非阅读材料");
    expect(text).toContain("描述：");
    expect(text).toContain(catalogBody.slice(0, 40)); // 正文全文在内
    expect(p.block).toContain("<active-skills>");
  });

  it("byteLengthUtf8=TextEncoder UTF-8 字节数（中文三字节口径，预算判定用）", () => {
    expect(byteLengthUtf8("证据")).toBe(6);
    expect(byteLengthUtf8("abc")).toBe(3);
  });
});

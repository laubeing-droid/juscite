// 【功能 #7 证据目录生成·全量面】技能触发语义内核（RE-7 §3 技能类附加；对拍 1~8 与 1a）。
// 纯函数、零 IO；Node（桥注入/测试）与浏览器两栖——字节数口径=TextEncoder UTF-8 字节数，
// 与 Buffer.byteLength(text,"utf8") 逐字节等值（RE-7 §1 预算计量口径钉死为 UTF-8 字节非字符）。
// 通道分值（分值档位=竞品 skill-runtime 等量，实现自写）：
//   explicit（$/@//skill: 三形态+名称点名）1000+priority —— 压过一切
//   command（回合 startsWith）900+priority —— 目录检索另走 includes（双语义，见 searchSkills）
//   pattern（RegExp(p,"i")）500+priority
//   fileType（附件路径+消息内扩展名扫描）300+priority
//   keyword 200+priority —— 仅用户根 supplemental 技能；native 技能不走此通道
// 排序=explicit 命中优先 → native 优先 → 分值降序 → id 字典序；每回合上限 3 个；
// 注入预算 24000 字节，超限技能静默跳过（不报错不提示，后续更小者仍可入选）。
// 多通道同时命中取最高档通道计分（保证 explicit 压过一切），命中通道全列进激活原因。

export interface SkillTriggerSpec {
  commands?: string[];
  promptPatterns?: string[];
  fileTypes?: string[];
}

export interface ActivatableSkill {
  id: string;
  /** 显式点名别名（preset 原生 id，如 evidence-catalog——注册 id 带桥前缀时的点名短形）。 */
  aliasIds?: string[];
  name: string;
  description?: string;
  body: string;
  /** 触发清单（skill.json triggers 真源直读）；无 triggers 的技能只剩 explicit 点名通道。 */
  triggers?: SkillTriggerSpec;
  priority?: number;
  /** builtin=native 技能；user=用户根 supplemental（默认不自动注入，仅显式点名）。 */
  scope?: "builtin" | "user";
  /** supplemental 自动注入开关（用户根技能默认 false；native 恒可自动注入）。 */
  autoInject?: boolean;
  /** 技能根路径（注入文本里的来源锚，竞品同位字段等量）。 */
  rootPath?: string;
  /** 仅 supplemental 生效的关键词通道词表。 */
  keywords?: string[];
}

export type ActivationChannel = "explicit" | "command" | "pattern" | "fileType" | "keyword";

export interface SkillActivation {
  skill: ActivatableSkill;
  channels: ActivationChannel[];
  score: number;
  reason: string;
  /** 该技能注入指令的 UTF-8 字节数（预算口径）。 */
  instructionBytes: number;
}

export interface SkillSearchHit {
  skill: ActivatableSkill;
  reason: string;
}

export const SKILL_INJECTION_BUDGET_BYTES = 24_000;
export const MAX_SKILLS_PER_TURN = 3;
export const SKILL_CHANNEL_BASE_SCORE: Record<ActivationChannel, number> = {
  explicit: 1000,
  command: 900,
  pattern: 500,
  fileType: 300,
  keyword: 200,
};

const CHANNEL_ORDER: ActivationChannel[] = ["explicit", "command", "pattern", "fileType", "keyword"];
const CHANNEL_LABEL: Record<ActivationChannel, string> = {
  explicit: "显式点名",
  command: "命令触发",
  pattern: "触发词命中",
  fileType: "文件类型命中",
  keyword: "关键词命中",
};

const encoder = new TextEncoder();
/** UTF-8 字节数（=Buffer.byteLength(text,"utf8")）。 */
export function byteLengthUtf8(text: string): number {
  return encoder.encode(text).length;
}

function explicitForms(skill: ActivatableSkill): string[] {
  const ids = [skill.id, ...(skill.aliasIds ?? [])];
  const forms: string[] = [];
  for (const id of ids) forms.push(`$${id}`, `@${id}`, `/skill:${id}`);
  // 名称点名：中文名/拉丁名皆可（$证据目录生成、@evidence-catalog 同档）
  if (skill.name && skill.name !== skill.id && !ids.includes(skill.name)) forms.push(`$${skill.name}`, `@${skill.name}`);
  return forms;
}

/** 单技能通道匹配；不命中返回 null。supplemental 未开自动注入时只保留 explicit 通道。 */
export function matchSkillChannels(
  skill: ActivatableSkill,
  input: { text: string; attachmentFilenames?: string[] },
): SkillActivation | null {
  const text = String(input.text ?? "");
  const lower = text.toLowerCase();
  const names = (input.attachmentFilenames ?? []).map((n) => String(n).toLowerCase());
  const supplementalAutoBlocked = skill.scope === "user" && skill.autoInject !== true;
  const channels: ActivationChannel[] = [];

  if (explicitForms(skill).some((f) => text.includes(f))) channels.push("explicit");
  if (!supplementalAutoBlocked) {
    const cmds = skill.triggers?.commands ?? [];
    if (cmds.some((c) => text.startsWith(c))) channels.push("command"); // 回合激活=startsWith（非 include）
    const patterns = skill.triggers?.promptPatterns ?? [];
    if (patterns.some((p) => new RegExp(p, "i").test(text))) channels.push("pattern");
    const fts = (skill.triggers?.fileTypes ?? []).map((f) => String(f).toLowerCase());
    if (
      fts.length > 0 &&
      (fts.some((ft) => names.some((n) => n.endsWith(ft))) || fts.some((ft) => lower.includes(ft)))
    ) {
      channels.push("fileType"); // 来源=附件路径+消息内扩展名扫描
    }
    // keyword 通道仅 supplemental（scope=user）技能——native 技能无此通道
    if (skill.scope === "user" && (skill.keywords ?? []).some((k) => lower.includes(String(k).toLowerCase()))) {
      channels.push("keyword");
    }
  }
  if (channels.length === 0) return null;
  const best = CHANNEL_ORDER.find((c) => channels.includes(c)) as ActivationChannel;
  const score = SKILL_CHANNEL_BASE_SCORE[best] + (skill.priority ?? 0);
  const reason = channels.map((c) => `${CHANNEL_LABEL[c]}（${c}，${SKILL_CHANNEL_BASE_SCORE[c]}${skill.priority ? "+" + skill.priority : ""}）`).join("；");
  return { skill, channels, score, reason, instructionBytes: byteLengthUtf8(buildSkillInstructionText({ skill, channels, score, reason })) };
}

export interface SkillInstructionParts {
  skill: ActivatableSkill;
  channels: ActivationChannel[];
  score: number;
  reason: string;
}

/** 单技能注入指令文本（RE-7 §3 注入格式：Active Skill 行+来源+激活原因+根路径+执行合同+描述+正文全文）。 */
export function buildSkillInstructionText(parts: SkillInstructionParts): string {
  const s = parts.skill;
  return [
    `Active Skill: ${s.name} (${s.id})`,
    `来源：${s.scope === "user" ? "用户根技能" : "内置预装（builtin）"}`,
    `激活原因：${parts.reason}`,
    `技能根路径：${s.rootPath ?? ""}`,
    "执行合同：把技能当操作流程而非阅读材料；落地产物化（能生成文件就生成文件）；事实与假设分离；缺输入要标而不编；收尾自检。",
    `描述：${s.description ?? ""}`,
    "正文：",
    s.body,
  ].join("\n");
}

export type SkillThreadKind = "conversation" | "knowledge-qa";

export interface SkillActivationPlan {
  activations: SkillActivation[];
  /** 注入块（全部入选技能拼接）；无激活为 null。 */
  block: string | null;
  /** 预算内放不下的激活（静默跳过面，对账用；竞品为无提示 continue）。 */
  skippedOverBudget: SkillActivation[];
}

/**
 * 回合技能激活：知识库问答线程整体短路（技能解析为空）；排序→上限 3→预算 24000 字节静默跳过。
 */
export function planSkillInjection(input: {
  skills: ActivatableSkill[];
  text: string;
  attachmentFilenames?: string[];
  threadKind?: SkillThreadKind;
}): SkillActivationPlan {
  if (input.threadKind === "knowledge-qa") return { activations: [], block: null, skippedOverBudget: [] };
  const hits: SkillActivation[] = [];
  for (const skill of input.skills) {
    const m = matchSkillChannels(skill, { text: input.text, attachmentFilenames: input.attachmentFilenames });
    if (m) hits.push(m);
  }
  hits.sort((a, b) => {
    const ea = a.channels.includes("explicit") ? 0 : 1;
    const eb = b.channels.includes("explicit") ? 0 : 1;
    if (ea !== eb) return ea - eb; // explicit 压过一切
    const na = a.skill.scope === "user" ? 1 : 0;
    const nb = b.skill.scope === "user" ? 1 : 0;
    if (na !== nb) return na - nb; // native 优先于 supplemental
    if (b.score !== a.score) return b.score - a.score; // 分值降序
    return a.skill.id < b.skill.id ? -1 : a.skill.id > b.skill.id ? 1 : 0; // id 字典序
  });
  const capped = hits.slice(0, MAX_SKILLS_PER_TURN);
  const activations: SkillActivation[] = [];
  const skipped: SkillActivation[] = [];
  let used = 0;
  for (const hit of capped) {
    if (used + hit.instructionBytes > SKILL_INJECTION_BUDGET_BYTES) {
      skipped.push(hit); // 静默跳过：不报错不提示，继续看更小者
      continue;
    }
    used += hit.instructionBytes;
    activations.push(hit);
  }
  if (activations.length === 0) return { activations: [], block: null, skippedOverBudget: skipped };
  const block =
    "<active-skills>\n（以下技能由本轮消息自动激活，作为操作流程合同执行；置于消息尾部，前缀缓存友好。）\n" +
    activations.map((a) => buildSkillInstructionText(a)).join("\n\n") +
    "\n</active-skills>";
  return { activations, block, skippedOverBudget: skipped };
}

/**
 * 目录检索（search_skills 等量）：空 query=全列（理由 list）；非空按 includes 语义分档——
 * 命令检索=includes（与回合激活 startsWith 双语义）；explicit 形态/名称/描述/触发词逐档。
 */
export function searchSkills(input: { skills: ActivatableSkill[]; query?: string }): SkillSearchHit[] {
  const query = (input.query ?? "").trim();
  if (!query) return input.skills.map((s) => ({ skill: s, reason: "list" }));
  const hits: Array<{ skill: ActivatableSkill; tier: number; reason: string }> = [];
  for (const s of input.skills) {
    const reasons: string[] = [];
    let tier = Number.MAX_SAFE_INTEGER;
    if (explicitForms(s).some((f) => query.includes(f))) { reasons.push("explicit"); tier = Math.min(tier, 0); }
    if ((s.triggers?.commands ?? []).some((c) => query.includes(c))) { reasons.push("command(includes)"); tier = Math.min(tier, 1); }
    if ((s.triggers?.promptPatterns ?? []).some((p) => new RegExp(p, "i").test(query))) { reasons.push("pattern"); tier = Math.min(tier, 2); }
    if ((s.keywords ?? []).some((k) => query.toLowerCase().includes(String(k).toLowerCase()))) { reasons.push("keyword"); tier = Math.min(tier, 3); }
    if (reasons.length === 0 && (s.name.includes(query) || (s.description ?? "").includes(query))) { reasons.push("text"); tier = 4; }
    if (reasons.length > 0) hits.push({ skill: s, tier, reason: reasons.join("+") });
  }
  hits.sort((a, b) => (a.tier - b.tier) || (a.skill.id < b.skill.id ? -1 : 1));
  return hits.map((h) => ({ skill: h.skill, reason: h.reason }));
}

export interface SkillLoadResult {
  status: "ok" | "not-found";
  skill?: ActivatableSkill;
  /** 未找到时的建议列表（同形话术的数据面：不报错卡死）。 */
  suggestions?: string[];
}

/**
 * 按需加载（load_skill 等量）：精确 id 或插件限定 id 的末段后缀；加载不受注入预算限制
 * （正文全文返回）；未找到给建议列表（按名称/触发词模糊），不抛错。
 */
export function loadSkill(input: { skills: ActivatableSkill[]; id: string }): SkillLoadResult {
  const want = String(input.id ?? "").trim();
  const last = want.split(".").pop() ?? want;
  // 精确 id，或插件限定 id 的末段后缀（"plugin.evidence-catalog"/"evidence-catalog" 皆可载
  // "juscite-builtin-evidence-catalog"——后缀以 . / - 边界钉住，防误载近邻技能）
  const exact = input.skills.find(
    (s) => s.id === want || (s.aliasIds ?? []).includes(want)
      || s.id === last || s.id.endsWith("." + last) || s.id.endsWith("-" + last)
      || (s.aliasIds ?? []).some((a) => a === last),
  );
  if (exact) return { status: "ok", skill: exact };
  // 未找到：按 token 交叠给建议列表（不报错卡死）
  const tokens = want.toLowerCase().split(/[^a-z0-9\u4e00-\u9fff]+/).filter((t) => t.length >= 3);
  const suggestions = input.skills
    .filter((s) => {
      const hay = `${s.id} ${(s.aliasIds ?? []).join(" ")} ${s.name}`.toLowerCase();
      return tokens.some((t) => hay.includes(t));
    })
    .slice(0, 5)
    .map((s) => `${s.id}（${s.name}）`);
  return { status: "not-found", suggestions };
}

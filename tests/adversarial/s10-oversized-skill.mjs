#!/usr/bin/env node
// S10 合成材料：SKILL.md 正文超过 24KB 时，技能注入必须静默跳过，不得抛错。
import { planSkillInjection, SKILL_INJECTION_BUDGET_BYTES } from "../../packages/juscite-legal/src/kernel/skillActivationModel.ts";
import { identifySkill } from "../../tools/bridge/skills_service.mjs";

const hugeBody = "合成技能正文。\n" + "甲".repeat(9_000);
const hugeBytes = Buffer.byteLength(hugeBody, "utf8");
const small = {
  id: "synth-small",
  name: "合成小技能",
  description: "合成",
  body: "小技能正文。",
  triggers: { commands: ["/small"] },
  scope: "builtin",
};
const huge = {
  id: "synth-huge",
  name: "合成超限技能",
  description: "合成",
  body: hugeBody,
  triggers: { commands: ["/huge"] },
  scope: "builtin",
};

let failed = 0;
function check(name, cond, detail = "") {
  if (cond) console.log(`[S10] OK ${name}`);
  else {
    failed += 1;
    console.error(`[S10] FAIL ${name}${detail ? " — " + detail : ""}`);
  }
}

check("fixture over 24KB", hugeBytes > 24 * 1024 && hugeBytes > SKILL_INJECTION_BUDGET_BYTES, String(hugeBytes));

let plan;
try {
  plan = planSkillInjection({ skills: [huge, small], text: "/small $synth-huge 合成回合" });
} catch (error) {
  console.error("[S10] FAIL throw", error?.message ?? error);
  console.log("RESULT crash");
  process.exit(1);
}

check("huge skipped", plan.skippedOverBudget.some((hit) => hit.skill.id === "synth-huge"));
check("huge not injected", !plan.activations.some((hit) => hit.skill.id === "synth-huge") && !(plan.block ?? "").includes("合成技能正文"));
check("smaller sibling still eligible", plan.activations.some((hit) => hit.skill.id === "synth-small"));

const md = `---\nname: synth-huge\ndescription: 合成超限技能\n---\n${hugeBody}`;
let identified = null;
let identifyError = null;
try {
  identified = identifySkill(new Map([["SKILL.md", Buffer.from(md, "utf8")]]));
} catch (error) {
  identifyError = error;
}
check("skill loader does not crash", !identifyError, identifyError?.message ?? "");
check("loaded huge body is not forced into a throw", identified?.name === "synth-huge");

if (failed) {
  console.log("RESULT fail");
  process.exit(1);
}
console.log("RESULT pass");

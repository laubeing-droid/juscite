// 功能 #4 办案时间线技能（RE-4 §3 技能类附加；随 #21 技能安装线分发 + BUILTIN_SKILLS 注册）。
// 规范包唯一真源=implementation/skill-presets/timeline-generation/{skill.json,SKILL.md}，
// 本模块运行时读取（桥启动即验存在性，缺失 fail-closed 启动失败），不复制内容防两处漂移。
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

const DIR = fileURLToPath(new URL("../../implementation/skill-presets/timeline-generation/", import.meta.url));

export const TIMELINE_SKILL_META = JSON.parse(readFileSync(DIR + "skill.json", "utf-8"));
export const TIMELINE_SKILL_MD = readFileSync(DIR + "SKILL.md", "utf-8");

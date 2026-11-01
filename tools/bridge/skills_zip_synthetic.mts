// 功能 #21 合成 cat zip 装卸用例（RE-21 §5 验收）：对 ：3030 桥 skills 通道实跑——
// 1 SkillHub 形单层目录 zip（skill.json+SKILL.md）安装；2 cat/agent-skills 形根级
// SKILL.md frontmatter zip 安装；3 list 含两新技能且内置仍在；4 非法 zip 显式报错；
// 5 卸载（removeFromCommon/deleteSkill）后 list 不含。末行 SKILLS_ZIP_PASS/FAIL。合成材料。
import WebSocket from "ws";
import { VSBuffer, SocketProtocol, ChannelClient } from "@zcode/rpc";
import { deflateRawSync, crc32 } from "node:zlib";

// 最小 zip 写入器（deflate；够本用例）
function makeZip(files) {
  const locals = [];
  const centrals = [];
  let offset = 0;
  for (const [name, content] of files) {
    const nameBytes = Buffer.from(name, "utf8");
    const crc = crc32(content);
    const comp = deflateRawSync(content);
    const useDeflate = comp.length < content.length;
    const payload = useDeflate ? comp : content;
    const method = useDeflate ? 8 : 0;
    const local = Buffer.alloc(30);
    local.writeUInt32LE(0x04034b50, 0); local.writeUInt16LE(20, 4); local.writeUInt16LE(0, 6);
    local.writeUInt16LE(method, 8); local.writeUInt16LE(0, 10); local.writeUInt16LE(0, 12);
    local.writeUInt32LE(crc, 14); local.writeUInt32LE(payload.length, 18);
    local.writeUInt32LE(content.length, 22); local.writeUInt16LE(nameBytes.length, 26);
    local.writeUInt16LE(0, 28);
    locals.push(local, nameBytes, payload);
    const central = Buffer.alloc(46);
    central.writeUInt32LE(0x02014b50, 0); central.writeUInt16LE(20, 4); central.writeUInt16LE(20, 6);
    central.writeUInt16LE(0, 8); central.writeUInt16LE(method, 10); central.writeUInt16LE(0, 12);
    central.writeUInt16LE(0, 14); central.writeUInt32LE(crc, 16);
    central.writeUInt32LE(payload.length, 20); central.writeUInt32LE(content.length, 24);
    central.writeUInt16LE(nameBytes.length, 28); central.writeUInt16LE(0, 30);
    central.writeUInt16LE(0, 32); central.writeUInt16LE(0, 34); central.writeUInt16LE(0, 36);
    central.writeUInt32LE(offset, 42);
    centrals.push(central, nameBytes);
    offset += local.length + nameBytes.length + payload.length;
  }
  const cdStart = offset;
  let cdSize = 0;
  for (const b of centrals) cdSize += b.length;
  const eocd = Buffer.alloc(22);
  eocd.writeUInt32LE(0x06054b50, 0); eocd.writeUInt16LE(files.size, 8); eocd.writeUInt16LE(files.size, 10);
  eocd.writeUInt32LE(cdSize, 12); eocd.writeUInt32LE(cdStart, 16);
  return Buffer.concat([...locals, ...centrals, eocd]);
}

const ws = new WebSocket("ws://localhost:3030/ws");
ws.binaryType = "arraybuffer";
const data = { fire: (_b: VSBuffer) => {} };
ws.on("message", (buf: ArrayBuffer) => data.fire(VSBuffer.wrap(new Uint8Array(buf))));
await new Promise((r, j) => { ws.on("open", r); ws.on("error", j); });
const isocket = {
  onData: (l: (b: VSBuffer) => void) => { data.fire = l; return { dispose: () => {} }; },
  onClose: () => ({ dispose: () => {} }),
  onEnd: () => ({ dispose: () => {} }),
  write: (b: VSBuffer) => ws.send(b.buffer),
  end: () => ws.close(), drain: async () => {}, dispose: () => ws.close(),
};
const ch = new ChannelClient(new SocketProtocol(isocket as never)).getChannel("skills");
const call = <T,>(m: string, a?: unknown) => ch.call<T>(m, a === undefined ? [] : [a]);

const results: Array<{ name: string; ok: boolean; detail: string }> = [];
function check(name: string, ok: boolean, detail: string) {
  results.push({ name, ok, detail });
  console.log(`[skills-zip] ${name}: ${ok ? "OK" : "FAIL"} ${detail}`);
}

// 合成 zip A：SkillHub 形（单层子目录 skill.json+SKILL.md+资源）
const zipA = makeZip(new Map([
  ["law-contract-review/skill.json", Buffer.from(JSON.stringify({ name: "law-contract-review", description: "合成 SkillHub 形技能：合同审查清单", version: "1.0.0" }))],
  ["law-contract-review/SKILL.md", Buffer.from("# 合同审查清单\n合成正文（skillhub 形）。")],
  ["law-contract-review/reference/clauses.md", Buffer.from("合成条款参考材料。")],
]));
// 合成 zip B：cat/agent-skills 形（根级 SKILL.md frontmatter）
const zipB = makeZip(new Map([
  ["SKILL.md", Buffer.from("---\nname: cat-style-search\ndescription: 合成 cat 形技能：案内检索助手\n---\n# 检索助手\n合成正文（cat 形）。")],
  ["scripts/prompt.md", Buffer.from("合成提示词资源。")],
]));

// 用例 0：基线 list（内置 2 在场）
const base = await call<{ skills: Array<{ id: string }>; capability: { userScopeAvailable: boolean }; diagnostics: unknown[] }>("list");
check("基线 list（内置在场/形状合法）", base.skills.length >= 2 && base.capability.userScopeAvailable === true && Array.isArray(base.diagnostics),
  `skills=${base.skills.length} capability=${base.capability.userScopeAvailable}`);

// 用例 1：SkillHub 形安装
const i1 = await call<{ name: string; format: string }>("installSkillArchive", { archiveBase64: zipA.toString("base64"), filename: "law-contract-review.zip" });
check("SkillHub 形 zip 安装", i1.name === "law-contract-review" && i1.format === "skillhub-json", `name=${i1.name} format=${i1.format}`);

// 用例 2：cat 形安装
const i2 = await call<{ name: string; format: string }>("installSkillArchive", { archiveBase64: zipB.toString("base64"), filename: "cat-style-search.zip" });
check("cat 形 zip 安装", i2.name === "cat-style-search" && i2.format === "cat-frontmatter", `name=${i2.name} format=${i2.format}`);

// 用例 3：list 含两新技能（id=user-<name>；A 无 frontmatter → description 空但 body=SKILL.md 全文，B frontmatter → description）
const after = await call<{ skills: Array<{ id: string; description: string; body: string }> }>("list");
const gotA = after.skills.find((s) => s.id === "user-law-contract-review");
const gotB = after.skills.find((s) => s.id === "user-cat-style-search");
check("list 含两新技能", !!gotA && !!gotB && (gotA.body ?? "").includes("合同审查清单") && (gotB.description ?? "").includes("案内检索助手") && (gotB.body ?? "").includes("检索助手"),
  `A.body=${gotA?.body.slice(0, 16)} B.desc=${gotB?.description.slice(0, 16)}`);

// 用例 4：非法 zip 显式报错（不崩溃、不落库）
let err4 = "";
try { await call("installSkillArchive", { archiveBase64: Buffer.from("this is not a zip").toString("base64"), filename: "bad.zip" }); } catch (e) { err4 = String((e as Error).message ?? e); }
check("非法 zip 显式报错", err4.length > 0, `err=${err4.slice(0, 60)}`);

// 用例 5：启停
await call("setEnabled", { skillId: "user-cat-style-search", enabled: false });
const midList = await call<{ skills: Array<{ id: string; enabled: boolean }> }>("list");
const enabledNow = midList.skills.find((s) => s.id === "user-cat-style-search")?.enabled;
check("setEnabled 生效", enabledNow === false, `enabled=${enabledNow}`);

// 用例 6：卸载 cat 形（deleteSkill）→ list 不含；SkillHub 形（removeFromCommon）→ list 不含
await call("deleteSkill", { skillId: "user-cat-style-search" });
await call("removeFromCommon", { skillId: "user-law-contract-review" });
const final = await call<{ skills: Array<{ id: string }> }>("list");
const gone = !final.skills.some((s) => s.id === "user-cat-style-search") && !final.skills.some((s) => s.id === "user-law-contract-review");
const builtinStill = final.skills.filter((s) => s.id.startsWith("juscite-builtin")).length >= 2;
check("卸载生效且内置保留", gone && builtinStill, `A/B 已卸，内置 ${final.skills.filter((s) => s.id.startsWith("juscite-builtin")).length} 个`);

ws.close();
const failed = results.filter((r) => !r.ok);
console.log(failed.length ? "SKILLS_ZIP_FAIL" : "SKILLS_ZIP_PASS");
process.exit(failed.length ? 1 : 0);

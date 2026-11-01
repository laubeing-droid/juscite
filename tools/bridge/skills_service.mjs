// 功能 #21 技能安装 cat-zip 兼容（RE-21）：桥侧 ISkillsService 合成实现。
// zip 解析零依赖（EOCD→central directory→local header；stored/deflate；拒加密）；
// manifest 双格式兼容：cat/agent-skills 形（根 SKILL.md YAML frontmatter name/description）
// 与 SkillHub 形（skill.json 或 SKILL.md，根级/单层子目录——LegalWork skill-service 同构）。
// 技能库目录 %APPDATA%\Juscite\bridge\skills\<name>\；装卸全走该目录（Juscite 分区红线内）。
import { mkdirSync, existsSync, readFileSync, writeFileSync, rmSync, readdirSync } from "node:fs";
import { homedir } from "node:os";
import { join, dirname, basename } from "node:path";
import { inflateRawSync, crc32 } from "node:zlib";

const SKILLS_ROOT = join(homedir(), "AppData", "Roaming", "Juscite", "bridge", "skills");

// ── 最小 ZIP 解析 ────────────────────────────────────────────────
// 返回 Map<entryPath, Buffer>；目录项跳过；加密位/多卷/zip64 超界显式抛错。
export function parseZip(bytes) {
  if (bytes.length < 22 || bytes[0] !== 0x50 || bytes[1] !== 0x4b) throw new Error("不是有效的 zip 压缩包");
  let eocd = -1;
  for (let i = bytes.length - 22; i >= 0 && i > bytes.length - 66000; i--) {
    if (bytes[i] === 0x50 && bytes[i + 1] === 0x4b && bytes[i + 2] === 0x05 && bytes[i + 3] === 0x06) { eocd = i; break; }
  }
  if (eocd < 0) throw new Error("zip 缺少 central directory（EOCD）");
  const count = bytes.readUInt16LE(eocd + 10);
  let ptr = bytes.readUInt32LE(eocd + 16);
  const entries = new Map();
  for (let n = 0; n < count; n++) {
    if (bytes.readUInt32LE(ptr) !== 0x02014b50) throw new Error("central directory 损坏");
    const flags = bytes.readUInt16LE(ptr + 8);
    if (flags & 0x0001) throw new Error("不支持加密 zip");
    const method = bytes.readUInt16LE(ptr + 10);
    const crcExpected = bytes.readUInt32LE(ptr + 16);
    const size = bytes.readUInt32LE(ptr + 24);
    const nameLen = bytes.readUInt16LE(ptr + 28);
    const extraLen = bytes.readUInt16LE(ptr + 30);
    const commentLen = bytes.readUInt16LE(ptr + 32);
    const lho = bytes.readUInt32LE(ptr + 42);
    const name = bytes.slice(ptr + 46, ptr + 46 + nameLen).toString("utf8");
    ptr += 46 + nameLen + extraLen + commentLen;
    if (name.endsWith("/")) continue; // 目录项
    if (bytes.readUInt32LE(lho) !== 0x04034b50) throw new Error(`local header 损坏：${name}`);
    const lNameLen = bytes.readUInt16LE(lho + 26);
    const lExtraLen = bytes.readUInt16LE(lho + 28);
    const dataStart = lho + 30 + lNameLen + lExtraLen;
    const raw = bytes.slice(dataStart, dataStart + size);
    let content;
    if (method === 0) content = raw;
    else if (method === 8) content = inflateRawSync(raw);
    else throw new Error(`不支持的压缩方法 ${method}：${name}`);
    if (content.length !== size) throw new Error(`解压尺寸不符：${name}`);
    if (crc32(content) !== crcExpected) throw new Error(`CRC 校验失败：${name}`);
    entries.set(name.replace(/\\/g, "/"), content);
  }
  if (entries.size === 0) throw new Error("zip 内无文件");
  return entries;
}

// 剥公共首层目录（全部 entry 同一首层且无根级 manifest 时降一级——LegalWork 单层子目录布局等价）
function stripCommonPrefix(entries) {
  const paths = [...entries.keys()];
  const first = paths.map((p) => p.split("/")[0]);
  const sameDir = first.length > 0 && first.every((d) => d === first[0]) && paths.some((p) => p.includes("/"));
  if (!sameDir) return entries;
  const stripped = new Map();
  for (const [p, b] of entries) {
    const rest = p.slice(first[0].length + 1);
    if (rest) stripped.set(rest, b);
  }
  return stripped.size ? stripped : entries;
}

// YAML frontmatter 最小解析（--- 围栏内 name:/description: 行值）——cat/agent-skills 形
// 【施工单-10 单元二】读回忠实：双引号包裹值按转义序列还原（与 configWriteModel 写入面同语）；
// 单引号包裹值还原 '' 转义；裸值保持历史行为（剥首尾引号）。读回不成功不猜测。
function unquoteYamlValue(v) {
  if (v.length >= 2 && v.startsWith('"') && v.endsWith('"')) {
    try { return JSON.parse(v); } catch { return v.slice(1, -1); }
  }
  if (v.length >= 2 && v.startsWith("'") && v.endsWith("'")) {
    return v.slice(1, -1).replace(/''/g, "'");
  }
  return v.replace(/^["']|["']$/g, "");
}
function parseFrontmatter(md) {
  const m = /^---\r?\n([\s\S]*?)\r?\n---/.exec(md);
  if (!m) return null;
  const out = {};
  for (const line of m[1].split(/\r?\n/)) {
    const kv = /^(name|description):\s*(.+?)\s*$/.exec(line);
    if (kv) out[kv[1]] = unquoteYamlValue(kv[2]);
  }
  return out.name ? out : null;
}

// 双格式 manifest 识别（RE-21 §3）：返回 {name, description, body}；无法识别抛错。
export function identifySkill(entries) {
  const root = stripCommonPrefix(entries);
  const md = root.get("SKILL.md");
  const json = root.get("skill.json");
  if (md !== undefined) {
    const fm = parseFrontmatter(md.toString("utf8"));
    if (fm) {
      if (!fm.description) throw new Error("SKILL.md frontmatter 缺 description");
      return { name: fm.name, description: fm.description, body: md.toString("utf8"), format: "cat-frontmatter" };
    }
    if (json !== undefined) {
      const j = JSON.parse(json.toString("utf8"));
      if (!j.name) throw new Error("skill.json 缺 name");
      return { name: j.name, description: j.description ?? "", body: md.toString("utf8"), format: "skillhub-json" };
    }
    // 无 frontmatter 的裸 SKILL.md：名字取不了，拒绝（对齐 LegalWork「未找到 SKILL.md 或 skill.json」的严格面）
    throw new Error("SKILL.md 缺 YAML frontmatter（name/description）");
  }
  if (json !== undefined) {
    const j = JSON.parse(json.toString("utf8"));
    if (!j.name) throw new Error("skill.json 缺 name");
    const body = root.get(`${j.name}/SKILL.md`)?.toString("utf8") ?? "";
    return { name: j.name, description: j.description ?? "", body, format: "skillhub-json" };
  }
  throw new Error("未找到 SKILL.md 或 skill.json");
}

// ── 技能库（目录制）──────────────────────────────────────────────
function skillDir(name) {
  if (!/^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$/.test(name)) throw new Error(`非法技能名：${name}`);
  return join(SKILLS_ROOT, name);
}
export function installSkillArchiveEntries(entries) {
  const skill = identifySkill(entries);
  const dir = skillDir(skill.name);
  mkdirSync(dir, { recursive: true });
  const root = stripCommonPrefix(entries);
  for (const [p, b] of root) {
    const target = join(dir, p);
    if (!target.startsWith(dir)) throw new Error("zip 条目路径越界");
    mkdirSync(dirname(target), { recursive: true });
    writeFileSync(target, b);
  }
  return { name: skill.name, description: skill.description, format: skill.format, path: dir };
}
export function listInstalledSkillDirs() {
  if (!existsSync(SKILLS_ROOT)) return [];
  return readdirSync(SKILLS_ROOT, { withFileTypes: true })
    .filter((d) => d.isDirectory())
    .map((d) => join(SKILLS_ROOT, d.name));
}
export function readSkillMd(dir) {
  const p = join(dir, "SKILL.md");
  return existsSync(p) ? readFileSync(p, "utf8") : "";
}
export function removeSkillDir(name) {
  const dir = skillDir(name);
  if (!existsSync(dir)) return false;
  rmSync(dir, { recursive: true, force: true });
  return true;
}
export function skillsRoot() { return SKILLS_ROOT; }
// 已安装技能的描述信息（list 面）：根 SKILL.md frontmatter 优先，缺省空
export function describeInstalledSkill(dir) {
  const md = readSkillMd(dir);
  const fm = parseFrontmatter(md);
  return { name: basename(dir), description: fm?.description ?? "", body: md };
}
export const zipBasenames = { basename };

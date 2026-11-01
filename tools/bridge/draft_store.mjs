// 功能 #10 模板文书起草（RE-10 §3.1）：用户模板 + 生成历史持久化（JSON 文件 + 原子写）。
// 路径只落 %APPDATA%\Juscite（发布门②红线）；模型/凭据等敏感物不入此存储。
// 上限合同（对齐 RE-10 §3.1）：模板 content ≤5 万字 / fields ≤200 / 源文件 ≤16MB；
// 历史 fieldValues 每值 ≤5 万（无 200 字截断——竞品注释/实现偏差，我方按实现等量）/ 材料 ≤50 / 指令 ≤1 万 / 正文 ≤20 万。
import { createHash } from "node:crypto";
import { existsSync, mkdirSync, readFileSync, renameSync, rmSync, writeFileSync } from "node:fs";
import { homedir } from "node:os";
import { join } from "node:path";

const ROOT = join(homedir(), "AppData", "Roaming", "Juscite");
const USER_TEMPLATES_DIR = join(ROOT, "user-templates");
const SOURCES_DIR = join(USER_TEMPLATES_DIR, "sources");
const TEMPLATES_JSON = join(USER_TEMPLATES_DIR, "templates.json");
const HISTORY_DIR = join(ROOT, "document-history");
const HISTORY_JSON = join(HISTORY_DIR, "history.json");

const CONTENT_CAP = 50000;
const FIELDS_CAP = 200;
const SOURCE_BASE64_CAP = 16 * 1024 * 1024;
const HISTORY_CAP = 500;
const FIELD_VALUE_CAP = 50000;
const MATERIALS_CAP = 50;
const INSTRUCTIONS_CAP = 10000;
const GENERATED_CAP = 200000;
const LEARNING_STATUS = new Set(["idle", "analyzing", "done", "failed"]);

function atomicWrite(file, data) {
  mkdirSync(join(file, ".."), { recursive: true });
  const tmp = file + ".tmp-" + process.pid + "-" + Date.now();
  writeFileSync(tmp, data);
  renameSync(tmp, file); // 临时文件+rename 原子写
}
function sha256Of(buf) {
  return createHash("sha256").update(buf).digest("hex");
}
function clampStr(v, cap) {
  const s = typeof v === "string" ? v : "";
  return s.length > cap ? s.slice(0, cap) : s;
}

// ---------- 用户模板 ----------
function validateTemplateRecord(rec) {
  if (!rec || typeof rec !== "object") return null;
  if (typeof rec.id !== "string" || !rec.id) return null;
  if (typeof rec.name !== "string" || !rec.name) return null;
  if (typeof rec.content !== "string") return null;
  if (!Array.isArray(rec.fields)) return null;
  if (rec.content.length > CONTENT_CAP) return null; // 超上限=坏档剔除，不静默截断入库
  if (rec.fields.length > FIELDS_CAP) return null;
  if (rec.learningStatus !== undefined && !LEARNING_STATUS.has(rec.learningStatus)) return null;
  return {
    id: rec.id,
    name: rec.name,
    description: typeof rec.description === "string" ? rec.description : "",
    content: rec.content,
    fields: rec.fields.filter((f) => f && typeof f === "object" && typeof f.id === "string" && typeof f.label === "string"),
    legalBasis: typeof rec.legalBasis === "string" ? rec.legalBasis : "",
    category: "custom",
    createdAt: Number(rec.createdAt) || Date.now(),
    learningStatus: LEARNING_STATUS.has(rec.learningStatus) ? rec.learningStatus : "idle",
    learningError: typeof rec.learningError === "string" ? rec.learningError : "",
    sourceDocument: (rec.sourceDocument && typeof rec.sourceDocument === "object" &&
      typeof rec.sourceDocument.storedFileName === "string" && typeof rec.sourceDocument.sha256 === "string")
      ? { storedFileName: rec.sourceDocument.storedFileName, sha256: rec.sourceDocument.sha256, originalName: String(rec.sourceDocument.originalName ?? "") }
      : null,
  };
}
function loadTemplatesIndex() {
  if (!existsSync(TEMPLATES_JSON)) return [];
  let raw;
  try {
    raw = JSON.parse(readFileSync(TEMPLATES_JSON, "utf-8"));
  } catch {
    return []; // 索引损坏：按空目录处理（加载失败静默回退内置，RE-10 §2 I9）
  }
  if (!Array.isArray(raw)) return [];
  return raw.map(validateTemplateRecord).filter(Boolean); // 逐条校验剔坏档
}
export function listUserTemplates() {
  return loadTemplatesIndex();
}
export function getUserTemplate(id) {
  return loadTemplatesIndex().find((t) => t.id === id) ?? null;
}
export function upsertUserTemplate(rec) {
  const list = loadTemplatesIndex();
  const validated = validateTemplateRecord(rec);
  if (!validated) throw new Error("用户模板记录不合法（content 超上限/fields 超上限/缺 id 或 name）");
  const idx = list.findIndex((t) => t.id === validated.id);
  if (idx >= 0) list[idx] = validated; else list.push(validated);
  atomicWrite(TEMPLATES_JSON, JSON.stringify(list, null, 2));
  return validated;
}
// 上传成功即建 custom-<时间戳> 模板；.docx 额外保存原文件（sha256 记录，原子写）。
export function createUserTemplateFromUpload({ fileName, text, sourceBase64 }) {
  const content = clampStr(text, CONTENT_CAP);
  const id = "custom-" + Date.now();
  const rec = {
    id,
    name: String(fileName ?? "自定义模板").replace(/\.[^.]+$/, "") || "自定义模板",
    description: "上传的自定义模板（AI 学习完成前仅含全文（文本）字段）",
    content,
    fields: [{ id: "全文（文本）", label: "全文（文本）", type: "textarea", placeholder: "模板全部文字" }],
    legalBasis: "",
    category: "custom",
    createdAt: Date.now(),
    learningStatus: "analyzing",
    learningError: "",
    sourceDocument: null,
  };
  if (typeof sourceBase64 === "string" && sourceBase64.length > 0) {
    if (sourceBase64.length > SOURCE_BASE64_CAP) throw new Error("模板原文件超过 16MB 上限");
    const bytes = Buffer.from(sourceBase64, "base64");
    const storedFileName = id + ".docx";
    atomicWrite(join(SOURCES_DIR, storedFileName), bytes);
    rec.sourceDocument = { storedFileName, sha256: sha256Of(bytes), originalName: String(fileName ?? "") };
  }
  return upsertUserTemplate(rec);
}
// 读取原版 DOCX：哈希校验不过/路径含目录穿越 → 拒绝使用（RE-10 §2 I7）。
export function readTemplateSourceDocx(id) {
  const rec = getUserTemplate(id);
  if (!rec?.sourceDocument) return null;
  const name = rec.sourceDocument.storedFileName;
  if (/[\/]/.test(name) || name.includes("..")) throw new Error("模板原文件路径非法（拒绝使用，请重新上传 DOCX 模板）");
  const p = join(SOURCES_DIR, name);
  if (!p.startsWith(SOURCES_DIR)) throw new Error("模板原文件路径非法（拒绝使用，请重新上传 DOCX 模板）");
  if (!existsSync(p)) throw new Error("未找到模板原文件，请重新上传 DOCX 模板后再导出");
  const bytes = readFileSync(p);
  if (sha256Of(bytes) !== rec.sourceDocument.sha256) {
    throw new Error("模板原文件校验失败（内容已变化），请重新上传 DOCX 模板后再导出");
  }
  return { bytes, record: rec };
}
export function deleteUserTemplate(id) {
  const list = loadTemplatesIndex();
  const rec = list.find((t) => t.id === id);
  if (!rec) return false;
  const next = list.filter((t) => t.id !== id);
  atomicWrite(TEMPLATES_JSON, JSON.stringify(next, null, 2));
  if (rec.sourceDocument?.storedFileName) {
    const p = join(SOURCES_DIR, rec.sourceDocument.storedFileName);
    if (p.startsWith(SOURCES_DIR) && existsSync(p)) {
      try { rmSync(p); } catch { /* 删除连带失败不阻塞索引删除 */ }
    }
  }
  return true; // 删除模板连带删原版 DOCX
}

// ---------- 生成历史（500 条滚动淘汰；逐条校验剔坏档） ----------
function validateHistoryRecord(rec) {
  if (!rec || typeof rec !== "object") return null;
  if (typeof rec.id !== "string" || !rec.id) return null;
  if (typeof rec.templateName !== "string") return null;
  if (typeof rec.generatedContent !== "string") return null;
  const fieldValues = {};
  if (rec.fieldValues && typeof rec.fieldValues === "object") {
    for (const [k, v] of Object.entries(rec.fieldValues)) {
      if (typeof k !== "string" || typeof v !== "string") continue;
      fieldValues[k] = clampStr(v, FIELD_VALUE_CAP); // 每值 5 万上限；无 200 字截断
    }
  }
  return {
    id: rec.id,
    templateName: rec.templateName,
    templateCategory: typeof rec.templateCategory === "string" ? rec.templateCategory : "",
    templateSource: rec.templateSource === "custom" ? "custom" : "builtin",
    fieldValues,
    materialFileNames: Array.isArray(rec.materialFileNames) ? rec.materialFileNames.slice(0, MATERIALS_CAP).map(String) : [],
    instructions: clampStr(typeof rec.instructions === "string" ? rec.instructions : "", INSTRUCTIONS_CAP),
    generatedContent: clampStr(rec.generatedContent, GENERATED_CAP),
    verdict: typeof rec.verdict === "string" ? rec.verdict : "",
    model: typeof rec.model === "string" ? rec.model : "",
    createdAt: Number(rec.createdAt) || Date.now(),
  };
}
export function listDraftHistory() {
  if (!existsSync(HISTORY_JSON)) return [];
  let raw;
  try {
    raw = JSON.parse(readFileSync(HISTORY_JSON, "utf-8"));
  } catch {
    return []; // 加载失败报错误条由 UI 层负责；此处不炸
  }
  if (!Array.isArray(raw)) return [];
  return raw.map(validateHistoryRecord).filter(Boolean);
}
export function getDraftHistory(id) {
  return listDraftHistory().find((r) => r.id === id) ?? null;
}
export function addDraftHistoryRecord(rec) {
  const list = listDraftHistory();
  const validated = validateHistoryRecord({ ...rec, id: String(rec?.id ?? "dh-" + Date.now()) });
  if (!validated) throw new Error("历史记录不合法");
  list.unshift(validated);
  if (list.length > HISTORY_CAP) list.length = HISTORY_CAP; // 500 条滚动淘汰最旧
  atomicWrite(HISTORY_JSON, JSON.stringify(list, null, 2));
  return validated;
}
export function deleteDraftHistory(id) {
  const list = listDraftHistory();
  const next = list.filter((r) => r.id !== id);
  if (next.length === list.length) return false;
  atomicWrite(HISTORY_JSON, JSON.stringify(next, null, 2));
  return true;
}

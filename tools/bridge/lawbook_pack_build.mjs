#!/usr/bin/env node
// 法条手册内置包 v1 打包管线（RE-13-法条手册.md §3.1/§3.3 落码）。
// 种子=在盘 LawRefBook/Laws 快照（公有领域法条文本，著作权法第 5 条；源 commit=5057151，只读）。
// 管线：载入→清洗（去 frontmatter/裸 # 行，出注记）→契约预校验（违规文件拒绝入包并列清单，
//       双闸之打包闸，与桥解析同规 lawbook_model.validateLawMd）→ingest（名称去国名前缀/发布日取文件名/
//       生效日三分支）→修订链（H1）→跨法废止链（H2）→写 pack.sqlite3 + content/*.md + pack.meta。
// 产物：lawbook-packs/base/（随产品分发，materialize-bridge-bundle 随包搬运）。
// 用法：node tools/bridge/lawbook_pack_build.mjs [--laws-root <Laws克隆路径>] [--out lawbook-packs/base]
// 纯 Node 零新增依赖；包体断言 ≤2MB（§3.1 目标），超限 exit 1。
import { createHash } from "node:crypto";
import { existsSync, mkdirSync, readFileSync, readdirSync, rmSync, statSync, writeFileSync } from "node:fs";
import { join, resolve } from "node:path";
import { DatabaseSync } from "node:sqlite";
import { fileURLToPath } from "node:url";
import {
  buildRepealChain, buildRevisionChain, extractValidFrom, validateLawMd,
} from "./lawbook_model.mjs";

const REPO_ROOT = fileURLToPath(new URL("../../", import.meta.url)); // tools/bridge/ → 仓库根
const MANIFEST_PATH = join(REPO_ROOT, "tools", "bridge", "lawbook_pack_seed.json");
const SEED_NOTE = "LawRefBook/Laws 快照（在盘竞品资产，只读引用；commit 5057151）";
// 六目录名→同名 level，否则"法律"（等量 H5 get_law_level_by_folder）
const LEVEL_FOLDERS = new Set(["司法解释", "地方性法规", "宪法", "案例", "行政法规", "部门规章"]);
// category 分组/排序（等量参考库 category 表形态：is_subfolder=1 按(group)聚合成子文件夹区块，A3）
const CATEGORY_SHAPE = {
  "宪法": { group: "法律法规", order: 1 },
  "民法典": { group: "法律法规", order: 2 },
  "宪法相关法": { group: "法律法规", order: 3 },
  "行政法": { group: "法律法规", order: 4 },
  "民法商法": { group: "法律法规", order: 5 },
  "社会法": { group: "法律法规", order: 6 },
  "刑法": { group: "法律法规", order: 7 },
  "经济法": { group: "法律法规", order: 8 },
  "诉讼与非诉讼程序法": { group: "法律法规", order: 9 },
  "行政法规": { group: null, order: 801 },
  "司法解释": { group: null, order: 802 },
};

// ── CLI 参数 ──
function parseArgs(argv) {
  const args = { lawsRoot: process.env.LAWBOOK_SEED_ROOT ?? "", out: join(REPO_ROOT, "lawbook-packs", "base") };
  for (let i = 0; i < argv.length; i++) {
    if (argv[i] === "--laws-root") args.lawsRoot = resolve(argv[++i]);
    else if (argv[i] === "--out") args.out = resolve(argv[++i]);
  }
  return args;
}

function stripFrontmatter(text) {
  const m = String(text).match(/^\uFEFF?---\r?\n[\s\S]*?\r?\n---\r?\n?/);
  return m ? String(text).slice(m[0].length) : String(text);
}
function dropBareHeadingLines(text) {
  const kept = [];
  const dropped = [];
  String(text).split(/\r?\n/).forEach((l, i) => {
    if (/^#{1,6}\s*$/.test(l.trim()) && l.trim() !== "") dropped.push(i + 1);
    else kept.push(l);
  });
  return { text: kept.join("\n"), dropped };
}
function levelOfFolder(folder) { return LEVEL_FOLDERS.has(folder) ? folder : "法律"; }
function lawNameFromTitles(titles) {
  const first = (titles[0] ?? "").replace(/^中华人民共和国/, "");
  return [first, ...titles.slice(1)].filter(Boolean).join(" ");
}
function publishOfBasename(base) {
  const m = base.replace(/\.md$/u, "").match(/\((\d{4}-\d{2}-\d{2})\)$/u);
  return m ? m[1] : "";
}
function safeFileName(name) { return name.replace(/[\\/:*?"<>|]/g, "／"); }

function main() {
  const args = parseArgs(process.argv.slice(2));
  const manifest = JSON.parse(readFileSync(MANIFEST_PATH, "utf-8"));
  const lawsRoot = args.lawsRoot || manifest.lawsRootHint || "";
  if (!lawsRoot || !existsSync(lawsRoot)) {
    console.error(`[lawbook-build] FAIL：种子根不存在（--laws-root 或 LAWBOOK_SEED_ROOT 或 manifest.lawsRootHint）：${lawsRoot}`);
    process.exit(1);
  }
  console.log(`[lawbook-build] 种子根 ${lawsRoot}（${SEED_NOTE}）`);
  const notes = [];
  const excluded = [];
  const rows = []; // {id,name,subtitle,level,category_id,publish,valid_from,valid_to,ver,tags,filename,order_num,folder,body}
  const catSeen = new Map();

  for (const rel of manifest.files) {
    const folder = rel.includes("/") ? rel.slice(0, rel.indexOf("/")) : "";
    const base = rel.includes("/") ? rel.slice(rel.indexOf("/") + 1) : rel;
    const src = join(lawsRoot, rel);
    if (!existsSync(src)) { excluded.push(`${rel}：源文件缺失`); continue; }
    const catId = createHash("sha1").update(`cat:${folder}`).digest("hex").slice(0, 32);
    if (!catSeen.has(folder)) {
      const shape = CATEGORY_SHAPE[folder];
      if (!shape) { excluded.push(`${rel}：未知目录（CATEGORY_SHAPE 无 ${folder}）`); continue; }
      catSeen.set(folder, { id: catId, name: folder, folder, is_subfolder: 1, group: shape.group, sort_order: shape.order });
    }
    let text = stripFrontmatter(readFileSync(src, "utf-8"));
    const bare = dropBareHeadingLines(text);
    if (bare.dropped.length) notes.push(`${rel}：清洗裸标题行 ${bare.dropped.length} 处（行 ${bare.dropped.join(",")}）`);
    text = bare.text;
    const pre = validateLawMd(text);
    if (!pre.ok) { excluded.push(`${rel}：契约违规 ${pre.violations.map((v) => `${v.type}@L${v.line}`).join(";")}`); continue; }
    const id = createHash("sha1").update(`${folder}/${base}`).digest("hex").slice(0, 32);
    const filenameRel = `${folder}/${safeFileName(base.replace(/\.md$/u, ""))}.md`;
    const titles = [...text.matchAll(/^#\s+(.+)$/gm)].map((m) => m[1].trim());
    if (!titles.length) { excluded.push(`${rel}：无 # 标题行`); continue; }
    const name = lawNameFromTitles(titles);
    const publish = publishOfBasename(base) || null;
    const bodyStart = text.indexOf("<!-- INFO END -->");
    const body = text.slice(bodyStart >= 0 ? bodyStart : 0);
    const validFrom = extractValidFrom(body, publish);
    const dup = rows.find((r) => r.name === name && (r.publish ?? "") === (publish ?? ""));
    if (dup) { excluded.push(`${rel}：同名同公布日重复（已在包：${dup.filename}）`); continue; }
    rows.push({
      id, name, subtitle: null, level: levelOfFolder(folder), category_id: catId,
      publish, valid_from: validFrom, valid_to: "2099-12-31", ver: 1, tags: "[]",
      filename: filenameRel, order_num: 0, folder, body: text,
    });
  }
  if (!rows.length) { console.error("[lawbook-build] FAIL：可入包文件为零"); process.exit(1); }

  // 组内排序：manifest 顺序即序（多版本行相邻，publish 升序排后者在后）
  const perCat = new Map();
  for (const r of rows) {
    const n = perCat.get(r.category_id) ?? 0;
    r.order_num = n;
    perCat.set(r.category_id, n + 1);
  }
  // 修订链（H1）→ 跨法废止链（H2，次序固定：版本衔接先归位，跨法废止补最后一版）
  const chain = buildRevisionChain(rows.map(({ body, ...r }) => r));
  for (const r of rows) {
    const u = chain.updates.get(r.id);
    if (u) { r.ver = u.ver; if (u.valid_to) r.valid_to = u.valid_to; }
  }
  const bodies = new Map(rows.map((r) => [r.id, r.body]));
  const repeal = buildRepealChain(rows.map(({ body, ...r }) => r), bodies);
  for (const r of rows) {
    const u = repeal.updates.get(r.id);
    if (u?.valid_to) r.valid_to = u.valid_to;
  }

  // ── 落盘 ──
  const outDir = args.out;
  const contentDir = join(outDir, "content");
  rmSync(outDir, { recursive: true, force: true });
  mkdirSync(contentDir, { recursive: true });
  for (const r of rows) {
    const p = join(contentDir, r.filename);
    mkdirSync(join(p, ".."), { recursive: true });
    writeFileSync(p, r.body, "utf-8");
  }
  const dbPath = join(outDir, "pack.sqlite3");
  if (existsSync(dbPath)) rmSync(dbPath);
  const db = new DatabaseSync(dbPath);
  db.exec(`
    PRAGMA journal_mode = DELETE;
    CREATE TABLE law (
      id TEXT PRIMARY KEY, name TEXT NOT NULL, subtitle TEXT, level TEXT NOT NULL,
      category_id TEXT, publish TEXT, valid_from TEXT DEFAULT '', valid_to TEXT DEFAULT '2099-12-31',
      ver INTEGER NOT NULL DEFAULT 1, tags TEXT NOT NULL DEFAULT '[]', filename TEXT NOT NULL,
      order_num INTEGER NOT NULL DEFAULT 0
    );
    CREATE INDEX idx_law_name ON law (name);
    CREATE INDEX idx_law_category ON law (category_id);
    CREATE TABLE category (
      id TEXT PRIMARY KEY, name TEXT NOT NULL, folder TEXT, is_subfolder INTEGER NOT NULL DEFAULT 0,
      "group" TEXT, sort_order INTEGER NOT NULL DEFAULT 0
    );
  `);
  const qLaw = db.prepare(`INSERT INTO law (id,name,subtitle,level,category_id,publish,valid_from,valid_to,ver,tags,filename,order_num)
    VALUES (?,?,?,?,?,?,?,?,?,?,?,?)`);
  const qCat = db.prepare(`INSERT INTO category (id,name,folder,is_subfolder,"group",sort_order) VALUES (?,?,?,?,?,?)`);
  db.exec("BEGIN");
  for (const c of [...catSeen.values()].sort((a, b) => a.sort_order - b.sort_order)) {
    qCat.run(c.id, c.name, c.folder, c.is_subfolder, c.group, c.sort_order);
  }
  for (const r of rows) {
    qLaw.run(r.id, r.name, r.subtitle, r.level, r.category_id, r.publish, r.valid_from, r.valid_to, r.ver, r.tags, r.filename, r.order_num);
  }
  db.exec("COMMIT");
  const quick = db.prepare("PRAGMA quick_check").get();
  db.close();
  if (quick?.quick_check !== "ok") { console.error(`[lawbook-build] FAIL：quick_check=${quick?.quick_check}`); process.exit(1); }

  const stat = statSync(dbPath);
  const hash = createHash("sha256").update(readFileSync(dbPath)).digest("hex");
  const meta = { name: "base", hash, update: Math.floor(Date.now() / 1000), filesize: stat.size };
  writeFileSync(join(outDir, "pack.meta"), JSON.stringify(meta, null, 2), "utf-8");

  const dirSize = (d) => readdirSync(d, { withFileTypes: true })
    .reduce((n, e) => n + (e.isDirectory() ? dirSize(join(d, e.name)) : statSync(join(d, e.name)).size), 0);
  const total = dirSize(outDir);
  const multiVer = rows.filter((r) => r.ver > 1).length;
  const chained = rows.filter((r) => r.valid_to !== "2099-12-31").length;
  console.log(`[lawbook-build] 行数=${rows.length}（多版本行=${multiVer}，非默认 valid_to 行=${chained}）目录数=${catSeen.size}`);
  console.log(`[lawbook-build] 包体=${total} B（${(total / 1024 / 1024).toFixed(2)} MB）目标 ≤2MB`);
  if (chain.warnings.length) console.log(`[lawbook-build] H1 警告：\n  ${chain.warnings.join("\n  ")}`);
  if (repeal.warnings.length) console.log(`[lawbook-build] H2 警告：\n  ${repeal.warnings.join("\n  ")}`);
  if (notes.length) console.log(`[lawbook-build] 清洗注记：\n  ${notes.join("\n  ")}`);
  if (excluded.length) console.log(`[lawbook-build] 拒绝入包清单（${excluded.length}）：\n  ${excluded.join("\n  ")}`);
  if (total > 2 * 1024 * 1024) { console.error("[lawbook-build] FAIL：包体超 2MB 目标"); process.exit(1); }
  console.log(`[lawbook-build] OK sha256=${hash.slice(0, 12)}… size=${stat.size} B → ${outDir}`);
}

main();

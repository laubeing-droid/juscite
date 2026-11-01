// 功能 #13 法条手册桥面服务（RE-13-法条手册.md §3.2 落码）。
// 包聚合：lawbook-packs/ 目录多包（等量 E6），包校验 fail-closed（sha256 对账+quick_check+抽一条解析自检，
// §3.1 首启包引导）；解析走 lawbook_model（双闸同规，禁 LLM）；收藏/历史落桥同库（迁移 0016_lawbook）。
// 删除延迟语义（等量 E7/E5）：{name}.delete 标记下次启动统一清理，支持撤销；DLC 六态枚举本期只落
// 本地可达态（success/deleted/error），下载类态随远端订阅线挂起（§3.1 预留接口）。
// HTTP 面挂 /api/legal/laws* 与 /api/legal/packs*（新增端点族·命名提案沿 /api/legal 前缀，§3.2）。
import { createHash, randomUUID } from "node:crypto";
import { existsSync, readdirSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { join, resolve } from "node:path";
import { DatabaseSync } from "node:sqlite";
import { deriveEffect, EFFECT_LABEL, parseLawMd, titleMatches, todayCn } from "./lawbook_model.mjs";

const LAW_LEVEL_ORDER = [ // 阶位组序固定 11 档（等量 Consts.LawLevel）
  "宪法", "法律", "司法解释", "行政法规", "地方性法规", "部门规章",
  "经济特区法规", "自治条例", "单行条例", "案例", "其他",
];
const HISTORY_LIMIT = 10; // 搜索历史最近 10 条（等量 buildRequest limit 10）
const SEARCH_RESULT_CAP = 200;
const PACK_STATE = {
  UNKNOWN: "unknown", SUCCESS: "success", DOWNLOADING: "downloading",
  FAILED: "failed", UPDATE_AVAILABLE: "update_available", DELETED: "deleted",
};
const DELETE_MARKER_EXT = "delete"; // 等量 LocalManager EXT_DELETE：{name}.delete 标记

function resolvePacksRoot() {
  const envRoot = process.env.BRIDGE_LAWBOOK_PACK_ROOT;
  if (envRoot) return resolve(envRoot);
  let dir = process.cwd();
  for (let i = 0; i < 8 && dir; i++) { // kbBuiltinSourceRoot 同款向上 8 级扫描
    const cand = join(dir, "lawbook-packs");
    if (existsSync(cand)) return cand;
    const parent = resolve(dir, "..");
    if (parent === dir) break;
    dir = parent;
  }
  return null;
}

function metaOf(row, catName, today) {
  const effect = deriveEffect({ valid_from: row.valid_from, valid_to: row.valid_to, publish: row.publish }, today);
  return {
    id: row.id, name: row.name, subtitle: row.subtitle ?? "", level: row.level,
    categoryId: row.category_id, categoryName: catName ?? "",
    publish: row.publish ?? "", ver: row.ver ?? 1,
    publishShow: (row.ver ?? 1) > 1 && !!row.publish, // 等量 A5 双条件：ver>1 且 publish 非空才显公布日
    effect, effectLabel: EFFECT_LABEL[effect],
  };
}

export function createLawbookService({ workspaceKey, store }) {
  const ws = workspaceKey;
  const root = resolvePacksRoot();
  const packs = []; // {name,dir,state,lawCount,reason,meta}
  const lawMap = new Map(); // 同 ID 先到先得（等量 lawMap linkLaws 跨包去重）
  const catMap = new Map(); // id → category 行
  const parseCache = new Map(); // lawId → 解析结果（等量 LawContentManager.cache）

  // ── 载入与首启校验（fail-closed：坏包标 error 并排除，不静默用残包）──
  function loadPacks() {
    packs.length = 0; lawMap.clear(); catMap.clear(); parseCache.clear();
    if (!root || !existsSync(root)) {
      packs.push({ name: "(无包根)", dir: "", state: "error", lawCount: 0, reason: "lawbook-packs 目录不存在", meta: null });
      return;
    }
    // 延迟删除落地：上次会话的 {name}.delete 标记本次启动统一清理（等量 LocalManager 注释语义）
    for (const entry of readdirSync(root)) {
      if (!entry.endsWith(`.${DELETE_MARKER_EXT}`)) continue;
      const targetName = entry.slice(0, -(DELETE_MARKER_EXT.length + 1));
      try { rmSync(join(root, targetName), { recursive: true, force: true }); } catch { /* 尽力而为 */ }
      try { rmSync(join(root, entry), { force: true }); } catch { /* 尽力而为 */ }
    }
    const dirs = readdirSync(root, { withFileTypes: true })
      .filter((d) => d.isDirectory()).map((d) => d.name).sort();
    for (const name of dirs) {
      const dir = join(root, name);
      const rec = { name, dir, state: "error", lawCount: 0, reason: "", meta: null };
      packs.push(rec);
      const metaPath = join(dir, "pack.meta");
      const dbPath = join(dir, "pack.sqlite3");
      if (!existsSync(metaPath) || !existsSync(dbPath)) { rec.reason = "缺 pack.meta 或 pack.sqlite3"; continue; }
      let meta;
      try { meta = JSON.parse(readFileSync(metaPath, "utf-8")); } catch { rec.reason = "pack.meta 解析失败"; continue; }
      try {
        const buf = readFileSync(dbPath);
        const hash = createHash("sha256").update(buf).digest("hex");
        if (meta.hash !== hash || Number(meta.filesize) !== buf.length) { rec.reason = "sha256/filesize 对账失败（包损坏）"; continue; }
      } catch (e) { rec.reason = `读取包失败：${e.message}`; continue; }
      let db;
      try {
        db = new DatabaseSync(dbPath, { readOnly: true });
        const quick = db.prepare("PRAGMA quick_check").get();
        if (quick?.quick_check !== "ok") throw new Error(`quick_check=${quick?.quick_check}`);
      } catch (e) { rec.reason = `sqlite 打开/quick_check 失败：${e.message}`; continue; }
      let rows = []; let catRows = [];
      try {
        rows = db.prepare("SELECT * FROM law").all();
        catRows = db.prepare("SELECT * FROM category ORDER BY sort_order").all();
      } catch (e) { rec.reason = `包库读取失败：${e.message}`; db.close?.(); continue; }
      try {
        const first = rows[0]; // 抽一条解析自检（§3.1 首启包引导校验）
        if (first) parseLawMd(readFileSync(join(dir, "content", first.filename), "utf-8"), first.id);
      } catch (e) { rec.reason = `抽检解析自检失败：${e.message}`; db.close?.(); continue; }
      rec.state = PACK_STATE.SUCCESS;
      rec.lawCount = rows.length;
      rec.meta = { name: String(meta.name ?? name), hash: meta.hash, update: Number(meta.update ?? 0), filesize: Number(meta.filesize ?? 0) };
      for (const c of catRows) if (!catMap.has(c.id)) catMap.set(c.id, { ...c, pack: name });
      for (const r of rows) {
        if (lawMap.has(r.id)) continue; // 同 ID 先到先得（等量 E6）
        lawMap.set(r.id, { ...r, pack: name, dirAbs: dir });
      }
      db.close();
    }
  }
  loadPacks();

  const catNameOf = (row) => catMap.get(row.category_id)?.name ?? "";
  const contentPathOf = (row) => join(row.dirAbs, "content", row.filename);

  function parsedOf(row) {
    if (parseCache.has(row.id)) return parseCache.get(row.id);
    const parsed = parseLawMd(readFileSync(contentPathOf(row), "utf-8"), row.id);
    parseCache.set(row.id, parsed);
    return parsed;
  }

  function availableOrThrow() {
    if (!packs.some((p) => p.state === PACK_STATE.SUCCESS)) {
      const reason = packs[0]?.reason || "未安装法条包";
      const e = new Error(`法条包不可用：${reason}`);
      e.http = 503;
      throw e;
    }
  }

  // ── 目录树（对拍 1：双分组同序；效力计数）──
  function categories() {
    const today = todayCn();
    const dept = [...catMap.values()]
      .sort((a, b) => (a.sort_order ?? 0) - (b.sort_order ?? 0))
      .map((c) => ({ id: c.id, name: c.name, folder: c.folder, group: c.group ?? "", sortOrder: c.sort_order ?? 0, count: 0, repealed: 0, notYet: 0 }));
    const byId = new Map(dept.map((d) => [d.id, d]));
    const levels = new Map();
    for (const r of lawMap.values()) {
      const m = metaOf(r, catNameOf(r), today);
      const d = byId.get(m.categoryId);
      if (d) { d.count += 1; if (m.effect === "repealed") d.repealed += 1; if (m.effect === "not_yet") d.notYet += 1; }
      const lv = levels.get(m.level) ?? { level: m.level, count: 0, repealed: 0, notYet: 0 };
      lv.count += 1;
      if (m.effect === "repealed") lv.repealed += 1;
      if (m.effect === "not_yet") lv.notYet += 1;
      levels.set(m.level, lv);
    }
    const present = [...levels.values()].sort((a, b) =>
      LAW_LEVEL_ORDER.indexOf(a.level) - LAW_LEVEL_ORDER.indexOf(b.level)); // 阶位序固定 11 档
    return { available: true, total: lawMap.size, dept, levels: present, levelOrder: LAW_LEVEL_ORDER };
  }

  // ── 搜索（对拍 9/10：双模式；标题=包含或全分词包含顺序无关；全文=逐法解析命中）──
  // query 空 + category/level 非空 = 组内浏览（等量 A1/A2：目录树展开列出组内全部法规，组内按 order+name 排序；
  // level=法律阶位分组浏览承载，对拍 1 双分组面板目录树同构）
  function search({ query, mode, category, level }) {
    availableOrThrow();
    const today = todayCn();
    const q = String(query ?? "").trim();
    const cat = String(category ?? "");
    const lv = String(level ?? "");
    const m = mode === "fulltext" ? "fulltext" : "title";
    const results = [];
    if (!q && !cat && !lv) return { mode: m, query: q, count: 0, results }; // 空查询=空结果（C6 清空回历史由 UI 承接）
    const rows = [...lawMap.values()].filter((r) => (!cat || r.category_id === cat) && (!lv || r.level === lv));
    for (const r of rows) {
      if (m === "title") {
        if (q && !titleMatches(r.name, q)) continue;
      } else {
        if (!q) continue; // 全文模式必须带词
        let parsed;
        try { parsed = parsedOf(r); } catch { continue; } // 单法契约违规不拖垮全文搜索（fail-closed 已在 detail 具名报）
        if (!parsed.paragraphs.some((p) => (p.text || "").includes(q))) continue;
      }
      results.push(metaOf(r, catNameOf(r), today));
    }
    const catOrder = new Map([...catMap.values()].map((c) => [c.id, c.sort_order ?? 0]));
    results.sort((a, b) => (catOrder.get(a.categoryId) ?? 0) - (catOrder.get(b.categoryId) ?? 0)
      || (lawMap.get(a.id).order_num ?? 0) - (lawMap.get(b.id).order_num ?? 0)
      || a.name.localeCompare(b.name, "zh-Hans-CN")
      || (b.publish ?? "").localeCompare(a.publish ?? ""));
    return { mode: m, query: q, count: results.length, results: results.slice(0, SEARCH_RESULT_CAP) };
  }

  // ── 详情（对拍 4/5/6/7/14/25：解析后内容带行号；fail-closed 具名报错）──
  function detail(id) {
    availableOrThrow();
    const row = lawMap.get(String(id ?? ""));
    if (!row) {
      const e = new Error(`法条不存在：${id}`);
      e.http = 404;
      throw e;
    }
    const today = todayCn();
    try {
      const parsed = parsedOf(row);
      return { law: metaOf(row, catNameOf(row), today), content: parsed };
    } catch (e) {
      e.http = 422; // 契约违规=解析失败具名报错（法 ID+违规类型+行号），UI 错误占位不白屏
      throw e;
    }
  }

  // ── 篇内过滤（对拍 8：服务端过滤，保留含命中的节；全不命中=空列表，UI 出空态占位）──
  function filter(id, q) {
    availableOrThrow();
    const query = String(q ?? "");
    const row = lawMap.get(String(id ?? ""));
    if (!row) {
      const e = new Error(`法条不存在：${id}`);
      e.http = 404;
      throw e;
    }
    const parsed = parsedOf(row);
    if (!query.trim()) return { query, hitCount: 0, firstHitLine: null, sections: [], paragraphs: [] };
    const hits = parsed.paragraphs.filter((p) => (p.text || "").includes(query));
    const keptSections = [];
    const bounds = parsed.sections.map((s, i) => [s, parsed.sections[i + 1]?.line ?? Infinity]);
    for (const [s, nextLine] of bounds) {
      if (hits.some((h) => h.line >= s.line && h.line < nextLine)) keptSections.push(s);
    }
    return {
      query, hitCount: hits.length,
      firstHitLine: hits.length ? hits[0].line : null,
      sections: keptSections, paragraphs: hits,
    };
  }

  // ── 搜索历史（对拍 11：10 条/倒序/同词刷新不新增/空文本不落库/共享与独立两制）──
  function putHistory({ text, scope, lawId }) {
    const t = String(text ?? "").trim();
    if (!t) return { stored: false, reason: "空文本不落库" };
    const sc = scope === "standalone" ? "standalone" : "shared";
    const scopeLawId = sc === "standalone" ? (lawId ? String(lawId) : null) : null;
    const ts = Date.now();
    const existing = store.lbGetHistoryByText(ws, sc, scopeLawId, t);
    if (existing) { // 同词重复提交=刷新原记录时间戳不新增（等量 SearchHistoryUtil :18-21）
      store.lbRefreshHistory(ws, existing.row_id, ts);
      return { stored: true, rowId: existing.row_id, refreshed: true };
    }
    const rowId = randomUUID();
    store.lbPutHistory({ workspace_key: ws, row_id: rowId, scope: sc, law_id: scopeLawId, text: t, search_t: ts });
    return { stored: true, rowId, refreshed: false };
  }
  const listHistory = ({ scope, lawId }) => ({
    scope: scope === "standalone" ? "standalone" : "shared",
    items: store.lbListHistory(ws, scope === "standalone" ? "standalone" : "shared",
      scope === "standalone" ? (lawId ? String(lawId) : null) : null, HISTORY_LIMIT)
      .map((r) => ({ rowId: r.row_id, text: r.text, lawId: r.law_id ?? null, searchT: r.search_t })),
  });
  const deleteHistory = ({ rowId }) => { store.lbDeleteHistoryRow(ws, String(rowId ?? "")); return { ok: true }; };
  const clearHistory = ({ scope, lawId }) => {
    store.lbClearHistory(ws, scope === "standalone" ? "standalone" : "shared",
      scope === "standalone" ? (lawId ? String(lawId) : null) : null);
    return { ok: true };
  };

  // ── 收藏（对拍 12：两级+夹管理+级联连删+无幂等；乐观更新失败回滚由 UI 承接）──
  function favoritesAll() {
    const today = todayCn();
    const folders = store.lbListFolders(ws).map((f) => ({ id: f.folder_id, name: f.name, sortOrder: f.sort_order }));
    const laws = store.lbListFavLaws(ws).map((r) => {
      const row = lawMap.get(r.law_id);
      return {
        rowId: r.row_id, lawId: r.law_id, createdAt: r.created_at,
        name: row?.name ?? "(法条不在当前包)", effect: row ? metaOf(row, catNameOf(row), today).effect : "unknown",
        publish: row?.publish ?? "",
      };
    });
    const contents = store.lbListFavContents(ws).map((r) => {
      const row = lawMap.get(r.law_id);
      let text = null;
      if (row) {
        try {
          const p = parsedOf(row).paragraphs.find((x) => x.line === r.line);
          text = p?.text ?? null;
        } catch { text = null; } // 解析失败不拖垮书签列表
      }
      return {
        rowId: r.row_id, lawId: r.law_id, line: r.line, folderId: r.folder_id, createdAt: r.created_at,
        name: row?.name ?? "(法条不在当前包)", effect: row ? metaOf(row, catNameOf(row), today).effect : "unknown",
        text,
      };
    });
    return { folders, laws, contents };
  }
  function lawState(lawId) {
    return { lawId: String(lawId ?? ""), favorited: store.lbCountFavLaw(ws, String(lawId ?? "")) > 0 };
  }
  function lawToggle({ lawId }) {
    const id = String(lawId ?? "");
    if (store.lbCountFavLaw(ws, id) > 0) { store.lbDeleteFavLawRows(ws, id); return { favorited: false }; }
    store.lbAddFavLaw({ workspace_key: ws, row_id: randomUUID(), law_id: id, created_at: Date.now() });
    return { favorited: true };
  }
  function folderCreate({ name }) {
    const n = String(name ?? "").trim();
    if (!n) { const e = new Error("夹名不能为空"); e.http = 400; throw e; }
    const existing = store.lbListFolders(ws);
    const nextOrder = existing.length ? Math.max(...existing.map((f) => f.sort_order ?? 0)) + 1 : 0;
    const id = randomUUID();
    store.lbCreateFolder({ workspace_key: ws, folder_id: id, name: n, sort_order: nextOrder, created_at: Date.now() });
    return { id, name: n };
  }
  function folderRename({ folderId, name }) {
    const n = String(name ?? "").trim();
    if (!n) { const e = new Error("夹名不能为空"); e.http = 400; throw e; }
    store.lbRenameFolder(ws, String(folderId ?? ""), n);
    return { ok: true };
  }
  function folderDelete({ folderId }) {
    const fid = String(folderId ?? "");
    const count = store.lbFolderContentCount(ws, fid);
    store.lbDeleteFolder(ws, fid); // 级联连删夹内收藏条目（等量 D2）
    return { deletedContents: count };
  }
  function folderReorder({ orderedIds }) {
    store.lbReorderFolders(ws, (orderedIds ?? []).map(String));
    return { ok: true };
  }
  function contentAdd({ lawId, line, folderId }) {
    const fid = String(folderId ?? "");
    if (!store.lbListFolders(ws).some((f) => f.folder_id === fid)) {
      const e = new Error("收藏夹不存在");
      e.http = 400;
      throw e;
    }
    const rowId = randomUUID(); // 无幂等：重复收藏同夹=重复条目（等量 B7/对拍 12）
    store.lbAddFavContent({ workspace_key: ws, row_id: rowId, law_id: String(lawId ?? ""), line: Number(line ?? 0), folder_id: fid, created_at: Date.now() });
    return { rowId };
  }
  function contentDelete({ rowId }) { store.lbDeleteFavContentRow(ws, String(rowId ?? "")); return { ok: true }; }
  function contentMove({ rowIds, folderId }) {
    store.lbMoveFavContentRows(ws, (rowIds ?? []).map(String), String(folderId ?? ""));
    return { ok: true };
  }

  // ── 包管理面（对拍 15/18 本期子集：本地态 + 延迟删除 + 撤销；下载态随远端订阅挂起）──
  function packsList() {
    return {
      root: root ?? "",
      packs: packs.map((p) => ({
        name: p.name,
        state: p.state === PACK_STATE.SUCCESS && root !== null && existsSync(join(root, `${p.name}.${DELETE_MARKER_EXT}`))
          ? PACK_STATE.DELETED : p.state,
        lawCount: p.lawCount, reason: p.reason ?? "",
        hash: p.meta?.hash ?? "", update: p.meta?.update ?? 0, filesize: p.meta?.filesize ?? 0,
      })),
    };
  }
  function packDelete({ name }) {
    if (!root) { const e = new Error("无包根"); e.http = 503; throw e; }
    const dir = join(root, String(name ?? ""));
    if (!existsSync(dir)) { const e = new Error(`包不存在：${name}`); e.http = 404; throw e; }
    writeFileSync(join(root, `${String(name)}.${DELETE_MARKER_EXT}`), ""); // 只标记，不立即删（下次启动统一清理）
    return { marked: true, note: "已标记删除，重启后清理；撤销可恢复" };
  }
  function packRevert({ name }) {
    if (!root) { const e = new Error("无包根"); e.http = 503; throw e; }
    const marker = join(root, `${String(name ?? "")}.${DELETE_MARKER_EXT}`);
    if (existsSync(marker)) rmSync(marker, { force: true });
    return { reverted: true };
  }

  function status() {
    const ok = packs.some((p) => p.state === PACK_STATE.SUCCESS);
    return { available: ok, root: root ?? "", packs: packsList().packs, total: lawMap.size };
  }

  // ── HTTP 面（/api/legal/laws* + /api/legal/packs*）──
  async function httpHandler(req, res, url) {
    const path = url.pathname;
    if (!path.startsWith("/api/legal/laws") && !path.startsWith("/api/legal/packs")) return false;
    const send = (code, obj) => {
      if (res.headersSent) { res.end(); return; }
      res.writeHead(code, { "content-type": "application/json; charset=utf-8" });
      res.end(JSON.stringify(obj));
    };
    const readBody = async () => {
      const chunks = [];
      let size = 0;
      for await (const c of req) {
        size += c.length;
        if (size > 1024 * 1024) throw Object.assign(new Error("请求体超限"), { http: 413 });
        chunks.push(c);
      }
      const raw = Buffer.concat(chunks).toString("utf-8");
      return raw ? JSON.parse(raw) : {};
    };
    try {
      const m = req.method ?? "GET";
      // —— 包管理面（先于 laws/:id 兜底匹配）——
      if (path === "/api/legal/packs" && m === "GET") { send(200, packsList()); return true; }
      if (path === "/api/legal/packs/delete" && m === "POST") { send(200, packDelete(await readBody())); return true; }
      if (path === "/api/legal/packs/revert" && m === "POST") { send(200, packRevert(await readBody())); return true; }
      // —— 法条面 ——
      if (path === "/api/legal/laws/status" && m === "GET") { send(200, status()); return true; }
      if (path === "/api/legal/laws/categories" && m === "GET") { send(200, categories()); return true; }
      if (path === "/api/legal/laws" && m === "GET") {
        send(200, search({ query: url.searchParams.get("query") ?? "", mode: url.searchParams.get("mode") ?? "title", category: url.searchParams.get("category") ?? "", level: url.searchParams.get("level") ?? "" }));
        return true;
      }
      if (path === "/api/legal/laws/history" && m === "GET") {
        send(200, listHistory({ scope: url.searchParams.get("scope") ?? "shared", lawId: url.searchParams.get("lawId") ?? null }));
        return true;
      }
      if (path === "/api/legal/laws/history" && m === "POST") { send(200, putHistory(await readBody())); return true; }
      if (path === "/api/legal/laws/history/delete" && m === "POST") { send(200, deleteHistory(await readBody())); return true; }
      if (path === "/api/legal/laws/history/clear" && m === "POST") { send(200, clearHistory(await readBody())); return true; }
      if (path === "/api/legal/laws/favorites" && m === "GET") { send(200, favoritesAll()); return true; }
      if (path === "/api/legal/laws/favorites/law" && m === "GET") {
        send(200, lawState(url.searchParams.get("lawId") ?? ""));
        return true;
      }
      if (path === "/api/legal/laws/favorites/law/toggle" && m === "POST") { send(200, lawToggle(await readBody())); return true; }
      if (path === "/api/legal/laws/favorites/folders" && m === "POST") {
        const body = await readBody();
        const action = String(body.action ?? "");
        if (action === "create") send(200, folderCreate(body));
        else if (action === "rename") send(200, folderRename(body));
        else if (action === "delete") send(200, folderDelete(body));
        else if (action === "reorder") send(200, folderReorder(body));
        else { const e = new Error(`未知夹操作：${action}`); e.http = 400; throw e; }
        return true;
      }
      if (path === "/api/legal/laws/favorites/content" && m === "POST") { send(200, contentAdd(await readBody())); return true; }
      if (path === "/api/legal/laws/favorites/content/delete" && m === "POST") { send(200, contentDelete(await readBody())); return true; }
      if (path === "/api/legal/laws/favorites/content/move" && m === "POST") { send(200, contentMove(await readBody())); return true; }
      // —— 详情/篇内过滤兜底：/api/legal/laws/{id}（id=32 hex 或短串）——
      const dm = path.match(/^\/api\/legal\/laws\/([0-9a-zA-Z_-]+)$/);
      if (dm && m === "GET") {
        const q = url.searchParams.get("q");
        send(200, q === null ? detail(dm[1]) : filter(dm[1], q));
        return true;
      }
      send(404, { error: { message: `法条手册未知路由：${m} ${path}` } });
      return true;
    } catch (e) {
      send(e?.http ?? 500, { error: { message: e?.message ?? String(e), lawId: e?.lawId, violations: e?.violations } });
      return true;
    }
  }

  return {
    httpHandler, categories, search, detail, filter, status, packsList, packDelete, packRevert,
    putHistory, listHistory, deleteHistory, clearHistory,
    favoritesAll, lawState, lawToggle, folderCreate, folderRename, folderDelete, folderReorder,
    contentAdd, contentDelete, contentMove,
    reload: loadPacks, // 重试/重新导入指引后的重载入口（§3.1 兜底）
  };
}

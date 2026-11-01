// 功能 #36 分层记忆（RE-36 §3）：桥侧运行时——本地可读文件族 IO（Markdown/JSON，F1 形态等量）。
// 四层两作用域：用户级=个人偏好/操作纠正（跨案跟随律师，D2 口径；§3 有意偏离：不随单只业务流）；
// 项目级=项目约定/资源指引（随项目隔离，D2/D3 本地落盘）。
// 存储根=%APPDATA%\Juscite\bridge\layered-memory\（BRIDGE_LAYERED_MEMORY_ROOT 仅测试覆盖；
// 红线②：只碰 Juscite 分区；凭据/令牌不入记忆域，RE-36 §5）。
// 纯模型单源=packages/juscite-legal/src/kernel/layeredMemoryModel.ts（回写合并/置信门/注入装配）；
// 本文件只做 IO 装配。空态静默（F4/F15/F18）：文件缺失=空态直接可用不报错；
// 自动维护文件只经回写 API 变更、不设手工写入入口（F17）；偏好 md 族可直接编辑新建（F16）；
// 用户数据可控：原样读（可查看）+ 删文件/删作用域级清除（红线）。
// 文案全部自写（表达隔离：等量≠抄文案）。
import {
  assembleInjection,
  canSedimentResearch,
  isValidProjectId,
  matchPreferenceFiles,
  mergeCorrection, mergeRepresentative, mergeTaxonomy,
  normalizeCorrectionsFile, normalizeRepresentativesFile, normalizeTaxonomyFile,
  normalizeMemoryRelPath, resolveMemoryFileKind,
  findTaxonomyNode,
  PREFERENCE_COMMON_FILE,
  renderCorrectionLines,
  resolveConfidenceGate,
  researchReuseDecision,
  markResearched,
  typeKeyOfPreferenceFileName,
} from "../../packages/juscite-legal/src/kernel/layeredMemoryModel.ts";
import { mkdirSync, readdirSync, readFileSync, renameSync, rmSync, statSync, writeFileSync } from "node:fs";
import { join } from "node:path";

const ATOMIC_RETRY = 5;

export function createLayeredMemoryRuntime({
  root,                     // 记忆域根绝对路径（桥侧钉 Juscite 分区；测试经 env 覆盖）
  now = () => Date.now(),
  log = () => {},
}) {
  if (!root || typeof root !== "string") throw new Error("layered-memory: root 未注入");

  // ── 原子写（Windows 竞争容错：临时文件+改名+瞬态重试；#18 K3 同族自写，同步面不驻留）──
  function atomicWrite(target, data) {
    let lastErr = null;
    for (let attempt = 0; attempt < ATOMIC_RETRY; attempt++) {
      const tmp = `${target}.tmp-${now().toString(36)}-${attempt}`;
      try {
        writeFileSync(tmp, data, "utf-8");
        try { rmSync(target, { force: true }); } catch { /* 首写不存在 */ }
        renameSync(tmp, target);
        return;
      } catch (e) {
        lastErr = e;
        try { rmSync(tmp, { force: true }); } catch { /* tmp 已消失 */ }
        if (!/EPERM|EACCES|EBUSY/i.test(String(e?.message ?? e))) break; // 非瞬态不重试
      }
    }
    throw lastErr ?? new Error("layered-memory: 写入失败");
  }

  // ── 相对路径→绝对路径（越界/白名单外拒绝）──
  function toAbs(rel) {
    const segs = normalizeMemoryRelPath(rel);
    if (!segs) throw new Error(`记忆域路径非法：${rel}`);
    return { segs, abs: join(root, ...segs) };
  }

  // ── 读文件（缺失=静默空；JSON 损坏=自动知识树按空库重建、用户纠正记录如实抛错 fail-closed）──
  function readText(rel) {
    const { abs } = toAbs(rel);
    try {
      return readFileSync(abs, "utf-8");
    } catch (e) {
      if (e?.code === "ENOENT") return null;
      throw e;
    }
  }
  function readJson(rel, normalize, kindLabel) {
    const text = readText(rel);
    if (text === null) return normalize(undefined, now());
    try {
      return normalize(JSON.parse(text), now());
    } catch (e) {
      if (kindLabel === "corrections") throw new Error(`纠正记录文件损坏，请先在查看面核对或清除后重试：${rel}`);
      log(`[layered-memory] ${rel} 解析失败按空库重建（自动可再生知识）：${String(e?.message ?? e).slice(0, 80)}`);
      return normalize(undefined, now());
    }
  }
  function writeJson(rel, obj) {
    const { segs, abs } = toAbs(rel);
    mkdirSync(join(root, ...segs.slice(0, -1)), { recursive: true });
    atomicWrite(abs, JSON.stringify(obj, null, 2) + "\n");
  }

  const correctionsRel = () => "user/corrections.json";
  const taxonomyRel = (pid) => `projects/${pid}/auto/taxonomy.json`;
  const representativesRel = (pid) => `projects/${pid}/auto/representatives.json`;
  const researchRel = (pid, leaf) => `projects/${pid}/auto/research/${leaf}.md`;

  // ── 可查看（红线：用户数据可控）──
  function listFiles() {
    const out = [];
    const walk = (dir, relPrefix, depth) => {
      if (depth > 6) return;
      let entries = [];
      try { entries = readdirSync(dir, { withFileTypes: true }); } catch { return; }
      for (const e of entries) {
        const abs = join(dir, e.name);
        const rel = relPrefix ? `${relPrefix}/${e.name}` : e.name;
        if (e.isDirectory()) { walk(abs, rel, depth + 1); continue; }
        if (!e.isFile() || e.isSymbolicLink()) continue;
        const segs = normalizeMemoryRelPath(rel);
        const meta = segs ? resolveMemoryFileKind(segs) : null;
        if (!meta) continue; // 记忆域白名单外残骸不列
        let sizeBytes = 0, updatedAt = 0;
        try { const st = statSync(abs); sizeBytes = st.size; updatedAt = st.mtimeMs; } catch { continue; }
        out.push({ rel, kind: meta.kind, scope: meta.scope, layer: meta.layer, sizeBytes, updatedAt });
      }
    };
    walk(root, "", 0);
    out.sort((a, b) => (a.rel < b.rel ? -1 : 1));
    return out;
  }

  function overview() {
    const files = listFiles();
    const userPrefs = files.filter((f) => f.scope === "user" && f.layer === "preference");
    let correctionCount = 0;
    try { correctionCount = readJson(correctionsRel(), normalizeCorrectionsFile, "overview").records.length; }
    catch { /* 损坏如实显示 0，详情面读原样时可见错误 */ }
    const projectIds = new Set(files.filter((f) => f.scope === "project").map((f) => f.rel.split("/")[1]));
    return {
      root,
      layers: {
        preference: { scope: "user", fileCount: userPrefs.length },
        correction: { scope: "user", recordCount: correctionCount },
        convention: { scope: "project", projectCount: projectIds.size },
        resource: { scope: "project", projectCount: projectIds.size },
      },
      files,
    };
  }

  // ── 手写族编辑（F16 可直接编辑新建；F17 自动维护文件拒绝手写；F15 缺失静默）──
  function writeHandwritten(rel, content) {
    const { segs, abs } = toAbs(rel);
    const meta = resolveMemoryFileKind(segs);
    if (!meta) throw new Error(`不在记忆域文件族内：${rel}`);
    if (meta.kind !== "handwritten") throw new Error(`该文件由业务动作自动维护，不设手工编辑入口（可经清除入口删除）：${rel}`);
    const body = String(content ?? "");
    if (body.length > 512 * 1024) throw new Error("偏好文件超出 512KB 上限");
    mkdirSync(join(root, ...segs.slice(0, -1)), { recursive: true });
    atomicWrite(abs, body === "" || body.endsWith("\n") ? body : body + "\n");
    return { rel, kind: meta.kind, layer: meta.layer };
  }

  function readRaw(rel) {
    const { segs } = toAbs(rel);
    const meta = resolveMemoryFileKind(segs);
    if (!meta) throw new Error(`不在记忆域文件族内：${rel}`);
    const content = readText(rel);
    if (content === null) return { exists: false, rel, kind: meta.kind, layer: meta.layer, content: "", updatedAt: 0 };
    let updatedAt = 0;
    try { updatedAt = statSync(join(root, rel)).mtimeMs; } catch { /* 读到即算在 */ }
    return { exists: true, rel, kind: meta.kind, layer: meta.layer, content, updatedAt };
  }

  // ── 可清除（删文件级 + 删作用域级；自动维护文件同样可清除=删文件级，红线：用户数据可控）──
  function clearFile(rel) {
    const { segs, abs } = toAbs(rel);
    const meta = resolveMemoryFileKind(segs);
    if (!meta) throw new Error(`不在记忆域文件族内：${rel}`);
    rmSync(abs, { force: true });
    return { cleared: [rel] };
  }
  function clearScope(scope, projectId) {
    if (scope === "user") {
      rmSync(join(root, "user"), { recursive: true, force: true });
      return { cleared: ["user/*"] };
    }
    if (scope === "project") {
      if (!isValidProjectId(projectId ?? "")) throw new Error("项目 id 非法");
      rmSync(join(root, "projects", projectId), { recursive: true, force: true });
      return { cleared: [`projects/${projectId}/*`] };
    }
    throw new Error("scope 须为 user|project");
  }

  // ── 写入触发①：显式纠正（用户指出并纠正的做法；同类去重累加+时间戳，§3）──
  function recordCorrection({ scene, wrong, right, origin }) {
    const rel = correctionsRel();
    const file = readJson(rel, normalizeCorrectionsFile, "corrections");
    const r = mergeCorrection(file, { scene, wrong, right, origin }, now());
    writeJson(rel, r.file);
    return { id: r.id, merged: r.merged, rel };
  }

  // ── 写入触发②：模式沉淀（重复选择/偏好自动累积；随对应业务动作回写，形态对齐 F2/F12）──
  function sedimentTaxonomy({ projectId, treeKey, path }) {
    if (!isValidProjectId(projectId ?? "")) throw new Error("项目 id 非法");
    const rel = taxonomyRel(projectId);
    const file = readJson(rel, normalizeTaxonomyFile, "taxonomy");
    const r = mergeTaxonomy(file, treeKey, Array.isArray(path) ? path : [], now());
    writeJson(rel, r.file);
    return { rel, appended: r.appended, totalClassified: r.file._meta.total_classified };
  }

  function sedimentRepresentative({ projectId, name, role, category, scale, date }) {
    if (!isValidProjectId(projectId ?? "")) throw new Error("项目 id 非法");
    const rel = representativesRel(projectId);
    const file = readJson(rel, normalizeRepresentativesFile, "representatives");
    const r = mergeRepresentative(file, { name, role, category, scale, date }, now());
    writeJson(rel, r.file);
    return { rel, merged: r.merged, rowCount: r.file.rows.length };
  }

  // ── 置信门（F8/F9/F10/F11/F18）：候选由调用方按业务匹配给出，本门只做分支判定 ──
  function resolveGate({ candidates, inputs }) {
    return resolveConfidenceGate(Array.isArray(candidates) ? candidates : [], inputs ?? {});
  }

  // ── 注入装配（§3：按层装配，项目约定优先于个人偏好；类型>通用 F14；缺失静默 F15）──
  function preferenceFilesOf() {
    const out = [];
    let entries = [];
    try { entries = readdirSync(join(root, "user"), { withFileTypes: true }); } catch { return out; }
    for (const e of entries) {
      if (!e.isFile() || e.isSymbolicLink()) continue;
      const isType = typeKeyOfPreferenceFileName(e.name) !== null;
      if (!isType && e.name !== PREFERENCE_COMMON_FILE) continue;
      let body = "";
      try { body = readFileSync(join(root, "user", e.name), "utf-8"); } catch { continue; } // 读失败静默跳过（F15）
      out.push({ fileName: e.name, typeKey: isType ? typeKeyOfPreferenceFileName(e.name) : null, body });
    }
    out.sort((a, b) => (a.fileName < b.fileName ? -1 : 1));
    return out;
  }

  function injectionPlan({ projectId, category, turnText }) {
    const sections = [];
    const pid = projectId == null || projectId === "" ? null : String(projectId);
    if (pid !== null && !isValidProjectId(pid)) throw new Error("项目 id 非法");
    // 项目级（随项目走）：约定 > 资源；文件缺失静默跳过（F15/D3 空态）
    if (pid !== null) {
      const conv = readText(`projects/${pid}/conventions.md`);
      if (conv !== null && conv.trim()) sections.push({ key: `projects/${pid}/conventions.md`, layer: "convention", body: conv });
      const res = readText(`projects/${pid}/resources.md`);
      if (res !== null && res.trim()) sections.push({ key: `projects/${pid}/resources.md`, layer: "resource", body: res });
    }
    // 用户级（随律师走）：类型偏好 > 通用偏好（F14，多关键词命中只取第一个）；纠正按轮次文本命中渲染
    const matched = matchPreferenceFiles(preferenceFilesOf(), category ?? "");
    if (matched.typeFile?.body?.trim()) sections.push({ key: `user/${matched.typeFile.fileName}`, layer: "preference", body: matched.typeFile.body });
    if (matched.commonFile?.body?.trim()) sections.push({ key: `user/${matched.commonFile.fileName}`, layer: "preference", body: matched.commonFile.body });
    try {
      const corrections = readJson(correctionsRel(), normalizeCorrectionsFile, "overview");
      const lines = renderCorrectionLines(corrections.records, turnText ?? "");
      if (lines.length) sections.push({ key: "user/corrections.json", layer: "correction", body: lines.join("\n") });
    } catch { /* 纠正文件损坏不阻塞注入（对话可用性优先，查看面可见原样错误） */ }
    return assembleInjection(sections);
  }

  // ── researched 沉淀复用（F5/F6；叶钉 contract_category 树=合同类别主树，自定收敛）──
  function sedimentResearch({ projectId, leafName, content }) {
    if (!isValidProjectId(projectId ?? "")) throw new Error("项目 id 非法");
    const leaf = String(leafName ?? "").trim();
    if (!leaf || leaf.includes("/") || leaf.includes("\\") || leaf === "." || leaf === "..") throw new Error("叶节点名非法");
    if (!canSedimentResearch(content ?? "")) {
      // F6：研究未做（数据源未就绪/内容为空）→ 不沉淀文件、不改标记
      return { sedimented: false, rel: researchRel(projectId, leaf) };
    }
    const rel = researchRel(projectId, leaf);
    const tRel = taxonomyRel(projectId);
    const file = readJson(tRel, normalizeTaxonomyFile, "taxonomy");
    writeJson(tRel, markResearched(file, "contract_category", [leaf])); // 路径不存在=错误，不虚设节点
    const { segs, abs } = toAbs(rel);
    mkdirSync(join(root, ...segs.slice(0, -1)), { recursive: true });
    atomicWrite(abs, String(content).trim() + "\n");
    return { sedimented: true, rel };
  }

  function researchReuse({ projectId, leafName }) {
    if (!isValidProjectId(projectId ?? "")) throw new Error("项目 id 非法");
    const leaf = String(leafName ?? "").trim();
    const tFile = readJson(taxonomyRel(projectId), normalizeTaxonomyFile, "taxonomy");
    const node = findTaxonomyNode(tFile, "contract_category", leaf);
    const sediment = readText(researchRel(projectId, leaf));
    return { leaf, ...researchReuseDecision(node?.researched === true, sediment) };
  }

  // 空库直接可用（F4）：构造不建目录，首写惰性创建
  return {
    root,
    overview, listFiles, readRaw, writeHandwritten, clearFile, clearScope,
    recordCorrection, sedimentTaxonomy, sedimentRepresentative, resolveGate,
    injectionPlan, sedimentResearch, researchReuse,
  };
}

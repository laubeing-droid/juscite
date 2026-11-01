// 功能 #29 新手引导与产品指引（RE-29 §3 实现规格，等量自研）：
//   onboarding 状态机（pending/completed × guideStatus × demoChoice）+ 演示集一次性导入
//   （单事务+台账防重+四表卫检+表空才插）+ 法库指路（F1/F2 拦截文案与可用性检查）。
// 全部文案自写（表达隔离）；演示集为合成虚构数据，禁用真实案件材料（红线①）。
import { readFileSync } from "node:fs";
import { homedir } from "node:os";
import { join } from "node:path";

export const DEMO_DATASET_VERSION = "demo-v1";

// ---------- app_meta KV（三键：onboarding.status / onboarding.guideStatus / onboarding.demoChoice） ----------
export function metaGet(db, key) {
  const row = db.prepare("SELECT value FROM app_meta WHERE key = ?").get(key);
  return row ? row.value : null;
}

export function metaSet(db, key, value) {
  db.prepare(`
    INSERT INTO app_meta (key, value, updated_at) VALUES (?, ?, datetime('now'))
    ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = datetime('now')`).run(key, String(value));
}

// ---------- 首启判定（A1/A2/P2b）----------
// 首建（库文件此前不存在）→ pending/pending；真旧库升级（文件在但 meta 无 onboarding.status）→
// 一次性 completed/skipped 永不出向导；同版本 pending 重开 → 守卫拦下保持 pending。
export function initOnboardingState(db, existedBeforeOpen) {
  if (metaGet(db, "onboarding.status") !== null) return; // 守卫：只认 meta 缺失，重开不翻判
  if (existedBeforeOpen) {
    metaSet(db, "onboarding.status", "completed");
    metaSet(db, "onboarding.guideStatus", "skipped");
  } else {
    metaSet(db, "onboarding.status", "pending");
    metaSet(db, "onboarding.guideStatus", "pending");
  }
}

// ---------- 归一化读（G2）----------
export function getOnboardingState(db) {
  const rawStatus = metaGet(db, "onboarding.status");
  const rawGuide = metaGet(db, "onboarding.guideStatus");
  const rawChoice = metaGet(db, "onboarding.demoChoice");
  const status = rawStatus === "pending" ? "pending" : "completed"; // 非 pending 一律归一 completed
  const guideStatus = rawGuide === "completed" || rawGuide === "skipped" ? rawGuide : "pending"; // 非法归一 pending
  const demoChoice = rawChoice === "blank" || rawChoice === "demo" ? rawChoice : null; // 非法/未置归一 null
  const demoImported = !!db.prepare("SELECT version FROM onboarding_demo_ledger WHERE version = ?").get(DEMO_DATASET_VERSION);
  return { status, demoChoice, demoImported, guideStatus };
}

// ---------- 演示集导入 ----------
// 四表卫检（C3）：案件/文档/客户/日程任一非空即拒（调用方负责回滚，UI 红字可重试）。
export function assertDemoImportable(db) {
  const occupied = ["demo_cases", "demo_documents", "demo_clients", "demo_schedule_events"]
    .filter((t) => db.prepare(`SELECT COUNT(*) AS n FROM ${t}`).get().n > 0);
  if (occupied.length > 0) throw new Error("检测到工作区已有业务数据，为免混入虚构演示内容，本次导入已取消（数据未做任何改动）。");
}

function daysAgo(n) { return Date.now() - n * 86_400_000; }

// 本周周一 09:00（本地时区）锚（C4：本周日程以周一为锚）
export function currentWeekMonday(now = Date.now()) {
  const d = new Date(now);
  const shift = d.getDay() === 0 ? 6 : d.getDay() - 1;
  d.setDate(d.getDate() - shift);
  d.setHours(9, 0, 0, 0);
  return d.getTime();
}

// 演示集内容（全部合成虚构；计数=RE-29 C4 同量级：六案/八文档/六客户/七日程/全局任务5/案内任务3/
// 当事人3/证据4/策略1/阶段节点3）。日期相对锚定（N 天前/本周周一）。
function demoSeedRows(monday) {
  const at = (dayIdx, h = 9) => monday + dayIdx * 86_400_000 + (h - 9) * 3_600_000;
  return {
    cases: [
      { case_id: "c1", name: "演示·借款合同纠纷（张三 诉 李四）", case_no: "（2026）合0101民初1号", case_type: "民间借贷", stage: "一审审理中", client_id: "cl1", created_at: daysAgo(21) },
      { case_id: "c2", name: "演示·劳动争议（王五 诉 合成科技）", case_no: "（2026）合0102民初2号", case_type: "劳动争议", stage: "仲裁前准备", client_id: "cl3", created_at: daysAgo(18) },
      { case_id: "c3", name: "演示·买卖合同纠纷（合成贸易 诉 合成建材）", case_no: "（2026）合0103民初3号", case_type: "买卖合同", stage: "立案", client_id: "cl2", created_at: daysAgo(12) },
      { case_id: "c4", name: "演示·房屋租赁纠纷（赵六 诉 钱七）", case_no: "（2026）合0104民初4号", case_type: "租赁合同", stage: "协商阶段", client_id: "cl5", created_at: daysAgo(9) },
      { case_id: "c5", name: "演示·物业服务合同纠纷（合成物业 批量诉）", case_no: "（2026）合0105民初5号", case_type: "物业服务合同", stage: "诉前调解", client_id: "cl6", created_at: daysAgo(6) },
      { case_id: "c6", name: "演示·机动车交通事故责任纠纷（孙八）", case_no: "（2026）合0106民初6号", case_type: "交通事故", stage: "证据收集", client_id: "cl4", created_at: daysAgo(3) },
    ],
    stageEvents: [
      { case_id: "c1", stage: "接待委托", summary: "委托手续与风险告知完成", happened_at: daysAgo(21) },
      { case_id: "c1", stage: "立案受理", summary: "法院已立案并排期", happened_at: daysAgo(14) },
      { case_id: "c1", stage: "开庭排期", summary: "一审第一次开庭已排期（本周）", happened_at: daysAgo(2) },
    ],
    clients: [
      { client_id: "cl1", name: "张三", kind: "自然人", contact: "138-0000-0001（合成）", created_at: daysAgo(30) },
      { client_id: "cl2", name: "合成贸易有限公司", kind: "企业法人", contact: "0592-0000002（合成）", created_at: daysAgo(28) },
      { client_id: "cl3", name: "王五", kind: "自然人", contact: "139-0000-0003（合成）", created_at: daysAgo(20) },
      { client_id: "cl4", name: "孙八", kind: "自然人", contact: "137-0000-0004（合成）", created_at: daysAgo(5) },
      { client_id: "cl5", name: "赵六", kind: "自然人", contact: "136-0000-0005（合成）", created_at: daysAgo(10) },
      { client_id: "cl6", name: "合成物业管理有限公司", kind: "企业法人", contact: "0592-0000006（合成）", created_at: daysAgo(7) },
    ],
    documents: [
      { doc_id: "d1", case_id: "c1", title: "民事起诉状（演示草稿）", kind: "文书", status: "draft", created_at: daysAgo(20) },
      { doc_id: "d2", case_id: "c1", title: "证据清单（演示）", kind: "文书", status: "final", created_at: daysAgo(16) },
      { doc_id: "d3", case_id: "c1", title: "借款合同扫描件（合成样本）", kind: "材料", status: "final", created_at: daysAgo(22) },
      { doc_id: "d4", case_id: "c1", title: "微信催款记录导出（合成样本）", kind: "材料", status: "final", created_at: daysAgo(15) },
      { doc_id: "d5", case_id: "c2", title: "劳动仲裁申请书（演示）", kind: "文书", status: "final", created_at: daysAgo(11) },
      { doc_id: "d6", case_id: "c3", title: "对账单与催告函（合成样本）", kind: "材料", status: "final", created_at: daysAgo(8) },
      { doc_id: "d7", case_id: "c4", title: "租赁合同与交接单（合成样本）", kind: "材料", status: "final", created_at: daysAgo(6) },
      { doc_id: "d8", case_id: "c5", title: "物业费欠费明细表（演示）", kind: "材料", status: "final", created_at: daysAgo(4) },
    ],
    schedule: [
      { event_id: "sch1", case_id: "c1", title: "内部案件讨论（演示案合集）", kind: "meeting", due_at: at(0, 10) },
      { event_id: "sch2", case_id: "c2", title: "劳动仲裁立案材料准备", kind: "work", due_at: at(1, 14) },
      { event_id: "sch3", case_id: "c1", title: "证据交换（演示借款案）", kind: "work", due_at: at(2, 15) },
      { event_id: "sch4", case_id: "c1", title: "开庭·一审第一次（演示借款案）", kind: "hearing", due_at: at(3, 9) },
      { event_id: "sch5", case_id: null, title: "客户接待（演示：新案咨询）", kind: "meeting", due_at: at(4, 11) },
      { event_id: "sch6", case_id: "c6", title: "上诉期与举证期核对", kind: "work", due_at: at(5, 10) },
      { event_id: "sch7", case_id: null, title: "本周案卷归档与周结", kind: "work", due_at: at(6, 17) },
    ],
    globalTasks: [
      { task_id: "t1", case_id: null, title: "完善利益冲突检索台账", source: "manual", done: 1, created_at: daysAgo(25) },
      { task_id: "t2", case_id: null, title: "更新所内收费标准", source: "manual", done: 1, created_at: daysAgo(19) },
      { task_id: "t3", case_id: null, title: "归档上月案卷", source: "manual", done: 1, created_at: daysAgo(13) },
      { task_id: "t4", case_id: null, title: "核对合规培训学时", source: "manual", done: 1, created_at: daysAgo(7) },
      { task_id: "t5", case_id: null, title: "准备下周开庭提纲（演示借款案）", source: "manual", done: 0, created_at: daysAgo(1) },
    ],
    caseTasks: [
      { task_id: "ct1", case_id: "c1", title: "补齐转账凭证原件核对", source: "manual", done: 0, created_at: daysAgo(5) },
      { task_id: "ct2", case_id: "c1", title: "起草庭审提纲", source: "manual", done: 0, created_at: daysAgo(3) },
      { task_id: "ct3", case_id: "c1", title: "梳理诉讼时效起算与中断证据", source: "ai", done: 0, created_at: daysAgo(2) },
    ],
    parties: [
      { case_id: "c1", name: "张三", role: "原告", client_id: "cl5" },
      { case_id: "c1", name: "李四", role: "被告", client_id: null },
      { case_id: "c1", name: "合成担保有限公司", role: "第三人", client_id: null },
    ],
    evidence: [
      { evidence_id: "ev1", case_id: "c1", title: "借款合同原件（合成样本）", tag: "核心" },
      { evidence_id: "ev2", case_id: "c1", title: "银行转账回单（合成样本）", tag: "核心" },
      { evidence_id: "ev3", case_id: "c1", title: "微信催款记录（合成样本）", tag: "辅助" },
      { evidence_id: "ev4", case_id: "c1", title: "证人出庭提纲（演示）", tag: "辅助" },
    ],
    strategies: [
      { strategy_id: "st1", case_id: "c1", created_at: daysAgo(2), suggestions_json: JSON.stringify([
        { title: "诉讼时效核查", detail: "逐笔核对借款发生日与催收记录，确认未过三年时效（演示建议）" },
        { title: "财产保全评估", detail: "评估被告名下财产线索，决定是否申请保全（演示建议）" },
        { title: "调解窗口", detail: "开庭前留出调解授权与底线报价（演示建议）" },
      ]) },
    ],
  };
}

// 单事务导入（C2/C5/G6）：台账防重（demo-v1 已在账→跳过）+ 各表"表空才插"。
// 调用方（completeOnboarding）负责 BEGIN/COMMIT 与卫检，任一失败全回滚。
export function importDemoDataOnce(db) {
  if (db.prepare("SELECT version FROM onboarding_demo_ledger WHERE version = ?").get(DEMO_DATASET_VERSION)) {
    return { imported: false, reason: "ledger" };
  }
  const seed = demoSeedRows(currentWeekMonday());
  const isEmpty = (t) => db.prepare(`SELECT COUNT(*) AS n FROM ${t}`).get().n === 0;
  const inserted = {};
  const insertAll = (table, cols, rows) => {
    if (!rows.length || !isEmpty(table)) { inserted[table] = 0; return; }
    const q = db.prepare(`INSERT INTO ${table} (${cols.join(",")}) VALUES (${cols.map(() => "?").join(",")})`);
    for (const r of rows) q.run(...cols.map((c) => r[c] ?? null));
    inserted[table] = rows.length;
  };
  insertAll("demo_cases", ["case_id", "name", "case_no", "case_type", "stage", "client_id", "created_at"], seed.cases);
  insertAll("demo_stage_events", ["case_id", "stage", "summary", "happened_at"], seed.stageEvents);
  insertAll("demo_clients", ["client_id", "name", "kind", "contact", "created_at"], seed.clients);
  insertAll("demo_documents", ["doc_id", "case_id", "title", "kind", "status", "created_at"], seed.documents);
  insertAll("demo_schedule_events", ["event_id", "case_id", "title", "kind", "due_at", "created_at"], seed.schedule.map((s) => ({ ...s, created_at: Date.now() })));
  insertAll("demo_tasks", ["task_id", "case_id", "title", "source", "done", "created_at"], [...seed.globalTasks, ...seed.caseTasks]);
  insertAll("demo_parties", ["case_id", "name", "role", "client_id"], seed.parties);
  insertAll("demo_evidence", ["evidence_id", "case_id", "title", "tag"], seed.evidence);
  insertAll("demo_strategies", ["strategy_id", "case_id", "suggestions_json", "created_at"], seed.strategies);
  db.prepare("INSERT INTO onboarding_demo_ledger (version) VALUES (?)").run(DEMO_DATASET_VERSION);
  return { imported: true, inserted };
}

// ---------- 完成（B7/C6/D10/G3/G6）----------
// 强布尔语义：demo/startGuide 仅 ===true 为真；已 completed 再调=幂等返回现状（不重导）。
export function completeOnboarding(db, params) {
  const demo = params?.demo === true;
  const startGuide = params?.startGuide === true;
  const current = getOnboardingState(db);
  if (current.status === "completed") return current;
  db.exec("BEGIN IMMEDIATE");
  try {
    if (demo) {
      assertDemoImportable(db); // 卫检失败→抛错→回滚：三键不落盘（B7/对拍 13）
      importDemoDataOnce(db);
    }
    metaSet(db, "onboarding.demoChoice", demo ? "demo" : "blank");
    metaSet(db, "onboarding.guideStatus", startGuide ? "pending" : "skipped");
    metaSet(db, "onboarding.status", "completed");
    db.exec("COMMIT");
  } catch (e) {
    try { db.exec("ROLLBACK"); } catch { /* 未开事务/已回滚 */ }
    throw e;
  }
  return getOnboardingState(db);
}

// ---------- tour 上报（D5/G4）----------
export function setProductGuideStatus(db, status) {
  if (status !== "pending" && status !== "completed" && status !== "skipped") {
    throw new Error("无效的产品指引状态（仅接受 pending/completed/skipped）");
  }
  metaSet(db, "onboarding.guideStatus", status);
  return getOnboardingState(db);
}

// ---------- 法库可用性（F1/F2；#13 法条手册域的本地件检查）----------
// 约定：%APPDATA%/Juscite/bridge/laws/index.json 存在且 {enabled:true} 视为可用；
// 文件缺失=未安装（F1 路径）；读取/解析异常=状态查询本身抛错（F2 fail-closed 路径）。
export const LAWS_INDEX_PATH = join(homedir(), "AppData", "Roaming", "Juscite", "bridge", "laws", "index.json");
export function lawsLibraryStatus() {
  let raw;
  try {
    raw = readFileSync(LAWS_INDEX_PATH, "utf-8");
  } catch (e) {
    if (e && e.code === "ENOENT") return { available: false, reason: "not_installed" };
    throw e; // 权限等读取异常 → 上抛（F2）
  }
  let parsed;
  try {
    parsed = JSON.parse(raw);
  } catch {
    throw new Error("法规库索引损坏（JSON 解析失败）"); // F2
  }
  if (parsed && parsed.enabled === true) return { available: true };
  return { available: false, reason: "disabled" };
}

// ---------- 检索法规意图判别（F1；确定性正则组合，禁模型猜）----------
export function isLawsRetrievalIntent(text) {
  const t = typeof text === "string" ? text.trim() : "";
  if (!t) return false;
  const verb = /(检索|查找|查一下|查询|搜一搜|搜索|找一下|查查)/.test(t);
  const object = /(法条|法规|法律条文|法律依据|司法解释|相关规定|条文)/.test(t);
  return verb && object;
}

// F1/F2 指路文案（自写；语义=不执行检索+说明原因+指路；不含任何竞品表达）
export const LAWS_GUIDANCE = {
  unavailable: "未执行法规检索：本地法规库尚未安装或未启用。为避免凭空给出法条，这条消息没有发送给模型。请先安装并启用本地法规库，再重新发起检索。",
  error: "已停止本次法规检索：无法确认本地法规库的可用性（状态检查出错）。为避免误引法规，这条消息没有发送给模型；请检查法规库的安装状态后重试。",
};

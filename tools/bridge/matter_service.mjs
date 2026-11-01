// 【步骤4·案件族底座】MatterLite —— 桥内轻量案件表的枚举单源/强校验/行形状映射。
// 唯一依据：juscite/docs/RE规格库/RE-3-案件看板.md 实现规格节（§3.2 数据模型/§3.3 状态机/§3.6 确定性纪律）。
// ⚠ 过渡态：case_board_cases/todos/events 三表只是看板数据的临时真源——决策台账 2026-10-27
// 03:35：MatterStore 解挂后翻牌真源、本轻量表退役（迁移 0005_case_board 同注）。
// 桥面纪律（§3.4）：只做机械 CRUD+强校验；状态推断/提醒引擎/排序桶全为 UI 侧纯函数，桥不预做；
// 确定性纪律（§3.6）：日期 YYYY-MM-DD 后端强校验、金额整型分禁浮点、状态值 11 档白名单。

// 11 档状态单源（§3.2：字段值固定字符串；推断器与色表同表驱动——UI 侧按此口径取值）
export const MATTER_STATUS_DEFS = [
  "接案", "立案中", "仲裁中", "待开庭", "审理中", "已调解", "上诉期", "二审中", "再审中", "执行中", "已结案",
];
export const MATTER_COURT_TYPES = ["法院", "仲裁委"];

const DATE_RE = /^\d{4}-\d{2}-\d{2}$/;
// 格式+真日历日双校验（2 月 30 日/第 13 月拒）
export function isCalendarDate(v) {
  if (typeof v !== "string" || !DATE_RE.test(v)) return false;
  const [y, m, d] = v.split("-").map(Number);
  const dt = new Date(y, m - 1, d);
  return dt.getFullYear() === y && dt.getMonth() === m - 1 && dt.getDate() === d;
}
export function requiredDate(v, label) {
  if (!isCalendarDate(v)) throw new Error(`${label}须为 YYYY-MM-DD 日历日（实收 ${JSON.stringify(v ?? null)}）`);
  return v;
}
export function optionalDate(v, label) {
  if (v === undefined || v === null || v === "") return null;
  return requiredDate(v, label);
}
function trimStr(v) { return typeof v === "string" ? v.trim() : ""; }
export function optionalNote(v) {
  if (v === undefined || v === null) return null;
  if (typeof v !== "string") throw new Error("备注须为字符串");
  return v;
}

// 案件字段规范化：create 全量（requireName 必填 name）；update 只收参数里出现的键。
// 产出 store 列名形状（snake），值全部过白名单校验后才落库。
export function normalizeCaseFields(p, { requireName }) {
  const cols = {};
  if ("name" in p || requireName) {
    const name = trimStr(p.name);
    if (!name) throw new Error("案件名不能为空");
    cols.name = name;
  }
  // 协议参数 camel、列名 snake：caseNo→case_no（cause/court 同形）
  for (const [key, col] of [["cause", "cause"], ["caseNo", "case_no"], ["court", "court"]]) {
    if (key in p) cols[col] = trimStr(p[key]);
  }
  if ("courtType" in p) {
    if (!MATTER_COURT_TYPES.includes(p.courtType)) {
      throw new Error(`法院类型须为「${MATTER_COURT_TYPES.join("」或「")}」（实收 ${JSON.stringify(p.courtType ?? null)}）`);
    }
    cols.court_type = p.courtType;
  }
  if ("claimAmountCents" in p) {
    const v = p.claimAmountCents;
    // 金额整型分（§3.6）：浮点/负数/非整数一律拒
    if (!Number.isInteger(v) || v < 0) throw new Error("诉讼金额须为非负整数（整型分，禁浮点）");
    cols.claim_amount_cents = v;
  }
  for (const [key, col] of [["plaintiffs", "plaintiffs_json"], ["defendants", "defendants_json"], ["judges", "judges_json"]]) {
    if (key in p) {
      const arr = p[key];
      if (!Array.isArray(arr) || arr.some((x) => typeof x !== "string" || !x.trim())) {
        throw new Error(`${key} 须为非空字符串数组`);
      }
      cols[col] = JSON.stringify(arr.map((x) => x.trim()));
    }
  }
  return cols;
}

// 覆盖层合并（§3.4-3）：overrides.calendar_events[sourceKey] 只并四字段增量（date/title/note/hidden）。
// 原值不在本表（来自 #4 时间线与 #6 抽取产物），天然不可被覆盖（对拍行 25/89 覆盖层纪律）。
export function mergeCalendarOverride(overrides, sourceKey, patch) {
  if (typeof sourceKey !== "string" || !sourceKey.trim()) throw new Error("sourceKey 不能为空");
  if (!patch || typeof patch !== "object" || Array.isArray(patch)) throw new Error("覆盖补丁须为对象");
  const FIELDS = ["date", "title", "note", "hidden"];
  const bad = Object.keys(patch).filter((k) => !FIELDS.includes(k));
  if (bad.length) throw new Error(`覆盖字段超出白名单：${bad.join(",")}`);
  if ("date" in patch) requiredDate(patch.date, "覆盖日期");
  if ("title" in patch) {
    if (typeof patch.title !== "string") throw new Error("覆盖标题须为字符串");
    if (patch.hidden !== true && !patch.title.trim()) throw new Error("非隐藏覆盖的标题不能为空");
  }
  if ("hidden" in patch && typeof patch.hidden !== "boolean") throw new Error("hidden 须为布尔");
  if ("note" in patch && patch.note !== null && typeof patch.note !== "string") throw new Error("覆盖备注须为字符串");
  const calendar = { ...(overrides.calendar_events ?? {}) };
  calendar[sourceKey.trim()] = { ...(calendar[sourceKey.trim()] ?? {}) };
  for (const k of FIELDS) if (k in patch) calendar[sourceKey.trim()][k] = patch[k];
  return { ...overrides, calendar_events: calendar };
}

// 读降级口径（对拍行 60：读失败保空渲染）：损坏 JSON 不炸列表、降空值；写路径对损坏 fail-closed。
function jsonArr(s) {
  try { const v = JSON.parse(s || "[]"); return Array.isArray(v) ? v : []; } catch { return []; }
}
function jsonObj(s) {
  try { const v = JSON.parse(s || "{}"); return v && typeof v === "object" && !Array.isArray(v) ? v : {}; } catch { return {}; }
}
export function caseToProtocol(row) {
  return {
    id: row.id, name: row.name, cause: row.cause, caseNo: row.case_no, court: row.court,
    courtType: row.court_type, claimAmountCents: row.claim_amount_cents,
    plaintiffs: jsonArr(row.plaintiffs_json), defendants: jsonArr(row.defendants_json),
    judges: jsonArr(row.judges_json),
    workflowStatus: row.workflow_status ?? null,
    workflowLocked: row.workflow_locked === 1,
    overrides: jsonObj(row.overrides_json),
    sortOrder: row.sort_order ?? null,
    updatedAt: row.updated_at,
  };
}
export function todoToProtocol(row) {
  return { id: row.id, caseId: row.case_id, title: row.title, done: row.done === 1,
    doneAt: row.done_at ?? null, dueDate: row.due_date ?? null,
    createdAt: row.created_at, updatedAt: row.updated_at };
}
// ── 【步骤4·#3 看板日历面】日程 kind 词表/开火常量/字段校验（RE-3 §3.4-5 + 对拍行 80/81/83）──
// kind 自定词表（对拍行 81：kind 分类徽章，值层面单源；展示词 UI 侧自写）
export const BOARD_KINDS = ["hearing", "deadline", "schedule"];
export const BOARD_DEFAULT_KIND = "schedule";
// §3.4-5：date-only 行归一开火时刻=当日 09:00（桥常量；宿主可经 BRIDGE_BOARD_DAY_FIRE_TIME 覆盖）
export const BOARD_DAY_FIRE_TIME = "09:00";
// 对拍行 80/85：提前提醒分钟默认 30
export const BOARD_DEFAULT_LEAD_MINUTES = 30;
const BOARD_TIME_RE = /^([01]\d|2[0-3]):[0-5]\d$/;
export function isBoardTime(v) {
  return typeof v === "string" && BOARD_TIME_RE.test(v);
}

// 日程字段规范化：add 全量（requireTitle 必填 title）；update 只收参数里出现的键。
// 产出 store 列名形状（snake）；值全过校验后才落库（§3.6 确定性纪律）。
export function normalizeEventFields(p, { requireTitle }) {
  const cols = {};
  if ("title" in p || requireTitle) {
    const t = trimStr(p.title);
    if (!t) throw new Error("日程标题不能为空（标题必填，空拒）");
    cols.title = t;
  }
  if ("date" in p) cols.date = requiredDate(p.date, "日程日期");
  if ("kind" in p) {
    if (!BOARD_KINDS.includes(p.kind)) {
      throw new Error(`日程分类须为 ${BOARD_KINDS.join("/")} 之一（实收 ${JSON.stringify(p.kind ?? null)}）`);
    }
    cols.kind = p.kind;
  }
  for (const [key, col, label] of [["location", "location", "地点"], ["trip", "trip", "出行安排"]]) {
    if (key in p) {
      if (p[key] !== undefined && p[key] !== null && typeof p[key] !== "string") {
        throw new Error(`${label}须为字符串`);
      }
      cols[col] = typeof p[key] === "string" ? p[key].trim() : "";
    }
  }
  for (const [key, col, label] of [["startAt", "start_at", "开始时刻"], ["endAt", "end_at", "结束时刻"]]) {
    if (key in p) {
      if (p[key] === undefined || p[key] === null || p[key] === "") { cols[col] = null; continue; }
      if (!isBoardTime(p[key])) {
        throw new Error(`${label}须为 HH:MM 24 小时制（实收 ${JSON.stringify(p[key])}）`);
      }
      cols[col] = p[key];
    }
  }
  if ("caseId" in p) {
    const v = p.caseId;
    if (v === undefined || v === null || v === "") cols.case_id = null;
    else if (typeof v !== "string" || !v.trim()) throw new Error("关联案件 id 须为非空字符串或 null");
    else cols.case_id = v.trim();
  }
  if ("remind" in p) {
    if (typeof p.remind !== "boolean") throw new Error("提醒开关须为布尔");
    cols.remind = p.remind ? 1 : 0;
  }
  if ("remindMinutes" in p) {
    const v = p.remindMinutes;
    if (!Number.isInteger(v) || v < 0) throw new Error("提前提醒分钟须为非负整数（禁浮点/负数）");
    cols.remind_minutes = v;
  }
  if ("note" in p) cols.note = optionalNote(p.note);
  return cols;
}

export function eventToProtocol(row) {
  return {
    id: row.id, date: row.date, title: row.title, note: row.note ?? null,
    caseId: row.case_id ?? null, kind: row.kind ?? BOARD_DEFAULT_KIND,
    location: row.location ?? "", startAt: row.start_at ?? null, endAt: row.end_at ?? null,
    trip: row.trip ?? null, remind: row.remind === 1,
    remindMinutes: row.remind_minutes ?? BOARD_DEFAULT_LEAD_MINUTES,
    createdAt: row.created_at,
  };
}

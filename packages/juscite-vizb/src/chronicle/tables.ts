// 大事记封闭表族（契约一「封闭表机制」：凡分类皆封闭表＋表外拒绝＋由律师补表，模型不造词）。
// 条目内容=我方自写资产（依中国民事程序通行事实动作自拟，表达隔离不抄源仓）；机制=封闭表+表外拒绝。
// 补表流程：表外动词被拒时，错误信息指明「由律师确认后补入本表并记 changelog」，绝不静默放行。

/** 事项动词封闭表（事实动作，中性不含定性）。补表须律师确认＋在文末 CHANGELOG 记一行。 */
export const CHRONICLE_VERBS: ReadonlySet<string> = new Set([
  // 合同与物权类事实动作
  "签订", "成立", "设立", "变更", "补充", "转让", "受让", "交付", "收货", "验收",
  "付款", "收款", "转账", "出借", "归还", "结算", "对账", "催告", "通知", "送达",
  "签发", "盖章", "签字", "抵押", "质押", "保证", "解押", "登记", "备案", "注销",
  // 事实状态类
  "开工", "停工", "竣工", "入住", "腾退", "占有", "租赁", "交付使用", "受损", "灭失",
  // 程序类
  "委托", "报案", "受理", "开庭", "休庭", "调解", "撤诉", "判决", "裁定", "上诉",
  "申请执行", "执行", "和解", "结案",
]);

/** 动词表补表台账（本表初始为空：有真实运行补词时由落账员追加，格式=日期|动词|依据）。 */
export const CHRONICLE_VERB_CHANGELOG: string[] = [];

/**
 * 定性词表（禁入「事项标题」等模型撰写字段；材料原文照录不受此限——原文出现这些词必须照录，
 * 对原文施加此表等于不许照录，故只查模型撰写的字段）。
 */
export const CHRONICLE_BANNED_QUALIFIERS: ReadonlySet<string> = new Set([
  "违约", "违法", "非法", "恶意", "善意", "有效", "无效", "依法", "应当", "擅自",
  "故意", "过失", "重大误解", "欺诈", "胁迫", "显失公平", "过错", "侵权", "胜诉",
  "败诉", "确凿", "无疑", "显然", "必然",
]);

/** 日期四档精度（认不准按最粗档收入不丢，写法与档位必须正则相符）。 */
export const DATE_PRECISIONS = ["day", "month", "year", "span"] as const;
export type DatePrecision = (typeof DATE_PRECISIONS)[number];

export const DATE_PRECISION_LABEL: Record<DatePrecision, string> = {
  day: "确切日", month: "仅至月", year: "仅至年", span: "区间",
};

// 各档写法正则（封闭：档位与写法一一对应，不符即拒，绝不猜测升档）
const RE_DAY = /^\d{4}-(?:0[1-9]|1[0-2])-(?:0[1-9]|[12]\d|3[01])$/;
const RE_MONTH = /^\d{4}-(?:0[1-9]|1[0-2])$/;
const RE_YEAR = /^\d{4}$/;
const RE_SPAN = /^(\d{4})(?:-(\d{2}))?(?:-(\d{2}))?~(\d{4})(?:-(\d{2}))?(?:-(\d{2}))?$/;

/** 真日历校验（2 月闰年、大小月），纯函数。 */
export function daysInMonth(year: number, month: number): number {
  if (month < 1 || month > 12) return 0;
  if (month === 2) return (year % 4 === 0 && year % 100 !== 0) || year % 400 === 0 ? 29 : 28;
  return [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31][month - 1]!;
}

/** 档位与写法双校验：返回 null=通过；否则具名错误。 */
export function checkDateStr(dateStr: string, precision: DatePrecision): string | null {
  if (typeof dateStr !== "string" || !dateStr) return "日期为空";
  if (!DATE_PRECISIONS.includes(precision)) return `未知精度档「${String(precision)}」`;
  if (precision === "day") {
    if (!RE_DAY.test(dateStr)) return `确切日档写法应为 YYYY-MM-DD，实得「${dateStr}」`;
    const [y, m, d] = dateStr.split("-").map(Number) as [number, number, number];
    if (d! > daysInMonth(y!, m!)) return `「${dateStr}」不是真实日历日`;
    return null;
  }
  if (precision === "month") {
    if (!RE_MONTH.test(dateStr)) return `仅至月档写法应为 YYYY-MM，实得「${dateStr}」`;
    return null;
  }
  if (precision === "year") {
    if (!RE_YEAR.test(dateStr)) return `仅至年档写法应为 YYYY，实得「${dateStr}」`;
    return null;
  }
  const m = RE_SPAN.exec(dateStr);
  if (!m) return "区间档写法应为 起日~止日（两侧各为 YYYY[-MM[-DD]]）";
  const [ , y1, mo1, d1, y2, mo2, d2 ] = m;
  const sideErr = (y: string, mo: string | undefined, d: string | undefined, tag: string): string | null => {
    if (mo && !(Number(mo) >= 1 && Number(mo) <= 12)) return `区间${tag}侧月份非法`;
    if (d) {
      const dim = daysInMonth(Number(y), Number(mo ?? "1"));
      if (Number(d) > dim) return `区间${tag}侧日超真实日历`;
    }
    return null;
  };
  return sideErr(y1!, mo1, d1, "起") ?? sideErr(y2!, mo2, d2, "止")
    ?? (sortKeyOfSpan(dateStr).start > sortKeyOfSpan(dateStr).end ? "区间起点晚于终点" : null);
}

/** 区间排序键取起点（两侧缺省补 01；仅用于排序，不回填任何展示字段）。 */
export function sortKeyOfSpan(dateStr: string): { start: string; end: string } {
  const m = RE_SPAN.exec(dateStr);
  if (!m) return { start: "9999-99-99", end: "9999-99-99" };
  const pad = (y: string, mo?: string, d?: string) =>
    `${y}-${(mo ?? "01").padStart(2, "0")}-${(d ?? "01").padStart(2, "0")}`;
  return { start: pad(m[1]!, m[2] ?? undefined, m[3] ?? undefined), end: pad(m[4]!, m[5] ?? undefined, m[6] ?? undefined) };
}

/** 排序键：day/month/year 直接可比（缺省补 01），span 取起点。 */
export function dateSortKey(dateStr: string, precision: DatePrecision): string {
  if (precision === "span") return sortKeyOfSpan(dateStr).start;
  if (precision === "day") return dateStr;
  if (precision === "month") return `${dateStr}-01`;
  return `${dateStr}-01-01`;
}

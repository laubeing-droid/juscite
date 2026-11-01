#!/usr/bin/env node
// 【施工单-10 单元四·tabular-review 逐字引文回验】共享 validator 合成自测（RE-12 对照源增补节 T40-T42；
// 规格=docs/RE规格库/RE-12-合同审查基础.md「claude-for-legal tabular-review 逐字引文回验」节）。
// 验收断言（施工单-10 单元四原文口径）：合成语料 20 值（15 逐字相符含全半角标点/空白变体、3 无引文、
// 2 引文不符）→validator 输出恰 15 pass/3 fabricated/2 mismatch；severity 排序 mismatch>unclear 实测成立；
// 无引文值显式 fabricated 旗标零静默丢弃。三消费面（#33/#34/#32）接线回执在各自合成脚本
// （cross_verification_synthetic/fact_verification_synthetic/diligence_synthetic），本件只测共享内核。
// 全合成材料；纯 Node 零依赖零端口零真模型；单命令 exit 0/1，末行 QUOTEBACK_SYNTH_PASS 可判。
// 用法：node tools/bridge/quote_back_synthetic.mjs
import { fileURLToPath } from "node:url";

const qb = await import("../../packages/juscite-flow/src/quote-back.mjs");
const { verifyQuoteBack, checkQuoteBack, normalizeQuoteText, severityRank, QUOTE_BACK_SEVERITY, QUOTE_BACK_VERDICTS } = qb;

let passed = 0, failed = 0;
function ok(n, msg) { passed += 1; console.log(`[quoteback-synth] ${n}: OK ${msg}`); }
function fail(n, msg, detail) { failed += 1; console.error(`[quoteback-synth] ${n}: FAIL ${msg}${detail ? `\n  ${detail}` : ""}`); }
const assert = (n, cond, msg, detail) => (cond ? ok(n, msg) : fail(n, msg, typeof detail === "string" ? detail : JSON.stringify(detail)));

// ── 合成语料 20 值（15 逐字相符 / 3 无引文 / 2 引文不符；全半角标点与空白变体织入 pass 组）──
const CORPUS = [
  // 15 pass：值可在引文中逐字复现（归一空白+全半角标点互认后）
  { id: "v01", value: "5,000 万元", quote: "投资总额人民币 5,000 万元（大写：伍仟万元整）" },
  { id: "v02", value: "2026 年 12 月 15 日", quote: "交割日：2026 年 12 月 15 日" },
  { id: "v03", value: "ZL202310000001.0", quote: "专利号：ZL202310000001.0" },
  { id: "v04", value: "５,０００万元", quote: "投资总额 5,000 万元" },            // 全角数字折半角
  { id: "v05", value: "1,500,000元", quote: "借款本金：１，５００，０００元" },   // 引文侧全角数字+全角逗号
  { id: "v06", value: "普通许可", quote: "许可类型为“普通许可”（非独占）" },      // 中文弯引号折 ASCII
  { id: "v07", value: "60 日", quote: "排他期 60 日（自签署日起算）" },
  { id: "v08", value: "第45类", quote: "商标注册类别：第４５类（合成）" },        // 值半角/引文全角数字
  { id: "v09", value: "1.5 倍投资款", quote: "优先清算：1.5 倍投资款" },
  { id: "v10", value: "沈阳", quote: "出卖人住所地：辽宁省沈阳市和平区（合成）" },
  { id: "v11", value: "30 日内", quote: "交割后 30 日内办理工商变更登记" },
  { id: "v12", value: "民法典", quote: "依据《民法典》第五百六十三条" },          // 书名号折叠不碍子串
  { id: "v13", value: "第 186 条", quote: "《民法典》第 186 条（合成引文）" },
  { id: "v14", value: "账户状态：销户", quote: "账户状态:销户" },                 // 值全角冒号/引文半角冒号
  { id: "v15", value: "9000001", quote: "注册号第 9000001 号" },
  // 3 fabricated：无引文之值=按编造处理（null / 空串 / 纯空白引文三形态）
  { id: "v16", value: "注册资本 9,999 万元", quote: null },
  { id: "v17", value: "专利权人：合成公司丙", quote: "" },
  { id: "v18", value: "交割日 2027 年 1 月 1 日", quote: "   " },
  // 2 mismatch：有引文但引文不支持该值（数值/类别不符——伪造证据链）
  { id: "v19", value: "登记日为 2023 年 6 月 1 日", quote: "登记日 2023 年 6 月 15 日" },
  { id: "v20", value: "注册商标第 44 类", quote: "第 45 类" },
];

// T40：20 值语料 → 恰 15 pass / 3 fabricated / 2 mismatch
const report = verifyQuoteBack(CORPUS);
assert("T40", report.total === 20
  && report.counts.pass === 15 && report.counts.fabricated === 3 && report.counts.mismatch === 2,
  "合成 20 值语料过共享 validator：恰 15 pass / 3 fabricated / 2 mismatch（含全半角标点与空白变体不改判）",
  JSON.stringify(report.counts));

// T41：无引文值显式 fabricated 旗标 + 零静默丢弃（结果集与输入逐条对应）
const fabricatedIds = report.results.filter((r) => r.verdict === "fabricated").map((r) => r.id);
const mismatchIds = report.results.filter((r) => r.verdict === "mismatch").map((r) => r.id);
assert("T41", report.results.length === CORPUS.length
  && JSON.stringify(fabricatedIds) === JSON.stringify(["v16", "v17", "v18"])
  && JSON.stringify(mismatchIds) === JSON.stringify(["v19", "v20"])
  && report.results.filter((r) => r.verdict === "fabricated").every((r) => typeof r.reason === "string" && r.reason.length > 0),
  "编造旗标零丢弃：结果 20/20 逐条对应；v16-v18 显式 fabricated（含纯空白引文形态）各带理由文本；v19/v20 mismatch",
  JSON.stringify({ fabricatedIds, mismatchIds }));

// T42：severity 排序——mismatch>unclear、fabricated>unclear 实测成立；全序 pass<unclear<mismatch<fabricated
assert("T42", severityRank("mismatch") > severityRank("unclear") && severityRank("fabricated") > severityRank("unclear")
  && QUOTE_BACK_SEVERITY.pass < QUOTE_BACK_SEVERITY.unclear
  && QUOTE_BACK_SEVERITY.unclear < QUOTE_BACK_SEVERITY.mismatch
  && QUOTE_BACK_SEVERITY.mismatch < QUOTE_BACK_SEVERITY.fabricated,
  "严重度全序实测：pass(0)<unclear(1)<mismatch(2)<fabricated(3)——已答错与已答无据均压过如实未答",
  JSON.stringify(QUOTE_BACK_SEVERITY));

// 判定值域恰三值 + 未知档 fail-fast
const badRank = (() => { try { severityRank("nope"); return false; } catch { return true; } })();
assert("4", JSON.stringify(QUOTE_BACK_VERDICTS) === JSON.stringify(["pass", "mismatch", "fabricated"]) && badRank,
  "判定值域闭集 {pass,mismatch,fabricated}；未知严重度档具名抛错（fail-fast 不猜测）");

// 归一化单元针：全角 ASCII 折半角、中文标点折算、空白剔除（含全角空格）
assert("5",
  normalizeQuoteText("５,０００ 万元（大写）") === "5,000万元(大写)"
  && normalizeQuoteText("账户状态：销户　") === "账户状态:销户"
  && normalizeQuoteText("“普通许可”") === "\"普通许可\""
  && normalizeQuoteText("《民法典》第 186 条") === "<民法典>第186条",
  "归一化四针：全角数字/冒号折半角、全角空格与 ASCII 空白剔除、弯引号/书名号折算",
  JSON.stringify([normalizeQuoteText("５,０００ 万元（大写）"), normalizeQuoteText("账户状态：销户　")]));

// 确定性：同输入两跑输出字节级一致
const again = verifyQuoteBack(CORPUS);
assert("6", JSON.stringify(again) === JSON.stringify(report), "确定性：同语料两跑 JSON 字节级一致（零随机零时钟入判定面）");

// 单值边界：空值由消费面先剔除——validator 对空值 fail-fast（外边界防御，不猜）
const emptyValue = (() => { try { checkQuoteBack({ value: "", quote: "x" }); return false; } catch { return true; } })();
assert("7", emptyValue, "单值边界：空 value 具名抛错（空值不入回验分母=消费面适配器职责，内核不吞）");

// 收尾
console.log(`[quoteback-synth] ── ${passed} OK / ${failed} FAIL ──`);
if (failed > 0) { console.error("QUOTEBACK_SYNTH_FAIL"); process.exit(1); }
console.log("QUOTEBACK_SYNTH_PASS");

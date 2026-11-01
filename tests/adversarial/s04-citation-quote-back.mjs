#!/usr/bin/env node
// S04 合成材料：引文回验。一字改写应失败，全半角标点互换应通过，拼接片段应失败，空引文不得判已核验。
let qb;
try {
  qb = await import("../../packages/juscite-flow/src/quote-back.mjs");
} catch (error) {
  console.error("[S04] IMPORT", error?.code ?? "", String(error?.message ?? error).split("\n")[0]);
  console.log("RESULT crash");
  process.exit(1);
}

const { checkQuoteBack } = qb;
let failed = 0;
function check(name, cond, detail = "") {
  if (cond) console.log(`[S04] OK ${name}`);
  else {
    failed += 1;
    console.error(`[S04] FAIL ${name}${detail ? " — " + detail : ""}`);
  }
}

const altered = checkQuoteBack({ value: "合成金额1000元", quote: "合成金额1001元" });
check("one-char altered is mismatch", altered.verdict === "mismatch", JSON.stringify(altered));

const folded = checkQuoteBack({ value: "状态：有效", quote: "状态:有效" });
check("fullwidth/halfwidth punctuation verifies", folded.verdict === "pass", JSON.stringify(folded));

const spliced = checkQuoteBack({ value: "甲公司签署", quote: "甲公司于北京签署合同，乙方确认" });
check("spliced fragments mismatch", spliced.verdict === "mismatch", JSON.stringify(spliced));

const empty = checkQuoteBack({ value: "合成主张", quote: "" });
check("empty quote is not verified", empty.verdict === "fabricated" && empty.verdict !== "pass", JSON.stringify(empty));

const blank = checkQuoteBack({ value: "合成主张", quote: " \u3000\n\t" });
check("whitespace quote is not verified", blank.verdict === "fabricated", JSON.stringify(blank));

const emptyValue = checkQuoteBack({ value: "   ", quote: "引文里有合成句子" });
check("whitespace-only value is not verified", emptyValue.verdict !== "pass", JSON.stringify(emptyValue));

const intact = checkQuoteBack({ value: "普通许可", quote: "许可类型为“普通许可”（非独占）" });
check("contiguous quote still verifies", intact.verdict === "pass", JSON.stringify(intact));

if (failed) {
  console.log("RESULT fail");
  process.exit(1);
}
console.log("RESULT pass");

#!/usr/bin/env node
// 知识库截断同步：只删除本批扫到的前缀里、盘上已不在的索引行。
// 晚于 cutoff 的账本行这次没被看到，必须保留。纯函数，不碰磁盘。
import { kbIndexRemovals } from "./kb_service.mjs";

let failed = 0;
function check(name, actual, expected) {
  const ok = JSON.stringify(actual) === JSON.stringify(expected);
  if (ok) console.log(`[kb-index-removal] OK ${name}`);
  else {
    failed += 1;
    console.error(`[kb-index-removal] FAIL ${name}`, JSON.stringify({ actual, expected }));
  }
}

const known = ["a.txt", "m.txt", "z.txt"];
check(
  "全量扫描删除未见行",
  kbIndexRemovals(known, new Set(["a.txt"]), { truncated: false }),
  ["m.txt", "z.txt"],
);
check(
  "截断时不删除晚于 cutoff 的行",
  kbIndexRemovals(known, new Set(["a.txt"]), { truncated: true, cutoff: "a.txt" }),
  [],
);
check(
  "截断时仍删除 cutoff 以内、盘上已无的行",
  kbIndexRemovals(known, new Set(["m.txt"]), { truncated: true, cutoff: "m.txt" }),
  ["a.txt"],
);
check(
  "已见到的 cutoff 行本身不删",
  kbIndexRemovals(known, new Set(["a.txt", "m.txt"]), { truncated: true, cutoff: "m.txt" }),
  [],
);

if (failed > 0) {
  console.error(`[kb-index-removal] FAIL ${failed}`);
  process.exit(1);
}
console.log("[kb-index-removal] 4 项全过");
console.log("KB_INDEX_REMOVAL_SYNTH_PASS");

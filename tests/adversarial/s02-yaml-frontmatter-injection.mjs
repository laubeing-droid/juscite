#!/usr/bin/env node
// S02 合成材料：YAML frontmatter 注入。锚点、多文档分隔、类型标签、嵌套键必须按契约拒绝或标量化。
import {
  ConfigWriteError,
  buildFrontmatterBlock,
  readFrontmatterScalars,
  roundTripCheckFrontmatter,
  writeFrontmatterChecked,
} from "../../packages/juscite-legal/src/kernel/configWriteModel.ts";

let failed = 0;
function check(name, cond, detail = "") {
  if (cond) console.log(`[S02] OK ${name}`);
  else {
    failed += 1;
    console.error(`[S02] FAIL ${name}${detail ? " — " + detail : ""}`);
  }
}
function codeOf(fn) {
  try {
    fn();
    return null;
  } catch (error) {
    return error instanceof ConfigWriteError ? error.code : `throw:${error?.message ?? error}`;
  }
}

const attacks = [
  { name: "anchor", value: "前情 &a 锚点 *a 别名" },
  { name: "multi-doc", value: "---\n!!python/execute {cmd: 'id'}\n---" },
  { name: "type-tag", value: "!!python/execute os.system" },
  { name: "nested-looking", value: "a.b.c: !!python/execute\n&a *a" },
];

for (const { name, value } of attacks) {
  const text = writeFrontmatterChecked(
    [
      { key: "name", value: "synth-skill" },
      { key: "description", value },
    ],
    ["name", "description"],
  );
  const own = readFrontmatterScalars(text);
  const lines = text.split("\n");
  const bareStructure = lines.some((line, index) => index > 0 && index < lines.length - 1 && /^(---|!!|&|\*)/.test(line.trim()));
  check(
    `sanitize ${name}`,
    own?.description === value && own?.name === "synth-skill" && !bareStructure && !text.includes("\n---\n"),
    JSON.stringify({ keys: own && Object.keys(own), bareStructure, text }),
  );
}

check("reject nested key a.b.c", codeOf(() => buildFrontmatterBlock([{ key: "a.b.c", value: "x" }])) === "cfgwrite_key_invalid");
check("reject anchor key", codeOf(() => buildFrontmatterBlock([{ key: "&a", value: "*a" }])) === "cfgwrite_key_invalid");

const good = writeFrontmatterChecked([{ key: "name", value: "synth" }], ["name"]);
const secondDoc = `${good}\n---\n!!python/execute {cmd: "id"}\n`;
check(
  "reject appended multi-doc",
  codeOf(() => roundTripCheckFrontmatter(secondDoc, ["name"])) === "cfgwrite_roundtrip_shape",
  codeOf(() => roundTripCheckFrontmatter(secondDoc, ["name"])) ?? "accepted",
);

if (failed) {
  console.log("RESULT fail");
  process.exit(1);
}
console.log("RESULT pass");

#!/usr/bin/env node
// S07 合成材料：读许可文件的同时把内容覆写成损坏字节，必须失败关闭，不得出现开放允许。
import { spawn } from "node:child_process";
import { mkdtempSync, writeFileSync, readFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { LICENSE_MODULE_IDS, readLicenseShape } from "../../tools/bridge/license_shape.mjs";

const dir = mkdtempSync(join(tmpdir(), "r3-s07-"));
const path = join(dir, "license.json");
const valid = {
  schema: "juscite-license/1",
  licenseId: "synth-h2",
  issuedAt: "2020-01-01T00:00:00.000Z",
  modules: { H2: true },
};
writeFileSync(path, JSON.stringify(valid), "utf8");

let failed = 0;
function check(name, cond, detail = "") {
  if (cond) console.log(`[S07] OK ${name}`);
  else {
    failed += 1;
    console.error(`[S07] FAIL ${name}${detail ? " — " + detail : ""}`);
  }
}

function allClosed(shape) {
  return LICENSE_MODULE_IDS.every((id) => shape.modules[id] === false);
}
function onlyH2(shape) {
  return shape.state === "valid"
    && shape.licenseId === "synth-h2"
    && shape.modules.H2 === true
    && LICENSE_MODULE_IDS.every((id) => (id === "H2" ? shape.modules[id] === true : shape.modules[id] === false));
}

const staticCorrupt = [
  "{CORRUPT",
  "",
  "null",
  JSON.stringify({ schema: "juscite-license/1", licenseId: "x", issuedAt: "2020-01-01T00:00:00.000Z", modules: { H1: "yes" } }),
  JSON.stringify({ modules: Object.fromEntries(LICENSE_MODULE_IDS.map((id) => [id, true])) }),
];
for (const [index, raw] of staticCorrupt.entries()) {
  writeFileSync(path, raw, "utf8");
  let shape;
  try {
    shape = readLicenseShape({ path, now: new Date("2026-06-01T00:00:00.000Z") });
  } catch (error) {
    check(`static ${index} no throw`, false, String(error));
    continue;
  }
  check(`static ${index} fail-closed`, shape.state === "base" && shape.tier === "base" && allClosed(shape), JSON.stringify(shape));
}

writeFileSync(path, JSON.stringify(valid), "utf8");
const child = spawn(process.execPath, ["-e", `
  const fs = require("node:fs");
  const p = process.env.LICENSE_PATH;
  const valid = process.env.LICENSE_VALID;
  const corrupt = "NOT-JSON{{{{";
  for (let i = 0; i < 400; i++) fs.writeFileSync(p, i % 2 === 0 ? corrupt + i : valid);
  fs.writeFileSync(p, corrupt);
`], { env: { ...process.env, LICENSE_PATH: path, LICENSE_VALID: JSON.stringify(valid) } });

const observed = [];
const deadline = Date.now() + 1500;
while (Date.now() < deadline) {
  try {
    observed.push(readLicenseShape({ path, now: new Date("2026-06-01T00:00:00.000Z") }));
  } catch (error) {
    observed.push({ threw: String(error) });
  }
}
await new Promise((resolve) => child.on("exit", resolve));
const finalShape = readLicenseShape({ path, now: new Date("2026-06-01T00:00:00.000Z") });
const threw = observed.filter((s) => s.threw);
const opened = observed.filter((s) => !s.threw && !allClosed(s) && !onlyH2(s));
check("race never throws", threw.length === 0, JSON.stringify(threw.slice(0, 2)));
check("race never open-allow", opened.length === 0, JSON.stringify(opened.slice(0, 2)));
check("final corrupt is fail-closed", finalShape.state === "base" && allClosed(finalShape), JSON.stringify(finalShape));
check("samples taken", observed.length > 10, String(observed.length));
void readFileSync;

if (failed) {
  console.log("RESULT fail");
  process.exit(1);
}
console.log("RESULT pass");

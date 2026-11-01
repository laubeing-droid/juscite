#!/usr/bin/env node
// S09 合成材料：版本族 stem::ext。中文名、尾随空白、多点扩展名 .tar.gz、纯数字扩展名必须折到同一族键。
import { dedupeVersionFamily, deliveryFamilyKey } from "../../packages/juscite-legal/src/kernel/deliveryChainModel.ts";

let failed = 0;
function check(name, cond, detail = "") {
  if (cond) console.log(`[S09] OK ${name}`);
  else {
    failed += 1;
    console.error(`[S09] FAIL ${name}${detail ? " — " + detail : ""}`);
  }
}

const zh = deliveryFamilyKey("证据目录.docx");
check("chinese stem", zh === "证据目录::docx" && deliveryFamilyKey("证据目录v2.docx") === zh, JSON.stringify([zh, deliveryFamilyKey("证据目录v2.docx")]));
check("trailing space folds", deliveryFamilyKey("证据目录.docx ") === zh, JSON.stringify(deliveryFamilyKey("证据目录.docx ")));
check("fullwidth trailing space folds", deliveryFamilyKey("证据目录终稿.docx\u3000") === zh, JSON.stringify(deliveryFamilyKey("证据目录终稿.docx\u3000")));

const tar = deliveryFamilyKey("合成备份.tar.gz");
check("tar.gz compound ext", tar === "合成备份::tar.gz", JSON.stringify(tar));
check("tar.gz version folds", deliveryFamilyKey("合成备份v2.tar.gz") === tar, JSON.stringify(deliveryFamilyKey("合成备份v2.tar.gz")));
check("tar.gz not confused with gz-only", deliveryFamilyKey("合成备份.gz") !== tar);

const num = deliveryFamilyKey("清单.12");
check("numeric extension kept", num === "清单::12", JSON.stringify(num));
check("numeric extension version folds", deliveryFamilyKey("清单v2.12") === num, JSON.stringify(deliveryFamilyKey("清单v2.12")));
check("different numeric extensions stay apart", deliveryFamilyKey("清单.13") !== num);

const folded = dedupeVersionFamily([
  { filename: "合成备份.tar.gz", producer: "agent" },
  { filename: "合成备份v2.tar.gz", producer: "agent" },
  { filename: "证据目录.docx ", producer: "agent" },
  { filename: "证据目录v2.docx", producer: "agent" },
  { filename: "清单.12", producer: "agent" },
  { filename: "清单v2.12", producer: "agent" },
]);
check(
  "dedupe keeps one per family",
  folded.map((item) => item.filename).join("|") === "合成备份v2.tar.gz|证据目录v2.docx|清单v2.12",
  folded.map((item) => item.filename).join("|"),
);

if (failed) {
  console.log("RESULT fail");
  process.exit(1);
}
console.log("RESULT pass");

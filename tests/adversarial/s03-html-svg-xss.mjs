#!/usr/bin/env node
// S03 合成材料：safeHtmlDocument 不得发出可执行 XSS。
// 覆盖 noscript/title 截断、SVG/MathML 命名空间混淆、data:text/javascript。
import { cspMeta, safeHtmlDocument } from "../../packages/juscite-vizb/src/shared/html.ts";

const NONCE = "AAAAAAAAAAAAAAAAAAAAAAAAAAA=";
const csp = cspMeta({ nonce: NONCE });

const body = [
  "<noscript><p title=\"</noscript><img src=x onerror=alert(1)>\">",
  "<title></title><script>alert(2)</script>",
  "<svg xmlns=\"http://www.w3.org/2000/svg\"><script href=\"data:text/javascript,alert(3)\"></script></svg>",
  "<math><mi><img src=x onerror=alert(4)></mi></math>",
  "<a href=\"data:text/javascript,alert(5)\">合成链接</a>",
  "<a href='javascript:alert(6)'>合成链接</a>",
  "<iframe src=\"data:text/javascript,alert(7)\"></iframe>",
  "<p>合成正文保持可见</p>",
].join("");

let failed = 0;
function check(name, cond, detail = "") {
  if (cond) console.log(`[S03] OK ${name}`);
  else {
    failed += 1;
    console.error(`[S03] FAIL ${name}${detail ? " — " + detail.slice(0, 400) : ""}`);
  }
}

let doc = "";
try {
  doc = safeHtmlDocument({
    title: "</title><script>alert(8)</script>",
    csp,
    body,
    style: "p{color:red}</style><script>alert(9)</script>",
    script: { nonce: NONCE, js: "var x=1;</script><script>alert(10)</script>" },
  });
} catch (error) {
  console.error("[S03] FAIL throw", error?.message ?? error);
  console.log("RESULT crash");
  process.exit(1);
}

const withoutTrustedScripts = doc
  .replace(/<script\s+nonce="[^"]*">[\s\S]*?<\/script>/gi, "")
  .replace(/<script\s+type="application\/json"[\s\S]*?<\/script>/gi, "");

check("title breakout escaped", !doc.includes("<script>alert(8)</script>") && doc.includes("&lt;"));
check("no payload script tags", !/<script\b/i.test(withoutTrustedScripts), withoutTrustedScripts);
check("no event handlers", !/\son[a-z0-9:-]+\s*=/i.test(doc), doc);
check("no javascript url", !/javascript\s*:/i.test(doc));
check("no data text javascript url", !/data\s*:\s*text\/javascript/i.test(doc));
check("no noscript", !/<noscript\b/i.test(doc));
check("no svg/math", !/<(svg|math)\b/i.test(doc));
check("static paragraph kept", doc.includes("合成正文保持可见"));
check("template still has nonce script", doc.includes(`nonce="${NONCE}"`) && doc.includes("var x=1;"));
check("style breakout not a script", !doc.includes("<script>alert(9)</script>"));
check("script breakout not a second script", !doc.includes("<script>alert(10)</script>"));

if (failed) {
  console.log("RESULT fail");
  process.exit(1);
}
console.log("RESULT pass");

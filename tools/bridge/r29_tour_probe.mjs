// R29 引擎验收探针（RE-29 §3 技术选型验收）：锁版 driver.js@1.10.2（node_modules，npm nilbuild 发布线）
// 在合成页上复跑规格同款 12 项引擎行为。独立无头 Chrome 临时 profile（不碰用户浏览器，用完即删）。
// 运行：node tools/bridge/r29_tour_probe.mjs；末行 SUMMARY n/12 PASS，EXIT 0/1。
import { createRequire } from "node:module";
import { pathToFileURL, fileURLToPath } from "node:url";
import fs from "node:fs";
import path from "node:path";
import os from "node:os";

const require = createRequire(import.meta.url);
const playwright = require("playwright-core");

const here = path.dirname(fileURLToPath(import.meta.url));
const pageUrl = pathToFileURL(path.join(here, "r29_probe_page.html")).href;
const OUT = process.env.R29_PROBE_OUT ?? path.join(here, "..", "..", "evidence");
const shots = path.join(OUT, "步骤4-新手引导-RE29-20261027", "engine-probe-shots");
fs.mkdirSync(shots, { recursive: true });

const R = {};
const ok = (t, c, obs) => { R[t] = { pass: !!c, obs }; console.log((c ? "PASS" : "FAIL") + " | " + t + " | " + JSON.stringify(obs)); };

const prof = fs.mkdtempSync(path.join(os.tmpdir(), "r29-prof-"));
const ctx = await playwright.chromium.launchPersistentContext(prof, { channel: "chrome", headless: true });
try {
  const page = ctx.pages()[0] || await ctx.newPage();
  await page.setViewportSize({ width: 1100, height: 760 });
  await page.goto(pageUrl);

  // T1 启动态：body 活动类+遮罩+popover+自定义皮肤类+首步进度 1/6+下一步钮
  await page.evaluate(() => { window.__d = window.makeTour(); window.__d.drive(); });
  await page.waitForTimeout(600);
  const t1 = await page.evaluate(() => {
    const $ = (s) => document.querySelector(s);
    const txt = (s) => { const e = $(s); return e ? e.textContent.trim() : null; };
    return {
      bodyActive: document.body.classList.contains("driver-active"),
      overlay: !!$(".driver-overlay"),
      popover: !!$(".driver-popover"),
      skinCls: $(".driver-popover")?.className.includes("juscite-product-tour"),
      title: txt(".driver-popover-title"),
      progress: txt(".driver-popover-progress-text"),
      next: txt(".driver-popover-next-btn"),
    };
  });
  await page.screenshot({ path: path.join(shots, "t1-boot.png") });
  ok("T1 启动态+皮肤+进度1/6", t1.bodyActive && t1.overlay && t1.popover && t1.skinCls
    && t1.progress === "1 / 6" && t1.next === "下一步" && t1.title === "S1 起点", t1);

  // T2 首步「上一步」在但禁用
  const t2 = await page.evaluate(() => {
    const prev = document.querySelector(".driver-popover-prev-btn");
    return prev ? { display: getComputedStyle(prev).display, disabled: prev.disabled } : null;
  });
  ok("T2 首步上一步禁用", t2 && t2.display !== "none" && t2.disabled === true, t2);

  // T3 推进：高亮迁移+进度递增+上一步可用
  await page.evaluate(() => { window.__d.moveNext(); });
  await page.waitForTimeout(500);
  const t3 = await page.evaluate(() => {
    const $ = (s) => document.querySelector(s);
    const txt = (s) => { const e = $(s); return e ? e.textContent.trim() : null; };
    return {
      progress: txt(".driver-popover-progress-text"),
      activeEl: $(".driver-active-element")?.getAttribute("data-tour") || null,
      prevDisplay: $(".driver-popover-prev-btn") ? getComputedStyle($(".driver-popover-prev-btn")).display : null,
      prevText: $(".driver-popover-prev-btn")?.textContent.trim(),
    };
  });
  await page.screenshot({ path: path.join(shots, "t3-step2.png") });
  ok("T3 推进至步2", t3.progress === "2 / 6" && t3.activeEl === "tour-chat" && t3.prevDisplay !== "none" && t3.prevText === "上一步", t3);

  // T4 disableActiveInteraction：点击被高亮元素不触发
  await page.click('[data-tour="tour-chat"]', { force: true }).catch(() => {});
  await page.waitForTimeout(200);
  const t4 = await page.evaluate(() => window.__clicks);
  ok("T4 高亮元素点击被拦截", t4 === 0, { clicks: t4 });

  // T5 中段进度模板 3/6
  await page.evaluate(() => { window.__d.moveNext(); });
  await page.waitForTimeout(350);
  const t5 = await page.evaluate(() => document.querySelector(".driver-popover-progress-text")?.textContent.trim());
  ok("T5 进度模板 3/6", t5 === "3 / 6", { progress: t5 });

  // T6 末步完成钮+completed 首报生效（onDestroyed 的 skipped 被吞）
  await page.evaluate(() => { window.__d.moveTo(5); });
  await page.waitForTimeout(450);
  const t6a = await page.evaluate(() => ({
    doneText: document.querySelector(".driver-popover-next-btn")?.textContent.trim(),
    progress: document.querySelector(".driver-popover-progress-text")?.textContent.trim(),
  }));
  await page.screenshot({ path: path.join(shots, "t6-last.png") });
  await page.click(".driver-popover-next-btn");
  await page.waitForTimeout(300);
  const t6b = await page.evaluate(() => ({ done: window.__doneClicks, destroyed: window.__destroyed, report: window.__report, all: window.__reportAll }));
  ok("T6 完成=completed 首报生效", t6a.doneText === "完成" && t6a.progress === "6 / 6" && t6b.report === "completed"
    && t6b.done === 1 && t6b.destroyed === 1 && t6b.all.join(",") === "completed,skipped", { ...t6a, ...t6b });

  // T7 X 关闭 → skipped
  await page.evaluate(() => { window.__d = window.makeTour(); window.__d.drive(); });
  await page.waitForTimeout(450);
  await page.click(".driver-popover-close-btn");
  await page.waitForTimeout(300);
  const t7 = await page.evaluate(() => ({ close: window.__closeClicks, destroyed: window.__destroyed, report: window.__report }));
  ok("T7 X 关闭=skipped", t7.report === "skipped" && t7.close === 1 && t7.destroyed === 1, t7);

  // T8 ESC → destroyed → skipped（allowKeyboardControl）
  await page.evaluate(() => { window.__d = window.makeTour(); window.__d.drive(); });
  await page.waitForTimeout(450);
  await page.keyboard.press("Escape");
  await page.waitForTimeout(300);
  const t8 = await page.evaluate(() => ({ destroyed: window.__destroyed, report: window.__report }));
  ok("T8 ESC 退出=skipped", t8.report === "skipped" && t8.destroyed === 1, t8);

  // T9 遮罩点击 → 退出=skipped
  await page.evaluate(() => { window.__d = window.makeTour(); window.__d.drive(); });
  await page.waitForTimeout(450);
  await page.mouse.click(6, 400);
  await page.waitForTimeout(300);
  const t9 = await page.evaluate(() => ({ destroyed: window.__destroyed, report: window.__report, isActive: window.__d.isActive() }));
  ok("T9 遮罩点击退出=skipped", t9.report === "skipped" && t9.isActive === false, t9);

  // T10 highlight 单元素模式：三钮隐藏+无进度（空 footer 残留随库版本如实接受）
  await page.evaluate(() => { window.__d = window.makeTour(); window.__d.highlight({ element: '[data-tour="tour-schedule"]', popover: { showButtons: [], showProgress: false, progressText: "", title: "H 单点", description: "HD" } }); });
  await page.waitForTimeout(450);
  const t10 = await page.evaluate(() => {
    const $ = (s) => document.querySelector(s);
    const disp = (s) => ($(s) ? getComputedStyle($(s)).display : null);
    return {
      title: $(".driver-popover-title")?.textContent.trim(),
      next: disp(".driver-popover-next-btn"), prev: disp(".driver-popover-prev-btn"), close: disp(".driver-popover-close-btn"),
      progress: $(".driver-popover-progress-text")?.textContent.trim() ?? null,
    };
  });
  await page.screenshot({ path: path.join(shots, "t10-highlight.png") });
  ok("T10 highlight 三钮隐藏", t10.title === "H 单点" && t10.next === "none" && t10.prev === "none" && t10.close === "none", t10);

  // T11 视口缩放后聚光跟随
  await page.evaluate(() => { window.__d.destroy(); window.__d = window.makeTour(); window.__d.drive(); });
  await page.waitForTimeout(450);
  await page.evaluate(() => { document.querySelector(".side").style.width = "20vw"; });
  const before = await page.evaluate(() => document.querySelector(".driver-active-element")?.getBoundingClientRect().toJSON());
  await page.setViewportSize({ width: 800, height: 620 });
  await page.waitForTimeout(600);
  const after = await page.evaluate(() => document.querySelector(".driver-active-element")?.getBoundingClientRect().toJSON());
  ok("T11 缩放后聚光跟随", !!before && !!after && (Math.abs(before.width - after.width) > 1 || Math.abs(before.height - after.height) > 1),
    { before: Math.round(before?.width), after: Math.round(after?.width) });

  // T12 destroy 清场：body 活动类/遮罩/popover 全部移除
  const t12 = await page.evaluate(() => {
    window.__d.destroy();
    return {
      active: document.body.classList.contains("driver-active"),
      overlay: !!document.querySelector(".driver-overlay"),
      popover: !!document.querySelector(".driver-popover"),
    };
  });
  ok("T12 destroy 清场", !t12.active && !t12.overlay && !t12.popover, t12);
} finally {
  await ctx.close();
  setTimeout(() => { try { fs.rmSync(prof, { recursive: true, force: true }); } catch { /* 临时目录清理失败可忽略 */ } }, 800);
}
const npass = Object.values(R).filter((v) => v.pass).length;
const total = Object.keys(R).length;
console.log("SUMMARY " + npass + "/" + total + " PASS");
fs.writeFileSync(path.join(shots, "..", "engine-probe-results.json"),
  JSON.stringify({ when: new Date().toISOString(), driver: "1.10.2 (node_modules, npm nilbuild line)", summary: npass + "/" + total, results: R }, null, 2));
process.exit(npass === total ? 0 : 1);

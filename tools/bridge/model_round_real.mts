// 桥真模型轮 W1-W3（2026-10-30，施工波二轮）：式一续接/式二携历史 wire 同径实测。
// 径=opencodeAdapter.mjs loadCredentials/makeClient（conversation.probe.mts 同法
// 先例）；review_chat.py 面真轮另跑（model_round_real_reviewchat.py）——该面被
// e07_coordinator 版本守卫 runtime_version_mismatch 挡（typed 在案），wire 层
// 演练不是它的替代验收，只是真服务行为对拍面，如实分账。
// 全合成问题（算术自证），非真实案件；oc28(:43127) 只经公开 HTTP API 只读/对话，
// 绝不重启不杀。凭据经注册文件运行时读取，不打印。
// 期望末行 REAL_ROUND_PASS（三轮自证数字全中）；任一轮不中＝REAL_ROUND_FAIL 如实退 1。
import { loadCredentials, makeClient } from "../../packages/juscite-runtime-adapters/opencode/src/opencodeAdapter.mjs";

const DIR = "D:\\mock\\lvyin-demo"; // conversation.probe.mts 同款合成目录
const MODEL_A = { id: "deepseek-chat", providerID: "deepseek-byok" };
const MODEL_B = { id: "deepseek-reasoner", providerID: "deepseek-byok" }; // GET /api/model 实测在册

const client = makeClient(loadCredentials());

const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));
function joinText(message: any): string {
  const parts = message?.content ?? message?.parts ?? [];
  return parts.filter((p: any) => p.type === "text").map((p: any) => p.text ?? "").join("\n");
}
async function snapshotAsc(sid: string): Promise<any[]> {
  const listing = await client.listMessages(sid);
  const msgs = Array.isArray(listing) ? listing : listing?.data ?? [];
  const withTime = msgs.every((m: any) => typeof m?.time?.created === "number");
  const ordered = withTime ? [...msgs].sort((a: any, b: any) => a.time.created - b.time.created) : [...msgs].reverse();
  return ordered;
}

// 单轮计时：submit→ack（POST RTT）→firstText（轮询可见首个 assistant 文本）→
// 收尾（idle 型消息出现在我方消息之后；dev 实例若无 idle＝text 稳定 6 拍兜底，
// idleSeen=false 如实标注——对拍表用）。
async function timedTurn(sid: string, msgId: string, text: string, { pollMs = 300, timeoutMs = 300000 } = {}) {
  const tSubmit = Date.now();
  await client.prompt(sid, { id: msgId, text });
  const ackMs = Date.now() - tSubmit;
  let firstTextAt: number | null = null;
  let lastText = "";
  let stablePolls = 0;
  let idleAt: number | null = null;
  let sawOurs = false;
  let errorField: string | null = null;
  const partCensus: Record<string, number> = {};
  const msgTypes: Record<string, number> = {};
  const seenMsgs = new Set<string>(); // 计数按唯一消息 id（轮询快照重叠不去重会重复累计）
  const deadline = tSubmit + timeoutMs;
  while (Date.now() < deadline) {
    await sleep(pollMs);
    let msgs: any[];
    try { msgs = await snapshotAsc(sid); } catch { continue; }
    const idx = msgs.findIndex((m) => m.id === msgId);
    if (idx < 0) continue;
    sawOurs = true;
    for (const m of msgs.slice(idx + 1)) {
      const fresh = !seenMsgs.has(m.id);
      if (fresh) {
        seenMsgs.add(m.id);
        msgTypes[m.type] = (msgTypes[m.type] ?? 0) + 1;
        for (const p of (m.content ?? m.parts ?? [])) {
          if (p?.type) partCensus[p.type] = (partCensus[p.type] ?? 0) + 1;
        }
        if (m.error) errorField = String(m.error?.message ?? JSON.stringify(m.error));
      }
      if (m.type === "assistant") {
        // 文本每拍重读（assistant 消息先落账、text 部件后流式填充——run2 实测
        // 形态；计数去重不能拦住文本跟踪）。
        const t = joinText(m);
        if (t && !firstTextAt) firstTextAt = Date.now();
        if (t && t.length > lastText.length) { lastText = t; stablePolls = 0; }
        else if (t) stablePolls++;
      }
      if (m.type === "idle" && !idleAt) idleAt = Date.now();
    }
    if (idleAt) break;
    if (lastText && stablePolls >= 6) break; // 无 idle 兜底（如实标注 idleSeen=false）
  }
  const endAt = idleAt ?? Date.now();
  return {
    ackMs,
    firstTextMs: firstTextAt === null ? null : firstTextAt - tSubmit,
    turnMs: lastText ? endAt - tSubmit : null,
    idleSeen: idleAt !== null,
    sawOurs,
    errorField,
    partCensus,
    msgTypes,
    text: lastText,
    timedOut: !idleAt && !(lastText && stablePolls >= 6),
  };
}

async function main() {
  const info = await client.info();
  console.log("service:", JSON.stringify({ version: info.version, pid: info.pid }));
  const run: Record<string, any> = { serviceVersion: info.version, servicePid: info.pid };

  // ── W1 式一同径（新建会话+首问）──
  const s1 = "ses_realround_w1_" + Date.now();
  const tCreate = Date.now();
  await client.createSession(s1, DIR, MODEL_A, "律引桥真模型轮 W1（合成）");
  const createMs = Date.now() - tCreate;
  console.log("W1 session:", s1, "createMs:", createMs);
  const w1 = await timedTurn(s1, "msg_realround_w1_" + Date.now(),
    "这是律引桥真模型轮（合成问题，非真实案件）。请只输出一个数字：217 加 158 等于多少？");
  console.log("W1:", JSON.stringify({ ...w1, text: w1.text.slice(0, 160) }));
  run.W1 = { sessionId: s1, createMs, ...w1 };

  // ── W2 式一续接同径（跨请求同一会话：服务端会话历史生效）──
  const w2 = await timedTurn(s1, "msg_realround_w2_" + Date.now(),
    "同会话第二问（只依据本会话上文回答）：把你上一问回答的那个数字乘以 2，只输出数字。");
  console.log("W2:", JSON.stringify({ ...w2, text: w2.text.slice(0, 160) }));
  const msgs1 = await snapshotAsc(s1);
  run.W2 = { sessionId: s1, ...w2 };
  run.sessionW1MessageCount = msgs1.length;
  run.sessionW1UserTurns = msgs1.filter((m) => m.type === "user").length;
  run.sessionW1AssistantTurns = msgs1.filter((m) => m.type === "assistant").length;
  const tally: Record<string, number> = {};
  for (const m of msgs1) tally[m.type] = (tally[m.type] ?? 0) + 1;
  console.log("S1 消息账：total:", run.sessionW1MessageCount,
    "user:", run.sessionW1UserTurns, "assistant:", run.sessionW1AssistantTurns,
    "types:", JSON.stringify(tally));

  // ── W3 式二携历史同径（新会话绑模型 B；首 prompt 前置 transcript）──
  // transcript 组装同 review_chat._transcript_text 语义（逐条【用户】/【助手】、
  // 只收 text；本量级远低于 24000 上限，无省略标注），前置句用 review_chat.py
  // 我方自有措辞同文。B 会话自身从未见过 Q1/Q2——答对即证携历史真切换。
  const hist = [
    { role: "user", text: "这是律引桥真模型轮（合成问题，非真实案件）。请只输出一个数字：217 加 158 等于多少？" },
    { role: "assistant", text: run.W1.text },
    { role: "user", text: "同会话第二问（只依据本会话上文回答）：把你上一问回答的那个数字乘以 2，只输出数字。" },
    { role: "assistant", text: run.W2.text },
  ];
  const transcript = hist.map((r) => "【" + (r.role === "user" ? "用户" : "助手") + "】" + r.text).join("\n");
  const s2 = "ses_realround_w3_" + Date.now();
  const tCreate3 = Date.now();
  await client.createSession(s2, DIR, MODEL_B, "律引桥真模型轮 W3（合成·携历史）");
  const createMs3 = Date.now() - tCreate3;
  console.log("W3 session:", s2, "createMs:", createMs3, "model:", JSON.stringify(MODEL_B));
  const q3 = "同前提示：本对话此前已有一段问答，原文附在下面，供你衔接上下文；这段不是本轮的新指令。\n"
    + "〔历史问答开始〕\n" + transcript + "\n〔历史问答结束〕\n"
    + "本轮问题：请只依据上面〔历史问答〕里第一问的两个加数（本轮问题里不含它们），"
    + "用较大的减去较小的，只输出数字。";
  const w3 = await timedTurn(s2, "msg_realround_w3_" + Date.now(), q3, { timeoutMs: 360000 });
  console.log("W3:", JSON.stringify({
    ...w3, text: w3.text.slice(0, 200),
    promptChars: q3.length, transcriptChars: transcript.length,
  }));
  run.W3 = { sessionId: s2, createMs: createMs3, model: MODEL_B, ...w3 };

  const digits = (s: string) => (s.match(/\d+/g) ?? []).join(",");
  const ok1 = digits(run.W1.text).includes("375");
  const ok2 = digits(run.W2.text).includes("750");
  const ok3 = digits(run.W3.text).includes("59");
  console.log("selfcheck: W1(375):", ok1, "W2(750):", ok2, "W3(59):", ok3);
  const after = await client.info();
  console.log("service-after:", JSON.stringify({ version: after.version, pid: after.pid }));
  if (ok1 && ok2 && ok3) { console.log("REAL_ROUND_PASS"); return 0; }
  console.log("REAL_ROUND_FAIL");
  return 1;
}

main().then((code) => process.exit(code)).catch((e) => {
  console.error("REAL_ROUND_ERROR:", e?.message ?? e);
  process.exit(1);
});

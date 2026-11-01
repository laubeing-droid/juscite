// 走查种子小件：经桥 RPC 增/删一条提醒日程（合成数据，落 :3030 桥库，走查完由调用方删）。
// 用法: node --import tsx tools/bridge/board_seed.mts add <date> <HH:MM> "<标题>" <remindMinutes>
//       node --import tsx tools/bridge/board_seed.mts del <eventId>
import WebSocket from "ws";
import { VSBuffer, SocketProtocol, ChannelClient } from "@zcode/rpc";

const [, , mode, a1, a2, a3, a4] = process.argv;
// 连接+hello 各带超时，失败重连一次（:3030 共享通道被并行工位间歇拥塞——
// 2026-10-28 实证：ws open 但 hello 8s+ 不回，原实现无超时挂满 spawn 60s 输出为空）。
async function connectOnce() {
  const ws = new WebSocket(`ws://127.0.0.1:${process.env.BOARD_SEED_PORT ?? 3030}/ws`);
  ws.binaryType = "arraybuffer";
  const data = { fire: (_b) => {} };
  ws.on("message", (buf) => data.fire(VSBuffer.wrap(new Uint8Array(buf))));
  const to = (pms: Promise<unknown>, ms: number, label: string) =>
    Promise.race([pms, new Promise<never>((_, rej) =>
      setTimeout(() => rej(new Error(`${label} 超时 ${ms}ms`)), ms))]);
  await to(new Promise((r, j) => { ws.on("open", r); ws.on("error", j); }), 8000, "ws 握手");
  const isocket = {
    onData: (l) => { data.fire = l; return { dispose: () => {} }; },
    onClose: () => ({ dispose: () => {} }),
    onEnd: () => ({ dispose: () => {} }),
    write: (b) => ws.send(b.buffer),
    end: () => ws.close(), drain: async () => {}, dispose: () => ws.close(),
  };
  const ch = new ChannelClient(new SocketProtocol(isocket)).getChannel("zcode-agent");
  await to(ch.call("helloConversationV4", []), 8000, "hello");
  return ch;
}
let ch: Awaited<ReturnType<typeof connectOnce>> | null = null;
for (let i = 0; i < 2 && !ch; i++) {
  try { ch = await connectOnce(); } catch (e) {
    if (i === 1) { console.error(`bridge 连接失败：${String((e as Error)?.message ?? e)}`); process.exit(3); }
  }
}
if (mode === "add") {
  const [sh, sm] = String(a2).split(":").map(Number);
  const end = new Date();
  end.setHours(sh, sm + 30, 0, 0); // 结束=开始+30 分钟（桥校验结束>开始）
  const endAt = `${String(end.getHours()).padStart(2, "0")}:${String(end.getMinutes()).padStart(2, "0")}`;
  const created = await ch.call("matterEventAdd", [{
    date: a1, title: a3, kind: "schedule", startAt: a2, endAt,
    remind: true, remindMinutes: Number(a4 ?? 1), location: "", trip: "", note: null,
  }]);
  console.log(JSON.stringify({ id: created?.id ?? null }));
} else if (mode === "del") {
  await ch.call("matterEventDelete", [{ id: a1 }]);
  console.log(JSON.stringify({ deleted: a1 }));
} else if (mode === "demo") {
  // 演示集（合成）：案件 1 + 待办 4（逾期/3 日内/30 日内/窗外）+ 期限日程 1 + 案绑未来节点 1
  const day = (delta: number) => {
    const d = new Date();
    d.setDate(d.getDate() + delta);
    return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
  };
  const c = await ch.call("matterCreate", [{ name: "合成案件·阶梯演示", cause: "民间借贷", caseNo: "(2026)合0203民初7777号" }]);
  const t1 = await ch.call("matterTodoAdd", [{ caseId: c.id, title: "合成期限·交证据（已逾期）", dueDate: day(-2) }]);
  const t2 = await ch.call("matterTodoAdd", [{ caseId: c.id, title: "合成期限·举证期限届满", dueDate: day(2) }]);
  const t3 = await ch.call("matterTodoAdd", [{ caseId: c.id, title: "合成期限·上诉期届满", dueDate: day(20) }]);
  const t4 = await ch.call("matterTodoAdd", [{ caseId: c.id, title: "合成期限·窗外项", dueDate: day(40) }]);
  const e1 = await ch.call("matterEventAdd", [{ date: day(6), title: "合成期限·续封申请截止", kind: "deadline", remind: true, remindMinutes: 30 }]);
  const e2 = await ch.call("matterEventAdd", [{ date: day(9), title: "合成节点·证据质证", kind: "hearing", caseId: c.id, startAt: "09:30", endAt: "11:00", remind: false }]);
  console.log(JSON.stringify({ caseId: c.id, todoIds: [t1.id, t2.id, t3.id, t4.id], eventIds: [e1.id, e2.id] }));
} else if (mode === "cleantodos") {
  // 清场小件：删标题精确匹配的走查样本待办（跨轮残留清扫；matterTodoList 全量+逐条删）
  const listed = await ch.call("matterTodoList", [{}]);
  let n = 0;
  for (const t of (listed?.todos ?? [])) {
    if (t?.title === "合成待办·走查样本") { await ch.call("matterTodoDelete", [{ id: t.id }]); n += 1; }
  }
  console.log(JSON.stringify({ cleaned: n }));
} else if (mode === "undemo") {
  const caseId = a1;
  for (const id of (a2 ?? "").split(",").filter(Boolean)) await ch.call("matterEventDelete", [{ id }]);
  await ch.call("matterDelete", [{ id: caseId }]); // 待办随 FK 级联清
  console.log(JSON.stringify({ cleaned: caseId }));
} else {
  console.error("用法: board_seed.mts add <date> <HH:MM> <标题> <remindMinutes> | del <id> | cleantodos");
  process.exit(2);
}
process.exit(0);

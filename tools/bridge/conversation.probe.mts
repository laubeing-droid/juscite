// M2-1 下表面探针：真 oc28 serve + 真 DeepSeek 一轮对话（合成问题，非真实案件）
// 期望末行 CONVERSATION_PASS。凭据自动读服务注册文件。
import { loadCredentials, makeClient, waitForAssistant } from "../../packages/juscite-runtime-adapters/opencode/src/opencodeAdapter.mjs";

const cred = loadCredentials();
const client = makeClient(cred);
console.log("[probe] service pid:", cred.pid);
const info = await client.info();
console.log("[probe] info version:", info.version);

const sid = "ses_m2_bridge_" + Date.now();
await client.createSession(sid, "D:\\mock\\lvyin-demo", { id: "deepseek-chat", providerID: "deepseek-byok" });
console.log("[probe] session:", sid);

const t0 = Date.now();
await client.prompt(sid, {
  id: "msg_m2_" + Date.now(),
  text: "这是律引 M2 桥探针（合成问题，非真实案件）。请只用一句话回答：合同中常见的违约金计算方式是什么？",
});
console.log("[probe] prompt submitted");

let chunks = 0;
const result = await waitForAssistant(client, sid, {
  timeoutMs: 90000,
  onDelta: (delta) => { chunks++; if (chunks <= 3 || chunks % 10 === 0) console.log(`[probe] delta#${chunks}:`, delta.slice(0, 40).replace(/\n/g, " ")); },
});
console.log("[probe] reply:", result.text.slice(0, 200));
console.log(`[probe] ${chunks} deltas in ${Date.now() - t0}ms`);
console.log(result.text.length > 5 ? "CONVERSATION_PASS" : "CONVERSATION_FAIL");
process.exit(result.text.length > 5 ? 0 : 1);

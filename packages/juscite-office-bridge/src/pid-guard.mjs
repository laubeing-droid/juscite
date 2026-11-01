// 单对端 PID 守卫（方案 §三·④，机制参照 AutoClaw 的"唯一对端 PID 确认后才放行"）。
// 每条 ESTABLISHED 连接在 netstat 里有两条行：本桥侧（local=监听口，pid=桥自己）与
// 对端侧（local=对端临时口，foreign=监听口，pid=对端进程）。取 PID 必须匹配**对端侧**行。
// 仅 win32；非 win、netstat 超窗（共享工位负载下可慢）或竞态丢行时返回 null，
// 调用方退化为按 远端地址:端口 识别——诚实降级，不假装拿到 PID。
import { spawnSync } from "node:child_process";

export function peerPidOf(bridgePort, clientRemotePort) {
  if (process.platform !== "win32") return null;
  if (!Number.isInteger(bridgePort) || !Number.isInteger(clientRemotePort)) return null;
  const r = spawnSync("netstat", ["-ano"], { encoding: "utf-8", timeout: 5000, windowsHide: true });
  const out = String(r.stdout ?? "");
  const lineRe = /^\s*TCP\s+(\S+?):(\d+)\s+(\S+?):(\d+)\s+ESTABLISHED\s+(\d+)/;
  const bridgeSide = `127.0.0.1:${bridgePort}`;
  for (const line of out.split(/\r?\n/)) {
    const m = lineRe.exec(line);
    if (!m) continue;
    const localAddr = `${m[1]}:${m[2]}`;
    const foreignAddr = `${m[3]}:${m[4]}`;
    // 对端侧行：local=对端临时口，foreign=桥监听口 → 该行 pid 即对端进程
    if (m[2] === String(clientRemotePort) && foreignAddr === bridgeSide && m[1] === "127.0.0.1") {
      return Number(m[5]);
    }
  }
  return null;
}

// 对端身份键：优先 PID，拿不到则用地址:端口（同一 TCP 连接的稳定标识）
export function peerKeyOf(bridgePort, remoteAddress, remotePort) {
  const pid = peerPidOf(bridgePort, remotePort);
  return pid != null ? `pid:${pid}` : `addr:${remoteAddress}:${remotePort}`;
}

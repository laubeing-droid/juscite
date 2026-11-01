// 发现文件：taskpane/宿主外的本地进程不猜端口——统一读 <stateDir>/bridge.json。
// 写入走 tmp+rename 原子替换；stop() 时删除（卸载四清之一）。
import { existsSync, readFileSync, renameSync, rmSync, writeFileSync } from "node:fs";
import { join } from "node:path";

const DISCOVERY_NAME = "bridge.json";

export function discoveryPath(stateDir) {
  return join(stateDir, DISCOVERY_NAME);
}

export function writeDiscovery(stateDir, data) {
  const final = discoveryPath(stateDir);
  const tmp = final + ".tmp";
  writeFileSync(tmp, JSON.stringify(data, null, 2) + "\n", "utf-8");
  renameSync(tmp, final);
  return final;
}

export function readDiscovery(stateDir) {
  const p = discoveryPath(stateDir);
  return existsSync(p) ? JSON.parse(readFileSync(p, "utf-8")) : null;
}

export function removeDiscovery(stateDir) {
  rmSync(discoveryPath(stateDir), { force: true });
  rmSync(discoveryPath(stateDir) + ".tmp", { force: true });
}

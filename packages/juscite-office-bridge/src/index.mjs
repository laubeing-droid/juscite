// @juscite/office-bridge 公开入口：Office 插件本地桥（方案 B-Office插件复刻方案-v1 §三/§五 S1）。
// 只绑回环、动态端口、发现文件 + pair→auth→request/subscribe/ping 帧协议、token 生命周期、单对端守卫。
// 消费方（工作台桌面进程）只经本入口；S5 才接 agent 会话（requestHandler）。
export { startOfficeBridge } from "./server.mjs";
export { createBridgeIdentity } from "./identity.mjs";
export { createBootstrapToken, verifyBootstrapToken } from "./token.mjs";
export { writeDiscovery, readDiscovery, removeDiscovery, discoveryPath } from "./discovery.mjs";
export { peerPidOf, peerKeyOf } from "./pid-guard.mjs";
export { PROTOCOL_VERSION, MAX_FRAME_BYTES, C2S_KINDS, S2C_KINDS, SURFACES, ERROR_CODES, parseInbound, s2cFrame } from "./protocol.mjs";

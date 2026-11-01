// 桥身份：每次服务启动生成一次性 RSA 身份对，公钥指纹（sha256）作为配对钉扎值。
// 表达隔离说明：机制形状参照复刻方案 §一/§三（AutoClaw 拆解报告的"RSA 公钥指纹钉扎"），
// 实现与命名全部自写；模长取 2048（配对只需指纹校验，非加密信道，启动速度优先——
// 方案 §三 已定调"回环明文不保密，安全靠 token 绑定+指纹钉扎"）。
import { createHash, generateKeyPairSync } from "node:crypto";

export function createBridgeIdentity() {
  const { publicKey, privateKey } = generateKeyPairSync("rsa", {
    modulusLength: 2048,
    publicKeyEncoding: { type: "spki", format: "der" },
    privateKeyEncoding: { type: "pkcs8", format: "pem" },
  });
  const fingerprint = createHash("sha256").update(publicKey).digest("hex");
  return { fingerprint, privateKeyPem: privateKey, createdAt: new Date().toISOString() };
}

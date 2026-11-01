// 帧协议（方案 §三：学 AutoClaw 的形状自研实现）——
// c2s：pair（首帧 sequence 必须为 1）→ auth / request / subscribe / unsubscribe / ping
// s2c：ready / response / run.events / tool.request / pong / goaway / error
// 帧 = JSON 文本；上限 1 MiB；sequence 逐帧 +1（服务端校验）。
// 命名与载荷是我方域词（surface/peerPid 等自定），与闭源实现零文本重叠。

export const PROTOCOL_VERSION = 1;
export const MAX_FRAME_BYTES = 1024 * 1024;

export const C2S_KINDS = new Set(["pair", "auth", "request", "subscribe", "unsubscribe", "ping"]);
export const S2C_KINDS = new Set(["ready", "response", "run.events", "tool.request", "pong", "goaway", "error"]);

// 一期实际接线的宿主面：word/wps 可用，excel/powerpoint 仅协议留名（方案 §二.5）
export const SURFACES = new Set(["word", "wps", "excel", "powerpoint"]);

export const ERROR_CODES = {
  bootstrapTokenInvalid: "bootstrap_token_invalid",
  publicKeyMismatch: "public_key_mismatch",
  badFrame: "bad_frame",
  badSequence: "bad_sequence",
  peerAlreadyPaired: "peer_already_paired",
  notPaired: "not_paired",
  unsupportedSurface: "unsupported_surface",
  shutdown: "server_shutdown",
};

export function s2cFrame(kind, extra = {}) {
  if (!S2C_KINDS.has(kind)) throw new Error(`unknown s2c frame kind: ${kind}`);
  return { kind, at: new Date().toISOString(), ...extra };
}

// 入站帧静态校验：JSON 可解析 + kind 在词表内。sequence/配对状态由连接层判定。
export function parseInbound(text) {
  let frame;
  try {
    frame = JSON.parse(text);
  } catch {
    return { ok: false, err: ERROR_CODES.badFrame };
  }
  if (frame === null || typeof frame !== "object" || Array.isArray(frame)) {
    return { ok: false, err: ERROR_CODES.badFrame };
  }
  if (typeof frame.kind !== "string" || !C2S_KINDS.has(frame.kind)) {
    return { ok: false, err: ERROR_CODES.badFrame };
  }
  if (typeof frame.sequence !== "number" || !Number.isInteger(frame.sequence)) {
    return { ok: false, err: ERROR_CODES.badSequence };
  }
  return { ok: true, frame };
}

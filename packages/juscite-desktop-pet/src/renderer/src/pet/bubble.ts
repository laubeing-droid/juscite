// 功能 #28 桌宠 · 气泡词库与 seed 稳定轮选（RE-28 §3.2；B18 语义自写词库）。
// 标题兜底、描述候选链按会话键 seed 稳定轮选（同键同句，不闪刷）；中英按窗口语言二选一。
// 全部措辞自写（表达隔离；A28 词表语义逐词落点：待命中/等待授权确认或提问/
// 刚完成一次运行/运行已取消/需要查看错误/桌面端未连接 + thinking/working 自写细分）。

export type BubbleTone = "info" | "success" | "warn" | "error";

export interface BubbleCopy {
  title: string;
  body: string;
  tone: BubbleTone;
  /** 渲染层按 ttl 自动消失；0=常驻跟随状态。 */
  ttlMs: number;
}

function pickLang<T>(zh: T, en: T, lang: string): T {
  return lang.toLowerCase().startsWith("zh") ? zh : en;
}

/** 会话键 → 稳定种子（B18 seedNumber 语义，自实现）。 */
export function seedNumber(key: string): number {
  let h = 2166136261;
  for (let i = 0; i < key.length; i += 1) {
    h ^= key.charCodeAt(i);
    h = Math.imul(h, 16777619);
  }
  return h >>> 0;
}

/** seed 稳定轮选：同键恒选同句（对拍 18）。 */
export function pickStable(candidates: string[], seed: number): string {
  if (candidates.length === 0) return "";
  return candidates[seed % candidates.length]!;
}

const IDLE_COPY_ZH = ["窝里蹲着呢", "随时候命", "打个盹儿也醒着"];
const RUNNING_COPY_ZH = ["正在处理「{title}」", "埋头办「{title}」", "「{title}」走着呢"];

export function idleBubble(lang: string, seed: number): string {
  const candidates = pickLang(IDLE_COPY_ZH, ["Resting on duty", "Standing by"], lang);
  return pickStable(candidates, seed);
}

export function runningBubble(lang: string, seed: number, title: string): string {
  const candidates = pickLang(RUNNING_COPY_ZH, ['Working on "{title}"'], lang);
  return pickStable(candidates, seed).replaceAll("{title}", title);
}

export function terminalBubble(
  lang: string,
  seed: number,
  outcome: "completed" | "error" | "interrupted",
): { body: string; tone: BubbleTone; ttlMs: number } {
  const ttlMs = 3000;
  if (outcome === "completed") {
    return {
      body: pickStable(pickLang(["刚办完一单，收工！", "这轮跑完了，漂亮"], ["Run finished nicely"], lang), seed),
      tone: "success",
      ttlMs,
    };
  }
  if (outcome === "error") {
    return {
      body: pickStable(pickLang(["这轮出了点问题，得看看错误", "跑岔了，错误得盯一眼"], ["Something failed, take a look"], lang), seed),
      tone: "error",
      ttlMs,
    };
  }
  return {
    body: pickStable(pickLang(["这轮被取消了", "运行已中止"], ["Run was cancelled"], lang), seed),
    tone: "info",
    ttlMs,
  };
}

export function pendingBubble(lang: string): { body: string; tone: BubbleTone; ttlMs: number } {
  return {
    body: pickLang("等你授权确认，或有话要答我", "Waiting for your approval", lang),
    tone: "warn",
    ttlMs: 0,
  };
}

export function disconnectedBubble(lang: string): { body: string; tone: BubbleTone; ttlMs: number } {
  return {
    body: pickLang("桌面端未连接，我在等它回来", "Desktop bridge is offline", lang),
    tone: "warn",
    ttlMs: 0,
  };
}

/** 气泡标题：会话 title 兜底"新会话"（B18 标题候选链简化：v1 单气泡位）。 */
export function bubbleTitle(lang: string, sessionTitle: string | null | undefined): string {
  const trimmed = sessionTitle?.trim();
  if (trimmed) return trimmed;
  return pickLang("新会话", "New session", lang);
}

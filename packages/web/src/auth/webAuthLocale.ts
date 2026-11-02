import type { WebOAuthProviderId } from "./browserOAuthCredentialRepo.js";

type WebAuthLocale = "zh-CN" | "en-US";

interface WebAuthPageCopy {
  brand: string;
  loginTitle: string;
  loginDescription: string;
  loginSteps: readonly string[];
  loginPending: string;
  loginError: string;
  loginAction: Record<WebOAuthProviderId, string>;
  loginRegion: Record<WebOAuthProviderId, string>;
  callbackTitle: string;
  callbackDescription: string;
  callbackNext: string;
  callbackErrorTitle: string;
  callbackErrorDescription: string;
  callbackErrorPath: string;
  callbackErrorDetail: string;
  retryAction: string;
}

const WEB_AUTH_COPY = {
  "zh-CN": {
    brand: "Juscite",
    loginTitle: "登录后继续使用 Web 远程控制",
    loginDescription: "请选择与电脑端相同的登录平台，并使用同一账号。",
    loginSteps: ["登录", "选择电脑", "打开任务"],
    loginPending: "正在打开授权页…",
    loginError: "登录没有开始。请再选一次平台。",
    loginAction: { zai: "连接 Z.ai 继续使用", bigmodel: "连接 BigModel 继续使用" },
    loginRegion: { zai: "全球", bigmodel: "中国" },
    callbackTitle: "正在完成登录",
    callbackDescription: "请稍候，正在校验账号身份。",
    callbackNext: "完成后进入远程控制，选择电脑即可开始。",
    callbackErrorTitle: "登录失败",
    callbackErrorDescription: "授权流程未完成，请重新登录。",
    callbackErrorPath: "将回到登录页。重新选择平台即可再试一次。",
    callbackErrorDetail: "查看详情",
    retryAction: "重新登录",
  },
  "en-US": {
    brand: "Juscite",
    loginTitle: "Sign In To Continue",
    loginDescription: "Choose the same sign-in provider and account as on your computer.",
    loginSteps: ["Sign in", "Choose a computer", "Open a task"],
    loginPending: "Opening the authorization page…",
    loginError: "Sign-in did not start. Choose a provider again.",
    loginAction: { zai: "Connect to Z.ai", bigmodel: "Connect to BigModel" },
    loginRegion: { zai: "Global", bigmodel: "CN" },
    callbackTitle: "Finishing Sign-In",
    callbackDescription: "Verifying your account identity.",
    callbackNext: "Next you will enter remote control and choose a computer.",
    callbackErrorTitle: "Sign-In Failed",
    callbackErrorDescription: "The authorization flow did not complete. Sign in again.",
    callbackErrorPath: "You will return to sign-in. Choose a provider to try once more.",
    callbackErrorDetail: "Details",
    retryAction: "Sign In Again",
  },
} satisfies Record<WebAuthLocale, WebAuthPageCopy>;

function resolveWebAuthLocale(language?: string): WebAuthLocale {
  const candidate =
    language ??
    document.documentElement.lang ??
    navigator.language ??
    navigator.languages?.[0] ??
    "";

  return candidate.toLowerCase().startsWith("zh") ? "zh-CN" : "en-US";
}

export function getWebAuthCopy(locale: WebAuthLocale = resolveWebAuthLocale()): WebAuthPageCopy {
  return WEB_AUTH_COPY[locale];
}

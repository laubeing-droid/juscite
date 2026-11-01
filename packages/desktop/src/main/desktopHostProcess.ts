/*
 * 换宿主（v4 §1.3）：原 Electron utilityProcess 宿主（打包 @zcode/server）整链废弃，
 * 改为应用级单例桥进程 —— `node <tsx> tools/bridge/bridge_host.mjs`（桥协议=ChannelServer
 * WebSocket /ws，renderer 直连，不再走 MessagePortMain 服务端口）。
 * oc28 serve 只做注册文件探测（%APPDATA%\Juscite\state\opencode\service-local.json），
 * 未运行时弹提示、绝不自动拉起（spawn oc28 留待用户裁决）；桥进程本身照常拉起，
 * 会话请求由桥 fail-closed。
 */
import { app, BrowserWindow, dialog } from "electron";
import { spawn, type ChildProcess } from "node:child_process";
import { existsSync, readFileSync } from "node:fs";
import { homedir } from "node:os";
import { join } from "node:path";
import { LAUNCH_MARKS_QUERY_KEY, serializeLaunchMarks, type WorkspacePurpose } from "@zcode/shared";
import { getMainLaunchPartialMarks } from "./desktopLaunchMarks.js";
import { createHostLogRelay } from "./hostLogRelay.js";

export interface WindowBootstrapOptions {
  restoreSession?: boolean;
  supportsSettings?: boolean;
  initialWorkspacePath?: string;
  initialWorkspacePurpose?: WorkspacePurpose;
  unavailableWorkspacePath?: string;
  windowKind?: "main" | "update-status";
  locale?: string;
  /** 桥 WebSocket 地址（renderer 直连 Juscite 桥，替代原 utilityProcess 服务端口）。 */
  bridgeWsUrl?: string;
}

/** 兼容保留：上游 InitLocal 消息形状。桥进程不经此消息初始化，字段仅供调用方组装。 */
export interface HostInitMessage {
  type?: string;
  hostId?: string;
  deviceMid?: string;
  workspacePath?: string;
  workspaceIdentity?: string;
  [key: string]: unknown;
}

export interface BridgeHostLogger {
  info: (...args: unknown[]) => void;
  warn: (...args: unknown[]) => void;
  error: (...args: unknown[]) => void;
}

export interface BridgeHostHandle {
  child: ChildProcess;
  port: number;
  wsUrl: string;
}

const DEFAULT_BRIDGE_PORT = 3030;

let bridgeHandle: BridgeHostHandle | null = null;
let bridgeSpawnGeneration = 0;

export function resolveBridgePort(): number {
  const raw = Number(process.env["JUSCITE_BRIDGE_PORT"] ?? DEFAULT_BRIDGE_PORT);
  return Number.isFinite(raw) && raw > 0 ? raw : DEFAULT_BRIDGE_PORT;
}

export function resolveBridgeWsUrl(): string {
  return `ws://127.0.0.1:${resolveBridgePort()}/ws`;
}

/** 仓库根（dev 布局：packages/desktop → 上两级）。可用 JUSCITE_REPO_ROOT 覆盖。 */
function resolveRepoRoot(): string {
  return process.env["JUSCITE_REPO_ROOT"] ?? join(app.getAppPath(), "..", "..");
}

function resolveBridgePaths(): { bridgeDir: string; entry: string; tsxCli: string } {
  // 打包态：桥随包物化在 resources/bridge（electron-builder.config.js extraResources ←
  // scripts/materialize-bridge-bundle.mjs 自足目录）。不再假设仓库布局——r7 记档
  // （78b34899）的「无仓库布局机器桥 spawn fail-closed」边界由此销项；随包要件缺失时
  // 仍由 ensureBridgeHostProcess 的 existsSync 检查 fail-closed。
  if (app.isPackaged) {
    const bridgeRoot = join(process.resourcesPath, "bridge");
    const bridgeDir = join(bridgeRoot, "tools", "bridge");
    return {
      bridgeDir,
      entry: join(bridgeDir, "bridge_host.mjs"),
      tsxCli: join(bridgeRoot, "node_modules", "tsx", "dist", "cli.mjs"),
    };
  }
  const bridgeDir = join(resolveRepoRoot(), "tools", "bridge");
  return {
    bridgeDir,
    entry: join(bridgeDir, "bridge_host.mjs"),
    tsxCli: join(bridgeDir, "node_modules", "tsx", "dist", "cli.mjs"),
  };
}

function resolveOc28RegistrationFile(): string {
  const appData = process.env["APPDATA"] ?? join(homedir(), "AppData", "Roaming");
  return join(appData, "Juscite", "state", "opencode", "service-local.json");
}

interface Oc28Registration {
  url: string;
  pid?: number;
}

function readOc28Registration(): Oc28Registration | null {
  const file = resolveOc28RegistrationFile();
  if (!existsSync(file)) return null;
  try {
    const parsed = JSON.parse(readFileSync(file, "utf-8")) as Record<string, unknown>;
    if (typeof parsed["url"] !== "string" || !parsed["url"].trim()) return null;
    return {
      url: parsed["url"].trim(),
      pid: typeof parsed["pid"] === "number" ? parsed["pid"] : undefined,
    };
  } catch {
    return null;
  }
}

/** 探测 oc28 serve 是否在跑（HTTP 探针；凭据不出注册文件、不落日志）。 */
async function probeOc28Alive(registration: Oc28Registration): Promise<boolean> {
  try {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), 2_000);
    try {
      const response = await fetch(
        registration.url.replace(/\/+$/, "") + "/api/info",
        { method: "GET", signal: controller.signal },
      );
      // 401/403 也证明服务活着（鉴权层应答）。
      return response.ok || response.status === 401 || response.status === 403;
    } finally {
      clearTimeout(timer);
    }
  } catch {
    return false;
  }
}

async function warnIfOc28Down(logger: BridgeHostLogger): Promise<void> {
  const registration = readOc28Registration();
  if (!registration) {
    logger.warn(
      "[bridge-host] oc28 注册文件缺失（" + resolveOc28RegistrationFile() + "）；会话请求将 fail-closed",
    );
    void dialog.showMessageBox({
      type: "warning",
      title: "Juscite：oc28 未注册",
      message: "未找到 oc28 serve 注册文件。",
      detail:
        "预期位置：%APPDATA%\Juscite\state\opencode\service-local.json\n请先手动启动 oc28 serve 后再使用对话功能（Juscite 不会自动拉起 oc28）。",
      buttons: ["知道了"],
    });
    return;
  }
  if (!(await probeOc28Alive(registration))) {
    logger.warn("[bridge-host] oc28 serve 未响应（" + registration.url + "）；会话请求将 fail-closed");
    void dialog.showMessageBox({
      type: "warning",
      title: "Juscite：oc28 serve 未运行",
      message: "oc28 serve 当前不可达。",
      detail:
        "注册地址：" +
        registration.url +
        "\n请手动启动 oc28 serve 后再使用对话功能（Juscite 不会自动拉起 oc28）。",
      buttons: ["知道了"],
    });
  }
}

export function getBridgeHostProcess(): ChildProcess | null {
  return bridgeHandle?.child ?? null;
}

export function isBridgeHostAlive(): boolean {
  return bridgeHandle != null && bridgeHandle.child.exitCode == null && !bridgeHandle.child.killed;
}

/** 幂等拉起桥进程；桥退出后清空句柄，下一次调用可重建。 */
export function ensureBridgeHostProcess(logger: BridgeHostLogger): BridgeHostHandle {
  if (isBridgeHostAlive() && bridgeHandle) {
    return bridgeHandle;
  }
  const { bridgeDir, entry, tsxCli } = resolveBridgePaths();
  const port = resolveBridgePort();
  if (!existsSync(entry)) {
    logger.error("[bridge-host] 桥入口缺失：" + entry + "（spawn 放弃）");
    throw new Error("bridge host entry not found: " + entry);
  }
  if (!existsSync(tsxCli)) {
    logger.error("[bridge-host] tsx 未安装（" + tsxCli + "）；请先在 tools/bridge 安装依赖（spawn 放弃）");
    throw new Error("tsx cli not found: " + tsxCli);
  }

  const generation = ++bridgeSpawnGeneration;
  const label = "bridge-" + generation;
  // @zcode 工作区包 exports 指 TS 源，桥必须经 tsx 转译运行（M1/M2 已验证的启动方式）。
  // ELECTRON_RUN_AS_NODE 让打包态复用随包 Electron 二进制当 Node 用，不依赖系统 PATH。
  const child = spawn(process.execPath, [tsxCli, entry], {
    cwd: bridgeDir,
    env: {
      ...process.env,
      ELECTRON_RUN_AS_NODE: "1",
      BRIDGE_PORT: String(port),
      // 功能 #31 支持通道：诊断包 app_version 取真版本（RE-31 §3.1，不复刻竞品 B16 硬编码漂移）。
      JUSCITE_APP_VERSION: app.getVersion(),
    },
    stdio: ["ignore", "pipe", "pipe"],
    windowsHide: true,
  });

  const hostLogRelay = createHostLogRelay(label, logger);
  child.stdout?.on("data", (data: Buffer) => hostLogRelay.onStdout(data.toString()));
  child.stderr?.on("data", (data: Buffer) => hostLogRelay.onStderr(data.toString()));
  child.once("exit", (code, signal) => {
    logger.warn("[bridge-host] 桥进程退出（generation=" + generation + " code=" + code + " signal=" + signal + "）");
    if (bridgeHandle && bridgeHandle.child === child) {
      bridgeHandle = null;
    }
  });
  child.once("error", (error) => {
    logger.error("[bridge-host] 桥进程 spawn 失败：", error);
    if (bridgeHandle && bridgeHandle.child === child) {
      bridgeHandle = null;
    }
  });

  logger.info("[bridge-host] spawned bridge (pid=" + (child.pid ?? "unknown") + ") on port " + port);
  bridgeHandle = { child, port, wsUrl: resolveBridgeWsUrl() };
  void warnIfOc28Down(logger);
  return bridgeHandle;
}

export function disposeBridgeHostProcess(reason: string): void {
  if (!bridgeHandle) return;
  const child = bridgeHandle.child;
  bridgeHandle = null;
  if (child.exitCode == null && !child.killed) {
    child.kill();
  }
}

export function loadWindow(
  win: BrowserWindow,
  page: "index" | "login" = "index",
  bootstrap?: WindowBootstrapOptions,
): Promise<void> {
  const query = Object.fromEntries(
    Object.entries({
      restoreSession:
        bootstrap?.restoreSession == null ? undefined : String(bootstrap.restoreSession),
      supportsSettings:
        bootstrap?.supportsSettings == null ? undefined : String(bootstrap.supportsSettings),
      initialWorkspacePath: bootstrap?.initialWorkspacePath,
      initialWorkspacePurpose: bootstrap?.initialWorkspacePurpose,
      unavailableWorkspacePath: bootstrap?.unavailableWorkspacePath,
      windowKind: bootstrap?.windowKind,
      locale: bootstrap?.locale,
      bridgeWsUrl: bootstrap?.bridgeWsUrl ?? resolveBridgeWsUrl(),
    }).filter((entry): entry is [string, string] => entry[1] != null),
  );

  if (page === "index") {
    const partial = getMainLaunchPartialMarks();
    query[LAUNCH_MARKS_QUERY_KEY] = serializeLaunchMarks({
      ...partial,
      loadUrl: Date.now(), // T3
    });
  }

  // 生产包不能信任继承环境中的开发服务器地址，否则会被本机开发会话劫持为空白页。
  if (!app.isPackaged && process.env["ELECTRON_RENDERER_URL"]) {
    const base = process.env["ELECTRON_RENDERER_URL"];
    const url = new URL(page === "login" ? base + "/login.html" : base);
    for (const [key, value] of Object.entries(query)) {
      url.searchParams.set(key, value);
    }
    return win.loadURL(url.toString());
  } else {
    return win.loadFile(join(import.meta.dirname, "../renderer/" + page + ".html"), {
      query,
    });
  }
}

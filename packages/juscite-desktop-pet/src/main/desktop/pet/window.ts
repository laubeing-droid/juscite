// 功能 #28 桌宠 · 窗口生命周期/几何/持久化/监督（RE-28 §3.2/§3.3/§3.4）。
// 形态=桌面壳内独立透明 BrowserWindow（§3.0：Electron 原生 transparent+alwaysOnTop+
// skipTaskbar+setIgnoreMouseEvents(true,{forward:true}) 覆盖竞品行为面，无 Rust 侧车）。
// 监督保行为面（A3-A5 精神）：ready 8s 不就绪记诊断并重建一次；render-process-gone 同；
// 再败=销毁+诊断。关闭次序（B29）：先停转发/反注册，再 destroy（幂等）。
// 位置持久化独立键 desktop/pet.window.json（B4：仅记位置；仅以可见性门跳过采样；
// rememberPosition=false 每次回系统默认位）。

import { existsSync, readFileSync, renameSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import {
  app,
  BrowserWindow,
  ipcMain,
  Menu,
  screen,
  type MenuItemConstructorOptions,
} from "electron";
import { PlatformChannels } from "@zcode/shared";
import type { PetConfigPatch, PetRunEventPayload, PetStatusPayload } from "@zcode/shared";
import { petBodyRect, petWindowLogicalSize } from "./geometry.js";
import { createPetStore } from "./store.js";
import { PetRunProjection } from "./projection.js";
import {
  PetAdmissionController,
  type PetSequenceResult,
  type PetStepExecutor,
  type PetStepOutcome,
} from "./admission.js";
import { createPetTool, type PetTool } from "./tool.js";

const PET_READY_TIMEOUT_MS = 8_000;
const PET_BRIDGE_POLL_MS = 2_000;
const PET_POSITION_SAVE_DEBOUNCE_MS = 300;
const PET_DEFAULT_MARGIN = 24;

export interface PetModuleDeps {
  /** %APPDATA%\Juscite（app.getPath("userData")），pet.json 与 pet.window.json 落其 desktop/ 下。 */
  userDataDir: string;
  logger: { info: (...args: unknown[]) => void; warn: (...args: unknown[]) => void };
  /** 桥进程存活（desktopHostProcess.isBridgeHostAlive）——桌面端未连接态的事实源。 */
  isBridgeAlive: () => boolean;
  /** 单击桌宠唤出主窗口（对拍 19）。 */
  ensurePrimaryWindow: (reason: string) => void;
  /** 广播到主渲染层（设置页 onPetStatus）；pet 窗口广播模块内部自理。 */
  broadcastToRenderers: (channel: string, payload: unknown) => void;
}

export interface PetModule {
  getStatus(): PetStatusPayload;
  updateConfig(patch: PetConfigPatch): PetStatusPayload;
  /** 主渲染层转发钩子入口（驱动流 1）。 */
  reportRunEvent(event: PetRunEventPayload): void;
  /** AI 工具 juscite_pet（驱动流 2）。 */
  petTool: PetTool;
  dispose(): void;
}

interface PetWindowState {
  x?: number;
  y?: number;
}

function readWindowState(file: string): PetWindowState {
  if (!existsSync(file)) return {};
  try {
    const raw = JSON.parse(readFileSync(file, "utf-8")) as PetWindowState;
    return typeof raw.x === "number" && typeof raw.y === "number" ? { x: raw.x, y: raw.y } : {};
  } catch {
    return {};
  }
}

function writeWindowState(file: string, state: PetWindowState): void {
  const temp = `${file}.tmp`;
  writeFileSync(temp, `${JSON.stringify(state, null, 2)}\n`, "utf-8");
  renameSync(temp, file);
}

interface DisplayArea {
  x: number;
  y: number;
  width: number;
  height: number;
}

function workAreas(): DisplayArea[] {
  return screen.getAllDisplays().map((display) => {
    const area = display.workArea;
    return { x: area.x, y: area.y, width: area.width, height: area.height };
  });
}

export function createPetModule(deps: PetModuleDeps): PetModule {
  const windowStateFile = join(deps.userDataDir, "desktop", "pet.window.json");
  // 诊断分级（对拍 31/A24 语义）：失败类=warn，常规=info。
  const diagnostic = (name: string, detail?: unknown, level: "info" | "warn" = "info"): void => {
    const write = level === "warn" ? deps.logger.warn : deps.logger.info;
    write(`[pet] ${name}`, detail ?? "");
  };

  let petWindow: BrowserWindow | null = null;
  let readyReceived = false;
  let readyTimer: ReturnType<typeof setTimeout> | null = null;
  let rebuildCount = 0;
  let forwardingToWindow = true; // 关闭次序闸（B29）：置 false 后不再向窗口投递
  let positionSaveTimer: ReturnType<typeof setTimeout> | null = null;

  const store = createPetStore({
    file: join(deps.userDataDir, "desktop", "pet.json"),
    events: {
      onChange: (status) => {
        broadcastStatus(status);
        applyConfigHot(status);
      },
    },
  });

  // 驱动流 1：运行状态投影（八态；A28 六词全落点）。
  const projection = new PetRunProjection({
    store,
    isBridgeAlive: () => deps.isBridgeAlive(),
  });

  // ── 准入执行器：pet 窗口渲染面桥（§3.1 动作协议的进程内落点）────────────
  const pendingSteps = new Map<string, (outcome: PetStepOutcome) => void>();

  const executor: PetStepExecutor = {
    isAvailable: () => petWindow !== null && !petWindow.isDestroyed() && readyReceived,
    interruptCurrent: () => {
      const win = petWindow;
      if (!forwardingToWindow || !win || win.isDestroyed()) return;
      win.webContents.send("pet:interrupt");
    },
    runStep: (step, context) =>
      new Promise<PetStepOutcome>((resolve) => {
        const win = petWindow;
        if (!forwardingToWindow || !win || win.isDestroyed() || !readyReceived) {
          resolve({ kind: "unavailable" });
          return;
        }
        pendingSteps.set(context.stepId, resolve);
        win.webContents.send("pet:step", { id: context.stepId, step });
      }),
  };

  const admission = new PetAdmissionController({ executor });

  /** 宏序列执行 + 播放期占位（期间运行投影不覆盖；收口回基态）。 */
  function executeSequenceTracked(params: unknown): Promise<PetSequenceResult> {
    projection.setSequenceActive(true);
    return admission.execute(params).finally(() => {
      projection.setSequenceActive(false);
    });
  }

  const petTool = createPetTool({ executeSequence: executeSequenceTracked });

  // ── 广播与热生效 ────────────────────────────────────────────────────────
  function isWindowAlive(): boolean {
    return petWindow !== null && !petWindow.isDestroyed();
  }

  /** 状态广播（windowAlive 随行实况覆写；对拍 28：再败销毁后设置页据此提示）。 */
  function broadcastStatus(status: PetStatusPayload): void {
    const enriched: PetStatusPayload = { ...status, windowAlive: isWindowAlive() };
    deps.broadcastToRenderers(PlatformChannels.PetStatusChanged, enriched);
    const win = petWindow;
    if (!forwardingToWindow || !win || win.isDestroyed()) return;
    win.webContents.send("pet:status", enriched);
  }

  function currentStatus(): PetStatusPayload {
    return { ...store.getStatus(), windowAlive: isWindowAlive() };
  }

  function applyConfigHot(status: PetStatusPayload): void {
    const win = petWindow;
    if (!win || win.isDestroyed()) return;
    win.setAlwaysOnTop(status.config.alwaysOnTop);
    const size = petWindowLogicalSize(status.config.sizePercent);
    if (Math.round(win.getBounds().width) !== Math.round(size.width)) {
      win.setSize(Math.round(size.width), Math.round(size.height));
      clampPetWindowToWorkArea();
    }
  }

  // ── 几何：默认位/夹取/持久化 ────────────────────────────────────────────
  function defaultPosition(size: { width: number; height: number }): { x: number; y: number } {
    const area = screen.getPrimaryDisplay().workArea;
    return {
      x: area.x + area.width - size.width - PET_DEFAULT_MARGIN,
      y: area.y + area.height - size.height - PET_DEFAULT_MARGIN,
    };
  }

  /** 工作区夹取按本体（B23/对拍 23）：本体中心选屏、间隙取最近、透明留白可出屏。 */
  function clampPetWindowToWorkArea(): void {
    const win = petWindow;
    if (!win || win.isDestroyed()) return;
    const status = store.getStatus();
    const bounds = win.getBounds();
    const body = petBodyRect({ width: bounds.width, height: bounds.height }, status.config.sizePercent);
    const bodyAbs = { x: bounds.x + body.x, y: bounds.y + body.y, width: body.width, height: body.height };
    const center = { x: bodyAbs.x + bodyAbs.width / 2, y: bodyAbs.y + bodyAbs.height / 2 };
    const areas = workAreas();
    if (areas.length === 0) return;
    // 本体中心所在屏优先；都不含则取中心距离最近的屏；全拔完=首个（主屏）兜底（§3.4）。
    let target = areas[0]!;
    let best = Number.POSITIVE_INFINITY;
    for (const area of areas) {
      const dx =
        center.x < area.x ? area.x - center.x : center.x > area.x + area.width ? center.x - (area.x + area.width) : 0;
      const dy =
        center.y < area.y ? area.y - center.y : center.y > area.y + area.height ? center.y - (area.y + area.height) : 0;
      const distance = dx * dx + dy * dy;
      if (distance < best) {
        best = distance;
        target = area;
      }
    }
    // 本体矩形收入目标工作区（留白随窗口一起移动，可留在屏外）。
    const bodyLeft = Math.min(Math.max(bodyAbs.x, target.x), Math.max(target.x, target.x + target.width - bodyAbs.width));
    const bodyTop = Math.min(Math.max(bodyAbs.y, target.y), Math.max(target.y, target.y + target.height - bodyAbs.height));
    const nextX = Math.round(bodyLeft - body.x);
    const nextY = Math.round(bodyTop - body.y);
    if (nextX !== bounds.x || nextY !== bounds.y) {
      win.setPosition(nextX, nextY);
    }
  }

  function schedulePositionSave(): void {
    if (positionSaveTimer) clearTimeout(positionSaveTimer);
    positionSaveTimer = setTimeout(() => {
      positionSaveTimer = null;
      const win = petWindow;
      // B4 按代码口径：仅以可见性门跳过采样（不可见不采）；rememberPosition=false 不落位置。
      if (!win || win.isDestroyed() || !win.isVisible() || !store.getConfig().rememberPosition) return;
      const bounds = win.getBounds();
      try {
        writeWindowState(windowStateFile, { x: Math.round(bounds.x), y: Math.round(bounds.y) });
      } catch (error) {
        diagnostic("pet.position.save_failed", error, "warn");
      }
    }, PET_POSITION_SAVE_DEBOUNCE_MS);
  }

  // ── 窗口创建/销毁（B28：隐藏=销毁；未启用不预创建；关闭次序见 forwardingToWindow）──
  function resolvePetPageUrl(): { file: string } | { url: string } {
    if (!app.isPackaged && process.env["ELECTRON_RENDERER_URL"]) {
      return { url: `${process.env["ELECTRON_RENDERER_URL"]}/pet.html` };
    }
    return { file: join(import.meta.dirname, "../renderer/pet.html") };
  }

  function createPetWindow(): void {
    if (petWindow && !petWindow.isDestroyed()) return;
    const status = store.getStatus();
    const size = status.geometry.window;
    const saved = status.config.rememberPosition ? readWindowState(windowStateFile) : {};
    const fallback = defaultPosition(size);
    const preloadFile = join(import.meta.dirname, "../preload/petPreload.cjs");
    const win = new BrowserWindow({
      width: Math.round(size.width),
      height: Math.round(size.height),
      x: typeof saved.x === "number" ? saved.x : fallback.x,
      y: typeof saved.y === "number" ? saved.y : fallback.y,
      show: true,
      frame: false,
      transparent: true,
      hasShadow: false,
      resizable: false,
      movable: true,
      skipTaskbar: true,
      focusable: false,
      alwaysOnTop: status.config.alwaysOnTop,
      roundedCorners: false,
      title: "Juscite 桌宠",
      webPreferences: {
        preload: existsSync(preloadFile) ? preloadFile : undefined,
        contextIsolation: true,
        nodeIntegration: false,
        backgroundThrottling: false,
      },
    });
    win.setIgnoreMouseEvents(true, { forward: true }); // 默认整窗穿透（B22）
    petWindow = win;
    readyReceived = false;
    forwardingToWindow = true;
    const page = resolvePetPageUrl();
    const loadPromise = "url" in page ? win.loadURL(page.url) : win.loadFile(page.file);
    void loadPromise.catch((error: unknown) => {
      diagnostic("pet.page.load_failed", error, "warn");
    });

    readyTimer = setTimeout(() => {
      if (readyReceived || !petWindow || petWindow.isDestroyed()) return;
      rebuildCount += 1;
      diagnostic("pet.ready_timeout", { rebuildCount }, "warn");
      if (rebuildCount <= 1 && store.getConfig().enabled) {
        // 8s 不就绪：记诊断并重建窗口一次（§3.2 监督）。
        destroyPetWindow();
        createPetWindow();
      } else {
        // 再败：销毁+诊断+广播（对拍 28：设置页提示的数据面）。
        diagnostic("pet.ready_timeout_give_up", undefined, "warn");
        destroyPetWindow();
        broadcastStatus(store.getStatus());
      }
    }, PET_READY_TIMEOUT_MS);

    win.webContents.on("render-process-gone", () => {
      diagnostic("pet.render_process_gone", { rebuildCount }, "warn");
      rebuildCount += 1;
      if (rebuildCount <= 1 && store.getConfig().enabled) {
        destroyPetWindow();
        createPetWindow();
      } else {
        destroyPetWindow();
        broadcastStatus(store.getStatus());
      }
    });

    win.on("moved", schedulePositionSave);
    win.on("closed", () => {
      if (petWindow === win) petWindow = null;
    });

    win.webContents.on("context-menu", () => {
      showContextMenu();
    });

    // 新窗口拉起即收当前全量状态与工作区，并夹回可见屏（§3.3/B27）。
    win.webContents.once("did-finish-load", () => {
      if (!forwardingToWindow || win.isDestroyed()) return;
      win.webContents.send("pet:status", store.getStatus());
      win.webContents.send("pet:work-areas", workAreas());
      clampPetWindowToWorkArea();
    });
    diagnostic("pet.window.created", { size });
  }

  /** 关闭次序（B29/对拍 3）：先停转发与未决步，再 destroy（幂等）。 */
  function destroyPetWindow(): void {
    forwardingToWindow = false;
    if (readyTimer) {
      clearTimeout(readyTimer);
      readyTimer = null;
    }
    for (const [id, resolve] of [...pendingSteps]) {
      pendingSteps.delete(id);
      resolve({ kind: "unavailable" });
    }
    const win = petWindow;
    petWindow = null;
    readyReceived = false;
    if (win && !win.isDestroyed()) {
      try {
        win.destroy();
      } catch (error) {
        diagnostic("pet.window.destroy_failed", error, "warn");
      }
    }
  }

  function syncWindowToEnabled(): void {
    if (store.getConfig().enabled) {
      createPetWindow();
    } else {
      destroyPetWindow(); // enabled=false 不预创建、重启不自动拉起（B28/对拍 34）。
    }
  }

  // ── 右键菜单（对拍 36 差异行：免开设置页快捷路径）────────────────────────
  function showContextMenu(): void {
    const config = store.getConfig();
    const sizeEntry = (percent: number): MenuItemConstructorOptions => ({
      label: `大小 ${percent}%`,
      type: "checkbox",
      checked: config.sizePercent === percent,
      click: () => {
        void updateConfig({ sizePercent: percent });
      },
    });
    const menu = Menu.buildFromTemplate([
      { label: "打开 Juscite", click: () => deps.ensurePrimaryWindow("pet-context-menu") },
      { type: "separator" },
      sizeEntry(50),
      sizeEntry(100),
      sizeEntry(200),
      { type: "separator" },
      {
        label: "窗口置顶",
        type: "checkbox",
        checked: config.alwaysOnTop,
        click: () => {
          void updateConfig({ alwaysOnTop: !config.alwaysOnTop });
        },
      },
      {
        label: "启用桌宠",
        type: "checkbox",
        checked: config.enabled,
        click: () => {
          void updateConfig({ enabled: !config.enabled });
        },
      },
      { type: "separator" },
      { label: "退出 Juscite", click: () => app.quit() },
    ]);
    menu.popup({ window: petWindow ?? undefined });
  }

  // ── 配置更新入口（设置面/右键菜单）──────────────────────────────────────
  function updateConfig(patch: PetConfigPatch): PetStatusPayload {
    store.update(patch);
    syncWindowToEnabled();
    broadcastStatus(store.getStatus()); // 以创建/销毁后的实况覆写 windowAlive（幂等广播）
    return currentStatus();
  }

  // ── 桥存活轮询（§3.4：断连=桌面端未连接态；重连自动恢复）────────────────
  const bridgePollTimer = setInterval(() => {
    projection.pollBridge();
  }, PET_BRIDGE_POLL_MS);

  // ── 显示器热插拔/DPI 变更（§3.3/§3.4·对拍 33）：按几何公式重算尺寸+夹取回屏；
  // 渲染层工作区缓存随事件刷新；全拔完的极端由夹取取主屏兜底。
  const refreshForDisplayChange = (): void => {
    const win = petWindow;
    if (!win || win.isDestroyed()) return;
    applyConfigHot(store.getStatus());
    win.webContents.send("pet:work-areas", workAreas());
    clampPetWindowToWorkArea();
  };
  screen.on("display-metrics-changed", refreshForDisplayChange);
  screen.on("display-added", refreshForDisplayChange);
  screen.on("display-removed", refreshForDisplayChange);

  // ── 渲染面回执 IPC（petPreload 对面）────────────────────────────────────
  ipcMain.on("pet:ready", () => {
    if (readyTimer) {
      clearTimeout(readyTimer);
      readyTimer = null;
    }
    readyReceived = true;
    rebuildCount = 0;
    diagnostic("pet.ready");
  });
  ipcMain.on("pet:step-done", (_event, payload: { id?: string; outcome?: PetStepOutcome }) => {
    const id = typeof payload?.id === "string" ? payload.id : "";
    const resolver = pendingSteps.get(id);
    if (!resolver) return;
    pendingSteps.delete(id);
    const outcome = payload.outcome;
    resolver(outcome && typeof outcome.kind === "string" ? outcome : { kind: "failed" });
  });
  ipcMain.on("pet:hover", (_event, hovering: unknown) => {
    const win = petWindow;
    if (!win || win.isDestroyed()) return;
    // 命中区翻转穿透（B22）：本体上收鼠标，其余穿透并转发 move 事件。
    win.setIgnoreMouseEvents(hovering !== true, { forward: true });
  });
  ipcMain.on("pet:click", () => {
    deps.ensurePrimaryWindow("pet-click");
  });
  ipcMain.on("pet:move", (_event, payload: { x?: number; y?: number }) => {
    const win = petWindow;
    if (!win || win.isDestroyed()) return;
    const x = Number(payload?.x);
    const y = Number(payload?.y);
    if (!Number.isFinite(x) || !Number.isFinite(y)) return;
    // 物理写入取整（§3.3：亚像素抖动；Electron DIP 坐标按整数写入）。
    win.setPosition(Math.round(x), Math.round(y));
  });
  ipcMain.on("pet:asset-error", (_event, message: unknown) => {
    // 资产缺失/损坏：可见提示由渲染面画，主进程记诊断（B15/§3.4 pet.asset.error）。
    diagnostic("pet.asset.error", message, "warn");
  });
  ipcMain.handle("pet:work-areas", () => workAreas());
  ipcMain.handle("pet:bounds", () => {
    const win = petWindow;
    if (!win || win.isDestroyed()) return { x: 0, y: 0, width: 0, height: 0 };
    return win.getBounds();
  });
  ipcMain.on("pet:clamp", () => {
    clampPetWindowToWorkArea();
  });

  // 启动：enabled=false 不预创建（B28）。
  syncWindowToEnabled();

  return {
    getStatus: () => currentStatus(),
    updateConfig,
    reportRunEvent: (event) => projection.reportRunEvent(event),
    petTool,
    dispose() {
      clearInterval(bridgePollTimer);
      screen.off("display-metrics-changed", refreshForDisplayChange);
      screen.off("display-added", refreshForDisplayChange);
      screen.off("display-removed", refreshForDisplayChange);
      if (positionSaveTimer) clearTimeout(positionSaveTimer);
      destroyPetWindow();
    },
  };
}

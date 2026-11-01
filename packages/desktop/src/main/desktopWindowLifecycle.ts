import { app, BrowserWindow, Menu } from "electron";
import { type Locale } from "@zcode/shared";
import { PlatformChannels } from "@zcode/shared";
import { createBrowserWindow } from "./desktopWindowChrome.js";
import { ensureBridgeHostProcess, type WindowBootstrapOptions } from "./desktopHostProcess.js";
import { handleDarwinWindowCloseRequest } from "./desktopDarwinCloseBehavior.js";
import {
  parseWindowUnreadCount,
  maxWindowUnreadCounts,
  syncUnreadBadgeForPlatform,
} from "./unreadBadge.js";
import { attachDesktopWindowSizePersistence, type DesktopWindowSize } from "./desktopWindowSize.js";
import {
  registerMainApplicationWindow,
  unregisterMainApplicationWindow,
} from "./resourceManagerWindow.js";

/**
 * 换宿主（v4 §1.3）：每个窗口不再 spawn 独立 utilityProcess 宿主，也不再经
 * MessagePortMain 投递服务端口。应用级单例桥进程（tools/bridge/bridge_host.mjs）
 * 在首个窗口 dom-ready 前幂等拉起，桥 WS 地址随窗口 query 注入，renderer 直连。
 */
export function createWindow(options: {
  iconPath: string;
  preloadPath: string;
  logger: { info: (...args: unknown[]) => void; warn: (...args: unknown[]) => void };
  forceQuitRef: { current: boolean };
  handleBeforeClose?: (win: BrowserWindow, label: string) => boolean;
  syncAutoUpdaterStateToWindow: (win: BrowserWindow) => void;
  syncReadyUpdateToWindow: (win: BrowserWindow) => void;
  syncPostUpdateReleaseNotesToWindow: (win: BrowserWindow) => void;
  bootstrap?: WindowBootstrapOptions;
  deviceMid: string;
  initialDesktopZoomLevel?: number;
  initialWindowSize?: DesktopWindowSize;
  currentApplicationLocale?: () => Locale;
  persistWindowSize?: (state: DesktopWindowSize) => Promise<void>;
  resolveBrowserViewOwner?: Parameters<typeof createBrowserWindow>[0]["resolveBrowserViewOwner"];
}) {
  const win = createBrowserWindow({
    iconPath: options.iconPath,
    preloadPath: options.preloadPath,
    bootstrap: {
      restoreSession: options.bootstrap?.restoreSession ?? true,
      supportsSettings: options.bootstrap?.supportsSettings ?? true,
      initialWorkspacePath: options.bootstrap?.initialWorkspacePath,
      initialWorkspacePurpose: options.bootstrap?.initialWorkspacePurpose,
      unavailableWorkspacePath: options.bootstrap?.unavailableWorkspacePath,
    },
    logger: options.logger,
    deviceMid: options.deviceMid,
    initialDesktopZoomLevel: options.initialDesktopZoomLevel,
    initialWindowSize: options.initialWindowSize,
    currentApplicationLocale: options.currentApplicationLocale,
    resolveBrowserViewOwner: options.resolveBrowserViewOwner,
  });
  const label = `local-${win.webContents.id}`;

  if (options.persistWindowSize) {
    attachDesktopWindowSizePersistence(win, options.persistWindowSize, (error) => {
      options.logger.warn("[desktop-window] failed to persist main window size", error);
    });
  }

  if (process.platform === "darwin") {
    win.on("close", (event) => {
      if (
        handleDarwinWindowCloseRequest({
          win,
          forceQuit: options.forceQuitRef.current,
          label,
          logger: options.logger,
        })
      ) {
        event.preventDefault();
      }
    });
  } else if (options.handleBeforeClose) {
    win.on("close", (event) => {
      if (options.handleBeforeClose?.(win, label)) {
        event.preventDefault();
      }
    });
  }

  const wcId = win.webContents.id;
  // 资源采样把主窗口 renderer 归 renderer_main；辅助窗口与 DevTools 归 chromium_other。
  registerMainApplicationWindow(wcId);
  win.webContents.on("dom-ready", () => {
    options.logger.info(`[createWindow] dom-ready fired (${label})`);

    if (process.platform === "win32" && !win.isDestroyed()) {
      win.show();
      win.focus();
    }

    // 幂等拉起应用级桥进程（renderer 用 query 里的 bridgeWsUrl 直连）。
    try {
      ensureBridgeHostProcess({
        info: options.logger.info,
        warn: options.logger.warn,
        error: (...args: unknown[]) => options.logger.warn("[bridge-host]", ...args),
      });
    } catch (error) {
      options.logger.warn(`[createWindow] 桥进程拉起失败 (${label})：`, error);
    }
    options.syncAutoUpdaterStateToWindow(win);
    options.syncReadyUpdateToWindow(win);
    options.syncPostUpdateReleaseNotesToWindow(win);
  });

  win.on("closed", () => {
    unregisterMainApplicationWindow(wcId);
    options.logger.info(`[createWindow] window closed (${label})`);
  });

  return win;
}

export function showCurrentWindowFromDock(primaryWindowCoordinator: {
  ensurePrimaryWindow(reason: string): Promise<void>;
}) {
  if (process.platform === "darwin") {
    app.show();
  }

  void primaryWindowCoordinator.ensurePrimaryWindow("dock-show-current-window");
}

export function focusWorkspaceInExistingWindow(
  path: string,
  windowWorkspaceMap: Map<number, Set<string>>,
  options?: { skipWindowId?: number },
): { activated: boolean; winId?: number } {
  for (const [winId, pathSet] of windowWorkspaceMap) {
    if (options?.skipWindowId === winId) {
      continue;
    }
    if (!pathSet.has(path)) {
      continue;
    }

    const existingWin = BrowserWindow.fromId(winId);
    if (existingWin && !existingWin.isDestroyed()) {
      if (existingWin.isMinimized()) {
        existingWin.restore();
      }
      existingWin.focus();
      existingWin.webContents.send(PlatformChannels.FocusTab, path);
      return { activated: true, winId };
    }

    windowWorkspaceMap.delete(winId);
  }

  return { activated: false };
}

export function syncApplicationUnreadBadge(windowUnreadCountMap: Map<number, number>) {
  syncUnreadBadgeForPlatform({
    platform: process.platform,
    totalUnreadCount: maxWindowUnreadCounts(windowUnreadCountMap),
    setBadgeCount: (count) => {
      app.setBadgeCount(count);
    },
    // 窗口 overlay 徽章装饰面（上游 Windows 任务栏角标图）不在 Juscite 壳范围：no-op，Dock 计数语义不变。
    applyOverlay: () => {},
  });
}

export function handleWindowUnreadCountSync(
  win: BrowserWindow | null,
  payload: unknown,
  windowUnreadCountMap: Map<number, number>,
  logger: { warn: (...args: unknown[]) => void },
) {
  const unreadCount = parseWindowUnreadCount(payload);
  if (unreadCount == null) {
    logger.warn("[sync-window-unread-count] invalid payload:", payload);
    return false;
  }

  if (!win) {
    return false;
  }

  if (unreadCount === 0) {
    windowUnreadCountMap.delete(win.id);
  } else {
    windowUnreadCountMap.set(win.id, unreadCount);
  }
  syncApplicationUnreadBadge(windowUnreadCountMap);
  return true;
}

export function configureDockMenu(getLabel: () => string, onShowCurrentWindow: () => void) {
  if (process.platform !== "darwin" || app.dock == null) {
    return;
  }

  const dockMenu = Menu.buildFromTemplate([
    {
      label: getLabel(),
      click: onShowCurrentWindow,
    },
  ]);

  app.dock.setMenu(dockMenu);
}

export function handleDesktopWindowCloseRequest(options: {
  platform: NodeJS.Platform;
  forceQuit: boolean;
  explicitQuitRequested?: boolean;
  closeToTray?: boolean;
  /**
   * Linux 关闭驻留的托盘能力（spec：docs/desktop/linux-close-to-tray.md）。
   * GNOME 等无 StatusNotifierWatcher 的桌面托盘不渲染且不报错，必须在隐藏前显式确认能力；
   * 空值按"不可用"安全默认，走确认退出路径，避免窗口隐藏后失联。
   */
  closeToTraySupported?: boolean;
  isLastWindow: boolean;
  label: string;
  logger: { info: (...args: unknown[]) => void };
  shouldConfirmQuit?: boolean;
  confirmQuit: () => boolean;
  requestQuit: () => void;
  hideWindow?: () => void;
}) {
  // CR 修复:win32 不能短路丢弃 closeToTraySupported——它承载 resolveCloseToTraySupported
  // 的合并裁决(Windows=托盘实例创建成功)。托盘创建失败时隐藏窗口即失联,与 spec
  // "关窗分支与设置页能力查询都读同一合并结果"保持一致。
  const canHideToTray =
    (options.platform === "win32" || options.platform === "linux") &&
    options.closeToTraySupported === true;
  if (
    canHideToTray &&
    options.closeToTray &&
    !options.forceQuit &&
    !options.explicitQuitRequested
  ) {
    options.logger.info(`[createWindow] window close hidden to tray (${options.label})`);
    options.hideWindow?.();
    return true;
  }

  if (options.platform === "darwin" || options.forceQuit || !options.isLastWindow) {
    return false;
  }

  if (options.shouldConfirmQuit === false) {
    options.logger.info(
      `[createWindow] last window close skipped confirmation, quitting app (${options.label})`,
    );
    options.requestQuit();
    return true;
  }

  if (!options.confirmQuit()) {
    options.logger.info(`[createWindow] last window close canceled by user (${options.label})`);
    return true;
  }

  options.logger.info(
    `[createWindow] last window close confirmed, quitting app (${options.label})`,
  );
  options.requestQuit();
  return true;
}

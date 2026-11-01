import { recordArmsCustomEventForE2E } from "@zcode/ui";
import { DesktopCommandIds, buildLocalMediaPreviewUrl, type IPlatformService } from "@zcode/shared";

import { desktopBrowserPlatformBridge } from "./desktopBrowserPlatformBridge.js";
import { createDesktopPluginSandboxPlatform } from "./plugin-sandbox/desktopPluginSandboxPlatform.js";

/**
 * worktree @zcode/client globals（M1 底座裁剪版）未覆盖本壳 preload 的全部暴露面；
 * 这里按 packages/desktop/src/preload/index.ts 的实际实现补齐缺失成员形状。
 */
type DesktopZcodeBridgeExtras = Required<
  Pick<
  IPlatformService,
  | "createTempTextAttachment"
  | "loadMcpFromUserDirectory"
  | "saveMcpToUserDirectory"
  | "migrateLegacyCommonMcp"
  | "onShareImport"
  | "reportArmsCustomEvent"
  | "reportLocalTtftBatch"
  | "setShortcutRecordingActive"
  | "onCloseActiveContextRequest"
  | "onOpenFeedbackDialog"
  | "onOpenTicketsPanel"
  | "getWindowControlsOverlayMetrics"
  | "onWindowControlsOverlayChanged"
  | "getZCodeStdioTapDevState"
  >
>;

export function createDesktopPlatform(options: {
  isLocalDevelopmentRuntime: boolean;
}): IPlatformService {
  const zcodeBridge = window.zcode as NonNullable<Window["zcode"]> & DesktopZcodeBridgeExtras;
  return {
    canSelectFilePath: true,
    pluginSandbox: createDesktopPluginSandboxPlatform(),
    createLocalMediaPreviewUrl: buildLocalMediaPreviewUrl,
    isLocalDevelopmentRuntime: options.isLocalDevelopmentRuntime,
    selectDirectory: () => zcodeBridge.selectDirectory(),
    selectFile: () => zcodeBridge.selectFile(),
    selectFiles: () => zcodeBridge.selectFiles?.() ?? Promise.resolve([]),
    createTempTextAttachment: (payload) => zcodeBridge.createTempTextAttachment(payload),
    materializeWorkflowArtifactFile: (payload) =>
      zcodeBridge.materializeWorkflowArtifactFile(payload),
    onRemoteConnectionLog: (handler) => zcodeBridge.onRemoteConnectionLog(handler),
    onRemoteSessionClosed: (handler) => zcodeBridge.onRemoteSessionClosed(handler),
    onBotRemoteWorkspaceReconnected: (handler) =>
      zcodeBridge.onBotRemoteWorkspaceReconnected(handler),
    activateOrSetWorkspace: (path) =>
      zcodeBridge.activateOrSetWorkspace?.(path) ?? Promise.resolve({ activated: false }),
    connectRemote: (remoteOptions, requestId, context) =>
      zcodeBridge.connectRemote(remoteOptions, requestId, context),
    cancelPendingRemoteConnection: (requestId) =>
      zcodeBridge.cancelPendingRemoteConnection?.(requestId) ?? Promise.resolve(),
    bindRemoteWorkspaceSessionContext: (context) =>
      zcodeBridge.bindRemoteWorkspaceSessionContext?.(context).then(() => undefined) ??
      Promise.resolve(),
    startWebRemoteControl: (context) => zcodeBridge.startWebRemoteControl(context),
    refreshWebRemoteControlPairing: (context) =>
      zcodeBridge.refreshWebRemoteControlPairing(context),
    stopWebRemoteControl: () => zcodeBridge.stopWebRemoteControl(),
    getWebRemoteControlStatus: () => zcodeBridge.getWebRemoteControlStatus(),
    onWebRemoteControlStatusChanged: (handler) =>
      zcodeBridge.onWebRemoteControlStatusChanged?.(handler) ?? (() => {}),
    disposeRemoteSession: (sessionId) => zcodeBridge.disposeRemoteSession(sessionId),
    isDockerAvailable: () => zcodeBridge.isDockerAvailable(),
    listWSLDistros: () => zcodeBridge.listWSLDistros(),
    listDockerContainers: () => zcodeBridge.listDockerContainers(),
    listSSHConfigAliases: () => zcodeBridge.listSSHConfigAliases(),
    loadMcpFromUserDirectory: (payload) => zcodeBridge.loadMcpFromUserDirectory(payload),
    saveMcpToUserDirectory: (payload) => zcodeBridge.saveMcpToUserDirectory(payload),
    migrateLegacyCommonMcp: (payload) => zcodeBridge.migrateLegacyCommonMcp(payload),
    openExternal: (url) => zcodeBridge.openExternal(url),
    openFeedback: () => zcodeBridge.executeDesktopCommand(DesktopCommandIds.OpenFeedback),
    openCommunity: () => zcodeBridge.executeDesktopCommand(DesktopCommandIds.OpenCommunity),
    canOpenCommunity: (locale) => zcodeBridge.canOpenCommunity(locale),
    openInFileManager: (path) => zcodeBridge.openInFileManager(path),
    openExternalFile: (path) => zcodeBridge.openExternalFile(path),
    openCuaPermissionOnboarding: zcodeBridge.openCuaPermissionOnboarding
      ? (permissionOptions) =>
          zcodeBridge.openCuaPermissionOnboarding?.(permissionOptions) ??
          Promise.resolve({ success: false, error: "not_supported" })
      : undefined,
    prepareCuaHelperPermissionDrag: zcodeBridge.prepareCuaHelperPermissionDrag
      ? () =>
          zcodeBridge.prepareCuaHelperPermissionDrag?.() ??
          Promise.resolve({ success: false, error: "not_supported" })
      : undefined,
    startCuaHelperPermissionDrag: zcodeBridge.startCuaHelperPermissionDrag
      ? () => zcodeBridge.startCuaHelperPermissionDrag?.()
      : undefined,
    registerOAuthState: (payload) => zcodeBridge.registerOAuthState(payload),
    onOAuthCallback: (callback) => zcodeBridge.onOAuthCallback(callback),
    onPaymentCallback: (callback) => zcodeBridge.onPaymentCallback(callback),
    onShareImport: (callback) => zcodeBridge.onShareImport?.(callback) ?? (() => {}),
    notifyRendererReady: () => zcodeBridge.notifyRendererReady(),
    reportTelemetryEvent: (payload) => zcodeBridge.reportTelemetryEvent(payload),
    reportArmsCustomEvent: (payload) => {
      recordArmsCustomEventForE2E(payload);
      return zcodeBridge.reportArmsCustomEvent(payload);
    },
    getRendererActionTraceConfig: zcodeBridge.getRendererActionTraceConfig
      ? () => zcodeBridge.getRendererActionTraceConfig!()
      : undefined,
    onRendererActionTraceConfigChanged: zcodeBridge.onRendererActionTraceConfigChanged
      ? (callback) => zcodeBridge.onRendererActionTraceConfigChanged!(callback)
      : undefined,
    reportLocalTtftBatch: (batch) => zcodeBridge.reportLocalTtftBatch(batch),
    reportRendererActionTraceBatch: zcodeBridge.reportRendererActionTraceBatch
      ? (batch) => zcodeBridge.reportRendererActionTraceBatch!(batch)
      : undefined,
    reportRendererHeapSample: zcodeBridge.reportRendererHeapSample
      ? (sample) => zcodeBridge.reportRendererHeapSample!(sample)
      : undefined,
    showTaskNotification: (payload) => zcodeBridge.showTaskNotification(payload),
    syncWindowTabs: (paths) => zcodeBridge.syncWindowTabs(paths),
    syncWebRemoteControlWorkspaces: (workspaces) =>
      zcodeBridge.syncWebRemoteControlWorkspaces?.(workspaces),
    syncWebRemoteControlTasks: (tasks) => zcodeBridge.syncWebRemoteControlTasks?.(tasks),
    onWebRemoteControlReconnectWorkspace: (handler) =>
      zcodeBridge.onWebRemoteControlReconnectWorkspace?.(handler) ?? (() => {}),
    syncWindowUnreadCount: (count) => zcodeBridge.syncWindowUnreadCount(count),
    syncActiveTaskSession: (sessionId) => zcodeBridge.syncActiveTaskSession(sessionId),
    syncAppSettings: (patch) => zcodeBridge.syncAppSettings?.(patch),
    // 桥缺失（旧 preload 升级窗口）时按 supported 兜底，与 Windows 现状一致，设置开关可用。
    getCloseToTrayCapability: () =>
      zcodeBridge.getCloseToTrayCapability?.() ??
      Promise.resolve({ supported: true, gnomeLikeWithoutTray: false }),
    // 功能 #28 桌宠：桥缺失（旧 preload）时按离线态兜底，设置页可读不可写坏。
    getPetStatus: () => zcodeBridge.getPetStatus?.() ?? Promise.reject(new Error("pet bridge unavailable")),
    updatePetConfig: (patch) =>
      zcodeBridge.updatePetConfig?.(patch) ?? Promise.reject(new Error("pet bridge unavailable")),
    onPetStatus: (handler) => zcodeBridge.onPetStatus?.(handler) ?? (() => {}),
    reportPetRunEvent: (event) => zcodeBridge.reportPetRunEvent?.(event),
    setShortcutRecordingActive: (active) => zcodeBridge.setShortcutRecordingActive?.(active),
    onFocusTab: (handler) => zcodeBridge.onFocusTab(handler),
    onNewTab: (handler) => zcodeBridge.onNewTab(handler),
    onCloseActiveContextRequest: (handler) =>
      zcodeBridge.onCloseActiveContextRequest?.(handler) ?? (() => {}),
    onOpenBrowserUrl: (handler) => zcodeBridge.onOpenBrowserUrl?.(handler) ?? (() => {}),
    onEmbeddedBrowserPermissionPrompt: (handler) =>
      zcodeBridge.onEmbeddedBrowserPermissionPrompt?.(handler) ?? (() => {}),
    resolveEmbeddedBrowserPermissionPrompt: (request) =>
      zcodeBridge.resolveEmbeddedBrowserPermissionPrompt?.(request),
    getEmbeddedBrowserSitePermissions: () =>
      zcodeBridge.getEmbeddedBrowserSitePermissions?.() ?? Promise.resolve({}),
    setEmbeddedBrowserSitePermission: (request) =>
      zcodeBridge.setEmbeddedBrowserSitePermission?.(request) ?? Promise.resolve({}),
    clearEmbeddedBrowserSitePermissions: () =>
      zcodeBridge.clearEmbeddedBrowserSitePermissions?.() ?? Promise.resolve({}),
    resetEmbeddedBrowserSitePermission: (request) =>
      zcodeBridge.resetEmbeddedBrowserSitePermission?.(request) ?? Promise.resolve({}),
    onBrowserViewScreenshotSurfacePrepare: (handler) =>
      zcodeBridge.onBrowserViewScreenshotSurfacePrepare?.(handler) ?? (() => {}),
    onBrowserViewScreenshotSurfaceRelease: (handler) =>
      zcodeBridge.onBrowserViewScreenshotSurfaceRelease?.(handler) ?? (() => {}),
    browserViewScreenshotSurfaceReady: (payload) =>
      zcodeBridge.browserViewScreenshotSurfaceReady?.(payload),
    ...desktopBrowserPlatformBridge,
    onNewTask: (handler) => zcodeBridge.onNewTask(handler),
    onOpenWorkspace: (handler) => {
      // 开发态或升级后的旧窗口可能仍运行未暴露 onOpenWorkspace 的 preload，
      // renderer 直接调用会在启动时崩溃。这里和 activateOrSetWorkspace 一样做兼容兜底，
      // 缺少该 bridge 时只禁用原生菜单回调，不影响应用继续打开。
      return zcodeBridge.onOpenWorkspace?.(handler) ?? (() => {});
    },
    onOpenWorkspacePath: (handler) => zcodeBridge.onOpenWorkspacePath?.(handler) ?? (() => {}),
    onOpenFeedbackDialog: (handler) => zcodeBridge.onOpenFeedbackDialog?.(handler) ?? (() => {}),
    onOpenTicketsPanel: (handler) => zcodeBridge.onOpenTicketsPanel?.(handler) ?? (() => {}),
    onWindowFullscreenChanged: (handler) => zcodeBridge.onWindowFullscreenChanged(handler),
    getDesktopWindowChromeState: zcodeBridge.getDesktopWindowChromeState
      ? () => zcodeBridge.getDesktopWindowChromeState!()
      : undefined,
    onDesktopWindowChromeStateChanged: zcodeBridge.onDesktopWindowChromeStateChanged
      ? (handler) => zcodeBridge.onDesktopWindowChromeStateChanged!(handler)
      : undefined,
    getWindowControlsOverlayMetrics: () => zcodeBridge.getWindowControlsOverlayMetrics?.() ?? null,
    onWindowControlsOverlayChanged: (handler) =>
      zcodeBridge.onWindowControlsOverlayChanged?.(handler) ?? (() => {}),
    getDesktopZoomLevel: () =>
      zcodeBridge.getDesktopZoomLevel?.() ?? Promise.resolve({ zoomLevel: 0 }),
    onDesktopZoomLevelChanged: (handler) =>
      zcodeBridge.onDesktopZoomLevelChanged?.(handler) ?? (() => {}),
    onTaskNotificationClick: (handler) => zcodeBridge.onTaskNotificationClick(handler),
    exportLogs: () => zcodeBridge.exportLogs(),
    captureWindowScreenshot: () =>
      zcodeBridge.captureWindowScreenshot?.() ?? Promise.resolve(null),
    onUpdateReady: (callback) => zcodeBridge.onUpdateReady(callback),
    onUpdateCheckResult: (callback) => zcodeBridge.onUpdateCheckResult(callback),
    onUpdateStateChanged: (callback) => zcodeBridge.onUpdateStateChanged?.(callback) ?? (() => {}),
    getUpdateState: () =>
      zcodeBridge.getUpdateState?.() ?? Promise.resolve({ kind: "idle", enabled: true }),
    downloadUpdate: () => zcodeBridge.downloadUpdate?.() ?? Promise.resolve(),
    cancelUpdateDownload: () => zcodeBridge.cancelUpdateDownload?.() ?? Promise.resolve(),
    openUpdateStatusWindow: () => zcodeBridge.openUpdateStatusWindow?.() ?? Promise.resolve(),
    getAutoUpdatePreferences: () =>
      zcodeBridge.getAutoUpdatePreferences?.() ??
      Promise.resolve({ autoDownloadAndInstallUpdates: false }),
    setAutoDownloadAndInstallUpdates: (enabled) =>
      zcodeBridge.setAutoDownloadAndInstallUpdates?.(enabled) ?? Promise.resolve(),
    getDesktopSessionActivity: () =>
      zcodeBridge.getDesktopSessionActivity?.() ??
      Promise.resolve({ runningAgentSessionCount: 0 }),
    getZCodeStdioTapDevState: () =>
      zcodeBridge.getZCodeStdioTapDevState?.() ??
      Promise.resolve({ enabled: false, visible: false, logDir: "", statePath: "" }),
    onSettingsChanged: (callback) => zcodeBridge.onSettingsChanged?.(callback) ?? (() => {}),
    onApplicationLocaleChanged: (callback) =>
      zcodeBridge.onApplicationLocaleChanged?.(callback) ?? (() => {}),
    onPostUpdateReleaseNotes: (callback) => zcodeBridge.onPostUpdateReleaseNotes(callback),
    acknowledgePostUpdateReleaseNotes: (version) =>
      zcodeBridge.acknowledgePostUpdateReleaseNotes(version),
    skipUpdateVersion: (version) => zcodeBridge.skipUpdateVersion?.(version) ?? Promise.resolve(),
    quitAndInstallUpdate: () => zcodeBridge.quitAndInstallUpdate(),
    getInstalledEditors: () => zcodeBridge.getInstalledEditors(),
    getApplicationIcon: (bundleId) =>
      zcodeBridge.getApplicationIcon?.(bundleId) ?? Promise.resolve(null),
    openInEditor: (editorId, path, editorOptions) =>
      zcodeBridge.openInEditor(editorId, path, editorOptions),
    executeDesktopCommand: (command) => zcodeBridge.executeDesktopCommand(command),
    setApplicationLocale: (locale) => zcodeBridge.setApplicationLocale(locale),
    getSystemLocale: () =>
      zcodeBridge.getSystemLocale?.() ??
      Promise.resolve(navigator.language.toLowerCase().startsWith("zh") ? "zh-CN" : "en-US"),
    setTitleBarTheme: (theme) => zcodeBridge.setTitleBarTheme(theme),
    getDeviceId: () =>
      (window as Window & { __ZCODE_DEVICE_ID__?: string }).__ZCODE_DEVICE_ID__ ?? "",
  };
}

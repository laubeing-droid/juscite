// 功能 #28 桌宠 · pet 窗口专用 preload（RE-28 §3.3 渲染层桥）。
// 面=petHost 窄接口：状态/工作区/步驱动下行 + 命中/单击/移动/步回执/资产错误上行。
// 与主进程 desktop/pet/window.ts 的 ipcMain 面一一对应；不暴露 node 能力。

import { contextBridge, ipcRenderer } from "electron";

export interface PetStepEnvelope {
  id: string;
  step: {
    kind: "playAction" | "moveByPath";
    animation?: string;
    playback?: { kind: "once" | "loopForDuration"; durationMs: number; clipMs?: number };
    timeoutMs?: number;
    path?: Array<{ kind: string }>;
  };
}

export interface PetHostBridge {
  ready(): void;
  onStatus(handler: (status: unknown) => void): () => void;
  onWorkAreas(handler: (areas: unknown) => void): () => void;
  /** 主进程步驱动（宏序列播放）；handler 收到后执行动画并 ackStep。 */
  onStep(handler: (envelope: PetStepEnvelope) => void): () => void;
  onInterrupt(handler: () => void): () => void;
  ackStep(id: string, outcome: { kind: "completed" | "interrupted" | "failed" | "unavailable" }): void;
  /** 命中区翻转穿透（B22）：true=指针在本体上（收鼠标），false=穿透。 */
  setHover(hovering: boolean): void;
  /** 单击本体=唤出主窗口（对拍 19）。 */
  click(): void;
  /** 拖拽/抛射位置写入（主进程取整落窗）。 */
  move(x: number, y: number): void;
  /** 资产缺失/损坏可见提示的上行诊断（B15）。 */
  reportAssetError(message: string): void;
  getWorkAreas(): Promise<unknown>;
  /** 窗口当前 bounds（拖拽/抛射坐标基准）。 */
  getBounds(): Promise<{ x: number; y: number; width: number; height: number }>;
  /** 飞行静止后请求工作区夹取（B23）。 */
  requestClamp(): void;
}

const bridge: PetHostBridge = {
  ready: () => ipcRenderer.send("pet:ready"),
  onStatus: (handler) => {
    const wrapped = (_e: unknown, status: unknown) => handler(status);
    ipcRenderer.on("pet:status", wrapped);
    return () => ipcRenderer.removeListener("pet:status", wrapped);
  },
  onWorkAreas: (handler) => {
    const wrapped = (_e: unknown, areas: unknown) => handler(areas);
    ipcRenderer.on("pet:work-areas", wrapped);
    return () => ipcRenderer.removeListener("pet:work-areas", wrapped);
  },
  onStep: (handler) => {
    const wrapped = (_e: unknown, envelope: PetStepEnvelope) => handler(envelope);
    ipcRenderer.on("pet:step", wrapped);
    return () => ipcRenderer.removeListener("pet:step", wrapped);
  },
  onInterrupt: (handler) => {
    const wrapped = () => handler();
    ipcRenderer.on("pet:interrupt", wrapped);
    return () => ipcRenderer.removeListener("pet:interrupt", wrapped);
  },
  ackStep: (id, outcome) => ipcRenderer.send("pet:step-done", { id, outcome }),
  setHover: (hovering) => ipcRenderer.send("pet:hover", hovering),
  click: () => ipcRenderer.send("pet:click"),
  move: (x, y) => ipcRenderer.send("pet:move", { x, y }),
  reportAssetError: (message) => ipcRenderer.send("pet:asset-error", message),
  getWorkAreas: () => ipcRenderer.invoke("pet:work-areas"),
  getBounds: () => ipcRenderer.invoke("pet:bounds"),
  requestClamp: () => ipcRenderer.send("pet:clamp"),
};

contextBridge.exposeInMainWorld("petHost", bridge);

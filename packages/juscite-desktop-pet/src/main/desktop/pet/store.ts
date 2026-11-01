// 功能 #28 桌宠 · PetConfig 持久化 + PetStatus 推导（RE-28 §3.1 数据模型）。
// 落盘 %APPDATA%\Juscite\desktop\pet.json（目录 0700/文件 0600，随壳 store 机制；
// Electron 侧路径由 window.ts 注入 app.getPath("userData")，本文件不 import electron，
// 纯 Node 可合成自测）。visible≡enabled（dsh B6 历史字段语义）；不落盘字段见 PetStatusPayload。

import { existsSync, mkdirSync, readFileSync, renameSync, writeFileSync } from "node:fs";
import { dirname } from "node:path";
import type {
  PetBubbleState,
  PetConfig,
  PetConfigPatch,
  PetMotion,
  PetStatusPayload,
} from "@zcode/shared";
import {
  PET_SIZE_DEFAULT_PERCENT,
  clampSizePercent,
  petBodyRect,
  petWindowLogicalSize,
} from "./geometry.js";

export type { PetBubbleState, PetConfig, PetConfigPatch, PetStatusPayload };

export const PET_CONFIG_DEFAULTS: PetConfig = {
  enabled: true,
  alwaysOnTop: true,
  rememberPosition: true,
  sizePercent: PET_SIZE_DEFAULT_PERCENT,
  throwEnabled: false,
  activeSkin: "default",
};

function toBoolean(value: unknown, fallback: boolean): boolean {
  return typeof value === "boolean" ? value : fallback;
}

function toStringSkin(value: unknown): string {
  return typeof value === "string" && value.trim() !== "" ? value : PET_CONFIG_DEFAULTS.activeSkin;
}

/** 逐字段清洗：文件里多出的键/错型一律回落默认（fail-closed 不猜）。 */
export function sanitizePetConfig(raw: unknown): PetConfig {
  const source = typeof raw === "object" && raw !== null ? (raw as Record<string, unknown>) : {};
  return {
    enabled: toBoolean(source.enabled, PET_CONFIG_DEFAULTS.enabled),
    alwaysOnTop: toBoolean(source.alwaysOnTop, PET_CONFIG_DEFAULTS.alwaysOnTop),
    rememberPosition: toBoolean(source.rememberPosition, PET_CONFIG_DEFAULTS.rememberPosition),
    sizePercent: clampSizePercent(Number(source.sizePercent ?? PET_CONFIG_DEFAULTS.sizePercent)),
    throwEnabled: toBoolean(source.throwEnabled, PET_CONFIG_DEFAULTS.throwEnabled),
    activeSkin: toStringSkin(source.activeSkin),
  };
}

export function readPetConfigFile(filePath: string): PetConfig {
  if (!existsSync(filePath)) return { ...PET_CONFIG_DEFAULTS };
  try {
    return sanitizePetConfig(JSON.parse(readFileSync(filePath, "utf-8")));
  } catch {
    // 文件缺失/损坏=默认不报错（XTLaw config.rs A8 同语义）；下次保存覆盖。
    return { ...PET_CONFIG_DEFAULTS };
  }
}

/** 原子写（temp+rename）；目录 0700/文件 0600 尽力而为（Windows 上 chmod 语义弱化为只读位）。 */
export function writePetConfigFile(filePath: string, config: PetConfig): void {
  mkdirSync(dirname(filePath), { recursive: true, mode: 0o700 });
  const temp = `${filePath}.tmp`;
  writeFileSync(temp, `${JSON.stringify(config, null, 2)}\n`, { encoding: "utf-8", mode: 0o600 });
  renameSync(temp, filePath);
}

export interface PetStoreEvents {
  /** 任意配置/运行态变更后回调（主进程据此广播 pet://status 给 pet 窗与设置面）。 */
  onChange: (status: PetStatusPayload) => void;
}

export interface PetStore {
  getConfig(): PetConfig;
  getStatus(): PetStatusPayload;
  /** 合法字段合并落盘；非法值钳位（sizePercent）。 */
  update(patch: PetConfigPatch): PetStatusPayload;
  /** 运行态投影（不落盘）：motion 与气泡由驱动流写入。 */
  setMotion(motion: PetMotion): void;
  setBubble(bubble: PetBubbleState | null): void;
}

export function createPetStore(options: { file: string; events: PetStoreEvents }): PetStore {
  let config = readPetConfigFile(options.file);
  let motion: PetMotion = "idle";
  let bubble: PetBubbleState | null = null;

  const buildStatus = (): PetStatusPayload => {
    const window = petWindowLogicalSize(config.sizePercent);
    return {
      config: { ...config },
      visible: config.enabled,
      motion,
      bubble: bubble ? { ...bubble } : null,
      geometry: { window, body: petBodyRect(window, config.sizePercent) },
    };
  };

  const emit = (): PetStatusPayload => {
    const status = buildStatus();
    options.events.onChange(status);
    return status;
  };

  return {
    getConfig: () => ({ ...config }),
    getStatus: buildStatus,
    update(patch: PetConfigPatch) {
      const next = sanitizePetConfig({ ...config, ...patch });
      config = next;
      try {
        writePetConfigFile(options.file, config);
      } catch (error) {
        // 落盘失败不阻断内存态生效（热生效优先），错误随诊断日志由调用方记。
        options.events.onChange(buildStatus());
        throw error instanceof Error ? error : new Error(String(error));
      }
      return emit();
    },
    setMotion(next: PetMotion) {
      if (motion === next) return;
      motion = next;
      emit();
    },
    setBubble(next: PetBubbleState | null) {
      const changed =
        (bubble === null) !== (next === null) ||
        (bubble !== null && next !== null && bubble.id !== next.id);
      bubble = next ? { ...next } : null;
      if (changed) emit();
    },
  };
}

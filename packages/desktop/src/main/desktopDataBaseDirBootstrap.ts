import { existsSync, readFileSync } from "node:fs";
import { homedir } from "node:os";
import { join } from "node:path";
import { setDataBaseDir } from "@zcode/services/node";

/**
 * 换宿主（v4 §1.3）：Juscite 的数据目录 = %APPDATA%\Juscite。
 * settings 落 %APPDATA%\Juscite\config\setting.json（与桥 setting 面同根）；
 * 未显式配置 dataBaseDir 时默认 %APPDATA%\Juscite\data（services 侧在其下再拼 .zcode/v2，
 * 该内层段由 @zcode/services 收口，不在本包轨道内改动）。
 */
export function resolveJusciteAppDataDir(): string {
  return process.env["APPDATA"] ?? join(homedir(), "AppData", "Roaming");
}

export function resolveBootstrapSettingsFile(): string {
  return join(resolveJusciteAppDataDir(), "Juscite", "config", "setting.json");
}

export function extractBootstrapDataBaseDir(rawValue: unknown): string | null {
  if (!rawValue || typeof rawValue !== "object") {
    return null;
  }

  const dataBaseDir = (rawValue as { dataBaseDir?: unknown }).dataBaseDir;
  if (typeof dataBaseDir !== "string") {
    return null;
  }

  const trimmed = dataBaseDir.trim();
  return trimmed.length > 0 ? trimmed : null;
}

function readBootstrapDataBaseDirFromDisk(): string | null {
  const settingsFile = resolveBootstrapSettingsFile();
  if (!existsSync(settingsFile)) {
    return null;
  }

  try {
    const raw = readFileSync(settingsFile, "utf-8");
    return extractBootstrapDataBaseDir(JSON.parse(raw));
  } catch {
    return null;
  }
}

export function applyEarlyDataBaseDirBootstrap(): string {
  const dataBaseDir =
    readBootstrapDataBaseDirFromDisk() ?? join(resolveJusciteAppDataDir(), "Juscite", "data");
  // 启动早期就把 dataBaseDir 注入进来，避免 logger / crashReporter 先按默认 HOME 建目录，
  // 导致后续再切换到自定义目录时，日志和 crash dump 落在两套路径里。
  setDataBaseDir(dataBaseDir);
  return dataBaseDir;
}

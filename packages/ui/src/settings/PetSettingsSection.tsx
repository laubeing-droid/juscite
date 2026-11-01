// 功能 #28 桌宠 · 设置分区（RE-28 §3.3 设置面）。
// 五控件：启用/窗口置顶/记住位置三开关 + 大小滑条（50..200 步进 5）+ 抛射开关。
// XTLaw 行为面：行为开关（置顶/记住位置）在桌宠禁用或"启用"保存中时禁用且置灰（A10）；
// 保存逐字段 pending、失败逐字段错误文案（A9）；滑条拖动中的本地值不被回包覆盖（B9）。
// 状态订阅经 pet://status（onPetStatus），写经 updatePetConfig；仅桌面壳实现（Web 无桥不渲染）。

import { useCallback, useEffect, useRef, useState } from "react";
import { Cat } from "lucide-react";
import { Switch } from "@/components/ui/switch.js";
import { SettingsGroupCard, SettingsRangeControl, SettingsRow } from "@/settings/SettingsPageParts.js";
import type { PetConfigPatch, PetStatusPayload } from "@zcode/shared";

interface PetPlatform {
  getPetStatus?: () => Promise<PetStatusPayload>;
  updatePetConfig?: (patch: PetConfigPatch) => Promise<PetStatusPayload>;
  onPetStatus?: (handler: (status: PetStatusPayload) => void) => () => void;
}

const SIZE_MIN = 50;
const SIZE_MAX = 200;
const SIZE_STEP = 5;

export function PetSettingsSection(props: { platform: PetPlatform | null | undefined }) {
  const platform = props.platform;
  const [status, setStatus] = useState<PetStatusPayload | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  // 逐字段 pending/失败（A9）。
  const [pendingFields, setPendingFields] = useState<Set<string>>(new Set());
  const [failedField, setFailedField] = useState<string | null>(null);
  // 滑条拖动中的本地值（B9：拖动中不被回包覆盖）。
  const [localSize, setLocalSize] = useState<number | null>(null);
  const sizeCommitTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const applyPatch = useCallback(
    async (field: string, patch: PetConfigPatch) => {
      if (!platform?.updatePetConfig) return;
      setFailedField(null);
      setPendingFields((prev) => new Set(prev).add(field));
      try {
        const next = await platform.updatePetConfig(patch);
        setStatus(next);
      } catch (error) {
        setFailedField(field);
        // 失败回真值：重拉权威状态。
        platform
          .getPetStatus?.()
          .then((fresh) => setStatus(fresh))
          .catch(() => undefined);
        setLocalSize(null);
        throw error instanceof Error ? error : new Error(String(error));
      } finally {
        setPendingFields((prev) => {
          const next = new Set(prev);
          next.delete(field);
          return next;
        });
      }
    },
    [platform],
  );

  useEffect(() => {
    if (!platform?.getPetStatus) {
      setLoadError("当前环境没有桌宠桥（仅桌面壳可用）");
      return;
    }
    let alive = true;
    platform
      .getPetStatus()
      .then((initial) => {
        if (alive) setStatus(initial);
      })
      .catch((e: Error) => {
        if (alive) setLoadError(e.message);
      });
    const unsubscribe = platform.onPetStatus?.((next) => {
      if (alive) setStatus(next);
    });
    return () => {
      alive = false;
      unsubscribe?.();
    };
  }, [platform]);

  const handleSizeChange = useCallback(
    (value: number) => {
      setLocalSize(value);
      if (sizeCommitTimer.current) clearTimeout(sizeCommitTimer.current);
      sizeCommitTimer.current = setTimeout(() => {
        sizeCommitTimer.current = null;
        void applyPatch("sizePercent", { sizePercent: value }).catch(() => undefined);
      }, 180);
    },
    [applyPatch],
  );

  useEffect(
    () => () => {
      if (sizeCommitTimer.current) clearTimeout(sizeCommitTimer.current);
    },
    [],
  );

  if (!platform?.getPetStatus) {
    return (
      <div className="space-y-6" data-testid="settings-pet-section">
        <SettingsGroupCard>
          <SettingsRow
            label="桌宠"
            description={loadError ?? "仅桌面壳可用；Web/远控端没有桌宠。"}
            control={<span className="text-ui-caption text-foreground-subtle">不可用</span>}
          />
        </SettingsGroupCard>
      </div>
    );
  }

  const config = status?.config;
  // A10：行为开关在桌宠禁用或"启用"保存中时禁用且置灰。
  const behaviorDisabled = !config?.enabled || pendingFields.has("enabled");
  const fieldPending = (field: string) => pendingFields.has(field);

  return (
    <div className="space-y-6" data-testid="settings-pet-section">
      <SettingsGroupCard>
        <SettingsRow
          label={
            <span className="flex items-center gap-2">
              <Cat className="size-4 text-foreground-subtle" />
              启用桌宠
            </span>
          }
          description={
            failedField === "enabled"
              ? "保存失败：桌宠桥没有应答，请重试。"
              : "关闭后桌宠窗口随即收起，重启后也保持关闭。"
          }
          control={
            <span className={fieldPending("enabled") ? "opacity-60" : undefined}>
              <Switch
                checked={config?.enabled ?? false}
                disabled={fieldPending("enabled")}
                onCheckedChange={(v) => void applyPatch("enabled", { enabled: v }).catch(() => undefined)}
                data-testid="settings-pet-enabled"
                aria-label="启用桌宠"
              />
            </span>
          }
        />
        <SettingsRow
          label="窗口置顶"
          description={failedField === "alwaysOnTop" ? "保存失败，请重试。" : "桌宠浮在其他窗口之上。"}
          control={
            <span className={behaviorDisabled ? "opacity-40" : undefined}>
              <Switch
                checked={config?.alwaysOnTop ?? false}
                disabled={behaviorDisabled || fieldPending("alwaysOnTop")}
                onCheckedChange={(v) =>
                  void applyPatch("alwaysOnTop", { alwaysOnTop: v }).catch(() => undefined)
                }
                data-testid="settings-pet-always-on-top"
                aria-label="窗口置顶"
              />
            </span>
          }
        />
        <SettingsRow
          label="记住位置"
          description={failedField === "rememberPosition" ? "保存失败，请重试。" : "重启后回到上次停留的屏幕位置。"}
          control={
            <span className={behaviorDisabled ? "opacity-40" : undefined}>
              <Switch
                checked={config?.rememberPosition ?? false}
                disabled={behaviorDisabled || fieldPending("rememberPosition")}
                onCheckedChange={(v) =>
                  void applyPatch("rememberPosition", { rememberPosition: v }).catch(() => undefined)
                }
                data-testid="settings-pet-remember-position"
                aria-label="记住位置"
              />
            </span>
          }
        />
      </SettingsGroupCard>
      <SettingsGroupCard>
        <SettingsRow
          label={`大小（${localSize ?? config?.sizePercent ?? 100}%）`}
          description={failedField === "sizePercent" ? "保存失败，请重试。" : "拖动即时生效，范围 50%–200%。"}
          control={
            <div data-testid="settings-pet-size">
              <SettingsRangeControl
                value={localSize ?? config?.sizePercent ?? 100}
                min={SIZE_MIN}
                max={SIZE_MAX}
                step={SIZE_STEP}
                onChange={handleSizeChange}
                valueLabel={`${localSize ?? config?.sizePercent ?? 100}%`}
              />
            </div>
          }
        />
        <SettingsRow
          label="抛射（把宠物扔出去）"
          description={failedField === "throwEnabled" ? "保存失败，请重试。" : "默认关。开启后快速甩动松手会把桌宠抛出去，落地弹几下自己停回屏幕里。"}
          control={
            <span className={behaviorDisabled ? "opacity-40" : undefined}>
              <Switch
                checked={config?.throwEnabled ?? false}
                disabled={behaviorDisabled || fieldPending("throwEnabled")}
                onCheckedChange={(v) =>
                  void applyPatch("throwEnabled", { throwEnabled: v }).catch(() => undefined)
                }
                data-testid="settings-pet-throw"
                aria-label="抛射"
              />
            </span>
          }
        />
      </SettingsGroupCard>
      {status?.config.enabled && status.windowAlive === false ? (
        <p className="text-ui-caption text-destructive" data-testid="settings-pet-window-alive-hint">
          桌宠窗口连续两次启动失败，已暂时收起；把「启用桌宠」关一下再打开即可重试。
        </p>
      ) : null}
      {status ? (
        <p className="text-ui-caption text-foreground-subtle" data-testid="settings-pet-motion">
          当前状态：{
            {
              idle: "待命中",
              thinking: "模型推理中",
              working: "工具执行中",
              awaitApproval: "等待授权确认或提问",
              success: "刚完成一次运行",
              cancelled: "运行已取消",
              failed: "需要查看错误",
              disconnected: "桌面端未连接",
            }[status.motion]
          }
        </p>
      ) : null}
    </div>
  );
}

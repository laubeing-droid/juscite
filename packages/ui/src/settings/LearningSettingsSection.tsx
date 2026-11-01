// 设置页·学习迭代分区（RE-18 J14：通用节内 3 控件）：总开关（默认开）/空闲等待下拉
// 5/15/30/60 分钟（默认 15，关总开关禁用）/学习时保持托盘运行（默认开，关总开关禁用）。
// 保存即 settingService.update 合并 patch（learningIteration additive 字段），桥运行时每轮
// tick 热读取（热 sync 等量）。托盘挂接随打包步骤接线，本面先落设置项与行为开关（§5 建议不做条）。
import { useCallback, useEffect, useState } from "react";
import { Switch } from "@/components/ui/switch.js";
import { SettingsGroupCard, SettingsRow } from "@/settings/SettingsPageParts.js";
import { useServices } from "@/hooks/useServices.js";

const IDLE_CHOICES = [5, 15, 30, 60];
interface LearningSettingsShape { enabled: boolean; idleMinutes: number; keepRunningInTray: boolean }

export function LearningSettingsSection() {
  const { settingService } = useServices();
  const [enabled, setEnabled] = useState(true);
  const [idleMinutes, setIdleMinutes] = useState(15);
  const [keepRunningInTray, setKeepRunningInTray] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    settingService.get()
      .then((s: unknown) => {
        if (!alive) return;
        const raw = (s as { learningIteration?: Partial<LearningSettingsShape> })?.learningIteration ?? {};
        setEnabled(raw.enabled !== false); // A1 仅显式 false 才关
        const n = Number(raw.idleMinutes);
        setIdleMinutes(Number.isFinite(n) ? Math.min(240, Math.max(5, Math.round(n))) : 15);
        setKeepRunningInTray(raw.keepRunningInTray !== false);
      })
      .catch((e: Error) => { if (alive) setError(e.message); });
    return () => { alive = false; };
  }, [settingService]);

  const save = useCallback(async (patch: Partial<LearningSettingsShape>) => {
    const next = { enabled, idleMinutes, keepRunningInTray, ...patch };
    try {
      await settingService.update({
        learningIteration: next,
      } as unknown as Parameters<typeof settingService.update>[0]);
      setError(null);
    } catch (e) {
      setError(String(e));
    }
  }, [enabled, idleMinutes, keepRunningInTray, settingService]);

  return (
    <div className="space-y-6" data-testid="settings-learning-section">
      <SettingsGroupCard>
        <SettingsRow
          label="学习迭代"
          description={
            error
              ? `设置读写失败：${error}（请确认桥在 3030 运行）`
              : "空闲时自动通读最近的工作记录，把稳定可复用的内容整理进记忆、方法与知识库；每个自然日至多成功一次，可整轮回滚。"
          }
          control={
            <Switch
              checked={enabled}
              onCheckedChange={(v: boolean) => { setEnabled(v); void save({ enabled: v }); }}
              data-testid="settings-learning-toggle"
              aria-label="学习迭代开关"
            />
          }
        />
        <SettingsRow
          label="空闲等待时间"
          description="系统空闲达到该时长后，学习迭代才会自动开始检查（手动「立即学习」不受此限）。"
          control={
            <select
              value={idleMinutes}
              disabled={!enabled} // J14 关总开关禁用
              data-testid="settings-learning-idle"
              aria-label="空闲等待时间"
              onChange={(e) => { const v = Number(e.target.value); setIdleMinutes(v); void save({ idleMinutes: v }); }}
              className="rounded border border-border bg-background px-2 py-1 text-ui-sm disabled:opacity-50"
            >
              {IDLE_CHOICES.map((m) => <option key={m} value={m}>{m} 分钟</option>)}
            </select>
          }
        />
        <SettingsRow
          label="学习时保持托盘运行"
          description="学习进行中关闭主窗口时驻留托盘，等本轮结束再退出；不会自动设置开机自启。托盘挂接随桌面打包步骤启用。"
          control={
            <Switch
              checked={keepRunningInTray}
              disabled={!enabled} // J14 关总开关禁用
              onCheckedChange={(v: boolean) => { setKeepRunningInTray(v); void save({ keepRunningInTray: v }); }}
              data-testid="settings-learning-tray"
              aria-label="学习时保持托盘运行"
            />
          }
        />
      </SettingsGroupCard>
    </div>
  );
}

// 【#21 安全层】设置面板·工具安全（RE-21 增补 §3.1「三档模式进设置」；文案自写）。
// 内容=toolSecurity.shellEnabled 开关（默认关维持——2026-10-30 主控裁定，用户可翻）+
// Allow/Ask/Deny 策略展示（纯模型查表，判序语义与桥 tool_policy.mjs 一致）。
// yolo 档不暴露只留设置键（2026-10-30 用户裁决）：界面只显示当前档位说明，不给切换面；
// always_ask/yolo 如实注明仅设置键 toolSecurity.permissionMode。
// 挂载点=设置→隐身模式（安全节）packages/ui/src/settings/StealthSettingsSection.tsx
// （树内注册点，contracts/pin-points.json 登记）。开关写入走 read-modify-write 整对象
// 写回（桥侧 mergeSettingKeepTeam 浅合并，防冲掉 permissionMode——mergeToolSecurityPatch）。
import { useCallback, useEffect, useState } from "react";
import { Shield } from "lucide-react";
import { Switch, useServices } from "../ui-kit.js";
import {
  POLICY_TIERS,
  effectMetaOf,
  mergeToolSecurityPatch,
  modeDisplayLine,
  readPermissionMode,
  readShellEnabled,
  readToolSecurityRaw,
} from "./toolSecurityModel.js";

export function ToolSecuritySettingsSection() {
  const { settingService } = useServices();
  const [shellEnabled, setShellEnabled] = useState(false); // 默认关（2026-10-30 主控裁定）
  const [mode, setMode] = useState(readPermissionMode(null)); // 未读到前按 smart 展示
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    let alive = true;
    settingService
      .get()
      .then((s: unknown) => {
        if (!alive) return;
        setShellEnabled(readShellEnabled(s));
        setMode(readPermissionMode(s));
      })
      .catch((e: unknown) => {
        if (alive) setError(String((e as Error)?.message ?? e));
      });
    return () => {
      alive = false;
    };
  }, [settingService]);

  const handleShellToggle = useCallback(
    async (next: boolean) => {
      const prev = shellEnabled;
      setShellEnabled(next);
      setSaving(true);
      try {
        const s = await settingService.get();
        // 浅合并桥语义：toolSecurity 整对象写回，防冲掉 permissionMode（mergeToolSecurityPatch）
        await settingService.update({
          toolSecurity: mergeToolSecurityPatch(readToolSecurityRaw(s), { shellEnabled: next }),
        } as unknown as Parameters<typeof settingService.update>[0]);
        setError(null);
      } catch (e) {
        setShellEnabled(prev);
        setError(String((e as Error)?.message ?? e));
      } finally {
        setSaving(false);
      }
    },
    [settingService, shellEnabled],
  );

  return (
    <div className="space-y-4" data-testid="settings-tool-security">
      <div className="rounded-lg border border-border/60 p-4">
        <div className="flex items-start justify-between gap-4">
          <div className="min-w-0">
            <div className="flex items-center gap-2 text-ui-sm font-medium text-foreground">
              <Shield className="size-4 text-foreground-subtle" />
              技能工具策略
            </div>
            <p className="mt-1 text-ui-caption leading-relaxed text-foreground-subtle">
              技能运行时动的是你的工具和案件文件：命令执行默认关闭，放行、确认、拒绝三档把关，每次决定都留痕。
            </p>
            {error ? (
              <p className="mt-1 text-ui-caption text-[#b23c36]" role="alert" data-testid="settings-tool-security-error">
                设置读写失败：{error}
              </p>
            ) : null}
          </div>
          <Switch
            checked={shellEnabled}
            onCheckedChange={(v) => void handleShellToggle(v)}
            disabled={saving}
            data-testid="settings-tool-security-shell-toggle"
            aria-label="命令执行开关"
          />
        </div>
        <p className="mt-2 text-ui-caption text-foreground-subtle" data-testid="settings-tool-security-shell-state">
          {shellEnabled
            ? "命令执行已开启：shell 类调用逐条确认，且仍受宿主命令闸把关；关闭即恢复默认拒绝。"
            : "命令执行已关闭（默认）：shell 类调用一律拒绝。"}
        </p>
      </div>

      <div className="rounded-lg border border-border/60 p-4" data-testid="settings-tool-security-mode">
        <div className="text-ui-sm font-medium text-foreground">把关档位</div>
        <p className="mt-1 text-ui-caption text-foreground-subtle" data-testid="settings-tool-security-mode-line">
          {modeDisplayLine(mode)}
        </p>
      </div>

      <div className="rounded-lg border border-border/60 p-4" data-testid="settings-tool-security-policy">
        <div className="text-ui-sm font-medium text-foreground">策略一览（放行 / 逐条确认 / 一律拒绝）</div>
        <div className="mt-3 space-y-4">
          {POLICY_TIERS.map((tier) => {
            const meta = effectMetaOf(tier.effect);
            return (
              <div key={tier.effect} data-testid={`settings-tool-security-tier-${tier.effect}`}>
                <div className="flex items-center gap-2">
                  <span className={`rounded px-1.5 py-0.5 text-[10px] font-medium ${meta.cls}`}>{meta.label}</span>
                  <span className="text-ui-sm text-foreground">{tier.title}</span>
                </div>
                <p className="mt-0.5 text-ui-caption text-foreground-subtle">{tier.description}</p>
                <ul className="mt-1 space-y-0.5">
                  {tier.items.map((item) => (
                    <li key={item} className="text-ui-caption leading-relaxed text-foreground-subtle">
                      · {item}
                    </li>
                  ))}
                </ul>
              </div>
            );
          })}
        </div>
        <p className="mt-3 text-ui-caption text-foreground-subtle">
          开关与档位即时生效，无须重启；每次决定的留痕见安全审计中心的「工具决策」。
        </p>
      </div>
    </div>
  );
}

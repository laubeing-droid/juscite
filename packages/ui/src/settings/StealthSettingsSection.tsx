// 设置页·隐身模式分区（v4 §8 / patch 022）：一键全屏蔽开关 + 五通道屏蔽清单。
// 开关写 setting.stealthMode.enabled（桥已消费：开启即 sendText fail-closed，见
// tools/bridge/bridge_host.mjs）。v1 边界：对话出站已接桥阻断，五通道其余阻断
// 实现随 M3 后——清单如实展示，不伪造已阻断状态。
import { useCallback, useEffect, useState } from "react";
import { Shield } from "lucide-react";
import { Switch } from "@/components/ui/switch.js";
import { Button } from "@/components/ui/button.js";
import { SettingsGroupCard, SettingsRow } from "@/settings/SettingsPageParts.js";
import { useServices } from "@/hooks/useServices.js";
// 功能 #30 安全审计中心（RE-30 对拍 2）：设置安全节导流卡——点击即关设置 tab 并打开审计中心。
import { requestSecurityAuditCenter } from "@juscite/legal/panels/SecurityAuditCenter";
// 功能 #21 安全层（RE-21 增补 §3.1）：设置安全节工具策略面板——shell 开关（默认关）+
// Allow/Ask/Deny 策略展示；yolo 档不暴露只留设置键（2026-10-30 用户裁决）。组件出树
// @juscite/legal，此处仅一行挂载注册（contracts/pin-points.json 登记）。
import { ToolSecuritySettingsSection } from "@juscite/legal/panels/ToolSecuritySettingsSection";

// §8 隐身屏蔽清单（五通道，顺序照施工表）
const STEALTH_CHANNELS: Array<{ name: string; description: string }> = [
  { name: "内嵌浏览器", description: "browserView（闸后保留件），隐身开启即断" },
  { name: "Chrome 数据导入", description: "登录态数据，仅内存态不落盘，隐身开启即断" },
  { name: "自动更新", description: "自建源换源后仍入闸，隐身开启即断" },
  {
    name: "远程服务通道",
    description: "oc28 serve/attach、remote-connection、P2 网关 api_server/七通道/a2a（入站/出站双登记）",
  },
  { name: "语音供应商出站", description: "TTS/STT 供应商请求，隐身开启即断" },
];

export function StealthSettingsSection() {
  const { settingService } = useServices();
  const [enabled, setEnabled] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    settingService
      .get()
      // stealthMode 为 Juscite additive 字段（AppSettings 冻结 schema 外），运行时宽容、类型层断言桥接
      .then((s: unknown) => {
        if (!alive) return;
        setEnabled(Boolean((s as { stealthMode?: { enabled?: boolean } })?.stealthMode?.enabled));
      })
      .catch((e: Error) => {
        if (alive) setError(e.message);
      });
    return () => {
      alive = false;
    };
  }, [settingService]);

  const handleToggle = useCallback(
    async (next: boolean) => {
      const prev = enabled;
      setEnabled(next);
      try {
        await settingService.update({
          stealthMode: { enabled: next },
        } as unknown as Parameters<typeof settingService.update>[0]);
      } catch (e) {
        setEnabled(prev);
        setError(String(e));
      }
    },
    [enabled, settingService],
  );

  return (
    <div className="space-y-6" data-testid="settings-stealth-section">
      <SettingsGroupCard>
        <SettingsRow
          label="隐身模式（一键全屏蔽）"
          description={
            error
              ? `设置读写失败：${error}（请确认桥在 3030 运行）`
              : "开启后出站通道全断，仅保留本地处理（patch 022 三闸语义：一键全屏蔽 / 出站白名单展示 / 状态灯）。当前版本：对话出站已接桥阻断；五通道其余阻断实现随 M3 后。"
          }
          control={
            <Switch
              checked={enabled}
              onCheckedChange={(v) => void handleToggle(v)}
              data-testid="settings-stealth-toggle"
              aria-label="隐身模式开关"
            />
          }
        />
      </SettingsGroupCard>
      {/* 功能 #30 安全审计导流卡（对拍 2：盾形图标+标题+说明+按钮；点击=关设置+开审计中心）。 */}
      <SettingsGroupCard>
        <div data-testid="settings-security-audit">
          <SettingsRow
            label={
              <span className="flex items-center gap-2">
                <Shield className="size-4 text-foreground-subtle" />
                安全审计中心
              </span>
            }
            description="每次 AI 出站的脱敏命中与本地关键操作都会在这里留痕，可随时核对记录完整性与命中明细（台账不保存敏感原文）。"
            control={
              <Button
                variant="ghost"
                size="sm"
                data-testid="settings-security-audit-open"
                onClick={() => requestSecurityAuditCenter()}
              >
                打开审计中心
              </Button>
            }
          />
        </div>
      </SettingsGroupCard>
      {/* 功能 #21 安全层工具策略面板（RE-21 增补 §3.1；组件自绘卡片，出树 @juscite/legal）。 */}
      <ToolSecuritySettingsSection />
      <SettingsGroupCard>
        <div data-testid="settings-stealth-channel-list">
          {STEALTH_CHANNELS.map((c, i) => (
            <SettingsRow
              key={c.name}
              label={`${i + 1}. ${c.name}`}
              description={c.description}
              control={
                <span className="text-ui-caption text-foreground-subtle">随隐身开启屏蔽</span>
              }
            />
          ))}
        </div>
      </SettingsGroupCard>
    </div>
  );
}

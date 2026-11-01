// 功能 #29 设置内重看入口（RE-29 §2-E1/E2）：设置→帮助与反馈→产品指引分区→幽灵按钮「开始指引」。
// 点击即走 D1 同链（关设置→切对话页→启 tour），无需确认弹窗；重看不改 onboarding.status（D10 幂等）。
// 功能 #31 支持通道（RE-31 §3.3）：本分区扩为三段=产品指引（#29 段）/提交工单/诊断包（SupportHelpSection）。
import { LifeBuoy, Star } from "lucide-react";
import { Button } from "@/components/ui/button.js";
import { SettingsGroupCard, SettingsRow } from "@/settings/SettingsPageParts.js";
import { requestProductTour } from "@/onboarding/ProductTour.js";
import { SupportHelpSection } from "@/settings/SupportHelpSection.js";

export function HelpFeedbackSection() {
  return (
    <div className="space-y-6" data-testid="settings-help-section">
      <SettingsGroupCard>
        <SettingsRow
          label="帮助与反馈"
          description="使用说明、工单与诊断入口集中在这里。"
          control={<LifeBuoy className="size-4 text-foreground-subtle" />}
        />
      </SettingsGroupCard>
      <SettingsGroupCard>
        <div data-testid="settings-help-product-tour">
          <SettingsRow
            label={
              <span className="flex items-center gap-2">
                <Star className="size-4 text-amber-500" />
                产品指引
              </span>
            }
            description="重新观看新建对话、法律工作台、定时任务、插件和设置入口的说明（约 2 分钟，纯导览，不改动业务数据）。"
            control={
              <Button
                variant="ghost"
                size="sm"
                data-testid="settings-help-start-tour"
                onClick={() => requestProductTour()}
              >
                开始指引
              </Button>
            }
          />
        </div>
      </SettingsGroupCard>
      {/* #31 提交工单+诊断包两段（RE-31 §3.3 段 2/段 3） */}
      <SupportHelpSection />
    </div>
  );
}

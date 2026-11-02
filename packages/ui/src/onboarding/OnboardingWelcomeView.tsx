import { ArrowRightIcon } from "lucide-react";
import { Button } from "@/components/ui/button.js";
import { ZCodeAboutLogo } from "@/components/ui/ZCodeAboutLogo.js";
import { useZCodeIntl } from "@/i18n/IntlProvider.js";
import { OnboardingWelcomeAsciiVisual } from "@/onboarding/OnboardingWelcomeAsciiVisual.js";

export function OnboardingWelcomeView(props: { onStart: () => void; onOpenMigration: () => void }) {
  const { intl } = useZCodeIntl();

  return (
    <div className="flex h-full min-h-0 flex-col md:flex-row">
      <div className="flex min-h-0 flex-1 flex-col justify-center px-6 py-6 md:w-[62%] md:flex-none md:px-8">
        <div className="inline-flex items-center self-start rounded-full border border-border bg-background-alt px-3 py-1 text-ui-sm text-foreground-subtle">
          {intl.formatMessage({ id: "onboarding.welcome.eyebrow" })}
        </div>

        <div className="mt-4 space-y-3">
          {/* 欢迎标壳固定海军蓝底加金环，不跟随浅色主题 token，避免浅色下边框发灰。 */}
          <div
            className="relative flex size-12 items-center justify-center rounded-xl bg-[#1B2A4A] text-white shadow-lg/20 ring-1 ring-[#C9A45C]/80"
            aria-label="Juscite"
            role="img"
          >
            <ZCodeAboutLogo className="h-auto w-7" />
          </div>
          <div className="text-3xl font-bold tracking-tight text-foreground">
            {intl.formatMessage({ id: "onboarding.welcome.title" })}
          </div>
        </div>

        <p className="mt-3 max-w-md text-ui-base leading-6 text-foreground-subtle">
          {intl.formatMessage({ id: "onboarding.welcome.helper" })}
        </p>

        <div className="mt-6 w-full space-y-3">
          <Button
            type="button"
            size="lg"
            className="h-11 w-full justify-between text-ui-base"
            onClick={props.onStart}
          >
            {intl.formatMessage({ id: "onboarding.welcome.start" })}
            <ArrowRightIcon className="size-4" />
          </Button>
          <Button
            type="button"
            size="lg"
            variant="outline"
            className="h-11 w-full justify-between text-ui-base"
            onClick={props.onOpenMigration}
          >
            {intl.formatMessage({ id: "onboarding.welcome.migrate" })}
            <ArrowRightIcon className="size-4" />
          </Button>
        </div>
      </div>

      <div className="hidden min-h-0 md:flex md:w-[38%] md:flex-col md:p-2 md:pl-0">
        <OnboardingWelcomeAsciiVisual />
      </div>
    </div>
  );
}

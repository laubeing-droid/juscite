import { useState } from "react";
import { BIGMODEL_PROVIDER_ID, ZAI_PROVIDER_ID } from "@zcode/shared";
import { ZCodeAppLogo } from "@zcode/ui/app-logo";
import { renderOAuthProviderIcon } from "@zcode/ui/oauth-provider-icon";
import type { WebOAuthProviderId } from "./browserOAuthCredentialRepo.js";
import { Button } from "@zcode/ui/button";
import { getWebAuthCopy } from "./webAuthLocale.js";

interface WebLoginPageProps {
  onLogin: (provider: WebOAuthProviderId) => void;
}

export function WebLoginPage({ onLogin }: WebLoginPageProps) {
  const copy = getWebAuthCopy();
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const beginLogin = (provider: WebOAuthProviderId) => {
    if (isSubmitting) return;
    setError(null);
    setIsSubmitting(true);
    try {
      const result = onLogin(provider) as void | Promise<void>;
      if (result && typeof result.then === "function") {
        void result.catch((caught: unknown) => {
          setIsSubmitting(false);
          setError(caught instanceof Error ? caught.message : copy.loginError);
        });
      }
    } catch (caught) {
      setIsSubmitting(false);
      setError(caught instanceof Error ? caught.message : copy.loginError);
    }
  };

  return (
    <main className="flex min-h-dvh items-center justify-center bg-background px-4 py-8 text-foreground">
      <section className="w-full max-w-sm rounded-lg border border-card-border border-t-2 border-t-[#C9A45C] bg-card p-5 shadow-sm">
        <div className="mb-4 flex items-center gap-3">
          <ZCodeAppLogo className="size-10" />
          <div className="min-w-0">
            <div className="text-ui-xs font-medium text-foreground">{copy.brand}</div>
            <h1 className="text-ui-lg font-medium text-foreground">{copy.loginTitle}</h1>
          </div>
        </div>
        <p className="text-ui-sm leading-6 text-foreground-subtle">{copy.loginDescription}</p>
        <ol className="my-4 flex items-center gap-2" aria-label={copy.loginSteps.join(" → ")}>
          {copy.loginSteps.map((step, index) => (
            <li key={step} className="flex min-w-0 items-center gap-1.5 text-ui-xs text-foreground">
              <span className="flex size-5 shrink-0 items-center justify-center rounded-full bg-[#1B2A4A] text-[11px] font-semibold text-[#C9A45C]">
                {index + 1}
              </span>
              <span className="truncate">{step}</span>
            </li>
          ))}
        </ol>
        {isSubmitting ? (
          <p role="status" className="mb-3 text-ui-sm text-foreground-subtle">
            {copy.loginPending}
          </p>
        ) : null}
        {error ? (
          <p role="alert" className="mb-3 text-ui-sm text-destructive">
            {error}
          </p>
        ) : null}
        <div className="space-y-2">
          {[ZAI_PROVIDER_ID, BIGMODEL_PROVIDER_ID].map((provider) => (
            <Button
              key={provider}
              type="button"
              size="lg"
              className="h-11 w-full"
              disabled={isSubmitting}
              onClick={() => beginLogin(provider)}
            >
              {renderOAuthProviderIcon(provider, "size-4")}
              <span>{copy.loginAction[provider]}</span>
              <span className="ml-1 inline-flex h-5 shrink-0 items-center rounded-full border border-primary-foreground/30 px-2 text-ui-xs font-medium leading-none text-primary-foreground/60">
                {copy.loginRegion[provider]}
              </span>
            </Button>
          ))}
        </div>
      </section>
    </main>
  );
}

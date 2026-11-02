import { useEffect, useState } from "react";
import { Button } from "@zcode/ui/button";
import type { WebAuthCallbackResult, WebAuthService } from "./webAuthService.js";
import { getWebAuthCopy } from "./webAuthLocale.js";

interface WebCallbackPageProps {
  authService: Pick<WebAuthService, "handleCallback">;
  onSuccess: (result: WebAuthCallbackResult) => void;
  onRetry: () => void;
}

export function WebCallbackPage({ authService, onRetry, onSuccess }: WebCallbackPageProps) {
  const copy = getWebAuthCopy();
  const [error, setError] = useState<string | null>(null);
  const [retrying, setRetrying] = useState(false);

  useEffect(() => {
    let isMounted = true;

    authService
      .handleCallback(window.location.href)
      .then((result) => {
        if (!isMounted || !result) {
          return;
        }
        onSuccess(result);
      })
      .catch((caught) => {
        if (!isMounted) {
          return;
        }
        setError(caught instanceof Error ? caught.message : String(caught));
      });

    return () => {
      isMounted = false;
    };
  }, [authService, onSuccess]);

  return (
    <main className="flex min-h-dvh items-center justify-center bg-background px-4 py-8 text-foreground">
      <section className="w-full max-w-sm rounded-lg border border-card-border bg-card p-5 shadow-sm">
        {error ? (
          <>
            <div className="mb-4 flex size-10 items-center justify-center rounded-lg bg-destructive text-ui-xs font-medium text-destructive-foreground">
              !
            </div>
            <h1 className="text-ui-lg font-medium text-foreground">{copy.callbackErrorTitle}</h1>
            <p role="alert" className="mt-2 text-ui-sm leading-6 text-foreground-subtle">
              {copy.callbackErrorDescription}
            </p>
            <p className="mt-2 text-ui-sm leading-6 text-foreground-subtle">
              {copy.callbackErrorPath}
            </p>
            <details className="mt-3 rounded-lg border border-border bg-surface px-3 py-2">
              <summary className="cursor-pointer text-ui-xs text-foreground-subtle">
                {copy.callbackErrorDetail}
              </summary>
              <p className="mt-2 break-words text-ui-xs leading-5 text-foreground-subtle">{error}</p>
            </details>
            <Button
              type="button"
              size="lg"
              className="mt-5 h-11 w-full"
              disabled={retrying}
              onClick={() => {
                if (retrying) return;
                setRetrying(true);
                try {
                  onRetry();
                } catch {
                  setRetrying(false);
                }
              }}
            >
              {copy.retryAction}
            </Button>
          </>
        ) : (
          <>
            <div
              aria-hidden="true"
              className="mb-4 size-9 animate-spin rounded-full border-2 border-border border-t-[#C9A45C]"
            />
            <h1 className="text-ui-lg font-medium text-foreground">{copy.callbackTitle}</h1>
            <p role="status" className="mt-2 text-ui-sm leading-6 text-foreground-subtle">
              {copy.callbackDescription}
            </p>
            <p className="mt-2 text-ui-sm leading-6 text-foreground">{copy.callbackNext}</p>
          </>
        )}
      </section>
    </main>
  );
}

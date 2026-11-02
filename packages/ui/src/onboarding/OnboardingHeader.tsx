import { Button } from "@/components/ui/button.js";
import { cn } from "@/components/lib/utils.js";
import { ArrowLeft, X } from "lucide-react";

export function OnboardingHeader({
  step,
  saving,
  t,
  onBack,
  onClose,
}: {
  step: 0 | 1 | 2;
  saving: boolean;
  t: (key: string) => string;
  onBack: () => void;
  onClose: () => void;
}) {
  return (
    <header className="relative grid min-h-14 shrink-0 grid-cols-[1fr_auto_1fr] items-center px-6 py-1 sm:px-10 [@media(max-height:740px)]:h-10 [@media(max-height:740px)]:min-h-10">
      {step > 0 ? (
        <Button
          variant="ghost"
          disabled={saving}
          className="col-start-1 row-start-1 justify-self-start h-9 rounded-xl px-2 text-ui-sm text-foreground-subtle"
          onClick={onBack}
        >
          <ArrowLeft className="size-4" />
          {t("back")}
        </Button>
      ) : null}
      <div className="col-start-2 row-start-1 flex flex-col items-center gap-1">
        <ol aria-label={t("preferences")} className="flex w-28 items-center gap-2">
          {["stepRole", "stepMode", "stepPreferences"].map((key, index) => (
            <li
              key={key}
              aria-current={step === index ? "step" : undefined}
              className="min-w-0 flex-1"
            >
              <div
                aria-hidden="true"
                className={cn(
                  "h-1 rounded-full transition-colors",
                  index <= step ? "bg-[#C9A45C]" : "bg-border",
                )}
              />
              <span className="sr-only">
                {index + 1}. {t(key)}
              </span>
            </li>
          ))}
        </ol>
        <span className="text-ui-xs text-foreground-subtle [@media(max-height:740px)]:sr-only">
          {step + 1}/3 · {t(["stepRole", "stepMode", "stepPreferences"][step] ?? "stepRole")}
        </span>
      </div>
      <Button
        variant="ghost"
        size="icon"
        disabled={saving}
        aria-label={t("close")}
        title={t("close")}
        className="col-start-3 row-start-1 justify-self-end size-9 rounded-xl text-foreground-subtle"
        onClick={onClose}
      >
        <X className="size-4" />
      </Button>
    </header>
  );
}

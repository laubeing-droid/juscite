// 功能 #29 首启向导（RE-29 §2-A/B 组等量自研，三步状态机 welcome→setup→guide；账户族裁剪随规格 §5）。
// 强制完成型模态（A5：无 X 关闭钮、点遮罩不关、ESC 不关；出路仅三步推进）。
// 两粒进度点（setup/guide；welcome 不显示）=裁剪连带差异非等量缺陷（规格 §3 皮肤段第 4 轮裁定）。
// 数据二选一（B5 blank|demo）+ 指引二选一（B6 start|skip）→ onboardingComplete 单事务（B7，失败红字可重试）。
import { useCallback, useEffect, useState } from "react";
import { useServices } from "@/hooks/useServices.js";
import { requestProductTour } from "@/onboarding/ProductTour.js";

type Step = "welcome" | "setup" | "guide";
type State = {
  status: "pending" | "completed";
  demoChoice: "blank" | "demo" | null;
  demoImported: boolean;
  guideStatus: "pending" | "completed" | "skipped";
};

const STEP_TITLES: Record<Step, string> = {
  welcome: "欢迎使用 Juscite 工作台",
  setup: "如何开始",
  guide: "需要快速了解一下吗？",
};

function ChoiceCard(props: {
  selected: boolean;
  onSelect: () => void;
  testId: string;
  title: string;
  badge?: string;
  description: string;
}) {
  return (
    <button
      type="button"
      data-testid={props.testId}
      aria-pressed={props.selected}
      onClick={props.onSelect}
      className={`rounded-md border-2 p-3 text-left transition-colors ${
        props.selected ? "border-primary bg-primary/5" : "border-border hover:border-foreground/30"
      }`}
    >
      <span className="flex items-center gap-2 text-ui-sm font-medium">
        {props.title}
        {props.badge ? (
          <span className="rounded-full bg-primary/10 px-1.5 py-0.5 text-[10px] font-medium text-primary">
            {props.badge}
          </span>
        ) : null}
      </span>
      <span className="mt-1 block text-ui-caption leading-relaxed text-foreground-subtle">
        {props.description}
      </span>
    </button>
  );
}

export function FirstRunWizard() {
  const { zcodeAgentService } = useServices();
  const [open, setOpen] = useState(false); // A3：IPC 失败不弹（静默降级，不阻塞主界面）
  const [step, setStep] = useState<Step>("welcome");
  const [demoChoice, setDemoChoice] = useState<"blank" | "demo">("blank"); // B5 默认选中空白
  const [guideChoice, setGuideChoice] = useState<"start" | "skip">("start");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    zcodeAgentService
      .onboardingGet?.()
      .then((state: State | undefined) => {
        if (alive && state?.status === "pending") setOpen(true);
      })
      .catch(() => { /* A3：失败不弹 */ });
    return () => { alive = false; };
  }, [zcodeAgentService]);

  const finish = useCallback(() => {
    if (busy) return;
    setBusy(true);
    setError(null);
    zcodeAgentService
      .onboardingComplete?.({ demo: demoChoice === "demo", startGuide: guideChoice === "start" })
      .then((state: State | undefined) => {
        setBusy(false);
        setOpen(false); // B7 成功→关向导
        if (state?.guideStatus === "pending") requestProductTour(); // startGuide=true → 立即启动 tour
      })
      .catch((e: unknown) => {
        // B7 失败→卡内红字、可重试；桥侧单事务回滚，状态未落盘
        setBusy(false);
        setError(String((e as Error)?.message ?? e));
      });
  }, [busy, demoChoice, guideChoice, zcodeAgentService]);

  if (!open) return null;
  const showDots = step !== "welcome"; // 两粒进度点（setup/guide）；welcome 步不显示
  return (
    <div className="fixed inset-0 z-[200] flex items-center justify-center bg-black/55" data-testid="first-run-wizard">
      {/* 强制完成型模态：遮罩无点击关闭、无 X、无 ESC 监听（A5） */}
      <div className="w-[500px] max-w-[calc(100vw-32px)] rounded-lg border border-border bg-background p-6 shadow-2xl">
        <h2 className="text-ui-lg font-semibold">{STEP_TITLES[step]}</h2>
        {showDots ? (
          <div className="mt-2 flex items-center gap-1.5" aria-label="首次使用进度" data-testid="wizard-dots">
            {(["setup", "guide"] as const).map((s, i) => {
              const current = step === s;
              const passed = step === "guide" && s === "setup";
              return (
                <span
                  key={s}
                  data-testid={`wizard-dot-${s}`}
                  className={`h-1.5 rounded-full transition-all ${
                    current ? "w-5 bg-primary" : passed ? "w-1.5 bg-primary/40" : "w-1.5 bg-foreground/20"
                  }`}
                  aria-current={current ? "step" : undefined}
                >
                  <span className="sr-only">第 {i + 1} 步，共 2 步</span>
                </span>
              );
            })}
          </div>
        ) : null}

        {step === "welcome" ? (
          <div className="mt-4">
            <p className="text-ui-base leading-relaxed">
              您好，律师。这是一款在本地运行的法律工作工具，装好即可直接使用，无需注册账号。
            </p>
            <p className="mt-2 text-ui-caption leading-relaxed text-foreground-subtle">
              接下来只用两步：选择起步方式，再决定要不要看一份约 2 分钟的功能导览。
            </p>
            <div className="mt-5 flex justify-end">
              <button
                type="button"
                data-testid="wizard-primary"
                className="rounded-md bg-primary px-4 py-2 text-ui-sm font-medium text-primary-foreground hover:opacity-90"
                onClick={() => setStep("setup")}
              >
                开始配置
              </button>
            </div>
          </div>
        ) : null}

        {step === "setup" ? (
          <div className="mt-4">
            <p className="text-ui-caption leading-relaxed text-foreground-subtle">
              正式数据默认保持为空。只有您明确选择后，才会一次性导入一套虚构的演示内容（可随时删除）。
            </p>
            <div className="mt-3 grid grid-cols-2 gap-3">
              <ChoiceCard
                testId="wizard-choice-blank"
                selected={demoChoice === "blank"}
                onSelect={() => setDemoChoice("blank")}
                title="空白开始"
                badge="推荐"
                description="不添加任何案件、客户、文档或日程，直接开始正式工作。"
              />
              <ChoiceCard
                testId="wizard-choice-demo"
                selected={demoChoice === "demo"}
                onSelect={() => setDemoChoice("demo")}
                title="导入演示数据"
                description="一次性添加虚构的案件、文档、客户和本周日程，方便先熟悉界面；删除后不会自动恢复。"
              />
            </div>
          </div>
        ) : null}

        {step === "guide" ? (
          <div className="mt-4">
            <p className="text-ui-caption leading-relaxed text-foreground-subtle">
              一份约 2 分钟的界面导览，依次介绍新建对话、法律工作台、定时任务、插件和设置入口；以后也可在设置的「帮助与反馈」里重新观看。
            </p>
            <div className="mt-3 grid grid-cols-2 gap-3">
              <ChoiceCard
                testId="wizard-choice-start"
                selected={guideChoice === "start"}
                onSelect={() => setGuideChoice("start")}
                title="开始产品指引"
                badge="推荐"
                description="进入工作台后逐步高亮主要功能；纯导览，不会自动创建或修改业务数据。"
              />
              <ChoiceCard
                testId="wizard-choice-skip"
                selected={guideChoice === "skip"}
                onSelect={() => setGuideChoice("skip")}
                title="暂时跳过"
                description="直接自行探索，需要时可在设置里重新打开这份指引。"
              />
            </div>
          </div>
        ) : null}

        {error ? (
          <p role="alert" data-testid="wizard-error" className="mt-3 text-ui-sm text-red-500">
            {error}
          </p>
        ) : null}

        {step !== "welcome" ? (
          <div className="mt-5 flex items-center justify-between">
            <button
              type="button"
              data-testid="wizard-back"
              disabled={busy}
              className="rounded-md px-3 py-2 text-ui-sm text-foreground-subtle hover:text-foreground disabled:opacity-50"
              onClick={() => setStep(step === "guide" ? "setup" : "welcome")}
            >
              返回
            </button>
            {step === "setup" ? (
              <button
                type="button"
                data-testid="wizard-primary"
                className="rounded-md bg-primary px-4 py-2 text-ui-sm font-medium text-primary-foreground hover:opacity-90"
                onClick={() => setStep("guide")}
              >
                继续
              </button>
            ) : (
              <button
                type="button"
                data-testid="wizard-primary"
                disabled={busy}
                className="rounded-md bg-primary px-4 py-2 text-ui-sm font-medium text-primary-foreground hover:opacity-90 disabled:opacity-60"
                onClick={finish}
              >
                {busy ? "正在准备…" : guideChoice === "start" ? "完成并开始指引" : "完成设置"}
              </button>
            )}
          </div>
        ) : null}
      </div>
    </div>
  );
}

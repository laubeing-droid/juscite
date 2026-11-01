// 功能 #29 产品指引（RE-29 §3/§2-D 组等量自研）：driver.js 六步侧栏导览。
// 触发链（D1）=向导完成选「开始指引」或设置→帮助与反馈→「开始指引」：关面板→切对话页→runToken+1→rAF 后 drive。
// 引擎=npm driver.js@1.10.2（MIT，nilbuild 发布线=规格在盘 1.8.0 同源；锁版，验收=12 项引擎探针复跑）。
// 上报一次锁定（D5）：整个 tour 生命周期只发一次 onboardingGuideStatus；失败静默吞掉（A8 残留 pending 仅设置兜底）。
import { useEffect, useRef } from "react";
import { driver } from "driver.js";
import "driver.js/dist/driver.css";
import { useServices } from "@/hooks/useServices.js";

/** 跨组件触发总线：向导/设置重看入口都发同一事件，App 层消费（关设置→切对话→令牌+1）。 */
export const PRODUCT_TOUR_EVENT = "juscite:product-tour:start";
export function requestProductTour() {
  window.dispatchEvent(new CustomEvent(PRODUCT_TOUR_EVENT));
}

// D3 同款配置面：动画/平滑滚动/可关闭/键盘/禁高亮交互/遮罩 0.58/padding 7/radius 10/进度模板/三钮文案。
const TOUR_CONFIG = {
  animate: true,
  smoothScroll: true,
  allowClose: true,
  allowKeyboardControl: true,
  disableActiveInteraction: true,
  overlayOpacity: 0.58,
  stagePadding: 7,
  stageRadius: 10,
  showProgress: true,
  progressText: "{{current}} / {{total}}",
  nextBtnText: "下一步",
  prevBtnText: "上一步",
  doneBtnText: "完成",
} as const;

// 六步全挂侧栏（D2 同构映射：品牌区/对话/法律工作台(案件·文档·期限)/日程(定时任务)/插件/设置）。
// 文案自写；每步声明纯导览（D6），首步承担免责+时长预期。
const TOUR_STEPS: Array<{
  element: string;
  popover: { title: string; description: string; side: "right"; align: "start" | "center" | "end" };
}> = [
  {
    element: "[data-tour=\"tour-overview\"]",
    popover: {
      title: "认识一下 Juscite 工作台",
      description: "用大约 2 分钟看完六个主要入口。这是纯导览：不会创建或修改任何业务数据，随时可以按 Esc 或点右上角关闭退出。",
      side: "right", align: "start",
    },
  },
  {
    element: "[data-tour=\"tour-chat\"]",
    popover: {
      title: "从一次对话开始",
      description: "点「新任务」即可与 AI 助手对话，整理材料、起草文书都从这里出发（本导览不会替你创建任务）。",
      side: "right", align: "center",
    },
  },
  {
    element: "[data-tour=\"tour-legal\"]",
    popover: {
      title: "法律工作台",
      description: "案件、材料、审查、核验、期限与文书的统一入口，日常业务在这里展开（纯导览，不改动业务数据）。",
      side: "right", align: "center",
    },
  },
  {
    element: "[data-tour=\"tour-schedule\"]",
    popover: {
      title: "定时任务",
      description: "把周期性工作交给计划任务到点自动执行，运行历史可回看（纯导览，不改动业务数据）。",
      side: "right", align: "center",
    },
  },
  {
    element: "[data-tour=\"tour-plugins\"]",
    popover: {
      title: "插件",
      description: "在这里浏览、安装和管理插件，扩展工作台能力（纯导览，不改动业务数据）。",
      side: "right", align: "center",
    },
  },
  {
    element: "[data-tour=\"tour-settings\"]",
    popover: {
      title: "设置",
      description: "模型、外观、快捷键与隐私都集中在这里（纯导览，不改动业务数据）；这份产品指引以后也可以在设置的「帮助与反馈」里重新观看。",
      side: "right", align: "end",
    },
  },
];

export function ProductTour({ runToken }: { runToken: number }) {
  const { zcodeAgentService } = useServices();
  const activeRef = useRef<ReturnType<typeof driver> | null>(null);
  // service 引用只经 ref 消费：accessor 身份变化（重连/重订）不得打断进行中的 tour，
  // 重启唯一凭据=runToken（否则桥早期重订会让 tour 销毁重建，走查实测踩坑已修）。
  const serviceRef = useRef(zcodeAgentService);
  serviceRef.current = zcodeAgentService;
  useEffect(() => {
    if (runToken <= 0) return; // 令牌≤0 不启动（首渲染/重复挂载安全）
    // 换令牌先静默销毁上一实例：cleanup 的 destroy 是程序性退出，不算用户退出、不报 skipped。
    const prev = activeRef.current;
    activeRef.current = null;
    prev?.destroy();
    let tearingDown = false;
    let reported = false; // D5 首报锁定：completed 先发则 destroy 的 skipped 被吞
    const report = (status: "completed" | "skipped") => {
      if (reported) return;
      reported = true;
      serviceRef.current.onboardingGuideStatus?.({ status }).catch(() => { /* 上报失败静默（D5） */ });
    };
    const raf = requestAnimationFrame(() => {
      // 步挂点运行时才可查（侧栏挂载时序）；缺挂点的步剔除，五个入口覆盖面保底（规格 §3 步挂点注）。
      const steps = TOUR_STEPS.filter((s) => document.querySelector(s.element));
      if (!steps.length) return;
      const instance = driver({
        ...TOUR_CONFIG,
        popoverClass: "juscite-product-tour",
        steps,
        onCloseClick: () => { report("skipped"); instance.destroy(); },
        onDoneClick: () => { report("completed"); instance.destroy(); },
        onDestroyed: () => { if (!tearingDown) report("skipped"); },
      });
      activeRef.current = instance;
      instance.drive();
    });
    return () => {
      tearingDown = true;
      cancelAnimationFrame(raf);
      activeRef.current?.destroy();
      activeRef.current = null;
    };
  }, [runToken]); // 故意不含 service：见 serviceRef 注
  return null;
}

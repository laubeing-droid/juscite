import { Blocks, CalendarClock, FolderOpen, GraduationCap, Scale, ScanSearch, Telescope, Users } from "lucide-react";
import { TID_AUTOMATIONS_OPEN } from "@zcode/shared/test-ids";
import type { ProjectSidebarProps } from "@/project-sidebar/contract.js";
import { Button } from "@/components/ui/button.js";
import { NewTaskButtonGroup } from "@/NewTaskButtonGroup.js";
import { useZCodeIntl } from "@/i18n/IntlProvider.js";
import { WebRemoteControlDeviceHeader } from "@/web-remote-control/WebRemoteControlDeviceHeader.js";

/** 顶部导航只展示 Shell 的选中状态，路由仍由 Shell 唯一持有。 */
export function ProjectSidebarNavigation({
  props,
  onCreate,
}: {
  props: Pick<
    ProjectSidebarProps,
    | "isWebRemoteControl"
    | "onOpenAutomations"
    | "automationsActive"
    | "onOpenPluginStore"
    | "pluginStoreActive"
    | "onOpenLegal"
    | "legalActive"
    | "onOpenKnowledgeBase"
    | "knowledgeBaseActive"
    | "onOpenResearchReport"
    | "researchReportActive"
    | "onOpenTeam"
    | "teamActive"
    | "onOpenConflictPrecheck"
    | "conflictPrecheckActive"
    | "onOpenLearningIteration"
    | "learningIterationActive"
    | "webRemoteControlWorkspaceSwitcher"
  >;
  onCreate(): void;
}) {
  const { intl } = useZCodeIntl();
  const deviceNavigation = props.webRemoteControlWorkspaceSwitcher?.deviceNavigation;
  return (
    <div
      data-testid="sidebar-primary-navigation"
      data-tour="tour-overview"
      className={`flex flex-col gap-2 px-2 py-3 ${props.isWebRemoteControl && !deviceNavigation ? "max-md:pt-11" : ""}`}
    >
      {/* Relay V2 远控：当前电脑是项目与任务的上一级，放在导航首行；手机端占用原顶部留白。 */}
      {deviceNavigation ? <WebRemoteControlDeviceHeader navigation={deviceNavigation} /> : null}
      <NewTaskButtonGroup onCreateTask={onCreate} />
      {props.onOpenAutomations ? (
        <Button
          variant="ghost"
          size="lg"
          className={`w-full justify-start gap-2 ${props.automationsActive ? "bg-selected text-foreground" : ""}`}
          aria-pressed={props.automationsActive ?? false}
          data-tour="tour-schedule"
          data-testid={TID_AUTOMATIONS_OPEN}
          // 点击事件不能进入业务导航的可选 automationId 参数。
          onClick={() => props.onOpenAutomations?.()}
        >
          <CalendarClock className="size-4" />
          {intl.formatMessage({ id: "workspace.openScheduledSettings" })}
        </Button>
      ) : null}
      {/* 法律工作台入口（v4 §4.5 八模块法律面）：锚点重放自 M3 面轨。 */}
      <Button
        variant="ghost"
        size="lg"
        data-icon="inline-start"
        data-testid="legal-workbench-sidebar-open"
        data-tour="tour-legal"
        aria-pressed={props.legalActive ?? false}
        className={`w-full justify-start gap-2 ${props.legalActive ? "bg-selected text-foreground" : ""}`}
        onClick={() => props.onOpenLegal?.()}
      >
        <Scale className="size-4" />
        法律工作台
      </Button>
      {/* 【步骤4·#20 知识库】所内文集问答工作区入口（B01 同位入口同名工作区）。 */}
      <Button
        variant="ghost"
        size="lg"
        data-icon="inline-start"
        data-testid="knowledge-base-sidebar-open"
        data-tour="tour-knowledge"
        aria-pressed={props.knowledgeBaseActive ?? false}
        className={`w-full justify-start gap-2 ${props.knowledgeBaseActive ? "bg-selected text-foreground" : ""}`}
        onClick={() => props.onOpenKnowledgeBase?.()}
      >
        <FolderOpen className="size-4" />
        知识库
      </Button>
      {/* 【步骤4·#16 调研报告】调研工作区入口（B01 侧栏入口+lazy 面板）。 */}
      <Button
        variant="ghost"
        size="lg"
        data-icon="inline-start"
        data-testid="research-report-sidebar-open"
        aria-pressed={props.researchReportActive ?? false}
        className={`w-full justify-start gap-2 ${props.researchReportActive ? "bg-selected text-foreground" : ""}`}
        onClick={() => props.onOpenResearchReport?.()}
      >
        <Telescope className="size-4" />
        调研报告
      </Button>
      {/* 【步骤4·#26 团队同步】一级「团队」入口（A1：恒显，未入团也显示）。 */}
      <Button
        variant="ghost"
        size="lg"
        data-icon="inline-start"
        data-testid="team-sidebar-open"
        aria-pressed={props.teamActive ?? false}
        className={`w-full justify-start gap-2 ${props.teamActive ? "bg-selected text-foreground" : ""}`}
        onClick={() => props.onOpenTeam?.()}
      >
        <Users className="size-4" />
        团队
      </Button>
      {/* 【步骤4·#5 冲突查重】冲突预检工作区入口（收案动线：先预检再建案）。 */}
      <Button
        variant="ghost"
        size="lg"
        data-icon="inline-start"
        data-testid="conflict-precheck-sidebar-open"
        aria-pressed={props.conflictPrecheckActive ?? false}
        className={`w-full justify-start gap-2 ${props.conflictPrecheckActive ? "bg-selected text-foreground" : ""}`}
        onClick={() => props.onOpenConflictPrecheck?.()}
      >
        <ScanSearch className="size-4" />
        冲突预检
      </Button>
      {/* 【步骤4·#18 学习迭代】工作区入口（J1 侧栏入口+lazy 面板）。 */}
      <Button
        variant="ghost"
        size="lg"
        data-icon="inline-start"
        data-testid="learning-iteration-sidebar-open"
        aria-pressed={props.learningIterationActive ?? false}
        className={`w-full justify-start gap-2 ${props.learningIterationActive ? "bg-selected text-foreground" : ""}`}
        onClick={() => props.onOpenLearningIteration?.()}
      >
        <GraduationCap className="size-4" />
        学习迭代
      </Button>
      <Button
        variant="ghost"
        size="lg"
        className={`w-full justify-start gap-2 ${props.pluginStoreActive ? "bg-selected text-foreground" : ""}`}
        aria-pressed={props.pluginStoreActive ?? false}
        data-tour="tour-plugins"
        data-testid="plugin-store-sidebar-open"
        onClick={() => props.onOpenPluginStore?.()}
      >
        <Blocks className="size-4" />
        {intl.formatMessage({ id: "workspace.openPluginsSettings" })}
      </Button>
    </div>
  );
}

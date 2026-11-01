// legalUiKit —— 法律面板族的 UI 窄适配层（r12 波3，设计 docs/上游对齐债清零设计-r12-20261028.md §八 原则3）。
// 面板（./panels 全家）只 import 本文件，禁止直接 import 上游 ui 内部模块：
// 上游换样式系统/换组件库/改路由 → 只修宿主注册点一处，面板零动。
// 注册点 = packages/ui/src/legal/register.tsx（App.tsx 静态导入，先于任何面板渲染执行）。
// 端口类型为按面板实际用面收敛的结构类型（与宿主真件结构对齐，注册赋值时编译期校验）；
// 导出用 let 活绑定：configureLegalUiKit 覆写后，面板同名 import 在渲染期取到真件。
// 未注册即渲染 = fail-fast 抛错（不静默降级）。服务类型一律取 @zcode/services 真源，零手写协议形状。
import type { ComponentProps, ReactNode } from "react";
import type { IServiceAccessor } from "@zcode/services";

// ── 端口类型（按 panels/ 实际用面；宿主真件必须可赋值，见 register.tsx）──

// ref 双重身份问题：宿主 ui 与本包对 @types/react 的模块身份在 tsc 下不完全合一，
// 而 ref 是面板族用面之外的属性——端口 props 一律 Omit "ref"（面板不碰 ref；注册端真件仍兼容）。
export type LegalButtonProps = Omit<ComponentProps<"button">, "ref"> & {
  variant?: "default" | "outline" | "secondary" | "ghost" | "destructive" | "warning" | "link" | null;
  size?: "default" | "xs" | "sm" | "lg" | "icon" | "icon-xs" | "icon-sm" | "icon-md" | "icon-lg" | null;
  asChild?: boolean;
};

export type LegalInputProps = Omit<ComponentProps<"input">, "ref" | "size"> & {
  size?: "default" | "sm" | "lg" | "xs" | null;
  htmlSize?: number;
};

export type LegalDiffViewerProps = {
  className?: string;
  oldFile: { name: string; contents: string };
  newFile: { name: string; contents: string };
  options?: { diffStyle?: "split" | "unified" };
};

export type LegalMessageResponseProps = {
  className?: string;
  children?: ReactNode;
};

export type LegalPdfPreviewContentProps = {
  source: string | Blob | ArrayBuffer | Uint8Array;
  labels: {
    loading: string;
    loadError: string;
    noData: string;
    previousPage: string;
    nextPage: string;
    pageInput: string;
    zoomIn: string;
    zoomOut: string;
  };
  onPageChange?: (page: number) => void;
};

export type LegalCollectDroppedFiles = (dataTransfer: DataTransfer) => Promise<File[]>;
export type LegalServicesHook = () => IServiceAccessor;

// 开关控件端口（#21 安全层工具策略面板）：radix Switch.Root 用面收敛——
// 受控 checked + onCheckedChange + 禁用与无障碍透传（宿主真件可赋值，注册端编译期校验）。
export type LegalSwitchProps = Omit<ComponentProps<"button">, "ref" | "onChange"> & {
  checked?: boolean;
  onCheckedChange?: (checked: boolean) => void;
};

type LegalButtonComponent = (props: LegalButtonProps) => ReactNode;
type LegalInputComponent = (props: LegalInputProps) => ReactNode;
type LegalDiffViewerComponent = (props: LegalDiffViewerProps) => ReactNode;
type LegalMessageResponseComponent = (props: LegalMessageResponseProps) => ReactNode;
type LegalPdfPreviewContentComponent = (props: LegalPdfPreviewContentProps) => ReactNode;
type LegalSwitchComponent = (props: LegalSwitchProps) => ReactNode;

// ── 活绑定出口（面板 import 这些名字；注册前调用 fail-fast）──

function unconfigured(capability: string): never {
  throw new Error(
    `legalUiKit 能力「${capability}」未注册：packages/ui/src/legal/register.tsx 未加载（须由 App 根静态导入）`,
  );
}

export let Button: LegalButtonComponent = () => unconfigured("Button");
export let Input: LegalInputComponent = () => unconfigured("Input");
export let DiffViewer: LegalDiffViewerComponent = () => unconfigured("DiffViewer");
export let MessageResponse: LegalMessageResponseComponent = () => unconfigured("MessageResponse");
export let PdfPreviewContent: LegalPdfPreviewContentComponent = () => unconfigured("PdfPreviewContent");
export let collectDroppedFiles: LegalCollectDroppedFiles = () => unconfigured("collectDroppedFiles");
export let useServices: LegalServicesHook = () => unconfigured("useServices");
export let Switch: LegalSwitchComponent = () => unconfigured("Switch");

// ── 注册（宿主注册点唯一调用方）──

export interface LegalUiKitImpl {
  Button: LegalButtonComponent;
  Input: LegalInputComponent;
  DiffViewer: LegalDiffViewerComponent;
  MessageResponse: LegalMessageResponseComponent;
  PdfPreviewContent: LegalPdfPreviewContentComponent;
  collectDroppedFiles: LegalCollectDroppedFiles;
  useServices: LegalServicesHook;
  Switch: LegalSwitchComponent;
}

export function configureLegalUiKit(impl: LegalUiKitImpl): void {
  Button = impl.Button;
  Input = impl.Input;
  DiffViewer = impl.DiffViewer;
  MessageResponse = impl.MessageResponse;
  PdfPreviewContent = impl.PdfPreviewContent;
  collectDroppedFiles = impl.collectDroppedFiles;
  useServices = impl.useServices;
  Switch = impl.Switch;
}

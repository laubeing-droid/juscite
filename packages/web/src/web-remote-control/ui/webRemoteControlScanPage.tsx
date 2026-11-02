import { WebRemoteControlBrand } from "#src/web-remote-control/ui/webRemoteControlBrand.js";

export function WebRemoteControlScanPage({ locale }: { locale: "zh-CN" | "en-US" }) {
  const zh = locale === "zh-CN";
  return (
    <main className="flex min-h-dvh items-center justify-center bg-background px-4 py-8 text-foreground">
      <section className="w-full max-w-sm rounded-xl border border-card-border bg-card p-5 shadow-sm">
        <WebRemoteControlBrand className="mb-2" />
        <h1 className="text-ui-lg font-medium">
          {zh ? "请扫描桌面二维码" : "Scan the desktop QR code"}
        </h1>
        <ol className="mt-4 space-y-2 text-ui-sm leading-6 text-foreground-subtle">
          <li className="flex gap-2">
            <span className="flex size-5 shrink-0 items-center justify-center rounded-full bg-[#1B2A4A] text-[11px] font-semibold text-[#C9A45C]">
              1
            </span>
            <span>
              {zh ? "在电脑端打开 Web 远程控制" : "Open Web remote control on your computer"}
            </span>
          </li>
          <li className="flex gap-2">
            <span className="flex size-5 shrink-0 items-center justify-center rounded-full bg-[#1B2A4A] text-[11px] font-semibold text-[#C9A45C]">
              2
            </span>
            <span>{zh ? "用手机扫描二维码" : "Scan its QR code with this phone"}</span>
          </li>
        </ol>
        <p className="mt-3 text-ui-xs leading-5 text-foreground-subtlest">
          {zh
            ? "扫码后进入设备列表，选择这台电脑。"
            : "After scanning, pick this computer from the list."}
        </p>
      </section>
    </main>
  );
}

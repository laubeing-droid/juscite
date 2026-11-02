import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { JSDOM } from "jsdom";
import { describe, expect, it } from "vitest";

function readWebIndexHtml(): string {
  return readFileSync(resolve(process.cwd(), "packages/web/index.html"), "utf8");
}

function readWorkspaceFile(path: string): Buffer {
  return readFileSync(resolve(process.cwd(), path));
}

function createBootstrapDocument(theme: "zai-dark" | "zai-light"): JSDOM {
  return new JSDOM(readWebIndexHtml(), {
    beforeParse(window) {
      window.localStorage.setItem("zcode-theme", theme);
      Object.defineProperty(window, "matchMedia", {
        configurable: true,
        value: () => ({ matches: false }),
      });
    },
    runScripts: "dangerously",
    url: "https://zcode.example/remote",
  });
}

describe("web remote control bootstrap shell", () => {
  it("浏览器标签图标使用锁定的引用锚点，而不是桌面旧图标", () => {
    const html = readWebIndexHtml();
    const document = new JSDOM(html).window.document;
    const icons = [...document.querySelectorAll<HTMLLinkElement>('link[rel="icon"]')];
    const svgIcon = icons.find((icon) => icon.getAttribute("type") === "image/svg+xml");
    const icoIcon = icons.find((icon) => icon.getAttribute("href") === "/favicon.ico");

    expect(svgIcon?.getAttribute("href")).toBe("/favicon.svg");
    expect(icoIcon?.getAttribute("sizes")).toBe("32x32");

    const svg = readWorkspaceFile("packages/web/public/favicon.svg").toString("utf8");
    expect(svg).toContain("mark-navy-gold.png");
    expect(svg).not.toContain("天平");
    expect(svg).not.toContain("M8 10");

    const ico = readWorkspaceFile("packages/web/public/favicon.ico");
    expect(ico.subarray(0, 4).equals(Buffer.from([0, 0, 1, 0]))).toBe(true);
    expect(ico.equals(readWorkspaceFile("packages/desktop/build/icon.ico"))).toBe(false);
  });

  it.each([
    ["zai-dark", "dark", "#161616"],
    ["zai-light", "light", "#f8f8f8"],
  ] as const)(
    "在业务 bundle 执行前把 %s 同步到浏览器主题表面",
    (storedTheme, resolvedTheme, expectedColor) => {
      const dom = createBootstrapDocument(storedTheme);
      const { document } = dom.window;

      expect(document.documentElement.getAttribute("data-zcode-browser-theme-surface")).toBe(
        resolvedTheme,
      );
      expect(document.querySelector('meta[name="theme-color"]')?.getAttribute("content")).toBe(
        expectedColor,
      );
      expect(document.querySelector('meta[name="color-scheme"]')?.getAttribute("content")).toBe(
        resolvedTheme,
      );

      dom.window.close();
    },
  );
});

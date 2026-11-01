// 【施工单-10 单元二】结构化配置写入防御内核合同测试（YAML/JSON 配置面）。
// 验收断言（施工单原文口径）：合成 payload（冒号键/多行/锚点 &a·*a/标签 !!python）round-trip 后
// =纯标量、结构键集合零变化；键名禁来自用户原文（键语法闸+原型面危险键拒）。
// 对拍用标准 YAML 解析器（yaml 包，与上游 oc28/宿主同语）独立证伪：写出的每个值都是 string 纯标量，
// 顶层键集合恰等于声明闭集——不是只被我们自己的读回器"自证"。
import { describe, expect, it } from "vitest";
import { parse as parseYaml } from "yaml";

// 标准 YAML 解析器只吃"文档体"（首 --- 开档标记）：剥尾围栏再解析（尾 --- 会成空二文档）。
const parseFrontmatterByYaml = (fenced: string): Record<string, unknown> =>
  parseYaml(fenced.replace(/\n---$/u, "")) as Record<string, unknown>;
import {
  buildFrontmatterBlock,
  readFrontmatterScalars,
  roundTripCheckFrontmatter,
  writeFrontmatterChecked,
  yamlQuoteScalar,
  ConfigWriteError,
} from "../src/kernel/configWriteModel.ts";

// 合成负例族（施工单指定四族+引号/反斜杠/控制字符/围栏变体；全部合成材料）。
const PAYLOADS: Array<{ name: string; value: string }> = [
  { name: "冒号值（映射注入）", value: "正常前缀: 后半段想变成另一个键" },
  { name: "多行（块结构注入）", value: "第一行\n第二行\n  - 看似列表项\n第三行" },
  { name: "锚点与别名", value: "前情 &a 锚点 *a 别名引用" },
  { name: "YAML 标签", value: "!!python/object/apply:os.system 伪载荷" },
  { name: "双引号与反斜杠", value: "含\"双引号\"与\\反斜杠\\n字面" },
  { name: "制表与回车", value: "a\tb\rc" },
  { name: "围栏伪装", value: "---\nname: evil\n---" },
  { name: "注释伪装", value: "正文 # 想截断成注释" },
  { name: "纯数字/布尔伪装", value: "123" },
  { name: "中英混排正常描述", value: "写文书前先列证据清单再动笔的固定做法" },
];

function expectCode(fn: () => unknown, code: string) {
  try {
    fn();
  } catch (error) {
    expect(error).toBeInstanceOf(ConfigWriteError);
    expect((error as ConfigWriteError).message).toBe(code);
    return;
  }
  throw new Error(`期望抛 ${code}，实际未抛`);
}

describe("configWriteModel · 引号化与纯标量（safe dump）", () => {
  it.each(PAYLOADS)("payload=$name 写出为单行双引号标量", ({ value }) => {
    const quoted = yamlQuoteScalar(value);
    expect(quoted.startsWith('"')).toBe(true);
    expect(quoted.endsWith('"')).toBe(true);
    expect(quoted.includes("\n")).toBe(false);
    // 标准 YAML 解析器读回：恰为 string 纯标量且逐字相等（不是 number/boolean/map/alias）。
    const parsed = parseFrontmatterByYaml(`k: ${quoted}`);
    expect(parsed.k).toBe(value);
    expect(typeof parsed.k).toBe("string");
  });

  it("yamlQuoteScalar 拒绝非标量类型输入", () => {
    expectCode(() => yamlQuoteScalar({} as unknown as string), "cfgwrite_field_invalid");
    expectCode(() => yamlQuoteScalar(null as unknown as string), "cfgwrite_field_invalid");
  });
});

describe("configWriteModel · 键名禁来自用户原文（键闭集闸）", () => {
  it("冒号键/空格键/前导连字符键一律 typed 拒", () => {
    expectCode(() => buildFrontmatterBlock([{ key: "evil: &a", value: "x" }]), "cfgwrite_key_invalid");
    expectCode(() => buildFrontmatterBlock([{ key: "a b", value: "x" }]), "cfgwrite_key_invalid");
    expectCode(() => buildFrontmatterBlock([{ key: "-x", value: "x" }]), "cfgwrite_key_invalid");
    expectCode(() => buildFrontmatterBlock([{ key: "", value: "x" }]), "cfgwrite_key_invalid");
  });

  it("JS 原型面危险键（__proto__/constructor/prototype）typed 拒", () => {
    expectCode(() => buildFrontmatterBlock([{ key: "__proto__", value: "x" }]), "cfgwrite_key_invalid");
    expectCode(() => buildFrontmatterBlock([{ key: "constructor", value: "x" }]), "cfgwrite_key_invalid");
    expectCode(() => buildFrontmatterBlock([{ key: "prototype", value: "x" }]), "cfgwrite_key_invalid");
  });

  it("重复键 typed 拒（防同键覆盖丢字段）", () => {
    expectCode(
      () => buildFrontmatterBlock([{ key: "name", value: "a" }, { key: "name", value: "b" }]),
      "cfgwrite_duplicate_key",
    );
  });
});

describe("configWriteModel · 写入前 round-trip 校验（结构键集合零变化）", () => {
  it.each(PAYLOADS)("payload=$name 全族过 writeFrontmatterChecked 后键集合零变化", ({ value }) => {
    const text = writeFrontmatterChecked(
      [
        { key: "name", value: "payload-skill" },
        { key: "description", value },
      ],
      ["name", "description"],
    );
    // 自家严格读回：键集合恰等于闭集、值逐字相等。
    const own = readFrontmatterScalars(text)!;
    expect(Object.keys(own).sort()).toEqual(["description", "name"]);
    expect(own.description).toBe(value);
    // 标准 YAML 解析器独立对拍：顶层键集合零变化、每个值都是 string 纯标量。
    const byYaml = parseFrontmatterByYaml(text);
    expect(Object.keys(byYaml).sort()).toEqual(["description", "name"]);
    expect(byYaml.description).toBe(value);
    expect(typeof byYaml.name).toBe("string");
    expect(typeof byYaml.description).toBe("string");
  });

  it("expectedKeys 与字段键集合不一致=typed 拒（多键/少键都不放行）", () => {
    const fields = [{ key: "name", value: "a" }, { key: "description", value: "b" }];
    expectCode(() => writeFrontmatterChecked(fields, ["name"]), "cfgwrite_roundtrip_mismatch");
    expectCode(
      () => writeFrontmatterChecked(fields, ["name", "description", "extra"]),
      "cfgwrite_roundtrip_mismatch",
    );
  });

  it("注入加行/换键/裸值变形在 roundTripCheckFrontmatter 全部 typed 拒", () => {
    const good = writeFrontmatterChecked(
      [{ key: "name", value: "a" }, { key: "description", value: "b: &c *d !!e" }],
      ["name", "description"],
    );
    const lines = good.split("\n");
    const injected = [...lines.slice(0, 3), 'injected: "x"', ...lines.slice(3)].join("\n");
    expectCode(() => roundTripCheckFrontmatter(injected, ["name", "description"]), "cfgwrite_roundtrip_mismatch");
    expectCode(() => roundTripCheckFrontmatter(good, ["name", "description", "injected"]), "cfgwrite_roundtrip_mismatch");
    // 裸值形态（引号化被剥掉）=形态不符拒：注入面读不回来即拦。
    const bare = good.replace('name: "a"', "name: a");
    expectCode(() => roundTripCheckFrontmatter(bare, ["name", "description"]), "cfgwrite_roundtrip_shape");
    // 未闭合围栏拒。
    expectCode(() => roundTripCheckFrontmatter(good.slice(1), ["name", "description"]), "cfgwrite_roundtrip_shape");
  });

  it("合格文本 roundTripCheckFrontmatter 返回读回键值（回执面）", () => {
    const text = writeFrontmatterChecked([{ key: "title", value: "多行\n标题" }], ["title"]);
    const parsed = roundTripCheckFrontmatter(text, ["title"]);
    expect(parsed.title).toBe("多行\n标题");
  });
});

import assert from "node:assert/strict";
import { test } from "node:test";
import {
  assertInjectListsHitLockPackages,
  assertInjectNamesInLockPackages,
} from "./assert-inject-lock-packages.mjs";

test("exported inject lists hit lock packages, including Feishu", async () => {
  const { REQUIRED_ASAR_RUNTIME_MODULES } = await import("../electron-builder.config.js");
  const { requiredRuntimeModules } = await import("./bundle.mjs");
  assert.ok(REQUIRED_ASAR_RUNTIME_MODULES.includes("@larksuiteoapi/node-sdk"));
  assert.ok(requiredRuntimeModules.includes("@larksuiteoapi/node-sdk"));
  assertInjectListsHitLockPackages();
});

test("a name that is not its own lock package fails", () => {
  assert.throws(
    () =>
      assertInjectNamesInLockPackages(
        ["dead-inject-root"],
        "packages:\n  forms@1.0.0:\n  dead-inject-root-extra@1.0.0:\n\nsnapshots:\n",
      ),
    /dead-inject-root/,
  );
});

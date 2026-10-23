import type { TFunction } from "i18next";
import { describe, expect, it } from "vitest";

import { nodeSchema, passwordSchema, setupSchema, usernameSchema } from "@/lib/validation";

const t = ((key: string) => key) as TFunction;

describe("username and password validation", () => {
  it("accepts a valid username", () => {
    expect(usernameSchema(t).safeParse("net.ops-1").success).toBe(true);
  });

  it("rejects invalid username characters", () => {
    expect(usernameSchema(t).safeParse("bad user").success).toBe(false);
  });

  it("requires 12 characters and three character classes", () => {
    expect(passwordSchema(t).safeParse("short").success).toBe(false);
    expect(passwordSchema(t).safeParse("onlylowercase").success).toBe(false);
    expect(passwordSchema(t).safeParse("ValidPassword9!").success).toBe(true);
  });

  it("rejects a password identical to the username", () => {
    expect(passwordSchema(t, "netops").safeParse("netops").success).toBe(false);
  });

  it("checks the confirmation in the setup schema", () => {
    const schema = setupSchema(t);
    const base = { username: "netops", password: "ValidPassword9!", confirm_password: "DifferentPass9!", language: "es", theme: "system" as const };
    expect(schema.safeParse(base).success).toBe(false);
    expect(schema.safeParse({ ...base, confirm_password: base.password }).success).toBe(true);
  });
});

describe("node validation", () => {
  it("accepts a realistic node", () => {
    const result = nodeSchema(t).safeParse({
      name: "core-sw-01",
      address: "10.20.0.11",
      model: "ios",
      group_name: "__none__",
      input: "ssh",
      port: 22,
      username: "netops",
      output: "",
      prompt: "",
      timeout_seconds: Number.NaN,
    });
    expect(result.success).toBe(true);
  });

  it("rejects a malformed node name and model", () => {
    const schema = nodeSchema(t);
    expect(schema.safeParse({ name: "core/sw", model: "ios" }).success).toBe(false);
    expect(schema.safeParse({ name: "core", model: "bad model" }).success).toBe(false);
    expect(schema.safeParse({ name: "core", model: "" }).success).toBe(false);
  });
});

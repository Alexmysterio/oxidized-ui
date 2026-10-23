import type { TFunction } from "i18next";
import { describe, expect, it, vi } from "vitest";

import { ApiError } from "@/lib/api";
import { errorCodeMessage, errorMessage, fieldErrorMessage } from "@/lib/errors";

const t = vi.fn((key: string, options?: Record<string, unknown>) => `${key}:${JSON.stringify(options ?? {})}`) as unknown as TFunction;

describe("API error translation", () => {
  it("translates stable error codes with parameters", () => {
    const error = new ApiError(409, "node.duplicate_name", { name: "core" });
    expect(errorMessage(t, error)).toContain("errors.node.duplicate_name");
    expect(errorMessage(t, error)).toContain("core");
  });

  it("supports plain error codes and fallbacks", () => {
    expect(errorCodeMessage(t, "auth.forbidden")).toContain("errors.auth.forbidden");
    expect(errorMessage(t, new Error("boom"))).toBe("boom");
  });

  it("translates field errors", () => {
    const message = fieldErrorMessage(t, { path: "name", code: "validation.invalid_format", params: { field: "name" } });
    expect(message).toContain("errors.validation.invalid_format");
    expect(message).toContain("name");
  });
});

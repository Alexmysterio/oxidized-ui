import { describe, expect, it } from "vitest";

import { formatDate, formatDateTime, formatNumber, formatRelative } from "@/lib/format";

describe("Intl formatting", () => {
  it("formats timestamps with an explicit timezone", () => {
    const value = formatDateTime("2026-10-21T20:00:00Z", "en", "UTC");
    expect(value).toContain("Oct");
    expect(value).toContain("2026");
    expect(value).toContain("8:00");
  });

  it("formats dates and numbers with the selected locale", () => {
    expect(formatDate("2026-10-21T20:00:00Z", "en", "UTC")).toContain("2026");
    expect(formatNumber(1234.5, "en")).toBe("1,234.5");
  });

  it("formats relative times", () => {
    const now = new Date("2026-10-21T20:00:00Z");
    expect(formatRelative("2026-10-21T19:55:00Z", "en", now)).toMatch(/5 minutes ago/);
  });
});

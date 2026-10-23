import { describe, expect, it } from "vitest";

import { getPath, humanizeKey, removeEmpty, setPath, truncate } from "@/lib/utils";

describe("object path helpers", () => {
  const source = {
    output: { default: "git", git: { single_repo: true } },
    groups: { core: { username: "netops" } },
  };

  it("reads nested values", () => {
    expect(getPath(source, "output.git.single_repo")).toBe(true);
    expect(getPath(source, "groups.core.username")).toBe("netops");
    expect(getPath(source, "missing.path")).toBeUndefined();
  });

  it("sets values without mutating the original object", () => {
    const updated = setPath(source, "output.git.user", "Oxidized");
    expect((updated.output as Record<string, unknown>).git).toMatchObject({ user: "Oxidized" });
    expect((source.output.git as Record<string, unknown>).user).toBeUndefined();
  });

  it("removes empty values from paths", () => {
    const updated = setPath(source, "output.default", "");
    expect((updated.output as Record<string, unknown>).default).toBeUndefined();
  });

  it("creates intermediate objects", () => {
    const updated = setPath(source, "a.b.c", 3);
    expect(getPath(updated, "a.b.c")).toBe(3);
  });
});

describe("display helpers", () => {
  it("normalizes technical keys", () => {
    expect(humanizeKey("next_adds_job")).toBe("Next Adds Job");
  });

  it("truncates with an ellipsis", () => {
    expect(truncate("abcdefgh", 5)).toBe("abcd…");
  });

  it("drops empty leaf values recursively", () => {
    expect(removeEmpty({ a: "", b: { c: "", d: 1 }, e: [""] })).toEqual({ b: { d: 1 }, e: [] });
  });
});

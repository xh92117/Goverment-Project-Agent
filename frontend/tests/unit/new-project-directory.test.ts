import { describe, expect, it } from "vitest";

import {
  isNewProjectDirectoryReady,
  newProjectRootPath,
} from "@/features/projects/new-project-directory";

describe("new project directory selection", () => {
  it("requires the user to choose a path mode", () => {
    expect(isNewProjectDirectoryReady(null, "")).toBe(false);
  });

  it("accepts the default path without a custom directory", () => {
    expect(isNewProjectDirectoryReady("default", "")).toBe(true);
    expect(newProjectRootPath("default", "C:\\ignored")).toBeNull();
  });

  it("requires and normalizes a custom directory", () => {
    expect(isNewProjectDirectoryReady("custom", "  ")).toBe(false);
    expect(isNewProjectDirectoryReady("custom", " C:\\Projects\\申报 ")).toBe(
      true,
    );
    expect(newProjectRootPath("custom", " C:\\Projects\\申报 ")).toBe(
      "C:\\Projects\\申报",
    );
  });
});

import { describe, expect, it } from "vitest";

import { threadsWithoutAvailableProject } from "@/shared/layout/workspace-thread-groups";

describe("workspace thread groups", () => {
  const threads = [
    { thread_id: "standalone", metadata: {} },
    { thread_id: "available", metadata: { project_id: "project-a" } },
    { thread_id: "orphaned", metadata: { project_id: "project-missing" } },
  ];

  it("keeps standalone and orphaned history visible", () => {
    expect(
      threadsWithoutAvailableProject(threads, [
        { project_id: "project-a" },
      ]).map((thread) => thread.thread_id),
    ).toEqual(["standalone", "orphaned"]);
  });

  it("keeps every thread visible when no project records are available", () => {
    expect(
      threadsWithoutAvailableProject(threads, []).map(
        (thread) => thread.thread_id,
      ),
    ).toEqual(["standalone", "available", "orphaned"]);
  });
});

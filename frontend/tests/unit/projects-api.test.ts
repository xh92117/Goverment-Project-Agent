import { afterEach, describe, expect, it, vi } from "vitest";

import {
  createProject,
  selectNewProjectDirectory,
} from "@/features/projects/api";

afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

describe("projects api", () => {
  it("sends a custom root path while creating a project", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      Response.json({
        project_id: "project-1",
        name: "申报项目",
        type: "government-project-declaration",
        status: "active",
        root_path: "C:\\Projects\\申报",
        created_at: "2026-07-28T00:00:00Z",
        updated_at: "2026-07-28T00:00:00Z",
      }),
    );
    vi.stubGlobal("fetch", fetchMock);

    await createProject({
      name: "申报项目",
      root_path: "C:\\Projects\\申报",
    });

    const [, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(typeof init.body).toBe("string");
    expect(JSON.parse(init.body as string)).toMatchObject({
      name: "申报项目",
      root_path: "C:\\Projects\\申报",
    });
  });

  it("opens the pre-create directory selector with an optional initial path", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValue(
        Response.json({
          selection_id: "selection-1",
          status: "selected",
          selected: true,
          root_path: "C:\\Projects",
        }),
      );
    vi.stubGlobal("fetch", fetchMock);

    await selectNewProjectDirectory(" C:\\Projects ");

    expect(fetchMock).toHaveBeenCalledWith(
      "/api/projects/directory/select",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({ initial_path: "C:\\Projects" }),
      }),
    );
  });

  it("polls a directory selection without keeping one HTTP request open", async () => {
    vi.useFakeTimers();
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(
        Response.json({
          selection_id: "selection-2",
          status: "pending",
          selected: false,
        }),
      )
      .mockResolvedValueOnce(
        Response.json({
          selection_id: "selection-2",
          status: "selected",
          selected: true,
          root_path: "C:\\Projects",
        }),
      );
    vi.stubGlobal("fetch", fetchMock);

    const selection = selectNewProjectDirectory();
    await vi.advanceTimersByTimeAsync(300);

    await expect(selection).resolves.toMatchObject({
      status: "selected",
      root_path: "C:\\Projects",
    });
    expect(fetchMock).toHaveBeenNthCalledWith(
      2,
      "/api/projects/directory/select/selection-2",
      expect.objectContaining({ credentials: "include" }),
    );
  });
});

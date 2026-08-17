import { afterEach, describe, expect, it, vi } from "vitest";

import {
  createProject,
  downloadProjectFile,
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
    const fetchMock = vi.fn().mockResolvedValue(
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

  it("downloads both project files and thread output files", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(new Response(new Blob(["project file"])))
      .mockResolvedValueOnce(new Response(new Blob(["thread file"])));
    vi.stubGlobal("fetch", fetchMock);

    const projectBlob = await downloadProjectFile("project-1", {
      source: "project",
      read_path: "outputs/申报书.md",
    });
    const threadBlob = await downloadProjectFile("project-1", {
      source: "thread",
      read_path: "reports/研究综述.md",
      thread_id: "thread-1",
    });

    expect(await projectBlob.text()).toBe("project file");
    expect(await threadBlob.text()).toBe("thread file");
    expect(fetchMock).toHaveBeenNthCalledWith(
      1,
      "/api/projects/project-1/files/download?path=outputs%2F%E7%94%B3%E6%8A%A5%E4%B9%A6.md&source=project",
      expect.objectContaining({ credentials: "include" }),
    );
    expect(fetchMock).toHaveBeenNthCalledWith(
      2,
      "/api/projects/project-1/files/download?path=reports%2F%E7%A0%94%E7%A9%B6%E7%BB%BC%E8%BF%B0.md&source=thread&thread_id=thread-1",
      expect.objectContaining({ credentials: "include" }),
    );
  });
});

import { readFileSync } from "node:fs";

import { afterEach, describe, expect, it, vi } from "vitest";

import {
  buildKnowledgeIndex,
  listKnowledgeBuildJobs,
  processIncomingAndBuildKnowledgeIndex,
} from "@/features/knowledge/api";

afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

describe("knowledge build jobs", () => {
  const pageSource = readFileSync(
    new URL("../../src/features/knowledge/knowledge-page.tsx", import.meta.url),
    "utf8",
  );

  it("starts a background build, reports progress and polls its result", async () => {
    vi.useFakeTimers();
    const queued = {
      job_id: "job-1",
      state: "running",
      progress: {
        stage: "indexing",
        current: 1,
        total: 3,
        percent: 35,
        message: "正在解析文件",
      },
      created_at: "2026-01-01T00:00:00Z",
    };
    const completed = {
      ...queued,
      state: "completed",
      progress: {
        stage: "completed",
        current: 3,
        total: 3,
        percent: 100,
        message: "构建完成",
      },
      result: {
        scanned_files: 3,
        created: 4,
        updated: 0,
        skipped: 0,
        quality_report: {
          enabled: true,
          passed: true,
          score: 100,
          checked_entries: 4,
          error_count: 0,
          warning_count: 0,
          metrics: { body_coverage: 1 },
          issues: [],
        },
      },
    };
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(Response.json(queued, { status: 202 }))
      .mockResolvedValueOnce(Response.json(completed));
    vi.stubGlobal("fetch", fetchMock);
    const progress = vi.fn();

    const build = buildKnowledgeIndex(undefined, "private", progress);
    await vi.advanceTimersByTimeAsync(750);

    await expect(build).resolves.toMatchObject({
      scanned_files: 3,
      quality_report: { passed: true },
    });
    expect(progress).toHaveBeenCalledTimes(2);
    expect(fetchMock).toHaveBeenNthCalledWith(
      1,
      "/api/knowledge/index/build-jobs?scope=private",
      expect.objectContaining({ method: "POST" }),
    );
    expect(fetchMock).toHaveBeenNthCalledWith(
      2,
      "/api/knowledge/index/build-jobs/job-1?scope=private",
      expect.objectContaining({ credentials: "include" }),
    );
  });

  it("surfaces a failed background build", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      Response.json(
        {
          job_id: "job-2",
          state: "failed",
          progress: {
            stage: "failed",
            current: 0,
            total: 0,
            percent: 100,
            message: "构建失败",
          },
          error: "Embedding API unavailable",
          created_at: "2026-01-01T00:00:00Z",
        },
        { status: 202 },
      ),
    );
    vi.stubGlobal("fetch", fetchMock);

    await expect(buildKnowledgeIndex()).rejects.toThrow(
      "Embedding API unavailable",
    );
  });

  it("starts organization as a background job", async () => {
    const queued = {
      job_id: "job-organize",
      operation: "organize_and_build",
      state: "queued",
      progress: {
        stage: "queued",
        current: 0,
        total: 0,
        percent: 0,
        message: "整理与构建任务已排队。",
      },
      created_at: "2026-01-01T00:00:00Z",
    };
    const fetchMock = vi
      .fn()
      .mockResolvedValue(Response.json(queued, { status: 202 }));
    vi.stubGlobal("fetch", fetchMock);

    await expect(
      processIncomingAndBuildKnowledgeIndex("public"),
    ).resolves.toMatchObject({
      job_id: "job-organize",
      operation: "organize_and_build",
    });
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/knowledge/index/process-incoming-jobs?scope=public",
      expect.objectContaining({ method: "POST" }),
    );
  });

  it("reloads persisted jobs so page refresh can recover progress", async () => {
    const running = {
      job_id: "job-running",
      operation: "organize_and_build",
      state: "running",
      progress: {
        stage: "indexing",
        current: 2,
        total: 5,
        percent: 48,
        message: "正在解析并分块：研究现状.pdf",
      },
      created_at: "2026-01-01T00:00:00Z",
    };
    const fetchMock = vi.fn().mockResolvedValue(Response.json([running]));
    vi.stubGlobal("fetch", fetchMock);

    await expect(listKnowledgeBuildJobs("private")).resolves.toEqual([running]);
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/knowledge/index/build-jobs?scope=private&limit=10",
      expect.objectContaining({ credentials: "include" }),
    );
  });

  it("polls active persisted jobs and explains refresh safety", () => {
    expect(pageSource).toContain("listKnowledgeBuildJobs(knowledgeScope)");
    expect(pageSource).toContain("refetchInterval");
    expect(pageSource).toContain("? 750");
    expect(pageSource).toContain("刷新或离开本页面不会中断构建");
    expect(pageSource).toContain("buildJob.progress.percent");
  });
});

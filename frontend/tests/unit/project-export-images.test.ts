import { readFileSync } from "node:fs";

import { afterEach, describe, expect, it, vi } from "vitest";

import { exportProjectFilesDocx } from "@/features/projects/api";

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("project Word image export", () => {
  it("sends the image-agent choice to the backend", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValue(new Response("docx", { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);

    await exportProjectFilesDocx(
      "project-1",
      [
        {
          name: "foundation.md",
          source: "project",
          read_path: "outputs/foundation.md",
        },
      ],
      "merged",
      "Project",
      { includeImages: true, modelName: "qwen-selector" },
    );

    const request = fetchMock.mock.calls[0]?.[1] as RequestInit;
    expect(typeof request.body).toBe("string");
    const payload = JSON.parse(request.body as string);
    expect(payload.include_images).toBe(true);
    expect(payload.applicant_id).toBe("default");
    expect(payload.model_name).toBe("qwen-selector");
  });

  it("renders an explicit image choice in the export modal", () => {
    const source = readFileSync(
      new URL(
        "../../src/features/projects/project-workspace-page.tsx",
        import.meta.url,
      ),
      "utf8",
    );
    const modalStart = source.indexOf('aria-labelledby="export-modal-title"');
    const modalSource = source.slice(modalStart);

    expect(modalSource).toContain("是否插入图片");
    expect(modalSource).toContain("不插入图片");
    expect(modalSource).toContain("智能匹配并插入");
    expect(modalSource).toContain("includeImages");
    expect(modalSource).not.toContain(
      "选择当前文件夹下需要导出的一个或多个文件。",
    );
    expect(modalSource).not.toContain(
      "合并导出生成一个 Word；单独导出生成包含多个 Word",
    );
    expect(modalSource).not.toContain(
      "开启后，智能体会匹配知识库中已人工确认的相关图片",
    );
    expect(modalSource).not.toContain("export-image-note");
    expect(modalSource).not.toContain("合并导出排序范本");
  });
});

import { readFileSync } from "node:fs";

import { describe, expect, it } from "vitest";

import {
  canManagePublicKnowledge,
  canReadPublicKnowledge,
  defaultKnowledgeScope,
} from "@/features/knowledge/knowledge-access";

describe("knowledge public scope", () => {
  const pageSource = readFileSync(
    new URL("../../src/features/knowledge/knowledge-page.tsx", import.meta.url),
    "utf8",
  );
  const apiSource = readFileSync(
    new URL("../../src/features/knowledge/api.ts", import.meta.url),
    "utf8",
  );

  it("allows only administrators to select the public knowledge base", () => {
    expect(
      canManagePublicKnowledge({
        kind: "authenticated",
        user: { id: "admin", email: null, system_role: "admin" },
      }),
    ).toBe(true);
    expect(
      canManagePublicKnowledge({
        kind: "authenticated",
        user: { id: "member", email: null, system_role: "user" },
      }),
    ).toBe(false);
    expect(canManagePublicKnowledge({ kind: "disabled" })).toBe(true);
    expect(canManagePublicKnowledge({ kind: "anonymous" })).toBe(false);
  });

  it("allows every authenticated user to read the public knowledge base", () => {
    expect(
      canReadPublicKnowledge({
        kind: "authenticated",
        user: { id: "member", email: null, system_role: "user" },
      }),
    ).toBe(true);
    expect(canReadPublicKnowledge({ kind: "anonymous" })).toBe(false);
  });

  it("defaults every authenticated user to public knowledge", () => {
    expect(
      defaultKnowledgeScope({
        kind: "authenticated",
        user: { id: "admin", email: null, system_role: "admin" },
      }),
    ).toBe("public");
    expect(
      defaultKnowledgeScope({
        kind: "authenticated",
        user: { id: "member", email: null, system_role: "user" },
      }),
    ).toBe("public");
  });

  it("renders public scope for readers while retaining admin-only management", () => {
    expect(pageSource).toContain("canReadPublic");
    expect(pageSource).toContain("canManagePublic");
    expect(pageSource).toContain('role="tablist"');
    expect(pageSource).toContain("公共知识库");
    expect(pageSource).toContain("我的知识库");
  });

  it("forwards scope to list, read, write, upload and download endpoints", () => {
    expect(apiSource).toContain("/api/knowledge/index/page?scope=${scope}");
    expect(apiSource).toContain("/api/knowledge/files/read?scope=${scope}");
    expect(apiSource).toContain("/api/knowledge/files/save?scope=${scope}");
    expect(apiSource).toContain('scope: KnowledgeScope = "private"');
    expect(apiSource).toContain(
      "new URLSearchParams({ file_path: filePath, scope })",
    );
  });

  it("shows DOCX upload, pending-ingest and error feedback", () => {
    expect(pageSource).toContain(".docx");
    expect(pageSource).toContain("待整理入库");
    expect(pageSource).toContain("DOCX");
    expect(pageSource).toContain("等文档已保存到待整理区");
    expect(pageSource).toContain("upload.isError");
    expect(pageSource).toContain("upload.data?.warnings");
  });
});

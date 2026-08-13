import { readFileSync } from "node:fs";

import { describe, expect, it } from "vitest";

describe("knowledge image model dialog", () => {
  const pageSource = readFileSync(
    new URL("../../src/features/knowledge/knowledge-page.tsx", import.meta.url),
    "utf8",
  );
  const apiSource = readFileSync(
    new URL("../../src/features/knowledge/api.ts", import.meta.url),
    "utf8",
  );

  it("keeps the image model status entry in the knowledge page header", () => {
    const heroStart = pageSource.indexOf('<section className="kb-hero">');
    const heroEnd = pageSource.indexOf("</section>", heroStart);
    const heroSource = pageSource.slice(heroStart, heroEnd);

    expect(heroSource).toContain("图片识别模型");
    expect(heroSource).toContain('aria-haspopup="dialog"');
    expect(heroSource).toContain(
      'aria-controls="knowledge-image-model-dialog"',
    );
    expect(heroSource).toContain("kb-image-model-dot");
    expect(heroSource).toContain("className={`kb-image-model-status ${");
    expect(heroSource).toContain("kb-image-model-label");
    expect(heroSource).not.toContain("<small>图片识别模型</small>");
    expect(heroSource).toContain(
      "\u56fe\u7247\u8bc6\u522b\u6a21\u578b\u672a\u914d\u7f6e",
    );
  });

  it("renders a top-layer accessible selection dialog", () => {
    expect(pageSource).toContain('id="knowledge-image-model-dialog"');
    expect(pageSource).toContain('role="dialog"');
    expect(pageSource).toContain('aria-modal="true"');
    expect(pageSource).toContain("知识库图片识别模型");
  });

  it("loads and persists the dedicated knowledge image model setting", () => {
    expect(apiSource).toContain("loadKnowledgeImageModelSettings");
    expect(apiSource).toContain("updateKnowledgeImageModelSettings");
    expect(apiSource).toContain('"/api/settings/knowledge-image-model"');
  });

  it("migrates the settings model form and marks created models as vision capable", () => {
    expect(pageSource).toContain("modelProviderOptions");
    expect(pageSource).toContain('aria-label="\u6a21\u578b\u4f9b\u5e94\u5546"');
    expect(pageSource).toContain('placeholder="\u6a21\u578b\u540d\u79f0"');
    expect(pageSource).toContain('placeholder="URL"');
    expect(pageSource).toContain('placeholder="API Key"');
    expect(apiSource).toContain("createKnowledgeImageModel");
    expect(apiSource).toContain("supports_vision: true");
  });
});

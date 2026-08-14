import { readFileSync } from "node:fs";

import { describe, expect, it } from "vitest";

describe("knowledge build model dialog", () => {
  const pageSource = readFileSync(
    new URL("../../src/features/knowledge/knowledge-page.tsx", import.meta.url),
    "utf8",
  );
  const apiSource = readFileSync(
    new URL("../../src/features/knowledge/api.ts", import.meta.url),
    "utf8",
  );

  it("keeps the knowledge model status entry in the knowledge page header", () => {
    const heroStart = pageSource.indexOf('<section className="kb-hero">');
    const heroEnd = pageSource.indexOf("</section>", heroStart);
    const heroSource = pageSource.slice(heroStart, heroEnd);

    expect(heroSource).toContain("知识库构建模型");
    expect(heroSource).toContain('aria-haspopup="dialog"');
    expect(heroSource).toContain(
      'aria-controls="knowledge-image-model-dialog"',
    );
    expect(heroSource).toContain("kb-image-model-dot");
    expect(heroSource).toContain("className={`kb-image-model-status ${");
    expect(heroSource).toContain("kb-image-model-label");
    expect(heroSource).toContain("知识库模型未配置");
  });

  it("renders a top-layer accessible selection dialog", () => {
    expect(pageSource).toContain('id="knowledge-image-model-dialog"');
    expect(pageSource).toContain('role="dialog"');
    expect(pageSource).toContain('aria-modal="true"');
    expect(pageSource).toContain("知识库构建模型");
    expect(pageSource).toContain("语义分块和元数据归类");
    expect(pageSource).toContain('model.supports_vision ? "支持图片" : "仅文本"');
  });

  it("loads and persists the model selected by the knowledge page", () => {
    expect(apiSource).toContain("loadKnowledgeModelSettings");
    expect(apiSource).toContain("updateKnowledgeModelSettings");
    expect(apiSource).toContain('"/api/settings/knowledge-model"');
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

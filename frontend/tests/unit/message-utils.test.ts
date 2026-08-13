import { describe, expect, it } from "vitest";

import { normalizeAssistantMarkdown, prepareAssistantContent } from "@/features/chat/message-utils";

describe("normalizeAssistantMarkdown", () => {
  it("separates glued headings and markdown tables", () => {
    const normalized = normalizeAssistantMarkdown(
      "## 核心结论###主要检测方法对比|方法 |冷缝检测能力 |\n|:--|:--:|",
    );

    expect(normalized).toContain("## 核心结论\n\n### 主要检测方法对比\n\n|方法 |冷缝检测能力 |");
    expect(normalized).toContain("\n|:--|:--:|");
  });

  it("separates glued numbered findings after headings and Chinese text", () => {
    const normalized = normalizeAssistantMarkdown(
      "###关键发现1. **技术瓶颈**：闭合型冷缝是共同难点2. **标准空白**：暂无专门规程",
    );

    expect(normalized).toContain("### 关键发现\n\n1. **技术瓶颈**");
    expect(normalized).toContain("共同难点\n2. **标准空白**");
  });

  it("normalizes numeric headings and trailing separators from generated reports", () => {
    const normalized = normalizeAssistantMarkdown(
      "# 隧道衬砌结构施工冷缝无损检测技术研究现状---\n二、主要技术路线及其冷缝适用性分析###2.1地质雷达法（GPR）",
    );

    expect(normalized).toContain(
      "# 隧道衬砌结构施工冷缝无损检测技术研究现状\n\n---",
    );
    expect(normalized).toContain(
      "二、主要技术路线及其冷缝适用性分析\n\n### 2.1地质雷达法（GPR）",
    );
  });

  it("separates report headings from blockquotes and glued prose", () => {
    const normalized = normalizeAssistantMarkdown(
      "专项检索。##隧道衬砌结构施工冷缝无损检测技术研究现状> **说明**：知识库中未检索到直接相关材料。\n\n###一、总体判断隧道衬砌施工冷缝是传统无损检测方法的检测盲区。\n\n###六、项目申报切入点建议本项目宜以多方法联合检测为核心。\n- IAEA Guide- Sansalone Method",
    );

    expect(normalized).toContain(
      "专项检索。\n\n## 隧道衬砌结构施工冷缝无损检测技术研究现状\n\n> **说明**",
    );
    expect(normalized).toContain(
      "### 一、总体判断\n\n隧道衬砌施工冷缝是传统无损检测方法的检测盲区。",
    );
    expect(normalized).toContain(
      "### 六、项目申报切入点建议\n\n本项目宜以多方法联合检测为核心。",
    );
    expect(normalized).toContain("- IAEA Guide\n- Sansalone Method");
  });

  it("does not normalize markdown-like text inside fenced code blocks", () => {
    const normalized = normalizeAssistantMarkdown(
      "前言###标题\n```md\n###2.1raw---\n```\n结论###2.2结果",
    );

    expect(normalized).toContain("前言\n\n### 标题");
    expect(normalized).toContain("```md\n###2.1raw---\n```");
    expect(normalized).toContain("结论\n\n### 2.2结果");
  });

  it("normalizes numbered subsection labels and repeated quote delimiters", () => {
    const normalized = normalizeAssistantMarkdown(
      '2.3热成像方法："隧道衬砌冷缝""""混凝土冷缝超声"',
    );

    expect(normalized).toContain("2.3 热成像方法");
    expect(normalized).toContain('"隧道衬砌冷缝" "混凝土冷缝超声"');
  });

  it("extracts bare citation markers without showing raw citation syntax", () => {
    const prepared = prepareAssistantContent(
      "多方法融合是趋势。[citation:SHRP2 S2-R06A-RR-1]",
    );

    expect(prepared.content).toBe("多方法融合是趋势。");
    expect(prepared.citations).toEqual([
      { kind: "web", title: "SHRP2 S2-R06A-RR-1" },
    ]);
  });
});

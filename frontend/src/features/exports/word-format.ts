export interface WordFormatOptions {
  bodyFont: string;
  bodyFontSizePt: number;
  lineSpacing: number;
  headingFont: string;
  headingStartLevel: number;
}

export const DEFAULT_WORD_FORMAT: WordFormatOptions = {
  bodyFont: "仿宋",
  bodyFontSizePt: 12,
  lineSpacing: 1.5,
  headingFont: "黑体",
  headingStartLevel: 1,
};

export const WORD_FONT_OPTIONS = [
  "仿宋",
  "宋体",
  "黑体",
  "楷体",
  "微软雅黑",
] as const;

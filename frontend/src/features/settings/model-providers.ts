export const modelProviderOptions = [
  {
    value: "deepseek",
    label: "DeepSeek",
    url: "https://api.deepseek.com/v1",
  },
  {
    value: "openai",
    label: "OpenAI",
    url: "https://api.openai.com/v1",
  },
  {
    value: "anthropic",
    label: "Anthropic Claude",
    url: "https://api.anthropic.com",
  },
  {
    value: "google",
    label: "Google Gemini",
    url: "https://generativelanguage.googleapis.com/v1beta/openai/",
  },
  {
    value: "qwen",
    label: "阿里通义千问 / 百炼",
    url: "https://dashscope.aliyuncs.com/compatible-mode/v1",
  },
  {
    value: "moonshot",
    label: "Moonshot Kimi",
    url: "https://api.moonshot.cn/v1",
  },
  {
    value: "zhipu",
    label: "智谱 GLM",
    url: "https://open.bigmodel.cn/api/paas/v4",
  },
  {
    value: "minimax",
    label: "MiniMax",
    url: "https://api.minimaxi.com/v1",
  },
  {
    value: "baidu",
    label: "百度文心 / 千帆",
    url: "https://qianfan.baidubce.com/v2",
  },
  {
    value: "tencent",
    label: "腾讯混元",
    url: "https://api.hunyuan.cloud.tencent.com/v1",
  },
  {
    value: "volcengine",
    label: "火山方舟 / 豆包",
    url: "https://ark.cn-beijing.volces.com/api/v3",
  },
  {
    value: "siliconflow",
    label: "硅基流动",
    url: "https://api.siliconflow.cn/v1",
  },
  {
    value: "mimo",
    label: "小米 MiMo",
    url: "https://api.xiaomimimo.com/v1",
  },
  {
    value: "openrouter",
    label: "OpenRouter",
    url: "https://openrouter.ai/api/v1",
  },
  {
    value: "ollama",
    label: "Ollama 本地",
    url: "http://127.0.0.1:11434/v1",
  },
  { value: "custom", label: "自定义", url: "" },
] as const;

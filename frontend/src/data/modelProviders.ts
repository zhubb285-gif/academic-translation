export const PROVIDERS = [
  {
    "id": "deepseek",
    "name": "DeepSeek",
    "tone": "blue",
    "base": "https://api.deepseek.com/v1",
    "model": "deepseek-chat",
    "description": "同一厂家共享连接，具体型号在下方选择与配置。",
    "models": [
      {
        "name": "DeepSeek Chat",
        "model_id": "deepseek-chat"
      },
      {
        "name": "DeepSeek Reasoner",
        "model_id": "deepseek-reasoner"
      }
    ]
  },
  {
    "id": "openai",
    "name": "OpenAI",
    "tone": "ivory",
    "base": "https://api.openai.com/v1",
    "model": "gpt-4o",
    "description": "同一厂家共享连接，具体型号在下方选择与配置。",
    "models": [
      {
        "name": "GPT-4o",
        "model_id": "gpt-4o"
      },
      {
        "name": "o3-mini",
        "model_id": "o3-mini"
      }
    ]
  },
  {
    "id": "anthropic",
    "name": "Anthropic",
    "tone": "coral",
    "base": "",
    "model": "claude-sonnet-4-5",
    "description": "同一厂家共享连接，具体型号在下方选择与配置。",
    "models": [
      {
        "name": "Claude Sonnet",
        "model_id": "claude-sonnet-4-5"
      }
    ]
  },
  {
    "id": "qwen",
    "name": "千问 Qwen",
    "tone": "lilac",
    "base": "https://dashscope.aliyuncs.com/compatible-mode/v1",
    "model": "qwen-plus",
    "description": "按你的百炼地域与工作空间调整接口地址；模型 ID 以控制台为准。",
    "models": [
      {
        "name": "Qwen Plus",
        "model_id": "qwen-plus"
      },
      {
        "name": "Qwen Max",
        "model_id": "qwen-max"
      }
    ]
  },
  {
    "id": "mimo",
    "name": "小米 MiMo",
    "tone": "orange",
    "base": "https://api.xiaomimimo.com/v1",
    "model": "",
    "description": "使用小米 MiMo 平台的 API Key；具体模型 ID 请从控制台复制。",
    "models": []
  },
  {
    "id": "moonshot",
    "name": "Kimi",
    "tone": "black",
    "base": "https://api.moonshot.cn/v1",
    "model": "kimi-k3",
    "description": "同一厂家共享连接，具体型号在下方选择与配置。",
    "models": [
      {
        "name": "Kimi K3",
        "model_id": "kimi-k3"
      }
    ]
  },
  {
    "id": "zhipu",
    "name": "智谱 GLM",
    "tone": "sky",
    "base": "https://open.bigmodel.cn/api/paas/v4",
    "model": "glm-5.3",
    "description": "同一厂家共享连接，具体型号在下方选择与配置。",
    "models": [
      {
        "name": "GLM 5.3",
        "model_id": "glm-5.3"
      }
    ]
  },
  {
    "id": "doubao",
    "name": "豆包",
    "tone": "teal",
    "base": "https://ark.cn-beijing.volces.com/api/v3",
    "model": "",
    "description": "填写火山方舟控制台提供的模型 ID 或 ep- 开头的推理接入点 ID。",
    "models": []
  },
  {
    "id": "minimax",
    "name": "MiniMax",
    "tone": "rose",
    "base": "https://api.minimaxi.com/v1",
    "model": "MiniMax-M2.7",
    "description": "同一厂家共享连接，具体型号在下方选择与配置。",
    "models": [
      {
        "name": "MiniMax M2.7",
        "model_id": "MiniMax-M2.7"
      },
      {
        "name": "MiniMax M3",
        "model_id": "MiniMax-M3"
      }
    ]
  },
  {
    "id": "google",
    "name": "Google Gemini",
    "tone": "mint",
    "base": "https://generativelanguage.googleapis.com/v1beta/openai",
    "model": "",
    "description": "使用 Gemini API 的密钥与 OpenAI 兼容接口；模型 ID 请从控制台复制。",
    "models": []
  },
  {
    "id": "custom",
    "name": "自定义模型",
    "tone": "green",
    "base": "",
    "model": "",
    "description": "添加你自己的模型或本地 OpenAI 兼容接口。",
    "models": []
  }
] as const
export type Provider = typeof PROVIDERS[number]["id"]
export const defaultModel = (id: string) => PROVIDERS.find(p => p.id === id)?.model || ""

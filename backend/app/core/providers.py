"""Provider defaults shared by translation, review and connection checks."""
PROVIDERS = {'deepseek': {'base': 'https://api.deepseek.com/v1', 'model': 'deepseek-chat'},
 'openai': {'base': 'https://api.openai.com/v1', 'model': 'gpt-4o'},
 'anthropic': {'base': '', 'model': 'claude-sonnet-4-5'},
 'qwen': {'base': 'https://dashscope.aliyuncs.com/compatible-mode/v1', 'model': 'qwen-plus'},
 'mimo': {'base': 'https://api.xiaomimimo.com/v1', 'model': ''},
 'moonshot': {'base': 'https://api.moonshot.cn/v1', 'model': 'kimi-k3'},
 'zhipu': {'base': 'https://open.bigmodel.cn/api/paas/v4', 'model': 'glm-5.3'},
 'doubao': {'base': 'https://ark.cn-beijing.volces.com/api/v3', 'model': ''},
 'minimax': {'base': 'https://api.minimaxi.com/v1', 'model': 'MiniMax-M2.7'},
 'google': {'base': 'https://generativelanguage.googleapis.com/v1beta/openai', 'model': ''},
 'custom': {'base': '', 'model': ''}}

def auth_headers(provider: str, key: str) -> dict:
    auth = {"api-key": key} if provider == "mimo" else {"Authorization": f"Bearer {key}"}
    return {**auth, "Content-Type": "application/json"}

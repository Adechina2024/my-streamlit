# 配置读取优先级：st.secrets → 环境变量 → 默认值
# ModelScope 等平台不支持 .streamlit/secrets.toml，必须走环境变量

# 阿里云百炼 API Key
_api_key_st = ""
_api_key_env = _os.environ.get("DASHSCOPE_API_KEY", "")
try:
    import streamlit as _st
    _api_key_st = _st.secrets.get("API_KEY", "")
except Exception:
    pass
API_KEY = _api_key_st or _api_key_env or "sk-cd4af317332a4fe2add39b8814f47b50"

# 模型配置
CHAT_MODEL_FAST = "qwen-turbo"       # 问答用，免费额度多，速度快
CHAT_MODEL_PREMIUM = "qwen-plus"      # 内容生成用，质量更高

# GitHub Token（用于自动提交用户上传数据到仓库）
_github_token_st = ""
_github_token_env = _os.environ.get("GITHUB_TOKEN", "")
try:
    import streamlit as _st2
    _github_token_st = _st2.secrets.get("GITHUB_TOKEN", "")
except Exception:
    pass
GITHUB_TOKEN = _github_token_st or _github_token_env

# GitHub 仓库信息（owner/repo 格式）
# Streamlit Cloud 部署时可自动检测，本地开发需设置环境变量
GITHUB_REPO = _os.environ.get("GITHUB_REPO", "Adechina2024/my-streamlit")
GITHUB_BRANCH = _os.environ.get("GITHUB_BRANCH", "main")

# 知识库配置（TF-IDF + jieba 本地检索，无需外部embedding）
_PROJECT_ROOT = _os.path.dirname(_os.path.abspath(__file__))
KNOWLEDGE_DIR = _os.path.join(_PROJECT_ROOT, "knowledge")
USER_UPLOADS_DIR = _os.path.join(_PROJECT_ROOT, "user_uploads")
KNOWLEDGE_INDEX_FILE = _os.path.join(_PROJECT_ROOT, "knowledge_index.json")

# 确保 user_uploads 目录存在
_os.makedirs(USER_UPLOADS_DIR, exist_ok=True)

# 阿里云百炼API配置（DashScope OpenAI兼容模式）
# 部署环境：从 Streamlit secrets 读取
# 本地开发：从环境变量或直接填写回退
try:
    import streamlit as _st
    API_KEY = _st.secrets["API_KEY"]
except (KeyError, ModuleNotFoundError, RuntimeError):
    import os as _os
    API_KEY = _os.environ.get("DASHSCOPE_API_KEY", "sk-cd4af317332a4fe2add39b8814f47b50")

# 模型配置
CHAT_MODEL_FAST = "qwen-turbo"       # 问答用，免费额度多，速度快
CHAT_MODEL_PREMIUM = "qwen-plus"      # 内容生成用，质量更高

# GitHub Token（用于自动提交用户上传数据到仓库）
# 部署环境：从 Streamlit secrets 读取
# 本地开发：从环境变量读取
try:
    import streamlit as _st2
    GITHUB_TOKEN = _st2.secrets.get("GITHUB_TOKEN", "")
except (KeyError, ModuleNotFoundError, RuntimeError):
    GITHUB_TOKEN = _os.environ.get("GITHUB_TOKEN", "")

# 知识库配置（TF-IDF + jieba 本地检索，无需外部embedding）
import os as _os
_PROJECT_ROOT = _os.path.dirname(_os.path.abspath(__file__))
KNOWLEDGE_DIR = _os.path.join(_PROJECT_ROOT, "knowledge")
USER_UPLOADS_DIR = _os.path.join(_PROJECT_ROOT, "user_uploads")
KNOWLEDGE_INDEX_FILE = _os.path.join(_PROJECT_ROOT, "knowledge_index.json")

# 确保 user_uploads 目录存在
_os.makedirs(USER_UPLOADS_DIR, exist_ok=True)

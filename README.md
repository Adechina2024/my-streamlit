---
title: 珠宝AI内容工具
sdk: streamlit
app_port: 8501
entry_file: app.py
---

# 珠宝AI内容工具

基于 Streamlit 的珠宝行业AI内容生成平台，集成知识库管理与智能问答。

## 功能

- **知识库管理**：支持上传 PDF/TXT/MD 文档，自动构建向量索引
- **智能问答**：基于知识库的精准问答，支持引用来源
- **内容生成**：基于 RAG 的内容创作辅助
- **数据同步**：用户上传自动同步到 GitHub

## 技术栈

- Streamlit 前端
- TF-IDF + jieba 本地检索
- 阿里云百炼 DashScope API（qwen-turbo / qwen-plus）
- GitHub REST API 持久化

## 环境变量

| 变量名 | 说明 | 必填 |
|--------|------|------|
| DASHSCOPE_API_KEY | 阿里云百炼 API Key | ✅ |
| GITHUB_TOKEN | GitHub Personal Access Token | ✅ |
| GITHUB_REPO | GitHub 仓库名（owner/repo 格式） | ✅ |
| GITHUB_BRANCH | GitHub 分支名（默认 main） | 可选 |

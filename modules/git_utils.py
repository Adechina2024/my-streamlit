"""
GitHub 持久化模块（基于 GitHub REST API）
用户上传/删除文件后，通过 API 直接写入 GitHub 仓库，不依赖 git 进程
适用于 Streamlit Cloud 等不支持 git push 的容器环境

GitHub Contents API 自动创建 commit，无需手动管理 git 状态
"""
import os
import json
import base64
import logging
import threading
import requests
from config import GITHUB_TOKEN, GITHUB_REPO, GITHUB_BRANCH, _PROJECT_ROOT

logger = logging.getLogger(__name__)

# GitHub API 配置
GITHUB_API_BASE = "https://api.github.com"

# API 请求头
def _get_headers() -> dict:
    return {
        "Authorization": f"token {GITHUB_TOKEN}",
        "Accept": "application/vnd.github.v3+json",
        "User-Agent": "AI-Content-Tool/1.0"
    }


def _github_put_file(repo_path: str, content, message: str, is_binary: bool = False) -> bool:
    """
    通过 GitHub API 创建或更新文件

    Args:
        repo_path: 仓库内路径（如 "user_uploads/水晶.txt"）
        content: 文件内容（文本字符串或二进制内容）
        message: commit message
        is_binary: 是否为二进制文件（PDF等）

    Returns:
        bool: 是否成功
    """
    if not GITHUB_TOKEN:
        logger.info("No GITHUB_TOKEN, skipping GitHub API call")
        return False

    repo = GITHUB_REPO
    url = f"{GITHUB_API_BASE}/repos/{repo}/contents/{repo_path}"
    headers = _get_headers()

    # 编码内容
    if is_binary:
        if isinstance(content, str):
            content_bytes = content.encode("utf-8")
        else:
            content_bytes = content
        b64_content = base64.b64encode(content_bytes).decode("utf-8")
    else:
        b64_content = base64.b64encode(content.encode("utf-8")).decode("utf-8")

    # 先查询文件是否存在（需要 sha 来更新）
    sha = None
    try:
        resp = requests.get(url, headers=headers, timeout=10)
        if resp.status_code == 200:
            sha = resp.json().get("sha")
    except Exception:
        pass

    data = {
        "message": message,
        "content": b64_content,
        "branch": GITHUB_BRANCH,
    }
    if sha:
        data["sha"] = sha

    try:
        resp = requests.put(url, headers=headers, json=data, timeout=30)
        if resp.status_code in (200, 201):
            logger.info(f"GitHub API: 文件已更新 {repo_path}")
            return True
        else:
            logger.error(f"GitHub API error ({resp.status_code}): {resp.text[:200]}")
            return False
    except Exception as e:
        logger.error(f"GitHub API request failed: {e}")
        return False


def _github_delete_file(repo_path: str, message: str) -> bool:
    """
    通过 GitHub API 删除文件

    Args:
        repo_path: 仓库内路径
        message: commit message

    Returns:
        bool: 是否成功
    """
    if not GITHUB_TOKEN:
        return False

    repo = GITHUB_REPO
    url = f"{GITHUB_API_BASE}/repos/{repo}/contents/{repo_path}"
    headers = _get_headers()

    # 必须提供 sha 才能删除
    try:
        resp = requests.get(url, headers=headers, timeout=10)
        if resp.status_code != 200:
            logger.warning(f"GitHub API: 文件不存在 {repo_path}")
            return False
        sha = resp.json().get("sha")
    except Exception as e:
        logger.error(f"GitHub API get sha failed: {e}")
        return False

    data = {
        "message": message,
        "sha": sha,
        "branch": GITHUB_BRANCH,
    }

    try:
        resp = requests.delete(url, headers=headers, json=data, timeout=30)
        if resp.status_code == 200:
            logger.info(f"GitHub API: 文件已删除 {repo_path}")
            return True
        else:
            logger.error(f"GitHub API delete error ({resp.status_code}): {resp.text[:200]}")
            return False
    except Exception as e:
        logger.error(f"GitHub API delete failed: {e}")
        return False


def _upload_file_to_github(local_path: str, repo_path: str, message: str) -> None:
    """上传单个文件到 GitHub"""
    # 判断是否为二进制文件
    ext = os.path.splitext(local_path)[1].lower()
    is_binary = ext == ".pdf"

    if is_binary:
        with open(local_path, "rb") as f:
            content = f.read()
    else:
        with open(local_path, "r", encoding="utf-8") as f:
            content = f.read()

    _github_put_file(repo_path, content, message, is_binary=is_binary)


def _sync_knowledge_db(message: str) -> None:
    """同步 knowledge_db.json 到 GitHub"""
    db_path = os.path.join(_PROJECT_ROOT, "knowledge_db.json")
    if os.path.exists(db_path):
        with open(db_path, "r", encoding="utf-8") as f:
            content = f.read()
        _github_put_file("knowledge_db.json", content, message)


def git_auto_commit(files_message: dict[str, str] | None = None, message: str = "") -> None:
    """
    异步同步文件到 GitHub（通过 REST API，不依赖 git 进程）

    Args:
        files_message: {本地文件路径: 说明}，None 则只同步索引
        message: 自定义 commit message
    """
    if not GITHUB_TOKEN:
        logger.info("No GITHUB_TOKEN configured, skipping GitHub sync")
        return

    def _sync():
        try:
            if not message:
                if files_message:
                    desc = ", ".join(files_message.values())
                else:
                    desc = "知识库数据更新"
                message = f"auto: {desc}"

            # 上传用户文件
            if files_message:
                for local_path, desc in files_message.items():
                    filename = os.path.basename(local_path)
                    repo_path = f"user_uploads/{filename}"
                    _upload_file_to_github(local_path, repo_path, message)

            # 同步索引
            _sync_knowledge_db(message)

        except Exception as e:
            logger.error(f"GitHub sync failed: {e}")

    # 后台线程执行，不阻塞 UI
    thread = threading.Thread(target=_sync, daemon=True)
    thread.start()


def git_auto_delete(filename: str, message: str = "") -> None:
    """
    异步从 GitHub 删除文件

    Args:
        filename: 文件名（在 user_uploads/ 下）
        message: commit message
    """
    if not GITHUB_TOKEN:
        return

    def _delete():
        try:
            if not message:
                message = f"auto: 删除用户文件 {filename}"
            repo_path = f"user_uploads/{filename}"
            _github_delete_file(repo_path, message)
            # 同步索引
            _sync_knowledge_db(message)
        except Exception as e:
            logger.error(f"GitHub delete failed: {e}")

    thread = threading.Thread(target=_delete, daemon=True)
    thread.start()


def has_git_config() -> bool:
    """检查是否配置了 GitHub Token"""
    return bool(GITHUB_TOKEN)

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

# 缓存最后一次同步结果（供 UI 读取）
_last_sync_result = {"ok": None, "msg": "", "time": None}


def _get_headers() -> dict:
    return {
        "Authorization": f"token {GITHUB_TOKEN}",
        "Accept": "application/vnd.github.v3+json",
        "User-Agent": "AI-Content-Tool/1.0"
    }


def validate_token() -> dict:
    """
    验证 GitHub Token 是否有效、是否有仓库写入权限
    返回 {"ok": bool, "msg": str}
    """
    if not GITHUB_TOKEN:
        return {"ok": False, "msg": "Token 未配置"}

    # 1) 验证 token 本身
    try:
        resp = requests.get(
            f"{GITHUB_API_BASE}/user",
            headers=_get_headers(),
            timeout=10
        )
        if resp.status_code == 401:
            return {"ok": False, "msg": "Token 无效（401），请检查 Token 是否正确复制。注意：Fine-grained PAT 以 github_pat_ 开头，不要加 ghp_ 前缀。"}
        if resp.status_code != 200:
            return {"ok": False, "msg": f"Token 验证失败: HTTP {resp.status_code}"}
        user = resp.json().get("login", "unknown")
    except Exception as e:
        return {"ok": False, "msg": f"网络错误，无法连接 GitHub API: {e}"}

    # 2) 验证仓库访问和写入权限
    try:
        repo_url = f"{GITHUB_API_BASE}/repos/{GITHUB_REPO}"
        resp = requests.get(repo_url, headers=_get_headers(), timeout=10)
        if resp.status_code == 404:
            return {"ok": False, "msg": f"仓库 {GITHUB_REPO} 不存在或无访问权限"}
        if resp.status_code != 200:
            return {"ok": False, "msg": f"仓库访问失败: HTTP {resp.status_code}"}

        # 检查权限字段
        perms = resp.json().get("permissions", {})
        if not perms.get("push"):
            return {
                "ok": False,
                "msg": (
                    f"Token 有效（用户: {user}），但没有仓库写入权限。"
                    "请在 GitHub → Settings → Personal Access Tokens → Fine-grained tokens 中，"
                    f"为 {GITHUB_REPO} 开启 'Contents: Read and Write' 权限。"
                )
            }
    except Exception as e:
        return {"ok": False, "msg": f"验证仓库权限时出错: {e}"}

    return {"ok": True, "msg": f"Token 有效（用户: {user}），仓库 {GITHUB_REPO} 可读写"}


def get_last_sync_result() -> dict:
    """获取最后一次同步的结果（用于 UI 展示）"""
    return _last_sync_result.copy()


def _set_sync_result(ok: bool, msg: str):
    global _last_sync_result
    _last_sync_result = {"ok": ok, "msg": msg, "time": _now_str()}


def _now_str() -> str:
    from datetime import datetime
    return datetime.now().strftime("%H:%M:%S")


def _github_put_file(repo_path: str, content, message: str, is_binary: bool = False) -> bool:
    """
    通过 GitHub API 创建或更新文件
    """
    if not GITHUB_TOKEN:
        logger.info("No GITHUB_TOKEN, skipping GitHub API call")
        _set_sync_result(False, "Token 未配置")
        return False

    repo = GITHUB_REPO
    url = f"{GITHUB_API_BASE}/repos/{repo}/contents/{repo_path}"
    headers = _get_headers()

    # 编码内容
    if is_binary:
        content_bytes = content.encode("utf-8") if isinstance(content, str) else content
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
            _set_sync_result(True, f"已同步: {repo_path}")
            return True
        else:
            err_text = resp.text[:300]
            logger.error(f"GitHub API error ({resp.status_code}): {err_text}")
            _set_sync_result(False, f"同步失败 HTTP {resp.status_code}: {err_text}")
            return False
    except Exception as e:
        logger.error(f"GitHub API request failed: {e}")
        _set_sync_result(False, f"同步异常: {e}")
        return False


def _github_delete_file(repo_path: str, message: str) -> bool:
    """通过 GitHub API 删除文件"""
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
            _set_sync_result(True, f"已删除: {repo_path}")
            return True
        else:
            err_text = resp.text[:300]
            logger.error(f"GitHub API delete error ({resp.status_code}): {err_text}")
            _set_sync_result(False, f"删除失败 HTTP {resp.status_code}: {err_text}")
            return False
    except Exception as e:
        logger.error(f"GitHub API delete failed: {e}")
        _set_sync_result(False, f"删除异常: {e}")
        return False


def _upload_file_to_github(local_path: str, repo_path: str, message: str) -> bool:
    """上传单个文件到 GitHub"""
    ext = os.path.splitext(local_path)[1].lower()
    is_binary = ext == ".pdf"

    if is_binary:
        with open(local_path, "rb") as f:
            content = f.read()
    else:
        with open(local_path, "r", encoding="utf-8") as f:
            content = f.read()

    return _github_put_file(repo_path, content, message, is_binary=is_binary)


def _sync_knowledge_db(message: str) -> bool:
    """同步 knowledge_db.json 到 GitHub"""
    db_path = os.path.join(_PROJECT_ROOT, "knowledge_db.json")
    if os.path.exists(db_path):
        with open(db_path, "r", encoding="utf-8") as f:
            content = f.read()
        return _github_put_file("knowledge_db.json", content, message)
    return True


def git_auto_commit(files_message: dict | None = None, message: str = "") -> None:
    """
    异步同步文件到 GitHub（通过 REST API，不依赖 git 进程）
    """
    if not GITHUB_TOKEN:
        logger.info("No GITHUB_TOKEN configured, skipping GitHub sync")
        _set_sync_result(False, "Token 未配置，跳过同步")
        return

    def _sync():
        try:
            commit_msg = message if message else f"auto: {', '.join(files_message.values()) if files_message else '知识库数据更新'}"

            # 上传用户文件
            if files_message:
                for local_path, desc in files_message.items():
                    filename = os.path.basename(local_path)
                    repo_path = f"user_uploads/{filename}"
                    _upload_file_to_github(local_path, repo_path, commit_msg)

            # 同步索引
            _sync_knowledge_db(commit_msg)

        except Exception as e:
            logger.error(f"GitHub sync failed: {e}")
            _set_sync_result(False, f"同步异常: {e}")

    thread = threading.Thread(target=_sync, daemon=True)
    thread.start()


def git_auto_delete(filename: str, message: str = "") -> None:
    """异步从 GitHub 删除文件"""
    if not GITHUB_TOKEN:
        return

    def _delete():
        try:
            commit_msg = message if message else f"auto: 删除用户文件 {filename}"
            repo_path = f"user_uploads/{filename}"
            _github_delete_file(repo_path, commit_msg)
            _sync_knowledge_db(commit_msg)
        except Exception as e:
            logger.error(f"GitHub delete failed: {e}")
            _set_sync_result(False, f"删除异常: {e}")

    thread = threading.Thread(target=_delete, daemon=True)
    thread.start()


def has_git_config() -> bool:
    """检查是否配置了 GitHub Token"""
    return bool(GITHUB_TOKEN)


def test_sync_one_file() -> dict:
    """
    测试同步：创建一个测试文件到 user_uploads/，验证 Token 和权限是否正常
    返回 {"ok": bool, "msg": str}
    """
    import time
    test_content = f"# 同步测试\n时间: {time.strftime('%Y-%m-%d %H:%M:%S')}\n"
    test_path = "user_uploads/__sync_test__.md"
    ok = _github_put_file(test_path, test_content, "auto: 同步连接测试")
    if ok:
        return {"ok": True, "msg": "测试成功！文件已写入 GitHub user_uploads/__sync_test__.md"}
    else:
        result = get_last_sync_result()
        return {"ok": False, "msg": result.get("msg", "未知错误")}

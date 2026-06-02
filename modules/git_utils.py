"""
GitHub 自动提交模块
用户上传文件后，异步 commit + push 到远程仓库，实现持久化
"""
import os
import subprocess
import threading
import logging
from config import GITHUB_TOKEN, _PROJECT_ROOT

logger = logging.getLogger(__name__)


def _run_git(*args) -> tuple[bool, str]:
    """执行 git 命令，返回 (success, output)"""
    env = os.environ.copy()
    if GITHUB_TOKEN:
        # 通过 token 配置远程 URL（HTTPS）
        # 环境变量 GIT_ASKPASS 方式更安全，避免 token 出现在命令行
        env["GIT_ASKPASS"] = "echo"
        env["GIT_USERNAME"] = "x-access-token"
        env["GIT_PASSWORD"] = GITHUB_TOKEN
        # 设置 URL 使用 token 认证
        env["GIT_AUTHOR_NAME"] = "AI Content Tool"
        env["GIT_AUTHOR_EMAIL"] = "bot@ai-content-tool.local"
        env["GIT_COMMITTER_NAME"] = "AI Content Tool"
        env["GIT_COMMITTER_EMAIL"] = "bot@ai-content-tool.local"

    try:
        result = subprocess.run(
            ["git"] + list(args),
            cwd=_PROJECT_ROOT,
            capture_output=True,
            text=True,
            timeout=60,
            env=env
        )
        output = result.stdout + result.stderr
        if result.returncode != 0 and "nothing to commit" not in output and "no changes" not in output:
            logger.warning(f"git command failed: git {' '.join(args)}\n{output}")
            return False, output
        return True, output
    except subprocess.TimeoutExpired:
        logger.error(f"git command timed out: git {' '.join(args)}")
        return False, "git command timed out"
    except Exception as e:
        logger.error(f"git command error: {e}")
        return False, str(e)


def _configure_remote_if_needed():
    """如果存在 GITHUB_TOKEN，配置远程 URL 带 token 认证"""
    if not GITHUB_TOKEN:
        return
    try:
        # 获取当前远程 URL
        ok, output = _run_git("remote", "get-url", "origin")
        if ok and output.strip():
            url = output.strip()
            # 如果已经包含 token，跳过
            if "@github.com" in url:
                return
            # 替换 https:// 为 https://x-access-token@xxx@github.com
            if url.startswith("https://github.com/"):
                new_url = url.replace("https://", f"https://x-access-token:{GITHUB_TOKEN}@")
                _run_git("remote", "set-url", "origin", new_url)
                logger.info("Remote URL configured with token authentication")
    except Exception as e:
        logger.warning(f"Failed to configure remote: {e}")


def git_auto_commit(files_message: dict[str, str] | None = None, message: str = "") -> None:
    """
    异步 git add + commit + push

    Args:
        files_message: {文件路径: 说明}，用于精细控制提交信息，None 则 add 全部
        message: 自定义 commit message，为空时自动生成
    """
    if not GITHUB_TOKEN:
        logger.info("No GITHUB_TOKEN configured, skipping auto commit")
        return

    def _commit():
        try:
            _configure_remote_if_needed()

            if files_message:
                for fpath in files_message:
                    _run_git("add", "--", fpath)
            else:
                _run_git("add", "--", "user_uploads/", "knowledge_db.json")

            if not message:
                if files_message:
                    desc = ", ".join(files_message.values())
                else:
                    desc = "知识库数据更新"
                message = f"auto: {desc}"

            ok, _ = _run_git("commit", "-m", message, "--allow-empty")
            if not ok:
                return

            _run_git("push", "origin", "HEAD")
            logger.info(f"Auto commit success: {message}")
        except Exception as e:
            logger.error(f"Auto commit failed: {e}")

    # 后台线程执行，不阻塞 UI
    thread = threading.Thread(target=_commit, daemon=True)
    thread.start()


def has_git_config() -> bool:
    """检查是否配置了 git 认证"""
    return bool(GITHUB_TOKEN)

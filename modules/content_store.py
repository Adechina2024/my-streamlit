"""
内容历史存储模块 - 管理生成内容的保存/浏览/导出/收藏
数据持久化到 content_history.json（本地文件，无需数据库）
"""
import os
import json
import time
import tempfile
from datetime import datetime

# 使用项目根目录作为文件基准路径（不受工作目录影响）
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HISTORY_FILE = os.path.join(_PROJECT_ROOT, "content_history.json")
EXPORT_DIR = os.path.join(_PROJECT_ROOT, "exports")


def _load_history() -> list[dict]:
    """加载历史记录"""
    if os.path.exists(HISTORY_FILE):
        with open(HISTORY_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return []


def _save_history(records: list[dict]):
    """保存历史记录到文件（原子写入：先写临时文件再替换，防止损坏）"""
    fd, tmp_path = tempfile.mkstemp(
        dir=os.path.dirname(HISTORY_FILE),
        prefix=".history_tmp_",
        suffix=".json"
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(records, f, ensure_ascii=False, indent=2)
        # 原子替换
        os.replace(tmp_path, HISTORY_FILE)
    except Exception:
        # 清理临时文件
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)
        raise


# ==================== CRUD 操作 ====================

def save_content(
    content: str,
    template: str,
    crystal_name: str,
    style: str = "",
    quality_score: int = -1,
    quality_issues: list = None,
    quality_passed: bool = True,
    extra: dict = None,
) -> dict:
    """
    保存一条生成内容到历史记录。
    返回保存后的完整记录（含 id 和时间戳）。
    """
    records = _load_history()

    record = {
        "id": f"content_{int(time.time() * 1000)}",
        "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "content": content,
        "template": template,
        "crystal_name": crystal_name,
        "style": style,
        "quality_score": quality_score,
        "quality_issues": quality_issues or [],
        "quality_passed": quality_passed,
        "favorite": False,
    }
    if extra:
        record.update(extra)

    records.insert(0, record)  # 最新的排最前面
    _save_history(records)
    return record


def save_batch(copies: list[str], template: str, crystal_name: str, style: str = "",
               quality_scores: list = None, quality_issues: list = None) -> list[dict]:
    """
    批量保存（用于朋友圈等多条生成场景）。
    每条独立保存，共享同一个 batch_id。
    返回所有保存的记录。
    """
    records = _load_history()
    batch_id = f"batch_{int(time.time() * 1000)}"
    saved = []

    batch_records = []
    for i, copy in enumerate(copies):
        score = quality_scores[i] if quality_scores and i < len(quality_scores) else -1
        issues = quality_issues[i] if quality_issues and i < len(quality_issues) else []

        record = {
            "id": f"{batch_id}_{i}",
            "batch_id": batch_id,
            "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "content": copy.strip(),
            "template": template,
            "crystal_name": crystal_name,
            "style": style,
            "batch_index": i + 1,
            "quality_score": score,
            "quality_issues": issues,
            "quality_passed": score >= 70 if score >= 0 else True,
            "favorite": False,
        }
        batch_records.append(record)
        saved.append(record)

    # 批次整体插入到列表头部（保持批次内顺序：方案1在前）
    records[0:0] = batch_records
    _save_history(records)
    return saved


def list_contents(
    template: str = "",
    crystal_name: str = "",
    favorite_only: bool = False,
    limit: int = 100,
) -> list[dict]:
    """
    列出历史记录，支持筛选。
    - template: 按模板类型筛选（空=不限）
    - crystal_name: 按水晶名称筛选（空=不限）
    - favorite_only: 仅显示收藏
    - limit: 最大返回条数
    """
    records = _load_history()

    if template:
        records = [r for r in records if r.get("template") == template]
    if crystal_name:
        records = [r for r in records if r.get("crystal_name") == crystal_name]
    if favorite_only:
        records = [r for r in records if r.get("favorite")]

    return records[:limit]


def get_content(content_id: str) -> dict | None:
    """根据 ID 获取单条记录"""
    records = _load_history()
    for r in records:
        if r.get("id") == content_id:
            return r
    return None


def toggle_favorite(content_id: str) -> dict | None:
    """切换收藏状态"""
    records = _load_history()
    for r in records:
        if r.get("id") == content_id:
            r["favorite"] = not r.get("favorite", False)
            _save_history(records)
            return r
    return None


def delete_content(content_id: str) -> bool:
    """删除单条记录"""
    records = _load_history()
    before = len(records)
    records = [r for r in records if r.get("id") != content_id]
    if len(records) < before:
        _save_history(records)
        return True
    return False


def delete_batch(batch_id: str) -> int:
    """删除整个批次（朋友圈批量场景）"""
    records = _load_history()
    before = len(records)
    records = [r for r in records if r.get("batch_id") != batch_id]
    deleted = before - len(records)
    if deleted > 0:
        _save_history(records)
    return deleted


# ==================== 统计 ====================

def get_stats() -> dict:
    """获取内容库统计信息"""
    records = _load_history()
    templates = set(r.get("template", "") for r in records)
    crystals = set(r.get("crystal_name", "") for r in records)
    favorites = sum(1 for r in records if r.get("favorite"))

    return {
        "total": len(records),
        "favorites": favorites,
        "template_types": len(templates),
        "crystal_names": len(crystals),
        "templates": sorted(templates),
        "crystals": sorted(crystals),
    }


# ==================== 导出 ====================

def export_txt(content: str, filename: str = None) -> str:
    """
    导出单条内容为 TXT 文件。
    返回保存的文件路径。
    """
    if not filename:
        filename = f"export_{int(time.time())}.txt"

    export_dir = EXPORT_DIR
    os.makedirs(export_dir, exist_ok=True)
    filepath = os.path.join(export_dir, filename)

    with open(filepath, "w", encoding="utf-8") as f:
        f.write(content)

    return filepath


def export_batch_txt(records: list[dict], filename: str = None) -> str:
    """
    批量导出多条内容为一个 TXT 文件。
    """
    if not filename:
        filename = f"batch_export_{int(time.time())}.txt"

    export_dir = EXPORT_DIR
    os.makedirs(export_dir, exist_ok=True)
    filepath = os.path.join(export_dir, filename)

    lines = []
    for i, r in enumerate(records):
        template = r.get("template", "")
        crystal = r.get("crystal_name", "")
        created = r.get("created_at", "")
        style = r.get("style", "")
        batch_idx = r.get("batch_index", "")

        lines.append(f"{'='*50}")
        lines.append(f"模板: {template} | 水晶: {crystal} | 风格: {style} | 时间: {created}")
        if batch_idx:
            lines.append(f"方案: 第{batch_idx}条")
        lines.append(f"{'='*50}")
        lines.append(r.get("content", ""))
        lines.append("")

    with open(filepath, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    return filepath

"""
检索模块 - 调用 knowledge_base 的 BM25 检索
支持查询扩展、结果去重、索引缓存
"""
from modules import knowledge_base


def retrieve(query: str, top_k: int = 5) -> list[dict]:
    """检索与 query 最相关的文档片段（BM25 + 查询扩展）"""
    return knowledge_base.retrieve(query, top_k=top_k)


def format_context(results: list[dict], max_chars: int = 3000) -> str:
    """将检索结果格式化为 LLM 上下文，控制总长度"""
    if not results:
        return ""

    parts = []
    total = 0
    for r in results:
        text = r["text"].strip()
        # 截断过长的单个chunk
        if len(text) > 500:
            text = text[:500] + "..."
        section_tag = f" [{r.get('section', '')}]" if r.get('section') else ""
        part = f"【来源: {r['source_file']}{section_tag} | 相关度: {r['score']:.2f}】\n{text}"
        if total + len(part) > max_chars:
            break
        parts.append(part)
        total += len(part)

    return "\n\n---\n\n".join(parts)

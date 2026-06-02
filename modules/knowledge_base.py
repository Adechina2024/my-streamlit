"""
知识库管理模块（纯文本检索版，不依赖外部模型/API）
- 文档解析（MD/TXT/PDF）
- 文本分块 + jieba分词 + BM25检索
- 查询扩展（同义词/领域词）
- 索引缓存 + 结果去重
- 持久化存储到本地JSON
"""
import os
import re
import json
import math
import hashlib
import tempfile
from pathlib import Path
from collections import Counter

import jieba
from config import KNOWLEDGE_DIR, USER_UPLOADS_DIR

# 加载珠宝领域自定义词典
_DICT_PATH = os.path.join(KNOWLEDGE_DIR, "jieba_dict.txt")
if os.path.exists(_DICT_PATH):
    jieba.load_userdict(_DICT_PATH)

# 使用项目根目录作为文件基准路径
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_FILE = os.path.join(_PROJECT_ROOT, "knowledge_db.json")


# ===================== 文档解析 =====================

def parse_markdown(filepath: str) -> str:
    with open(filepath, "r", encoding="utf-8") as f:
        return f.read()


def parse_txt(filepath: str) -> str:
    with open(filepath, "r", encoding="utf-8") as f:
        return f.read()


def parse_pdf(filepath: str) -> str:
    import fitz
    doc = fitz.open(filepath)
    text = ""
    for page in doc:
        text += page.get_text() + "\n"
    doc.close()
    return text


def _extract_section_title(text: str) -> str:
    """从文本开头提取最近的标题作为section元数据"""
    # 取文本开头的非空行，找最近的标题
    lines = text.strip().split('\n')
    for line in lines[:5]:
        stripped = line.strip()
        if stripped.startswith('#'):
            # 取最深层级标题（最具体的）
            return stripped.lstrip('#').strip()
    return ""


def split_text(text: str, chunk_size: int = 400, overlap: int = 50) -> list[str]:
    """按段落分块，优先在标题/小节边界分割，保持语义完整性"""
    paragraphs = re.split(r'\n\n+', text.strip())
    chunks = []
    current_chunk = ""
    current_title = ""

    for para in paragraphs:
        para = para.strip()
        if not para:
            continue

        # 检测是否为新章节标题（标题行单独成段）
        is_new_section = bool(re.match(r'^#{1,4}\s', para))

        if is_new_section and current_chunk:
            # 新章节开始，先保存当前chunk
            chunks.append(current_chunk.strip())
            current_chunk = para + "\n\n"
        elif len(current_chunk) + len(para) + 2 <= chunk_size:
            current_chunk += para + "\n\n"
        else:
            if current_chunk:
                chunks.append(current_chunk.strip())
            if len(para) > chunk_size:
                # 长段落按句子分割
                sentences = re.split(r'(?<=[。！？.!?])', para)
                sub_chunk = ""
                for sent in sentences:
                    if len(sub_chunk) + len(sent) <= chunk_size:
                        sub_chunk += sent
                    else:
                        if sub_chunk:
                            chunks.append(sub_chunk.strip())
                        sub_chunk = sent
                current_chunk = sub_chunk
            else:
                current_chunk = para + "\n\n"

    if current_chunk.strip():
        chunks.append(current_chunk.strip())

    return chunks


def tokenize(text: str) -> list[str]:
    """中文分词，过滤停用词和短词"""
    words = jieba.lcut(text)
    # 简单停用词过滤
    stopwords = {'的', '了', '是', '在', '我', '有', '和', '就', '不', '人', '都', '一',
                 '一个', '上', '也', '很', '到', '说', '要', '去', '你', '会', '着', '没有',
                 '看', '好', '自己', '这', '他', '她', '它', '们', '那', '些', '什么', '怎么',
                 '如何', '可以', '能', '与', '及', '等', '对', '把', '被', '让', '用',
                 '为', '从', '而', '但', '又', '或', '更', '最', '已', '还', '之', '其'}
    return [w for w in words if len(w) >= 2 and w not in stopwords]


# ===================== 数据库操作 =====================

def _load_db() -> dict:
    """加载本地JSON数据库，自动迁移补全 source_type 字段"""
    migrated = False
    if os.path.exists(DB_FILE):
        with open(DB_FILE, "r", encoding="utf-8") as f:
            db = json.load(f)
    else:
        return {"documents": [], "chunks": []}

    # 迁移：为历史 chunk 补全 source_type 字段
    _knowledge_dir = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "knowledge"))
    _user_dir = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "user_uploads"))
    for c in db.get("chunks", []):
        if "source_type" not in c:
            sf = c.get("source_file", "")
            full_path_k = os.path.join(_knowledge_dir, sf)
            if os.path.exists(full_path_k):
                c["source_type"] = "system"
            else:
                c["source_type"] = "user"
            migrated = True
    if migrated:
        _save_db(db)
    return db


def _save_db(db: dict):
    """保存数据库到本地JSON（原子写入：先写临时文件再替换，防止损坏）"""
    fd, tmp_path = tempfile.mkstemp(
        dir=os.path.dirname(DB_FILE),
        prefix=".kb_tmp_",
        suffix=".json"
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(db, f, ensure_ascii=False, indent=2)
        os.replace(tmp_path, DB_FILE)
    except Exception:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)
        raise


def add_document(filepath: str, source: str = "user") -> dict:
    """
    添加文档到知识库

    Args:
        filepath: 文件路径
        source: 来源标识 "system"（预置知识库）或 "user"（用户上传）

    Returns:
        dict: {file, chunks, status, source}
    """
    db = _load_db()
    filename = os.path.basename(filepath)
    ext = Path(filepath).suffix.lower()

    # 解析
    try:
        if ext == ".md":
            text = parse_markdown(filepath)
        elif ext == ".txt":
            text = parse_txt(filepath)
        elif ext == ".pdf":
            text = parse_pdf(filepath)
        else:
            return {"file": filename, "chunks": 0, "status": f"不支持的格式: {ext}", "source": source}
    except Exception as e:
        return {"file": filename, "chunks": 0, "status": f"解析失败: {e}", "source": source}

    if not text.strip():
        return {"file": filename, "chunks": 0, "status": "文件内容为空", "source": source}

    # 删除旧版本
    db["chunks"] = [c for c in db["chunks"] if c["source_file"] != filename]
    db["documents"] = [d for d in db["documents"] if d["filename"] != filename]

    # 分块 + 分词
    chunks = split_text(text)
    chunk_data = []
    for i, chunk_text in enumerate(chunks):
        words = tokenize(chunk_text)
        section = _extract_section_title(chunk_text)
        chunk_data.append({
            "id": f"{filename}_chunk_{i}",
            "source_file": filename,
            "source_type": source,
            "chunk_index": i,
            "section": section,
            "text": chunk_text,
            "words": words
        })

    # 记录文档
    db["documents"].append({
        "filename": filename,
        "filepath": filepath,
        "source": source,
        "chunks_count": len(chunks)
    })
    db["chunks"].extend(chunk_data)
    _save_db(db)
    invalidate_index_cache()

    return {"file": filename, "chunks": len(chunks), "status": "success", "source": source}


def delete_document(filename: str) -> dict:
    """删除文档（含索引和物理文件）"""
    db = _load_db()

    # 找到文档记录，确认来源
    doc_record = next((d for d in db["documents"] if d["filename"] == filename), None)
    source = doc_record.get("source", "user") if doc_record else "user"

    before = len(db["chunks"])
    db["chunks"] = [c for c in db["chunks"] if c["source_file"] != filename]
    db["documents"] = [d for d in db["documents"] if d["filename"] != filename]
    deleted = before - len(db["chunks"])
    _save_db(db)
    invalidate_index_cache()

    # 删除用户上传的物理文件
    if source == "user" and doc_record:
        filepath = doc_record.get("filepath", "")
        if filepath and os.path.exists(filepath):
            os.remove(filepath)

    return {"file": filename, "deleted": deleted, "status": "success" if deleted > 0 else "未找到该文档", "source": source}


def clean_orphan_docs() -> dict:
    """
    启动时自动清理：删除 user_uploads/ 目录中已不存在的文件的 DB 记录。
    GitHub 是唯一真相源——在 GitHub 上删除文件后，重启/部署即自动同步。
    """
    db = _load_db()
    _user_dir = os.path.normpath(
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "user_uploads")
    )

    # 收集 user_uploads/ 目录中实际存在的文件
    if os.path.exists(_user_dir):
        existing_files = set(
            f for f in os.listdir(_user_dir)
            if os.path.isfile(os.path.join(_user_dir, f))
        )
    else:
        existing_files = set()

    # 找出 DB 里有记录但本地文件已不存在的 user 文件
    user_files_in_db = sorted(set(
        c["source_file"] for c in db["chunks"] if c.get("source_type") == "user"
    ))
    orphan_files = [f for f in user_files_in_db if f not in existing_files]

    if not orphan_files:
        return {"cleaned": [], "count": 0}

    # 执行清理
    before = len(db["chunks"])
    db["chunks"] = [c for c in db["chunks"] if c["source_file"] not in orphan_files]
    db["documents"] = [d for d in db["documents"] if d["filename"] not in orphan_files]
    deleted = before - len(db["chunks"])
    _save_db(db)
    invalidate_index_cache()
    return {"cleaned": orphan_files, "count": len(orphan_files)}


def get_doc_stats() -> dict:
    """获取知识库统计（含来源分类）"""
    db = _load_db()
    all_files = sorted(set(c["source_file"] for c in db["chunks"]))

    # 兼容历史数据：优先用 source_type 字段，缺失时根据文件路径判断
    _knowledge_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "knowledge")
    _knowledge_dir = os.path.normpath(_knowledge_dir)
    _user_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "user_uploads")
    _user_dir = os.path.normpath(_user_dir)

    system_files = set()
    user_files = set()
    for c in db["chunks"]:
        sf = c["source_file"]
        stype = c.get("source_type")
        if stype == "system":
            system_files.add(sf)
        elif stype == "user":
            user_files.add(sf)
        else:
            # 兼容历史数据：根据文件实际路径判断
            full_path = os.path.join(_knowledge_dir, sf)
            if os.path.exists(full_path):
                system_files.add(sf)
            else:
                user_files.add(sf)

    return {
        "total_chunks": len(db["chunks"]),
        "total_files": len(all_files),
        "files": all_files,
        "system_files": sorted(system_files),
        "user_files": sorted(user_files)
    }


# ===================== 索引缓存 =====================

_index_cache = {"mtime": 0, "index": None}


def _get_index():
    """获取缓存的检索索引，避免每次查询重复计算 IDF/BM25 参数"""
    global _index_cache
    db = _load_db()
    if not db["chunks"]:
        return None

    # 检查文件是否被修改（简单 mtime 检查）
    if os.path.exists(DB_FILE):
        mtime = os.path.getmtime(DB_FILE)
    else:
        mtime = 0

    if _index_cache["index"] and _index_cache["mtime"] == mtime:
        return _index_cache["index"]

    # 构建索引
    N = len(db["chunks"])
    # 文档频率 DF
    df = Counter()
    # 每个chunk的词频 TF（预计算，避免检索时重复计算）
    chunk_tfs = []
    # 平均文档长度
    total_len = 0

    for chunk in db["chunks"]:
        tf = Counter(chunk["words"])
        chunk_tfs.append(tf)
        total_len += len(chunk["words"])
        for w in set(chunk["words"]):
            df[w] += 1

    avgdl = total_len / N if N > 0 else 1

    _index_cache["mtime"] = mtime
    _index_cache["index"] = {
        "chunks": db["chunks"],
        "N": N,
        "df": df,
        "chunk_tfs": chunk_tfs,
        "avgdl": avgdl,
    }
    return _index_cache["index"]


def invalidate_index_cache():
    """知识库变更后调用，清除缓存"""
    global _index_cache
    _index_cache = {"mtime": 0, "index": None}


# ===================== 查询扩展 =====================

# 珠宝领域同义词/近义词映射（用于查询扩展提升召回率）
_SYNONYMS = {
    # 水晶别名
    "紫晶": ["紫水晶"],
    "粉晶": ["粉水晶"],
    "黄晶": ["黄水晶"],
    "白晶": ["白水晶"],
    "茶晶": ["烟晶", "茶石英"],
    "绿幽灵": ["鬼佬财神", "绿 Phantom"],
    "发晶": ["金发晶", "钛晶"],
    "碧玺": ["电气石"],
    "玛瑙": ["红玛瑙", "南红"],
    # 五行表达
    "招财": ["招财", "旺财", "财运", "正财", "偏财"],
    "旺事业": ["事业运", "招贵人", "职场", "升职"],
    "招桃花": ["正缘", "桃花", "感情运", "姻缘", "旺正缘"],
    "保护": ["辟邪", "挡煞", "护身", "防小人"],
    "安神": ["静心", "安眠", "助眠", "改善失眠", "冥想"],
    "提升自信": ["增强自信", "增强魄力", "坚定内心", "太阳轮"],
    "改善情绪": ["舒缓情绪", "治愈", "疗愈", "情绪调理"],
    # 脉轮别名
    "心轮": ["心轮", "第四脉轮", "心之轮"],
    "喉轮": ["喉轮", "第五脉轮", "喉之轮"],
    "眉心轮": ["眉心轮", "第三眼", "第六脉轮"],
    "顶轮": ["顶轮", "第七脉轮", "梵天轮"],
    "海底轮": ["海底轮", "根轮", "第一脉轮", "基础轮"],
    "脐轮": ["脐轮", "本我轮", "第二脉轮"],
    "太阳轮": ["太阳轮", "胃轮", "第三脉轮", "太阳神经丛"],
    # 星座别名（用户常用"座"，知识库用"星座"）
    "白羊座": ["白羊星座"],
    "金牛座": ["金牛星座"],
    "双子座": ["双子星座"],
    "巨蟹座": ["巨蟹星座"],
    "狮子座": ["狮子星座"],
    "处女座": ["处女星座"],
    "天秤座": ["天秤星座"],
    "天蝎座": ["天蝎星座"],
    "射手座": ["射手星座"],
    "摩羯座": ["摩羯星座"],
    "水瓶座": ["水瓶星座"],
    "双鱼座": ["双鱼星座"],
}

# 查询关键词 → 应额外检索的领域词
_QUERY_BOOST = {
    "水晶": ["天然水晶", "晶石"],
    "五行": ["五行搭配", "喜用神", "相生", "相克"],
    "脉轮": ["能量中枢", "疏通", "阻塞"],
    "星座": ["守护石", "星盘", "本命"],
    "运势": ["流年", "流月", "命理"],
    "搭配": ["推荐", "适合", "适配"],
    "保养": ["净化", "消磁", "注意事项"],
}


def expand_query(query: str) -> list[str]:
    """对查询词进行同义词扩展"""
    words = list(jieba.cut(query))
    expanded_words = []
    for w in words:
        expanded_words.append(w)
        # 同义词扩展
        if w in _SYNONYMS:
            expanded_words.extend(_SYNONYMS[w])
        # 检查是否是映射的目标词
        for key, values in _SYNONYMS.items():
            if w in values and key not in expanded_words:
                expanded_words.append(key)
        # 领域关键词扩展
        if w in _QUERY_BOOST:
            expanded_words.extend(_QUERY_BOOST[w])

    return expanded_words


# ===================== BM25 检索 =====================

# BM25 参数
_BM25_K1 = 1.5   # 词频饱和参数（越大越重视词频）
_BM25_B = 0.75    # 文档长度归一化参数（越大越惩罚长文档）
_SCORE_THRESHOLD = 0.05  # 最低相似度阈值，过滤低质量结果


def retrieve(query: str, top_k: int = 5) -> list[dict]:
    """
    基于 BM25 的文本检索（含查询扩展 + 结果去重）
    """
    index = _get_index()
    if not index:
        return []

    # 查询扩展后分词
    expanded_query = " ".join(expand_query(query))
    query_words = tokenize(expanded_query)
    if not query_words:
        return []

    N = index["N"]
    df = index["df"]
    chunk_tfs = index["chunk_tfs"]
    chunks = index["chunks"]
    avgdl = index["avgdl"]

    # BM25 评分
    query_tf = Counter(query_words)
    scores = []

    for i, chunk in enumerate(chunks):
        chunk_tf = chunk_tfs[i]
        dl = len(chunk["words"])  # 文档长度

        score = 0.0
        for word, qtf in query_tf.items():
            if word not in chunk_tf:
                continue
            # IDF: Robertson–Spärck Jones 公式
            n_t = df.get(word, 0)
            idf = math.log((N - n_t + 0.5) / (n_t + 0.5) + 1)
            # TF 饱和: 词频越多贡献越大但有上限
            tf = chunk_tf[word]
            tf_component = (tf * (_BM25_K1 + 1)) / (tf + _BM25_K1 * (1 - _BM25_B + _BM25_B * dl / avgdl))
            score += idf * tf_component

        if score >= _SCORE_THRESHOLD:
            scores.append({
                "text": chunk["text"],
                "source_file": chunk["source_file"],
                "chunk_index": chunk["chunk_index"],
                "section": chunk.get("section", ""),
                "score": round(score, 4)
            })

    # 按分数降序
    scores.sort(key=lambda x: x["score"], reverse=True)

    # 去重：相邻且文本相似度>70%的只保留分数更高的
    deduped = []
    seen_texts = set()
    for s in scores:
        # 简单去重：取前50字作为指纹
        fingerprint = s["text"][:50].strip()
        if fingerprint not in seen_texts:
            seen_texts.add(fingerprint)
            deduped.append(s)

    return deduped[:top_k]

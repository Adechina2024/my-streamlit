"""
输出质量校验模块 - 校验LLM生成内容是否符合格式/字数/结构要求
- 各模板独立的校验函数
- 通用质量评分（0-100）
- 违规项列表 + 改进建议
"""
import re
import unicodedata


# ==================== 工具函数 ====================

# emoji Unicode 范围（常用表情符号区块）
_EMOJI_RANGES = [
    (0x1F600, 0x1F64F),  # Emoticons
    (0x1F300, 0x1F5FF),  # Misc Symbols and Pictographs
    (0x1F680, 0x1F6FF),  # Transport and Map
    (0x1F1E0, 0x1F1FF),  # Flags
    (0x2600, 0x26FF),    # Misc symbols
    (0x2700, 0x27BF),    # Dingbats
    (0xFE00, 0xFE0F),    # Variation Selectors
    (0x1F900, 0x1F9FF),  # Supplemental Symbols
    (0x1FA00, 0x1FA6F),  # Chess Symbols
    (0x1FA70, 0x1FAFF),  # Symbols Extended
]


def _is_emoji(char: str) -> bool:
    """判断单个字符是否为 emoji（纯Python实现，无第三方库依赖）"""
    code = ord(char)
    for start, end in _EMOJI_RANGES:
        if start <= code <= end:
            return True
    # ZWJ sequences 中的结合符号
    if code == 0x200D:  # ZWJ
        return False
    category = unicodedata.category(char)
    if category == 'So':  # Other Symbol
        return True
    return False


def _count_emoji(text: str) -> int:
    """统计文本中 emoji 数量"""
    return sum(1 for c in text if _is_emoji(c))


def _count_text_chars(text: str) -> int:
    """统计纯文本字数（去掉空白和markdown标记）"""
    # 去掉 markdown 标记符号
    cleaned = re.sub(r'[#*\-\_\|\[\]>`]', '', text)
    cleaned = re.sub(r'\s+', '', cleaned)
    return len(cleaned)


def _extract_sections(text: str) -> list[str]:
    """提取文本中所有 【xxx】 标记的板块名"""
    return re.findall(r'【([^】]+)】', text)


def _count_hashtags(text: str) -> int:
    """统计 #话题标签 数量"""
    return len(re.findall(r'#[^\s#]+', text))


def _get_text_between_markers(text: str, start_marker: str, end_marker: str) -> str:
    """提取两个标记之间的文本"""
    pattern = re.escape(start_marker) + r'(.*?)' + re.escape(end_marker)
    match = re.search(pattern, text, re.DOTALL)
    return match.group(1).strip() if match else ""


# ==================== 小红书文案校验 ====================

def validate_xiaohongshu(content: str) -> dict:
    """
    校验小红书种草文案
    规则：
    - 标题10-18字
    - 正文250-350字
    - 标签5-8个
    - emoji总数≤6
    """
    issues = []
    score = 100

    # 解析结构
    has_title = bool(re.search(r'【标题】', content))
    has_body = bool(re.search(r'【正文】', content))
    has_tags = bool(re.search(r'【标签】', content))

    if not has_title:
        issues.append("缺少【标题】标记")
        score -= 15
    if not has_body:
        issues.append("缺少【正文】标记")
        score -= 15
    if not has_tags:
        issues.append("缺少【标签】标记")
        score -= 10

    # 标题字数
    title_text = ""
    if has_title:
        # 提取标题内容（到下一个标记为止）
        m = re.search(r'【标题】\s*(.*?)(?=【正文】|$)', content, re.DOTALL)
        title_text = m.group(1).strip() if m else ""
        title_len = _count_text_chars(title_text)
        if title_len < 10:
            issues.append(f"标题过短（{title_len}字，建议10-18字）")
            score -= 10
        elif title_len > 18:
            issues.append(f"标题过长（{title_len}字，建议10-18字）")
            score -= 8

    # 正文字数
    body_text = ""
    if has_body:
        m = re.search(r'【正文】\s*(.*?)(?=【标签】|$)', content, re.DOTALL)
        body_text = m.group(1).strip() if m else ""
        body_len = _count_text_chars(body_text)
        if body_len < 200:
            issues.append(f"正文过短（{body_len}字，建议250-350字）")
            score -= 10
        elif body_len > 400:
            issues.append(f"正文过长（{body_len}字，建议250-350字）")
            score -= 5
        elif body_len < 250:
            issues.append(f"正文偏短（{body_len}字，建议250-350字）")
            score -= 5

    # 标签数量
    if has_tags:
        tag_count = _count_hashtags(content)
        if tag_count < 5:
            issues.append(f"标签过少（{tag_count}个，建议5-8个）")
            score -= 8
        elif tag_count > 10:
            issues.append(f"标签过多（{tag_count}个，建议5-8个）")
            score -= 5

    # emoji 数量
    emoji_count = _count_emoji(content)
    if emoji_count > 6:
        issues.append(f"emoji过多（{emoji_count}个，建议≤6个）")
        score -= 5

    # 推销话术检测
    spam_words = ["赶紧下单", "限量抢购", "不要错过", "立即购买", "限时优惠", "抢购"]
    found_spam = [w for w in spam_words if w in content]
    if found_spam:
        issues.append(f"含推销话术：{', '.join(found_spam)}")
        score -= 10

    # 硬编码标题检测
    boring_titles = ["科普", "推荐", "介绍"]
    if has_title:
        for bt in boring_titles:
            if bt in title_text and len(title_text) < 15:
                issues.append("标题过于平淡，建议加入悬念/情绪/反差/数字")
                score -= 5
                break

    score = max(0, score)
    return {
        "passed": score >= 70,
        "score": score,
        "issues": issues,
        "details": {
            "title_len": _count_text_chars(title_text) if has_title else 0,
            "body_len": _count_text_chars(body_text) if has_body else 0,
            "tag_count": _count_hashtags(content) if has_tags else 0,
            "emoji_count": emoji_count,
        }
    }


# ==================== 产品详情校验 ====================

def validate_product_desc(content: str) -> dict:
    """
    校验产品详情描述
    规则：
    - 7个板块齐全（品名/核心功效/能量原理/适合人群/搭配建议/保养须知/温馨提示）
    - 总字数300-500
    - 每个功效/人群/保养板块至少2条
    """
    issues = []
    score = 100

    sections = _extract_sections(content)

    # 检查必需板块
    required = ["品名", "核心功效", "能量原理", "适合人群", "搭配建议", "保养须知", "温馨提示"]
    missing = [s for s in required if s not in sections]
    if missing:
        issues.append(f"缺少板块：{', '.join(missing)}")
        score -= len(missing) * 8

    # 总字数
    total_chars = _count_text_chars(content)
    if total_chars < 200:
        issues.append(f"总字数过少（{total_chars}字，建议300-500字）")
        score -= 10
    elif total_chars > 600:
        issues.append(f"总字数过多（{total_chars}字，建议300-500字）")
        score -= 5
    elif total_chars < 300:
        issues.append(f"总字数偏少（{total_chars}字，建议300-500字）")
        score -= 3

    # 检查核心功效至少有要点列表
    if "核心功效" in sections:
        body_part = _get_text_between_markers(content, "【核心功效】", "【")
        bullet_count = len(re.findall(r'[·•\-\*]', body_part))
        if bullet_count < 2:
            issues.append("核心功效至少需列出3条（用·或-开头）")
            score -= 5

    # 检查适合人群至少有分类
    if "适合人群" in sections:
        body_part = _get_text_between_markers(content, "【适合人群】", "【")
        bullet_count = len(re.findall(r'[·•\-\*]', body_part))
        if bullet_count < 2:
            issues.append("适合人群至少需列出3类")
            score -= 5

    # 检查保养须知至少有要点
    if "保养须知" in sections:
        body_part = _get_text_between_markers(content, "【保养须知】", "【")
        bullet_count = len(re.findall(r'[·•\-\*]', body_part))
        if bullet_count < 2:
            issues.append("保养须知至少需列出3条")
            score -= 5

    # 绝对化表述检测
    abs_words = ["一定能", "绝对", "100%", "保证", "特效", "根治"]
    found_abs = [w for w in abs_words if w in content]
    if found_abs:
        issues.append(f"含绝对化表述：{', '.join(found_abs)}")
        score -= 8

    score = max(0, score)
    return {
        "passed": score >= 70,
        "score": score,
        "issues": issues,
        "details": {
            "sections_found": sections,
            "total_chars": total_chars,
        }
    }


# ==================== 朋友圈文案校验 ====================

def validate_moments(content: str) -> dict:
    """
    校验朋友圈文案
    规则：
    - 单条≤80字（允许略超，不扣太多分）
    - 不含硬推销
    """
    issues = []
    score = 100

    char_count = _count_text_chars(content)
    if char_count > 100:
        issues.append(f"文案过长（{char_count}字，建议≤60字）")
        score -= 15
    elif char_count > 80:
        issues.append(f"文案略长（{char_count}字，建议≤60字）")
        score -= 5

    # 硬推销检测
    spam_words = ["下单", "购买", "抢购", "限时", "立即", "点击链接"]
    found_spam = [w for w in spam_words if w in content]
    if found_spam:
        issues.append(f"含硬推销词：{', '.join(found_spam)}")
        score -= 10

    score = max(0, score)
    return {
        "passed": score >= 70,
        "score": score,
        "issues": issues,
        "details": {
            "char_count": char_count,
        }
    }


# ==================== 视频号口播文案校验 ====================

def validate_video_script(content: str) -> dict:
    """
    校验视频号口播文案
    规则：
    - 15s版约60字（±20）
    - 45s版约180字（±40）
    - 口语化（不能有书面语）
    """
    issues = []
    score = 100

    has_15s = "15秒" in content or "快剪" in content
    has_45s = "45秒" in content or "深度" in content

    if not has_15s and not has_45s:
        issues.append("未识别到版本标记（15秒/45秒）")
        score -= 20

    # 提取各版本文本（去除标记头）
    parts = re.split(r'---', content)
    for part in parts:
        part = part.strip()
        if not part:
            continue
        # 去掉标记头
        clean_part = re.sub(r'^(🎬\s*)?【.*?】\s*\n*', '', part).strip()
        char_count = _count_text_chars(clean_part)

        if "15秒" in part or "快剪" in part:
            if char_count > 90:
                issues.append(f"15秒版字数偏多（{char_count}字，建议约60字）")
                score -= 8
            elif char_count < 30:
                issues.append(f"15秒版字数过少（{char_count}字，建议约60字）")
                score -= 8
        elif "45秒" in part or "深度" in part:
            if char_count > 250:
                issues.append(f"45秒版字数偏多（{char_count}字，建议约180字）")
                score -= 8
            elif char_count < 120:
                issues.append(f"45秒版字数过少（{char_count}字，建议约180字）")
                score -= 8

    # 书面语检测（简单规则）
    formal_words = ["综上所述", "由此可见", "研究表明", "据统计", "由此可见", "换言之"]
    found_formal = [w for w in formal_words if w in content]
    if found_formal:
        issues.append(f"含书面语：{', '.join(found_formal)}，口语化不够")
        score -= 5

    score = max(0, score)
    return {
        "passed": score >= 70,
        "score": score,
        "issues": issues,
        "details": {
            "has_15s": has_15s,
            "has_45s": has_45s,
        }
    }


# ==================== 路由函数 ====================

_VALIDATORS = {
    "小红书种草文案": validate_xiaohongshu,
    "产品详情描述": validate_product_desc,
    "朋友圈文案": validate_moments,
    "视频号口播文案": validate_video_script,
}


def validate_output(content: str, template_name: str) -> dict:
    """
    根据模板名称路由到对应的校验函数
    返回: {"passed": bool, "score": int, "issues": list, "details": dict}
    """
    validator = _VALIDATORS.get(template_name)
    if not validator:
        return {"passed": True, "score": -1, "issues": [], "details": {}}
    return validator(content)

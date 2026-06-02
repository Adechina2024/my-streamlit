"""
内容生成模块 - 善福阁珠宝AI内容工具
- 小红书种草文案（3种风格）
- 产品详情描述（电商详情页风格）
- 朋友圈文案（3种风格 + 批量生成）
- 视频号口播文案（15秒快剪 + 45秒深度）
"""

from modules import llm_client, retriever
from modules.output_validator import validate_output
from modules.content_store import save_content, save_batch
from config import CHAT_MODEL_FAST, CHAT_MODEL_PREMIUM

# 校验重试配置
_MAX_RETRIES = 2  # 校验不通过时的最大重试次数（共调用 API 最多 1+2=3 次）


# ==================== 公共方法 ====================

def _retrieve_context(crystal_name: str, extra_query: str = "", top_k: int = 5, max_chars: int = 2500) -> str:
    """检索水晶相关知识作为生成上下文"""
    query = f"{crystal_name} 功效 适合人群 搭配 保养 {extra_query}"
    results = retriever.retrieve(query, top_k=top_k)
    if not results:
        return ""
    return retriever.format_context(results, max_chars=max_chars)


def _build_crystal_name(crystal_name: str, spec: str = "") -> str:
    """智能组合完整产品名称"""
    if not spec:
        return crystal_name
    if spec in crystal_name:
        return crystal_name
    return f"{crystal_name}（{spec}）"


def _generate_with_validation(
    generate_fn,
    template_name: str,
    *args,
    **kwargs
) -> dict:
    """
    包装生成函数：先调用生成，再校验质量，不通过则自动重试。
    返回结果中附加 quality_score, quality_issues, quality_passed 字段。
    """
    best_result = None
    best_score = -1

    for attempt in range(1 + _MAX_RETRIES):
        result = generate_fn(*args, **kwargs)

        # 检查 API 是否返回了错误兜底信息
        if "服务暂时不可用" in result.get("content", ""):
            if attempt < _MAX_RETRIES:
                import time
                wait = 3 * (attempt + 1)
                print(f"API返回错误，第{attempt+1}次重试，等待{wait}s...")
                time.sleep(wait)
                continue
            # 最后一次也失败，直接抛出异常
            raise RuntimeError("API服务暂时不可用，请稍后再试")

        quality = validate_output(result["content"], template_name)

        # 附加质量信息
        result["quality_score"] = quality["score"]
        result["quality_issues"] = quality["issues"]
        result["quality_passed"] = quality["passed"]
        result["quality_details"] = quality.get("details", {})

        if quality["score"] > best_score:
            best_score = quality["score"]
            best_result = result

        # 校验通过直接返回
        if quality["passed"]:
            return result

        # 未通过，准备重试（最后一次不需要等待）
        if attempt < _MAX_RETRIES:
            import time
            wait = 3 * (attempt + 1)  # 3s/6s 间隔
            print(f"质量校验未通过（score={quality['score']}），第{attempt+1}次重试，等待{wait}s...")
            time.sleep(wait)

    # 全部重试都未通过，返回最佳结果
    if best_result:
        return best_result
    return result


# ==================== 小红书种草文案 ====================

_XHS_STYLES = {
    "科普种草": """风格要求「科普种草」：
- 开头用反常识/提问钩住读者（如"原来XX还有这功效？"）
- 正文穿插1-2个知识点（功效/搭配/五行/脉轮等）
- 有科普价值感，让读者觉得"学到了"
- 语气像懂行的朋友在分享，专业但亲切""",

    "情感共鸣": """风格要求「情感共鸣」：
- 开头用情绪/场景代入（如"最近压力好大…""想给妈妈挑个礼物"）
- 正文围绕情感需求展开（治愈/陪伴/好运/安全感）
- 讲一个小故事或感受，引发共鸣
- 语气温柔真诚，像闺蜜聊天""",

    "颜值展示": """风格要求「颜值展示」：
- 开头强调视觉/美学（如"被这条手串美到了！""颜色太绝了"）
- 正文描述外观、光泽、搭配效果、拍照场景
- 适合配图发布，突出颜值和氛围感
- 语气轻快活泼，有时尚博主感""",
}

_XHS_EXAMPLES = {
    "科普种草": """【参考示例】
标题：💡紫水晶真的能助眠吗？亲测有效！
正文：
最近失眠严重，闺蜜安利了紫水晶手串，抱着试试看的心态入手了。

查了资料才知道，紫水晶在水晶界被称为"智慧之石"，对应眉心轮，能量温和平稳，长期佩戴确实能舒缓焦虑、帮助入眠✨

我戴了大概两周，入睡速度明显加快了，睡眠质量也好了不少。

如果你也有失眠/焦虑的困扰，真心推荐试试天然紫水晶，选择品质好的效果更明显哦～💜

#紫水晶 #助眠好物 #水晶科普 #天然水晶 #失眠救星 #能量水晶""",

    "情感共鸣": """【参考示例】
标题：送给自己的第一串水晶💛
正文：
28岁生日那天，给自己挑了一串黄水晶。

不是因为信什么，只是觉得需要一点仪式感，给自己一个"会越来越好的"心理暗示。

没想到戴上之后真的莫名安心，可能这就是所谓的水晶能量吧，也可能是心里终于踏实了。🌟

不管怎样，希望看到这条笔记的你，也能找到让自己安心的那一串。

#黄水晶 #送自己的礼物 #水晶能量 #自我疗愈 #仪式感""",

    "颜值展示": """【参考示例】
标题：被这串粉水晶美哭了😭
正文：
实物真的太好看了！！！

天然的草莓冰裂纹，在阳光下透光感绝了，粉色柔和又高级，戴在手上像开了一朵小花🌸

搭配白色裙子绝配，拍照特别出片，同事都以为我花了几千块哈哈哈

天然水晶就是好看，每一条都是独一无二的✨

#粉水晶 #水晶手串 #颜值担当 #搭配日常 #天然珠宝 #女生礼物""",
}


def _generate_xiaohongshu_raw(
    crystal_name: str,
    target_audience: str = "",
    scene: str = "",
    style: str = "科普种草"
) -> dict:
    """小红书种草文案 - 原始生成（不带校验）"""
    context = _retrieve_context(crystal_name, "种草 推荐 好处 功效", top_k=5, max_chars=2000)
    style_desc = _XHS_STYLES.get(style, _XHS_STYLES["科普种草"])
    example = _XHS_EXAMPLES.get(style, _XHS_EXAMPLES["科普种草"])

    system_prompt = f"""你是善福阁的小红书内容创作者，擅长写高赞种草笔记。

## 输出格式（严格按此结构）
【标题】10-18字，有吸引力，含1个emoji
【正文】250-350字，分段排版，每段2-3行，适当用emoji（不超过6个）
【标签】5-8个话题标签，从具体到泛

## 核心规则
1. 标题不能是"XX科普""XX推荐"这种无聊标题，要有悬念/情绪/反差/数字
2. 正文不能硬推销，不能出现"赶紧下单""限量抢购"等推销话术
3. 语气真诚自然，像真实用户分享，不能像广告
4. 基于知识库信息生成，不编造功效，不确定的说"据说""传说中"
5. 如果知识库中有具体功效/搭配信息，一定要用上

{style_desc}"""

    audience_hint = f"\n目标人群：{target_audience}" if target_audience else ""
    scene_hint = f"\n使用场景/需求：{scene}" if scene else ""

    user_prompt = f"""请为「{crystal_name}」写一篇小红书种草文案。
{audience_hint}{scene_hint}

知识库参考资料：
{context if context else '（无参考资料，基于你的水晶专业知识生成）'}

请严格按照【标题】【正文】【标签】的格式输出。
{example}"""

    result = llm_client.chat(
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ],
        model=CHAT_MODEL_PREMIUM,
        temperature=0.85
    )
    return {
        "content": result,
        "crystal": crystal_name,
        "template": "小红书种草文案",
        "style": style,
    }


def generate_xiaohongshu(
    crystal_name: str,
    target_audience: str = "",
    scene: str = "",
    style: str = "科普种草"
) -> dict:
    """生成小红书种草文案（带质量校验+自动重试+自动保存）"""
    result = _generate_with_validation(
        _generate_xiaohongshu_raw,
        "小红书种草文案",
        crystal_name, target_audience, scene, style
    )
    # 自动保存到内容库
    save_content(
        content=result["content"],
        template="小红书种草文案",
        crystal_name=crystal_name,
        style=style,
        quality_score=result.get("quality_score", -1),
        quality_issues=result.get("quality_issues", []),
        quality_passed=result.get("quality_passed", True),
    )
    return result


# ==================== 产品详情描述 ====================

def _generate_product_desc_raw(
    crystal_name: str,
    spec: str = "",
    purpose: str = ""
) -> dict:
    """产品详情描述 - 原始生成（不带校验）"""
    context = _retrieve_context(
        crystal_name, "功效 保养 搭配 适合人群 能量原理 文化寓意",
        top_k=6, max_chars=3000
    )
    full_name = _build_crystal_name(crystal_name, spec)

    system_prompt = """你是善福阁的专业产品文案，负责撰写水晶产品详情页描述。

## 输出格式（严格按此结构，每个板块用emoji标识）

💎 【品名】完整产品名称（如：天然紫水晶圆珠手串 8mm）
✨ 【核心功效】3-4条核心功效，每条一句话（如：· 舒缓焦虑情绪，帮助改善睡眠）
🧘 【能量原理】用2-3句话解释水晶的能量作用原理，要通俗不玄乎
👥 【适合人群】3-4类适用人群（如：经常熬夜的上班族、考试备考的学生党）
🎨 【搭配建议】推荐2-3种搭配方式（与其他水晶叠戴/穿搭场景/五行脉轮搭配）
📋 【保养须知】3条简明保养注意事项
⚠️ 【温馨提示】水晶功效为传统文化寓意，因人而异，仅供参考

## 写作规则
1. 基于【知识库】内容撰写，有据可查的信息优先使用
2. 功效描述用"传统文化认为""据记载""寓意"等措辞，避免绝对化表述
3. 语气专业但温暖，像一位懂行的店主在介绍产品
4. 不夸大不编造，不确定的信息如实说明
5. 总字数300-500字"""

    purpose_hint = f"\n用途侧重：{purpose}" if purpose else ""

    user_prompt = f"""请为以下产品撰写详情描述：
产品名称：{full_name}{purpose_hint}

知识库参考资料：
{context if context else '（无参考资料，基于专业知识生成）'}

请严格按照上述格式输出，不需要额外解释。"""

    result = llm_client.chat(
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ],
        model=CHAT_MODEL_PREMIUM,
        temperature=0.5
    )
    return {
        "content": result,
        "crystal": crystal_name,
        "template": "产品详情描述",
    }


def generate_product_desc(
    crystal_name: str,
    spec: str = "",
    purpose: str = ""
) -> dict:
    """生成产品详情描述（带质量校验+自动重试+自动保存）"""
    result = _generate_with_validation(
        _generate_product_desc_raw,
        "产品详情描述",
        crystal_name, spec, purpose
    )
    save_content(
        content=result["content"],
        template="产品详情描述",
        crystal_name=crystal_name,
        style=spec,
        quality_score=result.get("quality_score", -1),
        quality_issues=result.get("quality_issues", []),
        quality_passed=result.get("quality_passed", True),
    )
    return result


# ==================== 朋友圈文案 ====================

_MOMENTS_STYLES = {
    "简约专业": """风格「简约专业」：
- 克制、高级感，像奢侈品朋友圈
- 2-3行，每行8-15字
- 用词精炼，不用感叹号
- 1-2个emoji（用低调的💎🌿等，不用❗️🔥等）""",

    "温馨种草": """风格「温馨种草」：
- 温暖亲切，像朋友安利好物
- 3-4行，可略长
- 语气轻柔，有生活感
- 2-3个emoji（用可爱的💜🌟✨等）""",

    "促销活动": """风格「促销活动」：
- 有紧迫感，促转化
- 2-3行，突出优惠/稀缺
- 适当用🔥💰等emoji
- 结尾引导行动（私信/评论/限量等）""",
}


def _generate_single_moments(crystal_name: str, scene: str, style: str, context: str) -> str:
    """生成单条朋友圈文案"""
    style_desc = _MOMENTS_STYLES.get(style, _MOMENTS_STYLES["简约专业"])

    system_prompt = f"""你是善福阁的朋友圈运营，负责写简短的朋友圈文案。

{style_desc}

## 通用规则
1. 基于参考资料提取1-2个核心卖点，融入文案
2. 不要硬推销，但可以自然带出"私信了解"等引导
3. 朋友圈不适合长文，控制在60字以内
4. 如果提供了知识库信息，必须用到其中的具体功效/特点
5. 直接输出文案文本，不要输出任何标记或解释"""

    scene_hint = f"\n发布场景：{scene}" if scene else ""

    user_prompt = f"""产品：{crystal_name}{scene_hint}

参考资料（提取卖点用）：
{context if context else '（无参考资料，基于专业知识）'}

直接输出文案："""

    return llm_client.chat(
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ],
        model=CHAT_MODEL_FAST,
        temperature=0.7
    )


def generate_moments(
    crystal_name: str,
    scene: str = "",
    style: str = "简约专业",
    batch: int = 3
) -> dict:
    """
    生成朋友圈文案（支持批量生成多条供选择）
    每条独立校验，返回各条质量评分，自动批量保存
    """
    context = _retrieve_context(crystal_name, "一句话 卖点 特点 功效", top_k=3, max_chars=1500)

    copies = []
    scores = []
    all_issues = []
    for i in range(batch):
        copy = _generate_single_moments(crystal_name, scene, style, context)

        # API 错误检测
        if "服务暂时不可用" in copy:
            raise RuntimeError("API服务暂时不可用，请稍后再试")

        # 单条校验
        quality = validate_output(copy, "朋友圈文案")
        scores.append(quality["score"])
        all_issues.append(quality["issues"])
        copies.append(copy)

    # 综合质量取平均分
    avg_score = sum(scores) / len(scores) if scores else 0
    merged_issues = []
    for i, iss in enumerate(all_issues):
        if iss:
            merged_issues.append(f"方案{i+1}: {', '.join(iss)}")

    # 自动批量保存到内容库
    save_batch(
        copies=copies,
        template="朋友圈文案",
        crystal_name=crystal_name,
        style=style,
        quality_scores=scores,
        quality_issues=all_issues,
    )

    return {
        "content": "\n\n---\n\n".join([f"📝 方案 {i+1}：\n{c}" for i, c in enumerate(copies)]),
        "copies": copies,
        "crystal": crystal_name,
        "template": "朋友圈文案",
        "style": style,
        "count": batch,
        "quality_score": round(avg_score),
        "quality_issues": merged_issues,
        "quality_passed": avg_score >= 70,
        "quality_details": {"individual_scores": scores},
    }


# ==================== 视频号口播文案 ====================

def _generate_video_script_raw(
    crystal_name: str,
    purpose: str = "",
    version: str = "both"
) -> dict:
    """
    视频号口播文案 - 原始生成（不带校验）
    version: "15s" | "45s" | "both"
    """
    context = _retrieve_context(
        crystal_name,
        "功效 适合人群 五行搭配 脉轮 星盘 知识点",
        top_k=6, max_chars=3000
    )

    system_prompt = """你是善福阁的视频号内容创作者，擅长写水晶类短视频口播文案。

## 通用规则
1. 口播文案 = 直接用嘴说的词，不能有书面语，要口语化
2. 开头3秒必须抓眼球（提问/反常识/数字/情绪）
3. 结尾要有引导（点赞关注/评论区留言/私信咨询）
4. 语速参考：15秒版约60字，45秒版约180字
5. 基于知识库内容，有据可查，不编造
6. 语气自然亲切，像面对面聊天"""

    purpose_hint = f"\n视频目的：{purpose}" if purpose else ""

    if version == "15s":
        user_prompt = f"""请为「{crystal_name}」写一条15秒视频号口播文案（快剪版）。
要求：高节奏、记忆点强、适合作为视频号首页流量入口。{purpose_hint}

知识库参考资料：
{context if context else '（无参考资料，基于专业知识）'}

直接输出文案："""
        result = llm_client.chat(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            model=CHAT_MODEL_PREMIUM,
            temperature=0.8
        )
        return {
            "content": f"🎬 【15秒快剪版】\n\n{result}",
            "crystal": crystal_name,
            "template": "视频号口播文案",
            "version": version,
        }

    elif version == "45s":
        user_prompt = f"""请为「{crystal_name}」写一条45秒视频号口播文案（深度种草版）。
要求：有质感有专业度，讲解清楚核心逻辑，促转化引导咨询。{purpose_hint}

知识库参考资料：
{context if context else '（无参考资料，基于专业知识）'}

直接输出文案："""
        result = llm_client.chat(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            model=CHAT_MODEL_PREMIUM,
            temperature=0.8
        )
        return {
            "content": f"🎬 【45秒深度种草版】\n\n{result}",
            "crystal": crystal_name,
            "template": "视频号口播文案",
            "version": version,
        }

    else:  # "both"
        prompt_15 = f"""请为「{crystal_name}」写一条15秒视频号口播文案（快剪版）。
要求：高节奏、记忆点强、适合作为视频号首页流量入口。约60字。{purpose_hint}

知识库参考资料：
{context if context else '（无参考资料，基于专业知识）'}

直接输出文案："""
        result_15 = llm_client.chat(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt_15}
            ],
            model=CHAT_MODEL_PREMIUM,
            temperature=0.8
        )

        prompt_45 = f"""请为「{crystal_name}」写一条45秒视频号口播文案（深度种草版）。
要求：有质感有专业度，讲解清楚核心功效和搭配逻辑，促转化引导咨询。约180字。{purpose_hint}

知识库参考资料：
{context if context else '（无参考资料，基于专业知识）'}

直接输出文案："""
        result_45 = llm_client.chat(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt_45}
            ],
            model=CHAT_MODEL_PREMIUM,
            temperature=0.8
        )

        combined = f"""🎬 【15秒快剪版】（约60字）
{result_15}

---

🎬 【45秒深度种草版】（约180字）
{result_45}"""

        return {
            "content": combined,
            "crystal": crystal_name,
            "template": "视频号口播文案",
            "version": "both",
        }


def generate_video_script(
    crystal_name: str,
    purpose: str = "",
    version: str = "both"
) -> dict:
    """生成视频号口播文案（带质量校验+自动重试+自动保存）"""
    result = _generate_with_validation(
        _generate_video_script_raw,
        "视频号口播文案",
        crystal_name, purpose, version
    )
    save_content(
        content=result["content"],
        template="视频号口播文案",
        crystal_name=crystal_name,
        style=version,
        quality_score=result.get("quality_score", -1),
        quality_issues=result.get("quality_issues", []),
        quality_passed=result.get("quality_passed", True),
        extra={"version": version},
    )
    return result

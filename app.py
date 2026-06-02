"""
珠宝行业AI内容工具 - Streamlit 主入口
"""
import sys
import os
import time

# 确保项目根目录在 path 中
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import streamlit as st
from modules import knowledge_base, retriever, llm_client
from modules.git_utils import git_auto_commit, git_auto_delete, has_git_config

# 项目根目录（与 modules 保持一致）
_PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
_KNOWLEDGE_DIR = os.path.join(_PROJECT_ROOT, "knowledge")
_USER_UPLOADS_DIR = os.path.join(_PROJECT_ROOT, "user_uploads")
os.makedirs(_USER_UPLOADS_DIR, exist_ok=True)

# ===================== 页面配置 =====================
st.set_page_config(
    page_title="珠宝AI内容工具",
    page_icon="💎",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ===================== 全局样式 =====================
st.markdown("""
<style>
    /* 全局宽度 */
    .stApp { max-width: 1200px; margin: 0 auto; }

    /* Tab 字体加大 */
    .stTabs [data-baseweb="tab-list"] { gap: 12px; }
    .stTabs [data-baseweb="tab"] {
        border-radius: 8px 8px 0 0;
        padding: 10px 24px;
        font-size: 17px !important;
        font-weight: 600;
    }
    .stTabs [aria-selected="true"] {
        background: #f0edff;
        border-bottom: 3px solid #7c3aed;
    }

    /* blockquote 样式 */
    blockquote {
        border-left: 3px solid #8B5CF6;
        padding: 8px 12px;
        background: #f5f3ff;
        border-radius: 0 6px 6px 0;
        margin: 8px 0;
    }

    /* 生成按钮加大高亮 */
    .stButton button[data-baseweb="button"][kind="primary"] {
        font-size: 17px !important;
        padding: 10px 28px !important;
        border-radius: 8px !important;
        font-weight: 600;
    }

    /* 普通按钮稍大 */
    .stButton button {
        font-size: 15px !important;
        padding: 6px 16px !important;
    }

    /* spinner 不换行 */
    .stSpinner { white-space: nowrap !important; }

    /* 侧边栏精简 */
    [data-testid="stSidebar"] {
        min-width: 240px !important;
    }

    /* 文件列表样式 */
    .file-list-item {
        padding: 6px 10px;
        background: #f9fafb;
        border-radius: 6px;
        margin: 4px 0;
        font-size: 14px;
        color: #374151;
    }

    /* 内容库操作按钮缩小 */
    .content-actions button {
        font-size: 13px !important;
        padding: 4px 12px !important;
    }

    /* 隐藏 Streamlit 右上角菜单里的 clear cache 提示 */
    [data-testid="stToolbar"] { display: none !important; }
    button[title="Clear cache"] { display: none !important; }
    .stActionButton button[title="Clear cache"] { display: none !important; }
</style>
""", unsafe_allow_html=True)


# ===================== 辅助函数 ====================
def show_quality_badge(result: dict):
    """展示质量评分徽章和优化空间"""
    score = result.get("quality_score", -1)
    issues = result.get("quality_issues", [])
    details = result.get("quality_details", {})

    if score < 0:
        return

    # 评分等级
    if score >= 90:
        level = "优秀"
        icon = "🟢"
    elif score >= 80:
        level = "良好"
        icon = "✅"
    elif score >= 70:
        level = "合格"
        icon = "🟡"
    elif score >= 60:
        level = "待改进"
        icon = "⚠️"
    else:
        level = "不合格"
        icon = "🔴"

    # 评分展示
    col_score, col_detail = st.columns([1, 3])
    with col_score:
        st.metric("质量评分", f"{score}分", label_visibility="visible")
        st.caption(f"{icon} {level}")

    with col_detail:
        if issues:
            st.warning("**优化空间：**\n" + "\n".join(f"- {iss}" for iss in issues))
        else:
            st.success("格式规范，内容质量良好")

        # 显示具体数据
        detail_parts = []
        if "title_len" in details:
            detail_parts.append(f"标题 {details['title_len']}字")
        if "body_len" in details:
            detail_parts.append(f"正文 {details['body_len']}字")
        if "tag_count" in details:
            detail_parts.append(f"标签 {details['tag_count']}个")
        if "emoji_count" in details:
            detail_parts.append(f"emoji {details['emoji_count']}个")
        if "total_chars" in details:
            detail_parts.append(f"总字数 {details['total_chars']}字")
        if "char_count" in details:
            detail_parts.append(f"字数 {details['char_count']}字")
        if "individual_scores" in details:
            for i, s in enumerate(details["individual_scores"]):
                detail_parts.append(f"方案{i+1}: {s}分")
        if detail_parts:
            st.caption(" | ".join(detail_parts))


# ===================== 侧边栏 =====================
with st.sidebar:
    st.markdown("## 💎 珠宝AI内容工具")
    st.caption("善福阁 · AI驱动的内容生产")

    # 知识库统计
    stats = knowledge_base.get_doc_stats()
    st.markdown("---")
    st.markdown("### 📚 知识库状态")
    st.metric("文档数量", stats["total_files"])
    st.metric("知识段落", stats["total_chunks"])

    # 文件列表（只读展示）
    if stats.get("system_files") or stats.get("user_files"):
        with st.expander("已入库文档", expanded=True):
            for f in (stats.get("system_files", []) + stats.get("user_files", [])):
                st.markdown(f"- `{f}`")

    # Git 同步状态（只显示一句话，无按钮无详情）
    st.markdown("---")
    if has_git_config():
        st.caption("🔄 数据自动同步到 GitHub")
    else:
        st.caption("⚠️ 未配置 GitHub Token，上传数据不会持久化")

# ===================== Tab 导航 =====================
tab1, tab2, tab3, tab4 = st.tabs(["📚 知识库管理", "💬 智能问答", "✍️ 内容生成", "📂 内容库"])

# ===================== Tab1: 知识库管理 =====================
with tab1:
    st.header("知识库管理")
    st.caption("上传水晶相关知识文档，系统自动解析、分块、BM25索引存储")

    # 上方：上传区域
    st.subheader("上传文档")
    uploaded_files = st.file_uploader(
        "支持格式：Markdown / TXT / PDF",
        type=["md", "txt", "pdf"],
        accept_multiple_files=True
    )
    if uploaded_files:
        for file in uploaded_files:
            save_path = os.path.join(_USER_UPLOADS_DIR, file.name)
            with open(save_path, "wb") as f:
                f.write(file.getbuffer())
            with st.spinner(f"正在处理 {file.name}..."):
                result = knowledge_base.add_document(save_path, source="user")
            if result["status"] == "success":
                st.success(f"✅ {result['file']}：{result['chunks']} 个段落已入库")
                git_auto_commit(
                    files_message={save_path: f"用户上传 {file.name}"},
                    message=f"auto: 用户上传 {file.name}（{result['chunks']}段落）"
                )
            else:
                st.error(f"❌ {result['file']}：{result['status']}")

    # 分隔线
    st.markdown("---")

    # 下方：已入库文档列表（只读，无删除按钮）
    st.subheader("已入库文档")
    stats = knowledge_base.get_doc_stats()
    if stats["files"]:
        for f in stats["files"]:
            tag = "📌 预置" if f in stats.get("system_files", []) else "📤 用户上传"
            st.markdown(f"- `{f}`  {tag}")
    else:
        st.info("知识库为空，请先上传文档")

    # 预置知识库快速导入
    _preset_files = [f for f in os.listdir(_KNOWLEDGE_DIR)
                     if f.endswith(('.md', '.txt')) and f != 'jieba_dict.txt']
    _indexed = set(stats["files"])
    _unindexed = [f for f in _preset_files if f not in _indexed]
    if _unindexed:
        st.markdown("---")
        st.subheader("📚 预置知识库")
        st.caption("以下文件已随项目打包，可一键导入到知识库")
        for fname in _unindexed:
            fpath = os.path.join(_KNOWLEDGE_DIR, fname)
            if st.button(f"📥 导入 {fname}", key=f"import_{fname}"):
                with st.spinner(f"正在导入 {fname}..."):
                    result = knowledge_base.add_document(fpath, source="system")
                if result["status"] == "success":
                    st.success(f"✅ 导入成功：{result['chunks']} 个段落")
                    git_auto_commit(
                        message=f"auto: 导入预置知识库 {fname}（{result['chunks']}段落）"
                    )
                    st.rerun()
                else:
                    st.error(f"❌ 导入失败：{result['status']}")
    elif _preset_files:
        st.markdown("---")
        st.caption(f"📚 预置知识库已全部导入（{len(_preset_files)} 个文件）")

# ===================== Tab2: 智能问答 =====================
with tab2:
    st.header("智能问答")
    st.caption("基于知识库回答水晶相关问题，检索结果作为上下文确保准确性")

    if "qa_messages" not in st.session_state:
        st.session_state.qa_messages = []

    # 快捷问题
    st.markdown("**快捷提问：**")
    quick_qs = [
        "粉水晶适合什么人佩戴？",
        "黄水晶怎么保养？",
        "五行属木的人推荐什么水晶？",
        "紫水晶有什么功效？",
        "2026年适合佩戴什么水晶？"
    ]
    cols = st.columns(len(quick_qs))
    for i, q in enumerate(quick_qs):
        if cols[i].button(q, key=f"q{i}"):
            st.session_state.qa_quick_submit = q

    # 对话显示
    for msg in st.session_state.qa_messages:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])
            if "sources" in msg and msg["sources"]:
                with st.expander("📖 引用来源"):
                    for src in msg["sources"]:
                        st.markdown(f"- `{src['source_file']}` (相关度: {src['score']:.2f})")
                        st.markdown(f"> {src['text'][:150]}...")

    # 输入框
    prompt = st.chat_input("输入你的问题...", key="qa_input")
    if "qa_quick_submit" in st.session_state and st.session_state.qa_quick_submit:
        prompt = st.session_state.qa_quick_submit
        del st.session_state.qa_quick_submit

    if prompt:
        st.session_state.qa_messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)

        with st.spinner("正在检索知识库并生成回答..."):
            try:
                results = retriever.retrieve(prompt, top_k=5)

                if results:
                    context = retriever.format_context(results)
                    system_msg = f"""你是善福阁专业水晶文化顾问。

## 回答规则
1. 优先基于下方【知识库内容】回答，引用具体信息
2. 知识库中没有的信息，明确说"知识库暂无相关内容"
3. 不编造水晶功效、五行搭配等专业知识
4. 回答简洁有结构，适当分点

## 知识库内容
{context}"""
                else:
                    system_msg = "你是善福阁专业水晶文化顾问，基于你的专业知识回答水晶相关问题。注意：不编造信息，不确定的如实说明。"

                answer = llm_client.chat(
                    messages=[
                        {"role": "system", "content": system_msg},
                        {"role": "user", "content": prompt}
                    ]
                )
            except Exception as e:
                answer = f"服务暂时不可用（{e}），请稍后重试。"
                results = []

        msg_data = {"role": "assistant", "content": answer}
        if results:
            msg_data["sources"] = results[:3]
        st.session_state.qa_messages.append(msg_data)

        with st.chat_message("assistant"):
            st.markdown(answer)
            if results:
                with st.expander("📖 引用来源"):
                    for src in results[:3]:
                        st.markdown(f"- `{src['source_file']}` (相关度: {src['score']:.2f})")

    if st.session_state.qa_messages:
        if st.button("🗑️ 清空对话"):
            st.session_state.qa_messages = []
            st.rerun()

# ===================== Tab3: 内容生成 =====================
with tab3:
    st.header("内容生成")
    st.caption("选择模板，填入关键信息，一键生成营销文案")

    template = st.selectbox(
        "选择文案模板",
        ["小红书种草文案", "产品详情描述", "朋友圈文案", "视频号口播文案"]
    )

    # ==================== 小红书种草文案 ====================
    if template == "小红书种草文案":
        st.subheader("📝 小红书种草文案")
        col1, col2 = st.columns(2)
        with col1:
            crystal = st.text_input("水晶名称 *", placeholder="如：紫水晶、粉水晶", key="xhs_crystal")
            audience = st.text_input("目标人群", placeholder="如：上班族、学生党（选填）", key="xhs_audience")
        with col2:
            scene = st.text_input("使用场景", placeholder="如：招贵人、改善睡眠（选填）", key="xhs_scene")
            style = st.selectbox("文案风格", ["科普种草", "情感共鸣", "颜值展示"], key="xhs_style")

        col_gen, col_reg = st.columns([1, 5])
        with col_gen:
            if st.button("✨ 生成文案", type="primary", disabled=not crystal, key="xhs_gen"):
                with st.spinner("正在生成小红书文案..."):
                    try:
                        from modules.generator import generate_xiaohongshu
                        result = generate_xiaohongshu(crystal, audience, scene, style)
                        st.session_state.xhs_result = result
                    except Exception as e:
                        st.error(f"生成失败：{e}")
                        st.caption("可能是 API 超时或限流，请稍后重试")
        with col_reg:
            if "xhs_result" in st.session_state:
                if st.button("🔄 换一条", key="xhs_reg"):
                    with st.spinner("正在重新生成..."):
                        try:
                            from modules.generator import generate_xiaohongshu
                            result = generate_xiaohongshu(crystal, audience, scene, style)
                            st.session_state.xhs_result = result
                        except Exception as e:
                            st.error(f"生成失败：{e}")

        if "xhs_result" in st.session_state:
            st.markdown("---")
            st.markdown("### 生成结果")
            show_quality_badge(st.session_state.xhs_result)
            st.markdown(st.session_state.xhs_result["content"])
            with st.expander("📝 纯文本"):
                st.text(st.session_state.xhs_result["content"])

    # ==================== 产品详情描述 ====================
    elif template == "产品详情描述":
        st.subheader("📦 产品详情描述")
        col1, col2 = st.columns(2)
        with col1:
            crystal = st.text_input("水晶名称 *", placeholder="如：绿幽灵", key="pd_crystal")
            spec = st.text_input("规格", placeholder="如：8mm、10mm、原矿（选填）", key="pd_spec")
        with col2:
            purpose = st.text_input("用途", placeholder="如：旺事业、招财、送人（选填）", key="pd_purpose")

        col_gen, col_reg = st.columns([1, 5])
        with col_gen:
            if st.button("✨ 生成描述", type="primary", disabled=not crystal, key="pd_gen"):
                with st.spinner("正在生成产品描述..."):
                    try:
                        from modules.generator import generate_product_desc
                        result = generate_product_desc(crystal, spec, purpose)
                        st.session_state.pd_result = result
                    except Exception as e:
                        st.error(f"生成失败：{e}")
                        st.caption("可能是 API 超时或限流，请稍后重试")
        with col_reg:
            if "pd_result" in st.session_state:
                if st.button("🔄 换一条", key="pd_reg"):
                    with st.spinner("正在重新生成..."):
                        try:
                            from modules.generator import generate_product_desc
                            result = generate_product_desc(crystal, spec, purpose)
                            st.session_state.pd_result = result
                        except Exception as e:
                            st.error(f"生成失败：{e}")

        if "pd_result" in st.session_state:
            st.markdown("---")
            st.markdown("### 生成结果")
            show_quality_badge(st.session_state.pd_result)
            st.markdown(st.session_state.pd_result["content"])
            with st.expander("📝 纯文本"):
                st.text(st.session_state.pd_result["content"])

    # ==================== 朋友圈文案 ====================
    elif template == "朋友圈文案":
        st.subheader("📱 朋友圈文案")
        col1, col2 = st.columns(2)
        with col1:
            crystal = st.text_input("水晶名称 *", placeholder="如：黄水晶", key="mom_crystal")
            scene = st.text_input("场景", placeholder="如：上新、今日推荐（选填）", key="mom_scene")
        with col2:
            style = st.selectbox("文案风格", ["简约专业", "温馨种草", "促销活动"], key="mom_style")
            batch = st.selectbox("生成条数", [1, 2, 3], index=2, key="mom_batch")

        if st.button("✨ 批量生成", type="primary", disabled=not crystal, key="mom_gen"):
            with st.spinner(f"正在生成 {batch} 条朋友圈文案..."):
                try:
                    from modules.generator import generate_moments
                    result = generate_moments(crystal, scene, style, batch=batch)
                    st.session_state.mom_result = result
                except Exception as e:
                    st.error(f"生成失败：{e}")
                    st.caption("可能是 API 超时或限流，请稍后重试")

        if "mom_result" in st.session_state:
            st.markdown("---")
            st.markdown("### 生成结果")
            show_quality_badge(st.session_state.mom_result)
            copies = st.session_state.mom_result["copies"]
            individual_scores = st.session_state.mom_result.get("quality_details", {}).get("individual_scores", [])
            for i, copy in enumerate(copies):
                with st.container():
                    score_tag = f"（{individual_scores[i]}分）" if i < len(individual_scores) else ""
                    st.markdown(f"**📝 方案 {i+1}**{score_tag}")
                    st.markdown(copy)
                    if i < len(copies) - 1:
                        st.divider()

    # ==================== 视频号口播文案 ====================
    elif template == "视频号口播文案":
        st.subheader("🎬 视频号口播文案")
        col1, col2 = st.columns(2)
        with col1:
            crystal = st.text_input("水晶名称 *", placeholder="如：紫水晶、绿幽灵", key="vid_crystal")
            purpose = st.text_input("视频目的", placeholder="如：种草转化、知识科普、引流（选填）", key="vid_purpose")
        with col2:
            version = st.selectbox(
                "文案版本",
                ["两个版本都生成（15秒+45秒）", "仅15秒快剪版", "仅45秒深度版"],
                key="vid_version"
            )

        version_map = {
            "两个版本都生成（15秒+45秒）": "both",
            "仅15秒快剪版": "15s",
            "仅45秒深度版": "45s"
        }

        col_gen, col_reg = st.columns([1, 5])
        with col_gen:
            if st.button("✨ 生成文案", type="primary", disabled=not crystal, key="vid_gen"):
                with st.spinner("正在生成视频号文案..."):
                    try:
                        from modules.generator import generate_video_script
                        result = generate_video_script(crystal, purpose, version=version_map[version])
                        st.session_state.vid_result = result
                    except Exception as e:
                        st.error(f"生成失败：{e}")
                        st.caption("可能是 API 超时或限流，请稍后重试")
        with col_reg:
            if "vid_result" in st.session_state:
                if st.button("🔄 换一条", key="vid_reg"):
                    with st.spinner("正在重新生成..."):
                        try:
                            from modules.generator import generate_video_script
                            result = generate_video_script(crystal, purpose, version=version_map[version])
                            st.session_state.vid_result = result
                        except Exception as e:
                            st.error(f"生成失败：{e}")

        if "vid_result" in st.session_state:
            st.markdown("---")
            st.markdown("### 生成结果")
            show_quality_badge(st.session_state.vid_result)
            st.markdown(st.session_state.vid_result["content"])
            with st.expander("📝 纯文本"):
                st.text(st.session_state.vid_result["content"])

# ===================== Tab4: 内容库 =====================
with tab4:
    st.header("内容库")
    st.caption("浏览、收藏、导出历史生成内容")

    from modules.content_store import list_contents, toggle_favorite, delete_content, get_stats, export_txt, export_batch_txt

    # 统计概览
    stats = get_stats()
    if stats["total"] == 0:
        st.info("内容库为空。在「内容生成」中生成文案后会自动保存到这里。")
    else:
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("总内容", stats["total"])
        col2.metric("已收藏", stats["favorites"])
        col3.metric("模板类型", stats["template_types"])
        col4.metric("水晶种类", stats["crystal_names"])

    # 筛选栏
    if stats["total"] > 0:
        st.markdown("---")
        filter_col1, filter_col2, filter_col3 = st.columns([1, 1, 1])
        with filter_col1:
            filter_template = st.selectbox(
                "按模板筛选",
                ["全部"] + stats["templates"],
                key="lib_filter_template"
            )
        with filter_col2:
            filter_crystal = st.selectbox(
                "按水晶筛选",
                ["全部"] + stats["crystals"],
                key="lib_filter_crystal"
            )
        with filter_col3:
            filter_fav = st.checkbox("仅显示收藏", key="lib_filter_fav")

        # 获取筛选结果
        records = list_contents(
            template="" if filter_template == "全部" else filter_template,
            crystal_name="" if filter_crystal == "全部" else filter_crystal,
            favorite_only=filter_fav,
        )

        if not records:
            st.info("没有符合筛选条件的内容。")

        # 列表展示
        for record in records:
            rid = record["id"]
            template = record.get("template", "")
            crystal = record.get("crystal_name", "")
            style = record.get("style", "")
            created = record.get("created_at", "")
            score = record.get("quality_score", -1)
            is_fav = record.get("favorite", False)
            batch_idx = record.get("batch_index", "")

            # 标题行
            title_parts = [template]
            if crystal:
                title_parts.append(crystal)
            if style:
                title_parts.append(style)
            if batch_idx:
                title_parts.append(f"方案{batch_idx}")
            title_text = " · ".join(title_parts)

            # 评分标记
            if score >= 0:
                if score >= 80:
                    score_tag = f"🟢 {score}分"
                elif score >= 60:
                    score_tag = f"🟡 {score}分"
                else:
                    score_tag = f"🔴 {score}分"
            else:
                score_tag = ""

            fav_icon = "⭐" if is_fav else "☆"

            with st.container():
                expander_title = f"{fav_icon} {title_text}  |  {created}  |  {score_tag}"
                with st.expander(expander_title):
                    # 操作按钮行（去掉了"复制"按钮）
                    btn_col1, btn_col2, btn_col3 = st.columns([1, 1, 2])
                    with btn_col1:
                        fav_label = "取消收藏" if is_fav else "收藏"
                        if st.button(fav_label, key=f"fav_{rid}"):
                            toggle_favorite(rid)
                            st.rerun()
                    with btn_col2:
                        if st.button("删除", key=f"del_{rid}"):
                            delete_content(rid)
                            st.rerun()
                    with btn_col3:
                        if st.button("导出TXT", key=f"export_{rid}"):
                            path = export_txt(record["content"], f"{crystal}_{template}.txt")
                            st.success(f"已导出到: {path}")

                    # 内容展示
                    st.markdown(record["content"])

                    # 质量信息
                    if score >= 0:
                        issues = record.get("quality_issues", [])
                        if issues:
                            st.caption(f"优化空间: {'; '.join(issues)}")

        # 底部操作
        if records:
            st.markdown("---")
            export_col1, export_col2 = st.columns([1, 3])
            with export_col1:
                if st.button("📦 批量导出全部（TXT）", key="export_all"):
                    path = export_batch_txt(records, f"全部导出_{int(time.time())}.txt")
                    st.success(f"已导出 {len(records)} 条到: {path}")

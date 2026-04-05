import re
from io import BytesIO

import streamlit as st
from PyPDF2 import PdfReader


def clean_text(text: str) -> str:
    """
    清理 PDF 提取出来的文本。
    这样可以减少多余空格和换行，方便后面做匹配。
    """
    lines = text.splitlines()
    cleaned_lines = []

    for line in lines:
        line = line.strip()
        if line:
            cleaned_lines.append(line)

    cleaned_text = "\n".join(cleaned_lines)
    cleaned_text = re.sub(r"[ \t]+", " ", cleaned_text)
    cleaned_text = re.sub(r"\n{2,}", "\n", cleaned_text)

    return cleaned_text.strip()


def read_pdf_pages(uploaded_file) -> list[dict]:
    """
    读取上传的 PDF 文件，保留每一页的文字内容。
    这样后面回答问题时，就能告诉用户答案来自哪一页。
    """
    file_bytes = uploaded_file.getvalue()
    reader = PdfReader(BytesIO(file_bytes))
    pages = []

    for page_index, page in enumerate(reader.pages, start=1):
        page_text = page.extract_text()

        if page_text:
            cleaned_page_text = clean_text(page_text)
            if cleaned_page_text:
                pages.append(
                    {
                        "page_number": page_index,
                        "text": cleaned_page_text,
                    }
                )

    return pages


def split_into_paragraphs(page_text: str) -> list[str]:
    """
    把一页 PDF 文本切分成段落列表。
    这里优先按空行切分段落。
    单个换行通常只是排版换行，所以先把它们合并成空格，
    这样参考原文会保留更完整的上下文。
    """
    normalized_text = page_text.replace("\r", "\n")
    normalized_text = re.sub(r"\n{2,}", "\n\n", normalized_text)
    raw_paragraphs = re.split(r"\n\s*\n+", normalized_text)
    paragraphs = []

    for paragraph in raw_paragraphs:
        paragraph = re.sub(r"\s*\n\s*", " ", paragraph).strip()
        if not paragraph:
            continue

        paragraphs.append(paragraph)

    return paragraphs


def split_into_sentences(text: str) -> list[str]:
    """
    把一段文字继续切成句子。
    这样可以更准确地定位到真正包含关键词的那一句。
    """
    sentences = re.split(r"(?<=[。！？.!?])\s*", text)
    return [sentence.strip() for sentence in sentences if sentence.strip()]


def build_context_text(paragraph: str, sentence_index: int, window: int = 1) -> str:
    """
    根据命中的句子，返回更长一点的上下文。
    默认取“前一句 + 当前句 + 后一句”。
    """
    sentences = split_into_sentences(paragraph)

    if not sentences:
        return paragraph

    start = max(0, sentence_index - window)
    end = min(len(sentences), sentence_index + window + 1)
    return " ".join(sentences[start:end])


def extract_keywords(keyword_input: str) -> list[str]:
    """
    从用户输入的关键词中提取关键词。
    中文、英文和数字都会保留。
    """
    words = re.findall(r"[\u4e00-\u9fff]+|[a-zA-Z0-9]+", keyword_input.lower())

    keywords = []
    for word in words:
        # 中文问题里，单个字也可能有意义，比如“税”“爱”“光”
        if len(word) >= 2:
            keywords.append(word)
        elif len(word) == 1 and re.match(r"[\u4e00-\u9fff]", word):
            keywords.append(word)

    return keywords


def calculate_score(paragraph: str, keywords: list[str]) -> int:
    """
    计算一个段落和关键词的匹配分数。
    命中的关键词越多、出现次数越多，分数越高。
    """
    paragraph_lower = paragraph.lower()
    score = 0

    for keyword in keywords:
        score += paragraph_lower.count(keyword)

    return score


def highlight_keywords(text: str, keywords: list[str], color: str) -> str:
    """
    把文本中的关键词高亮显示成指定颜色。
    """
    highlighted_text = text
    sorted_keywords = sorted(set(keywords), key=len, reverse=True)

    for keyword in sorted_keywords:
        if not keyword:
            continue

        pattern = re.escape(keyword)
        replacement = (
            f"<span style='color: {color}; font-weight: bold;'>{keyword}</span>"
        )
        highlighted_text = re.sub(pattern, replacement, highlighted_text, flags=re.IGNORECASE)

    return highlighted_text


def find_relevant_sentences(pages: list[dict], keyword_input: str, top_n: int = 3) -> list[dict]:
    """
    从所有页面里找出和关键词最相关的几句话，并保留页码信息。
    """
    keywords = extract_keywords(keyword_input)

    if not keywords:
        return []

    scored_sentences = []

    for page in pages:
        page_number = page["page_number"]
        paragraphs = split_into_paragraphs(page["text"])

        for paragraph_index, paragraph in enumerate(paragraphs, start=1):
            sentences = split_into_sentences(paragraph)

            for sentence_index, sentence in enumerate(sentences, start=1):
                score = calculate_score(sentence, keywords)

                if score > 0:
                    scored_sentences.append(
                        {
                            "score": score,
                            "page_number": page_number,
                            "sentence_number": sentence_index,
                            "text": sentence,
                            "context_text": build_context_text(paragraph, sentence_index - 1),
                        }
                    )

    if not scored_sentences:
        return []

    scored_sentences.sort(key=lambda item: item["score"], reverse=True)

    selected_sentences = []
    seen_sentences = set()

    for item in scored_sentences:
        unique_key = (item["page_number"], item["sentence_number"], item["text"])

        if unique_key not in seen_sentences:
            selected_sentences.append(item)
            seen_sentences.add(unique_key)

        if len(selected_sentences) >= top_n:
            break

    return selected_sentences


def generate_answer(keyword_input: str, reference_items: list[dict]) -> str:
    """
    基于找到的参考原文，生成一个最简单的回答。
    这里不调用大模型，只把最相关内容整理成答案。
    """
    if not reference_items:
        return "没有在 PDF 中找到和这个关键词相关的内容。"

    if len(reference_items) == 1:
        return f"根据 PDF 内容，和关键词“{keyword_input}”最相关的信息是：{reference_items[0]['text']}"

    merged_text = "；".join(item["text"] for item in reference_items[:3])
    return f"根据 PDF 内容，和关键词“{keyword_input}”相关的信息主要有这些：{merged_text}"


def generate_answer_lines(keyword_input: str, reference_items: list[dict]) -> list[str]:
    """
    把回答拆成多行，便于页面逐条展示。
    """
    if not reference_items:
        return ["没有在 PDF 中找到和这个关键词相关的内容。"]

    answer_lines = []
    for item in reference_items:
        answer_lines.append(f"和关键词“{keyword_input}”相关的信息：{item['text']}")

    return answer_lines


def main() -> None:
    st.set_page_config(page_title="AI PDF学习助手", page_icon="📘")
    st.title("AI PDF学习助手")
    st.write("上传 PDF 文件后，输入关键词，系统会从文档中找出最相关的内容。")

    st.subheader("第一步：上传 PDF")
    uploaded_file = st.file_uploader("请选择一个 PDF 文件", type=["pdf"])

    st.subheader("第二步：输入关键词")
    with st.form("question_form"):
        keyword_input = st.text_input("请输入关键词")
        ask_button = st.form_submit_button("开始检索")

    if ask_button:
        if uploaded_file is None:
            st.warning("请先上传 PDF 文件")
            return

        if not keyword_input.strip():
            st.warning("请输入关键词")
            return

        try:
            pages = read_pdf_pages(uploaded_file)
        except Exception as error:
            st.error(f"读取 PDF 失败：{error}")
            return

        if not pages:
            st.warning("这个 PDF 没有读取到可用文字内容。")
            return

        relevant_sentences = find_relevant_sentences(pages, keyword_input)
        keywords = extract_keywords(keyword_input)
        answer_lines = generate_answer_lines(keyword_input, relevant_sentences)

        st.divider()
        st.subheader("用户关键词")
        st.write(keyword_input)

        st.subheader("AI 回答")
        for answer_line in answer_lines:
            highlighted_answer = highlight_keywords(answer_line, keywords, "#d97706")
            st.markdown(
                (
                    "<div style='color: #2563eb; background-color: #eff6ff; "
                    "padding: 12px; border-radius: 10px; line-height: 1.8; "
                    "margin-bottom: 12px;'>"
                    f"{highlighted_answer}"
                    "</div>"
                ),
                unsafe_allow_html=True,
            )

        st.subheader("参考原文片段")
        if relevant_sentences:
            for index, item in enumerate(relevant_sentences, start=1):
                highlighted_context = highlight_keywords(item["context_text"], keywords, "#dc2626")
                st.markdown(f"**片段 {index}：**")
                st.markdown(
                    (
                        "<div style='color: #166534; background-color: #f0fdf4; "
                        "padding: 12px; border-radius: 10px; line-height: 1.8;'>"
                        f"{highlighted_context}"
                        "</div>"
                    ),
                    unsafe_allow_html=True,
                )
                st.caption(f"定位：第 {item['page_number']} 页")
        else:
            st.write("没有找到相关原文片段。")
    else:
        if uploaded_file is None:
            st.info("请先上传 PDF 文件")


if __name__ == "__main__":
    main()

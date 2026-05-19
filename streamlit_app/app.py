import streamlit as st
from groq import Groq
import os
from dotenv import load_dotenv
import json
import html
import re
import csv
import sys
from datetime import datetime

# ---------------- PAGE CONFIG ----------------

st.set_page_config(
    page_title="QA AI Assistant",
    layout="wide"
)

# ---------------- GROQ CLIENT ----------------
load_dotenv()

client = Groq(
    api_key=os.getenv("GROQ_API_KEY")
)

MAX_ATTACHMENT_PREVIEW_ROWS = 10
MAX_ATTACHMENT_SUMMARY_CHARS = 12000


def ensure_workspace_packages():
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    site_packages = os.path.join(project_root, "venv", "Lib", "site-packages")

    if os.path.isdir(site_packages) and site_packages not in sys.path:
        sys.path.insert(0, site_packages)


def get_ticket_topic(ticket_content):
    for line in ticket_content.splitlines():
        cleaned_line = line.strip()

        if cleaned_line:
            return cleaned_line

    return "General investigation"


def get_available_tickets():
    try:
        ticket_files = [
            file_name[:-4]
            for file_name in os.listdir("tickets")
            if file_name.lower().endswith(".txt")
        ]

        return sorted(ticket_files)
    except:
        return []


def get_ticket_attachments(ticket_id):
    try:
        ticket_key = ticket_id.lower()

        return sorted([
            file_name
            for file_name in os.listdir("attachments")
            if ticket_key in file_name.lower()
        ])
    except:
        return []


def get_interesting_columns(columns):
    keywords = [
        "id",
        "student",
        "mobile",
        "phone",
        "status",
        "discount",
        "scholarship",
        "order",
        "code",
    ]

    return [
        column
        for column in columns
        if any(keyword in str(column).lower() for keyword in keywords)
    ]


def summarize_dataframe(df, source_name):
    summary = [
        f"Source: {source_name}",
        f"Rows: {len(df)}",
        f"Columns: {', '.join(str(column) for column in df.columns)}",
    ]

    interesting_columns = get_interesting_columns(df.columns)

    if interesting_columns:
        summary.append(
            "Likely QA-relevant columns: "
            + ", ".join(str(column) for column in interesting_columns)
        )

        for column in interesting_columns[:6]:
            values = (
                df[column]
                .dropna()
                .astype(str)
                .str.strip()
            )
            values = values[values != ""].unique()[:8]

            if len(values):
                summary.append(
                    f"Sample values for {column}: {', '.join(values)}"
                )

    if not df.empty:
        preview = df.head(MAX_ATTACHMENT_PREVIEW_ROWS).fillna("").astype(str)
        summary.append("Preview rows:")
        summary.append(preview.to_string(index=False))

    return "\n".join(summary)


def summarize_table(headers, rows, source_name, total_rows=None):
    headers = [str(header) if header is not None else "" for header in headers]
    rows = [
        ["" if value is None else str(value) for value in row]
        for row in rows
    ]
    row_count = total_rows if total_rows is not None else len(rows)
    summary = [
        f"Source: {source_name}",
        f"Rows: {row_count}",
        f"Columns: {', '.join(headers)}",
    ]
    interesting_columns = get_interesting_columns(headers)

    if interesting_columns:
        summary.append(
            "Likely QA-relevant columns: " + ", ".join(interesting_columns)
        )

        for column in interesting_columns[:6]:
            column_index = headers.index(column)
            values = []

            for row in rows:
                if column_index < len(row):
                    value = row[column_index].strip()

                    if value and value not in values:
                        values.append(value)

                if len(values) >= 8:
                    break

            if values:
                summary.append(
                    f"Sample values for {column}: {', '.join(values)}"
                )

    if rows:
        summary.append("Preview rows:")
        summary.append("\t".join(headers))

        for row in rows[:MAX_ATTACHMENT_PREVIEW_ROWS]:
            padded_row = row + [""] * max(0, len(headers) - len(row))
            summary.append("\t".join(padded_row[:len(headers)]))

    return "\n".join(summary)


def read_csv_fallback(file_path):
    with open(file_path, "r", encoding="utf-8-sig", newline="") as file:
        reader = csv.reader(file)
        headers = next(reader, [])
        rows = []

        for index, row in enumerate(reader):
            if index < 50:
                rows.append(row)

        total_rows = index + 1 if "index" in locals() else 0

    return summarize_table(headers, rows, "CSV", total_rows)


def read_excel_fallback(file_path):
    ensure_workspace_packages()

    from openpyxl import load_workbook

    workbook = load_workbook(file_path, read_only=True, data_only=True)
    sheet_blocks = []

    for sheet in workbook.worksheets:
        rows_iterator = sheet.iter_rows(values_only=True)
        headers = next(rows_iterator, [])
        rows = []

        for index, row in enumerate(rows_iterator):
            if index < 50:
                rows.append(list(row))

        total_rows = max((sheet.max_row or (len(rows) + 1)) - 1, 0)
        sheet_blocks.append(
            summarize_table(headers, rows, f"Sheet: {sheet.title}", total_rows)
        )

    workbook.close()
    return "\n\n".join(sheet_blocks)


@st.cache_data(show_spinner=False)
def build_attachment_content_summary(attachments):
    ensure_workspace_packages()

    try:
        import pandas as pd
        pandas_error = None
    except Exception as error:
        pd = None
        pandas_error = error

    summary_blocks = []
    parsed_files = 0
    unsupported_files = []

    if pandas_error:
        summary_blocks.append(
            "Pandas could not be loaded in this environment, so the app used "
            "a lightweight fallback reader for Excel/CSV parsing."
        )

    for attachment in attachments:
        file_path = os.path.join("attachments", attachment)
        extension = os.path.splitext(attachment)[1].lower()

        try:
            if extension in [".xlsx", ".xls"]:
                if pd is not None:
                    excel_file = pd.ExcelFile(file_path)
                    sheet_blocks = [f"File: {attachment}"]

                    for sheet_name in excel_file.sheet_names:
                        df = pd.read_excel(file_path, sheet_name=sheet_name)
                        sheet_blocks.append(
                            summarize_dataframe(df, f"Sheet: {sheet_name}")
                        )

                    summary_blocks.append("\n\n".join(sheet_blocks))
                elif extension == ".xlsx":
                    summary_blocks.append(
                        "\n".join([
                            f"File: {attachment}",
                            read_excel_fallback(file_path),
                        ])
                    )
                else:
                    unsupported_files.append(attachment)
                    continue

                parsed_files += 1
            elif extension == ".csv":
                if pd is not None:
                    df = pd.read_csv(file_path)
                    summary_blocks.append(
                        "\n".join([
                            f"File: {attachment}",
                            summarize_dataframe(df, "CSV"),
                        ])
                    )
                else:
                    summary_blocks.append(
                        "\n".join([
                            f"File: {attachment}",
                            read_csv_fallback(file_path),
                        ])
                    )

                parsed_files += 1
            else:
                unsupported_files.append(attachment)
        except Exception as error:
            summary_blocks.append(
                f"File: {attachment}\nCould not parse attachment: {error}"
            )

    if unsupported_files:
        summary_blocks.append(
            "Unsupported attachments not parsed yet: "
            + ", ".join(unsupported_files)
        )

    summary = "\n\n---\n\n".join(summary_blocks).strip()

    if len(summary) > MAX_ATTACHMENT_SUMMARY_CHARS:
        summary = (
            summary[:MAX_ATTACHMENT_SUMMARY_CHARS]
            + "\n\n[Attachment summary truncated for prompt size.]"
        )

    return summary, parsed_files, len(unsupported_files)


def get_topic_for_ticket(ticket_id):
    try:
        with open(f"tickets/{ticket_id}.txt", "r", encoding="utf-8") as file:
            return get_ticket_topic(file.read())
    except:
        return "General investigation"


def build_history_groups(history):
    groups = {}
    topic_cache = {}

    for item in history:
        ticket_id = item.get("ticket", "Unknown ticket")
        topic = item.get("topic")

        if not topic:
            if ticket_id not in topic_cache:
                topic_cache[ticket_id] = get_topic_for_ticket(ticket_id)

            topic = topic_cache[ticket_id]

        group_key = f"{ticket_id}::{topic}"

        if group_key not in groups:
            groups[group_key] = {
                "ticket": ticket_id,
                "topic": topic,
                "items": []
            }

        groups[group_key]["items"].append(item)

    return groups


def parse_timestamp(timestamp):
    if not timestamp:
        return datetime.min

    try:
        return datetime.fromisoformat(timestamp)
    except ValueError:
        try:
            return datetime.strptime(timestamp, "%Y-%m-%d %H:%M:%S.%f")
        except ValueError:
            return datetime.min


def format_timestamp(timestamp):
    if not timestamp:
        return ""

    try:
        return parse_timestamp(timestamp).strftime("%d %b %Y, %I:%M %p")
    except ValueError:
        return timestamp


ANALYSIS_SECTIONS = [
    ("Affected Areas", ["Affected Areas"]),
    ("DB Checks", ["DB Checks", "Important DB Checks"]),
    ("Risky Dependencies", ["Risky Dependencies"]),
    ("Suggested Investigation", ["Suggested Investigation"]),
    ("Suggested Test Scenarios", ["Suggested Test Scenarios", "Test Scenarios"]),
    ("Suggested SQL Queries", ["Suggested SQL Queries", "SQL Queries"]),
    ("Regression Focus", ["Regression Focus"]),
]

SECTION_ICONS = {
    "Affected Areas": "🎯",
    "DB Checks": "🗄️",
    "Risky Dependencies": "⚠️",
    "Suggested Investigation": "🧭",
    "Suggested Test Scenarios": "🧪",
    "Suggested SQL Queries": "🧾",
    "Regression Focus": "✅",
}


def normalize_heading(heading):
    return heading.lower().replace("important ", "").strip()


def parse_analysis_sections(response):
    sections = {}
    current_section = None
    current_lines = []

    for line in response.splitlines():
        heading_match = re.match(r"^\s*#{1,3}\s+(.+?)\s*$", line)

        if heading_match:
            heading = heading_match.group(1).strip()
            normalized_heading = normalize_heading(heading)
            matched_title = None

            for title, aliases in ANALYSIS_SECTIONS:
                if normalized_heading in [normalize_heading(alias) for alias in aliases]:
                    matched_title = title
                    break

            if matched_title:
                if current_section:
                    sections[current_section] = "\n".join(current_lines).strip()

                current_section = matched_title
                current_lines = []
                continue

        if current_section:
            current_lines.append(line)

    if current_section:
        sections[current_section] = "\n".join(current_lines).strip()

    return sections


def render_inline_markdown(text):
    escaped_text = html.escape(text.strip())
    return re.sub(r"`([^`]+)`", r"<code>\1</code>", escaped_text)


def render_section_body(content):
    html_lines = []
    in_list = False
    in_code_block = False
    code_lines = []

    for line in content.splitlines():
        stripped_line = line.strip()

        if stripped_line.startswith("```"):
            if in_code_block:
                html_lines.append(
                    "<pre><code>"
                    + html.escape("\n".join(code_lines))
                    + "</code></pre>"
                )
                code_lines = []
                in_code_block = False
            else:
                if in_list:
                    html_lines.append("</ul>")
                    in_list = False

                in_code_block = True

            continue

        if in_code_block:
            code_lines.append(line)
            continue

        if not stripped_line:
            if in_list:
                html_lines.append("</ul>")
                in_list = False
            continue

        if stripped_line.startswith("- "):
            if not in_list:
                html_lines.append("<ul>")
                in_list = True

            html_lines.append(f"<li>{render_inline_markdown(stripped_line[2:])}</li>")
        else:
            if in_list:
                html_lines.append("</ul>")
                in_list = False

            html_lines.append(f"<p>{render_inline_markdown(stripped_line)}</p>")

    if in_list:
        html_lines.append("</ul>")

    if in_code_block:
        html_lines.append(
            "<pre><code>"
            + html.escape("\n".join(code_lines))
            + "</code></pre>"
        )

    return "\n".join(html_lines)


def render_ai_analysis(response):
    sections = parse_analysis_sections(response)

    if not sections:
        st.markdown(response)
        return

    st.markdown('<div class="qa-analysis-grid">', unsafe_allow_html=True)

    for title, _ in ANALYSIS_SECTIONS:
        content = sections.get(title)

        if not content:
            continue

        st.markdown(
            f"""
            <section class="qa-analysis-card">
                <h4>{SECTION_ICONS.get(title, "•")} {html.escape(title)}</h4>
                <div class="qa-analysis-body">
                    {render_section_body(content)}
                </div>
            </section>
            """,
            unsafe_allow_html=True
        )

    st.markdown("</div>", unsafe_allow_html=True)


def calculate_confidence_score(
    ticket_content,
    attachment_count,
    attachment_summary,
    has_historical_context
):
    score = 48
    ticket_length = len(ticket_content.strip())

    if ticket_content and ticket_content != "Ticket not found.":
        score += min(ticket_length // 80, 22)

    if attachment_count:
        score += 10

    if attachment_summary:
        score += 14

    if has_historical_context:
        score += 8

    return max(35, min(score, 95))


def get_data_sources_used(
    ticket_content,
    attachments,
    attachment_summary,
    has_historical_context
):
    sources = []

    if ticket_content and ticket_content != "Ticket not found.":
        sources.append("Jira Ticket")

    if any(
        os.path.splitext(attachment)[1].lower() in [".xlsx", ".xls", ".csv"]
        for attachment in attachments
    ):
        sources.append("Excel Attachment")

    if attachment_summary:
        sources.append("Parsed Document")

    if has_historical_context:
        sources.append("Historical Investigation")

    return sources


def render_grounding_panel(confidence_score, data_sources):
    source_items = "".join(
        f"<li>✓ {html.escape(source)}</li>"
        for source in data_sources
    )

    st.markdown(
        f"""
        <div class="grounding-grid">
            <section class="grounding-card confidence-card">
                <span>Confidence Level</span>
                <strong>{confidence_score}%</strong>
            </section>
            <section class="grounding-card sources-card">
                <span>Sources Used</span>
                <ul>{source_items}</ul>
            </section>
        </div>
        """,
        unsafe_allow_html=True
    )


# ---------------- SIDEBAR ----------------

st.sidebar.title("QA AI Assistant")

st.sidebar.markdown("## 📌 Investigation History")

history = []

try:
    with open("chat_history/history.json", "r", encoding="utf-8") as file:
        history = json.load(file)

        if not history:
            st.sidebar.write("No history yet.")

        history_groups = build_history_groups(history)

        sorted_groups = sorted(
            history_groups.values(),
            key=lambda group: max(
                parse_timestamp(item.get("timestamp", ""))
                for item in group["items"]
            ),
            reverse=True
        )

        for group in sorted_groups:
            ticket_id = group["ticket"]
            topic = group["topic"]
            searches = sorted(
                group["items"],
                key=lambda item: parse_timestamp(item.get("timestamp", "")),
                reverse=True
            )
            search_count = len(searches)
            group_title = f"{ticket_id} - {topic}"

            if len(group_title) > 48:
                group_title = f"{group_title[:48]}..."

            with st.sidebar.expander(f"{group_title} ({search_count})"):
                tab_labels = [f"Search {index + 1}" for index in range(search_count)]
                tabs = st.tabs(tab_labels)

                for tab, item in zip(tabs, searches):
                    with tab:
                        timestamp = format_timestamp(item.get("timestamp", ""))
                        question = item.get("question", "No question")
                        response = item.get("response", "No response saved.")

                        if timestamp:
                            st.caption(timestamp)

                        st.markdown("**Question**")
                        st.write(question)

                        if item.get("confidence_score") and item.get("data_sources"):
                            render_grounding_panel(
                                item["confidence_score"],
                                item["data_sources"]
                            )

                        st.markdown("**AI Analysis**")
                        render_ai_analysis(response)

except:
    st.sidebar.write("No history yet.")
    st.sidebar.markdown("- Scholarship")
    st.sidebar.markdown("- Orders")
    st.sidebar.markdown("- Discounts")

# ---------------- MAIN UI ----------------

st.image("banner.png", use_container_width=True)

st.title("🔎 QA AI Impact Analysis Assistant")

st.markdown(
    "Analyze Jira tickets and identify affected areas, business logic, and regression risks."
)

st.markdown(
    """
    <style>
    html, body, [data-testid="stAppViewContainer"] {
        background: #0f172a;
    }

    [data-testid="stAppViewContainer"] {
        color: #f8fafc;
    }

    h1, h2, h3 {
        color: #e0f2fe;
    }

    [data-testid="stExpander"] {
        border: 1px solid rgba(56, 189, 248, 0.26);
        border-radius: 8px;
        background: rgba(15, 23, 42, 0.42);
    }

    .qa-analysis-grid {
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
        gap: 0.85rem;
        margin-top: 0.5rem;
    }

    .qa-analysis-card {
        border: 1px solid rgba(125, 211, 252, 0.34);
        border-radius: 8px;
        background: linear-gradient(180deg, rgba(30, 41, 59, 0.96), rgba(15, 23, 42, 0.96));
        box-shadow: 0 14px 28px rgba(2, 132, 199, 0.12);
        padding: 1rem;
        min-height: 10rem;
    }

    .qa-analysis-card h4 {
        color: #bae6fd;
        font-size: 1.08rem;
        margin: 0 0 0.65rem 0;
    }

    .qa-analysis-body {
        color: #e2e8f0;
        font-size: 1rem;
        line-height: 1.55;
    }

    .qa-analysis-body ul {
        margin: 0;
        padding-left: 1.1rem;
    }

    .qa-analysis-body li {
        margin-bottom: 0.45rem;
    }

    .qa-analysis-body code {
        background: rgba(14, 165, 233, 0.16);
        color: #e0f2fe;
        border-radius: 4px;
        padding: 0.08rem 0.28rem;
    }

    .qa-analysis-body pre {
        background: rgba(2, 6, 23, 0.68);
        border: 1px solid rgba(125, 211, 252, 0.22);
        border-radius: 8px;
        margin: 0.6rem 0 0 0;
        overflow-x: auto;
        padding: 0.75rem;
    }

    .qa-analysis-body pre code {
        background: transparent;
        color: #e0f2fe;
        padding: 0;
        white-space: pre;
    }

    .grounding-grid {
        display: grid;
        grid-template-columns: minmax(180px, 0.65fr) minmax(260px, 1.35fr);
        gap: 0.85rem;
        margin: 0.75rem 0 1rem 0;
    }

    .grounding-card {
        border: 1px solid rgba(125, 211, 252, 0.34);
        border-radius: 8px;
        background: rgba(14, 165, 233, 0.12);
        padding: 0.9rem 1rem;
    }

    .grounding-card span {
        color: #bae6fd;
        display: block;
        font-size: 0.92rem;
        font-weight: 700;
        margin-bottom: 0.35rem;
    }

    .confidence-card strong {
        color: #f8fafc;
        font-size: 2rem;
        line-height: 1;
    }

    .sources-card ul {
        color: #e2e8f0;
        list-style: none;
        margin: 0;
        padding: 0;
    }

    .sources-card li {
        margin-bottom: 0.25rem;
    }

    div[data-testid="stButton"] > button {
        height: 3.2rem;
        width: 100%;
        white-space: normal;
        line-height: 1.2;
        padding: 0.55rem 0.75rem;
        border: 1px solid #7dd3fc;
        border-radius: 8px;
        background: linear-gradient(180deg, #e0f2fe 0%, #bae6fd 100%);
        color: #0f172a;
        font-weight: 700;
        box-shadow: 0 8px 18px rgba(14, 165, 233, 0.16);
    }

    div[data-testid="stButton"] > button:hover {
        border-color: #38bdf8;
        background: linear-gradient(180deg, #f0f9ff 0%, #7dd3fc 100%);
        color: #082f49;
    }

    section[data-testid="stSidebar"] {
        min-width: 22rem;
        border-right: 1px solid rgba(125, 211, 252, 0.2);
    }

    section[data-testid="stSidebar"] [data-testid="stExpander"] {
        background: rgba(30, 41, 59, 0.9);
    }

    section[data-testid="stSidebar"] .qa-analysis-grid {
        grid-template-columns: 1fr;
    }

    section[data-testid="stSidebar"] .qa-analysis-card {
        min-height: auto;
        padding: 0.75rem;
    }

    section[data-testid="stSidebar"] .qa-analysis-card h4 {
        font-size: 0.98rem;
    }

    section[data-testid="stSidebar"] .qa-analysis-body {
        font-size: 0.92rem;
    }

    section[data-testid="stSidebar"] .grounding-grid {
        grid-template-columns: 1fr;
    }

    section[data-testid="stSidebar"] .confidence-card strong {
        font-size: 1.45rem;
    }

    .attachment-summary {
        border: 1px solid rgba(125, 211, 252, 0.32);
        border-radius: 8px;
        background: rgba(14, 165, 233, 0.12);
        color: #e0f2fe;
        font-weight: 700;
        margin: 0.35rem 0 0.75rem 0;
        padding: 0.75rem 0.9rem;
    }

    .attachment-summary span {
        color: #7dd3fc;
    }

    .sidebar-context-card {
        border: 1px solid rgba(125, 211, 252, 0.26);
        border-radius: 8px;
        background: rgba(14, 165, 233, 0.1);
        color: #e0f2fe;
        margin: 0.5rem 0 0.75rem 0;
        padding: 0.75rem 0.85rem;
    }

    .sidebar-context-card strong {
        color: #7dd3fc;
    }
    </style>
    """,
    unsafe_allow_html=True
)

st.caption(
    "Select a ticket, choose a suggested QA question or write your own, then run the impact analysis."
)

col1, col2 = st.columns(2)

with col1:
    environment = st.selectbox(
        "Environment",
        ["Preprod", "Production", "Staging"]
    )

with col2:
    available_tickets = get_available_tickets()

    if available_tickets:
        ticket = st.selectbox("Ticket ID", available_tickets)
    else:
        ticket = st.text_input("Ticket ID")
        st.warning("No ticket files found in the tickets folder.")

ticket_attachments = get_ticket_attachments(ticket)
attachment_count = len(ticket_attachments)
attachment_summary = ""
parsed_attachment_count = 0
unsupported_attachment_count = 0

st.sidebar.markdown("## Ticket Context")
st.sidebar.markdown(
    f"""
    <div class="sidebar-context-card">
        <div><strong>Ticket:</strong> {html.escape(ticket)}</div>
        <div><strong>Environment:</strong> {html.escape(environment)}</div>
        <div><strong>Attachments:</strong> {attachment_count}</div>
    </div>
    """,
    unsafe_allow_html=True
)

if ticket_attachments:
    with st.sidebar.expander("📎 Attachment names"):
        for attachment in ticket_attachments:
            st.markdown(f"- `{attachment}`")

    if st.sidebar.button("Preview Attachment Data", use_container_width=True):
        with st.spinner("Reading Excel/CSV attachments..."):
            (
                attachment_summary,
                parsed_attachment_count,
                unsupported_attachment_count
            ) = build_attachment_content_summary(tuple(ticket_attachments))

        if attachment_summary:
            st.sidebar.markdown("#### 📊 Attachment Summary")
            st.sidebar.caption(
                f"Parsed tabular files: {parsed_attachment_count} | "
                f"Unsupported files: {unsupported_attachment_count}"
            )
            st.sidebar.code(attachment_summary[:3500])
        else:
            st.sidebar.info("No Excel or CSV attachment content found for this ticket.")

if (
    "attachment_summary_by_ticket" not in st.session_state
    or st.session_state.get("attachment_summary_ticket") != ticket
):
    st.session_state.attachment_summary_by_ticket = ""
    st.session_state.attachment_summary_ticket = ticket

if attachment_summary:
    st.session_state.attachment_summary_by_ticket = attachment_summary
else:
    attachment_summary = st.session_state.attachment_summary_by_ticket

if attachment_summary and not st.session_state.get("hide_attachment_summary", False):
    with st.sidebar.expander("📊 Current attachment summary", expanded=False):
        st.code(attachment_summary[:3500])

if not ticket_attachments:
    st.sidebar.info("No attachments found for this ticket.")

suggested_questions = [
    "What should I regression test?",
    "What DB columns may be affected?",
    "What hidden dependencies should I check?",
    "What are the risky areas?",
    "What validations are needed?",
    "What APIs should I verify?",
]

if "question" not in st.session_state:
    st.session_state.question = ""

st.markdown("### 💬 Suggested Questions")

for row_start in range(0, len(suggested_questions), 3):
    question_cols = st.columns(3)
    row_questions = suggested_questions[row_start:row_start + 3]

    for index, suggested_question in enumerate(row_questions):
        question_index = row_start + index

        with question_cols[index]:
            if st.button(
                suggested_question,
                key=f"suggested_question_{question_index}",
                use_container_width=True
            ):
                st.session_state.question = suggested_question

    for empty_index in range(len(row_questions), 3):
        with question_cols[empty_index]:
            st.empty()

question = st.text_area(
    "Ask your QA question",
    placeholder="Example: What should I regression test in STF-7063?",
    key="question"
)

# ---------------- BUTTON ----------------

if st.button("Analyze Impact"):

    ticket_content = ""

    try:
        ticket = ticket.strip().upper()

        with open(f"tickets/{ticket}.txt", "r", encoding="utf-8") as file:
            ticket_content = file.read()
    except:
        ticket_content = "Ticket not found."

    ticket_topic = get_ticket_topic(ticket_content)
    attachment_summary = st.session_state.get("attachment_summary_by_ticket", "")

    if ticket_attachments and not attachment_summary:
        with st.spinner("Reading Excel/CSV attachments..."):
            (
                attachment_summary,
                parsed_attachment_count,
                unsupported_attachment_count
            ) = build_attachment_content_summary(tuple(ticket_attachments))

        st.session_state.attachment_summary_by_ticket = attachment_summary

    has_historical_context = any(
        item.get("ticket") == ticket
        for item in history
    )
    confidence_score = calculate_confidence_score(
        ticket_content,
        attachment_count,
        attachment_summary,
        has_historical_context
    )
    data_sources = get_data_sources_used(
        ticket_content,
        ticket_attachments,
        attachment_summary,
        has_historical_context
    )

    # Empty question validation
    if not question.strip():
        st.warning("Please enter a question.")
        st.stop()

    prompt = f"""
    You are an AI QA investigation assistant.

    Your role is NOT to summarize tickets.

    Your role is to help QA engineers identify:
    - impacted areas
    - affected modules
    - possible database relations
    - important validations
    - risky logic dependencies

    Environment:
    {environment}

    Ticket ID:
    {ticket}

    Ticket Content:
    {ticket_content}

    Attachments Found:
    {attachment_count}

    Parsed Tabular Attachments:
    {parsed_attachment_count}

    Attachment Content Summary:
    {attachment_summary if attachment_summary else "No parsable Excel or CSV content found for this ticket."}

    User Question:
    {question}

    IMPORTANT RULES:
    - Keep answers concise and investigation-focused
    - Avoid repeating ticket details
    - Use bullet points
    - Focus on actionable QA insights
    - Infer likely DB tables/columns if applicable
    - Mention possible hidden dependencies
    - Include 3 to 6 concrete QA test scenarios when possible
    - Suggest 2 to 4 read-only SQL SELECT queries when DB checks are relevant
    - Do NOT suggest UPDATE, DELETE, INSERT, DROP, ALTER, TRUNCATE, or migration SQL
    - Add a note that table and column names must be validated before execution
    - Think like a senior QA investigator

    VALIDATION RULES:

    - If the question is unrelated to QA investigation, politely refuse.
    - If the question is unrelated to the provided ticket context, explain that the investigation should stay related to the selected ticket.
    - Do NOT answer general casual questions.
    - Only answer questions related to:
    - testing
    - regression
    - affected areas
    - business logic
    - DB impact
    - APIs
    - validations
    - dependencies
    - investigations

    Response Format:

    ## Affected Areas
    - ...

    ## Important DB Checks
    - ...

    ## Risky Dependencies
    - ...

    ## Suggested Investigation
    - ...

    ## Suggested Test Scenarios
    - ...

    ## Suggested SQL Queries
    - Purpose: ...
    ```sql
    SELECT ...
    ```

    ## Regression Focus
    - ...
    """
    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[
            {
                "role": "user",
                "content": prompt
            }
        ]
    )

    st.success("Analysis Generated Successfully")

    st.markdown("## 🧠 AI Analysis")

    ai_response = response.choices[0].message.content

    chat_entry = {
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "ticket": ticket,
        "topic": ticket_topic,
        "question": question,
        "response": ai_response,
        "confidence_score": confidence_score,
        "data_sources": data_sources
    }

    history_file = "chat_history/history.json"

    try:
        with open(history_file, "r", encoding="utf-8") as file:
            history = json.load(file)
    except:
        history = []

    history.append(chat_entry)

    with open(history_file, "w", encoding="utf-8") as file:
        json.dump(history, file, indent=4)

    render_grounding_panel(confidence_score, data_sources)
    render_ai_analysis(ai_response)

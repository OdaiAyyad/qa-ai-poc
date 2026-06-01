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
MAX_VALIDATION_ROWS = 500
VALIDATION_HISTORY_FILE = "chat_history/validation_runs.json"

CONSTRAINT_OPERATORS = [
    "equals",
    "not equals",
    "contains",
    "is not null",
    "is null",
    "greater than",
    "less than",
    "in list",
]


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


def sanitize_sql_identifier(value):
    cleaned_value = re.sub(r"[^a-zA-Z0-9_]+", "_", str(value).strip().lower())
    cleaned_value = cleaned_value.strip("_")

    return cleaned_value or "parsed_attachment"


def get_sql_value(value):
    stripped_value = str(value).strip()

    if stripped_value == "":
        return "''"

    try:
        float(stripped_value)
        return stripped_value
    except ValueError:
        return "'" + stripped_value.replace("'", "''") + "'"


def normalize_cell_value(value):
    if value is None:
        return ""

    return str(value).strip()


def parse_number(value):
    try:
        return float(str(value).strip())
    except ValueError:
        return None


def read_csv_table(file_path, attachment):
    with open(file_path, "r", encoding="utf-8-sig", newline="") as file:
        reader = csv.reader(file)
        headers = [str(header) for header in next(reader, [])]
        rows = []
        total_rows = 0

        for row in reader:
            total_rows += 1

            if len(rows) < MAX_VALIDATION_ROWS:
                rows.append(row)

    return [{
        "id": f"{attachment}::CSV",
        "label": f"{attachment} / CSV",
        "file": attachment,
        "sheet": "CSV",
        "columns": headers,
        "rows": rows,
        "total_rows": total_rows,
    }]


def read_excel_tables(file_path, attachment):
    ensure_workspace_packages()

    from openpyxl import load_workbook

    workbook = load_workbook(file_path, read_only=True, data_only=True)
    tables = []

    for sheet in workbook.worksheets:
        rows_iterator = sheet.iter_rows(values_only=True)
        headers = [str(header) if header is not None else "" for header in next(rows_iterator, [])]
        rows = []
        total_rows = 0

        for row in rows_iterator:
            total_rows += 1

            if len(rows) < MAX_VALIDATION_ROWS:
                rows.append(["" if value is None else str(value) for value in row])

        tables.append({
            "id": f"{attachment}::{sheet.title}",
            "label": f"{attachment} / {sheet.title}",
            "file": attachment,
            "sheet": sheet.title,
            "columns": headers,
            "rows": rows,
            "total_rows": total_rows,
        })

    workbook.close()
    return tables


@st.cache_data(show_spinner=False)
def parse_attachment_tables(attachments):
    tables = []
    unsupported_files = []
    parse_errors = []

    for attachment in attachments:
        file_path = os.path.join("attachments", attachment)
        extension = os.path.splitext(attachment)[1].lower()

        try:
            if extension == ".csv":
                tables.extend(read_csv_table(file_path, attachment))
            elif extension == ".xlsx":
                tables.extend(read_excel_tables(file_path, attachment))
            else:
                unsupported_files.append(attachment)
        except Exception as error:
            parse_errors.append(f"{attachment}: {error}")

    return tables, unsupported_files, parse_errors


def get_table_by_id(tables, table_id):
    for table in tables:
        if table["id"] == table_id:
            return table

    return None


def evaluate_constraint(row_value, operator, expected_value):
    actual = normalize_cell_value(row_value)
    expected = normalize_cell_value(expected_value)

    if operator == "equals":
        return actual.lower() == expected.lower()
    if operator == "not equals":
        return actual.lower() != expected.lower()
    if operator == "contains":
        return expected.lower() in actual.lower()
    if operator == "is not null":
        return actual != ""
    if operator == "is null":
        return actual == ""
    if operator == "greater than":
        actual_number = parse_number(actual)
        expected_number = parse_number(expected)
        return actual_number is not None and expected_number is not None and actual_number > expected_number
    if operator == "less than":
        actual_number = parse_number(actual)
        expected_number = parse_number(expected)
        return actual_number is not None and expected_number is not None and actual_number < expected_number
    if operator == "in list":
        expected_values = [
            item.strip().lower()
            for item in expected.split(",")
            if item.strip()
        ]
        return actual.lower() in expected_values

    return False


def validate_constraint(table, column, operator, expected_value):
    if not table or column not in table["columns"]:
        return {
            "status": "Failed",
            "checked_rows": 0,
            "passed_rows": 0,
            "failed_rows": 0,
            "sample_failures": [],
        }

    column_index = table["columns"].index(column)
    checked_rows = 0
    passed_rows = 0
    sample_failures = []

    for row_number, row in enumerate(table["rows"], start=2):
        checked_rows += 1
        row_value = row[column_index] if column_index < len(row) else ""
        passed = evaluate_constraint(row_value, operator, expected_value)

        if passed:
            passed_rows += 1
        elif len(sample_failures) < 5:
            sample_failures.append({
                "row": row_number,
                "value": normalize_cell_value(row_value),
            })

    failed_rows = checked_rows - passed_rows

    return {
        "status": "Passed" if failed_rows == 0 and checked_rows > 0 else "Failed",
        "checked_rows": checked_rows,
        "passed_rows": passed_rows,
        "failed_rows": failed_rows,
        "sample_failures": sample_failures,
    }


def generate_constraint_sql(table, column, operator, expected_value):
    table_name = sanitize_sql_identifier(f"{table['file']}_{table['sheet']}")
    column_name = sanitize_sql_identifier(column)
    expected_sql = get_sql_value(expected_value)

    if operator == "equals":
        where_clause = f"({column_name} <> {expected_sql} OR {column_name} IS NULL)"
    elif operator == "not equals":
        where_clause = f"{column_name} = {expected_sql}"
    elif operator == "contains":
        escaped_value = str(expected_value).replace("'", "''")
        where_clause = f"({column_name} NOT LIKE '%{escaped_value}%' OR {column_name} IS NULL)"
    elif operator == "is not null":
        where_clause = f"({column_name} IS NULL OR {column_name} = '')"
    elif operator == "is null":
        where_clause = f"{column_name} IS NOT NULL"
    elif operator == "greater than":
        where_clause = f"({column_name} <= {expected_sql} OR {column_name} IS NULL)"
    elif operator == "less than":
        where_clause = f"({column_name} >= {expected_sql} OR {column_name} IS NULL)"
    elif operator == "in list":
        values = [
            get_sql_value(item.strip())
            for item in str(expected_value).split(",")
            if item.strip()
        ]
        where_clause = f"{column_name} NOT IN ({', '.join(values)})"
    else:
        where_clause = "1 = 1"

    return "\n".join([
        "-- Suggested read-only validation query",
        "-- Replace table/column names with the real DB schema before execution.",
        f"SELECT *",
        f"FROM {table_name}",
        f"WHERE {where_clause};",
    ])


def suggest_constraints_for_table(table):
    suggestions = []

    for column in table.get("columns", []):
        column_lower = str(column).lower()

        if "discount" in column_lower:
            suggestions.append((column, "equals", "50"))
        elif "status" in column_lower:
            suggestions.append((column, "equals", "Accepted"))
        elif "mobile" in column_lower or column_lower.endswith("id") or "_id" in column_lower:
            suggestions.append((column, "is not null", ""))

        if len(suggestions) >= 5:
            break

    return suggestions


def read_json_file(path, fallback):
    try:
        with open(path, "r", encoding="utf-8") as file:
            return json.load(file)
    except:
        return fallback


def write_json_file(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)

    with open(path, "w", encoding="utf-8") as file:
        json.dump(data, file, indent=4, ensure_ascii=False)


def save_validation_run(run_entry):
    runs = read_json_file(VALIDATION_HISTORY_FILE, [])
    runs.append(run_entry)
    write_json_file(VALIDATION_HISTORY_FILE, runs)


def render_validation_history_sidebar():
    runs = read_json_file(VALIDATION_HISTORY_FILE, [])
    st.sidebar.markdown("## SQL History")

    if not runs:
        st.sidebar.caption("No validation runs yet.")
        return

    sorted_runs = sorted(
        runs,
        key=lambda run: parse_timestamp(run.get("timestamp", "")),
        reverse=True
    )
    grouped_runs = {}

    for run in sorted_runs:
        grouped_runs.setdefault(run.get("ticket", "Unknown Ticket"), []).append(run)

    for ticket_id, ticket_runs in list(grouped_runs.items())[:8]:
        with st.sidebar.expander(f"{ticket_id} ({len(ticket_runs)} runs)"):
            for index, run in enumerate(ticket_runs[:8], start=1):
                label = (
                    f"Run {index}: {run.get('status', 'Status')} - "
                    f"{run.get('environment', 'Env')}"
                )

                if st.button(
                    label,
                    key=f"history_{ticket_id}_{run.get('timestamp', index)}",
                    use_container_width=True
                ):
                    st.session_state.selected_history_run = run

                st.caption(format_timestamp(run.get("timestamp", "")))


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


def render_analysis_card(title, content):
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


def render_ai_analysis(response):
    sections = parse_analysis_sections(response)

    if not sections:
        st.markdown(response)
        return

    tab_config = [
        ("Impact", ["Affected Areas", "DB Checks", "Risky Dependencies"]),
        ("QA Scenarios", ["Suggested Test Scenarios", "Regression Focus"]),
        ("SQL", ["Suggested SQL Queries"]),
        ("Investigation", ["Suggested Investigation"]),
    ]
    visible_tabs = [
        (label, section_titles)
        for label, section_titles in tab_config
        if any(sections.get(section_title) for section_title in section_titles)
    ]

    if not visible_tabs:
        st.markdown(response)
        return

    tabs = st.tabs([label for label, _ in visible_tabs])

    for tab, (_, section_titles) in zip(tabs, visible_tabs):
        with tab:
            st.markdown('<div class="qa-analysis-grid">', unsafe_allow_html=True)

            for title in section_titles:
                content = sections.get(title)

                if content:
                    render_analysis_card(title, content)

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

st.sidebar.image("banner.png", use_container_width=True)
st.sidebar.title("QA SQL Validation Assistant")

# ---------------- MAIN UI ----------------

st.title("🔎 QA SQL Validation Assistant")

st.markdown(
    "Understand ticket data, define critical constraints, and generate SQL-style validation evidence."
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
        grid-template-columns: repeat(auto-fit, minmax(320px, 1fr));
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

    div[data-testid="stButton"] > button[kind="primary"] {
        height: 3.35rem;
        border: 1px solid #22d3ee;
        background: linear-gradient(180deg, #0891b2 0%, #0e7490 100%);
        color: #ffffff;
        font-size: 1.02rem;
        box-shadow: 0 12px 24px rgba(8, 145, 178, 0.28);
    }

    div[data-testid="stButton"] > button[kind="primary"]:hover {
        border-color: #67e8f9;
        background: linear-gradient(180deg, #06b6d4 0%, #0891b2 100%);
        color: #ffffff;
    }

    section[data-testid="stSidebar"] {
        min-width: 22rem;
        border-right: 1px solid rgba(125, 211, 252, 0.2);
    }

    section[data-testid="stSidebar"] [data-testid="stExpander"] {
        background: rgba(30, 41, 59, 0.9);
    }

    section[data-testid="stSidebar"] [data-testid="stExpander"] details {
        padding: 0;
    }

    section[data-testid="stSidebar"] [data-testid="stExpander"] summary {
        font-size: 0.9rem;
        line-height: 1.25;
    }

    section[data-testid="stSidebar"] [data-testid="stImage"] {
        margin-bottom: 0.4rem;
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

    .context-row {
        display: grid;
        grid-template-columns: 6.25rem 1fr;
        gap: 0.45rem;
        margin-bottom: 0.35rem;
    }

    .context-row:last-child {
        margin-bottom: 0;
    }
    </style>
    """,
    unsafe_allow_html=True
)

st.caption(
    "Simple flow: select a ticket, load its file fields, add validation checks, then run and save the SQL-style result."
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

render_validation_history_sidebar()

st.sidebar.markdown("## Current Ticket")
st.sidebar.markdown(
    f"""
    <div class="sidebar-context-card">
        <div class="context-row"><strong>Ticket</strong><span>{html.escape(ticket)}</span></div>
        <div class="context-row"><strong>Files</strong><span>{attachment_count}</span></div>
    </div>
    """,
    unsafe_allow_html=True
)

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

if not ticket_attachments:
    st.sidebar.caption("No files for this ticket.")

if (
    "constraint_ticket" not in st.session_state
    or st.session_state.constraint_ticket != ticket
):
    st.session_state.constraint_ticket = ticket
    st.session_state.parsed_tables = []
    st.session_state.validation_constraints = []
    st.session_state.last_validation_run = None

st.markdown("### 1. Load Ticket Data")

if ticket_attachments:
    st.info(
        f"{ticket} has {attachment_count} attachment(s). Load the fields to see available sheets and columns."
    )
else:
    st.warning("No attachments are available for this ticket, so file-based validation cannot run yet.")

if ticket_attachments:
    if st.button("Load Attachment Fields", use_container_width=True):
        with st.spinner("Reading attachment tables..."):
            parsed_tables, unsupported_files, parse_errors = parse_attachment_tables(
                tuple(ticket_attachments)
            )

        st.session_state.parsed_tables = parsed_tables
        st.session_state.parsed_unsupported_files = unsupported_files
        st.session_state.parsed_errors = parse_errors

    if not st.session_state.parsed_tables:
        st.caption("Nothing is loaded yet. Click the button above to start.")

parsed_tables = st.session_state.get("parsed_tables", [])

if parsed_tables:
    st.markdown("### 2. Choose What To Validate")

    overview_rows = []

    for table in parsed_tables:
        overview_rows.append({
            "File / sheet": table["label"],
            "Rows": table["total_rows"],
            "Columns": len(table["columns"]),
            "Suggested fields": ", ".join(get_interesting_columns(table["columns"])[:5]) or "-"
        })

    with st.expander("Loaded file fields", expanded=True):
        st.dataframe(overview_rows, use_container_width=True, hide_index=True)

    table_options = {
        table["label"]: table["id"]
        for table in parsed_tables
    }

    builder_col1, builder_col2 = st.columns([1.2, 0.8])

    with builder_col1:
        selected_table_label = st.selectbox(
            "Parsed file / sheet",
            list(table_options.keys())
        )
        selected_table = get_table_by_id(
            parsed_tables,
            table_options[selected_table_label]
        )
        selected_column = st.selectbox(
            "Column",
            selected_table["columns"]
        )

    with builder_col2:
        selected_operator = st.selectbox("Constraint", CONSTRAINT_OPERATORS)
        expected_value = st.text_input(
            "Expected value",
            disabled=selected_operator in ["is null", "is not null"],
            placeholder="Example: 50, Accepted, 100"
        )

    st.caption(
        f"Rows available in selected sheet: {selected_table['total_rows']}."
    )

    suggestions = suggest_constraints_for_table(selected_table)

    if suggestions:
        with st.expander("Quick constraint suggestions"):
            suggestion_cols = st.columns(min(3, len(suggestions)))

            for index, suggestion in enumerate(suggestions):
                column, operator, value = suggestion

                with suggestion_cols[index % len(suggestion_cols)]:
                    if st.button(
                        f"{column} {operator} {value}".strip(),
                        key=f"suggestion_{selected_table['id']}_{index}",
                        use_container_width=True
                    ):
                        st.session_state.validation_constraints.append({
                            "table_id": selected_table["id"],
                            "table_label": selected_table["label"],
                            "file": selected_table["file"],
                            "sheet": selected_table["sheet"],
                            "column": column,
                            "operator": operator,
                            "expected_value": value,
                        })

    add_disabled = selected_operator not in ["is null", "is not null"] and not expected_value.strip()

    if st.button(
        "Add Constraint",
        type="primary",
        use_container_width=True,
        disabled=add_disabled
    ):
        st.session_state.validation_constraints.append({
            "table_id": selected_table["id"],
            "table_label": selected_table["label"],
            "file": selected_table["file"],
            "sheet": selected_table["sheet"],
            "column": selected_column,
            "operator": selected_operator,
            "expected_value": "" if selected_operator in ["is null", "is not null"] else expected_value,
        })

constraints = st.session_state.get("validation_constraints", [])

if constraints:
    st.markdown("### 3. Run Validation")
    st.caption("These checks will be validated against the loaded file data and saved as SQL-style history.")

    for index, constraint in enumerate(constraints, start=1):
        st.markdown(
            f"{index}. `{constraint['table_label']}` | "
            f"`{constraint['column']}` **{constraint['operator']}** "
            f"`{constraint['expected_value']}`"
        )

    action_col1, action_col2 = st.columns([1, 1])

    with action_col1:
        clear_constraints = st.button("Clear Constraints", use_container_width=True)

    with action_col2:
        run_validation = st.button(
            "Run SQL Validation Check",
            type="primary",
            use_container_width=True
        )

    if clear_constraints:
        st.session_state.validation_constraints = []
        st.session_state.last_validation_run = None
        st.rerun()

    if run_validation:
        validation_results = []
        sql_queries = []

        for constraint in constraints:
            table = get_table_by_id(parsed_tables, constraint["table_id"])
            result = validate_constraint(
                table,
                constraint["column"],
                constraint["operator"],
                constraint["expected_value"]
            )
            sql_query = generate_constraint_sql(
                table,
                constraint["column"],
                constraint["operator"],
                constraint["expected_value"]
            )
            validation_results.append({
                **constraint,
                **result,
                "sql": sql_query,
            })
            sql_queries.append(sql_query)

        failed_constraints = sum(
            1 for result in validation_results if result["status"] != "Passed"
        )
        passed_constraints = len(validation_results) - failed_constraints
        run_status = "Passed" if failed_constraints == 0 else "Failed"
        run_entry = {
            "timestamp": datetime.now().isoformat(timespec="seconds"),
            "ticket": ticket,
            "environment": environment,
            "status": run_status,
            "constraints": constraints,
            "results": validation_results,
            "sql_queries": sql_queries,
            "passed_constraints": passed_constraints,
            "failed_constraints": failed_constraints,
        }

        save_validation_run(run_entry)
        st.session_state.last_validation_run = run_entry

if st.session_state.get("last_validation_run"):
    run = st.session_state.last_validation_run
    st.markdown("### 4. Review Result")
    status_method = st.success if run["status"] == "Passed" else st.error
    status_method(
        f"{run['status']}: {run['passed_constraints']} passed, "
        f"{run['failed_constraints']} failed"
    )
    result_tab, sql_tab = st.tabs(["Validation Results", "Generated SQL"])

    with result_tab:
        for result in run["results"]:
            st.markdown(
                f"**{result['status']}** - `{result['column']}` "
                f"{result['operator']} `{result['expected_value']}`"
            )
            st.caption(
                f"Checked {result['checked_rows']} rows | "
                f"Passed {result['passed_rows']} | Failed {result['failed_rows']}"
            )

            if result["sample_failures"]:
                st.write("Sample failed rows:")
                st.dataframe(result["sample_failures"], use_container_width=True)

    with sql_tab:
        for query in run["sql_queries"]:
            st.code(query, language="sql")

selected_history_run = st.session_state.get("selected_history_run")

if selected_history_run:
    with st.expander("Selected history run", expanded=False):
        st.markdown(
            f"**{selected_history_run.get('ticket', 'Ticket')}** | "
            f"{selected_history_run.get('environment', 'Env')} | "
            f"**{selected_history_run.get('status', 'Status')}**"
        )
        st.caption(format_timestamp(selected_history_run.get("timestamp", "")))
        st.write(
            f"{selected_history_run.get('passed_constraints', 0)} passed, "
            f"{selected_history_run.get('failed_constraints', 0)} failed"
        )

        for query in selected_history_run.get("sql_queries", []):
            st.code(query, language="sql")

with st.expander("Optional natural-language helper"):
    st.caption("This helper does not create project history. Official saved history is based on SQL validation runs.")

    if "question" not in st.session_state:
        st.session_state.question = ""

    question = st.text_area(
        "Ask your QA question",
        placeholder="Example: What should I regression test in STF-7063?",
        key="question"
    )

    analyze_clicked = st.button(
        "Analyze Impact",
        type="primary",
        use_container_width=True
    )

# ---------------- BUTTON ----------------

if analyze_clicked:

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

    prior_validation_runs = read_json_file(VALIDATION_HISTORY_FILE, [])
    has_historical_context = any(
        item.get("ticket") == ticket
        for item in prior_validation_runs
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

    render_grounding_panel(confidence_score, data_sources)
    render_ai_analysis(ai_response)


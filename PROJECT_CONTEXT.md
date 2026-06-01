# QA AI Investigation Assistant - Project Context

## Product Goal

Build an AI-assisted QA investigation tool focused on validating ticket impact through data, SQL checks, and environment verification.

The project started as a Streamlit + Groq QA impact-analysis POC, but the manager's desired direction is more database- and SQL-centered.

## Current Stack

- Streamlit UI
- Groq LLM
- Local Jira ticket text files in `tickets/`
- Local attachments in `attachments/`
- JSON history archive in `chat_history/history.json`
- Attachment parsing for tabular files:
  - `.xlsx` via fallback `openpyxl`
  - `.csv` via Python CSV fallback
  - pandas is attempted first, but the current local environment has a pandas/NumPy binary mismatch

## Current Features

- Ticket dropdown from files in `tickets/`
- Attachment detection by ticket ID
- Attachment content preview for Excel/CSV-like files
- AI impact analysis
- Suggested test scenarios
- Suggested read-only SQL queries
- Confidence score
- Data sources used
- Investigation history
- Sidebar ticket context
- AI output organized into tabs/cards
- File-based SQL Constraint Builder
- Read-only SQL generation from selected constraints
- Validation run history stored in `chat_history/validation_runs.json`

## New Manager Direction

The product should become more related to **DB validation and SQL execution**.

Instead of the main flow being "ask a QA question", the core workflow should become:

1. Select a ticket.
2. Read and understand attached files.
3. Display important parsed file columns/fields.
4. Let QA define critical constraints from the data.
5. Generate or run SQL checks against those constraints.
6. Validate whether the ticket passes in Preprod.
7. Later repeat/compare validation in Production.
8. Save history of executed checks and SQL results.

## Full Project Vision From Manager Discussion

The full product vision can be understood as a three-step QA intelligence and validation system.

### Step 1: Understand Business Logic And Pre-Process Data

The system should first understand the business logic from Jira tickets.

Jira tickets may include:

- plain ticket descriptions
- acceptance criteria
- business rules
- attached Excel/CSV sheets
- supporting documents
- images/screenshots

If files or sheets exist, the system should parse and inspect the data before any DB validation.

The first step should identify:

- what the ticket is changing
- what business logic must be true
- what data is included in attachments
- which columns/fields are important
- whether there are duplicate records
- whether there are missing values
- whether values look unexpected
- which constraints should be checked
- which edge cases matter most

Examples:

- If the ticket is about scholarships, detect scholarship-related fields.
- If the data has a scholarship percentage column, infer expected valid values.
- If scholarship percentage should be `100`, rows with any other value may be invalid.
- If only listed students should be affected, the attachment becomes the allowed data scope.
- If mobile/user/student IDs are present, they become key validation identifiers.

If there is no Excel/CSV data, the system should still extract possible constraints and edge cases from the Jira ticket text itself, but with lower confidence.

This step is effectively the **business logic extraction + data pre-processing** layer.

### Step 2: SQL And Database Validation

The second step is to translate extracted business logic and constraints into SQL checks.

The system should compare database output against:

- Jira business rules
- attachment data
- inferred constraints
- expected statuses
- expected discount/scholarship values
- allowed affected records
- edge cases

The goal is to verify whether the DB state matches the business logic.

Example:

- Ticket says scholarship percentage should be `100`.
- Attachment lists affected student IDs.
- SQL checks whether those students have scholarship percentage `100` in the DB.
- SQL also checks whether students outside the attachment were not affected.

This step should eventually run against:

- Preprod first
- Production later, after Preprod validation passes

The output should be evidence-based:

- SQL query
- DB result
- matched/not matched
- pass/fail status
- failed rows or unexpected records

### Step 3: Natural Language QA Assistant Over DB

The third step is the interactive AI assistant/UI layer.

QA members should be able to ask natural language questions, especially when testing an area for the first time.

The system should convert questions into safe SQL queries and run them against the selected environment.

Example:

User asks:

> Do these student IDs have scholarship percentage 100?

System should:

1. understand the requested check
2. map it to known fields/tables
3. generate a read-only SQL query
4. run it against the DB, later
5. explain the result in QA-friendly language

This layer is not only chat. It should be grounded in:

- ticket logic
- parsed attachments
- known schema/DB metadata, later
- previous validation runs
- SQL execution results

## Important Product Reframe

The app should not be positioned mainly as a generic QA chatbot.

The stronger product framing is:

**Business Logic Understanding -> Data Constraint Extraction -> SQL Validation -> Natural Language DB Investigation**

The current POC should continue moving toward that vision.

## Current POC Scope After Latest Clarification

Because there is currently no database/source-of-truth connection, the POC should **not** attempt real DB validation yet.

For now, the POC should focus on two practical steps:

1. **Business Logic And Data Understanding**
   - Read Jira ticket text.
   - Parse attached Excel/CSV files.
   - Display parsed sheets, columns, row counts, and likely critical fields.
   - Help QA identify constraints and edge cases from ticket logic and attached data.
   - Check the attachment data itself for basic issues such as missing values, unexpected values, and invalid constraints.

2. **SQL-Style Constraint Validation Without DB Execution**
   - Let QA choose parsed file/sheet, column, operator, and expected value.
   - Validate the constraint against the parsed attachment data.
   - Generate read-only SQL that represents the future DB check.
   - Save validation run history by ticket/environment/query/constraint.

The old AI question/search history is no longer the main history model. The project history should now be based on **SQL validation runs and generated queries**, not natural-language AI searches.

The optional natural-language helper can remain for support, but it should not be treated as the core workflow or main saved history.

## Latest UX Simplification

The app should feel like a small validation workflow, not a generic investigation dashboard.

Current simplified UI direction:

1. Keep the sidebar minimal.
   - Show only the current ticket and SQL history.
   - Do not show attachment previews, raw summaries, long SQL blocks, or duplicate ticket entries in the sidebar.
2. Group history by ticket ID.
   - The ticket should appear once.
   - Each saved validation attempt appears inside that ticket as Run 1, Run 2, etc.
3. Remove raw file-like summaries from the sidebar.
   - File summaries should not repeat the whole file or preview many rows.
   - After loading files, show a compact table overview in the main page: file/sheet, row count, column count, and suggested fields.
4. Keep the main page as the workflow.
   - 1. Load Ticket Data
   - 2. Data Quality Check
   - 3. Choose What To Validate
   - 4. Run Validation
   - 5. Review Result

The data quality check should run before constraint building. If duplicated full rows are found in a parsed attachment table, the app should block only that duplicated file/sheet, show duplicate samples, remove pending constraints for the blocked file/sheet, and still allow validation on other clean files/sheets under the same ticket. If every file/sheet has duplicates, the app should refuse validation until at least one clean file/sheet is available.

This is intended to make the POC easier for managers and QA members to understand quickly.

## Desired Future Workflow

### 1. Ticket And File Parsing

After selecting a ticket, the app should parse related attachments and extract:

- file names
- sheet names
- row counts
- column names
- likely critical columns
- sample values
- possible DB-related identifiers
- possible status/discount/order/student fields

Examples of critical columns:

- `student_id`
- `user_id`
- `mobile`
- `scholarship_status`
- `discount`
- `discount_amount`
- `order_id`
- `scholarship_code`
- `status`

### 2. Constraint Builder UI

Replace or reduce "Suggested Questions" and introduce a **Constraint Builder**.

The UI should guide the QA member through chained controls:

1. Select file or parsed sheet.
2. Select column from that file.
3. Enter expected constraint/value.
4. Add the constraint to a validation list.

Example:

- Column: `discount_amount`
- Constraint: must equal `100`

Other possible constraint types:

- equals
- not equals
- contains
- is not null
- is null
- greater than
- less than
- in list
- status should be `Accepted`
- count should match attachment row count

### 3. Constraint Suggestions

Instead of suggested questions, the AI/app can suggest constraints based on ticket and attachment data.

Examples:

- `scholarship_status` should be `Accepted`
- `discount_value` should equal `50`
- orders linked to listed students should be `Canceled`
- only students in the attachment should be affected
- no records outside the attachment should change

### 4. SQL-Centered Validation

The main value should be SQL checks.

The app should generate read-only SQL queries from selected constraints.

Important guardrails:

- Only generate `SELECT` queries initially.
- Do not generate or run destructive SQL:
  - `UPDATE`
  - `DELETE`
  - `INSERT`
  - `DROP`
  - `ALTER`
  - `TRUNCATE`
  - migrations
- Table and column names must be validated.
- SQL should be environment-aware:
  - Preprod first
  - Production later

Example generated SQL:

```sql
SELECT *
FROM scholarship_orders
WHERE scholarship_status = 'Accepted';
```

Example validation SQL:

```sql
SELECT student_id, scholarship_status, discount_value
FROM scholarships
WHERE student_id IN (...)
  AND scholarship_status = 'Accepted'
  AND discount_value = 50;
```

### 5. Run SQL Checks

Near-term POC:

- Generate SQL but do not connect to DB yet.
- Allow QA to copy SQL.
- Save generated SQL and constraint history.

Later:

- Connect to Preprod DB.
- Run read-only SQL queries.
- Display results as tables.
- Compare expected vs actual result.
- Mark each constraint as passed/failed.

Future Production flow:

- After Preprod validation passes, run the same checks against Production.
- Save environment comparison results.

### 6. Validation Result

The final output should answer:

- Did the ticket pass data validation?
- Which constraints passed?
- Which constraints failed?
- Which SQL queries were run?
- Which environment was checked?
- What evidence supports the result?

Possible status:

- Passed
- Failed
- Needs Investigation
- Not Enough Data

### 7. History Model Change

History should move from "question history" to **validation run history**.

Save:

- timestamp
- ticket ID
- environment
- selected file/sheet
- selected columns
- constraints
- generated SQL
- SQL execution result, later
- pass/fail status
- notes

The sidebar should show history by:

- Ticket ID
- Environment
- Validation Run

Example:

- `STF-7063`
  - `Preprod Run 1`
  - `Preprod Run 2`
  - `Production Run 1`

## Suggested Next Implementation Phase

Implement a **Constraint Builder POC** using parsed attachment data only, without DB connection.

### Phase 1: File-Based Constraint Builder

1. Parse selected ticket attachments.
2. Let user choose:
   - attachment
   - sheet/table
   - column
   - operator
   - expected value
3. Add constraint to a list.
4. Validate constraints against the parsed file data using Python.
5. Show pass/fail result.
6. Generate suggested SQL for the same constraint.
7. Save validation run history.

Status: implemented as the first SQL-centered POC flow. The app can load parsed attachment tables, let QA select file/sheet, column, operator, and expected value, validate the constraint against parsed file rows, generate read-only SQL, and save validation runs.

### Phase 2: SQL Generation

1. Use selected constraints to generate read-only SQL.
2. Show SQL in a dedicated SQL tab/card.
3. Allow copy/export.
4. Save generated SQL in history.

### Phase 3: DB Integration

1. Add DB connection config for Preprod.
2. Run read-only SQL.
3. Display SQL results.
4. Compare expected constraints vs DB results.
5. Save run result.

### Phase 4: Production Validation

1. Add Production environment connection.
2. Re-run validated Preprod checks on Production.
3. Save comparison.

## Current Important Design Decision

The core product direction is no longer just AI chat or Q&A.

The core should be:

**Ticket + Attachments -> Critical Constraints -> SQL Checks -> Environment Validation -> Saved Evidence**

## Copy-Paste Summary For New Chat

We are building a Streamlit + Groq QA AI Investigation Assistant. The project started as a ticket impact-analysis assistant with local Jira ticket files, attachment parsing, suggested test scenarios, suggested SQL, confidence score, and JSON investigation history. The manager now wants the product to become SQL/DB-validation focused. The full project vision has three steps: first, understand Jira ticket business logic and pre-process any attached files/documents to detect important fields, duplicates, unexpected values, constraints, and edge cases; second, convert those constraints into read-only SQL checks and compare DB output against the ticket logic and attachment data in Preprod, then later Production; third, provide a natural-language QA assistant where QA members can ask questions and the system converts them into safe SQL queries, runs them against the selected environment, and explains the result. The core framing is: Business Logic Understanding -> Data Constraint Extraction -> SQL Validation -> Natural Language DB Investigation. Current POC includes ticket dropdown, attachment parsing, file-based SQL Constraint Builder, read-only SQL generation, validation run history, optional AI impact analysis, and sidebar context/history. Future phases add real DB integration, schema awareness, SQL execution, environment comparison, Jira sync, and semantic search/RAG if needed.

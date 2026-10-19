# AI-Powered Personal Task Manager

A single-user task manager that accepts natural-language instructions and performs real,
validated operations against SQLite. The LLM is used **only** to choose one of five predefined
tools and supply arguments; Python validates those arguments, executes the operation, and builds
the response from the actual stored result.

The mandatory submission notebook is
[`notebooks/ai_personal_task_manager.ipynb`](notebooks/ai_personal_task_manager.ipynb).
It is a **standalone deliverable**: its code is contained in its own cells, it uses only the
Python standard library, and it runs offline in a clean directory without importing `src/`,
running `tests/`, or reading any repository file. The modular application in [`src/`](src/)
is the source of truth for behavior; the notebook is a faithful, condensed implementation of
the same design.

## Project Status

| Item | Status |
|---|---|
| Core task operations | Implemented and tested |
| Structured due dates, times, and periods | Implemented and tested; safe in-place migration |
| Bulk completion by date with confirmation | Implemented and tested |
| Transient Gemini 429/503 retries | Implemented and tested; bounded exponential backoff |
| Destructive requests ("clear all tasks") | Refused explicitly; no deletion is possible |
| SQLite persistence | Implemented and tested |
| LLM function-calling layer | Implemented; mock and real Gemini verified |
| Real provider APIs | Gemini is the only supported provider and is live-verified |
| Automated tests | **312 passed** |
| Notebook | Standalone, offline (standard library only); executed top-to-bottom in a clean directory; 41/41 inline checks pass |
| Secrets | No API keys in the repository or notebook |

The code-level default provider is `mock`, so the project and notebook run offline without an
API key. The `.env.example` file is configured for Gemini, and the interactive CLI refuses to run
with any provider other than `gemini`.

## Features

- **Create tasks** from natural language with a required title and an ISO due date.
  Relative dates such as "tomorrow", "next Saturday", and "in 3 days" are resolved using the
  explicitly configured timezone.
- **Structured due times**: exact times (`"3 PM"`, `"3:30 PM"`, `"10 AM"`, `"15:00"`) are
  normalized to 24-hour `HH:MM` and displayed in 12-hour form; approximate periods
  (`tomorrow morning`, `tomorrow evening`) are stored separately and never converted into an
  invented exact time. Titles stay independent of date/time words.
- **List pending tasks** with ID, title, due date, time or period, and status, sorted
  chronologically. Tasks without a time sort before timed tasks on the same date.
- **Schedule lookups**: "What do I have tomorrow at 10 AM?", "Show my schedule for Saturday.",
  and "What is my next task?" are answered with filtered task lists.
- **Complete a uniquely identified task**; ambiguous references trigger clarification instead
  of silently changing the wrong record.
- **Bulk-complete by date**: "Mark all tomorrow's tasks as done." first returns the matching
  tasks and IDs and asks for confirmation. Only an explicit "yes" completes those IDs; "no"
  changes nothing, and an unclear date never completes every task.
- **Retrieve task details** including ID, due date, time or period, and status.
- **Handle missing information** such as an omitted due date or an ambiguous time ("at 3")
  by asking for it.
- **Handle nonexistent and already-completed tasks** with honest, non-destructive messages.
- **Reject invalid model output** (unknown tools, malformed JSON, empty arguments, invalid
  dates/times/periods, missing bulk dates).
- **Retry transient Gemini errors**: HTTP 429/503 responses are retried with bounded exponential
  backoff (`GEMINI_MAX_RETRIES`, `GEMINI_RETRY_BASE_DELAY`). If the retries are exhausted, a
  friendly message explains that the service is temporarily unavailable and that no task changes
  were made.
- **Refuse destructive requests**: "clear/delete all tasks" is never executed. The assistant
  explains that deletion is not supported, confirms that nothing was deleted, and suggests
  marking tasks as completed instead. Deletion tools do not exist in the contract, and any
  model-invented deletion tool call is rejected before execution.
- **Fail safely** when the LLM or database fails; no fabricated success messages, including when
  a tool result cannot be parsed.
- **Persist across restarts** in SQLite, with parameterized SQL, transaction-safe writes, and
  in-place schema migration for older databases.

## Technology Stack

| Component | Choice | Reason |
|---|---|---|
| Language | Python 3.12 | Readable, strong standard library, stable Jupyter/GenAI support |
| Storage | SQLite (`sqlite3`) | Zero-setup persistence with constraints and transactions |
| LLM interface | Function calling with five JSON tool schemas | Restricts the model to predefined operations |
| Providers | Gemini (real) + mock (offline) | One supported real provider; the small `BaseLLMClient` interface keeps future adapters isolated |
| Dates and times | `datetime`, `zoneinfo`, shared `src/date_utils.py` | ISO dates, normalized 24-hour times, separate approximate periods, explicit timezone |
| Notebook | Jupyter / nbconvert | Required deliverable; executable explanations and evidence |
| Testing | pytest | Isolated temporary databases and fast, repeatable tests |
| Configuration | Environment variables + `python-dotenv` | Keeps credentials out of source control |

No web framework, ORM, vector database, or agent framework is used. The assignment calls for a
small, explainable implementation.

## Architecture Summary

```text
Natural-language user input
          |
          v
Assistant  (conversation + minimal clarification/bulk-confirmation state)
          |
          v
LLM client  (mock / Gemini)
          |
          v  structured tool call
Validation + allowlist routing
          |
          v
TaskService  (business rules, validation, OperationResult)
          |
          v
TaskRepository  (parameterized SQL, transactions)
          |
          v
SQLite tasks table
          |
          v
Response built from the actual execution result
```

Key properties:

- `TaskService` and `TaskRepository` work without any LLM.
- The model can only select `create_task`, `list_pending_tasks`, `complete_task`,
  `get_task_details`, or `complete_tasks_by_date`; anything else is rejected.
- Tool arguments are validated before a handler runs.
- User input is never executed as SQL or Python.
- Bulk completion is two-step: the tool returns candidates, and only explicit confirmation
  completes the stored IDs.
- The user-facing message comes from Python's `OperationResult`, not from free-form model text.

## Project Structure

```text
.
├── README.md
├── PMP.md
├── PROJECT_EXECUTION_LOG.md
├── requirements.txt
├── .env.example
├── .gitignore
├── notebooks/
│   └── ai_personal_task_manager.ipynb
├── src/
│   ├── __init__.py
│   ├── config.py
│   ├── date_utils.py
│   ├── database.py
│   ├── models.py
│   ├── task_repository.py
│   ├── task_service.py
│   ├── llm_client.py
│   ├── tool_schemas.py
│   ├── assistant.py
│   ├── response_formatter.py
│   └── cli.py
└── tests/
    ├── conftest.py
    ├── test_database.py
    ├── test_database_migration.py
    ├── test_date_utils.py
    ├── test_due_time.py
    ├── test_bulk_completion.py
    ├── test_retrieval.py
    ├── test_task_service.py
    ├── test_task_matching.py
    ├── test_llm_integration.py
    ├── test_assistant.py
    ├── test_error_handling.py
    └── test_llm_failures.py
```

`src/date_utils.py` centralizes time/period normalization, 12-hour display, and configured-
timezone handling. `tests/test_llm_integration.py` is an additional test module beyond the
PMP's proposed tree; the modules added for structured times, bulk completion, migration,
retrieval, and LLM failure handling are regression suites for the improvements described below.
See the progress notes at the end of `PMP.md`.

## Prerequisites

- Python **3.12** (verified with 3.12.14). The code uses standard-library features available in
  Python 3.10+.
- `pip` and the ability to create a virtual environment.
- No API key is required for the `mock` provider. Gemini requires `GOOGLE_API_KEY` in `.env`.
- Jupyter is installed through `requirements.txt`.

SQLite ships with Python; no separate database server is needed.

## Installation

```bash
# From the repository root
python3.12 -m venv .venv

# Linux / macOS
source .venv/bin/activate

# Windows PowerShell
# .venv\Scripts\Activate.ps1

python -m pip install --upgrade pip
pip install -r requirements.txt

cp .env.example .env
```

The project was developed with a local `.venv`; system Python is not modified. The environment
uses Python 3.12 because the available Python 3.14 installation lacked `ensurepip`.

## Environment Configuration

`.env` is local, is ignored by Git, and must never be committed. `.env.example` documents the
available variables without real credentials.

| Variable | Default | Purpose |
|---|---|---|
| `LLM_PROVIDER` | `mock` (code default); `gemini` in `.env.example` | `mock` or `gemini` |
| `GOOGLE_API_KEY` | unset | Required only for Gemini |
| `GEMINI_MODEL` | `gemini-3.5-flash` | Gemini model override |
| `DATABASE_PATH` | `./tasks.db` | SQLite database location |
| `TIMEZONE` | `UTC` | IANA timezone used to resolve "today"/relative dates and in the LLM prompt |
| `GEMINI_MAX_RETRIES` | `3` | Bounded retries for transient Gemini 429/503 errors |
| `GEMINI_RETRY_BASE_DELAY` | `0.5` | Base seconds for exponential backoff (`base * 2**attempt`) |
| `DEBUG` | `false` | Debug flag |

### Using Gemini

1. Install dependencies with `pip install -r requirements.txt`. The Gemini SDK
   (`google-genai`) is included in the requirements; no other provider SDK is needed.
2. Set `LLM_PROVIDER=gemini` and `GOOGLE_API_KEY` in `.env`.
3. Start the assistant with that provider.

Example `.env`:

```dotenv
LLM_PROVIDER=gemini
GOOGLE_API_KEY=your-key-here
GEMINI_MODEL=gemini-3.5-flash
TIMEZONE=Asia/Kolkata
```

> **Verification status:** Gemini was live-verified on 2026-10-19 with `gemini-3.5-flash` using
> one create-task request and one task-details request against a temporary SQLite database.
> `gemini-1.5-flash` and `gemini-2.5-flash` are no longer available to new users;
> `gemini-3.8-flash` and `gemini-3.7-flash` returned `503` high-demand errors during setup.

### Adding another provider

Gemini is the only wired-in real provider by design. The `BaseLLMClient` interface and the
shared tool schemas keep the task-management layer independent of Gemini, but switching
providers is not just an API-key change: a new adapter must implement `BaseLLMClient.chat`,
map the shared tool schemas to the SDK's function-calling format, handle that provider's errors
and retries, add configuration entries, and pass its own tests.

## Running the Notebook

The notebook is an **independent deliverable**. It needs only Python 3.10+ and the standard
library — no installation, no environment variables, no API key:

```bash
cd /any/clean/directory          # the notebook does not read repository files
jupyter notebook /path/to/ai_personal_task_manager.ipynb
```

Then select **Kernel → Restart & Run All**. It runs fully offline with a deterministic mock
client, stores tasks in a temporary SQLite database, and removes that database at the end; a
real `tasks.db` is never touched. Real Gemini integration is optional and read from the
environment (`GOOGLE_API_KEY`); the saved outputs contain no key and no live API call.

Non-interactive execution (from the repository, using the working environment):

```bash
.venv/bin/jupyter nbconvert \
  --to notebook --execute --inplace \
  --ExecutePreprocessor.timeout=600 \
  notebooks/ai_personal_task_manager.ipynb
```

The submitted notebook already contains saved outputs: 32 cells (14 code), executed top to
bottom in an empty directory with **0 errors** and **41/41 inline checks passing**.

## Usage

### Direct task operations (no LLM)

```python
from datetime import date, timedelta
from src.task_service import TaskService

service = TaskService("tasks.db")

service.create_task("Prepare the GenAI assignment", date.today() + timedelta(days=1))
service.create_task("Standup", date.today() + timedelta(days=1), due_time="10:00")
service.create_task("Call mom", date.today() + timedelta(days=1), due_period="evening")

print(service.list_pending_tasks().message)
print(service.list_pending_tasks(due_date=date.today() + timedelta(days=1)).message)
print(service.get_task_details("Standup").message)
print(service.complete_task("Standup").message)
```

### Natural-language assistant

```python
from src.assistant import create_assistant
from src.task_service import TaskService

service = TaskService("tasks.db")
assistant = create_assistant(task_service=service, llm_provider="mock")

print(assistant.process_message("Add a task to prepare for the GenAI assignment by tomorrow."))
print(assistant.process_message("Train at 3 PM on Saturday"))            # due_time 15:00
print(assistant.process_message("Add a task to call mom tomorrow morning."))  # due_period morning
print(assistant.process_message("What do I have tomorrow at 10 AM?"))
print(assistant.process_message("Show my schedule for Saturday."))
print(assistant.process_message("What is my next task?"))
print(assistant.process_message("Mark all tomorrow's tasks as done."))   # asks for confirmation
print(assistant.process_message("Yes."))                                 # completes those IDs
print(assistant.process_message("When is my train?"))
print(assistant.process_message("Complete my Python task."))             # asks which one if ambiguous
```

### Date and time input examples

| Input | Stored result |
|---|---|
| `"Add a task to train tomorrow"` | title `train`, `due_date` tomorrow, `due_time` NULL, `due_period` NULL |
| `"Train at 3 PM on Saturday"` | title `Train`, `due_time` `15:00`, displayed as 3:00 PM |
| `"Add a task to call mom tomorrow morning"` | `due_period` `morning` (no invented exact time) |
| `"Add a task to run at 15:00 tomorrow"` | `due_time` `15:00` |
| `"Add a task to train at 3 tomorrow"` | assistant asks "3 AM or 3 PM?"; nothing is created |
| `"Mark all tomorrow's tasks as done."` | candidates + IDs, then explicit "yes" to complete |

### Interactive CLI (real Gemini)

Start the REPL from the repository root:

```bash
.venv/bin/python -m src.cli
```

The CLI loads `.env`, requires `LLM_PROVIDER=gemini`, and prints the active provider, model, and
database path before accepting messages. It exits with code 2 if the provider is not Gemini; it
never falls back to mock mode. Type `exit` or `quit` to leave.

To exercise the CLI without touching the normal `tasks.db`, point it at a temporary database:

```bash
DATABASE_PATH=/tmp/task-manager-test.db .venv/bin/python -m src.cli
```

Example session:

```text
You: Create a task titled "Prepare demo" due on 2026-10-22.
Assistant: Task created: Prepare demo (due: 2026-10-22, status: pending)

You: Give me the details for the task "Prepare demo".
Assistant: Task details: Prepare demo (id: 1, due: 2026-10-22, status: pending)
```

## Testing

```bash
# Full suite
.venv/bin/python -m pytest tests/ -v

# Quiet run
.venv/bin/python -m pytest tests/ -q

# Coverage report
.venv/bin/python -m pytest tests/ --cov=src --cov-report=term-missing
```

All tests use isolated temporary SQLite databases through `tests/conftest.py`; they never touch a
real task database and never call a live LLM. The separate real-Gemini check is a manual, opt-in
verification and is not part of the pytest suite.

| Test module | Tests | Focus |
|---|---:|---|
| `test_database.py` | 15 | Schema, idempotent initialization, constraints, transactions, persistence |
| `test_database_migration.py` | 9 | In-place migration, preserved rows, period CHECK constraint |
| `test_date_utils.py` | 47 | Time/period normalization, 12-hour display, timezone handling |
| `test_due_time.py` | 38 | Structured times, NULL times, filters, ordering, mock parsing, date boundaries |
| `test_bulk_completion.py` | 39 | Bulk prepare/confirm/cancel, validation, DB errors, false success |
| `test_retrieval.py` | 10 | Schedule lookups, next task, ambiguity handling |
| `test_task_service.py` | 22 | Create/list/complete/details, validation, duplicate completion |
| `test_task_matching.py` | 12 | Exact/partial/word matching, stop words, ambiguity, case-insensitivity |
| `test_llm_integration.py` | 45 | Tool schemas, validation, mock client, tool execution, orchestration |
| `test_assistant.py` | 15 | End-to-end scenarios and clarification follow-up |
| `test_error_handling.py` | 18 | DB failures, malformed output, no false success, SQL-injection safety |
| `test_llm_failures.py` | 42 | Gemini 429/503 retries and backoff, friendly exhaustion message, destructive refusal, cancellation |
| **Total** | **312** | |

Last verified run: **312 passed** on Python 3.12.14, both in the working environment and in a
freshly created temporary virtual environment installed only from `requirements.txt`.

The notebook does **not** run this pytest suite; it contains its own compact, self-contained
checks (41/41 passing) and explicitly does not claim the project's 312 tests.

## Data Model

```sql
CREATE TABLE tasks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    due_date TEXT NOT NULL,
    due_time TEXT,
    due_period TEXT CHECK (
        due_period IS NULL OR
        due_period IN ('morning', 'afternoon', 'evening', 'night')
    ),
    status TEXT NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending', 'completed')),
    created_at TEXT NOT NULL
);
```

Dates are stored as ISO `YYYY-MM-DD` strings; exact times are stored as 24-hour `HH:MM` and
displayed in 12-hour form; approximate periods are stored separately and never converted into
exact times. `created_at` is an ISO timestamp. Indexes exist on `status`, `due_date`, and
`(due_date, due_time)`.

### Migration behaviour

`initialize_database()` is safe to run against an older database:

1. it creates the table/indexes if they are missing;
2. it inspects `PRAGMA table_info(tasks)` and adds `due_time` (nullable) and `due_period`
   (nullable with CHECK) with `ALTER TABLE` when absent;
3. it creates the `(due_date, due_time)` index;
4. it never deletes rows or resets existing data.

Existing tasks keep their data and get `due_time = NULL` / `due_period = NULL`, which is
displayed as a plain date. Migration is covered by `tests/test_database_migration.py` and the
executed notebook.

## Error Handling and Safety

- Empty/whitespace titles, invalid dates, invalid times/periods, missing arguments, mixed
  time+period, and unknown tool names are rejected.
- Completion/details references are resolved exactly, then partially, then by all significant
  words; multiple matches produce a clarification request and no mutation.
- Ambiguous times such as "at 3" produce a question instead of an invented time.
- A bulk action with no concrete date asks which date and never completes every task; bulk
  completion only changes the IDs returned by its preview and explicitly confirmed by the user.
- Nonexistent tasks return `not_found`; already-completed tasks return `already_completed`;
  a date with no matches reports that accurately.
- LLM API errors, timeouts, malformed JSON, and invalid tool output are reported clearly.
- Transient Gemini HTTP 429/503 responses are retried up to `GEMINI_MAX_RETRIES` times with
  exponential backoff. When retries are exhausted, the user sees a friendly message stating that
  the service is temporarily unavailable and that no task changes were made.
- A failed LLM request never executes a tool and never claims a task was created, completed, or
  deleted. If a tool result cannot be parsed, the assistant reports that it could not process the
  result safely instead of falling back to a success message.
- Destructive requests ("clear/delete/remove all tasks") are refused deterministically before any
  provider call; nothing is deleted. Deletion tools are absent from the contract, and any
  model-invented deletion tool call is rejected by the allowlist.
- Database exceptions become error results; the assistant never prints a success message for a
  failed read or write.
- All SQL uses placeholders. The LLM never supplies SQL.
- API keys are read from the environment; no key is present in source, tests, notebook outputs, or
  tracked project files. Error messages redact the key. The local `.env` is ignored by Git and is
  never committed.

## Known Limitations

- **Only one real provider is wired in.** Gemini is the supported live provider. Adding another
  provider requires a new SDK adapter (message and tool-schema mapping, error handling, retries,
  configuration, and tests), not just an API key.
- **Gemini model availability can change.** `gemini-1.5-flash` and `gemini-2.5-flash` are no
  longer available to new users. The configured default is `gemini-3.5-flash`, which completed
  the live create/details checks; `gemini-3.8-flash` and `gemini-3.7-flash` were temporarily
  overloaded during setup.
- **The mock is not a general NLU system.** It handles representative phrasings, common time
  formats, and a small set of relative dates. A real LLM is expected to handle broader language.
- **Title matching is lexical, not semantic.** Similar titles may be ambiguous; the system asks
  for clarification rather than guessing. There is no fuzzy or embedding-based matching.
- **Single user only.** No authentication, multi-tenancy, synchronization, or shared deployment.
- **Deletion is not supported by design.** Task records can be created, viewed, listed, and marked
  completed, but never deleted, individually or in bulk. "Clear/delete all tasks" requests are
  refused explicitly so no user or model mistake can erase data.
- **Gemini retries are bounded.** Transient 429/503 errors are retried a fixed number of times;
  long provider outages still surface as an error after the final retry.
- **Interaction state is in memory.** Clarification candidates and bulk-confirmation IDs are lost
  if the application restarts; the user must repeat the request.
- **No reminders, recurrence, calendar sync, or notifications.** These are outside the assignment
  scope.
- **Timezone is configured per installation.** `TIMEZONE` (default UTC) resolves "today" and is
  supplied to the LLM prompt; there is no per-message timezone override. An exact `due_time` is a
  wall-clock time on the due date, not a full timestamp with offset.
- **The notebook is a separate, standalone deliverable.** Its compact inline checks (41/41) cover
  the demonstration flows and are intentionally not the project's 312-test pytest suite; rerun the
  notebook to refresh its saved outputs.

## Deliverables

Two independent deliverables share the same behavior:

1. **Assignment notebook** — `notebooks/ai_personal_task_manager.ipynb`: a single self-contained
   file (standard library only, offline mock mode, its own 41 inline checks) that runs in a clean
   directory without the repository.
2. **GitHub project** — the complete repository: modular `src/` implementation, CLI, `tests/`
   (312 passing), configuration examples, and documentation. It never imports or executes the
   notebook.

- [x] `notebooks/ai_personal_task_manager.ipynb` — standalone, executed top to bottom; 41/41 checks
- [x] `src/` — modular Python implementation, including `src/cli.py` interactive REPL
- [x] `tests/` — 312 automated tests passing (working env and a fresh temporary env)
- [x] `requirements.txt` — dependencies
- [x] `README.md` — this document
- [x] `PMP.md` — project plan plus progress notes
- [x] `PROJECT_EXECUTION_LOG.md` — implementation and verification history
- [x] `.gitignore` — excludes `.env`, virtual environments, databases, caches
- [x] `.env.example` — documented variables, no real credentials

# PROJECT MANAGEMENT PLAN (PMP)
# AI-Powered Personal Task Manager — GenAI Internship Assignment

**Project Type:** GenAI Mini-Project  
**Purpose:** Internship hiring assignment  
**Primary Language:** Python  
**Final Deliverable:** Jupyter Notebook (`.ipynb`)  
**Target Completion:** 21 October 2026, 11:59 PM  
**Development Environment:** VS Code / Codex / Python / Jupyter Notebook

---

# 1. PROJECT OVERVIEW

## 1.1 Project Title

AI-Powered Personal Task Manager

## 1.2 Problem Statement

People often struggle to organize daily tasks, track pending work, and remember deadlines. The goal is to develop a GenAI-powered assistant that allows users to manage tasks using natural-language instructions.

Users should be able to create tasks, view pending tasks, mark tasks as completed, retrieve task details, and handle ambiguous requests or tasks that do not exist.

The system must be implemented in Python and submitted as a Jupyter Notebook containing explanations, implementation, sample inputs and outputs, tests, error handling, limitations, and future improvements.

## 1.3 Project Objective

Build a functional, beginner-friendly AI assistant that translates natural-language instructions into structured task-management operations.

The application must demonstrate:

1. Natural-language understanding using a large language model (LLM).
2. Structured action selection through function calling or an equivalent structured-output approach.
3. Reliable execution of task operations through Python.
4. Persistent task storage using SQLite.
5. Correct handling of missing information, ambiguous requests, invalid inputs, and nonexistent tasks.
6. Testable implementation with clear technical explanations.
7. A complete and reproducible Jupyter Notebook submission.

## 1.4 Definition of Success

The project is successful when a user can interact with the assistant using ordinary language and the application performs the correct operation, updates or reads persistent data, and returns a response based on the actual execution result.

The system must never claim that a task was created or completed unless the underlying Python operation confirms the result.

---

# 2. PROJECT SCOPE

## 2.1 In-Scope Features

### Feature F1: Create Tasks

Example:

"Add a task to prepare for the GenAI assignment by tomorrow."

Expected behaviour:

- Identify the create-task intent.
- Extract the task title.
- Resolve the relative due date using the current date and the applicable local timezone.
- Validate the title and due date.
- Insert the task into SQLite.
- Assign the initial status `pending`.
- Return a confirmation containing the title, due date, and status.

If the due date is missing, ask the user to provide it. Do not invent a due date.

### Feature F2: View Pending Tasks

Example:

"Show me all my pending tasks."

Expected behaviour:

- Retrieve tasks whose status is `pending`.
- Display their IDs, titles, and due dates.
- Return a clear message when no pending tasks exist.
- Never include completed tasks in the pending-task list.

### Feature F3: Mark Tasks as Completed

Example:

"Mark the Python assignment as completed."

Expected behaviour:

- Identify the intended task.
- Resolve the task to a unique record.
- Verify that the record exists.
- Update its status to `completed`.
- Return the actual result.

If multiple tasks match, ask the user to clarify. If the task does not exist, report that it was not found.

### Feature F4: Retrieve Task Details

Example:

"When is my GenAI assignment due?"

Expected behaviour:

- Find the requested task.
- Return its ID, title, due date, and status.
- Ask for clarification if several tasks match.
- Report a not-found result if no task matches.

### Feature F5: Handle Ambiguous and Invalid Requests

The application must handle:

- Empty or unclear task titles.
- Missing due dates.
- Invalid calendar dates.
- Ambiguous task references.
- Nonexistent tasks.
- Attempts to complete an already completed task.
- Unsupported user requests.
- Invalid or unexpected LLM output.
- LLM API failures and timeouts.
- Database errors.

### Feature F6: Notebook Documentation and Testing

The final notebook must include:

- Problem understanding and proposed approach.
- Tech stack and justification.
- Python implementation.
- Sample inputs and outputs.
- Testing of core functionality and error handling.
- Limitations and possible improvements.

## 2.2 Out-of-Scope Features

Do not implement the following in the initial version:

- User registration and authentication.
- Multi-user or multi-tenant support.
- Cloud deployment.
- Vector databases or retrieval-augmented generation.
- Multi-agent architecture.
- Calendar synchronization.
- Email or push notifications.
- Recurring tasks.
- Task sharing and collaboration.
- Complex web frontend.
- Voice input.
- Autonomous background agents.
- Payments or subscriptions.

These features are not necessary for the assignment and must not delay completion of the required functionality.

## 2.3 Scope Rule

Implement the required features completely before considering any optional enhancement. Do not add unnecessary dependencies or architectural complexity.

---

# 3. TECHNOLOGY STACK

Use the following stack unless repository inspection reveals a compelling compatibility issue.

## 3.1 Python

Purpose:

- Application logic.
- Input validation.
- Date processing.
- Task operations.
- Database integration.
- Error handling.
- Test implementation.

Use a stable Python version compatible with the chosen LLM SDK and Jupyter dependencies.

## 3.2 Large Language Model

Preferred approach: use one LLM provider that supports tool/function calling or structured outputs.

Google Gemini may be used if an appropriate model and API access are available. Otherwise, select another suitable provider with equivalent capabilities.

The LLM will:

- Interpret natural-language instructions.
- Identify the intended operation.
- Extract structured arguments.
- Select from explicitly supported actions.
- Ask for clarification when information is insufficient.

The LLM must not be responsible for directly manipulating the database or generating executable SQL.

### Provider abstraction

Keep LLM-specific logic in a dedicated module so the provider can be changed without rewriting the task-management layer.

Do not implement multiple providers unless necessary.

If an API key is unavailable during development, continue implementing and testing the core application using mocked LLM responses. Clearly document which integration tests require real API access.

## 3.3 SQLite

Use Python's built-in `sqlite3` module.

Purpose:

- Persistent task storage.
- Reliable task retrieval.
- Status updates.
- Database-backed verification.

SQLite is sufficient for this single-user assignment. Do not introduce PostgreSQL, Redis, or a vector database.

## 3.4 Date and Time Handling

Use:

- `datetime`
- `date`
- `zoneinfo` where timezone-aware timestamps are required

An optional natural-language date-parsing library may be introduced if necessary.

Requirements:

- Supply the current date to the LLM when interpreting relative dates.
- Resolve expressions such as "tomorrow" into a normalized date.
- Validate dates in Python.
- Store due dates in ISO format: `YYYY-MM-DD`.
- Use a consistent timezone policy for relative-date interpretation.
- Never silently guess a missing due date.
- Ask for clarification when a date expression has multiple plausible interpretations.

## 3.5 Jupyter Notebook

Use Jupyter Notebook as the primary interface and final deliverable.

The notebook must contain both explanatory Markdown and executable Python code.

A command-line input loop may be used inside the notebook to demonstrate the assistant. A separate frontend is not required.

## 3.6 Testing Tools

Use:

- `pytest` for automated tests.
- `unittest.mock` or equivalent for mocking the LLM.
- In-memory SQLite or a dedicated temporary test database.
- Python assertions for simple notebook demonstrations.

All core task operations must be testable without calling the real LLM.

## 3.7 Dependency Management

Create a minimal `requirements.txt` containing only the necessary runtime and development dependencies.

Possible dependencies include:

- `jupyter`
- `ipykernel`
- `pytest`
- The selected LLM SDK
- An optional date-parsing library, only if required

Do not install frameworks or libraries that are not used by the implementation.

Record the Python version and dependency versions used for successful verification.

---

# 4. SYSTEM ARCHITECTURE

## 4.1 Architectural Overview

The application will use a simple layered architecture.

User Input
    |
    v
Natural-Language Interpreter
    |
    v
Structured Action and Arguments
    |
    v
Validation and Action Router
    |
    v
Task Service
    |
    v
SQLite Database
    |
    v
Structured Execution Result
    |
    v
Assistant Response Formatter
    |
    v
User Output

## 4.2 Component Responsibilities

### A. User Interface Layer

Responsibilities:

- Accept a user message.
- Send the message to the assistant.
- Display the response.
- Support multiple interactions in one session.

The initial interface should remain simple and notebook-friendly.

### B. LLM Interpreter

Responsibilities:

- Interpret natural-language requests.
- Select an allowed action.
- Extract the required arguments.
- Identify missing information.
- Request clarification when necessary.

The model must be instructed to choose only from the supported actions.

### C. Validation and Routing Layer

Responsibilities:

- Validate the selected action.
- Check required arguments.
- Normalize task queries and dates where appropriate.
- Reject invalid or unsupported tool calls.
- Route valid requests to predefined Python functions.

Never execute arbitrary function names or code returned by the LLM.

### D. Task Service

Responsibilities:

- Create tasks.
- List pending tasks.
- Find matching tasks.
- Complete tasks.
- Retrieve task details.

This layer contains the business rules and must remain independent of the LLM provider.

### E. Repository and Database Layer

Responsibilities:

- Initialize the schema.
- Insert task records.
- Retrieve task records.
- Update task status.
- Handle database connections and transactions.

Use parameterized SQL queries. Do not construct SQL statements by concatenating user input.

### F. Response Formatter

Responsibilities:

- Convert operation results into understandable messages.
- Show task information.
- Explain errors.
- Present clarification questions.

The formatter must use actual execution results, not assumptions made by the LLM.

---

# 5. DATABASE DESIGN

## 5.1 Table: tasks

Create a table named `tasks`.

Fields:

- `id`: INTEGER PRIMARY KEY AUTOINCREMENT
- `title`: TEXT NOT NULL
- `due_date`: TEXT NOT NULL
- `status`: TEXT NOT NULL DEFAULT 'pending'
- `created_at`: TEXT NOT NULL

Add database constraints where appropriate, including a status constraint restricting values to `pending` and `completed`.

Use parameterized queries and explicit transaction handling.

## 5.2 Data Validation Rules

1. A task title must not be empty or contain only whitespace.
2. A task must have a valid due date.
3. Due dates must be stored in ISO date format.
4. Newly created tasks must start as pending.
5. Status changes must use only supported status values.
6. A task must exist before its status can be updated.
7. A task should not be marked completed twice without an informative response.
8. Similar task titles must be allowed.
9. Database failures must not produce false success messages.
10. User input must never be executed as SQL.

## 5.3 Task Matching Strategy

Implement matching in this order:

1. Exact, case-insensitive title match.
2. Normalized exact match, if useful.
3. Partial title match.
4. Optional fuzzy matching only if it can be implemented and tested reliably.

Matching outcomes:

- Zero matches: return `not_found`.
- Exactly one match: return the unique task.
- More than one match: return `ambiguous` and provide the candidate tasks.

Do not automatically choose the first partial match.

Use task IDs internally to perform updates once a unique task has been identified.

## 5.4 Structured Due-Time Extension (Phase 8)

The approved plan above stores only `due_date`. Phase 8 extends the schema without removing it:

- `due_time`: nullable TEXT, normalized 24-hour `HH:MM` (displayed as 12-hour).
- `due_period`: nullable TEXT restricted by CHECK to `morning`, `afternoon`, `evening`, `night`.
  An approximate period is never converted into an invented exact time.
- `title` remains independent of date/time words ("Train at 3 PM on Saturday" → title `Train`,
  `due_time` `15:00`).
- A task uses `due_time` or `due_period` or neither, never both.
- Chronological ordering is `due_date`, then untimed/period tasks for that date, then exact
  times in ascending order.
- `initialize_database()` migrates older databases in place: `ALTER TABLE ... ADD COLUMN` for
  the new nullable columns plus `CREATE INDEX IF NOT EXISTS` on `(due_date, due_time)`. Existing
  rows are preserved with NULL times; the database is never reset or deleted.

Additional validation rules:

11. A `due_time` must normalize to a valid 24-hour time (`HH:MM`); ambiguous input such as
    "at 3" must trigger a clarification question instead of a guessed time.
12. A `due_period` must be one of the four supported periods.
13. Provide either an exact time or a period, never both.

Additional matching/retrieval support:

- `list_pending_tasks` accepts optional `due_date` (exact; or inclusive range start with
  `end_date`), `end_date`, `due_time`, `due_period`, and `limit`.
- "What is my next task?" uses `limit=1` with chronological ordering.
- Bulk completion matches an exact date unless an inclusive `end_date` range is supplied.

---

# 6. FUNCTION-CALLING CONTRACT

Expose only the following application tools to the LLM.

## 6.1 create_task

Arguments:

- `title`: string
- `due_date`: normalized ISO date string
- `due_time`: optional exact time, `HH:MM` (Phase 8 extension)
- `due_period`: optional approximate period, one of `morning`, `afternoon`, `evening`, `night` (Phase 8 extension)

Supply `due_time` or `due_period` or neither, never both. Returns a structured result containing:

- `success`
- `status`
- `message`
- `task`, when available

## 6.2 list_pending_tasks

Arguments (all optional; Phase 8 extension adds filters):

- `due_date`: exact date, or inclusive range start together with `end_date`
- `end_date`: inclusive range end
- `due_time`: exact time filter, `HH:MM`
- `due_period`: approximate period filter
- `limit`: maximum number of tasks (used for "next task")

Returns:

- `success`
- `tasks`
- `count`
- `message`

## 6.3 complete_task

Arguments:

- `task_query`: string

Returns:

- `success`
- `status`
- `message`
- `task`, when available
- `matches`, when clarification is required

## 6.4 get_task_details

Arguments:

- `task_query`: string

Returns:

- `success`
- `status`
- `message`
- `task`, when available
- `matches`, when clarification is required

## 6.5 Tool Execution Rules

1. The model may select only the predefined tools.
2. Validate every tool argument before execution.
3. Do not permit arbitrary code execution.
4. Do not permit arbitrary SQL execution.
5. Do not claim an operation succeeded before receiving its result.
6. Do not retry a database mutation blindly after an uncertain execution outcome.
7. Do not expose API keys or internal stack traces to the user.
8. Keep errors informative but safe.
9. When the user needs to clarify a task, do not perform the mutation.
10. Return a consistent result format from every task function.
11. Never delete task records. Deletion is not part of the tool contract; requests to clear or
    delete tasks are refused explicitly (changing nothing) and model-invented deletion tools are
    rejected by the allowlist.
12. Retry transient provider errors (HTTP 429/503) a bounded number of times with exponential
    backoff; when retries are exhausted, report the failure honestly and perform no task
    mutation.

The tool-calling orchestration must support the complete provider-specific tool-call lifecycle, including returning the tool result to the model when another response is needed.

Implement only the orchestration required by the selected SDK.

## 6.6 complete_tasks_by_date (Phase 8 extension)

Arguments:

- `due_date`: required normalized ISO date string
- `end_date`: optional inclusive range end

Returns:

- `success`
- `status` (`confirmation_required`, `bulk_completed`, `not_found`, or `error`)
- `message`
- `tasks`: the matching pending tasks with IDs, before any change
- `count`

Execution rules:

- The tool only prepares candidates; it never completes a task itself.
- The assistant must present the matching tasks and IDs and ask for explicit confirmation.
- Only an explicit affirmative reply completes the stored IDs, through the existing service and
  repository layers, in a single transaction.
- A negative or unrecognized reply changes nothing (unrecognized replies re-ask).
- When no concrete date can be determined, the assistant must ask for a date and must never
  complete every pending task.
- Already-completed tasks are excluded from the candidate set.
- A date with no matches returns `not_found` with an accurate message; database failures return
  `error` and must not be reported as success.

---

# 7. CONVERSATION AND AMBIGUITY HANDLING

## 7.1 Missing Due Date

Input:

"Add a task to revise Python."

Expected behaviour:

Ask the user for a due date. Do not create the task until the required information has been supplied.

## 7.2 Ambiguous Task Reference

Suppose these records exist:

- Python assignment
- Python interview preparation

Input:

"Mark my Python task as completed."

Expected behaviour:

Return both candidates and ask which task should be completed.

Do not modify either record until the intended task is clear.

## 7.3 Nonexistent Task

Input:

"Show the details of my flight booking task."

If no matching task exists, return a helpful not-found response.

## 7.4 Already Completed Task

If the requested task is already completed, report that its status is already completed. Do not misrepresent this as a new state change.

## 7.5 Unsupported Intent

Input:

"Book me a flight to Delhi."

The assistant should explain that it supports task management only.

It must not create a flight-booking task unless the user explicitly asks to create such a task.

## 7.6 Follow-Up Clarification

If the user responds to an ambiguity question with a task title or candidate number, resolve that response against the previously presented candidate set.

Maintain only the minimal conversational state required to complete the clarification safely.

If the application is restarted or the prior clarification context is missing, ask the user to repeat the intended task.

## 7.7 LLM Failure

If the LLM request fails:

- Return a clear error message.
- Do not execute an action that was never validated.
- Preserve existing database records.
- Permit the user to retry.

Core task functions must remain usable independently of the LLM.

## 7.8 Bulk Completion Confirmation (Phase 8)

Input:

"Mark all tomorrow's tasks as done."

Expected behaviour:

1. Resolve "tomorrow" using the configured timezone and list the matching pending tasks with
   their IDs.
2. Ask the user to confirm, for example: "I found 3 pending task(s) for 2026-10-20: ... Should I
   mark all 3 as completed? (yes/no)".
3. On an explicit affirmative reply ("yes", "confirm", "ok", ...), complete exactly the listed
   IDs and report the count and titles.
4. On a negative reply ("no", "cancel", "stop", ...), change nothing and say so.
5. On an unrecognized reply, re-ask without changing anything.
6. If the date is unclear ("Mark all tasks as done."), ask which date to use; never complete
   every pending task.

A new command received while a confirmation is pending abandons the confirmation without
changing anything and is processed normally.

## 7.9 Ambiguous Time (Phase 8)

Input:

"Add a task to train at 3 tomorrow."

Expected behaviour:

Ask "Did you mean 3 AM or 3 PM?" and do not create the task until an exact time is supplied.
An approximate period ("tomorrow morning") is stored as a period, never converted into a guessed
exact time.

## 7.10 Clear/Delete Requests (Phase 9)

Input:

"Clear all my tasks."

Expected behaviour:

1. Deletion is not supported: the tool contract contains no delete tool and the assistant never
   removes task records.
2. Refuse explicitly and deterministically, before any provider call: explain that bulk deletion is
   not supported, state that nothing was deleted, and suggest marking tasks as completed instead.
3. A destructive request received while a clarification or bulk confirmation is pending abandons
   that state without changing anything and returns the same refusal.
4. A model-invented deletion tool call (`clear_all_tasks`, `delete_all_tasks`, ...) is rejected by
   argument validation as an unknown tool and must never mutate data.
5. The refusal must never claim that tasks were deleted or completed.

## 7.11 Transient Provider Errors (Phase 9)

Gemini may answer with HTTP 429 (rate limited) or HTTP 503 (service unavailable / high demand).

Expected behaviour:

1. Retry transient 429/503 responses up to `GEMINI_MAX_RETRIES` times (default 3) with exponential
   backoff: `GEMINI_RETRY_BASE_DELAY * 2**attempt` (default base 0.5 s, so 0.5 s, 1 s, 2 s).
2. Retry only transient errors; non-transient errors (for example HTTP 400) are reported
   immediately without sleeping, and timeouts are never silently retried.
3. When the retries are exhausted, display a friendly message: the service is temporarily
   unavailable, bounded retries did not succeed, no task changes were made, and the user may try
   again shortly.
4. A failed or retried LLM request never executes a tool and never reports a task operation as
   successful; API keys never appear in error messages.

---

# 8. REPOSITORY STRUCTURE

Create a clean project repository using this structure:

ai-personal-task-manager/
|
|-- README.md
|-- requirements.txt
|-- .gitignore
|-- .env.example
|-- PMP.md
|
|-- notebooks/
|   |-- ai_personal_task_manager.ipynb
|
|-- src/
|   |-- __init__.py
|   |-- config.py
|   |-- date_utils.py
|   |-- database.py
|   |-- models.py
|   |-- task_repository.py
|   |-- task_service.py
|   |-- llm_client.py
|   |-- tool_schemas.py
|   |-- assistant.py
|   |-- response_formatter.py
|   |-- cli.py
|
|-- tests/
|   |-- conftest.py
|   |-- test_database.py
|   |-- test_database_migration.py
|   |-- test_date_utils.py
|   |-- test_due_time.py
|   |-- test_bulk_completion.py
|   |-- test_retrieval.py
|   |-- test_task_service.py
|   |-- test_task_matching.py
|   |-- test_llm_integration.py
|   |-- test_assistant.py
|   |-- test_error_handling.py
|   |-- test_llm_failures.py
|
|-- .env

The `.env` file must remain local and must not be committed. Add `.env` and other secret-bearing files to `.gitignore`.

Do not create unused modules merely to match the proposed structure. Keep the architecture modular but proportionate to the assignment.

The notebook must import and demonstrate the tested implementation rather than contain a separate, inconsistent implementation of the same business logic.

If the environment requires a slightly different structure, document the change in `PMP.md` and `README.md`.

---

# 9. IMPLEMENTATION PHASES

Codex must implement the project in the following phases. Do not skip phase verification.

## PHASE 0: Repository Inspection and Planning

Tasks:

1. Inspect the current working directory and existing files.
2. Determine whether the repository already contains useful code.
3. Check Python and package-manager availability.
4. Review the assignment requirements in this PMP.
5. Identify the chosen LLM provider and whether its credentials are available.
6. Confirm the final notebook path.
7. Create or update the project plan and initial README.
8. Avoid overwriting existing work without inspection.

Deliverables:

- Repository assessment.
- Confirmed project structure.
- Dependency plan.
- Implementation checklist.

Exit criteria:

- Existing work is preserved.
- The project requirements are understood.
- The implementation sequence is documented.

## PHASE 1: Project Foundation and Configuration

Tasks:

1. Create the necessary directories and Python modules.
2. Add minimal dependencies.
3. Implement configuration loading.
4. Add `.gitignore` and `.env.example`.
5. Configure the database path.
6. Implement database initialization.
7. Create the `tasks` table.
8. Add connection and transaction management.
9. Verify that the application can initialize its database repeatedly without losing existing data.

Tests:

- Database initialization.
- Schema creation.
- Repeated initialization.
- Persistence.
- Database constraints.

Exit criteria:

- The database initializes successfully.
- Existing records are preserved.
- No secrets are committed.
- Database tests pass.

## PHASE 2: Core Task Management

Tasks:

1. Implement task creation.
2. Implement pending-task retrieval.
3. Implement task matching.
4. Implement task completion.
5. Implement task-detail retrieval.
6. Add title and date validation.
7. Add structured results.
8. Handle nonexistent and ambiguous tasks.
9. Handle already completed tasks.

Tests:

- Successful creation.
- Invalid title.
- Invalid date.
- Pending-task filtering.
- Empty task list.
- Exact title matching.
- Partial title matching.
- Ambiguous matching.
- Nonexistent task.
- Successful completion.
- Duplicate completion.
- Retrieval of due date and status.
- Database persistence.

Exit criteria:

- All core task functions work without an LLM.
- All task-service tests pass.
- No unintended database mutation occurs during validation failures.

## PHASE 3: LLM Integration

Tasks:

1. Implement the LLM client.
2. Define the supported tool schemas.
3. Add the system instructions.
4. Supply the current date and relevant timezone.
5. Implement structured tool-call handling.
6. Validate model-generated arguments.
7. Route tool calls to predefined Python functions.
8. Return tool results to the model where required.
9. Handle invalid output, API errors, and timeouts.
10. Ensure that the LLM cannot execute arbitrary functions or SQL.

Tests:

- Create-task intent.
- List-pending-tasks intent.
- Complete-task intent.
- Task-detail intent.
- Missing due date.
- Ambiguous task.
- Unsupported intent.
- Invalid tool arguments.
- Malformed model output.
- LLM timeout or failure.
- Tool execution failure.

Use mocked LLM responses for deterministic tests. Run a small number of real API integration tests only when credentials and API access are available.

Exit criteria:

- All supported intents are routed correctly.
- Tool calls are validated before execution.
- Error handling does not produce false confirmations.
- Core functionality remains independently testable.

## PHASE 4: Assistant Orchestration

Tasks:

1. Implement the main assistant entry point.
2. Connect the input layer, LLM client, task service, and response formatter.
3. Handle clarification requests.
4. Support the minimum conversational state required for follow-up clarification.
5. Keep the user interaction simple.
6. Ensure responses reflect actual execution results.
7. Add safe recovery from failures.

Tests:

- End-to-end task creation.
- End-to-end pending-task listing.
- End-to-end task completion.
- End-to-end task-detail retrieval.
- Clarification followed by a valid selection.
- Not-found response.
- Unsupported request.
- LLM failure.
- Persistence across assistant interactions.

Exit criteria:

- The assistant works through the intended user-facing entry point.
- All required workflows are demonstrable.
- No critical error causes a false success response.

## PHASE 5: Notebook Development

Create `notebooks/ai_personal_task_manager.ipynb`.

Required sections:

1. Project title and overview.
2. Problem understanding.
3. Requirements and assumptions.
4. Proposed approach and architecture.
5. Tech stack and justification.
6. Configuration and imports.
7. Database setup.
8. Core task-management implementation.
9. GenAI and function-calling integration.
10. Assistant orchestration.
11. Sample interactions.
12. Testing and error handling.
13. Limitations.
14. Future improvements.
15. Conclusion.

Tasks:

- Add explanatory Markdown before major code sections.
- Import the application implementation from `src/`.
- Demonstrate all required operations.
- Show representative error-handling cases.
- Include actual test outcomes.
- Avoid hard-coded API credentials.
- Ensure the notebook can be run in sequence.
- Keep outputs concise and readable.

Exit criteria:

- All required notebook sections are present.
- The notebook demonstrates the actual implementation.
- No secrets appear in code or saved outputs.

## PHASE 6: Verification and Final Quality Assurance

Tasks:

1. Run the complete automated test suite.
2. Fix failing tests.
3. Run tests against an isolated test database.
4. Check task persistence.
5. Verify ambiguous-request handling.
6. Verify that nonexistent tasks are not modified.
7. Verify date interpretation and validation.
8. Check LLM failure handling.
9. Restart the notebook kernel and run all cells in order.
10. Inspect notebook outputs for errors and secrets.
11. Review documentation.
12. Confirm the final deliverable exists and opens correctly.

Exit criteria:

- All required tests pass.
- All notebook cells execute successfully under documented conditions.
- Any test requiring unavailable external credentials is clearly identified rather than falsely reported as passed.
- The final notebook is ready for submission.

---

# 10. ACCEPTANCE CRITERIA

The following criteria define completion.

## Functional Acceptance Criteria

AC-01: A user can create a task using natural language.

AC-02: The assistant extracts and validates the task title and due date.

AC-03: Relative dates are interpreted consistently using the current date and timezone policy.

AC-04: The created task is persisted in SQLite.

AC-05: Newly created tasks have pending status.

AC-06: A user can view all pending tasks.

AC-07: Completed tasks are excluded from the pending-task list.

AC-08: A user can mark a uniquely identified task as completed.

AC-09: A user can retrieve a task's due date and status.

AC-10: An ambiguous task reference triggers clarification.

AC-11: A nonexistent task returns an appropriate error.

AC-12: An already completed task is handled correctly.

AC-13: Missing required information triggers a clarification request.

AC-14: Invalid model output is rejected safely.

AC-15: An LLM failure does not result in a fabricated success message.

AC-16: Unsupported requests do not trigger unintended task operations.

## Technical Acceptance Criteria

AC-17: Python is used for all core application logic.

AC-18: Task operations are implemented as testable Python functions.

AC-19: The LLM selects only predefined operations.

AC-20: SQL queries are parameterized.

AC-21: Database writes are validated and transaction-safe.

AC-22: API keys are not included in the submission.

AC-23: The notebook contains explanations and executable code.

AC-24: The notebook demonstrates the required functionality.

AC-25: Automated tests cover core operations and error handling.

AC-26: The notebook can be executed from top to bottom using the documented setup.

AC-27: The final deliverable is a valid `.ipynb` file.

---

# 11. TESTING STRATEGY

## 11.1 Unit Tests

Test the database and task-service modules independently.

Each test must use an isolated database so it cannot modify the user's real task data.

Test normal operation, validation failures, matching rules, and persistence.

## 11.2 Integration Tests

Test the interaction between the assistant, LLM adapter, routing layer, task service, and database.

Use mocked model outputs where possible.

Test the real LLM integration separately and only when credentials are available.

## 11.3 End-to-End Scenarios

Scenario A: Create a task.

Input:
"Add a task to prepare for the GenAI assignment by tomorrow."

Verify:
- The create-task operation is selected.
- The title is extracted correctly.
- The date is normalized correctly.
- The task is saved.
- The response reflects the stored record.

Scenario B: List pending tasks.

Input:
"Show me all my pending tasks."

Verify:
- Only pending records are returned.
- The count matches the result set.

Scenario C: Complete a task.

Input:
"Mark the Python assignment as completed."

Verify:
- A unique task is selected.
- Its status changes to completed.
- The update persists.

Scenario D: Retrieve details.

Input:
"When is my GenAI assignment due?"

Verify:
- The correct record is identified.
- The returned due date and status match the database.

Scenario E: Ambiguous task.

Input:
"Complete my Python task."

Verify:
- Multiple matches trigger clarification.
- No task is modified before clarification.

Scenario F: Nonexistent task.

Input:
"Show details for my nonexistent task."

Verify:
- A not-found result is returned.
- No record is inserted or updated.

## 11.4 Quality Gates

Gate 1: Database and schema tests pass.

Gate 2: All core task-service tests pass.

Gate 3: Tool schemas and LLM routing tests pass.

Gate 4: Assistant integration tests pass.

Gate 5: Notebook executes successfully.

Gate 6: Final deliverable and documentation are verified.

Do not proceed past a failed critical gate without resolving the failure or explicitly documenting an external blocker.

---

# 12. SECURITY AND RELIABILITY

Codex must follow these requirements throughout development.

1. Never hard-code API keys, passwords, or tokens.
2. Read secrets from environment variables.
3. Provide a `.env.example` with placeholder values only.
4. Ensure `.env` is ignored by Git.
5. Never print secret values in notebook output.
6. Never execute generated Python or SQL from the LLM.
7. Restrict tool execution to an explicit allowlist.
8. Validate all model-generated arguments.
9. Use parameterized SQL queries.
10. Handle database failures without false confirmations.
11. Do not automatically retry potentially completed database mutations without checking the operation outcome.
12. Keep error messages useful without exposing secrets or full internal stack traces.
13. Use a separate database for automated tests.
14. Do not delete or overwrite user data during initialization.
15. Do not introduce unnecessary permissions, services, or dependencies.

---

# 13. NOTEBOOK QUALITY REQUIREMENTS

The notebook is the primary deliverable and must be treated as a first-class project artifact.

It must:

- Have a clear title and objective.
- Explain the problem and proposed solution.
- Explain the tech stack and its justification.
- Show the architecture and workflow.
- Include readable, modular Python code.
- Demonstrate every required feature.
- Include sample requests and outputs.
- Include automated test results.
- Explain error-handling decisions.
- Discuss limitations and improvements.
- Avoid unnecessary output and excessive logs.
- Avoid embedded credentials.
- Avoid relying on undeclared state from previous manual execution.
- Run from a fresh kernel in sequential order.
- Include instructions for installing dependencies and configuring the LLM API key.

Do not replace the notebook with a README, a web application, or a Python script. Supporting Python modules are allowed, but the final submission must include the requested notebook.

---

# 14. DOCUMENTATION REQUIREMENTS

## README.md

Include:

- Project overview.
- Features.
- Technology stack.
- Architecture summary.
- Prerequisites.
- Installation instructions.
- Environment configuration.
- Notebook execution instructions.
- Testing instructions.
- Known limitations.

## PMP.md

Maintain the project plan and update it when meaningful implementation decisions change.

Record:

- Current phase.
- Completed milestones.
- Test status.
- Known issues.
- Remaining work.
- Any deviation from the approved scope.

## Execution Log

Maintain a concise `PROJECT_EXECUTION_LOG.md`.

For each development phase, record:

- Work completed.
- Files created or modified.
- Tests executed.
- Test results.
- Problems encountered.
- Fixes applied.
- Remaining issues.
- Next phase.

Do not record tests as successful unless they were actually executed.

---

# 15. DEVELOPMENT RULES FOR CODEX

Codex must follow these operating rules.

## Rule 1: Inspect Before Modifying

Inspect the repository before creating or replacing files. Preserve useful existing code.

## Rule 2: Work Incrementally

Implement one phase at a time. Do not generate the entire project in a single unverified change.

## Rule 3: Verify Every Phase

Run the relevant tests and checks before declaring a phase complete.

## Rule 4: Keep the Design Simple

Prefer standard Python libraries and a small number of dependencies.

Do not add frameworks, databases, services, or abstractions without a clear requirement.

## Rule 5: Separate Business Logic from the LLM

Task functions must work independently of the LLM.

## Rule 6: Avoid Fake Implementations

Do not replace real functionality with hard-coded sample outputs.

Mocking is permitted in tests, but the actual application must execute real task operations.

## Rule 7: Handle Failures Honestly

If an API key is unavailable, document the limitation and continue with mock-based tests. Never claim that real LLM integration has been verified when it has not.

## Rule 8: Preserve Data

Do not delete an existing database or reset task data as part of ordinary application initialization.

## Rule 9: Keep Documentation Accurate

Update the README, PMP, and execution log when relevant.

## Rule 10: Do Not Overbuild

Prioritize the assignment's requirements over optional enhancements.

## Rule 11: Ensure Reproducibility

The project must be runnable using documented setup instructions.

## Rule 12: Report Completion Precisely

At the end of each phase, report:

- What was implemented.
- Which files were changed.
- Which tests were run.
- Which tests passed or failed.
- Any remaining blockers.
- Whether the phase acceptance criteria are satisfied.
- The recommended next step.

---

# 16. FINAL DELIVERABLES

The final repository must contain:

1. `notebooks/ai_personal_task_manager.ipynb` — mandatory submission.
2. `src/` — modular Python implementation.
3. `tests/` — automated tests.
4. `requirements.txt` — required dependencies.
5. `README.md` — setup and usage instructions.
6. `PMP.md` — approved project plan and progress.
7. `PROJECT_EXECUTION_LOG.md` — implementation and verification history.
8. `.gitignore` — prevents committing secrets and generated files.
9. `.env.example` — documents the required environment variables without real credentials.

The actual `.env` file and any real API keys must not be included in the submitted repository or notebook.

---

# 17. FINAL DEFINITION OF DONE

The project is complete only when:

- All five required behaviour categories are supported: creation, pending-task listing, completion, task-detail retrieval, and ambiguous/nonexistent-task handling.
- The task-management logic is implemented in Python.
- SQLite persistence is verified.
- GenAI function calling or an equivalent structured-action approach is integrated.
- Model outputs are validated before execution.
- Core operations have automated tests.
- Error handling has been tested.
- The notebook contains all required sections.
- The notebook runs sequentially under the documented setup.
- API credentials and other secrets are absent from the submission.
- The README and execution log are accurate.
- The final `.ipynb` file exists and is ready to submit.
- Any remaining external dependency or limitation is clearly disclosed.

# 18. STARTING INSTRUCTION

Begin with Phase 0: inspect the existing workspace and repository. Then implement the phases sequentially.

Do not stop after producing a plan or sample code. Continue through implementation, testing, notebook preparation, and final verification, subject to available tools and credentials.

Do not claim completion until the Definition of Done has been verified.

Prioritize correctness, simplicity, reproducibility, and the ability of the project owner to explain every important design decision during the internship evaluation.

---

# 19. PROJECT PROGRESS NOTES

**Last updated:** 2026-10-19

These notes record implementation progress without changing the approved requirements above.

## Current Phase

Phase 12 — Finalized both independent deliverables. The assignment notebook is now a single
self-contained file (standard library only, offline mock mode, its own 41-check inline suite,
temporary SQLite storage, optional Gemini via environment credentials) that runs in an empty
directory without `src/`, `tests/`, or any repository file. The modular project is unchanged and
verified with 312 passing tests in both the working environment and a fresh temporary
environment. No live API calls; nothing committed.

## Completed Milestones

- **Phase 0:** Repository inspection, Python 3.12 virtual environment, structure, initial
  documentation, Git initialization.
- **Phase 1:** Configuration, SQLite schema/connections/transactions, models, repository, service,
  isolated test fixtures.
- **Phase 2:** Create, pending list, complete, and details operations with validation, matching,
  ambiguity, and honest error results.
- **Phase 3:** Four function-calling schemas, provider clients (mock/Gemini/OpenAI/Anthropic;
  the unused OpenAI/Anthropic clients were removed in Phase 10), system prompt, allowlist tool
  execution, assistant orchestration, clarification state.
- **Phase 4:** End-to-end assistant scenarios and clarification follow-up tests, including
  persistence and failure recovery.
- **Phase 5:** Fifteen-section executed notebook importing the tested `src/` implementation, plus
  `README.md`.
- **Phase 6:** Full-suite verification, fresh notebook execution, secret scan, deliverable audit.
- **Phase 7:** Added `src/cli.py` interactive REPL; migrated the Gemini adapter to the installed
  `google-genai` SDK; live-verified one create and one details request against a temporary SQLite
  database with `gemini-3.5-flash`; 126 tests still passing.
- **Phase 8:** Added `due_time` (24-hour `HH:MM`) and `due_period`
  (morning/afternoon/evening/night) with safe in-place migration of existing databases; exact
  times normalized and displayed in 12-hour form; approximate periods never converted into
  guessed times; ambiguous times ("at 3") now ask for AM/PM; titles kept free of date/time words;
  `list_pending_tasks` gained date/time/period/limit filters for schedule and "next task"
  queries; new validated `complete_tasks_by_date` tool implements a prepare → confirm → complete
  workflow that never mass-completes without a concrete date and explicit confirmation;
  the assistant gained a bulk-confirmation state; five regression test modules added (migration,
  date utilities, due time, bulk completion, retrieval); notebook, README, PMP, and execution log
  updated; **270 tests passing**; no live Gemini calls were made in this phase (offline tool-schema
  conversion was verified with a fake key).
- **Phase 9:** Added bounded retry handling for transient Gemini HTTP 429/503 responses with
  exponential backoff (`GEMINI_MAX_RETRIES`, `GEMINI_RETRY_BASE_DELAY`) and a friendly message when
  retries are exhausted; transient text-only errors are recognized, while non-transient errors and
  timeouts are never silently retried. Hardened the no-false-success guarantees: a failed LLM
  request executes no tool, and an unparseable tool result can no longer fall back to a
  success-sounding message. "Clear/delete all tasks" is now handled explicitly: the assistant
  refuses deterministically before any provider call (also from pending clarification/confirmation
  states), the mock refuses as well, the system prompt forbids claiming deletion, and
  model-invented deletion tools are rejected by the allowlist. Added `tests/test_llm_failures.py`
  (42 tests); notebook, README, PMP, and execution log updated; **312 tests passing**; no live API
  calls were made (all retry checks stub the SDK call offline).
- **Phase 10:** Simplified provider support. Removed the unused `OpenAILLMClient` and
  `AnthropicLLMClient` implementations (about 180 lines), their factory branches, configuration
  (`OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `OPENAI_MODEL`, `ANTHROPIC_MODEL`), commented dependency
  entries, and provider-specific documentation. `LLM_PROVIDER` now accepts only `gemini` (real) and
  `mock` (offline); startup validation, the CLI guard, Gemini tool calling, bounded retries, and
  key redaction are unchanged. The small `BaseLLMClient` interface and shared tool schemas remain
  for future extensibility. Notebook and docs updated; **312 tests passing**; no live API calls
  were made.
- **Phase 11:** Final repository cleanup and GitHub readiness. Removed the unused, empty Python
  3.14 environment (`.venv-314`) and regenerable caches (`.pytest_cache`, `__pycache__`);
  hardened `.gitignore` (env variants with a `.env.example` exception, coverage artifacts,
  logs/temp files, generic SQLite sidecars) while keeping every required source and test file;
  sanitized local absolute paths from the execution log; preserved `tasks.db`, `.env`, `.venv`,
  and the notebook; **312 tests passing**; notebook executed top-to-bottom; no live API calls.
- **Phase 12:** Finalized the two independent deliverables. The assignment notebook was rewritten
  as a single self-contained file: standard library only, no `src/` imports, no `tests/`
  execution, no repository files required, temporary SQLite storage, offline mock demonstrations
  and stubbed error simulations clearly separated from the optional live Gemini section (key read
  from the environment only), and its own compact suite that ends with **41/41 notebook checks
  passing**. It was executed top to bottom in an empty temporary directory (32 cells, 14 code,
  0 errors) and the executed file is the submitted deliverable. The modular project was preserved
  and re-verified: **312 tests passing** in the working environment and in a fresh temporary
  virtual environment installed only from `requirements.txt`; CLI starts offline with a fake key
  (exit 0) and refuses mock mode by design (exit 2); config validation, Git ignore rules, and
  secret scans all pass; `tasks.db` untouched; no live API calls; no commits.

## Test Status

- Command: `.venv/bin/python -m pytest tests/ -q --color=no`
- Result: **312 passed, 0 failed** (Python 3.12.14)
- Modules: 15 database, 9 migration, 47 date utilities, 38 due time, 39 bulk completion,
  10 retrieval, 22 task service, 12 matching, 45 LLM integration, 15 assistant, 18 error handling,
  42 LLM failure handling (Gemini retries, destructive refusal, cancellation).
- The executed notebook runs the same suite and prints the actual result (312 passed).
- Real Gemini integration was **verified live** on 2026-10-19 with `gemini-3.5-flash`: one
  create-task request and one task-details request against a temporary SQLite database, both
  successful. Phases 8–10 made **no live API calls**; the Gemini tool-schema conversion and the
  retry/backoff behaviour were verified offline with a stubbed SDK client and a fake key.
  Gemini is the only supported real provider.

## Known Issues and Limitations

- Gemini is the only supported real provider. Switching providers later requires a new SDK
  adapter (message/tool-schema mapping, error handling and retries, configuration, and tests),
  not just an API key.
- Gemini model availability changed during setup: `gemini-1.5-flash` and `gemini-2.5-flash` are
  unavailable to new users; `gemini-3.8-flash` and `gemini-3.7-flash` returned HTTP 503
  (high demand); `gemini-3.5-flash` is configured and verified.
- The deterministic mock handles representative phrases and a limited set of relative dates; it is
  not a general natural-language parser.
- Task matching is lexical (exact, partial, all significant words), not semantic/fuzzy.
- Single-user, local application only; no authentication, synchronization, reminders, recurrence,
  or notifications.
- Clarification and bulk-confirmation state are in memory and do not survive a restart.
- Timezone is explicitly configured (`TIMEZONE`, default UTC) and used for resolving "today" and
  relative dates as well as the LLM prompt; there is no per-message timezone override.
- Exact `due_time` values are wall-clock times on the due date in the configured timezone, not
  full timestamps with UTC offsets.
- The mock parser handles representative time formats and relative expressions, but one date (or
  one date range) per bulk request; it is not a general natural-language parser.
- Deletion is not supported by design: task records can be created, viewed, listed, and marked
  completed, but never deleted. "Clear/delete all tasks" requests are refused explicitly.
- Gemini retries for transient 429/503 errors are bounded (`GEMINI_MAX_RETRIES`, default 3). A
  prolonged provider outage still surfaces as a friendly error after the final retry, and no task
  changes are made.

## Deviations from the Proposed Structure

- `tests/test_llm_integration.py` is an additional test module that consolidates provider,
  tool-validation, tool-execution, and orchestration tests.
- `src/date_utils.py` centralizes time/period normalization, 12-hour display, and timezone
  handling so the repository, service, tool validation, mock client, and formatters agree.
- `tests/test_database_migration.py`, `tests/test_date_utils.py`, `tests/test_due_time.py`,
  `tests/test_bulk_completion.py`, and `tests/test_retrieval.py` are regression suites added in
  Phase 8.
- `tests/test_llm_failures.py` is a regression suite added in Phase 9 for Gemini retries,
  destructive-operation safety, and cancellation.
- The provider layer supports only Gemini and the offline mock (Phase 10); the `BaseLLMClient`
  interface remains as the extension point for a future adapter.
- The local environment uses Python 3.12 because the available Python 3.14 lacked `ensurepip`.
- The code-level default provider is `mock`; `.env.example` is configured for Gemini, and the CLI
  refuses to start with any provider other than `gemini`. No API key is committed.
- `.env` and `.env.example` document `TIMEZONE=UTC` explicitly instead of relying on an
  undocumented default.
- The notebook forces mock mode so it runs reproducibly without credentials.
- The Gemini adapter uses the current `google-genai` SDK rather than the deprecated
  `google-generativeai` package.
- `src/cli.py` is an additional interactive entry point beyond the notebook; the notebook remains
  the mandatory deliverable.

## Remaining Work

No required implementation or documentation work remains. Optional follow-up: implement a new
provider adapter behind `BaseLLMClient` if one is needed later, including its tool-schema mapping,
error/retry handling, configuration, and tests. No inactive provider integration is maintained.

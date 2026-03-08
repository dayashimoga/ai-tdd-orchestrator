# AI TDD Orchestrator: Issue Resolution & Troubleshooting Log

> **Purpose**: This document tracks every significant bug, execution anomaly, and pipeline failure encountered during the development and operation of the AI TDD Orchestrator. Each entry contains the exact symptoms observed in CI/local logs, a detailed root-cause analysis, the specific code-level fix applied, and the files modified. Refer to this log when investigating identical or similar behavior patterns in the orchestration pipeline.

---

## Table of Contents
1. [TDD Loop Premature Exit](#1-tdd-loop-premature-exit)
2. [Unseen PyTest Coverage Failures](#2-unseen-pytest-coverage-failures)
3. [Slow Context Generation on Re-Runs](#3-slow-context-generation-on-re-runs)
4. [Inaccurate Code Fixing / Hallucinated Variables](#4-inaccurate-code-fixing--hallucinated-variables)
5. [Missing Token Analytics for Cloud LLMs](#5-missing-token-analytics-for-cloud-llms)
6. [Repository Git State Pollution](#6-repository-git-state-pollution)
7. [Pipeline Crash: Remote Origin Already Exists](#7-pipeline-crash-remote-origin-already-exists)
8. [TDD Loop Fails with ModuleNotFoundError](#8-tdd-loop-fails-with-modulenotfounderror)
9. [Per-Task Retry Cap and Dependency Caching](#9-per-task-retry-cap-and-dependency-caching)
10. [Stable Discovery Cache Key](#10-stable-discovery-cache-key)
11. [Stale Feedback on Failures](#11-stale-feedback-on-failures)
12. [Auto-Create conftest.py for Clean Imports](#12-auto-create-conftestpy-for-clean-imports)
13. [Quieter Pytest Output](#13-quieter-pytest-output)
14. [Reset Dep Cache on Rollback](#14-reset-dep-cache-on-rollback)
15. [LLM Embeds English Prose in Code Files](#15-llm-embeds-english-prose-in-code-files)
16. [LLM Generates Incorrect Import Paths](#16-llm-generates-incorrect-import-paths)
17. [Identical Failures Across All Retry Iterations](#17-identical-failures-across-all-retry-iterations)

---

## 1. TDD Loop Premature Exit

| Field | Detail |
|-------|--------|
| **Symptom** | When operating on a cloned/existing project repository, the Orchestrator runs a single Engineer task generation, fails PyTest validation, and exits printing `ALL TASKS COMPLETE`. The `project_tasks.md` is empty or missing. |
| **Log Signature** | `🎉 ALL TASKS COMPLETE AND TESTS PASS. TDD PIPELINE FINISHED.` — after only 1 iteration |
| **Affected Environment** | GitHub Actions CI with `PROJECT_TYPE=existing` |

**Root Cause (4-step chain)**:
1. When the target repo was cloned (`PROJECT_TYPE=existing`), `setup_target_repository()` skipped configuring `user.name` and `user.email`.
2. `save_rollback_point()` called `git commit -m "pre-iteration snapshot"`, which **failed silently** because Git requires an author identity.
3. When PyTest failed, `rollback_if_worse()` executed `git reset --hard <hash>`. Since the snapshot commit was never created, it rolled back past the `project_tasks.md` creation commit, **wiping it from disk**.
4. The outer loop re-read `project_tasks.md`, found zero `- [ ]` checkboxes, and gracefully terminated.

**Resolution** (`ai_pipeline.py`):
- Modified `setup_target_repository()` to **unconditionally** run `git config user.name ai-orchestrator` and `git config user.email actions@github.com` after any Clone or Init operation.
- Strengthened `save_rollback_point()` to use `check=False` to prevent crashes while ensuring the snapshot is actually committed.

---

## 2. Unseen PyTest Coverage Failures

| Field | Detail |
|-------|--------|
| **Symptom** | Pipeline reports "Test Validated", commits, and pushes to GitHub. GitHub Actions then fails the build with `FAIL Required test coverage of 90% not reached`. |
| **Log Signature** | `FAIL Required test coverage of 90% not reached. Total coverage: 85%` |
| **Affected Environment** | GitHub Actions CI only (not caught locally by the orchestrator) |

**Root Cause**: The orchestrator treated a Pytest exit code of 0 (tests passed) as full success, ignoring `pytest-cov`'s separate exit code for coverage threshold violations.

**Resolution** (`ai_pipeline.py::extract_test_failures`):
- Integrated native coverage enforcement: scrapes output for `Required test coverage of 90% not reached`.
- Dynamically parses the `pytest-cov` table for the `Missing` column.
- Constructs a precise feedback prompt: *"Your code works, but lines 45-50 are missing test coverage. Write PyTest fixtures to hit these branches."*

---

## 3. Slow Context Generation on Re-Runs

| Field | Detail |
|-------|--------|
| **Symptom** | `repo_map.py` consumes 10-30s per TDD iteration on larger projects, causing extreme execution delays. |
| **Log Signature** | Long pauses between `[Engineer] Executing Task:` and LLM generation start |
| **Affected Environment** | Large repositories (>50 files) |

**Root Cause**: The pipeline rebuilt the full AST structure by parsing every file on disk during every single TDD loop iteration.

**Resolution** (`scripts/repo_map.py`):
- Implemented `mtime`-based AST caching with `.repo_map_cache.json`.
- Files unchanged since last parse are loaded from cache instantly.
- Added `setUp` teardown in tests to clear `_AST_CACHE` between test runs to prevent state bleeding.

---

## 4. Inaccurate Code Fixing / Hallucinated Variables

| Field | Detail |
|-------|--------|
| **Symptom** | On retry, the LLM "guesses" how to fix errors, often hallucinating variable names from test files not in its context window. |
| **Log Signature** | `NameError: name 'expected_result' is not defined` — where `expected_result` exists in the test file but was never shown to the LLM |
| **Affected Environment** | All retry iterations |

**Root Cause**: The source code of failing `test_*.py` files was not injected into the retry prompt until `retry_count == 2`, leaving the model blind to the actual assertion logic.

**Resolution** (`ai_pipeline.py::run_tdd_loop`):
- Retry prompts now inject the raw string contents of all `test_*.py` files immediately on `retry_count == 1`.
- **[Sprint 3 Enhancement]**: Retry prompts now also include all source `.py` files (not just tests) so the LLM sees both the code it generated AND the tests that failed.

---

## 5. Missing Token Analytics for Cloud LLMs

| Field | Detail |
|-------|--------|
| **Symptom** | Execution logs lack visibility into API costs and token consumption during streaming generations. |
| **Log Signature** | No token usage info after LLM responses |
| **Affected Providers** | Groq, Cerebras, OpenAI, Anthropic, Gemini, Ollama |

**Root Cause**: The `iter_lines()` HTTP stream parsers only collected text chunks, ignoring usage statistics blocks at the end of SSE streams.

**Resolution** (`scripts/llm_router.py`):

| Provider | Extraction Method |
|----------|------------------|
| **Groq / Cerebras / OpenAI** | Injected `stream_options: {"include_usage": True}`, parsed final `usage` block |
| **Anthropic** | Extracted `input_tokens` / `output_tokens` from response JSON |
| **Gemini** | Parsed `usageMetadata` from stream chunks (`promptTokenCount`, `candidatesTokenCount`) |
| **Ollama** | Captured `prompt_eval_count` / `eval_count` from the `done: true` chunk |

Output format: `📊 [TOKEN USAGE] Prompt: X | Generated: Y | Total: Z`

---

## 6. Repository Git State Pollution

| Field | Detail |
|-------|--------|
| **Symptom** | `git status` shows leftover artifacts from execution loops dirtying the working tree. |
| **Log Signature** | `modified: out.txt`, `modified: .repo_map_cache.json` in `git status --short` |

**Root Cause**: Pipeline cache files and debug logs were not excluded from version control.

**Resolution** (`.gitignore`):
- Added exclusions for `out*.txt`, `.ast_cache/`, `.repo_map_cache.json`, `*.log`, `pytest_out*.txt`.

---

## 7. Pipeline Crash: Remote Origin Already Exists

| Field | Detail |
|-------|--------|
| **Symptom** | When the GitHub API returns `422` (repo already exists) and the pipeline falls back to cloning, it immediately crashes with `git remote add origin` exit code 3. |
| **Log Signature** | `subprocess.CalledProcessError: Command '['git', 'remote', 'add', 'origin', '...']' returned non-zero exit status 3` |
| **Affected Environment** | GitHub Actions with existing `temp_api` repository |

**Root Cause**: A Python indentation error caused `git init`, workflow templating, and `git remote add origin` to execute **outside** the `else` branch (new project path), meaning they also ran on cloned repos where `origin` was already set by `git clone`.

**Resolution** (`ai_pipeline.py::setup_target_repository`):
- Re-scoped all new-project initialization logic (`git init`, `git remote add origin`, CI workflow template) strictly inside the `else` branch.
- Moved Git Author configuration to the unconditional tail of the function so both paths (new and existing) set the author identity.

---

## 8. TDD Loop Fails with ModuleNotFoundError

| Field | Detail |
|-------|--------|
| **Symptom** | Every TDD iteration fails with `ModuleNotFoundError: No module named 'flask'`. All 5-15 retries hit the same error. |
| **Log Signature** | `E   ModuleNotFoundError: No module named 'flask'` followed by `ℹ️ No requirements.txt found in project` |
| **Affected Environment** | All CI runs generating Flask/FastAPI/Django projects |

**Root Cause**: `run_pytest_validation()` executed `pytest` directly without ever running `pip install -r requirements.txt`. Even when the Engineer correctly generated a `requirements.txt`, the pipeline never installed it.

**Resolution** (`ai_pipeline.py`):
- **New function**: `_install_project_dependencies()` auto-detects and installs `requirements.txt` before every pytest run.
- **MD5 hash caching**: Dependencies are only reinstalled when `requirements.txt` content changes, saving ~5-10s per retry.
- **Engineer prompt**: Added `CRITICAL` instruction requiring `requirements.txt` generation, with a concrete example in the few-shot template.
- **Error extraction**: Added `ModuleNotFoundError` detection in `extract_test_failures()` that extracts missing module names and feeds explicit guidance: *"You MUST generate a requirements.txt containing these packages."*

---

## 9. Per-Task Retry Cap and Dependency Caching

| Field | Detail |
|-------|--------|
| **Symptom** | A single stuck task consumes all iterations, leaving no budget for other tasks. Dependencies are redundantly reinstalled on every retry. |
| **Configuration** | `MAX_TDD_ITERATIONS=15`, `MAX_RETRIES_PER_TASK=5` |

**Resolution** (`ai_pipeline.py`):
- **Increased iterations**: `MAX_TDD_ITERATIONS` changed from 5 → 15 (configurable via env var).
- **Per-task cap**: If a task fails 5 consecutive retries, it is **skipped** and the orchestrator moves to the next pending `- [ ]` task.
- **Dep hash caching**: `_deps_installed_hash` stores an MD5 of `requirements.txt` to skip redundant `pip install` calls.

---

## 10. Stable Discovery Cache Key

| Field | Detail |
|-------|--------|
| **Symptom** | The file-discovery LLM call fires on every retry, wasting ~2-5s per iteration even though the same task is being retried. |
| **Log Signature** | `🔍 Inspecting Repo Map to determine context window...` appears on every retry |

**Root Cause**: The discovery cache key was `task_description[:80]`, which changes on every retry because the prompt gains error-context text (e.g., `"FIX PREVIOUS BUG..."`).

**Resolution** (`ai_pipeline.py::execute_task`):
- Changed cache key to `(base_task or task_description)[:80]` where `base_task` is the original task name, stable across all retries.
- Added `base_task` parameter to `execute_task()` function signature.

---

## 11. Stale Feedback on Failures

| Field | Detail |
|-------|--------|
| **Symptom** | After the first failure, subsequent retry prompts show outdated error messages from the 1st attempt instead of the latest errors. |

**Root Cause**: The line `current_feedback = feedback if not current_feedback else current_feedback` preserved the first failure's feedback and discarded all subsequent ones.

**Resolution** (`ai_pipeline.py::run_tdd_loop`):
- Changed to `current_feedback = feedback` — always update to the latest test output.

---

## 12. Auto-Create conftest.py for Clean Imports

| Field | Detail |
|-------|--------|
| **Symptom** | Tests fail with `ImportError` because `your_project/` isn't on `sys.path`. The LLM generates `from your_project.app import app`. |
| **Log Signature** | `ImportError: cannot import name 'app' from 'your_project.app'` |

**Root Cause**: `your_project/` is a directory, not an installed Python package. Pytest can't resolve imports like `from your_project.app import app` without path manipulation.

**Resolution** (`ai_pipeline.py::run_tdd_loop`):
- After code generation, auto-create `your_project/conftest.py` with:
  ```python
  import sys, os
  sys.path.insert(0, os.path.dirname(__file__))
  ```
- This ensures pytest adds `your_project/` to `sys.path` at collection time.

---

## 13. Quieter Pytest Output

| Field | Detail |
|-------|--------|
| **Symptom** | Verbose pytest headers and progress bars bloat the feedback string, consuming LLM token budget when sent back as error context. |

**Resolution** (`ai_pipeline.py::detect_test_command`):
- Added `--no-header` and `-q` flags to all pytest commands.
- Reduces feedback token consumption by ~40%, leaving more context budget for actual error information.

---

## 14. Reset Dep Cache on Rollback

| Field | Detail |
|-------|--------|
| **Symptom** | After rolling back, `requirements.txt` may have changed but dependencies are not reinstalled because the hash cache still matches the old content. |

**Resolution** (`ai_pipeline.py::rollback_if_worse`):
- Added `_deps_installed_hash = ""` reset inside the rollback function to force a fresh install check on the next pytest run.

---

## 15. LLM Embeds English Prose in Code Files

| Field | Detail |
|-------|--------|
| **Symptom** | Generated `.py` files contain plain English sentences like *"This setup provides a basic structure for a project with tasks, an initialization file..."* causing `SyntaxError: invalid syntax`. |
| **Log Signature** | `SyntaxError: invalid syntax` on lines containing English sentences |
| **Severity** | **Critical** — blocks ALL test validation for the entire project |

**Root Cause**: Small LLMs (3B-7B parameter models) often append conversational explanations after code blocks. The `parse_and_write_files()` function extracted code from ```` ``` ```` blocks but some explanatory text leaked through when the LLM placed it outside the backticks but inside the `--- FILE:` delimiter boundaries.

**Resolution** (`ai_pipeline.py`):
- **New function**: `_sanitize_generated_code(content, file_path)` post-processes every generated file:
  - Detects lines that look like conversational English prose (long strings with no code characters like `=`, `(`, `)`, `:`, `import`, etc.) and **strips them** from `.py` files.
  - Preserves comments (lines starting with `#`), docstrings (`"""`/`'''`), and all non-Python files.
- **Engineer prompt**: Added `CRITICAL` instruction: *"Do NOT include any explanations, descriptions, or English prose inside code files. Every line in a .py file must be valid Python syntax."*

---

## 16. LLM Generates Incorrect Import Paths

| Field | Detail |
|-------|--------|
| **Symptom** | Generated test files use `from your_project.app import app` instead of `from app import app`, causing `ImportError`. |
| **Log Signature** | `ImportError: cannot import name 'add_task' from 'your_project.project_tasks'` |
| **Severity** | **Critical** — prevents test discovery entirely |

**Root Cause**: The LLM interprets the `your_project/` directory path as a Python package path and generates absolute imports using it as a prefix. Since `your_project` is a working directory, not an installed package, these imports fail.

**Resolution** (`ai_pipeline.py::_sanitize_generated_code`):
- Auto-rewrites `from your_project.X import` → `from X import` via regex substitution.
- Auto-rewrites `import your_project.X` → `import X`.
- **Engineer prompt**: Added `CRITICAL` instruction: *"Do NOT use 'from your_project.X import' — use 'from X import' instead. The project root is already on sys.path."*

---

## 17. Identical Failures Across All Retry Iterations

| Field | Detail |
|-------|--------|
| **Symptom** | All 15 retry iterations produce **identical broken code** with the same errors. The LLM never learns from its previous attempts. |
| **Log Signature** | Same `ImportError` or `SyntaxError` appears on iteration 1, 5, 10, and 15 |
| **Severity** | **Critical** — renders the entire retry mechanism useless |

**Root Cause (2-part)**:
1. `rollback_if_worse()` executed `git reset --hard` + `git clean -fd`, **erasing all AI-generated files**. The next iteration started from a completely blank project state.
2. The retry prompt only contained the error text and test file contents — it did **not** include the source code the LLM had generated. With no memory of its previous output, the LLM regenerated identical broken code every time.

**Resolution** (`ai_pipeline.py::run_tdd_loop`):
- **Before rollback**: The retry logic now scans `your_project/` and captures the **full text of all source `.py` files** (not just test files) into `source_files_context`.
- **Retry prompts**: All retry tiers (1, 2, 3+) now inject both `source_files_context` and `test_files_context` as:
  ```
  HERE IS YOUR PREVIOUS BROKEN CODE (fix it, don't regenerate from scratch):
  --- SOURCE FILE: your_project/app.py ---
  [full source code]
  --- TEST FILE: your_project/tests/test_app.py ---
  [full test code]
  ```
- **Retry 3+**: Includes conversation memory of all previous attempts with the instruction: *"Try a COMPLETELY DIFFERENT approach. Do NOT repeat previous mistakes."*
- Each retry prompt reinforces the three critical rules: no prose in code, correct import paths, generate `requirements.txt`.

---

## Quick Reference: Configuration Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `MAX_TDD_ITERATIONS` | `15` | Maximum outer loop iterations before pipeline gives up |
| `MAX_RETRIES_PER_TASK` | `5` | Max consecutive retries on one task before skipping |
| `LLM_PROVIDER` | `auto` | LLM provider selection (`auto`, `groq`, `cerebras`, `ollama`, etc.) |
| `OLLAMA_NUM_CTX` | `8192` | Context window size for Ollama models |
| `GIT_TIMEOUT` | `120` | Seconds before git commands are killed |
| `PROJECT_TYPE` | `new` | `new` = create repo, `existing` = clone existing |
| `TARGET_REPO` | (empty) | GitHub repo path (e.g., `user/repo-name`) |

## Quick Reference: Test Coverage

| Metric | Value |
|--------|-------|
| **Total Tests** | 281 |
| **Pass Rate** | 100% |
| **Coverage** | 90.77% |
| **Coverage Threshold** | 90% |

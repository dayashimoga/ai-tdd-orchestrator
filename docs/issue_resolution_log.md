# AI TDD Orchestrator: Issue Resolution & Troubleshooting Log

This document tracks significant bugs, execution anomalies, and pipeline failures encountered during the development and usage of the orchestrator. It outlines the root causes and the specific mitigation strategies implemented to ensure those issues do not occur again. 

Refer to this log when investigating identical or similar behavior patterns in the orchestration pipeline.

---

## 1. TDD Loop Premature Exit ("ALL TASKS COMPLETE" after 1 iteration)
**Symptom**: When operating on an imported/existing project repository, the Orchestrator would run a single Engineer task generation, fail PyTest validation, and suddenly exit printing `ALL TASKS COMPLETE`. The `project_tasks.md` would be completely empty or missing.  
**Root Cause**:
- When the target repo was cloned (`PROJECT_TYPE=existing`), the script did not configure `user.name` and `user.email`. 
- When the pipeline called `save_rollback_point()` to save the initial `project_tasks.md` state prior to the Engineer writing code, the `git commit -m` failed silently because Git requires an author identity.
- When PyTest failed, `rollback_if_worse()` executed `git reset --hard` to revert the repository back to the *previous* commit hash. Since the pre-iteration snapshot was never created, it rolled back past the creation of `project_tasks.md`, wiping it from the disk.
- The outer loop observed zero pending `- [ ]` checkboxes and gracefully terminated.
**Resolution**:
- Modified `ai_pipeline.py::setup_target_repository()` to unconditionally set `git config user.name ai-orchestrator` and `git config user.email actions@github.com` immediately after any Clone or Init commands.
- Strengthened `save_rollback_point()` to aggressively fail if the snapshot commit cannot be formed.

---

## 2. Unseen PyTest Coverage Failures ("Passes Locally, Fails in CI")
**Symptom**: The AI Pipeline would successfully report "Test Validated", commit the code, and push to GitHub, only for GitHub Actions to fail the CI build because test coverage was below 90%.  
**Root Cause**: The orchestrator interpreted a clean zero-error Pytest exit as a full success, ignoring `pytest-cov` exit code 5 (coverage threshold not met).  
**Resolution**:
- Integrated Internal Coverage Enforcement into `ai_pipeline.py::extract_test_failures`. 
- The Orchestrator now natively scrapes the `pytest-cov` output for `Required test coverage of 90% not reached`.
- It dynamically parses the coverage table for the `Missing` column lines and explicitly constructs a new prompt for the Engineer Agent: *"Your code works, but lines 45-50 are missing test coverage. Write PyTest fixtures to hit these branches."*

---

## 3. Slow Context Generation on Re-Runs (Large Repositories)
**Symptom**: Generating the `repo_map.py` architecture string consumed massive amounts of time during every step of the TDD loop on larger projects, causing extreme execution delays.  
**Root Cause**: The pipeline rebuilt the AST structure and parsed code references repeatedly for every single file on disk during every loop.  
**Resolution**:
- Implemented `mtime`-based AST caching in `scripts/repo_map.py`.
- Generates a local `.repo_map_cache.json` which hashes file modification timestamps against parsed AST data. Unchanged files are bypassed automatically.
- Added a `setUp` teardown method to clear `_AST_CACHE` between Pytest executions to avoid variable bleeding across tests.

---

## 4. Inaccurate Code Fixing / Hallucinated Variables
**Symptom**: On the first Pytest failure, the LLM engineer would "guess" how to fix the error based purely on the traceback text, often hallucinating variables from test files that were not loaded into its context window.  
**Root Cause**: The source code for newly created integration tests wasn't explicitly injected until `retry_count == 2`, depriving the model of the raw assertion logic context.  
**Resolution**:
- Enhanced the Retry Logic context window. The agent now dynamically loads the raw string contents of any failing `test_*.py` file immediately on `retry_count == 1`.

---

## 5. Missing Token Analytics for Cloud LLMs
**Symptom**: Execution logs lacked visibility into API costs and token consumption during streaming generations.  
**Root Cause**: The `iter_lines()` HTTP stream parsers were solely focused on text chunks, ignoring usage statistics blocks typically served at the end of SSE streams.  
**Resolution**:
- Injected `stream_options: {"include_usage": True}` for OpenAI-compatible providers.
- Configured log parsers in `llm_router.py` to intercept `usageMetadata` (Gemini), `usage` (Anthropic, Groq, Cerebras, OpenAI), and `eval_count` (Ollama) from the terminal line sequences.
- Structured CLI outputs to display `[TOKEN USAGE] Prompt: X | Generated: Y | Total: Z` after generation sequences.

---

## 6. Repository Git State Logging Pollution
**Symptom**: `git status` commands showed leftover artifacts from execution loops modifying tracked changes.  
**Root Cause**: Pipeline cache files and debug pipes were not tracked natively.  
**Resolution**:
- Modified `.gitignore` to explicitly ban `out*.txt`, `.ast_cache/`, and `.repo_map_cache.json`.

---

## 7. Pipeline Crash: "Remote Origin Already Exists" on Fallback
**Symptom**: If the user's GitHub API token lacked repository creation permissions (triggering the `422` or `403` fallback to existing project detection), the Orchestrator threw `Command '['git', 'remote', 'add', 'origin']' returned non-zero exit status 3.` and crashed the `ai_pipeline.py --manual` run.
**Root Cause**: A Python indentation logic error caused the pipeline to execute `git init` and `git remote add origin` on the newly cloned fallback directory. A cloned repository natively establishes `origin`, causing the `git remote add` step to immediately crash.
**Resolution**:
- Re-scoped `setup_target_repository()` inside `ai_pipeline.py`.
- Ensured GitHub CI workflow templating, `git init`, and `git remote add origin` strictly remain inside the `else` logic branch (used exclusively for instantiating net-new projects).
- Migrated the Git Author configuration (`user.name`/`user.email`) to the unconditional execution tail of the function, ensuring both cloned and newly-generated repositories successfully support subsequent auto-commits for state rollback management.

---

## 8. TDD Loop Fails with "ModuleNotFoundError" for Generated Dependencies
**Symptom**: The AI Engineer generates Flask/FastAPI/Django code, but every TDD iteration fails with `ModuleNotFoundError: No module named 'flask'`. All 5 retry loops hit the same error, and the code is never validated.
**Root Cause**: The `run_pytest_validation()` function executed `pytest` directly without ever installing the project's generated `requirements.txt`. Even when the Engineer correctly generated a `requirements.txt`, the pipeline never ran `pip install -r requirements.txt`.
**Resolution**:
- Added `_install_project_dependencies()` function that auto-detects and installs `requirements.txt` from the generated project directory before every pytest validation run.
- Enhanced the Engineer Agent prompt to explicitly require generating a `requirements.txt` file with all third-party dependencies, with a concrete example in the few-shot template.
- Added `ModuleNotFoundError` detection in `extract_test_failures()` that extracts the missing module names and feeds explicit guidance back to the LLM: *"You MUST generate a requirements.txt containing these packages."*

---

## 9. Efficiency: Per-Task Retry Cap and Dependency Caching
**Symptom**: A single stuck task would consume all 5 TDD iterations, leaving no budget for other tasks. Dependencies were redundantly reinstalled on every retry even when `requirements.txt` hadn't changed.
**Resolution**:
- Increased `MAX_TDD_ITERATIONS` from 5 → 15 (configurable via env var).
- Added `MAX_RETRIES_PER_TASK=5` cap. If a task fails 5 consecutive retries, it is skipped and the orchestrator moves to the next pending task.
- Added MD5 hash caching for `requirements.txt` — dependencies are only reinstalled when the file content changes, saving ~5-10s per retry iteration.

---

## 10. Optimization: Stable Discovery Cache Key
**Problem:** The file-discovery LLM call used `task_description[:80]` as cache key, which changes on every retry (because the prompt gains error context). Result: the discovery cache was never reused on retries.
**Fix:** Changed to use `base_task` (the original task name, stable across retries) as the cache key, saving 1 LLM round-trip (~2-5s) per retry.

---

## 11. Accuracy: Always Use Latest Feedback on Failure
**Problem:** `current_feedback = feedback if not current_feedback else current_feedback` discarded the 2nd+ failure's feedback if `current_feedback` was already set. The LLM saw stale errors.
**Fix:** Changed to always update: `current_feedback = feedback`.

---

## 12. Accuracy: Auto-Create conftest.py for Clean Imports
**Problem:** Tests failed with `ImportError` because `your_project/` wasn't on `sys.path`. The LLM generated `from your_project.app import app` which only works if `your_project` is an installed package.
**Fix:** Auto-create `your_project/conftest.py` with `sys.path.insert(0, os.path.dirname(__file__))` after code generation, ensuring pytest can resolve project modules.

---

## 13. Speed: Quieter Pytest Output
**Problem:** Verbose pytest headers/progress consumed token budget when sent back to the LLM as error feedback.
**Fix:** Added `--no-header -q` flags to pytest commands, reducing feedback size by ~40%.

---

## 14. Efficiency: Reset Dep Cache on Rollback
**Problem:** After `git reset --hard`, `requirements.txt` may have changed but the installer skipped re-install due to stale hash.
**Fix:** Reset `_deps_installed_hash = ""` inside `rollback_if_worse()` to force re-evaluation.

# Project Status & Tracking

## Completed (V1 Release)
- ✅ **Base Pipeline:** Git differential scanning & LLM prompt formulation (`scripts/ai_pipeline.py`).
- ✅ **GitHub Actions:** CI workflow enforcing <90% test coverage and <8/10 python lint scores.
- ✅ **Toolchain Integration:** Pre-installed `pylint`, `eslint`, `golint`.
- ✅ **Hardware Intelligence:** Dynamic RAM/VRAM detection (`scripts/select_model.py`) to prevent runner OOM errors.
- ✅ **Model Selection:** Integrated `qwen2.5-coder` architecture (3b to 32b) over basic HTTP `requests` instead of bulky `transformers`.
- [x] **Local Execution:** Implemented Docker Compose and `run-local.sh` orchestration layer.
- [x] **Security Scanners:** Embedded `bandit` (Python), `njsscan` (JS), and `gosec` (Go) reports into the LLM context.
- [x] **Inline Annotation:** API hook inside `ai_generate()` mapping LLM line outputs directly to GitHub PR review lines.
- [x] **Multi-File Generation Engine:** Dynamically transforms LLM delimited output into complex multi-folder frontend/backend scaffolds.
- [x] **Full-Stack Linters:** CI Pipeline explicitly runs `htmlhint`, `stylelint`, `eslint`, `njsscan`, `gosec`, `pylint`, and `bandit` seamlessly.
- [x] **Local Execution:** Implemented Docker Compose and `run-local.sh` orchestration layer.
- [x] **Security Scanners:** Embedded `bandit` (Python), `njsscan` (JS), and `gosec` (Go) reports into the LLM context.
- [x] **Inline Annotation:** API hook inside `ai_generate()` mapping LLM line outputs directly to GitHub PR review lines.
- [x] **Multi-File Generation Engine:** Dynamically transforms LLM delimited output into complex multi-folder frontend/backend scaffolds.
- [x] **Full-Stack Linters:** CI Pipeline explicitly runs `htmlhint`, `stylelint`, `eslint`, `njsscan`, `gosec`, `pylint`, and `bandit` seamlessly.
- [x] **Multi-Agent Workflow:** Cleanly decoupled `ai_pipeline.py` into single-responsibility agents: "The Planner" (Checklist Analysis) and "The Engineer" (Autonomous Fixing), executing a relentless TDD cycle.
- ✅ **Dynamic Target Repositories:** Orchestrator can seamlessly clone existing remote projects or create brand-new GitHub repositories via PyGithub depending on `PROJECT_TYPE` inputs.
- ✅ **Streaming Execution Observability:** Added real-time chunk streaming on Ollama HTTP queries so developers can watch generation live in CI runner logs, preventing blind-hang scenarios.
- ✅ **Isolated Ephemeral Test Suites:** Enhanced `run-tests.sh` and `run-tests.ps1` to rapidly spin up and tear down `.test_venv` wrappers specifically to enforce >90% test coverage without cross-polluting runner environments.
- ✅ **Context Window Optimization (Repo Map):** AST-based `scripts/repo_map.py` extracts compressed structural outlines of Python files (class names, function signatures, docstrings). The Engineer Agent uses a two-step discovery prompt to load only necessary files, preventing token overflow on large projects.
- ✅ **CI Matrix Speedups:** Refactored `ai-review.yml` to use `actions/cache` for pip and `.test_venv` dependencies. Split lint/complexity checks into a parallel `quality-gates` matrix job, cutting CI runtimes in half.
- ✅ **Autonomous GitHub Issue Resolver:** New `issue-resolver.yml` workflow triggers on `issues: [opened]` events. The `--issue` CLI flag causes `ai_pipeline.py` to read the issue, branch, TDD-fix it, and automatically open a Pull Request using PyGithub.
- ✅ **Human-in-the-Loop PR Chat:** New `pr-chat.yml` workflow listens for `@ai-hint` comments on PRs. When the TDD loop is stuck after 5 iterations, it posts a help request comment. User replies with `@ai-hint` guidance, which resumes the pipeline via `--resume-with-hint`.
- ✅ **Visual Quality Assurance via VLMs:** `scripts/visual_qa.py` screenshots generated HTML files using Playwright/Selenium and submits them to an Ollama Vision LLM (e.g., `llava`) for aesthetic assessment. Failed visual checks are fed back to the Engineer for CSS fixes.

## Completed (V3 Release)
- ✅ **A. Performance Optimizations:** Consolidated imports, deduplicated file-parsing into shared `parse_and_write_files()`, added `GIT_TIMEOUT=120s` to all subprocess calls, fixed `sys.executable` for pytest, configurable `NUM_CTX` via env var.
- ✅ **B. Code Quality Fixes:** Added type hints to all functions, `get_github_client()` helper, `mask_secret()` for log safety, `safe_path()` with `realpath` sandboxing, ANSI-stripping `truncate_feedback()`.
- ✅ **C. Future Enhancements:** `save_rollback_point()` / `rollback_if_worse()` automatically reverts AI changes if tests get worse. Smart error truncation (last 50 lines).
- ✅ **D. GPU Platform Intelligence:** New `scripts/gpu_platform.py` auto-detects 11+ platforms (Colab, Kaggle, Lightning, etc.) with **automatic health-check failover**.
- ✅ **E. CI Caching & Speed:** `run-tests.sh` and `run-tests.ps1` preserve cached venvs. `ai-review.yml` skips Ollama model download if already cached.
- ✅ **F. Full Coverage:** Achieved **116 tests with >90% code coverage** and 100% pass rate.

## Pending (Immediate Backlog)
- [ ] Implement Rust support (`cargo clippy`, `cargo sec`).
- [ ] Implement Java/C# support (`checkstyle`).
- [ ] Enhance inline review GitHub Action permissions scope to support cross-fork PR annotations cleanly.

## Further Enhancements (V2 Planning)
### 1. Context File Uploads
Allow developers to prefix a `context:` annotation in `prompt.txt` or a PR Description to point the LLM at specifically hosted API Docs, OpenAPI Swaggers, or Architectural diagrams to inform its code generation.

### 2. Web UI for Local Execution
Create a lightweight React dashboard mapped to `localhost:8080` in `docker-compose.yml` to visually see the AI stream its thoughts and fixes instead of tailing terminal logs.

# Project Status & Tracking

## Completed (V1 Release)
- ✅ **Base Pipeline:** Git differential scanning & LLM prompt formulation (`scripts/ai_pipeline.py`).
- ✅ **GitHub Actions:** CI workflow enforcing <90% test coverage and <8/10 python lint scores.
- ✅ **Toolchain Integration:** Pre-installed `pylint`, `eslint`, `golint`.
- ✅ **Hardware Intelligence:** Dynamic RAM/VRAM detection (`scripts/select_model.py`) to prevent runner OOM errors.
- ✅ **Model Selection:** Integrated `qwen2.5-coder` architecture (3b to 32b) over basic HTTP `requests`.
- ✅ **Local Execution:** Implemented Docker Compose and `run-local.sh` orchestration layer.
- ✅ **Security Scanners:** Embedded `bandit` (Python), `njsscan` (JS), and `gosec` (Go) reports.
- ✅ **Inline Annotation:** API hook mapping LLM line outputs directly to GitHub PR review lines.
- ✅ **Multi-File Generation Engine:** Dynamically transforms LLM delimited output into multi-folder scaffolds.
- ✅ **Full-Stack Linters:** CI Pipeline runs `htmlhint`, `stylelint`, `eslint`, `njsscan`, `gosec`, `pylint`, and `bandit`.

## Completed (V2 Release)
- ✅ **Dynamic Target Repositories:** Clone existing or create new GitHub repositories via PyGithub.
- ✅ **Streaming Execution Observability:** Real-time chunk streaming on Ollama HTTP queries.
- ✅ **Isolated Ephemeral Test Suites:** Rapid spin up/tear down of `.test_venv` wrappers.
- ✅ **Context Window Optimization (Repo Map):** AST-based `scripts/repo_map.py` with two-step discovery prompt.
- ✅ **CI Matrix Speedups:** `actions/cache` for pip and `.test_venv` dependencies, parallel quality-gates matrix.
- ✅ **Intelligent Hardware Router:** Seamless failover between Colab → Kaggle → Local Ollama.
- ✅ **Interactive PR Chat:** Engineers can tag `@ai-hint` on PRs.
- ✅ **Self-Correction TDD Loop:** Pytest traceback auto-retry loop.
- ✅ **Persistent Requirement Context:** `docs/requirements.md` persists the original product goal.
- ✅ **Robust Regex Extraction:** Strips conversational fluff and markdown fences.

## Completed (V3 Release)
- ✅ **Autonomous GitHub Issue Resolver:** `issue-resolver.yml` creates branches, fixes bugs, and opens PRs.
- ✅ **Human-in-the-Loop PR Chat:** `pr-chat.yml` + `--resume-with-hint` workflow.
- ✅ **Visual Quality Assurance via VLMs:** Playwright/Selenium screenshots + `llava` aesthetic assessment.
- ✅ **Performance Optimizations:** Consolidated imports, `GIT_TIMEOUT=120s`, shared `parse_and_write_files()`.
- ✅ **Code Quality Fixes:** Type hints, `get_github_client()`, `mask_secret()`, `safe_path()`.
- ✅ **Auto-Rollback:** `save_rollback_point()` / `rollback_if_worse()` for regression prevention.
- ✅ **GPU Platform Intelligence:** 11+ platform auto-detection with health-check failover.

## Completed (V4 Release — Current)

### Performance Optimizations
- ✅ **O(n) String Accumulation:** Replaced `+=` with `list.append()` + `join()` in streaming.
- ✅ **Repo Map Caching:** Cached across TDD retry iterations (skips rebuild on bug-fix retries).
- ✅ **Discovery Prompt Caching:** LLM file-discovery results cached across retries.
- ✅ **Preserved CI Venvs:** `run-tests.sh`/`.ps1` no longer destroy cached `.test_venv`.
- ✅ **Parallel GPU Health Checks:** `ThreadPoolExecutor` pings all platforms simultaneously.
- ✅ **Upgraded CI Caching:** All `actions/cache@v3` → `@v4` (ZSTD compression).
- ✅ **npm Global Cache:** Dedicated npm cache step in CI pipeline.
- ✅ **Context Manager Fix:** All `open()` calls use proper `with` statements.

### New Features
- ✅ **External LLM Provider Router:** `scripts/llm_router.py` supports Ollama, OpenAI, Anthropic, Google Gemini via `LLM_PROVIDER` env var.
- ✅ **RAG Context Engine:** `scripts/rag_engine.py` indexes `docs/reference/` and injects relevant chunks into engineer prompts (zero external deps, TF-IDF similarity).
- ✅ **`--dry-run` CLI Flag:** Preview pipeline behavior without generating code or pushing.
- ✅ **`--index-docs` CLI Flag:** Manually re-index RAG reference documents.
- ✅ **Elapsed Time Tracking:** Each TDD iteration prints wall-clock time.
- ✅ **Auto-Generated Run Summary:** `docs/run_summary.md` with coverage, pass rate, and task status.
- ✅ **Configurable Max Iterations:** `MAX_TDD_ITERATIONS` env var (default: 5).
- ✅ **Slack/Discord Webhooks:** Set `WEBHOOK_URL` for pipeline notifications.
- ✅ **GPU Cost Tracking:** `estimate_gpu_cost()` for paid platforms.
- ✅ **JS/TS AST Support:** Regex-based structural extraction in `repo_map.py`.
- ✅ **Auto-Detect Test Framework:** Detects `pytest`, `jest`, `go test`, or `cargo test` from project files.
- ✅ **144 Tests, >90% Coverage:** Full test suite covering all new modules.

## Pending (Backlog)
- [ ] Implement Rust support (`cargo clippy`, `cargo sec`).
- [ ] Implement Java/C# support (`checkstyle`).
- [ ] Enhance inline review permissions for cross-fork PR annotations.
- [ ] Upgrade RAG engine to ChromaDB/FAISS for larger document sets.
- [ ] Add MCP (Model Context Protocol) for dynamic tool calling.
- [ ] Web UI for local execution (React dashboard on `localhost:8080`).

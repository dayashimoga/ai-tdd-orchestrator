# Comprehensive Requirements Document

## 1. Introduction
The AI TDD Orchestrator is an autonomous CI/CD and local development tool that generates, tests, and iteratively fixes code using entirely free, offline-capable local LLMs. It supports intelligent routing to free GPU compute platforms for accelerated inference.

## 2. Functional Requirements

### 2.1 Repository Bootstrap & Project Targeting
- **FR1:** If `PROJECT_TYPE=new`, the system generates a fresh codebase and creates a private GitHub repository via PyGithub.
- **FR1a:** If `PROJECT_TYPE=existing`, the system clones the designated `TARGET_REPO` to inject fixes directly.

### 2.2 Intelligent Model Selection
- **FR2:** The system detects host RAM and GPU VRAM via `scripts/select_model.py`.
- **FR3:** Based on the memory profile, dynamically pulls an appropriately sized Ollama model (3b–32b).

### 2.3 TDD Orchestration Loop
- **FR4:** The Planner Agent generates a task checklist from a prompt or issue description.
- **FR5:** The Engineer Agent iterates over each task, generating code and tests.
- **FR6:** After each iteration, `pytest` with coverage is run. Failing tests are fed back to the Engineer for up to `max_iterations` retry attempts.
- **FR6a:** The system uses `truncate_feedback()` to strip ANSI codes and limit error output to the last 50 lines, preventing context overflow.

### 2.4 Context Window Optimization (Repo Map)
- **FR7:** Python AST parsing (`scripts/repo_map.py`) generates a compressed structural map (class names, function signatures, docstrings).
- **FR8:** A two-step discovery prompt asks the LLM which specific files it needs in full before loading them, reducing token usage by ~90%.

### 2.5 Inline Review Annotations
- **FR9:** The system posts autonomous code suggestions directly on affected lines via GitHub PR Review Comments using the standard `GITHUB_TOKEN`.

### 2.6 Real-time Streaming Observability
- **FR10:** HTTP response chunks from Ollama are streamed to `sys.stdout` in real-time, preventing CI/CD jobs from silently hanging.

### 2.7 Autonomous GitHub Issue Resolution
- **FR11:** The `--issue` CLI flag reads `ISSUE_NUMBER`, `ISSUE_TITLE`, and `ISSUE_BODY`, creates a fix branch, executes TDD, and opens a Pull Request.
- **FR12:** `issue-resolver.yml` triggers automatically when a GitHub issue is opened.

### 2.8 Human-in-the-Loop PR Chat
- **FR13:** When the TDD loop exhausts `max_iterations`, it posts a PR comment requesting `@ai-hint` guidance.
- **FR14:** `pr-chat.yml` listens for `@ai-hint` comments and resumes with the user's hint.

### 2.9 Visual Quality Assurance via VLMs
- **FR15:** Screenshots generated HTML files using Playwright (with Selenium fallback) and submits to a Vision LLM (e.g., `llava`).
- **FR16:** Failed visual checks (score < 6/10) are fed back to the Engineer for CSS corrections.

### 2.10 Auto-Rollback Safety Net
- **FR17:** `save_rollback_point()` captures the current git state before each task.
- **FR18:** `rollback_if_worse()` automatically reverts AI changes if tests regress (more failures than before).

### 2.11 GPU Platform Intelligence with Failover
- **FR19:** `scripts/gpu_platform.py` auto-detects GPU platforms from environment variables (Colab, Kaggle, Lightning, SageMaker, Paperspace, Oracle, Vast.ai, RunPod, custom).
- **FR20:** `health_check()` verifies endpoint liveness. `detect_with_failover()` tries platforms in priority order, automatically falling back to the next if one is down.
- **FR21:** Falls back to local Ollama as last resort if all remote endpoints are unavailable.

### 2.12 Security & Safety
- **FR22:** `safe_path()` validates file paths using `os.path.realpath()` to prevent directory traversal attacks.
- **FR23:** `mask_secret()` prevents token leaks in subprocess output logs.
- **FR24:** All git subprocess calls use `GIT_TIMEOUT=120s` to prevent infinite CI hangs.

## 3. Non-Functional Requirements

### 3.1 Quality Gates & Build Breakers
Tests run in isolated ephemeral virtual environments (`.test_venv`). The PR fails if:
- **Test Coverage:** `pytest`/`coverage` must be `≥ 90%`.
- **Lint Score:** Python `pylint` must be `≥ 8/10`.
- **Complexity:** `radon` must not assign an 'F' grade.

### 3.2 Security Scanning
- `bandit` (Python), `njsscan` (JS), `gosec` (Go).

### 3.3 Performance & Cost
- Executes on standard GitHub 7GB free-tier `ubuntu-latest` runners without OOM.
- No paid API dependencies. GPU acceleration via free cloud platforms is optional.
- Cached venv preservation in `run-tests.sh`/`.ps1` for faster CI reruns.
- Ollama model download skipped if already cached in CI.

### 3.4 Correctness
- `sys.executable` used for pytest to ensure the correct Python interpreter.
- `OLLAMA_NUM_CTX` configurable via environment variable (default: 8192).

## 4. Supported Architecture
- **Languages:** Python, Go, JS/TS, HTML/CSS.
- **Execution:** GitHub Actions CI/CD or local Docker Compose.
- **GPU Platforms:** 9 remote platforms + local (see `docs/gpu_setup_guide.md`).

## 5. Hardware Support Matrix
- **Local Dev:** Linux, macOS, WSL2 (via Docker Compose).
- **CI/CD:** Any GitHub Actions runner supporting bash, Python 3.10+, and `curl`.
- **Remote GPU:** Google Colab, Kaggle, Lightning.ai, SageMaker Lab, Paperspace, Oracle Cloud, Vast.ai, RunPod, or any custom Ollama endpoint.

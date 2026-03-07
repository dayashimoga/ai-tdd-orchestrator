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

## Pending (Immediate Backlog)
- [ ] Implement Rust support (`cargo clippy`, `cargo sec`).
- [ ] Implement Java/C# support (`checkstyle`).
- [ ] Enhance inline review GitHub Action permissions scope to support cross-fork PR annotations cleanly.

## Further Enhancements (V2 Planning)
### 1. Context File Uploads
Allow developers to prefix a `context:` annotation in `prompt.txt` or a PR Description to point the LLM at specifically hosted API Docs, OpenAPI Swaggers, or Architectural diagrams to inform its code generation.

### 2. Web UI for Local Execution
Create a lightweight React dashboard mapped to `localhost:8080` in `docker-compose.yml` to visually see the AI stream its thoughts and fixes instead of tailing terminal logs.

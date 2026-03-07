# Open-Source AI Reviewer User Guide

This guide explains how to install and utilize the intelligent PR Code Reviewer to enforce quality, security, and coverage across your project.

## 1. Setup

### 1.1 Prerequisites
- A GitHub Repository.
- Code written in Python, NodeJS, Go, or Rust.

### 1.2 Installation
Simply copy the `.github/workflows/ai-review.yml`, `scripts/`, and `run-local.sh` into your repository.
Commit and push to `main`. 

## 2. Setting Up a Target Project
The AI Orchestrator can generate a brand new project or jump straight into an existing one via the GitHub Actions "Run workflow" tab.

### 2.1 Generating a New Repository
1. Navigate to your repository and click **Actions** -> **AI Code Review**.
2. Click **Run workflow**. 
3. Select `new` for the **project_type** input.
4. Input your desired repository format (e.g., `username/my-new-app`) under **target_repo**.
5. Optionally, fill out the `prompt_override` with your exact requirements. Example:
   > "A full stack web application using React and Flask backend serving a SQLite Database."
6. The AI will create your new private GitHub repository, commit the foundation, and embed a testing CI pipeline inside it!

### 2.2 Cloning an Existing Repository
1. Click **Run workflow**.
2. Select `existing` for **project_type**.
3. Point **target_repo** to an existing repo (e.g., `username/existing-app`).
4. Provide a prompt on what you want the AI to fix or implement there.
5. The AI will clone the code, analyze the architecture, attempt fixes, and dynamically push the updates directly back to your existing repository!

## 3. Choosing Your LLM Provider
By default the pipeline uses **Ollama** (local/remote). You can switch to any supported provider by setting environment variables:

| Provider | Variables to Set |
|----------|-----------------|
| **Ollama** (default) | `OLLAMA_URL`, `OLLAMA_MODEL` |
| **OpenAI** (GPT-4o) | `LLM_PROVIDER=openai`, `OPENAI_API_KEY`, `OPENAI_MODEL` (optional) |
| **Anthropic** (Claude) | `LLM_PROVIDER=anthropic`, `ANTHROPIC_API_KEY`, `ANTHROPIC_MODEL` (optional) |
| **Google Gemini** | `LLM_PROVIDER=gemini`, `GOOGLE_API_KEY`, `GOOGLE_MODEL` (optional) |

Set these as GitHub Secrets or in your local `.env` file. If an API key is missing, the system falls back to Ollama automatically.

## 4. RAG: Reference Documents for Better Code Quality
To help the AI write more accurate code (especially with smaller models), provide reference documents:

1. Place your API specs, architecture docs, OpenAPI schemas, or any reference material in `your_project/docs/reference/`.
2. Supported formats: `.md`, `.txt`, `.json`, `.yaml`, `.py`, `.js`, `.ts`, `.html`, `.css`, `.go`, `.rs`.
3. The RAG engine **auto-indexes** these documents and injects the most relevant chunks into every engineer prompt.
4. Manual indexing: `python scripts/ai_pipeline.py --index-docs`.

## 5. Pull Request Workflow
1. Create a new branch, write your code, and generate a Pull Request.
2. The Action will automatically intercept the PR and run `git diff`.
3. The AI reads `docs/requirements.md` plus any RAG reference documents to guarantee context.
4. The AI spins up, scans your changes using `njsscan`, `gosec`, `pylint`, etc., within isolated ephemeral virtual environments.
5. Each TDD iteration (e.g., `⏱ Iteration 1/5 completed in 47s`) explicitly reports whether it is implementing a new task or fixing a test failure.
6. If it succeeds, the workflow turns **green**.
7. If it fails the strict gates (<90% Coverage, <8/10 Lint), the PR is **blocked**.

### 5.1 Live Streaming CI Interactivity
The AI Orchestrator streams responses in real-time chunk-by-chunk. You can open the GitHub Actions execution log while the task is running to read the Agent's internal thought processes.

### 5.2 Inline Comments
The AI will post native GitHub Review Comments on the exact lines it believes contain bugs or security flaws.

## 6. Autonomous Issue Resolution
The AI can automatically fix bugs when you open a GitHub issue!

1. Navigate to the **Issues** tab on your repository.
2. Click **New Issue**.
3. Write a clear title and description of the bug.
4. The `issue-resolver.yml` workflow triggers automatically.
5. The AI creates a `fix-issue-{N}` branch, preserves existing project state, runs TDD, and opens a Pull Request.

## 7. Interactive AI Chat on Pull Requests
If the AI gets stuck fixing a test:

1. The AI will post a PR comment saying **"I need your help!"** and list the failing tasks.
2. Reply to the comment with `@ai-hint` followed by your guidance.
3. The `pr-chat.yml` workflow picks up your comment and resumes the TDD loop.

## 8. CLI Flags Reference

| Flag | Description |
|------|-------------|
| `--manual` | Run the full TDD pipeline from a `prompt.txt` |
| `--issue` | Autonomous GitHub issue resolution |
| `--resume-with-hint` | Resume TDD with user hint from PR comment |
| `--index-docs` | Manually re-index `docs/reference/` for RAG |
| `--dry-run` | Preview what the AI would do without generating code or pushing |

## 9. Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `LLM_PROVIDER` | `ollama` | LLM backend: `ollama`, `openai`, `anthropic`, `gemini` |
| `MAX_TDD_ITERATIONS` | `5` | Maximum TDD retry iterations |
| `OLLAMA_NUM_CTX` | `8192` | Context window size for Ollama |
| `WEBHOOK_URL` | — | Slack/Discord webhook for pipeline notifications |

## 10. Visual Quality Assurance
When the AI generates HTML/CSS code, it can optionally:
1. Screenshot the rendered page using Playwright (or Selenium fallback).
2. Submit the screenshot to a Vision LLM (e.g., `llava`) for aesthetic assessment.
3. If the VLM rates layout or typography below 6/10, the critique is fed back for automatic CSS fixes.

## 11. GPU Acceleration (Remote Ollama)
To run high-quality 7b+ models without a local GPU, utilize the automated GPU platform intelligence.

1. **Option A (Google Colab):** Open `gpu-notebooks/colab_gpu_server.ipynb` in Colab, run all, and set `COLAB_OLLAMA_URL` secret.
2. **Option B (Kaggle):** Open `gpu-notebooks/kaggle_gpu_server.ipynb` in Kaggle, run all, and set `KAGGLE_OLLAMA_URL` secret.
3. **Failover:** All platforms are health-checked **in parallel** for faster startup.

See the [GPU Setup Guide](gpu_setup_guide.md) for detailed step-by-step instructions for all 11 supported platforms.

## 12. Local Development (Docker)
You can test the AI against your code without pushing to GitHub.
1. Install [Docker Desktop](https://www.docker.com/).
2. Run `docker-compose up --build`.

## 13. Troubleshooting
- **CI Hangs:** Ensure `COLAB_OLLAMA_URL` is active (notebook is running) or it will fall back to local CPU.
- **Coverage Blocks:** The PR will fail if test coverage drops below 90%. Adjust your task prompt to include more tests.
- **Token Overflow:** On very large projects, the AST Repo Map handles pruning. If it still fails, increase `OLLAMA_NUM_CTX` in your GitHub secrets.
- **RAG Not Working:** Ensure reference documents are in `your_project/docs/reference/` and have supported extensions.

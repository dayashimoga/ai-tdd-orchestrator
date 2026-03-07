# Open-Source AI Reviewer User Guide

This guide explains how to install and utilize the intelligent PR Code Reviewer to enforce quality, security, and coverage across your project.

## 1. Setup

### 1.1 Prerequisites
- A GitHub Repository.
- Code written in Python, NodeJS, or Go.

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

## 3. Pull Request Workflow
1. Create a new branch, write your code, and generate a Pull Request.
2. The Action will automatically intercept the PR and run `git diff`.
3. The AI will spin up locally on the runner, scan your changes using `njsscan`, `gosec`, `pylint`, etc., within isolated ephemeral virtual environments to prevent pollution.
4. If issues are found, the AI gets multiple iterative attempts to execute TDD and push a fix for your files.
5. If it succeeds, the workflow turns **green**.
6. If it fails the strict gates (<90% Coverage, <8/10 Lint), the PR is **blocked**.

### 3.1 Live Streaming CI Interactivity
The AI Orchestrator streams responses in real-time chunk-by-chunk. You can open the GitHub Actions execution log while the task is running to read the Agent's internal thought processes as it codes, instead of blindly staring at a loading screen!

### 3.2 Inline Comments
The AI will post native GitHub Review Comments on the exact lines it believes contain bugs or security flaws. You can view these directly in the "Files Changed" tab on GitHub to either accept or reject them.

## 4. Autonomous Issue Resolution
The AI can automatically fix bugs when you open a GitHub issue!

1. Navigate to the **Issues** tab on your repository.
2. Click **New Issue**.
3. Write a clear title and description of the bug (e.g., *"Login route returns 500 instead of redirecting"*).
4. The `issue-resolver.yml` workflow triggers automatically.
5. The AI creates a `fix-issue-{N}` branch, runs TDD to fix the bug, and opens a Pull Request for your review.

## 5. Interactive AI Chat on Pull Requests
If the AI gets stuck fixing a test:

1. The AI will post a PR comment saying **"I need your help!"** and list the failing tasks.
2. Reply to the comment with `@ai-hint` followed by your guidance. Example:
   > `@ai-hint The authentication middleware expects a JWT token in the Authorization header.`
3. The `pr-chat.yml` workflow picks up your comment and resumes the TDD loop with your hint injected.

## 6. Visual Quality Assurance
When the AI generates HTML/CSS code, it can optionally:
1. Screenshot the rendered page using Playwright (or Selenium fallback).
2. Submit the screenshot to a Vision LLM (e.g., `llava`) for aesthetic assessment.
3. If the VLM rates layout, color, or typography below 6/10, the critique is fed back to the Engineer for automatic CSS fixes.

> **Note:** Visual QA requires Playwright (`pip install playwright && playwright install chromium`) or Selenium + ChromeDriver on the runner.

## 7. GPU Acceleration (Remote Ollama)
To run high-quality 7b+ models without a local GPU, utilize the automated GPU platform intelligence.

1. **Option A (Google Colab):** Open `gpu-notebooks/colab_gpu_server.ipynb` in Colab, run all, and set `COLAB_OLLAMA_URL` secret.
2. **Option B (Kaggle):** Open `gpu-notebooks/kaggle_gpu_server.ipynb` in Kaggle, run all, and set `KAGGLE_OLLAMA_URL` secret.
3. **Failover:** If you set both, the pipeline automatically fails over to Kaggle if Colab is down.

See the [GPU Setup Guide](file:///j:/aigithub/ai-tdd-orchestrator/docs/gpu_setup_guide.md) for detailed step-by-step instructions for all 11 supported platforms.

## 8. Local Development (Docker)
You can test the AI against your code without pushing to GitHub.
1. Install [Docker Desktop](https://www.docker.com/).
2. Run `docker-compose up --build`.

The intelligence script (`select_model.py`) will automatically query your Local RAM/GPU and select the highest quality model your physical computer can handle.

## 9. Troubleshooting
- **CI Hangs:** Ensure `COLAB_OLLAMA_URL` is active (notebook is running) or it will fall back to local CPU.
- **Coverage Blocks:** The PR will fail if test coverage drops below 90%. Adjust your task prompt to include more tests.
- **Token Overflow:** On very large projects, the AST Repo Map handles pruning. If it still fails, increase `OLLAMA_NUM_CTX` in your GitHub secrets.

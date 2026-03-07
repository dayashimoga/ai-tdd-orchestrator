# Comprehensive Requirements Document

## 1. Introduction
The Open-Source AI Code Reviewer is an automated CI/CD and local development tool. Its primary goal is to enforce stringent code quality, test coverage, and security, utilizing entirely free, offline-capable local LLMs. 

## 2. Functional Requirements
### 2.1 Repository Bootstrap & Project Targeting
- **FR1:** The system must evaluate `PROJECT_TYPE` and `TARGET_REPO`. If `new`, the system evaluates the prompt and generates a fresh codebase mapped to a brand new remote GitHub Repository automatically built via PyGithub.
- **FR1a:** If `existing`, the system must automatically clone the designated `TARGET_REPO` to inject fixes directly.

### 2.2 Intelligent Model Selection
- **FR2:** The system must actively detect the host machine's available RAM and GPU VRAM.
- **FR3:** Based on the memory profile, the system must dynamically pull and execute an appropriately sized Ollama model (e.g., `3b` for 7GB runners, `32b` for powerful self-hosted instances).

### 2.3 Assessment & Remediation Loop
- **FR4:** The pipeline must only analyze files explicitly changed in the Pull Request utilizing `git diff/refs`. 
- **FR5:** Discovered lint, testing, or security issues must be passed back to the LLM. 
- **FR6:** The LLM must be given up to 3 iterative chances to rewrite and fix the failed file autonomously.

### 2.4 Inline Review Annotations
- **FR7:** The system must utilize the standard `GITHUB_TOKEN` to post autonomous code suggestions directly on the affected lines via PR Review Comments.

### 2.5 Real-time Streaming Observability
- **FR8:** The pipeline must stream HTTP response chunks from the local Ollama API directly to the standard output (`sys.stdout`) in real-time. This ensures CI/CD jobs don't silently hang and developers can watch the LLM write code live.

## 3. Non-Functional Requirements
### 3.1 Quality Gates & Build Breakers
The Action must execute tests strictly within isolated, ephemeral Python virtual environments (`.test_venv`) to prevent polluting the host runner. It must hard fail the GitHub PR if any of the following metrics are not met:
- **Lint Score:** Python `pylint` must be `≥ 8/10`.
- **Test Coverage:** Python `pytest`/`coverage` must be `≥ 90%`.
- **Complexity:** `radon` must not assign an 'F' grade to any module.

### 3.2 Security Scanning
- The system must integrate `bandit` (Python), `njsscan` (JS), and `gosec` (Go) into the AI's standard analysis flow.

### 3.3 Performance & Cost
- Must execute correctly inside standard Github 7GB Free Tier `ubuntu-latest` runners without OOM.
- Must not rely on paid APIs (e.g. OpenAI, Anthropic).

## 4. Supported Architecture
- **Language Stack:** Python (Backend), `Go` (Backend), `JS/TS` (Frontend/Backend), `HTML/CSS` (Static Markup).
- **Execution Mode:** Automated CI/CD (GitHub Actions) or Offline Container Orchestration (`Docker Compose`).

## 5. Hardware Support Matrix
- **Local Dev:** Linux, macOS, WSL2 (via Docker Compose).
- **CI/CD:** Any GitHub Actions runner supporting bash, Python 3.10+, and `curl`.

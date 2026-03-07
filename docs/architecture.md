# Technical Architecture

## 1. System Overview
The pipeline is designed to be highly modular. By migrating away from bulky Hugging Face `transformers` modules, the architecture separates the "Thinker" (the LLM server) from the "Orchestrator" (the CI scripts). 

## 2. Component Diagram
```mermaid
graph TD
    A[GitHub Action / Local Docker] -->|1. Setup Target Repo| R[PyGithub / Git Clone]
    R -->|2. Measures RAM/VRAM| B(select_model.py)
    B -->|3. Loads optimal model| C{Ollama Server}
    A -->|4. Runs| D[ai_pipeline.py]
    D -->|5. Identifies Git Diff| E[Security & Lint Tools]
    E -->|6. Passes failures| D
    D <-->|7. Streams generation| C
    D -->|8. Commits & Pushes Fixes| R
    D -->|9. Posts Comments| F((GitHub PR API))
```

## 3. Hardware Intelligence Layer
Located in `scripts/select_model.py`.
Standard LLMs require monolithic VRAM which causes Actions runners to crash. This layer intercepts the environment before Ollama boots, detects the `/proc/meminfo` or `sysctl`, and exports `OLLAMA_MODEL`. 
- `qwen2.5-coder:32b` (>32GB Memory Envelope)
- `deepseek-coder:6.7b` (>14GB Memory Envelope)
- `qwen2.5-coder:3b` (<14GB standard runner envelope)

## 4. Remediation Loop (`ai_pipeline.py`)
1. **Repository Setup:** PyGithub creates a new remote repository or clones an existing one to execute tests on via isolated Docker/Venvs.
2. **Extraction:** Discovers changed source lines via `git diff origin/main...HEAD`.
3. **Analysis Execution:** Runs `pytest`, `pylint`, `eslint`, `golint`, and strict security scanners locally.
4. **AI Injection:** Directly appends `stderr/stdout` of the tool output into a unified prompt.
5. **Streaming Generaton:** Responses are streamed via `iter_lines()` back to the runner's stdout to prevent CI stalling. 
6. **Writing & Pushing:** Cleans the LLM's Markdown output overwrites the source file, and securely pushes it back to the remote `TARGET_REPO`.

## 5. Security Toolchain
- **Python:** `bandit` - Scans AST for hardcoded credentials, eval(), injections.
- **NodeJS:** `njsscan` - Scans Server-Side JavaScript logic.
- **Go:** `gosec` - Abstract Syntax Tree security inspector for Golang.

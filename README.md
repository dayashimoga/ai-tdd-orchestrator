# AI TDD Orchestrator — Professional Edition 🚀

A high-performance codebase generator and autonomous engineering pipeline powered by professional AI orchestrators.

## 🌟 Core Architecture

The system acts as a **Thin Delegator**, offloading complex reasoning and execution to best-in-class orchestrators. Everything runs in **ephemeral, disposable environments** (Venv/Docker) to keep your host system clean.

### 🤖 Supported Orchestrators

1.  **CrewAI (`--crewai`)**: Multi-agent specialist team (Planner, Engineer, Reviewer).
2.  **OpenHands (`--openhands`)**: Fully autonomous Docker-based software engineering.
3.  **PydanticAI (`--pydanticai`)**: Fast, typed micro-agents for structured tasks.
4.  **Aider (`--aider`)**: High-efficiency CLI coding agent with deep Git integration.
5.  **LangGraph (`--langgraph`)**: Modular, stateful directed workflows.

## ⚙️ Usage

### Local Execution (Ephemeral)
Run any orchestrator without installing its dependencies locally:
```bash
# General Syntax
python scripts/ai_pipeline.py <orchestrator_flag> "[Your Prompt]"

# Examples
python scripts/ai_pipeline.py --crewai "Build a REST API with FastAPI"
python scripts/ai_pipeline.py --aider "Refactor the authentication logic"
python scripts/ai_pipeline.py --openhands "Fix the memory leak in the data processor"
```

### GitHub Actions (Automation)
Go to the **Actions** tab in your repository and trigger the `AI Orchestrator CI` workflow:
- **Orchestrator**: Select from the dropdown.
- **Prompt**: Enter your task requirements.
- **LLM Provider**: (Optional) Override the default model/provider.

## 🖥️ High-Performance Compute & Model Routing

- **GPU Compute**: Retains full support for external GPU nodes (Ollama, RunPod) via `scripts/gpu_platform.py`.
- **Model Agnostic**: Integrated `llm_router.py` dynamically switches between OpenAI, Anthropic, Gemini, Groq, and Local models.
- **Failover**: Automatic failover between providers on rate limits or outages.

## 🧪 Testing

The infrastructure is verified with a robust mock-based test suite:
```bash
pytest tests/test_ephemeral_orchestration.py
```
*Tested with 100% pass rate and high coverage on delegation logic.*

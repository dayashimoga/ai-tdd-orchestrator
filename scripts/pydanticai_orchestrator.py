import os
import sys
from pydantic_ai import Agent, RunContext
from pydantic import BaseModel
from typing import List

# Import local modules
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
# Add scripts to path for imports
try:
    import scripts.llm_router as llm_router
except ImportError:
    import llm_router as llm_router

# Configuration
MODEL_NAME = os.getenv("OLLAMA_MODEL") or "qwen2.5-coder:3b"

# Define the output format for the agent
class TaskList(BaseModel):
    tasks: List[str]
    summary: str

# Determine the model and provider
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "auto").lower()

if LLM_PROVIDER == "openai":
    from pydantic_ai.models.openai import OpenAIModel
    model = OpenAIModel(os.getenv("OPENAI_MODEL", "gpt-4o-mini"))
elif LLM_PROVIDER == "anthropic":
    from pydantic_ai.models.anthropic import AnthropicModel
    model = AnthropicModel(os.getenv("ANTHROPIC_MODEL", "claude-3-haiku-20240307"))
else:
    # Default to Ollama/OpenAI-compatible local endpoint
    from pydantic_ai.models.openai import OpenAIModel
    ollama_url = os.getenv("OLLAMA_URL") or "http://localhost:11434"
    if "/v1" not in ollama_url:
        ollama_url = ollama_url.rstrip("/") + "/v1"
    
    model = OpenAIModel(
        model_name=MODEL_NAME,
        base_url=ollama_url,
        api_key="ollama"
    )

agent = Agent(
    model,
    result_type=TaskList,
    system_prompt=(
        "You are a Senior Software Architect. Your goal is to analyze user requirements "
        "and provide a structured implementation plan. "
        "Break the work into small, atomic tasks that are easy to implement and test. "
        "Use the RAG tool for context and the Repo Map tool to understand the codebase."
    )
)

agent.model_provider = LLM_PROVIDER

# --- Specialized Tools ---
from scripts.rag_engine import get_rag_context
from scripts.repo_map import generate_repo_map
from scripts.visual_qa import run_visual_qa

@agent.tool_plain
def retrieve_context(query: str) -> str:
    """Retrieves technical context from reference documents."""
    return get_rag_context(query)

@agent.tool_plain
def get_codebase_map(directory: str = ".") -> str:
    """Returns a structural outline of the codebase classes and functions."""
    return generate_repo_map(directory)

@agent.tool_plain
def assess_ui_quality(directory: str = ".") -> str:
    """Captures screenshots and assesses UI aesthetic quality."""
    results = run_visual_qa(directory)
    return str(results)

async def run_pydantic_orchestration(prompt: str):
    print(f"🧠 [PydanticAI] Analyzing: {prompt}")
    result = await agent.run(prompt)
    return result.data

if __name__ == "__main__":
    import asyncio
    prompt = sys.argv[1] if len(sys.argv) > 1 else "Build a simple task manager."
    
    try:
        data = asyncio.run(run_pydantic_orchestration(prompt))
        print("\n--- IMPLEMENTATION PLAN ---")
        print(f"Summary: {data.summary}")
        for i, task in enumerate(data.tasks, 1):
            print(f"{i}. {task}")
    except Exception as e:
        print(f"ERROR: PydanticAI failed: {e}")
        # Fallback to a simple message if the agent fails (e.g. Ollama /v1 not ready)
        print("INFO: Tip: Ensure Ollama is running with 'OLLAMA_ORIGINS=*' if using web browser, or just ensure it's accessible.")

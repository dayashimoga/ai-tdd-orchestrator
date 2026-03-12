import os
import sys
from crewai import Agent, Task, Crew, Process
from typing import List, Optional, Type
from pydantic import BaseModel, Field

# Import local modules
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
import scripts.llm_router as llm_router

# Configuration
MODEL_NAME = os.getenv("OLLAMA_MODEL") or "qwen2.5-coder:3b"
OLLAMA_URL = os.getenv("OLLAMA_URL") or "http://localhost:11434"

# Custom LangChain LLM wrapper for our Provider-Agnostic Router
try:
    from langchain_core.language_models.llms import LLM
except ImportError:
    class LLM: pass

# Use the router-backed LLM for all agents
# We satisfy CrewAI's internal validation by providing a dummy key if OpenAI isn't being used
if not os.getenv("OPENAI_API_KEY"):
    os.environ["OPENAI_API_KEY"] = "not-needed"

class RouterLLM(LLM):
    """Custom LangChain LLM that routes to our provider-agnostic generator."""
    
    @property
    def _llm_type(self) -> str:
        return "router_llm"

    def _call(self, prompt: str, stop: List[str] = None, **kwargs) -> str:
        return llm_router.generate(prompt, stream=False)

    @property
    def _identifying_params(self) -> dict:
        return {"name_of_model": "router_llm"}

local_llm = RouterLLM()

# --- Specialized Tools Integration ---
from scripts.rag_engine import get_rag_context
from scripts.repo_map import generate_repo_map
from scripts.visual_qa import run_visual_qa

# Try to use CrewAI's own tool decorator if available, fallback to LangChain's
try:
    from crewai.tools import tool
except ImportError:
    try:
        from langchain_core.tools import tool
    except ImportError:
        from langchain.tools import tool

# Pydantic models for tool arguments (improves validation in Pydantic v2)
class QueryInput(BaseModel):
    query: str = Field(..., description="The query string to search for.")

class DirectoryInput(BaseModel):
    directory: str = Field(".", description="The directory to analyze. Use '.' for root.")

@tool("rag_knowledge_retrieval")
def rag_tool(query: str):
    """Useful for retrieving context from reference documents and API specs."""
    return get_rag_context(query)

@tool("repository_structure_map")
def repo_map_tool(directory: str = "."):
    """Useful for understanding the overall project structure. Returns a file tree with signatures."""
    return generate_repo_map(directory)

@tool("visual_qa_assessment")
def visual_qa_tool(directory: str = "."):
    """Useful for assessing the aesthetic quality of generated HTML/UI files via computer vision."""
    return run_visual_qa(directory)

all_tools = [rag_tool, repo_map_tool, visual_qa_tool]

# 1. Define Agents
planner = Agent(
    role='Lead Software Planner',
    goal='Create a comprehensive and technically sound implementation plan based on user requirements.',
    backstory='You are an expert software architect with decades of experience in TDD and system design.',
    llm=local_llm,
    verbose=True,
    allow_delegation=False
)

engineer = Agent(
    role='Senior Software Engineer',
    goal='Write high-quality, production-ready code and comprehensive unit tests to satisfy the requirements.',
    backstory='You are a coding prodigy specialized in Python and TDD. You write clean, efficient code.',
    llm=local_llm,
    verbose=True,
    allow_delegation=False,
    tools=all_tools
)

reviewer = Agent(
    role='Principal Quality Engineer',
    goal='Review the generated code for security, performance, and adherence to the plan.',
    backstory='You are a meticulous reviewer who finds even the most subtle bugs and vulnerabilities.',
    llm=local_llm,
    verbose=True,
    allow_delegation=False
)

# 2. Define Tasks
def run_orchestration(user_prompt: str):
    plan_task = Task(
        description=f"Analyze requirements and create a technical checklist: {user_prompt}",
        expected_output="A markdown checklist of technical tasks including unit testing requirements.",
        agent=planner
    )

    coding_task = Task(
        description="Implement the code and unit tests based on the plan. Ensure production quality.",
        expected_output="The full source code and test files.",
        agent=engineer,
        context=[plan_task]
    )

    review_task = Task(
        description="Review the implemented code and tests. Verify requirements and quality.",
        expected_output="A summary of the review results. PASS/FAIL.",
        agent=reviewer,
        context=[coding_task]
    )

    # 3. Form the Crew
    crew = Crew(
        agents=[planner, engineer, reviewer],
        tasks=[plan_task, coding_task, review_task],
        process=Process.sequential,
        verbose=True
    )

    return crew.kickoff()

if __name__ == "__main__":
    prompt = sys.argv[1] if len(sys.argv) > 1 else "Build a simple calculator API."
    result = run_orchestration(prompt)
    print("\n\n########################")
    print("## ORCHESTRATION RESULT")
    print("########################\n")
    print(result)

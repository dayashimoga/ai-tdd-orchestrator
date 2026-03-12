import os
import sys
from crewai import Agent, Task, Crew, Process
from langchain_community.llms import Ollama
try:
    from langchain_core.tools import tool
except ImportError:
    from langchain.tools import tool
from typing import List

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

class RouterLLM(LLM):
    @property
    def _llm_type(self) -> str:
        return "router_llm"

    def _call(self, prompt: str, stop: List[str] = None, **kwargs) -> str:
        return llm_router.generate(prompt, stream=False)

# Use the router-backed LLM for all agents
local_llm = RouterLLM()

# --- Specialized Tools Integration ---
from scripts.rag_engine import get_rag_context
from scripts.repo_map import generate_repo_map
from scripts.visual_qa import run_visual_qa

@tool
def rag_tool(query: str):
    """Useful for retrieving context from reference documents and API specs."""
    return get_rag_context(query)

@tool
def repo_map_tool(directory: str):
    """Useful for understanding the overall project structure and finding relevant files. Pass '.' for root."""
    return generate_repo_map(directory or ".")

@tool
def visual_qa_tool(directory: str):
    """Useful for assessing the aesthetic quality of generated HTML/UI files. Pass '.' for root."""
    return run_visual_qa(directory or ".")

all_tools = [rag_tool, repo_map_tool, visual_qa_tool]

# 1. Define Agents
planner = Agent(
    role='Lead Software Planner',
    goal='Create a comprehensive and technically sound implementation plan based on user requirements.',
    backstory='You are an expert software architect with decades of experience in TDD and system design. You break down complex requirements into atomic, testable tasks.',
    llm=local_llm,
    verbose=True,
    allow_delegation=False
)

engineer = Agent(
    role='Senior Software Engineer',
    goal='Write high-quality, production-ready code and comprehensive unit tests to satisfy the requirements.',
    backstory='You are a coding prodigy specialized in Python and TDD. You write clean, efficient code and always ensure 90%+ test coverage.',
    llm=local_llm,
    verbose=True,
    allow_delegation=False,
    tools=all_tools
)

reviewer = Agent(
    role='Principal Quality Engineer',
    goal='Review the generated code for security, performance, and adherence to the plan. Ensure tests pass and coverage is met.',
    backstory='You are a meticulous reviewer who finds even the most subtle bugs and security vulnerabilities. You enforce strict quality gates.',
    llm=local_llm,
    verbose=True,
    allow_delegation=False
)

# 2. Define Tasks
def run_orchestration(user_prompt: str):
    plan_task = Task(
        description=f"Analyze the following requirements and create a detailed Markdown checklist of implementation steps: {user_prompt}",
        expected_output="A markdown checklist of technical tasks including unit testing requirements.",
        agent=planner
    )

    coding_task = Task(
        description="Based on the approved plan, implement the necessary code and unit tests. Ensure the code is production-ready.",
        expected_output="The full source code and test files in a structured format.",
        agent=engineer,
        context=[plan_task]
    )

    review_task = Task(
        description="Review the implemented code and tests. Verify that all requirements are met and that the coverage is sufficient.",
        expected_output="A summary of the review results and a confirmation if the code passes the quality gates.",
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
    if len(sys.argv) > 1:
        prompt = sys.argv[1]
    else:
        prompt = "Create a simple calculator API with basic arithmetic operations."
    
    result = run_orchestration(prompt)
    print("\n\n########################")
    print("## ORCHESTRATION RESULT")
    print("########################\n")
    print(result)

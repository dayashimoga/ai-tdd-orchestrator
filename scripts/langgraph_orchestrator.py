import os
import sys
from typing import TypedDict, List
from langgraph.graph import StateGraph, END
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage

# Import local modules
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
try:
    import scripts.llm_router as llm_router
except ImportError:
    import llm_router as llm_router
from scripts.rag_engine import get_rag_context
from scripts.repo_map import generate_repo_map
from scripts.visual_qa import run_visual_qa

# Configuration
MODEL_NAME = os.getenv("OLLAMA_MODEL") or "qwen2.5-coder:3b"

# Define the state for the graph
class AgentState(TypedDict):
    prompt: str
    plan: str
    code: str
    review: str

# Define nodes for the graph
# Determine the model and provider
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "auto").lower()

if LLM_PROVIDER == "openai":
    llm = ChatOpenAI(model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"), api_key=os.getenv("OPENAI_API_KEY"))
elif LLM_PROVIDER == "anthropic":
    from langchain_anthropic import ChatAnthropic
    llm = ChatAnthropic(model=os.getenv("ANTHROPIC_MODEL", "claude-3-haiku-20240307"), api_key=os.getenv("ANTHROPIC_API_KEY"))
else:
    # Default to Ollama/OpenAI-compatible local endpoint
    ollama_url = os.getenv("OLLAMA_URL") or "http://localhost:11434"
    if "/v1" not in ollama_url:
        ollama_url = ollama_url.rstrip("/") + "/v1"
    
    llm = ChatOpenAI(
        model=MODEL_NAME,
        base_url=ollama_url,
        api_key="ollama"
    )

def planner_node(state: AgentState):
    print("🧠 [LangGraph] Planning...")
    # Inject repo map for better context
    repo_map = generate_repo_map(".")
    rag_context = get_rag_context(state['prompt'])
    
    context_prompt = f"Context:\n{repo_map}\n{rag_context}\n\nUser Request: {state['prompt']}"
    
    response = llm.invoke([
        SystemMessage(content="You are a software architect. Create a plan for the following request using the provided context."),
        HumanMessage(content=context_prompt)
    ])
    return {"plan": response.content}

def engineer_node(state: AgentState):
    print("💻 [LangGraph] Coding...")
    response = llm.invoke([
        SystemMessage(content=f"You are a software engineer. Implement the following plan:\n{state['plan']}"),
        HumanMessage(content=state['prompt'])
    ])
    return {"code": response.content}

def reviewer_node(state: AgentState):
    print("🔍 [LangGraph] Reviewing...")
    response = llm.invoke([
        SystemMessage(content=f"You are a code reviewer. Review the following code:\n{state['code']}"),
        HumanMessage(content="Does this meet the requirements?")
    ])
    return {"review": response.content}

# build the graph
workflow = StateGraph(AgentState)
workflow.add_node("planner", planner_node)
workflow.add_node("engineer", engineer_node)
workflow.add_node("reviewer", reviewer_node)

workflow.set_entry_point("planner")
workflow.add_edge("planner", "engineer")
workflow.add_edge("engineer", "reviewer")
workflow.add_edge("reviewer", END)

app = workflow.compile()

async def run_langgraph(prompt: str):
    inputs = {"prompt": prompt}
    final_state = await app.ainvoke(inputs)
    return final_state

if __name__ == "__main__":
    import asyncio
    prompt = sys.argv[1] if len(sys.argv) > 1 else "Write a python script to parse CSV files."
    try:
        final_result = asyncio.run(run_langgraph(prompt))
        print("\n\n--- LANGGRAPH ORCHESTRATION RESULT ---")
        print(f"PLAN:\n{final_result['plan'][:200]}...")
        print(f"\nCODE:\n{final_result['code'][:200]}...")
        print(f"\nREVIEW:\n{final_result['review'][:200]}...")
    except Exception as e:
        print(f"❌ LangGraph failed: {e}")

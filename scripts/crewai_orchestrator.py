import os
import sys

# 1. Import local router first
try:
    import scripts.llm_router as llm_router
except ImportError:
    import llm_router as llm_router

# 2. --- ROBUST MULTI-LAYER MONKEYPATCH ---
# This intercepts EVERY direct or indirect LLM call.

def monkeypatch_llms():
    # A. Monkeypatch litellm (Heavy lifting for CrewAI)
    try:
        import litellm
        from litellm import completion as litellm_completion
        
        if not hasattr(litellm, "_original_completion"):
            litellm._original_completion = litellm.completion
        
        def patched_litellm_completion(*args, **kwargs):
            messages = kwargs.get('messages', [])
            prompt = ""
            for m in messages:
                role = m.get('role', 'user')
                content = m.get('content', '')
                prompt += f"{role.capitalize()}: {content}\n"
            prompt += "Assistant: "
            
            print(f"DEBUG: [MONKEYPATCH-LITELLM] Intercepted call. Routing to local router...")
            response_text = llm_router.generate(prompt, stream=False)
            
            # Return a mock litellm response
            return type('ModelResponse', (), {
                'choices': [
                    type('Choice', (), {
                        'message': type('Message', (), {'content': response_text, 'role': 'assistant'}),
                        'finish_reason': 'stop'
                    })
                ],
                'usage': type('Usage', (), {'total_tokens': 0, 'prompt_tokens': 0, 'completion_tokens': 0})
            })
            
        litellm.completion = patched_litellm_completion
        print("DONE: litellm monkeypatched successfully.")
    except Exception as e:
        print(f"DEBUG: litellm monkeypatch deferred: {e}")

    # B. Monkeypatch openai (Secondary fallback)
    try:
        import openai
        from openai.resources.chat import completions
        
        if not hasattr(completions.Completions, "_original_create"):
            completions.Completions._original_create = completions.Completions.create
        
        def patched_openai_create(self, *args, **kwargs):
            messages = kwargs.get('messages', [])
            prompt = ""
            for m in messages:
                role = m.get('role', 'user')
                content = m.get('content', '')
                prompt += f"{role.capitalize()}: {content}\n"
            prompt += "Assistant: "
            
            print(f"DEBUG: [MONKEYPATCH-OPENAI] Intercepted call. Routing to local router...")
            response_text = llm_router.generate(prompt, stream=False)
            
            class MockResponse:
                def __init__(self, text):
                    self.choices = [type('Choice', (), {'message': type('Message', (), {'content': text}), 'finish_reason': 'stop'})]
                    self.usage = type('Usage', (), {'total_tokens': 0, 'prompt_tokens': 0, 'completion_tokens': 0})
                    self.model = kwargs.get('model', 'patched-model')
                    self.id = "mock-id"; self.created = 123456789; self.object = "chat.completion"
            
            return MockResponse(response_text)
            
        completions.Completions.create = patched_openai_create
        print("DONE: OpenAI monkeypatched successfully.")
    except Exception as e:
        print(f"DEBUG: OpenAI monkeypatch deferred: {e}")

# Apply monkeypatches immediately
monkeypatch_llms()

# 3. Import CrewAI
from crewai import Agent, Task, Crew, Process
from typing import List, Optional, Type
from pydantic import BaseModel, Field

# For the Agent's llm attribute, we can now use a dummy name since litellm is patched.
local_llm = "gpt-4o" # This string triggers litellm.completion("gpt-4o", ...)

# --- Specialized Tools Integration ---
from scripts.rag_engine import get_rag_context
from scripts.repo_map import generate_repo_map

# Try to use CrewAI's own tool decorator
try:
    from crewai.tools import tool
except ImportError:
    from langchain_core.tools import tool

@tool("rag_knowledge_retrieval")
def rag_tool(query: str):
    """Useful for retrieving context from reference documents."""
    return get_rag_context(query)

@tool("repository_structure_map")
def repo_map_tool(directory: str = "."):
    """Useful for understanding the overall project structure."""
    return generate_repo_map(directory)

all_tools = [rag_tool, repo_map_tool]

# 1. Define Agents (Passing a string as llm makes CrewAI use litellm.completion)
planner = Agent(
    role='Lead Software Planner',
    goal='Create a comprehensive and technically sound implementation plan.',
    backstory='Expert architect.',
    llm=local_llm,
    verbose=True,
    allow_delegation=False
)

engineer = Agent(
    role='Senior Software Engineer',
    goal='Write high-quality code and tests.',
    backstory='Coding prodigy.',
    llm=local_llm,
    verbose=True,
    allow_delegation=False,
    tools=all_tools
)

reviewer = Agent(
    role='Principal Quality Engineer',
    goal='Review the generated code.',
    backstory='Meticulous reviewer.',
    llm=local_llm,
    verbose=True,
    allow_delegation=False
)

def run_orchestration(user_prompt: str):
    plan_task = Task(description=f"Analyze requirements: {user_prompt}", expected_output="A checklist.", agent=planner)
    coding_task = Task(description="Implement the code.", expected_output="Full source code.", agent=engineer, context=[plan_task])
    review_task = Task(description="Review the code.", expected_output="PASS/FAIL.", agent=reviewer, context=[coding_task])

    crew = Crew(
        agents=[planner, engineer, reviewer],
        tasks=[plan_task, coding_task, review_task],
        process=Process.sequential,
        verbose=True,
        planning=False,
    )

    print(f"DEBUG: Using custom router LLM: {llm_router.get_provider_info()}")
    return crew.kickoff()

if __name__ == "__main__":
    prompt = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else "Refactor the authentication module."
    result = run_orchestration(prompt)
    print("\n\n########################")
    print("## ORCHESTRATION RESULT")
    print("########################\n")
    print(result)

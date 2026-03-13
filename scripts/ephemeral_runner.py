import subprocess
import os
import sys
import shutil
import tempfile
import time

# Add project root to sys.path for robust imports
root_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if root_dir not in sys.path:
    sys.path.insert(0, root_dir)

def run_ephemeral_orchestration(prompt: str, mode: str = "venv", orchestrator: str = "crewai"):
    """Runs the AI orchestration in a disposable environment."""
    print(f"INFO: Starting {orchestrator} orchestration in {mode} mode...")
    
    if mode == "venv":
        execute_in_venv(prompt, orchestrator)
    elif mode == "docker":
        execute_in_docker(prompt, orchestrator)
    else:
        raise ValueError(f"Unknown orchestration mode: {mode}")

def execute_in_venv(prompt: str, orchestrator: str):
    """Creates a temporary venv, installs dependencies for the specific orchestrator, and runs it."""
    # Use a local directory for temporary environments to avoid Windows path/security issues in AppData/Temp
    temp_base = os.path.join(os.getcwd(), ".temp_envs")
    os.makedirs(temp_base, exist_ok=True)
    temp_dir = tempfile.mkdtemp(dir=temp_base, prefix="ai_orchestrator_")
    
    venv_dir = os.path.join(temp_dir, ".venv")
    
    print(f"INFO: Created temporary environment in: {temp_dir}")
    
    try:
        # 1. Create venv
        subprocess.run([sys.executable, "-m", "venv", venv_dir], check=True)
        
        # 2. Identify python/pip in venv
        if os.name == "nt":
            python_exe = os.path.join(venv_dir, "Scripts", "python.exe")
            pip_exe = os.path.join(venv_dir, "Scripts", "pip.exe")
        else:
            python_exe = os.path.join(venv_dir, "bin", "python")
            pip_exe = os.path.join(venv_dir, "bin", "pip")
            
        # 3. Install orchestrator-specific dependencies
        print(f"INFO: Installing dependencies for {orchestrator} into ephemeral venv...")
        deps = {
            "crewai": ["crewai", "langchain", "langchain-community", "langchain-core", "openai", "langchain-openai", "pydantic-settings", "requests", "pydantic==2.8.2", "pydantic-core==2.20.1"],
            "pydanticai": ["pydantic-ai", "logfire", "requests"],
            "aider": ["aider-chat"],
            "langgraph": ["langgraph", "langchain", "langchain-openai", "langchain-community", "langchain-core", "openai", "requests", "pydantic==2.8.2", "pydantic-core==2.20.1"]
        }
        
        target_deps = deps.get(orchestrator, [])
        if target_deps:
            subprocess.run([pip_exe, "install"] + target_deps, check=True)
            
        # 4. Copy current project scripts to temp dir for execution consistency
        # Avoid copying large untracked folders or .git
        scripts_to_copy = ["llm_router.py", f"{orchestrator}_orchestrator.py", "rag_engine.py", "repo_map.py", "visual_qa.py", "gpu_platform.py"]
        temp_scripts_dir = os.path.join(temp_dir, "scripts")
        os.makedirs(temp_scripts_dir, exist_ok=True)
        
        for script in scripts_to_copy:
            src = os.path.join(root_dir, "scripts", script)
            if os.path.exists(src):
                shutil.copy2(src, temp_scripts_dir)
        
        # Create an __init__.py in the temp scripts dir
        with open(os.path.join(temp_scripts_dir, "__init__.py"), "w") as f:
            pass

        # 5. Execute orchestrator
        final_script = os.path.join(temp_scripts_dir, f"{orchestrator}_orchestrator.py")
        env = os.environ.copy()
        env["PYTHONPATH"] = temp_dir # Set PYTHONPATH to the temp root
        
        print(f"INFO: Executing {orchestrator} script: {final_script}")
        subprocess.run([python_exe, final_script, prompt], env=env, check=True)
        
    except Exception as e:
        print(f"ERROR: Exception during ephemeral execution: {e}")
        raise
    finally:
        # 6. Cleanup unless DEBUG is set
        if not os.getenv("DEBUG_AI"):
            print(f"INFO: Cleaning up: {temp_dir}")
            try:
                shutil.rmtree(temp_dir)
            except Exception as cleanup_err:
                print(f"WARN: Cleanup failed for {temp_dir}: {cleanup_err}")

def execute_in_docker(prompt: str, orchestrator: str):
    """Placeholder for docker-based execution (e.g. for OpenHands)."""
    print(f"INFO: Docker execution for {orchestrator} is coming soon.")
    # In a real scenario, we'd pull an image, mount volumes, and run.

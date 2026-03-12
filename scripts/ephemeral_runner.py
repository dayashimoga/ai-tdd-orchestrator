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
    temp_dir = tempfile.mkdtemp(prefix="ai_orchestrator_")
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
            "crewai": ["crewai", "langchain", "langchain-community", "pydantic-settings", "requests"],
            "pydanticai": ["pydantic-ai", "logfire", "requests"],
            "aider": ["aider-chat"],
            "langgraph": ["langgraph", "langchain", "langchain-openai", "langchain-community", "requests"]
        }
        
        target_deps = deps.get(orchestrator, [])
        if target_deps:
            subprocess.run([pip_exe, "install"] + target_deps, check=True)
        
        # 4. Run the orchestrator
        scripts_dir = os.path.dirname(__file__)
        orchestrator_map = {
            "crewai": os.path.join(scripts_dir, "crewai_orchestrator.py"),
            "pydanticai": os.path.join(scripts_dir, "pydanticai_orchestrator.py"),
            "aider": "aider", # Aider is usually run as a command after pip install
            "langgraph": os.path.join(scripts_dir, "langgraph_orchestrator.py")
        }
        
        orchestrator_path = orchestrator_map.get(orchestrator)
        
        # Pass necessary environment variables to the subprocess
        env = os.environ.copy()
        env["PYTHONPATH"] = os.path.abspath(os.path.join(scripts_dir, ".."))
        
        if orchestrator == "aider":
            # Aider runs directly as a command in the venv
            # 'aider' command is in the venv's scripts
            aider_cmd = os.path.join(venv_dir, "Scripts", "aider.exe") if os.name == "nt" else os.path.join(venv_dir, "bin", "aider")
            # Run aider in the your_project directory with the prompt
            os.makedirs("your_project", exist_ok=True)
            subprocess.run([aider_cmd, "--message", prompt, "--yes"], cwd="your_project", env=env, check=True)
        elif orchestrator_path:
            subprocess.run([python_exe, orchestrator_path, prompt], env=env, check=True)
        else:
            print(f"ERROR: Could not find runner for {orchestrator}")
            return
        
        print("DONE: Orchestration complete.")
        
    except Exception as e:
        print(f"ERROR: Exception during ephemeral execution: {e}")
    finally:
        # 5. Cleanup
        print(f"INFO: Cleaning up: {temp_dir}")
        shutil.rmtree(temp_dir, ignore_errors=True)

def execute_in_docker(prompt: str, orchestrator: str):
    """Runs the orchestration inside an OpenHands Docker container."""
    if orchestrator != "openhands":
        print(f"WARN: Docker mode currently only optimized for OpenHands. Skipping {orchestrator}.")
        return

    print("INFO: Initializing OpenHands in Docker mode...")
    
    # 1. Configuration for OpenHands
    image = "ghcr.io/all-hands-ai/openhands:0.20"
    workspace_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "your_project"))
    
    # Ensure workspace exists
    os.makedirs(workspace_path, exist_ok=True)
    
    # 2. Construct Docker command
    # We mount the workspace and provide the LLM configuration via environment variables
    # OpenHands typically expects an API key, we'll pass whatever is configured in llm_router
    docker_cmd = [
        "docker", "run", "--rm",
        "-it",
        "--pull", "always",
        "-v", f"{workspace_path}:/opt/workspace",
        "-v", "/var/run/docker.sock:/var/run/docker.sock", # Allow OpenHands to spawn its own sandboxes
        "-e", f"SANDBOX_WORKSPACE_DIR={workspace_path}",
        "-e", f"LLM_API_KEY={os.getenv('OPENAI_API_KEY', 'empty')}", # Example: OpenHands often needs an API key
        "-e", f"LLM_MODEL={os.getenv('OPENAI_MODEL', 'gpt-4o')}",
        image
    ]
    
    print(f"INFO: Running OpenHands on workspace: {workspace_path}")
    print(f"INFO: Command: {' '.join(docker_cmd)}")
    
    try:
        # Note: OpenHands is an interactive agent, so we normally use -it.
        # In a CI context, we would use headless scripts.
        subprocess.run(docker_cmd, check=True)
        print("DONE: OpenHands execution session complete.")
    except Exception as e:
        print(f"ERROR: Docker execution failed: {e}")
        print("INFO: Make sure Docker is running and you have access to ghcr.io.")

if __name__ == "__main__":
    user_prompt = sys.argv[1] if len(sys.argv) > 1 else "Create a microservice plan for a weather app."
    run_ephemeral_orchestration(user_prompt)

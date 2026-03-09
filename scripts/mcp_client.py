import json
import subprocess
import os
import sys
from typing import Dict, Any, Tuple

# ---------------------------------------------------------------------------
# MCP Tool Registry
# ---------------------------------------------------------------------------

MCP_TOOLS = [
    {
        "name": "execute_local_inference",
        "description": "Farms out a sub-task to a local GPU LLM model. Useful for delegating non-critical parallel reasoning tasks.",
        "parameters": {
            "type": "object",
            "properties": {
                "prompt": {
                    "type": "string",
                    "description": "The exact prompt to send to the local LLM."
                },
                "model": {
                    "type": "string",
                    "description": "Optional local model to hit (e.g., 'llama3.2'). Defaults to the best available."
                }
            },
            "required": ["prompt"]
        }
    },
    {
        "name": "run_shell_command",
        "description": "Executes a shell command on the host machine. Extremely powerful for checking files, testing scripts, or querying DBs using CLI tools.",
        "parameters": {
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "description": "The shell command to execute."
                }
            },
            "required": ["command"]
        }
    }
]

def format_mcp_tools_for_prompt() -> str:
    """Returns a formatted JSON schema string of all available MCP tools."""
    return json.dumps(MCP_TOOLS, indent=2)

def execute_mcp_tool(tool_name: str, kwargs_json: str) -> str:
    """Executes a requested MCP tool and returns the observation result."""
    try:
        kwargs = json.loads(kwargs_json)
    except json.JSONDecodeError as e:
        return f"Error: Failed to parse tool arguments as JSON: {e}"

    if tool_name == "execute_local_inference":
        return _mcp_execute_local_inference(kwargs.get("prompt", ""), kwargs.get("model"))
    
    elif tool_name == "run_shell_command":
        return _mcp_run_shell_command(kwargs.get("command", ""))
    
    else:
        return f"Error: Unknown MCP tool '{tool_name}'"

# ---------------------------------------------------------------------------
# Tool Implementations
# ---------------------------------------------------------------------------

def _mcp_execute_local_inference(prompt: str, model: str = None) -> str:
    """Delegates a prompt to the local Ollama instance running on the GPU."""
    from scripts.llm_router import generate  # lazy import to avoid circular dependency
    
    print(f"\n[MCP] Delegating sub-task to local inference model...")
    # Temporarily override LLM provider to point strictly to ollama
    original_provider = os.environ.get("LLM_PROVIDER", "")
    os.environ["LLM_PROVIDER"] = "ollama"
    
    if model:
        original_model = os.environ.get("OLLAMA_MODEL", "")
        os.environ["OLLAMA_MODEL"] = model

    try:
        # We assume local inference doesn't need to loop back to MCP
        result = generate(prompt)
        return f"Local GPU Output:\n{result}"
    except Exception as e:
        return f"Local GPU Error: {e}"
    finally:
        os.environ["LLM_PROVIDER"] = original_provider
        if model:
            os.environ["OLLAMA_MODEL"] = original_model

def _mcp_run_shell_command(command: str) -> str:
    """Runs a shell command and returns the stdout/stderr."""
    print(f"\n[MCP] Running shell command: {command}")
    try:
        # Running in the current working directory, shell=True to allow pipes etc
        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=60 # Prevent hanging forever
        )
        
        output = result.stdout
        if result.stderr:
            output += "\n--- STDERR ---\n" + result.stderr
            
        if not output.strip():
            output = "Command executed successfully with no output."
            
        return output
    except subprocess.TimeoutExpired:
        return "Error: Command timed out after 60 seconds."
    except Exception as e:
        return f"Error executing command: {e}"

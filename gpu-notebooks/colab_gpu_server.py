# 🚀 AI TDD Orchestrator - Free GPU Server (Google Colab)
#
# This notebook turns a free Google Colab T4 GPU into an Ollama API server.
# Once running, your GitHub Actions pipeline automatically uses this GPU
# instead of slow CPU inference.
#
# Steps:
#   1. Open this notebook in Google Colab (Runtime > Change runtime > T4 GPU)
#   2. Run all cells (Runtime > Run all)
#   3. Copy the ngrok URL printed at the end
#   4. Add it as `COLAB_OLLAMA_URL` secret in your GitHub repo
#   5. That's it! Your pipeline now uses a free T4 GPU!

# %% [markdown]
# ## Cell 1: Install Ollama + ngrok

# %%
# Install Ollama
!curl -fsSL https://ollama.com/install.sh | sh

# Install ngrok for tunneling
!pip install pyngrok -q

# %% [markdown]
# ## Cell 2: Start Ollama Server

# %%
import subprocess, time

# Start Ollama in background
process = subprocess.Popen(
    ["ollama", "serve"],
    stdout=subprocess.DEVNULL,
    stderr=subprocess.DEVNULL,
)
time.sleep(5)
print("✅ Ollama server started!")

# %% [markdown]
# ## Cell 3: Pull the AI Coding Model

# %%
# Pull the optimal model for code generation (7B fits in T4's 15GB VRAM)
!ollama pull qwen2.5-coder:7b

# Verify it works
!curl -s http://localhost:11434/api/tags | python3 -c "import sys,json; d=json.load(sys.stdin); print('✅ Models loaded:', [m['name'] for m in d.get('models',[])])"

# %% [markdown]
# ## Cell 4: Expose via ngrok Tunnel
#
# **Copy the URL printed below and add it as a GitHub secret called `COLAB_OLLAMA_URL`**

# %%
from pyngrok import ngrok
import os

# Set your ngrok auth token (get free at https://dashboard.ngrok.com)
# Either set it here or via Colab secrets
NGROK_TOKEN = os.getenv("NGROK_TOKEN", "")  # Add your token here

if NGROK_TOKEN:
    ngrok.set_auth_token(NGROK_TOKEN)

# Create tunnel
tunnel = ngrok.connect(11434)
public_url = tunnel.public_url

print("\n" + "=" * 60)
print("🎉 YOUR FREE GPU OLLAMA SERVER IS LIVE!")
print("=" * 60)
print(f"\n🌐 Public URL: {public_url}")
print(f"\n📋 Add this as GitHub Secret:")
print(f"   Secret Name:  COLAB_OLLAMA_URL")
print(f"   Secret Value: {public_url}")
print(f"\n💡 Or set in workflow:")
print(f"   OLLAMA_URL: {public_url}/api/generate")
print(f"\n⏰ This server stays alive as long as this Colab tab is open.")
print(f"   Free tier: ~12 hours max per session, 15-30 GPU hrs/week")
print("=" * 60)

# %% [markdown]
# ## Cell 5: Keep Alive (run this to prevent Colab timeout)

# %%
import time
from IPython.display import clear_output

print(f"🖥️ GPU Server running at: {public_url}")
print("Press Stop (⏹) to shut down.\n")

counter = 0
while True:
    counter += 1
    # Send a lightweight health check every 60 seconds
    !curl -s http://localhost:11434/api/tags > /dev/null
    time.sleep(60)
    if counter % 5 == 0:
        print(f"💚 Still alive ({counter} minutes) | URL: {public_url}")

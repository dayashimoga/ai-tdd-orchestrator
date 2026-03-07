# GPU & Environment Configuration Guide

Complete step-by-step guide for configuring the AI TDD Orchestrator, including all GPU platforms, GitHub secrets, and environment variables.

---

## 1. GitHub Repository Secrets

Navigate to **Settings → Secrets and variables → Actions → New repository secret** in your orchestrator repo.

### Required Secrets

| Secret Name | Purpose | Example Value |
|---|---|---|
| `TARGET_REPO_TOKEN` | GitHub PAT with `repo` scope for creating/pushing to target repos | `ghp_xxxxxxxxxxxx` |

### Optional: GPU Platform Secrets

Set **one or more** of these to route LLM inference to a free GPU. The pipeline tries them in priority order and **automatically falls back** to the next if one is down.

| Priority | Secret Name | Platform | Free GPU Hours | GPU Hardware |
|---|---|---|---|---|
| 1 | `COLAB_OLLAMA_URL` | Google Colab | ~15-30 hrs/week | NVIDIA T4 (15GB) |
| 2 | `KAGGLE_OLLAMA_URL` | Kaggle Kernels | 30 hrs/week | NVIDIA P100 (16GB) |
| 3 | `LIGHTNING_OLLAMA_URL` | Lightning.ai | 22 hrs/month | T4/A10G |
| 4 | `SAGEMAKER_OLLAMA_URL` | AWS SageMaker Lab | ~4 hrs/session | NVIDIA T4 (15GB) |
| 5 | `PAPERSPACE_OLLAMA_URL` | Gradient/Paperspace | Limited free tier | Various |
| 6 | `ORACLE_OLLAMA_URL` | Oracle Cloud Always-Free | Unlimited (if available) | NVIDIA A10 (24GB) |
| — | `VASTAI_OLLAMA_URL` | Vast.ai (Paid) | Pay-per-use | RTX 3090/4090 (24GB) |
| — | `RUNPOD_OLLAMA_URL` | RunPod (Paid) | Pay-per-use | A40/A100 (48-80GB) |
| — | `CUSTOM_OLLAMA_URL` | Any custom endpoint | — | User-defined |
| — | `OLLAMA_URL` | Direct override | — | Skips auto-detection |

### Other Optional Secrets

| Secret Name | Purpose | Default |
|---|---|---|
| `GPU_PLATFORM` | Force a specific platform (skip auto-detect) | `auto` |
| `OLLAMA_MODEL` | Override the model used for code generation | Auto-selected by RAM |
| `OLLAMA_NUM_CTX` | Context window size (tokens) | `8192` |

---

## 2. GPU Platform Setup (Step-by-Step)

### Platform A: Google Colab (Recommended Starter)

**Free Tier:** ~15-30 GPU hours/week, T4 GPU (15GB VRAM)

1. Get a **free ngrok account** at [dashboard.ngrok.com](https://dashboard.ngrok.com) and copy your auth token
2. Open [Google Colab](https://colab.research.google.com)
3. Click **File → Upload notebook** → upload `gpu-notebooks/colab_gpu_server.ipynb`
4. Select **Runtime → Change runtime type → T4 GPU**
5. Click **Runtime → Run all**
6. In **Cell 4**, paste your ngrok auth token in the `NGROK_TOKEN` variable
7. Copy the printed public URL (e.g., `https://abc123.ngrok-free.app`)
8. Add as GitHub secret: **Name:** `COLAB_OLLAMA_URL` → **Value:** the URL

> **Note:** Keep the Colab tab open with Cell 5 (keep-alive) running while the pipeline executes. Free tier gives ~4-12 hours per session.

---

### Platform B: Kaggle Kernels (Best Free Quota)

**Free Tier:** 30 GPU hours/week, P100 GPU (16GB VRAM)

**Prerequisites:** Phone verification required at [kaggle.com/settings](https://www.kaggle.com/settings)

1. Go to [kaggle.com/code](https://www.kaggle.com/code) → **New Notebook**
2. Click **File → Import Notebook** → upload `gpu-notebooks/kaggle_gpu_server.ipynb`
3. Go to **Settings (gear icon)** → **Accelerator → GPU P100**
4. Run all cells
5. In **Cell 3**, paste your ngrok auth token
6. Copy the printed public URL
7. Add as GitHub secret: **Name:** `KAGGLE_OLLAMA_URL` → **Value:** the URL

> **Note:** If GPU options are greyed out, verify your phone number first at [kaggle.com/settings](https://www.kaggle.com/settings).

---

### Platform C: Lightning.ai

**Free Tier:** 22 GPU hours/month, T4/A10G

1. Sign up at [lightning.ai](https://lightning.ai)
2. Create a new **Studio** with GPU runtime
3. Open a terminal and run:
   ```bash
   curl -fsSL https://ollama.com/install.sh | sh
   OLLAMA_HOST=0.0.0.0 ollama serve &
   sleep 5
   ollama pull qwen2.5-coder:7b
   pip install pyngrok
   python -c "from pyngrok import ngrok; ngrok.set_auth_token('YOUR_TOKEN'); t=ngrok.connect(11434); print(t.public_url)"
   ```
4. Copy the URL and add as GitHub secret: `LIGHTNING_OLLAMA_URL`

---

### Platform D: Amazon SageMaker Studio Lab

**Free Tier:** Free T4 GPU, ~4 hours per session, no credit card required

1. Sign up at [studiolab.sagemaker.aws](https://studiolab.sagemaker.aws) (approval may take 1-5 days)
2. Launch a **GPU runtime**
3. Open a terminal and run the same commands as Lightning.ai above
4. Add the URL as GitHub secret: `SAGEMAKER_OLLAMA_URL`

---

### Platform E: Oracle Cloud (Always-Free A10)

**Free Tier:** Always-free VM with A10 GPU (24GB VRAM) — limited regional availability

1. Sign up at [cloud.oracle.com](https://cloud.oracle.com) (free tier, credit card required for verification only)
2. Create a **VM.GPU.A10.1** compute instance (check availability in your region)
3. SSH into the instance:
   ```bash
   curl -fsSL https://ollama.com/install.sh | sh
   OLLAMA_HOST=0.0.0.0 ollama serve &
   sleep 5
   ollama pull qwen2.5-coder:14b  # A10 can run 14b!
   ```
4. Open firewall port 11434 in the Oracle Cloud security list
5. Add as GitHub secret: `ORACLE_OLLAMA_URL` → `http://YOUR_PUBLIC_IP:11434`

> **Best option if available** — always-on, no session limits, and A10 can run the 14b model for best code quality.

---

### Platform F: Gradient by Paperspace

**Free Tier:** Free GPU notebooks with limited hours

1. Sign up at [gradient.run](https://gradient.run)
2. Create a new notebook with free GPU
3. Follow the same Ollama + ngrok setup as above
4. Add as GitHub secret: `PAPERSPACE_OLLAMA_URL`

---

### Paid Options (Low Cost)

#### Vast.ai ($0.15-0.30/hr)
1. Sign up at [vast.ai](https://vast.ai), add $5 credit
2. Search for **RTX 3090** instances → Deploy **ollama/ollama** Docker image
3. SSH in: `ollama pull qwen2.5-coder:7b`
4. Add as GitHub secret: `VASTAI_OLLAMA_URL` → `http://INSTANCE_IP:11434`

#### RunPod ($0.39/hr)
1. Sign up at [runpod.io](https://runpod.io)
2. Deploy a **Serverless** endpoint with Ollama template
3. Add as GitHub secret: `RUNPOD_OLLAMA_URL`

---

## 3. Failover Behavior

When multiple GPU secrets are configured, the pipeline performs **health checks** and automatically fails over:

```
Pipeline starts
  → Tries COLAB_OLLAMA_URL (priority 1)... Health check passes → Uses Colab
  
If Colab is DOWN (expired/disconnected):
  → Tries KAGGLE_OLLAMA_URL (priority 2)... UP → Uses Kaggle

If both Colab AND Kaggle are DOWN:
  → Tries LIGHTNING_OLLAMA_URL (priority 3)... etc.

If ALL remote GPUs are DOWN:
  → Falls back to local Ollama on the GitHub runner (CPU inference)
```

**Combined free GPU time** with all platforms configured: **~70-100+ hours/week**.

---

## 4. Model Recommendations

| GPU VRAM | Recommended Model | Set via `OLLAMA_MODEL` secret | Quality |
|---|---|---|---|
| CPU only (no GPU) | `qwen2.5-coder:3b` | Auto-selected | Basic |
| 8GB | `qwen2.5-coder:7b` | `qwen2.5-coder:7b` | Good |
| 15-16GB (T4/P100) | `qwen2.5-coder:7b` | `qwen2.5-coder:7b` | **Sweet spot** |
| 24GB (A10/RTX 3090) | `qwen2.5-coder:14b` | `qwen2.5-coder:14b` | Great |
| 48GB+ (A100) | `qwen2.5-coder:32b` | `qwen2.5-coder:32b` | Excellent |

---

## 5. Environment Variables Reference

All configurable via GitHub secrets or workflow `env:` block:

| Variable | Purpose | Default |
|---|---|---|
| `OLLAMA_URL` | Direct Ollama API endpoint (overrides auto-detect) | Auto-detected |
| `OLLAMA_MODEL` | Model to use for code generation | Auto-selected by RAM |
| `OLLAMA_NUM_CTX` | Context window token limit | `8192` |
| `GPU_PLATFORM` | Force a platform: `colab`, `kaggle`, `auto`, etc. | `auto` |
| `TARGET_REPO` | Target repository (`user/repo`) | Workflow input |
| `PROJECT_TYPE` | `new` (create repo) or `existing` (clone repo) | Workflow input |
| `TARGET_REPO_TOKEN` | PAT for target repo operations | `GITHUB_TOKEN` |
| `GITHUB_TOKEN` | Auto-provided by GitHub Actions | Auto |
| `LOCAL_MODE` | Set to `true` for local Docker execution | `false` |
| `USER_HINT` | Human guidance for `--resume-with-hint` | From PR comment |

---

## 6. Verification

### Test GPU Connection Locally
```bash
python scripts/gpu_platform.py
```
Output:
```
[GPU] Trying Google Colab (T4 via ngrok)...
[GPU] Connected: Google Colab (T4 via ngrok) (NVIDIA T4 (15GB))
Selected: colab -> https://abc123.ngrok-free.app/api/generate
```

### Test From GitHub Actions
Trigger the workflow and check the logs. You should see:
```
[GPU] Trying Google Colab (T4 via ngrok)...
[GPU] Connected: Google Colab (T4 via ngrok) (NVIDIA T4 (15GB))
```

# Free Resources Guide — AI TDD Orchestrator

Complete reference for all free compute resources, credits, quotas, and configuration.

---

## ⚡ Quick Start: You're 1 Secret Away

You already have `GROQ_API_KEY` and `CEREBRAS_API_KEY` in GitHub Actions. **Add one more secret:**

```
Secret Name:  LLM_PROVIDER
Secret Value: groq
```

**That's it.** Your CI will now use Groq's free Llama 70B at ~500 tok/s instead of Ollama. No GPU, no model downloads, no setup time saved = **~3 min/run**.

To switch to Cerebras (faster, Llama 3.1 70B at ~2000 tok/s):
```
LLM_PROVIDER = cerebras
```

---

## Free LLM APIs (No GPU Required)

| Provider | How to Get Key | Default Model | Speed | Free Limit | Best For |
|----------|---------------|---------------|-------|-----------|----------|
| **Groq** | [console.groq.com](https://console.groq.com) | `llama-3.3-70b-versatile` | ~500 tok/s | 30 req/min, 14,400 req/day | General use, daily CI |
| **Cerebras** | [cloud.cerebras.ai](https://cloud.cerebras.ai) | `llama3.1-70b` | ~2,000 tok/s | Rate-limited | Max speed |

### GitHub Secrets Required
| Secret | Value | Status |
|--------|-------|:------:|
| `GROQ_API_KEY` | `gsk_xxx...` | ✅ Set |
| `CEREBRAS_API_KEY` | `csk_xxx...` | ✅ Set |
| `LLM_PROVIDER` | `groq` or `cerebras` | ⬜ **Set this!** |

### Local Usage
```bash
# Groq
export LLM_PROVIDER=groq
export GROQ_API_KEY=gsk_your_key
python scripts/ai_pipeline.py --manual

# Cerebras
export LLM_PROVIDER=cerebras
export CEREBRAS_API_KEY=your_key
python scripts/ai_pipeline.py --manual
```

### Available Models

**Groq Free Models:**
| Model | Params | Context | Best For |
|-------|--------|---------|----------|
| `llama-3.3-70b-versatile` | 70B | 128K | Code generation (default) |
| `llama-3.1-8b-instant` | 8B | 128K | Fast, simple tasks |
| `mixtral-8x7b-32768` | 47B | 32K | Long context reasoning |
| `gemma2-9b-it` | 9B | 8K | Lightweight tasks |

**Cerebras Free Models:**
| Model | Params | Speed | Best For |
|-------|--------|-------|----------|
| `llama3.1-70b` | 70B | 2,000 tok/s | Max quality + speed |
| `llama3.1-8b` | 8B | 4,000 tok/s | Ultra-fast simple tasks |

---

## Free GPU Platforms (Ollama-based)

For when you want to run Ollama with custom/fine-tuned models:

### Tier 1: Free Forever (Unlimited)

| Platform | GPU | VRAM | Session Length | Weekly Limit | Setup |
|----------|-----|------|---------------|:------------:|-------|
| **Google Colab** | T4 | 15 GB | 4-12 hrs | Unlimited | [Notebook](../gpu-notebooks/colab_ollama.ipynb) |

**How to use:**
1. Open `gpu-notebooks/colab_ollama.ipynb` in Colab
2. Runtime → Change runtime type → **T4 GPU**
3. Set `NGROK_AUTH_TOKEN` (free at [ngrok.com](https://ngrok.com))
4. Run all cells → copy the ngrok URL
5. Add as `COLAB_OLLAMA_URL` GitHub Secret

### Tier 2: Free with Weekly/Monthly Quotas

| Platform | GPU | VRAM | Free Quota | Signup |
|----------|-----|------|-----------|--------|
| **Kaggle** | P100/T4 | 16 GB | 30 hrs/week | [kaggle.com](https://www.kaggle.com) |
| **Saturn Cloud** | T4 | 15 GB | 30 hrs/month | [saturncloud.io](https://saturncloud.io) |
| **Lightning.ai** | T4/A10G | 15-24 GB | 22 hrs/month | [lightning.ai](https://lightning.ai) |
| **SageMaker Studio Lab** | T4 | 15 GB | ~4 hrs/session | [studiolab.sagemaker.aws](https://studiolab.sagemaker.aws) |
| **HuggingFace Spaces** | T4 (shared) | Shared | Public spaces | [huggingface.co](https://huggingface.co/spaces) |

### Tier 3: Free CPU Fallbacks

| Platform | CPU | RAM | Free Quota | Use Case |
|----------|-----|-----|-----------|----------|
| **Google Cloud Shell** | e2-small | 2 GB | 50 hrs/week | Lightweight tasks, `qwen2.5-coder:1.5b` |
| **GitHub Codespaces** | 4-core | 16 GB | 60 core-hrs/month | Can run `qwen2.5-coder:3b` on CPU |

---

## Oracle Cloud (Your Credits)

| Detail | Value |
|--------|-------|
| **Credits Remaining** | ~SGD 400 |
| **Expiry** | April 5, 2026 |
| **GPU Available** | NVIDIA A10 (24 GB VRAM) |
| **Cost** | ~SGD 1.35/hr |
| **Auto-Provision** | `python scripts/gpu_scheduler.py --provision` |
| **Auto-Destroy** | VM self-shuts after 2 hrs (configurable) |

### Terraform Setup (One-time)
```bash
cd infra/oracle
cp example.tfvars terraform.tfvars
# Edit: set compartment_id, ssh_public_key, alert_email
terraform init
```

### Each Session
```bash
./budget_check.sh              # Verify credits
terraform apply -auto-approve   # Creates GPU VM (~3 min)
# Copy OLLAMA_URL from output
terraform destroy -auto-approve # STOP BILLING
```

### Budget Protection (5 Layers)
| Layer | Mechanism | Status |
|-------|-----------|:------:|
| Pre-apply credit check | `budget_check.sh` blocks if < SGD 50 | ✅ |
| VM auto-shutdown | Cloud-init timer (2 hrs default) | ✅ |
| Local auto-destroy | `auto_destroy.sh` runs `terraform destroy` | ✅ |
| Resource tagging | `project=ai-tdd-orchestrator` on all resources | ✅ |
| Budget alerts | Email at 50%, 75%, 90% (Terraform) | ✅ |

> ⚠️ **NEVER upgrade to Pay-As-You-Go.** Free trial = no charges after credits expire.

---

## Smart Platform Scheduler

Automatically selects the best available platform:

```bash
python scripts/gpu_scheduler.py --status      # Dashboard
python scripts/gpu_scheduler.py               # Auto-select
python scripts/gpu_scheduler.py --provision   # Auto terraform apply
python scripts/gpu_scheduler.py --destroy     # Instant cleanup
```

**Priority Order:**
```
Colab → Kaggle → Lightning → HuggingFace → SageMaker →
Saturn → Oracle →
Groq API → Cerebras API →
Cloud Shell → Codespaces →
Local Ollama
```

---

## Environment Variables Reference

### LLM Provider Selection
| Variable | Values | Default |
|----------|--------|---------|
| `LLM_PROVIDER` | `ollama`, `openai`, `anthropic`, `gemini`, `groq`, `cerebras` | `ollama` |

### API Keys
| Variable | Provider | Get Key At |
|----------|----------|-----------|
| `GROQ_API_KEY` | Groq | [console.groq.com](https://console.groq.com) |
| `CEREBRAS_API_KEY` | Cerebras | [cloud.cerebras.ai](https://cloud.cerebras.ai) |
| `OPENAI_API_KEY` | OpenAI | [platform.openai.com](https://platform.openai.com) |
| `ANTHROPIC_API_KEY` | Anthropic | [console.anthropic.com](https://console.anthropic.com) |
| `GOOGLE_API_KEY` | Gemini | [aistudio.google.com](https://aistudio.google.com) |

### Platform URLs (Ollama endpoints)
| Variable | Platform |
|----------|----------|
| `COLAB_OLLAMA_URL` | Google Colab (via ngrok) |
| `KAGGLE_OLLAMA_URL` | Kaggle (via ngrok) |
| `ORACLE_OLLAMA_URL` | Oracle Cloud |
| `SATURN_OLLAMA_URL` | Saturn Cloud |
| `LIGHTNING_OLLAMA_URL` | Lightning.ai |
| `HF_OLLAMA_URL` | HuggingFace Spaces |
| `SAGEMAKER_OLLAMA_URL` | SageMaker Studio Lab |
| `CODESPACES_OLLAMA_URL` | GitHub Codespaces |
| `CLOUDSHELL_OLLAMA_URL` | Google Cloud Shell |

### Model Selection
| Variable | Provider | Default |
|----------|----------|---------|
| `GROQ_MODEL` | Groq | `llama-3.3-70b-versatile` |
| `CEREBRAS_MODEL` | Cerebras | `llama3.1-70b` |
| `OLLAMA_MODEL` | Ollama | `qwen2.5-coder:3b` |
| `OPENAI_MODEL` | OpenAI | `gpt-4o-mini` |
| `ANTHROPIC_MODEL` | Anthropic | `claude-3-haiku-20240307` |
| `GOOGLE_MODEL` | Gemini | `gemini-1.5-flash` |

---

## Recommended Strategy

### For CI (GitHub Actions) — Use Groq
- Zero setup cost, no model downloads
- 30 req/min is plenty for CI runs
- Saves ~3 min per run vs installing Ollama

### For Heavy Development — Use Colab + Kaggle
- Run notebooks, get ngrok URL, set as secret
- 30+ free GPU hours per week combined

### For Max Power — Use Oracle Cloud
- A10 GPU with 24GB VRAM
- Auto-provisions via Terraform
- Use only when Groq rate limits hit

### Monthly Free Compute Budget

| Source | Hours | GPU | Value |
|--------|-------|-----|-------|
| Groq API | Unlimited* | LPU cloud | ~$0 |
| Cerebras API | Unlimited* | WSE cloud | ~$0 |
| Colab | ~50-100 | T4 | ~$50-100 |
| Kaggle | 120 (30/wk) | P100/T4 | ~$120 |
| Saturn | 30 | T4 | ~$30 |
| Lightning | 22 | T4/A10G | ~$22 |
| Oracle | ~10 (conserving) | A10 | ~SGD 14 |
| **Total** | **230+ GPU hrs** | | **~$322/month value** |

*Rate-limited, not hour-limited

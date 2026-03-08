# GPU Setup Guide — AI TDD Orchestrator

Complete guide to setting up free GPU resources for the AI TDD Orchestrator.

## Platform Overview

### Free GPU Platforms (Ollama-compatible)

| Platform | GPU | Free Limit | Setup Effort |
|----------|-----|-----------|--------------|
| **Google Colab** | T4 (15GB) | Unlimited sessions, ~4-12 hrs each | ⭐ Easy |
| **Kaggle** | P100/T4 (16GB) | 30 GPU hrs/week | ⭐ Easy |
| **Saturn Cloud** | T4 (15GB) | 30 GPU hrs/month | ⭐⭐ Medium |
| **Lightning.ai** | T4/A10G | 22 GPU hrs/month | ⭐⭐ Medium |
| **HuggingFace Spaces** | T4 (shared) | Free for public spaces | ⭐⭐ Medium |
| **SageMaker Studio Lab** | T4 (15GB) | ~4 hrs/session, no CC needed | ⭐⭐ Medium |
| **Oracle Cloud** | A10 (24GB) | SGD 400 trial credits | ⭐⭐⭐ Setup needed |

### Free LLM APIs (No Ollama needed — direct API)

| Platform | Models | Free Limit | Speed |
|----------|--------|-----------|-------|
| **Groq** | Llama 3, Mixtral, Gemma | 30 req/min, 14,400 req/day | ~500 tok/s |
| **Cerebras** | Llama 3.1 70B | Free tier, rate-limited | ~2,000 tok/s |

### Free CPU-Only Fallbacks

| Platform | vCPUs/RAM | Free Limit |
|----------|-----------|-----------|
| **Google Cloud Shell** | e2-small (0.5 vCPU, 2GB) | 50 hrs/week, 5GB persistent |
| **GitHub Codespaces** | Up to 4 cores, 16GB RAM | 60 core-hours/month |

---

## Quick Start

### 1. Google Colab (Recommended — easiest)

```
1. Open gpu-notebooks/colab_ollama.ipynb in Google Colab
2. Runtime → Change runtime type → T4 GPU
3. Set NGROK_AUTH_TOKEN (get free at https://ngrok.com)
4. Run all cells
5. Copy the COLAB_OLLAMA_URL output
6. Set as environment variable or GitHub Secret
```

### 2. Kaggle (30 free GPU hrs/week)

```
1. Upload gpu-notebooks/kaggle_ollama.ipynb to Kaggle
2. Settings → Accelerator → GPU T4 x2
3. Set NGROK_AUTH_TOKEN
4. Run all cells
5. Copy the KAGGLE_OLLAMA_URL output
```

### 3. Oracle Cloud (A10 GPU via Terraform)

```bash
# One-time setup
cd infra/oracle
cp example.tfvars terraform.tfvars
# Edit terraform.tfvars with your compartment_id

# Each session
./budget_check.sh          # Verify credits
terraform init
terraform apply -auto-approve
# Use the OLLAMA_URL output
# VM auto-shuts down after 2 hours

# Manual cleanup
terraform destroy -auto-approve
```

#### Budget Setup (Terraform-automated)
Set these in `terraform.tfvars`:
```hcl
create_budget  = true
tenancy_ocid   = "ocid1.tenancy.oc1..your_tenancy_id"
budget_amount  = 50       # USD per month
alert_email    = "your@email.com"
```

Terraform creates budget alerts at **50%**, **75%**, and **90%** automatically.

All resources are tagged with `project = ai-tdd-orchestrator` for budget filtering.

### 4. Groq API (Free, ultra-fast inference)

```bash
# Get free API key at https://console.groq.com
export GROQ_API_KEY="gsk_your_key_here"
export LLM_PROVIDER="groq"
```

No GPU needed — Groq runs inference on their LPU cloud at ~500 tokens/sec.

### 5. Cerebras API (Free, Llama 3.1 70B)

```bash
# Get free API key at https://cloud.cerebras.ai
export CEREBRAS_API_KEY="your_key_here"
export LLM_PROVIDER="cerebras"
```

---

## Smart Scheduler

Auto-selects the best available platform:

```bash
# Show all platform status
python scripts/gpu_scheduler.py --status

# Auto-select best free platform
python scripts/gpu_scheduler.py

# Auto-provision Oracle if needed
python scripts/gpu_scheduler.py --provision

# Destroy Oracle resources
python scripts/gpu_scheduler.py --destroy
```

**Priority**: Colab → Kaggle → Lightning → HuggingFace → SageMaker → Saturn → Oracle → Groq → Cerebras → Cloud Shell → Codespaces → Local

---

## Credit Protection (Oracle Cloud)

| Layer | Mechanism | Automated? |
|-------|-----------|:----------:|
| Budget alerts (50/75/90%) | Terraform `oci_budget_budget` | ✅ |
| Resource tagging | `freeform_tags` on all resources | ✅ |
| VM auto-shutdown | Cloud-init timer (default: 2 hrs) | ✅ |
| Local auto-destroy | `auto_destroy.sh` runs `terraform destroy` | ✅ |
| Pre-apply credit check | `budget_check.sh` blocks if low | ✅ |
| Free trial safety | No charges after credits expire | ✅ |

> **⚠️ NEVER upgrade your Oracle account to Pay-As-You-Go.** Keep it as Free Tier trial.

---

## Environment Variables Reference

| Variable | Platform | Example |
|----------|----------|---------|
| `COLAB_OLLAMA_URL` | Google Colab | `https://abc123.ngrok.io` |
| `KAGGLE_OLLAMA_URL` | Kaggle | `https://def456.ngrok.io` |
| `ORACLE_OLLAMA_URL` | Oracle Cloud | `http://1.2.3.4:11434` |
| `SATURN_OLLAMA_URL` | Saturn Cloud | `https://saturn.ngrok.io` |
| `LIGHTNING_OLLAMA_URL` | Lightning.ai | `https://lit.ngrok.io` |
| `HF_OLLAMA_URL` | HuggingFace | `https://hf-space.ngrok.io` |
| `GROQ_API_KEY` | Groq (direct API) | `gsk_xxxx` |
| `CEREBRAS_API_KEY` | Cerebras (direct API) | `csk_xxxx` |
| `LLM_PROVIDER` | Provider selector | `ollama\|openai\|groq\|cerebras` |

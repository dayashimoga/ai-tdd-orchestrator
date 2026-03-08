# ============================================================
# Example Terraform Variables — Copy to terraform.tfvars
# ============================================================
# cp example.tfvars terraform.tfvars
# Edit terraform.tfvars with your values
# ============================================================

compartment_id = "ocid1.compartment.oc1..your_compartment_id"
region         = "ap-singapore-1"
ssh_public_key = "ssh-rsa AAAA... your_key"

# GPU Configuration
gpu_shape     = "VM.GPU.A10.1"  # 24GB VRAM, ~$1/hr
ollama_model  = "qwen2.5-coder:7b"

# Credit Protection
max_hours        = 2    # Auto-shutdown after 2 hours
budget_limit_sgd = 50   # Block provisioning if credits < SGD 50

# Security — RESTRICT TO YOUR IP
allowed_cidr = "0.0.0.0/0"  # Change to "YOUR.IP.ADDR.ESS/32"

# Budget & Alerts (optional but recommended)
tenancy_ocid  = "ocid1.tenancy.oc1..your_tenancy_id"
create_budget = true      # Set to true to auto-create budget with alerts
budget_amount = 50        # Monthly budget in USD
alert_email   = "dayashm@gmail.com"  # Budget alert recipient

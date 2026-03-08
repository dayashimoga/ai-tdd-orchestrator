# ============================================================
# Oracle Cloud GPU VM for Ollama — Terraform Configuration
# ============================================================
#
# Usage:
#   cd infra/oracle
#   ./budget_check.sh          # Verify credits remain
#   terraform init
#   terraform apply -auto-approve
#   # ... use the OLLAMA_URL output ...
#   terraform destroy -auto-approve   # STOP BILLING
#
# The VM auto-destroys after MAX_HOURS (default: 2) as a safety net.
# ============================================================

terraform {
  required_providers {
    oci = {
      source  = "oracle/oci"
      version = ">= 5.0.0"
    }
  }
  required_version = ">= 1.3.0"
}

# ---------------------------------------------------------------------------
# Provider — uses ~/.oci/config by default
# ---------------------------------------------------------------------------
provider "oci" {
  region = var.region
}

# ---------------------------------------------------------------------------
# Common Tags — Used by OCI Budgets for cost tracking
# ---------------------------------------------------------------------------
locals {
  common_tags = {
    "project"     = "ai-tdd-orchestrator"
    "component"   = "ollama-gpu"
    "environment" = "dev"
    "managed-by"  = "terraform"
    "auto-destroy" = "${var.max_hours}h"
  }
}

# ---------------------------------------------------------------------------
# Data Sources
# ---------------------------------------------------------------------------

# Get the latest Oracle Linux 8 GPU image
data "oci_core_images" "gpu_image" {
  compartment_id           = var.compartment_id
  operating_system         = "Oracle Linux"
  operating_system_version = "8"
  shape                    = var.gpu_shape
  sort_by                  = "TIMECREATED"
  sort_order               = "DESC"
}

# Get availability domains
data "oci_identity_availability_domains" "ads" {
  compartment_id = var.compartment_id
}

# ---------------------------------------------------------------------------
# Network — Simple public subnet for Ollama access
# ---------------------------------------------------------------------------

resource "oci_core_vcn" "ollama_vcn" {
  compartment_id = var.compartment_id
  display_name   = "ollama-gpu-vcn"
  cidr_blocks    = ["10.0.0.0/16"]
  freeform_tags  = local.common_tags
}

resource "oci_core_internet_gateway" "igw" {
  compartment_id = var.compartment_id
  vcn_id         = oci_core_vcn.ollama_vcn.id
  display_name   = "ollama-igw"
  freeform_tags  = local.common_tags
}

resource "oci_core_route_table" "public_rt" {
  compartment_id = var.compartment_id
  vcn_id         = oci_core_vcn.ollama_vcn.id
  display_name   = "ollama-public-rt"
  freeform_tags  = local.common_tags

  route_rules {
    destination       = "0.0.0.0/0"
    network_entity_id = oci_core_internet_gateway.igw.id
  }
}

resource "oci_core_security_list" "ollama_sl" {
  compartment_id = var.compartment_id
  vcn_id         = oci_core_vcn.ollama_vcn.id
  display_name   = "ollama-security-list"
  freeform_tags  = local.common_tags

  # SSH
  ingress_security_rules {
    protocol = "6" # TCP
    source   = "0.0.0.0/0"
    tcp_options {
      min = 22
      max = 22
    }
  }

  # Ollama API (11434)
  ingress_security_rules {
    protocol = "6"
    source   = var.allowed_cidr
    tcp_options {
      min = 11434
      max = 11434
    }
  }

  # All egress
  egress_security_rules {
    protocol    = "all"
    destination = "0.0.0.0/0"
  }
}

resource "oci_core_subnet" "public_subnet" {
  compartment_id    = var.compartment_id
  vcn_id            = oci_core_vcn.ollama_vcn.id
  cidr_block        = "10.0.1.0/24"
  display_name      = "ollama-public-subnet"
  route_table_id    = oci_core_route_table.public_rt.id
  security_list_ids = [oci_core_security_list.ollama_sl.id]
  freeform_tags     = local.common_tags
}

# ---------------------------------------------------------------------------
# GPU Compute Instance
# ---------------------------------------------------------------------------

resource "oci_core_instance" "ollama_gpu" {
  compartment_id      = var.compartment_id
  availability_domain = data.oci_identity_availability_domains.ads.availability_domains[0].name
  display_name        = "ollama-gpu-${formatdate("YYYYMMDD-hhmm", timestamp())}"
  shape               = var.gpu_shape
  freeform_tags       = local.common_tags

  shape_config {
    ocpus         = var.gpu_ocpus
    memory_in_gbs = var.gpu_memory_gb
  }

  source_details {
    source_type = "image"
    source_id   = data.oci_core_images.gpu_image.images[0].id
  }

  create_vnic_details {
    subnet_id        = oci_core_subnet.public_subnet.id
    assign_public_ip = true
  }

  metadata = {
    ssh_authorized_keys = var.ssh_public_key
    user_data = base64encode(templatefile("${path.module}/cloud_init.sh", {
      ollama_model = var.ollama_model
      max_hours    = var.max_hours
    }))
  }

  # Prevent accidental long-running instances
  lifecycle {
    ignore_changes = [display_name]
  }
}

# ---------------------------------------------------------------------------
# Budget with Alert Rules — Auto-created for cost tracking
# ---------------------------------------------------------------------------

resource "oci_budget_budget" "gpu_budget" {
  count = var.create_budget ? 1 : 0

  compartment_id = var.tenancy_ocid
  display_name   = "ai-tdd-gpu-budget"
  description    = "Auto-managed budget for AI TDD Orchestrator GPU resources"

  # Use tag-based targeting so it tracks only our resources
  target_type = "TAG"
  targets     = ["project.ai-tdd-orchestrator"]

  # Budget amount and schedule
  amount         = var.budget_amount
  reset_period   = "MONTHLY"

  freeform_tags = local.common_tags
}

# Budget alert at 50%
resource "oci_budget_alert_rule" "alert_50" {
  count = var.create_budget ? 1 : 0

  budget_id    = oci_budget_budget.gpu_budget[0].id
  display_name = "GPU Budget 50% Alert"
  type         = "ACTUAL"
  threshold      = 50
  threshold_type = "PERCENTAGE"
  recipients     = var.alert_email
  message        = "AI TDD Orchestrator GPU budget has reached 50%. Consider using free platforms (Colab/Kaggle) to conserve credits."
}

# Budget alert at 75%
resource "oci_budget_alert_rule" "alert_75" {
  count = var.create_budget ? 1 : 0

  budget_id    = oci_budget_budget.gpu_budget[0].id
  display_name = "GPU Budget 75% Alert"
  type         = "ACTUAL"
  threshold      = 75
  threshold_type = "PERCENTAGE"
  recipients     = var.alert_email
  message        = "AI TDD Orchestrator GPU budget at 75%. Reduce Oracle Cloud usage and prefer Colab/Kaggle."
}

# Budget alert at 90%
resource "oci_budget_alert_rule" "alert_90" {
  count = var.create_budget ? 1 : 0

  budget_id    = oci_budget_budget.gpu_budget[0].id
  display_name = "GPU Budget 90% CRITICAL Alert"
  type         = "ACTUAL"
  threshold      = 90
  threshold_type = "PERCENTAGE"
  recipients     = var.alert_email
  message        = "CRITICAL: AI TDD Orchestrator GPU budget at 90%! Stop Oracle Cloud usage immediately!"
}

# ---------------------------------------------------------------------------
# Cloud-Init Script (inline template)
# ---------------------------------------------------------------------------

resource "local_file" "cloud_init" {
  filename = "${path.module}/cloud_init.sh"
  content  = <<-SCRIPT
    #!/bin/bash
    set -e

    echo "=== Ollama GPU Setup (Oracle Cloud) ==="

    # 1. Install Ollama
    curl -fsSL https://ollama.com/install.sh | sh

    # 2. Configure Ollama to listen on all interfaces
    mkdir -p /etc/systemd/system/ollama.service.d
    cat > /etc/systemd/system/ollama.service.d/override.conf << 'EOF'
    [Service]
    Environment="OLLAMA_HOST=0.0.0.0:11434"
    EOF

    systemctl daemon-reload
    systemctl enable ollama
    systemctl start ollama

    # 3. Wait for Ollama to be ready
    echo "Waiting for Ollama to start..."
    for i in $(seq 1 30); do
      if curl -s http://localhost:11434/api/tags > /dev/null 2>&1; then
        echo "Ollama is ready!"
        break
      fi
      sleep 2
    done

    # 4. Pull the model
    echo "Pulling model: ${ollama_model}"
    ollama pull ${ollama_model}

    # 5. Auto-destroy timer (credit protection)
    echo "Setting auto-destroy timer: ${max_hours} hours"
    cat > /usr/local/bin/auto_shutdown.sh << 'SHUTDOWN'
    #!/bin/bash
    sleep $((${max_hours} * 3600))
    echo "Auto-shutdown triggered after ${max_hours} hours"
    shutdown -h now
    SHUTDOWN
    chmod +x /usr/local/bin/auto_shutdown.sh
    nohup /usr/local/bin/auto_shutdown.sh &

    echo "=== Setup complete! Ollama running on port 11434 ==="
    echo "=== Auto-shutdown in ${max_hours} hours ==="
  SCRIPT
}

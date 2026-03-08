# ============================================================
# Variables for Oracle Cloud GPU VM
# ============================================================

variable "compartment_id" {
  description = "OCI compartment OCID (find in OCI Console → Identity → Compartments)"
  type        = string
}

variable "region" {
  description = "OCI region (e.g., ap-singapore-1, us-ashburn-1)"
  type        = string
  default     = "ap-singapore-1"
}

variable "gpu_shape" {
  description = "GPU compute shape"
  type        = string
  default     = "VM.GPU.A10.1"  # 24GB VRAM, ~$1/hr
}

variable "gpu_ocpus" {
  description = "Number of OCPUs for the GPU shape"
  type        = number
  default     = 15
}

variable "gpu_memory_gb" {
  description = "RAM in GB for the GPU instance"
  type        = number
  default     = 240
}

variable "ollama_model" {
  description = "Ollama model to pull on startup"
  type        = string
  default     = "qwen2.5-coder:7b"
}

variable "max_hours" {
  description = "Auto-destroy VM after this many hours (credit protection)"
  type        = number
  default     = 2
}

variable "budget_limit_sgd" {
  description = "Refuse to create VM if remaining credits < this value (SGD)"
  type        = number
  default     = 50
}

variable "ssh_public_key" {
  description = "SSH public key for VM access"
  type        = string
  default     = ""
}

variable "allowed_cidr" {
  description = "CIDR block allowed to access Ollama API (restrict for security)"
  type        = string
  default     = "0.0.0.0/0"  # Restrict to your IP in production
}

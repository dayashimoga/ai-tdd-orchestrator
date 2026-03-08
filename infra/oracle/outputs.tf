# ============================================================
# Outputs — Use these to connect your pipeline
# ============================================================

output "gpu_instance_public_ip" {
  description = "Public IP of the GPU VM"
  value       = oci_core_instance.ollama_gpu.public_ip
}

output "ollama_url" {
  description = "Full Ollama API URL — set as ORACLE_OLLAMA_URL"
  value       = "http://${oci_core_instance.ollama_gpu.public_ip}:11434/api/generate"
}

output "ssh_command" {
  description = "SSH into the GPU VM"
  value       = "ssh opc@${oci_core_instance.ollama_gpu.public_ip}"
}

output "auto_destroy_hours" {
  description = "VM will auto-shutdown after this many hours"
  value       = var.max_hours
}

output "estimated_cost_sgd" {
  description = "Estimated cost for this session"
  value       = "~SGD ${format("%.2f", var.max_hours * 1.35)} (${var.max_hours} hours × ~SGD 1.35/hr)"
}

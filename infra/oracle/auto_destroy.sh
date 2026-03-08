#!/bin/bash
# ============================================================
# Auto-Destroy Script — Destroys Terraform resources after N hours
# ============================================================
# Run this on your LOCAL machine (not the VM) to auto-destroy
# the Oracle Cloud GPU VM after the pipeline finishes or times out.
#
# Usage:
#   ./auto_destroy.sh [max_hours] [terraform_dir]
#   ./auto_destroy.sh 2 .         # Destroy after 2 hours
#   ./auto_destroy.sh 1           # Destroy after 1 hour
#
# The VM also has an internal shutdown timer, but this script
# ensures the Terraform state is cleaned up too.
# ============================================================

set -e

MAX_HOURS=${1:-2}
TF_DIR=${2:-.}
MAX_SECONDS=$((MAX_HOURS * 3600))

echo "============================================"
echo "  Oracle Cloud Auto-Destroy Timer"
echo "============================================"
echo ""
echo "⏱️  Will destroy resources in: ${MAX_HOURS} hours"
echo "📁 Terraform directory: ${TF_DIR}"
echo "🔄 PID: $$"
echo ""
echo "To cancel: kill $$"
echo "============================================"
echo ""

# Function to destroy resources
destroy_resources() {
    echo ""
    echo "🔴 Auto-destroy triggered!"
    echo "🗑️  Running terraform destroy..."
    cd "$TF_DIR"
    terraform destroy -auto-approve 2>&1
    RESULT=$?
    if [ $RESULT -eq 0 ]; then
        echo "✅ All resources destroyed. Billing stopped."
    else
        echo "❌ Terraform destroy failed (exit code: $RESULT)"
        echo "⚠️  IMPORTANT: Manually destroy resources in OCI Console!"
        echo "   https://cloud.oracle.com/compute/instances"
    fi
    exit $RESULT
}

# Trap SIGTERM and SIGINT to destroy gracefully
trap destroy_resources SIGTERM SIGINT

# Wait for the specified duration
echo "💤 Sleeping for ${MAX_HOURS} hours (${MAX_SECONDS} seconds)..."
echo "   Started at: $(date)"
echo "   Will destroy at: $(date -d "+${MAX_HOURS} hours" 2>/dev/null || date -v+${MAX_HOURS}H 2>/dev/null || echo "in ${MAX_HOURS} hours")"
echo ""

sleep $MAX_SECONDS

# Time's up — destroy everything
destroy_resources

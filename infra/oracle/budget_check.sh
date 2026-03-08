#!/bin/bash
# ============================================================
# Oracle Cloud Budget Check — Run BEFORE terraform apply
# ============================================================
# Checks remaining credits and blocks provisioning if below threshold.
#
# Usage:
#   ./budget_check.sh [minimum_sgd]
#   ./budget_check.sh 50    # Block if < SGD 50 remaining
#
# Prerequisites:
#   - OCI CLI installed and configured (~/.oci/config)
#   - jq installed (sudo apt install jq / brew install jq)
# ============================================================

set -e

MINIMUM_CREDITS=${1:-50}  # Default: SGD 50 minimum
TENANCY_OCID=$(oci iam compartment list --include-root 2>/dev/null | jq -r '.data[0]."compartment-id"' 2>/dev/null || echo "")

echo "============================================"
echo "  Oracle Cloud Budget Check"
echo "============================================"
echo ""

# Check if OCI CLI is available
if ! command -v oci &> /dev/null; then
    echo "⚠️  OCI CLI not installed. Install: https://docs.oracle.com/en-us/iaas/Content/API/SDKDocs/cliinstall.htm"
    echo "⚠️  Skipping budget check — PROCEED WITH CAUTION"
    exit 0
fi

# Check if jq is available
if ! command -v jq &> /dev/null; then
    echo "⚠️  jq not installed. Install: sudo apt install jq / brew install jq"
    echo "⚠️  Skipping budget check — PROCEED WITH CAUTION"
    exit 0
fi

# Query subscription info
echo "📊 Querying Oracle Cloud subscription..."
SUBSCRIPTION_INFO=$(oci account subscription list 2>/dev/null || echo "")

if [ -z "$SUBSCRIPTION_INFO" ]; then
    echo "⚠️  Could not query subscription info. Check OCI CLI config."
    echo "⚠️  Skipping budget check — PROCEED WITH CAUTION"
    exit 0
fi

# Try to get the credit balance
# Note: This uses the Account Management API
BALANCE=$(echo "$SUBSCRIPTION_INFO" | jq -r '.data[0]."available-credit-amount" // "unknown"' 2>/dev/null || echo "unknown")
CURRENCY=$(echo "$SUBSCRIPTION_INFO" | jq -r '.data[0]."currency-code" // "SGD"' 2>/dev/null || echo "SGD")

if [ "$BALANCE" = "unknown" ] || [ "$BALANCE" = "null" ]; then
    echo "⚠️  Could not determine exact credit balance."
    echo "💡 Check manually: https://cloud.oracle.com/account-management/overview"
    echo ""
    read -p "Do you want to proceed anyway? (y/N): " PROCEED
    if [ "$PROCEED" != "y" ] && [ "$PROCEED" != "Y" ]; then
        echo "❌ Aborted. Check your credits first."
        exit 1
    fi
    exit 0
fi

echo "💰 Remaining credits: $CURRENCY $BALANCE"
echo "🛡️  Minimum threshold: $CURRENCY $MINIMUM_CREDITS"
echo ""

# Compare (using bc for floating point)
BELOW_THRESHOLD=$(echo "$BALANCE < $MINIMUM_CREDITS" | bc -l 2>/dev/null || echo "0")

if [ "$BELOW_THRESHOLD" = "1" ]; then
    echo "❌ BLOCKED: Credits ($CURRENCY $BALANCE) are below minimum ($CURRENCY $MINIMUM_CREDITS)"
    echo "❌ Will NOT provision GPU VM to protect remaining credits."
    echo ""
    echo "Options:"
    echo "  1. Use Google Colab or Kaggle instead (free)"
    echo "  2. Lower the threshold: ./budget_check.sh 20"
    echo "  3. Top up Oracle Cloud credits"
    exit 1
fi

echo "✅ Credits OK ($CURRENCY $BALANCE > $CURRENCY $MINIMUM_CREDITS)"
echo "✅ Safe to proceed with terraform apply"
echo ""
echo "⏱️  Remember: VM will auto-shutdown after MAX_HOURS (default: 2)"
echo "💡 Run 'terraform destroy' when done to stop billing immediately."

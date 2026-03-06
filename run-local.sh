#!/bin/bash
# Start Ollama server in background
ollama serve &
# Wait for server to be ready
sleep 5
# Pull the required optimal model based on local hardware
echo "🧠 Determining Hardware Intelligence..."
python3 scripts/select_model.py > output.log
cat output.log
OLLAMA_MODEL=$(tail -n 1 output.log)
rm output.log
export OLLAMA_MODEL=$OLLAMA_MODEL
echo "Local Intelligence selected: $OLLAMA_MODEL"
ollama pull $OLLAMA_MODEL
# Keep the container running or hand over execution
exec "$@"

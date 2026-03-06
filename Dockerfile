FROM ubuntu:22.04

# Avoid prompts from apt
ENV DEBIAN_FRONTEND=noninteractive

# Install dependencies
RUN apt-get update && apt-get install -y \
    curl \
    git \
    python3 \
    python3-pip \
    golang-go \
    nodejs \
    npm \
    # Install Ollama curl script deps
    sudo \
    && rm -rf /var/lib/apt/lists/*

# Install Ollama Server
RUN curl -fsSL https://ollama.com/install.sh | sh

# Set up working directory
WORKDIR /app

# Copy requirement files first
COPY requirements.txt .

# Install Python packages
RUN pip3 install --no-cache-dir -r requirements.txt

# Install Web & Node linters
RUN npm install -g eslint htmlhint stylelint stylelint-config-standard
RUN go install golang.org/x/lint/golint@latest
RUN go install github.com/securego/gosec/v2/cmd/gosec@latest

# Add Go binaries to PATH
ENV PATH="${PATH}:/root/go/bin"

# Expose Ollama port
EXPOSE 11434

# Startup script to run Ollama and bash
COPY run-local.sh /usr/local/bin/run-local.sh
RUN chmod +x /usr/local/bin/run-local.sh

ENTRYPOINT ["/usr/local/bin/run-local.sh"]

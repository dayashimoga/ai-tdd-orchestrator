# 🤖 Open-Source AI Code Reviewer

[![Actions Status](https://github.com/dayashimoga/ai-tdd-orchestrator/workflows/AI%20Code%20Review%20&%20Quality%20Gates%20(Ollama%20+%20Security%20Check)/badge.svg)](https://github.com/dayashimoga/ai-tdd-orchestrator/actions)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

An intelligent, fully open-source, and free continuous integration layer for GitHub. 

This repository provides an autonomous pipeline that spins up localized, hardware-aware LLMs (via [Ollama](https://ollama.com/)) directly inside your GitHub Actions runner or local Docker environment. It identifies git differentials in your Pull Requests, runs aggressive security and linting tools, and iteratively fixes your code until it passes strict quality gates.

> ⚡ **No OpenAI API Keys. No subscription fees. No data harvesting.**

## 📚 Documentation
Everything you need to configure, extend, and understand this Action is thoroughly documented in the `docs/` folder:

- 📖 **[User Guide & Setup Instructions](docs/user_guide.md)**
- 🧠 **[Technical Architecture & Hardware Intelligence](docs/architecture.md)**
- 📋 **[Comprehensive Requirements](docs/requirements.md)**
- 🗺️ **[Project Status & Future Enhancements](docs/project_status.md)**

## 🚀 Quick Start
1. Fork or copy this repository.
2. Edit `prompt.txt`.
3. Push to `main`.
4. The AI will generate your foundational codebase according to the prompt!
5. On subsequent Pull Requests, the AI interceptor will review, analyze, and automatically fix your code, leaving inline annotations on your PR.

## 🐳 Running Locally
Want to test the AI review loop before pushing your PR? We support dynamic hardware allocation. Simply launch Docker:
```bash
docker-compose up --build
```
*The pipeline will read your machine's system memory and GPU VRAM and pick the most powerful Qwen/DeepSeek model your physical hardware can handle without crashing.*

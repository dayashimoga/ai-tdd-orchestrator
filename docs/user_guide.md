# Open-Source AI Reviewer User Guide

This guide explains how to install and utilize the intelligent PR Code Reviewer to enforce quality, security, and coverage across your project.

## 1. Setup

### 1.1 Prerequisites
- A GitHub Repository.
- Code written in Python, NodeJS, or Go.

### 1.2 Installation
Simply copy the `.github/workflows/ai-review.yml`, `scripts/`, and `run-local.sh` into your repository.
Commit and push to `main`. 

## 2. Setting Up an Empty Project
If your project is entirely empty, the AI will build the foundation for you!
1. Open `prompt.txt` at the root of your repo.
2. Provide a descriptive prompt. Example:
   > "A full stack web application using React and Flask backend serving a SQLite Database. Include Dockerfiles."
3. Push to `main`. The AI will execute, generate the architecture, attempt to fix any initial linters, and commit the code to `your_project/`.

## 3. Pull Request Workflow
1. Create a new branch, write your code, and generate a Pull Request.
2. The Action will automatically intercept the PR and run `git diff`.
3. The AI will spin up locally on the runner, scan your changes using `njsscan`, `gosec`, `pylint`, etc.
4. If issues are found, the AI gets 3 attempts to push a fix for your files.
5. If it succeeds, the workflow turns **green**.
6. If it fails the strict gates (<90% Coverage, <8/10 Lint), the PR is **blocked**.

### 3.1 Inline Comments
The AI will post native GitHub Review Comments on the exact lines it believes contain bugs or security flaws. You can view these directly in the "Files Changed" tab on GitHub to either accept or reject them.

## 4. Local Development (Docker)
You can test the AI against your code without pushing to GitHub.
1. Install [Docker Desktop](https://www.docker.com/).
2. Run `docker-compose up --build`.

The intelligence script (`select_model.py`) will automatically query your Local RAM/GPU and select the highest quality model your physical computer can handle. The AI will then run the exact same pipeline used in the CI/CD environment.

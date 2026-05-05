# AI Agent — Telegram Server Admin Bot

[![Release](https://img.shields.io/github/v/release/CodinginID/ai-agent)](https://github.com/CodinginID/ai-agent/releases)
[![Docker Image](https://img.shields.io/badge/ghcr.io-ai--agent-blue)](https://github.com/CodinginID/ai-agent/pkgs/container/ai-agent)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

A Telegram bot that lets you monitor and control a server through natural language (English or Indonesian). Chat is powered by **Qwen** running locally through **Ollama** — no data leaves your machine. Optional **Codex CLI** and **Claude Code CLI** integrations forward prompts to those providers when you explicitly enable them.

---

## Table of Contents

- [Overview](#overview)
- [Features](#features)
- [System Requirements](#system-requirements)
- [Installation](#installation)
  - [Option 1 — One-line installer (recommended for VPS)](#option-1--one-line-installer-recommended-for-vps)
  - [Option 2 — Docker Compose (manual)](#option-2--docker-compose-manual)
  - [Option 3 — From source (development)](#option-3--from-source-development)
- [Configuration](#configuration)
  - [Environment variables](#environment-variables)
  - [Get a Telegram bot token](#get-a-telegram-bot-token)
  - [Restrict access](#restrict-access)
  - [Optional: full-access AI agents](#optional-full-access-ai-agents)
  - [Optional: terminal tools](#optional-terminal-tools)
- [Usage](#usage)
- [AI Models](#ai-models)
- [Deployment (Production)](#deployment-production)
- [CI/CD with GitHub Actions](#cicd-with-github-actions)
- [Project Structure](#project-structure)
- [Troubleshooting](#troubleshooting)
- [Contributing](#contributing)
- [License](#license)

---

## Overview

`ai-agent` ships as a single Docker image that runs alongside an Ollama service. You send a natural-language message in Telegram (e.g. *"how is the server doing?"*, *"list running containers"*, *"check memory"*) and the bot translates it into a safe, scoped server action and replies with the result.

The architecture follows **Hexagonal (Ports & Adapters)** design. The domain logic is isolated from Telegram, Ollama, and `psutil`, which makes the bot easy to test and swap providers in.

---

## Features

| Category | Capability |
|---|---|
| **Server** | Status, uptime, CPU, load average |
| **Memory** | RAM and swap usage |
| **Disk** | Per-partition usage |
| **Processes** | Top 15 processes by CPU/RAM |
| **Docker** | Running containers, images, resource stats |
| **Git** | Repository status |
| **Files** | List files in the working directory |
| **Manual commands** | Run a whitelisted command via `/cmd` |
| **AI agents** | Invoke `/codex`, `/claude`, and `/agents` for status |
| **Terminal tools** | Run whitelisted utilities via `/tool`, `/btop`, `/spf`, `/tools` |

All actions are also reachable through plain natural-language messages, for example:

> *"check ram now"*, *"what containers are running"*, *"how is the server"*

---

## System Requirements

| Requirement | Notes |
|---|---|
| OS | Linux (Ubuntu/Debian/RHEL) or macOS |
| Docker | Engine 24+ with the `docker compose` plugin (recommended path) |
| Python | 3.10+ (only when running from source) |
| RAM | ≥ 4 GB for `qwen2.5:3b`, ≥ 8 GB for `qwen2.5:7b` |
| Disk | ~3 GB free for the AI model |
| Network | Outbound HTTPS to GitHub, ghcr.io, and ollama.com |

You do **not** need a GPU. Ollama runs on CPU by default; performance scales with the chosen model size.

---

## Installation

Pick the path that matches your goal:

| If you want to… | Use |
|---|---|
| Run the bot on a VPS as fast as possible | [One-line installer](#option-1--one-line-installer-recommended-for-vps) |
| Run via Docker but configure things yourself | [Docker Compose](#option-2--docker-compose-manual) |
| Hack on the code locally | [From source](#option-3--from-source-development) |

### Option 1 — One-line installer (recommended for VPS)

**Prerequisites**

- A Linux host with Docker installed and the daemon running
- A Telegram bot token (see [Get a Telegram bot token](#get-a-telegram-bot-token))

**Install**

```bash
curl -fsSL https://raw.githubusercontent.com/CodinginID/ai-agent/main/install.sh | bash
```

The script will:

1. Pull the latest container image from `ghcr.io/codinginid/ai-agent`.
2. Prompt for your Telegram bot token and admin user ID.
3. Write a `.env` file with sensible defaults.
4. Start the bot and Ollama services.
5. Download the default `qwen2.5:3b` model (~2 GB) on first run.

**Verify**

```bash
docker compose ps          # bot + ollama + ollama-init listed
docker compose logs -f bot # follow bot logs
```

In Telegram, send `/start` to your bot. You should receive a help message.

**Update**

```bash
docker compose pull && docker compose up -d
```

### Option 2 — Docker Compose (manual)

Use this path if you want explicit control over the configuration files.

**1. Download the compose file and the env template**

```bash
mkdir -p ai-agent && cd ai-agent
curl -fsSL https://raw.githubusercontent.com/CodinginID/ai-agent/main/docker-compose.yml -o docker-compose.yml
curl -fsSL https://raw.githubusercontent.com/CodinginID/ai-agent/main/.env.example -o .env
```

**2. Fill in the required values**

Open `.env` and set at least:

```env
TELEGRAM_BOT_TOKEN=123456789:AA...      # from @BotFather
ADMIN_USER_IDS=123456789                # your Telegram user ID
```

**3. Start the stack**

```bash
docker compose up -d
```

The `ollama-init` container will download the model on first start; this takes a few minutes. Watch progress with:

```bash
docker compose logs -f ollama-init
```

**4. Verify**

```bash
docker compose ps
docker compose logs -f bot
```

### Option 3 — From source (development)

Use this path when you plan to modify the bot code or run it without Docker.

**1. Clone the repository**

```bash
git clone https://github.com/CodinginID/ai-agent.git
cd ai-agent
```

**2. Run the setup script (recommended)**

```bash
bash setup.sh
```

The script creates a virtualenv, installs Python dependencies, installs Ollama if missing, downloads the default model, and writes a starter `.env`.

**Or, install manually:**

```bash
# 1. Create a virtual environment
python3 -m venv env
source env/bin/activate

# 2. Install Python dependencies
pip install -r requirements.txt
pip install -r requirements-dev.txt   # only if you plan to run tests/lint

# 3. Install Ollama
#    macOS:
brew install ollama
#    Linux:
curl -fsSL https://ollama.com/install.sh | sh

# 4. Start Ollama and pull the model
ollama serve &
ollama pull qwen2.5:3b

# 5. Configure
cp .env.example .env
$EDITOR .env   # set TELEGRAM_BOT_TOKEN and ADMIN_USER_IDS
```

**3. Run the bot**

```bash
source env/bin/activate
python app/bot.py
```

**4. Run the test suite**

```bash
make check    # ruff + mypy + pytest
```

---

## Configuration

All configuration is read from a single `.env` file. Copy the template and edit it:

```bash
cp .env.example .env
```

### Environment variables

| Variable | Required | Default | Description |
|---|---|---|---|
| `TELEGRAM_BOT_TOKEN` | Yes | — | Token from [@BotFather](https://t.me/BotFather) |
| `ADMIN_USER_IDS` | Recommended | _(empty)_ | Comma-separated Telegram user IDs allowed to use the bot |
| `ALLOW_UNRESTRICTED_ACCESS` | No | `false` | Development only — allow any user. **Never set true in production.** |
| `OLLAMA_HOST` | No | `http://localhost:11434` | URL of the Ollama service |
| `OLLAMA_MODEL` | No | `qwen2.5:3b` | Ollama model name |
| `PROJECT_DIR` | No | `.` | Working directory for shell commands |
| `COMMAND_TIMEOUT` | No | `20` | Timeout (seconds) for manual commands |
| `CHAT_HISTORY_LIMIT` | No | `6` | Recent messages forwarded to the model as context |
| `ENABLE_CODEX` | No | `false` | Enable the `/codex` command |
| `ENABLE_CLAUDE` | No | `false` | Enable the `/claude` command |
| `AGENT_WORKDIR` | No | `.` | Working directory for Codex/Claude |
| `AGENT_TIMEOUT` | No | `180` | Timeout (seconds) for AI agents |
| `CODEX_SANDBOX` | No | `read-only` | `read-only`, `workspace-write`, or `danger-full-access` |
| `CLAUDE_PERMISSION_MODE` | No | `dontAsk` | Set `bypassPermissions` for full access |
| `CLAUDE_ALLOWED_TOOLS` | No | `Read,Grep,Glob` | Comma-separated allowed Claude tools |
| `CLAUDE_TOOLS` | No | _(empty)_ | Set `default` for the full Claude toolset |
| `AGENT_ROLE_ENGINEER` | No | `codex` | Agent assigned to the engineer role |
| `AGENT_ROLE_ARCHITECT` | No | `glm` | Agent assigned to the architect role |
| `AGENT_ROLE_REVIEWER` | No | `claude` | Agent assigned to the reviewer role |
| `ENABLE_GLM` | No | `false` | Register GLM CLI as an architect worker when installed |
| `ENABLE_TERMINAL_TOOLS` | No | `false` | Enable `/tool`, `/btop`, `/spf` |
| `TERMINAL_ALLOWED_COMMANDS` | No | _(built-in list)_ | Whitelisted commands runnable via `/tool` |
| `DATABASE_URL` | No | `sqlite:///data/control_plane.sqlite3` | Runtime control-plane database URL; use pooled Neon URL in production |
| `DATABASE_MIGRATION_URL` | No | same as `DATABASE_URL` | Migration database URL; use direct Neon URL for Alembic |

The full annotated list lives in [`.env.example`](.env.example).

For Neon PostgreSQL, keep real connection strings in server secrets or `.env` only. Use the pooled Neon URL for `DATABASE_URL`, and use a direct Neon URL for `DATABASE_MIGRATION_URL`.

### Get a Telegram bot token

1. Open Telegram and chat with [@BotFather](https://t.me/BotFather).
2. Send `/newbot` and follow the prompts.
3. Copy the token and put it in `TELEGRAM_BOT_TOKEN` in your `.env`.

### Restrict access

Send `/whoami` to your bot to discover your Telegram user ID, then add it to `.env`:

```env
# One admin
ADMIN_USER_IDS=123456789

# Multiple admins
ADMIN_USER_IDS=123456789,987654321
```

If `ADMIN_USER_IDS` is empty, every command except `/whoami` is rejected. For temporary local testing only, you can set `ALLOW_UNRESTRICTED_ACCESS=true`.

### Optional: full-access AI agents

To let Codex or Claude edit files on the host through Telegram, add this to `.env`:

```env
ADMIN_USER_IDS=123456789

ENABLE_CODEX=true
ENABLE_CLAUDE=true
AGENT_WORKDIR=/home/you/projects/ai-agent

CODEX_SANDBOX=danger-full-access

CLAUDE_PERMISSION_MODE=bypassPermissions
CLAUDE_ALLOWED_TOOLS=
CLAUDE_TOOLS=default
```

When running in Docker, mount the host project into `/workspace` and point the agents there:

```env
HOST_PROJECT_DIR=/home/you/projects/ai-agent
PROJECT_DIR=/workspace
AGENT_WORKDIR=/workspace
TERMINAL_WORKDIR=/workspace
```

The `codex`, `claude`, `btop`, and `spf` binaries must be present in the environment where the bot runs. Send `/agents` and `/tools` to verify what is detected.

`/agents` separates four states: installed on the server, enabled in `.env`, assigned to a role, and ready for execution. This is the recommended path before adding queue-based multi-agent workflows.

> **Warning:** Full-access mode lets the AI execute arbitrary commands and write to your filesystem. Only enable it for trusted Telegram users listed in `ADMIN_USER_IDS`.

### Optional: terminal tools

Enable wrapped CLI utilities:

```env
ENABLE_TERMINAL_TOOLS=true
TERMINAL_WORKDIR=/home/you/projects/ai-agent
TERMINAL_ALLOWED_COMMANDS=btop,spf,fastfetch,neofetch,df,free,uptime,whoami,pwd,ls,git,docker,systemctl,journalctl,tail
```

Example Telegram commands:

```text
/tools
/tool fastfetch
/tool docker ps
/btop
/spf app
```

`btop` and `spf` are TUI applications, so the bot returns a text snapshot rather than an interactive session.

---

## Usage

### Slash commands

| Command | Description |
|---|---|
| `/start`, `/help` | Show the help screen |
| `/whoami` | Show your Telegram user ID |
| `/cmd <command>` | Run a whitelisted shell command directly |
| `/codex <prompt>` | Forward a prompt to Codex CLI (if enabled) |
| `/claude <prompt>` | Forward a prompt to Claude Code CLI (if enabled) |
| `/agents` | Show the status of Codex/Claude integrations |
| `/tools`, `/tool <cmd>` | Run a whitelisted terminal tool |
| `/btop`, `/spf` | Snapshot of those TUI tools |

Commands available to `/cmd` by default: `docker`, `git`, `ls`, `ps`, `df`, `du`, `free`, `uptime`, `whoami`, `pwd`, `hostname`.

### Natural language

Just type a request — the AI classifies the intent and runs the right action:

```
check server status
how much ram is free
which containers are running
git status
list files
which process is using the most cpu
```

---

## AI Models

The default model is `qwen2.5:3b`. Pick a larger one if you have the RAM:

| Model | RAM | Quality | Use case |
|---|---|---|---|
| `qwen2.5:3b` | ~3 GB | Good | Small VPS |
| `qwen2.5:7b` | ~5 GB | Better | Server with ≥ 8 GB RAM |
| `qwen2.5:14b` | ~9 GB | Best | Server with ≥ 16 GB RAM |

Switch the model:

```bash
# 1. Edit .env
OLLAMA_MODEL=qwen2.5:7b

# 2. Pull the new model and restart the bot
make pull-model
make restart
```

---

## Deployment (Production)

The recommended production setup is Docker Compose on a VPS. The bot auto-restarts on crash or reboot.

### Install Docker on the VPS (Ubuntu)

```bash
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER
newgrp docker
```

### Initial setup

```bash
git clone https://github.com/CodinginID/ai-agent.git
cd ai-agent
cp .env.example .env
$EDITOR .env       # set TELEGRAM_BOT_TOKEN and ADMIN_USER_IDS
make up            # builds bot, starts Ollama, downloads model, starts bot
```

The first `make up` takes several minutes because it downloads the AI model. Watch progress:

```bash
make logs
```

### Day-to-day operations

| Command | Action |
|---|---|
| `make up` | Start everything (rebuild bot if code changed) |
| `make down` | Stop everything |
| `make restart` | Restart only the bot (keeps Ollama running) |
| `make logs` | Tail bot logs |
| `make logs-ollama` | Tail Ollama logs |
| `make logs-init` | Tail model-pull logs |
| `make status` | Show container status |
| `make shell` | Open a shell inside the bot container |
| `make pull-model` | Pull/refresh the AI model |
| `make clean` | Remove containers **and volumes** (deletes the model) |

### Update the bot

```bash
git pull
make up   # rebuilds the image automatically
```

### Auto-restart on reboot

All services use `restart: unless-stopped`. Verify Docker itself starts on boot:

```bash
sudo systemctl is-enabled docker   # should print: enabled
```

### Service architecture

```
┌─────────────────────────────────┐
│         docker-compose          │
│                                 │
│  ┌──────────┐   ┌────────────┐  │
│  │  ollama  │◄──│    bot     │  │
│  │  :11434  │   │  (python)  │  │
│  └──────────┘   └────────────┘  │
│       │                         │
│  [ollama_data volume]           │
│  (model persists across reboots)│
└─────────────────────────────────┘
```

- **ollama** — model server, auto-restart, model stored in a Docker volume
- **ollama-init** — one-shot container that pulls the model on first deploy
- **bot** — Telegram bot, auto-restart on crash or reboot

---

## CI/CD with GitHub Actions

Every push to `main` triggers an automatic deploy to the VPS — no manual SSH needed.

```
push to main
    │
    ├── [validate] runs on GitHub-hosted runner — Python syntax + docker-compose lint
    └── [deploy]   runs on self-hosted runner inside the VPS:
                   git pull origin main
                   make up
                   make status
```

### Why a self-hosted runner instead of SSH?

VPSes behind **Cloudflare Access** or strict firewalls usually cannot accept inbound SSH from GitHub-hosted runners. A self-hosted runner installed inside the VPS connects outbound to GitHub instead, which avoids the inbound restriction entirely.

```
❌ Plain SSH (blocked by Cloudflare Access):
   GitHub Actions → SSH → Cloudflare → VPS

✅ Self-hosted runner:
   GitHub Actions ←→ Runner (already inside the VPS)
```

### One-time setup

**1. SSH into the VPS** — if you use Cloudflare Access:

```bash
cloudflared access login ssh-your-host.example.com
ssh your-vps
```

**2. Register a runner**

In GitHub: **Settings → Actions → Runners → New self-hosted runner**, choose **Linux x64**, then run the displayed commands on the VPS:

```bash
mkdir -p ~/actions-runner && cd ~/actions-runner
curl -o actions-runner-linux-x64.tar.gz -L <URL_FROM_GITHUB>
tar xzf actions-runner-linux-x64.tar.gz
./config.sh --url https://github.com/<owner>/<repo> --token <TOKEN_FROM_GITHUB>
```

**3. Run the runner as a systemd service**

```bash
sudo ./svc.sh install
sudo ./svc.sh start
sudo ./svc.sh status   # must report: active (running)
```

**4. Clone the project on the VPS**

```bash
cd ~
git clone https://github.com/<owner>/<repo>.git ai-agent
cd ai-agent
cp .env.example .env
$EDITOR .env       # TELEGRAM_BOT_TOKEN and ADMIN_USER_IDS
make up
```

The default workflow expects the project at `/home/ali/project/codinginid/ai-agent`. To use another path, set the repository variable `DEPLOY_DIR` and update the workflow.

**5. Done.** No GitHub secrets are needed — the runner has direct access to Docker and the project.

### Troubleshooting CI/CD

**`Waiting for a runner to pick up this job…`**

The deploy is valid but no runner is online with matching labels. On the VPS:

```bash
cd ~/actions-runner
sudo ./svc.sh status
sudo ./svc.sh start
# or, if not yet installed:
sudo ./svc.sh install
sudo ./svc.sh start
```

In GitHub, **Settings → Actions → Runners** should show the runner as **Idle**.

**`git@github.com: Permission denied (publickey)`**

The runner user does not have a matching SSH key. If you use a multi-account Git setup, configure an alias in `~/.ssh/config`:

```sshconfig
Host github-work
  HostName github.com
  User git
  IdentityFile ~/.ssh/id_ed25519_work
  IdentitiesOnly yes
```

Verify from the VPS:

```bash
ssh -T git@github-work
git -C /home/ali/project/codinginid/ai-agent fetch origin main
```

If the runner runs as a different user, move the SSH config and key to that user's home, or reinstall the runner service under your user. To override the remote without touching the local repo, set the repository variable `DEPLOY_GIT_REMOTE_URL`.

**SSH key with a passphrase**

GitHub Actions cannot type passphrases interactively. Use `ssh-agent` with a fixed socket so the workflow can find it:

```bash
export SSH_AUTH_SOCK=/home/ali/.ssh/ssh-agent.sock
ssh-agent -a "$SSH_AUTH_SOCK"
ssh-add /home/ali/.ssh/id_ed25519_work
```

If the VPS reboots or `ssh-agent` dies, run those commands again.

### Manual trigger

Deploy without pushing code: GitHub repo → **Actions → Deploy to VPS → Run workflow**.

---

## Project Structure

```
ai-agent/
├── .github/workflows/        # CI/CD pipelines (validate, deploy, release)
├── app/
│   ├── domain/               # Pure business logic (zero external deps)
│   ├── ports/                # Protocol definitions for adapters
│   ├── adapters/             # Telegram, Ollama, psutil implementations
│   ├── actions/              # Server, docker, git actions
│   └── bot.py                # Entrypoint and dependency wiring
├── tests/                    # pytest suites mirroring app/ layout
├── docs/                     # Design documents and plans
├── .env.example              # Annotated configuration template
├── docker-compose.yml        # bot + ollama + ollama-init
├── Dockerfile                # Bot container image
├── Makefile                  # Common dev and ops shortcuts
├── install.sh                # One-line VPS installer
├── setup.sh                  # Local development bootstrap
└── requirements*.txt         # Python dependencies
```

The codebase follows **Hexagonal Architecture**. See [`CLAUDE.md`](CLAUDE.md) for the layering rules and contribution conventions.

---

## Troubleshooting

**The bot does not respond.**
Check that `TELEGRAM_BOT_TOKEN` is set correctly and that you have sent `/start` to the bot at least once.

**Cannot reach Ollama.**
```bash
curl http://localhost:11434   # expect a response
ollama serve                  # start it if not running
```

**Model is missing.**
```bash
ollama list                   # list installed models
ollama pull qwen2.5:3b        # download the default model
```

**`dependency failed to start: container aiagent_ollama is unhealthy`**

Compose was waiting for Ollama to become healthy and the healthcheck timed out. Inspect:

```bash
make status
make logs-ollama
docker inspect aiagent_ollama --format '{{json .State.Health}}'
```

If Ollama is actually running, restart the stack:

```bash
docker compose down
docker compose up -d --build
```

On small/cold-start VPSes, wait 1–2 minutes and check:

```bash
docker compose exec ollama ollama list
make logs-init
```

**Model download is still in progress on first deploy.**
```bash
docker compose logs -f ollama-init
```

**Bot does not start after `make up`.**
```bash
make logs
make status
```

---

## Contributing

Contributions are welcome. Before opening a PR:

1. Read [`CLAUDE.md`](CLAUDE.md) — it documents the hexagonal layering rules, naming conventions, and Git workflow.
2. Branch naming: `<type>/<short-description>`, e.g. `feat/docker-stats-action`. Allowed types: `feat`, `fix`, `refactor`, `chore`, `docs`, `test`, `hotfix`.
3. Commit messages follow [Conventional Commits](https://www.conventionalcommits.org/), e.g. `feat: add docker stats action`.
4. Run `make check` (lint + type-check + tests) and ensure it is green.
5. One PR = one concern. Don't mix features with refactors.

Direct pushes to `main` are not allowed; all changes go through a pull request.

---

## License

[MIT](LICENSE)

# Octopus

[![Release](https://img.shields.io/github/v/release/CodinginID/ai-agent)](https://github.com/CodinginID/ai-agent/releases)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

Octopus lets you monitor and control your server through natural language — from Telegram or a terminal TUI. Type what you want in plain text; Octopus figures out what to run and asks for confirmation before anything risky happens.

---

## What you can do

**Server monitoring**
- Check server status, CPU load, memory, disk, and running processes

**Docker Compose**
- List running services, pull images, build, bring services up, restart a specific service

**Git**
- Status, diff, log, add, commit, push, pull, branch — all from chat

**Deploy**
- Run a full deploy (pull → build → up → health check) with one command
- Rollback to a previous commit if something goes wrong
- Health check any HTTP endpoint

**AI agents on your device**
- Register your machine as a worker, Octopus detects which AI CLIs you have installed (Codex, Claude, GLM)
- View per-device agent status and readiness

**Safety first**
- Low-risk commands run immediately
- Medium and high-risk commands show a plan and wait for your `/approve` before executing
- Destructive patterns (force delete, overwrite system paths, fork bombs) are blocked outright

---

## Two ways to use Octopus

### 1. Telegram

Send a message to your Octopus bot:

```
cek status server
container mana yang running?
deploy sekarang
git status
cek memory
```

Octopus interprets the intent, builds an execution plan, and either runs it directly (low-risk) or asks for confirmation first.

Slash commands:

| Command | What it does |
|---|---|
| `/start`, `/help` | Show available commands |
| `/approve <id>` | Approve a pending execution plan |
| `/reject <id>` | Reject a pending plan |
| `/agents` | Show AI agent status on your devices |
| `/devices` | List registered worker devices |

---

### 2. Terminal TUI

Install the `octopus` CLI on your machine and get a full terminal interface:

```bash
curl -fsSL https://raw.githubusercontent.com/CodinginID/ai-agent/main/octopus-cli/install.sh | bash
```

Then just type:

```bash
octopus
```

You get a chat-style TUI connected to your Octopus backend. Type commands the same way you would in Telegram.

**Self-upgrade:**

```bash
octopus upgrade
```

---

## Install the backend

The backend runs on your own server. One-liner:

```bash
curl -fsSL https://raw.githubusercontent.com/CodinginID/ai-agent/main/install.sh | bash
```

The script will ask for your Telegram bot token, set up the config, and start all services.

**Need a Telegram bot token?**
1. Open Telegram → search for **@BotFather**
2. Send `/newbot` and follow the prompts
3. Paste the token when the installer asks

**Manual setup** (if you prefer to control each step):

```bash
mkdir octopus && cd octopus
curl -fsSL https://raw.githubusercontent.com/CodinginID/ai-agent/main/docker-compose.yml -o docker-compose.yml
curl -fsSL https://raw.githubusercontent.com/CodinginID/ai-agent/main/.env.example -o .env
# Edit .env: set TELEGRAM_BOT_TOKEN and ADMIN_USER_IDS
docker compose up -d
```

**Verify it's running:**

```bash
docker compose ps
```

Send `/start` to your bot in Telegram.

---

## Connect your device as a worker

A *worker* is your local machine (laptop, desktop, VPS) registered with Octopus so it can run AI agent jobs on your behalf.

```bash
# Install the CLI
curl -fsSL https://raw.githubusercontent.com/CodinginID/ai-agent/main/octopus-cli/install.sh | bash

# Open the TUI and log in
octopus
```

Inside the TUI, type `/login` to link your account. Once connected, Octopus automatically detects which AI CLIs (Codex, Claude, GLM) are installed on that machine and reports their status back to the backend.

Check your devices and their agent status from Telegram:

```
/devices
/agents
```

---

## Approval flow

For any operation that could change state — deploys, docker compose up, git push — Octopus shows the plan first:

```
📋 Execution Plan
─────────────────
1. git pull origin main
2. docker compose build
3. docker compose up -d --remove-orphans
4. health check → https://yourapp.com/health

Risiko: HIGH

Konfirmasi: /approve abc123
Batalkan:  /reject abc123
```

Low-risk reads (status, logs, git log) run immediately without confirmation.

---

## Updates

**Backend:**

```bash
docker compose pull && docker compose up -d
```

**CLI:**

```bash
octopus upgrade
```

---

## Contributing

See [`CLAUDE.md`](CLAUDE.md) for architecture rules, naming conventions, and the Git workflow used in this project.

---

## License

[MIT](LICENSE)

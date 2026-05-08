# Octopus

[![Release](https://img.shields.io/github/v/release/CodinginID/ai-agent)](https://github.com/CodinginID/ai-agent/releases)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

Octopus lets you monitor and control your server through natural language — from Telegram or a terminal TUI. Type what you want in plain text; Octopus figures out what to run and asks for confirmation before anything risky happens.

The Octopus backend is hosted centrally. You only need to install the CLI worker on your own machine.

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
- Octopus detects which AI CLIs you have installed (Codex, Claude, GLM) and reports their readiness
- Each device is registered separately — you can have multiple machines

**Safety first**
- Low-risk commands run immediately
- Medium and high-risk commands show a plan and wait for your `/approve` before executing
- Destructive patterns (force delete, overwrite system paths, fork bombs) are blocked outright

---

## Get started

### 1. Install the CLI on your machine

```bash
curl -fsSL https://raw.githubusercontent.com/CodinginID/ai-agent/main/octopus-cli/install.sh | bash
```

### 2. Open Octopus

```bash
octopus
```

### 3. Log in

Type `/login` inside the TUI. You'll get a link to connect your Telegram account.

That's it. Your machine is now registered as a worker. Octopus starts detecting which AI CLIs you have installed and reports their status to the backend.

---

## Two ways to interact

### Telegram

Send a message directly to the Octopus bot:

```
cek status server
container mana yang running?
deploy sekarang
git status
cek memory
```

Slash commands:

| Command | What it does |
|---|---|
| `/start`, `/help` | Show available commands |
| `/approve <id>` | Approve a pending execution plan |
| `/reject <id>` | Reject a pending plan |
| `/agents` | Show AI agent status across your devices |
| `/devices` | List your registered worker devices |

### Terminal TUI

The same commands work inside the `octopus` terminal interface. Type naturally — the same way you would in Telegram.

**Self-upgrade:**

```bash
octopus upgrade
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

## Multiple devices

You can register as many machines as you want. Each one runs the `octopus` worker independently. From Telegram, `/devices` shows all your connected machines and `/agents` shows which AI CLIs are ready on each one.

---

## Contributing

See [`CLAUDE.md`](CLAUDE.md) for architecture rules, naming conventions, and the Git workflow used in this project.

---

## Self-hosting

If you want to run your own Octopus backend instead of using the hosted service, see the instructions in [`install.sh`](install.sh).

---

## License

[MIT](LICENSE)

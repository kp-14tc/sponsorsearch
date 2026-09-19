# Deployment and setup

This runbook covers a Windows 11 host running native Ollama and Docker Desktop with the WSL2/Linux-container backend. Compose provides PostgreSQL, n8n, SearXNG, and the Python worker. Host Python, Node.js, and separate database installations are not required.

For implementation-specific diagnostics, see [Windows integration](docs/windows-setup.md), [workflow configuration](docs/workflows.md), [performance tuning](docs/windows-performance.md), [remote access](docs/remote-access.md), and [backup and restore](docs/backup-restore.md).

## 1. Prerequisites

Install and validate:

- Current GPU drivers; `nvidia-smi` must report the adapter correctly.
- WSL2; `wsl --status` and `wsl --version` must succeed.
- Docker Desktop using Linux containers; `docker version` must report both client and server.
- Git; `git --version` must succeed.
- Native Ollama for Windows; `ollama --version` must succeed.

Run project commands in a non-elevated PowerShell session. Use elevation only for operating-system changes described in [Windows integration](docs/windows-setup.md).

## 2. Repository

```powershell
New-Item -ItemType Directory -Force "$env:USERPROFILE\Projects" | Out-Null
Set-Location "$env:USERPROFILE\Projects"
git clone https://github.com/YOUR_GITHUB_ACCOUNT/sponsor-research.git
Set-Location "$env:USERPROFILE\Projects\sponsor-research"
```

If the repository already exists, enter that working tree rather than cloning over it. All remaining commands assume the repository root as the working directory.

## 3. Configuration

Create the local environment file once:

```powershell
Copy-Item .env.example .env
```

Generate independent high-entropy values for `POSTGRES_PASSWORD`, `N8N_ENCRYPTION_KEY`, and `SEARXNG_SECRET`. One suitable PowerShell expression is:

```powershell
$bytes = [byte[]]::new(32)
[Security.Cryptography.RandomNumberGenerator]::Fill($bytes)
[Convert]::ToBase64String($bytes)
```

Run it separately for each secret. Preserve the n8n encryption key with backups; rotating it without migrating credentials makes stored n8n credentials unreadable. Changing the configured PostgreSQL password after database initialization does not alter the existing database role.

Review the remaining environment contract:

| Variable | Default | Operational note |
|---|---|---|
| `POSTGRES_USER`, `POSTGRES_DB` | `frc` | Database identity and database name. |
| `TZ` | `UTC` | Set to an IANA time-zone identifier before enabling schedules. |
| `N8N_EDITOR_BASE_URL`, `WEBHOOK_URL` | Local n8n URL | Replace only when configuring the optional private proxy. |
| `N8N_PROXY_HOPS` | `0` | Set to `1` behind Tailscale Serve. |
| `OLLAMA_URL` | `http://host.docker.internal:11434` | Container-to-host model endpoint. |
| `SCOUT_MODEL` | `qwen3.5:4b` | Candidate screening model. |
| `RESEARCH_MODEL` | `qwen3.5:9b` | Research and drafting model. |
| `DRAFT_TEMPERATURE` | `0.3` | Sampling temperature for drafting only. |
| `SCOUT_TIMEOUT_SECONDS` | `120` | Capped at 120 seconds. |
| `RESEARCH_TIMEOUT_SECONDS` | `900` | Capped at 1200 seconds. |
| `FETCH_TIMEOUT_SECONDS` | `30` | Capped at 60 seconds per page. |
| `CRAWL4AI_URL`, `CRAWL4AI_TOKEN` | Empty | Optional diagnostics; not part of the default extraction path. |
| Image variables | Pinned in `.env.example` | Review upstream release notes before changing versions or floating tags. |

Keep `.env` outside version control and redact it from logs and support material.

## 4. Domain configuration

Replace the fictional examples in:

- `prompts/team-context.md`
- `prompts/email-team-context.md`
- `config/locations.json`
- `config/search-query-templates.json`

The two context files serve different trust boundaries: research context may contain internal planning ranges, while email context must contain only information suitable for draft generation. Keep both accurate. `config/industries.json` is reference data and does not independently alter discovery queries.

Validate configuration before starting services:

```powershell
docker compose config --quiet
```

## 5. Models

Install the configured models on the Windows host:

```powershell
ollama pull qwen3.5:4b
ollama pull qwen3.5:9b
```

Run `scripts\windows\test-ollama.ps1` or the structured inference probes in [Windows integration](docs/windows-setup.md#3-download-and-test-both-models). A model appearing in `ollama list` is not sufficient; both models must complete inference successfully.

## 6. Service startup

```powershell
docker compose up -d --build --wait --wait-timeout 180
docker compose ps
docker compose exec -T worker python scripts/healthcheck.py --inside
```

Required health checks are PostgreSQL, n8n, SearXNG, Ollama, and worker. `NOT AVAILABLE` is acceptable only for optional Crawl4AI. If host Ollama works but the worker cannot reach it, follow the bind and firewall procedure in [Windows integration](docs/windows-setup.md#4-native-ollama-from-docker).

The runtime topology is:

| Producer | Consumer | Endpoint |
|---|---|---|
| Browser | n8n | `http://localhost:5678` |
| n8n | PostgreSQL | `postgres:5432`, schema `n8n` |
| n8n workflows | worker | `http://worker:8000` |
| worker | PostgreSQL | `postgres:5432`, schema `fundraising` |
| worker | SearXNG | `http://searxng:8080` |
| worker | host Ollama | `http://host.docker.internal:11434` |

No SMTP or provider model credentials are required. Outreach delivery is intentionally outside the application.

## 7. Workflow provisioning

Create the n8n owner account at `http://localhost:5678` before exposing n8n through any proxy. Then follow [workflow configuration](docs/workflows.md) to import and connect the supplied workflows.

Use a bounded smoke test before a production-like run:

1. Execute discovery with one explicit query and a one-result limit.
2. Confirm persisted company, lead, evidence, and contact provenance.
3. Run research and drafting with both model paths verified.
4. Inspect score arithmetic, evidence citations, draft policy checks, and pending-review state.
5. Record explicit approval and verify that no automatic email delivery occurs.
6. Restore the normal result limit only after the bounded path succeeds.

## 8. Optional integrations

- Configure [Telegram review and commands](docs/daily-telegram.md) only after the local workflow path passes.
- Configure [private remote access](docs/remote-access.md) only after creating the n8n owner account and validating local access. Do not use Funnel, router forwarding, or a public tunnel.
- Enable schedules only after a successful manual run. Ensure `TZ` is correct, keep lead processing sequential, and prevent overlapping research jobs.

## 9. Operations

Start or reconcile the stack:

```powershell
docker compose up -d --build --wait --wait-timeout 180
```

Stop services without deleting state:

```powershell
docker compose stop
```

Do not use `docker compose down -v`, delete volumes, or reset Docker as routine troubleshooting. Back up PostgreSQL, n8n state, and `.env` using [backup and restore](docs/backup-restore.md), then rehearse restoration in an isolated stack.

Before updates, finish active runs, back up state, inspect `git status`, review upstream release notes, and preserve local configuration changes. After updates, rebuild the worker and rerun health, inference, workflow, and persistence checks.

For failures, capture the failing command, exit status, relevant service logs, and current `docker compose ps` output. Remove secrets and private research data before sharing diagnostics.

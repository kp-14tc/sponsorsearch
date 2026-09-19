# FRC Fundraising Agent

A self-hosted sponsor research pipeline for an FRC team. The runtime target is a Windows 11 desktop with an RTX 3050; the Mac is used to build and check the repository.

n8n runs discovery, research and drafting in order. A small Python worker searches SearXNG, fetches bounded public pages, screens candidates with Qwen3.5:4b, and researches/drafts with Qwen3.5:9b. PostgreSQL stores leads, scores, evidence, contacts and drafts. Ollama runs directly on Windows; containers reach it through `host.docker.internal:11434`.

Start with [SETUP_INSTRUCTIONS.md](SETUP_INSTRUCTIONS.md) for the deployment runbook covering host prerequisites, configuration, models, Compose services, workflow provisioning, verification, and operations. No paid model/search API keys or separate PostgreSQL/n8n installation is required.

For a completely empty local account, start with [fresh Windows profile setup](docs/fresh-windows-profile.md), then use [the Windows performance guide](docs/windows-performance.md) after the basic integrations work. The performance settings are conservative starting points to measure on your own hardware, not benchmarked speed guarantees.

Sponsorship drafts are pending human review and are never automatically sent. Drafting is relationship-first: the model writes a professional first-contact sequence that asks for one short conversation and does not discuss fundraising. The email writer uses a separate context with no cash planning ranges; those stay internal for research and human review. A code-level check re-reads every draft for fundraising language, dollar figures, hard asks, corporate filler, vague greetings, excess length, multiple questions, unsupported rapport, and invented follow-up timing before it reaches you; see [workflow docs](docs/workflows.md) for details. The optional [daily owner digest](docs/daily-telegram.md) sends the saved review queue to your own Telegram bot chat, readable on a phone or at [web.telegram.org](https://web.telegram.org/) without a mail client. Optional [private Telegram commands](docs/telegram-commands.md) can start bounded search/drafting or request the same review queue without exposing n8n publicly. Evidence validation checks supplied URLs and matching excerpts; it cannot establish that a website's claim is true or that a generated draft uses every fact correctly. Open the sources and review every draft before manually copying it into your email client.

The pipeline uses bounded HTTP extraction. The optional Crawl4AI Compose profile is diagnostic only; no Crawl4AI extraction adapter is implemented. Dynamic sites may yield no usable evidence.

## Check on the Mac

Use a current Python (3.10+; 3.12 recommended). Docker and local models are optional for development checks:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-dev.txt
.venv/bin/python scripts/validate_config.py
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python scripts/healthcheck.py
```

The health check reports unavailable services separately; fixture tests do not require the Windows desktop.

## Current status

Company exclusions live in `config/excluded-companies.json`: reason, company names, explicit aliases and registrable domains. Matching ignores case/punctuation and requires whole name phrases; search snippets are not exclusion evidence. Excluded companies cannot enter research, drafting or approval, including existing records and cached retries. Discovery reports `excluded`; stage/approval requests return HTTP 409 with the reason. Records remain available for review. Missing or invalid exclusion configuration blocks processing.

To update exclusions, edit this JSON and rebuild the worker with `docker compose up -d --build worker` (configuration is copied into the image). No database migration or deletion is needed.

- **Verified on Mac:** `scripts/validate_config.py` passed YAML/JSON parsing, Python AST parsing, configuration/prompt checks, SQL structure and workflow-link checks. Python compilation passed separately; SQL also parsed with pglast. Fixture tests passed; these mock external services and do not establish database or n8n behavior. A live public HTTPS fetch of `https://example.com/` passed DNS pinning, TLS and extraction (142 cleaned characters); this does not validate a real-company pipeline. Six n8n Code scripts also passed JavaScript syntax checks.
- **Statically validated:** configuration/workflow files and service contracts can be checked without Docker. This does not prove n8n importability or database startup.
- **Requires Windows desktop:** NVIDIA/Ollama GPU use and model performance, Docker-to-native-Ollama access, PowerShell execution, Tailscale Serve and Mac access from another network, a real company run and later scheduled/nightly operation.

Detailed notes: [Windows setup](docs/windows-setup.md), [private remote access](docs/remote-access.md), [backup and restore](docs/backup-restore.md). PostgreSQL, n8n, Ollama and Windows operation still require live validation.

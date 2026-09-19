# First usable version

## Decisions and interfaces

Workflow 05 may send the deterministic saved-lead review queue to one fixed Telegram chat controlled by the operator. This is the explicitly authorized exception to the no-send policy; sponsorship outreach remains manual after review. The worker only exposes a read-only `/digest` endpoint and has no mail or chat transport; it returns the queue pre-split into parts under Telegram's 4096-character message limit, and n8n owns delivery. Discovery optionally rotates queries by local calendar date (not per run). Schedule defaults are research at 6:00 AM and the digest at 11:00 AM in the configured time zone, disabled until configured and tested.

Windows 11 / Docker Desktop is the deployment target; Ollama runs natively on Windows. Mac checks are development checks only. Compose contains PostgreSQL, n8n, SearXNG and a small Python worker. Crawl4AI is optional because its Docker API/authentication is changing and its default crawl path launches Chromium; ordinary bounded HTTP extraction is the initial fetch path. No browser automation is required.

n8n owns stage ordering and qualification branches. Python owns deterministic search/fetch limits, domain normalization, schema validation, model calls and transactional persistence. PostgreSQL owns durable state; n8n execution output is a review aid, never the only record. Use ordinary functions, a single process, and a lock to serialize GPU work. No job broker, autonomous agent framework, send endpoint or SMTP credentials.

Internal worker API (JSON):

- `GET /health`: availability/configuration, without secrets.
- `POST /discover` with `{query_limit: 1, result_limit: 5}`: run bounded configured queries, normalize/upsert companies, screen unseen candidates; return `{leads: [{lead_id, domain, company_name}], ...}` for relevant confidence >= 0.70 candidates. Persist rejected screens too. An explicit query override is useful for testing.
- `POST /research` with `{lead_id}`: load persisted company/scout context, search/fetch, research and contacts; return `{lead_id, status, overall_score, tier, qualified}`. `qualified` means score >= 70 and validated research exists.
- `POST /draft` with `{lead_id}`: enforce qualification again, load persisted evidence, return stored draft with `approved=false` and `status=pending_review`.
- `GET /leads` and `GET /leads/{id}`: review persisted research, sources, contacts and drafts through n8n HTTP Request nodes. Avoid a separate dashboard in v1.
- `GET /telegram-drafts/{lead_id}`: render one persisted draft into bounded owner-review messages. Workflow 05 remains the only Telegram sender; this endpoint cannot deliver or approve anything.
- `GET /telegram-commands/cursor` and `POST /telegram-commands/intake`: persist the Telegram polling cursor in PostgreSQL, accept only the configured owner's `/search`, `/draft` or `/status`, and durably deduplicate update IDs. `POST /telegram-commands/claim` remains the narrow parsed-command contract. The bot token remains in n8n; these endpoints cannot send messages or run stages.

A retry must not create duplicate companies/leads/drafts or discard previous valid evidence. One lead per company and one current draft per lead is sufficient. Allow explicit re-research only with clear replacement semantics; do not overwrite approved content silently. Persist stage/error information; failed model/network validation must not promote a lead. Retrying discovery should expose previously screened, unreached research candidates rather than stranding them forever.

Use synchronous bounded endpoints initially. n8n HTTP timeout must exceed the worker's bounded model/search/fetch time budget (60 minutes per stage; document slow 9B inference). Manual discovery starts at one query/five results. Process leads sequentially, never parallelize inference. Native n8n Execute Sub-workflow nodes call workflows 02 and 03; document any imported workflow-ID selection required. Each child also supports a small manual test input. An n8n review workflow/query may be added if it makes database-backed review usable.

## Data and evidence

Use an application schema separate from n8n's public tables in the same database. Tables: companies (unique normalized registrable domain), leads (unique company FK, seven score components, derived sum/tier, lifecycle/error metadata), evidence (lead FK, claim, exact source URL/title/excerpt/retrieval timestamp), contacts (company FK, supplied public name/title/email/profile plus source and verification status), email_drafts (lead FK, optional contact FK, text fields and approval audit). CHECK constraints enforce score ranges, confidence, tier and approval consistency. Add timestamps/indexes; schema reruns must preserve data.

Normalize with an offline Public Suffix List dependency (no surprise startup download), lowercase/IDNA, remove www/ports/paths and reject IP/private/local hosts. Deterministic junk-domain filtering precedes inference. Fetch only HTTP(S) public targets: validate DNS and every redirect, cap bytes/time/page count, and reject local/private/reserved targets. Do not pass model-produced URLs to fetchers. Treat all retrieved text as untrusted data, never instructions.

Sources supplied to models carry final URL, title, concise cleaned text and retrieval timestamp. Research returns claims with source URLs and verbatim excerpts. Accept only URLs in supplied fetched sources and excerpts present in their supplied text; persist supporting source metadata. Unsupported factual claims must not flow into drafts. A matching URL alone does not establish a claim's truth: human review remains necessary. Prefer a claim-based research summary or explicitly distinguish analyst conclusions from externally asserted facts. Search snippets may inform scouting but do not count as verified deep-research evidence.

Research scores are model judgments constrained to 20/20/20/15/10/10/5. Python computes sum and tiers 85/70/55, and deterministic ask ranges. Ignore the model's claimed total/tier. Missing evidence lowers confidence and may fail research; never fabricate it. Draft only from persisted evidence and team context. Contacts must cite supplied sources; any email/name claimed as publicly listed must occur in the source text. Never guess an address. Role suggestions are suggestions, not identified people. Approval records can be set by an explicit documented human action; no code sends sponsorship outreach. Only the owner-authorized review queue digest can be delivered automatically, and only to the owner's own Telegram chat.

## Phases and dependencies

1. Repository/configuration, Compose, SQL, model schemas and environment contract. Validate configuration before service integration. Publish only localhost n8n and SearXNG ports; PostgreSQL and worker stay internal. Use volumes, restart policies and health checks. Compose requires secrets via .env and fails clearly if absent.
2. HTTP/SearXNG/Ollama clients, optional Crawl4AI diagnostic profile, health checks. Extraction adapter is deferred. Ollama from containers is `http://host.docker.internal:11434`; direct host diagnostics use localhost. Qwen3.5 4B uses about 8K context and 9B about 16K. Source text budget is bounded below context limits. Health tools distinguish PASS, FAIL and NOT AVAILABLE.
3. Discovery/scout, offline domain normalization/deduplication, persistence, workflow 01. Prove new/rejected/retry paths with fixtures before the next stage.
4. Research queries and targeted extraction (4–8 pages), structured evidence validation, scoring/tiering, atomic persistence and workflow 02. Test fabricated URL/excerpt rejection and failures before drafting.
5. Conservative contact extraction, evidence-only draft input, workflow 03 and persisted human review state. Confirm no send node/API/dependency exists; support reviewing records remotely through n8n.
6. Windows scripts, backup/restore notes, Tailscale Serve, honest handoff verification. Keep scripts within Windows setup; no Mac paths in runtime.

## Deployment and failure boundaries

Keep Ollama native and private. Containers may require Windows Ollama's bind address to accept Docker connections; document explicit Windows environment/restart steps and firewall restriction rather than implying localhost always works. Do not open port 11434 to public networks. Tailscale Serve publishes only n8n to the tailnet (`tailscale serve --bg 5678`); no Funnel or router forwarding. Configure n8n's actual Tailscale HTTPS URL after Serve reports it; create the n8n owner account before remote use.

Network calls have timeouts and bounded results; HTTP/model failures are surfaced, not converted into success. Search returning no results is different from search failing. Model output is JSON-schema constrained where supported and independently parsed/range-checked. Bad responses do not silently become plausible research. Database writes for a completed stage are transactional. No concurrent run should duplicate records or overwrite approved drafts. Back up PostgreSQL plus n8n encryption key and volume; restoration is an explicit separate operation.

## Verification and handoff

Run fixture-based unit/integration tests for URL/domain normalization, exact rubric boundaries, evidence/contact rejection, persistence idempotency and pipeline stage contracts; mock external dependencies honestly. Validate every JSON, YAML/Compose when available, Python syntax, SQL structure and workflow endpoint alignment. Live PostgreSQL initialization and n8n importability require Docker and must not be claimed from static inspection.

Current development environment: empty Git repository, Python 3.9.6, no Docker or PowerShell discovered. Prefer Mac-testable Python syntax compatible with 3.9 where practical; container runtime may use 3.12. Record actual checks in README rather than hypothetical successes.

Windows-only acceptance: NVIDIA driver/GPU loading and 4B/9B performance; Docker-to-native-Ollama networking; PowerShell helpers; native Tailscale Serve and Mac access from an external network; real company pipeline and later scheduled/nightly operation. Start manually; scheduling is a documented follow-up once a real end-to-end run succeeds.

Official interface references consulted: [Crawl4AI self-hosting](https://docs.crawl4ai.com/core/self-hosting/), [Crawl4AI quick start](https://docs.crawl4ai.com/core/quickstart/), [n8n Execute Sub-workflow](https://docs.n8n.io/integrations/builtin/core-nodes/n8n-nodes-base.executeworkflow/). Workers should verify actual installed versions and avoid treating current `latest` interfaces as tested.

Final implementation bounds: scout model timeout defaults/caps at 120 seconds; research model timeout defaults to 900 seconds and caps at 1200 per call; fetch timeout defaults to 30 seconds and caps at 60. Research may use two model calls, eight fetches and five searches. n8n HTTP stages allow 60 minutes; stale-stage recovery waits 90 minutes. Run sequential batches conservatively. These limits are configuration bounds, not measured GPU performance. Stored research summaries derive from validated evidence claims and citations; scores/outreach interpretations remain judgments. Crawl4AI is diagnostic-profile-only; no extraction adapter is implemented.

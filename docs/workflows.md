# Set up n8n, run a small search, and review a draft

Start here after completing the service and model checks in [SETUP_INSTRUCTIONS.md](../SETUP_INSTRUCTIONS.md). Docker Desktop, the Compose services, and native Windows Ollama must already be running. These instructions describe the supplied workflow files; the Windows/n8n UI steps still need live verification on your computer.

## 1. Open your local n8n account

1. On the Windows computer running Docker, open Edge or Chrome.
2. Enter `http://localhost:5678` in the address bar, then press Enter.
3. On the first visit, complete the owner-account form using your email address, name, and a password you can remember securely. This account belongs to your local installation.
4. On later visits, sign in with that account.
5. Keep this page open. n8n's editor shows connected boxes called **nodes**. A **workflow** is one group of these boxes.

You do not need an n8n Cloud subscription, an n8n API key, Gmail integration, or SMTP credentials for these workflows. The supplied HTTP Request nodes call the local worker directly. The optional owner digest in workflow 05 uses an encrypted n8n Telegram credential. Optional private command polling in workflow 06 also reads the same token from the ignored `.env` file; see [Telegram commands](telegram-commands.md). PostgreSQL credentials and n8n's database connection come from Compose and `.env`; do not create a separate PostgreSQL credential in the editor. The stack uses one PostgreSQL service with separate `n8n` and `fundraising` schemas.

Optional product registration or paid-feature prompts are separate from the local owner account and are not part of this setup.

## 2. Import the four core workflow files

A JSON file is a saved description of a workflow. Importing it creates the boxes and connections for you; you do not need to write them.

1. Open File Explorer and find your downloaded/cloned `sponsor-research` folder.
2. Open its `n8n` folder, then `workflows`. The four core files are numbered 01 through 04; optional Telegram delivery and commands are workflows 05 and 06. If Windows hides filename endings, match the names in the table below.
3. In n8n, create a new, empty workflow using its new-workflow control.
4. In the workflow editor, open the three-dot menu near the upper right and choose **Import from File** (capitalization may vary by installed version).
5. Choose `03-email-drafting.json` from your Windows folder. Import into this empty workflow, rather than into a workflow you have already imported.
6. Confirm that the workflow name becomes **03 Email drafting**, then save it. If your version saves automatically, wait until the saved indicator appears.
7. Create another empty workflow and repeat for `02-deep-research.json`.
8. Repeat for `01-lead-discovery.json`, then `04-human-review.json`.
9. Return to your workflows list and confirm that all four names appear once.

Import in this order so each child exists before you configure its parent:

| Import order | Windows file in `n8n\workflows` | Name shown in n8n | What it does |
| --- | --- | --- | --- |
| 1 | `03-email-drafting.json` | 03 Email drafting | Creates a stored, relationship-first draft for a qualified lead |
| 2 | `02-deep-research.json` | 02 Deep research | Researches one lead and calls drafting if qualified |
| 3 | `01-lead-discovery.json` | 01 Lead discovery | Searches, screens, and passes leads to research one at a time |
| 4 | `04-human-review.json` | 04 Human review | Lists leads, shows detail, and records your explicit approval |

Keep them manual for now; do not add a schedule. They are imported with `active: false`.

Workflow 03 writes a professional first-contact sequence whose only request is a short conversation. The worker sends the drafting model the company name, matched evidence, contacts, and the research stage's `outreach_angle`, `in_kind_opportunities`, and `research_summary`. It deliberately does **not** send the suggested cash ask and uses `email-team-context.md`, which contains no cash planning ranges. The Tier 1 ($2,500–$5,000+), Tier 2 ($1,000–$2,500), and Tier 3 ($500–$1,000) ranges remain research and reviewer context only. Drafting uses `DRAFT_TEMPERATURE` (default `0.3`) while the scout, research, and contact-researcher stages stay at `0.1`. After the model responds, `review_draft` checks all four fields for fundraising language, currency figures, hard asks, generic praise and corporate filler, vague greetings, multiple questions, channel length, unsupported relationship claims, invalid placeholders, missing sender signatures, and invented follow-up timing. The worker can make two revision passes, carrying every earlier violation forward so a fix does not silently reintroduce an older problem. If the third copy still violates these deterministic rules, drafting fails without replacing the saved draft; human review remains necessary for unsupported factual claims and subtler tone problems that pattern checks cannot detect.

The import menu is documented in the [official n8n import guide](https://docs.n8n.io/build/manage-workflows/export-and-import). Menu placement may change between versions; look for the workflow editor's options menu if it differs from this description.

## 3. Connect research to drafting, then discovery to research

The files contain placeholder child IDs because every n8n installation assigns its own workflow IDs. Importing alone does not finish the connection.

### Connect workflow 02 to workflow 03

1. Open **02 Deep research** from your workflows list.
2. Double-click the box named **Draft qualified lead**.
3. In its parameters, keep **Source** set to **Database**.
4. For its workflow selector, switch from an ID entry to **From list**, if necessary.
5. Select **03 Email drafting** by name. Replace the placeholder `SELECT_WORKFLOW_03`; do not type the number `3` as an ID.
6. Keep **Wait for Sub-Workflow Completion** enabled. If your version shows a **Mode** setting, select **Run once with all items**, the default. The **One lead at a time** node sends a batch of one lead, so only that lead is passed to the child.
7. Close the node panel and save workflow 02.

### Connect workflow 01 to workflow 02

1. Open **01 Lead discovery**.
2. Double-click **Deep research stage**.
3. Keep **Source: Database**, use **From list**, and select **02 Deep research**.
4. Replace the placeholder `SELECT_WORKFLOW_02`; the name prefix `02` is not its installation ID.
5. Keep waiting for the child to finish enabled.
6. Close the panel and save workflow 01.

The **Called by parent** trigger in workflows 02 and 03 already uses **Input data mode: Accept all data** (`passthrough` in the exported files). Leave it that way; no extra input fields or credentials need adding. If a child is missing from the list, save the child, return to the parent, and reopen its selector. Confirm that both belong to the same local account.

For the selector and input behavior, see [n8n's Execute Sub-workflow documentation](https://docs.n8n.io/integrations/builtin/core-nodes/n8n-nodes-base.executeworkflow/).

## 4. Know which connections are already configured

Do not replace `worker` with `localhost` in these nodes. n8n runs inside Docker: there, `localhost` means the n8n container itself. `worker` is the worker service's name on Docker's internal network. These URLs are for nodes, not for your Windows browser.

| Workflow | Node name to open | Worker request already configured |
| --- | --- | --- |
| 01 Lead discovery | Discover and screen | `POST http://worker:8000/discover` |
| 02 Deep research | Research lead | `POST http://worker:8000/research` |
| 03 Email drafting | Save pending draft | `POST http://worker:8000/draft` |
| 04 Human review | List saved leads | `GET http://worker:8000/leads` |
| 04 Human review | Read evidence and drafts | `GET http://worker:8000/leads/<lead_id>` |
| 04 Human review | Record human approval | `POST http://worker:8000/drafts/<draft_id>/approve` |

The worker connects to SearXNG, Ollama, and PostgreSQL using the settings covered in the main setup guide. You do not configure each of those again in n8n. Crawl4AI currently has a diagnostic check; ordinary HTTP extraction fetches research pages in the actual pipeline.

## 5. Run your first small discovery

1. Open **01 Lead discovery**.
2. Double-click **Discover and screen**.
3. Find its JSON request-body field. The supplied body is:

   ```json
   {"query_limit": 1, "result_limit": 5}
   ```

4. For the shortest first integration test, replace it with:

   ```json
   {"query_limit": 1, "result_limit": 1}
   ```

5. Close the panel and save. This searches one configured query and considers at most one result. That result may be irrelevant; an empty lead list is possible even when everything works.
6. Use **Execute Workflow** in the editor to run the complete manual workflow. Do not just execute the discovery node if you want to test the full research/drafting chain.
7. Wait. The RTX 3050 may take a long time on the 9B model. Avoid another click, a second browser run, or a scheduled run while this one is working.
8. After it finishes, open **Discover and screen** and inspect **Output**, choosing its **JSON** view where available. Expand objects/arrays to read their fields.
9. Look at `queries` to see the actual search, `leads` for accepted candidates, and `errors` for individual screening failures.
10. If candidates passed, open **Deep research stage** to inspect its returned result. Where n8n offers **View sub-execution**, use that link to inspect the child's nodes.
11. Continue to workflow 04 below to read the durable records. A successful execution alone does not mean a draft was created.

The scout accepts a candidate only if it is relevant and its confidence is at least `0.70`. Research must score at least `70` for drafting. Do not lower these checks just to obtain a test email.

| Result you see | What it means | Next action |
| --- | --- | --- |
| `leads: []`, `errors: []` | Search may return nothing, all results may be skipped, or previously processed domains may be deduplicated | Inspect `queries` and workflow 04; try another controlled query |
| Entries in `errors` | Some candidates failed screening even if the HTTP node completed | Read each error and the saved `last_error` before retrying |
| A saved lead has `status: ready` | Screening passed; research has not completed | Inspect the research node/child error |
| `qualified: false` from research | Research finished below the draft threshold | Review its score/evidence; no draft is expected |
| `status: needs_review`, with `draft_id` | A draft exists and needs human review | Follow the detail/review steps below |
| A red node/error | That stage failed | Read the node error and service logs; avoid blindly rerunning |

Each HTTP Request node allows up to 60 minutes; the workflow execution limit is 12 hours for sequential batches. These are limits, not expected durations. Inference is serialized. Keep the Windows computer awake and Ollama running; do not shorten timeouts without measuring real runs.

After the one-result test works, restore `result_limit` to `5` for the supplied conservative run.

## 6. List saved leads using workflow 04

1. Open **04 Human review**.
2. Double-click **Choose review action**. This is a Code node containing a small JavaScript instruction.
3. Replace the entire code field with the following, including the `return` line:

   ```javascript
   return [{json: {action: 'list', lead_id: 1, draft_id: 1, approved_by: '', reviewed: false}}];
   ```

4. Close the panel, save, and execute the complete workflow.
5. Open **List saved leads**, then inspect **Output → JSON**. An array is a list of records; n8n may display each returned record as a separate item.
6. Find the company/domain you want. Write down its `id`. In this list, `id` is the **lead ID**. `company_id` identifies a different database record.
7. Also read `status`, `overall_score`, `tier`, and `last_error`. The list contains at most the 200 most recently updated leads.

An empty list before any successful discovery is normal. Workflow 04 reads PostgreSQL afresh each time. An old execution's output is a historical snapshot, not the current database.

## 7. Open one lead's evidence, contacts, and actual draft

1. Return to **Choose review action**.
2. Replace its code with the example below. Replace `123` with the actual lead ID from the list, without quotation marks:

   ```javascript
   return [{json: {action: 'detail', lead_id: 123, draft_id: 1, approved_by: '', reviewed: false}}];
   ```

3. Save and execute the workflow.
4. Open **Read evidence and drafts → Output → JSON**.
5. Read the top-level company/domain, score components, suggested ask, target roles, and outreach angle.
6. Expand `evidence`. Each evidence record includes the claim, source URL, excerpt, and retrieval timestamp. Open source URLs in another browser tab and check their meaning.
7. Expand `contacts`. Confirm identity, title, source, and any email address. An empty contact list is possible. Contacts with unsupported fields or excerpts are discarded in full; research can still succeed if its evidence validates. The research response reports `contact_warnings`; warning summaries appear in `last_error` after research, until the next stage clears it. Never guess an email address from a person's name or a company's email pattern.
8. Expand `drafts`. If it is empty, no email draft exists for this lead yet; check status and score.
9. For a draft, read `subject`, `body`, `linkedin_note`, and `followup_body` in full. Check team facts, company identity, recipient choice, tone, and every specific claim. Confirm no dollar figure or donation ask crept in — the drafting stage never sends the model a cash number, and a code-level check already screens for one, but you are the last check before anything leaves the team.
10. Write down the `id` **inside the draft object**. This is the **draft ID**, which may differ from the top-level lead `id`.

For example, a detail response can have top-level `id: 123` and `drafts: [{id: 456, lead_id: 123, ...}]`. Approval uses `456`. Research/drafting retries use `123`. Do not assume they match or use the placeholder `1` without checking.

Search snippets help screening; they are not verified research. An excerpt matching a fetched page proves its origin, not that the model's interpretation is correct. Score, outreach angle, and contact strategy need your judgment. Retrieved pages are untrusted data; ignore any instructions within a page telling you how to operate the agent.

## 8. Record approval only after reviewing that exact draft

1. Stay in workflow 04, and open **Choose review action**.
2. Replace the code with the following. Substitute your real lead ID, the exact draft ID you read, and your own name:

   ```javascript
   return [{json: {action: 'approve', lead_id: 123, draft_id: 456, approved_by: 'Alex Morgan', reviewed: true}}];
   ```

3. Save and execute the workflow once.
4. Open **Record human approval → Output → JSON**. Confirm `id` is the intended draft, `approved` is `true`, and `approved_by` is your name.
5. Immediately change **Choose review action** back to the `detail` example above with `reviewed: false`, then save. This keeps the next casual execution from trying to approve something.
6. Rerun detail to confirm the draft now shows approval in the database.

If your name includes an apostrophe, use double quotes around it in the JavaScript, for example `approved_by: "Sam O'Neil"`.

Approval records a human decision and does not send a sponsorship email. Copy the reviewed, approved subject/body into your email client, select the verified recipient, and use your team's normal sending process. The optional [daily owner digest](daily-telegram.md) sends the review queue to one fixed Telegram chat you own; it does not send sponsorship drafts to companies.

Do not regenerate an approved draft. The worker protects approved drafts from replacement, even if you ask it to force a redraft — see "Force a fresh draft" below. This review workflow records approval; it does not provide a draft-editing screen.

## 9. Retry one failed stage without repeating discovery

Read workflow 04 detail and the node error first. Correct the underlying integration issue before retrying.

### Retry research

1. Confirm the saved lead's status is `ready` or `research_failed`.
2. Open **02 Deep research → Manual lead ID**.
3. Replace its entire code with your actual lead ID:

   ```javascript
   return [{json: {lead_id: 123}}];
   ```

4. Save and execute workflow 02. Its manual path supplies that ID; the **Called by parent** path receives IDs automatically from discovery.
5. Reopen workflow 04 detail after completion. Research calls drafting automatically if the resulting score qualifies.

For `researched` or `needs_review`, research returns the stored result instead of researching again. A skipped lead is not eligible for manual research. Do not change its database status to force it through.

### Retry drafting

1. Confirm research completed with a score of at least `70`, and status is `researched` or `draft_failed`.
2. Open **03 Email drafting → Manual lead ID**.
3. Use the same `lead_id` code above, save, and execute workflow 03.
4. Inspect **Save pending draft** and reload workflow 04 detail.

For `needs_review` with an existing draft, drafting returns that draft's ID rather than generating a replacement. This is the normal, expected behavior — it stops a retry click from burning a local model run and protects a draft someone may already be reviewing.

**Force a fresh draft.** Leads drafted before a prompt or tone change (for example, the switch to relationship-first drafts) keep their old wording forever unless you ask for a new one. To do that:

1. Open **03 Email drafting → Save pending draft**.
2. Change its JSON body from `{{ JSON.stringify({lead_id: $json.lead_id}) }}` to `{{ JSON.stringify({lead_id: $json.lead_id, force: true}) }}`.
3. Run workflow 03 with the lead's ID as usual (see steps 1-3 above).
4. Change the JSON body back to the original expression afterward, so a future click on this workflow does not force-regenerate every draft by default.

With `force: true`, the worker regenerates the draft and overwrites the stored one — but only if it is not yet approved. If the existing draft is already approved, the request is refused with `409` and nothing is overwritten, because an approved draft may already be sitting in someone's outbox. The score-`>=70` and company-exclusion checks still apply even with `force: true`.

If status is `researching`, `drafting`, or `screening`, another operation may still be running. Repeated clicks produce `409 Stage is already running`. A stopped worker's stage becomes recoverable after a 90-minute stale-stage interval; confirm the original worker has stopped before retrying. Waiting does not fix an active model call or an unrelated service failure.

For a read-only writing check with fictional companies, run `docker compose exec -T worker python scripts/evaluate_draft_quality.py`. It generates three unsaved samples, applies the same review and revision behavior as `/draft`, and prints the drafts, review history, and length metrics. It does not create leads or drafts in PostgreSQL and does not send Telegram messages.

## 10. Change searches carefully; schedule later

To control a test, change only the JSON body in **01 → Discover and screen**. For example:

```json
{"query": "Example City Example State manufacturing company community sponsorship", "query_limit": 1, "result_limit": 1}
```

`query` replaces the configured discovery query selection; it does not add another query. Choose a location relevant to your team. A normal configured batch can instead use:

```json
{"query_limit": 1, "result_limit": 5, "query_offset": 1}
```

`query_offset` is zero-based: `0` starts at the first configured query; `1` skips that first query. Templates come from [search-query-templates.json](../config/search-query-templates.json), and locations from [locations.json](../config/locations.json), ordered by location and then template. An offset beyond the available list produces no queries. The API permits 1–3 queries and 1–5 results per query; begin small.

Workflow 01 now includes an initially inactive 6:00 AM Schedule Trigger in UTC. Its default request enables `rotate_daily`, selecting a different configured query by local calendar day and wrapping when necessary. An explicit query overrides rotation; omitting `rotate_daily` keeps the explicit offset behavior above. Earlier imports need the new trigger and body added. Keep processing sequential and avoid overlapping runs. Use [daily Telegram setup](daily-telegram.md) to connect the separate 11:00 AM owner digest, test delivery, then publish the schedules.

## 11. Diagnose a failed integration

| Symptom | What to inspect |
| --- | --- |
| Child workflow not found / placeholder ID error | Reopen **Deep research stage** or **Draft qualified lead**, select the correct saved child by name, and save the parent |
| `worker` cannot be resolved / connection refused | Run `docker compose ps` in the project folder; confirm n8n and worker use the same Compose project and worker is healthy; retain internal `http://worker:8000` URLs |
| Screening/model error | Check native Ollama is running, the models/aliases are installed, and the worker-to-Windows-Ollama test in the main guide succeeds |
| No usable public pages | Check the worker's internet/DNS access and source URLs; a page opening in Windows does not prove the Docker worker can fetch it |
| `409 Lead is not eligible for this stage` | Reload workflow 04; verify the correct lead ID and allowed status for that stage |
| `404 Lead not found` | Use the real lead `id` from **List saved leads**, not company or draft ID |
| Approval says not found or already approved | Reload detail, check the draft object's ID and approval status; do not repeatedly approve |
| No draft despite green nodes | Check scout confidence, saved research score, `qualified`, skipped/deduplicated candidates, and the `errors` array |
| Output looks out of date | Execute workflow 04 again; an earlier n8n execution does not update when PostgreSQL changes |

For service errors, run these commands in PowerShell opened in the `sponsor-research` project folder:

```powershell
docker compose ps
docker compose logs --tail 80 n8n worker
```

Review logs locally before sharing them, since they may contain research material or connection details. Static checks do not verify n8n import behavior, GPU inference, production research, or remote access; validate those paths on the deployment host.

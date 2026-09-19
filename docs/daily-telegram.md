# Daily lead Telegram digest

The owner digest is sent to one fixed Telegram chat: your own conversation with your own bot. Sponsorship drafts still require human review; the digest never messages company contacts and never approves a draft.

Research starts at 6:00 AM and the digest starts at 11:00 AM, both in `UTC`. Delivery can take a little longer than the trigger time. Windows must be awake with Docker Desktop and Ollama running for either to work. Research that finishes after 11:00 appears in the next day's digest.

`rotate_daily` picks one configured query per **calendar day**, so each morning's run advances through the configured queries and wraps at the end. Pending leads can repeat in later daily digests until a draft is approved or the lead is excluded.

One bounded research run starts each morning. Keep an eye on execution history because overlapping manual and scheduled runs can make concurrent model calls fail fast with "Another inference is running."

Workflow 01 uses `{"query_limit":1,"result_limit":5,"rotate_daily":true}`. Ordinary Python rotates configured queries by local calendar day, wrapping at the end. An explicit `query` overrides rotation. Keep inference sequential and avoid manual runs while scheduled research is active.

Workflow 05 reads PostgreSQL through `GET http://worker:8000/digest`. It lists current qualified leads with source URLs and a draft status. Approved drafts and IMTS exclusions are omitted. Pending leads repeat until their drafts are approved; this is a review queue, not a promise of new leads every day. It checks up to 200 recent qualified pending records and displays up to 25. The digest discloses those limits and reports an empty queue when appropriate.

Telegram rejects any message over 4096 characters, so the worker returns the digest already split into `messages` parts under that limit. **Split digest parts** turns that array into one item per part and **Send owner digest** sends them in order, each labelled `(1/2)`, `(2/2)` and so on. A single line longer than the limit — an unusually long evidence URL — is shortened with `…` in the sent message only; the full `text` field still holds it.

## Why Telegram instead of email

Telegram delivers to your phone and to [web.telegram.org](https://web.telegram.org/), so the queue is readable at school without a mail client and without connecting a Google account. Nothing leaves your machine except the digest text you see in the preview. If your school network blocks Telegram, read the digest on your phone's cellular connection or run **Preview summary** later from home; this repository has no other delivery path.

## Create the bot and find your chat ID

The bot token is a password for sending as that bot. Keep it in n8n's credential store. Never paste it into repository files, screenshots or chat. If it leaks, open BotFather and use `/revoke` to issue a new one.

1. Install Telegram and sign in with your phone number. Any account you control works; this does not touch your school account.
2. Open a chat with **@BotFather** (verified, blue check) and send `/newbot`.
3. Give it a display name, for example `Robotics Team Leads`, then a username that must be unique and must end in `bot`, for example `example_robotics_leads_bot`.
4. BotFather replies with a token shaped like `8123456789:AAH...`. Copy it somewhere private for the next steps.
5. Open a chat with your new bot and press **Start** (or send `/start`). **Do not skip this.** Telegram forbids a bot from opening a conversation first, so sending before you press Start fails with `403 bot can't initiate conversation with a user`.
6. Find your numeric chat ID. Open `https://api.telegram.org/bot<YOUR_TOKEN>/getUpdates` in a browser, replacing `<YOUR_TOKEN>` with the whole token including the colon. Read the number at `result[0].message.chat.id` — a plain integer such as `5551234567`. If `result` is empty, send your bot another message and reload. Closing the tab afterwards is enough; the URL contains your token, so do not bookmark or share it.

## Connect the credential in n8n

1. Import or reopen workflow **05 Daily lead summary** and open the **Send owner digest** node.
2. Under **Credential to connect with**, create a new **Telegram API** credential, paste the token into **Access Token**, and save it.
3. Replace **Chat ID** — it ships as the placeholder `REPLACE_WITH_YOUR_TELEGRAM_CHAT_ID` — with the numeric ID from step 6 above. Type the number literally; do not use an expression, because the destination must never depend on lead data.
4. Leave **Append n8n Attribution** off and **Disable Web Page Preview** on. Keep **Parse Mode** set to **HTML**. The checked-in text expression escapes HTML characters so company names and evidence URLs render as ordinary text; n8n otherwise defaults omitted parse mode to legacy Markdown, which breaks values such as `needs_review`.

## Test and enable

1. Execute only **Read daily summary** first and inspect `title`, `text` and `messages`. It contains no sending action.
2. Execute **Split digest parts** and confirm you get one item per part, each with `part`, `parts` and `text`.
3. Execute workflow **05** once with the **Preview summary** trigger to send a real test message. Confirm it arrives in your bot chat, in order, and that multi-part digests read correctly.
4. Confirm workflow **01 → Deep research stage** selects the actual workflow **02**, and **02 → Draft qualified lead** selects the actual **03**.
5. Save and **Publish/Activate** workflow **05**, then workflow **01**. The schedule requires publishing. [Schedule Trigger documentation](https://docs.n8n.io/integrations/builtin/core-nodes/n8n-nodes-base.scheduletrigger/)
6. Confirm delivery after 11:00 AM the next day and inspect execution errors if it is missing. The schedule and Telegram delivery are not proven by fixture tests or a summary preview.

To pause the daily digest, unpublish/deactivate **05**. To pause daily research, unpublish/deactivate **01**. A repeated test execution sends another digest; there is no delivery ledger and no automatic send retry, so a partly sent multi-part digest resends from part 1.

## If nothing arrives

| Symptom | What to inspect |
| --- | --- |
| `403 bot can't initiate conversation with a user` | Open the bot chat and press **Start**, then rerun |
| `400 chat not found` | The chat ID is wrong or belongs to another account; redo `getUpdates` |
| `401 Unauthorized` | The token is wrong, has whitespace, or was revoked in BotFather |
| `400 message is too long` | Report it: the worker is meant to keep every part under 4096 characters |
| Node sends nothing, no error | **Read daily summary** returned an empty `messages` array; check the worker and database |
| Message arrives with stray `*` or broken words | Confirm Parse Mode is **HTML** and restore the checked-in HTML-escaping text expression |

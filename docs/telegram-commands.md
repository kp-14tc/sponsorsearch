# Telegram commands

Workflow **06 Telegram commands** polls Telegram once per minute from inside n8n, so the Windows computer does not need a public webhook, Cloudflare Tunnel, router forwarding or Tailscale Funnel. The bot token is used only by n8n and remains in the ignored `.env` file. The worker receives only parsed command metadata, never the token.

Only messages whose Telegram chat ID and sender ID both equal the configured owner chat are accepted. PostgreSQL stores the polling cursor and records each Telegram `update_id` before work starts, so restarts and repeated polls cannot run the same command twice. Invalid commands and messages from every other chat are silently discarded. Commands never approve or send sponsorship email.

Supported commands:

- `/search` runs the normal bounded rotating discovery query, researches returned candidates sequentially and saves pending drafts for candidates scoring at least 70.
- `/search precision machining near Example City Example State` uses that one bounded explicit search query instead.
- `/draft 8` creates or returns the pending draft for already-researched qualified lead 8, then sends the saved subject, email body, LinkedIn note and follow-up to the owner's Telegram chat for review. It fails for an unknown, excluded or unqualified lead.
- `/status` sends the same saved review queue as the daily 11:00 AM digest.

After `/draft`, the bot sends the complete saved draft to the owner. After `/search` or `/status`, it sends the current review queue. A search can take many minutes while the 9B model runs. Resend a failed command as a new Telegram message; claimed commands are not retried automatically.

## Finish the private setup

1. Open the ignored `.env` file. Add `TELEGRAM_BOT_TOKEN=` followed by the current BotFather token, with no quotes or spaces. Never put the token in `.env.example`, a workflow, screenshots or chat.
2. Set `TELEGRAM_OWNER_CHAT_ID=` to the same numeric private chat ID used by workflow 05.
3. Run `docker compose up -d --build worker n8n` so the worker receives the owner ID and n8n receives the token.

The provided Compose file sets `N8N_BLOCK_ENV_ACCESS_IN_NODE=false` because workflow 06 reads the token through `$env`. Limit workflow editing to the trusted instance owner; do not import untrusted workflows.
4. Run the database schema once against the existing volume: `Get-Content database/schema.sql | docker compose exec -T postgres psql -U frc -d frc`. If the `.env` database user or database name differs, substitute those values.
5. Import workflow 06 into the same n8n project. Select the actual workflows **01**, **03**, and **05** in its three Execute Sub-workflow nodes. Workflow 01 must have **Telegram command** connected to **Discover and screen**; workflow 05 must have **Called after command** connected to **Read daily summary**. The worker checks the owner chat ID from `.env` during cursor reads and command intake.
6. Publish workflows 01, 02, 03, and 05 after those edits. Workflows 02 and 03 must be published so n8n permits the command workflow to call them. Publish workflow 06 last.
7. Wait at least one polling minute before sending the first command. The first poll intentionally discards old bot messages and establishes a cursor.
8. Send `/status`. Confirm the review queue arrives once. Then try `/draft 8` or a bounded `/search ...` command.

To stop commands while keeping the daily digest, unpublish workflow 06. Revoking the BotFather token also stops both polling and Telegram delivery until `.env` and the n8n Telegram credential are updated.

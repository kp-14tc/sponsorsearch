# Private remote access from another device

Complete local Windows setup and create the n8n owner account before this optional stage. Keep n8n's Compose port bound to `127.0.0.1:5678`. Only n8n is shared for private review; PostgreSQL, worker, Ollama, and SearXNG do not need remote exposure.

## 1. Install and sign in on both devices

1. On Windows, download the [official Tailscale Windows installer](https://tailscale.com/download/windows), run it, and open Tailscale. Use its tray icon to sign in when prompted; complete sign-in in the browser.
2. On the client device you'll use for remote review, install [Tailscale](https://tailscale.com/download) for that platform. Open Tailscale and sign in with the **same account/tailnet** used on Windows. If your organization provides a tailnet, join the intended one on both devices.
3. Confirm both devices appear in the [Tailscale device console](https://login.tailscale.com/admin/machines). A **tailnet** is the private network of devices/users connected through this account; it is separate from your home Wi-Fi. Tailscale authentication is separate from the n8n owner login.
4. On Windows, open a new normal PowerShell and run `tailscale status`. Expect both devices in the list. If the command is not recognized, reopen PowerShell after installation. Confirm Tailscale is connected on the client device too.

Do not buy a domain, open router ports, or install a public tunnel. Tailnet members allowed by your Tailscale access policy can reach shared services; restrict that policy if other members should not have access.

## 2. Share Windows n8n privately with Serve

Verify Windows `http://localhost:5678` works first. In normal Windows PowerShell:

```powershell
tailscale serve --bg 5678
tailscale serve status
```

If prompted to enable HTTPS certificates, open the link Tailscale prints, sign in, and follow the enablement steps; then rerun the command. Copy the **actual HTTPS URL** printed by Serve, such as your machine's own `https://...ts.net` address. Do not use a guessed hostname or literally copy an example from documentation. `--bg` keeps the Serve configuration active after closing PowerShell. [Official Serve reference](https://tailscale.com/docs/reference/tailscale-cli/serve).

Serve forwards that private HTTPS address to Windows n8n on localhost. **Serve** is private to the tailnet; **Funnel** exposes services publicly and is not part of this setup. Do not serve port 11434, port 8080, or the database.

## 3. Tell n8n its private HTTPS address

From the project folder on Windows:

```powershell
Set-Location "$env:USERPROFILE\Projects\sponsor-research"
notepad .env
```

Change only these three settings using the exact URL you copied:

- `N8N_EDITOR_BASE_URL=` followed by the HTTPS base URL, without a final slash.
- `WEBHOOK_URL=` followed by the same URL **with** a final `/`.
- `N8N_PROXY_HOPS=1`, because this setup has one Serve proxy in front of n8n.

Save with Ctrl+S and close Notepad. Keep the existing secrets and n8n encryption key. Apply the settings:

```powershell
docker compose up -d --force-recreate n8n
```

Wait until Windows `http://localhost:5678` loads again; container startup can take time. Then run:

```powershell
docker compose exec -T worker python scripts/healthcheck.py --inside --service n8n
tailscale serve status
```

Expect n8n health `PASS` and the same private HTTPS address. The container recreation keeps the existing database/volumes. Secure cookies remain enabled.

## 4. Log in from the client device and test away from home

1. Open the exact Serve HTTPS URL in a browser on the client device while Tailscale is connected.
2. Log in with the **existing n8n owner email/password created on Windows**, not the `.env` database password and not your Tailscale password. You should see the same imported workflows. Do not create a second installation on the client device.
3. Use workflow **04** to list/reload the current database records. Old n8n execution output can be stale; use the [review instructions](workflows.md).
4. To verify remote access, keep the host powered on and connect the client through a separate external network. Leave Tailscale connected and repeat login/review. Record the result in your operational notes.

## 5. If it does not work

| Symptom | Check |
|---|---|
| Client device opens its own localhost and sees nothing | Use the actual Windows Serve HTTPS address. |
| Serve asks for HTTPS enablement | Follow its printed enablement link, then repeat Serve. |
| HTTPS address unreachable | On Windows run `tailscale status` and `tailscale serve status`; confirm both devices use the same tailnet and access policy permits the connection. |
| Serve reports backend unreachable | Confirm Docker Desktop is running and Windows localhost n8n loads; inspect `docker compose ps` and n8n logs. |
| Login fails | Use the local n8n owner account; verify the URL points to your Windows machine. |
| Works until Windows sleeps | Keep Windows awake/plugged in; see [Windows availability](windows-setup.md#2-keep-the-desktop-available). |
| Settings seem unchanged | Save the real `.env` and recreate n8n using section 3; restarting the browser alone does not apply container settings. |

To remove this project's forwarding, inspect `tailscale serve status` first. `tailscale serve reset` removes **all Serve configuration on that Windows machine**, including any unrelated service you may share. Only use reset if that is your intent. Without remote access, restore local `.env` URLs and `N8N_PROXY_HOPS=0`, then recreate n8n. Do not troubleshoot by enabling Funnel or forwarding ports at the router.

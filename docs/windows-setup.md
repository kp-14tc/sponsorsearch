# Windows installation and integration checks

This is the detailed companion to [SETUP_INSTRUCTIONS.md](../SETUP_INSTRUCTIONS.md). For an empty local Windows account, begin with [fresh-profile setup](fresh-windows-profile.md). Use Windows 11 with native Ollama and Docker Desktop's WSL2/Linux-container backend. Run project commands in **normal PowerShell** after `Set-Location "$env:USERPROFILE\Projects\sponsor-research"`, except explicitly marked Administrator steps. Use your actual path if the project already lives elsewhere.

## 1. Install the prerequisites

### NVIDIA driver

1. Open [NVIDIA's official driver page](https://www.nvidia.com/en-us/drivers/), select the actual GeForce RTX 3050 variant in your desktop and Windows 11, and install the appropriate current driver. Restart Windows if requested.
2. Open normal PowerShell and run `nvidia-smi`. Expect a table showing the NVIDIA GPU and driver version. If the command is unavailable, reopen PowerShell after restarting and check that the driver installed successfully. Seeing this table establishes driver detection; it does not yet prove Ollama uses the GPU.

### WSL2

1. Open **Administrator PowerShell**: Start → type PowerShell → right-click → Run as administrator.
2. For a computer without WSL, run `wsl --install --no-distribution`. Follow Windows prompts and reboot. A separate Ubuntu installation and Linux account are unnecessary for this PowerShell-based project. If the Store download fails, use `wsl --install --no-distribution --web-download`. See [Microsoft's WSL commands](https://learn.microsoft.com/en-us/windows/wsl/basic-commands).
3. In PowerShell run `wsl --update`, `wsl --set-default-version 2`, then `wsl --version` and `wsl --status`. Docker currently requires WSL **2.1.5 or newer**; use current stable WSL. If updating through the Store fails, use `wsl --update --web-download`. `wsl --list --verbose` may list no distributions before Docker creates its own; that is expected with `--no-distribution`. Docker's distributions must use version **2**. Leave an existing Ubuntu distribution installed; it is not needed for this setup. [Docker's WSL documentation](https://docs.docker.com/desktop/features/wsl/)
4. If Windows reports virtualization disabled, enable hardware virtualization in your PC firmware using your PC manufacturer's instructions. Do not continue until WSL works.

### Docker Desktop

1. Download the Windows AMD64 installer from the [official Windows installation instructions](https://docs.docker.com/desktop/setup/install/windows-install/). On current installers, choose the recommended **per-user** installation under your intended Windows account, then choose **Use WSL 2 instead of Hyper-V** when offered. Restart if requested. Enabling WSL needs Administrator access even though ordinary per-user Docker installation does not.
2. Launch Docker Desktop from Start and complete its onboarding. No registry login is required to run this project's public images.
3. In Docker Desktop's Settings → General, check **Use the WSL 2 based engine** when that setting is available; choose Apply/Restart if you changed it. Use **Linux containers**. If Docker's tray menu offers **Switch to Linux containers**, select it; if it offers **Switch to Windows containers**, you are already using Linux containers.
4. Wait for Docker Desktop to indicate the engine is running. Open a new normal PowerShell and run:

```powershell
docker version
docker compose version
docker info --format '{{.OSType}}'
```

Expect both Client and Server sections in `docker version`, a Compose version, and `linux` from the last command. A named-pipe/daemon connection error usually means Docker Desktop has not finished starting or its engine failed; inspect Docker Desktop rather than reinstalling the project.

### Git and Ollama

1. Install [Git for Windows](https://git-scm.com/downloads/win); the default installer options are sufficient for using Git from PowerShell. Open a new PowerShell and run `git --version`.
2. Download [Ollama for Windows](https://ollama.com/download/windows), install it, and launch it from Start. Ollama runs on Windows directly, not inside WSL or a container. Run `ollama --version` in a new PowerShell.
3. Return to [Repository setup](../SETUP_INSTRUCTIONS.md#2-repository) to clone and configure the project. No separate PostgreSQL, SearXNG, Python, Node.js, or n8n installer is needed: Docker supplies them.

## 2. Keep the desktop available

For long research or remote access, keep Windows plugged in. In **Settings → System → Power** (or **Power & battery**) find screen/sleep settings and set plugged-in device sleep to **Never** while operating the agent. Letting the display turn off or locking the screen is okay; sleeping or shutting down interrupts services. The exact setting label varies by Windows version. Start Docker Desktop and Ollama after signing in following a reboot; containers' restart policy cannot launch these Windows applications itself.

## 3. Download and test both models

In normal PowerShell:

```powershell
ollama pull qwen3.5:4b
ollama pull qwen3.5:9b
ollama list
Invoke-RestMethod http://localhost:11434/api/tags
```

Wait for each download to complete. `ollama list` should include both exact names; `/api/tags` should return a `models` field. If Windows cannot connect to localhost, launch Ollama and retry before changing any firewall settings. Models come from the [official Qwen3.5 library](https://ollama.com/library/qwen3.5); no cloud API key is needed.

Now test **real inference**, not just the downloaded names. Copy this entire block together:

```powershell
$probe = @{
  model = 'qwen3.5:4b'
  stream = $false
  think = $false
  format = @{
    type = 'object'
    properties = @{ ok = @{ type = 'boolean' } }
    required = @('ok')
    additionalProperties = $false
  }
  messages = @(@{ role = 'user'; content = 'Return {"ok":true}.' })
}
$reply = Invoke-RestMethod -Method Post -Uri 'http://localhost:11434/api/chat' -ContentType 'application/json' -Body ($probe | ConvertTo-Json -Depth 10) -TimeoutSec 1200
$reply.message.content
($reply.message.content | ConvertFrom-Json).ok
```

Expect JSON containing `"ok":true`, then `True`. In the **same PowerShell window**, test the research model separately:

```powershell
ollama stop qwen3.5:4b
$probe.model = 'qwen3.5:9b'
$reply = Invoke-RestMethod -Method Post -Uri 'http://localhost:11434/api/chat' -ContentType 'application/json' -Body ($probe | ConvertTo-Json -Depth 10) -TimeoutSec 1200
$reply.message.content
($reply.message.content | ConvertFrom-Json).ok
```

Again expect JSON and `True`. Leave the models processing until a result/error returns. In a **second normal PowerShell** during inference, run `ollama ps` and `nvidia-smi`. Record elapsed time and the `PROCESSOR` column: GPU, CPU, or a split. The 9B model may partly load into CPU memory and be slow on this desktop. These tiny probes do not establish real-company quality or production latency. [Ollama explains GPU allocation and Windows configuration](https://docs.ollama.com/faq).

## 4. Native Ollama from Docker

After starting the stack in main-guide Stage 6, run:

```powershell
docker compose exec -T worker python -c "import urllib.request; print(urllib.request.urlopen('http://host.docker.internal:11434/api/tags', timeout=15).read().decode())"
```

Expect JSON listing both models. `host.docker.internal` is [Docker Desktop's host address](https://docs.docker.com/desktop/features/networking/); `localhost` inside worker would mean the worker container itself. Do not change `.env`'s `OLLAMA_URL` to Windows localhost.

### If Windows localhost works but Docker cannot connect

1. Find Ollama in the Windows system tray (use the up-arrow near the clock if hidden), right-click it, and **Quit**.
2. Press Start and search **Edit environment variables for your account**. Open the result.
3. In the **User variables** area choose **New** (or select an existing variable and Edit): name `OLLAMA_HOST`, value `0.0.0.0:11434`. Add `OLLAMA_NO_CLOUD` with value `1` to disable optional cloud features. These are Windows user settings, separate from the project's `.env`.
4. Click OK to save and close the dialogs. Start Ollama from Start. Merely typing an environment variable in PowerShell does not update an already running tray app. This follows the [official Windows environment/restart procedure](https://docs.ollama.com/faq).
5. Keep Windows Defender Firewall enabled. If Windows asks to allow broad network access, do not grant a broad exception; use the restricted rule below. Retry Windows localhost and the Docker check.

`0.0.0.0` makes Ollama listen on network interfaces. If an existing broad inbound Ollama rule is enabled, narrow/disable that allowance before using this configuration. Never publish port 11434 through router forwarding or Tailscale.

### Restricted Windows firewall rule, only if needed

The source address Windows sees for Docker traffic depends on Docker/WSL networking and may be proxied. **Do not guess a subnet or copy someone else's address.** Use an observed address to create a narrow rule:

1. Press Start, search **Windows Defender Firewall with Advanced Security**, right-click and run as administrator. Windows may require an administrator password.
2. Click **Inbound Rules**. Inspect existing Ollama or TCP 11434 allow rules: open Properties → Protocols and Ports and Scope. Disable broad Ollama allowances (right-click → Disable Rule); do not disable unrelated Windows rules or the firewall itself.
3. To identify a dropped request, select the top **Windows Defender Firewall with Advanced Security on Local Computer** item, open **Properties**, and on the relevant Domain/Private/Public profile tab choose **Logging → Customize**. Set **Log dropped packets → Yes**, note the log filename, and save. If the applicable profile is unclear, enable dropped logging for all three profiles and give each a distinct filename in the same folder: `pfirewall_Domain.log`, `pfirewall_Private.log`, and `pfirewall_Public.log`. The matching file then identifies the profile. [Microsoft's firewall logging guide](https://learn.microsoft.com/en-us/windows/security/operating-system-security/network-security/windows-firewall/configure-logging) explains these fields.
4. Rerun the Docker Ollama check once and note its time. Open the noted log file(s) using Administrator Notepad. Read the `#Fields:` header: find a fresh `DROP TCP` row with destination port `11434` matching this attempt. Its `src-ip` is the remote address for the rule. Do not use `dst-ip`, the computer's LAN IP, or an unrelated old row. If no matching drop exists, this may be a bind/proxy/routing issue rather than firewall filtering; inspect Ollama logs/restart instead of widening access.
5. In **Inbound Rules → New Rule**, choose **Custom**. Select **All programs** for this narrowly port/address-scoped rule; choose TCP and **Specific local ports: 11434**. In **Scope**, leave local addresses as supplied; under **Remote IP addresses** choose **These IP addresses → Add** and enter the exact observed `src-ip` as a single IP address. Choose **Allow the connection**, select only the profile(s) that generated the observed dropped request, and name it `FRC Ollama from observed Docker source`.
6. Open the new rule's Properties → Scope and confirm it contains that single remote IP, not **Any IP address** or **LocalSubnet**. Retry the Docker check; it must return model JSON.
7. Confirm an unrelated LAN computer cannot open `http://<Windows-LAN-IP>:11434/api/tags`. Obtain the desktop's actual LAN IPv4 address with `ipconfig` under its Wi-Fi/Ethernet adapter; do not literally enter the placeholder. If it succeeds, another broad allowance exists: inspect rules and correct it before continuing.
8. Docker/WSL source addresses can change after reboot. If the bridge later fails, repeat observation and update the narrow rule. Logging can be returned to its original settings after diagnosis. If the source/profile is ambiguous, get help with this specific networking step; do not solve it by allowing everyone.

Return to main-guide Stage 6 and rerun the full inside health check after the bridge works.

## 5. Verify the integrations

### PostgreSQL and its tables

The first startup with an empty volume runs `database/schema.sql`. Check connectivity:

```powershell
docker compose exec -T worker python scripts/healthcheck.py --inside --service postgres
```

Expect `PASS: postgres: PostgreSQL query succeeds`. Then list tables directly:

```powershell
docker compose exec -T worker python -c "import psycopg; print(psycopg.connect().execute('SELECT tablename FROM pg_tables WHERE schemaname=%s ORDER BY tablename', ('fundraising',)).fetchall())"
```

Expect five fundraising tables: `companies`, `contacts`, `email_drafts`, `evidence`, and `leads`. n8n also uses this database, in its own `n8n` schema. No n8n PostgreSQL credential connector is necessary.

An existing volume does not rerun initial SQL. If tables are missing, inspect `docker compose logs --tail 100 postgres`. Do not delete the volume. For an intentional schema rerun after checking the file and backing up existing data:

```powershell
Get-Content -Raw database/schema.sql | docker compose exec -T postgres sh -c 'psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB"'
```

This file is not a general migration system for future changes.

### SearXNG JSON search

From Windows:

```powershell
$search = Invoke-RestMethod 'http://localhost:8080/search?q=industrial+automation+Example City+Illinois&format=json'
$search.results.Count
$search.results | Select-Object -First 3 title,url
```

Expect JSON conversion without an HTTP error, a count, and ideally company/source results. A count of zero confirms an empty search response, not useful discovery: inspect engine errors/logs and try a relevant query before the research batch. The container connection check is:

```powershell
docker compose exec -T worker python scripts/healthcheck.py --inside --service searxng
```

Expect `PASS`; the health check verifies a results list but does not require it to be nonempty. JSON is enabled in `config/searxng/settings.yml`. No SearXNG API key or separate SearXNG account is needed.

### Worker and n8n

```powershell
docker compose exec -T worker python scripts/healthcheck.py --inside --service worker
docker compose exec -T worker python scripts/healthcheck.py --inside --service n8n
```

Expect `PASS` for each. The worker's `/health` endpoint is internal; `http://localhost:8000` in your Windows browser will not work because Compose publishes no worker port. Likewise PostgreSQL has no published port. Open Windows `http://localhost:5678` for n8n, then main-guide Stage 7.

## 6. If PowerShell blocks the helper scripts

Manual Compose commands work without script execution. If you want the convenience helpers and see `running scripts is disabled on this system`, first inspect them in Notepad. In **normal PowerShell** run:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy RemoteSigned
Unblock-File .\scripts\windows\*.ps1
.\scripts\windows\check-prereqs.ps1
.\scripts\windows\test-ollama.ps1
.\scripts\windows\start.ps1
```

Answer the policy confirmation if prompted. `Process` affects only the current window and disappears when it closes; no Administrator window or permanent machine policy change is needed. `Unblock-File` removes downloaded-file blocking only from those inspected helper files. An organization's Group Policy can override this: use the manual commands rather than bypassing organization controls. See [Microsoft's execution-policy reference](https://learn.microsoft.com/en-us/powershell/module/microsoft.powershell.security/set-executionpolicy).

`test-ollama.ps1` checks native API availability and both downloaded model names; it does not test inference. Use the separate 4B and 9B structured-output probes in section 3.

## 7. Troubleshooting

| Symptom | Next action |
|---|---|
| `git`, `docker`, or `ollama` is not recognized | Finish its installation, close/reopen PowerShell, rerun its version command. |
| Docker daemon/named-pipe connection error | Start Docker Desktop, wait for its engine, verify Linux/WSL2 settings. |
| `no configuration file provided` | Run `Set-Location "$env:USERPROFILE\Projects\sponsor-research"` (or your actual project path); verify `Get-ChildItem compose.yml`. |
| Missing-variable error from Compose | Check `.env` exists without `.txt`, then complete secrets. Use `docker compose config --quiet`; plain `config` can print passwords. |
| Startup wait times out | Run `docker compose ps` and `docker compose logs --tail 100 worker n8n searxng postgres`; identify the failing service before retrying. |
| Native Ollama connection refused | Launch/restart Ollama; retry localhost tags before Docker networking. |
| Native tags work; container tags fail | Use section 4's environment/restart and observed-source firewall procedure. |
| Model missing / `model not found` | Run both exact `ollama pull` commands; compare `.env` model names to `ollama list`. |
| Inference slow or timeout | Inspect `ollama ps`, `nvidia-smi`, and available memory; run one model/lead at a time. Record time before changing bounded timeouts. |
| SearXNG HTTP 403 or invalid JSON | Check SearXNG logs and JSON format in its settings; public engines may independently rate-limit. |
| SearXNG returns zero results | Inspect engine failures; try a specific relevant query. Do not treat no results as evidence about a company. |
| PostgreSQL password authentication failed after editing `.env` | Existing database kept its original account password. Restore matching settings or follow deliberate database credential maintenance after backup; do not delete data. |
| Workflow stage fails | Load current review detail and `last_error`; use [retry instructions](workflows.md). Do not fill gaps with invented evidence. |
| Public page yields no usable text | Skip or review manually; dynamic sites may not work with HTTP extraction. |
| Optional Crawl4AI says `NOT AVAILABLE` | Expected: it is not needed or connected to the research pipeline. |

The optional Crawl4AI profile is diagnostic only. The pipeline uses bounded HTTP extraction, not browser automation. Scout calls are capped at 120 seconds; research at 1200 seconds per call; fetches at 60 seconds per page. Research may require two sequential model calls, up to eight fetches, and five searches. n8n allows 60 minutes per HTTP stage and 12 hours per workflow; these are limits, not measured RTX 3050 performance.

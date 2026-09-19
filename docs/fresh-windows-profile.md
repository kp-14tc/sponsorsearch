# Set up the agent from an empty Windows local profile

Use this guide when you have signed into a new **Windows 11 local account** and have installed nothing for this project. This walkthrough assumes an **RTX 3050 and 16 GB system RAM**. Keep using this same Windows account for Ollama, Docker Desktop, project files and everyday operation.

An empty profile is not a new Windows installation: Windows updates, NVIDIA drivers and firmware settings affect the whole computer. Reuse working installations where appropriate. These instructions have been checked against official documentation, but have **not been executed on your Windows computer**.

## 1. Know which accounts and permissions you need

| Item | What you need |
|---|---|
| Windows login | Your existing local account. You can keep it local. |
| Administrator access | Needed for enabling WSL, installing the NVIDIA driver and any required firewall changes. A standard account can use the services afterward. |
| GitHub | No account or token needed to download this public repository. |
| Docker Desktop | Install the application and complete its onboarding; a Docker Hub login is not required for ordinary public-image downloads. |
| Ollama | Native Windows application and local model downloads; no cloud API key needed. |
| n8n | Create its own owner login after the containers start. This is separate from Windows and database passwords. |
| Tailscale | Optional, only for private access from another device; needs an identity-provider sign-in. It does not require converting your Windows login to a Microsoft account. |

Open **normal PowerShell** by pressing Start, typing `PowerShell`, and selecting the app. For an **Administrator PowerShell** step, right-click the result and select **Run as administrator**. Accept the Windows prompt or enter the computer administrator's credentials. A local account can be either an administrator or a standard user; being local alone does not tell you which.

If an Administrator window uses a different person's credentials, close it after the machine setup step. Install per-user applications, set Ollama user variables and run the project from your own normal account. Otherwise you can accidentally install or configure Ollama under the wrong profile.

Paste commands into PowerShell, not Command Prompt, Ubuntu or Git Bash. Paste each line separately unless a step explicitly says to copy the whole block. Wait for the `PS ...>` prompt before continuing. Text inside a code block is the command; do not copy the Markdown fences.

## 2. Prepare Windows and check the hardware

1. Connect the computer to power and the internet. Ethernet is useful if available; Wi-Fi works too.
2. Open **Settings → Windows Update → Check for updates**. Install updates offered for a currently supported Windows 11 release, restart when asked, and check again. Use the ordinary release channel. Docker's minimum build is not a promise that an old Windows release still receives support. See [Microsoft's release information](https://learn.microsoft.com/en-us/windows/release-health/windows11-release-information).
3. Open **Settings → System → About**. Record the processor, installed RAM, Windows edition and system type. This RTX 3050 guide uses **64-bit Windows on an x64 processor**, so download Windows **AMD64/x86-64** installers; AMD64 also applies to Intel x64 CPUs.
4. Press **Ctrl+Shift+Esc** for Task Manager. Select **Performance → CPU**, expanding the left navigation if necessary. Check **Virtualization: Enabled**. If disabled, use your PC/motherboard manufacturer's firmware instructions to enable hardware virtualization, often called Intel VT-x or AMD SVM, then restart. Do not change unrelated firmware settings.
5. In File Explorer select **This PC** and check the free space on your SSD. Roughly **100 GB free is a comfortable starting allowance**, not a measured project requirement. Docker images, its Linux virtual disk, models and backups all need room to grow. Keep the Windows profile and Docker/model data on an SSD when possible.
6. If your local account has no password, add one in **Settings → Accounts → Sign-in options → Password** before enabling remote access. Lock the screen with **Windows+L** when stepping away.

Windows 11 Home can use Linux containers through WSL2; this project uses Linux containers. Check [Docker's current Windows requirements](https://docs.docker.com/desktop/setup/install/windows-install/) for your installed release.

## 3. Install the NVIDIA driver

1. Open the existing **Microsoft Edge** browser from Start; no extra browser is required.
2. Go to [NVIDIA's official driver download page](https://www.nvidia.com/en-us/drivers/). Choose the actual RTX 3050 desktop/laptop variant and Windows 11. Download a current driver supported for that GPU.
3. Open the downloaded installer from **Edge Downloads** or File Explorer's **Downloads** folder. Follow the installer and grant Administrator access when requested. Restart afterward if requested.
4. Open a **new normal PowerShell** and run:

   ```powershell
   nvidia-smi
   nvidia-smi --query-gpu=name,memory.total,driver_version --format=csv
   ```

5. Expect the RTX 3050 and a driver version. Write down its **dedicated GPU memory**: RTX 3050 variants differ, and 16 GB system RAM is not 16 GB GPU memory. If the command is not recognized, restart/reopen PowerShell and check the driver installation.

This proves Windows detects the NVIDIA driver. GPU inference is checked later with Ollama running a model.

## 4. Install WSL2 without an extra Ubuntu installation

WSL2 provides the Linux environment used by Docker Desktop. Ollama will run directly on Windows, so you do not need to install Linux NVIDIA drivers, CUDA Toolkit or another Docker Engine inside Ubuntu for this project.

1. Open **Administrator PowerShell**. For a computer without WSL, run:

   ```powershell
   wsl --install --no-distribution
   ```

2. Restart Windows and sign back into your intended local account. Close any Administrator window afterward.
3. If the initial download was blocked by the Store or stalled, use this Microsoft-supported download option from Administrator PowerShell, then restart if requested:

   ```powershell
   wsl --install --no-distribution --web-download
   ```

4. After signing back in, open PowerShell and run:

   ```powershell
   wsl --update
   wsl --set-default-version 2
   wsl --version
   wsl --status
   ```

5. Allow Administrator access if an update requests it. If the update's Store download fails, run `wsl --update --web-download`. Docker currently requires **WSL 2.1.5 or newer**; installing the current stable WSL release is preferable.
6. Before Docker starts, `wsl --list --verbose` may report no installed distributions. That is expected with `--no-distribution`; Docker creates its own environment later. If Ubuntu is already installed, you can leave it installed and closed.

The `--no-distribution` and `--web-download` options are in [Microsoft's WSL command reference](https://learn.microsoft.com/en-us/windows/wsl/basic-commands). [Docker documents that a separate Linux distribution is unnecessary](https://docs.docker.com/desktop/features/wsl/).

## 5. Install Docker Desktop, Git and native Ollama

Download installers through Edge; you do not need winget or a Microsoft Store sign-in.

### Docker Desktop

1. Download **Docker Desktop for Windows AMD64** from [Docker's Windows installation page](https://docs.docker.com/desktop/setup/install/windows-install/).
2. Run the installer from your own account. Select **per-user installation** if offered; current Docker recommends this mode, and it does not need Administrator access for ordinary installation/updates. Older installers may request elevation.
3. Choose the **WSL 2** backend when offered. Use **Linux containers**.
4. Start **Docker Desktop** from Start after installation. Read and accept the displayed terms if applicable to your use, then complete onboarding. Skip the optional registry sign-in for now.
5. In **Settings → General**, confirm **Use the WSL 2 based engine** if the option is visible. It can be enabled automatically and hidden on some systems. Apply/restart after changing it.
6. Wait until the Docker engine is running. Open a new normal PowerShell:

   ```powershell
   docker version
   docker compose version
   docker info --format '{{.OSType}}'
   ```

7. Expect both **Client** and **Server** in the first output and `linux` in the last. If only Client works, open Docker Desktop and fix engine startup before continuing. You do not need to add your account to `docker-users` for the ordinary WSL2/Linux path.

### Git

1. Download the 64-bit installer from [Git for Windows](https://git-scm.com/downloads/win).
2. Follow the installer. Keep the option that makes Git available from the command line and other software; ordinary default options are sufficient. If an installation scope choice appears, use your own account unless you need all-user installation.
3. Open a new normal PowerShell and run `git --version`. Expect a version number.

### Ollama

1. Download [Ollama for Windows](https://ollama.com/download/windows).
2. Run its installer **as your own user**, then open Ollama from Start. It normally installs into your profile without Administrator rights. [Official Windows installation notes](https://docs.ollama.com/windows)
3. Open a new normal PowerShell and run:

   ```powershell
   ollama --version
   Invoke-RestMethod http://localhost:11434/api/tags
   ```

4. Expect a version and a response containing `models`. An empty models list is fine before downloads. If the API cannot connect, start Ollama before adjusting network settings.

The other services are installed by Docker. You do not need host Python, Node.js, PostgreSQL, n8n, SearXNG, Visual Studio or VS Code to run this version.

## 6. Download the project into your own profile

In **normal PowerShell**, run:

```powershell
New-Item -ItemType Directory -Force "$env:USERPROFILE\Projects" | Out-Null
Set-Location "$env:USERPROFILE\Projects"
git clone https://github.com/YOUR_GITHUB_ACCOUNT/sponsor-research.git
Set-Location "$env:USERPROFILE\Projects\sponsor-research"
Get-ChildItem
```

`$env:USERPROFILE` expands to your own profile, such as `C:\Users\Alex`. This avoids needing permission to create a folder at the root of C:. It also keeps the project outside OneDrive/Desktop synchronization. If the destination already exists, inspect and reuse it; do not delete it to repeat cloning.

Expect `compose.yml`, `.env.example`, `SETUP_INSTRUCTIONS.md`, `config` and `n8n`. To open the folder in Explorer, run `explorer .`. Enable **View → Show → File name extensions**.

## 7. Configure and connect the integrations in order

Open **SETUP_INSTRUCTIONS.md** in this folder. You have completed its prerequisite and repository stages. Continue with [Configuration](../SETUP_INSTRUCTIONS.md#3-configuration).

Do these stages in this order:

1. **Settings:** copy `.env.example` to `.env` only for a new installation. Generate three different secrets using the main guide's PowerShell block. Set the database password, n8n encryption key and SearXNG secret; save `.env` without a `.txt` suffix. These secrets do not require online accounts.
2. **Team facts:** verify `prompts/team-context.md`, then the location/query configuration. Use Notepad; begin with the supplied JSON if unfamiliar with editing it.
3. **Models:** run `ollama pull qwen3.5:4b`, wait for completion, then `ollama pull qwen3.5:9b`. Use the separate structured-JSON inference checks in [Windows setup section 3](windows-setup.md#3-download-and-test-both-models). Model names appearing in a list do not prove inference works.
4. **Containers:** with Docker running, execute the main guide's `docker compose config --quiet`, then `docker compose up -d --build --wait --wait-timeout 180`, then `docker compose ps`. Downloads may take time. Configuration validation uses `--quiet` to avoid printing secrets.
5. **Ollama bridge:** test container access to `host.docker.internal:11434` using [Windows setup section 4](windows-setup.md#4-native-ollama-from-docker). If Windows localhost works but Docker fails, follow its exact bind/restart and narrow firewall procedure. Ollama's Windows user variables and the project's `.env` are separate settings. Keep the firewall enabled.
6. **Database/search/backend:** follow [Windows setup section 5](windows-setup.md#5-verify-the-integrations), checking the five PostgreSQL fundraising tables, useful SearXNG JSON results and service health. Compose already connects these; no separate n8n database/search credentials are needed.
7. **n8n:** open `http://localhost:5678` in Edge on Windows and create its owner login. Use [workflow instructions](workflows.md) to import 03, 02, 01 and 04 in order, choose the actual imported child workflows and save. Run one query/one result first. Inspect saved evidence and the pending draft, then explicitly record human review when appropriate.
8. **Performance:** once basic connections and model inference work, use [the performance guide](windows-performance.md). On a 16 GB host, begin with its 4 GB WSL memory budget, one loaded model and sequential processing. Record a baseline first and change one setting at a time. The 9B model can still be slow if it needs CPU offloading or Windows starts paging; settings cannot increase the GPU's VRAM.
9. **Backups and optional remote access:** back up your installation using [backup instructions](backup-restore.md). After local setup works, install Tailscale and follow [private remote access](remote-access.md). Tailscale is optional for local operation; a convenience prerequisite check should report it as optional.

No email integration is necessary. There are no send nodes; sending a reviewed draft is a manual action in your email client. Crawl4AI is optional diagnostics and should remain off for first setup.

## 8. Use it after a restart

Sign into this same Windows account. Launch Ollama and Docker Desktop if they did not start automatically, then wait for Docker's engine. In normal PowerShell:

```powershell
Set-Location "$env:USERPROFILE\Projects\sponsor-research"
docker compose up -d
docker compose exec -T worker python scripts/healthcheck.py --inside
```

Open `http://localhost:5678` only after the required services pass. Keep the computer awake during work; the display may turn off and the screen may be locked. Docker restart policies do not start the Windows applications before sign-in. Background operation before any user signs in is not configured by this guide.

To pause the project, wait for the current run to finish, then run `docker compose stop`. This keeps the data. Do not delete Docker volumes or use `docker compose down -v` as a troubleshooting shortcut.

Record the Windows version, RAM, GPU VRAM, model timings, integration results, and first production-like review in your operational notes. A fast tiny-model probe is not proof that a full company research run will be fast or accurate.

# Windows 11 performance and measurement guide

Use this guide on the Windows deployment desktop after the basic installation, native inference, and Docker-to-Ollama checks in [Windows setup](windows-setup.md) succeed. The target is **16 GB system RAM, a GeForce RTX 3050, Docker Desktop with WSL2/Linux containers, and Ollama installed directly on Windows**. No Windows performance setting has been tested from this Mac development workspace.

The aim is a responsive host and reliable sequential research. The settings below are starting experiments, not measured ideal values. Make one change at a time, compare the same workload, and retain a change only if speed, stability, and output quality improve. Record results in your operational notes.

## 1. Understand which program uses which memory

| Part | Where it runs | What to observe |
|---|---|---|
| PostgreSQL, n8n, SearXNG, Python worker | Docker's WSL2 environment | Docker container memory/CPU and Windows `VmmemWSL` |
| Qwen3.5 through Ollama | Native Windows application | Ollama's CPU/GPU allocation, Windows RAM, NVIDIA VRAM |
| Windows and your other applications | Windows | Available RAM, CPU load, disk activity, responsiveness |

An RTX 3050 name alone does not establish its VRAM capacity; inspect the actual card. System RAM and dedicated VRAM are different resources. A WSL memory limit does **not** limit native Windows Ollama's RAM or enlarge the GPU's VRAM. Ollama supports native Windows GPU execution. [Ollama Windows documentation](https://docs.ollama.com/windows)

The application currently uses:

| Job | Model | Requested context | Execution |
|---|---|---|---|
| Screen candidates | `qwen3.5:4b` | 8,192 tokens | One model call at a time |
| Research, contact strategy, drafting | `qwen3.5:9b` | 16,384 tokens | One model call at a time |

These values come from [app/services.py](../app/services.py), which also sends `think=false`, a JSON schema, and an output ceiling of 3,000 tokens; temperature is `0.1` for the scout, research, and contact-researcher stages, and `DRAFT_TEMPERATURE` (default `0.3`) for the email-writer stage. A context window is capacity, not a requirement to fill every prompt. The worker lock serializes its own calls; avoid running another Ollama chat application or diagnostic request alongside it.

The 9B model may use both GPU and CPU memory, especially with its 16K context. Expect that to be a possible speed constraint, rather than assuming every model fits entirely on the card. With 16 GB RAM, Windows, containers, and CPU-offloaded model work share a tighter budget. Increasing WSL memory will not solve native Ollama's VRAM shortage. Keep the project's two specified models for this deployment; a 30B coder model is not a performance upgrade for this RTX 3050 workflow.

## 2. Record a baseline before changing limits

Use normal PowerShell under the same Windows account that installed Ollama. Enter the project directory:

```powershell
Set-Location "$env:USERPROFILE\Projects\sponsor-research"
Get-CimInstance Win32_ComputerSystem | Select-Object NumberOfLogicalProcessors, @{Name='RAM_GB'; Expression={[math]::Round($_.TotalPhysicalMemory / 1GB, 1)}}
wsl --version
wsl --status
wsl --list --verbose
docker version
docker compose version
ollama --version
ollama list
nvidia-smi
```

Record the CPU's logical processor count, RAM, GPU name/VRAM, driver version, Ollama version, and installed model IDs. A downloaded model's size is not its complete inference memory requirement. The official library lists the available Qwen3.5 variants; your installed model and quantization are what matter for a comparison. [Qwen3.5 model library](https://ollama.com/library/qwen3.5)

1. Press **Ctrl + Shift + Esc** to open Task Manager. Select **Performance → CPU** to see logical processors; select **Memory** to see installed and available RAM.
2. In **Performance → GPU**, inspect **Dedicated GPU memory**. The default 3D graph can miss compute activity; use the NVIDIA command in section 6 as well.
3. Select **Processes**, then click the CPU, Memory, or Disk column to find the largest consumers. Observe once while idle, once during a 4B call, and once during a 9B call. Close other heavy applications before the baseline, then keep the same ordinary desktop applications open for each comparison. Record peak host RAM and dedicated VRAM during 9B inference; fitting within a timeout is not enough if Windows becomes unresponsive.
4. With Docker running, inspect its containers:

```powershell
docker compose ps
docker stats --no-stream
```

Docker statistics describe containers. They do not include all WSL VM overhead or native Windows Ollama. Task Manager helps identify competing host processes. [Microsoft performance troubleshooting](https://support.microsoft.com/en-us/windows/experience/performance-optimization/tips-to-improve-pc-performance-in-windows)

Do one successful real company run before tuning. Observe research evidence, structured output, contacts, scores, and the pending-review draft. Keep a note of the company and number of pages/results. Later live research can fetch changed pages, so it is less controlled than repeating a saved diagnostic request.

## 3. Keep Windows available without adding unnecessary load

### Power and sleep

1. Open **Start → Settings → System → Power & battery**. A desktop may label this page **Power**.
2. Open **Screen, sleep & hibernate timeouts**; older builds may show **Screen and sleep**. Set the **plugged-in device sleep** timeout to **Never** while running long jobs or providing remote access. If a plugged-in hibernate timeout is offered, prevent hibernation during those jobs too. The screen can still turn off, and you can lock Windows.
3. Begin with the current **Balanced** power mode. For a later comparison, select **Power mode → Plugged in → Best performance**, or the equivalent single Power mode dropdown. Compare the same warm 9B request. Watch temperature, fan noise, and responsiveness; keep Balanced if the faster mode does not provide a useful benefit. If this control is unavailable because of a custom plan, **Control Panel → System and Security → Power Options → Balanced** restores the standard plan choice. [Microsoft power mode instructions](https://support.microsoft.com/en-us/windows/change-the-power-mode-for-your-windows-pc-c2aff038-22c9-f46d-5ca0-78696fdf2de8), [Windows 11 power settings](https://support.microsoft.com/en-us/windows/experience/power-battery/power-settings-in-windows-11)

### Startup and maintenance

1. Open **Start → Settings → Apps → Startup**, or **Task Manager → Startup apps**. Turn off automatic startup only for applications you recognize and do not need during research, such as an unused game launcher. Leave required project and remote-access applications available. Do not disable unfamiliar driver or security entries. Startup settings apply when you sign in. [Microsoft startup application instructions](https://support.microsoft.com/en-gb/windows/experience/startup-boot/configure-startup-applications-in-windows)
2. In **Docker Desktop → Settings → General**, enable **Start Docker Desktop when you sign in** if you want the stack available after login. Start Ollama after signing in and verify its tray icon/API; check its entry in Startup apps if present. Do not add a second `ollama serve` process alongside the tray app. A container restart policy cannot launch either Windows application. [Docker Desktop settings](https://docs.docker.com/desktop/settings-and-maintenance/settings/)
3. Before recording timings, let pending updates, model downloads, and large file copies finish. Use **Settings → Windows Update → Check for updates** and restart when required, then reopen Docker and Ollama. Keep Windows Update, Defender, the firewall, and the system-managed Windows pagefile enabled. Do not apply registry debloat scripts or blanket service-disabling recipes.
4. Open **Settings → System → Storage** if the drive is nearly full. Review any cleanup selection before deleting it. Keep model files, Docker storage, PostgreSQL/n8n volumes, and backups. Do not use `docker system prune --volumes` as a speed tweak. Low disk space and competing processes are worth addressing before changing model settings. [Microsoft performance guidance](https://support.microsoft.com/en-us/windows/experience/performance-optimization/tips-to-improve-pc-performance-in-windows)

## 4. Try a conservative WSL2 container limit

Do this only after the unchanged stack passes its basic integration checks. For this **16 GB host**, a proposed first experiment is **4 GB WSL memory and 2 GB WSL swap**. If the host has **at least four logical processors**, try **two WSL processors**. If it has fewer than four, omit the `processors` line initially and observe the default before imposing a cap. This proposal leaves room for native Ollama and Windows, including CPU-offloaded inference; it is not a measured minimum, performance promise, or guarantee that the containers need exactly 4 GB. On a host with at least eight logical processors, four WSL processors can be a later controlled experiment if container CPU work is the observed bottleneck.

Docker's WSL2 backend uses the WSL utility VM's memory, CPU, and swap configuration. Do not look for the Hyper-V/macOS CPU and RAM sliders or switch away from WSL2 to obtain them. **Docker Desktop → Settings → General → Use the WSL 2 based engine** should remain enabled. **Settings → Resources → WSL Integration** selects distribution integration; it does not allocate native Ollama resources. [Docker Desktop resource settings](https://docs.docker.com/desktop/settings-and-maintenance/settings/)

Microsoft now recommends the **WSL Settings** application from Start for WSL configuration. The following explicit file method makes the experiment and rollback easy to inspect. `.wslconfig` belongs in your **Windows user profile**, applies to all WSL2 distributions for that account, and is read when WSL starts. Memory is a VM limit, not a dedicated 4 GB reservation; swap is disk-backed overflow, not GPU memory. [Microsoft WSL configuration reference](https://learn.microsoft.com/en-us/windows/wsl/wsl-config)

### Save the current configuration

1. Finish or stop n8n jobs first. Do not interrupt database writes or inference. Save work in any other WSL distributions.
2. In normal PowerShell, run:

```powershell
if (Test-Path "$env:USERPROFILE\.wslconfig") {
    if (Test-Path "$env:USERPROFILE\.wslconfig.frc-before-performance") {
        throw 'The backup already exists. Preserve it and choose a new backup filename before copying.'
    }
    Copy-Item "$env:USERPROFILE\.wslconfig" "$env:USERPROFILE\.wslconfig.frc-before-performance" -ErrorAction Stop
    Get-Content "$env:USERPROFILE\.wslconfig"
}
notepad "$env:USERPROFILE\.wslconfig"
```

If the backup already exists from an earlier experiment, preserve it or choose a new backup filename before copying again. Keep the backup outside the repository.

3. In Notepad, preserve existing unrelated settings. Add or edit these entries under the existing `[wsl2]` section; create that section if missing. Do not create duplicate entries or sections:

```ini
[wsl2]
memory=4GB
processors=2
swap=2GB
```

Omit `processors=2` when your earlier inventory showed fewer than four logical processors. Use **File → Save**. For a new file, **Save as → Save as type: All files**, filename `.wslconfig`, in your user-profile folder. It must not become `.wslconfig.txt`.

4. Confirm the saved name and contents:

```powershell
Get-Item "$env:USERPROFILE\.wslconfig"
Get-Content "$env:USERPROFILE\.wslconfig"
```

### Apply the limit while the system is idle

1. From the project folder, stop the project containers cleanly:

```powershell
docker compose stop
```

2. Right-click the Docker whale in the Windows system tray (expand the up-arrow near the clock if needed) and choose **Quit Docker Desktop**.
3. In PowerShell run:

```powershell
wsl --shutdown
```

This stops **all** running WSL distributions, not just this project's containers. WSL must stop and restart for the configuration to apply. [Microsoft WSL restart instructions](https://learn.microsoft.com/en-us/windows/wsl/wsl-config)

4. Launch Docker Desktop from Start. Wait until its engine is running, then run:

```powershell
docker info --format '{{.OSType}}'
docker compose up -d --wait --wait-timeout 180
docker compose ps
docker compose exec -T worker python scripts/healthcheck.py --inside
docker info --format 'CPUs={{.NCPU}} MemoryBytes={{.MemTotal}}'
```

Expect `linux`, healthy required containers, and passing required health checks. Docker's reported capacity should broadly reflect the new WSL limits; usable bytes can differ from the literal limit because of VM overhead. If the change appears ignored, recheck the filename/section, fully quit Docker, and repeat the idle shutdown/restart.

Do not turn on the optional Crawl4AI profile for these measurements. Its diagnostic browser workload adds a different resource demand; the normal extraction path is bounded HTTP. Leave any existing WSL memory-reclaim defaults alone during the first comparison. Docker documents that Resource Saver on WSL reduces idle CPU use without shutting down the shared WSL VM or reclaiming its memory; it is not an active-inference accelerator. Keep its current setting while testing the cap. [Docker WSL backend](https://docs.docker.com/desktop/features/wsl/), [Resource Saver on Windows](https://docs.docker.com/desktop/use-desktop/resource-saver/)

## 5. Keep native Ollama concurrency bounded

Use **Windows user environment variables**, not this project's `.env`. Project `.env` settings configure the worker/containers; native Ollama does not read that file. Keep `.env`'s `OLLAMA_URL=http://host.docker.internal:11434`; direct Windows probes use `http://localhost:11434`.

1. Wait until all model work has finished. Right-click Ollama's tray icon and choose **Quit**.
2. Open Start, type **Edit environment variables for your account**, and open that result.
3. In **User variables**, choose **New** for a missing variable, or select it and choose **Edit**. Set:

| Variable | Value | Reason for this experiment |
|---|---|---|
| `OLLAMA_NUM_PARALLEL` | `1` | One request per model |
| `OLLAMA_MAX_LOADED_MODELS` | `1` | One resident model at a time |

4. Click **OK** to save each variable and close the dialogs. Launch Ollama from Start, then open a new PowerShell window. An already running tray process does not pick up a later variable assignment. This follows Ollama's documented Windows restart procedure. Parallel requests also increase context-memory demand. [Ollama Windows configuration](https://docs.ollama.com/windows), [Ollama concurrency settings](https://github.com/ollama/ollama/blob/main/envconfig/config.go)

These limits complement the worker's lock and discourage accidental competing model loads. Switching between 4B and 9B can require a reload, so compare warm and cold calls separately. Do not set a global large context window: this application already requests the appropriate context per call.

## 6. Measure actual native API calls

Keep workflows idle for these diagnostics. A **model-cold** request starts after the model has been unloaded from Ollama. Windows may still cache files in RAM, so this is not a controlled cold-disk benchmark. A **warm** request follows immediately with the same model still loaded. Repeated prompts can also benefit from prompt caching; record the cached-token count where available. Compare cold with cold and warm with warm.

### Watch allocation while inference is running

Open a second normal PowerShell window. After a timing call below starts, run:

```powershell
ollama ps
nvidia-smi --query-gpu=timestamp,name,memory.total,memory.used,utilization.gpu,temperature.gpu --format=csv -l 2
```

Record `ollama ps`'s **PROCESSOR** field: GPU, CPU, or a split. Press **Ctrl + C** to end the NVIDIA monitor when finished; this ends the monitor, not the inference. Run `ollama ps` again if needed. GPU allocation and GPU utilization are different observations. A partial CPU/GPU allocation is a possible explanation for slow 9B inference, not proof of a broken driver. [Ollama allocation check](https://docs.ollama.com/faq), [NVIDIA SMI reference](https://docs.nvidia.com/deploy/nvidia-smi/)

If Ollama unexpectedly reports CPU only, verify the installed NVIDIA driver against the current Windows requirements, quit/restart Ollama while idle, and retest. Inspect **File Explorer → address bar → `%LOCALAPPDATA%\Ollama` → `server.log`** for backend or allocation errors. A successful `nvidia-smi` table alone does not establish GPU inference. [Ollama Windows requirements and logs](https://docs.ollama.com/windows), [Ollama hardware support](https://docs.ollama.com/gpu)

### Run a repeatable structured-output timing probe

Copy this whole function into the first PowerShell window. It calls the real native API, parses its response, and reports wall time plus Ollama's timing metrics. The contexts, thinking setting, temperature, and output ceiling match the worker; the prompt/schema are intentionally much smaller. The API supports structured formatting and non-streaming responses. [Ollama chat API](https://docs.ollama.com/api/chat)

```powershell
function Test-FrcOllamaTiming {
    param(
        [Parameter(Mandatory=$true)][string]$Model,
        [Parameter(Mandatory=$true)][int]$Context,
        [Parameter(Mandatory=$true)][string]$Label
    )
    $probe = @{
        model = $Model
        stream = $false
        think = $false
        keep_alive = '5m'
        format = @{
            type = 'object'
            properties = @{
                ok = @{ type = 'boolean' }
                summary = @{ type = 'string' }
            }
            required = @('ok', 'summary')
            additionalProperties = $false
        }
        options = @{ temperature = 0.1; num_ctx = $Context; num_predict = 3000 }
        messages = @(@{
            role = 'user'
            content = 'Set ok to true. In one short sentence, explain why running one local model request at a time can reduce competing memory demand.'
        })
    }
    $clock = [System.Diagnostics.Stopwatch]::StartNew()
    try {
        $reply = Invoke-RestMethod -Method Post -Uri 'http://localhost:11434/api/chat' -ContentType 'application/json' -Body ($probe | ConvertTo-Json -Depth 10) -TimeoutSec 1200 -ErrorAction Stop
    } finally {
        $clock.Stop()
    }
    $content = $reply.message.content | ConvertFrom-Json -ErrorAction Stop
    if ($content.ok -ne $true -or [string]::IsNullOrWhiteSpace($content.summary)) {
        throw 'The diagnostic JSON did not contain ok=true and a summary. Record the failure.'
    }
    $generationRate = $null
    if ($reply.eval_duration -gt 0) {
        $generationRate = [math]::Round($reply.eval_count / ($reply.eval_duration / 1e9), 2)
    }
    [PSCustomObject]@{
        Label = $Label
        Model = $Model
        Context = $Context
        WallSeconds = [math]::Round($clock.Elapsed.TotalSeconds, 3)
        OllamaTotalSeconds = [math]::Round($reply.total_duration / 1e9, 3)
        LoadSeconds = [math]::Round($reply.load_duration / 1e9, 3)
        PromptTokens = $reply.prompt_eval_count
        CachedPromptTokens = $reply.prompt_eval_cached_count
        PromptSeconds = [math]::Round($reply.prompt_eval_duration / 1e9, 3)
        OutputTokens = $reply.eval_count
        GenerationTokensPerSecond = $generationRate
        DoneReason = $reply.done_reason
        ResponseJSON = $reply.message.content
    }
}
```

Run each call to completion. The `ollama stop` commands below are **idle-only unload helpers**: never use them to tune memory during a running worker/API call. No separate stop-model script is supplied.

```powershell
ollama stop qwen3.5:4b
ollama stop qwen3.5:9b
$cold4 = Test-FrcOllamaTiming -Model 'qwen3.5:4b' -Context 8192 -Label '4B model-cold'
$warm4 = Test-FrcOllamaTiming -Model 'qwen3.5:4b' -Context 8192 -Label '4B warm'
@($cold4, $warm4) | Format-List
```

Then, only after both 4B calls finish:

```powershell
ollama stop qwen3.5:4b
ollama stop qwen3.5:9b
$cold9 = Test-FrcOllamaTiming -Model 'qwen3.5:9b' -Context 16384 -Label '9B model-cold'
$warm9 = Test-FrcOllamaTiming -Model 'qwen3.5:9b' -Context 16384 -Label '9B warm'
@($cold9, $warm9) | Format-List
```

Do not start the next call if one errors or times out. Confirm the previous inference has ended before unloading a model or trying again. Ollama exposes model unloading and keep-alive controls. [Ollama CLI model unloading](https://docs.ollama.com/cli), [Chat API keep-alive setting](https://docs.ollama.com/api/chat)

All API durations are in nanoseconds, hence division by `1e9`. `LoadSeconds` separates model loading from evaluation; generation throughput is output tokens divided by output evaluation seconds. Wall time includes the client request/response path. A blank cached-token field can mean the installed version did not return it. Record errors and `DoneReason`, including output truncation, alongside successes. [Ollama usage metrics](https://docs.ollama.com/api/usage)

**This short probe is an integration and allocation check, not a real research benchmark.** It does not fill 8K/16K context, exercise the application's long source text, or prove evidence/contact quality. Do not extrapolate real-company latency from its few output tokens. After any retained change, time one real sequential research/draft run in n8n and inspect the persisted result. The worker's default scout timeout is 120 seconds; research defaults to 900 seconds per model call, with a configurable cap of 1,200 seconds. A direct probe's 1,200-second ceiling does not change those application limits.

## 7. Optional cache experiment after the baseline works

Downloaded **model-weight quantization** changes the stored weights. **K/V cache quantization** changes inference context-cache precision. They are separate settings; `OLLAMA_KV_CACHE_TYPE=q8_0` does not turn downloaded model weights into an 8-bit model or guarantee that 9B fits fully in VRAM.

Ollama documents `q8_0` as an optional lower-memory cache type used with Flash Attention, and states that precision effects depend on the model/task. Flash Attention support depends on the selected backend/device. [Ollama cache and Flash Attention guidance](https://docs.ollama.com/faq)

Qwen3.5 uses a hybrid of linear and full attention. Generic Qwen3 or ordinary-transformer context-memory arithmetic is not a verified memory estimate for this architecture and installed Ollama backend. Measure the actual allocation rather than promising a fixed VRAM saving. [Official Qwen3.5-9B model card](https://huggingface.co/Qwen/Qwen3.5-9B)

If the default setup is stable and memory pressure remains a problem:

1. Record whether `OLLAMA_KV_CACHE_TYPE` and `OLLAMA_FLASH_ATTENTION` already exist and their original values. Keep the one-request/one-model limits.
2. Finish all jobs, quit the Ollama tray application, and use the Windows **User variables** dialog from section 5. Set `OLLAMA_KV_CACHE_TYPE` to `q8_0`. Relaunch Ollama.
3. Verify in `%LOCALAPPDATA%\Ollama\server.log` whether the selected backend actually enables supported Flash Attention and applies the requested cache type. If the log cannot establish this, treat support as **unverified**; an environment variable alone is not proof. Do not report success from a smaller Task Manager number alone.
4. If Flash Attention was disabled explicitly, an optional separate experiment is to set `OLLAMA_FLASH_ATTENTION=1`, quit/restart, and inspect the logs again. Do not force an unsupported backend. Revert on errors or unsupported operation.
5. Repeat the same warm/cold timing probes, then the same representative saved prompt/schema or real-company quality review. Check JSON validity, supported excerpts/URLs, contacts, and drafting accuracy. Keep `q8_0` only if the backend supports it and speed/memory improve without unacceptable quality loss.
6. To roll back, finish jobs, quit Ollama, restore original values (or delete only variables you added), and relaunch. Avoid `q4_0` as a beginner baseline; it adds another precision tradeoff before this project's quality has been established.

This optional experiment changes native Ollama's global cache behavior. It does not change the project's model selection, context settings, prompts, or API integration.

## 8. Tune from observations and keep a record

| Observation | Next controlled experiment |
|---|---|
| Image building reports memory exhaustion with the 4 GB WSL cap | While idle, temporarily raise WSL memory by 1–2 GB, restart WSL/Docker, and retry the build; after building, return to 4 GB through another idle restart and recheck services and host headroom |
| Required containers remain unhealthy or report memory exhaustion at runtime with the 4 GB cap | Inspect the failing container's logs/statistics; compare a small WSL memory increase only if Windows/native Ollama have headroom, then repeat health and 9B peak RAM/VRAM checks |
| Windows has little available RAM or stalls during native 9B inference | Identify other memory consumers; keep inference sequential and only one model resident; do not blindly raise WSL's cap |
| `VmmemWSL` CPU is busy and containers are the measured bottleneck while Windows has headroom | On a host with at least eight logical CPUs, compare an increase from two to four WSL processors; native Ollama is outside that CPU cap |
| CPU/GPU split appears in `ollama ps` and 9B generation is slow | Record the split, VRAM and timings; test the optional supported cache change, or accept the measured sequential latency |
| GPU utilization is low only between calls or during page fetching | Time the full stage and identify search/fetch/load time before assuming GPU generation is the bottleneck |
| Timing improves only after the first request | Record model load and prompt-cache effects; use separate cold/warm columns |

If WSL needs sustained swap to keep the containers alive, investigate memory demand. More disk-backed swap is not a substitute for RAM and is not a speed upgrade. Avoid lowering the application's 8K/16K contexts as an undocumented machine tweak; changing them requires separate prompt-budget and quality validation.

Keep the Windows pagefile automatically managed. If sustained host memory pressure remains after reducing competing applications, an optional upgrade to 32 GB system RAM could add headroom, but it does not add dedicated VRAM or guarantee faster 9B generation. Verify this desktop's supported memory configuration before considering a purchase; an upgrade is not required to follow this guide. The actual GPU memory capacity and model offload remain central to inference speed.

To restore WSL's prior configuration, finish jobs, stop project containers, quit Docker, restore the backed-up `.wslconfig` (or remove only the entries you added if there was no prior file), then perform the section 4 shutdown/restart. Repeat health checks. Preserve unrelated settings.

Copy observations into the checklist's record, without secrets or invented measurements:

| Date / version | Configuration changed | Workload / cold or warm | Wall / load / generation rate | CPU/GPU split and peak RAM/VRAM | Quality / errors | Keep or revert |
|---|---|---|---|---|---|---|
| | | | | | | |

A reliable outcome is passing required service checks, a responsive Windows desktop, verified native inference allocation, and a reviewed real-company result within the configured time budget. All GPU, timing, Windows restart, and quality observations remain Windows-only acceptance work until you record them on the actual desktop.

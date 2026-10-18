# OSINT Digest

Collect cybersecurity articles from RSS/Atom feeds, filter them by topic, and publish summaries to Discord or the Windows app. AI is optional: start with publisher excerpts, or connect Google Gemini, OpenAI, Anthropic Claude, or a local Ollama model.

The desktop and server editions check every enabled source, select articles published within the last **48 hours**, and skip previously delivered articles. Set an **articles-per-source limit** and choose from seven independent keyword scopes. Explicit test modes allow repeats and older articles.

## Choose your installation

| Method | Best for | Requirements | Start here |
|---|---|---|---|
| Windows installer | A desktop app with Start menu shortcuts | Windows 10/11 x64; Python included | [Install on Windows](#windows-installer) |
| Windows portable ZIP | Running without an installer | Windows 10/11 x64; Python included | [Use the portable app](#windows-portable-app) |
| Linux container | An always-on server, managed over SSH | Docker Engine and Docker Compose | [Install the server](#linux-server-with-docker) |
| Python source | Command-line use or development | Python 3.11+; extra dependencies for the GUI | [Run from source](#run-from-source) |
| GitHub Actions | Scheduled collection hosted by GitHub | Your own repository and Actions configuration | [Set up Actions](docs/CLI.md#github-actions) |

## Downloads

| Package | Current release | Download |
|---|---|---|
| Windows installer | **1.8.1** | [OSINTDigest-Setup-1.8.1-x64.exe](https://github.com/nullglobdev/osint-digest/releases/download/v1.8.1/OSINTDigest-Setup-1.8.1-x64.exe) |
| Windows portable app | **1.8.1** | [OSINTDigest-Portable-1.8.1-x64.zip](https://github.com/nullglobdev/osint-digest/releases/download/v1.8.1/OSINTDigest-Portable-1.8.1-x64.zip) |
| Linux server bundle | **1.6.0** | [OSINTDigest-Server-1.6.0.tar.gz](https://github.com/nullglobdev/osint-digest/releases/download/server-v1.6.0/OSINTDigest-Server-1.6.0.tar.gz) |

[All releases and checksums](https://github.com/nullglobdev/osint-digest/releases) · [Windows guide](docs/DESKTOP.md) · [Server guide](docs/CONTAINER.md)

Use the named download assets above for installation. GitHub's automatically generated **Source code** archives do not contain a ready-to-run Windows app. The Windows installer is currently unsigned.

## Adjust an installed Docker server

SSH to your Docker host and enter the existing checkout. On Ryan's current Docker VM:

```sh
ssh ry@192.168.6.238
cd /home/ry/osint-digest
sh scripts/server.sh settings
```

Use the interactive menu to change the schedule, articles per source, AI provider/model, sources, filters, or Discord destinations, and save the change. For a focused menu:

```sh
sh scripts/server.sh sources
sh scripts/server.sh models
sh scripts/server.sh webhooks
sh scripts/server.sh filters
```

`scope` remains an alias for `filters`. Enter webhook URLs and API keys only in the hidden-input prompts; do not paste them into shell commands, screenshots, Git, or issue reports. The server does not use the standalone CLI's repository `.env` file. Do not rerun `setup` to make routine adjustments.

**Saved settings reload automatically; no restart or image rebuild is required.** While idle, changes are noticed within a few seconds. A collection already in progress keeps its original settings until it finishes. Pause automatic checks in Settings before making a series of changes if you do not want another collection to start meanwhile; enable them again when ready.

```sh
sh scripts/server.sh status
sh scripts/server.sh logs
```

Status hides saved credentials. Ctrl+C exits log viewing without stopping the service. Review logs locally and redact sensitive details before sharing. Closing SSH leaves the background container running.

Settings, credentials and delivery history persist in the named Docker volume `osint-digest_digest-data`, mounted at `/data`; keep the Compose project name unchanged. Rebuilding the application does not replace this volume. Never use `docker compose down -v` when preserving your configuration or history.

Before a software upgrade, pause automatic checks and wait for any active collection to finish, then create a consistent backup:

```sh
sh scripts/server.sh backup
```

The command prints the archive path under `/data/backups/`. Copy that specific archive to a private backup location outside the repository (replace the filename and destination):

```sh
docker compose cp digest:/data/backups/ARCHIVE-NAME.tar.gz /private/backup/ARCHIVE-NAME.tar.gz
```

Backups contain credentials, history and previews. Restrict access and do not commit them. A backup left in the same Docker volume does not protect against losing that volume.

Only when you intend to upgrade the running application, review the intended revision and release notes, check `git status --short`, preserve any local edits, and then use:

```sh
sh scripts/server.sh stop
git pull --ff-only
sh scripts/server.sh update
sh scripts/server.sh status
```

If the checkout is dirty or `git pull --ff-only` fails, stop and reconcile the source without resetting local work. `update` rebuilds from the checked-out source, refreshes the base image, and recreates the service; it is not needed for settings changes. Re-enable automatic checks in Settings if you paused them for maintenance. For a server installed from a release archive, use the reviewed replacement server bundle instead of `git pull`. See the [server guide](docs/CONTAINER.md#data-logs-and-backups) for backup and restore details.

## Windows installer

1. Download the `.exe` installer above.
2. Close any older running copy of OSINT Digest, including its tray icon.
3. Run the installer. It installs for your Windows account without requiring administrator rights.
4. Open **OSINT Digest** from the Start menu, then follow [First launch](#first-launch-on-windows).

You do not need to install Python, Git, or Docker.

## Windows portable app

1. Download the portable `.zip` above.
2. Extract the **entire ZIP** into a folder such as `C:\Tools\OSINTDigest`.
3. Open the extracted `OSINTDigest` folder and run `OSINTDigest.exe`. Keep its `_internal` folder beside it.
4. Follow [First launch](#first-launch-on-windows).

The portable app uses the same Windows app-data location as the installed app; its settings are not stored beside the executable.

### First launch on Windows

1. Open **Connection**. Choose **Publisher excerpts** to start without AI, or select a provider, enter its **AI API key**, and choose a model.
2. Leave **Discord webhook URL** blank to publish in the app's **Results** tab. To send to Discord, create a channel webhook under **Channel Settings → Integrations → Webhooks** and enter its URL. Click **Save connection**.
3. Open **Sources**, enable the feeds you want, and click **Save sources**. Use **Add source** for a custom RSS/Atom feed.
4. On **Dashboard**, set **Articles per source** (1–100, default 5). Choose any article filters; **All** leaves a scope unrestricted.
5. Click **Collect new**. Read progress in **Activity**, then open **Results** or your Discord channel.

For recurring checks, set **Check every** to 15–360 minutes and click **Start automatic checks**. **Run in background** hides the window in the system tray while checks continue. The PC must remain awake and online.

Themes, text size, accessibility controls, and Dev mode are in **Preferences**. Dev mode reveals previews, AI tests, and a 1–365 day test timeframe. See the [desktop guide](docs/DESKTOP.md) for details.

## Linux server with Docker

The server runs without a GUI and supports **multiple Discord webhooks**. Configuration uses interactive terminal menus. No Python installation or inbound application ports are required on the host.

Install [Docker Engine](https://docs.docker.com/engine/install/) and the [Docker Compose plugin](https://docs.docker.com/compose/install/linux/) for your Linux distribution. Your account must be able to run Docker commands. Check them before continuing:

```bash
docker version
docker compose version
```

### Option A: clone from GitHub

Install [Git](https://git-scm.com/downloads) if needed, then run:

```bash
git clone https://github.com/nullglobdev/osint-digest.git
cd osint-digest
```

This follows the current source on `main` and supports updates with `git pull`.

### Option B: download a server release

With `curl` and `tar` installed, run:

```bash
curl -fLO https://github.com/nullglobdev/osint-digest/releases/download/server-v1.6.0/OSINTDigest-Server-1.6.0.tar.gz
curl -fLO https://github.com/nullglobdev/osint-digest/releases/download/server-v1.6.0/SERVER-SHA256SUMS.txt
sha256sum -c SERVER-SHA256SUMS.txt && \
tar -xzf OSINTDigest-Server-1.6.0.tar.gz && \
cd OSINTDigest-Server-1.6.0
```

Continue only if checksum verification reports `OK`. The bundle includes the Docker build files and administration scripts; Git is not required.

### Configure and start

From the folder created by either option:

```bash
sh scripts/server.sh setup
sh scripts/server.sh start
sh scripts/server.sh status
```

Setup builds the image and prompts for Discord webhooks, an optional AI provider, the article limit, interval, sources, and filters. Enable automatic checks in setup if you want scheduled collection; a fresh configuration starts paused. Closing your SSH session leaves the container running.

Use these commands from the same folder to manage it:

| Task | Command |
|---|---|
| Change settings or enable the schedule | `sh scripts/server.sh settings` |
| Add or change Discord destinations | `sh scripts/server.sh webhooks` |
| Add or edit sources | `sh scripts/server.sh sources` |
| Change article filters | `sh scripts/server.sh filters` |
| Check feed access | `sh scripts/server.sh check-feeds` |
| Follow logs; Ctrl+C stops viewing them | `sh scripts/server.sh logs` |
| Stop the service | `sh scripts/server.sh stop` |

The [server guide](docs/CONTAINER.md) covers testing, backups, Ollama networking, multiple webhooks, and troubleshooting. Images are built locally; no prebuilt container registry image is published.

## Run from source

### Python command line

Install [Python 3.11 or newer](https://www.python.org/downloads/) and [Git](https://git-scm.com/downloads). On Windows, include the Python launcher (`py`). The command-line collector uses the Python standard library; it needs **no pip packages**.

**Windows PowerShell:**

```powershell
git clone https://github.com/nullglobdev/osint-digest.git
cd osint-digest
Copy-Item .env.example .env
notepad .env
py -3 bot.py --dry-run --per-source-limit 5 --max-age-hours 48
```

**Linux or macOS:**

```bash
git clone https://github.com/nullglobdev/osint-digest.git
cd osint-digest
cp .env.example .env
nano .env
python3 bot.py --dry-run --per-source-limit 5 --max-age-hours 48
```

In `.env`, leave `AI_PROVIDER=none` for publisher excerpts and set `DISCORD_WEBHOOK_URL` for Discord delivery. The preview command writes reports to `preview/` without sending messages. To publish, remove `--dry-run`; add `--local` to save reports in the checkout's `results/` folder instead of Discord. Configured AI can still be called during a preview.

**Keep `--per-source-limit 5 --max-age-hours 48` to match desktop/server defaults.** Bare `bot.py` retains legacy behavior with no article-count cap or publication-age limit. Each CLI command checks once and exits. See the [CLI guide](docs/CLI.md) for AI configuration, tests, filters, and scheduling.

### Windows GUI from source

In a repository checkout, use **Python 3.12** and install the desktop dependencies in a virtual environment:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements/desktop.txt
.\.venv\Scripts\python.exe desktop.py
```

Configure the app through its **Connection** tab. The GUI uses its own saved settings; it does not automatically read the checkout's `.env`.

## Update an existing installation

**Windows:** close the running app, including the tray process, and run the new installer. For a portable copy, extract the new ZIP into a new folder and run its executable. Both use the existing Windows profile.

**Server installed with Git:** back up using the [server guide](docs/CONTAINER.md#data-logs-and-backups), then run from the existing checkout:

```bash
sh scripts/server.sh stop && \
git pull --ff-only origin main && \
sh scripts/server.sh update
sh scripts/server.sh status
```

**Server installed from a bundle:** download and extract the newer server bundle, stop the existing service, and run `sh scripts/server.sh update` from the new bundle folder. Keep the Compose project name `osint-digest` and its data volume. Do not use `docker compose down -v`; it deletes saved settings and history.

**Python source:** run `git pull --ff-only origin main` from your checkout. For the GUI, also rerun the desktop dependency installation command above. Keep your existing `.env` and data folders.

## Sources, filters, and results

Included sources cover Microsoft, Google/Mandiant, Proofpoint, Huntress, SOCRadar, Cisco Talos, Palo Alto Unit 42, ESET, SentinelLabs, and Securelist. CISA is included but disabled by default. Use **Check feeds** from your deployment to verify access. The default catalog is [config/sources.json](config/sources.json); desktop and server installations manage their own saved source lists.

Seven scopes are available: **Sector**, **Threat actor**, **Social engineering**, **Access & exploitation**, **Malware & impact**, **Other styles**, and **Education combinations**. Every selected scope must match; all scopes default to **All**. Filtering happens before AI analysis and publishing. See the [filter catalog](docs/SCOPES.md).

Reports include the publisher, original article link, publication time, a summary or excerpt, referenced CVEs and ATT&CK IDs, and extracted IOC candidates. Discord posts have no JSON/CSV attachments; IOC previews use spoiler text. The desktop reader opens article, CVE, and ATT&CK links in your browser. IOC matches and AI summaries require review against the source; they are not confirmed detections.

## Where settings and history are stored

| Installation | Location |
|---|---|
| Windows installer, portable app, or GUI from source | `%LOCALAPPDATA%\OSINTDigest`; credentials use Windows account encryption |
| Docker server | Named volume `osint-digest_digest-data`, mounted at `/data` |
| Python CLI | Private `.env`, `state/`, `results/`, and `preview/` inside the checkout |
| GitHub Actions | Repository secrets for credentials; delivery state committed to that repository |

Release downloads contain no configured API keys or webhooks. `.env` and local runtime data are excluded from Git. Each deployment keeps its own delivery history; running separate deployments against the same channel can produce duplicate posts.

## Documentation and development

- [Desktop guide](docs/DESKTOP.md): providers, models, tray behavior, accessibility, and Windows package builds.
- [Server guide](docs/CONTAINER.md): setup, operation, backups, test mode, and multiple webhooks.
- [CLI guide](docs/CLI.md): environment settings, commands, GitHub Actions, Task Scheduler, and cron.
- [Filter catalog](docs/SCOPES.md): all scopes, keywords, and CLI flags.
- [Accessibility](docs/ACCESSIBILITY.md): supported controls and remaining conformance checks.
- [Validation record](docs/VALIDATION.md): completed checks and known limits.

Application code lives in `osint_digest/`, defaults in `config/`, tests in `tests/`, and build/management tools in `scripts/` and `packaging/`. The root `bot.py`, `desktop.py`, and `server.py` files are launchers.

Run offline tests with `python -m unittest -v` from the repository root. GUI tests require the desktop dependencies and run on Windows. Build instructions are in the desktop and server guides.

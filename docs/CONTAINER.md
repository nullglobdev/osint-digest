# OSINT Digest on a server

The container edition runs the same collector as the Windows desktop app, with terminal menus instead of a GUI. It can run continuously on a Linux server with Docker Engine and the Docker Compose plugin. It needs outbound internet access to selected publishers, Discord, and your AI provider. It exposes no ports and includes no graphical dependencies. The Windows desktop app remains available separately.

## First-time setup

Clone this repository for the current source, or download a published server bundle from [GitHub Releases](https://github.com/nullglobdev/osint-digest/releases). The bundle builder produces `OSINTDigest-Server-1.1.0.tar.gz` for this source version.

```sh
git clone https://github.com/nullglobdev/osint-digest.git
cd osint-digest
sh scripts/server.sh setup
```

For the downloaded bundle, extract it with `tar -xzf OSINTDigest-Server-1.1.0.tar.gz`, enter `OSINTDigest-Server-1.1.0`, and run the same setup command.

The script builds the image and opens the setup wizard. No Python installation is needed on the server. The wizard walks through:

1. Discord webhook, entered with hidden terminal input.
2. Google Gemini, OpenAI, Anthropic Claude, Ollama, or publisher excerpts without AI.
3. The selected provider's API key and model. You can load models from the provider, page through the choices, or enter a model ID. Keys and models are retained separately for each provider. OpenAI/Claude require an explicit usage-billing opt-in.
4. Manual test article limit (1–20) and normal check interval (15–360 minutes).
5. Whether automatic checks should be enabled, and optional source changes.

Start the background service after saving:

```sh
sh scripts/server.sh start
sh scripts/server.sh status
sh scripts/server.sh logs
```

Automatic checks start only if you enabled them in setup. A fresh profile starts paused. Every cycle checks all enabled sources and processes all unsent articles and due retries, without an article-count cap. Successfully delivered URLs are skipped across restarts. Closing your SSH session does not stop the container. Docker must be running and the server must stay awake and online.

The first normal run sends all available unsent feed articles. After an upgrade, older quiet-baseline articles also become eligible if still in a feed, because they were never delivered. Existing successful delivery history is preserved. Use a preview or limited test to review the output first.

You can use the Compose commands directly, including from PowerShell with Docker Desktop in Linux-container mode:

```sh
docker compose build --pull
docker compose run --rm digest setup
docker compose up -d
```

Setup and settings need an interactive terminal; do not add `-T` or pipe secrets into them. Ctrl+C cancels an unfinished edit without saving it. Credentials are not accepted as command-line arguments.

## Change settings or sources

```sh
sh scripts/server.sh settings
sh scripts/server.sh sources
sh scripts/server.sh models
```

The settings menu includes connection/provider configuration, scheduling, source management, model discovery, status, preview/testing, delivery actions, and backup. The Sources menu can add/edit HTTPS RSS/Atom feeds, enable or disable publishers, remove them, and reorder test sampling priority. Include exact allowed hostnames for article links and redirects; the feed hostname is included automatically. Existing publisher names stay fixed so their delivery history remains associated correctly.

Changes save to the data volume and are noticed by the service within a few seconds while idle. An active task keeps its original configuration until it finishes. Pausing automatic checks prevents subsequent runs. Concurrent editing sessions cannot silently overwrite one another. Changes do not require an image rebuild or container restart.

Windows settings use Windows account encryption and are not directly portable to Linux. Configure server credentials using this wizard. The server does not import the repository's `.env` or your desktop profile.

## Run an individual task

| Command | Behavior |
|---|---|
| `sh scripts/server.sh check-feeds` | Check enabled RSS/Atom feeds; no AI or Discord calls |
| `sh scripts/server.sh test-discord` | Verify the webhook using a read-only request; no message |
| `sh scripts/server.sh test-ai` | Summarize one article and save a local preview; no Discord message |
| `sh scripts/server.sh test-ai --source Huntress` | Test AI using a particular configured source |
| `sh scripts/server.sh new` | Check all enabled sources and send all unsent articles and due retries |
| `sh scripts/server.sh preview` | Preview all eligible unsent articles without posting or changing history |
| `sh scripts/server.sh preview --test-mode --count 5` | Check all feeds and preview up to five articles, including repeats |
| `sh scripts/server.sh new --test-mode --count 5` | Check all feeds and send up to five articles, including repeats |
| `sh scripts/server.sh new --test-mode --count 10` | Run a manual test with up to ten articles, including repeats |

AI tests and previews use the configured provider's quota. **Test mode is manual only:** it checks all feeds, samples first entries across publishers before taking second entries, and permits repeats up to the limit. Successful test deliveries update history; failed tests leave normal retries unchanged. Automatic checks always use normal deduplication with no article limit. `--count` and the legacy `batch` command require `--test-mode`. If the service is currently collecting, another task returns “Another operation is using this data folder”; retry after it finishes or pause automatic checks in Settings first. There is one collector at a time per data volume.

Equivalent direct commands are `docker compose run --rm -T digest new` or `docker compose run --rm -T digest preview --test-mode --count 5`. In Settings, choose **Test mode** to select a count and preview or send a single test. The saved test limit defaults to 5; existing `max_posts` settings are retained as test limits only.

## Ollama connectivity

The Ollama server is a separate service; this image does not include models or an Ollama runtime. In the wizard, set a base URL the container can reach:

- On the same Docker network: `http://ollama:11434`, where `ollama` is that service's name. Attach this service to the same network in your Compose override.
- On the Docker host: `http://host.docker.internal:11434`. The supplied Compose file maps that hostname to the host gateway, including on Linux. Ollama must listen on a reachable interface; a Linux loopback-only listener cannot be reached from a bridged container. Restrict access to your intended local clients.
- On another trusted server: its reachable HTTP(S) base URL.

Both model discovery and generation use the configured endpoint. No cloud provider key is sent to Ollama. Inside a container, `127.0.0.1` refers to that container itself.

For the original Python CLI outside Docker, `OLLAMA_BASE_URL` is optional and defaults to `http://127.0.0.1:11434`.

## Data, logs, and backups

Compose creates a named volume, `osint-digest_digest-data`, mounted at `/data`. Keep the Compose project name stable when updating: a different project name creates a separate volume and separate history.

| Path inside the volume | Purpose |
|---|---|
| `server.json` | Provider profiles, webhook, schedule, and sources |
| `state/state.json` | Delivered URLs, pending articles, and retries |
| `preview/` | JSON/CSV previews and AI-test text; these files are not attached to Discord |
| `runtime.json` | Service heartbeat, phase, and next-check time |
| `last-run.json` | Last completed task, exit status, and stop status |
| `backups/` | Backups created through the menu or command |

The container runs as UID/GID 10001, uses a read-only application filesystem, and writes only to its data volume and temporary storage. Configuration files have mode `0600` and data directories `0700` on Linux. Credentials are stored as plaintext in this protected server volume, not encrypted with Windows DPAPI. Server administrators and Docker administrators can access them; use appropriate host/disk encryption and private backups. No credentials are passed through Compose environment variables or baked into the image. The build context uses an explicit public-file allowlist.

Create a consistent backup when no collection task is active:

```sh
sh scripts/server.sh backup
```

Copy the printed archive path to a private backup location; for example:

```sh
docker compose cp digest:/data/backups/ARCHIVE-NAME.tar.gz ./ARCHIVE-NAME.tar.gz
```

The service must exist for `compose cp`. Backups contain credentials, history, and previews; keep them private. Backups are retained until you remove them and are not included in later backup archives. Monitor volume usage, including previews and delivery history.

To restore, stop the service, then restore a trusted archive into this volume using your normal Docker-volume backup tooling. Preserve UID/GID 10001 and restrictive file permissions, and start the service again. Do not restore Windows `settings.json` as `server.json`. `docker compose down` preserves the volume; **`docker compose down -v` deletes the saved configuration and history**.

Logs go to Docker stdout/stderr and rotate at 10 MB with three files. `status` never prints saved webhook/API-key values. Health checks validate the heartbeat and configuration state; they do not guarantee publisher reachability, AI quota, or successful Discord delivery. Check task exit codes and logs for those failures.

## Stop and update

```sh
sh scripts/server.sh stop
git pull --ff-only
sh scripts/server.sh update
```

Stop requests finish the current operation and retain queued work before exiting. Compose gives the process up to five minutes before forcing termination. Delivery remains at least once: a crash or forced stop immediately after Discord accepts a post but before the state write can cause a duplicate on retry. The normal restart policy restarts unexpected exits and resumes the configured schedule when Docker starts; a deliberately stopped container stays stopped until you start it again.

The `update` command rebuilds from the code already in this checkout, refreshes the Python base image, and recreates the service while retaining its volume. Back up first. If you installed from an archive, replace the application files with a newer server bundle instead of using `git pull`, then run `update`. Keep the Compose project name unchanged so it reuses the volume. The container option is distributed as source plus Docker/Compose definitions; no prebuilt registry image is currently published.

Do not run the desktop collector and a separate server collector against the same Discord channel unless you want two independent delivery streams; their history is separate.

## Validation and reference

Run `python -m unittest -v` for unit tests. After building the image, `python scripts/test_container.py` runs isolated, offline container acceptance checks. It creates and removes only uniquely named test containers/volumes. See [VALIDATION.md](VALIDATION.md) for actual test results and platform limits.

Docker references: [Engine installation](https://docs.docker.com/engine/install/), [Compose service settings](https://docs.docker.com/reference/compose-file/services/), and [persistent volumes](https://docs.docker.com/engine/storage/volumes/).

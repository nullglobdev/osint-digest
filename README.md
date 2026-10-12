# OSINT Digest for Discord

Download the Windows installer or portable ZIP from [GitHub Releases](https://github.com/nullglobdev/osint-digest/releases/latest).

**Windows desktop app:** a compact rounded navy workspace with a searchable Results tab; local publishing when the Discord webhook is blank; provider model discovery; editable RSS/Atom sources; and automatic checks every 15–360 minutes with system-tray support. Appearance and accessibility controls are in Preferences. The Dashboard article limit applies per source; normal collection uses only articles published in the last 48 hours and skips prior deliveries. Preview tools and resends require Dev mode, with an adjustable test timeframe of 1-365 days. See [DESKTOP.md](docs/DESKTOP.md) for installation and build instructions and [ACCESSIBILITY.md](docs/ACCESSIBILITY.md) for accessibility features and validation status. The desktop installer bundles Python; the CLI instructions below remain supported.

**Server container:** run continuously without a GUI using Docker Compose, with interactive terminal setup/settings, multiple named Discord webhooks, provider model discovery, custom sources, delivery history and retries for each webhook, and checks every 15–360 minutes. The server uses the same per-source article limit and 48-hour publication window as Windows. No Python installation or exposed ports are needed on the host. See [CONTAINER.md](docs/CONTAINER.md).

**Article filters:** the Windows **Dashboard** and server filter menu offer seven independent scopes: Sector, Threat actor, Social engineering, Access & exploitation, Malware & impact, Other styles, and Education combinations. Each defaults to **All**. Every active scope must match before AI analysis or publishing; aliases within an option are alternatives. See [SCOPES.md](docs/SCOPES.md) for the complete catalog and CLI flags. Windows Results opens article, CVE, and ATT&CK links in your default browser.

| Deployment | Setup and management | Runs while |
|---|---|---|
| Windows desktop | Rounded graphical app and system tray | The app is open and the PC is awake |
| Server container | Interactive terminal scripts over SSH | Docker and the server are running |
| Original Python CLI | `.env`, source file, and your scheduler | Each scheduled command executes |

From a checkout on your Docker server:

```sh
sh scripts/server.sh setup
sh scripts/server.sh start
# Change configuration later:
sh scripts/server.sh settings
```

The shared collector watches publisher RSS/Atom feeds and posts new articles to a Discord channel through a webhook. The original CLI needs Python 3.11+ and **no pip packages**. It does not read Discord messages or support slash commands.

## Project layout

```text
osint_digest/       Application package
  core/             Shared collector, AI providers, and source validation
  desktop/          Windows UI, tray, settings, and worker
  server/           Headless service and interactive administration
config/             Default publisher sources (sources.json)
docs/               Desktop, container, accessibility, and validation guides
  validation/       Saved feed-check evidence
tests/              Offline unit and UI tests
scripts/            Windows build, server management, and container checks
requirements/       Desktop and build dependency lists
packaging/          Server bundle builder and third-party licenses
  windows/          PyInstaller spec, installer, version info, and icon builder
assets/             Application icons and theme artwork
dist/               Generated installers, portable builds, and server bundles
```

The root `bot.py`, `desktop.py`, and `server.py` are small launchers, so existing run commands still work. `Dockerfile` and `compose.yaml` remain at the root for normal Docker commands. CLI credentials stay in your private `.env`; local `state/` and `preview/` remain in place. Desktop profiles and container volumes retain their existing locations. `.work/` holds ignored local validation artifacts, while `.build-venv/`, `.build-tools/`, and `build/` hold local build tooling/output.

Run all tests from the repository root with `python -m unittest discover -s tests -v` (the shorter `python -m unittest -v` also works). Build Windows packages with `scripts/build_windows.ps1`; headless server commands remain in `scripts/server.sh`.

## Choose the cost model

| Mode | AI summaries | Hosting | Cost considerations |
|---|---|---|---|
| `none` (default) | A short publisher excerpt plus deterministic IOC/CVE extraction | Your PC or standard GitHub Actions runner | No AI bill; not a synthesized summary |
| `gemini` | Gemini API | Your PC or GitHub Actions | Eligible free-tier projects/models have quotas. Keep the project on the unpaid tier; a billed project can incur charges. Check current eligibility. |
| `ollama` | Local open-weight model | Your own PC/server | No API fee; needs sufficient RAM/compute and incurs electricity cost. This is not Claude or ChatGPT. |
| `openai` | OpenAI API | Either | Paid by usage unless you independently have eligible credits; explicit opt-in required |
| `anthropic` | Claude API | Either | Paid by usage unless you independently have eligible credits; explicit opt-in required |

There is no dependable promise of permanently free automated Claude/OpenAI API use. Consumer chat access is not a substitute for an API account. This project does not automate consumer chat websites or reuse their session cookies.

Use the desktop for a personal PC or the container for an always-on server. On desktop, start with publisher excerpts and a blank webhook to collect into Results, then configure your AI provider or Discord. The original CLI scheduling options below remain available.

## What each post contains

- Publisher, article title, original link and publication time.
- AI summary, affected systems/sectors, actors/malware, techniques and publisher recommendations when supported by extracted source text.
- Separate linked CVE and ATT&CK identifiers mentioned in the article, plus publication times displayed in each reader?s timezone; identifiers are not IOCs or proof of exploitation.
- A defanged IOC preview behind click-to-reveal spoiler text, with an explicit count when entries are omitted. No files are attached to Discord messages. A true interactive dropdown requires a Discord application and interaction handling.
- Retrieval coverage and AI/fallback status remain in local JSON reports; full JSON and CSV reports are available through `--dry-run`.

IOC extraction is deterministic and separate from the model. It finds MD5/SHA-1/SHA-256, IPv4/IPv6, domains, URLs and email addresses, including common defanging. Every match is an **unvalidated candidate**, not necessarily malicious: citations, benign services, version-like strings and infrastructure shared by many customers can be false positives. Review the context before using indicators in detections; never automatically block everything in this feed. JSON contains normalized original values. Defanging is applied to IOC values in CSV and Discord previews. Summary/excerpt punctuation, version numbers, filenames, ATT&CK IDs, reference links and CSV evidence keep their normal formatting.

The AI must provide an exact supporting source substring for each claim. Missing evidence is rejected, but substring validation cannot prove a claim follows logically from its evidence. Review consequential claims against the linked article. No enrichment, private telemetry, external tools or article instructions are given to the model.

## Included sources

The following feeds returned parseable entries during checks on October 9, 2026 UTC. URLs and site layouts can change; rerun diagnostics in your deployment.

| Source | Scope | Feed |
|---|---|---|
| Microsoft | Threat intelligence category | https://www.microsoft.com/en-us/security/blog/topic/threat-intelligence/feed/ |
| Google / Mandiant | Google Threat Intelligence | https://feeds.feedburner.com/threatintelligence/pvexyqv7v0v |
| Proofpoint | Threat Insight | https://www.proofpoint.com/us/threat-insight-blog.xml |
| Huntress | Broad blog; includes non-research articles | https://www.huntress.com/blog/rss.xml |
| SOCRadar | Broad blog | https://socradar.io/feed/ |
| Cisco Talos | Research and team blog | https://blog.talosintelligence.com/rss/ |
| Palo Alto Unit 42 | Threat research | https://unit42.paloaltonetworks.com/feed/ |
| ESET WeLiveSecurity | Research and security news | https://www.welivesecurity.com/en/rss/feed/ |
| SentinelLabs | Threat research | https://www.sentinelone.com/labs/feed/ |
| Securelist | Kaspersky research | https://securelist.com/feed/ |

CISA advisories are included **disabled** because the feed returned HTTP 403 in this environment. Do not treat that as an empty feed. Enable it only after a successful check from your host. Additional future candidates: CERT-EU, CERT/CC, The DFIR Report, Volexity, Elastic Security Labs, Red Canary, Rapid7 and Sophos X-Ops. Their adapters are not included or claimed tested.

To change sources, edit `config/sources.json`. Set `enabled` to false to disable one. `hosts` must explicitly include every permitted feed, redirect and article hostname. Do not add arbitrary hosts from article content. Google’s FeedBurner address is linked from its official Threat Intelligence page.

## Start locally on Windows

1. Install Python 3.11 or newer from https://www.python.org/downloads/ if needed. Include the Python launcher.
2. Extract the ZIP into a permanent folder such as `C:\Tools\discord-osint-bot`. Open PowerShell in that folder.
3. Run the offline tests and live feed check:

   ```powershell
   py -3 -m unittest -v
   py -3 bot.py --check-feeds
   ```

4. Create a private test channel in a Discord server where you can manage webhooks. In channel settings, use **Integrations → Webhooks → New Webhook**, select the channel, name it OSINT Digest, and copy its URL. Treat the URL like a password.
5. Copy `.env.example` to `.env`, then edit `.env` in a text editor:

   ```powershell
   Copy-Item .env.example .env
   notepad .env
   ```

   Set `DISCORD_WEBHOOK_URL` to the copied URL. Leave `AI_PROVIDER=none` for the first test. Never upload `.env` to GitHub or paste the webhook/API keys in a chat.

6. Preview up to three articles locally, without posting or changing delivery state:

   ```powershell
   py -3 bot.py --test-mode --max-posts 3 --dry-run
   ```

   Open the JSON and CSV files in `preview`. With AI enabled, a dry run still calls that AI provider. `--check-feeds` never calls AI.

7. Send a small initial batch to your test channel, if desired:

   ```powershell
   py -3 bot.py --test-mode --max-posts 3
   ```

   This checks **every enabled feed** and attempts up to three articles. Test mode allows repeats. Successful posts are recorded; failed test attempts do not create or change normal retries.

8. Run `py -3 bot.py` for normal collection. Every enabled source is checked, and all unsent articles and due retries are processed. Previously delivered URLs are skipped.

On macOS/Linux, use `python3` instead of `py -3`; the rest is the same.

## Original CLI: normal collection and limited tests

The desktop and server apply their saved **Articles per source** limit and a **48-hour publication window** to normal collection. Dev previews, AI tests, and manual resend tests can choose a lookback of 1-365 days; normal and automatic checks remain unchanged. For a 30-day CLI preview, use `py -3 bot.py --dry-run --max-age-hours 720 --per-source-limit 5`. Sending with a window over 48 hours requires `--test-mode`. The original CLI defaults below remain available; to apply the same rules there, use `py -3 bot.py --per-source-limit 5 --max-age-hours 48`.

With your provider and Discord webhook configured in `.env`, run:

```powershell
py -3 bot.py
```

Normal runs check every enabled source in `config/sources.json`, queue all available URLs without a successful delivery record, and process all eligible pending articles. Processing is sequential, with no article-count cap. Delivery history persists between runs and restarts. A failed source does not prevent the others from being checked; failed articles retain their retry delay.

The optional CLI flag `--local` publishes to `results/` with separate history in `state/local-state.json`, instead of Discord. The desktop selects this destination automatically when its webhook is blank, using its own app-data folder. Developer previews (`--dry-run`) remain separate and do not publish articles.

**First run and upgrades:** available feed articles that have never been delivered are eligible immediately. Older `baseline` records represent unsent articles, so they become eligible if still in a feed. Successfully sent records stay intact. The first normal run can therefore send many articles. Preview with `py -3 bot.py --dry-run`, or use a limited test first.

Enable Test mode explicitly for repeat articles and a limit of 1–20 attempts (default 5):

```powershell
py -3 bot.py --test-mode --max-posts 5 --dry-run
py -3 bot.py --test-mode --max-posts 5
py -3 bot.py --test-mode --max-posts 10
```

Tests also check every enabled source. They sample the first entry from each feed in source order, then the second entries, until the limit is reached, skipping duplicate URLs within the test. Repeats of previously sent articles and immediate retries are allowed. Fewer articles may be processed if feeds have fewer unique entries or fail. A successful test delivery updates history, so normal collection will skip it. Test failures do not enter or alter the normal retry queue. Previews never post or change history; configured AI still uses its quota.

`--batch N` remains an alias for `--max-posts N`, but requires `--test-mode`. The old `--backfill` option has been removed, and `MAX_POSTS` in an existing `.env` no longer limits normal runs. Remove limits from scheduled commands; use `py -3 bot.py`. Each CLI command checks once and exits; use the scheduling options below for recurring runs.

## Enable AI

### Gemini free tier

Create an API key in https://aistudio.google.com/. Check that your project and chosen model are eligible for the free tier, and leave billing disabled to prevent usage charges. In `.env`:

```dotenv
AI_PROVIDER=gemini
AI_MODEL=gemini-3.1-flash-lite
GEMINI_API_KEY=your_key_here
```

The model is configurable because availability changes. If your project hits its quota or the model/API fails, the bot sends the excerpt/IOC fallback for that article. It does not retry a paid provider or silently upgrade billing. Free-tier AI inputs may be used by Google to improve products; the collector sends public article text, not your Discord messages. It cannot check your billing tier from an API key.

### Test AI even when the queue is empty

After setting your provider and API key, run:

```powershell
py -3 bot.py --test-ai
```

This retrieves the first article in the first enabled feed and runs the same extraction and AI analysis used for normal posts, even if the article was already sent. To choose a publisher, use `py -3 bot.py --test-ai Unit42` (names come from `config/sources.json`).

The command prints the AI status and summary, saves the report to `preview/ai-test.json`, and saves a readable summary with supporting evidence to `preview/ai-test.txt`. It calls your configured AI provider and uses its quota. It never sends a Discord message or changes delivery history or retry delays. An AI fallback counts as a failed test and returns a nonzero exit code. Each test replaces these two preview files.

A normal `py -3 bot.py` run only processes eligible queued articles; enabling AI does not regenerate previously sent posts. Use `--test-ai` to verify AI without resetting the queue.

### Local AI

Install Ollama from https://ollama.com/ and download a model your hardware can run, for example `ollama pull qwen3:8b`. Set:

```dotenv
AI_PROVIDER=ollama
AI_MODEL=qwen3:8b
```

Ollama defaults to `http://127.0.0.1:11434` for the CLI. Set `OLLAMA_BASE_URL` to use another operator-controlled endpoint. The container wizard stores its own reachable Ollama URL; see [container connectivity](docs/CONTAINER.md#ollama-connectivity). Model files use several GB and larger contexts require additional RAM. This integration has not been tested here against a downloaded model. Do not run this mode on an ordinary ephemeral GitHub runner.

### Optional OpenAI or Claude

Set `AI_PROVIDER=openai` with `OPENAI_API_KEY`, or `AI_PROVIDER=anthropic` with `ANTHROPIC_API_KEY`. Set `AI_MODEL` to a currently available API model ID in your provider account, and `ALLOW_PAID_AI=true`. The OpenAI adapter requires Chat Completions and JSON mode support. Configure provider spending controls yourself. These adapters were implemented from official API documentation, but live credentialed calls have not been tested here.

## Schedule for free

### Option A: GitHub Actions, no always-on PC

1. Create a repository and upload the **contents** of this folder, including `.github/workflows/osint.yml`, `bot.py`, `osint_digest/`, `config/sources.json` and `tests/`. Do not upload `.env`, local previews or `.run.lock`.
2. For the documented no-runner-charge option, use a **public repository with standard GitHub-hosted runners**. Your source configuration and `state/state.json` will be public. They contain public article URLs, source status, timestamps, retry metadata and Discord message IDs, but no webhook token, API key or full article body. If that visibility is inappropriate, use a private repository and check its included minutes, or run locally.
3. Under **Settings → Secrets and variables → Actions → Secrets**, create `DISCORD_WEBHOOK_URL`; also create `GEMINI_API_KEY` if using Gemini. Store secrets only as repository secrets.
4. Under **Variables**, set `AI_PROVIDER` to `gemini` (or `none`). Optionally set `AI_MODEL`. Optional paid providers also need their own secret and `ALLOW_PAID_AI=true` variable.
5. Ensure Actions may write repository contents. Branch protection/rulesets can prevent state commits; do not weaken an existing protected project just for this bot. A separate dedicated repository is simpler.
6. Open **Actions → OSINT Digest → Run workflow** on the default branch. The first run sends all available unsent articles; later runs skip delivered URLs.
7. To enable hourly checks, set the repository variable `ENABLE_SCHEDULE` to `true` after configuring secrets. Scheduled collection is off by default. Enabled schedules check at minute 17 of each hour (UTC). For twice an hour, change cron to `17,47 * * * *`. Start hourly and watch quotas and noise before increasing frequency.
8. Check workflow results. A failed feed/article produces a failed job while other sources continue, and pending/retry state is still committed. **A failed state-persistence step needs attention** to avoid repeats on later runs.

GitHub schedules are best effort: they can be late or dropped under load, run from the default branch, and public-repository schedules can be disabled after 60 days without activity. Do not promise instant alerts. The included workflow changes state regularly, but you should still monitor it. There is no scheduled run guarantee or uptime SLA in this starter. Private repository quotas differ; paid/larger runners are not required.

The repository will accumulate state commits. This provides durable state rather than relying on an evictable cache. Only the state file is staged. Do not manually edit it while a job is running. The workflow has concurrency control; do not run separate deployments sharing one webhook unless you intend duplicate deliveries.

### Option B: Windows Task Scheduler

Create a task with an hourly trigger (or repeat every 30 minutes). Action:

- **Program/script:** full path to your Python executable (find it with `py -3 -c "import sys; print(sys.executable)"`).
- **Arguments:** `"C:\Tools\discord-osint-bot\bot.py"`.
- **Start in:** `C:\Tools\discord-osint-bot`.

Use the account that owns the folder. Enable “Run task as soon as possible after a scheduled start is missed” and “Do not start a new instance” when already running. Your PC must be on and connected; a sleeping/offline PC will not check feeds. A process lock also prevents simultaneous local runs.

On Linux, an hourly cron example is `17 * * * * /usr/bin/python3 /absolute/path/bot.py >> /absolute/path/bot.log 2>&1`. Use your actual paths.

## Reliability and limits

- Conditional RSS requests use ETag/Last-Modified when publishers provide them. HTML is retrieved only for queued articles; page redirects remain restricted to the publisher allowlist. Robots.txt is respected for article retrieval. Feed access does not grant redistribution rights; share short summaries and attribution, not full article mirrors.
- The first successful read queues all available unsent articles. A failed feed is not initialized and is retried next time.
- Newly discovered URLs are durably queued before article processing. A queue entry persists even if the article falls out of a later RSS response. A long outage can still miss items that left the RSS window before discovery.
- A URL is marked sent only after Discord acknowledges the message. Failed deliveries remain queued with bounded exponential retry delay. Discord 429 responses receive short retries.
- Delivery is **at least once**, not exactly once. A crash/network timeout after Discord accepts a post but before state is saved can create a duplicate. GitHub state-push failure can do the same. Normal repeated runs deduplicate by canonical article URL.
- This watches new URLs. It does not detect edits to already-seen articles, consolidate different publishers covering the same campaign, or reliably recognize a republished article at a new URL.
- Generic HTML extraction is imperfect. Images, screenshots, PDFs, linked IOC files and JavaScript-only content are not parsed. A challenge page with enough text can evade the basic length check; inspect early outputs. The bot never follows or probes extracted IOC URLs.
- The collector caps a page at 4 MB, IOC candidates at 2,000 and AI input at 24,000 characters (head plus tail for long articles). Coverage/truncation is labeled. All deterministic IOC extraction uses the full extracted text within the page size cap.
- Missing AI or quota exhaustion results in an excerpt, not invented sections. Missing source facts remain unstated. There is no paid fallback.
- Normal runs have no article-count cap. Only explicit Test mode limits attempts (1–20, default 5) and permits repeats. Persistent source/article failures are visible in logs and state. The queue/state has no automated retention cleanup; monitor its size if you run it long term.
- Secrets are read from the environment or untracked `.env`. Exception messages are not printed because they may contain secret URLs. Discord mentions are suppressed and CSV formula prefixes are escaped.
- This is an analyst information feed, not a malware detector, SIEM, threat-reputation verdict or automated enforcement system.

## Validation

Run `python -m unittest -v` for offline tests of IOC normalization, HTML extraction, unsupported AI evidence, failure fallback, opt-in for paid AI, feed initialization, queue persistence, deduplication, URL restrictions, Discord field limits and failed delivery recovery. See [docs/VALIDATION.md](docs/VALIDATION.md) for the checks completed with this package.

## Official references (checked October 9, 2026 UTC)

- OpenAI API pricing: https://developers.openai.com/api/docs/pricing
- OpenAI Chat Completions: https://developers.openai.com/api/reference/resources/chat/subresources/completions/methods/create
- Claude billing: https://support.claude.com/en/articles/8977456-how-do-i-pay-for-my-claude-api-usage
- Claude Messages API: https://platform.claude.com/docs/en/api/messages/create
- Gemini free/paid pricing and data use: https://ai.google.dev/gemini-api/docs/pricing
- Gemini REST generation: https://ai.google.dev/api/generate-content
- Ollama local chat API: https://docs.ollama.com/api/chat
- GitHub runner billing: https://docs.github.com/en/actions/concepts/billing-and-usage
- GitHub schedule behavior: https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule
- Discord webhook and attachment API: https://docs.discord.com/developers/resources/webhook
- Google Threat Intelligence and its official feed link: https://cloud.google.com/blog/topics/threat-intelligence
